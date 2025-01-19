import time
import hashlib
import requests
from decimal import Decimal

from django.db import transaction
from django.conf import settings

from apps.users.models import FortunePandasGameList, Users
from apps.bets.models import CHARGED, CREDIT, DEBIT, Transactions
from apps.bets.utils import generate_reference


class FortunePandaAPIClient:
    def __init__(self, base_url, redirect_url, agent_name, agent_passwd, agent_key):
        self.base_url = base_url
        self.redirect_url = f"{redirect_url}redirectHome"
        self.agent_name = agent_name
        self.agent_passwd = agent_passwd
        self.agent_key = agent_key

    
    def _generate_sign(self, *args):
        sign_str = ''.join(args).lower()
        return hashlib.md5(sign_str.encode()).hexdigest()

    
    def _post_request(self, url=None, params=None)-> dict:
        response = requests.post(self.base_url, params=params)
        return response.json()

    
    def agent_login(self):
        timestamp = str(int(time.time() * 1000))
        params = {
            "action": "agentLogin",
            "agentName": self.agent_name,
            "agentPasswd": self.agent_passwd,
            "time": timestamp
        }

        response = self._post_request(params=params)
        if response.get("code") in [200, "200"]:
            self.agent_key = response.get('agentkey')
        return response
    
    
    def update_apikey(self, admin:Users):
        self.agent_login()
        admin.fortune_pandas_api_key = self.agent_key
        admin.save()
            
    
    def register_user(self, account, passwd):
        timestamp = str(int(time.time() * 1000))
        sign = self._generate_sign(self.agent_name, timestamp, self.agent_key)
        passwd = self._generate_sign(passwd)
        # print("account - ",account)
        # print("password - ",passwd)
        params = {
            "action": "registerUser",
            'account': account,
            'passwd': passwd,
            'agentName': self.agent_name,
            'time': timestamp,
            'sign': sign
        }
        return self._post_request(params=params), passwd

    
    def get_game_list(self):
        timestamp = str(int(time.time() * 1000))
        sign = self._generate_sign(self.agent_name, timestamp, self.agent_key)

        params = {
            "action": "getgamelist",
            "agentName": self.agent_name,
            "time": timestamp,
            "sign": sign
        }
        return self._post_request(params=params)

    
    def get_user_balance(self, account, passwd):
        timestamp = str(int(time.time() * 1000))
        sign = self._generate_sign(self.agent_name, timestamp, self.agent_key)
        params = {
            "action": "queryInfo",
            'account': account,
            'passwd': passwd,
            'agentName': self.agent_name,
            'time': timestamp,
            'sign': sign
        }
        return self._post_request(params=params)

    
    def enter_game(self, account, passwd, kind_id):
        timestamp = str(int(time.time() * 1000))
        sign = self._generate_sign(self.agent_name, timestamp, self.agent_key)
        # passwd = self._generate_sign(passwd)
        params = {
            "action": "entergame",
            'account': account,
            'passwd': passwd,
            'agentName': self.agent_name,
            'kindId': kind_id,
            'redirectUrl': self.redirect_url,
            'time': timestamp,
            'sign': sign
        }
        return self._post_request(params=params)

    
    def change_password(self, account, passwd, new_passwd):
        timestamp = str(int(time.time() * 1000))
        sign = self._generate_sign(self.agent_name, timestamp, self.agent_key)
        passwd = self._generate_sign(passwd)
        new_passwd = self._generate_sign(new_passwd)
        params = {
            "action": "changePasswd",
            'account': account,
            'passwd': passwd,
            'passwdNew': new_passwd,
            'agentName': self.agent_name,
            'time': timestamp,
            'sign': sign
        }
        return self._post_request(params=params), passwd

    
    def recharge(self, account, amount):
        timestamp = str(int(time.time() * 1000))
        sign = self._generate_sign(self.agent_name, timestamp, self.agent_key)
        params = {
            "action": "recharge",
            'account': account,
            'amount': amount,
            'agentName': self.agent_name,
            'time': timestamp,
            'sign': sign
        }
        return self._post_request(params=params)

    
    def redeem(self, account, amount):
        timestamp = str(int(time.time() * 1000))
        sign = self._generate_sign(self.agent_name, timestamp, self.agent_key)
        params = {
            "action": "redeem",
            'account': account,
            'amount': amount,
            'agentName': self.agent_name,
            'time': timestamp,
            'sign': sign
        }
        return self._post_request(params=params)

    
    def get_trade_record(self, account, from_date, to_date):
        url = f"{self.base_url}?action=getTradeRecord"
        timestamp = str(int(time.time() * 1000))
        sign = self._generate_sign(self.agent_name, timestamp, self.agent_key)
        params = {
            "action": "getTradeRecord",
            'agentName': self.agent_name,
            'account': account,
            'fromDate': from_date,
            'toDate': to_date,
            'time': timestamp,
            'sign': sign
        }
        return self._post_request(params=params)

    
    def get_jp_record(self, account, from_date, to_date):
        timestamp = str(int(time.time() * 1000))
        sign = self._generate_sign(self.agent_name, timestamp, self.agent_key)
        params = {
            "action": "getJpRecord",
            'agentName': self.agent_name,
            'account': account,
            'fromDate': from_date,
            'toDate': to_date,
            'time': timestamp,
            'sign': sign
        }
        return self._post_request(params=params)

    
    def get_game_record(self, account):
        timestamp = str(int(time.time() * 1000))
        sign = self._generate_sign(self.agent_name, timestamp, self.agent_key)
        params = {
            "action": "getGameRecord",
            'agentName': self.agent_name,
            'account': account,
            'time': timestamp,
            'sign': sign
        }
        return self._post_request(params=params)
    

