import json
from threading import Thread
import time
import traceback
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from asn1crypto.ocsp import ResponseDataExtension
from humanize import activate

import pytz
import requests
from dateutil.parser import parse
from django.conf import settings
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone
from django_coinpayments.models import Payment
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets
from apps.users.utils import redis_client
from apps.admin_panel.tasks import ipn_status_transaction_mail
from apps.bets.models import PENDING, WITHDRAW, Transactions, DEPOSIT
from apps.bets.utils import generate_reference, validate_date
from apps.casino.utils import ErrorResponseMsg
from apps.core.pagination import PageNumberPagination
from apps.core.permissions import IsAgent, IsPlayer
from apps.core.rest_any_permissions import AnyPermissions
from apps.core.utils import get_user_ip_from_request, save_request
from apps.payments.coinflow import CoinFlowClient
from apps.users.models import VERIFICATION_APPROVED, CoinflowAuthState, Users, Admin, BonusPercentage, PromoCodes
from apps.casino.custom_pagination import CustomPagination
from django.db.models import OuterRef, Subquery

from apps.users.utils import send_player_balance_update_notification
from apps.payments.mnet import MnetPayment
from .models import (AlchemypayOrder, CoinFlowTransaction, CoinWithdrawal, MnetTransaction, NowPaymentsTransactions,
    WithdrawalCurrency, WithdrawalRequests)
from .serializers import (AlchemypayTransactionsSerializer, CallbackWithdrawalSerializer,
    CreatePaymentQrSerializer, CreatePaymentSerializer, CreateWithdrawalSerializer,
    CreateWithdrawalSerializerCoinpayments, MnetTransactionsSerializer,
    NowPaymentsTransactionsSerializer, RequestCoinWithdrawalSerializer)
from .utils import COIN_PAYMENTS, checkbonus, create_refund_transactions, create_tx, generate_hmac_signature, get_payment_address, make_alchemypay_token_request
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import hashlib
import hmac


