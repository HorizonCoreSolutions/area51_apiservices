from decimal import Decimal
from typing import Dict

from django.db.models import Q, Count, Sum
from apps.bets.models import WageringRequirement
from apps.users.models import Users


def get_react_bonus_amount(user: Users) -> Dict:
    data = WageringRequirement.objects.filter(
        user=user,
        active=True,
        betable=False,
    ).aggregate(
        amount=Count('id'),
        pool_amount=Sum('balance'),
        generated=Sum("result", filter=Q(result__isnull=False)),
    )
    oldest = WageringRequirement.objects.filter(
        user=user,
        active=True,
        betable=False,
    ).order_by('created').values('played').first()
    percentage = ((oldest['played'] % 20) * 5) // 1 if oldest else Decimal('0.00')
    return {
        'cycly_progress': 20,
        'cycle_progress_ratio': 1,
        'next_reward': 1,
        'pool_amount': data.get('pool_amount') or 0,
        'generated': data.get('generated') or 0,
        'percentage': percentage,
    }
