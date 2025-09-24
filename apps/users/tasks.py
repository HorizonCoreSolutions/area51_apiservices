from celery import shared_task
from django.utils import timezone
from apps.bets.models import Transactions
from apps.bets.utils import generate_reference
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

    bonus = PromoCodes.objects.filter(
        is_expired=False,
        promo_code=event,
        dealer=user.admin,
        bonus__bonus_type="automated_promos",
        bonus_distribution_method=PromoCodes.BonusDistributionMethod.instant,
    ).order_by("-created").first()
    # Process each bonus one by one
    if not bonus:
        return
    # Skip if user already redeemed this bonus
    if PromoCodesLogs.objects.filter(promocode=bonus, user=user).exists():
        return

    bonus_t = 0
    gold_t = 0
    pre_balance = user.balance

    gold_t = bonus.gold_bonus
    bonus_t = bonus.instant_bonus_amount

    user.bonus_balance = bonus.gold_bonus
    user.balance = bonus.instant_bonus_amount

    user.save()

    Transactions.objects.update_or_create(
        user=user,
        status="charged",
        journal_entry="bonus",
        new_balance=user.balance,
        previous_balance=pre_balance,
        bonus_amount=bonus.gold_bonus,
        bonus_type="automated_promos",
        amount=bonus.instant_bonus_amount,
        reference=generate_reference(user=user),
        description=f"{event} bonus of {bonus.instant_bonus_amount} SC {bonus.gold_bonus} GC",
    )

    # Log the redemption
    PromoCodesLogs.objects.create(
        promocode=bonus,
        transfer=bonus_t,
        transfer_gold=gold_t,
        user=user,
        log=f"User {user.id} redeemed event {event}",
        date=timezone.now()
    )