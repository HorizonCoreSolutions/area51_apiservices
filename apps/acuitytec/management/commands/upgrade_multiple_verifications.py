from django.core.management.base import BaseCommand
from apps.users.models import Users


class Command(BaseCommand):
    help = "Migrates the old users to the new countries"

    def handle(self, *args, **kwargs):
        counter = 0
        for user in Users.objects.all():
            user.phone_verified = 1 if user.is_verified else 0
            counter += 1 if user.is_verified else 0
            user.save()
            
        print(f"{counter} users are phone verified.")