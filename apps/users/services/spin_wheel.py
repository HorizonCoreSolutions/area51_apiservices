from decimal import Decimal
import random
from datetime import timedelta
from django.utils import timezone

from apps.payments.service import platform_deposit
from apps.users.models import SpintheWheelDetails, Users
from apps.core.coins import coin_matches, Coins
from apps.bets.models import Transactions, SPIN_WHEEL
from apps.bets.utils import generate_reference
from apps.users.utils import get_tz_offset


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

def process_spin_transaction(user: Users, spin_wheel: SpintheWheelDetails, now, offset: timedelta):
    # Updates user balance
    result = use_price(user, spin_wheel)
    if not result:
        raise ValueError("Failed to use price")
    user.save()

    # Save the bonus on transactions
    bonus_amount = Decimal(spin_wheel.value)
    balance = Decimal(user.balance or 0)

    t = Transactions.objects.create(
        user=user,
        journal_entry="bonus",
        amount=bonus_amount,
        status="charged",
        previous_balance=balance,
        new_balance=balance,
        description="Spin the Wheel Bonus to player",
        reference=generate_reference(user),
        bonus_type=SPIN_WHEEL,
        bonus_amount=bonus_amount,
    )

    # saves the spin with the correct date (user_date)
    t._force_created = now + offset
    t.save()
    return t

def get_spin_status(user: Users, tz_offset: str):
    tz_offset = str(tz_offset or "").strip()
    if tz_offset == "":
        tz_offset = "UTC+0:00"
        
    result = get_tz_offset(tz_offset)
    if result.get("message"):
        return {
            "success": False,
            "message": result.get("message")
        }
    
    offset: timedelta = result.get("offset") # type: ignore
    now = timezone.now()
    users_date = (now + offset).date()

    spin_wheel = Transactions.objects.filter(
        journal_entry="bonus",
        bonus_type=SPIN_WHEEL,
        created__date__gte=users_date,
        user=user
    ).order_by("-created").first()

    is_available = not bool(spin_wheel)
    next_spin = users_date
    if not is_available:
        next_spin = (spin_wheel.created + timedelta(days=1)).date()

    return {
        "success": True,
        "offset": offset,
        "now": now,
        "is_available": is_available,
        "next_spin": next_spin,
        "last_spin": spin_wheel
    }