class FortunePandaAPI():
    def __init__(self, user:Users):
        self.user = user
        self.account=f"{self.user.id}-{self.user.username}"
        self.client = FortunePandaAPIClient(
            settings.FORTUNEPANDAS_BASE_URL,
            settings.FE_DOMAIN,
            settings.FORTUNEPANDAS_AGENT_NAME,
            settings.FORTUNEPANDAS_AGENT_PASSWORD,
            self.user.admin.fortune_pandas_api_key,
        )
        self.success_status_code = [200, "200"]
        
    def update_apikey(self):
        self.client.update_apikey(self.user.admin)
        
    def register_user(self):
        response, password = self.client.register_user(account=self.account, passwd=f"{self.user.username}@123")
        if response.get("code") in self.success_status_code or response.get("msg") == "The account number already exists, please re-enter it!":
            self.user.fortune_pandas_password = password
            self.user.is_registered_in_fortune_pandas = True
            self.user.save()
            return {"message": True}, 200
        return {"message": response.get("msg")}, 400
        
    def change_password(self, current_password, new_password):
        response, password = self.client.change_password(account=self.account, passwd=current_password, new_passwd=new_password)
        if response.get("code") in self.success_status_code:
            self.user.fortune_pandas_password = password
            self.user.save()
            return {"message": "Password changed sucessfully"}, 200
        return {"message": response.get("msg")}, 400
        
    def recharge_wallet(self, amount):
        response = self.client.recharge(account=self.account, amount=int(amount*100))
        if response.get("code") in self.success_status_code:
            with transaction.atomic():
                previous_balance = self.user.balance
                self.user.balance -= amount
                self.user.fortune_pandas_balance += amount
                self.user.save()
                
                Transactions.objects.create(
                    user = self.user,
                    amount = amount,
                    journal_entry = DEBIT,
                    status = CHARGED,
                    previous_balance = previous_balance,
                    new_balance = self.user.balance,
                    description = f"Fortunepandas deposit by {self.user.username}",
                    reference = generate_reference(self.user),
                    bonus_type = "N/A",
                    bonus_amount = 0
                )
            return {"message": "Desposit sucessfully"}, 200
        else:
            if response.get("msg")=="Sorry, there is not enough gold for the operator!":
                return {"message": "Please enter less amount, and try again."}, 400
            return {"message": response.get("msg")}, 400
        
    def redeem_balance(self, amount):
        self.user.refresh_from_db()
        if self.user.fortune_pandas_balance < amount:
            return {"message": "Insufficient balance"}, 400
        
        response = self.client.redeem(account=self.account, amount=int(amount*100))
        if response.get("code") in self.success_status_code:
            with transaction.atomic():
                previous_balance = self.user.balance
                self.user.balance += amount
                self.user.fortune_pandas_balance -= amount
                self.user.save()
                
                Transactions.objects.create(
                    user = self.user,
                    amount = amount,
                    journal_entry = CREDIT,
                    status = CHARGED,
                    previous_balance = previous_balance,
                    new_balance = self.user.balance,
                    description = f'Fortunepandas withdrawal by {self.user.username}',
                    reference = generate_reference(self.user),
                    bonus_type = "N/A",
                    bonus_amount = 0
                )
                
            return {"message": "Withdraw sucessfully"}, 200
        return {"message": response.get("msg")}, 400
                
    def start_game(self, kind_id):
        response = self.client.enter_game(
            account=self.account,
            passwd=self.user.fortune_pandas_password,
            kind_id=kind_id
        )

        if response.get("code") in self.success_status_code:
            user_balance = Decimal(response.get("userBalance"))
            self.user.fortune_pandas_balance = round(user_balance,2)
            self.user.save()
            return {
                "user_balance": user_balance,
                "web_login_url": response.get("webLoginUrl")
            }, 200
        return {"message": response.get("msg")}, 400
        
    def get_and_update_balance(self):
        response = self.client.get_user_balance(
            account=self.account,
            passwd=self.user.fortune_pandas_password,
        )
        
        if response.get("code") in self.success_status_code:
            balance = response.get("userBalance")
            self.user.fortune_pandas_balance = round(Decimal(balance),2)
            self.user.save()
            return {"fortune_pandas_balance": self.user.fortune_pandas_balance}, 200
        return {"message": response.get("msg")}, 400
        
