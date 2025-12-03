from decimal import Decimal
import datetime
import math

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework import status

from apps.users import promo_handler

from .models import AlchemypayOrder, Bundle, CoinFlowTransaction, CoinWithdrawal, MnetTransaction, NowPaymentsTransactions
from apps.users.models import Users
from apps.bets.models import Transactions, DEPOSIT, ROLLBACK, CHARGED, WITHDRAW
from apps.casino.utils import ErrorResponseMsg
from .utils import COIN_PAYMENTS,get_min_amount,get_validate_address


class CreateWithdrawalSerializer(serializers.Serializer):
    withdraw_id = serializers.IntegerField(required=True)


class CancelWithdrawalSerializer(serializers.Serializer):
    withdraw_id = serializers.IntegerField(required=True)




class RequestCoinWithdrawalSerializer(serializers.Serializer):
    amount = serializers.FloatField(required=True, min_value=0)
    currency = serializers.CharField(required=True)
    address = serializers.CharField(required=True)
    verification_code = serializers.CharField(required=False)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class CreateWithdrawalSerializerCoinpayments(serializers.Serializer):
    withdraw_id = serializers.IntegerField(required=True)

    def create(self, validated_data):
        withdraw_id = validated_data.get("withdraw_id")
        response = {}

        cw = CoinWithdrawal.objects.filter(id=withdraw_id).first()
        if cw and cw.status == CoinWithdrawal.StatusType.pending:
            print("===Amount===", cw.amount)
            data = {
                'amount': Decimal(cw.amount),
                'currency': cw.currency,
                'address': cw.address,
                'currency2': cw.currency2,
                'auto_confirm': 1,
                'ipn_url': settings.COINPAYMENTS_IPN_URL,
            }
            response = COIN_PAYMENTS.create_withdrawal(params=data)
            if "error" in response and response["error"] == "ok":
                cw.status = CoinWithdrawal.StatusType.processing
                cw.coin_withdraw_id = response["result"]["id"]
                cw.save()

        return response

    def update(self, instance, validated_data):
        pass


class CallbackWithdrawalSerializer(serializers.Serializer):
    withdraw_id = serializers.IntegerField(required=True)

    def create(self, validated_data):
        withdraw_id = validated_data.get("withdraw_id")
        response = {}
        try:
            cw = CoinWithdrawal.objects.filter(id=withdraw_id).first()
            txn = Transactions.objects.filter(txn_id=withdraw_id).first()
            if cw and txn and cw.status == CoinWithdrawal.StatusType.pending:
                user = Users.objects.filter(id=cw.user.id).first()
                if user:
                    now = str(datetime.datetime.now())
                    reference = user.username + now
                    user.balance = round(Decimal(user.balance) + Decimal(cw.amount), 2)
                    user.locked = round(float(user.locked) - float(cw.amount), 2)
                    cw.status = CoinWithdrawal.StatusType.rollback
                    txn.journal_entry = ROLLBACK
                    txn.status = CHARGED
                    txn.reference = reference
                    user.save()
                    cw.save()
                    txn.id = None
                    txn.save()
                    response["error"] = 'ok'
                    response["txn_id"] = cw.id
                    response["user"] = cw.user.username
                    response["amount"] = cw.amount
                else:
                    response["error"] = ErrorResponseMsg.PLAYER_NOT_FOUND.value
            else:
                response["error"] = "Transaction not found"

        except Exception as e:
            print("====CreateWithdrawal Error===", e)
            response["error"] = e
            return Response(response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        print("====CreateWithdrawal Response===", response)
        return Response(response, status=status.HTTP_200_OK)

    def update(self, instance, validated_data):
        pass


class CreatePaymentSerializer(serializers.Serializer):
    price_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    pay_currency = serializers.CharField(max_length=10, required=True)
    promo_code = serializers.CharField(max_length=50, required=False)
    
    def validate(self, data):
        data['ipn_callback_url'] = settings.IPN_CALLBACK_URL
        data['price_currency'] = 'usd'
        min_amount = get_min_amount(data['pay_currency'])
        if min_amount.get('fiat_equivalent'):
            if data['price_amount'] < min_amount['fiat_equivalent']:
                raise serializers.ValidationError(f"amount must be greater than or equal to {math.ceil(min_amount['fiat_equivalent'])}")
        if data.get("promo_code"):
            is_valid, msg = promo_handler.verify_code(
                promo_code=data.get("promo_code"),
                user=self.context.get("user"),
                bonus_type="deposit")
            if not is_valid:
                raise serializers.ValidationError(msg)
            
        return data
   
class CreateWithdrawalSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=8)
    address = serializers.CharField(max_length=255)
    currency = serializers.CharField(max_length=10)
    def validate(self, data):
        validate_address = get_validate_address(data['address'],data['currency'])
        print(validate_address)
        if not validate_address:
              raise serializers.ValidationError(f"Invalid address")

        min_amount = get_min_amount(data['currency'])
        if min_amount.get('fiat_equivalent'):
            if data['amount'] < min_amount['fiat_equivalent']:
                raise serializers.ValidationError(f"amount must be greater than or equal to {math.ceil(min_amount['fiat_equivalent'])}")
        return data
    
  
