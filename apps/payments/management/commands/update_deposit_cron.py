import json
import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from apps.payments.utils import checkbonus
from apps.users.models import Users
from requests.auth import HTTPBasicAuth
from django.http.response import HttpResponse
import time
import requests
from django.conf import settings
from apps.payments.models import NowPaymentsTransactions, WithdrawalCurrency


class Command(BaseCommand):
    """
    NOTE: Not required, we were using this before create ipn_callback method for getting update of payment status.
    """
    
    def handle(self, *args, **kwargs):
        try:
            while True:
                api_key = settings.NOWPAYMENTS_API_KEY 
                url = settings.NOWPAYMENTS_API_URL+"payment/"

                headers = {
                    'x-api-key': api_key,
                }
                transactions = NowPaymentsTransactions.objects.filter(transaction_type="DEPOSIT").exclude(payment_status__in=['finished','failed','refunded','expired'])
                for transaction in transactions:
                    response = requests.get(url+transaction.payment_id, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        transaction.payment_status = data['payment_status']
                        transaction.updated_at = data['updated_at']
                        if data['payment_status']=='finished':
                            user=transaction.user
                            user.balance+= transaction.price_amount
                            user.save()
                            checkbonus(transaction.payment_id)   
                        transaction.save()
                print(datetime.now())
                print('Sleep for 40 mins')
                time.sleep(60*40)      
        except Exception as e:
            print(e)    