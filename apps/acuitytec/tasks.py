from celery import Celery
from django.conf import settings
from celery.exceptions import Retry

from apps.acuitytec.acuitytec import AcuityTecAPI
from apps.acuitytec.models import AcuitytecUser
from apps.users.models import Users
from django.utils import timezone

# Celery configuration
app = Celery("api_services")
app.config_from_object("django.conf:settings", namespace="CELERY")

# Retry delays: 2h, 4h, 8h, 16h, 24h (in seconds)
RETRY_DELAYS = [2*3600, 4*3600, 8*3600, 16*3600, 24*3600]

@app.task(bind=True, max_retries=5, queue="acuitytec_queue")
def register_pr_update_user(self, ip, schedule, user_id):
    try:
        user = Users.objects.filter(id=user_id).first()
        if user is None:
            return

        ac = AcuityTecAPI(user=user)

        if not hasattr(user, 'acuitytec_account'):
            res = ac.register_customer(ip)
            if res['status'] == 0:
                AcuitytecUser.objects.update_or_create(
                    user=user,
                    defaults={
                        "login_ip": ip,
                        "updated": timezone.now()
                    }
                )
                return
            elif res['status'] == -1:
                raise self.retry(exc=Exception("AcuityTec registration failed (status -1)"))
            return  # Stop here if registration failed with other statuses

        acuitytec_user: AcuitytecUser = user.acuitytec_account
        if schedule < acuitytec_user.updated:
            return  # No update needed

        ip_to_use = acuitytec_user.login_ip if acuitytec_user.login_ip else ip
        res = ac.register_customer(ip_to_use)
        if res['status'] == 0:
            AcuitytecUser.objects.update_or_create(
                user=user,
                defaults={
                    "login_ip": ip_to_use,
                    "updated": timezone.now()
                }
            )
            return
        elif res['status'] == -1:
            raise self.retry(exc=Exception("AcuityTec update failed (status -1)"))
        return

    except Exception as exc:
        retry_count = self.request.retries
        delay = RETRY_DELAYS[retry_count] if retry_count < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
        raise self.retry(exc=exc, countdown=delay)


