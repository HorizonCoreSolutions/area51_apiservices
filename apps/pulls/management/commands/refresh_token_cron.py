import requests
import datetime
import time
import traceback
import json
from django.conf import settings
from django.core.management.base import BaseCommand
from apps.users.models import Users


class Command(BaseCommand):
    help = 'Refresh Casino User Token Cron'

    def handle(self, *args, **kwargs):
        try:
            while True:
                print('Token Initialized')
                username = settings.CASINO_USERNAME
                password = settings.CASINO_PASSWORD
                url = settings.CASINO_BASE_URL+"v1/auth/token?grant_type=password&response_type=token" \
                                               "&username="+username+"&password="+password
                headers = {"Content-Type": "application/json"}
                response = requests.get(url)
                response = response.json()
                print(response)
                expired_milliseconds = response["expires_in"]
                hours_added = datetime.timedelta(milliseconds=expired_milliseconds)
                current_date_time = datetime.datetime.now()
                expires_date_time = current_date_time + hours_added
                user = Users.objects.filter(is_superuser=True).first()
                if user:
                    user.casino_token = response["access_token"]
                    user.expires_in = expires_date_time
                    user.save()
                    print('Waiting for 5 hours')
                    time.sleep(18000)
                    # Revoke Token
                    headers["Authorization"] = "Bearer "+response["access_token"]
                    response = requests.delete(url, headers=headers)
                    print("Response", response)
        except Exception as e:
            #tb = traceback.format_exc()
            #print(tb)
            print(e)
