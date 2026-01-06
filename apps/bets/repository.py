from typing import Dict
from decimal import Decimal
from django.conf import settings
from apps.users.models import Users
from django.db.models import Q, Count, Sum
from apps.bets.models import WageringRequirement


def get_react_bonus_amount(user: Users) -> Dict:
    base = WageringRequirement.objects.filter(
        user=user,
        active=True,
        betable=False,
    )
    
    data = base.aggregate(
        amount=Count('id'),
        pool_amount=Sum('balance'),
        generated=Sum("result", filter=Q(result__isnull=False)),
    )
    oldest = base.order_by('created').first()
    if oldest:
        cycle_progress = (oldest.limit / oldest.amount) * 100
        percentage = (((oldest.played % oldest.limit) * (100 / cycle_progress)) // 1)
    else:
        cycle_progress = settings.REACTOR_MULTIPLIER
        percentage = Decimal('0.00')
    return {
        'cycle_progress': cycle_progress,
        'cycle_progress_ratio': 1,
        'next_reward': 1,
        'pool_amount': data.get('pool_amount') or 0,
        'generated': data.get('generated') or 0,
        'percentage': percentage,
    }
