import json
import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from apps.casino.models import CasinoGameList, CasinoManagement, Providers
from apps.users.models import Users
from requests.auth import HTTPBasicAuth
from django.http.response import HttpResponse
import time
from api_services.settings.base import (
    GSOFT_USER,
    GSOFT_PASSWORD,
    GSOFT_LOGIN_URL,
    GSOFT_GAME_URL,
)

# local imports
def get_login_token(username, password):
    data={
        "email":username,
        "password":password
    }
    url=GSOFT_LOGIN_URL
    response = requests.post(url=url, json=data)
    if response.status_code == 200:
        return response.headers["jwt-auth"]
    else:
        return None


class Command(BaseCommand):
    help = 'Get G-soft game list'

    def handle(self, *args, **kwargs):
        try:
            while True:
                auth_token = get_login_token(GSOFT_USER, GSOFT_PASSWORD)
                url=GSOFT_GAME_URL
                resp = requests.get(url=url, headers={"version":"1.0","jwt-auth":auth_token})
                if resp:
                    if resp.status_code == 200:
                        casino_games = json.loads(resp.text)
                        print(F"TOTAL GAMES = {len(casino_games)}")
                        CasinoGameList.objects.all().delete()
                        for game in casino_games:
                            is_support_jackpot = game.get('supportJackpot', "No")
                            gsoft_casino_games={
                                
                            }

                            provider = self.fetch_provider_obj(game.get('subVendorName'))
                            obj, created = CasinoGameList.objects.update_or_create(
                                game_name = game.get('gameName'),
                                game_id = game.get('gameId'),
                                game_type = game.get('gameType'),
                                game_category = game.get('gameCategory'),
                                game_image = game.get('defaultImg', ''),
                                vendor_name = game.get('subVendorName'),
                                provider=provider,
                                is_support_jackpot = True if is_support_jackpot == "Yes" else False,
                                jackpot_type = game.get('jackpotType'),
                                release_date = game.get('releaseDate'),
                                currencies_list = game.get('currencies',[]),
                                platform = game.get('platforms', []),
                                languages_list = game.get('languages',[]),
                                )
                            self.update_or_create_casino_management(obj)
                            
                            print(f"GAME {game.get('gameName')} saved!!!")
                    else:
                        return HttpResponse(json.dumps(resp.json()), status=resp.status_code)
                    
                else:
                    print("No response from gsoft gamelist")
                time.sleep(43200)
                print('Sleep for 12 hours')
        except Exception as e:
            print(e)
            raise e


    def fetch_provider_obj(self, name: str) -> Providers:
        queryset = Providers.objects.filter(name=name)

        if queryset.exists():
            return queryset.first()

        return Providers.objects.create(name=name)
    
    
    def update_or_create_casino_management(self, game):

                        users = Users.objects.filter(role="admin")
                        for user in users:
                            obj, created = CasinoManagement.objects.get_or_create(
                                admin = user,
                                game = game
                            )
                            if created:
                                games = CasinoManagement.objects.filter(admin = user).exclude(
                                    game = game
                                )
                            obj.save()