
from datetime import datetime, timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand
import time
from apps.payments.models import AlchemypayOrder


class Command(BaseCommand):
    
    def handle(self, *args, **kwargs):
        try:
            while True:
                one_week_ago = timezone.now() - timedelta(days=3)
                transactions = AlchemypayOrder.objects.filter(created__lte=one_week_ago,status='pending')
                for transaction in transactions:
                        transaction.status = transaction.StatusType.payfail   
                        transaction.save()
                print(datetime.now())
                print('Sleep for 12 hours')
                time.sleep(60*60*12)      
        except Exception as e:
            print(e)    