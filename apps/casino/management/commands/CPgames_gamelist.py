import json
import time
import requests

from django.conf import settings
from django.db.models import Q
from django.core.management.base import BaseCommand

from apps.casino.cpgames import CPgames
from apps.users.models import Users
from apps.casino.models import CasinoGameList, CasinoHeaderCategory, CasinoManagement, Providers


class Command(BaseCommand):
    help = 'Get Casino25 game list'

    cp = CPgames()
    games = cp.get_games()
    # name_en
    # game_id
    # type
    change_to_stable = {
        "SLOTS" : "Slots",
        "Mini Games" : "Mini Games",
    }
    DEMO_GAMES = [
        "1_16",
        "1_32",
        "1_41",
        "1_53",
        "1_55",
        "1_60",
        "2_1700026",
        "2_1700029",
        "2_1700031",
        "2_1700047",
        "2_1700049",
        "2_1700051",
        "2_1700053",
        "2_1700054",
        "2_1700058",
        "2_1700067",
        "2_1700071"
    ]


    def handle(self, *args, **kwargs):
        if not self.games:
            print("No games where given by the api")
            return
        print(f"TOTAL GAMES: {len(self.games)}")
        for game in self.games:
            if not game:
                continue
            obj, _ = CasinoGameList.objects.update_or_create(
                game_id=game.get("game_id"),
                defaults={
                    "game_name" : game.get("name_en"),
                    "section_id" : "CPgames",
                    "vendor_name" : "CPgames",
                    "game_category" : self.change_to_stable.get(game.get("type", "SLOTS"), "Slots"),
                    "is_mobile_supported" : True,
                    "is_desktop_supported" : True,
                    "is_free_round_supported" : game.get("game_id") in self.DEMO_GAMES
                }
            )
            self.update_or_create_casino_management(obj)
            obj.save()
            self.update_or_create_casino_categories()

    def update_or_create_casino_management(self, game):
        users = Users.objects.filter(role="admin")
        for user in users:
            obj, _ = CasinoManagement.objects.get_or_create(
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


