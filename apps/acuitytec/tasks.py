from celery import Celery
from django.conf import settings
from celery.exceptions import Retry

# Celery configuration
app = Celery("api_services")
app.config_from_object("django.conf:settings", namespace="CELERY")

# Retry delays: 2h, 4h, 8h, 16h, 24h (in seconds)
RETRY_DELAYS = [2*3600, 4*3600, 8*3600, 16*3600, 24*3600]

@app.task(bind=True, max_retries=5, queue="acuitytec_queue")
def register_user(self):
    try:
        print("here should be the code")
        # Your actual task logic goes here
        # Simulate an error for testing:
        raise Exception("Something went wrong")

    except Exception as exc:
        retry_count = self.request.retries
        delay = RETRY_DELAYS[retry_count] if retry_count < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
        raise self.retry(exc=exc, countdown=delay)