class QrCodePayment(APIView):
    http_method_names = ("post",)
    permission_class = [IsPlayer]

    def post(self, request, **kwargs):
        url = settings.QR_CODE_PAYMENT_URL
        txn_id = f"{str(uuid.uuid4().hex)}123"
        amount = request.data.get('amount', None)
        if not amount:
            return Response('Amount should be given', status.HTTP_500_INTERNAL_SERVER_ERROR)
        params = {
            "txId": txn_id,
            "cobranca": {
                "calendario": {
                    "expiracao": 360,
                },
                "devedor": {
                    "cpf": "13113033756",  # user.id
                    "nome": "Victor Agostinho Melo Duarte",  # user.name
                },
                "valor": {
                    "original": float(amount),
                },
                "chave": "junior@pixbet.com",  # user.email
            },
        }
        try:
            superuser = Users.objects.filter(is_superuser=True).first()
            response = requests.post(
                url, headers={"Authorization": f"Bearer {superuser.payment_access_token}"}, json=params
            )
            print("Response", response.text)
            response = json.loads(response.text, strict=False)
        except Exception as e:
            print(e)
            return Response(
                ErrorResponseMsg.UNKNOWN_ERROR.value, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(response, status=status.HTTP_200_OK)


class NotificationsView(APIView):
    http_method_names = ("post")

    def post(self, request):
        print("*******************Payment Webhook bs2***************************")
        print(request.data)
        # serializer = UserPaymentInfoSerializer(data=post_data)
        # if serializer.is_valid():
        #     serializer.save()
        return Response({"message":"Payment Created"}, status.HTTP_200_OK)




# Coin payment GetBasicInfo
class GetBasicInfo(APIView):

    def get(self, request):
        response = COIN_PAYMENTS.get_basic_info()
        return Response(response)


# Coin Payment Get Transaction Information
class GetTxnInfo(APIView):
    http_method_names = ["post"]

    def post(self, request):
        txn_id = request.data.get("txnId")
        data = {"txid": txn_id}
        response = COIN_PAYMENTS.get_tx_info_multi(data)
        return Response(response)


# info by id
class GetWithdrawalStatus(APIView):
    http_method_names = ["post"]

    def post(self, request, txid):
        data = {"id": txid}
        response = COIN_PAYMENTS.get_withdrawal_info(data)
        amt = response["amountf"]
        txndata = {"id": txid, "amount": amt}
        if response["status"] == 0:
            return redirect("/withdrawal/not-confirmed/", txndata)
        elif response["status"] == 1:
            return redirect("/withdrawal/pending/", txndata)
        elif response["status"] == 2:
            return redirect("/withdrawal/success/", txndata)
        elif response["status"] == -1:
            return redirect("/withdrawal/cancelled/", txndata)

        return Response(response)


class GetDepositAddress(APIView):
    http_method_names = ["post"]

    def post(self, request):
        currency = request.data.get("currency")
        response = COIN_PAYMENTS.get_deposit_address({"currency": currency})
        return Response(response)


# info by id
class GetWithdrawalInfo(APIView):
    http_method_names = ["post"]

    def post(self, request):
        id = request.data.get("id")
        data = {'id': id}
        response = COIN_PAYMENTS.get_withdrawal_info(data)
        return Response(response)


class GetExchangeRates(APIView):
    http_method_names = ["post"]

    def post(self, request):
        currency = request.data.get("currency", '').upper()
        if not currency:
            return Response({"code": "CURRENCY_REQUIRED", "message": "currency parameter required"},
                            status=status.HTTP_400_BAD_REQUEST)
        result = COIN_PAYMENTS.rates()
        if "result" in result and currency in result["result"]:
            response = {
                "rate_btc": Decimal(result["result"][currency]["rate_btc"]),
                "input_currency": currency
            }
        else:
            return Response({"code": "CURRENCY_NOT_FOUND", "message": "Requested currency not found"},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(response)


class GetBalance(APIView):

    def get(self, request):
        all = request.query_params.get("all", 1)
        params = {"all": all}
        try:
            response = COIN_PAYMENTS.balances(params)
        except Exception as e:
            print("===GetBalance=== Error", e)
            return Response(ErrorResponseMsg.UNKNOWN_ERROR.value, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(response, status=status.HTTP_200_OK)


class GetCallbackAddress(APIView):
    http_method_names = ["post"]

    def post(self, request):
        amount = request.data.get("amount")
        currency = request.data.get("currency")
        ipn_url = request.data.get("ipn_url")
        label = request.data.get("label")
        eip55 = request.data.get("eip55")
        data = {
            'amount': Decimal(amount),
            'currency': currency,
            'ipn_url': ipn_url,
            'label': label,
            'eip55': eip55
        }
        try:
            response = COIN_PAYMENTS.get_callback_address(params=data)
        except Exception as e:
            print("===GetCallbackAddress=== Error", e)
            return Response(ErrorResponseMsg.UNKNOWN_ERROR.value, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(response, status=status.HTTP_200_OK)


class GetConversionInfo(APIView):
    http_method_names = ["post"]

    def post(self, request):
        id = request.data.get("id")
        data = {"id": id}
        try:
            response = COIN_PAYMENTS.get_conversion_info(params=data)
        except Exception as e:
            print("===CreateTransfer=== Error", e)
            return Response(ErrorResponseMsg.UNKNOWN_ERROR.value, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(response, status=status.HTTP_200_OK)


class GetWithdrawalHistory(APIView):

    http_method_names = ["post"]

    def post(self, request):
        print("===GetWithdrawalHistory Request Data===", request.data)
        limit = request.data.get("limit", 10)
        start = request.data.get("start")
        newer = request.data.get("newer")
        data = {
            "limit": limit,
            "start": start,
            "newer": newer
        }
        try:
            response = COIN_PAYMENTS.get_withdrawal_history(params=data)
        except Exception as e:
            print("===GetWithdrawalHistory=== Error", e)
            return Response(ErrorResponseMsg.UNKNOWN_ERROR.value, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        print("====GetWithdrawalHistory Response Data", response)
        return Response(response, status=status.HTTP_200_OK)


# Coin payment Create Transaction
class CreateTransaction(APIView):
    http_method_names = ["post"]
    permission_classes = [IsPlayer]

    def post(self, request):
        print("====CreateTransaction Request Data ====", request.data)
        amount = request.data.get("amount")
        buyer_email = request.data.get("buyer_email")
        currency2 = request.data.get("currency2")
        user = request.user
        if not user:
            return Response({"msg": "Invalid User"}, status=status.HTTP_400_BAD_REQUEST)
        buyer_name = user.username
        try:
            payment = Payment(
                currency_original=user.currency,
                currency_paid=currency2,
                amount=Decimal(amount),
                amount_paid=Decimal(0),
                status=Payment.PAYMENT_STATUS_PROVIDER_PENDING
            )
            response = create_tx(payment, buyer_name=buyer_name, buyer_email=buyer_email,
                                 ipn_url=settings.COINPAYMENTS_IPN_URL)

            if 'error' in response:
                return Response({"error": response['error']}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print("====CreateTransaction Error====", e)
            return Response(ErrorResponseMsg.UNKNOWN_ERROR.value, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        admin = Admin.objects.filter().first()
        transactions = Transactions.objects.filter(user=user, journal_entry=DEPOSIT)
        # Check if welcome bonus enable then give them welcome bonus on first deposite
        if admin.is_welcome_bonus_enabled is True and admin.is_referral_bonus_enabled is False and transactions.count() == 1:
            welcome_bonus_obj = BonusPercentage.objects.filter(bonus_type="welcome_bonus").first()
            promo_code_obj = PromoCodes.objects.filter(promo_code=user.applied_promo_code, is_expired=False).first()
            try:
                # if welcome_bonus_obj and welcome_bonus_obj.percentage > 0:
                # check if promo-code use limit is not expired and not user exceeded limit

                if promo_code_obj and not promo_code_obj.is_expired:
                    user.bonus_balance = round(Decimal(float(user.bonus_balance) + float(amount) * float(promo_code_obj.bonus_percentage / 100)), 2)
                    user.save()

            except Exception as e:
                print(e)

        # Check if referral bonus enabled and give them bonus on first deposite
        if admin.is_referral_bonus_enabled is True and admin.is_welcome_bonus_enabled is False and transactions.count() == 1:
            referral_bonus_obj = BonusPercentage.objects.filter(bonus_type="referral_bonus").first()
            try:
                if referral_bonus_obj and referral_bonus_obj.percentage > 0:
                    referred_by_user = user.referred_by
                    referred_by_user.bonus_balance = round(Decimal(float(user.bonus_balance) + float(amount) * float(referral_bonus_obj.percentage / 100)), 2)
                    referred_by_user.save()

            except Exception as e:
                print(e)

        return Response(response, status=status.HTTP_200_OK)


# Player can request for coin withdrawal
class RequestCoinWithdrawal(APIView):
    http_method_names = ["post"]
    permission_classes = [IsPlayer]

    def post(self, request):
        print("====RequestCoinWithdrawal Request Data====", request.data)
        player = request.user
        if not player:
            return Response({"error": "Invalid Player","result":[]}, status=status.HTTP_400_BAD_REQUEST)
        validation = RequestCoinWithdrawalSerializer(data=request.data)
        if not validation.is_valid():
            return Response(validation.errors, status=status.HTTP_400_BAD_REQUEST)
        amount = request.data.get("amount", 0.0)
        currency = request.data.get("currency")
        address = request.data.get("address")
        verification_code = request.data.get("verification_code")

        with transaction.atomic():
            # verification = verification_checks(request.user.phone_number,
            #                                    request.user.country_code,
            #                                    verification_code)
            # if not verification.ok():
            #     status_code = verification.response.status_code
            #     if verification.response.status_code == status.HTTP_401_UNAUTHORIZED \
            #             or verification.response.status_code == status.HTTP_400_BAD_REQUEST:
            #         status_code = status.HTTP_403_FORBIDDEN
            #     return Response(verification.content, status_code)

            if float(amount) > float(player.balance):
                return Response({"error": ErrorResponseMsg.INSUFFICIENT_FUNDS.value['message'], "result":[]}, status=status.HTTP_400_BAD_REQUEST)
            response = {}
            cw = CoinWithdrawal.objects.create(amount=Decimal(amount),
                                               user=player,
                                               currency=currency,
                                               currency2=player.currency,
                                               address=address,
                                               status=CoinWithdrawal.StatusType.pending)
        
            data = {
                'amount': Decimal(cw.amount),
                'currency': cw.currency,
                'address': cw.address,
                'currency2': cw.currency2,
                'auto_confirm': 1,
                'ipn_url': settings.COINPAYMENTS_IPN_URL,
            }

            response = COIN_PAYMENTS.create_withdrawal(params=data)
            if "error" in response and response["error"] == "ok" and response['result']['status'] == 1:
                cw.status = CoinWithdrawal.StatusType.complete
                cw.coin_withdraw_id = response["result"]["id"]
                cw.save()
                previous_balance = player.balance
                new_balance = round(Decimal(player.balance) - Decimal(cw.amount), 2)
                player.balance = new_balance
                now = str(datetime.now())
                reference = player.username + now
                txn = Transactions(txn_id=cw.id,
                                   user=player,
                                   amount=Decimal(cw.amount),
                                   address=cw.address,
                                   journal_entry=WITHDRAW,
                                   previous_balance=previous_balance,
                                   new_balance=new_balance,
                                   status='complete',
                                   reference=reference,
                                   description="Coin Payment Withdraw")
                txn.save()
                return Response(response, status=status.HTTP_200_OK)


            return Response(response, status=status.HTTP_400_BAD_REQUEST)


# Process Coin Payment Create Withdrawal
class CreateWithdrawalCoinpayments(APIView):
    http_method_names = ["post"]
    permission_classes = [IsAgent]

    def post(self, request):
        print("====CreateWithdrawal Request Data====", request.data)
        validation = CreateWithdrawalSerializerCoinpayments(data=request.data)
        if not validation.is_valid():
            return Response(validation.errors, status=status.HTTP_400_BAD_REQUEST)
        return validation.save()


# Cancels initiated request for coin withdrawal
class CancelWithdrawalCoinpayments(APIView):
    http_method_names = ["post"]
    permission_classes = [IsAgent]

    def post(self, request):
        print("====CancelWithdrawal Request Data===", request.data)
        validation = CallbackWithdrawalSerializer(data=request.data)
        if not validation.is_valid():
            return Response(validation.errors, status=status.HTTP_400_BAD_REQUEST)
        return validation.save()


class ConvertCoins(APIView):
    http_method_names = ["post"]

    def post(self, request):
        amount = request.data.get("amount")
        cur_from = request.data.get("from")
        to = request.data.get("to")
        address = request.data.get("address")
        dest_tag = request.data.get("dest_tag")
        data = {
            'amount': Decimal(amount),
            'from': cur_from,
            'to': to,
            'address': address,
            'dest_tag': dest_tag
        }
        response = COIN_PAYMENTS.convert_coins(params=data)
        if 'result' in response and response["result"]:
            response = response["result"]
        return Response(response)


class CreatePaymentAPIView(APIView):
    permission_classes = [IsPlayer]
    NOWPAYMENTS_API_KEY = settings.NOWPAYMENTS_API_KEY
    NOWPAYMENTS_API_URL = settings.NOWPAYMENTS_API_URL

    def post(self, request):
        data = request.data.copy()
        data['pay_currency'] = 'USD'

        serializer = CreatePaymentSerializer(data=data, context = {"user":self.request.user})
        serializer.is_valid(raise_exception=True)

        payload = serializer.validated_data
        promo_code=None
        if "promo_code" in payload:
            promo_code = payload.pop("promo_code")
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-API-Key': self.NOWPAYMENTS_API_KEY,
        }
        response = requests.post(self.NOWPAYMENTS_API_URL + 'payment', json=payload, headers=headers)
        if response.status_code == status.HTTP_201_CREATED:
                payment_data = response.json()
                user=Users.objects.filter(id=request.user.id).first()
                NowPaymentsTransactions.objects.create(
                user = user,    
                payment_id=payment_data['payment_id'],
                payment_status=payment_data['payment_status'],
                pay_address=payment_data['pay_address'],
                price_amount=payment_data['price_amount'],
                price_currency=payment_data['price_currency'],
                pay_amount=payment_data['pay_amount'],
                pay_currency=payment_data['pay_currency'],
                ipn_callback_url=payment_data['ipn_callback_url'],
                created_at=payment_data['created_at'],
                updated_at=payment_data['updated_at'],
                purchase_id=payment_data['purchase_id'],
                applied_promo_code=promo_code,
                transaction_type='DEPOSIT'
                )

                payment_data['invoice_url'] = payment_data['redirectData']['redirect_url']
                return Response(payment_data, status=status.HTTP_200_OK)
        else:
            return Response(response.json(), status=response.status_code)




class WithdrawalAPIView(APIView):
    permission_classes = [IsPlayer]
    def post(self, request):
        data = request.data
        serializer = CreateWithdrawalSerializer(data=data)
        if serializer.is_valid():
            user = Users.objects.filter(id=request.user.id).first()
            # if serializer.validated_data['amount']>user.balance:
            #     return Response({"msg": "please enter correct amount"}, status=status.HTTP_400_BAD_REQUEST)
            if serializer.validated_data['amount']>(user.balance):
                return Response({"msg": f"you cannot withdraw max amount you can withdraw {user.balance}"}, status=status.HTTP_400_BAD_REQUEST)
            WithdrawalRequests.objects.create(
                user = user,
                amount=serializer.validated_data['amount'],
                address=serializer.validated_data['address'],
                currency = serializer.validated_data['currency']
            )
        
            user.balance = user.balance-serializer.validated_data['amount']
            user.save()
            return Response({"msg": "Withdrawal Request Created"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@csrf_exempt
def ipn_callback(request):
    try:
        if request.method == 'POST':
            ipn_secret = settings.NOW_PAYMENTS_IPN_SECRET_KEY
            received_hmac = request.headers.get('x-nowpayments-sig', '')
        
            request_data = json.loads(request.body)
            
            sorted_data = dict(sorted(request_data.items(), key=lambda item: item[0]))
            sorted_data = json.dumps(sorted_data)
            sorted_data = sorted_data.replace(" ", "")
            hmac_signature = hmac.new(ipn_secret.encode('utf-8'), digestmod=hashlib.sha512)
            hmac_signature.update(sorted_data.encode('utf-8'))
            signature = hmac_signature.hexdigest()
            payment=None
            print(signature,"sig")
            print(received_hmac,"hamc")
            print(sorted_data,"sorted")
            if received_hmac == signature:
                print('matched')
                if request_data.get('payment_id') or request_data.get('invoice_id'):
                    if request_data.get('invoice_id'):
                        payment = NowPaymentsTransactions.objects.filter(invoice_id=request_data['invoice_id']).first()
                    else:
                        payment = NowPaymentsTransactions.objects.filter(payment_id=request_data['payment_id']).first()
                    if((payment) and not (request_data.get('invoice_id')) and (payment.payment_status not in ['finished','REJECTED','failed','expired','partially_paid'])):  
                        if((request_data['payment_status']=='finished') and (payment.transaction_type=='DEPOSIT')):
                            print('finished,not invoice')
                            user=payment.user
                            user.balance+= payment.price_amount
                            user.save()
                            Thread(target=ipn_status_transaction_mail,
                            args=(payment.payment_id,)).start() 
                            payment.payment_id = request_data['payment_id']
                            payment.payment_status = request_data['payment_status']
                            payment.save()
                            checkbonus(request_data['payment_id'])
                        elif((request_data['payment_status']=='partially_paid') and (payment.transaction_type=='DEPOSIT')):
                            print('partially paid,not invoice')
                            user=payment.user
                            user.balance+= Decimal(request_data['actually_paid_at_fiat'])
                            user.save()
                            Thread(target=ipn_status_transaction_mail,
                            args=(payment.payment_id,)).start() 
                            payment.payment_id = request_data['payment_id']
                            payment.price_amount = request_data['actually_paid_at_fiat']
                            payment.payment_status = request_data['payment_status']
                            payment.save()    
                            checkbonus(request_data['payment_id'])
                        payment.payment_id = request_data.get('payment_id',None)   
                        payment.payment_status = request_data['payment_status']
                        payment.save()  
                    elif((payment) and (payment.payment_status not in ['finished','REJECTED','failed','expired','partially_paid'])):  
                        if((request_data['payment_status']=='finished') and (payment.transaction_type=='DEPOSIT')):
                            print('finished,invoice')
                            user=payment.user
                            user.balance+= payment.price_amount
                            user.save()
                            Thread(target=ipn_status_transaction_mail,
                            args=(payment.payment_id,)).start() 
                            payment.payment_id = request_data['payment_id']
                            payment.payment_status = request_data['payment_status']
                            payment.pay_currency = request_data['pay_currency']
                            payment.save()
                            checkbonus(request_data['payment_id'])
                        elif((request_data['payment_status']=='partially_paid') and (payment.transaction_type=='DEPOSIT')):
                            print('partially paid,invoice')
                            user=payment.user
                            user.balance+= Decimal(request_data['actually_paid_at_fiat'])
                            user.save()
                            Thread(target=ipn_status_transaction_mail,
                            args=(payment.payment_id,)).start() 
                            payment.payment_id = request_data['payment_id']
                            payment.price_amount = request_data['actually_paid_at_fiat']
                            payment.payment_status = request_data['payment_status']
                            payment.pay_currency = request_data['pay_currency']
                            payment.save()    
                            checkbonus(request_data['payment_id'])
                        payment.payment_id = request_data.get('payment_id',None)   
                        payment.payment_status = request_data['payment_status']
                        payment.save()     
                elif request_data.get('id'):
                        payment = NowPaymentsTransactions.objects.filter(payment_id=request_data['id']).first()
                        if((payment) and (payment.payment_status not in ['FINISHED','REJECTED','FAILED','EXPIRED'])):  
                            if((request_data['status']=='FAILED') and (payment.transaction_type=='WITHDRAWAL')):
                                user=payment.user
                                user.balance+= payment.price_amount
                                user.save()
                                create_refund_transactions(payment.payment_id)
                                payment.payment_status = request_data['status']
                                payment.save()
                        elif((request_data['status']=='REJECTED') and (payment.transaction_type=='WITHDRAWAL')):
                            user=payment.user
                            user.balance+= payment.price_amount
                            user.save()    
                            create_refund_transactions(payment.payment_id)
                            payment.payment_status = request_data['status']
                            payment.save()   
                        payment.payment_status = request_data['status']
                        payment.save()       
                if payment:
                    send_player_balance_update_notification(payment.user)
                return JsonResponse({'status': 'success'}, status=200)
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=403)
        else:
            return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)
    except Exception as e:
        print(e)    

class PaymentStatusView(APIView):
    permission_class = [IsPlayer]
    NOWPAYMENTS_API_URL = settings.NOWPAYMENTS_API_URL 
    def get(self, request, payment_id):
        headers = {
            'x-api-key': settings.NOWPAYMENTS_API_KEY,
        }
        response = requests.get(self.NOWPAYMENTS_API_URL + payment_id, headers=headers)
        if response.status_code == requests.codes.ok:
            data = response.json()
            return Response(data)
        else:
            return Response({"error": "Unable to get payment status"})
        
class NowPaymentsTransaction(APIView):
    NOWPAYMENTS_API_URL = settings.NOWPAYMENTS_API_URL 
    def get(self,request):
        trans = NowPaymentsTransactions.objects.all()
        
        response =  NowPaymentsTransactionsSerializer(trans,many=True)
        return Response(response.data)


class MinAmountView(APIView):
    API_KEY = settings.NOWPAYMENTS_API_KEY
    API_URL = settings.NOWPAYMENTS_API_URL

    def get(self, request):
        currency_from = request.GET.get('currency_from', '')


        headers = {'x-api-key': self.API_KEY}
        params = {
            'currency_from': currency_from,
            'fiat_equivalent': 'USD'
        }

        response = requests.get(self.API_URL+'min-amount', headers=headers, params=params)
        data = response.json()

        return Response(data)
    

from itertools import chain

class NowPaymentsTransactionsAPI(APIView):
    """to get list of fav casino games for each user(FE)."""

    http_method_name = ["get"]
    permission_classes = (IsPlayer,)
    pagination_class = CustomPagination

    def get(self, request, **kwargs):
        try:
            player = Users.objects.filter(id=request.user.id).first()
            if player:
                transaction_filter_dict = {}
                tip_transaction_filter_dict = {
                    "user": player,
                    "description__istartswith": "tip",
                }
                from_date = self.request.query_params.get("from_date", None)
                to_date = self.request.query_params.get("to_date", None)
                activity_type = self.request.query_params.get("activity_type", None) 
                if activity_type:
                    activity_type = activity_type.upper()
                    transaction_filter_dict["transaction_type"] = activity_type
                    if activity_type.lower() != "tip":
                        # For tip transactions journal entry is credit
                        tip_transaction_filter_dict['journal_entry'] = "tip"
                timezone_offset = self.request.query_params.get("timezone_offset", None)
                if from_date and validate_date(from_date):
                    from_date = datetime.strptime(
                        from_date + " 00:00:00", "%Y-%m-%d %H:%M:%S"
                    )
                    if timezone_offset:
                        timezone_offset = float(timezone_offset)
                        if timezone_offset < 0:
                            transaction_filter_dict[
                                "created__gte"
                            ] = from_date + timedelta(
                                minutes=(-(timezone_offset) * 60)
                            )
                            tip_transaction_filter_dict[
                                "created__gte"
                            ] = from_date + timedelta(
                                minutes=(-(timezone_offset) * 60)
                            )
                        else:
                            transaction_filter_dict[
                                "created__gte"
                            ] = from_date - timedelta(minutes=(timezone_offset * 60))
                            tip_transaction_filter_dict[
                                "created__gte"
                            ] = from_date - timedelta(minutes=(timezone_offset * 60))
                    else:
                        transaction_filter_dict["created__date__gte"] = from_date
                        tip_transaction_filter_dict["created__date__gte"] = from_date

                if to_date and validate_date(to_date):
                    to_date = datetime.strptime(
                        to_date + " 23:59:59", "%Y-%m-%d %H:%M:%S"
                    )
                    if timezone_offset:
                        timezone_offset = float(timezone_offset)
                        if timezone_offset < 0:
                            transaction_filter_dict[
                                "created__lte"
                            ] = to_date + timedelta(minutes=(-(timezone_offset) * 60))
                            tip_transaction_filter_dict[
                                "created__lte"
                            ] = to_date + timedelta(minutes=(-(timezone_offset) * 60))
                        else:
                            transaction_filter_dict[
                                "created__lte"
                            ] = to_date - timedelta(minutes=(timezone_offset * 60))
                            tip_transaction_filter_dict[
                                "created__lte"
                            ] = to_date - timedelta(minutes=(timezone_offset * 60))
                nowpayments_transactions = NowPaymentsTransactions.objects.filter(user=player).order_by("-created").all()
                withdrawal_amounts = WithdrawalRequests.objects.filter(transaction_id=OuterRef('pk')).values('amount')
                nowpayments_transactions = nowpayments_transactions.annotate(withdrawal_amount=Subquery(withdrawal_amounts))
                nowpayments_transactions = nowpayments_transactions.filter(**transaction_filter_dict).order_by("-created")
                tip_tran = Transactions.objects.filter(**tip_transaction_filter_dict).order_by("-created").all()
                if tip_transaction_filter_dict.get("journal_entry"):
                    del tip_transaction_filter_dict["journal_entry"]
                tip_transaction_filter_dict["description__istartswith"]="tournament"
                tournament_transactions = Transactions.objects.filter(**tip_transaction_filter_dict).order_by("-created").all()
                tip_transaction_filter_dict["description__istartswith"]="fortunepandas"
                fortunepandas_transactions = Transactions.objects.filter(**tip_transaction_filter_dict).order_by("-created").all()
                combined_transactions = list(sorted(
                    chain(nowpayments_transactions, tip_tran, tournament_transactions, fortunepandas_transactions),
                    key=lambda obj: obj.created,
                    reverse=True
                ))
                paginator = self.pagination_class()
                try:
                    result_page = paginator.paginate_queryset(combined_transactions, request)
                except Exception as e:
                    print(e)
                    return Response({"msg": "Something went Wrong", "status_code": status.HTTP_400_BAD_REQUEST})
                serializer =  NowPaymentsTransactionsSerializer(result_page, many=True)
                return paginator.get_paginated_response(serializer.data)

            else:
                return Response({"msg": "user not found", "status_code":status.HTTP_404_NOT_FOUND})
        except Exception as e:
            print(traceback.format_exc())
            print(f"error in fetching data {e}.")
            response = {"msg": "Some Internal error.", "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR}
            return Response(response)
        
    
class WithdrawalCurrencyAPI(APIView):
        
    http_method_names = ['get']
    # Add any necessary permission classes here
    
    def get(self, request, format=None):
        headers = {'x-api-key': settings.NOWPAYMENTS_API_KEY}

        response = requests.get(settings.NOWPAYMENTS_API_URL + 'merchant/coins', headers=headers)
        if response.status_code != 200:
            return Response({"msg": "Something went Wrong", "status_code": status.HTTP_400_BAD_REQUEST}, status=status.HTTP_400_BAD_REQUEST)
        data = response.json()


        available = {
            "BTC" : "BTC",
            "ETH" : "ETH",
            "BNB": "BNB",
            "BRISE": "BRISE",
            "BSV": "BSV",
            "DGB": "DGB",
            "ILV": "ILV",
            "MIOTA": "MIOTA",
            "OMNI": "OMNI",
            "THETA": "THETA",
            "XMR": "XMR",
            "ZINU": "ZINU",
            "USDC" : "USDC",
            "USDTTRC20" : "USDT",
            "LTC" : "LTC",
            "USDTERC20" : "USDT",
            "USDTMATIC" : "USDT",
            "DOGE" : "DOGE" ,
            "PYUSD" : "PYUSD",
            "USDCMATIC" : "USDC"
        }

        currencies = data['selectedCurrencies']
        static_url_crypto = settings.DOMAIN_URL + 'static/crypto/'

        passed = []

        for currency in currencies:
            currency = currency.upper()
            if currency in available.keys():
                passed.append(
                    {
                        "code": currency,
                        "logo_url": static_url_crypto + available[currency] + '.webp',
                    }
                )
            elif currency != 'USD':
                passed.append(
                    {
                        "code": currency,
                        "logo_url": static_url_crypto + 'BTC' + '.webp',
                    }
                )



        return Response(passed, status=status.HTTP_200_OK)
    
    
class CreateNowPaymentsTestWithdrawal(APIView):
    def post(self, request,format=None):
        try:
        
            trans_id= request.data.get('trans_id', '')
            d={}
            NOWPAYMENTS_API_URL = settings.NOWPAYMENTS_API_URL

            auth_payload = {
                'email': settings.NOWPAYMENTS_EMAIL,
                'password': settings.NOWPAYMENTS_PASSWORD
            }
            auth_response = requests.post(NOWPAYMENTS_API_URL  + 'auth', json=auth_payload)
            d['auth_response']=auth_response
            auth_response.raise_for_status()
            token = auth_response.json()['token']
            withdrawal = WithdrawalRequests.objects.filter(id=trans_id).first()
            request_payload = {
                "ipn_callback_url": settings.IPN_CALLBACK_URL,
                "withdrawals": [
                    {
                        "address": withdrawal.address,
                        "currency": withdrawal.currency,
                        "amount": withdrawal.amount,
                        "ipn_callback_url": settings.IPN_CALLBACK_URL
                    }
                ]
            }

            headers = {
                'Content-Type': 'application/json',
                'x-api-key': settings.NOWPAYMENTS_API_KEY,
                'Accept': 'application/json',
                'Authorization': 'Bearer ' + token
            }
            payout_response = requests.post(NOWPAYMENTS_API_URL + 'payout', json=request_payload, headers=headers)
            response_content = payout_response.content.decode('utf-8')
            response_data = json.loads(response_content)
            payout_response = response_data.get('withdrawals', [])
            print(payout_response)
            if payout_response:
                for withdrawals in payout_response: 
                    payment_data = withdrawals
                    NowPaymentsTransactions.objects.create(
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
                    withdrawal.transaction = NowPaymentsTransactions.objects.filter(payment_id=payment_data['id']).first()
                    withdrawal.save()
                return Response({"data":payout_response},status=status.HTTP_200_OK)
            return Response(status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        

class PayoutVerification(APIView):
    def post(self, request):
        verification_code = request.data.get('verification_code')
        payout_id = request.data.get('payout_id')
        auth_payload = {
                'email': settings.NOWPAYMENTS_EMAIL,
                'password': settings.NOWPAYMENTS_PASSWORD
            }
        auth_response = requests.post(settings.NOWPAYMENTS_API_URL  + 'auth', json=auth_payload)
        auth_response.raise_for_status()
        token = auth_response.json()['token']
        
        api_url = f'https://api.nowpayments.io/v1/payout/{payout_id}/verify'
        api_key = settings.NOWPAYMENTS_API_KEY


        headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json',
             'Authorization': 'Bearer ' + token
        }

        payload = {
            'verification_code': verification_code
        }

        try:
            response = requests.post(api_url, headers=headers, json=payload)
            return Response(response)
        except requests.exceptions.RequestException as e:
            # Handle any error that occurred during the API call
            return Response({'error': str(e)}, status=500)



class GetRecentUsedAddress(APIView):
    http_method_name = ["get"]
    permission_classes = (IsPlayer,)
    def get(self, request, **kwargs):
        
        try:
            addresses_count = int(request.query_params.get("addresses_count", 5))
            currency = request.query_params.get("currency", None)
            if currency:
                player_recent_transactions = WithdrawalRequests.objects.filter(user=request.user,currency=currency).order_by('address','-created').distinct('address').values('address','currency')[:addresses_count]
                return Response({'data': player_recent_transactions}, status=200)
            return Response({'error': 'currency params not found'}, status=400)

        except Exception as e:
            return Response({'error': str(e)}, status=500)
        

class GetIsValidAddress(APIView):
    http_method_name = ["get"]
    # permission_classes = (IsPlayer,)
    def get(self, request, **kwargs):
        
        try:
            address = request.query_params.get("address", None)
            currency = request.query_params.get("currency", None)
            if currency and address:
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
                        return Response({'data': {'is_valid_address':True}}, status=200)

                    else:
                        return Response({'data': {'is_valid_address':False}}, status=200)
                except requests.exceptions.RequestException as e:
                    print('Error occurred:', e)
                    return Response({'error': str(e)}, status=500)
                
            return Response({'error': 'currency and address required'}, status=400)
        except Exception as e:
             print('Error occurred:', e)
             return Response({'error': str(e)}, status=500)


class CreatePaymentQrAPIView(APIView):
    permission_class = [IsPlayer]
    NOWPAYMENTS_API_KEY = settings.NOWPAYMENTS_API_KEY
    NOWPAYMENTS_API_URL = settings.NOWPAYMENTS_API_URL

    def post(self, request):
        data = request.data.copy()

        serializer = CreatePaymentQrSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        payload = serializer.validated_data
        promo_code=None
        if "promo_code" in payload:
            promo_code = payload.pop("promo_code")
            
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-API-Key': self.NOWPAYMENTS_API_KEY,
        }
        response = requests.post(self.NOWPAYMENTS_API_URL + 'invoice', json=payload, headers=headers)
        if response.status_code == status.HTTP_200_OK:
                payment_data = response.json()
                user=Users.objects.filter(id=request.user.id).first()
                NowPaymentsTransactions.objects.create(
                user = user,    
                invoice_id=payment_data['id'],
                price_amount=payment_data['price_amount'],
                price_currency=payment_data['price_currency'],
                ipn_callback_url=payment_data['ipn_callback_url'],
                created_at=payment_data['created_at'],
                updated_at=payment_data['updated_at'],
                pay_currency=payment_data['pay_currency'],
                payment_status='waiting',
                transaction_type='DEPOSIT',
                applied_promo_code=promo_code,
                )

                payment_data['invoice_url'] = settings.NOW_PAYMENTS_KADO_WIDGET + payment_data['id']

                return Response(payment_data, status=status.HTTP_200_OK)
        else:
            return Response(response.json(), status=response.status_code)

class Alchemypaytest(APIView):
    def post(self, request,format=None):
        try:
        
            timestamp= request.data.get('timestamp', '')
            app_id= request.data.get('app_id', '')
            sign= request.data.get('sign', '')

            headers = {
                    "accept": "application/json",
                    "appId": app_id,
                    "timestamp": timestamp,
                    "sign": sign,
                    "content-type": "application/json"
                    }
            payload = { "email": "shubhamjijais@gmail.com" }
            
            response = requests.post('https://openapi.alchemypay.org/open/api/v3/merchant/getToken',json=payload,headers=headers)
            response_content = response.content.decode('utf-8')
            response_data = json.loads(response_content)
            return Response({"data":response},status=status.HTTP_200_OK)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)



class CreateAlchemyPayOrder(APIView):
    permission_class = [IsPlayer]
    ALCHEMYPAY_URL =settings.ALCHEMYPAY_URL
    ALCHEMYPAY_APPID =settings.ALCHEMYPAY_APPID
    ALCHEMYPAY_SECRETKEY =settings.ALCHEMYPAY_SECRETKEY

    def post(self, request):
        try:
            user = Users.objects.filter(id=request.user.id).first()
            if user and not user.email:
                return Response({'error': 'Please update your email'}, status=400)
            
            amount = request.data.get('amount')
            crypto_currency = 'USDT'
            country = request.data.get('country')
            payment_method = request.data.get('payment_method')
            pay_code = request.data.get('pay_code')
            promo_code = request.data.get('promo_code')
            network = 'ETH'
            timestamp = str(int(time.time() * 1000))
            fiat_currency = "USD"
            address_payload = {
                 "price_amount": amount,
                 "price_currency": "usd",
                 "pay_currency": "USDTERC20",
                 "ipn_callback_url": settings.IPN_CALLBACK_URL,
            }
            # if not user.alchemypay_address:
            address = get_payment_address(address_payload)
            if not address:
                return Response({'error': 'error in generating address'}, status=status.HTTP_400_BAD_REQUEST)
            if promo_code:
                promo_obj = PromoCodes.objects.filter(promo_code=promo_code, bonus__bonus_type="deposit_bonus").first()
                nowpayment_promo_deposit_transactions = NowPaymentsTransactions.objects.filter(
                    user=user,
                    applied_promo_code=promo_code,
                    created__date=datetime.now().date()
                ).count()
                alchemypay_promo_deposit_transactions = AlchemypayOrder.objects.filter(
                    user=user,
                    applied_promo_code=promo_code,
                    created__date=datetime.now().date()
                ).count()
                
                if not promo_obj:
                    return Response({'error': 'Invalid promo code'}, status=status.HTTP_400_BAD_REQUEST)
                elif promo_obj.is_expired or promo_obj.end_date < timezone.now().date():
                    return Response({'error': 'Promo code expired'}, status=status.HTTP_400_BAD_REQUEST)
                elif nowpayment_promo_deposit_transactions + alchemypay_promo_deposit_transactions >= promo_obj.usage_limit:
                    return Response({'error': f"Maximum limit for using '{promo_obj.promo_code}' reached"}, status=status.HTTP_400_BAD_REQUEST)

            user.alchemypay_address = address
            user.save()
            address = user.alchemypay_address
            
            params = { 
                "address": address,
                "alpha2": country,
                "amount": amount,
                "appid": self.ALCHEMYPAY_APPID,
                "cryptoCurrency": crypto_currency,
                "depositType": 2,
                "fiatCurrency": fiat_currency,
                "redirectUrl": "https://beta.area51.casino/success",
                "callbackUrl": "https://admin.area51.casino/payments/alchemypay-callback",
                "failRedirectUrl": "https://beta.area51.casino/error",
                "side": "BUY",
                "network": network,
                "payWayCode": pay_code,
                "timestamp": timestamp
            }
            payload = {
                "address": address,
                "alpha2": country,
                "amount": amount,
                "cryptoCurrency": crypto_currency,
                "depositType": 2,
                "fiatCurrency": fiat_currency,
                "side": "BUY",
                "redirectUrl": "https://beta.area51.casino/success",
                "callbackUrl": "https://admin.area51.casino/payments/alchemypay-callback",
                "failRedirectUrl": "https://beta.area51.casino/error",
                "network": network,
                "payWayCode": pay_code
            }
            
            token = make_alchemypay_token_request(user.email)
            sign = generate_hmac_signature(self.ALCHEMYPAY_SECRETKEY, params)
            headers = {
                "accept": "application/json",
                "appId": self.ALCHEMYPAY_APPID,
                "timestamp": timestamp,
                "sign": sign,
                "access-token": token,
                "content-type": "application/json"
            }
            
            response = requests.post(self.ALCHEMYPAY_URL + 'trade/create', json=payload, headers=headers)
            
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                return Response({'error': str(e)}, status=response.status_code)
            
            payment_data = response.json()
            if payment_data.get('success'):
                trace_id = payment_data['traceId']
                data = payment_data['data']
                AlchemypayOrder.objects.create(
                    user=user,    
                    amount=amount,
                    network=network,
                    crypto_currency=crypto_currency,
                    fiat_currency=fiat_currency,
                    country=country,
                    address=address,
                    payment_method=payment_method,
                    pay_code=pay_code,
                    status=AlchemypayOrder.StatusType.pending,
                    email=user.email,
                    pay_url=data['payUrl'],
                    order_no=data['orderNo'],
                    trace_id=trace_id,
                    applied_promo_code=promo_code
                )
                return Response(payment_data, status=status.HTTP_200_OK)
            else:
                return Response(payment_data, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AlchemyPayFiatQuery(APIView):
    ALCHEMYPAY_URL = settings.ALCHEMYPAY_URL
    ALCHEMYPAY_APPID = settings.ALCHEMYPAY_APPID
    ALCHEMYPAY_SECRETKEY = settings.ALCHEMYPAY_SECRETKEY

    def post(self, request):
        try:
            timestamp = str(int(time.time() * 1000))
            params = { 
                "appid": self.ALCHEMYPAY_APPID,
                "timestamp": timestamp,
                "type": "BUY"
            }
            payload = {
                "type": "BUY"
            }
            sign = generate_hmac_signature(self.ALCHEMYPAY_SECRETKEY, params)
            headers = {
                "appId": self.ALCHEMYPAY_APPID,
                "timestamp": timestamp,
                "sign": sign,
            }
            response = requests.get(self.ALCHEMYPAY_URL + 'fiat/list', headers=headers, params=payload)
            print(response)
            response.raise_for_status()  # Raise exception if the response status is not OK
            return Response(response.json(), status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AlchemyPayCryptoQuery(APIView):
    ALCHEMYPAY_URL = settings.ALCHEMYPAY_URL
    ALCHEMYPAY_APPID = settings.ALCHEMYPAY_APPID
    ALCHEMYPAY_SECRETKEY = settings.ALCHEMYPAY_SECRETKEY

    def post(self, request):
        try:
            timestamp = str(int(time.time() * 1000))
            params = { 
                "appid": self.ALCHEMYPAY_APPID,
                "timestamp": timestamp
            }
            payload = {}
            sign = generate_hmac_signature(self.ALCHEMYPAY_SECRETKEY, params)
            headers = {
                "appId": self.ALCHEMYPAY_APPID,
                "timestamp": timestamp,
                "sign": sign,
            }
            response = requests.get(self.ALCHEMYPAY_URL + 'crypto/list', headers=headers, params=payload)
            print(response)
            response.raise_for_status()  # Raise exception if the response status is not OK
            return Response(response.json(), status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class AlchemyPayCryptoFiatQuery(APIView):
    ALCHEMYPAY_URL =settings.ALCHEMYPAY_URL
    ALCHEMYPAY_APPID =settings.ALCHEMYPAY_APPID
    ALCHEMYPAY_SECRETKEY =settings.ALCHEMYPAY_SECRETKEY

    def post(self, request):
        timestamp = str(int(time.time() * 1000))
        params = { 
                    "appid":self.ALCHEMYPAY_APPID,
                    "crypto":"USDT",
                    "network":"USDT",
                    "timestamp":timestamp  
        }
        payload={
           "crypto":"USDT",
           "network":"USDT"
        }
        sign = generate_hmac_signature(self.ALCHEMYPAY_SECRETKEY, params)
        headers = {
            "appId": self.ALCHEMYPAY_APPID,
            "timestamp": timestamp,
            "sign": sign,
        }
        response = requests.get(self.ALCHEMYPAY_URL + 'fait/info',headers=headers,params=payload)
        print(response.json(),"DATA")
        if response.status_code == status.HTTP_200_OK:
                return Response(response.json(), status=status.HTTP_200_OK)
        else:
            return Response(response.json(), status=response.status_code)
        


class AlchemypayTransactionView(APIView):
    http_method_name = ["get"]
    permission_classes = (IsPlayer,)
    pagination_class = CustomPagination

    def get(self, request, **kwargs):
        from apps.bets.utils import validate_date
        try:
            player = Users.objects.filter(id=request.user.id).first()
            if player:
                transaction_filter_dict = {}
                from_date = self.request.query_params.get("from_date", None)
                to_date = self.request.query_params.get("to_date", None)
                activity_type = self.request.query_params.get("activity_type", None)
                search = self.request.query_params.get("search", None) 
                if activity_type:
                    transaction_filter_dict["status"] = activity_type
                timezone_offset = self.request.query_params.get("timezone_offset", None)
                if from_date and validate_date(from_date):
                    from_date = datetime.strptime(
                        from_date + " 00:00:00", "%Y-%m-%d %H:%M:%S"
                    )
                    if timezone_offset:
                        timezone_offset = float(timezone_offset)
                        if timezone_offset < 0:
                            transaction_filter_dict[
                                "created__gte"
                            ] = from_date + timedelta(
                                minutes=(-(timezone_offset) * 60)
                            )
                        else:
                            transaction_filter_dict[
                                "created__gte"
                            ] = from_date - timedelta(minutes=(timezone_offset * 60))
                    else:
                        transaction_filter_dict["created__date__gte"] = from_date

                if to_date and validate_date(to_date):
                    to_date = datetime.strptime(
                        to_date + " 23:59:59", "%Y-%m-%d %H:%M:%S"
                    )
                    if timezone_offset:
                        timezone_offset = float(timezone_offset)
                        if timezone_offset < 0:
                            transaction_filter_dict[
                                "created__lte"
                            ] = to_date + timedelta(minutes=(-(timezone_offset) * 60))
                        else:
                            transaction_filter_dict[
                                "created__lte"
                            ] = to_date - timedelta(minutes=(timezone_offset * 60))
           
                alchemypay_transactions = AlchemypayOrder.objects.filter(user=player).order_by("-created")
                alchemypay_transactions = alchemypay_transactions.filter(**transaction_filter_dict).order_by("-created")
                paginator = self.pagination_class()
                try:
                    result_page = paginator.paginate_queryset(alchemypay_transactions, request)
                except Exception as e:
                    print(e)
                    return Response({"msg": "Something went Wrong", "status_code": status.HTTP_400_BAD_REQUEST})
                serializer =  AlchemypayTransactionsSerializer(result_page, many=True)
                return paginator.get_paginated_response(serializer.data)

            else:
                return Response({"msg": "user not found", "status_code":status.HTTP_404_NOT_FOUND})
        except Exception as e:
            print(f"error in fetching data {e}.")
            response = {"msg": "Some Internal error.", "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR}
            return Response(response)
    

class AlchemyPayCallback(APIView):
    ALCHEMYPAY_URL = settings.ALCHEMYPAY_URL
    ALCHEMYPAY_APPID = settings.ALCHEMYPAY_APPID
    ALCHEMYPAY_SECRETKEY = settings.ALCHEMYPAY_SECRETKEY

    def post(self, request):
        try:
            print(request.data,"CALLBACK")
            order_no = request.data.get('orderNo')
            payment_status = request.data.get('status')
            transaction = AlchemypayOrder.objects.filter(order_no=order_no).first()
            if payment_status=='PAY_FAIL':
                transaction.status = transaction.StatusType.payfail
            elif payment_status=='FINISHED':
                transaction.status = transaction.StatusType.finished
                user = transaction.user
                user.balance = user.balance + Decimal(transaction.amount)
                user.save() 
                checkbonus(transaction.id, payment_through="alchemypay")
            elif payment_status =='PAY_SUCCESS':
                transaction.status = transaction.StatusType.peysuccess
            transaction.save()        
            send_player_balance_update_notification(transaction.user)
            return Response(status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class MnetCallback(APIView):

    def post(self, request):
        try:
            data = request.data
            mnet = MnetPayment()
            
            if not isinstance(data, dict) or not data:
                return Response({"Status": "FAIL", "Error": "Invalid data format"}, 400)
    
            request_type, request_data = next(iter(data.items()))
            request_type = request_type.lower()
            user = mnet.validate_user(request_data)
            if not user:
                return Response({"Status": "FAIL", "Error":"Invalid CustPIN or CustPassword"}, 400)
            elif request_type == "getcustomerinfo":
                return mnet.get_customer_info()
            elif request_type == "getbalance":
                return mnet.balance_query(request_data)
            elif request_type == "transfer":
                trans_type = request_data.get("TransType", "").lower()
                if trans_type == "deposit":
                    return mnet.deposit(request_data)
                elif trans_type == "payout":
                    return mnet.approve_payout(request_data)
                elif trans_type == "rejected":
                    return mnet.reject(request_data)
                elif trans_type in ["chargeback", "refund"]:
                    return mnet.refund_or_chargeback(request_data)
            elif request_type == "payoutrequest":
                return mnet.request_payout(request_data)
            elif request_type == "payoutcancelled":
                return mnet.cancel_payout(request_data)
            return Response({"Response": "none"}, 400)
            
        except Exception as e:
            print(e)
            print(traceback.format_exc())
            return Response({"Status": "FAIL", "Error":"external integration error"}, 500)
        

class MnetTransactionView(APIView):
    http_method_name = ["get"]
    permission_classes = (IsPlayer,)
    pagination_class = CustomPagination
    serializer_class = MnetTransactionsSerializer

    def get(self, request, **kwargs):
        from apps.bets.utils import validate_date
        try:
            transaction_filter_dict = {"user":self.request.user}
            from_date = self.request.query_params.get("from_date", None)
            to_date = self.request.query_params.get("to_date", None)
            transaction_type = self.request.query_params.get("transaction_type", None)
            status = self.request.query_params.get("status", None) 
            if transaction_type:
                transaction_filter_dict["transaction_type"] = transaction_type
            if status:
                transaction_filter_dict["status"] = status
            timezone_offset = self.request.query_params.get("timezone_offset", None)
            if from_date and validate_date(from_date):
                from_date = datetime.strptime(
                    from_date + " 00:00:00", "%Y-%m-%d %H:%M:%S"
                )
                if timezone_offset:
                    timezone_offset = float(timezone_offset)
                    if timezone_offset < 0:
                        transaction_filter_dict[
                            "created__gte"
                        ] = from_date + timedelta(
                            minutes=(-(timezone_offset) * 60)
                        )
                    else:
                        transaction_filter_dict[
                            "created__gte"
                        ] = from_date - timedelta(minutes=(timezone_offset * 60))
                else:
                    transaction_filter_dict["created__date__gte"] = from_date

            if to_date and validate_date(to_date):
                to_date = datetime.strptime(
                    to_date + " 23:59:59", "%Y-%m-%d %H:%M:%S"
                )
                if timezone_offset:
                    timezone_offset = float(timezone_offset)
                    if timezone_offset < 0:
                        transaction_filter_dict[
                            "created__lte"
                        ] = to_date + timedelta(minutes=(-(timezone_offset) * 60))
                    else:
                        transaction_filter_dict[
                            "created__lte"
                        ] = to_date - timedelta(minutes=(timezone_offset * 60))
        
            mnet_transactions = MnetTransaction.objects.filter(**transaction_filter_dict).order_by("-created")
            paginator = self.pagination_class()
            try:
                result_page = paginator.paginate_queryset(mnet_transactions, request)
            except Exception as e:
                print(e)
                return Response({"msg": "Something went Wrong", "status_code": status.HTTP_400_BAD_REQUEST})
            serializer =  self.serializer_class(result_page, many=True)
            return paginator.get_paginated_response(serializer.data)

        except Exception as e:
            print(f"error in fetching data {e}.")
            response = {"msg": "Some Internal error.", "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR}
            return Response(response)
        

# Player can request for coin withdrawal
class GetCoinFlowLink(APIView):
    http_method_names = ["post"]
    permission_classes = [IsPlayer]
    
    def post(self, request):
        if not request.user.is_authenticated:
            return Response(data={'message' : 'You need to be login to use this endpoint.'}, status=status.HTTP_400_BAD_REQUEST)
        
        user: Users = request.user
        
        if request.user.document_verified != VERIFICATION_APPROVED:
            return Response(data={'message' : 'Please finish up all the verification steps.'}, status=status.HTTP_400_BAD_REQUEST)
        
        # country = user.country_obj.code_cca2 if user.country_obj else user.country
        # if country != 'US':
        #     return Response(data={'message' : 'Please update your information. We only accept US documents.'}, status=status.HTTP_400_BAD_REQUEST)
        
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')

        if x_forwarded_for:
            print(x_forwarded_for)
            ip = x_forwarded_for.split(',')[0].strip()  # client’s real IP
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        cf = CoinFlowClient()
        
        # data = cf.register_user_with_document(
        #     user=user,
        #     # ssn=f'{user.id}5'
        # )
        
        # if data.error:
        #     return Response(data={'message' : data.error}, status=status.HTTP_400_BAD_REQUEST)
        
        cents = request.data.get('cents', None)
        
        if cents is None:
            return Response(data={'message' : 'You must sent a cent amount.'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not str(cents).isdigit():
            return Response(data={'message' : 'Cents must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
        
        cents = int(cents)
        
        if cents < 500 or cents > 100000:
            return Response(data={'message' : 'Cents must be higher than 500 and lower than 100000.'}, status=status.HTTP_400_BAD_REQUEST)
            
        link = cf.create_checkout_link(user=user, amount_cents=cents)
        if link.error:
            return Response(data={'message' : link.error}, status=status.HTTP_400_BAD_REQUEST)
        
        if link.data is None:
            return Response(data={'message' : 'there is no id'}, status=status.HTTP_400_BAD_REQUEST)
        
        idt = link.data.pop('id', None)
        
        return Response(data=link.data, status=status.HTTP_200_OK)


class WebhookView(APIView):
    def post(self, request):
        save_request('spy', request)
        
        cf = CoinFlowClient()
        data = cf.handle_webhook(request.data, request.headers.get('Authorization'))
        if data.error:
            save_request('spy', {'data' : data.error, 'Authorization' : request.headers.get('Authorization', 'None')}, is_response=True)
            
        
        return Response(data={'message' : 'OK'}, status=status.HTTP_200_OK)
    
class TestCoinflow(APIView):
    '''
    This endpoint is meant to test new ideas
    something i should have created a long time ago
    so this can be use by my coworkers to at least in teory play the game
    '''
    def post(self, request):
        save_request('coinflow_testing', request)
        
        cf = CoinFlowClient()
        data = cf.register_user_with_document(user=request.user)
        if data.error:
            save_request('coinflow_testing', {'data' : data.error}, is_response=True)
        
        data = cf.register_user_attested(user=request.user, ssn=f'{request.user.id}3245'[:4])
        if data.error:
            save_request('conflow_testing', {'data' : data.error}, is_response=True)
            
        return Response(data={'message' : 'OK'}, status=status.HTTP_200_OK)
    
class GetBankRegistrationLink(APIView):
    permission_class = [IsPlayer]
    def post(self, request):
        
        cf = CoinFlowClient()
        data = cf.create_bank_registration_link(user=request.user)
        if data.error:
            return Response(data={'message' : data.error}, status=status.HTTP_400_BAD_REQUEST)        
        
        return Response(data={'message' : data.data})
    
class CoinflowTotals(APIView):
    permission_class = [IsPlayer]
    def post(self, request):
        
        cents = request.data.get('cents')
        if cents is None:
            return Response(data={'message' : 'Please use the @cents value to get the total'}, status=status.HTTP_400_BAD_REQUEST)
        cents = str(cents)
        
        if not cents.isdigit():
            return Response(data={'message' : '@cents should be an integer'}, status=status.HTTP_400_BAD_REQUEST)
        
        cents = int(cents)
        if cents < 500 or cents > 20000:
            return Response(data={'message' : '@cents min depossit of 500 cents. Max depossit is 20000 cents'}, status=status.HTTP_400_BAD_REQUEST)
        
        cf = CoinFlowClient()
        data = cf.get_totals(cents=cents, user=request.user)
        if data.error:
            return Response(data={'message' : data.error}, status=status.HTTP_400_BAD_REQUEST)        
        
        return Response(data=data.data)
    
class CoinflowBanks(APIView):
    permission_class = [IsPlayer]
    def post(self, request):
        cf = CoinFlowClient()
        data = cf.get_cards_banks(request.user)
        if data.error:
            return Response(data={'message' : data.error}, status=status.HTTP_400_BAD_REQUEST)        
        
        return Response(data={'message' : data.data})
    
class CoinflowWithdraws(APIView):
    permission_class = [IsPlayer]
    def post(self, request):
        card = request.data.get('cardId')
        bank = request.data.get('bankId')
        
        
        cents = request.data.get('cents')
        if cents is None:
            return Response(data={'message' : 'Please use the @cents value to get the total'}, status=status.HTTP_400_BAD_REQUEST)
        cents = str(cents)
        
        if not cents.isdigit():
            return Response(data={'message' : '@cents should be an integer'}, status=status.HTTP_400_BAD_REQUEST)
        
        cents = int(cents)
        if cents < 500 or cents > 20000:
            return Response(data={'message' : '@cents min depossit of 500 cents. Max depossit is 20000 cents'}, status=status.HTTP_400_BAD_REQUEST)
        
        
        if card is None and bank is None:
            return Response(data={'message' : 'Please use @cardId or @bankId'}, status=status.HTTP_400_BAD_REQUEST)
        
        if card and bank:
            return Response(data={'message' : 'Please only use @cardId or @bankId'}, status=status.HTTP_400_BAD_REQUEST)
        
        prefix = 'card:' if card else 'bank:'
        token = card if card else bank
        data = redis_client.get(prefix+token)
        
        if not data:
            return Response(data={'message' : 'Please use and available card, For security reasons once started a transaction this id only last 30 min'}, status=status.HTTP_400_BAD_REQUEST)
        
        data = json.loads(str(data))
        cf = CoinFlowClient()
        user = request.user
        if not user.is_authenticated:
            return Response(data={'message' : 'Please use and available card, For security reasons once started a transaction this id only last 30 min'}, status=status.HTTP_400_BAD_REQUEST)
        
        ip = get_user_ip_from_request(request)
        result = cf.create_transaction_withdraw(user, data, prefix, cents, ip)
        
        if result.data:
            return Response(data=result.data, status=result.data.get("status"))
        
        return Response(data={'message' : 'HTTP error 400: Not enough founds'}, status=status.HTTP_400_BAD_REQUEST)
    
class CoinflowRegisterUserView(APIView):
    permission_class = [IsPlayer]
    def post(self, request):
        
        ssn = request.data.get('ssn', None)
        if not ssn:
            return Response(data={"message" : "Please ingres the 4 last digist of you ssn"}, status=status.HTTP_400_BAD_REQUEST)
        
        ssn = str(ssn[-4:])
        
        if not ssn.isdigit():
            return Response(data={"message" : "Please insert a valid ssn number, only the last 4 digist are needed."}, status=status.HTTP_400_BAD_REQUEST)
        ssn = int(ssn)
        
        if request.user.coinflow_state in {CoinflowAuthState.verified}:
            return Response(data={"message" : "This user is already verified."}, status=status.HTTP_200_OK)
        cf = CoinFlowClient()
        data = cf.register_user(user=request.user, ssn=ssn)
        if data.error:
            return Response(data={"message" : data.error}, status=status.HTTP_400_BAD_REQUEST)
        
        link = data.data.get('link')
        if link:
            return Response(data=data.data, status=status.HTTP_206_PARTIAL_CONTENT)
        
        return Response(data=data.data, status=status.HTTP_201_CREATED)