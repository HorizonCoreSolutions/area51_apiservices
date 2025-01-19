import base64
import json
import time
from django.utils import timezone
import datetime
from decimal import Decimal

from django.conf import settings
from django_coinpayments.models import CoinPayments
from django_coinpayments.exceptions import CoinPaymentsProviderError
from apps.bets.utils import generate_reference
from apps.payments.models import (AlchemypayOrder, MnetTransaction, NowPaymentsTransactions,
    WithdrawalRequests)

from apps.users.models import BonusPercentage, PromoCodes, Users
from apps.bets.models import Transactions, DEPOSIT, PENDING
import requests
from rest_framework import status
import pyotp

COIN_PAYMENTS = CoinPayments(settings.COINPAYMENTS_API_KEY, settings.COINPAYMENTS_API_SECRET)


def custom_create_transaction(params):
    obj = CoinPayments.get_instance()
    if params is None:
        params = {}
    if obj.ipn_url:
        params.update({'ipn_url': obj.ipn_url})
    params.update({'cmd': 'create_transaction',
                   'key': obj.publicKey,
                   'version': obj.version,
                   'format': obj.format})
    return obj.request('post', **params)


def custom_create_tx(payment=None, **kwargs):
    amount_left = payment.amount - payment.amount_paid
    params = dict(amount=amount_left, currency1=payment.currency_original,
                  currency2=payment.currency_paid)
    params.update(**kwargs)
    result = custom_create_transaction(params)
    if result['error'] == 'ok':
        result = result['result']
        timeout = timezone.now() + datetime.timedelta(seconds=result['timeout'])
        user_name = kwargs.get('buyer_name', None)
        user = Users.objects.filter(username=user_name).first()
        now = str(datetime.datetime.now())
        reference = user.username + now
        rates = COIN_PAYMENTS.rates()
        btc_rate = Decimal(rates["result"][payment.currency_paid]["rate_btc"])
        operation_rate = Decimal(rates["result"][user.currency]["rate_btc"])
        amount_btc = Decimal(result['amount']) * btc_rate
        amount = round(Decimal(amount_btc) / operation_rate, 2)
        txn = Transactions(txn_id=result['txn_id'],
                           user=user,
                           amount=amount,
                           address=result['address'],
                           confirms_needed=int(result['confirms_needed']),
                           timeout=timeout,
                           journal_entry=DEPOSIT,
                           status=PENDING,
                           reference=reference,
                           description="Coin Payment Transaction Request")
        txn.save()
    print("====CoinPayment Deposit api Response====", result)
    return result


def create_tx(payment, **kwargs):
    context = {}
    try:
        tx = custom_create_tx(payment=payment, **kwargs)
        if 'error' in tx:
            return tx
        print("transaction response", tx)
        context = {'txid': tx["txn_id"],
                   'address': tx["address"],
                   'amount': tx["amount"],
                   'qrcode_url': tx["qrcode_url"],
                   'status_url': tx["status_url"],
                   'checkout_url': tx["checkout_url"],
                   }
    except CoinPaymentsProviderError as e:
        context['error'] = e
    return context

def verify_withdrawal(payout_id):
    
    try:
        api_key = settings.NOWPAYMENTS_API_KEY
        api_url = f'https://api.nowpayments.io/v1/payout/{payout_id}/verify'
        auth_payload = {
                'email': settings.NOWPAYMENTS_EMAIL,
                'password': settings.NOWPAYMENTS_PASSWORD
            }
        auth_response = requests.post(settings.NOWPAYMENTS_API_URL  + 'auth', json=auth_payload)
        auth_response.raise_for_status()
        token = auth_response.json()['token']
        headers = {
                'x-api-key': api_key,
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token
            }
        secret_key = settings.NOW_PAYMENTS_2FA_SECRET_KEY

        totp = pyotp.TOTP(secret_key)
        verification_code = totp.now()

        payload = {
                'verification_code': verification_code
            }
        response = requests.post(api_url, headers=headers, json=payload)
        print(response.__dict__,"verification_code")
        if response.status_code == 200:
            return True
        elif response.status_code == 400:
            data = response.json()
            return data['message']
        return False
    except Exception as e:
        print(e)
        return False



