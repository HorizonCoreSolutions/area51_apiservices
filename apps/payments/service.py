from decimal import Decimal
from datetime import timedelta
from typing import Optional, Tuple
from apps.users.models import Users
from apps.bets.models import WageringRequirement
from apps.payments.repository import amount_deposited

def can_deposit_limits(
    user: Users,
    amount: Decimal
) -> Tuple[bool, str]:
    if amount < 5:
        return False, "Minimum deposit is 5 SC."

    if user.weekly_dl is None or user.daily_dl is None:
        return False, "Set your deposit limits first."

    if amount > user.weekly_dl or amount > user.daily_dl:
        return False, "Amount is above your limits."
    
    daily, weekly, first = amount_deposited(user=user)
    first = first.replace(hour=0, minute=0, second=0, microsecond=0)
    next_date = (first + timedelta(days=7)).strftime("%Y-%m-%d") 

    mx_week = round(user.weekly_dl - weekly, 2)
    mx_day  = round(user.daily_dl - daily, 2)
    mx_depo = min(mx_week, mx_day) 

    # weekly
    if weekly + amount > user.weekly_dl:
        if mx_depo < 5:
            return False, f"Weekly limit reached. Try again on {next_date}."
        return False, f"You can deposit up to {mx_depo} SC."

    # daily
    if daily + amount > user.daily_dl:
        if mx_depo < 5:
            return False, "Daily limit reached. Try again tomorrow."
        return False, f"You can deposit up to {mx_depo} SC."

    return True, "OK"


def deposit(
    user: Users,
    amount: Decimal,
    accreditable: Optional[Users]
):
    WageringRequirement.objects.create(
        user=user,
        limit=amount,
        betable=True,
        amount=amount,
        balnce=amount,
        accreditable=accreditable
    )