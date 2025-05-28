from django.core.management.base import BaseCommand
from apps.users.models import Users


class Command(BaseCommand):
    help = "Migrates the old users to the new countries"

    def handle(self, *args, **kwargs):
        usa = Users.objects.get(code_cca2="US")
        for user in Users.objects.all():
            if not user.full_name:
                continue
            full_name = user.full_name.split(" ")
            user.first_name = full_name[0]
            user.last_name = full_name[-1] if len(full_name) > 1 else ""