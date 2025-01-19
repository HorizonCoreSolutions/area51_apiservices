import random, string
from django.core.management.base import BaseCommand

from apps.users.models import Users


class Command(BaseCommand):
    help = "Update existing players with referral code"

    def handle(self, *args, **kwargs):
        try:
            players = Users.objects.filter(role="player", referral_code=None)
            print("::Start::")
            for player in players:
                if not player.referral_code:
                    user_referral_code = ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(5))
                    user_referral_code = "RF-" + player.username + user_referral_code
                    player.referral_code = user_referral_code
                    player.save()
                    print(f'Referral code Added for user {player.username}')
        except Exception as e:
            print("Update existing players with referral code exception ====>>>")
            print(e)
        print("::End::")
