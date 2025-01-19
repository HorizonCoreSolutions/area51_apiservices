import time
import datetime

from django.conf import settings
from django.utils import timezone
from django.core.management.base import BaseCommand

from apps.users.models import SMSDetails
from twilio.rest import Client
import html2text
client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def textify(html):
    h = html2text.HTML2Text()
    # Don't Ignore links, they are useful inside SMS
    h.ignore_links = False
    return h.handle(html)

class Command(BaseCommand):

    def handle(self, *args, **options):
        while True:
            current_time = timezone.now()
            print("************************************")
            print(f"CRM Cron Run Time: {current_time}")
            print("************************************")
            sms_list = SMSDetails.objects.filter(status="Active")
            print(sms_list)
            for sms_detail in sms_list:
                scheduled_at =  (sms_detail.scheduled_at - datetime.timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
                time_now = (current_time + datetime.timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
                try:
                    print("scheduled_at---->", scheduled_at)
                    print("time_now---->", time_now)
                    print(scheduled_at <= time_now)
                    if scheduled_at <= time_now:    
                        phone_numbers = sms_detail.phone_number
                        message_body = sms_detail.content
                        print(message_body)
                        for number in phone_numbers.split(','):
                            print(">>>>>>>>>>>>>>>>>", f"SMS sending to {number}.")
                            
                            message = client.messages.create(
                                                body = textify(message_body),
                                                from_= settings.TWILIO_PHONE_NUMBER,
                                                to=number
                                                )
                            print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>", message.sid)

                except Exception as e:
                    print(f"CRM SMS Cron Exception: {e}")

            print(f"Waiting for 30 seconds")
            time.sleep(30)
