import re
from django.test import TestCase
from apps.casino.cpgames import CPgames
from apps.users.models import Users
from random import choices


class CPgamesTest(TestCase):

    def setUp(self):
        Users.objects.create(
            id=1,
            username="test_user",
            balance=500,
            bonus_balance=10,
        )

    def test_01_login(self):
        t = Users.objects.filter(username="test_user").first()
        cp = CPgames()

        result = cp.login_user(t)

        self.assertTrue(result, "CPgames call was not successful")


    def test_02_get_url(self):
        t = Users.objects.filter(id=1).first()
        cp = CPgames()

        # list_games = cp.get_games()
        # game_key = choices(list_games)

        game_key = "2_1700063"
        url = cp.get_game_url(user=t, game_id=game_key,lang="es")

        print(url)
        valid_url = bool(re.match(r'^https?://[\w\.-]+\.\w+', url))
        self.assertTrue(valid_url, "the result is not a valid url")


    def test_03_game_list(self):
        cp = CPgames()

        result = cp.get_games()

        self.assertGreaterEqual(len(result), 1, msg="No games were fetched")



