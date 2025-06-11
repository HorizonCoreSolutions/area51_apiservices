from celery import Celery
from django.conf import settings
from celery.exceptions import Retry
from apps.acuitytec.acuitytec import AcuityTecAPI
from apps.acuitytec.models import AcuitytecUser
from apps.users.models import Users
from django.utils import timezone
from datetime import datetime

# Celery configuration
app = Celery("api_services")
app.config_from_object("django.conf:settings", namespace="CELERY")

# Retry delays: 2h, 4h, 8h, 16h, 24h (in seconds)
RETRY_DELAYS = [2 * 3600, 4 * 3600, 8 * 3600, 16 * 3600, 24 * 3600]

@app.task(bind=True, max_retries=5, queue="acuitytec_queue")
def register_or_update_user(self, ip, schedule, user_id):
    try:
        # Ensure schedule is a timezone-aware datetime object
        if isinstance(schedule, str):
            schedule = datetime.fromisoformat(schedule)
        if timezone.is_naive(schedule):
            schedule = timezone.make_aware(schedule)

        # Fetch the user
        user = Users.objects.filter(id=user_id).first()
        if user is None:
            return  # No such user

        ac = AcuityTecAPI(user=user)

        # If no AcuityTec account linked, register a new one
        if not hasattr(user, 'acuitytec_account'):
            res = ac.register_customer(ip)
            if res.get('status') == 0:
                AcuitytecUser.objects.update_or_create(
                    user=user,
                    defaults={
                        "login_ip": ip,
                        "updated": timezone.now()
                    }
                )
                return
            elif res.get('status') == -1:
                raise Exception("AcuityTec registration failed (status -1)")
            return  # Other statuses are ignored

        # Update existing AcuityTec account if schedule is newer
        acuitytec_user: AcuitytecUser = user.acuitytec_account
        if schedule < acuitytec_user.updated:
            return  # No update needed

        ip_to_use = acuitytec_user.login_ip or ip
        res = ac.register_customer(ip_to_use)
        if res.get('status') == 0:
            AcuitytecUser.objects.update_or_create(
                user=user,
                defaults={
                    "login_ip": ip_to_use,
                    "updated": timezone.now()
                }
            )
        elif res.get('status') == -1:
            raise Exception("AcuityTec update failed (status -1)")

    except Exception as exc:
        retry_count = self.request.retries
        delay = RETRY_DELAYS[retry_count] if retry_count < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
        raise self.retry(exc=exc, countdown=delay)
