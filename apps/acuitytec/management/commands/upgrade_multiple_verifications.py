from django.core.management.base import BaseCommand
from apps.users.models import Users
from django.db.models import Q


class Command(BaseCommand):
    help = "Migrates the old users to the new countries"

    def handle(self, *args, **kwargs):
        counter = 0
        if Users.objects.filter(~Q(phone_verified=0)).exists():
            print("you already have data. We suggest to create a more detailed migration")
            return
        for user in Users.objects.all():
            user.phone_verified = 1 if user.is_verified else 0
            counter += 1 if user.is_verified else 0
            user.save()
            
        print(f"{counter} users are phone verified.")