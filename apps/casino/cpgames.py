import json
import time
import requests
from typing import Optional, Dict, List, Union
from hashlib import md5, sha1
from django.conf import settings

from apps.users.models import Users

class CPgames():

    ERRORS = {
        # 0 : "success",
        -1 : "fail",
        1001 : "In maintenance",
        1002 : "The system is busy and the operation is in progress",
        1003 : "game_key game parameter error",
        1004 : "User sub_uid is empty",
        1006 : "Login failed",
        1110 : "Parameter error",
        1111 : "Signature error",
        1112 : "Request timed out",
        1113 : "appid error",
        1115 : "Wrong game id",
        1116 : "Player does not exist",
        1117 : "Player balance is insufficient",
        1118 : "Order does not exist",
        1119 : "Order error",
        1199 : "Unknown error generic error return"
    }

    BASE_SUCCESS: Dict[str, str] = {
        "code" : 0,
        "msg" : "success",
    }

    def __init__(self, config: Optional[dict]=None):
        if config is None:
            config = {}

        self.config = config
        self.config['api_domain'] = config.get('api_domain', settings.CP_GAMES_URL)
        self.config['appid'] = config.get('appid', settings.CP_GAMES_APP_ID)
        self.config['secret'] = config.get('secret', settings.CP_GAMES_SECRET)


        self.session = requests.Session()
        self.availables_languages: list[str] = ["en", "th", "vi", "pt", "es", "bn", "ko", "id", "fr", "tr"]


    def __execute_api(self, params: Optional[dict]=None, url: str="") -> dict:
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
                "token" : self.__generate_hash(params=params),
            }

            response = self.session.post(url=url, data=data)
            return response.json()
        except Exception as e:
            print(e)
            if response:
                print(response.text)
                if "503 service temporarily unavailable" in response.text.lower():
                    return {"code": 503,"msg": "Sorry, the service you're trying to access is currently unavailable. Please try again later."}
            return {"code" : 500, "msg" : "Sorry, there was a problem with the server response."}


    def __generate_hash(self, params: Optional[Dict[str, str]]) -> str:
        if params is None:
            params = {}

        # Sort the params
        param_keys: List[str] = list(params.keys())
        param_keys = sorted(param_keys)

        # Only hash the values where are different than None or 0 (sorted by name)
        data = "&".join([f"{p}={params.get(p)}" for p in param_keys if params.get(p) not in [None, "0", 0] and (p != "token")])
        # (except secret, always at the end)
        s_key = self.config.get("secret")
        data += f"&secret={s_key}"

        # Following the docs: strtoupper(sha1(md5(string)))
        return sha1(md5(data.encode()).hexdigest().encode()).hexdigest().upper()


    @staticmethod
    def get_username(user: Users) -> str:
        u_name = str(user.username)
        return u_name if len(u_name) <= 32 else u_name[:29] + "..."


    @staticmethod
    def get_sub_uid(user: Users) -> str:
        return str(user.id) + settings.ENV_POSTFIX


    @staticmethod
    def get_user_from_uid(sub_uid: str) -> Optional[Users]:
        qs = Users.objects.filter(id=sub_uid[:-len(settings.ENV_POSTFIX)])
        return qs.first() if qs else None


    @staticmethod
    def get_base_params() -> Dict[str, Union[str, int]]:
        return {
            "appid" : settings.CP_GAMES_APP_ID,
            "game_key" : "hog"
        }


    def login_user(self, user: Users) -> bool:
        params: dict[str, Union[str, int]] = self.get_base_params()

        params = {
            **params,
            "sub_uid" : self.get_sub_uid(user=user),
            "user_name" : self.get_username(user=user),
            "time" : int(time.time()),
        }
                # Request example：
        # https://{api_domain}/api/login
        url = self.config.get("api_domain", "") + "api/login"
        # Request subject:
        # appid=appidtest001&game_key=hog&sub_uid=1001&user_name=&time=1401248256&token=xxxx

        response = self.__execute_api(params=params, url=url)

        if response.get("code") != 0:
            print(response.get("code"))

        return response.get("code") == 0


    def get_game_url(self, user:Users, game_id: str, lang: str="en") -> str:
        params = self.get_base_params()

        # The currency is set in the CP appid
        # there are a few apps you can chose from
        # to date 15/04/2025 is set to USD appid and secret
        params = {
            **params,
            "sub_uid" : self.get_sub_uid(user=user),
            "game_id" : game_id,
            "lang" : lang if lang in self.availables_languages else "en",
            "time" : int(time.time())
        }

        url = self.config.get("api_domain", "") + "api/get_game_url"
        result = self.__execute_api(params=params, url=url)

        if result.get("code") != 0:
            raise RuntimeError(f"API error: { result.get('code') } {result.get('msg')}")

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
        params = self.get_base_params()
        params = {
            **params,
            "game_key" : "hog",
            "time" : int(time.time()),
        }

        url = self.config.get("api_domain", "") + "api/game_list"
        result = self.__execute_api(params=params, url=url)

        if result.get("code") != 0:
            return []

        return result.get("data")


    def get_games_on_db(self):
        return


    def verify_request(self, request:dict) -> bool:
        token = request.get("token")
        if not token:
            return False

        result_token = self.__generate_hash(params=request)
        return result_token == token


    def get_user_balance(self, user_sub: Optional[str]) -> Dict[str, Union[str, Dict[str, str]]]:
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

        return {
            **self.BASE_SUCCESS,
            "data" : {
                "balance" : user.balance + user.bonus_balance,
                "currency": "USD",
            }
        }

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


    @classmethod
    def parse_to_message(cls, code: int):
        return {"msg" : cls.ERRORS.get(code, 1199), "code": code if code in cls.ERRORS.keys() else 1199}

