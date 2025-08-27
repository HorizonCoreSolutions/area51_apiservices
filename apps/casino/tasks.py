import requests
from decimal import Decimal
from celery import shared_task
from django.conf import settings
from rest_framework import status
from apps.users.utils import refund_transactions
from apps.users.models import OffMarketTransactions
from django.db import transaction as db_transaction

# Retry delays in seconds
RETRY_DELAYS = [12, 22, 67]

class RetryableTransactionError(Exception):
    """Raised when transaction should be retried."""

@shared_task(bind=True, queue="casino_queue", max_retries=3)
def task_update_offmarket_transaction(self, transaction_id):
    transaction = OffMarketTransactions.objects.filter(
        id= transaction_id,
        status='Pending',
        transaction_type='DEPOSIT'
    ).first()
    
    if transaction is None:
        return
    
    try:
        params = {
            "deposit_id": transaction.txn_id,
            "secret_key": settings.OFF_MARKET_SECRETKEY,
        }

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        url = f"{settings.OFFMARKET_API_URL}read"
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()

        data = response.json().get("data", {})
        trx_status = data.get("status")
        
        # Atomic update to prevent race conditions
        with db_transaction.atomic():
            if response.status_code != status.HTTP_200_OK:
                print(f"Transaction {transaction_id}: received non-200 status {response.status_code}. Retrying.")
                raise RetryableTransactionError(f"Non-200: {response.status_code}")

            if trx_status == 'Completed':
                transaction.status = 'Completed'
            elif trx_status == 'Failed':
                user = transaction.user
                user.balance = user.balance + (Decimal(transaction.amount) - Decimal(transaction.bonus))
                user.save()
                refund_transactions(transaction.id) # type: ignore
                transaction.status = 'Failed'
            else:
                print(f"Unexpected status {trx_status} for transaction {transaction_id}")
                raise RetryableTransactionError(f"Unexpected status: {trx_status}")
            transaction.save()

    except (requests.RequestException, RetryableTransactionError) as e:
        print(f"Error updating transaction {transaction_id}: {e}")
        _retry_with_delay(self, e)
    except Exception as e:
        print(f"Unspected error updating transaction {transaction_id}: {e}")
        _retry_with_delay(self, e)


def _retry_with_delay(task_self, exc):
    retry_count = task_self.request.retries  # 0 for first retry, 1 for second, etc.
    if retry_count >= 3:  # already retried 3 times
        print(f"[Fail] Task {task_self.request.id} reached max retries ({task_self.max_retries}) and failed permanently.")
        raise exc
    delay = RETRY_DELAYS[retry_count] if retry_count < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
    print(f"[Retry] Task {task_self.request.id}: attempt {retry_count + 1} failed. Retrying in {delay} seconds.")
    raise task_self.retry(exc=exc, countdown=delay, throw=False)