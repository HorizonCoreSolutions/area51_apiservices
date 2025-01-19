import traceback
import boto3
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.casino.models import GameImages


def export_image_to_s3(path, folder_name):
    session = boto3.Session(
        aws_access_key_id=settings.ACCESS_KEY_ID,
        aws_secret_access_key=settings.SECRET_ACCESS_KEY
    )
    s3 = session.resource('s3')
    bucket = s3.Bucket(settings.AWS_S3_BUCKET_NAME)
    with open(path, 'rb') as data:
        file_name = os.path.basename(path)
        key = folder_name + "/" + file_name
        name = os.path.splitext(file_name)[0]
        bucket.put_object(Key=key, Body=data, ACL='public-read', ContentType="image/jpeg")
        image_url = f'https://{settings.AWS_S3_BUCKET_NAME}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/{key}'
        try:
            game_image = GameImages.objects.get(name=name)
            game_image.url = image_url
            game_image.save()
        except GameImages.DoesNotExist:
            GameImages(name=name, url=image_url).save()
        print(path, image_url)


class Command(BaseCommand):
    help = 'Export Images for Games'

    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument('--path', help='export file to s3 bucket',)
        parser.add_argument('--folder', help='Destination folder in s3 bucket', )

    def handle(self, *args, **kwargs):
        try:
            path = kwargs["path"]
            folder_name = kwargs["folder"] if kwargs["folder"] else ''
            if os.path.isfile(path):
                export_image_to_s3(path, folder_name)
            for subdir, dirs, files in os.walk(path):
                for file in files:
                    full_path = os.path.join(subdir, file)
                    export_image_to_s3(full_path, folder_name)
        except Exception as e:
            tb = traceback.format_exc()
            print(tb)
            raise e
