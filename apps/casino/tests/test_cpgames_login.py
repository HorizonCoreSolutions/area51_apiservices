from django.test import TestCase
from apps.casino.cpgames import CPgames
from apps.users.models import Users


class CPgamesTest(TestCase):
    def test_login(self):
        cp = CPgames()