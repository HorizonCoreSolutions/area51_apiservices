from celery import Celery
from django.conf import settings

# celery configurations
app = Celery("api_services")
app.config_from_object("django.conf:settings", namespace="CELERY")



@app.task(bind=True, queue="acuitytec_queue")
def register_user(self):
    print("here is the result")
    return
