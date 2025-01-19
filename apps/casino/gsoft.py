import json
import uuid
import requests
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.bets.models import Transactions
from apps.bets.utils import generate_reference

from apps.casino.models import CasinoGameList, Users, GSoftTransactions
from apps.users.models import BonusPercentage, Users, PlayerBettingLimit
from apps.casino.utils import GSoftUtils, bet_bonus
from apps.casino.serializers import GameListSerializer

class GsoftCasino:
    utils = GSoftUtils()

    def __init__(self):
        self.operator_id = settings.GSOFT_OPERATOR_ID
        self.sinatra_url = settings.GSOFT_SINATRA_URL
        self.start_game_url = settings.GSOFT_START_GAME_URL
        self.game_list_url = f"{self.sinatra_url}/games/1.0.0/view/detailed"
        self.login_url = f"{self.sinatra_url}/1.0/login"
        self.error_messages = {
            "internal_error": {"code": 1, "status": "Technical error", "message": "Technical error"},
            "operation_not_allowed": {"code": 110, "status": "Operation not allowed", "message": "Operation not allowed"},
            "authentication_error": {"code": 1003, "status": "Authentication failed", "message": "authentication failed"},
            "transaction_parameter_mismatch": {"code": 400, "status": "Transaction parameter mismatch", "message": "Transaction parameter mismatch"},
            "round_already_closed": {"code": 409, "status": "Round closed or transaction ID exists", "message": "Round closed or transaction ID exists"},
            "transaction_already_in_use": {"code": 409, "status": "transactionId already in use", "message": "transactionId already in use"},
            "unauthenticated": {"code": 1000, "status": "Not logged on", "message": "Not logged on"},
            "low_balance": {"code": 1006, "status": "Out of money", "message": "Out of money"},
            "limit_exceed": {"code": 1019, "status": "Gaming limit", "message": "overall wager limit exceeded"},
            "parameter_required": {"code": 1008, "status": "Parameter required", "message": "Parameter required"},
            "wager_not_found" : {"code" : 102, "status" : "Wager not found", "message" : "wager not found"},
        }

    def get_player_detail(self, request_param):
        game_session_id = request_param.get("gamesessionid")
        account_id = request_param.get("accountid")
        api_version = request_param.get("apiversion")

        user = Users.objects.filter(casino_account_id=account_id).first()
        if user and user.callback_key == game_session_id:
            response = {
                "code": 200,
                "status": "Success",
                "accountid": account_id,
                "city": user.state,
                "country": user.country,
                "currency": user.currency,
                "gamesessionid": game_session_id,
                "real_balance": float(user.balance),
                "bonus_balance": 0.00,
                "game_mode": 1,
                "order": "cash_money, bonus_money",
                "apiversion": api_version,
            }
            return True, response
        else:
            return False, self.error_messages.get("authentication_error")

    def get_player_balance(self, request_param):
        game_session_id = request_param.get("gamesessionid")
        account_id = request_param.get("accountid")
        api_version = request_param.get("apiversion")

        user = Users.objects.filter(casino_account_id=account_id).first()
        if user and user.callback_key == game_session_id:
            response = {
                "code": 200,
                "status": "Success",
                "balance": float(user.balance),
                "bonus_balance": 0.00,
                "real_balance": float(user.balance),
                "game_mode": 1,
                "order": "cash_money, bonus_money",
                "apiversion": api_version
            }
            return True, response
        else:
            return False, self.error_messages.get("internal_error")

    def game_list(self, request_param):
        game_list = CasinoGameList.objects.all()
        print(len(game_list), "===============")
        if game_list:
            casino_games = GameListSerializer(game_list, many=True)
            # casino_games = game_list
            return True, {"success": True, "game_list": casino_games}
        else:
            return True, {"success": False, "message":"No games found"}
        
    def get_jwt_auth_token(self):
        data = {
            "email": settings.GSOFT_EMAIL,
            "password": settings.GSOFT_PASSWORD
        }
        response = requests.post(self.login_url, json=data)
        if response.status_code == 200:
            jwt_auth = response.headers.get("jwt-auth")
            return jwt_auth
        return None

    def start_game(self, request_param):
        nogs_game_id = request_param.get("nogs_game_id")
        nogs_lang = request_param.get("nogs_lang")
        nogs_mode = request_param.get("nogs_mode")
        account_id = request_param.get("account_id")
        device_type = request_param.get("device_type")
        country = request_param.get("country")
        is_test_account = request_param.get("is_test_account")
        homeurl = settings.GSOFT_HOME_URL
        license = settings.GSOFT_LICENCE
        if nogs_game_id and nogs_lang and nogs_mode and account_id and device_type and country and is_test_account:
            user = Users.objects.filter(casino_account_id=account_id).first()
            if not user:
                return False, {"success": False, "message": "User with given account_id not found"}
            
            if nogs_mode.lower() == "demo":
                session_id = 0
                account_id = 'as213'
            else:
                session_id =  f"{str(self.operator_id)}_{str(uuid.uuid4())}"
                user.callback_key = session_id
                user.save()
            
            url = f"{self.start_game_url}/game?nogsgameid={nogs_game_id}&nogsoperatorid={self.operator_id}&sessionid={session_id}&nogscurrency={user.currency}&nogslang={nogs_lang}&nogsmode={nogs_mode}&accountid={account_id}&homeurl={homeurl}&device_type={device_type}&country={country}&is_test_account={is_test_account}&license={license}"
            return True, {"success": True,"url": url}
        else:
            return False, {"success": False, "message": "Please provide all required params - nogs_game_id, nogs_lang, nogs_mode, account_id, homeurl, device_type, country, is_test_account"}

    @transaction.atomic
    def wager(self, request_param):
        account_id = request_param.get("accountid")
        betamount = request_param.get("betamount")
        gameid = request_param.get("gameid")
        game_session_id = request_param.get("gamesessionid")
        device = request_param.get("device")
        roundid = request_param.get("roundid")
        transactionid = request_param.get("transactionid")
        apiversion = request_param.get("apiversion")
        request = request_param.get("request")
        frbid = request_param.get("frbid")
        user = Users.objects.filter(casino_account_id=account_id).first()
        if user and user.callback_key == game_session_id:
            transaction = GSoftTransactions.objects.filter(
                transaction_id = transactionid, 
                round_id = roundid,
                action_type = GSoftTransactions.ActionType.bet
            ).last()
            if transaction:
                print(f"casino bet :{round(float(transaction.amount),2)},  {round(float(betamount),2)}")
                if transaction.user.casino_account_id != account_id or round(float(transaction.amount),2) != round(float(betamount),2):
                    return False, self.error_messages.get("transaction_parameter_mismatch")
                
                response = {
                    "code": 200,
                    "status": "Success - duplicate request",
                    "accounttransactionid": transactionid,
                    "balance": float(user.balance),
                    "bonusmoneybet": 0.00,
                    "realmoneybet": betamount,
                    "bonus_balance": 0.00,
                    "real_balance": float(user.balance),
                    "game_mode": 1,
                    "order": "cash_money, bonus_money",
                    "apiversion": apiversion
                }
                return True, response
            if not frbid:
                if float(user.balance) < round(float(betamount),2):
                    return False, self.error_messages.get("low_balance")
                
                bet_limit = PlayerBettingLimit.objects.filter(player=user).first()
                if bet_limit:
                    utilized_amount = bet_limit.utilized_amount
                    utilized_amount += round(float(betamount),2)

                    if utilized_amount > round(float(bet_limit.amount),2):
                        return False, self.error_messages.get("limit_exceed")

                    bet_limit.utilized_amount = utilized_amount
                    bet_limit.save()

                amt = float(user.balance)
                amt -= round(float(betamount),2)
                user.balance = amt
                # deducting bonus amount
                try:
                    if float(user.bonus_balance) > 0:
                        if float(user.bonus_balance) >= round(float(betamount),2):
                                user.bonus_balance = float(user.bonus_balance) -round(float(betamount),2)
                        else:
                                user.bonus_balance = Decimal(0.00)
                except Exception as e:
                    pass
                user.save()
            
            transaction_obj = GSoftTransactions()
            transaction_obj.user = user
            transaction_obj.amount = round(float(betamount),2)
            transaction_obj.game_id = gameid
            transaction_obj.device = device
            transaction_obj.round_id = roundid
            transaction_obj.transaction_id = transactionid
            transaction_obj.request_type = GSoftTransactions.RequestType.wager
            transaction_obj.action_type = GSoftTransactions.ActionType.bet
            transaction_obj.frbid = frbid
            transaction_obj.gamesession_id =game_session_id
            transaction_obj.time = timezone.now()
            transaction_obj.save()
            
            response = {
                "code": 200,
                "status": "Success",
                "accounttransactionid": transactionid,
                "balance": float(user.balance),
                "bonusmoneybet": 0.00,
                "realmoneybet": betamount,
                "bonus_balance": 0.00,
                "real_balance": float(user.balance),
                "game_mode": 0,
                "order": "cash_money, bonus_money",
                "apiversion": apiversion
            }
            try:
                bet_bonus(user.id,betamount)
            except Exception as e:
                pass
            return True, response
        else:
            return False, self.error_messages.get("operation_not_allowed")

    @transaction.atomic
    def result(self, request_param):
        account_id = request_param.get("accountid")
        game_session_id = request_param.get("gamesessionid")
        game_status = request_param.get("gamestatus")
        result_amount = request_param.get("result")
        game_id = request_param.get("gameid")
        round_id = request_param.get("roundid")
        transaction_id = request_param.get("transactionid")
        api_version = request_param.get("apiversion")
        request = request_param.get("request")
        frbid = request_param.get("frbid")
        device = request_param.get("device")
        
        user = Users.objects.filter(casino_account_id=account_id).first()
        user_id = GSoftTransactions.objects.filter(gamesession_id=game_session_id,round_id=round_id).first().user.id
        if user and user_id and user.id == user_id and round(float(result_amount),2) >= 0 and game_status in ["completed", "pending"]:
            transaction = GSoftTransactions.objects.filter(
                transaction_id=transaction_id,
                round_id=round_id,
                request_type=GSoftTransactions.RequestType.result
            ).last()
            if transaction:
                if transaction.user.casino_account_id != account_id or round(float(transaction.amount),2) != round(float(result_amount),2):
                    return False, self.error_messages.get("transaction_parameter_mismatch")
                response = {
                    "code": 200,
                    "status": "Success - duplicate request",
                    "walletTx": transaction_id,
                    "balance": float(user.balance),
                    "bonusWin": 0.00,
                    "realMoneyWin": result_amount,
                    "bonus_balance": 0.00,
                    "real_balance": float(user.balance),
                    "game_mode": 0,
                    "order": "cash_money, bonus_money",
                    "apiversion": api_version
                }
                return True, response
            elif GSoftTransactions.objects.filter(round_id=round_id, game_status=GSoftTransactions.GameStatus.completed).exists():
                return False, self.error_messages.get("round_already_closed")
            
            bet_transaction = GSoftTransactions.objects.filter(
                user__casino_account_id = account_id, 
                action_type = GSoftTransactions.ActionType.bet,
                round_id = round_id
            ).last()
            if not frbid and bet_transaction == None:
                return False, self.error_messages.get("wager_not_found")

            if float(result_amount) > 0:
                user.balance += round(Decimal(result_amount),2)
                user.save()
            
            transaction_obj = GSoftTransactions()
            transaction_obj.user = user
            transaction_obj.amount = round(float(result_amount),2)
            transaction_obj.game_id = game_id
            transaction_obj.device = device
            transaction_obj.round_id = round_id
            transaction_obj.transaction_id = transaction_id
            transaction_obj.request_type = GSoftTransactions.RequestType.result
            transaction_obj.action_type = GSoftTransactions.ActionType.win if float(result_amount)>0 else GSoftTransactions.ActionType.lose
            transaction_obj.game_status = GSoftTransactions.GameStatus.completed if game_status == "completed" else GSoftTransactions.GameStatus.pending
            transaction_obj.frbid = frbid
            transaction_obj.time = timezone.now()
            transaction_obj.save()
            
            response = {
                "code": 200,
                "status": "Success",
                "walletTx": transaction_id,
                "balance": float(user.balance),
                "bonusWin": 0.00,
                "realMoneyWin": result_amount,
                "bonus_balance": 0.00,
                "real_balance": float(user.balance),
                "game_mode": 0,
                "order": "cash_money, bonus_money",
                "apiversion": api_version
            }
            return True, response
        else:
            return False, self.error_messages.get("operation_not_allowed")

    @transaction.atomic
    def wager_and_result(self,request_param):
        account_id = request_param.get("accountid")
        bet_amount = request_param.get("betamount")
        game_session_id = request_param.get("gamesessionid")
        game_id = request_param.get("gameid")
        device = request_param.get("device")
        round_id = request_param.get("roundid")
        transaction_id = request_param.get("transactionid")
        game_status = request_param.get("gamestatus")
        result_amount = request_param.get("result")
        api_version = request_param.get("apiversion")
        # request = request_param.get("request")
        frbid = request_param.get("frbid")

        user = Users.objects.filter(casino_account_id=account_id).first()
        if user and user.callback_key == game_session_id and round(float(result_amount),2) >= 0 and game_status in ["completed", "pending"]:
            transaction = GSoftTransactions.objects.filter(
                transaction_id = transaction_id,
                round_id = round_id,
                action_type = GSoftTransactions.ActionType.bet
            ).last()
            if transaction:
                if transaction.user.casino_account_id != account_id or float(transaction.amount) != float(bet_amount):
                    return False, self.error_messages.get("transaction_parameter_mismatch")

                response = {
                    "code": 200,
                    "status": "Success - duplicate request",
                    "walletTx": transaction_id,
                    "balance": round(Decimal(user.balance),2),
                    "bonusWin": Decimal(0.00),
                    "realmoneywin": round(Decimal(result_amount),2),
                    "bonusmoneybet": Decimal(0.00),
                    "realmoneybet": round(Decimal(bet_amount),2),
                    "bonus_balance": Decimal(0.00),
                    "real_balance": round(Decimal(user.balance),2),
                    "game_mode": 0,
                    "order": "cash_money, bonus_money",
                    "apiversion": api_version
                }
                return True,response
            elif GSoftTransactions.objects.filter(round_id=round_id, game_status=GSoftTransactions.GameStatus.completed).exists():
                return False, self.error_messages.get("round_already_closed")

            if not frbid:
                if float(user.balance) < round(float(bet_amount),2):
                    return False, self.error_messages.get("low_balance")
                
                bet_limit = PlayerBettingLimit.objects.filter(player=user).exists()
                if bet_limit:
                    utilized_amount = bet_limit.utilized_amount
                    utilized_amount += round(float(bet_amount),2)

                    if utilized_amount > bet_limit.amount:
                        return False, self.error_messages.get("limit_exceed")

                    bet_limit.utilized_amount = utilized_amount
                    bet_limit.save()

                
                amt = float(user.balance)
                amt -= float(bet_amount)
                user.balance = amt
                user.save()

            transaction_obj = GSoftTransactions()
            transaction_obj.user = user
            transaction_obj.amount = round(float(bet_amount),2)
            transaction_obj.game_id = game_id
            transaction_obj.device = device
            transaction_obj.round_id = round_id
            transaction_obj.transaction_id = transaction_id
            transaction_obj.request_type = GSoftTransactions.RequestType.wager
            transaction_obj.action_type = GSoftTransactions.ActionType.bet
            transaction_obj.frbid = frbid
            transaction_obj.time = timezone.now()
            transaction_obj.save()

            if round(float(result_amount),2) > 0:
                user.balance += round(float(result_amount),2)
                user.save()
            
            transaction_obj = GSoftTransactions()
            transaction_obj.user = user
            transaction_obj.amount = round(float(result_amount),2)
            transaction_obj.game_id = game_id
            transaction_obj.device = device
            transaction_obj.round_id = round_id
            transaction_obj.transaction_id = transaction_id
            transaction_obj.request_type = GSoftTransactions.RequestType.result
            transaction_obj.action_type = GSoftTransactions.ActionType.win if round(float(result_amount),2)>0 else GSoftTransactions.ActionType.lose
            transaction_obj.game_status = GSoftTransactions.GameStatus.completed if game_status == "completed" else GSoftTransactions.GameStatus.pending
            transaction_obj.frbid = frbid
            transaction_obj.time = timezone.now()
            transaction_obj.save()

            response = {
                "code": 200,
                "status": "Success",
                "walletTx": transaction_id,
                "balance": round(Decimal(user.balance),2),
                "bonusWin": 0.00,
                "realmoneywin": round(Decimal(result_amount),2),
                "bonusmoneybet": 0.00,
                "realmoneybet": round(Decimal(bet_amount),2),
                "bonus_balance": 0.00,
                "real_balance": round(Decimal(user.balance),2),
                "game_mode": 0,
                "order": "cash_money, bonus_money",
                "apiversion": "1.2"
            }
            return True,response
        else:
            return False, self.error_messages.get("operation_not_allowed")


    @transaction.atomic
    def wager_rollback(self, request_param):
        game_session_id = request_param.get("gamesessionid")
        account_id = request_param.get("accountid")
        api_version = request_param.get("apiversion")
        game_id = request_param.get("gameid")
        device = request_param.get("device")
        transaction_id = request_param.get("transactionid")
        rollback_amount = request_param.get("rollbackamount")
        round_id = request_param.get("roundid")
        request_type = request_param.get("request")
        rollback_transaction = GSoftTransactions.objects.filter(
            transaction_id = transaction_id,
            action_type = GSoftTransactions.ActionType.rollback
        ).last()
        if rollback_transaction:
            if rollback_transaction.user.casino_account_id != account_id:
                return False, self.error_messages.get("transaction_parameter_mismatch")

            response = {
                "code": 200,
                "status": "Success - duplicate request",
                "accounttransactionid": transaction_id,
                "balance": rollback_transaction.user.balance,
                "bonus_balance": 0.00,
                "real_balance": rollback_transaction.user.balance,
                "game_mode": 1,
                "order": "cash_money, bonus_money",
                "apiversion": api_version
            }
            return True, response
        elif GSoftTransactions.objects.filter(round_id=round_id, game_status=GSoftTransactions.GameStatus.completed).exists():
            return False, self.error_messages.get("round_already_closed")
        
        bet_transaction = GSoftTransactions.objects.filter(transaction_id = transaction_id, action_type = GSoftTransactions.ActionType.bet).last()
        if bet_transaction:
            if  rollback_amount == None or rollback_amount == "" or round(float(rollback_amount),2) == 0:
                rollback_amount = float(bet_transaction.amount)
            user = Users.objects.filter(casino_account_id=account_id).first()
            if not bet_transaction.frbid:
                user.balance += round(Decimal(rollback_amount),2)
                user.save()
            transaction_obj = GSoftTransactions()
            transaction_obj.user = user
            transaction_obj.amount = round(float(rollback_amount),2)
            transaction_obj.game_id = game_id
            transaction_obj.device = device
            transaction_obj.round_id = bet_transaction.round_id
            transaction_obj.transaction_id = transaction_id
            transaction_obj.request_type = GSoftTransactions.RequestType.rollback
            transaction_obj.action_type = GSoftTransactions.ActionType.rollback
            transaction_obj.time = timezone.now()
            transaction_obj.save()

            response = {
                "code": 200,
                "status": "Success",
                "accounttransactionid": transaction_id,
                "balance": float(user.balance),
                "bonus_balance": 0.00,
                "real_balance": float(user.balance),
                "game_mode": 1,
                "order": "cash_money, bonus_money",
                "apiversion": api_version
            }
            return True,response
        else:
            return False, self.error_messages.get("wager_not_found")

    @transaction.atomic
    def jackpot(self, request_param):
        account_id = request_param.get("accountid")
        game_session_id = request_param.get("gamesessionid")
        game_status = request_param.get("gamestatus")
        result_amount = request_param.get("amount")
        game_id = request_param.get("gameid")
        round_id = request_param.get("roundid")
        transaction_id = request_param.get("transactionid")
        api_version = request_param.get("apiversion")
        request = request_param.get("request")
        user = Users.objects.select_for_update().filter(casino_account_id=account_id).first()
        if user and user.callback_key == game_session_id and round(float(result_amount),2) >= 0 and game_status in ["completed", "pending"]:
            transaction = GSoftTransactions.objects.filter(
                transaction_id=transaction_id,
                round_id=round_id,
                request_type="jackpot"
            ).last()
            if transaction:
                if transaction.user.casino_account_id != account_id or transaction.amount != result_amount:
                    return False, self.error_messages.get("transaction_parameter_mismatch")
                response = {
                    "code": 200,
                    "status": "Success - duplicate request",
                    "walletTx": transaction_id,
                    "balance": float(user.balance),
                    "bonusWin": 0.00,
                    "realMoneyWin": result_amount,
                    "bonus_balance": 0.00,
                    "real_balance": float(user.balance),
                    "game_mode": 0,
                    "order": "cash_money, bonus_money",
                    "apiversion": api_version
                }
                return True, response
            elif GSoftTransactions.objects.filter(round_id=round_id, game_status="completed").exists():
                return False, self.error_messages.get("round_already_closed")
            
            bet_transaction = GSoftTransactions.objects.filter(
                user__casino_account_id = account_id, 
                action_type = "BET",
                round_id = round_id
            ).last()
            if bet_transaction == None:
                return False, self.error_messages.get("wager_not_found")
            
            transaction = GSoftTransactions.objects.filter(
                transaction_id = transaction_id,
                round_id = round_id,
                action_type = GSoftTransactions.ActionType.bet
            ).last()

            if GSoftTransactions.objects.filter(user=user,round_id=round_id,transaction_id = transaction_id,request_type=GSoftTransactions.RequestType.result).exists():
                transaction_obj =  GSoftTransactions.objects.filter(user=user,round_id=round_id,transaction_id = transaction_id,request_type=GSoftTransactions.RequestType.result).last()
                response = {
                "code": 200,
                "status": "Success - duplicate request",
                "walletTx": transaction_id,
                "balance": float(user.balance),
                "bonusWin": 0.00,
                "realMoneyWin": result_amount,
                "bonus_balance": 0.00,
                "real_balance": float(user.balance),
                "game_mode": 0,
                "order": "cash_money, bonus_money",
                "apiversion": api_version
            }
                
                return True, response

            if float(result_amount) > 0:
                user.balance += Decimal(result_amount)/100
                user.save()
            
            transaction_obj = GSoftTransactions()
            transaction_obj.user = user
            transaction_obj.amount = result_amount
            transaction_obj.game_id = game_id
            transaction_obj.round_id = round_id
            transaction_obj.transaction_id = transaction_id
            transaction_obj.request_type = GSoftTransactions.RequestType.result
            transaction_obj.action_type = GSoftTransactions.ActionType.win if float(result_amount)>0 else GSoftTransactions.ActionType.lose
            transaction_obj.game_status = GSoftTransactions.GameStatus.completed if game_status == "completed" else GSoftTransactions.GameStatus.pending
            transaction_obj.time = timezone.now()
            transaction_obj.save()
            
            response = {
                "code": 200,
                "status": "Success",
                "walletTx": transaction_id,
                "balance": float(user.balance),
                "bonusWin": 0.00,
                "realMoneyWin": result_amount,
                "bonus_balance": 0.00,
                "real_balance": float(user.balance),
                "game_mode": 0,
                "order": "cash_money, bonus_money",
                "apiversion": api_version
            }
            return True, response
        else:
            return False, self.error_messages.get("operation_not_allowed")

