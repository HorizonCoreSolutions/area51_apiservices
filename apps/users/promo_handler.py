from decimal import Decimal
from datetime import datetime
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.bets.models import Transactions
from django.db.models import Count, Q, Sum
from typing import Optional, Tuple, Literal
from apps.bets.utils import generate_reference
from apps.users.models import PromoCodes, PromoCodesLogs, Users
from apps.users.utils import send_player_balance_update_notification


ErrorMessage = Literal[
    "Invalid promocode",
    "Promo-code Expired",
    "Promo-code use limit exceeded",
    "OK",
]


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
    now,
) -> bool:
    """Check if promo is active (not expired or out of range)."""
    if promo_obj.is_expired:
        return False
    if promo_obj.start_date is None or promo_obj.end_date is None:
        return False
    if promo_obj.start_date > now:
        return False
    if promo_obj.end_date < now:
        return False
    return True


def _check_usage_limits(
    promo_obj: PromoCodes,
    user: Optional[Users],
    amount_dep: Optional[Decimal] = None,
) -> Tuple[bool, Optional[Literal["Promo-code use limit exceeded"]]]:
    """Check global and per-user usage limits."""
    qs = PromoCodesLogs.objects.filter(promocode=promo_obj, transfer__isnull=False)

    agg_kwargs = {
        "total": Count("id"),
        "amount_redeamed": Sum("transfer", filter=Q(transfer__isnull=False)),
    }
    if user:
        agg_kwargs["user_count"] = Count("id", filter=Q(user=user))

    counts = qs.aggregate(**agg_kwargs)

    if user and counts.get("user_count", 0) >= promo_obj.limit_per_user:
        return False, "Promo-code use limit exceeded"

    if counts.get("total", 0) >= promo_obj.usage_limit:
        return False, "Promo-code use limit exceeded"
    
    amount_redeamed = counts.get("amount_redeamed") or Decimal("0")

    if amount_redeamed >= promo_obj.max_bonus_limit:
        return False, "Promo-code use limit exceeded"

    if promo_obj.bonus_distribution_method == promo_obj.BonusDistributionMethod.instant:
        if amount_redeamed + promo_obj.instant_bonus_amount > promo_obj.max_bonus_limit:
            return False, "Promo-code use limit exceeded"
    elif amount_dep:
        total = amount_redeamed + amount_dep * Decimal(promo_obj.bonus_percentage or 0)
        if (total > promo_obj.max_bonus_limit):
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

    now = timezone.now().date()
    if not _is_promo_valid(promo_obj, now):
        return False, "Promo-code Expired"

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
            raise ValueError(
                "Mixture and Deposit should be used with a positive deposit amount"
            )
        if (
            promo_obj.bonus_distribution_method in {method.mixture, method.deposit}
            and amount_dep is None
        ):
            raise ValueError(
                "Mixture and Deposit should be used with a positive deposit amount"
            )

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
            date=timezone.now(),
            log=f"Redeem for {bonus_type} Tx.id:{t.id}",  #type: ignore
        )
    
    send_player_balance_update_notification(user)

    return True, "OK"


def claim_code(
    user: Users,
    promo_code:str
) -> bool:
    now = timezone.now()
    promo = PromoCodes.objects.filter(
        start_date__lte=now,
        end_date__gt=now,
        promo_code=promo_code,
        is_expired=False).first()

    if not promo:
        return False

    # If want to remove the None
    # please remember to change all the current Nones to 0

    PromoCodesLogs.objects.create(
        date=now,
        user=user,
        transfer=None,
        promocode=promo,
        log=f"Promo-code: {promo_code} claimed for player: {user.username}",
    )
    return True


def verify_code(
    promo_code: str,
    user: Optional[Users] = None,
    bypass_limit_check: bool = False,
    bonus_type: Optional[Literal["bet", "deposit", "welcome"]] = None,
) -> Tuple[bool, Optional[ErrorMessage]]:
    promo_obj = _get_promo(promo_code, bonus_type)
    if not promo_obj:
        return False, "Invalid promocode"

    now = datetime.now()
    if not _is_promo_valid(promo_obj, now):
        return False, "Promo-code Expired"

    if bypass_limit_check:
        valid, msg = _check_usage_limits(promo_obj, user)
        if not valid:
            return False, msg

    return True, "OK"
