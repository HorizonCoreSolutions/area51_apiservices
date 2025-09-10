from datetime import datetime
from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Q
from typing import Optional, Tuple, Literal
from apps.users.models import PromoCodes, PromoCodesLogs, Users


def create_code():
    pass


def redeam_code(
        user: Users,
        promo_code: str,
        bonus_type: Literal["bet", "deposit", "welcome"]
        ) -> Tuple[bool, Optional[str]]:
    """
    returns:
        is_valid, message: Tuple[bool, Optional[str]]
    """

    promo_obj = (
        PromoCodes.objects
        .filter(promo_code=promo_code, bonus__bonus_type=bonus_type+"_bonus")
        .exclude(bonus__bonus_type="automated_promos")
        .first()
    )

    if not promo_obj:
        return False, "Invalid promocode"

    now = datetime.now().date()

    if promo_obj.is_expired or promo_obj.start_date > now or promo_obj.end_date < now:
        return False, "Promo-code Expired"

    counts = (
        PromoCodesLogs.objects
        .filter(promocode=promo_obj)
        .aggregate(
            total=Count("id"),
            user_count=Count("id", filter=Q(user=user))
        )
    )

    promo_code_use_count = counts["total"]
    user_promo_code_use_count = counts["user_count"]

    if user_promo_code_use_count >= promo_obj.limit_per_user:
        return False, "Promo-code use limit exceeded"

    if promo_code_use_count >= promo_obj.usage_limit:
        return False, "Promo-code use limit exceeded"
    
    distribution = promo_obj.bonus_distribution_method
    method = PromoCodes.BonusDistributionMethod

    with transaction.atomic():
        user = Users.objects.select_for_update().get(id=user.id)

        if distribution == method.instant:
            user.balance += promo_obj.instant_bonus_amount
            user.bonus_balance += promo_obj.gold_bonus
        if distribution == method.mixture:
            user.bonus_balance += promo_obj.gold_bonus

        PromoCodesLogs.objects.create(
            user=user,
            promocode=promo_obj,
            data=timezone.now(),
            log=f"Redeam for {bonus_type}"
        )

    return True, "OK"


def verify_code(
        user: Users,
        promo_code: str,
        bonus_type: Literal["bet", "deposit", "welcome"]
        ) -> Tuple[bool, Optional[str]]:
    """
    
    returns:
        is_valid, message: Tuple[bool, Optional[str]]
    """

    promo_obj = (
        PromoCodes.objects
        .filter(promo_code=promo_code, bonus__bonus_type=bonus_type+"_bonus")
        .exclude(bonus__bonus_type="automated_promos")
        .first()
    )

    if not promo_obj:
        return False, "Invalid promocode"

    now = datetime.now().date()

    if promo_obj.is_expired or promo_obj.start_date > now or promo_obj.end_date < now:
        return False, "Promo-code Expired"

    if not user:
        promo_code_use_count = PromoCodesLogs.objects.filter(promocode=promo_obj).count()
        if promo_code_use_count >= promo_obj.usage_limit:
            return False, "Promo-code use limit exceeded"
        return True, "OK"

    counts = (
        PromoCodesLogs.objects
        .filter(promocode=promo_obj)
        .aggregate(
            total=Count("id"),
            user_count=Count("id", filter=Q(user=user))
        )
    )

    promo_code_use_count = counts["total"]
    user_promo_code_use_count = counts["user_count"]

    if user_promo_code_use_count >= promo_obj.limit_per_user:
        return False, "Promo-code use limit exceeded"

    if promo_code_use_count >= promo_obj.usage_limit:
        return False, "Promo-code use limit exceeded"

    return True, "OK"


def partial_redeam():
    pass