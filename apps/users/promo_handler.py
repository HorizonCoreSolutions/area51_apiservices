from decimal import Decimal
from functools import wraps
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.core.concurrency import limiter
from apps.bets.models import Transactions
from django.db.models import Count, Q, Sum
from datetime import datetime, date, timedelta
from apps.bets.utils import generate_reference
from typing import Optional, Tuple, Literal,Callable, TYPE_CHECKING
from apps.users.models import PromoCodes, PromoCodesLogs, Users
from apps.users.utils import send_player_balance_update_notification

OPEN_CODE = "validated_code"
TAKEN_CODE = "taken_code"

ErrorMessage = Literal[
    "Invalid promocode",
    "Promo-code Expired",
    "Invalid deposit amount.",
    "Promo-code use limit exceeded",
    "Too many attempts. All promo codes are disabled.",
    "OK",
]


def _ensure_date(dt):
    if isinstance(dt, datetime):
        return dt.date()   # convert datetime → date
    elif isinstance(dt, date):
        return dt         # already date
    else:
        raise TypeError(f"Unexpected type: {type(dt)}")


def _get_promo(
    promo_code: str, bonus_type: Optional[str]
) -> Optional[PromoCodes]:
    """Fetch promo object with filtering rules applied."""
    filters = {"promo_code": promo_code}
    if bonus_type:
        filters["bonus__bonus_type"] = f"{bonus_type}_bonus"

    return (
        PromoCodes.objects
        .filter(**filters)
        .exclude(bonus__bonus_type="automated_promos")
        .first()
    )


def _is_promo_valid(
    promo_obj: PromoCodes,
    now
) -> bool:
    """
    Check if a promo is active (not expired or out of range).

    Args:
        promo_obj (PromoCodes): The promo code object.
        now (datetime): Current datetime for comparison.

    Returns:
        bool: True if promo is valid, False otherwise.
    """
    if promo_obj.is_expired:
        return False
    
    now = _ensure_date(now)

    # If start or end date is missing, or promo is out of range
    if (
        not promo_obj.start_date
        or not promo_obj.end_date
        or not (promo_obj.start_date <= now <= promo_obj.end_date)
    ):
        promo_obj.is_expired = True
        promo_obj.save()
        return False

    return True


def _generate_key(
    user: Optional[Users],
    ip: Optional[str]
) -> str:
    """Generate limiter key using user.id if available, otherwise ip."""
    if user is not None:
        return "prmcd:uid:{}".format(user.id)
    if ip is not None:
        return "prmcd:ip:{}".format(ip)
    return "prmcd:unknown"


def _check_key_locked(
    key: str
) -> int:
    """Return seconds left if locked, 0 if not locked. Wrap limiter API."""
    return limiter.is_key_locked(key=key)


def _is_user_promo_banned(
    user: Optional[Users],
    ip: Optional[str]
) -> Optional[int]:
    """
    Returns the amount of seconds a user is banned
    from promo codes is return is None user is not
    banned.
    """
    if user is None and ip is None:
        return None

    key = _generate_key(user=user, ip=ip)
    time_left = _check_key_locked(key=key)
    if time_left > 0:
        return time_left

    is_allowed = limiter.allow(
        window=3600,
        key=key,
        limit=5
    )
    if not is_allowed:
        limiter.lock_key(key=key)
        return 3600
    return None


