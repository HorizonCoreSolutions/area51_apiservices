import random
from typing import Optional
from apps.users.models import SpintheWheelDetails, Users


def get_price(user: Users) -> SpintheWheelDetails:
    if not user.admin:
        raise ValueError("User does not have an admin")
    spin_wheel_details = SpintheWheelDetails.objects.filter(
        admin=user.admin
    )

    spin_wheel_detail = random.choice(spin_wheel_details)
    return spin_wheel_detail