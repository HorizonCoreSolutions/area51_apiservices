from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.core.concurrency import limiter
from apps.bets.models import Transactions
from django.db.models import Count, Q, Sum
from typing import Optional, Tuple, Literal
from datetime import datetime, date, timedelta
from apps.bets.utils import generate_reference
from apps.users.models import PromoCodes, PromoCodesLogs, Users
from apps.users.utils import send_player_balance_update_notification


OPEN_CODE = "validated_code"
TAKEN_CODE = "taken_code"

ErrorMessage = Literal[
    "Invalid promocode",
    "Promo-code Expired",
    "Invalid deposit amount.",
    "Promo-code use limit exceeded",
    "Too many attempts. All promo codes"
    " will be disables 60 minuts.",
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
        return True
    key = f"prmcd:uid:{user.id}" if user else f"prmcd:ip:{ip}"

    time_left = limiter.is_key_locked(key=key)
    if time_left > 0:
        return time_left

    is_allowed = limiter.allow(
        window=3600,
        key=key,
        limit=5
    )
    if not is_allowed:
        limiter.lock_key(key=key)
    return None if is_allowed else 3600


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
        "amount_redeamed": Sum("transfer", filter=Q(transfer__isnull=False)),
    }
    if user:
        agg_kwargs["user_count"] = Count("id", filter=Q(user=user))

    counts = qs.aggregate(**agg_kwargs)

    if user and counts.get("user_count", 0) >= promo_obj.limit_per_user:
        mark_expired()
        return False, "Promo-code use limit exceeded"

    if counts.get("total", 0) >= promo_obj.usage_limit:
        mark_expired()
        return False, "Promo-code use limit exceeded"
    
    amount_redeamed = counts.get("amount_redeamed") or Decimal("0")

    if amount_redeamed >= promo_obj.max_bonus_limit:
        mark_expired()
        return False, "Promo-code use limit exceeded"

    if promo_obj.bonus_distribution_method == promo_obj.BonusDistributionMethod.instant:
        if amount_redeamed + promo_obj.instant_bonus_amount > promo_obj.max_bonus_limit:
            mark_expired()
            return False, "Promo-code use limit exceeded"
    elif amount_dep:
        total = amount_redeamed + amount_dep * Decimal(promo_obj.bonus_percentage or 0)
        if (total > promo_obj.max_bonus_limit):
            mark_expired()
            return False, "Promo-code use limit exceeded"

    return True, None


def redeam_code(
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

        if not amount_dep:
            amount_dep = Decimal(0)

        pre_balance = user.balance

        amount = 0
        bonus_amount = 0

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
    bonus_type: Optional[str]
) -> bool:
    bonus_type = bonus_type or "welcome"
    if bonus_type not in {"welcome", "deposit"}:
        return False

    now = timezone.now()
    promo = PromoCodes.objects.filter(
        bonus__bonus_type=bonus_type,
        start_date__lte=now,
        end_date__gt=now,
        promo_code=promo_code,
        is_expired=False
    ).first()

    if not promo:
        return False

    # If want to remove the None
    # please remember to change all the current Nones to 0

    PromoCodesLogs.objects.create(
        date=now,
        user=user,
        transfer=None,
        promocode=promo,
        transfer_gold=None,
        log=OPEN_CODE,
    )

    return True


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
    pm: PromoCodes = promo_log.promocode  # type: ignore
    dm = pm.bonus_distribution_method

    if dm == "deposit":
        bonus = Decimal(pm.bonus_percentage) * amount / 100  # type: ignore
        g_bns = Decimal(pm.gold_percentage) * amount * settings.BONUS_MULTIPLIER / 100  # type: ignore
        pass
    elif dm == "mixture":
        bonus = Decimal(pm.bonus_percentage) * amount / 100  # type: ignore
        g_bns = pm.gold_bonus
    elif dm == "instant":
        bonus = pm.bonus
        g_bns = pm.gold_bonus
    else:
        return

    user.balance += bonus  # type: ignore
    user.bonus_balance += g_bns  # type: ignore
    user.save()

    t = Transactions.objects.create(
        user=promo_log.user,
        amount=bonus,
        gold_bonus=g_bns,
        status="charged",
        journal_entry="bonus",
        new_balance=user.balance,
        previous_balance=user.balance - bonus,
        bonus_type=pm.bonus.bonus_type,  # type: ignore
        description="Bonus for user",
        reference=generate_reference(user)
    )

    promo_log.transaction = t
    promo_log.save()


def rollback_validation_code(
    promo_log: PromoCodesLogs,
    remove_history: bool
) -> bool:
    if remove_history:
        promo_log.delete()
    return True


def verify_code(
    promo_code: str,
    ip: Optional[str] = None,
    user: Optional[Users] = None,
    bypass_limit_check: bool = False,
    bonus_type: Optional[Literal["bet", "deposit", "welcome"]] = None,
) -> Tuple[bool, Optional[str]]:
    now = datetime.now()
    if not bypass_limit_check:
        if (user or ip):
            time = _is_user_promo_banned(user, ip)
            if time is not None:
                s = time
                ftime = f"{s//3600}h "*(s>=3600) + f"{(s%3600)//60}m "*(s>=60) + f"{s%60}s"
                return False, ("Too many attempts. "
                               "All promo codes are"
                               f" disabled for {ftime}.")

    promo_obj = _get_promo(promo_code, bonus_type)

    if not promo_obj:
        return False, "Invalid promocode"

    if not _is_promo_valid(promo_obj, now):
        return False, "Promo-code Expired"

    if not bypass_limit_check:
        valid, msg = _check_usage_limits(promo_obj, user)
        if not valid:
            return False, msg

    return True, "OK"
