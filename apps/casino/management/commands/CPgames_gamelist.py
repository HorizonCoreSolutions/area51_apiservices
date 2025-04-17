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


    def handle(self, *args, **kwargs):
        if not self.games:
            print("No games where given by the api")
            return
        print(f"TOTAL GAMES: {len(self.games)}")
        for game in self.games:
            if not game:
                continue
            obj, created = CasinoGameList.objects.update_or_create(
                game_id=game.get("game_id"),
                defaults={
                    "game_name" : game.get("name_en"),
                    "section_id" : "CPGames",
                    "vendor_name" : "CPgames"
                }
            )

            if created:
                pass


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


