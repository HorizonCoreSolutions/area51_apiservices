import json
import time
import requests
from typing import Optional
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


    def __init__(self, config: Optional[dict|None]=None):
        if config is None:
            config = {}

        self.config = config
        self.config['api_domain'] = config.get('api_domain', settings.CP_GAMES_URL)
        self.config['appid'] = config.get('appid', settings.CP_GAMES_APP_ID)
        self.config['secret'] = config.get('appid', settings.CP_GAMES_SECRET)


        self.session = requests.Session()
        self.availables_languages: dict = ["en", "th", "vi", "pt", "es", "bn", "ko", "id", "fr", "tr"]


    def __execute_api(self, data: Optional[dict | None]=None, url=None):
        if params is None:
            params = {}
        try:
            self.session.headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
            })

            response = self.session.post(url, data=data)
            return response.json()
        except Exception as e:
            print(e)
            print(response.text)
            if "503 service temporarily unavailable" in response.text.lower():
                return {"code": 503,"msg": "Sorry, the service you're trying to access is currently unavailable. Please try again later."}
            return


    def __generate_hash(self, params: Optional[dict | None]) -> str:
        if params is None:
            params = {}

        # Sort the params
        param_keys: list[str] = params.values()
        param_keys = param_keys.sort()
        
        # Only hash the values where are different than None or 0 (sorted by name)
        data = "&".join([f"{p}={params.get(p)}" for p in param_keys if params.get(p, 0) != 0])
        # (except secret, always at the end)
        data += f"&secret={self.config.get("secret")}"

        # Following the docs: strtoupper(sha1(md5(string)))
        return sha1(md5(data.encode()).hexdigest().encode()).hexdigest().upper()


    @staticmethod
    def get_base_params():
        return {
            "appid" : settings.CP_GAMES_APP_ID,
        }
    

    def login_user(self, user: Users, game_key: str):
        params = self.get_base_params()
        
        result_params: dict[str] = {
            **params,
            "game_key" : game_key,
            "sub_uid" : user.id,
            "user_name" : user.username if len(user.username) <= 32 else user.username[:29] + "...",
            "time" : str(int(time.time())),
        }
        params = {
            **params,
            "token" : self.__generate_hash(params=result_params),
        }
        # Request example：
        # https://{api_domain}/api/login
        url = self.config.get("api_domain") + "api/login"
        # Request subject：
        # appid=appidtest001&game_key=hog&sub_uid=1001&user_name=&time=1401248256&token=xxxx

        response = self.__execute_api(data=params, url=url)
        return response.get("code") == 0


    def get_game_url(self, user:Users, game_id: str):
        pass


    def get_games():
        pass


    @classmethod
    def parse_to_message(cls, code: int):
        return {"message" : cls.ERRORS.get(code, 1199), "code": code if code in cls.ERRORS.values() else 1199}