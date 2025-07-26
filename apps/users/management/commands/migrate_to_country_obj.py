from django.core.management.base import BaseCommand
from apps.users.models import Country, Users


class Command(BaseCommand):
    help = "Migrates the old users to the new countries"

    def handle(self, *args, **kwargs):
        usa = Country.objects.get(code_cca2="US")
        for user in Users.objects.all():
            if user.country_obj:
                print(f'{user.username.ljust(20, " ")}: is already on country obj -> {user.country_obj.name}')
                continue
            old = user.country
            obj_country = Country.objects.filter(code_cca2=user.country).first()
            user.country_obj = obj_country or usa
            user.country = user.country_obj.code_cca2
            user.save()

            print(f'{user.username.ljust(20, " ")}: has been migrated from {old} to country obj -> {user.country_obj.name}')