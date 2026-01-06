from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from apps.users.models import Users
from typing import Literal, Optional, Tuple
from apps.bets.models import WageringRequirement
from apps.payments.models import BonusAbstractModel
from apps.payments.repository import amount_deposited

####################
# Deposit services #
####################

def can_deposit_limits(
    user: Users,
    amount: Decimal
) -> Tuple[bool, str]:
    if amount < 5:
        return False, "Minimum deposit is 5 SC."

    if user.weekly_dl is None or user.daily_dl is None:
        return False, "Please configure your responsible gaming first."
    
    daily, weekly, first = amount_deposited(user=user)
    first = first.replace(hour=0, minute=0, second=0, microsecond=0)
    next_date = (first + timedelta(days=7)).strftime("%Y-%m-%d") 

    mx_week = round(user.weekly_dl - weekly, 2)
    mx_day  = round(user.daily_dl - daily, 2)
    mx_depo = min(mx_week, mx_day)

    if amount > user.weekly_dl or amount > user.daily_dl:
        if mx_depo < 5:
            return False, "You have exceeded your limits. Please contact support."
        return False, f"You have exceeded your limits. You can deposit up to {mx_depo} SC"

    # weekly
    if weekly + amount > user.weekly_dl:
        if mx_depo < 5:
            return False, f"You have exceeded your weekly limits. Try again on {next_date}."
        return False, f"You can deposit up to {mx_depo} SC."

    # daily
    if daily + amount > user.daily_dl:
        if mx_depo < 5:
            return False, "You have exceeded your daily limits. Try again tomorrow."
        return False, f"You can deposit up to {mx_depo} SC."

    return True, "OK"


def platform_deposit(
    user: Users,
    is_bonus: bool,
    amount: Decimal,
    accreditable: Optional[Users],
    bonus_type: Literal["SC", "MC"],
    custom_multiplier: Optional[Decimal] = None,
    description: Optional[str] = None,
):
    """
        If is_bonos, custom_multiplier is ignored and default to x20
    """
    multiplier = custom_multiplier or Decimal(1)
    if bonus_type == "SC":
        betable = True
    elif bonus_type == "MC":
        betable = False
    
    limit = amount
    if is_bonus or bonus_type == "MC":
        limit = amount * settings.REACTOR_MULTIPLIER
    else:
        limit = amount * multiplier
    
    WageringRequirement.objects.create(
        user=user,
        limit=limit,
        amount=amount,
        balance=amount,
        betable=betable,
        accreditable=accreditable,
        description=description
    )

##################
# Bonus services #
##################

def apply_bonus(
    user: Users,
    bonus: BonusAbstractModel,
    accreditable: Optional[Users] = None,
    description: Optional[str] = None,
):
    bsc = bonus.balance
    # SC x1
    if bsc > 0:
        platform_deposit(
            user=user,
            amount=bsc,
            is_bonus=False,
            bonus_type="SC",
            accreditable=accreditable,
            custom_multiplier=Decimal(1),
            description=description,
        )
    # GC

    bgc = bonus.bonus
    user.bonus_balance += bgc
    user.save(update_fields=["bonus_balance"])

    # MC = SC x20
    mnc = bonus.miner
    if mnc > 0:
        platform_deposit(
            user=user,
            amount=mnc,
            is_bonus=True,
            bonus_type="MC",
            accreditable=accreditable,
            description=description,
        )
    
    # SC x multiplier
    if bonus.playable > 0:
        platform_deposit(
            user=user,
            amount=bonus.playable,
            is_bonus=False,
            bonus_type="SC",
            accreditable=accreditable,
            custom_multiplier=Decimal(bonus.multiplier),
            description=description,
        )