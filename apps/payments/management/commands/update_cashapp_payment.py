import json
from threading import Thread
import requests
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from apps.admin_panel.tasks import ipn_status_transaction_mail
from apps.payments.utils import checkbonus, create_refund_transactions
from apps.users.models import Users,CashAppDeatils
from requests.auth import HTTPBasicAuth
from django.http.response import HttpResponse
import time
import requests
from django.conf import settings
from apps.payments.models import NowPaymentsTransactions, WithdrawalCurrency
from apps.bets.models import Transactions
from decimal import Decimal
from apps.bets.utils import generate_reference
from urllib.parse import quote
from apps.users.utils import send_player_balance_update_notification
class Command(BaseCommand):
    
    def handle(self, *args, **kwargs):
        boot = True
        try:
            while True:
                if not boot:
                    boot = False
                    print(datetime.now())
                    print('Sleep for 10 mins')
                    time.sleep(60*10) 
                    
                to_date = datetime.today().strftime('%Y-%m-%d')
                from_date = (datetime.today() - timedelta(days=3)).strftime('%Y-%m-%d')
                url = f"{settings.OFFMARKET_API_URL}read_cashapp_requests?secret_key={settings.OFF_MARKET_SECRETKEY}&from_date={from_date}&to_date={to_date}&gmail=bitskymain@gmail.com"
                response = requests.get(url)
                print(response,"response")
                if response.status_code!=200:
                    continue

                cashapp_data = response.json()
                print(cashapp_data,"===========cashapp_data==============")
                cashapp_data = cashapp_data['data']
                for data in cashapp_data:
                    if data.get('status', None) != 'Pending':
                        continue
                    try:
                        cash_app = CashAppDeatils.objects.filter(name = data['cashapp'],is_active=True, status  = CashAppDeatils.StatusType.approved).first()
                        if not cash_app:
                            print(f'we are uable to found {data["cashapp"]}')
                            continue
                        user = cash_app.user
                        if not user:
                            continue
                        previous_bonus = user.balance
                        user.balance=user.balance + Decimal(data['amount'])
                        print(cash_app.user,"cash_app.user")                                 
                        transaction = Transactions.objects.create( 
                            user=user,
                            journal_entry="credit",
                            amount=Decimal(data['amount']),
                            status="charged",
                            previous_balance=previous_bonus,
                            new_balance=Decimal(user.balance),
                            description=f'Deposit {data["amount"]} by {user.username} in CashApp.',
                            reference=generate_reference(user),
                            payment_method = 'cashapp',
                            trans_id = data['cashapp_id'],
                            cashapp = cash_app
                        )
                        checkbonus(transaction)
                        send_player_balance_update_notification(transaction.user)
                        user.save()
                        url = f"{settings.OFFMARKET_API_URL}update_cashapp_request?secret_key={settings.OFF_MARKET_SECRETKEY}&status=Completed&cashapp_id={quote(data['cashapp_id'])}"
                        response = requests.put(url,headers={"Content-Type": "application/json"})
                        print(response.status_code)
                    except Exception as e:
                        print(e)
        except Exception as e:
            print(e)         
