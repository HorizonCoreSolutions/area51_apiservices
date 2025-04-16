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


    def handle(self, *args, **kwargs):
        pass