def _check_usage_limits(
    promo_obj: PromoCodes,
    user: Optional[Users],
    amount_dep: Optional[Decimal] = None,
) -> Tuple[bool, Optional[Literal["Promo-code use limit exceeded"]]]:
    """Check global and per-user usage limits."""
    def mark_expired():
        promo_obj.is_expired = True
        promo_obj.save()
    qs = PromoCodesLogs.objects.filter(promocode=promo_obj, transfer__isnull=False)

    agg_kwargs = {
        "total": Count("id"),
        "amount_redeemed": Sum("transfer", filter=Q(transfer__isnull=False)),
    }
    if user:
        agg_kwargs["user_count"] = Count("id", filter=Q(user=user))

    counts = qs.aggregate(**agg_kwargs)

    if user and promo_obj.limit_per_user and counts.get("user_count", 0) >= promo_obj.limit_per_user:
        mark_expired()
        return False, "Promo-code use limit exceeded"

    if promo_obj.usage_limit and counts.get("total", 0) >= promo_obj.usage_limit:
        mark_expired()
        return False, "Promo-code use limit exceeded"
    
    amount_redeemed = counts.get("amount_redeemed") or Decimal("0")

    if promo_obj.max_bonus_limit and amount_redeemed >= promo_obj.max_bonus_limit:
        mark_expired()
        return False, "Promo-code use limit exceeded"

    if promo_obj.bonus_distribution_method == promo_obj.BonusDistributionMethod.instant:
        if amount_redeemed + promo_obj.instant_bonus_amount > promo_obj.max_bonus_limit:
            mark_expired()
            return False, "Promo-code use limit exceeded"
    elif amount_dep:
        total = amount_redeemed + amount_dep * Decimal(promo_obj.bonus_percentage or 0)
        if (total > promo_obj.max_bonus_limit):
            mark_expired()
            return False, "Promo-code use limit exceeded"

    return True, None


def redeem_code(
    user: Users,
    promo_code: str,
    amount_dep: Optional[Decimal],
    bonus_type: Literal["bet", "deposit", "welcome"],
) -> Tuple[bool, Optional[ErrorMessage]]:
    promo_obj = _get_promo(promo_code, bonus_type)
    if not promo_obj:
        return False, "Invalid promocode"

    # now = timezone.now().date()
    # if not _is_promo_valid(promo_obj, now):
    #    return False, "Promo-code Expired"

    with transaction.atomic():
        user = Users.objects.select_for_update().get(id=user.id)

        valid, msg = _check_usage_limits(promo_obj, user, amount_dep=amount_dep)
        if not valid:
            return False, msg

        method = PromoCodes.BonusDistributionMethod

        if (
            promo_obj.bonus_distribution_method in {method.mixture, method.deposit}
            and (amount_dep is None or amount_dep <= Decimal("0.00"))
        ):
            return False, "Invalid deposit amount."

        amount_dep = Decimal(amount_dep) if amount_dep else Decimal(0)

        pre_balance = user.balance

        amount = Decimal("0")
        bonus_amount = Decimal("0")

        if promo_obj.bonus_distribution_method == method.instant:
            bonus_amount = promo_obj.gold_bonus
            amount = promo_obj.instant_bonus_amount
            user.bonus_balance += promo_obj.gold_bonus
            user.balance += promo_obj.instant_bonus_amount
        elif promo_obj.bonus_distribution_method == method.mixture:
            bonus_amount = promo_obj.gold_bonus
            amount = Decimal(promo_obj.bonus_percentage or 0) * amount_dep / 100
            user.balance += amount
            user.bonus_balance += promo_obj.gold_bonus
        elif promo_obj.bonus_distribution_method == method.deposit:
            amount = Decimal(promo_obj.bonus_percentage or 0) * amount_dep / 100
            bonus_amount = amount * settings.BONUS_MULTIPLIER
            user.balance += amount
            user.bonus_balance += promo_obj.gold_bonus
        user.save()

        t = Transactions.objects.create(
            user=user,
            amount=amount,
            status="charged",
            journal_entry="bonus",
            new_balance=user.balance,
            bonus_amount=bonus_amount,
            previous_balance=pre_balance,
            bonus_type=f"{bonus_type}_bonus",
            description=f"{bonus_type} bonus for {amount}SC and {bonus_amount}GC",
            reference=generate_reference(user),
        )

        PromoCodesLogs.objects.create(
            user=user,
            transfer=amount,
            promocode=promo_obj,
            transfer_gold=bonus_amount,
            date=timezone.now(),
            log=f"Redeem for {bonus_type} Tx.id:{t.id}",  #type: ignore
        )
    
    send_player_balance_update_notification(user)

    return True, "OK"


def claim_code(
    user: Users,
    promo_code: str,
    bonus_type: str = "welcome"
) -> Optional[PromoCodesLogs]:
    if bonus_type not in {"welcome", "deposit"}:
        return None

    now = timezone.now()
    promo = PromoCodes.objects.filter(
        bonus__bonus_type=f"{bonus_type}_bonus",
        start_date__lte=now,
        end_date__gte=now,
        promo_code=promo_code,
        is_expired=False
    ).first()

    if not promo:
        return None

    # If want to remove the None
    # please remember to change all the current Nones to 0

    a = PromoCodesLogs.objects.create(
        date=now,
        user=user,
        transfer=None,
        promocode=promo,
        transfer_gold=None,
        log=OPEN_CODE,
    )

    return a


