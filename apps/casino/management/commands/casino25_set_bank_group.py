import json
import time
import requests

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.users.models import Users
from apps.casino.models import CasinoGameList, CasinoManagement


class Command(BaseCommand):
    help = 'Set bank group on casino25 for casino, required to run only once'

    def handle(self, *args, **kwargs):
        try:
            bank_group_id = "usd_bank_group"
            currency = "USD"
            data = {
                "jsonrpc": "2.0",
                "method": "BankGroup.Set",
                "id": settings.CASINO_25_ID,
                "params": {
                    "Id": bank_group_id,
                    "Currency": currency,
                },
            }
            content_length = str(len(json.dumps(data)))

            session = requests.Session()
            session.headers['DEBUG'] = '1'
            session.cert = settings.CASINO_25_SSLKEY_PATH
            session.headers.update({
                'Content-Type': 'application/json',
                'Content-Length': content_length,
                'Accept': 'application/json'
            })

            response = session.post(settings.CASINO_25_URL, json=data)
            print(response.json())
            print("Bank group created successfully")
        except Exception as e:
            print(response.text)
            print(f"Error setting bank group: {e}")
            raise e
    
