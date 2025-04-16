from django.test import TestCase
from apps.casino.cpgames import CPgames
from apps.users.models import Users


class CPgamesTest(TestCase):

    def setUp(self):
        Users.objects.create(
            username="test_user",
            balance=500,
            bonus_balance=10,
        )

    def test_login(self):

        t = Users.objects.first()
        cp = CPgames()

        result = cp.login_user(t)

        self.assertTrue(result, "CPgames call was not successful")
