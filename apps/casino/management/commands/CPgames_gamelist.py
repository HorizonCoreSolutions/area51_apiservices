import sys
from django.db.models import Q
from datetime import timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand, CommandError

from apps.casino.cpgames import CPgames
from apps.users.models import Users
from apps.casino.models import (
        CasinoGameList,
        CasinoHeaderCategory,
        CasinoManagement
        )


class Command(BaseCommand):
    help = 'Get CPgames game list'

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-ask",
            action="store_true",
            dest="no_ask",
            help="Bypass interactive restriction",
        )

    cp = CPgames()
    games = None
    # name_en
    # game_id
    # type
    change_to_stable = {
        "SLOTS": "Slots",
        "Mini Games": "Mini Games",
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

    def handle(self, *args, **options):
        
        ask = not options.get("no_ask", False)

        # Check interactive requirement
        if not sys.stdin.isatty() and ask:
            raise CommandError("Interactive terminal required (use --no-ask to override).")
        
        print("Fetching games")
        self.games = self.cp.get_games()

        if not self.games:
            print("No games where given by the api")
            return
        print(f"TOTAL GAMES: {len(self.games)}")
        casino_game_ids = []
        for game in self.games:
            if not game:
                continue
            game_id = game.get("game_id", "lobby")
            if game_id.lower() == "lobby":
                continue

            previews_ids = list(
                CasinoGameList.objects
                .filter(section_id="CPgames", vendor_name="CPgames")
                .values_list("game_id", flat=True)
            )
            
            game_cat = self.change_to_stable.get(game.get("type", "SLOTS"), "Slots")
            answer = None
            if ask and not game_id in previews_ids:
                print(f"New Game Detected:\n{game.get('name_en')}\nType: {game_cat}\nID: {game_id}")
                while True:
                    answer = str(input("Want to add this game? (yes or no)")).lower()
                    if answer in {"yes", "no"}:
                        break
                
                    
            answer = (answer == "yes") or not ask or game_id in previews_ids
            
            if not answer:
                print("Game has not been added.")
                continue
            if not game_id in previews_ids:
                print("Game has been added.")
            else:
                print(f"Game {game.get('name_en')} is updating")

            casino_game_ids.append(game_id)
            obj, created = CasinoGameList.objects.update_or_create(
                game_id=game_id,
                defaults={
                    "game_name": game.get("name_en"),
                    "section_id": "CPgames",
                    "vendor_name": "CPgames",
                    "game_category": game_cat,
                    "is_mobile_supported": True,
                    "is_desktop_supported": True,
                    "is_free_round_supported": game_id in self.DEMO_GAMES
                }
            )
            if created:
                obj.created = timezone.now() - timedelta(days=7)
            self.update_or_create_casino_management(obj)
            obj.save()
            self.update_or_create_casino_categories()

        CasinoGameList.objects.filter(
                Q(vendor_name="CPgames") & ~Q(game_id__in=casino_game_ids)
                ).delete()

    def update_or_create_casino_management(self, game):
        users = Users.objects.filter(role="admin")
        for user in users:
            obj, _ = CasinoManagement.objects.get_or_create(
                admin=user,
                game=game
            )
            obj.save()

    def update_or_create_casino_categories(self):
        categories = CasinoGameList.objects.distinct(
                "game_category").values_list("game_category", flat=True)
        for category in categories:
            obj, created = CasinoHeaderCategory.objects.get_or_create(
                name=category
            )
            if created:
                cateogry = CasinoHeaderCategory.objects.filter(~Q(position=None)).order_by("position").last()
                obj.position = (cateogry.position or 0) + 1 if cateogry else 1
                obj.save()
