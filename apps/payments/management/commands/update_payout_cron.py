import json
from threading import Thread
import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from apps.admin_panel.tasks import ipn_status_transaction_mail
from apps.payments.utils import create_refund_transactions
from apps.users.models import Users
from requests.auth import HTTPBasicAuth
from django.http.response import HttpResponse
import time
import requests
from django.conf import settings
from apps.payments.models import NowPaymentsTransactions, WithdrawalCurrency


class Command(BaseCommand):
    
    def handle(self, *args, **kwargs):
        try:
            while True:
                api_key = settings.NOWPAYMENTS_API_KEY 
                url = settings.NOWPAYMENTS_API_URL+"payout/"

                headers = {
                    'x-api-key': api_key,
                }

                transactions = NowPaymentsTransactions.objects.filter(transaction_type="WITHDRAWAL").exclude(payment_status__in=['FINISHED','FAILED','REJECTED'])
                for transaction in transactions:
                    response = requests.get(url+transaction.payment_id, headers=headers)
                    if response.status_code==200:
                        data = response.json()
                        status = data['withdrawals'][0]['status']
                        transaction.updated_at = data['withdrawals'][0]['updated_at']
                        if status in ['FAILED','REJECTED']:
                            user=transaction.user
                            user.balance+= transaction.price_amount
                            user.save()
                            create_refund_transactions(transaction.payment_id)
                        transaction.payment_status = status
                        transaction.save()
                        
                print(datetime.now())
                print('Sleep for 10 mins')
                time.sleep(10*60) 
        except Exception as e:
            print(e)         