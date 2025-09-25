import json
import time
import requests

from django.conf import settings
from django.db.models import Q
from django.core.management.base import BaseCommand

from apps.users.models import Users
from apps.casino.models import CasinoGameList, CasinoHeaderCategory, CasinoManagement, Providers


class Command(BaseCommand):
    help = 'Get Casino25 game list'
    # Available categories for the game, if game_id is not present in one of this then category is "Slot". As there are 1000 plus slots game, we have not included those here
    available_categories = {
        "Bingo": ["bingo_disco_nights", "bingo_gold_of_poseidon", "bingo_mega_money", "bingo_muertitos", "bingo_planet_67", "bingo_football",],
        "Crash Games": ["aviatrix_ax", "rocketman_elbet", "aviator_spribe"],
        "Fishing": ["paradise_cq", "fishing2", "alienhunter", "fishinggod", "fishingwar", "zombieparty"],
        "Keno": ["keno_austria", "keno_universe_html", "kenoplustwoball_gt_html"],
        "Roulette": ["rouletteroyal_original", "american_roulette_html", "french_roulette_html", "roulette_touch"],
        "Table": ["baccarat", "blackjack_html", "blackjack_touch", "blackjack_classic_touch", "blackjack_single_deck_touch", "emoji_planet"],
        "Video Poker": ["oasis_poker_classic", "jacks_or_better_multiple_hands", "bonus_poker"],
    }


    available_providers = {
        'netent': 'NetEnt', 'greentube': 'Greentube', 'amatic': 'Amatic', 'microgaming': 'Microgaming', 'egt': 'EGT',
        'pragmatic': 'Pragmatic', 'wazdan': 'Wazdan', 'playson': 'Playson', 'aviatrix': 'Aviatrix', 'quickspin': 'Quickspin',
        'booongo': 'Booongo', 'aristocrat': 'Aristocrat', 'merkur': 'Merkur', 'gaminator': 'Gaminator', 'kajot': 'Kajot',
        'igrosoft': 'Igrosoft', 'apollo': 'Apollo Games', 'redrake': 'RedRake', 'konami': 'Konami', 'relaxgaming': 'Relaxgaming',
        'playngo': 'Playngo', 'playtech': 'Playtech', 'betsoft': 'BetSoft', 'igt': 'IGT', 'pushgaming': 'Pushgaming',
        'nolimit': 'NoLimit', 'wmg': 'WMG', 'hacksaw': 'Hacksaw', 'spadegaming': 'Spadegaming', 'austria': 'Austria',
        'cqgaming': 'cqgaming', 'elbet': 'Elbet', 'evoplay': 'EvoPlay', 'fishing': 'fishing', 'smartsoft': 'Smartsoft Gaming',
        'spribe': 'Spribe', 'stake': 'Stake'
    }


    def handle(self, *args, **kwargs):
        try:
            games_category = {}
            for category, games in self.available_categories.items():
                for game in games:
                    games_category[game] = category
            
            while True:
                casino_game_ids = []
                casino_game_list = self.get_game_list()
                if casino_game_list:
                    casino_game_list = casino_game_list.get("result", {}).get("Games", [])
                    print(F"TOTAL GAMES = {len(casino_game_list)}")
                    # CasinoGameList.objects.all().delete()
                    for game in casino_game_list:
                        tags = game.get("Tags", [])
                        obj, created = CasinoGameList.objects.update_or_create(
                            game_id = game.get("Id"),
                            defaults={
                                "game_name": game.get("Name"),
                                "description": game.get("Description"),
                                "section_id": game.get("SectionId"),
                                "tags": game.get("Tags"),
                                "format": game.get("Format"),
                                "is_demo_supported": False if "NoD" in tags else True,
                                "is_mobile_supported": False if "PC" in tags else True,
                                "is_desktop_supported": False if "mobile" in tags else True,
                                "is_free_round_supported": True if "FR" in tags else False,
                            }
                        )
                        if created:
                            obj.game_category = games_category.get(game.get("Id"), "Slots")
                            vendor_name = self.available_providers.get(game.get("SectionId"), game.get("SectionId"))
                            obj.vendor_name = vendor_name
                            obj.save()
                        self.update_or_create_casino_management(obj)
                        casino_game_ids.append(game.get("Id"))
                        
                        print(f"GAME {game.get('Name')} saved!!!")
                    CasinoGameList.objects.filter(~Q(section_id__in=["CPgames", "OneGameHub"]) & ~Q(game_id__in=casino_game_ids)).delete()
                    self.update_or_create_casino_categories()
                else:
                    print("No response from casino25 gamelist")

                print('Sleep for 12 hours')
                time.sleep(43200)
        except Exception as e:
            print(e)
            raise e

    
    def get_game_list(self):
        try:
            data = {
                "jsonrpc": "2.0",
                "method": "Game.List",
                "id": settings.CASINO_25_ID,
            }
            content_length = str(len(json.dumps(data)))

            session = requests.Session()
            session.headers['DEBUG'] = '1'
            session.cert = settings.CASINO_25_SSLKEY_PATH
            session.headers.update({
                'Content-Type': 'application/json',
                'Content-Length': content_length,
                'Accept': 'application/json'
            })

            response = session.post(settings.CASINO_25_URL, json=data)
            return response.json()
        except Exception as e:
            print(response.text)
            print(f"Error fetching game list: {e}")

    
    def update_or_create_casino_management(self, game):
        users = Users.objects.filter(role="admin")
        for user in users:
            obj, created = CasinoManagement.objects.get_or_create(
                admin = user,
                game = game
            )
            obj.save()

    def update_or_create_casino_categories(self):
        categories = CasinoGameList.objects.distinct("game_category").values_list("game_category", flat=True)
        for category in categories:
            obj, created = CasinoHeaderCategory.objects.get_or_create(
                name= category
            )
            if created:
                cateogry = CasinoHeaderCategory.objects.filter(~Q(position=None)).order_by("position").last()
                obj.position = cateogry.position + 1 if cateogry else 1
                obj.save()

            
