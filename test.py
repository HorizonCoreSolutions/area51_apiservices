from typing import Optional
from django.db import transaction
import requests
from apps.core.custom_types import BasicReturn
from apps.payments.models import CoinFlowTransaction
from apps.users.models import Users
from apps.payments.coinflow import CoinFlowClient, CoinFlowAPIError
from uuid import uuid4
from decimal import Decimal

cFT = None

class CoinFlowClientExtended(CoinFlowClient):
    def seudo_get_cards_banks(self, user: Users):
        try:
            data = self._make_api_request(
                method='GET',
                url=self.endpoints.get_withdrawers,
                headers=self._build_headers(auth_user_id=self._generate_user_id(user))
            ).json()
        except CoinFlowAPIError:
            from apps.payments.coinflow import BasicReturn  # Make sure BasicReturn is imported
            return BasicReturn(success=False, error='Withdraws are not available right now. Please try again later.')

        return data
    
    @transaction.atomic
    def seudo_create_transaction_withdraw(
        self,
        user: Users,
        cents: int,
        acc_type: str,
        token: str
    ):
        user = Users.objects.select_for_update().get(id=user.id)
        idpk = str(uuid4())
        actual_balance = user.balance
        new_balance    = actual_balance - (Decimal(cents) / 100)
        user.balance = new_balance
        if new_balance < 0:
            return BasicReturn(success=False, error="You have insufficient funds for this transaction.")
        user.save()

        cft = CoinFlowTransaction.objects.create(
            user=user,
            amount=(Decimal(cents) / 100),
            currency='USD',
            transaction_id=idpk,
            transaction_type=CoinFlowTransaction.TransactionType.withdraw_request,
            status=CoinFlowTransaction.StatusType.requested,
            pre_balance=actual_balance,
            post_balance=new_balance,
            ip_address='',
            signature=None,
            account_type=acc_type,
            account=token
        )
        global cFT
        cFT = cft
        payload = {
            "amount": { "cents": cents },
            "speed": "same_day" if acc_type == CoinFlowTransaction.AccountType.bank else acc_type,
            "account": token,
            "userId": self._generate_user_id(user),
            "waitForConfirmation": True,
            "idempotencyKey": idpk
        }

        res: Optional[requests.Response] = None
        counter = 0
        while counter < 3:
            counter+=1
            res = requests.post(
                self.endpoints.payout_user_coinflow,
                json=payload,
                headers=self._build_headers())
            print(res.text)
            if res.status_code != 503:
                break
        if res is None:
            print("Coinflow api response is outbonded request.post(*) -> None")
            return BasicReturn(success=False, error="This service is down, please try again later. If the problem persist contact support.")

        if res.status_code == 451:
            print(f"User: {user.id}-{user.username} had access to withdraw but did not had coinflow verification enabled.")
            data = res.json()
            link = data.get("verificationLink")
            return BasicReturn(success=False, error="User hadn't the full account info.", data={
                "message" : "Please complete the verification to use this service.",
                "url"     : link,
                "status"  : 451
            })

        if res.status_code == 503:
            print(f"{idpk} - for cents {cents} failed 3 times")
            return BasicReturn(success=False, error="This service is down, please try again later. If the problem persist contact support.")

        if res.status_code == 409:
            user.save()
            print(f"Duplication of ")
            return BasicReturn(success=False, error="The withdraw has already been created.")

        if res.status_code == 400:
            try:
                data=res.json()
            except:
                print("Coinflow data coudnt been deserialized")
                data={}
            serial = data.get("serialized", "No_serial_found")
            logs = data.get('logs', [])
            error = "non_indentified_error"
            for log in logs:
                if log.startswith("Program log: Error:"):
                    error=log[19:]

            print(f"Error {error} | for user {user.id}-{user.username}: {idpk} = {serial}")
            return BasicReturn(success=False, data="This transaction couldn't be processed, please try again later or call support.")

        if res.status_code != 200:
            print("Coinflow API is not working propertly")
            print(f"data {res.text}")
            return BasicReturn(success=False, error="This service is down, please try again later. If the problem persist contact support.")

        data = res.json()
        user.save()

        signature = data.get("signature")
        if signature is None:
            print("Coinflow API is not working propertly. There is not signature")
            print(f"data \n{data}")
            return BasicReturn(success=False, error="This service is down, please try again later. If the problem persist contact support.")

        cft.transaction_type = str(CoinFlowTransaction.TransactionType.withdraw)
        cft.signature = signature
        cft.save()
        
        return cft


cp = CoinFlowClientExtended()
a = Users.objects.get(id=238)
data = cp.seudo_get_cards_banks(a)
print(data)