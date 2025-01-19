import time
import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from django.conf import settings
from django.utils import timezone
from django.core.management.base import BaseCommand

from users.models import CrmDetails, Users


class Command(BaseCommand):
    def handle(self, *args, **options):
        while True:
            current_time = timezone.now()
            print("************************************")
            print(f"CRM Cron Run Time: {current_time}")
            print("************************************")
            crm_list = CrmDetails.objects.filter(status="Active")


            for mail_detail in crm_list:
                scheduled_at =  (mail_detail.scheduled_at - datetime.timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
                time_now = (current_time).strftime("%Y-%m-%d %H:%M:%S")
                try:
                    if scheduled_at <= time_now:
                        users_emails = []
                        if mail_detail.emails:
                            users_emails = [(email,) for email in mail_detail.emails.split(",")]
                        else:
                            if mail_detail.category == "Active User Notification":
                                users_emails = list(Users.objects.filter(role="player", email__isnull=False, modified__gte=current_time - datetime.timedelta(days=90)).values_list('email'))
                            elif mail_detail.category == "Inactive User Notification":
                                users_emails = list(Users.objects.filter(role="player", email__isnull=False, modified__lte=current_time - datetime.timedelta(days=90)).values_list('email'))
                            else:
                                users_emails = list(Users.objects.filter(role="player", email__isnull=False).values_list('email'))
                        for user_email in users_emails:
                            message = Mail(
                                from_email=settings.SENDGRID_EMAIL,
                                to_emails=user_email[0],
                                subject=mail_detail.subject,
                                html_content=mail_detail.get_crm_content())

                            sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
                            sg.send(message)

                            mail_detail.status = "Inactive"
                            mail_detail.save()

                except Exception as e:
                    print(f"CRM Mailing Cron Exception: {e}")

            print(f"Waiting for 10 Minutes")
            time.sleep(600)
