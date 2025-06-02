import urllib
import traceback

from django.db import transaction
from rest_framework.response import Response

from apps.users.models import *
from apps.payments.models import MnetTransaction
from apps.users.utils import send_player_balance_update_notification
from apps.payments.utils import checkbonus


class MnetPayment:
    def __init__(self):
        self.user = None
    
    def validate_user(self, data):
        if not isinstance(data, dict) or not data:
            return False

        customer_pin = data.get("CustPIN")
        customer_password = urllib.parse.unquote(data.get("CustPassword"))
        self.user = Users.objects.filter(username__iexact=customer_pin).first()
        if not self.user or self.user.mnet_password!=customer_password:
            return False
        return self.user
    
    def get_customer_info(self):
        self.user.refresh_from_db()
        full_name = self.user.full_name.split(" ")
        if self.user.dob:
            year, month, day = self.user.dob.split('-')
            formatted_date_str = f"{month}/{day}/{year}"
        else:
            formatted_date_str = None

        return Response({
            "Name": full_name[0],
            "LastName": full_name[-1] if len(full_name) > 1 else "",
            "SSN": str(self.user.id)[-4:],
            "Phone": self.user.phone_number,
            "Email": self.user.email,
            "City": self.user.city,
            "Address": self.user.complete_address,
            "ZipCode": self.user.zip_code,
            "DOB": formatted_date_str,
            "Country": self.user.country,
            "State": self.user.state,
            "CurrencyCode": self.user.currency,
            "CustomerProfile": "",
            "Balance": self.user.balance,
            "DocOnFile": 0,
        }, 200)
        
    def balance_query(self, request_data):
        self.user.refresh_from_db()
        if request_data.get("CustPayoutBalance", None):
            return Response({
                "Balance": self.user.mnet_payout_balance,
                "WithdrawableBalance": self.user.balance,
                "CurrencyCode": self.user.currency,
            }, 200)
            
        return Response({
            "Balance": self.user.balance,
            "WithdrawableBalance": self.user.balance,
            "CurrencyCode": self.user.currency,
        }, 200)
        
    @transaction.atomic
    def deposit(self, data:dict):
        try:
            amount = data.get('Amount', "").replace(",", ".")
            trans_type = data.get('TransType', None)
            card_type = data.get('CardType', None)
            processor_name = data.get('ProcessorName', None)
            transaction_id = data.get('TransactionID', None)
            trans_date = data.get('TransDate', None)
            trans_note = data.get('TransNote', None)
            ip_address = data.get('IPAddress', None)
            currency = data.get('Currency', None)
            card_number = data.get('CardNumber', None)
            error_code = data.get('ErrorCode', None)
            error_description = data.get('ErrorDescription', None)
            descriptor = data.get('Descriptor', None)
            
            if MnetTransaction.objects.filter(transaction_id=transaction_id).exists():
                return Response({"Status": "OK", "TransactionID": transaction_id}, 200)
            
            self.user.refresh_from_db()
            self.user.balance += Decimal(amount)
            self.user.save()
            
            transaction = MnetTransaction.objects.create(
                user = self.user,
                amount = amount,
                status = MnetTransaction.StatusType.approved,
                card_type = card_type,
                card_number = card_number,
                processor_name = processor_name,
                transaction_type = MnetTransaction.TransactionType.deposit,
                transaction_id = transaction_id,
                trans_note = trans_note,
                ip_address = ip_address,
                currency = currency,
                descriptor = descriptor,
                error_code = error_code,
                error_description = error_description,
            )
            
            checkbonus(transaction.id, payment_through="mnet")
            send_player_balance_update_notification(self.user)
            
            return Response({"Status": "OK", "TransactionID": transaction_id}, 200)
        except Exception as e:
            print(traceback.format_exc())
            print(e)
            return Response({"Status": "FAIL", "TransactionID": transaction_id, "Error":"external integration error"}, 500)
        
    @transaction.atomic
    def reject(self, data:dict):
        try:
            amount = data.get('Amount', "").replace(",", ".")
            trans_type = data.get('TransType', None)
            card_type = data.get('CardType', None)
            processor_name = data.get('ProcessorName', None)
            transaction_id = data.get('TransactionID', None)
            trans_date = data.get('TransDate', None)
            trans_note = data.get('TransNote', None)
            ip_address = data.get('IPAddress', None)
            currency = data.get('Currency', None)
            card_number = data.get('CardNumber', None)
            error_code = data.get('ErrorCode', None)
            error_description = data.get('ErrorDescription', None)
            descriptor = data.get('Descriptor', None)
            
            if MnetTransaction.objects.filter(transaction_id=transaction_id).exists():
                return Response({"Status": "OK", "TransactionID": transaction_id}, 200)
            
            transaction = MnetTransaction.objects.create(
                user = self.user,
                amount = amount,
                status = MnetTransaction.StatusType.rejected,
                card_type = card_type,
                card_number = card_number,
                processor_name = processor_name,
                transaction_type = MnetTransaction.TransactionType.deposit,
                transaction_id = transaction_id,
                trans_note = trans_note,
                ip_address = ip_address,
                currency = currency,
                descriptor = descriptor,
                error_code = error_code,
                error_description = error_description,
            )
            return Response({"Status": "OK", "TransactionID": transaction_id}, 200)
        except Exception as e:
            print(traceback.format_exc())
            print(e)
            return Response({"Status": "FAIL", "TransactionID": transaction_id, "Error":"external integration error"}, 500)
        
    @transaction.atomic
    def request_payout(self, data):
        try:
            amount = data.get('Amount', "").replace(",", ".")
            card_type = data.get('CardType', None)
            processor_name = data.get('ProcessorName', None)
            transaction_id = data.get('TransactionID', None)
            trans_date = data.get('TransDate', None)
            trans_note = data.get('TransNote', None)
            ip_address = data.get('IPAddress', None)
            currency = data.get('Currency', None)
            fee = data.get('Fee', None)

            if MnetTransaction.objects.filter(transaction_id=transaction_id).exists():
                return Response({"Status": "OK", "TransactionID": transaction_id}, 200)
            
            if not amount:
                return Response({"Status": "FAIL", "TransactionID": transaction_id}, 200)
            elif self.user.balance < Decimal(amount):
                return Response({"Status": "FAIL", "TransactionID": transaction_id,  "Error":"Insufficient Balance"}, 200)
            
            self.user.refresh_from_db()
            self.user.balance -= Decimal(amount)
            self.user.mnet_payout_balance += Decimal(amount)
            self.user.save()
            
            transaction = MnetTransaction.objects.create(
                user = self.user,
                amount = amount,
                status = MnetTransaction.StatusType.requested,
                card_type = card_type,
                processor_name = processor_name,
                transaction_type = MnetTransaction.TransactionType.withdraw,
                transaction_id = transaction_id,
                trans_note = trans_note,
                ip_address = ip_address,
                currency = currency,
            )
            send_player_balance_update_notification(self.user)
            
            return Response({"Status": "OK", "TransactionID": transaction_id}, 200)
        except Exception as e:
            print(traceback.format_exc())
            print(e)
            return Response({"Status": "FAIL", "TransactionID": transaction_id, "Error":"Internal Error"}, 200)
        
    @transaction.atomic
    def approve_payout(self, data):
        try:
            transaction_id = data.get('TransactionID', None)
            
            mnet_transaction = MnetTransaction.objects.filter(transaction_id=transaction_id).first()
            if not mnet_transaction:
                return Response({"Status": "FAIL", "TransactionID": transaction_id, "Error":"withdrawal request does not exists."}, 200)
            elif mnet_transaction.status == MnetTransaction.StatusType.approved:
                return Response({"Status": "OK", "TransactionID": transaction_id}, 200)
            
            mnet_transaction.status = MnetTransaction.StatusType.approved
            mnet_transaction.save()

            self.user.refresh_from_db()
            self.user.mnet_payout_balance -= mnet_transaction.amount
            self.user.save()
            
            return Response({"Status": "OK", "TransactionID": transaction_id}, 200)
        except Exception as e:
            print(traceback.format_exc())
            print(e)
            return Response({"Status": "FAIL", "TransactionID": transaction_id, "Error":"Internal Error"}, 200)
            
    @transaction.atomic
    def cancel_payout(self, data):
        try:
            transaction_id = data.get('TransactionID', None)

            mnet_transaction = MnetTransaction.objects.filter(transaction_id=transaction_id).first()
            if not mnet_transaction:
                return Response({"Status": "FAIL", "TransactionID": transaction_id, "Error":"withdrawal request does not exists."}, 200)
            elif mnet_transaction.status == MnetTransaction.StatusType.cancelled:
                return Response({"Status": "OK", "TransactionID": transaction_id}, 200)
            
            self.user.refresh_from_db()
            self.user.balance+=mnet_transaction.amount
            self.user.mnet_payout_balance -= mnet_transaction.amount
            self.user.save()
            
            mnet_transaction.status = MnetTransaction.StatusType.cancelled
            mnet_transaction.save()
            send_player_balance_update_notification(self.user)
            
            return Response({"Status": "OK", "TransactionID": transaction_id}, 200)
        except Exception as e:
            print(traceback.format_exc())
            print(e)
            return Response({"Status": "FAIL", "TransactionID": transaction_id, "Error":"Internal Error"}, 200)
        
    @transaction.atomic
    def refund_or_chargeback(self, data):
        try:
            amount = data.get('Amount', "").replace(",", ".")
            trans_type = data.get('TransType', None)
            card_type = data.get('CardType', None)
            processor_name = data.get('ProcessorName', None)
            transaction_id = data.get('TransactionID', None)
            trans_date = data.get('TransDate', None)
            trans_note = data.get('TransNote', None)
            ip_address = data.get('IPAddress', None)
            currency = data.get('Currency', None)
            card_number = data.get('CardNumber', None)
            error_code = data.get('ErrorCode', None)
            error_description = data.get('ErrorDescription', None)
            descriptor = data.get('Descriptor', None)

            if MnetTransaction.objects.filter(transaction_id=transaction_id).exists():
                return Response({"Status": "OK", "TransactionID": transaction_id}, 200)
            
            self.user.refresh_from_db()
            self.user.balance -= Decimal(amount)
            self.user.save()
            
            transaction = MnetTransaction.objects.create(
                user = self.user,
                amount = amount,
                status = MnetTransaction.StatusType.refund if trans_type.lower()=="refund" else MnetTransaction.StatusType.chargeback,
                card_type = card_type,
                card_number = card_number,
                processor_name = processor_name,
                transaction_type = MnetTransaction.TransactionType.deposit,
                transaction_id = transaction_id,
                trans_note = trans_note,
                ip_address = ip_address,
                currency = currency,
                descriptor = descriptor,
                error_code = error_code,
                error_description = error_description,
            )
            send_player_balance_update_notification(self.user)
            
            return Response({"Status": "OK", "TransactionID": transaction_id}, 200)
        except Exception as e:
            print(traceback.format_exc(), flush=True)
            print(e, flush=True)
            return Response({"Status": "FAIL", "TransactionID": transaction_id, "Error":"Internal Error"}, 200)
        
