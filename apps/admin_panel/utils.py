import json
import datetime

from decimal import Decimal
from django.utils import timezone
from pytz import timezone as zone
import requests

from apps.bets.models import Transactions
from apps.users.models import *
from io import BytesIO
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
import os
from django.conf import settings
import html2text
import random
import string
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from compat import render_to_string
from rest_framework import status
from django.db import transaction
from apps.bets.utils import generate_reference

def check_min_date(user, time_diff=1):
    bets = UserBets.objects.filter(user=user).order_by("-modified").first()
    trans = Transactions.objects.filter(user=user).order_by("-modified").first()
    group = []
    if trans:
        group.append(trans.modified)
    if bets:
        group.append(bets.modified)
    if trans:
        group.append(trans.modified)
    group.sort()
    if group:
        diff = timezone.now() - group[-1]
        if diff >= datetime.timedelta(seconds=time_diff):
            return True, None
        else:
            val = int((datetime.timedelta(seconds=time_diff) - diff).total_seconds())
            # print(val)
            return False, val
    return True, None


def get_casino_transactions_index(table, index_table, from_date, to_date):
    from_date = from_date.replace(hour=0, minute=0, second=0, microsecond=0)
    start_index = index_table.objects.filter(created_date__gte=from_date).order_by("created_date").first()
    if start_index:
        start_index = start_index.transaction.id
    else:
        start_index = table.objects.order_by("id").first().id

    to_date = to_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_index = index_table.objects.filter(created_date__lte=to_date).order_by("created_date").last()
    if end_index:
        end_index = end_index.transaction.id
    else:
        end_index = table.objects.order_by("id").last().id

    return start_index, end_index


def concurrent_aggregation(queryset, aggregate_params):
    return queryset.aggregate(**aggregate_params)


def adjust_datetime(dt, tz):
    time_now = datetime.datetime.utcnow()
    fmt = "%z"
    tz = zone(tz)
    offset = tz.localize(time_now).strftime(fmt)
    hours = float(offset[:-2])
    minutes = float(offset[-2:])
    return dt - datetime.timedelta(hours=hours, minutes=minutes)


def fetch_resources(uri, rel):
    path = os.path.join(uri.replace(settings.STATIC_URL, ""))
    return path


def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html  = template.render(context_dict)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("ISO-8859-1")), result)
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return None


def textify(html):
    h = html2text.HTML2Text()

    # Don't Ignore links, they are useful inside emails
    h.ignore_links = False
    return h.handle(html)


class DecimalDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(
            self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, obj):
        ret = {}
        for key, value in obj.items():
            ret[key] = Decimal(value) 
        return ret


def create_casino_account_id():
    '''create unique casino id for'''
    code = ''.join(random.choices(string.ascii_lowercase, k=3)) + str(random.randint(0,1000))
    if Users.objects.filter(casino_account_id=code).first():
        create_casino_account_id()
    print(code)
    return code

def send_email(player):
    player = Player.objects.filter(id=player).first() 
    context={
        "affiliate_link":player.affiliate_link,
        "fe_url": settings.FE_DOMAIN,
    }
    sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
    mail_template = EmailTemplateDetails.objects.filter(category='affiliate_mail').first()
    if mail_template:
        mail = Mail( 
            from_email=settings.SENDGRID_EMAIL,
            to_emails= [player.email]
        )
        mail.template_id = mail_template.template_id
        mail.dynamic_template_data = context
        sg.send(mail)
        return
    
    html_content = render_to_string("admin/affiliate_email.html", context)
    message = Mail( 
            from_email=settings.SENDGRID_EMAIL,
            to_emails=player.email,
            subject="Affiliate Link",
            html_content=html_content)
    sg.send(message)

def validate_address(address, currency):
    try:
        api_url = settings.NOWPAYMENTS_API_URL
        api_key = settings.NOWPAYMENTS_API_KEY

        headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json'
        }

        payload = {
            'address': address,
            'currency': currency,
        }

        try:
            response = requests.post(api_url+'payout/validate-address', headers=headers, json=payload)
            if response.status_code == status.HTTP_200_OK:
                return True
            else:
                return False
        except requests.exceptions.RequestException as e:
            print('Error occurred:', e)
            return None 
    except Exception as e:
        print(e)

@transaction.atomic
def off_market_refund_transactions(id):
    try:  
        transaction = OffMarketTransactions.objects.filter(id=id).first()
        user=Users.objects.filter(id = transaction.user_id).first()
        user.balance = user.balance + (Decimal(transaction.amount) - Decimal(transaction.bonus))
        user.save()
        admin = Users.objects.filter(role='admin').first()
        try:
            Transactions.objects.update_or_create(
            user=user,
            journal_entry="debit",
            amount=(Decimal(transaction.amount) - Decimal(transaction.bonus)),
            status="charged",
            merchant=admin,
            previous_balance=user.balance - Decimal(transaction.amount)-Decimal(transaction.bonus),
            new_balance=user.balance,
            description=f'refund for Failed deposit amount {(Decimal(transaction.amount) - Decimal(transaction.bonus))}',
            reference=generate_reference(user),
            bonus_type= None,
            bonus_amount=0
        )
        except Exception as e:
            print(e)
    except Exception as e:
        print(e)