from django.db.models import Q
from datetime import timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand

from apps.casino.onegamehub import OneGameHub
from apps.users.models import Users
from apps.casino.models import (
    CasinoGameList,
    CasinoHeaderCategory,
    CasinoManagement
)


class Command(BaseCommand):
    help = 'Get Casino25 game list'

    ogh = OneGameHub()
    # name_en
    # game_id
    # type
    change_to_stable = {
        "bingo": "Bingo",
        "crash-game": "Crash Games",
        "instant-win": "Slots",
        "dice": "Table",
        "fishing": "Fishing",
        "keno": "Keno",
        "lottery": "Keno",
        "others": "Slots",
        "scratch-cards": "Scratch Cards",
        "shooting": "Fishing",
        "slots": "Slots",
        "sports": "Table",
        "table-games": "Table",
        "video-poker": "Video Poker",
        "virtual-game": "Slots",
    }

    ALLOWED_PROVIDERS = {
        '18Peaches (Sweepstakes)',
        '1Spin4Win',
        '7777 Gaming',
        'BGaming',
        'BoldPlay',
        'Chilli Games Sweepstakes',
        'CT Interactive',
        'Grazgame',
        'Espresso',
        'EURASIAN Gaming',
        'Fa Chai Gaming',
        'Felix Gaming',
        'Funky Games',
        'GameArt', # This is not necesary
        'Inbet',
        'Jili Games (Sweepstakes)',
        'Kagaming2',
        'King Show Games',
        'Mancala',
        'MrSlotty',
        'Netgame',
        'Rogue Games',
        'Spadegaming',
        'Spinoro',
        'TaDa Gaming (Social Casinos)',
        'Zeus Play',
    }

    def handle(self, *args, **kwargs):
        print("Getting Games")
        self.games = self.ogh.get_games()
        if not self.games:
            print("No games where given by the api")
            return
        print("Process started")
        resumen = {}

        existing_categories = CasinoGameList.objects.distinct(
            "game_category"
        ).values_list(
            "game_category",
            flat=True
        )

        # Track providers we've already asked about and session-allowed providers
        asked_providers = set()
        session_allowed = set(self.ALLOWED_PROVIDERS)

        print(f"TOTAL GAMES: {len(self.games)}")
        casino_game_ids = []
        for game in self.games:
            if not game:
                continue
            game_id = game.get("id")
            provider = game.get("provider")
            
            # Check if provider is allowed
            if provider not in session_allowed:
                # Only ask once per provider
                if provider not in asked_providers:
                    asked_providers.add(provider)
                    answer = input(f"\nNew provider found: '{provider}'\nAdd to allowed providers? (y/n): ").strip().lower()
                    if answer == 'y':
                        session_allowed.add(provider)
                        print(f"Provider '{provider}' added for this session.")
                        print(f"NOTE: Add '{provider}' to ALLOWED_PROVIDERS in the code to make it permanent.")
                    else:
                        print(f"Provider '{provider}' skipped.")
                        continue
                else:
                    # Already asked and user said no
                    continue

            resumen[provider] = resumen.get(provider, 0) + 1

            casino_game_ids.append(game_id)
            cat_key = game.get('categories')[0] if game.get('categories') else 'slots'
            game_cat = self.change_to_stable.get(cat_key, "Slots")
            print(f"Game saved: {game.get('name')}\nType: {game_cat}\nID: {game_id}")

            obj, created = CasinoGameList.objects.update_or_create(
                game_id=game_id,
                defaults={
                    "game_name": game.get("name"),
                    "section_id": "OneGameHub",
                    "game_image": game.get('media', {}).get('thumbnails', {}).get('500x500'),
                    "vendor_name": provider.replace(' ', '-'),
                    "game_category": game_cat,
                    "is_mobile_supported": True,
                    "is_desktop_supported": True,
                    "is_demo_supported": game.get("is_demo_supported"),
                    "is_free_round_supported": game.get("is_free_rounds_supported")
                }
            )
            if created:
                obj.created = timezone.now() - timedelta(days=4)
            self.update_or_create_casino_management(obj)
            obj.save()
            if game_cat not in existing_categories:
                print(f"Category {game_cat} added")
                self.update_or_create_casino_categories()

        CasinoGameList.objects.filter(
                Q(section_id="OneGameHub") & ~Q(game_id__in=casino_game_ids)
                ).delete()

        print(resumen)

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
