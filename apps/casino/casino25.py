import json
import requests
import traceback

from django.conf import settings
from django.db.models import Q

from apps.users.models import Users
from apps.casino.models import (CasinoGameList, GSoftTransactions, TournamentTransaction,
    UserTournament)
from django.db import transaction as db_transaction
from decimal import Decimal
from django.utils import timezone
from apps.users.utils import send_player_balance_update_notification, update_tournament_scorboard
from apps.casino.utils import bet_bonus




class Casino25Client:
    def __init__(self, config: dict):
        if 'url' not in config:
            raise Exception("You must specify url for API")
        elif 'id' not in config:
            raise Exception("You must specify id for API")

        self.id = int(config.get("id"))
        self.url = config.get("url")
        self.session = requests.Session()
        if config.get('debug'):
            self.session.headers['DEBUG'] = '1'

        if not config.get('ssl_verification'):
            self.session.verify = False

        if 'sslKeyPath' in config:
            self.session.cert = config['sslKeyPath']

    
    def execute(self, method, params=None):
        if params is None:
            params = {}
        try:
            data = {
                "jsonrpc": "2.0",
                "method": method,
                "id": self.id,
                "params": params,
            }
            content_length = str(len(json.dumps(data)))
            self.session.headers.update({
                'Content-Type': 'application/json',
                'Content-Length': content_length,
                'Accept': 'application/json'
            })

            response = self.session.post(self.url, json=data)
            return response.json()
        except Exception as e:
            print(e)
            print(response.text)
            if "503 service temporarily unavailable" in response.text.lower():
                return {"message": "Sorry, the service you're trying to access is currently unavailable. Please try again later."}
            return

    
    def list_games(self, params):
        required_params = ['Id',]
        for param in required_params:
            if param not in params:
                raise Exception(f"{param} is required for game list")
        return self.execute('Game.List')


    def create_bank_group(self, bank_group):
        required_params = ['Id', 'Currency']
        for param in required_params:
            if param not in bank_group:
                raise Exception(f"{param} is required for bank group creation")
        return self.execute('BankGroup.Create', bank_group)


    def set_bank_group(self, bank_group):
        required_params = ['Id', 'Currency']
        for param in required_params:
            if param not in bank_group:
                raise Exception(f"{param} is required for setting bank group")
        return self.execute('BankGroup.Set', bank_group)


    def apply_settings_template(self, bank_group):
        required_params = ['BankGroupId', 'SettingsTemplateId']
        for param in required_params:
            if param not in bank_group:
                raise Exception(f"{param} is required for applying settings template to bank group")
        return self.execute('BankGroup.ApplySettingsTemplate', bank_group)


    def create_player(self, player):
        required_params = ['Id', 'BankGroupId']
        for param in required_params:
            if param not in player:
                raise Exception(f"{param} is required for player creation")
        return self.execute('Player.Create', player)


    def set_player(self, player):
        required_params = ['Id', 'BankGroupId']
        for param in required_params:
            if param not in player:
                raise Exception(f"{param} is required for setting player")
        return self.execute('Player.Set', player)


    def get_balance(self, player):
        if 'PlayerId' not in player:
            raise Exception("PlayerId is required for getting balance")
        return self.execute('Balance.Get', player)


    def change_balance(self, player):
        required_params = ['PlayerId', 'Amount']
        for param in required_params:
            if param not in player:
                raise Exception(f"{param} is required for changing balance")
        return self.execute('Balance.Change', player)


    def create_session(self, session):
        #required_params = ['PlayerId', 'GameId']
        #for param in required_params:
        #    if param not in session:
        #        raise Exception(f"{param} is required for session creation")
        #return self.execute('Session.Create', session)
        required_params = ['PlayerId', 'GameId']
        for param in required_params:
            if param not in session:
                raise Exception(f"{param} is required for session creation")

        if 'RestorePolicy' in session:
            restore_policy_values = ['Restore', 'Create', 'Last']
            if session['RestorePolicy'] not in restore_policy_values:
                raise Exception("Invalid value for RestorePolicy")

        # Optional: Check StaticHost parameter if needed

        return self.execute('Session.Create', session)


    def create_demo_session(self, demo_session):
        required_params = ['GameId', 'BankGroupId']
        for param in required_params:
            if param not in demo_session:
                raise Exception(f"{param} is required for demo session creation")
        return self.execute('Session.CreateDemo', demo_session)


    def close_session(self, session):
        if 'SessionId' not in session:
            raise Exception("SessionId is required for closing session")
        return self.execute('Session.Close', session)


    def get_session(self, session):
        if 'SessionId' not in session:
            raise Exception("SessionId is required for getting session details")
        return self.execute('Session.Get', session)


    def list_sessions(self, filters=None):
        if filters is None:
            filters = {}
        return self.execute('Session.List', filters)


    def set_bonus(self, bonus):
        if 'Id' not in bonus:
            raise Exception("Id is required for setting bonus")
        return self.execute('Bonus.Set', bonus)


    def list_bonuses(self):
        return self.execute('Bonus.List')


    def list_player_bonuses(self, params):
        if 'PlayerId' not in params:
            raise Exception("PlayerId is required for listing player bonuses")
        return self.execute('PlayerBonus.List', params)


    def get_player_bonus(self, params):
        required_params = ['BonusId', 'PlayerId']
        for param in required_params:
            if param not in params:
                raise Exception(f"{param} is required for getting player bonus")
        return self.execute('PlayerBonus.Get', params)


    def activate_player_bonus(self, params):
        required_params = ['BonusId', 'PlayerId']
        for param in required_params:
            if param not in params:
                raise Exception(f"{param} is required for activating player bonus")
        return self.execute('PlayerBonus.Activate', params)


    def execute_operations_on_player_bonus(self, params):
        required_params = ['BonusId', 'PlayerId', 'Operations']
        for param in required_params:
            if param not in params:
                raise Exception(f"{param} is required for executing operations on player bonus")
        return self.execute('PlayerBonus.Execute', params)
    

