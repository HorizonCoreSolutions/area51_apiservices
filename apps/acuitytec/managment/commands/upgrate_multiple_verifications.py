from django.core.management.base import BaseCommand
from apps.users.models import Users


class Command(BaseCommand):
    help = "Migrates the old users to the new countries"

    def handle(self):
        for user in Users.objects.all():
            user.phone_verified = user.is_verified
            user.save()