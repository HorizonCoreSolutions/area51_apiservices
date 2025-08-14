from datetime import timedelta,timezone,datetime
import json
import sys
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.users.models import OffMarketGames, OffMarketTransactions
import time
import random
import requests
from rest_framework import status
from decimal import Decimal
import logging

from apps.users.utils import refund_transactions

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger("fetch_offmarket_transaction")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)  # stdout is captured by supervisor
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        try:
            while True:
                try:
                    secret_key = settings.OFF_MARKET_SECRETKEY
                    off_market_api_url = settings.OFFMARKET_API_URL
                    pending_transaction = OffMarketTransactions.objects.filter(status='Pending',transaction_type='DEPOSIT')
                    logger.info("Loop started")
                    print("Loop started", flush=True)
                    for transaction in pending_transaction:
                        try:
                            params = {
                                "deposit_id": transaction.txn_id,
                                "secret_key": secret_key,
                            }

                            headers = {
                                'Content-Type': 'application/json',
                                'Accept': 'application/json',
                            }
                            response = requests.get(off_market_api_url + 'read',params=params, headers=headers)
                            if response.status_code == status.HTTP_200_OK:
                                data = response.json()
                                trx_status = data['data']['status']
                                if trx_status == 'Completed':
                                    transaction.status = 'Completed'
                                    transaction.save()
                                elif trx_status == 'Failed':
                                    user = transaction.user
                                    user.balance = user.balance + (Decimal(transaction.amount) - Decimal(transaction.bonus))
                                    user.save()
                                    refund_transactions(transaction.id)
                                    transaction.status = 'Failed'
                                    transaction.save()    
                        except Exception as e:
                                print(e)
                    logger.info("Sleeping for 10 minutes")
                    time.sleep(60*10)             
                except Exception as e:
                    print("ERROR : ",e)  
        except Exception as e:
            print(e)