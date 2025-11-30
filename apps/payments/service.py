from typing import Optional
from decimal import Decimal
from apps.bets.models import WageringRequirement
from apps.users.models import Users


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