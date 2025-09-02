from django.test import TestCase
from types import SimpleNamespace
from apps.casino.onegamehub import OneGameHub


class OneGameHubTest(TestCase):

    def setUp(self):
        self.ogh = OneGameHub(
            config={
                "salt": "93a8b2f2-6110-4fe3-bbfb-eee42583f363",
                "url": "https://1gamehub.com/",
            })

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
        result = self.ogh.is_valid_request(self.mock_request)

        self.assertTrue(result, "The hash result does not match.")
