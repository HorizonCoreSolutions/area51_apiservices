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

    games = [
        {"code": "1_1", "name": "Lucky Cat", "type": "SLOTS"},
        {"code": "1_2", "name": "Jungle King", "type": "SLOTS"},
        {"code": "1_4", "name": "Jungle Gems", "type": "SLOTS"},
        {"code": "1_8", "name": "Jurassic Jungle", "type": "SLOTS"},
        {"code": "1_16", "name": "Jungle Fruit", "type": "SLOTS"},
        {"code": "1_32", "name": "Jungle Treasure", "type": "SLOTS"},
        {"code": "1_33", "name": "Jungle Party", "type": "SLOTS"},
        {"code": "1_40", "name": "Lucky Santa", "type": "SLOTS"},
        {"code": "1_41", "name": "Lucky Panda", "type": "SLOTS"},
        {"code": "1_42", "name": "Lucky Dragon", "type": "SLOTS"},
        {"code": "1_43", "name": "Lucky Wheel", "type": "SLOTS"},
        {"code": "1_44", "name": "Lucky777", "type": "SLOTS"},
        {"code": "1_45", "name": "RioCarnival", "type": "SLOTS"},
        {"code": "1_50", "name": "LuckyCat II", "type": "SLOTS"},
        {"code": "1_51", "name": "Galactic GO", "type": "SLOTS"},
        {"code": "1_52", "name": "Cyber GO", "type": "SLOTS"},
        {"code": "1_53", "name": "Ocean Go", "type": "SLOTS"},
        {"code": "1_54", "name": "Fishing Go", "type": "SLOTS"},
        {"code": "1_55", "name": "Coin Master Go", "type": "SLOTS"},
        {"code": "1_56", "name": "Crazy Piggy", "type": "SLOTS"},
        {"code": "1_57", "name": "Crazy 777", "type": "SLOTS"},
        {"code": "1_58", "name": "Crazy Gems", "type": "SLOTS"},
        {"code": "1_60", "name": "Crazy Birds", "type": "SLOTS"},
        {"code": "2_1700002", "name": "Lucky Roller2", "type": "Mini Game"},
        {"code": "2_1700004", "name": "Mine", "type": "Mini Game"},
        {"code": "2_1700006", "name": "Mine", "type": "Mini Game"},
        {"code": "2_1700008", "name": "Crypto", "type": "Mini Game"},
        {"code": "2_1700011", "name": "Lucky Roller", "type": "Mini Game"},
        {"code": "2_1700014", "name": "Plinko", "type": "Mini Game"},
        {"code": "2_1700015", "name": "Lucky Dice", "type": "Mini Game"},
        {"code": "2_1700017", "name": "GoalShoot", "type": "Mini Game"},
        {"code": "2_1700022", "name": "Fortune Panda", "type": "SLOTS"},
        {"code": "2_1700024", "name": "Fruit Slots", "type": "Mini Game"},
        {"code": "2_1700026", "name": "Crazy Halloween", "type": "SLOTS"},
        {"code": "2_1700028", "name": "Keno", "type": "Mini Game"},
        {"code": "2_1700029", "name": "Sharpshooter", "type": "SLOTS"},
        {"code": "2_1700030", "name": "Christmas Gift", "type": "SLOTS"},
        {"code": "2_1700031", "name": "Glacier Treasure", "type": "SLOTS"},
        {"code": "2_1700033", "name": "Lucky Monkey", "type": "Mini Game"},
        {"code": "2_1700034", "name": "Tower", "type": "Mini Game"},
        {"code": "2_1700035", "name": "Fruits Crash", "type": "Mini Game"},
        {"code": "2_1700036", "name": "Hidden Realm", "type": "SLOTS"},
        {"code": "2_1700037", "name": "Maya Treasure", "type": "SLOTS"},
        {"code": "2_1700038", "name": "Triple", "type": "Mini Game"},
        {"code": "2_1700039", "name": "Ring", "type": "Mini Game"},
        {"code": "2_1700040", "name": "Treasure Hunt", "type": "SLOTS"},
        {"code": "2_1700041", "name": "Stairs", "type": "Mini Game"},
        {"code": "2_1700042", "name": "Hotpot", "type": "SLOTS"},
        {"code": "2_1700043", "name": "Blessing of Ice and Fire", "type": "SLOTS"},
        {"code": "2_1700047", "name": "Churrasco", "type": "SLOTS"},
        {"code": "2_1700049", "name": "Beach Fun", "type": "SLOTS"},
        {"code": "2_1700051", "name": "Magic Scroll", "type": "SLOTS"},
        {"code": "2_1700053", "name": "EDM Mania", "type": "SLOTS"},
        {"code": "2_1700054", "name": "Club Goddess", "type": "SLOTS"},
        {"code": "2_1700057", "name": "Mermaid", "type": "SLOTS"},
        {"code": "2_1700058", "name": "Bee Workshop", "type": "SLOTS"},
        {"code": "2_1700059", "name": "Farm Town", "type": "SLOTS"},
        {"code": "2_1700063", "name": "Wukong", "type": "SLOTS"},
        {"code": "2_1700064", "name": "Halloween Meow", "type": "SLOTS"},
        {"code": "2_1700065", "name": "Sunshine Coast", "type": "SLOTS"},
        {"code": "2_1700067", "name": "Freedom Day", "type": "SLOTS"},
        {"code": "2_1700071", "name": "Samba Sensation", "type": "SLOTS"},
    ]


    def handle(self, *args, **kwargs):
        pass
