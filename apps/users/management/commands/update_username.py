from django.core.management.base import BaseCommand
from django.conf import settings
from django.db.models.functions import Lower
from apps.users.models import Users



class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        try:
            change = {}
            usernames = list(Users.objects.values_list("username", flat=True))
            for username in usernames:
                users= Users.objects.filter(username__iexact=username.lower()).order_by("-created")
                if users.count()>1:
                    for index, user in enumerate(users[1:]):
                        change.update({user.username:f"{user.username}{index}".lower()})
                        user.username = f"{user.username}{index}".lower()
                        user.save()
                    print(f"{users.count()}-{username}-{users}-{users.first().role}")
                    print("====================================")
            print(change)
        
            users = Users.objects.all()
            users.update(username=Lower('username'))
        except Exception as e:
            print("ERROR : ",e)  

