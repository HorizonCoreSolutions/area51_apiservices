from decimal import Decimal
import hashlib
import hmac
import urllib
import uuid

import requests
from django.utils import timezone
import uuid
import enum
from rest_framework import status
from django.conf import settings
from apps.bets.models import Transactions
from apps.bets.utils import generate_reference

from apps.users.models import BonusPercentage, Player, Users


def format_date(date_time=timezone.now()):
    return "%sZ" % date_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:23]


class CasinoApiClinet(object):
    def __init__(self, url=settings.CASINO_API_URL, key=settings.CASINO_API_KEY):
        self.api_url = url
        self.api_key = key

    def send_data(self, params: dict):
        join_params = ""
        post_params = {}

        rand = str(uuid.uuid4())

        for key, val in params.items():
            if isinstance(val, list):
                val = ",".join(val)
            enc_val = urllib.parse.quote(val, safe="")

            post_params[key] = enc_val
            join_params += enc_val

        post_params["callid"] = rand
        join_params += rand

        key = self.api_key.encode('utf-8')
        msg = join_params.encode('utf-8')

        sign = hmac.new(key=key, msg=msg, digestmod=hashlib.sha1).hexdigest()
        post_params["sign"] = sign

        query_params = []
        for key, val in post_params.items():
            query_params.append(key + '=' + val)

        query_params = "&".join(query_params).encode("utf-8")
        response = requests.post(url=self.api_url, data=query_params, headers={'User-Agent': 'curl', 'Content-Type': 'application/x-www-form-urlencoded'}, timeout=15)
        return response


class GamePoolApiClinet(object):
    def __init__(self):
        pass


class ErrorResponseMsg(enum.Enum):
    INVALID_TOKEN = {"code": "INVALID_TOKEN", "message": "Missing player session token."}
    LOGIN_FAILED = {"code": "LOGIN_FAILED", "message": "Missing pass-key."}
    ACCOUNT_BLOCKED = {"code": "ACCOUNT_BLOCKED", "message": "The player account is blocked."}
    UNKNOWN_ERROR = {"code": "UNKNOWN_ERROR", "message": "Unexpected error."}
    INSUFFICIENT_FUNDS = {"code": "INSUFFICIENT_FUNDS",
                          "message": "Requested Amount is higher than the player's balance"
                          }
    REQUEST_DECLINED = {"code": "REQUEST_DECLINED", "message": "Missing required header parameters"}
    PLAYER_NOT_FOUND = {"code": "PLAYER_NOT_FOUND", "message": "Player Not Found"}
    INVALID_FORMAT = {"code": "INVALID_FORMAT",
                      "message": "The request could not be processed due to invalid JSON format."}
    VALIDATION_ERROR = {"code": "VALIDATION_ERROR",
                        "message": "The request could not be processed due to validation error."}
    QT_NOT_AVAILABLE = {"code": "QT_NOT_AVAILABLE",
                        "message": "QT Platform is not available. Temporary down, under maintenance etc."}
    GAME_NOT_FOUND = {"code": "GAME_NOT_FOUND", "message": "Game with the given id was not found."}
    GAME_NOT_AVAILABLE = {"code": "GAME_NOT_AVAILABLE", "message": "Game with the given id was not found."}


class ValidateRequest:

    def create_transaction_id(self):
        transaction_id = str(uuid.uuid4())
        return transaction_id

    def validate_request(self, session_id, pass_key, player, check_session=True):
        casino_pass_key = settings.CASINO_PASS_KEY
        print(f"Player Callback Key: {player.callback_key}")
        print(f"Session id Key: {session_id}")
        try:
            if not session_id and check_session:
                return {'msg': ErrorResponseMsg.INVALID_TOKEN.value, 'status': status.HTTP_400_BAD_REQUEST}
            if not pass_key:
                return {'msg': ErrorResponseMsg.LOGIN_FAILED.value, 'status': status.HTTP_401_UNAUTHORIZED}

            # Authenticate Pass - Key
            if pass_key != casino_pass_key:
                return {'msg': ErrorResponseMsg.LOGIN_FAILED.value, 'status': status.HTTP_401_UNAUTHORIZED}

            if not player:
                return {'msg': ErrorResponseMsg.ACCOUNT_BLOCKED.value, 'status': status.HTTP_403_FORBIDDEN}

            # Authenticate Session ID
            if session_id != player.callback_key and check_session:
                return {'msg': ErrorResponseMsg.INVALID_TOKEN.value, 'status': status.HTTP_400_BAD_REQUEST}
        except Exception as e:
            print(e)
            return {'msg': ErrorResponseMsg.UNKNOWN_ERROR.value, 'status': status.HTTP_500_INTERNAL_SERVER_ERROR}
        return {'msg': "Valid Request", 'status': status.HTTP_200_OK}


def return_possible_game_error(status_code, service_url):
    if status_code == 400:
        return ErrorResponseMsg.INVALID_FORMAT.value
    elif status_code == 422:
        return ErrorResponseMsg.VALIDATION_ERROR.value
    elif status_code == 401:
        return ErrorResponseMsg.INVALID_TOKEN.value
    elif status_code == 500:
        return ErrorResponseMsg.UNKNOWN_ERROR.value
    elif status_code == 503:
        return ErrorResponseMsg.QT_NOT_AVAILABLE.value
    else:
        return service_url

class GSoftUtils(object):
    something = ""
    
from datetime import date    
from apps.casino.models import Tournament, UserTournament
# bet bonus to player on wager place    
def bet_bonus(user,betamount):
    user = Player.objects.filter(id=user).first()
    bonus_obj = BonusPercentage.objects.filter(bonus_type='bet_bonus').first()
    if bonus_obj and bonus_obj.percentage and bonus_obj.percentage>0:
            if bonus_obj.bet_bonus_limit and bonus_obj.bet_bonus_limit<=float(betamount):
                        bet_bonus_given_count = Transactions.objects.filter(user=user, bonus_type=f"bet_bonus", created__date=date.today()).count()
                        if bonus_obj.bet_bonus_per_day_limit > bet_bonus_given_count:
                            bet_bonus_balance = round(Decimal(float( user.bonus_balance) + float(betamount) * float(bonus_obj.percentage/ 100)), 2)
                            bet_bonus = round(Decimal( float(betamount) * float(bonus_obj.percentage/ 100)), 2)
                            previous_bal = user.balance
                            user.bonus_balance = bet_bonus_balance
                            # user.balance += bet_bonus
                            bonus_to_be_given = bet_bonus
                            Transactions.objects.update_or_create(
                                    user=user,
                                    journal_entry="bonus",
                                    amount=betamount,
                                    status="charged",
                                    merchant=user.admin,
                                    previous_balance=previous_bal,
                                    new_balance=user.balance,
                                    description=f'bet bonus deposited to player for amount {betamount}',
                                    reference=generate_reference(user),
                                    bonus_type=f"bet_bonus",
                                    bonus_amount=bonus_to_be_given
                            )   
                            user.save()
                            

def get_user_tournament_rank(user_tournament: UserTournament):
    user_rank = list(UserTournament.objects.filter(
        tournament = user_tournament.tournament,
        win_points__gte=user_tournament.win_points
    ).order_by("-win_points", "last_win_at").values_list("id", flat=True))
        
    return user_rank.index(user_tournament.id) + 1

