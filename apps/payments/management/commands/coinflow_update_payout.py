
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from django.core.management.base import BaseCommand
import time

import requests
from apps.core.file_logger import SimpleLogger
from apps.payments.models import CoinFlowTransaction
from apps.payments.coinflow import CoinFlowEndpoints, CoinFlowClient

logger = SimpleLogger(name='Coinflow', log_file='logs/coinflow.log').get_logger()

class Command(BaseCommand):
    
    def handle(self, *args, **kwargs):
        try:
            endpoint = CoinFlowEndpoints(settings.COINFLOW_API_URL)
            while True:
                cf = CoinFlowClient()
                one_week_ago = timezone.now() - timedelta(days=7)
                transactions = CoinFlowTransaction.objects.filter(
                    transaction_type = CoinFlowTransaction.TransactionType.withdraw,
                    status = CoinFlowTransaction.StatusType.requested,)
                for transaction in transactions:
                    res = requests.get(
                        endpoint.get_withdrawal.format(signature=transaction.signature),
                        headers=cf.build_payout_headers())
                    if res.status_code not in {200, 404}:
                        logger.critical(f"Transaction get withdrawal give unespected code {res.status_code}, for signature:{transaction.signature}")
                        break
                    if res.status_code == 404:
                        transaction.status = CoinFlowTransaction.StatusType.cancelled
                    try:
                        data = res.json()
                        withdrawal = data.get("withdrawal", {})
                        status = withdrawal.get("status")
                        
                        if status is None:
                            logger.info(f"Withdrawal status is None on 200 for CoinFlowTransaction.transaction_id = {transaction.transaction_id}")
                        
                        if status == "completed":
                            transaction.status =  CoinFlowTransaction.StatusType.paid_out
                        if status == "failed":
                            transaction.status =  CoinFlowTransaction.StatusType.failed
                        transaction.save()
                    except:
                        logger.critical(f"Data for Signature couldn't be deserialized {transaction.signature}")
                print(datetime.now())
                print('Sleep for 4 hours')
                time.sleep(60*60*4)      
        except Exception as e:
            print(e)