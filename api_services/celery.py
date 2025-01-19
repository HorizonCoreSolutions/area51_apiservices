from __future__ import absolute_import, unicode_literals

import os
from celery import Celery
import dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv.read_dotenv(os.path.join(BASE_DIR + "/.env"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api_services.settings.production")

app = Celery("api_services")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()
