from dataclasses import dataclass
import json
import time
import requests
from decimal import Decimal
from rest_framework import status
from django.utils import timezone
from typing import Optional, Dict, List, Union, Tuple, cast
from decimal import Decimal
from hashlib import md5, sha1
from django.conf import settings

from apps.users.models import Users
from apps.casino.models import GSoftTransactions


@dataclass
class AppConfig:
    """Main configuration for App CPgames"""
    app_id: str
    api_url: str
    currency: str
    secret_key: str
    is_real_play: bool


class ApiCPGamesConfig:
    """This config should be use to create multiple Apps"""
    __slots__ = ('apps', 'has_fake_game')

    def __init__(self, apps: Optional[List[AppConfig]] = None):

        if apps is None or len(apps) < 1:
            real_money = AppConfig(
                app_id=settings.CP_GAMES_APP_ID_SC,
                api_url=settings.CP_GAMES_URL,
                currency='SC',
                secret_key=settings.CP_GAMES_SECRET_SC,
                is_real_play=True
            )

            fake_money = AppConfig(
                app_id=settings.CP_GAMES_APP_ID_GC,
                api_url=settings.CP_GAMES_URL,
                currency='GC',
                secret_key=settings.CP_GAMES_SECRET_GC,
                is_real_play=False
            )
            apps = [real_money, fake_money]

        self.apps: List[AppConfig] = apps
        self.has_fake_game = not all([app.is_real_play for app in self.apps])


