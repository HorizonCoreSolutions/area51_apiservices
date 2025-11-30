import pytz
from decimal import Decimal
from django.utils import timezone
from typing import Optional, Tuple
from apps.users.models import Users
from datetime import datetime, timedelta
from django.db.models import Q, Sum, Count, Max, Min
from apps.payments.models import CoinFlowTransaction

# Define the target timezone once
CT = pytz.timezone("America/Chicago")

def amount_deposited(user: Users) -> Tuple[Decimal, Decimal, datetime]:
    """This returnse the amount a user has deposited

    Args:
        user (Users): The user you want to retrieve the info from.

    Returns:
        Tuple[Decimal, Decimal, datetime]: daily, weekly, date_of_first_deposit_on_range
    """
    now_ct = timezone.now().astimezone(CT)
    day_start_ct = now_ct.replace(hour=0, minute=0, second=0, microsecond=0)

    day_start_utc = day_start_ct.astimezone(timezone.utc)

    week_start_ct = day_start_ct - timedelta(days=6)
    week_start_utc = week_start_ct.astimezone(timezone.utc)

    data = CoinFlowTransaction.objects.filter(
        user=user,
        status=CoinFlowTransaction.StatusType.approved,
        transaction_type=CoinFlowTransaction.TransactionType.deposit,
        created__gte=week_start_utc,
    ).aggregate(
        weekly_deposit=Sum("amount"),
        daily_deposit=Sum("amount", filter=Q(created__gte=day_start_utc)),
        date=Min("created")
    )

    # 4. Process Results
    weekly = Decimal(data["weekly_deposit"] or "0.00")
    daily = Decimal(data["daily_deposit"] or "0.00")

    return daily, weekly, (data.get("date") or now_ct)



def remaning_cooldown(user: Users) -> dict:
    WITHDRAW_STATUS = [
        CoinFlowTransaction.StatusType.requested,
        CoinFlowTransaction.StatusType.paid_out,
        CoinFlowTransaction.StatusType.pending,
        CoinFlowTransaction.StatusType.cancelled
        # CoinFlowTransaction.StatusType.failed,
    ]
    
    WITHDRAW_TYPES = [
        CoinFlowTransaction.TransactionType.withdraw,
        CoinFlowTransaction.TransactionType.withdraw_request
    ]

    qs = CoinFlowTransaction.objects.filter(
        user_id=user.id,
        transaction_type__in=WITHDRAW_TYPES,
        status__in=WITHDRAW_STATUS,
        created__gte=timezone.now()-timedelta(days=1),
        is_deleted=False
    )

    counts = qs.aggregate(
        total=Count("id"),
        requested=Count("id", filter=Q(
            transaction_type=CoinFlowTransaction.TransactionType.withdraw_request,
            status=CoinFlowTransaction.StatusType.requested
        )),
        cancelled=Count("id", filter=Q(
            transaction_type=CoinFlowTransaction.TransactionType.withdraw_request,
            status=CoinFlowTransaction.StatusType.cancelled
        )),
        latest_created_at=Max("created")
    )

    # total = proccesed + requested + failed_request
    total = counts.get("total") or 0
    # total - (requested + failed_request)
    requested = counts.get("requested") or 0
    cancelled = counts.get("cancelled") or 0
    
    latest: Optional[datetime] = counts.get("latest_created_at")
    latest = latest or timezone.now()
    
    had_procesed = total - (requested + cancelled) >= 1
    has_requested = requested >= 1
    should_request = cancelled + requested <= 2

    if ((had_procesed or has_requested)
        or not should_request):
        next_available = latest + timedelta(hours=24)
        remaining = next_available - timezone.now()
    
        return {
            "withdrawalAvailable": False,
            "time": remaining
        }

    return {"withdrawalAvailable": True, "time": 0}