class Casino25:
    def __init__(self, user: Users, tournament_id=None, user_tournament: UserTournament = None, debug=False, request_data=None):
        self.user = user
        self.tournament_id = tournament_id
        self.user_tournament = user_tournament
        self.request_data = request_data
        self.config = {
            "debug": debug,
            "id": int(settings.CASINO_25_ID),
            "url": settings.CASINO_25_URL,
            "sslKeyPath": settings.CASINO_25_SSLKEY_PATH,
            "ssl_verification": True,
        }
        self.casino_client = Casino25Client(config=self.config)
        self.default_language = "en"
        self.available_language = ["en", "fr", "de", "ru", "cn", "es", "pl", "it"]
        self.available_errors = ["ErrNotEnoughMoneyCode","ErrIllegalCurrencyCode", "ErrNegativeDepositCode", "ErrNegativeWithdrawalCode", "ErrSpendingBudgetExceeded", "ErrMaxBetLimitExceededCode", "ErrInternalErrorCode"]


    def return_server_error(self, error_message):
        if error_message not in self.available_errors:
            error_message = "ErrInternalErrorCode"
        
        return {
            "jsonrpc": 2.0,
            "id": self.config.get("id"),
            "error": {
                "code": 1,
                "message": error_message
            }
        }


    def list_games(self):
        params = {
            "Id": self.config.get("Id"),
        }

        games = self.casino_client.list_games(params=params)
        return games
    

    def set_player(self, bank_group_id="usd_bank_group"):
        if self.user_tournament:
            user_id = f"{self.user.id}-{self.tournament_id}-tournament"
            username = f"{self.user.username}-{self.tournament_id}-tournament"
        else:
            user_id = str(self.user.id)
            username = self.user.username
        
        player_params = {
            "Id": user_id,
            "Nick": username,
            "BankGroupId": bank_group_id,
        }
        self.casino_client.set_player(player=player_params)


    def start_demo_game(self, game_id, language, bank_group_id = "usd_bank_group"):
        params = {
            "BankGroupId": bank_group_id,
            "GameId": game_id,
            "StartBalance": 10000,
            "Params": {
                "language":language
            }
        }

        response = self.casino_client.create_demo_session(demo_session=params)
        return response
    
    
    def start_real_game(self, game_id, language):
        user_id = f"{self.user.id}-{self.tournament_id}-tournament" if self.user_tournament else str(self.user.id)
        
        params = {
            "PlayerId": user_id,
            "GameId": game_id,
            "RestorePolicy":"Create",
            "Params": {
                "language":language
            }
        }

        response = self.casino_client.create_session(session=params)
        print(response,"response")
        return response
    

    def start_game(self):
        request_param = self.request_data
        game_id = request_param.get("game_id")
        lang = request_param.get("lang", self.default_language)
        mode = request_param.get("mode", "demo")
        device_type = request_param.get("device_type", "pc")
        account_id = request_param.get("account_id")

        if game_id and lang and mode and device_type:
            user = Users.objects.filter(casino_account_id=account_id).first()
            casino_game = CasinoGameList.objects.filter(game_id=game_id).first()
            if not user:
                return False, {"success": False, "message": "User with given account_id not found"}
            elif not casino_game:
                return False, {"success": False, "message": "Invalid game ID"}
            elif device_type.lower() == "mobile" and not casino_game.is_mobile_supported:
                return False, {"success": False, "message": "Game not supported in mobile"}
            elif device_type.lower() in ["pc", "desktop"] and not casino_game.is_desktop_supported:
                return False, {"success": False, "message": "Game not supported in desktop"}


            lang = self.default_language if lang not in self.available_language else lang                
            if mode.lower() == "demo":
                response = self.start_demo_game(game_id=game_id, language=lang)
            else:
                self.set_player()
                response = self.start_real_game(game_id=game_id, language=lang)

            if response and response.get("result", {}).get("SessionUrl"):
                game_url = response.get("SessionUrl")
                session_id = response.get("SessionId")
                user.callback_key = session_id
                user.save()
                return True, {"success": True,"url": response}
            elif response and response.get("message", None):
                return False, response
            else:
                return False, {"success": False, "message": "Game is unavailable, plese try again in a few minutes."}        
        else:
            return False, {"success": False, "message": "Please provide all required params - game_id, lang, mode, device_type"}


    def get_balance(self):        
        if self.user_tournament:
            self.user_tournament.refresh_from_db()
            balance = int(self.user_tournament.points*100) if self.user_tournament else 0
        else:
            self.user.refresh_from_db()
            balance = int(self.user.balance*100) + int(self.user.bonus_balance*100)
        
        return True, {
            "jsonrpc": "2.0",
            "id": self.request_data.get("id"),
            "result": {
                "balance": balance,
            }
        }
    
    @db_transaction.atomic
    def withdraw_and_deposit(self):
        try:
            request = self.request_data
            request_param = request.get('params')
            callerId = request_param.get("callerId")
            player_name = request_param.get("playerName")
            withdraw = request_param.get("withdraw")
            deposit = request_param.get("deposit")
            currency = request_param.get("currency")
            transactionref = request_param.get("transactionRef")
            gameroundref = request_param.get("gameRoundRef")
            game_id = request_param.get("gameId")
            source =  request_param.get("source")
            reason = request_param.get("reason")
            game_session_id = request_param.get("sessionId")
            sessionalternativeid = request_param.get("sessionAlternativeId")
            spinDetails = request_param.get("spinDetails")
            bonusid = request_param.get("bonusId")
            chargefreerounds = request_param.get("chargeFreerounds")
            operatorid = True if settings.CASINO_25_ID == str(callerId) else False
            
            if round(float(deposit),2) <0:
                return True, self.return_server_error("ErrNegativeDepositCode")
            if round(float(withdraw),2) <0:
                return True, self.return_server_error("ErrNegativeWithdrawalCode")
            
            if self.user and operatorid and round(float(withdraw),2) >= 0 and round(float(deposit),2) >= 0:
                transaction = GSoftTransactions.objects.filter(
                    transaction_id=transactionref,
                    round_id=gameroundref,
                    request_type=GSoftTransactions.RequestType.result
                ).last()
                
                self.user.refresh_from_db()
                if transaction:
                    response = {
                        "jsonrpc": request.get('jsonrpc'),
                        "id": self.request_data.get("id"),
                        "result": {
                            "newBalance": int(self.user.balance*100)+int(self.user.bonus_balance*100) if not self.user_tournament else int(self.user_tournament.points*100),
                            "transactionId": transactionref
                        }
                    }
                    return True, response
                
                self.user.refresh_from_db()
                if not self.user_tournament and float(self.user.balance + self.user.bonus_balance) < float(withdraw/100):
                    return True, self.return_server_error("ErrNotEnoughMoneyCode")
                elif self.user_tournament:
                    self.user_tournament.refresh_from_db()
                    if float(self.user_tournament.points) < float(withdraw/100):
                        return True, self.return_server_error("ErrNotEnoughMoneyCode")
                if currency != 'USD':
                    return True, self.return_server_error("ErrIllegalCurrencyCode")
                
                with db_transaction.atomic():
                    """
                    # Balance Deduction Rule: Always deduct from bonus balance first, 
                    # and if the bonus balance is insufficient, deduct from the main balance to cover the bet.
                    """
                    if int(withdraw) != 0: 
                        transaction_obj = GSoftTransactions()
                        tournament_transaction = TournamentTransaction()
                        self.user.refresh_from_db()
                        if round(float(withdraw),2) >= 0:
                            bet_amount = round(Decimal(withdraw/100),2)
                            if self.user_tournament:
                                transaction_obj.is_tournament_transaction = True
                                self.user_tournament.refresh_from_db()
                                self.user_tournament.points -= bet_amount
                                self.user_tournament.spent_points += bet_amount
                                self.user_tournament.save()
                            else:
                                amount_to_deduct = min(self.user.bonus_balance, bet_amount)
                                transaction_obj.bonus_bet_amount = amount_to_deduct
                                self.user.bonus_balance -= amount_to_deduct
                                bet_amount = bet_amount-amount_to_deduct
                                self.user.balance -= bet_amount
                                self.user.save()
                            transaction_obj.amount = bet_amount
                            tournament_transaction.points = bet_amount
                        transaction_obj.user = self.user
                        transaction_obj.game_id = game_id
                        transaction_obj.callerId = callerId
                        transaction_obj.withdraw = withdraw
                        transaction_obj.deposit = deposit
                        transaction_obj.currency = currency
                        transaction_obj.transaction_id = transactionref
                        transaction_obj.gameroundref  = gameroundref
                        transaction_obj.game_id = game_id
                        transaction_obj.source = source
                        transaction_obj.reason = reason
                        transaction_obj.gamesession_id = game_session_id
                        transaction_obj.sessionalternativeid = sessionalternativeid
                        transaction_obj.spinDetails = spinDetails
                        transaction_obj.bonusid = bonusid
                        transaction_obj.chargefreerounds = chargefreerounds
                        transaction_obj.request_type = GSoftTransactions.RequestType.wager
                        transaction_obj.action_type = GSoftTransactions.ActionType.bet
                        transaction_obj.transaction_type = GSoftTransactions.TransactionType.debit
                        transaction_obj.time = timezone.now()
                        transaction_obj.save()

                        if self.user_tournament:
                            tournament_transaction.user = self.user
                            tournament_transaction.tournament = self.user_tournament.tournament
                            tournament_transaction.casino_transaction = transaction_obj
                            tournament_transaction.type = TournamentTransaction.TransactionType.bet
                            tournament_transaction.save()
                            
                        try:
                            # As entire amount is deducted in fishing games and bet bonus is percentage of bet amount, 
                            # this will give players high bonus amount which is not indented, so excluding this games
                            if CasinoGameList.objects.filter(~Q(game_category__iexact="Fishing"), game_id=game_id).exists():
                                bet_bonus(self.user.id, transaction_obj.amount)
                        except Exception as e:
                            pass

                    if reason in ['GAME_PLAY_FINAL', 'GAME_PLAY'] and GSoftTransactions.objects.filter(action_type = GSoftTransactions.ActionType.bet, gameroundref=gameroundref).exists():
                        transaction_obj = GSoftTransactions()
                        tournament_transaction = TournamentTransaction()
                        self.user.refresh_from_db()
                        if round(float(deposit),2) >= 0:
                            if self.user_tournament:
                                transaction_obj.is_tournament_transaction = True
                                transaction_obj.amount = round(float(deposit/100),2)
                                self.user_tournament.refresh_from_db()
                                self.user_tournament.win_points += round(Decimal(deposit/100),2)
                                self.user_tournament.last_win_at = timezone.now()
                                self.user_tournament.save()
                                tournament_transaction.points = round(float(deposit/100),2)
                            else:
                                win_amount = round(Decimal(deposit/100),2)
                                bet_transaction = GSoftTransactions.objects.filter(action_type = GSoftTransactions.ActionType.bet, gameroundref=gameroundref).first()
                                bonus_bet_amount = round(Decimal(bet_transaction.bonus_bet_amount), 2)
                                if bonus_bet_amount > 0:
                                    if win_amount > bonus_bet_amount:
                                        """
                                        # Case 1: Betting from Bonus Balance and Winning More Than Bet
                                        # Case 3: Betting from Both Main and Bonus Balances and win more than bonus balance bet
                                        """
                                        main_balance_to_add = win_amount - bonus_bet_amount
                                        self.user.bonus_balance += bonus_bet_amount
                                        self.user.balance += main_balance_to_add
                                        transaction_obj.bonus_bet_amount = bet_transaction.bonus_bet_amount
                                        transaction_obj.amount = main_balance_to_add
                                    else:
                                        """
                                        # Case 2: Betting from Bonus Balance and Winning Less Than Bet
                                        # Case 4: Betting from Both Main and Bonus Balances and win less than bonus balance bet
                                        """
                                        self.user.bonus_balance += win_amount
                                        transaction_obj.bonus_bet_amount = win_amount
                                        transaction_obj.amount = 0
                                else:
                                    # Case 5: Betting from Main Balance and Winning
                                    self.user.balance += round(Decimal(deposit/100),2)
                                    transaction_obj.amount = round(float(deposit/100),2)
                                    transaction_obj.bonus_bet_amount = 0
                            
                        self.user.save()
                        transaction_obj.request_type = GSoftTransactions.RequestType.result
                        transaction_obj.transaction_type = GSoftTransactions.TransactionType.credit
                        transaction_obj.action_type = GSoftTransactions.ActionType.win if int(deposit)>0 else GSoftTransactions.ActionType.lose
                        transaction_obj.user = self.user
                        transaction_obj.game_id = game_id
                        transaction_obj.callerId = callerId
                        transaction_obj.withdraw = withdraw
                        transaction_obj.deposit = deposit
                        transaction_obj.currency = currency
                        transaction_obj.transaction_id = transactionref
                        transaction_obj.gameroundref  = gameroundref
                        transaction_obj.game_id = game_id
                        transaction_obj.source = source
                        transaction_obj.reason = reason
                        transaction_obj.gamesession_id = game_session_id
                        transaction_obj.sessionalternativeid = sessionalternativeid
                        transaction_obj.spinDetails = spinDetails
                        transaction_obj.bonusid = bonusid
                        transaction_obj.chargefreerounds = chargefreerounds
                        transaction_obj.time = timezone.now()
                        transaction_obj.save()

                        if self.user_tournament:
                            tournament_transaction.user = self.user
                            tournament_transaction.tournament = self.user_tournament.tournament
                            tournament_transaction.casino_transaction = transaction_obj
                            tournament_transaction.type = TournamentTransaction.TransactionType.win if int(deposit)>0 else TournamentTransaction.TransactionType.lose
                            tournament_transaction.save()
                            update_tournament_scorboard(self.user_tournament.tournament, self.user_tournament)
                response = {
                    "jsonrpc": request.get('jsonrpc'),
                    "id": self.request_data.get("id"),
                    "result": {
                        "newBalance": int(self.user.balance*100)+int(self.user.bonus_balance*100) if not self.user_tournament else int(self.user_tournament.points*100),
                        "transactionId": transactionref
                    }
                }
                
                send_player_balance_update_notification(self.user, self.user_tournament)
                return True, response
        except Exception as e:
            print(traceback.format_exc())
            print(e)
            return True, self.return_server_error("ErrInternalErrorCode")
    
    
    @db_transaction.atomic
    def rollback_transaction(self):
        try:
            request = self.request_data
            request_param = request.get('params')
            callerid = request_param.get("callerId")
            playername = request_param.get("playerName")
            transactionref = request_param.get("transactionRef")
            game_id = request_param.get("gameId")
            sessionid = request_param.get("sessionId")
            sessionalternativeid = request_param.get("sessionAlternativeId")
            roundid = request_param.get("roundId")
            gameroundref = request_param.get("gameRoundRef")


            rollback_transaction = GSoftTransactions.objects.filter(
                transaction_id = transactionref,
                action_type = GSoftTransactions.ActionType.rollback
            ).last()
            if rollback_transaction:
                if settings.CASINO_25_ID == callerid:
                    return False, self.return_server_error("CallerIdDoesNotMatch")
                
                response = {
                            "jsonrpc": self.request_data.get('jsonrpc'),
                            "id": self.request_data.get("id"),
                            "result": {
                            }
                        }
                return True, response
            bet_transactions = GSoftTransactions.objects.filter(transaction_id = transactionref)
            for bet_transaction in bet_transactions:
                tournament__bet_transaction = TournamentTransaction.objects.filter(casino_transaction=bet_transaction).first()
                with db_transaction.atomic():
                    
                    transaction_obj = GSoftTransactions()
                    tournament_transaction = TournamentTransaction()
                    # user = Users.objects.filter(id=int(playername)).first()
                    self.user.refresh_from_db()
                    if bet_transaction.action_type==GSoftTransactions.ActionType.bet:
                        bet_amount = round(float(bet_transaction.withdraw/100),2)
                        if self.user_tournament:
                            transaction_obj.is_tournament_transaction = True
                            self.user_tournament.refresh_from_db()
                            self.user_tournament.points += round(Decimal(tournament__bet_transaction.points),2)
                            self.user_tournament.spent_points -= round(Decimal(tournament__bet_transaction.points),2)
                            self.user_tournament.save()
                            tournament_transaction.points = round(float(tournament__bet_transaction.points),2)
                        else:
                            bet_amount = bet_transaction.amount or 0
                            self.user.balance += round(Decimal(bet_amount),2)
                            self.user.bonus_balance += round(Decimal(bet_transaction.bonus_bet_amount or 0),2)
                            transaction_obj.bonus_bet_amount = bet_transaction.bonus_bet_amount
                        transaction_obj.amount = bet_amount
                        transaction_obj.transaction_type = GSoftTransactions.TransactionType.credit
                    elif bet_transaction.action_type==GSoftTransactions.ActionType.win:
                        win_amount = round(float(bet_transaction.deposit/100),2)
                        if self.user_tournament:
                            transaction_obj.is_tournament_transaction = True
                            self.user_tournament.refresh_from_db()
                            self.user_tournament.win_points -= round(Decimal(tournament__bet_transaction.points),2)
                            last_win_transaction = TournamentTransaction.objects.filter(
                                ~Q(id=tournament__bet_transaction.id),
                                user=self.user,
                                tournament=tournament__bet_transaction.tournament,
                                type = TournamentTransaction.TransactionType.win,
                            ).last()
                            if last_win_transaction and last_win_transaction.created < self.user_tournament.last_win_at:
                                self.user_tournament.last_win_at = last_win_transaction.created
                            elif not last_win_transaction:
                                self.user_tournament.last_win_at = None
                            self.user_tournament.save()
                            tournament_transaction.points = round(float(tournament__bet_transaction.points),2)
                        else:
                            win_amount = bet_transaction.amount or 0
                            self.user.balance -= round(Decimal(win_amount),2)
                            self.user.bonus_balance -= round(Decimal(bet_transaction.bonus_bet_amount or 0),2)
                            transaction_obj.bonus_bet_amount = bet_transaction.bonus_bet_amount
                        transaction_obj.amount = win_amount
                        transaction_obj.transaction_type = GSoftTransactions.TransactionType.debit
                    else:
                        continue
                    self.user.save()
                    transaction_obj.user = self.user
                    transaction_obj.callerId = callerid
                    transaction_obj.game_id = game_id
                    transaction_obj.gamesession_id = sessionid
                    transaction_obj.transaction_id = transactionref
                    transaction_obj.sessionalternativeid = sessionalternativeid
                    transaction_obj.round_id =  roundid
                    transaction_obj.gameroundref = gameroundref
                    transaction_obj.reason = "GAME_ROLLBACK"
                    transaction_obj.request_type = GSoftTransactions.RequestType.rollback
                    transaction_obj.action_type = GSoftTransactions.ActionType.rollback
                    transaction_obj.time = timezone.now()
                    transaction_obj.save()

                    if self.user_tournament:
                        tournament_transaction.user = self.user
                        tournament_transaction.tournament = self.user_tournament.tournament
                        tournament_transaction.casino_transaction = transaction_obj
                        tournament_transaction.type = TournamentTransaction.TransactionType.rollback
                        tournament_transaction.save()
                        if round(float(bet_transaction.deposit),2) > 0:
                            update_tournament_scorboard(self.user_tournament.tournament, self.user_tournament)

                send_player_balance_update_notification(self.user, self.user_tournament)

            if bet_transactions.count()>0:
                response = {
                            "jsonrpc": request.get('jsonrpc'),
                            "id": self.request_data.get("id"),
                            "result": {
                            }
                        }
                return True,response
            
            response = {
                            "jsonrpc": request.get('jsonrpc'),
                            "id": self.request_data.get("id"),
                            "result": {
                            }
                        }
            return True,response
            
            
        except Exception as e:
            print(traceback.format_exc())
            print(e)
            return True, self.return_server_error("ErrInternalErrorCode")
    

