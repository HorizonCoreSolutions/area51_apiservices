import traceback
import requests
import time
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.casino.models import GameImages, CasinoGameList
from apps.users.models import Users


class Command(BaseCommand):
    help = 'Update game images in game list'

    def handle(self, *args, **kwargs):
        try:
            while True:
                print('update_game_images_cron called for images update ')
                url = f"{settings.CASINO_BASE_URL}v1/games"
                slot = []
                virtual = []
                live_casino = []
                live_casino_games = {}
                superuser = Users.objects.filter(is_superuser=True).first()
                resp = requests.get(url, headers={"Authorization": f"Bearer {superuser.casino_token}"})
                if resp.status_code == 200:
                    game_list = resp.json()
                    if game_list.get("items"):
                        print("Game List Items From API", game_list.get("items"))
                        for game in game_list.get("items"):
                            gi = GameImages.objects.filter(name__iexact=game["id"]).first()
                            if gi is None:
                                game["imgURL"] = ''
                            else:
                                game["imgURL"] = gi.url
                            if "LIVECASINO" in game["category"]:
                                live_casino.append(game)
                            elif ('VIRTUAL_SPORTS' in game["category"]) or ('VIRTUALGAME' in game["category"]):
                                virtual.append(game)
                            else:
                                slot.append(game)
                    live_casino_games["slot"] = slot
                    live_casino_games["virtual"] = virtual
                    live_casino_games["live_casino"] = live_casino
                    print("Updated Game List", live_casino_games)
                    CasinoGameList.objects.all().delete()
                    CasinoGameList.objects.create(game_list=live_casino_games)
                print('Waiting for 12 hours')
                time.sleep(43200)
        except Exception as e:
            tb = traceback.format_exc()
            print(tb)
            raise e
