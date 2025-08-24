from celery import shared_task
from apps.users.models import BONUS_EVENTS
from celery.utils.log import get_task_logger
from django.db import transaction as transaction_db
from apps.users.models import PromoCodes, PromoCodesLogs, Users
# from apps.core.utils.tasks import RetryableTask, _retry_with_delay

logger = get_task_logger(__name__)

@shared_task(bind=True, queue="user_queue", max_retries=1)
@transaction_db.atomic
def redeam_user_event(self, event: str, user_id: int):
    
    if event not in BONUS_EVENTS.keys():
        return
    user = Users.objects.select_for_update().filter(id=user_id).first()
    
    if not user:
        logger.warning(f"Event {event}: tried to be redeamed by non existen user {user_id}")
        return

    queryset = PromoCodes.objects.filter(
        dealer=user.admin,
        bonus__bonus_type="automated_promos",
        is_expired=False,
    ).order_by("-created")
    # Process each bonus one by one
    for bonus in queryset:
        # Skip if user already redeemed this bonus
        if PromoCodesLogs.objects.filter(promocode=bonus, user=user).exists():
            continue

        if bonus.bonus_percentage is None:
            continue

        if bonus.bonus_percentage > 0:
            user.bonus_balance += bonus.instant_bonus_amount
        else:
            user.balance += bonus.instant_bonus_amount

        # Log the redemption
        PromoCodesLogs.objects.create(
            promocode=bonus,
            user=user,
            log=f"User {user.id} redeemed event {event}"
        )