def get_withdrawal_amount(currency_to,amount):
    try:
        headers = {'x-api-key': settings.NOWPAYMENTS_API_KEY}
        params = {
            'currency_from': 'USD',
            'currency_to': currency_to,
            'amount': amount
        }

        response = requests.get(settings.NOWPAYMENTS_API_URL + 'estimate', headers=headers, params=params)
        data = response.json()
        return data['estimated_amount']
    except Exception as e:
        print(e)


def createnowpaymentswithdrawal(trans_id):
    try:
        NOWPAYMENTS_API_URL = settings.NOWPAYMENTS_API_URL
        
        auth_payload = {
            'email': settings.NOWPAYMENTS_EMAIL,
            'password': settings.NOWPAYMENTS_PASSWORD
        }
        auth_response = requests.post(NOWPAYMENTS_API_URL  + 'auth', json=auth_payload)
        auth_response.raise_for_status()
        token = auth_response.json()['token']
        withdrawal = WithdrawalRequests.objects.filter(id=trans_id).first()
        amount = get_withdrawal_amount(withdrawal.currency,withdrawal.amount)
        request_payload={
            "ipn_callback_url": settings.IPN_CALLBACK_URL,
            "withdrawals": [
                {
                    "address": withdrawal.address,
                    "currency": withdrawal.currency,
                    "amount": amount,
                    "ipn_callback_url": settings.IPN_CALLBACK_URL
                }
            ]
        }
        
        headers = {
            'Content-Type': 'application/json',
            'x-api-key':settings.NOWPAYMENTS_API_KEY,
            'Accept': 'application/json',
            'Authorization': 'Bearer ' + token
        }
        payout_response = requests.post(NOWPAYMENTS_API_URL + 'payout', json=request_payload, headers=headers)
        
        if payout_response.status_code == 200:
            response_content = payout_response.content.decode('utf-8')
            response_data = json.loads(response_content)
            payout_response = response_data.get('withdrawals', [])
            print(f"####Payout Response {payout_response}", flush=True)
            if payout_response:
                for withdrawals in payout_response: 
                    payment_data = withdrawals
                    now_payment_tran = NowPaymentsTransactions.objects.create(
                            user=withdrawal.user,    
                            payment_id=payment_data['id'],
                            payment_status=payment_data['status'],
                            pay_address=payment_data['address'],
                            price_amount=payment_data['amount'],
                            pay_currency=payment_data['currency'],
                            ipn_callback_url=payment_data['ipn_callback_url'],
                            created_at=payment_data['created_at'],
                            batch_withdrawal_id=payment_data['batch_withdrawal_id'],
                            transaction_type='WITHDRAWAL',
                            requested_at=payment_data['requested_at'],
                            updated_at=payment_data['created_at']
                    )
                    
                    print(f"NOW_PAYMENT_TRANS {now_payment_tran.__dict__}", flush=True)
                    withdrawal.transaction_id = now_payment_tran.id
                    withdrawal.save()
                    if payment_data and payment_data['status'] in ['REJECTED','FAILED']:
                        return payment_data['status']
                    print(f"Now Payment Withdrawal {withdrawal.__dict__}", flush=True)
                    verification = verify_withdrawal(payment_data['batch_withdrawal_id'])
                    print(f"VErification {verification}", flush=True)
                    if verification == True:
                        return True
                    return verification
                return True
        elif payout_response.status_code == 400:
            response_content = payout_response.content.decode('utf-8')
            response_data = json.loads(response_content)
            payout_response = response_data.get('message', [])
            return payout_response   
        return False
    except Exception as e:
        print(e)
        return False 
                
               
               
def get_min_amount(currency_from):
    try:
        headers = {'x-api-key': settings.NOWPAYMENTS_API_KEY}
        params = {
            'currency_from': currency_from,
            'fiat_equivalent': 'USD'
        }

        response = requests.get(settings.NOWPAYMENTS_API_URL + 'min-amount', headers=headers, params=params)
        data = response.json()
        return data
    except Exception as e:
        print(e)
        

