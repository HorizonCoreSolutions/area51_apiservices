
from celery import Celery
from django.conf import settings

# celery configurations
app = Celery("api_services")
app.config_from_object("django.conf:settings", namespace="CELERY")



@app.task(bind=True, queue="bets_queue")
def keep_busy_task(self):
    return


@app.task(bind=True, queue="bets_queue")
def create_transaction_with_countdown(self, kwargs):
    return

