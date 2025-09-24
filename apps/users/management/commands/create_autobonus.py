from django.core.management.base import BaseCommand
from apps.users.models import BONUS_EVENTS, BonusPercentage, Users 


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        qs = BonusPercentage.objects.filter(dealer=None, bonus_type="automated_promos").first()
        if qs:
            self.stdout.write(self.style.WARNING("This object has been already created"))
            return

        users = Users.objects.filter(role="admin")

        for user in users:
            BonusPercentage.objects.create(
                dealer=user,
                bonus_type="automated_promos",
                percentage=0.0,
                deposit_bonus_limit=1,
                referral_bonus_limit=1,
                welcome_bonus_limit=5,
                losing_bonus_limit=1,
                bet_bonus_limit=1,
                bet_bonus_per_day_limit=1,
                deposit_bonus_per_day_limit=1,
            )

            self.stdout.write(self.style.SUCCESS("Default BonusPercentage created."))