# class NowPaymentsTransactionsSerializer(serializers.ModelSerializer):
#     withdrawal_amount = serializers.IntegerField()
#     class Meta:
#         model = NowPaymentsTransactions
#         fields = '__all__'

class NowPaymentsTransactionsSerializer(serializers.Serializer):
    created =   serializers.DateTimeField(required=False)
    withdrawal_amount = serializers.IntegerField(required=False)
    price_amount = serializers.SerializerMethodField(required=False)
    payment_id = serializers.CharField(max_length=100, required=False)
    transaction_type = serializers.SerializerMethodField(required=False)
    payment_status = serializers.SerializerMethodField(required=False)
    journal_entry = serializers.CharField(max_length=100, required=False,default=None)

    @staticmethod
    def get_price_amount(obj):
        if hasattr(obj, 'journal_entry') and obj.journal_entry and (obj.description.startswith('Tip') or obj.description.startswith('Tournament')  or obj.description.startswith('Fortunepandas')):
            return obj.amount
        return obj.price_amount
    
    @staticmethod
    def get_payment_status(obj):
        if hasattr(obj, 'journal_entry') and obj.journal_entry and obj.description.startswith('Tip'):
            return "Reward"
        elif hasattr(obj, 'journal_entry') and (obj.description.startswith('Tournament') or obj.description.startswith('Fortunepandas')):
            return obj.journal_entry
        return obj.payment_status

    @staticmethod
    def get_transaction_type(obj):
        if hasattr(obj, 'journal_entry') and obj.journal_entry and obj.description.startswith('Tip'):
            return "Tip"
        elif hasattr(obj, 'journal_entry') and obj.description.startswith('Tournament refund'):
            return "Tournament Refund"
        elif hasattr(obj, 'journal_entry') and obj.description.startswith('Tournament'):
            return "Tournament Opt"
        elif hasattr(obj, 'journal_entry') and obj.description.startswith('Fortunepandas deposit'):
            return "Fortunepandas Deposit"
        elif hasattr(obj, 'journal_entry') and obj.description.startswith('Fortunepandas withdrawal'):
            return "Fortunepandas Withdraw"
        return obj.transaction_type.capitalize() if obj.transaction_type else obj.transaction_type
    
    class Meta:
        model = NowPaymentsTransactions
        fields = '__all__'
        
class CreatePaymentQrSerializer(serializers.Serializer):
    price_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
    pay_currency = serializers.CharField(max_length=10, required=True)
    promo_code = serializers.CharField(max_length=50, required=False)
    
    def validate(self, data):
        data['ipn_callback_url'] = settings.IPN_CALLBACK_URL
        data['success_url'] = settings.SUCCESS_URL
        data['cancel_url'] = settings.CANCEL_URL
        data['price_currency'] = 'usd'
        
        if data.get("promo_code"):
            is_valid, msg = promo_handler.verify_code(
                user=self.context.get("user"),
                promo_code=data.get("promo_code"),
                bonus_type="deposit")
            if not is_valid:
                raise serializers.ValidationError(msg)
            
        return data


class AlchemypayTransactionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlchemypayOrder
        fields = '__all__'
        
class MnetTransactionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = MnetTransaction
        fields = ("id", "transaction_id", "created", "amount", "transaction_type", "status" )
    

class CoinflowTransactionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoinFlowTransaction
        fields = ("id", "transaction_id", "created", "amount", "transaction_type", "status" )


class BundleSerializer(serializers.ModelSerializer):

    total = serializers.SerializerMethodField()

    @staticmethod
    def get_total(obj):
        return obj.balance + obj.playable


    class Meta:
        model = Bundle
        fields = ("code", "price", "total", "bonus", "miner", "enabled")