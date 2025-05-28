from django.core.management.base import BaseCommand
from apps.users.models import Users


class Command(BaseCommand):
    help = "Migrates the old users to the new countries"

    def handle(self, *args, **kwargs):
        for user in Users.objects.all():
            print(user.username, end=': ')
            if not user.full_name:
                print('has no full_name')
                print(''.center(40, '='))
                continue
            full_name = user.full_name.split(" ")
            print(full_name[0], full_name[-1] if len(full_name) > 1 else "", sep=' | ')
            
            user.first_name = full_name[0]
            user.last_name = full_name[-1] if len(full_name) > 1 else ""
            
            user.save()