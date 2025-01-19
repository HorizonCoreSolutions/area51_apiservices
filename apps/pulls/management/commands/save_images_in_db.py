import traceback
import boto3
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.casino.models import GameImages



class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        session = boto3.Session(
            aws_access_key_id=settings.ACCESS_KEY_ID,
            aws_secret_access_key=settings.SECRET_ACCESS_KEY
        )
        s3 = session.resource('s3')
        bucket = s3.Bucket(settings.AWS_S3_BUCKET_NAME)
        print("Initialized Bucket")
        for image in bucket.objects.all():
            file_name = image.key
            print(file_name)
            if 'others' in file_name:
                try:
                    name = file_name.split('/')[1].split('.')[0]
                    if not name:
                        continue
                except:
                    continue
                image_url = f'https://{settings.AWS_S3_BUCKET_NAME}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/{file_name}'
                print(f"Image-url: {image_url}")
                try:
                    game_image = GameImages.objects.get(name=name)
                    game_image.url = image_url
                    game_image.save()
                except GameImages.DoesNotExist:
                    GameImages(name=name, url=image_url).save()
                print("GameImage object created")
