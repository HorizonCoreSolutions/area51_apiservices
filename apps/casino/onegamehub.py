import hmac
import requests
from decimal import Decimal
from hashlib import sha256
from django.conf import settings
from dataclasses import dataclass
from django.utils import timezone
from rest_framework import status
from apps.users.models import Users
from apps.core.file_logger import SimpleLogger
from apps.casino.models import GSoftTransactions
from django.db import transaction as db_transaction
from typing import Dict, Optional, Any, List, Tuple, Union
from urllib.parse import urlencode, quote, unquote, parse_qs

FAKE_COIN = "EUR"
REAL_COIN = "USD"

logger = SimpleLogger(name="OGH", log_file='logs/OGH.log').get_logger()

@dataclass
class Actions:
    balance: str = "balance"
    real_play: str = "real_play"
    demo_play: str = "demo_play"
    available_games: str = "available_games"
    freerounds_create: str = "freerounds_create"
    freerounds_cancel: str = "freerounds_cancel"
    available_currencies: str = "available_currencies"


class OneGameHub:

    availables_languages = {"es", "en", "fr", "lt"}
    # This follow the format
    # display | message | Action
    ERRORS = {
        "ERR001": (True, "Unknown error occurred.", "restart"),
        "ERR002": (
            True,
            "The session has timed out. "
            "Please login again to continue playing.",
            "restart",
        ),
        "ERR003": (
            True,
            "Insufficient funds to place current wager. "
            "Please reduce stake or add more funds to "
            "your balance.",
            "continue",
        ),
        "ERR004": (
            True,
            "This wagering will exceed your wagering limitation. "
            "Please try a smaller amount or or increase the limit.",
            "continue",
        ),
        "ERR005": (True, "Player authentication failed.", "restart"),
        "ERR006": (False, "Unauthorized request.", "restart"),
        "ERR008": (True, "Unsupported currency.", "restart"),
        "ERR009": (True, "Bonus bet max restriction.", "continue"),
    }

    def __init__(
        self, actions: Optional[Actions] = None,
        config: Optional[Dict[str, str]] = None
    ):
        if not actions:
            actions = Actions()
        if not config:
            config = {}

        self.actions: Actions = actions
        self.url = config.get("url", settings.ONE_GAME_HUB_URL or "")
        self.salt = config.get("salt", settings.ONE_GAME_HUB_SALT or "")
        self.secret = config.get("secret", settings.ONE_GAME_HUB_RPC_SECRET)

        pass

    def __generate_hash(self, params: Optional[Dict[str, str]]) -> str:
        if params is None:
            params = {}

        # Sort the params
        d = urlencode(sorted(params.items()))
        # Following the docs: Calculate HMAC with sha256 of payload with salt
        return hmac.new(self.salt.encode(), d.encode(), sha256).hexdigest()

    @staticmethod
    def parse_request_params(params: Dict) -> Dict:
        return {k: v[0] for k, v in params.items()}

    @staticmethod
    def get_player_uid(user: Users) -> str:
        return str(user.id) + settings.ENV_POSTFIX

    @staticmethod
    def get_user_from_uid(sub_uid: str) -> Optional[Users]:
        if not sub_uid.endswith(settings.ENV_POSTFIX):
            return None

        qs = Users.objects.filter(
            id=sub_uid[:-len(settings.ENV_POSTFIX)]
        ).first()
        return qs

    # @db_transaction.atomic
    def select_user_for_update(self,
                               player_id: str
                               ) -> Tuple[Optional[Users],
                                          Optional[Dict[str, str]]]:
        """
        This returns Tuple[Users,  dict(with error)],
        you can identify its an error if error is not None
        """

        # CHECK: user exist
        if not player_id:
            # ERR005: Player authentication failed
            return None, self.parse_to_message("ERR005")
        if not player_id.endswith(settings.ENV_POSTFIX):
            return None, self.parse_to_message("ERR005")

        user_id = player_id[:-len(settings.ENV_POSTFIX)]

        user = Users.objects.select_for_update().filter(id=user_id).first()
        if not user:
            return None, self.parse_to_message("ERR005")

        return user, None

    def get_formated_balance(self,
                             user: Users,
                             is_real_play: bool,
                             ) -> Dict[str, Union[int, Decimal, str]]:
        balance = user.balance if is_real_play else user.bonus_balance
        cur = REAL_COIN if is_real_play else FAKE_COIN
        return {"status": 200,
                "balance": int(Decimal(balance or 0)*100),
                "currency": cur}

    def parse_to_message(self,
                         error: str,
                         status: Optional[int] = None) -> Dict:
        data = self.ERRORS.get(error, "ERR001")
        return {
            "status": status or 400,
            "error": {
                "code": error,
                "display": data[0],
                "message": data[1],
                "action": data[2],
            },
        }

    def is_valid_request(self, request) -> bool:
        data = request.GET.dict()
        hash = data.pop("hash", "")
        return hash == self.__generate_hash(data)

    def verify_request(self, request) -> bool:
        hash = request.pop("hash", "")
        return hash == self.__generate_hash(request)

    def get_url(self, action: str,
                params: Optional[Dict[str, Any]] = None) -> str:
        extra = ""
        if params:
            extra = f"&{urlencode(params, quote_via=quote)}"
        return f"{self.url}?action={action}&secret={self.secret}{extra}"

    def get_available_games(self):
        response = requests.get(url=self.get_url(self.actions.available_games))
        if response.status_code != 200:
            print(response)

        data = response.json()

    def get_available_currencies(self):
        response = requests.get(url=self.get_url(
            self.actions.available_currencies))
        return response.json()

    @db_transaction.atomic
    def get_balance(self, data) -> Tuple[Dict, int]:
        is_verified = self.verify_request(request=data)
        if not is_verified:
            # Signature error ERR006
            response_data = self.parse_to_message("ERR006", status=401)
            return response_data, status.HTTP_401_UNAUTHORIZED

        try:
            player_id: str = data.get("player_id")
            user, error = self.select_user_for_update(player_id=player_id)
            if error is not None:
                return error, status.HTTP_400_BAD_REQUEST
            if user is None:
                return self.parse_to_message("ERR001"), status.HTTP_400_BAD_REQUEST
            is_real_play = data.get("currency", "") == REAL_COIN
            return self.get_formated_balance(
                    user=user,
                    is_real_play=is_real_play), status.HTTP_200_OK
        except AttributeError as e:
            print("grep here")
            print(e)
            return self.parse_to_message("ERR001"), status.HTTP_200_OK
        except TypeError as e:
            print("grep here")
            print(e)
            return self.parse_to_message("ERR001"), status.HTTP_200_OK

    @db_transaction.atomic
    def place_bet(self, data) -> Tuple[Dict, int]:
        is_verified = self.verify_request(request=data)
        if not is_verified:
            # Signature error ERR006
            response_data = self.parse_to_message("ERR006", status=401)
            return response_data, status.HTTP_401_UNAUTHORIZED

        try:
            player_id: str = data.get("player_id")
            user, error = self.select_user_for_update(player_id=player_id)
            if error is not None:
                return error, status.HTTP_400_BAD_REQUEST
            if user is None:
                logger.warning(f"User {player_id}, does not exist")
                return self.parse_to_message("ERR001"), status.HTTP_400_BAD_REQUEST

            is_real_play = data.get("currency", "") == REAL_COIN
            freerounds_id = data.get("freerounds_id")

            game_id = data.get("game_id")
            ext_round_id = data.get("ext_round_id")
            transaction_id = data.get("transaction_id")

            round_id = data.get("round_id")
            amount = Decimal(0 if freerounds_id else data.get("amount", 0)) / 100

            # CHECK: if the bet already exist
            existing_objs = GSoftTransactions.objects.filter(
                    user=user,
                    callerId=settings.ONE_GAME_HUB_ID,
                    transaction_id=transaction_id)
            rollback_exist = existing_objs.filter(
                request_type=GSoftTransactions.RequestType.rollback
            ).exists()
            # If rollback exist return error
            # Due to unespectec behaiviour
            if rollback_exist:
                logger.debug(f"Rollback already exist")
                return self.parse_to_message("ERR001"), status.HTTP_400_BAD_REQUEST
            if existing_objs.exists():
                # If transaction already exist return OK, cuz this is 
                # Deduplication
                return self.get_formated_balance(
                        user=user,
                        is_real_play=is_real_play), status.HTTP_200_OK

            # CHECK: win_amount is higher or equals to 0
            # 3.2: 7.
            if is_real_play:
                balance = Decimal(user.balance or 0)
            else:
                balance = Decimal(user.bonus_balance or 0)

            # Check if user  has enought money to bet
            if balance < amount:
                response_data = self.parse_to_message("ERR003")
                return response_data, status.HTTP_200_OK

            transfer_balance = - abs(amount)
            withdraw = abs(amount)

            transaction_obj = GSoftTransactions()

            if is_real_play:
                user.balance = transfer_balance + balance
                transaction_obj.amount = abs(transfer_balance)
            else:
                transaction_obj.bonus_bet_amount = abs(transfer_balance)
                user.bonus_balance = transfer_balance + balance
            user.save()

            transaction_obj.callerId = settings.ONE_GAME_HUB_ID
            transaction_obj.user = user
            transaction_obj.withdraw = withdraw if withdraw != 0 else None
            transaction_obj.game_id = game_id
            transaction_obj.round_id = round_id
            transaction_obj.bonusid = freerounds_id
            transaction_obj.transaction_id = transaction_id
            transaction_obj.sessionalternativeid = ext_round_id
            transaction_obj.action_type = GSoftTransactions.ActionType.bet
            transaction_obj.game_status = GSoftTransactions.GameStatus.pending
            transaction_obj.request_type = GSoftTransactions.RequestType.wager
            transaction_obj.time = timezone.now()
            transaction_obj.save()

            return self.get_formated_balance(
                    user=user,
                    is_real_play=is_real_play), status.HTTP_200_OK
        except AttributeError as e:
            logger.debug(f"This is {e}")
            return self.parse_to_message("ERR001"), status.HTTP_200_OK
        except TypeError as e:
            logger.debug(f"This is {e}")
            return self.parse_to_message("ERR001"), status.HTTP_200_OK

    @db_transaction.atomic
    def win(self, data) -> Tuple[Dict, int]:
        is_verified = self.verify_request(request=data)
        if not is_verified:
            # Signature error ERR006
            response_data = self.parse_to_message("ERR006", status=401)
            return response_data, status.HTTP_401_UNAUTHORIZED

        try:
            player_id: str = data.get("player_id")
            user, error = self.select_user_for_update(player_id=player_id)
            if error is not None:
                logger.debug("Some error has ocurre during user selection for update.")
                return error, status.HTTP_400_BAD_REQUEST
            if user is None:
                logger.warning(f"User {player_id}, does not exist")
                return self.parse_to_message("ERR001"), status.HTTP_400_BAD_REQUEST

            is_real_play = data.get("currency", "") == REAL_COIN
            freerounds_id = data.get("freerounds_id")

            game_id = data.get("game_id")
            ext_round_id = data.get("ext_round_id")
            transaction_id = data.get("transaction_id")

            round_id = data.get("round_id")
            payout = Decimal(data.get("amount", 0))

            # Idempotency by transaction_id (single credit per provider order)
            last_game = GSoftTransactions.objects.filter(
                user=user,
                transaction_id=transaction_id,
                callerId=settings.ONE_GAME_HUB_ID,
            ).order_by("-created").first()

            if not last_game:
                logger.debug("not last game found.")
                return self.parse_to_message("ERR001"), status.HTTP_400_BAD_REQUEST

            if transaction_id and last_game.game_status == GSoftTransactions.GameStatus.completed:
                # Already processed this provider order:
                # return success with current balance
                return self.get_formated_balance(
                        user=user,
                        is_real_play=is_real_play), status.HTTP_200_OK

            # CHECK: win_amount is higher or equals to 0
            # 3.2: 7.
            if payout < 0:
                logger.debug(f"Payout {payout} does not make sence.")
                return self.parse_to_message("ERR001"), status.HTTP_400_BAD_REQUEST

            last_game.game_status = GSoftTransactions.GameStatus.completed
            last_game.save()

            transfer_bonus = Decimal(0) if is_real_play else payout
            transfer_balance = payout if is_real_play else Decimal(0)

            user.bonus_balance = transfer_bonus + Decimal(user.bonus_balance or 0)
            user.balance = transfer_balance + Decimal(user.balance or 0)
            user.save()

            transaction_obj = GSoftTransactions()
            transaction_obj.callerId = settings.ONE_GAME_HUB_ID
            transaction_obj.user = user
            transaction_obj.amount = abs(transfer_balance)
            transaction_obj.bonus_bet_amount = abs(transfer_bonus)
            transaction_obj.deposit = payout if payout != 0 else None
            transaction_obj.game_id = game_id
            transaction_obj.round_id = round_id
            transaction_obj.bonusid = freerounds_id
            transaction_obj.transaction_id = transaction_id
            transaction_obj.sessionalternativeid = ext_round_id
            transaction_obj.action_type = GSoftTransactions.ActionType.win
            transaction_obj.request_type = GSoftTransactions.RequestType.result
            transaction_obj.game_status = GSoftTransactions.GameStatus.completed
            transaction_obj.time = timezone.now()
            transaction_obj.save()

            return self.get_formated_balance(
                    user=user,
                    is_real_play=is_real_play), status.HTTP_200_OK
        except AttributeError as e:
            logger.debug(f"This is {e}")
            return self.parse_to_message("ERR001"), status.HTTP_200_OK
        except TypeError as e:
            logger.debug(f"This is {e}")
            return self.parse_to_message("ERR001"), status.HTTP_200_OK

    @db_transaction.atomic
    def cancel_bet(self, data) -> Tuple[Dict, int]:
        is_verified = self.verify_request(request=data)
        if not is_verified:
            # Signature error ERR006
            response_data = self.parse_to_message("ERR006", status=401)
            return response_data, status.HTTP_401_UNAUTHORIZED

        try:
            player_id: str = data.get("player_id")
            user, error = self.select_user_for_update(player_id=player_id)
            if error is not None:
                return error, status.HTTP_400_BAD_REQUEST
            if user is None:
                return self.parse_to_message("ERR001"), status.HTTP_400_BAD_REQUEST

            extra = data.get("extra")
            parsed = parse_qs(unquote(extra).strip('"')).items()
            coin = {k: v[0] for k, v in parsed}
            coin = coin.get("coin")

            game_id = data.get("game_id")
            round_id = data.get("round_id")
            ext_round_id = data.get("ext_round_id")
            transaction_id = data.get("transaction_id")

            qs = GSoftTransactions.objects.filter(
                callerId=settings.ONE_GAME_HUB_ID,
                user=user,
                transaction_id=transaction_id,
            ).order_by("-created")

            to_rollback = qs.first()
            transfer_bonus = Decimal(0)
            transfer_balance = Decimal(0)
            deposit = Decimal(0)
            withdraw = Decimal(0)

            is_real_play = coin == REAL_COIN
            if to_rollback:
                if to_rollback.request_type == GSoftTransactions.RequestType.rollback:
                    return self.get_formated_balance(
                            user=user,
                            is_real_play=is_real_play), status.HTTP_200_OK

                deposit = Decimal(to_rollback.deposit or 0)
                withdraw = Decimal(to_rollback.withdraw or 0)
                multipliyer = 1 if withdraw > 0 else -1
                multipliyer = 0 if deposit == 0 and withdraw == 0 else multipliyer

                transfer_balance = Decimal(to_rollback.amount or 0) * multipliyer
                transfer_bonus = Decimal(to_rollback.bonus_bet_amount or 0) * multipliyer

                user.bonus_balance = transfer_bonus + Decimal(user.bonus_balance)
                user.balance = transfer_balance + Decimal(user.balance)
                user.save()
                to_rollback.game_status = GSoftTransactions.GameStatus.completed

            transaction_obj = GSoftTransactions()
            transaction_obj.callerId = settings.ONE_GAME_HUB_ID
            transaction_obj.user = user
            transaction_obj.deposit = deposit if deposit != 0 else None
            transaction_obj.withdraw = withdraw if withdraw != 0 else None
            transaction_obj.game_id = game_id
            transaction_obj.round_id = round_id
            transaction_obj.transaction_id = transaction_id
            transaction_obj.sessionalternativeid = ext_round_id
            transaction_obj.amount = abs(transfer_balance)
            transaction_obj.bonus_bet_amount = abs(transfer_bonus)
            transaction_obj.action_type = GSoftTransactions.ActionType.rollback
            transaction_obj.game_status = GSoftTransactions.GameStatus.completed
            transaction_obj.request_type = GSoftTransactions.RequestType.rollback
            transaction_obj.time = timezone.now()
            transaction_obj.save()

            return self.get_formated_balance(
                    user=user,
                    is_real_play=is_real_play), status.HTTP_200_OK
        except AttributeError as e:
            print("grep here")
            print(e)
            return self.parse_to_message("ERR001"), status.HTTP_200_OK
        except TypeError as e:
            print("grep here")
            print(e)
            return self.parse_to_message("ERR001"), status.HTTP_200_OK

    def get_game_url(
        self, user: Users, game_id: str, lang: str,
        currency: str, ip: str, device: str
    ) -> Tuple[Tuple[str, str], bool]:
        """
        Returns:
            Tuple[ session: Tuple, error: bool ]
            -> session: Tuple[ sessionId: str, SessionUrl: str ]
        """
        params = {
            "game_id": game_id,
            "player_id": self.get_player_uid(user),
            "currency": currency,
            "ip_address": ip,
            "mobile": device,
            "language": lang,
            "extra": f"%22coin%3D{currency}%22"
        }
        print(params)
        url = self.get_url(self.actions.real_play, params=params)

        try:
            print(url)
            res = requests.get(url=url, timeout=20)
            res.raise_for_status()
        except requests.exceptions.RequestException:
            return ("", ""), True

        try:
            data = res.json()
            print(data)
            if data.get("status") != 200:
                raise ValueError()
            data = data.get("response")
            token = data.get("token")
            return (token, data.get('game_url')), False

        except ValueError:
            return ("", ""), True

    def start_game(self,
                   request_param,
                   ip) -> Tuple[bool, Dict[str, Union[bool, str, Dict]]]:
        game_id = request_param.get("game_id")
        lang = request_param.get("lang", "en")
        account_id = request_param.get("account_id")
        device = 1 if request_param.get("device", "mobile") == "mobile" else 0
        currency = FAKE_COIN if bool(request_param.get(
            "mode", "gold") == "gold") else REAL_COIN

        user = Users.objects.filter(casino_account_id=account_id).first()
        if not user:
            return False, {
                "success": False,
                "message": "User with given account_id not found",
            }

        lang = lang if lang in self.availables_languages else "en"
        session, err = self.get_game_url(
            user=user,
            game_id=game_id,
            lang=lang,
            currency=currency,
            ip=ip,
            device=str(device),
        )
        if err:
            return False, {
                "success": False,
                "message": (
                    "Game is unavailable, plese try again in a few minutes."
                ),
            }

        response = {
            "success": True,
            "url": {
                "jsonrpc": "2.0",
                "id": 1008,
                "result": {"SessionId": session[0], "SessionUrl": session[1]},
            },
        }

        return True, response


if __name__ == "__main__":
    pass
