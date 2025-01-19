import datetime
import json
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from requests.auth import HTTPBasicAuth

from apps.users.models import Users


class Command(BaseCommand):
    help = "Refresh payment token cron"

    def handle(self, *args, **kwargs):
        try:
            while True:
                print("Token Initialized")
                url = settings.PAYMENT_API_URL
                params = {
                    "grant_type": "client_credentials",
                    "scope": "cob.write cob.read pix.write pix.read webhook.read webhook.write",
                }
                auth = HTTPBasicAuth(settings.PIX_PAYMENT_API_KEY, settings.PIX_PAYMENT_SECRET_KEY)
                response = requests.post(url, auth=auth, data=params)
                response = json.loads(response.text, strict=False)
                print(f"Access Token: {response}")
                expired_seconds = response["expires_in"]
                added_time = datetime.timedelta(seconds=expired_seconds)
                current_date_time = datetime.datetime.now()
                expires_date_time = current_date_time + added_time
                user = Users.objects.filter(is_superuser=True).first()
                if user:
                    user.payment_access_token = response["access_token"]
                    user.payment_token_expiry_in = expires_date_time
                    user.save()
                    print("Waiting for 3 minutes")
                    time.sleep(180)

        except Exception as e:
            # tb = traceback.format_exc()
            # print(tb)
            print(e)
