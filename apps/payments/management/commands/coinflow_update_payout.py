
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from django.core.management.base import BaseCommand
import time

import requests
from apps.core.file_logger import SimpleLogger
from django.db import transaction as db_transaction
from apps.payments.models import CoinFlowTransaction
from apps.payments.coinflow import CoinFlowEndpoints, CoinFlowClient
from apps.users.models import Users

logger = SimpleLogger(name='Coinflow', log_file='logs/coinflow.log').get_logger()

class Command(BaseCommand):
    
    def handle(self, *args, **kwargs):
        try:
            logger.info(" Payout Update Service: STARTED ".center(40, "-"))
            endpoint = CoinFlowEndpoints(settings.COINFLOW_API_URL)
            while True:
                logger.info(f'Payout update started at {datetime.now()}')
                cf = CoinFlowClient()
                updated = 0
                one_week_ago = timezone.now() - timedelta(days=7)
                transactions = CoinFlowTransaction.objects.filter(
                    transaction_type = CoinFlowTransaction.TransactionType.withdraw,
                    status = CoinFlowTransaction.StatusType.requested,)
                logger.info(f'Total transactions to update: {transactions.count()}')
                for transaction in transactions:
                    user = transaction.user
                    if user is None:
                        logger.warning(f"Transaction {transaction.id} has no user.")
                        continue
                    try:
                        res = requests.get(
                            endpoint.get_withdrawal.format(signature=transaction.signature),
                            headers=cf.build_payout_headers()
                        )
                    except Exception as req_err:
                        logger.error(f"Request failed for transaction {transaction.id}: {req_err}")
                        continue
                    if res.status_code not in {200, 404}:
                        logger.critical(f"Transaction get withdrawal give unespected code {res.status_code}, for signature:{transaction.signature}")
                        break
                    if res.status_code == 404:
                        transaction.status = CoinFlowTransaction.StatusType.cancelled
                        updated+=1
                        continue
                    try:
                        data = res.json()
                        withdrawal = data.get("withdrawal", {})
                        status = withdrawal.get("status")
                        
                        if status is None:
                            logger.info(f"Withdrawal status is None on 200 for CoinFlowTransaction.transaction_id = {transaction.transaction_id}")
                        
                        if status == "completed":
                            transaction.status =  CoinFlowTransaction.StatusType.paid_out
                            transaction.save()
                            updated+=1
                        if status == "failed":
                            with db_transaction.atomic():
                                user_locked = Users.objects.select_for_update().get(id=user.id)
                                user_locked.balance += transaction.amount
                                user_locked.save()
                                
                                transaction.status =  CoinFlowTransaction.StatusType.failed
                                transaction.pre_balance = user_locked.balance
                                transaction.post_balance= user_locked.balance
                                transaction.save()
                                updated+=1
                    except:
                        logger.critical(f"Data for Signature couldn't be deserialized {transaction.signature}")
                
                logger.info(f'Total transactions updated: {updated}')
                logger.info(f'Payout update ended at {datetime.now()}')
                print('Sleep for 4 hours')
                time.sleep(60*60*4)      
        except Exception as e:
            logger.exception(e)