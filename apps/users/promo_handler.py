from decimal import Decimal
from datetime import datetime
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Q
from apps.bets.models import Transactions
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
) -> Tuple[bool, Optional[Literal["Promo-code use limit exceeded"]]]:
    """Check global and per-user usage limits."""
    qs = PromoCodesLogs.objects.filter(promocode=promo_obj)
    counts = qs.aggregate(
        total=Count("id"),
        user_count=Count("id", filter=Q(user=user)) if user else None,
    )

    if user and counts["user_count"] >= promo_obj.limit_per_user:
        return False, "Promo-code use limit exceeded"

    if counts["total"] >= promo_obj.usage_limit:
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

    now = datetime.now().date()
    if not _is_promo_valid(promo_obj, now):
        return False, "Promo-code Expired"

    valid, msg = _check_usage_limits(promo_obj, user)
    if not valid:
        return False, msg

    with transaction.atomic():
        user = Users.objects.select_for_update().get(id=user.id)
        method = PromoCodes.BonusDistributionMethod
        
        if (
            promo_obj.bonus_distribution_method in {method.mixture, method.deposit}
            and (amount_dep is None or amount_dep <= Decimal("0.00"))
        ):
            raise ValueError(
                "Mixture and Deposit should be used with a positive deposit amount"
            )
        if amount_dep is None:
            raise ValueError(
                "Mixture and Deposit should be used with a positive deposit amount"
            )
            
        pre_balance = user.balance
        pre_gold = user.bonus_balance
        
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
            promocode=promo_obj,
            data=timezone.now(),
            log=f"Redeem for {bonus_type} Tx.id:{t.id}",  #type: ignore
        )
    
    send_player_balance_update_notification(user)

    return True, "OK"


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
