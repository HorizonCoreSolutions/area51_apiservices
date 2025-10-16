from django.test import TestCase
from types import SimpleNamespace
from urllib.parse import urlparse
from apps.users.models import Users
from apps.casino.onegamehub import OneGameHub


class OneGameHubTest(TestCase):

    def setUp(self):
        self.ogh = OneGameHub()
        self.hash_ogh = OneGameHub(
            config={
                "salt": "93a8b2f2-6110-4fe3-bbfb-eee42583f363",
                "url": "https://1gamehub.com/",
            })

        Users.objects.create(
            id=1,
            username="test_user",
            balance=500,
            bonus_balance=10,
            casino_account_id=1
        )

        data = {
            "action": "balance",
            "hash": ("686647c19a84f28fb42e82294b41b1a7"
                     "9309b15fcc8a7c01de2f75823d1e21b8"),
            "currency": "MYR",
            "extra": "",
            "player_id": "7",
        }

        self.mock_request = SimpleNamespace(
            GET=SimpleNamespace(dict=lambda: data))

    def test_01_verify_request(self):
        result = self.hash_ogh.is_valid_request(self.mock_request)

        self.assertTrue(result, "The hash result does not match.")

    def test_02_get_game(self):

        success, data = self.ogh.start_game(
            {
                "game_id": "marsdinner",
                "lang": "en",
                "account_id": "1",
                "device": "desktop",
                "mode": "gold"
            },
            ip="127.0.0.1"
        )
        self.assertTrue(success, "Method start_game 1gamehub failed")

        url = data.get(
                "url", {}
                ).get("result", {}).get("SessionUrl")  # type: ignore

        print(f"\n{url}")

        p = urlparse(url)
        self.assertTrue(p.scheme and p.netloc, f"{url} is not a valid URL")
