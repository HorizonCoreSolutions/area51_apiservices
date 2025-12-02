from decimal import Decimal
import random
from typing import Optional
from apps.payments.service import platform_deposit
from apps.users.models import SpintheWheelDetails, Users
from apps.core.coins import coin_matches, Coins


def get_price(user: Users) -> SpintheWheelDetails:
    if not user.admin:
        raise ValueError("User does not have an admin")

    # Sort by ID for consistent ordering
    spin_wheel_details = list(SpintheWheelDetails.objects.filter(
        admin=user.admin
    ).order_by('id'))

    if not spin_wheel_details:
        raise ValueError("No spin wheel details found for this admin")

    odds = [float(detail.odds) for detail in spin_wheel_details]
    total_odds = sum(odds)
    
    if total_odds <= 0:
        raise ValueError("Odds must be greater than zero")

    # Works in Python 3.6+
    return random.choices(spin_wheel_details, weights=odds, k=1)[0]

def use_price(user: Users, price: SpintheWheelDetails) -> bool:

    if coin_matches(price.coin, Coins.GC):
        user.bonus_balance += Decimal(price.value)
        user.save()
        return True

    platform_deposit(
        user,
        is_bonus=True,
        accreditable=None,
        bonus_type=price.coin,
        amount=Decimal(price.value),
    )

    return True