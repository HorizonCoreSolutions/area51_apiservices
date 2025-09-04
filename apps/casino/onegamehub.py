import json
import hmac
import requests
from hashlib import sha256
from django.conf import settings
from dataclasses import dataclass
from apps.users.models import Users
from urllib.parse import urlencode, quote
from typing import Dict, Optional, Any, List, Tuple, Union


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
        param_keys: List[str] = list(params.keys())
        param_keys = sorted(param_keys)

        # (sorted by name)
        d = "&".join(
            [f"{p}={params.get(p)}" for p in param_keys if (p != "hash")])
        # Following the docs: Calculate HMAC with sha256 of payload with salt
        return hmac.new(self.salt.encode(), d.encode(), sha256).hexdigest()

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
                               sub_uid: str
                               ) -> Tuple[Optional[Users],
                                          Optional[Dict[str, str]]]:
        """
        This returns Tuple[Users,  dict(with error)],
        you can identify its an error if error is not None
        """

        # CHECK: user exist
        if not sub_uid:
            # ERR005: Player authentication failed
            return None, self.parse_to_message("ERR005")
        if not sub_uid.endswith(settings.ENV_POSTFIX):
            return None, self.parse_to_message("ERR005")

        user_id = sub_uid[:-len(settings.ENV_POSTFIX)]

        user = Users.objects.select_for_update().filter(id=user_id).first()
        if not user:
            return None, self.parse_to_message("ERR005")

        return user, None

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
        currency = "USD" if bool(request_param.get(
            "mode", "gold") == "gold") else "SC"

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