def check_validation_code(
    user: Users,
    promo_code:str
) -> Optional[PromoCodesLogs]:
    now = timezone.now()

    promo_log = PromoCodesLogs.objects.filter(
        created__gte=now - timedelta(minutes=10),
        user=user,
        transfer=None,
        transfer_gold=None,
        promocode__promo_code=promo_code,
        log=OPEN_CODE,
    ).first()
    return promo_log


def materialize(
    promo_log: PromoCodesLogs,
    amount: Decimal,
    user: Users
):
    if promo_log.transaction:
        return
    pm = promo_log.promocode
    if pm is None:
        return
    dm = pm.bonus_distribution_method

    if dm == "deposit":
        bonus = Decimal(pm.bonus_percentage or 0) * amount / 100
        g_bns = Decimal(pm.gold_percentage or 0) * amount * settings.BONUS_MULTIPLIER / 100
    elif dm == "mixture":
        bonus = Decimal(pm.bonus_percentage or 0) * amount / 100
        g_bns = Decimal(pm.gold_bonus or 0)
    elif dm == "instant":
        bonus = Decimal(pm.bonus or 0)  # type: ignore
        g_bns = Decimal(pm.gold_bonus or 0)
    else:
        return

    user.balance += bonus
    user.bonus_balance += g_bns
    user.save()

    t = Transactions.objects.create(
        user=promo_log.user,
        amount=bonus,
        status="charged",
        bonus_amount=g_bns,
        journal_entry="bonus",
        new_balance=user.balance,
        previous_balance=user.balance - bonus,
        bonus_type=pm.bonus.bonus_type,  # type: ignore
        description="Bonus for user",
        reference=generate_reference(user)
    )

    promo_log.transaction = t  # type: ignore
    promo_log.save()


def rollback_validation_code(
    promo_log: PromoCodesLogs,
    remove_history: bool
) -> bool:
    if remove_history:
        promo_log.delete()
    return True


def _format_time(s: int) -> str:
    h, m = divmod(s, 3600)
    m, s = divmod(m, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)


def rate_limit_code(func: Callable) -> Callable:
    @wraps(func)
    def wrap(**kwargs) -> Tuple[Optional[PromoCodes], Optional[str]]:
        blc: bool = kwargs.get("bypass_limit_check", False)
        user: Optional[Users] = kwargs.get("user")
        ip: Optional[str] = kwargs.get("ip")

        should_limit = not blc and (user or ip)

        if should_limit:
            time_left = _check_key_locked(
                key=_generate_key(user=user, ip=ip)
            )
            if time_left > 0:
                ftime = _format_time(s=time_left)
                return None, ("Too many attempts. "
                            "All promo codes are"
                            f" disabled for {ftime}.")

        res = func(**kwargs)

        if not should_limit or res[0] is not None:
            return res

        time = _is_user_promo_banned(user, ip)

        if time is None:
            return res

        ftime = _format_time(s=time)
        return None, ("Too many attempts. "
                    "All promo codes are"
                    f" disabled for {ftime}.")
    return wrap


def verify_code(
    *,
    promo_code: str,
    ip: Optional[str] = None,
    user: Optional[Users] = None,
    bypass_limit_check: bool = False,
    bonus_type: Optional[Literal["bet", "deposit", "welcome"]] = None,
) -> Tuple[Optional[PromoCodes], Optional[str]]:
    now = datetime.now()
    promo_obj = _get_promo(promo_code, bonus_type)

    if not promo_obj:
        return None, "Invalid promocode"

    if not _is_promo_valid(promo_obj, now):
        return None, "Promo-code Expired"

    if not bypass_limit_check:
        valid, msg = _check_usage_limits(promo_obj, user)
        if not valid:
            return None, msg

    return promo_obj, "OK"


if not TYPE_CHECKING:
    verify_code = rate_limit_code(verify_code)