def checkbonus(payment_id, payment_through="nowpayment"):
    try:
        if payment_through == "nowpayment":
            payment = NowPaymentsTransactions.objects.filter(payment_id=payment_id).first()
            player = payment.user
            deposit_count_np = NowPaymentsTransactions.objects.filter(user=player,transaction_type='DEPOSIT',created__date=datetime.date.today()).count()
            deposit_bonus_given_count = Transactions.objects.filter(user=player, journal_entry='deposit', created__date=datetime.date.today()).count() + deposit_count_np + 1
            delta=payment.price_amount
        elif payment_through == "alchemypay":
            payment = AlchemypayOrder.objects.filter(id=payment_id).first()
            player = payment.user
            deposit_count_alchemypay = AlchemypayOrder.objects.filter(user=player,status="finished", created__date=datetime.date.today()).count()
            delta=payment.amount
        elif payment_through == "mnet":
            payment = MnetTransaction.objects.filter(id=payment_id).first()
            player = payment.user
            delta=payment.amount
        
    
        try:
            promo_code = PromoCodes.objects.filter(promo_code=payment.applied_promo_code, bonus__bonus_type="deposit_bonus").first()
            perc = promo_code.bonus_percentage if promo_code else 0
            bonus = (Decimal(delta)/100)* Decimal(perc)
        except Exception as e:
            promo_code = None
            exception=e
        
        if promo_code:                    
            previous_balance = player.balance
            bonus_to_be_given = min(bonus, promo_code.max_bonus_limit)
            player.bonus_balance += bonus_to_be_given
            
            Transactions.objects.update_or_create(
                user=player,
                journal_entry="bonus",
                amount=delta,
                status="charged",
                previous_balance=previous_balance,
                new_balance=player.balance,
                description=f"deposit bonus of {bonus_to_be_given}",
                reference=generate_reference(player),
                bonus_type="deposit_bonus",
                bonus_amount=bonus_to_be_given
            )
            player.save()
            send_player_balance_update_notification(player)
                                        
        welcome_bonus_obj = BonusPercentage.objects.filter(bonus_type="welcome_bonus").first()    
        deposit_count_np_wl = NowPaymentsTransactions.objects.filter(user=player,transaction_type='DEPOSIT',payment_status='finished').count()
        deposit_count_alchemypay = AlchemypayOrder.objects.filter(user=player,status="finished").count()
        deposit_count_mnet = MnetTransaction.objects.filter(user=player, transaction_type=MnetTransaction.TransactionType.deposit,status=MnetTransaction.StatusType.approved).count()
        deposit_count = Transactions.objects.filter(user=player, journal_entry='deposit').count() + deposit_count_np_wl + deposit_count_alchemypay + deposit_count_mnet
        try:
            promo_obj = PromoCodes.objects.filter(promo_code=player.applied_promo_code, is_expired=False).first() if player.applied_promo_code else None
            if promo_obj and deposit_count==1 and promo_obj.bonus_distribution_method == PromoCodes.BonusDistributionMethod.deposit and promo_obj.bonus_percentage>0:
                welcome_bonus = round(Decimal(float(delta) * float(promo_obj.bonus_percentage / 100)), 2)
                previous_bal = player.balance
                bonus_to_be_given = min(welcome_bonus, promo_obj.max_bonus_limit)
                player.bonus_balance = round(Decimal(float(player.bonus_balance)+float(bonus_to_be_given)),2)
                
                Transactions.objects.update_or_create(
                    user=player,
                    journal_entry="bonus",
                    amount=delta,
                    status="charged",
                    previous_balance=previous_bal,
                    new_balance=player.balance,
                    description=f"welcome bonus of {bonus_to_be_given}",
                    reference=generate_reference(player),
                    bonus_type="welcome_bonus",
                    bonus_amount=bonus_to_be_given
                )
                player.save()
                send_player_balance_update_notification(player)
        except Exception as e:
            print(e)
                    
        if(player.affiliated_by):
            affiliate = player.affiliated_by
            aff_deposit_count = Transactions.objects.filter(user=affiliate,journal_entry='bonus',bonus_type="affiliate_bonus").count()
            if affiliate.is_lifetime_affiliate or affiliate.affliate_expire_date>datetime.now(timezone.utc):
                if affiliate.is_bonus_on_all_deposits or aff_deposit_count<affiliate.no_of_deposit_counts:
                    try:
                        if affiliate:
                            commision_percenatge = affiliate.affiliation_percentage
                            referal_bonus_balance = round(Decimal(float( affiliate.bonus_balance) + float(delta) * float(commision_percenatge / 100)), 2)
                            referal_bonus = round(Decimal( float(delta) * float(commision_percenatge/ 100)), 2)
                            previous_bal = affiliate.balance
                            if affiliate.is_redeemable_amount:
                                affiliate.balance += referal_bonus
                            elif affiliate.is_non_redeemable_amount:
                                affiliate.bonus_balance = referal_bonus_balance
                                affiliate.balance += referal_bonus
                            else:
                                affiliate.bonus_balance = referal_bonus_balance
                                affiliate.balance += referal_bonus
                            txn_amount = referal_bonus
                            bonus_to_be_given = referal_bonus
                            Transactions.objects.update_or_create(
                                user=affiliate,
                                journal_entry="bonus",
                                amount=float(delta),
                                status="charged",
                                previous_balance=previous_bal,
                                new_balance=affiliate.balance,
                                description=f"affiliate bonus by {player} on deposit of {delta}",
                                reference=generate_reference(player),
                                bonus_type="affiliate_bonus",
                                bonus_amount=bonus_to_be_given
                            )
                            affiliate.save()
                            send_player_balance_update_notification(affiliate)
                    except Exception as e:
                        print(e)
       
    except Exception as e:
        print(e)                        