class CPgames():

    ERRORS = {
        # 0 : "success",
        -1: "fail",
        1001: "In maintenance",
        1002: "The system is busy and the operation is in progress",
        1003: "game_key game parameter error",
        1004: "User sub_uid is empty",
        1006: "Login failed",
        1110: "Parameter error",
        1111: "Signature error",
        1112: "Request timed out",
        1113: "appid error",
        1115: "Wrong game id",
        1116: "Player does not exist",
        1117: "Player balance is insufficient",
        1118: "Order does not exist",
        1119: "Order error",
        1199: "Unknown error generic error return"
    }

    BASE_SUCCESS: Dict[str, str] = {
        "code": 0,  # pyright: ignore
        "msg": "success",
    }

    def __init__(self, config: Optional[dict] = None,
                 e_config: Optional[ApiCPGamesConfig] = None):
        if config is None:
            config = {}
        if e_config is None:
            e_config = ApiCPGamesConfig()

        self.econfig: ApiCPGamesConfig = e_config

        self.config = config
        self.config['api_domain'] = config.get(
            'api_domain', settings.CP_GAMES_URL)
        self.config['appid'] = config.get('appid', settings.CP_GAMES_APP_ID)
        self.config['secret'] = config.get('secret', settings.CP_GAMES_SECRET)

        self.session = requests.Session()
        self.availables_languages: list[str] = [
            "en", "th", "vi", "pt", "es", "bn", "ko", "id", "fr", "tr"]

    def __execute_api(self,
                      params: Optional[dict] = None,
                      url: str = "",
                      app: AppConfig) -> dict:
        if params is None:
            params = {}
        response = None
        try:
            self.session.headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
            })

            # generate the token
            data = {
                **params,
                "token": self.__generate_hash(params=params, app=app),
            }

            response = self.session.post(url=url, data=data)
            return response.json()
        except Exception as e:
            print(e)
            if response:
                print(response.text)
                if "503 service temporarily unavailable" in response.text.lower():
                    return {"code": 503, "msg": "Sorry, the service you're trying to access is currently unavailable. Please try again later."}
            return {"code": 500, "msg": "Sorry, there was a problem with the server response."}

    def __generate_hash(self, params: Optional[Dict[str, str]],
                        app: AppConfig) -> str:
        if params is None:
            params = {}

        # Sort the params
        param_keys: List[str] = list(params.keys())
        param_keys = sorted(param_keys)

        # Only hash the values where are different than None or 0
        # (sorted by name)
        d = "&".join([f"{p}={params.get(p)}" for p in param_keys if params.get(
            p) not in [None, "0", 0] and (p != "token")])
        # (except secret, always at the end)
        s_key = app.secret_key
        d += f"&secret={s_key}"

        # Following the docs: strtoupper(sha1(md5(string)))
        return sha1(md5(d.encode()).hexdigest().encode()).hexdigest().upper()

    @staticmethod
    def get_username(user: Users) -> str:
        u_name = str(user.username)
        return u_name if len(u_name) <= 32 else u_name[:29] + "..."

    @staticmethod
    def get_sub_uid(user: Users) -> str:
        return str(user.id) + settings.ENV_POSTFIX

    @staticmethod
    def get_user_from_uid(sub_uid: str) -> Optional[Users]:
        if not sub_uid.endswith(settings.ENV_POSTFIX):
            return None

        qs = Users.objects.filter(id=sub_uid[:-len(settings.ENV_POSTFIX)])
        return qs.first() if qs else None

    @staticmethod
    def get_base_params(app: AppConfig) -> Dict[str, Union[str, int]]:
        return {
            "appid": app.app_id,
            "game_key": "hog"
        }

    def select_user_for_update(self, sub_uid: str) -> Tuple[Optional[Users], Optional[Dict[str, str]]]:
        """
        This returns Tuple[Users,  dict(with error)],
        you can identify its an error if error is not None
        """

        # CHECK: user exist
        if not sub_uid:
            # sub_uid is Empty
            return None, self.parse_to_message(1004)
        if not sub_uid.endswith(settings.ENV_POSTFIX):
            # 1116 player does not exist
            return None, self.parse_to_message(1116)

        user_id = sub_uid[:-len(settings.ENV_POSTFIX)]

        user = Users.objects.select_for_update().filter(id=user_id).first()
        if not user:
            # 1116 player does not exist
            return None, self.parse_to_message(1116)

        return user, None

    def get_formated_balance(self,
                             user: Users,
                             app: AppConfig
                             ) -> Dict[str,
                                       Union[str, Dict[str, Union[str, int]]]]:
        balance = 0
        if app.is_real_play:
            balance = user.balance or 0
        else:
            balance = user.bonus_balance or 0
        return {
            **self.BASE_SUCCESS,
            "data": {
                "balance": str(round(Decimal(balance), 2)),
                "currency": app.currency,
                "updated_ms": int(time.time() * 1000)
            }
        }

    def login_user(self, user: Users, app: AppConfig) -> bool:
        params: dict[str, Union[str, int]] = self.get_base_params(app=app)

        params = {
            **params,
            "sub_uid": self.get_sub_uid(user=user),
            "user_name": self.get_username(user=user),
            "time": int(time.time()),
        }
        # Request example：
        # https://{api_domain}/api/login
        url = app.api_url + "api/login"
        # Request subject:
        # appid=appidtest001&game_key=hog&sub_uid=1001&user_name=&time=1401248256&token=xxxx

        response = self.__execute_api(params=params, url=url, app=app)

        if response.get("code") != 0:
            print(response.get("code"))

        return response.get("code") == 0

    def get_game_url(self,
                     user: Users,
                     game_id: str,
                     lang: str = "en",
                     fake_game: bool = False) -> str:
        if not self.econfig.has_fake_game and fake_game:
            return settings.PROJECT_DOMAIN
        app = None
        for lapp in self.econfig.apps:
            if lapp.is_real_play == fake_game:
                app = lapp
        if app is None:
            return settings.PROJECT_DOMAIN

        params = self.get_base_params(app=app)

        # The currency is set in the CP appid
        # there are a few apps you can chose from
        # to date 15/04/2025 is set to USD appid and secret
        params = {
            **params,
            "sub_uid": self.get_sub_uid(user=user),
            "game_id": game_id,
            "lang": lang if lang in self.availables_languages else "en",
            "time": int(time.time())
        }

        url = self.config.get("api_domain", "") + "api/get_game_url"
        result = self.__execute_api(params=params, url=url, app=app)

        if result.get("code") != 0:
            raise RuntimeError(f"API error: {result.get('code')} {
                               result.get('msg')}")

        return result.get("data", "")

    def get_games(self) -> Optional[List[Optional[Dict[str, str]]]]:
        ''' Example: return
        [
        {
            "name_en": "Lucky Cat",
            "game_id": "1_1",
            "type": "SLOTS"
        },...
        ]
        '''
        app = self.econfig.apps[0]
        params = self.get_base_params(app=app)
        params = {
            **params,
            "game_key": "hog",
            "time": int(time.time()),
        }

        url = app.api_url + "api/game_list"
        result = self.__execute_api(params=params, url=url, app=app)

        if result.get("code") != 0:
            return []

        return result.get("data")

    def get_games_on_db(self):
        return

    def verify_request(self, request: dict) -> Optional[AppConfig]:
        token = request.get("token")
        if not token:
            return

        app_id = request.get('appid', '')
        app = None
        for lapp in self.econfig.apps:
            if lapp.app_id == app_id:
                app = lapp
                continue
        if app is None:
            return

        result_token = self.__generate_hash(params=request, app=app)
        return app if result_token == token else None

    # This is only meant for external use only
    def get_user_balance(self, user_sub: Optional[str], app_id: str) -> Dict[str, Union[str, Dict[str, str]]]:
        app = None
        for lapp in self.econfig.apps:
            if lapp.app_id == app_id:
                app = lapp
                continue
        if app is None:
            return self.parse_to_message(1113)

        if not user_sub:
            return self.parse_to_message(1004)
        if not user_sub.endswith(settings.ENV_POSTFIX):
            # 1116 player does not exist
            return self.parse_to_message(1116)
        user_id = user_sub[:-len(settings.ENV_POSTFIX)]

        user = Users.objects.filter(id=user_id)
        if not user.exists():
            return self.parse_to_message(1116)

        user = user.first()

        balance = 0
        if app.is_real_play:
            balance = user.balance or 0
        else:
            balance = user.bonus_balance or 0
        return {
            **self.BASE_SUCCESS,
            "data": {
                "balance": str(round(Decimal(balance), 2)),
                "currency": app.currency,
            }
        }

    def transfer_in_out(self, data) -> Tuple[Dict, int]:
        to_verify = data.copy()
        app = self.verify_request(request=to_verify)
        if not app:
            # Signature error 1111
            response_data = self.parse_to_message(1111)
            return response_data, status.HTTP_401_UNAUTHORIZED

        try:
            msg = json.loads(data.get("message", "{}"))
            sub_uid: str = msg.get("sub_uid")
            user, error = self.select_user_for_update(sub_uid=sub_uid)
            if error is not None:
                return error, status.HTTP_400_BAD_REQUEST
            if user is None:
                return self.parse_to_message(1116), status.HTTP_400_BAD_REQUEST

            # 3.2: 1.
            game_id = msg.get("game_id")
            bet_info = msg.get("bet_info")
            bet_id = bet_info.get("bet_id")
            transaction_id = bet_info.get("transaction_id", bet_id)

            # 3.2: 4.
            round_id = bet_info.get("parent_bet_id")
            amount = Decimal(bet_info.get("bet_amout", 0))
            win_amount = Decimal(bet_info.get("win_amount", 0))
            transfer_amount = Decimal(bet_info.get("transfer_amount", 0))

            # CHECK: if the bet already exist
            # 3.2: 2.
            if GSoftTransactions.objects.filter(callerId=settings.CP_GAMES_ID,
                                                user=user,
                                                bet_id=bet_id).exists():
                return self.get_formated_balance(user=user, app=app), status.HTTP_200_OK

            # CHECK: win_amount is higher or equals to 0
            # 3.2: 7.
            if win_amount < 0:
                return self.parse_to_message(1110), status.HTTP_400_BAD_REQUEST

            balance = None
            if app.is_real_play:
                balance = user.balance or 0
            else:
                balance = user.bonus_balance or 0

            balance = Decimal(balance)  # type: ignore

            # Check if user  has enought money to bet
            if balance < amount:
                response_data = self.parse_to_message(1117)
                return response_data, status.HTTP_400_BAD_REQUEST

            withdraw = 0
            deposit = 0

            if transfer_amount < 0:
                withdraw = abs(transfer_amount)
                action_type = GSoftTransactions.ActionType.lose
            else:
                deposit = transfer_amount
                action_type = GSoftTransactions.ActionType.win

            transaction_obj = GSoftTransactions()
            transfer_balance = transfer_amount

            if app.is_real_play:
                user.balance = transfer_balance + Decimal(user.balance)
                transaction_obj.amount = abs(transfer_balance)
            else:
                user.bonus_balance = transfer_balance + \
                    Decimal(user.bonus_balance or 0)
                transaction_obj.bonus_bet_amount = abs(transfer_balance)
            user.save()

            transaction_obj.callerId = settings.CP_GAMES_ID
            transaction_obj.user = user
            transaction_obj.withdraw = withdraw
            transaction_obj.deposit = deposit
            transaction_obj.game_id = game_id
            transaction_obj.transaction_id = transaction_id
            transaction_obj.bet_id = bet_id
            transaction_obj.round_id = round_id
            transaction_obj.request_type = GSoftTransactions.RequestType.result
            transaction_obj.action_type = action_type
            transaction_obj.game_status = GSoftTransactions.GameStatus.completed
            transaction_obj.time = timezone.now()
            transaction_obj.save()

            return (self.get_formated_balance(user=user, app=app),
                    status.HTTP_200_OK)
        except AttributeError as e:
            print("grep here")
            print(e)
            return self.parse_to_message(1110), status.HTTP_400_BAD_REQUEST
        except TypeError as e:
            print("grep here")
            print(e)
            return self.parse_to_message(1110), status.HTTP_400_BAD_REQUEST

    def cancel_in_out(self, data) -> Tuple[Dict, int]:
        to_verify = data.copy()
        app = self.verify_request(request=to_verify)
        if not app:
            # Signature error 1111
            response_data = self.parse_to_message(1111)
            return response_data, status.HTTP_401_UNAUTHORIZED

        try:
            msg = json.loads(data.get("message", "{}"))
            sub_uid: str = msg.get("sub_uid")
            user, error = self.select_user_for_update(sub_uid=sub_uid)
            if error is not None:
                return error, status.HTTP_400_BAD_REQUEST
            if user is None:
                return self.parse_to_message(1116), status.HTTP_400_BAD_REQUEST

            # 3.4: 1.
            game_id = msg.get("game_id")
            bet_id = msg.get("bet_id")

            # CHECK: if the bet already exist
            # 3.2: 2.
            qs = GSoftTransactions.objects.filter(
                callerId=settings.CP_GAMES_ID,
                user=user,
                game_id=bet_id,
            )
            has_rolled = qs.filter(
                request_type=GSoftTransactions.RequestType.rollback)
            if has_rolled.exists() or not qs.exists():
                return self.get_formated_balance(user=user, app=app), status.HTTP_200_OK

            to_rollback = qs.first()
            if to_rollback is None:
                return self.get_formated_balance(user=user, app=app), status.HTTP_200_OK

            # CHECK: win_amount is higher or equals to 0
            # 3.2: 7.
            deposit = to_rollback.deposit or Decimal(0)
            withdraw = to_rollback.withdraw or Decimal(0)
            if withdraw > 0:
                multipliyer = 1
            else:
                multipliyer = -1

            transfer_bonus: Decimal = Decimal(
                to_rollback.amount or 0) * multipliyer
            transfer_balance: Decimal = Decimal(
                to_rollback.bonus_bet_amount or 0) * multipliyer

            user.bonus_balance = transfer_bonus + \
                Decimal(user.bonus_balance or 0)
            user.balance = transfer_balance + Decimal(user.balance or 0)
            user.save()

            transaction_obj = GSoftTransactions()
            transaction_obj.callerId = settings.CP_GAMES_ID
            transaction_obj.user = user
            transaction_obj.deposit = deposit if deposit != 0 else None
            transaction_obj.withdraw = withdraw if withdraw != 0 else None
            transaction_obj.game_id = game_id
            transaction_obj.transaction_id = to_rollback.transaction_id
            transaction_obj.bet_id = bet_id
            transaction_obj.round_id = to_rollback.round_id
            transaction_obj.request_type = GSoftTransactions.RequestType.rollback
            transaction_obj.action_type = GSoftTransactions.ActionType.rollback
            transaction_obj.amount = abs(transfer_balance)
            transaction_obj.bonus_bet_amount = abs(transfer_bonus)
            transaction_obj.time = timezone.now()
            transaction_obj.game_status = GSoftTransactions.GameStatus.completed
            transaction_obj.save()

            return self.get_formated_balance(user=user, app=app), status.HTTP_200_OK
        except AttributeError:
            return self.parse_to_message(1110), status.HTTP_400_BAD_REQUEST
        except TypeError:
            return self.parse_to_message(1110), status.HTTP_400_BAD_REQUEST

    # 3.4: Bet

    def place_bet(self, data) -> Tuple[Dict, int]:
        to_verify = data.copy()
        app = self.verify_request(request=to_verify)
        if not app:
            # Signature error 1111
            response_data = self.parse_to_message(1111)
            return response_data, status.HTTP_401_UNAUTHORIZED

        try:
            msg = json.loads(data.get("message", "{}"))
            sub_uid: str = msg.get("sub_uid")
            user, error = self.select_user_for_update(sub_uid=sub_uid)
            if error is not None:
                return error, status.HTTP_400_BAD_REQUEST
            if user is None:
                return self.parse_to_message(1116), status.HTTP_400_BAD_REQUEST

            # 3.4: 1.
            game_id = msg.get("game_id")
            bet_info = msg.get("bet_info")
            bet_id = bet_info.get("bet_id")
            transaction_id = bet_info.get("transaction_id")

            # 3.4: 2.
            round_id = bet_info.get("round_id")
            amount = Decimal(bet_info.get("bet_amount", 0))

            # CHECK: if the bet already exist
            if GSoftTransactions.objects.filter(callerId=settings.CP_GAMES_ID,
                                                user=user,
                                                bet_id=bet_id).exists():
                return self.get_formated_balance(
                    user=user, app=app), status.HTTP_200_OK

            # CHECK: win_amount is higher or equals to 0
            # 3.2: 7.
            if app.is_real_play:
                balance = Decimal(user.balance or 0)
            else:
                balance = Decimal(user.bonus_balance or 0)

            # Check if user  has enought money to bet
            if balance < amount:
                response_data = self.parse_to_message(1117)
                return response_data, status.HTTP_400_BAD_REQUEST

            transfer_balance = - abs(amount)
            withdraw = abs(amount)

            transaction_obj = GSoftTransactions()

            if app.is_real_play:
                user.balance = transfer_balance + balance
                transaction_obj.amount = abs(transfer_balance)
            else:
                transaction_obj.bonus_bet_amount = abs(transfer_balance)
                user.bonus_balance = transfer_balance + balance
            user.save()

            transaction_obj.callerId = settings.CP_GAMES_ID
            transaction_obj.user = user
            transaction_obj.withdraw = withdraw
            transaction_obj.game_id = game_id
            transaction_obj.transaction_id = transaction_id
            transaction_obj.bet_id = bet_id
            transaction_obj.round_id = round_id
            transaction_obj.request_type = GSoftTransactions.RequestType.wager
            transaction_obj.action_type = GSoftTransactions.ActionType.bet
            transaction_obj.time = timezone.now()
            transaction_obj.game_status = GSoftTransactions.GameStatus.pending
            transaction_obj.save()

            return self.get_formated_balance(user=user, app=app), status.HTTP_200_OK
        except AttributeError as e:
            print("grep here")
            print(e)
            return self.parse_to_message(1110), status.HTTP_400_BAD_REQUEST
        except TypeError as e:
            print("grep here")
            print(e)
            return self.parse_to_message(1110), status.HTTP_400_BAD_REQUEST

    def cancel_bet(self, data) -> Tuple[Dict, int]:
        to_verify = data.copy()
        app = self.verify_request(request=to_verify)
        if not app:
            # Signature error 1111
            response_data = self.parse_to_message(1111)
            return response_data, status.HTTP_401_UNAUTHORIZED

        try:
            msg = json.loads(data.get("message", "{}"))
            sub_uid: str = msg.get("sub_uid")
            user, error = self.select_user_for_update(sub_uid=sub_uid)
            if error is not None:
                return error, status.HTTP_400_BAD_REQUEST
            if user is None:
                return self.parse_to_message(1116), status.HTTP_400_BAD_REQUEST

            # 3.4: 1.
            game_id = msg.get("game_id")
            bet_info = msg.get("bet_info")
            bet_id = bet_info.get("bet_id")
            transaction_id = bet_info.get("transaction_id", bet_id)

            # 3.2: 4.
            round_id = bet_info.get("round_id")

            # CHECK: if the bet already exist
            # 3.2: 2.
            qs = GSoftTransactions.objects.filter(
                callerId=settings.CP_GAMES_ID,
                user=user,
                bet_id=bet_id,
            )
            if qs.filter(request_type=GSoftTransactions.RequestType.rollback).exists() or not qs.exists():
                return self.get_formated_balance(user=user, app=app), status.HTTP_200_OK

            to_rollback = qs.first()
            if not to_rollback:
                return self.get_formated_balance(user=user, app=app), status.HTTP_200_OK

            # CHECK: win_amount is higher or equals to 0
            # 3.2: 7.
            deposit = Decimal(to_rollback.deposit or 0)
            withdraw = Decimal(to_rollback.withdraw or 0)
            if withdraw > 0:
                multipliyer = 1
            else:
                multipliyer = -1

            transfer_bonus: Decimal = Decimal(
                to_rollback.amount or 0) * multipliyer
            transfer_balance: Decimal = Decimal(
                to_rollback.bonus_bet_amount or 0) * multipliyer

            user.bonus_balance = transfer_bonus + Decimal(user.bonus_balance)
            user.balance = transfer_balance + Decimal(user.balance)
            user.save()
            to_rollback.game_status = GSoftTransactions.GameStatus.completed

            transaction_obj = GSoftTransactions()
            transaction_obj.callerId = settings.CP_GAMES_ID
            transaction_obj.user = user
            transaction_obj.deposit = deposit if deposit != 0 else None
            transaction_obj.withdraw = withdraw if withdraw != 0 else None
            transaction_obj.game_id = game_id
            transaction_obj.transaction_id = transaction_id
            transaction_obj.bet_id = bet_id
            transaction_obj.round_id = round_id
            transaction_obj.request_type = GSoftTransactions.RequestType.rollback
            transaction_obj.action_type = GSoftTransactions.ActionType.rollback
            transaction_obj.amount = abs(transfer_balance)
            transaction_obj.bonus_bet_amount = abs(transfer_bonus)
            transaction_obj.game_status = GSoftTransactions.GameStatus.completed
            transaction_obj.time = timezone.now()
            transaction_obj.save()

            return self.get_formated_balance(user=user, app=app), status.HTTP_200_OK
        except AttributeError as e:
            print("grep here")
            print(e)
            return self.parse_to_message(1110), status.HTTP_400_BAD_REQUEST
        except TypeError as e:
            print("grep here")
            print(e)
            return self.parse_to_message(1110), status.HTTP_400_BAD_REQUEST

    def settle(self, data) -> Tuple[Dict, int]:
        to_verify = data.copy()
        app = self.verify_request(request=to_verify)
        if not app:
            # Signature error 1111
            response_data = self.parse_to_message(1111)
            return response_data, status.HTTP_401_UNAUTHORIZED

        try:
            msg = json.loads(data.get("message", "{}"))
            sub_uid: str = msg.get("sub_uid")
            user, error = self.select_user_for_update(sub_uid=sub_uid)
            if error is not None:
                return error, status.HTTP_400_BAD_REQUEST
            if user is None:
                return self.parse_to_message(1116), status.HTTP_400_BAD_REQUEST

            # 3.4: 1.
            game_id = msg.get("game_id")
            bet_info = msg.get("bet_info", "{}")
            bet_id = bet_info.get("bet_id")
            round_id = bet_info.get("round_id")
            transaction_id = bet_info.get("transaction_id")
            settle_type = bet_info.get("settle_type")

            bet_amount = Decimal(bet_info.get("bet_amount", 0))
            payout = Decimal(bet_info.get("win_amount", 0))

            # CHECK: if the bet already exist
            # 3.2: 2.
            case_a = settle_type == "bet_id"
            case_b = settle_type == "round_id"

            qs = GSoftTransactions.objects.filter(
                callerId=settings.CP_GAMES_ID,
                user=user,
                bet_id=bet_id,
                game_status=GSoftTransactions.GameStatus.completed,
            )
            if qs.exists():
                return self.get_formated_balance(user=user,
                                                 app=app), status.HTTP_200_OK

            # CHECK: win_amount is higher or equals to 0
            # 3.2: 7.

            all_games = qs
            if case_a:
                # bet amount
                all_games = qs.values_list(
                    "deposit", "withdraw", "amount", "bonus_bet_amount")

            elif case_b:
                all_games = GSoftTransactions.objects.filter(
                    callerId=settings.CP_GAMES_ID,
                    round_id=round_id
                )
                all_games.update(
                    game_status=GSoftTransactions.GameStatus.completed)
                all_games = qs.values_list(
                    "deposit", "withdraw", "amount", "bonus_bet_amount")

            if payout < 0:
                return self.parse_to_message(1110), status.HTTP_400_BAD_REQUEST

            given_from_bonus = Decimal(0)
            given_from_balance = Decimal(0)
            for item in all_games:
                if item[0] is not None and item[0] > 0:
                    given_from_bonus -= Decimal(item[3])
                    given_from_balance -= Decimal(item[2])
                elif item[1] is not None and item[1] > 0:
                    given_from_bonus += Decimal(item[3])
                    given_from_balance += Decimal(item[2])

            if given_from_bonus > 0:
                transfer_bonus = min(given_from_bonus, payout)
            else:
                transfer_bonus = Decimal(0)
            transfer_balance = payout - transfer_bonus

            user.bonus_balance = transfer_bonus + Decimal(user.bonus_balance)
            user.balance = transfer_balance + Decimal(user.balance)
            user.save()

            transaction_obj = GSoftTransactions()
            transaction_obj.callerId = settings.CP_GAMES_ID
            transaction_obj.user = user
            transaction_obj.deposit = payout if payout != 0 else None
            transaction_obj.game_id = game_id
            transaction_obj.transaction_id = transaction_id
            transaction_obj.bet_id = bet_id
            transaction_obj.round_id = round_id
            transaction_obj.request_type = GSoftTransactions.RequestType.result
            transaction_obj.action_type = GSoftTransactions.ActionType.rollback
            transaction_obj.amount = abs(transfer_balance)
            transaction_obj.bonus_bet_amount = abs(transfer_bonus)
            transaction_obj.time = timezone.now()
            transaction_obj.game_status = GSoftTransactions.GameStatus.completed
            transaction_obj.save()

            return self.get_formated_balance(user=user, app=app), status.HTTP_200_OK
        except AttributeError as e:
            print("grep here")
            print(e)
            return self.parse_to_message(1110), status.HTTP_400_BAD_REQUEST
        except TypeError as e:
            print("grep here")
            print(e)
            return self.parse_to_message(1110), status.HTTP_400_BAD_REQUEST

    def save_request(self, request, is_response=False):
        file = "cp_request_log.txt"
        ts = str(time.time())
        full_url = request.build_absolute_uri() if not is_response else "response:"
        from pprint import pformat
        data = pformat(request.data) if not is_response else pformat(request)

        entry = (
            f"\n--- {ts} ---\n"
            f"URL: {full_url}\n"
            f"DATA:\n{data}\n"
        )

        with open(file, 'a') as f:
            f.write(entry)

    def start_game(self, request_param):
        game_id = request_param.get("game_id")
        lang = request_param.get("lang", "en")
        account_id = request_param.get("account_id")
        fake_game = bool(request_param.get('GC'))

        user = Users.objects.filter(casino_account_id=account_id).first()
        if not user:
            return False, {"success": False, "message": "User with given account_id not found"}

        app = None
        for lapp in self.econfig.apps:
            if not lapp.is_real_play == fake_game:
                app = lapp
                break
        if app is None:
            return False, {"success": False,
                           "message": "Not app available was found"}}

        result = self.login_user(user, app=app)

        lang = lang if lang in self.availables_languages else "en"
        url = self.get_game_url(user=user,
                                game_id=game_id,
                                lang=lang,
                                fake_game=fake_game)

        response = {
            "success": True,
            "url": {
                "jsonrpc": "2.0",
                "id": 1008,
                "result": {
                    "SessionId": "",
                    "SessionUrl": url
                }
            }
        }

        if response and result:
            return True, response
        else:
            return False, {"success": False, "message": "Game is unavailable, plese try again in a few minutes."}

    @classmethod
    def parse_to_message(cls, code: int):
        return {"msg": cls.ERRORS.get(code, 1199), "code": code if code in cls.ERRORS.keys() else 1199}
