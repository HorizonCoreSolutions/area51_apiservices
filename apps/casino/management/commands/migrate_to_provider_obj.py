import json
import time
import requests

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.users.models import Users
from apps.casino.models import CasinoGameList, Providers


class Command(BaseCommand):
    help = 'Migrate the current vendor_name to the Provider model, only run once if there are vendor_names'

    def handle(self, *args, **kwargs):
        for game in CasinoGameList.objects.all():
            if game.provider != None:
                print(f"game {game.game_image} has already a provider ({game.provider.name})")
                continue

            # Get provider_obj based on the vendor_name
            vendor_name = game.vendor_name
            provider = self.fetch_provider_obj(vendor_name)
            
            # Store it
            game.provider = provider
            game.save()

            print(f"game {game.game_image} has been update to provider ({game.provider.name})")


    def fetch_provider_obj(self, name: str) -> Providers:
        queryset = Providers.objects.filter(name=name)

        if queryset.exists():
            return queryset.first()

        return Providers.objects.create(name=name)