def get_validate_address(address, currency):
    try:
        api_url = settings.NOWPAYMENTS_API_URL
        api_key = settings.NOWPAYMENTS_API_KEY

        headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json'
        }

        payload = {
            'address': address,
            'currency': currency,
        }

        try:
            response = requests.post(api_url+'payout/validate-address', headers=headers, json=payload)
            if response.status_code == status.HTTP_200_OK:
                return True
            else:
                return False
        except requests.exceptions.RequestException as e:
            print('Error occurred:', e)
            return None 
    except Exception as e:
        print(e)


def create_refund_transactions(id):
            try:  
                payment = NowPaymentsTransactions.objects.filter(payment_id=id).first()
                withdrawal_request = WithdrawalRequests.objects.filter(transaction = payment).first()
                admin = Users.objects.filter(role='admin').first()
                player=withdrawal_request.user
                try:
                    Transactions.objects.update_or_create(
                    user=player,
                    journal_entry="debit",
                    amount=withdrawal_request.amount,
                    status="charged",
                    merchant=admin,
                    previous_balance=player.balance-int(withdrawal_request.amount),
                    new_balance=player.balance,
                    description=f'withdrawal refund for cancelled amount {withdrawal_request.amount}',
                    reference=generate_reference(player),
                    bonus_type= None,
                    bonus_amount=0
                )
                except Exception as e:
                    print(e)
            except Exception as e:
                print(e)

import hashlib
import hmac
from typing import Dict
from apps.users.utils import send_player_balance_update_notification

def generate_hmac_signature(key: str, params: Dict[str, object]) -> str:
    # Sort the parameters and construct the string to sign
    s2s = '&'.join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None and str(v))

    # Calculate the HMAC-SHA256 signature
    data = hmac.new(key.encode(), s2s.encode(), hashlib.sha256).digest()
    hmac256Sign = data.hex().lower()

    print(f"HmacSHA256 rawContent is [{s2s}], key is [{key}], hash result is [{hmac256Sign}]")

    return hmac256Sign



def make_alchemypay_token_request(email):
    appid = settings.ALCHEMYPAY_APPID
    secretKey = settings.ALCHEMYPAY_SECRETKEY
    ALCHEMYPAY_URL =settings.ALCHEMYPAY_URL

    timestamp = str(int(time.time() * 1000))
    params = {
        "appid": appid,
        "email": email,
        "timestamp": timestamp
    }
    sign = generate_hmac_signature(secretKey, params)
    try:
        headers = {
            "accept": "application/json",
            "appId": appid,
            "timestamp": timestamp,
            "sign": sign,
            "content-type": "application/json"
        }
        payload = {"email": email}

        response = requests.post(ALCHEMYPAY_URL+'getToken',
                                 json=payload,
                                 headers=headers)
        if response.status_code == status.HTTP_200_OK:
                response_data = response.json()
                access_token = response_data.get('data', {}).get('accessToken', '')
                return access_token
        else:
             return False
    except Exception as e:
        print(e)


def get_payment_address(payload):
    NOWPAYMENTS_API_KEY = settings.NOWPAYMENTS_API_KEY
    NOWPAYMENTS_API_URL = settings.NOWPAYMENTS_API_URL
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-API-Key': NOWPAYMENTS_API_KEY,
    }
    
    response = requests.post(NOWPAYMENTS_API_URL + 'payment', json=payload, headers=headers)
    
    if response.status_code == status.HTTP_201_CREATED:
        payment_data = response.json()
        pay_address=payment_data['pay_address']
        return pay_address
    else:
         return False
