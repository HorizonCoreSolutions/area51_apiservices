import io
import uuid
import time
import requests

from django.conf import settings
from django.db.models import Q
from django.core.management.base import BaseCommand
from django.core.files.uploadedfile import InMemoryUploadedFile

from apps.users.models import FortunePandasGameList, FortunePandasGameManagement, Users
from apps.users.fortunepandas import FortunePandaAPIClient


class Command(BaseCommand):
    help = 'Get FortunePandas Game List'

    def handle(self, *args, **kwargs):
        try:
            while True:
                game_ids = []
                game_list = self.get_game_list()
                if game_list:
                    print(F"TOTAL GAMES = {len(game_list)}")
                    for game in game_list:
                        image_url = game.get("gameLogo")
                        response = requests.get(image_url)
                        if response.status_code == 200:
                            image_content = io.BytesIO(response.content)
                            filename_format = image_url.split('/')[-1].split(".")
                            name, format = filename_format[-2], filename_format[-1]
                            image_name = f"{name}{uuid.uuid4()}.{format}"
                            image_file = InMemoryUploadedFile(
                                image_content,
                                'ImageField',
                                image_name,
                                'image/png',
                                len(response.content),
                                None
                            )

                            obj, created = FortunePandasGameList.objects.update_or_create(
                                game_id = game.get("kindId"),
                                defaults={
                                    "game_name": game.get("gameName"),
                                    "game_category": game.get("gameType"),
                                }
                            )
                            
                            if not created and obj.game_image:
                                obj.game_image.delete(save=False)
                                
                            obj.game_image = image_file
                            obj.save()

                            self.update_or_create_fortunepandas_management(obj)
                            game_ids.append(game.get("kindId"))
                            
                            print(f"GAME {game.get('gameName')} saved!!!")
                    FortunePandasGameList.objects.filter(~Q(game_id__in=game_ids)).delete()
                else:
                    print("No response from FortunePandas gamelist")

                print('Sleep for 12 hours')
                time.sleep(43200)
        except Exception as e:
            print(e)
            raise e
    
    
    def get_game_list(self):
        MAX_RETRIES = 3
        try:
            admin = Users.objects.filter(role="admin").first()
            client = FortunePandaAPIClient(
                settings.FORTUNEPANDAS_BASE_URL,
                settings.FE_DOMAIN,
                settings.FORTUNEPANDAS_AGENT_NAME,
                settings.FORTUNEPANDAS_AGENT_PASSWORD,
                admin.fortune_pandas_api_key,
            )
            for attempt in range(MAX_RETRIES):
                response = client.get_game_list()
                if response.get("code") in [200, "200"]:
                    return response.get("data")
                elif response.get("msg") in ["Session timeout.", "Signature error."]:
                    client.update_apikey(admin)

        except Exception as e:
            print(f"Error fetching game list: {e}")

    
    def update_or_create_fortunepandas_management(self, game):
        users = Users.objects.filter(role="admin")

        for user in users:
            obj, created = FortunePandasGameManagement.objects.get_or_create(
                admin = user,
                game = game
            )
            obj.save()

            