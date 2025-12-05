import datetime
from datetime import date, timedelta
from bisect import bisect_right
from itertools import count
import json
import math
import operator
import re
from decimal import Decimal
from threading import Thread
import traceback
from functools import reduce
import base64
from django.core.exceptions import PermissionDenied
import pytz
import boto3
import uuid
from itertools import chain
from operator import attrgetter
from urllib.parse import parse_qs
from collections import defaultdict

from PIL import Image
import sys
from io import BytesIO
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import InMemoryUploadedFile
from cryptography.fernet import Fernet

from braces import views
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import make_password
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from apps.casino.models import (CasinoGameList, CasinoHeaderCategory, CasinoManagement, GSoftTransactions, Tournament,
    TournamentPrize, TournamentTransaction, Providers)

from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import get_language, gettext_lazy as _
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, ListView, TemplateView, UpdateView, View
from django.views.generic.edit import FormMixin
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Exists, F, OuterRef, Q, Sum, Count, TextField, Value, DecimalField, ExpressionWrapper, \
    Subquery, Max, CharField, Case, When, BooleanField 
from django.db.models.functions import Coalesce, Lower, Replace, Cast
from django.contrib.postgres.aggregates import ArrayAgg

from apps.admin_panel.payments import get_payment_qr_code, get_preference
from apps.casino.models import (CasinoGameList, CasinoHeaderCategory, CasinoManagement, GSoftTransactions, Tournament,
    TournamentPrize, TournamentTransaction)
from apps.admin_panel.forms import (AdminModelForm, AgentModelForm,
                                    DealerModelForm, OffMarketGameForm, PlayerModelForm,
                                    AdminBannerForm, AboutForm, PromotionForm, PrivacyPolicyForm,FAQForm,
                                    TermsConditinosForm,CookiePolicyForm, IntroductionForm, CashappDetailForm,
                                    SettingsLimitsForm,FooterCategoryForm, CMSPagesForm, SocialLinkForm, EditSocialLinkForm,DetailSocialLinkForm, UserGamesForm
                                    )
from apps.casino.tasks import task_update_offmarket_transaction
from apps.casino.clients import RefujiClient
from apps.payments.models import (AlchemypayOrder, Bundle, CoinFlowTransaction, MnetTransaction, NowPaymentsTransactions,
    WithdrawalCurrency, WithdrawalRequests)
from apps.users.forms import PageBlockerCmsPromotionsForm, ToasterCmsPromotionsForm
from apps.users.models import FooterPages, MAX_SPEND_AMOUNT, Permission, ResponsibleGambling, BONUS_EVENTS
from apps.users.utils import send_message_to_chatlist, send_live_status_to_player, encrypt
from excel_response import ExcelResponse
from apps.bets.utils import generate_reference
from apps.admin_panel.utils import *
from apps.core.auth_mixins import CheckRolesMixin
from apps.core.permissions import IsPlayer, IsAdmin
from apps.payments.utils import COIN_PAYMENTS,createnowpaymentswithdrawal
from .tasks import email_template_crm, rejection_mail, send_sms_crm, transaction_mail


# from apps.pulls.management.commands.firestore import is_bet_disabled
from apps.users.models import (
        AccountDetails,
        BonusPercentage,
        OtpCredsInfo,
        PromoCodes,
        PromoCodesLogs,
        SuperAdminSetting,
        CmsPromotions)
from apps.bets.models import BONUS, CASHBACK, CREDIT, DEBIT, DEPOSIT, WITHDRAW, Transactions
from apps.users.utils import send_player_balance_update_notification
from apps.users.models import (
    Admin,
    Agent,
    CronInfo,
    Dealer,
    Player,
    CURRENCY_CHOICES,
    TIMEZONES,
    Users,
    AdminBanner,
    USER_ROLES,
    CmsAboutDetails,
    CmsContactDetails,
    CmsPromotionDetails,
    CrmDetails,
    CmsPrivacyPolicy,
    CmsFAQ,
    TermsConditinos,
    CookiePolicy,
    Introduction,
    SettingsLimits,
    SocialLink,
    FooterCategory,
    CmsPages,
    SMSDetails,
    SpintheWheelDetails
)
from apps.users.models import (
    CASHBACK_PERCENTAGE ,
    CASHBACK_TIME_LIMIT,
    MIN_AMOUNT_REQUIRED_FOR_JACKPOT,
    JACKPOT_TIME_LIMIT,
    JACKPOT_AMOUNT
)


FERNET_KEY = settings.FERNET_KEY
FERNET_SALT = settings.FERNET_SALT
SERVICE_CREDS_PASSWORD = settings.SERVICE_CREDS_PASSWORD


class PlayersView(CheckRolesMixin, FormMixin, ListView):

    model = Player
    paginate_by = 20
    template_name = "admin/player/players.html"
    form_class = PlayerModelForm
    allowed_roles = ["admin", "dealer", "superadmin", "agent",'staff']
    context_object_name = "players"
    date_format = "%d/%m/%Y"
    queryset = Player.objects.all()

    ORDER_MAPPING = {
        "1": "-last_login",
        "2": "balance",
        "3": "-balance",
        "4": "locked",
        "5": "-locked",
        "6": "created",
        "7": "-created",
    }

    def time_zone_converter(self,date_time_obj,Inverse_Time_flag):


        try:
            current_timezone = self.request.session['time_zone']
        except:
            current_timezone='en'
        if(current_timezone=="en"):
            return date_time_obj
        elif(current_timezone=='ru'):
            current_timezone='Europe/Moscow'
        elif(current_timezone=='tr'):
            current_timezone='Turkey'
        else:
            current_timezone='Europe/Berlin'
        timee=date_time_obj.replace(tzinfo=None)

        if(Inverse_Time_flag):
            new_tz=pytz.timezone(current_timezone)
            old_tz=pytz.timezone("EST")
        else:
            old_tz=pytz.timezone(current_timezone)
            new_tz=pytz.timezone("EST")
        new_timezone_timestamp = old_tz.localize(timee).astimezone(new_tz)
        return new_timezone_timestamp


    def get_queryset(self):
        agents = self.request.GET.getlist("agents", "")
        dealers = self.request.GET.getlist("dealers", "")
        user_name = self.request.GET.getlist("user_name", "")
        order = self.request.GET.get("order", "7")
        ability_to_play = self.request.GET.get("ability-to-play", "")
        location = self.request.GET.get("location", "")
        zip_code = self.request.GET.get("zip_code", "")
        is_verified = self.request.GET.get('is_verified', '')

        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
            self.queryset = self.queryset.filter(created__gte=start_date)
        # else:
            # by default show results from first day of month
            # current_date = timezone.now()
            # first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
            # self.queryset = self.queryset.filter(created__gte=first_day_of_month)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
            self.queryset = self.queryset.filter(created__date__lte=end_date)

        if agents and all([value.isdigit() for value in agents]):
            self.queryset = self.queryset.filter(agent_id__in=agents)
        if dealers and all([value.isdigit() for value in dealers]):
            self.queryset = self.queryset.filter(dealer_id__in=dealers)

        if user_name and all([value.isdigit() for value in user_name]):
            self.queryset = self.queryset.filter(id__in=user_name)

        if is_verified and is_verified not in ["", "3"]:
            is_verified = True if is_verified == "1" else False
            self.queryset = self.queryset.filter(is_verified = is_verified)

        if ability_to_play:
            ability_to_play = True if ability_to_play == "1" else False
            self.queryset = self.queryset.filter(is_active=ability_to_play)

        if location:
            self.queryset = self.queryset.filter(
                    Q(state__icontains=location) | Q(complete_address__icontains=location)
                )
        if(zip_code):
                self.queryset = self.queryset.filter(zip_code=zip_code)


        if order and order in self.ORDER_MAPPING.keys():
            self.queryset = self.queryset.order_by(self.ORDER_MAPPING[order])
        else:
            self.queryset = self.queryset.order_by("last_login")
        if self.request.user.role == "dealer":
            self.queryset = self.queryset.filter(dealer=self.request.user)
        if self.request.user.role == "agent":
            self.queryset = self.queryset.filter(agent=self.request.user)

        ResponsibleGambling.objects.filter(blackout_expire_time__lt = datetime.now(timezone.utc)) \
                                   .update(blackout_expire_time=None,blackout_expire_hours=None,is_blackout=False)

        self.queryset = self.queryset.annotate(
            debit=(
                Coalesce(
                    Sum(
                        "transactions__amount",
                        filter=Q(transactions__journal_entry="debit"),
                    ),
                    0,
                )
            ),
            credit=(
                Coalesce(
                    Sum(
                        "transactions__amount",
                        filter=Q(transactions__journal_entry="credit"),
                    ),
                    0,
                )
            ),
            profit=(
                Coalesce(
                    Sum(
                        "transactions__amount",
                        filter=Q(transactions__journal_entry="credit"),
                    ),
                    0,
                )
                - Coalesce(
                    Sum(
                        "transactions__amount",
                        filter=Q(transactions__journal_entry="debit"),
                    ),
                    0,
                )
            ),
        )
        return self.queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # defaults
        context['selected_dealers'] = Dealer.objects.none()
        context['selected_agents'] = Agent.objects.none()
        context['selected_players'] = Player.objects.none()
        context['data'] = {}

        current_date = timezone.now()
        first_day_of_month_UTC = current_date.replace(day=1, hour=0, minute=0)
        first_day_of_month=self.time_zone_converter(first_day_of_month_UTC,True)
        current_time=timezone.now()
        current_time=self.time_zone_converter(current_time,True)
        user_name = self.request.GET.getlist("user_name", [])
        agents = self.request.GET.getlist("agents", [])
        dealers = self.request.GET.getlist("dealers", [])
        ability_to_play = self.request.GET.get('ability-to-play', '')

        context['form2'] = UserGamesForm()
        context["username"] = self.request.GET.get("user_name", "")
        context["order"] = self.request.GET.get("order", "7")
        context["zip_code"] = self.request.GET.get("zip_code", "")
        context["is_verified"] = self.request.GET.get("is_verified", "")
        context["to"] = self.request.GET.get("to", current_time.strftime(self.date_format))
        context["from"] = self.request.GET.get("from", first_day_of_month.strftime(self.date_format))
        if ability_to_play  in ['1','2']:
            context["ability_to_play"] = '1' if ability_to_play == "1" else '2'
        else:
            context["ability_to_play"] = ''
        context["location"] = self.request.GET.get('location', '')

        if dealers:
            context["selected_dealers"] = Dealer.objects.filter(id__in=dealers)

        if agents:
            context["selected_agents"] = Agent.objects.filter(id__in=agents)

        if user_name:
            context["selected_players"] = Player.objects.filter(id__in=user_name)
        return context



class DealerAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "dealer", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        search = request.POST.get("search")
        dealers = Dealer.objects.all()
        if request.POST.get("affiliate_search"):
            dealers = dealers
        if search:
            dealers = dealers.annotate(username_lower=Lower("username")).filter(
               username__istartswith=search.lower()).order_by('username')

        dealers = dealers.values("id", "username")[0:10]
        results = []
        for dealer in dealers:
            results.append({"value": dealer["id"], "text": dealer["username"]})
        return self.render_json_response(results)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class AgentAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "dealer", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def post_ajax(self, request, *args, **kwargs):

        term = request.POST.get("search")
        dealer_ids = request.POST.getlist("dealers[]", None)
        agents = Agent.objects.all()

        if request.POST.get("affiliate_search"):
            agents = agents
        if term:
            agents = agents.annotate(username_lower=Lower("username")).filter(
                username__istartswith=term.lower()
            ).order_by('username')
        if dealer_ids:
            agents = agents.filter(dealer_id__in=dealer_ids)
        if request.user.role == "dealer":
            agents = agents.filter(dealer=self.request.user)
        agents = agents.values("id", "username")[0:10]

        results = []
        for agent in agents:
            results.append({"value": agent["id"], "text": agent["username"]})

        return self.render_json_response(results)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)        

class PlayerAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "dealer", "superadmin","agent","staff")


    def post_ajax(self, request, *args, **kwargs):
        term = request.POST.get("search")
        players = Player.objects.all()

        agents = Agent.objects.all()
        dealer_ids = request.POST.getlist("dealer[]", None)
        agent_ids = request.POST.getlist("agent[]",None)
        if term:
            players = players.annotate(username_lower=Lower("username")).filter(
                username_lower__istartswith=term.lower()
            ).order_by('username')
        if request.user.role=='dealer':
            agents=agents.filter(dealer=self.request.user)
            players=players.filter(agent_id__in=agents)

        if request.user.role == "agent":
            players = players.filter(agent=self.request.user)

        elif agent_ids:
            players = players.filter(agent_id__in=agent_ids)

        elif dealer_ids:

            agents=agents.filter(dealer_id__in=dealer_ids)
            players=players.filter(agent_id__in=agents)
        if term and request.POST.get("affiliate"):
            players = Player.objects.filter(affiliate_link__isnull=False)
            players = players.annotate(username_lower=Lower("username")).filter(
                username_lower__istartswith=term.lower()
            ).order_by('username')

        if term and request.POST.get("affiliate_new"):
            players = Player.objects.filter(affiliate_link__isnull=True)
            players = players.annotate(username_lower=Lower("username")).filter(
                username_lower__istartswith=term.lower()
            ).order_by('username')





        # if request.user.role == "dealer":
        #     agents = agents.filter(dealer=self.request.user)


        players = players.values("id", "username")[0:10]

        results = []
        for player in players:
            results.append({"value": player["id"], "text": player["username"]})

        return self.render_json_response(results)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class VerifyPlayer(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        try:
            player_id = request.POST.get("player_id", "")
            player = Player.objects.filter(id=player_id).first()
            if not player:
                return self.render_json_response(
                    {
                        "status": "Failed", 
                        "message": "Player with this username does not exists."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            if player.get_is_verified():
                player.set_is_verified(-1)
                verify = "unverified"
            else:
                player.set_is_verified(1)
                verify = "verified"

            player.save()

            return self.render_json_response({"status": "Success", "message": f"Player has been {verify}."}, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error in Verify player api : {e}")
            return self.render_json_response({"status": "Failed", "message": "Something went wrong!"}, status=status.HTTP_400_BAD_REQUEST)


class CreatePlayer(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("agent",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        try:
            user_name = request.POST.get("username", "").lower()
            email = request.POST.get("email", "")
            # country_code = request.POST.get("country_code", "")
            # phone_number = request.POST.get("phone_number", "")
            # zip_code = request.POST.get("zip_code", "")
            # complete_address = request.POST.get("complete_address", "")
            dob = request.POST.get("dob","")
            # profile_pic=request.FILES.get("profile_pic","")
            # user_id_proof=request.FILES.get("user_id_proof","")
            # state = request.POST.get("state", "")
            # city = request.POST.get("city", "")
            first_name = request.POST.get("first_name", "")
            last_name = request.POST.get("last_name", "")
            password = request.POST.get("password", "")
            confirm_password = request.POST.get("confirm_password", "")

            if Users.objects.filter(username__iexact=user_name).exists():
                return self.render_json_response({
                    "status": "Failed", 
                    "message": _("Username already exists")
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            email_pattern = r'^[\w\.-]+@[a-zA-Z\d\.-]+\.[a-zA-Z]{2,}$'
            if Users.objects.filter(email=email).exists():
                return self.render_json_response({
                    "status": "Failed", 
                    "message": _("email already exists")
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            elif not re.match(email_pattern, email):
                return self.render_json_response({
                    "status": "Failed", 
                    "message": _("Invalid email")
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )



            pattern = re.compile("[A-Za-z0-9]*$")
            if not pattern.fullmatch(user_name):
                return self.render_json_response(
                    {
                        "status": "Failed", 
                        "message": "Username must be Alphanumeric"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            # past = datetime.datetime.strptime(dob, "%Y-%m-%d")
            # present = datetime.datetime.now()

            if len(user_name) < 4:
                return self.render_json_response(
                    {
                        "status": "Failed",
                        "message": _("The username has to be at least 4 characters"),
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            if len(password) < 8:
                return self.render_json_response(
                    {
                        "status": "Failed",
                        "message": _("The password has to be at least 8 characters"),
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            if password != confirm_password:
                return self.render_json_response(
                    {
                        "status": "Failed",
                        "message": _("Confirm password does not match password."),
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # if (phone_number.isdigit()!=True):
            #     return self.render_json_response(
            #         {
            #             "status": "Failed",
            #             "message": _("enter a valid number"),
            #         },
            #         status=status.HTTP_400_BAD_REQUEST
            #     )
            # if (country_code.isdigit()!=True):
            #     return self.render_json_response(
            #         {
            #             "status": "Failed",
            #             "message": _("enter a valid country code"),
            #         },
            #         status=status.HTTP_400_BAD_REQUEST
            #     )
            # if Users.objects.filter(phone_number=phone_number,country_code=country_code).exists():
            #         return self.render_json_response({
            #         "status": "Failed", 
            #         "message": _("contact details already exists")
            #         },
            #         status=status.HTTP_400_BAD_REQUEST
            #     )  

            # if (zip_code.isdigit()!=True):
            #     return self.render_json_response(
            #         {
            #             "status": "Failed",
            #             "message": _("enter a valid zip code"),
            #         },
            #         status=status.HTTP_400_BAD_REQUEST
            #     )
            birth_year, birth_month, birth_day = dob.split("-")
            today = date.today()
            age = int(today.year) - int(birth_year) - ((int(today.month), int(today.day)) < (int(birth_month), int(birth_day)))

            if age < 18:
                return self.render_json_response(
                    {
                        "status": "Failed",
                        "message": _("Player's age should be 18+"),
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # if(past > present):


            #     return self.render_json_response(
            #         {
            #             "status": "Failed",
            #             "message": _("please enter a valid date of birth"),
            #         },
            #         status=status.HTTP_400_BAD_REQUEST
            #     )
            print(dob.split("-")[0], "**********************************")

            player = Player()

            player.username = user_name
            player.password = make_password(password)
            player.casino_account_id = create_casino_account_id()
            player.email = email
            # player.phone_number = phone_number
            # player.zip_code = zip_code
            # player.complete_address = complete_address
            player.first_name = first_name
            player.last_name = last_name
            player.dob = dob
            # if profile_pic:     
            #     filename_format = profile_pic.name.split(".")
            #     name, format = filename_format[-2], filename_format[-1]
            #     filename = f"{name}{uuid.uuid4()}.{format}"
            #     profile_thumbnail = Image.open(profile_pic)
            #     profile_thumbnail.thumbnail((500, 400))
            #     profile_thumbnail_io = BytesIO()
            #     format = 'JPEG' if format.lower() == 'jpg' else format.upper()
            #     profile_thumbnail.save(profile_thumbnail_io, format=format, filename=filename)
            #     page_thumbnail_inmemory = InMemoryUploadedFile(profile_thumbnail_io,
            #                                                      'FileField',
            #                                                      filename,
            #                                                      format,
            #                                                      sys.getsizeof(profile_thumbnail_io), None)
            #     profile_pic.name = filename
            #     player.profile_pic_thumbnail = page_thumbnail_inmemory
            #     player.profile_pic = profile_pic
            # player.user_id_proof=user_id_proof
            # player.state= state
            # player.city = city
            player.agent = request.user
            player.dealer = request.user.dealer
            player.admin = request.user.admin
            # player.country_code = country_code
            player.role = "player"
            player.is_staff = False
            player.is_superuser = False
            player.is_active = True
            player.last_activity_time = timezone.now()
            player.mnet_password = make_password(f"{user_name}{random.randint(1000, 9999)}")[:30]


            player.is_redeemable_amount = True
            default_val = DefaultAffiliateValues.objects.first()
            if default_val:
                player.affliate_expire_date = datetime.now() + timedelta(default_val.default_no_of_days)
                player.no_of_deposit_counts = default_val.default_no_of_deposit_counts
            else:
                player.no_of_deposit_counts = 1
                player.is_lifetime_affiliate = True
            # player.affliate_expire_date = datetime.datetime.now() + datetime.timedelta(days=DEFAULT_AFFILIATE_DURATION_IN_DAYS)
            # player.is_lifetime_affiliate = True
            player.ensure_country_obj()
            player.save()



            #########################  Affiliate Changes Start  ########################
            player = Users.objects.filter(id=player.id).first()

            project_domain = settings.PROJECT_DOMAIN
            key = str(settings.SECRET_KEY)[0:32]
            fernet_key = base64.urlsafe_b64encode(key.encode())
            fernet_obj = Fernet(fernet_key)
            encry_msg = fernet_obj.encrypt((str(player.id)).encode())
            encry_user = encry_msg.decode()
            player.affiliate_link = project_domain + "/affiliate-invite?affiliate_code=" + encry_user

            player.save()
            #########################  Affiliate Changes End  ########################

            return self.render_json_response({"status": "Success", "message": "Player created"}, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error in create player api : {e}")
            return self.render_json_response({"status": "Failed", "message": "Something went wrong!"}, status=status.HTTP_400_BAD_REQUEST)


class CheckLogin(TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "login.html"
    def post_ajax(self, request, *args, **kwargs):
        if not Users.objects.filter(username__iexact=request.POST.get("username")).exists():
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": "These credentials do not match our records.",
                }
            )

        username = request.POST.get("username", None)
        password = request.POST.get("password", None)
        if username and password:
            user = authenticate(username=username.lower(), password=password)
            if user is None:
                return self.render_json_response(
                    {
                        "status": "Failed",
                        "message": "These credentials do not match our records.",
                    }
                )
        else:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": "These credentials do not match our records.",
                }
            )
        user = authenticate(username=username.lower(), password=password)
        if user.role=='staff' and user.current_session_token:
            if user.last_activity_time < timezone.now()-timedelta(minutes=15):
                if user and user.role=='staff':
                    user.current_session_token = request.session.session_key
                    user.save()
                if user.role == "player":
                    return self.render_json_response({"status": "Failed", "message": "Permission denied."})
                login(request, user)
                return self.render_json_response({"status": "success", "message": "Success."})
            else:    
                return self.render_json_response({"status": "Failed", "message": "You are already logged in on another device"}) 
        if user and user.role=='staff':
            user.current_session_token = request.session.session_key
            user.save()
        if user.role == "player":
            return self.render_json_response({"status": "Failed", "message": "Permission denied. "})
        login(request, user)
        return self.render_json_response({"status": "success", "message": "Success."})


class UpdatePlayer(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("agent",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        user_name = request.POST.get("username", "")
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")
        first_name = request.POST.get("first_name","")
        last_name = request.POST.get("last_name","")
        email = request.POST.get("email", "")  
        # country_code = request.POST.get("country_code", "")
        # phone_number = request.POST.get("phone_number","")
        # pattern = re.compile("[A-Za-z0-9]*$")
        # address = request.POST.get("address","")
        # state = request.POST.get("state","")
        # city = request.POST.get("city","")
        # zipcode = request.POST.get("zip_code","")       
        # profile_pic=request.FILES.get("profile_pic","")                      
        player = Player.objects.get(username__iexact=user_name)

        # if phone_number!=player.phone_number and  Users.objects.filter(phone_number=phone_number).exists():
        #     return self.render_json_object_response(
        #         {"status": "Failed", "message": "phone number already exists"}
        #     )

        # if not pattern.fullmatch(user_name):
        #     return self.render_json_response(
        #         {"status": "Failed", "message": "Username must be Alphanumeric"}
        #     )

        # if len(user_name) < 4:
        #     return self.render_json_response(
        #         {
        #             "status": "Failed",
        #             "message": _("The username has to be at least 4 characters"),
        #         },status=status.HTTP_400_BAD_REQUEST
        #     )

        if password and len(password) < 8:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("The password has to be at least 8 characters"),
                },status=status.HTTP_400_BAD_REQUEST
            )

        if password and (password != confirm_password):
                return self.render_json_response(
                    {
                        "status": "Failed",
                        "message": _("Confirm password does not match password."),
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        email_pattern = r'^[\w\.-]+@[a-zA-Z\d\.-]+\.[a-zA-Z]{2,}$'
        if player.email!=email and Users.objects.filter(email=email).exists():
            return self.render_json_response({
                "status": "Failed", 
                "message": _("email already exists")
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        elif not re.match(email_pattern, email):
            return self.render_json_response({
                "status": "Failed", 
                "message": _("Invalid email")
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # if((player.phone_number!= phone_number) or (player.country_code!= country_code)):
        #     if Users.objects.filter(phone_number=phone_number,country_code=country_code).exists():
        #             return self.render_json_response({
        #             "status": "Failed", 
        #             "message": _("contact details already exists")
        #             },
        #             status=status.HTTP_400_BAD_REQUEST
        #         )    

        # if (country_code.isdigit()!=True):
        #         return self.render_json_response(
        #             {
        #                 "status": "Failed",
        #                 "message": _("enter a valid country code"),
        #             },
        #             status=status.HTTP_400_BAD_REQUEST
        #         )
        try: 
            player = Player.objects.get(username__iexact=user_name)
            if not player.casino_account_id:
                player.casino_account_id = create_casino_account_id()
            if password!="":
             player.password = make_password(password)
            player.role = "player"
            player.first_name = first_name
            player.last_name = last_name
            # player.zip_code = int(zipcode)

            # if profile_pic:     
            #     filename_format = profile_pic.name.split(".")
            #     name, format = filename_format[-2], filename_format[-1]
            #     filename = f"{name}{uuid.uuid4()}.{format}"
            #     profile_thumbnail = Image.open(profile_pic)
            #     profile_thumbnail.thumbnail((500, 400))
            #     profile_thumbnail_io = BytesIO()
            #     format = 'JPEG' if format.lower() == 'jpg' else format.upper()
            #     profile_thumbnail.save(profile_thumbnail_io, format=format, filename=filename)
            #     page_thumbnail_inmemory = InMemoryUploadedFile(profile_thumbnail_io,
            #                                                      'FileField',
            #                                                      filename,
            #                                                      format,
            #                                                      sys.getsizeof(profile_thumbnail_io), None)
            #     profile_pic.name = filename
                # player.profile_pic_thumbnail = page_thumbnail_inmemory
                # player.profile_pic = profile_pic
            # player.state = state
            # player.city = city
            # player.complete_address = address
            player.email = email
            # player.country_code = country_code
            player.is_staff = False
            player.is_superuser = False
            player.is_active = True
            player.save()

            return self.render_json_response({"status": "Success", "message": _("Player has edited successfully.")})
        except Exception as e:
            return self.render_json_response({"status": "Error", "message": _("Some internal error.")})

class LoginView(TemplateView):
    template_name = "login.html"
    allowed_roles = ("superadmin", "admin", "dealer", "agent", "manager","staff")

    def post(self, request, *args, **kwargs):
        print("login this")
        username = request.POST.get("username")
        password = request.POST.get("password")
        if username and password:
            user = authenticate(username=username, password=password)
            if user is not None:
                if user.is_active and user.role in self.allowed_roles:
                    login(request, user)
                    return HttpResponseRedirect(reverse_lazy("admin-panel:home"))
                else:
                    return HttpResponseRedirect(settings.LOGIN_URL)

        return HttpResponseRedirect(settings.LOGIN_URL)

    def dispatch(self, *args, **kwargs):
        try:
            if self.request.user.is_authenticated:
                return HttpResponseRedirect(reverse_lazy("admin-panel:home"))
        except Exception as e:
            print(e)
        return super().dispatch(*args, **kwargs)


class LogoutView(View):
    def get(self, request):
        if request.user.is_authenticated:
            request.user.current_session_token = None  
            request.user.save()
            Queue.objects.filter(pick_by = request.user).update(pick_by = None)
        logout(request)
        return HttpResponseRedirect(reverse_lazy("admin-panel:login"))


class HomeView(CheckRolesMixin, TemplateView):
    allowed_roles = ("admin", "dealer", "superadmin", "agent",'staff')
    template_name = "home.html"

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

class AgentsView(CheckRolesMixin, FormMixin, ListView):
    model = Agent
    paginate_by = 20
    template_name = "admin/agent/agents.html"
    form_class = AgentModelForm
    allowed_roles = ["admin", "dealer", "superadmin"]
    context_object_name = "agents"
    date_format = "%d/%m/%Y"
    queryset = Agent.objects.all()

    ORDER_MAPPING = {
        "1": "-last_login",
        "2": "balance",
        "3": "-balance",
        "4": "locked",
        "5": "-locked",
        "6": "created",
        "7": "-created",
    }

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def time_zone_converter(self,date_time_obj,Inverse_Time_flag):

        try:
            current_timezone = self.request.session['time_zone']
        except:
            current_timezone='en'
        if(current_timezone=="en"):
            return date_time_obj
        elif(current_timezone=='ru'):
            current_timezone='Europe/Moscow'
        elif(current_timezone=='tr'):
            current_timezone='Turkey'    
        else:
            current_timezone='Europe/Berlin'
        timee=date_time_obj.replace(tzinfo=None)
        if(Inverse_Time_flag):
            new_tz=pytz.timezone(current_timezone)
            old_tz=pytz.timezone("EST")
        else:
            old_tz=pytz.timezone(current_timezone)
            new_tz=pytz.timezone("EST")
        new_timezone_timestamp = old_tz.localize(timee).astimezone(new_tz)

        return new_timezone_timestamp



    def get_queryset(self):
        dealers = self.request.GET.get("dealers")
        user_name = self.request.GET.get("user_name", "").split(",")
        order = self.request.GET.get("order", "7")

        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
            self.queryset = self.queryset.filter(created__gte=start_date)
        # else:
            # by default show results from first day of month
            # current_date = timezone.now()
            # first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
            # self.queryset = self.queryset.filter(created__gte=first_day_of_month)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
            self.queryset = self.queryset.filter(created__date__lte=end_date)

        if dealers:
            self.queryset = self.queryset.filter(dealer_id__in=dealers.split(","))
        if user_name and all([value.isdigit() for value in user_name]):
            self.queryset = self.queryset.filter(id__in=user_name)

        if self.request.user.role == "dealer":
            self.queryset = self.queryset.filter(dealer=self.request.user)

        if order and order in self.ORDER_MAPPING.keys():
            self.queryset = self.queryset.order_by(self.ORDER_MAPPING[order])
        else:
            self.queryset = self.queryset.order_by("last_login")

        return self.queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)


        first_day_of_month_UTC = timezone.now()
        first_day_of_month=self.time_zone_converter(first_day_of_month_UTC,True).replace(day=1,hour=0,minute=0)
        current_time=timezone.now()
        current_time=self.time_zone_converter(current_time,True)

        context["username"] = self.request.GET.get("user_name", "")
        context["order"] = self.request.GET.get("order", "7")
        context["dealers"] = Dealer.objects.all().order_by("username")
        context["to"] = self.request.GET.get("to", current_time.strftime(self.date_format))
        context["from"] = self.request.GET.get("from", first_day_of_month.strftime(self.date_format))

        dealers = self.request.GET.get("dealers", "")

        if self.request.user.role == "dealer":
            context["dealers"] = Dealer.objects.none()
        if dealers:
            context["selected_dealers"] = Dealer.objects.filter(id__in=dealers.split(","))
            context["dealers"] = context["dealers"].exclude(id__in=dealers.split(","))
        return context


class CreateAgent(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("dealer",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def post_ajax(self, request, *args, **kwargs):
        user_name = request.POST.get("username", "").lower()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if Users.objects.filter(username__iexact=user_name).exists():
            return self.render_json_response({"status": "Failed", "message": _("Username already exists")})

        pattern = re.compile("[A-Za-z0-9]*$")
        if not pattern.fullmatch(user_name):
            return self.render_json_response(
                {"status": "Failed", "message": _("Username must be Alphanumeric")}
            )

        if len(user_name) < 4:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("The username has to be at least 4 characters"),
                }
            )

        if len(password) < 5:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("The password has to be at least 5 characters"),
                }
            )

        if password != confirm_password:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("Confirm password does not match password."),
                }
            )

        agent = Agent()
        agent.username = user_name
        agent.password = make_password(password)
        agent.dealer = request.user
        agent.admin = request.user.admin
        agent.role = "agent"
        agent.is_staff = False
        agent.is_superuser = False
        agent.is_active = True
        agent.save()


        CronInfo.objects.create(
            agent=agent,
        )
        return self.render_json_response({"status": "Success", "message": "Agent created"})


class UpdateAgent(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "superadmin", "dealer")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def post_ajax(self, request, *args, **kwargs):
        user_name = request.POST.get("username", "")
        password = request.POST.get("password", "")

        pattern = re.compile("[A-Za-z0-9]*$")
        if not pattern.fullmatch(user_name):
            return self.render_json_response(
                {"status": "Failed", "message": "Username must be Alphanumeric"}
            )

        if len(user_name) < 4:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("The username has to be at least 4 characters"),
                }
            )

        if len(password) < 5:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("The password has to be at least 5 characters"),
                }
            )

        dealer = Agent.objects.get(username__iexact=user_name)
        dealer.password = make_password(password)
        dealer.role = "agent"
        dealer.is_staff = False
        dealer.is_superuser = False
        dealer.is_active = True
        dealer.save()

        return self.render_json_response({"status": "Success", "message": _("Agent has been edited.")})


class DealerView(CheckRolesMixin, FormMixin, ListView):
    model = Dealer
    paginate_by = 20
    template_name = "admin/dealer/dealers.html"
    form_class = DealerModelForm
    allowed_roles = ("admin", "superadmin")
    context_object_name = "dealers"
    date_format = "%d/%m/%Y"
    queryset = Dealer.objects.all()

    ORDER_MAPPING = {
        "1": "-last_login",
        "2": "balance",
        "3": "-balance",
        "4": "locked",
        "5": "-locked",
        "6": "created",
        "7": "-created",
    }

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def time_zone_converter(self,date_time_obj,Inverse_Time_flag):


        try:
            current_timezone = self.request.session['time_zone']
        except:
            current_timezone='en'
        if(current_timezone=="en"):
            return date_time_obj
        elif(current_timezone=='ru'):
            current_timezone='Europe/Moscow'
        elif(current_timezone=='tr'):
            current_timezone='Turkey'    
        else:
            current_timezone='Europe/Berlin'
        timee=date_time_obj.replace(tzinfo=None)
        if(Inverse_Time_flag):
            new_tz=pytz.timezone(current_timezone)
            old_tz=pytz.timezone("EST")
        else:
            old_tz=pytz.timezone(current_timezone)
            new_tz=pytz.timezone("EST")
        new_timezone_timestamp = old_tz.localize(timee).astimezone(new_tz)
        return new_timezone_timestamp

    def get_queryset(self):
        user_name = self.request.GET.get("user_name")
        order = self.request.GET.get("order", "7")
        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format)
            self.queryset = self.queryset.filter(created__gte=start_date)
        # else:
            # by default show results from first day of month
            # current_date = timezone.now()
            # first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
            # self.queryset = self.queryset.filter(created__gte=first_day_of_month)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format)
            self.queryset = self.queryset.filter(created__date__lte=end_date)

        if user_name:
            self.queryset = self.queryset.filter(username__icontains=user_name.lower())
        if order and order in self.ORDER_MAPPING.keys():
            self.queryset = self.queryset.order_by(self.ORDER_MAPPING[order])
        else:
            self.queryset = self.queryset.order_by("last_login")

        return self.queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_date = timezone.now()
        first_day_of_month_UTC = current_date
        first_day_of_month=self.time_zone_converter(first_day_of_month_UTC,True)
        first_day_of_month=first_day_of_month.replace(day=1, hour=0, minute=0)
        current_time=timezone.now()
        current_time=self.time_zone_converter(current_time,True)

        context["to"] = self.request.GET.get("to", current_time.strftime(self.date_format))
        context["from"] = self.request.GET.get("from", first_day_of_month.strftime(self.date_format))

        context["order"] = self.request.GET.get("order", "7")
        context["CURRENCY_CHOICES"] = [currency[1] for currency in CURRENCY_CHOICES]
        context["TIMEZONES"] = [timezone[1] for timezone in TIMEZONES]

        if self.request.user.role in ("admin", "superadmin", "dealer"):
            context["username"] = self.request.GET.get("user_name", "")

        return context


class CreateDealer(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        user_name = request.POST.get("username", "").lower()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if Dealer.objects.filter(username__iexact=user_name).exists():
            return self.render_json_response({"status": "Failed", "message": "Username already exists"})

        pattern = re.compile("[A-Za-z0-9]*$")
        if not pattern.fullmatch(user_name):
            return self.render_json_response(
                {"status": "Failed", "message": "Username must be Alphanumeric"}
            )

        if len(user_name) < 4:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("The username has to be at least 4 characters"),
                }
            )

        if len(password) < 5:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("The password has to be at least 5 characters"),
                }
            )

        if password != confirm_password:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("Confirm password does not match password."),
                }
            )

        try:
            Users.objects.get(username__iexact=user_name)
            return self.render_json_response({"status": "Failed", "message": _("Username must be unique.")})
        except Users.DoesNotExist:
            dealer = Dealer()
            dealer.username = user_name
            dealer.password = make_password(password)
            dealer.timezone = request.POST.get("timezone", "EST")
            dealer.currency = request.POST.get("currency", "USD")
            dealer.role = "dealer"
            dealer.admin = request.user
            dealer.is_staff = False
            dealer.is_superuser = False
            dealer.is_active = True
            dealer.save()



            return self.render_json_response({"status": "Success", "message": _("Master Agent has been created.")})


class UpdateDealer(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        user_name = request.POST.get("username", "")
        password = request.POST.get("password", "")

        pattern = re.compile("[A-Za-z0-9]*$")
        if not pattern.fullmatch(user_name):
            return self.render_json_response(
                {"status": "Failed", "message": "Username must be Alphanumeric"}
            )

        if len(user_name) < 4:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("The username has to be at least 4 characters"),
                }
            )

        if len(password) < 5:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("The password has to be at least 5 characters"),
                }
            )

        dealer = Dealer.objects.get(username__iexact=user_name)
        dealer.password = make_password(password)
        dealer.timezone = request.POST.get("timezone")
        # dealer.currency = request.POST.get("currency")
        dealer.role = "dealer"
        dealer.is_staff = False
        dealer.is_superuser = False
        dealer.is_active = True
        dealer.save()

        return self.render_json_response({"status": "Success", "message": _("Master Agent has been edited.")})


class CreditAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "dealer", "superadmin", "agent")
    input_fields = ("value", "player_id", "type")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        response_data = {}
        if request.user.role == "agent":
            if (
                all(key in request.POST.keys() for key in CreditAjaxView.input_fields)
                and Player.objects.filter(id=request.POST["player_id"])
                and request.POST["value"].isnumeric()
            ):  

                admin = Admin.objects.filter(id=request.user.admin.id).first()
                if(request.POST["type"] == "decrease"):
                    player_id = request.POST["player_id"]
                    try:
                        latest_settled_bet_time = Transactions.objects.filter(user__id = id, journal_entry='debit').exclude(betslip__isnull=True).latest('modified').modified
                        current_time = timezone.now()
                        time_differnce = current_time - latest_settled_bet_time
                    except:
                        current_time = timezone.now()
                        time_differnce = timedelta( minutes = 50 )

                    resettlement_time = timedelta( minutes = 5 )
                    if(time_differnce < resettlement_time):
                        waiting_time = resettlement_time - time_differnce
                        waiting_time = timedelta(seconds=math.ceil(waiting_time.total_seconds()))
                        waiting_time=datetime.strftime(datetime.strptime(str(waiting_time), "%H:%M:%S"), "%M:%S")
                        minutes,seconds = waiting_time.split(":")
                        waiting_time = minutes + " M" + " : " + seconds + " S"
                        msg = _("You can withdraw after : ") + waiting_time
                        print(msg)
                        return self.render_json_response(
                            {"status": "Wait", "message": msg}
                        )

                player = Player.objects.filter(id=request.POST["player_id"]).first()
                deposit_count_np = NowPaymentsTransactions.objects.filter(user=player,transaction_type='DEPOSIT',payment_status='finished',created__date=date.today()).count()

                deposit_bonus_given_count = Transactions.objects.filter(user=player, journal_entry='deposit', created__date=date.today()).count() + deposit_count_np + 1

                # increase
                if request.POST["type"] == "increase":

                    # bonus_percentage_obj = BonusPercentage.objects.filter(bonus_type="deposit_bonus").first()
                    # if bonus_percentage_obj.deposit_bonus_per_day_limit < deposit_bonus_given_count + 1:
                    #     return self.render_json_response(
                    #         {"status": "Failed", "message": "Deposit bonus given limit exceeded."}
                    #     )
                    if Decimal(request.POST["value"]) > request.user.balance:
                        return self.render_json_response(
                            {"status": "Failed", "message": "Insufficient Funds"}
                        )
                    delta = request.POST["value"]
                    journal_entry = "deposit"
                    delta = Decimal(delta)
                    Agent.objects.filter(id=request.user.id).update(balance=F("balance") - delta)
                    description = "Deposit by Agent to player"
                # decrease
                elif request.POST["type"] == "decrease" and Player.objects.filter(
                    id=request.POST["player_id"], balance__gte=request.POST["value"]
                ):
                    player = Player.objects.filter(id=request.POST["player_id"]).first()
                    if(player.balance < Decimal(request.POST["value"])):
                         return self.render_json_response({"status": "Failed", "message": f"you cannot withdraw max amount you can withdraw {player.balance}"})

                    delta = "-" + request.POST["value"]
                    journal_entry = "withdraw"
                    description = "Withdraw by Agent from player"
                    Agent.objects.filter(id=request.user.id).update(balance=F("balance") - delta)
                else:
                    return self.render_json_response("Wrong data", status=400)
                player = Player.objects.filter(id=request.POST["player_id"]).first()
                player.balance += Decimal(delta) 
                bonus_to_be_given=0
                admin = Admin.objects.filter(id=request.user.admin.id).first()
                bonus_type = None

                player.save()

                send_player_balance_update_notification(player)

                # player = Player.objects.get(id=request.POST["player_id"])
                Transactions.objects.update_or_create(
                    user=player,
                    journal_entry=journal_entry,
                    amount=delta,
                    status="charged",
                    merchant=request.user,
                    previous_balance=player.balance - int(delta) - bonus_to_be_given,
                    new_balance=player.balance,
                    description=description,
                    reference=generate_reference(player),
                    bonus_type= bonus_type or None ,
                    bonus_amount=bonus_to_be_given
                )

            player = Player.objects.get(id=request.POST["player_id"])
            admin = Admin.objects.filter(id=request.user.admin.id).first()

            # try:
            #     bonus_percentage_obj = BonusPercentage.objects.filter(bonus_type="deposit_bonus").first()
            #     perc = bonus_percentage_obj.percentage if bonus_percentage_obj else 0
            #     bonus = (Decimal(delta)/100)* Decimal(perc)
            # except Exception as e:
            #     exception=e
            # if(admin.is_deposit_bonus_enabled):
            #         if(bonus_percentage_obj.deposit_bonus_limit):
            #             previous_balance = player.balance                    
            #             if(request.POST["type"] == "increase" and not player.is_special_agent) and bonus <= bonus_percentage_obj.deposit_bonus_limit and bonus_percentage_obj.deposit_bonus_per_day_limit >= deposit_bonus_given_count:
            #                 previous_balance = player.balance
            #                 player.bonus_balance += bonus
            #                 player.balance += bonus
            #                 bonus_type="deposit_bonus"
            #                 bonus_to_be_given=bonus
            #             elif(request.POST["type"] == "increase" and not player.is_special_agent) and bonus > bonus_percentage_obj.deposit_bonus_limit and bonus_percentage_obj.deposit_bonus_per_day_limit >= deposit_bonus_given_count:
            #                 previous_balance = player.balance
            #                 player.bonus_balance += bonus_percentage_obj.deposit_bonus_limit
            #                 player.balance += bonus_percentage_obj.deposit_bonus_limit
            #                 bonus_to_be_given = bonus_percentage_obj.deposit_bonus_limit
            #                 bonus_type="deposit_bonus"

            #             if bonus_percentage_obj.deposit_bonus_per_day_limit >= deposit_bonus_given_count and request.POST["type"] == "increase":

            #                 calculated_bonus = (Decimal(delta)/100)* Decimal(perc)
            #                 if calculated_bonus > bonus_percentage_obj.deposit_bonus_limit:
            #                     bonus = bonus_percentage_obj.deposit_bonus_limit

            #                 Transactions.objects.update_or_create(
            #                         user=player,
            #                         journal_entry="bonus",
            #                         amount=bonus,
            #                         status="charged",
            #                         merchant=request.user,
            #                         previous_balance=previous_balance,
            #                         new_balance=player.balance,
            #                         description=f"deposit bonus of {bonus_to_be_given}",
            #                         reference=generate_reference(player),
            #                         bonus_type="deposit_bonus",
            #                         bonus_amount=bonus_to_be_given
            #                 )
            #             player.save()                   
            #             send_player_balance_update_notification(player)                   

            deposit_count_np_wl = NowPaymentsTransactions.objects.filter(user=player,transaction_type='DEPOSIT',payment_status='finished').count()
            deposit_count = Transactions.objects.filter(user=player, journal_entry='deposit').count() + deposit_count_np_wl
            promo_obj = PromoCodes.objects.filter(promo_code=player.applied_promo_code, is_expired=False).first() if player.applied_promo_code else None
            if admin.is_welcome_bonus_enabled and promo_obj and deposit_count==1 and request.POST["type"] == "increase" and promo_obj.bonus_distribution_method == PromoCodes.BonusDistributionMethod.deposit and promo_obj.bonus_percentage>0:
                try:
                    welcome_bonus = round(Decimal(float(delta) * float(promo_obj.bonus_percentage / 100)), 2)
                    bonus_to_be_given = min(welcome_bonus, promo_obj.max_bonus_limit)
                    previous_bal = player.balance
                    player.bonus_balance = round(Decimal(float(player.bonus_balance)+float(bonus_to_be_given)),2)

                    Transactions.objects.update_or_create(
                        user=player,
                        journal_entry="bonus",
                        amount=delta,
                        status="charged",
                        previous_balance=previous_bal,
                        new_balance=player.balance,
                        description=f"welcome bonus of {bonus_to_be_given}",
                        reference=generate_reference(player),
                        bonus_type="welcome_bonus",
                        bonus_amount=bonus_to_be_given
                    )
                    player.save()
                    send_player_balance_update_notification(player)
                except Exception as e:
                    print(e)

            player = Player.objects.get(id=request.POST["player_id"])
            if(player.affiliated_by and request.POST["type"] == "increase"):
                affiliate = player.affiliated_by
                aff_deposit_count = Transactions.objects.filter(user=affiliate,journal_entry='bonus',bonus_type="affiliate_bonus").count()
                if affiliate.is_lifetime_affiliate or affiliate.affliate_expire_date>datetime.now(timezone.utc):
                    if affiliate.is_bonus_on_all_deposits or aff_deposit_count<affiliate.no_of_deposit_counts:
                        try:
                            if affiliate:
                                commision_percenatge = affiliate.affiliation_percentage
                                referal_bonus_balance = round(Decimal(float( affiliate.bonus_balance) + float(delta) * float(commision_percenatge / 100)), 2)
                                referal_bonus = round(Decimal( float(delta) * float(commision_percenatge/ 100)), 2)
                                previous_bal = affiliate.balance
                                if affiliate.is_redeemable_amount:
                                    affiliate.balance += referal_bonus
                                elif affiliate.is_non_redeemable_amount:
                                    affiliate.bonus_balance = referal_bonus_balance
                                    # affiliate.balance += referal_bonus
                                else:
                                    affiliate.bonus_balance = referal_bonus_balance
                                    # affiliate.balance += referal_bonus
                                txn_amount = referal_bonus
                                bonus_to_be_given = referal_bonus
                                Transactions.objects.update_or_create(
                                        user=affiliate,
                                        journal_entry="bonus",
                                        amount=float(delta),
                                        status="charged",
                                        merchant=request.user,
                                        previous_balance=previous_bal,
                                        new_balance=affiliate.balance,
                                        description=f"affiliate bonus by {player} on deposit of {delta}",
                                        reference=generate_reference(player),
                                        bonus_type="affiliate_bonus",
                                        bonus_amount=bonus_to_be_given
                        )
                                affiliate.save()
                                send_player_balance_update_notification(affiliate)

                        except Exception as e:
                            print(e)

            # Check if referral bonus enabled and give them bonus on first deposite
            player = Player.objects.get(id=request.POST["player_id"])
            deposit_count = Transactions.objects.filter(user=player, journal_entry='deposit').count()

            if((admin.is_welcome_bonus_enabled is False) and (admin.is_referral_bonus_enabled is True) and (deposit_count==1)):
                referral_bonus_obj = BonusPercentage.objects.filter(bonus_type="referral_bonus").first()
                try:
                    if referral_bonus_obj and referral_bonus_obj.percentage > 0:
                        referred_by_user = player.referred_by
                        referal_bonus_balance = round(Decimal(float(referred_by_user.bonus_balance) + float(delta) * float(referral_bonus_obj.percentage / 100)), 2)
                        referal_bonus = round(Decimal( float(delta) * float(referral_bonus_obj.percentage / 100)), 2)
                        previous_bal = player.balance
                        if(referal_bonus <= referral_bonus_obj.referral_bonus_limit):
                            referred_by_user.bonus_balance = referal_bonus_balance
                            # referred_by_user.balance += referal_bonus
                            bonus_to_be_given = referal_bonus
                        else:
                            referal_bonus_balance = round(Decimal(float(referred_by_user.bonus_balance) + float(referral_bonus_obj.referral_bonus_limit)), 2)
                            # referred_by_user.balance = round(Decimal(float(referred_by_user.balance) + float(referral_bonus_obj.referral_bonus_limit)), 2)
                            bonus_to_be_given = referral_bonus_obj.referral_bonus_limit
                        Transactions.objects.update_or_create(
                                   user=referred_by_user,
                                   journal_entry="deposit",
                                   amount=delta,
                                   status="charged",
                                   merchant=request.user,
                                   previous_balance=previous_bal,
                                   new_balance=referred_by_user.balance,
                                   description=description,
                                   reference=generate_reference(player),
                                   bonus_type="referral_bonus",
                                   bonus_amount=bonus_to_be_given
                )
                        referred_by_user.save()
                        send_player_balance_update_notification(referred_by_user)

                except Exception as e:
                    print(e)
            response_data["agent_bal"] = player.agent.balance
            response_data["player_bal"] = player.balance
            response_data["player_bonus_bal"] = player.bonus_balance


        # return self.render_json_response(Player.objects.get(id=request.POST["player_id"]).balance)
        return self.render_json_response(response_data)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class PaymentDelayView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "dealer", "superadmin", "agent")
    input_fields = ("player_id")

    def post_ajax(self, request, *args, **kwargs):
        response_data = {}
        id=request.POST.get("player_id")
        try:
            latest_settled_bet_time = Transactions.objects.filter(user__id = id, journal_entry='debit').exclude(betslip__isnull=True).latest('modified').modified
            current_time = timezone.now()
            time_differnce = current_time - latest_settled_bet_time

        except:
            current_time = timezone.now()
            time_differnce = timedelta( minutes = 50 )

        resettlement_time = timedelta( minutes = 5 )
        if(time_differnce > resettlement_time):
            response_data['status'] = "na"

            response_data['message'] = 'na'
        else:
            response_data['status'] = "wait"
            waiting_time = resettlement_time - time_differnce
            waiting_time = timedelta(seconds=math.ceil(waiting_time.total_seconds()))
            waiting_time=datetime.strftime(datetime.strptime(str(waiting_time), "%H:%M:%S"), "%M:%S")
            minutes,seconds = waiting_time.split(":")
            waiting_time = minutes + " M" + " : " + seconds + " S"
            response_data['message'] = _("You can withdraw after : ") + waiting_time


        return self.render_json_response(response_data)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class AgentCreditAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("dealer",)
    input_fields = ("value", "agent_id", "type")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        response_data = {}
        if request.user.role == "dealer":
            if (
                all(key in request.POST.keys() for key in AgentCreditAjaxView.input_fields)
                and Agent.objects.filter(id=request.POST["agent_id"])
                and request.POST["value"].isnumeric()
            ):

                # increase
                if request.POST["type"] == "increase":
                    if Decimal(request.POST["value"]) > request.user.balance:
                        return self.render_json_response(
                            {"status": "Failed", "message": "Insufficient Funds"}
                        )

                    delta = request.POST["value"]
                    journal_entry = "deposit"
                    Dealer.objects.filter(id=request.user.id).update(balance=F("balance") - delta)
                    description = "Deposit by masteragent to agent"
                # decrease
                elif request.POST["type"] == "decrease" and Agent.objects.filter(
                    id=request.POST["agent_id"], balance__gte=request.POST["value"]
                ):
                    delta = "-" + request.POST["value"]
                    journal_entry = "withdraw"
                    Dealer.objects.filter(id=request.user.id).update(balance=F("balance") - delta)
                    description = "Withdraw by masteragent from agent"
                else:
                    return self.render_json_response("Wrong data", status=400)

                Agent.objects.filter(id=request.POST["agent_id"]).update(balance=F("balance") + delta)
                agent = Agent.objects.get(id=request.POST["agent_id"])
                response_data["agent_bal"] = agent.balance
                response_data["dealer_bal"] = agent.dealer.balance
                Transactions.objects.update_or_create(
                    user=agent,
                    journal_entry=journal_entry,
                    amount=delta,
                    status="charged",
                    merchant=request.user,
                    previous_balance=agent.balance - int(delta),
                    new_balance=agent.balance,
                    description=description,
                    reference=generate_reference(agent),
                )
            # return self.render_json_response(Agent.objects.get(id=request.POST["agent_id"]).balance)
            return self.render_json_response(response_data)
        return self.render_json_response([], status=400)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class AdminView(CheckRolesMixin, ListView):
    model = Admin
    paginate_by = 20
    template_name = "admin/admins.html"
    allowed_roles = ("admin", "superadmin")
    context_object_name = "admins"
    queryset = Admin.objects.all()

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_queryset(self):
        user_name = self.request.GET.get("user_name")
        self.queryset = self.queryset.order_by("-created")
        if user_name:
            self.queryset = self.queryset.filter(username__iexact=user_name)
        if self.queryset.count() == 0:
            messages.error(self.request, _("Admin Not Found!"))




        return self.queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.role in ("admin", "superadmin"):
            context["username"] = self.request.GET.get("user_name", "")
            return context


class DealerCreditAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "superadmin")
    input_fields = ("value", "dealer_id", "type")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        if request.user.role in ("admin", "superadmin"):
            if (
                all(key in request.POST.keys() for key in DealerCreditAjaxView.input_fields)
                and Dealer.objects.filter(id=request.POST["dealer_id"])
                and request.POST["value"].isnumeric()
            ):
                # decrease
                if request.POST["type"] == "decrease" and Dealer.objects.get(
                    id=request.POST["dealer_id"]
                ).balance >= int(request.POST["value"]):
                    delta = "-" + request.POST["value"]
                    journal_entry = "withdraw"
                    description = "Withdraw by admin from masteragent"
                # increase
                elif request.POST["type"] == "increase":
                    delta = request.POST["value"]
                    journal_entry = "deposit"
                    description = "Deposit by admin to masteragent"
                else:
                    return self.render_json_response("Wrong data", status=400)

                Dealer.objects.filter(id=request.POST["dealer_id"]).update(balance=F("balance") + delta)
                dealer = Dealer.objects.get(id=request.POST["dealer_id"])
                # previous_balance = "new_balance" - delta
                Transactions.objects.update_or_create(
                    user=dealer,
                    journal_entry=journal_entry,
                    amount=delta,
                    status="charged",
                    merchant=request.user,
                    previous_balance=dealer.balance - int(delta),
                    new_balance=dealer.balance,
                    description=description,
                    reference=generate_reference(dealer),
                )
            return self.render_json_response(Dealer.objects.get(id=request.POST["dealer_id"]).balance)
        return self.render_json_response([], status=400)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)



class CreateAdmin(CheckRolesMixin, CreateView):
    allowed_roles = ("superadmin", "admin")
    model = Admin
    form_class = AdminModelForm
    template_name = "admin/create-admin.html"
    success_url = reverse_lazy("admin-panel:admins")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def form_valid(self, form):
        """If the form is valid, save the associated model."""

        self.object = form.save()
        self.object.role = "admin"
        self.object.is_staff = False
        self.object.is_superuser = False
        self.object.is_active = True



        return super().form_valid(form)

    def get_form(self, form_class=None):
        """Return an instance of the form to be used in this view."""
        if form_class is None:
            form_class = self.get_form_class()
        form_data = self.get_form_kwargs()
        if self.request.method == "GET":
            if self.kwargs.get("pk") and Admin.objects.filter(id=self.kwargs["pk"]).exists():
                form_data["instance"] = Admin.objects.get(id=self.kwargs["pk"])
        return form_class(**form_data)



class TransactionListView(CheckRolesMixin, ListView):
    model = Transactions
    paginate_by = 20
    template_name = "transactions/transactions.html"
    allowed_roles = ("admin", "superadmin", "dealer", "agent")
    context_object_name = "transactions"
    queryset = Transactions.objects.order_by("-created").all()
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        queryset = super().get_queryset()
        filter_clauses = []
        if self.request.user.role != "superadmin" and self.request.user.role != "admin":
            filter_clauses.append(Q(user=self.request.user))
            filter_clauses.append(Q(merchant=self.request.user))
            filter_clauses.append(Q(merchant__dealer=self.request.user))
            queryset = queryset.filter(reduce(operator.or_, filter_clauses))

        if self.request.GET.get("username"):

            queryset = queryset.annotate(
                user_username_lower=Lower("user__username"),
                merchant_username_lower=Lower("merchant__username"),
            ).filter(
                Q(user_username_lower__icontains=self.request.GET.get("username").lower())
                | Q(merchant_username_lower__icontains=self.request.GET.get("username").lower())
            )
        if self.request.GET.get("dropdown"):
             queryset=queryset.filter(journal_entry=self.request.GET.get("dropdown"))

        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__gte=start_date)
        else:
            # by default show results from first day of month
            current_date = timezone.now()
            first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
            queryset = queryset.filter(created__gte=first_day_of_month)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__date__lte=end_date)

        return queryset

    def get_context_data(self, **kwargs):
        # by default show results from first day of month
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

        context = super().get_context_data(**kwargs)
        context["username"] = self.request.GET.get("username", "")

        context["from"] = self.request.GET.get("from", first_day_of_month)
        context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))
        context["dropdown"]=self.request.GET.get("dropdown", "")

        return context


def change_language(request):
    response = HttpResponseRedirect("/")
    if request.method == "POST":
        language = request.POST.get("language")
        if language:
            redirect_path = reverse("admin-panel:home")
            from django.utils import translation
            translation.activate(language)
            response = HttpResponseRedirect(redirect_path)
            response.set_cookie(settings.LANGUAGE_COOKIE_NAME, language)
    return response

def change_timezone(request):
    response = HttpResponseRedirect("/")
    if request.method == "POST":
        timezone = request.POST.get("language")
        if timezone and timezone!="TIMEZONE":
            redirect_path = reverse("admin-panel:home")
            request.session['time_zone']=timezone
            response = HttpResponseRedirect(redirect_path)
    return response


def change_timezone(request):
    response = HttpResponseRedirect("/")
    if request.method == "POST":
        timezone = request.POST.get("language")
        if timezone and timezone != "TIMEZONE":
            redirect_path = reverse("admin-panel:home")
            request.session["time_zone"] = timezone
            response = HttpResponseRedirect(redirect_path)
    return response


class SetTimezoneView(views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)

    def post_ajax(self, request, *args, **kwargs):
        time_zone = request.POST.get("timezone")
        client_timezone = request.POST.get("user_timezone")
        request.session["user_timezone"] = time_zone
        request.session["client_timezone"] = client_timezone
        response_data = {"status": "true", "message": "user timezone set successfully."}
        return self.render_json_response(response_data)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)



class ProfitView(CheckRolesMixin, TemplateView,views.JSONResponseMixin,views.AjaxResponseMixin,View):
    http_method_names = ["post","get","POST"]
    template_name = "profit/profit.html"
    allowed_roles = ("admin", "superadmin", "dealer", "agent")
    date_format = "%d/%m/%Y"

    # currency="USD"
    # result = COIN_PAYMENTS.rates()

    def post_ajax(self, request, *args, **kwargs):
        # currency_val = request.POST.get("currency_val", ""),
        # if currency_val:
        #     self.currency=currency_val[0]
        # request.session['currency']=currency_val[0]

        return self.render_json_response("")


    def get_total_out(self, sports_book_out_sum_records):
        sports_book_out_sum_value = 0

        return sports_book_out_sum_value


    def time_zone_converter(self, date_time_obj, Inverse_Time_flag):

        try:
            current_timezone = self.request.session.get("time_zone", "en")
        except Exception:
            current_timezone = "en"
        if current_timezone == "en":
            return date_time_obj
        elif current_timezone == "ru":
            current_timezone = "Europe/Moscow"
        elif current_timezone == "tr":
            current_timezone = "Turkey"
        else:
            current_timezone = "Europe/Berlin"
        timee = date_time_obj.replace(tzinfo=None)
        if Inverse_Time_flag:
            new_tz = pytz.timezone(current_timezone)
            old_tz = pytz.timezone("EST")
        else:
            old_tz = pytz.timezone(current_timezone)
            new_tz = pytz.timezone("EST")
        new_timezone_timestamp = old_tz.localize(timee).astimezone(new_tz)
        return new_timezone_timestamp

    def get_ajax(self, request, *args, **kwargs):

        # currency=request.session['currency']

        # user_currency = self.request.user.currency

        # result=self.result
        context=dict()

        context["sports_book_in_sum"] = round(Decimal(0), 2)
        context["sports_book_out_sum"] = round(Decimal(0), 2)
        context["sports_book_out_sum_cash_out"] = round(Decimal(0), 2)
        context["casino_in_sum"] = round(Decimal(0), 2)
        context["casino_out_sum"] = round(Decimal(0), 2)
        context["live_casino_in_sum"] = round(Decimal(0), 2)
        context["live_casino_out_sum"] = round(Decimal(0), 2)
        context["bonus"] = round(Decimal(0), 2)
        context["selected_agents"] = None
        # Default context values - Ends


        # if "result" in result and currency in result["result"]:
        #         response={
        #         "base_rate_btc": Decimal(result["result"][user_currency]["rate_btc"]),
        #         "exchange_rate": Decimal(result["result"][currency]["rate_btc"]),

        #     }

        # base_rate_btc=response["base_rate_btc"]
        # exchangerate=response["exchange_rate"]
        # mf=(base_rate_btc)/(exchangerate)
        filter_clauses = []
        filter_clauses_cashout = []

        filter_clauses_cashback = []

        current_date = timezone.now()
        first_day_of_month_UTC = current_date.replace(day=1, hour=0, minute=0, second=0)
        first_day_of_month = self.time_zone_converter(first_day_of_month_UTC, True).replace(
            day=1, hour=0, minute=0, second=0
        )
        current_time = self.time_zone_converter(timezone.now(), True).date()

        if self.request.user.role == "dealer":
            filter_clauses.append(Q(user__dealer=self.request.user))
            filter_clauses_cashout.append(Q(user__dealer=self.request.user))
            filter_clauses_cashback.append(Q(user__dealer=self.request.user))
        elif self.request.user.role == "agent":
            filter_clauses.append(Q(user__agent=self.request.user) | Q(user=self.request.user))
            filter_clauses_cashout.append(Q(user__agent=self.request.user) | Q(user=self.request.user))
            filter_clauses_cashback.append(Q(user__agent=self.request.user) | Q(user=self.request.user))

        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format)
            start_date = self.time_zone_converter(start_date, False).date()

            filter_clauses.append(Q(created__date__gte=start_date))

            filter_clauses_cashout.append(Q(created__date__gte=start_date))
            filter_clauses_cashback.append(Q(created__date__gte=start_date))

        else:
            start_date=first_day_of_month
            first_day_of_month_UTC = self.time_zone_converter(first_day_of_month, False).replace(tzinfo=None).date()

            filter_clauses.append(Q(created__date__gte=first_day_of_month_UTC))

            filter_clauses_cashout.append(Q(created__date__gte=first_day_of_month_UTC))
            filter_clauses_cashback.append(Q(created__date__gte=first_day_of_month_UTC))

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format)
            end_date = self.time_zone_converter(end_date, False).date()

            filter_clauses.append(Q(created__date__lte=end_date))
            filter_clauses_cashout.append(Q(created__date__lte=end_date))
            filter_clauses_cashback.append(Q(created__date__lte=end_date))
        else:
            end_date = timezone.now().replace(tzinfo=None).date()
            filter_clauses.append(Q(created__date__lte=end_date))
            filter_clauses_cashout.append(Q(created__date__lte=end_date))
            filter_clauses_cashback.append(Q(created__date__lte=end_date))

        if self.request.GET.getlist("dealers[]"):
            dealer_ids = self.request.GET.getlist("dealers[]")
            filter_clauses.append(Q(user__dealer__in=dealer_ids))
            filter_clauses_cashout.append(Q(user__dealer__in=dealer_ids))
            filter_clauses_cashback.append(Q(user__dealer__in=dealer_ids))
            # context["selected_dealers"] = Dealer.objects.filter(id__in=dealer_ids)
        if self.request.GET.get("agents[]"):
            agent_ids = self.request.GET.getlist("agents[]")
            filter_clauses.append(Q(user__agent__in=agent_ids) | Q(user__in=agent_ids))
            filter_clauses_cashout.append(Q(user__agent__in=agent_ids) | Q(user__in=agent_ids))
            filter_clauses_cashback.append(Q(user__agent__in=agent_ids) | Q(user__in=agent_ids))
            # context["selected_agents"] = Agent.objects.filter(id__in=agent_ids)

        if self.request.GET.get("username"):
            username = self.request.GET.get("username")
            filter_clauses.append(Q(user__username=username))
            filter_clauses_cashout.append(Q(user__username=username))
            filter_clauses_cashback.append(Q(user__username=username))

        # context["from"] = (first_day_of_month.strftime(self.date_format))
        # context["to"] =(current_time.strftime(self.date_format))

        context["username"] = self.request.GET.get("username", "")
        context["from"] = start_date.strftime(self.date_format)
        context["to"] = end_date.strftime(self.date_format)


        bonus_sum = (
            Transactions.objects.filter(
                reduce(operator.and_, filter_clauses_cashback),
                bonus_type__in=['welcome_bonus','deposit_bonus','affiliate_bonus', "bet_bonus"]
            )

                .aggregate(cashback_amount=Sum("bonus_amount"))
        )

        # Casino Profit Calculation - Starts

        casino_in_sum = (
            GSoftTransactions.objects.filter(reduce(operator.and_, filter_clauses))
            .filter(request_type=GSoftTransactions.RequestType.wager)
            .aggregate(in_sum=Sum("amount"))
        )

        casino_out_sum = (
            GSoftTransactions.objects.filter(reduce(operator.and_, filter_clauses))
            .filter(request_type__in=[GSoftTransactions.RequestType.result, GSoftTransactions.RequestType.rollback])
            .aggregate(out_sum=Sum("amount"))
        )

        context["bonus"]=round((bonus_sum["cashback_amount"] or 0),2)
        context["casino_in_sum"] = round(Decimal(casino_in_sum.get("in_sum") or 0), 2)
        context["casino_out_sum"] = round(Decimal(casino_out_sum.get("out_sum") or 0), 2)
        context["casino_book_profit"] = context["casino_in_sum"] - context["casino_out_sum"]
        # Casino Profit Calculation - Ends


        # Offmarket Profit Calculation - Starts
        offmarket_bonus = 0
        # NOTE: Commenting because Offmarket bonus is not added to users bonus balance
        # offmarket_bonus = OffMarketTransactions.objects.filter(
        #     reduce(operator.and_, filter_clauses_cashback),
        #     bonus__gt= 0
        # ).aggregate(
        #     bonus_amount=Sum("bonus")
        # ).get("bonus_amount")

        offmarket_in_sum = OffMarketTransactions.objects.filter(reduce(operator.and_, filter_clauses)).filter(
            transaction_type = OffMarketTransactions.TransactionStatus.success,
            journal_entry = "credit"
        ).aggregate(in_sum=Sum("amount"))

        offmarket_out_sum = OffMarketTransactions.objects.filter(reduce(operator.and_, filter_clauses)).filter(
            transaction_type = OffMarketTransactions.TransactionStatus.success,
            journal_entry__in = ["debit", "refund"]
        ).aggregate(out_sum=Sum("amount"))

        context["bonus"] = -round((context["bonus"] + (offmarket_bonus or 0)), 2)
        context["offmarket_in_sum"] = round(Decimal(offmarket_in_sum.get("in_sum") or 0), 2)
        context["offmarket_out_sum"] = round(Decimal(offmarket_out_sum.get("out_sum") or 0), 2)
        context["offmarket_profit"] = context["offmarket_in_sum"] - context["offmarket_out_sum"]
        # Offmarket Profit Calculation - Ends

        # Sports Book Out Sum Adjusted - Starts

        context["sports_book_out_sum"] = (
            context["sports_book_out_sum"]
            +context["sports_book_out_sum_cash_out"]
        )

            # Sports Book Out Sum Adjusted - Ends

            # Sports Book Profit - Starts

            # Sports Book Profit - Ends

        # Total In Sum - Starts
        context["all_in"] = (
            context["casino_in_sum"]
            + context["offmarket_in_sum"]
            # + context["live_casino_in_sum_eur"]
        )
        # Total In Sum - Ends

        # Total Out Sum - 
        context["all_out"] = (context["casino_out_sum"]
            + context["offmarket_out_sum"]
            # + context["live_casino_out_sum_eur"]
        )
        # Total Out Sum - Ends

        # Total Profit - Starts
        context["all_profit"] = (
            context["casino_book_profit"]
            + context["offmarket_profit"]
            # + context["live_casino_book_profit_eur"]
        )
        # Total Profit - Ends

        # Net Profit - Starts
        context["net_profit"] = (
            context["all_profit"]
            + context["bonus"]
        )
        # Net Profit - Ends

        return self.render_json_response(context)


class EnableDisableCasinoView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "superadmin", "dealer")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        dealer_id = request.POST.get("dealer_id")
        agent_id = request.POST.get("agent_id")
        casino_status = request.POST.get("casino_status")

        if dealer_id:
            dealer = Dealer.objects.get(pk=dealer_id)
            if casino_status == "true":
                dealer.is_casino_enabled = True
                message = _("Casino has been enabled successfully.")
            else:
                dealer.is_casino_enabled = False
                message = _("Casino has been disabled successfully.")

            dealer.save()
        else:
            agent = Agent.objects.get(pk=agent_id)
            if casino_status == "true":
                agent.is_casino_enabled = True
                message = _("Casino has been enabled successfully.")
            else:
                agent.is_casino_enabled = False
                message = _("Casino has been disabled successfully.")

            agent.save()

        return self.render_json_response({"status": "Success", "message": message})


class EnableDisableLiveCasinoView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "superadmin", "dealer")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        agent_id = request.POST.get("agent_id")
        live_casino_status = request.POST.get("casino_status")

        agent = Agent.objects.get(pk=agent_id)
        if live_casino_status == "true":
            agent.is_live_casino_enabled = True
            message = _("Live Casino has been enabled successfully.")
        else:
            agent.is_live_casino_enabled = False
            message = _("Live Casino has been disabled successfully.")
        agent.save()

        return self.render_json_response({"status": "Success", "message": message})

class CashbackPermissionView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "dealer", "agent")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        try:
            user_id = request.POST.get("user_id")
            cashback_status = request.POST.get("cashback_status")


            user = Users.objects.get(pk=user_id)

            if user.role == "dealer":
                agents = Agent.objects.filter(dealer=user)
                players = Player.objects.filter(dealer=user)

                if cashback_status == "true":
                    for agent in agents:
                        cron_obj = CronInfo()
                        cron_obj.agent = agent
                        cron_obj.cron_name = "cashback_cron"
                        cron_obj.save()
                    user.cashback_status = True
                    agents.update(cashback_status = True)
                    players.update(cashback_status = True)

                    user.save()
                    message = _("Cashback has been enabled successfully.")
                else:
                    CronInfo.objects.filter(
                        agent__in=agents,
                        cron_name="cashback_cron", is_deleted=False
                    ).delete()

                    user.cashback_status = False
                    agents.update(cashback_status = False)
                    players.update(cashback_status = False)

                    user.cashback_percentage = CASHBACK_PERCENTAGE
                    user.cashback_time_limit = CASHBACK_TIME_LIMIT
                    user.save()

                    message = _("Cashback has been disabled successfully.")

            elif user.role == "agent":
                players = Player.objects.filter(agent=user)

                if cashback_status == "true":
                    cron_obj = CronInfo()
                    cron_obj.agent = user
                    cron_obj.cron_name = "cashback_cron"
                    cron_obj.save()
                    user.cashback_status = True
                    players.update(cashback_status = True)

                    user.save()
                    message = _("Cashback has been enabled successfully.")
                else:
                    CronInfo.objects.filter(
                        agent=user,
                        cron_name="cashback_cron", is_deleted=False
                    ).delete()

                    user.cashback_status = False
                    players.update(cashback_status = False)

                    user.save()
                    message = _("Cashback has been disabled successfully.")

            elif user.role == "player":

                if cashback_status == "true":
                    user.cashback_status = True
                    user.save()
                    message = _("Cashback has been enabled successfully.")
                else:
                    user.cashback_status = False

                    user.save()
                    message = _("Cashback has been disabled successfully.")

            return self.render_json_response({"status": "success", "message": message})

        except:
            return self.render_json_response({"status": "error", "message": "Something went wrong"}, status=500)


class JackpotPermissionView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("superadmin",)
    http_method_names = ["post"]

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        admin_id = self.request.POST.get("adminID", None)
        is_jackpot_enabled = self.request.POST.get("isJackpotEnabled", None)

        is_jackpot_enabled = True if is_jackpot_enabled == "true" else False

        if Admin.objects.filter(id=admin_id).exists():
            admin = Admin.objects.get(id=admin_id)

            admin.is_jackpot_enabled = is_jackpot_enabled

            if is_jackpot_enabled is True:
                message = "Jackpot has been Enabled Successfully"

            else:
                admin.min_amount_required_for_jackpot = MIN_AMOUNT_REQUIRED_FOR_JACKPOT
                admin.jackpot_amount = JACKPOT_AMOUNT
                admin.jackpot_time_limit = JACKPOT_TIME_LIMIT

                message = "Jackpot has been Disabled Successfully"

            admin.save()

            status = "success"
            status_code = 201

        else:
            status = "error"
            message = "Something went Wrong"
            status_code = 500

        return self.render_json_response(
            {
                "status": status,
                "message": _(message)
            },
            status=status_code
        )


class EnableDisableCashbackView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "superadmin", "dealer")

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        dealer_id = request.POST.get("dealer_id")
        agent_id = request.POST.get("agent_id")
        cashback_status = request.POST.get("cashback_status")

        if dealer_id:
            dealer = Dealer.objects.get(pk=dealer_id)
            agents = Agent.objects.filter(dealer=dealer)
            if cashback_status == "true":
                dealer.cashback_status = True
                for agent in agents:
                    agent.cashback_status = True
                    agent.save()
                message = _("Cashback has been enabled successfully.")
            else:
                dealer.cashback_status = False
                for agent in agents:
                    agent.cashback_status = False
                    agent.save()
                message = _("Cashback has been disabled successfully.")
            dealer.save()
        else:
            agent = Agent.objects.get(pk=agent_id)
            players = Player.objects.filter(agent=agent)
            if cashback_status == "true":
                agent.cashback_status = True
                for player in players:
                    player.cashback_status = True
                    player.save()
                message = _("Cashback has been enabled successfully.")
            else:
                agent.cashback_status = False
                for player in players:
                    player.cashback_status = False
                    player.save()
                message = _("Cashback has been disabled successfully.")

            agent.save()

        return self.render_json_response({"status": "Success", "message": message})


class ActivateDeactivatePlayerView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "superadmin", "dealer", "agent","staff")

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        player_id = request.POST.get("player_id")
        player = Player.objects.get(pk=player_id)
        message = _("Invalid Request.")
        post_data = request.POST
        if "player_status" in post_data:
            player_status = request.POST.get("player_status")
            if player_status == "true":
                player.is_active = True
                message = _("Player has been activated successfully.")
            else:
                player.is_active = False
                message = _("Player has been deactivated successfully.")
        elif "cancel_status" in post_data:
            cancel_status = request.POST.get("cancel_status")
            responsible_gambling = ResponsibleGambling.objects.get_or_create(user=player)[0]
            if cancel_status == "true":
                responsible_gambling.is_account_cancelled = True
                message = _("Player account has been closed/cancelled successfully.")
            else:
                responsible_gambling.is_account_cancelled = False
                message = _("Player has been reopen/active successfully.")
            responsible_gambling.save()

        elif "blackout_status" in post_data:
            blackout_status = request.POST.get("blackout_status")
            blackout_expire_hours = request.POST.get("blackout_expire_hours")
            responsible_gambling = ResponsibleGambling.objects.get_or_create(user=player)[0]

            if blackout_status == "true":
                responsible_gambling.is_blackout = True
                responsible_gambling.blackout_expire_time = datetime.now(timezone.utc)+timedelta(hours=int(blackout_expire_hours))
                responsible_gambling.blackout_expire_hours = blackout_expire_hours
                message = _("Player has been blackout successfully.")
            else:
                responsible_gambling.is_blackout = False
                responsible_gambling.blackout_expire_time = None
                responsible_gambling.blackout_expire_hours = None
                message = _("Player has been removed from blackout successfully.")
            responsible_gambling.save()

        player.save()
        return self.render_json_response({"status": "Success", "message": message})


class PlayerTransactionsView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = [
        "get",
    ]
    # pagination_class = PageNumberPagination
    date_format = "%d/%m/%Y"
    allowed_roles = ("superadmin", "admin", "dealer", "agent","staff")

    def get_ajax(self, request, *args, **kwargs):

        queryset = Transactions.objects.filter(
            journal_entry__in=(WITHDRAW, DEPOSIT, CREDIT, DEBIT, CASHBACK,BONUS)
        )
        from_date = self.request.GET.get("from_date", None)
        to_date = self.request.GET.get("to_date", None)
        activity_type = self.request.GET.get("activity_type", "")

        external = True if activity_type in ["nowpayments", "area51", "gsoft"] else False

        user_name = self.request.GET.get("user_id", None)

        transaction_filter_dict = {"user__username": user_name}
        if from_date:
            from_date = datetime.strptime(from_date, "%d/%m/%Y").strftime("%Y-%m-%d")
            transaction_filter_dict["created__date__gte"] = from_date
        if to_date:
            to_date = datetime.strptime(to_date, "%d/%m/%Y").strftime("%Y-%m-%d")
            transaction_filter_dict["created__date__lte"] = to_date
        if activity_type and not external:
            transaction_filter_dict["journal_entry"] = activity_type

        queryset = queryset.filter(**transaction_filter_dict).order_by("-created")
        transaction_filter_dict.pop("journal_entry", None)
        # Now Payments transactions
        npt_queryset = NowPaymentsTransactions.objects.filter(**transaction_filter_dict).order_by("-created")
        gst_queryset = GSoftTransactions.objects.filter(**transaction_filter_dict).order_by("-created")
        game_dict = CasinoGameList.objects.in_bulk(set(gst_queryset.filter(game_id__regex=r'^\d+$').values_list("game_id", flat=True)))


        # Creates a result and an index, the index saves cpu usage in exchange of some memory
        # in other methos you had to create a [itm.created.timestamp for itm in query]
        # if a faster method is found please change this
        # this might be O(n), though
        results = []
        createds = []

        if (external and activity_type == "nowpayments") or activity_type == "":
            for obj in npt_queryset:
                data = {"id": str(obj.payment_id),
                        "created": obj.created.strftime("%d/%m/%y %H:%M"),
                        "amount": round(obj.price_amount, 2),
                        "journal_entry": obj.payment_status,
                        "trans_type": obj.transaction_type,
                        "provider" : "NowPayments"}

                # Find the correct index to insert
                idx = bisect_right(createds, data["created"])

                # Insert the new entry at the found index
                results.insert(idx, data)
                createds.insert(idx, data["created"])


        if (external and activity_type == "gsoft") or activity_type == "":
            for obj in gst_queryset:
                if obj.action_type == "LOSE" or obj.bonus_type in GSoftTransactions.BonusType.choices:
                    continue
                multiply = 1 if obj.action_type == 'WIN' else (-1 if obj.action_type == 'BET' else 1)
                data = {"id": str(game_dict.get(gst.game_id, None) if str(obj.game_id).isdigit() else obj.game_id),
                        "created": obj.created.strftime("%d/%m/%y %H:%M"),
                        "amount": obj.amount * multiply,
                        "journal_entry": obj.transaction_type,
                        "trans_type": obj.action_type,
                        "provider" : "GSoft" if str(obj.game_id).isdigit() else "Casino25" }

                # Find the correct index to insert
                idx = bisect_right(createds, data["created"])

                # Insert the new entry at the found index
                results.insert(idx, data)
                createds.insert(idx, data["created"])


        if activity_type in ["casino", "wallet", "area51", ""]:
            for obj in queryset:
                description = obj.description
                trans_type = ""
                amount = round(obj.amount, 2)
                if obj.journal_entry in [WITHDRAW, DEPOSIT]:
                    trans_type = ""
                elif "cashout" in description.lower():
                    trans_type = "Cashout"
                elif (
                    ("refunded" in description.lower())
                    or ("refund" in description.lower())
                    or ("cancel" in description.lower())
                    or ("cancelled" in description.lower())
                ):
                    trans_type = "Refunded"
                elif "bonus" in description.lower() or (obj.bonus_type and  "bonus" in obj.bonus_type.lower()):
                    trans_type = obj.bonus_type.replace('_', ' ')
                    amount = round(obj.bonus_amount,2)

                else:
                    # if obj.journal_entry == CREDIT:
                    #     amount = -amount
                    trans_type = "Betting"

                timezone = request.session._session_cache['user_timezone'] 
                created = obj.created + timedelta(minutes=int(timezone))
                response = {
                    "id": obj.id,
                    "created": created.strftime("%d/%m/%y %H:%M"),
                    "amount": amount,
                    "journal_entry": obj.journal_entry,
                    "trans_type": trans_type,
                    "provider" : "Area 51"
                }
                # Find the correct index to insert
                idx = bisect_right(createds, response["created"])

                # Insert the new entry at the found index
                results.insert(idx, response)
                createds.insert(idx, response["created"])

        return self.render_json_response(results)



class CasinoTransactionsView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):

    http_method_names = [
        "get",
    ]
    # pagination_class = PageNumberPagination
    date_format = "%d/%m/%Y"
    allowed_roles = ("superadmin", "admin", "dealer", "agent", "staff")

    def get_ajax(self, request, *args, **kwargs):
        import datetime
        from_date = self.request.GET.get("from_date", None)
        to_date = self.request.GET.get("to_date", None)
        activity_type = self.request.GET.get("activity_type", None)

        user_name = self.request.GET.get("user_id", None)
        queryset = GSoftTransactions.objects.filter(user__username__iexact=user_name)

        transaction_filter_dict = {}
        if from_date:
            from_date = datetime.datetime.strptime(from_date, "%d/%m/%Y").strftime("%Y-%m-%d")
        if to_date:
            to_date = datetime.datetime.strptime(to_date, "%d/%m/%Y").strftime("%Y-%m-%d")
        if from_date:
            transaction_filter_dict["created__date__gte"] = from_date
        if to_date:
            transaction_filter_dict["created__date__lte"] = to_date
        if activity_type:
            if activity_type == "debit":
                transaction_filter_dict["action_type__in"] = [GSoftTransactions.ActionType.bet, GSoftTransactions.ActionType.rollback]
                queryset = queryset.filter(
                    Q(transaction_type=GSoftTransactions.TransactionType.debit) | Q(transaction_type__isnull=True)
                )
            else:
                transaction_filter_dict["action_type__in"] = [GSoftTransactions.ActionType.win, GSoftTransactions.ActionType.rollback]
                queryset = queryset.filter(
                    Q(transaction_type=GSoftTransactions.TransactionType.credit) | Q(transaction_type__isnull=True)
                )


        queryset = queryset.filter(**transaction_filter_dict).order_by("-created")
        results = []
        for obj in queryset:
            amount = round(obj.amount, 2)
            bonus_bet_amount = round(obj.bonus_bet_amount or 0, 2)
            journal_entry = "credit"
            if obj.action_type in [GSoftTransactions.ActionType.bet, ]:
                journal_entry = "debit"
            elif obj.transaction_type:
                journal_entry = obj.transaction_type.lower()
            response = {
                "id": obj.id,
                "created": obj.created.strftime("%d/%m/%y %H:%M"),
                "amount": amount if journal_entry == "credit" else -amount,
                "bonus_bet_amount": bonus_bet_amount if journal_entry == "credit" else -bonus_bet_amount,
                "journal_entry": journal_entry,
                "trans_type": obj.action_type or "Casino",
            }
            results.append(response)

        return self.render_json_response(results)



class UserProfitView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ["get"]
    date_format = "%d/%m/%Y"
    allowed_roles = ("superadmin", "admin", "dealer", "agent")

    def time_zone_converter(self,date_time_obj,Inverse_Time_flag):


        try:
            current_timezone = self.request.session['time_zone']
        except:
            current_timezone='en'
        if(current_timezone=="en"):
            return date_time_obj
        elif(current_timezone=='ru'):
            current_timezone='Europe/Moscow'
        elif(current_timezone=='tr'):
            current_timezone='Turkey'    
        else:
            current_timezone='Europe/Berlin'
        timee=date_time_obj.replace(tzinfo=None)
        if(Inverse_Time_flag):
            new_tz=pytz.timezone(current_timezone)
            old_tz=pytz.timezone("EST")
        else:
            old_tz=pytz.timezone(current_timezone)
            new_tz=pytz.timezone("EST")

        new_timezone_timestamp = old_tz.localize(timee).astimezone(new_tz)
        return new_timezone_timestamp


    def get_total_out(self, sports_book_out_sum_records):
        sports_book_out_sum_value = 0
        for betslip in sports_book_out_sum_records:
            if betslip.settlement_status == "won":
                sports_book_out_sum_value = Decimal(sports_book_out_sum_value) + Decimal(
                    betslip.possible_win_amount
                )

        return sports_book_out_sum_value

    def get_ajax(self, request, *args, **kwargs):
        filter_clauses = []
        filter_clauses_cashout = []
        filter_clauses_bonus = []
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0)

        to_date = self.request.GET.get("to", None)
        from_date = self.request.GET.get("from", None)

        if isinstance(from_date, str):
            from_date = datetime.strptime(from_date, self.date_format)

        if isinstance(to_date, str):
            to_date = datetime.strptime(to_date, self.date_format)

        # if from_date:
        #     from_date = self.time_zone_converter(from_date, False)
        # else:
        #     first_day_of_month_UTC = current_date.replace(day=1, hour=0, minute=0, second=0)
        #     first_day_of_month = self.time_zone_converter(first_day_of_month_UTC, True).replace(
        #         day=1, hour=0, minute=0, second=0
        #     )
        #     from_date = self.time_zone_converter(first_day_of_month, False)

        # if to_date:
        #     to_date = self.time_zone_converter(to_date, False)
        # else:
        #     to_date = timezone.now()
        #     to_date = to_date.replace(tzinfo=None)

        # if from_date:
        #     filter_clauses.append(Q(created__gte=from_date))
        #     filter_clauses_cashout.append(Q(created__gte=from_date))
        #     filter_clauses_bonus.append(Q(created__gte=from_date))


        # if to_date:
        #     filter_clauses.append(Q(created__lte=to_date))
        #     filter_clauses_cashout.append(Q(created__lte=to_date))
        #     filter_clauses_bonus.append(Q(created__lte=to_date))

        user_id = kwargs.get("user_id")
        user = Users.objects.get(pk=user_id)

        if user.role == "player":
            filter_clauses.append(Q(user__id=user_id))
            filter_clauses_bonus.append(Q(user__id=user_id))
        elif user.role == "agent":
            filter_clauses.append(Q(user__agent__id=user_id))
            filter_clauses_bonus.append(Q(user__agent__id=user_id))
        elif user.role == "dealer":
            filter_clauses.append(Q(user__dealer__id=user_id))
            filter_clauses_bonus.append(Q(user__dealer__id=user_id))


        player_bonus_amount = Transactions.objects.filter(
            reduce(operator.and_, filter_clauses_bonus),
            bonus_type__in=['welcome_bonus','deposit_bonus','affiliate_bonus', "bet_bonus"]
        ).aggregate(bonus_amount=Sum("bonus_amount")).get("bonus_amount")

        offmarket_bonus_amount = 0
        # NOTE: Commenting because Offmarket bonus is not added to users bonus balance
        # offmarket_bonus_amount = OffMarketTransactions.objects.filter(
        #     reduce(operator.and_, filter_clauses_bonus),
        #     bonus__gt= 0
        # ).aggregate(bonus_amount=Sum("bonus")).get("bonus_amount")

        # casino provider
        casino_in_sum = (
            GSoftTransactions.objects.filter(reduce(operator.and_, filter_clauses))
            .filter(request_type=GSoftTransactions.RequestType.wager)
            .aggregate(in_sum=Sum("amount"))
        )

        casino_out_sum = (
            GSoftTransactions.objects.filter(reduce(operator.and_, filter_clauses))
            .filter(request_type__in=[GSoftTransactions.RequestType.result, GSoftTransactions.RequestType.rollback])
            .aggregate(out_sum=Sum("amount"))
        )

        # Offmarket Profit Calculation - Starts

        offmarket_in_sum = OffMarketTransactions.objects.filter(reduce(operator.and_, filter_clauses)).filter(
            transaction_type = OffMarketTransactions.TransactionStatus.success,
            journal_entry = "credit"
        ).aggregate(in_sum=Sum("amount"))

        offmarket_out_sum = OffMarketTransactions.objects.filter(reduce(operator.and_, filter_clauses)).filter(
            transaction_type = OffMarketTransactions.TransactionStatus.success,
            journal_entry__in = ["debit", "refund"]
        ).aggregate(out_sum=Sum("amount"))

        response = {}
        response["offmarket_in_sum"] = round(Decimal(offmarket_in_sum.get("in_sum") or 0), 2)
        response["offmarket_out_sum"] = round(Decimal(offmarket_out_sum.get("out_sum") or 0), 2)
        response["offmarket_profit"] = response["offmarket_in_sum"] - response["offmarket_out_sum"]
        # Offmarket Profit Calculation - Ends

        response["casino_in_sum"] = round(Decimal(casino_in_sum.get("in_sum") or 0), 2)
        response["casino_out_sum"] = round(Decimal(casino_out_sum.get("out_sum") or 0), 2)
        response["casino_book_profit"] = response["casino_in_sum"] - response["casino_out_sum"]




        response["all_in"] = (
              response["casino_in_sum"]
        )
        response["all_out"] = (
            response["casino_out_sum"]
        )
        response["all_profit"] = (
            response["casino_book_profit"]
        )

        # Bonus and net profit calculation
        response["bonus"] = -(round((Decimal(player_bonus_amount or 0) + Decimal(offmarket_bonus_amount or 0)), 2))
        response["net_profit"] = response["all_profit"] + response["bonus"]
        user.locked = response["all_profit"]
        user.save()
        return self.render_json_response(response)



def SettingsView(request):
    if not request.user.is_authenticated:
        return HttpResponseRedirect(settings.LOGIN_URL)

    try:
        permission_value = SuperAdminSetting.objects.first().is_bet_disabled
    except:
        permission_value = False
    return render(request, "admin/settings.html", {"permission_value": permission_value})


# Payment Gateway Integration
def PaymentGatewayView(request):
    preference = get_preference()
    preference_id = preference.get('id')
    init_point = preference.get('init_point')
    return render(request, "includes/payment_gateway.html", {"preference_id":preference_id, "init_point":init_point})


class InitiatePaymentView(APIView):
    http_method_names = ("get",)
    permission_classes = [IsPlayer]

    def get(self, request):
        amount = request.GET.get('amount', None)
        try:
            if amount and float(amount) > 0:
                account_detail = AccountDetails.objects.filter(user__username__iexact=request.user.agent.username).first()
                if not account_detail:
                    return HttpResponse("User's Agent account details not found", status=status.HTTP_404_NOT_FOUND)
                # preference = get_preference(float(amount), account_detail.access_token)
                # preference_id = preference.get('id')

                # Qr based payment
                qr_code = get_payment_qr_code(float(amount), account_detail.access_token, request.user)
                if qr_code:
                    return Response({
                        "qr_code":qr_code, 
                        "public_key":account_detail.public_key
                    }, status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response({"message":"Internal Server error"}, status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"message":"Error in generating QR code"}, status.HTTP_404_NOT_FOUND)


class SaveAccountDetails(CheckRolesMixin, UpdateView):
    http_method_names = ["post"]
    template_name = "admin/agent/agents.html"
    allowed_roles = ("admin", "superadmin", "dealer")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post(self, request, *args, **kwargs):
        data = {k: v for k, v in request.POST.dict().items() if v}
        user_id = data.pop("agent_id")
        user = Users.objects.filter(id=user_id).first()
        if "access_token" not in data:
            return HttpResponse("access_token not provided")
        if "public_key" not in data:
            return HttpResponse("public_key not provided")

        account_detail = AccountDetails.objects.filter(user=user_id)
        if account_detail:
            account_detail.update(**data)
        else:
            data["user"] = user
            AccountDetails(**data).save()

        return HttpResponseRedirect(reverse_lazy("admin-panel:agents"))

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class DashboardView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = [
        "get",
    ]
    # pagination_class = PageNumberPagination
    date_format = "%d/%m/%Y"
    allowed_roles = ("superadmin", "admin", "dealer", "agent","staff")

    def get_ajax(self, request, *args, **kwargs):
        context=dict()
        today = date.today()
        if request.GET.get("data_range"):
            date_range = request.GET.get("data_range")
            today = date.today()
            if date_range == 'week':
                created_gte = today - timedelta(days=7)
                profit_range = 7
            elif date_range == 'month':
                created_gte = today - timedelta(days=30)
                profit_range = 30
            elif date_range == 'three_months':
                created_gte = today - timedelta(days=30*3) 
                profit_range = 3*30
            elif date_range == 'year':
                created_gte = today - timedelta(days=30*12)  
                profit_range = 30*12
        id = self.request.user.id
        total_profit_data = {}

        if request.user.role =='staff':
            player_count =  Queue.objects.filter(is_active=True,user__agent=request.user.agent).count() 
            tip_amount = Transactions.objects.filter(created__gte=created_gte,description__icontains=self.request.user.username).aggregate(Sum('amount'))
            total_players_served = ChatHistory.objects.filter(created__gte=created_gte,staff=self.request.user).count()
            context['total_players_served'] = total_players_served if total_players_served else 0
            context['player_count'] = player_count
            context['is_staff'] = 'true'
            context['tip_amount'] = round(tip_amount['amount__sum'], 2) if tip_amount['amount__sum'] else 0
            latest_tips = Transactions.objects.filter(description__icontains=self.request.user.username).order_by("-created")[:5].annotate(username=F('user__username'))
            data = [
                {
                    'id': tip.id,
                    'user': tip.user_id,
                    'username': tip.user.username,
                    'merchant': tip.merchant_id,
                    'amount': str(round(tip.amount, 2)),
                    'journal_entry': tip.journal_entry,
                } for tip in latest_tips
            ]
            data_json = json.dumps(data)
            context['latest_tips']=data_json
            now = datetime.now()
            total_profit_data['profitrange']=profit_range
            for days in range(profit_range):
                day = now - timedelta(days=days)
                total_profit_data[days] = str(day.strftime("%b-%d"))
                total_tip_amount = Transactions.objects.filter(created__date=day,description__icontains=self.request.user.username).aggregate(Sum("amount"))['amount__sum'] or 0
                total_profit_data[total_profit_data[days]] = {"amount__sum":int(total_tip_amount)}
            context["total_profit_data"] = total_profit_data
            context['pending_ca_req'] = CashAppDeatils.objects.filter(user__agent_id = id, status = CashAppDeatils.StatusType.pending,is_active = True, created__gte=created_gte).count()
            return self.render_json_response(context)


        if request.user.role=='superadmin':
            total_players=Users.objects.filter(role="player").count()
            new_registrations = Users.objects.filter(role="player",created__gte=created_gte).count()
            verified_players=Users.objects.filter(admin_id=id,role="player").count()
            unverified_players=Users.objects.filter(admin_id=id,role="player", is_verified = False).count()
            total_dealers=Users.objects.filter(role="dealer").count()
            total_agents=Users.objects.filter(role="agent").count()
            total_profit_data["credit"] = Transactions.objects.filter(journal_entry__in=["credit","withdraw"]).aggregate(Sum("amount"))
            total_profit_data["debit"] = Transactions.objects.filter(journal_entry__in=["debit","deposit"]).aggregate(Sum("amount")) 

        if request.user.role=="admin":
                total_players=Users.objects.filter(admin_id=id,role="player").count()
                total_earned_by_affiliates = Transactions.objects.filter(created__gte=created_gte,journal_entry='bonus',bonus_type='affiliate_bonus').aggregate(Sum("amount"))['amount__sum']
                total_earned_by_affiliates = round(float(total_earned_by_affiliates),2)  if total_earned_by_affiliates else 0
                context["total_earned_by_affiliates"] =  total_earned_by_affiliates
                context["total_player_joined_by_affiliate"] = Users.objects.filter(admin_id=id,role="player",affiliated_by__isnull=False,created__gte=created_gte).count()
                new_registrations = Users.objects.filter(role="player",created__gte=created_gte,admin_id=id).count()
                verified_players=Users.objects.filter(admin_id=id,role="player", is_verified = True).count()
                unverified_players=Users.objects.filter(admin_id=id,role="player", is_verified = False).count()
                total_dealers=Users.objects.filter(admin_id=id,role="dealer").count()
                total_agents=Users.objects.filter(admin_id=id,role="agent").count()
                total_profit_data["credit"] = Transactions.objects.filter(journal_entry__in=["credit","withdraw"]).aggregate(Sum("amount"))
                total_profit_data["debit"] = Transactions.objects.filter(journal_entry__in=["debit","deposit"]).aggregate(Sum("amount"))
        elif request.user.role=="dealer":
                total_players=Users.objects.filter(dealer_id=id,role="player").count()
                verified_players=Users.objects.filter(dealer_id=id,role="player", is_verified = True).count()
                unverified_players=Users.objects.filter(dealer_id=id,role="player", is_verified = False).count()
                new_registrations = Users.objects.filter(role="player",created__gte=created_gte,dealer_id=id).count()
                total_dealers=Users.objects.filter(role="dealer").count()
                total_agents=Users.objects.filter(dealer_id=id,role="agent").count()
                total_profit_data["credit"] = Transactions.objects.filter(journal_entry__in=["credit","withdraw"]).aggregate(Sum("amount"))
                total_profit_data["debit"] = Transactions.objects.filter(journal_entry__in=["debit","deposit"]).aggregate(Sum("amount"))
        elif request.user.role=="agent":
                total_players=Users.objects.filter(agent_id=id,role="player").count()
                new_registrations = Users.objects.filter(role="player",created__gte=created_gte,agent_id=id).count()
                verified_players=Users.objects.filter(agent_id=id,role="player", is_verified = True).count()
                unverified_players=Users.objects.filter(agent_id=id,role="player", is_verified = False).count()
                total_dealers=Users.objects.filter(role="dealer").count()
                total_agents=Users.objects.filter(role="agent").count()
                total_profit_data["credit"] = Transactions.objects.filter(journal_entry__in=["credit","withdraw"]).aggregate(Sum("amount"))
                total_profit_data["debit"] = Transactions.objects.filter(journal_entry__in=["debit","deposit"]).aggregate(Sum("amount"))
                context['pending_ca_req'] = CashAppDeatils.objects.filter(user__agent_id = id, status = CashAppDeatils.StatusType.pending,is_active = True, created__gte=created_gte).count()
        else:
            admin_id = self.request.user.admin.id
            context["total_tournaments"] = Tournament.objects.filter(created__gte=created_gte).count()
            context["total_active_tournaments"] = Tournament.objects.filter(is_active=True, created__gte=created_gte).count()
            context["total_tournaments_prize_distributed"] = round(Transactions.objects.filter(
                created__gte=created_gte,
                description__icontains="Tournament won by"
            ).aggregate(total=Coalesce(Sum('amount'), Value(0))).get("total"), 2)
            context["website_headers"] = list(CasinoHeaderCategory.objects.order_by("position").values("id", "name", "image", "is_active"))[:3]
            context["total_banners"] = AdminBanner.objects.filter(admin=admin_id, created__gte=created_gte).count()
            context["total_pages"] = CmsPages.objects.filter(created__gte=created_gte).count()

        context["total_withdraws"]=Transactions.objects.filter(created__gte=created_gte,journal_entry="withdraw").count()
        context["total_deposits"]=Transactions.objects.filter(created__gte=created_gte,journal_entry="deposit").count()

        if request.user.role in ["superadmin", "admin", "dealer", "agent", "staff"]:
            context["total_players"]=total_players
            context["verified_players"]=verified_players
            context["unverified_players"]=unverified_players
            context["total_dealers"]=total_dealers
            context["total_agents"]=total_agents
            context['is_staff'] = 'false'
            context["new_registrations"]=new_registrations

            now = datetime.now()
            total_profit_data['profitrange']=profit_range
            for days in range(profit_range):
                day = now - timedelta(days=days)
                total_profit_data[days] = str(day.strftime("%b-%d"))
                total_deposit_amount = Transactions.objects.filter(journal_entry="credit", created__date=day).aggregate(Sum("amount"))['amount__sum'] or 0
                total_wager_amount = GSoftTransactions.objects.filter(request_type=GSoftTransactions.RequestType.wager, created__date=day).aggregate(Sum("amount"))['amount__sum'] or 0
                total_amount = (Decimal(total_deposit_amount) + Decimal(total_wager_amount))
                total_profit_data[total_profit_data[days]] = {"amount__sum":int(total_amount)}

            context["total_profit_data"] = total_profit_data
            # data = self.calculate_profit_view(request.user, request.GET.get("data_range"))
            # context["top_chart_data"] = data
        return self.render_json_response(context)




class TransactionReportView(CheckRolesMixin, ListView):
    template_name = "report/transaction_report.html"
    model = Transactions
    queryset = Transactions.objects.order_by("-created").all()
    context_object_name = "transactionreport"
    allowed_roles = ("admin", "superadmin", "dealer", "agent")
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        queryset = super().get_queryset()

        user = Users.objects.get(username=self.request.user)
        if user.role == "dealer":
            queryset = queryset.filter(Q(user=self.request.user) | Q(merchant=self.request.user) | Q(merchant__dealer=self.request.user))
        elif user.role == "agent":
            queryset = queryset.filter(Q(user=self.request.user) | Q(merchant=self.request.user))
        elif user.role == "player":
            queryset = queryset.filter(Q(user=self.request.user))

        if(self.request.GET.getlist("players", None)):
            queryset = queryset.filter(user__id__in=self.request.GET.getlist("players"))

        if self.request.GET.get("username"):
            queryset = queryset.annotate(
                user_username_lower=Lower("user__username"),
                merchant_username_lower=Lower("merchant__username"),
            ).filter(
                Q(user_username_lower=self.request.GET.get("username").split(",").lower())
                | Q(merchant_username_lower=self.request.GET.get("username").split(",").lower())
            )

        if self.request.GET.get("journal-entry") and self.request.GET.get("journal-entry") != "all":
            queryset = queryset.filter(journal_entry=self.request.GET.get("journal-entry"))

        if self.request.GET.get("role"):
            queryset = queryset.filter(user__role = self.request.GET.get("role"))

        if self.request.GET.get("transactionid") and self.request.GET.get("transactionid").isdigit():
            queryset = queryset.filter(id=self.request.GET.get("transactionid"))

        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__gte=start_date)
        else:
            # by default show results from first day of month
            current_date = timezone.now()
            first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
            queryset = queryset.filter(created__gte=first_day_of_month)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__date__lte=end_date)


        if self.request.GET.get("duration"):
            check = self.request.GET.get("duration")
            today_date = datetime.today().strftime("%Y-%m-%d")
            duration_end_date = today_date
            if check == "today":
                yesterday_date = datetime.today() - timedelta(days=1)
                duration_start_date = yesterday_date.strftime("%Y-%m-%d")
            if check == "yesterday":
                yesterday_date = datetime.today() - timedelta(days=2)
                duration_start_date = yesterday_date.strftime("%Y-%m-%d")
            if check == "lastweek":
                last_week_date = datetime.today() - timedelta(days=7)
                duration_start_date = last_week_date.strftime("%Y-%m-%d")
            if check == "lastmonth":
                last_month = datetime.today() - timedelta(days=30)
                duration_start_date = last_month.strftime("%Y-%m-%d")
            queryset = queryset.filter(created__gte=duration_start_date).filter(created__date__lte=duration_end_date)

        if self.request.GET.getlist("dealers"):
            dealers = self.request.GET.getlist("dealers")
            queryset = queryset.filter(user__dealer__in=dealers)

        if self.request.GET.getlist("agents"):
            agents = self.request.GET.getlist("agents")
            queryset = queryset.filter(user__agent__in=agents)

        self.context_deposit = queryset.filter(journal_entry="deposit").aggregate(Sum("amount"))
        self.context_withdraw = queryset.filter(journal_entry="withdraw").aggregate(Sum("amount"))
        self.context_sum = queryset.filter(journal_entry__in=['deposit', 'withdraw']).aggregate(Sum("amount"))

        return queryset

    def get_context_data(self, **kwargs):
        # by default show results from first day of month
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

        context = super().get_context_data(**kwargs)
        context["role"] = self.request.GET.get("role", None)
        context["journal_entry"] = self.request.GET.get("journal-entry", None)
        context["username"] = self.request.GET.get("username", "")
        context["from"] = self.request.GET.get("from", first_day_of_month)
        context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))
        context["total_deposit"] = self.context_deposit["amount__sum"]
        context["total_withdraw"] = self.context_withdraw["amount__sum"]
        context["sum"] = self.context_sum["amount__sum"]
        context["duration"] = self.request.GET.get("duration", None)
        if not context["sum"]: context["sum"] = 0
        if not context["total_deposit"]: context["total_deposit"] = 0
        if not context["total_withdraw"]: context["total_withdraw"] = 0

        if self.request.GET.getlist("dealers"):
            dealers = self.request.GET.getlist("dealers")
            context["selected_dealers"] = Dealer.objects.filter(id__in=dealers)

        if self.request.GET.getlist("agents"):
            agents = self.request.GET.getlist("agents")
            context["selected_agents"] = Agent.objects.filter(id__in=agents)

        return context


class OffMarketReportView(CheckRolesMixin, ListView):
    template_name = "report/offmarket_report.html"
    model = OffMarketTransactions
    queryset = OffMarketTransactions.objects.order_by("-created").all()
    context_object_name = "offmarketreport"
    allowed_roles = ("admin", "superadmin", "dealer", "agent")
    date_format = "%d/%m/%Y"
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()

        user = Users.objects.get(username=self.request.user)
        if self.request.GET.get("status-id") and self.request.GET.get("status-id") != "all":
            status=self.request.GET.get("status-id").capitalize()
            queryset = queryset.filter(status=status)

        if self.request.GET.get("transaction-type") and self.request.GET.get("transaction-type") != "all":
            transaction_type=self.request.GET.get("transaction-type")
            queryset = queryset.filter(transaction_type=transaction_type)

        if(self.request.GET.getlist("players", None)):
            queryset = queryset.filter(user__id__in=self.request.GET.getlist("players"))

        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__gte=start_date)
        else:
            # by default show results from first day of month
            current_date = timezone.now()
            first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
            queryset = queryset.filter(created__gte=first_day_of_month)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__date__lte=end_date)
        return queryset

    def get_context_data(self, **kwargs):
        # by default show results from first day of month
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)
        context = super().get_context_data(**kwargs)
        context["status"] = self.request.GET.get("status", None)
        context["transaction_type"] = self.request.GET.get("transaction_type", None)
        context["from"] = self.request.GET.get("from", first_day_of_month)
        context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))
        return context


class DownloadTransactionReport(View):
    http_method_names = ["get",]
    allowed_roles = ("admin", "superadmin", "dealer", "agent")
    date_format = "%d/%m/%Y"

    def get(self, request, **kwargs):
        queryset = Transactions.objects.order_by("-created").all()

        user = Users.objects.get(username=self.request.user)
        if user.role == "dealer" or user.role == "agent":
            queryset = queryset.filter(Q(user=self.request.user) | Q(merchant=self.request.user))
        elif user.role == "player":
            queryset = queryset.filter(Q(merchant=self.request.user))

        if self.request.GET.get("username"):
            queryset = queryset.annotate(
                user_username_lower=Lower("user__username"),
                merchant_username_lower=Lower("merchant__username"),
            ).filter(
                Q(user_username_lower__icontains=self.request.GET.get("username").lower())
                | Q(merchant_username_lower__icontains=self.request.GET.get("username").lower())
            )

        if self.request.GET.get("journal-entry") and self.request.GET.get("journal-entry") != "all":
            queryset = queryset.filter(journal_entry=self.request.GET.get("journal-entry"))

        if self.request.GET.get("role"):
            queryset = queryset.filter(user__role = self.request.GET.get("role"))

        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format)
            queryset = queryset.filter(created__gte=start_date)
        else:
            # by default show results from first day of month
            current_date = timezone.now()
            first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
            queryset = queryset.filter(created__gte=first_day_of_month)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format)
            queryset = queryset.filter(created__date__lte=end_date)

        return ExcelResponse(queryset)


class SignUpBonusPermissionView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("superadmin",)
    http_method_names = ["post"]

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):

        admin_id = self.request.POST.get("adminID", None)
        sign_up_bonus_enabled = self.request.POST.get("isSignUpBonusEnabled", None)
        admin = Admin.objects.get(id=admin_id)


        if sign_up_bonus_enabled == "true":
            sign_up_bonus_enabled = True
            message = "Sign up bonus Enabled Successfully"
        else:
            sign_up_bonus_enabled = False
            message = "Sign up bonus Disabled Successfully"

        admin.is_welcome_bonus_enabled = sign_up_bonus_enabled
        admin.save()

        return self.render_json_response(
            {
                "status": "success",
                "message": _(message)
            },
            status=200
        )


def SettingsView(request):
    if request.user.role in ["admin"]:
        try:
            permission_value = SuperAdminSetting.objects.first().is_bet_disabled
        except:
            permission_value = False
        return render(request, "admin/settings.html", {"permission_value": permission_value})
    else:
        return HttpResponseRedirect(settings.LOGIN_URL)

def HeathCheckView(request):
    return JsonResponse({'message': 'OK'})


class OtpPermissionView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("superadmin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        admin = Admin.objects.get(id=self.request.POST.get("admin_id"))
        enabled = self.request.POST.get("enabled")
        admin = Users.objects.get(id=admin.id)
        if enabled == "true":
            admin.is_otp_enabled = True
            admin.save()
        elif enabled == "false":
            admin.is_otp_enabled = False
            admin.save()
            otp_creds = OtpCredsInfo.objects.filter(
                admin=admin,
                is_deleted=False
            )
            for obj in otp_creds:
                obj.is_deleted = True
                obj.save()
        return self.render_json_response({
            "status":"Success","message": _("OTP permission updated")})

# Note: This view is depricated and we have created seperate views for different type of bonuses with seperate UI. Will remove this later
class BonusesView(CheckRolesMixin, ListView):
    template_name = "admin/bonuses.html"
    model = PromoCodes
    queryset = PromoCodes.objects.order_by("-created").all()
    context_object_name = "bonuses"
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(
            dealer=self.request.user
        )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            bonus_obj = BonusPercentage.objects.get(dealer=self.request.user, bonus_type="welcome_bonus")
            context["welcome_bonus"] = bonus_obj.percentage
        except BonusPercentage.DoesNotExist:
            context["welcome_bonus"] = 0

        try:
            bonus_obj = BonusPercentage.objects.get(dealer=self.request.user, bonus_type="referral_bonus")
            context["referral_bonus"] = bonus_obj.percentage
        except BonusPercentage.DoesNotExist:
            context["referral_bonus"] = 0
        try:
            bonus_obj = BonusPercentage.objects.get(dealer=self.request.user, bonus_type="losing_bonus")
            context["losing_bonus"] = bonus_obj.percentage
            promo_obj = PromoCodes.objects.get(bonus=bonus_obj, is_expired=False)
            context["losing_promo_code"] = promo_obj.promo_code
            context["losing_start_date"] = promo_obj.start_date.strftime(self.date_format)
            context["losing_end_date"] = promo_obj.end_date.strftime(self.date_format)
            context["bonus_type"] = bonus_obj.bonus_type
            context["promo_code_usage_limit"] = promo_obj.usage_limit
            context["promo_code_user_limit"] = promo_obj.limit_per_user
        except:
            context["losing_bonus"] = 0
            context["losing_start_date"] = timezone.now().strftime(self.date_format)
            context["losing_end_date"] = timezone.now().strftime(self.date_format)
            context["promo_code_usage_limit"] = 1
            context["promo_code_user_limit"] = 1
        return context


class DetailBonusView(CheckRolesMixin, ListView):
    """
    This shows all the important info, as usage and times, from every promo_code
    """
    template_name = "admin/bonuses/bonus_info.html"
    model = PromoCodesLogs
    queryset = PromoCodesLogs.objects.none()
    context_object_name = "bonus"
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.request.user.is_authenticated:
            raise PermissionDenied
        user = self.request.user

        promo_code = self.kwargs.get("promo_code")
        if not promo_code:
            context['promo_code'] = None
            return context

        promo = PromoCodes.objects.filter(
            dealer=user,
            promo_code=promo_code,
            bonus__bonus_type__in={"welcome_bonus", "deposit_bonus"},
        ).first()

        if not promo:
            return context

        context["promo_code"] = promo_code
        context["promo"] = promo

        promos = PromoCodesLogs.objects.filter(
                promocode=promo,
                transfer__isnull=False
            )

        # Fetch raw logs
        promos = PromoCodesLogs.objects.filter(
            promocode=promo,
            transfer__isnull=False
        ).values("user__username", "created", "transfer", "transfer_gold")

        # Build per-user usage data manually
        promo_logs_dict = defaultdict(list)
        for log in promos:
            promo_logs_dict[log["user__username"]].append({
                "date": log["created"],
                "transfer": log["transfer"],
                "transfer_gold": log["transfer_gold"]
            })

        # Convert dict to list with totals
        promo_logs_list = []
        for username, usages in promo_logs_dict.items():
            promo_logs_list.append({
                "user__username": username,
                "total_usages": len(usages),
                "total_transfer": sum(u["transfer"] for u in usages),
                "total_transfer_gold": sum(u["transfer_gold"] for u in usages),
                "usages": usages
            })

        # Sort by total_transfer descending
        promo_logs_list = sorted(promo_logs_list, key=lambda x: x["total_transfer"], reverse=True)

        context["promo_logs"] = promo_logs_list
        # total days of promo
        total_days = 0
        days_passed = 0
        if (promo.start_date and promo.end_date):
            total_days = (promo.end_date - promo.start_date).days + 1
            days_passed = min((date.today() - promo.start_date).days, total_days)
        
        day_units = f"{days_passed}/{total_days}"

        if total_days - days_passed < 14:
            day_units = f"{total_days - days_passed} left"
        elif total_days > 50:
            days_passed = round((days_passed / total_days) * 100, 2)
            total_days = 100
            day_units = f"{days_passed}%"
            
        transfer = round(sum(log["transfer"] for log in promos) if promos else 0, 2)
        transfer_gold = round(sum(log["transfer_gold"] for log in promos) if promos else 0, 2)
        usages = len(promos)
        if not promos:
            context["promo_logs"] = None
        

        # Overall analytics
        context["analytics"] = {
            "total_days": total_days,
            "passed_days": days_passed,
            "midle_text_days": day_units,
            "total_midle_text": f"{transfer}",
            "total_usages": len(promos),
            "total_transfer": transfer,
            "total_transfer_gold": transfer_gold,
            "total_midle_text_gold": f"{transfer_gold}",
        }

        return context


class AutomatedBonusView(CheckRolesMixin, ListView):
    """
    Sign Up bonus view - Renamed from welcome bonus percentage
    """
    template_name = "admin/bonuses/automated_bonuses.html"
    model = PromoCodes
    queryset = PromoCodes.objects.order_by("-created").all()
    context_object_name = "bonuses"
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        try:
            queryset = super().get_queryset()
        except Exception:
            queryset = PromoCodes.objects.none()
        queryset = queryset.filter(
            dealer=self.request.user, bonus__bonus_type="automated_promos"
        )
        data = {}
        for item in queryset:
            pres = {
                "sc": item.instant_bonus_amount,
                "gc": item.gold_bonus,
                "enabled" : not bool(item.is_expired)
            }
            if item.promo_code in data:
                data[item.promo_code].update(pres)
            else:
                data[item.promo_code] = pres

        return data

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["available_events"] = BONUS_EVENTS.items()
        return context


class UpdateAutomatedBonusView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        bonus = BonusPercentage.objects.filter(dealer=request.user, bonus_type="automated_promos").first()
        if not bonus:
            return Response(data={ "message": "This function is not enabled." }, status=status.HTTP_400_BAD_REQUEST)
        action = request.data.get("action")
        if action not in BONUS_EVENTS.keys():
            return Response(data={ "message": "This action is not available." }, status=status.HTTP_400_BAD_REQUEST)


        # Extract and validate numeric fields
        def is_number(value):
            try:
                float(value)
                return True
            except (TypeError, ValueError):
                return False

        sc_price = request.data.get("sc_price")
        gc_price = request.data.get("gc_price")
        enabled = request.data.get("enabled")

        # Validation
        errors = {}
        if sc_price is None or not is_number(sc_price):
            errors["sc_price"] = "Must be a number and not None."
        if gc_price is None or not is_number(gc_price):
            errors["gc_price"] = "Must be a number and not None."
        if enabled is None:
            errors["enabled"] = "This field cannot be None."

        if errors:
            return Response({"message" : "Invalid values.", "errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        sc_price = Decimal(sc_price).quantize(Decimal("0.01"))
        gc_price = Decimal(gc_price).quantize(Decimal("0.01"))
        enabled = str(enabled).lower() in ["true", "1", "yes"]

        start_date = timezone.now()

        PromoCodes.objects.update_or_create(
            bonus=bonus,
            promo_code=action,
            dealer=request.user,
            bonus_percentage=Decimal("0.00"),
            defaults={
                "bonus_distribution_method": PromoCodes.BonusDistributionMethod.instant,
                "instant_bonus_amount": sc_price,
                "max_bonus_limit": Decimal(1),
                "start_date": start_date,
                "gold_bonus": gc_price,
                "usage_limit": Decimal(1),
                "is_expired": not enabled,
            }
        )

        return Response({"message": "Bonus updated successfully."}, status=status.HTTP_200_OK)



class SignUpBonusView(CheckRolesMixin, ListView):
    """
    Sign Up bonus view - Renamed from welcome bonus percentage
    Ref: https://trello.com/c/xoCgHWtk
    """
    template_name = "admin/bonuses/sign_up_bonus.html"
    model = PromoCodes
    queryset = PromoCodes.objects.order_by("-created").all()
    context_object_name = "bonuses"
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(
            dealer=self.request.user.id, bonus__bonus_type="welcome_bonus"
        )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            bonus_obj = BonusPercentage.objects.get(dealer=self.request.user.id, bonus_type="welcome_bonus")

            context["welcome_bonus"] = bonus_obj.percentage
            context["maximum_limit"] = bonus_obj.welcome_bonus_limit 
            promo_obj = PromoCodes.objects.filter(bonus=bonus_obj, is_expired=False).last()
            # context["losing_promo_code"] = promo_obj.promo_code if promo_obj else 0
            # context["losing_start_date"] = promo_obj.start_date.strftime(self.date_format) if promo_obj else timezone.now().strftime(self.date_format)
            # context["losing_end_date"] = promo_obj.end_date.strftime(self.date_format) if promo_obj else timezone.now().strftime(self.date_format)
            context["bonus_type"] = bonus_obj.bonus_type if promo_obj else "welcome_bonus"
            # context["promo_code_usage_limit"] = promo_obj.usage_limit if promo_obj else 0
            context["promo_code_user_limit"] = -1
        except BonusPercentage.DoesNotExist:
            context["welcome_bonus"] = 0
            # context["losing_start_date"] = timezone.now().strftime(self.date_format)
            # context["losing_end_date"] = timezone.now().strftime(self.date_format)
            context["promo_code_usage_limit"] = 1
            context["promo_code_user_limit"] = -1

        return context


class LosingBonusView(CheckRolesMixin, ListView):
    """
    LosingBonusView - 
    Ref: https://trello.com/c/xoCgHWtk
    """
    template_name = "admin/bonuses/losing_bonus.html"
    model = PromoCodes
    queryset = PromoCodes.objects.order_by("-created").all()
    context_object_name = "bonuses"
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(
            dealer=self.request.user.id, bonus__bonus_type="losing_bonus"
        )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            bonus_obj = BonusPercentage.objects.get(dealer=self.request.user.id, bonus_type="losing_bonus")

            context["losing_bonus"] = bonus_obj.percentage
            promo_obj = PromoCodes.objects.filter(bonus=bonus_obj, is_expired=False).last()
            context["losing_promo_code"] = promo_obj.promo_code if promo_obj else 0
            context["losing_start_date"] = promo_obj.start_date.strftime(self.date_format) if promo_obj else timezone.now().strftime(self.date_format)
            context["losing_end_date"] = promo_obj.end_date.strftime(self.date_format) if promo_obj else timezone.now().strftime(self.date_format)
            context["bonus_type"] = bonus_obj.bonus_type if promo_obj else "losing_bonus"
            context["promo_code_usage_limit"] = promo_obj.usage_limit if promo_obj else 0
            context["promo_code_user_limit"] = -1
        except BonusPercentage.DoesNotExist:
            context["losing_bonus"] = 0
            context["losing_start_date"] = timezone.now().strftime(self.date_format)
            context["losing_end_date"] = timezone.now().strftime(self.date_format)
            context["promo_code_usage_limit"] = 1
            context["promo_code_user_limit"] = -1

        return context


class ReferralBonusView(CheckRolesMixin, ListView):
    """
    ReferralBonusView - 
    Ref: https://trello.com/c/xoCgHWtk
    """
    template_name = "admin/bonuses/referral_bonus.html"
    model = PromoCodes
    queryset = PromoCodes.objects.order_by("-created").all()
    context_object_name = "bonuses"
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(
            dealer=self.request.user.id, bonus__bonus_type="referral_bonus"
        )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            bonus_obj = BonusPercentage.objects.get(dealer=self.request.user.id, bonus_type="referral_bonus")

            context["referral_bonus"] = bonus_obj.percentage
            context["referral_bonus_limit"] = bonus_obj.referral_bonus_limit
            promo_obj = PromoCodes.objects.filter(bonus=bonus_obj, is_expired=False).last()
            context["losing_promo_code"] = promo_obj.promo_code if promo_obj else 0
            context["bonus_type"] = bonus_obj.bonus_type if promo_obj else 0
            context["promo_code_usage_limit"] = promo_obj.usage_limit if promo_obj else 0
            context["promo_code_user_limit"] = -1
        except BonusPercentage.DoesNotExist:
            context["referral_bonus"] = 0
            context["promo_code_usage_limit"] = 1
            context["promo_code_user_limit"] = -1

        return context


# class BonusPercentageView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
#     allowed_roles = ("admin")
#     date_format = "%d/%m/%Y"

#     def handle_no_permission(self):
#         return HttpResponseRedirect(settings.LOGIN_URL)

#     def post_ajax(self, request, *args, **kwargs):
#         admin = Admin.objects.get(id=self.request.user.id)
#         percentage = self.request.POST.get("percentage", 0.00)
#         bonus_type = self.request.POST.get("bonusType", None)
#         usage_limit = self.request.POST.get("usage_limit", 1)
#         bet_bonus_per_day_limit = self.request.POST.get("per_day_usage_limit", 1)
#         deposit_per_day_usage_limit = self.request.POST.get("deposit_per_day_usage_limit", 1)
#         start_date = self.request.POST.get("start_time")
#         if start_date:
#             start_date = timezone.datetime.strptime(
#                 start_date, self.date_format
#             ).date()

#         end_date = self.request.POST.get("end_time")
#         if end_date:
#             end_date = timezone.datetime.strptime(
#                 end_date, self.date_format
#             ).date()

#         promo_code = self.request.POST.get("promo_code", None)
#         # promo_code_usage_limit = self.request.POST.get("promo_code_usage_limit", 1)

#         try:
#             bonus_obj = BonusPercentage.objects.get(dealer=admin, bonus_type=bonus_type)
#             bonus_obj.percentage = percentage
#             if bonus_type == "deposit_bonus":
#                 bonus_obj.deposit_bonus_limit = usage_limit
#                 bonus_obj.deposit_bonus_per_day_limit = deposit_per_day_usage_limit if deposit_per_day_usage_limit !='' else 1
#             # if bonus_type == "referral_bonus":
#             #     bonus_obj.referral_bonus_limit = usage_limit
#             elif bonus_type == "welcome_bonus":
#                 bonus_obj.welcome_bonus_limit = usage_limit
#             elif bonus_type == "bet_bonus":
#                 bonus_obj.bet_bonus_limit = usage_limit
#                 bonus_obj.bet_bonus_per_day_limit = bet_bonus_per_day_limit if bet_bonus_per_day_limit !='' else 1
#             # elif bonus_type == "losing_bonus":
#             #     bonus_obj.losing_bonus_limit = usage_limit
#             bonus_obj.save()
#         except BonusPercentage.DoesNotExist:
#             bonus_obj = BonusPercentage()
#             bonus_obj.dealer = admin
#             bonus_obj.percentage = percentage
#             bonus_obj.bonus_type = bonus_type
#             if bonus_type == "deposit_bonus":
#                 bonus_obj.deposit_bonus_limit = usage_limit
#                 bonus_obj.deposit_bonus_per_day_limit = deposit_per_day_usage_limit if deposit_per_day_usage_limit !='' else 1
#             # if bonus_type == "referral_bonus":
#             #     bonus_obj.referral_bonus_limit = usage_limit
#             elif bonus_type == "welcome_bonus":
#                 bonus_obj.welcome_bonus_limit = usage_limit
#             # elif bonus_type == "losing_bonus":
#             #     bonus_obj.losing_bonus_limit = usage_limit
#             elif bonus_type == "bet_bonus":
#                 bonus_obj.bet_bonus_per_day_limit = bet_bonus_per_day_limit if bet_bonus_per_day_limit !='' else 1
#             bonus_obj.save()


#             try:
#                 promo_obj = PromoCode/s()
#                 promo_obj.bonus = bonus_obj
#                 # promo_obj.promo_code = promo_code
#                 # promo_obj.start_date = start_date
#                 # promo_obj.end_date = end_date
#                 promo_obj.dealer = admin
#                 promo_obj.bonus_percentage = percentage
#                 # promo_obj.usage_limit = promo_code_usage_limit
#                 promo_obj.save()
#             except Exception:
#                 bonus_obj.percentage = 0
#                 bonus_obj.save()
#                 return self.render_json_response({"status": "error", "message": _("Something Went Wrong")})

#         return self.render_json_response({"status": "success", "message": _("Changes Done")})


class BonusPercentageView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        bonus_type = self.request.POST.get("bonusType", None)
        promocode_bonus_type = self.request.POST.get("signup_bonus_type")

        try:
            gold_percentage = Decimal(self.request.POST.get("gold_percentage", 0.00) or 0)
            bonus_percentage = Decimal(self.request.POST.get("percentage", 0.00) or 0)
            if gold_percentage < 0 or bonus_percentage < 0:
                raise ValueError
        except ValueError:
            return self.render_json_response({"status": "error", "message": _(f"Percentages are not valid.")},400)

        try:
            instant_gold_amount = Decimal(self.request.POST.get("instant_gold_amount", 0) or 0)
            instant_bonus_amount = Decimal(self.request.POST.get("instant_bonus_amount", 0) or 0)

            if instant_gold_amount < 0 or instant_gold_amount < 0:
                raise ValueError
        except ValueError:
            return self.render_json_response({"status": "error", "message": _(f"Instant values are not valid.")},400)
        
        
        if bonus_type is None:
            return self.render_json_response({"status": "error", "message": "Bonus Type must be set"}, 400)
        
        if bonus_type == "deposit_bonus":
            if bonus_percentage > 0:
                return self.render_json_response({"status": "error", "message": "SC is disabled, please set it to 0"} , 400)
        if bonus_type == "bet_bonus":
            if instant_bonus_amount > 0:
                return self.render_json_response({"status": "error", "message": "SC is disabled, please set it to 0"} , 400)

        try:
            user_limit = int(self.request.POST.get("user_limit", 1))
            bonus_limit = int(self.request.POST.get("bonus_limit", 1))
            usage_limit = int(self.request.POST.get("usage_limit", 1))

            if user_limit < 1 or bonus_limit < 1 or usage_limit < 1:
                raise ValueError
        except ValueError:
            return self.render_json_response({"status": "error", "message": _(f"Limits are not valid.")},400)

        start_date = self.request.POST.get("start_time")
        end_date = self.request.POST.get("end_time")

        deposit_per_day_usage_limit = self.request.POST.get("deposit_per_day_usage_limit", 1)
        bet_bonus_per_day_limit = self.request.POST.get("per_day_usage_limit", 1)

        if start_date is None or end_date is None:
            return self.render_json_response({"status": "error", "message": _(f"Dates are not valid.")},400)

        if start_date:
            start_date = timezone.datetime.strptime(
                start_date, self.date_format
            ).date()

        if end_date:
            end_date = timezone.datetime.strptime(
                end_date, self.date_format
            ).date()

        promo_code = self.request.POST.get("promo_code", None)
        if bonus_type not in {"deposit_bonus", "welcome_bonus", "bet_bonus"}:
            return self.render_json_response({"status": "error", "message": _(f"Bonus type: '{bonus_type}' does not exists.")},400)
        if promo_code and PromoCodes.objects.filter(promo_code=promo_code, bonus__bonus_type=bonus_type).exists():
            return self.render_json_response({"status": "error", "message": _(f"Promo code with the name '{promo_code}' already exists. Please choose a unique name.")},400)
        if promo_code is None:
            return self.render_json_response({"status": "error", "message": _(f"Promo code with the name must not be none.")},400)

        bonus_obj = BonusPercentage.objects.filter(dealer=self.request.user, bonus_type=bonus_type).first()
        if not bonus_obj:
            bonus_obj = BonusPercentage()
            bonus_obj.dealer = self.request.user
            bonus_obj.bonus_type = bonus_type

        if bonus_type == "deposit_bonus":
            # bonus_obj.deposit_bonus_limit = usage_limit
            # bonus_obj.deposit_bonus_per_day_limit = deposit_per_day_usage_limit if deposit_per_day_usage_limit !='' else 1
            # bonus_obj.percentage = percentage
            pass
        elif bonus_type == "welcome_bonus":
            # bonus_obj.welcome_bonus_limit = usage_limit
            pass
        elif bonus_type == "bet_bonus":
            # bonus_obj.bet_bonus_per_day_limit = bet_bonus_per_day_limit if bet_bonus_per_day_limit !='' else 1
            # bonus_obj.percentage = percentage
            # bonus_obj.bet_bonus_limit = usage_limit
            pass

        bonus_obj.save()

        if bonus_type not in ["welcome_bonus", "deposit_bonus"]:
            return self.render_json_response({"status": "success", "message": _("Bonus details saved successfully")})

        if promocode_bonus_type not in {"deposit", "mixture", "instant"}:
            return self.render_json_response({"status": "error", "message": _(f"Promo code type is not valid.")},400)

        try:
            promo_obj = PromoCodes()
            promo_obj.bonus_distribution_method = promocode_bonus_type
            promo_obj.bonus = bonus_obj
            promo_obj.promo_code = promo_code
            promo_obj.start_date = start_date
            promo_obj.end_date = end_date
            promo_obj.dealer = self.request.user

            promo_obj.is_deleted = True
            promo_obj.is_expired = True

            print(usage_limit)
            promo_obj.usage_limit = usage_limit
            promo_obj.limit_per_user = user_limit
            promo_obj.max_bonus_limit = bonus_limit

            if promocode_bonus_type == "deposit":
                promo_obj.gold_percentage = gold_percentage
                promo_obj.bonus_percentage = bonus_percentage
            elif promocode_bonus_type == "mixture":
                promo_obj.gold_bonus = instant_gold_amount
                promo_obj.bonus_percentage = bonus_percentage
            else:
                promo_obj.gold_bonus = instant_gold_amount
                promo_obj.instant_bonus_amount = instant_bonus_amount
            promo_obj.save()
        except Exception:
            bonus_obj.percentage = 0
            bonus_obj.save()
            return self.render_json_response({"status": "error", "message": _("Something Went Wrong")})

        return self.render_json_response({"status": "success", "message": _("Promo code created successfully")})


class DisableLosingBonusView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ["post"]
    allowed_roles = ("admin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        try:
            bonus_id = self.request.POST.get("bonus_id")
            promo_obj = PromoCodes.objects.get(id=bonus_id)

            promo_obj.end_date = timezone.now().date()
            promo_obj.is_expired=True
            promo_obj.is_deleted=True

            promo_obj.save()

            response = { "message":"Status changed succesfully", "status": "success" }

        except Exception as err:
            print(err)
            response = { "error": "failed" }

        return self.render_json_response(response)


class EnableBonusView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ["post"]
    allowed_roles = ("admin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        try:
            bonus_id = self.request.POST.get("bonus_id")
            promo_obj = PromoCodes.objects.get(id=bonus_id)

            promo_obj.end_date = timezone.now().date()
            promo_obj.is_expired=False
            promo_obj.is_deleted=False

            promo_obj.save()

            response = { "message":"Status changed succesfully", "status": "success" }

        except Exception as err:
            print(err)
            response = { "error": "failed" }

        return self.render_json_response(response)


class EditBonusView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)
    date_format = "%d/%m/%Y"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        bonus_id = request.POST.get("bonus_id")

        promo_code = request.POST.get("losing_promo_code")
        bonus_percentage = request.POST.get("losing_bonus_percentage")
        bonus_percentage = None if bonus_percentage in ("None", "", None) else bonus_percentage
        gold_percentage = request.POST.get("losing_gold_percentage")
        gold_percentage = None if gold_percentage in ("None", "", None) else gold_percentage
        
        start_date = request.POST.get("losing_start_time")
        end_date = request.POST.get("losing_end_time")
        bonus_type = request.POST.get("bonus_type")
        promoUsageLimit = request.POST.get("promoUsageLimit")
        user_limit = request.POST.get("promoUserLimit")
        max_bonus_limit = request.POST.get("max_bonus_limit")
        instant_gold_amount = request.POST.get("instant_gold_amount", "")
        instant_gold_amount = str(0 if instant_gold_amount in ("None", "", None) else instant_gold_amount)
        instant_bonus_amount = request.POST.get("instant_bonus_amount", "")
        instant_bonus_amount = str(0 if instant_bonus_amount in ("None", "", None) else instant_bonus_amount)

        if start_date:
            start_date = timezone.datetime.strptime(start_date, self.date_format).date()

        if end_date:
            end_date = timezone.datetime.strptime(end_date, self.date_format).date()
        
        # try:
        #     if bonus_percentage and Decimal(bonus_percentage) > 0:
        #         return self.render_json_response({"status": "error", "message": "SC are disabled please set it to set 0 to continue"}, 400)
        #     if instant_bonus_amount and Decimal(instant_bonus_amount) > 0:
        #         return self.render_json_response({"status": "error", "message": "SC are disabled please set it to set 0 to continue"}, 400)
        # except Exception:
        #     return self.render_json_response({"status": "error", "message": "Please insert valid values"}, 400)

        try:
            promo_obj = PromoCodes.objects.get(id=bonus_id)
            promo_obj.usage_limit = promoUsageLimit
            promo_obj.limit_per_user = user_limit
            promo_obj.bonus_percentage = bonus_percentage or 0
            promo_obj.gold_percentage = gold_percentage or 0
            promo_obj.end_date = end_date
            promo_obj.start_date = start_date
            promo_obj.max_bonus_limit = max_bonus_limit
            if promo_obj.bonus_distribution_method == "instant" and instant_bonus_amount.isdigit():
                promo_obj.instant_bonus_amount = instant_bonus_amount
            if promo_obj.bonus_distribution_method in {"instant", "mixture"} and instant_gold_amount.isdigit():
                promo_obj.gold_bonus = instant_gold_amount
            promo_obj.save()
            response = { "message":"Promo code updated succesfully", "status": "success" }

        except Exception as e:
            print(e)
            response = { "message":"Something went wrong", "status": "Failed" }

        return self.render_json_response(response)


class BonusPermissionView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("superadmin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        dealer = Dealer.objects.get(id=request.POST.get("dealer_id"))
        bonus_type = request.POST.get("bonus_type")
        enabled = request.POST.get("enabled")

        try:
            bonus_obj = BonusPercentage.objects.get(dealer=dealer, bonus_type=bonus_type)
        except BonusPercentage.DoesNotExist:
            bonus_obj = BonusPercentage()
            bonus_obj.percentage = 0
            bonus_obj.dealer = dealer
            bonus_obj.bonus_type = bonus_type
            bonus_obj.save()

        if bonus_type == "welcome_bonus":
            dealer.is_welcome_bonus_enabled = True if enabled == "true" else False
        elif bonus_type == "referral_bonus":
            dealer.is_referral_bonus_enabled = True if enabled == "true" else False
        elif bonus_type == "losing_bonus":
            if enabled == "true":
                dealer.is_losing_bonus_enabled = True
            else:
                dealer.is_losing_bonus_enabled = False
                losing_promo_obj = PromoCodes.objects.filter(
                    dealer=dealer,
                    is_expired=False
                )
                for obj in losing_promo_obj:
                    try:
                        obj.end_date = timezone.now().date()
                        obj.is_expired = True
                        obj.save()
                    except Exception:
                        obj.end_date = None
                        obj.is_expired = True
                        obj.save()
        dealer.save()

        if enabled == "false":
            bonus_obj.percentage = 0
            bonus_obj.save()

        return self.render_json_response({"status":"Success","message": _("Bonus permission updated")})



class SaveBetslipBonusPercentage(CheckRolesMixin, UpdateView):
    http_method_names = ["post"]
    template_name = "admin/agent/agents.html"
    allowed_roles = ("superadmin", "dealer")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post(self, request, *args, **kwargs):
        data = {k: v for k, v in request.POST.dict().items() if v}
        bet_id = data.pop("agent_id")
        agent = Agent.objects.filter(id=bet_id)[0]
        agent.betslip_bonus_percentage = data.pop("betslip_bonus_percentage")
        agent.save()
        return HttpResponseRedirect(reverse_lazy("admin-panel:agents"))

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

class SpecialAgentPermissionView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("superadmin",)
    http_method_names = ["post"]

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        admin_id = self.request.POST.get("adminID", None)
        is_special_agent_enabled = self.request.POST.get("isSpecialAgentEnabled", None)
        admin = Admin.objects.get(id=admin_id)

        if is_special_agent_enabled == "true":
            is_special_agent_enabled = True
            message = "Special Agent Enabled Successfully"
        else:
            is_special_agent_enabled = False
            agents = Agent.objects.filter(is_special_agent=True)
            for agent in agents:
                agent.is_special_agent = False
                player = Player.objects.get(agent=agent, is_special_agent=True)
                player.is_active = False
                agent.save()
                player.save()
            message = "Special Agent Disabled Successfully"


        admin.is_special_agent_enabled = is_special_agent_enabled
        admin.save()

        return self.render_json_response(
            {
                "status": "success",
                "message": _(message)
            },
            status=200
        )

class makeSpecialAgentView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin")
    http_method_names = ["post"]

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        if self.request.user.is_special_agent_enabled is True:
            agent_id = self.request.POST.get("agentId", None)
            is_special_agent = self.request.POST.get("isSpecialAgent", None)
            try:
                agent = Agent.objects.get(id=agent_id)
                if is_special_agent == "true":
                    agent.is_special_agent = True

                    player = Player.objects.filter(agent=agent, is_special_agent=True)
                    if player.exists():
                        player = player.first()
                        player.password = make_password(f"{agent.username}spplayer12345")
                        player.is_active = True
                    else:
                        player = Player()
                        player.username = f"{agent.username}spplayer"
                        player.password = make_password(f"{agent.username}spplayer12345")
                        player.currency = self.request.user.currency
                        player.timezone = self.request.user.timezone
                        player.agent = agent
                        player.dealer = agent.dealer
                        player.role = "player"
                        player.is_staff = False
                        player.is_superuser = False
                        player.is_active = True
                        player.is_special_agent = True
                        player.is_casino_enabled = False
                        player.is_live_casino_enabled = False
                        player.is_gg_slot_casino_enabled = False

                    player.save()
                    agent.save()
                    message = f"Agent {agent.username} has been successfully marked as Special Agent, Login creds for betting are:"
                    username = player.username
                    password = f"{player.username}12345"
                else:
                    agent.is_special_agent = False

                    player = Player.objects.get(agent=agent, is_special_agent=True)
                    player.is_active = False

                    player.save()
                    agent.save()
                    message = f"Agent {agent.username} has been successfully demoted as a normal agent"
                    username = None
                    password = None
            except Exception:
                return self.render_json_response(
                    {
                        "status": "Error",
                        "message": _("Something went wrong")
                    },
                    status=500
                )
            return self.render_json_response(
                {
                    "status": "Success",
                    "message": _(message),
                    "username": username,
                    "password": password
                },
                status=200
            )
        else:
            return self.render_json_response(
                {
                    "status": "error",
                    "message": _("Service not available"),
                },
                status=405
            )


class SpecialAgentLogoView(
    CheckRolesMixin, views.JSONResponseMixin,
    views.AjaxResponseMixin, View
):
    allowed_roles = ("admin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        agent_id = self.request.POST.get("agentId", "")
        logo = self.request.FILES.get("logo", None)
        logo_format = logo.name.split('.')[-1]

        if logo_format != "png":
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Logo image should be in png format")
                },
                status=400
            )

        agent = Agent.objects.filter(
            id=agent_id, is_deleted=False, is_special_agent=True
        )
        if not agent.exists():
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Agent is not a Special Agent")
                },
                status=405
            )

        special_player = Player.objects.filter(
            agent=agent.first(), is_deleted=False,
            is_active=True, is_special_agent=True
        )
        if not special_player.exists():
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Agent is not a Special Agent")
                },
                status=405
            )

        special_player = special_player.first()
        logo_filename = f"specialagentlogo/{special_player.id}.{logo_format}"
        session = boto3.Session(
            aws_access_key_id=settings.ACCESS_KEY_ID,
            aws_secret_access_key=settings.SECRET_ACCESS_KEY
        )
        s3 = session.resource("s3")

        try:
            s3.Object(
                settings.AWS_S3_BUCKET_NAME,
                logo_filename
            ).delete()
        except Exception:
            pass

        try:

            bucket = s3.Bucket(settings.AWS_S3_BUCKET_NAME)
            bucket.put_object(
                Key=logo_filename,
                Body=logo,
                ACL="public-read",
                ContentType="image/png"
            )
        except Exception as e:
            print(e)
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Unknown error, Please contact Admin")
                },
                status=500
            )


        logo = bucket.Object(logo_filename).get()
        logo = logo["Body"].read()
        return self.render_json_response(
            {
                "status": "Success",
                "message": _("Logo Uploaded Successfully"),
                "logo": base64.b64encode(logo).decode("utf-8")
            },
            status=200
        )


class SpecialAgentLogoDeleteView(CheckRolesMixin, views.JSONResponseMixin,
    views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        agent_id = self.request.POST.get("agentId")

        logo_format = 'png'

        agent = Agent.objects.filter(
            id=agent_id, is_deleted=False, is_special_agent=True
        )

        special_player = Player.objects.filter(
            agent=agent.first(), is_deleted=False,
            is_active=True, is_special_agent=True
        )
        special_player = special_player.first()
        logo_filename = f"specialagentlogo/{special_player.id}.{logo_format}"
        session = boto3.Session(
            aws_access_key_id=settings.ACCESS_KEY_ID,
            aws_secret_access_key=settings.SECRET_ACCESS_KEY
        )
        s3 = session.resource("s3")

        try:
            s3.Object(
                settings.AWS_S3_BUCKET_NAME,
                logo_filename
            ).delete()

            return self.render_json_response(
                {
                    "status": "Success",
                    "message": _("Logo Deleted Successfully")
                },
                status=200
            )

        except Exception:
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Logo not found")
                },
                status=404
            )

class GetSpecialAgentLogoView(CheckRolesMixin, views.JSONResponseMixin,
    views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        agent_id = self.request.POST.get("agentId")
        logo_format = 'png'

        agent = Agent.objects.filter(
            id=agent_id, is_deleted=False, is_special_agent=True
        )

        special_player = Player.objects.filter(
            agent=agent.first(), is_deleted=False,
            is_active=True, is_special_agent=True
        )
        special_player = special_player.first()
        logo_filename = f"specialagentlogo/{special_player.id}.{logo_format}"
        session = boto3.Session(
            aws_access_key_id=settings.ACCESS_KEY_ID,
            aws_secret_access_key=settings.SECRET_ACCESS_KEY
        )

        s3 = session.resource("s3")
        bucket = s3.Bucket(settings.AWS_S3_BUCKET_NAME)

        try:
            logo = bucket.Object(logo_filename).get()
            logo = logo["Body"].read()
            return self.render_json_response(
                {
                    "status": "Success",
                    "logo": base64.b64encode(logo).decode("utf-8"),
                    "agentId": agent_id  
                    },
                    status=200
            )
        except Exception:
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Logo not found")
                },
                status=200
            )

class AdminBetslipBonusPermissionAjax(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = "superadmin"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):

        admin_id = request.POST.get("admin_id")
        betslip_bonus_enabled = request.POST.get("betslip_bonus_enabled", None)
        if betslip_bonus_enabled and admin_id:
            admin = Admin.objects.get(pk=admin_id)

            if betslip_bonus_enabled == "false":
                admin.is_betslip_bonus_enabled = False
            elif betslip_bonus_enabled == "true":
                admin.is_betslip_bonus_enabled = True
            admin.save()

        return self.render_json_response({"status": "Success", "message": "Betslip Bonus Permission Successfuly Changed"})


class ChangeAgentBetslipBonusAjax(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = "dealer"

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def post_ajax(self, request, *args, **kwargs):

        agent_id = request.POST.get("agent_id")
        betslip_bonus_enabled = request.POST.get("betslip_bonus_enabled", None)

        if betslip_bonus_enabled and agent_id:
            agent = Agent.objects.get(pk=agent_id)
            if betslip_bonus_enabled == "false":
                agent.is_betslip_bonus_enabled = False
            elif betslip_bonus_enabled == "true":
                agent.is_betslip_bonus_enabled = True
            agent.save()

        return self.render_json_response({"status": "Success", "message": "ImprtantMatches Bonus Permission Successfuly Changed"})



class SetCashbackView(CheckRolesMixin, UpdateView):
    allowed_roles = ("admin")
    template_name = "admin/agent/agents.html"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post(self, request, *args, **kwargs):
        dealer_id = request.POST.get("dealer_id", None)
        cashback_percentage = request.POST.get("cashback_percentage", None)
        cashback_time_limit = request.POST.get("cashback_time_limit", None)

        try:
            dealer = Dealer.objects.get(id=dealer_id)

            if Decimal(cashback_percentage) < 0:
                return self.render_json_response({
                    "status": "error",
                    "message": _("Cashback Percentage should not be less than zero")
                }, status=400)

            if int(cashback_time_limit) < 24:
                return self.render_json_response({
                    "status": "error",
                    "message": _("Cashback Time Limit should not be less than 24hrs")
                }, status=400)

            if dealer.cashback_status:
                dealer.cashback_percentage = cashback_percentage
                dealer.cashback_time_limit = cashback_time_limit
                dealer.save()


                return HttpResponseRedirect(reverse_lazy("admin-panel:dealers"))

            else:
                return HttpResponseRedirect(reverse_lazy("admin-panel:dealers"))

        except Exception:
            return HttpResponseRedirect(reverse_lazy("admin-panel:dealers"))


    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class AdminBannersView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ["admin", ]
    template_name = "admin/banner.html"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request):
        try:
            admin_id = self.request.user.id if request.user.role == 'admin' else self.request.user.admin.id
            admin_banners = AdminBanner.objects.filter(admin_id=admin_id).order_by("-created")
            return render(request, template_name=self.template_name,
                            context={
                                "admin_banners": admin_banners,
                                "admin": admin_id,
                            })
        except Exception as e:
            print(e)
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateAdminBannerView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ["admin", "superadmin",]
    template_name = "admin/create_banner.html"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request):
        try:
            admin_id = self.request.user.id if request.user.role == 'admin' else self.request.user.admin.id
            form = AdminBannerForm()
            desktop_homepage_banner_count = AdminBanner.objects.filter(admin_id=admin_id,banner_type="HOMEPAGE",banner_category="DESKTOP").count()
            desktop_betslip_banner_count = AdminBanner.objects.filter(admin_id=admin_id,banner_type="BETSLIP",banner_category="DESKTOP").count()
            mobile_homepage_banner_count = AdminBanner.objects.filter(admin_id=admin_id,banner_type="HOMEPAGE",banner_category="MOBILE_RESPONSIVE").count()
            mobile_betslip_banner_count = AdminBanner.objects.filter(admin_id=admin_id,banner_type="BETSLIP",banner_category="MOBILE_RESPONSIVE").count()
            mobile_app_homepage_banner_count = AdminBanner.objects.filter(admin_id=admin_id,banner_type="HOMEPAGE",banner_category="MOBILE_APP").count()
            mobile_app_betslip_banner_count = AdminBanner.objects.filter(admin_id=admin_id,banner_type="BETSLIP",banner_category="MOBILE_APP").count()


            return render(request, template_name=self.template_name,
                            context={"form": form,
                                    "admin": admin_id ,
                                    "desktop_homepage_banner_count":desktop_homepage_banner_count,
                                    "desktop_betslip_banner_count": desktop_betslip_banner_count,
                                    "mobile_homepage_banner_count": mobile_homepage_banner_count,
                                    "mobile_betslip_banner_count":mobile_betslip_banner_count,
                                    "mobile_app_homepage_banner_count": mobile_app_homepage_banner_count,
                                    "mobile_app_betslip_banner_count": mobile_app_betslip_banner_count,
                            })
        except Exception as e:
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            form = AdminBannerForm(request.POST, request.FILES)
            banner = request.FILES.get('banner')
            admin_id = self.request.user.id if request.user.role == 'admin' else self.request.user.admin.id
            if form.is_valid():
                filename_format = banner.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                banner_thumbnail = Image.open(banner)
                banner_thumbnail.thumbnail((100, 100))
                banner_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                banner_thumbnail.save(banner_thumbnail_io, format=format,filename=filename)
                banner_thumbnail_inmemory = InMemoryUploadedFile(banner_thumbnail_io,
                                                                'FileField',
                                                                    filename,
                                                                    format,
                                                                    sys.getsizeof(banner_thumbnail_io), None)
                banner.name = filename
                banner_category = request.POST.get('banner_category')
                banner_content = request.POST.get('banner_content')
                banner_header = request.POST.get('banner_header')
                admin_banner = AdminBanner(admin_id=admin_id,
                                            banner=banner,
                                            title=form.cleaned_data['title'],
                                            banner_type=form.cleaned_data['banner_type'],
                                            banner_thumbnail = banner_thumbnail_inmemory,
                                            banner_category = banner_category,
                                            header = banner_header,
                                            content = banner_content,
                                            redirect_url = form.cleaned_data['redirect_url'],
                                            button_text = form.cleaned_data['button_text'],
                                            )
                admin_banner.save()
                messages.success(request, "Banner created successfully")
                return redirect('admin-panel:admin-banner')

            messages.error(request, _("Please provide valid banner details!"))
            return redirect('admin-panel:create-admin-banner')

        except Exception as e:
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeleteAdminBanner(CheckRolesMixin, views.JSONResponseMixin,
                                 views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        banner_id = self.request.POST.get("banner_id")
        try:
            banner = AdminBanner.objects.get(id=banner_id)
            banner.delete()
            return self.render_json_response(
                {
                    "status": "Success",
                    "message": _("Banner Deleted Successfully")
                },
                status=200
            )

        except Exception as e:
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Banner not found")
                },
                status=404
            )


class AffiliatePLayerPermission(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("superadmin", "admin", "dealer")
    http_method_names = ["post"]

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        user_id = self.request.POST.get("user_id", None)
        is_affiliate_player_enabled = self.request.POST.get("is_affiliate_player_enabled", None)
        user_obj = Users.objects.get(id=user_id)

        if is_affiliate_player_enabled == "true":
            is_affiliate_player_enabled = True
            message = "Affiliate PLayer Enabled Successfully"
        else:
            is_affiliate_player_enabled = False
            message = "Affiliate PLayer  Disabled Successfully"
        user_obj.is_affiliate_player_enabled = is_affiliate_player_enabled
        user_obj.save()
        return self.render_json_response(
            {
                "status": "success",
                "message": _(message)
            },
            status=200
        )


class CMSAboutView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/crm_cms/cms_about.html"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        about_detail = CmsAboutDetails.objects.first()
        form = AboutForm(instance=about_detail)
        banner_thumbnail = about_detail.banner_thumbnail if about_detail else ''
        return render(request, template_name=self.template_name,
                      context={"banner_thumbnail": banner_thumbnail,
                               "form": form}
                      )

    def post(self, request, *args, **kwargs):
        try:
            if not request.POST.get("title"):
                return self.render_json_response({"status": "error", "message": "Title should not be empty"})

            banner = request.FILES.get('banner')
            cms_obj = CmsAboutDetails.objects.first()
            if not cms_obj:
                cms_obj = CmsAboutDetails()
            if banner:
                filename_format = banner.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                banner_thumbnail = Image.open(banner)
                banner_thumbnail.thumbnail((750, 400))
                banner_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                banner_thumbnail.save(banner_thumbnail_io, format=format, filename=filename)
                banner_thumbnail_inmemory = InMemoryUploadedFile(banner_thumbnail_io,
                                                                 'FileField',
                                                                 filename,
                                                                 format,
                                                                 sys.getsizeof(banner_thumbnail_io), None)
                banner.name = filename
                cms_obj.banner_thumbnail = banner_thumbnail_inmemory
                cms_obj.banner = banner
            cms_obj.title = request.POST.get("title")
            cms_obj.more_info = request.POST.get("more_info")
            cms_obj.page_content = request.POST.get("page_content")
            cms_obj.save()
            messages.success(request, "Page content stored successfully")
        except Exception as e:
            print(e)
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:cms-about')


class CMSContactView(CheckRolesMixin, ListView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    model = CmsContactDetails
    paginate_by = 7
    template_name = "admin/crm_cms/cms_contact.html"
    allowed_roles = ("admin", "superadmin")
    context_object_name = "contact_datails"
    queryset = CmsContactDetails.objects.all().order_by("status")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_queryset(self):
        subject_content = self.request.GET.get("subject_content", None)
        if subject_content:
            self.queryset = self.queryset.filter(email__icontains=subject_content)
        return self.queryset

    def get_context_data(self, **kwargs):
        subject_search = self.request.GET.get("subject_content", None)
        context = super().get_context_data(**kwargs)
        if subject_search:
            context["subject_content"] = subject_search
        return context

    def post_ajax(self, request, *args, **kwargs):
        try:
            contact_id = request.POST.get("contact_id")

            contact_obj = CmsContactDetails.objects.get(id=contact_id)
            if request.POST.get("is_change_status") == "true":
                if contact_obj.status == "Active":
                    contact_obj.status = "Resolved"
                else:
                    contact_obj.status = "Active"
                contact_obj.save()
                return self.render_json_response({"status": "Success", "message": "Status Changed Sucessfully"}, 200)
            elif request.POST.get("is_delete") == "true":
                contact_obj.delete()
                return self.render_json_response({"status": "Success", "message": "Deleted Sucessfully"}, 200)
        except:
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})


class CMSPromotionView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/crm_cms/cms_promotion.html"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        promotion_detail = CmsPromotionDetails.objects.first()
        banner_thumbnail = promotion_detail.banner_thumbnail if promotion_detail else ''
        form = PromotionForm(instance=promotion_detail)
        return render(request, template_name=self.template_name,
                      context={"banner_thumbnail": banner_thumbnail,
                               "form": form}
                      )

    def post(self, request, *args, **kwargs):
        try:
            form = PromotionForm(request.POST, request.FILES)
            if not request.POST.get("title"):
                return self.render_json_response({"status": "error", "message": "Title should not be empty"})
            banner = request.FILES.get('banner')
            cms_obj = CmsPromotionDetails.objects.first()
            if not cms_obj:
                cms_obj = CmsPromotionDetails()
            if banner:
                filename_format = banner.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                banner_thumbnail = Image.open(banner)
                banner_thumbnail.thumbnail((750, 400))
                banner_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                banner_thumbnail.save(banner_thumbnail_io, format=format, filename=filename)
                banner_thumbnail_inmemory = InMemoryUploadedFile(banner_thumbnail_io,
                                                                 'FileField',
                                                                 filename,
                                                                 format,
                                                                 sys.getsizeof(banner_thumbnail_io), None)
                banner.name = filename
                cms_obj.banner_thumbnail = banner_thumbnail_inmemory
                cms_obj. banner = banner
            cms_obj.title = request.POST.get("title")
            cms_obj.more_info = request.POST.get("more_info")
            cms_obj.page_content = request.POST.get("page_content")
            cms_obj.save()
            messages.success(request, "Page content stored successfully")
        except Exception as e:
            print(e)
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:cms-promotions')


class CRMView(CheckRolesMixin, ListView):
    model = CrmDetails
    date_format = "%d/%m/%Y"
    template_name = "admin/crm_cms/crm.html"
    allowed_roles = ("admin", "superadmin")
    context_object_name = "crm_templates"
    queryset = CrmDetails.objects.all()

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_queryset(self):
        subject_search = self.request.GET.get("subject_content",None)
        status = self.request.GET.get("status",None)
        notification_category  = self.request.GET.get('notification_category',None)
        if subject_search:
            self.queryset = self.queryset.filter(subject__icontains=subject_search)
        if status:
            self.queryset = self.queryset.filter(status=status)
        if notification_category:
            self.queryset = self.queryset.filter(category=notification_category)

        if self.request.GET.get("to") and self.request.GET.get("from"):
            to_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
            from_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
            self.queryset = self.queryset.filter(scheduled_at__range=[from_date, to_date])

        return self.queryset

    def get_context_data(self, **kwargs):
        subject_search = self.request.GET.get("subject_content", None)
        status = self.request.GET.get("status",None)
        notification_category  = self.request.GET.get('notification_category',None)

        # current_date = timezone.now()
        # first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

        context = super().get_context_data(**kwargs)
        if subject_search:
            context["subject_content"] = subject_search
        if status:
            context["status"] = status
        if notification_category:
            context["notification_category"] = notification_category

        # context["from"] = self.request.GET.get("from", first_day_of_month)
        # context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))
        context["from"] = self.request.GET.get("from", "")
        context["to"] = self.request.GET.get("to", "")


        return context


class SMSView(CheckRolesMixin, ListView):
    model = SMSDetails
    date_format = "%d/%m/%Y"
    template_name = "admin/crm_cms/sms.html"
    allowed_roles = ("admin", "superadmin")
    context_object_name = "crm_templates"
    queryset = SMSDetails.objects.all()

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_queryset(self):
        subject_search = self.request.GET.get("subject_content",None)
        status = self.request.GET.get("status",None)
        if subject_search:
            self.queryset = self.queryset.filter(subject__icontains=subject_search)
        if status:
            self.queryset = self.queryset.filter(status=status)

        if self.request.GET.get("to") and self.request.GET.get("from"):
            to_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
            from_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
            self.queryset = self.queryset.filter(scheduled_at__range=[from_date, to_date])

        return self.queryset

    def get_context_data(self, **kwargs):
        subject_search = self.request.GET.get("subject_content", None)
        status = self.request.GET.get("status",None)

        # current_date = timezone.now()
        # first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

        context = super().get_context_data(**kwargs)
        if subject_search:
            context["subject_content"] = subject_search
        if status:
            context["status"] = status

        # context["from"] = self.request.GET.get("from", first_day_of_month)
        # context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))
        context["from"] = self.request.GET.get("from", "")
        context["to"] = self.request.GET.get("to", "")


        return context


class CreateCrmTemplateView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/crm_cms/create_crm_template.html"
    date_format = "%d/%m/%Y %H:%M"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        try:
            subject = request.POST.get("subject", None)
            category = request.POST.get("category", None)
            emails = request.POST.get("emails", None)
            scheduled_at = request.POST.get("scheduled_at", None)
            content = request.POST.get("content", None)
            if not (subject and category and scheduled_at and content):
                return self.render_json_response({"status": "error", "message": "All Fields Required"})
            crm_obj = CrmDetails()
            if emails:
                crm_obj.emails = emails
            else:
                crm_obj.emails = None
            crm_obj.subject = subject
            crm_obj.category = category
            crm_obj.scheduled_at = datetime.strptime(scheduled_at, self.date_format)
            crm_obj.content = content
            crm_obj.status = "Active"
            crm_obj.save()

            return self.render_json_response({"status": "Success", "message": "Success"})

        except Exception as e:
            print("Exception in Create CRM: ",e)
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})


class CreateSMSTemplateView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/crm_cms/create_sms_template.html"
    date_format = "%d/%m/%Y %H:%M"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        try:
            subject = request.POST.get("subject", None)
            phone_numbers = request.POST.get("phone_numbers", None)
            scheduled_at = request.POST.get("scheduled_at", None)
            content = request.POST.get("content", None)
            if not (subject and scheduled_at and content):
                return self.render_json_response({"status": "error", "message": "All Fields Required"})
            sms_obj = SMSDetails()
            if phone_numbers:
                sms_obj.phone_number = phone_numbers
            else:
                sms_obj.phone_number = None
            sms_obj.subject = subject
            sms_obj.scheduled_at = datetime.strptime(scheduled_at, self.date_format)
            sms_obj.content = content
            sms_obj.status = "Active"
            sms_obj.save()

            return self.render_json_response({"status": "Success", "message": "Success"})

        except Exception as e:
            print("Exception in Create SMS: ",e)
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})


class ManageCrmTemplateAjax(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "superadmin")

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        try:
            template_id = request.POST.get("template_id")
            template_obj = CrmDetails.objects.get(id=template_id)
            response_msg = ""
            if request.POST.get("is_change_status") == "true":
                if template_obj.status == "Active":
                    template_obj.status = "Inactive"
                    response_msg = "Status has changed successfully from Active to Inactive"
                else:
                    template_obj.status = "Active"
                    response_msg = "Status has changed successfully from Inactive to Active"
                template_obj.save()
                return self.render_json_response({"status": "Success", "message":response_msg}, 200)
            elif request.POST.get("is_delete") == "true":
                template_obj.delete()
                response_msg = "Deleted Sucessfully"
                return self.render_json_response({"status": "Success", "message": response_msg}, 200)
        except:
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})


class ManageSMSTemplateAjax(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "superadmin")

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        try:
            template_id = request.POST.get("template_id")
            template_obj = SMSDetails.objects.get(id=template_id)
            response_msg = ""
            if request.POST.get("is_change_status") == "true":
                if template_obj.status == "Active":
                    template_obj.status = "Inactive"
                    response_msg = "Status has changed successfully from Active to Inactive"
                else:
                    template_obj.status = "Active"
                    response_msg = "Status has changed successfully from Inactive to Active"
                template_obj.save()
                return self.render_json_response({"status": "Success", "message":response_msg}, 200)
            elif request.POST.get("is_delete") == "true":
                template_obj.delete()
                response_msg = "Deleted Sucessfully"
                return self.render_json_response({"status": "Success", "message": response_msg}, 200)
        except:
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})


class EditCrmTemplateAjax(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/crm_cms/edit_crm_template.html"
    allowed_roles = ("admin", "superadmin")
    date_format = "%d/%m/%Y %H:%M"
    context_object_name = "crm_template"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_context_data(self, **kwargs):
        template_id = self.request.GET.get("template_id", "")
        context = super().get_context_data(**kwargs)
        crm_obj = CrmDetails.objects.get(id=template_id)
        context["subject"] = crm_obj.subject
        context["category"] = crm_obj.category
        UTC_OFFSET_TIMEDELTA = datetime.utcnow() - datetime.now()
        context["scheduled_at"] = (crm_obj.scheduled_at - UTC_OFFSET_TIMEDELTA).strftime(self.date_format)
        context["content"] = crm_obj.content
        context["status"] = crm_obj.status
        context["template_id"] = crm_obj.id
        if crm_obj.emails:
            context["emails"] = crm_obj.emails
        return context

    def post_ajax(self, request, *args, **kwargs):
        try:
            subject = request.POST.get("subject", None)
            category = request.POST.get("category", None)
            emails = request.POST.get("emails", None)
            scheduled_at = request.POST.get("scheduled_at", None)
            content = request.POST.get("content", None)
            template_id = request.POST.get("template_id", None)
            scheduled_date = datetime.strptime(scheduled_at, "%d/%m/%Y %H:%M")
            present = datetime.now()
            if scheduled_date < present:
                return self.render_json_response({"status": "error", "message": "You cannot select a date and time in the past!"})

            crm_obj = CrmDetails.objects.filter(id=template_id).first()
            if not crm_obj:
                return self.render_json_response({"status": "error", "message": "Something Went Wrong"})
                
            if emails:
                crm_obj.emails = emails
            else:
                crm_obj.emails = None
            crm_obj.subject = subject
            crm_obj.category = category
            crm_obj.scheduled_at = datetime.strptime(scheduled_at, self.date_format)
            crm_obj.content = content
            crm_obj.status = "Active"
            crm_obj.save()

            return self.render_json_response({"status": "Success", "message": "Success"})

        except Exception as e:
            print("Exception in EditCrmTemplateAjax :", e)
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})


class EditSMSTemplateAjax(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/crm_cms/edit_sms_template.html"
    allowed_roles = ("admin", "superadmin")
    date_format = "%d/%m/%Y %H:%M"
    context_object_name = "crm_template"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_context_data(self, **kwargs):
        template_id = self.request.GET.get("template_id", "")
        context = super().get_context_data(**kwargs)
        crm_obj = SMSDetails.objects.get(id=template_id)
        context["subject"] = crm_obj.subject
        UTC_OFFSET_TIMEDELTA = datetime.utcnow() - datetime.now()
        context["scheduled_at"] = (crm_obj.scheduled_at - UTC_OFFSET_TIMEDELTA).strftime(self.date_format)
        context["content"] = crm_obj.content
        context["status"] = crm_obj.status
        context["template_id"] = crm_obj.id
        if crm_obj.phone_number:
            context["phone_number"] = crm_obj.phone_number
        return context

    def post_ajax(self, request, *args, **kwargs):
        try:
            subject = request.POST.get("subject", None)
            phone_number = request.POST.get("phone_number", None)
            scheduled_at = request.POST.get("scheduled_at", None)
            content = request.POST.get("content", None)
            template_id = request.POST.get("template_id", None)
            scheduled_date = datetime.strptime(scheduled_at, "%d/%m/%Y %H:%M")
            present = datetime.now()
            if scheduled_date < present:
                return self.render_json_response({"status": "error", "message": "You cannot select a date and time in the past!"})

            crm_obj = SMSDetails.objects.filter(id=template_id).first()
            if phone_number:
                crm_obj.phone_number = phone_number
            else:
                crm_obj.phone_number = None
            crm_obj.subject = subject
            crm_obj.scheduled_at = datetime.strptime(scheduled_at, self.date_format)
            crm_obj.content = content
            crm_obj.status = "Active"
            crm_obj.save()

            return self.render_json_response({"status": "Success", "message": "Success"})

        except Exception as e:
            print("Exception in EditCrmTemplateAjax :", e)
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})


class SendTemplateAjax(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        try:
            template_id = self.request.POST.get("template_id")
            email_template_crm.delay(template_id)
            return self.render_json_response({"status": "Success", "message": "Notification has sent to users email address"})

        except Exception as e:
            print("Exception in SendTemplateAjax :", e)
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})


class SendSMSTemplateAjax(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        try:
            template_id = self.request.POST.get("template_id")
            send_sms_crm.delay(template_id)
            return self.render_json_response({"status": "Success", "message": "Notification has sent to users phone number"})

        except Exception as e:
            print("Exception in SendTemplateAjax :", e)
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})



class CMSPrivacyPolicyView(CheckRolesMixin, TemplateView, View):
    template_name = "admin/crm_cms/cms_privacy_policy.html"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        promotion_detail = CmsPrivacyPolicy.objects.first()
        banner_thumbnail = promotion_detail.banner_thumbnail if promotion_detail else ''
        form = PrivacyPolicyForm(instance=promotion_detail)
        return render(request, template_name=self.template_name,
                      context={"banner_thumbnail": banner_thumbnail,
                               "form": form,
                               "privacy_policy":"PrivacyPolicy"}
                      )

    def post(self, request, *args, **kwargs):
        try:
            form = PrivacyPolicyForm(request.POST, request.FILES)
            if not request.POST.get("title"):
                return self.render_json_response({"status": "error", "message": "Title should not be empty"})
            banner = request.FILES.get('banner')
            cms_obj = CmsPrivacyPolicy.objects.first()
            if not cms_obj:
                cms_obj = CmsPrivacyPolicy()
            if banner:
                filename_format = banner.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                banner_thumbnail = Image.open(banner)
                banner_thumbnail.thumbnail((750, 400))
                banner_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                banner_thumbnail.save(banner_thumbnail_io, format=format, filename=filename)
                banner_thumbnail_inmemory = InMemoryUploadedFile(banner_thumbnail_io,
                                                                 'FileField',
                                                                 filename,
                                                                 format,
                                                                 sys.getsizeof(banner_thumbnail_io), None)
                banner.name = filename
                cms_obj.banner_thumbnail = banner_thumbnail_inmemory
                cms_obj. banner = banner
            cms_obj.title = request.POST.get("title")
            cms_obj.more_info = request.POST.get("more_info")
            cms_obj.page_content = request.POST.get("page_content")
            cms_obj.save()
            messages.success(request, "Page content stored successfully")
        except Exception as e:
            print(e)
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:cms-privacy-policy')


class CmsFAQView(CheckRolesMixin, TemplateView, View):
    template_name = "admin/crm_cms/cms_faq.html"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        promotion_detail = CmsFAQ.objects.first()
        banner_thumbnail = promotion_detail.banner_thumbnail if promotion_detail else ''
        form = FAQForm(instance=promotion_detail)
        return render(request, template_name=self.template_name,
                      context={"banner_thumbnail": banner_thumbnail,
                               "form": form,
                               "privacy_policy":"PrivacyPolicy"}
                      )

    def post(self, request, *args, **kwargs):
        try:
            form = FAQForm(request.POST, request.FILES)
            if not request.POST.get("title"):
                return self.render_json_response({"status": "error", "message": "Title should not be empty"})
            banner = request.FILES.get('banner')
            cms_obj = CmsFAQ.objects.first()
            if not cms_obj:
                cms_obj = CmsFAQ()
            if banner:
                filename_format = banner.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                banner_thumbnail = Image.open(banner)
                banner_thumbnail.thumbnail((750, 400))
                banner_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                banner_thumbnail.save(banner_thumbnail_io, format=format, filename=filename)
                banner_thumbnail_inmemory = InMemoryUploadedFile(banner_thumbnail_io,
                                                                 'FileField',
                                                                 filename,
                                                                 format,
                                                                 sys.getsizeof(banner_thumbnail_io), None)
                banner.name = filename
                cms_obj.banner_thumbnail = banner_thumbnail_inmemory
                cms_obj. banner = banner
            cms_obj.title = request.POST.get("title")
            cms_obj.more_info = request.POST.get("more_info")
            cms_obj.page_content = request.POST.get("page_content")
            cms_obj.save()
            messages.success(request, "Page content stored successfully")
        except Exception as e:
            print(e)
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:cms-faq')


class TermsConditinosView(CheckRolesMixin, TemplateView, View):
    template_name = "admin/crm_cms/cms_terms_and_conditions.html"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        promotion_detail = TermsConditinos.objects.first()
        banner_thumbnail = promotion_detail.banner_thumbnail if promotion_detail else ''
        form = TermsConditinosForm(instance=promotion_detail)
        return render(request, template_name=self.template_name,
                      context={"banner_thumbnail": banner_thumbnail,
                               "form": form,
                               "privacy_policy":"PrivacyPolicy"}
                      )

    def post(self, request, *args, **kwargs):
        try:
            form = TermsConditinosForm(request.POST, request.FILES)
            if not request.POST.get("title"):
                return self.render_json_response({"status": "error", "message": "Title should not be empty"})
            banner = request.FILES.get('banner')
            cms_obj = TermsConditinos.objects.first()
            if not cms_obj:
                cms_obj = TermsConditinos()
            if banner:
                filename_format = banner.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                banner_thumbnail = Image.open(banner)
                banner_thumbnail.thumbnail((750, 400))
                banner_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                banner_thumbnail.save(banner_thumbnail_io, format=format, filename=filename)
                banner_thumbnail_inmemory = InMemoryUploadedFile(banner_thumbnail_io,
                                                                 'FileField',
                                                                 filename,
                                                                 format,
                                                                 sys.getsizeof(banner_thumbnail_io), None)
                banner.name = filename
                cms_obj.banner_thumbnail = banner_thumbnail_inmemory
                cms_obj. banner = banner
            cms_obj.title = request.POST.get("title")
            cms_obj.more_info = request.POST.get("more_info")
            cms_obj.page_content = request.POST.get("page_content")
            cms_obj.save()
            messages.success(request, "Page content stored successfully")
        except Exception as e:
            print(e)
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:cms-terms-conditinos')



class CookiePolicyView(CheckRolesMixin, TemplateView, View):
    template_name = "admin/crm_cms/cms_cookies_policy.html"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        promotion_detail = CookiePolicy.objects.first()
        banner_thumbnail = promotion_detail.banner_thumbnail if promotion_detail else ''
        form = CookiePolicyForm(instance=promotion_detail)
        return render(request, template_name=self.template_name,
                      context={"banner_thumbnail": banner_thumbnail,
                               "form": form,
                               "privacy_policy":"PrivacyPolicy"}
                      )

    def post(self, request, *args, **kwargs):
        try:
            form = CookiePolicyForm(request.POST, request.FILES)
            if not request.POST.get("title"):
                return self.render_json_response({"status": "error", "message": "Title should not be empty"})
            banner = request.FILES.get('banner')
            cms_obj = CookiePolicy.objects.first()
            if not cms_obj:
                cms_obj = CookiePolicy()
            if banner:
                filename_format = banner.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                banner_thumbnail = Image.open(banner)
                banner_thumbnail.thumbnail((750, 400))
                banner_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                banner_thumbnail.save(banner_thumbnail_io, format=format, filename=filename)
                banner_thumbnail_inmemory = InMemoryUploadedFile(banner_thumbnail_io,
                                                                 'FileField',
                                                                 filename,
                                                                 format,
                                                                 sys.getsizeof(banner_thumbnail_io), None)
                banner.name = filename
                cms_obj.banner_thumbnail = banner_thumbnail_inmemory
                cms_obj. banner = banner
            cms_obj.title = request.POST.get("title")
            cms_obj.more_info = request.POST.get("more_info")
            cms_obj.page_content = request.POST.get("page_content")
            cms_obj.save()
            messages.success(request, "Page content stored successfully")
        except Exception as e:
            print(e)
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:cms-cookie-policy')


class IntroductionView(CheckRolesMixin, TemplateView, View):
    template_name = "admin/crm_cms/cms_introduction.html"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        promotion_detail = Introduction.objects.first()
        banner_thumbnail = promotion_detail.banner_thumbnail if promotion_detail else ''
        form = IntroductionForm(instance=promotion_detail)
        return render(request, template_name=self.template_name,
                      context={"banner_thumbnail": banner_thumbnail,
                               "form": form,
                               "privacy_policy":"PrivacyPolicy"}
                      )

    def post(self, request, *args, **kwargs):
        try:
            form = IntroductionForm(request.POST, request.FILES)
            if not request.POST.get("title"):
                return self.render_json_response({"status": "error", "message": "Title should not be empty"})
            banner = request.FILES.get('banner')
            cms_obj = Introduction.objects.first()
            if not cms_obj:
                cms_obj = Introduction()
            if banner:
                filename_format = banner.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                banner_thumbnail = Image.open(banner)
                banner_thumbnail.thumbnail((750, 400))
                banner_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                banner_thumbnail.save(banner_thumbnail_io, format=format, filename=filename)
                banner_thumbnail_inmemory = InMemoryUploadedFile(banner_thumbnail_io,
                                                                 'FileField',
                                                                 filename,
                                                                 format,
                                                                 sys.getsizeof(banner_thumbnail_io), None)
                banner.name = filename
                cms_obj.banner_thumbnail = banner_thumbnail_inmemory
                cms_obj. banner = banner
            cms_obj.title = request.POST.get("title")
            cms_obj.more_info = request.POST.get("more_info")
            cms_obj.page_content = request.POST.get("page_content")
            cms_obj.save()
            messages.success(request, "Page content stored successfully")
        except Exception as e:
            print(e)
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:cms-introduction')


class SettingsLimitsView(CheckRolesMixin, TemplateView, View):
    template_name = "admin/crm_cms/cms_setting_limits.html"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        promotion_detail = SettingsLimits.objects.first()
        banner_thumbnail = promotion_detail.banner_thumbnail if promotion_detail else ''
        form = SettingsLimitsForm(instance=promotion_detail)
        return render(request, template_name=self.template_name,
                      context={"banner_thumbnail": banner_thumbnail,
                               "form": form,
                               "privacy_policy":"PrivacyPolicy"}
                      )

    def post(self, request, *args, **kwargs):
        try:
            form = SettingsLimitsForm(request.POST, request.FILES)
            if not request.POST.get("title"):
                return self.render_json_response({"status": "error", "message": "Title should not be empty"})
            banner = request.FILES.get('banner')
            cms_obj = SettingsLimits.objects.first()
            if not cms_obj:
                cms_obj = SettingsLimits()
            if banner:
                filename_format = banner.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                banner_thumbnail = Image.open(banner)
                banner_thumbnail.thumbnail((750, 400))
                banner_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                banner_thumbnail.save(banner_thumbnail_io, format=format, filename=filename)
                banner_thumbnail_inmemory = InMemoryUploadedFile(banner_thumbnail_io,
                                                                 'FileField',
                                                                 filename,
                                                                 format,
                                                                 sys.getsizeof(banner_thumbnail_io), None)
                banner.name = filename
                cms_obj.banner_thumbnail = banner_thumbnail_inmemory
                cms_obj. banner = banner
            cms_obj.title = request.POST.get("title")
            cms_obj.more_info = request.POST.get("more_info")
            cms_obj.page_content = request.POST.get("page_content")
            cms_obj.save()
            messages.success(request, "Page content stored successfully")
        except Exception as e:
            print(e)
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:cms-settings-limits')


class UserEmailAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "dealer", "agent", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def post_ajax(self, request, *args, **kwargs):
        search = request.POST.get("search")
        users = Player.objects.filter(email__isnull=False)
        if search:
            users = users.annotate(username_lower=Lower("username")).filter(
                username__istartswith=search.lower()
            )
        users = users.values("id", "username", "email")[0:10]
        results = []
        for user in users:
            results.append({"value": user["id"], "text": user["username"], "email": user["email"]})
        return self.render_json_response(results)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class SetPlayerBettingLimitView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):

    allowed_roles = ("admin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        max_spending_limit = int(request.POST.get("max_spending_limit", MAX_SPEND_AMOUNT))
        player_id = request.POST.get("player_id")
        try:
            player = Player.objects.filter(id=player_id).first()
            if player:
                responsible_gambling = ResponsibleGambling.objects.get_or_create(user=player)[0]

                if max_spending_limit > MAX_SPEND_AMOUNT:
                    return self.render_json_response({"status":"error","message": f"Max spending limit cannot be greater than {MAX_SPEND_AMOUNT}"}, status.HTTP_400_BAD_REQUEST)

                responsible_gambling.max_spending_limit = max_spending_limit
                responsible_gambling.daily_spendings = 0
                responsible_gambling.is_max_spending_limit_set_by_admin = True
                responsible_gambling.max_spending_limit_expire_time = datetime.now(pytz.utc)+timedelta(hours=24)

                responsible_gambling.save()
                return self.render_json_response(
                    {"status":"success","message": "Player spending limit successfully updated"},
                    status.HTTP_200_OK,
                )
            return self.render_json_response({"status":"error","message":"Player doesn't exist"}, status.HTTP_400_BAD_REQUEST, )
        except Exception as err:
            return self.render_json_response({"status":"error","message": str(err)}, status.HTTP_400_BAD_REQUEST)


class LosingBonusPermissionView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("superadmin",)

    def post_ajax(self, request, *args, **kwargs):
        admin = Admin.objects.get(id=request.POST.get("adminID"))
        bonus_type = request.POST.get("bonus_type")
        enabled = request.POST.get("isLosingBonusEnabled")

        if bonus_type == "losing_bonus":
            if enabled == "true":
                admin.is_losing_bonus_enabled = True
                message = "Losing bonus Enabled Successfully"
            else:
                admin.is_losing_bonus_enabled = False
                message = "Losing bonus Disabled Successfully"

        admin.save()

        return self.render_json_response({"status":"success","message": _(message)})


class DepositPermission(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("superadmin", "admin", "dealer")
    http_method_names = ["post"]

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        user_id = self.request.POST.get("adminID", None)
        is_deposit_bonus_enabled = self.request.POST.get("is_deposit_bonus_enabled", None)
        user_obj = Users.objects.get(id=user_id)

        if is_deposit_bonus_enabled == "true":
            is_deposit_bonus_enabled = True
            message = "Deposit Bonus Enabled Successfully"
        else:
            is_deposit_bonus_enabled = False
            message = "Deposit Bonus  Disabled Successfully"
        user_obj.is_deposit_bonus_enabled = is_deposit_bonus_enabled
        user_obj.save()
        return self.render_json_response(
            {
                "status": "success",
                "message": _(message)
            },
            status=200
        )


class DepositBonusView(CheckRolesMixin, ListView):
    """
    DepositBonusView - 
    Ref: https://trello.com/c/xoCgHWtk
    """
    template_name = "admin/bonuses/deposit_bonus.html"
    model = PromoCodes
    queryset = PromoCodes.objects.filter(bonus__bonus_type="deposit_bonus").order_by("-created").all()
    context_object_name = "bonuses"
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset


class ReferAFriendBonusPermission(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("superadmin", "admin", "dealer")
    http_method_names = ["post"]

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        user_id = self.request.POST.get("adminID", None)
        is_referral_bonus_enabled = self.request.POST.get("isReferralBonusEnabled", None)
        user_obj = Users.objects.get(id=user_id)

        if is_referral_bonus_enabled == "true":
            is_referral_bonus_enabled = True
            message = "Refer-A-Friend Bonus Enabled Successfully"
        else:
            is_referral_bonus_enabled = False
            message = "Refer-A-Friend Bonus Disabled Successfully"
        user_obj.is_referral_bonus_enabled = is_referral_bonus_enabled
        user_obj.save()
        return self.render_json_response(
            {
                "status": "success",
                "message": _(message)
            },
            status=200
        )

class BundlesAdminView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ("admin", "superadmin")
    template_name = "admin/bundles/bundles.html"

    def get(self, request):
        bundles = Bundle.objects.all().order_by("price")
        return render(request, template_name=self.template_name,
                      context={"bundles": bundles})


class BundlesAdminCreateView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ("admin", "superadmin")
    template_name = "admin/bundles/bundles_create.html"

    def get(self, request):
        return render(request, template_name=self.template_name)


class BundlesAdminEditView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ("admin", "superadmin")
    template_name = "admin/bundles/bundles_create.html"

    def get(self, request, pk):
        bundle = Bundle.objects.filter(id=pk).first()
        return render(request, template_name=self.template_name, context={"bundle": bundle})


class EnableBundleView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ["post"]

    def post_ajax(self, request, *args, **kwargs):
        try:
            if request.user.role not in ("admin", "superadmin"):
                return self.render_json_response({"message": "You are not authorized to enable bundles", "status": "error"})
            
            filters = {} if request.user.role == "superadmin" else {"admin": request.user.admin}
            bundle_id = self.request.POST.get("bundle_id")
            bundle = Bundle.objects.filter(id=bundle_id, **filters).first()
            
            if not bundle:
                return self.render_json_response({"message": "Bundle not found", "status": "error"})

            bundle.enabled = not bundle.enabled
            bundle.save()

            status_text = "Active" if bundle.enabled else "Disabled"
            response = { "message": f"Bundle status changed to {status_text}", "status": "success", "enabled": bundle.enabled }

        except Exception as err:
            print(err)
            response = { "message": str(err), "status": "error" }

        return self.render_json_response(response)


class PromotionPageView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ["admin", ]
    template_name = "admin/cms/page.html"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request):
        try:
            admin_id = self.request.user.id if request.user.role == 'admin' else self.request.user.admin.id
            admin_page = CmsPromotionDetails.objects.filter(admin_id=admin_id)
            return render(request, template_name=self.template_name,
                            context={
                                "admin_page": admin_page,
                                "admin": admin_id,
                            })
        except Exception as e:
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreatePromotionPageView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/cms/create_page.html"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        form = PromotionForm()
        return render(request, template_name=self.template_name,
                      context={"form": form}
                      )

    def post(self, request, *args, **kwargs):
        try:
            if not request.POST.get("title").strip():
                return self.render_json_response({"status": "error", "message": "Title should not be empty"})
            page = request.FILES.get('page')
            admin = self.request.user if request.user.role == 'admin' else self.request.user.admin
            page_obj = CmsPromotionDetails()
            if page:     
                filename_format = page.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                page_thumbnail = Image.open(page)
                page_thumbnail.thumbnail((750, 400))
                page_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                page_thumbnail.save(page_thumbnail_io, format=format, filename=filename)
                page_thumbnail_inmemory = InMemoryUploadedFile(page_thumbnail_io,
                                                                 'FileField',
                                                                 filename,
                                                                 format,
                                                                 sys.getsizeof(page_thumbnail_io), None)
                page.name = filename
                page_obj.page_thumbnail = page_thumbnail_inmemory
                page_obj.page = page
            page_obj.title = request.POST.get("title")
            page_obj.page_content = request.POST.get("page_content")
            page_obj.more_info = request.POST.get("more_info")
            page_obj.meta_description = request.POST.get("meta_description")
            page_obj.json_metadata = request.POST.get("json_metadata")
            page_obj.admin = admin  
            page_obj.save()
            messages.success(request, "Page content stored successfully")
        except Exception as e:
            if(type(e) != ValueError):
                messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:promotion-page')


class DeletePromotionPage(CheckRolesMixin, views.JSONResponseMixin,
                                 views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        page_id = self.request.POST.get("page_id")
        try:
            page = CmsPromotionDetails.objects.get(id=page_id)
            page.delete()
            return self.render_json_response(
                {
                    "status": "Success",
                    "message": _("Page Deleted Successfully")
                },
                status=200
            )

        except Exception as e:
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Logo not found")
                },
                status=404
            )


class EditPromotionPageAjax(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/cms/edit_page_template.html"
    allowed_roles = ("admin", "superadmin")
    date_format = "%d/%m/%Y %H:%M"
    context_object_name = "crm_template"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def get(self, request, *args, **kwargs):
        template_id = self.request.GET.get("template_id", "")
        about_detail = CmsPromotionDetails.objects.get(id=template_id)
        form = PromotionForm(instance=about_detail)
        banner_thumbnail = about_detail.page_thumbnail if about_detail else ''

        return render(request, template_name=self.template_name,
                      context={"page_thumbnail": banner_thumbnail,
                               "form": form, 
                               "title" : about_detail.title,
                               "page" : about_detail.page,
                               "page_thumbnail" : about_detail.page_thumbnail,
                               "page_content" : about_detail.page_content,
                               "template_id" : about_detail.id}
                      )

    def post(self, request, *args, **kwargs):
        try:
            title = request.POST.get("title", None)
            page = request.FILES.get('page', None)
            page_content = request.POST.get("page_content", None)
            template_id = request.GET.get('template_id', None)
            page_obj = CmsPromotionDetails.objects.filter(id=template_id).first()
            if page:
                filename_format = page.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                page_thumbnail = Image.open(page)
                page_thumbnail.thumbnail((750, 400))
                page_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                page_thumbnail.save(page_thumbnail_io, format=format, filename=filename)
                page_thumbnail_inmemory = InMemoryUploadedFile(page_thumbnail_io,
                                                                 'FileField',
                                                                 filename,
                                                                 format,
                                                                 sys.getsizeof(page_thumbnail_io), None)
                page.name = filename
                page_obj.page_thumbnail = page_thumbnail_inmemory
                page_obj.page = page
            page_obj.title = title
            page_obj.page_content = page_content
            page_obj.more_info = request.POST.get("more_info")
            page_obj.meta_description = request.POST.get("meta_description")
            page_obj.json_metadata = request.POST.get("json_metadata")
            page_obj.save()
            messages.success(request, "Page content updated successfully")

        except Exception as e:
            if(type(e) != ValueError):
                messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:promotion-page')


class CmsPromotionsView(CheckRolesMixin, TemplateView):
    allowed_roles = ["admin"]
    template_name = "admin/cms/promotion.html"
    context_object_name = "promotions"

    def get_context_data(self, **kwargs):
        # Always call super() first
        context = super().get_context_data(**kwargs)
        # Add your promotions queryset
        context['promotions'] = CmsPromotions.objects.all().order_by('-created')
        return context


class CmsPromotionsBaseView(CheckRolesMixin, TemplateView):
    """Shared helpers for create/edit views."""
    template_name = "admin/cms/promotion_form.html"
    allowed_roles = ("admin", "superadmin")

    def get_form_class(self, promotion_type=None):
        if promotion_type == "toaster":
            return ToasterCmsPromotionsForm
        elif promotion_type == "page_blocker":
            return PageBlockerCmsPromotionsForm
        return ToasterCmsPromotionsForm

    def save_image_thumbnail(self, image_file):
        """Resize and return thumbnail InMemoryUploadedFile."""
        filename_format = image_file.name.split(".")
        name, ext = filename_format[-2], filename_format[-1]
        filename = f"{name}{uuid.uuid4()}.{ext}"
        thumb = Image.open(image_file)
        thumb.thumbnail((750, 400))
        thumb_io = BytesIO()
        fmt = "JPEG" if ext.lower() == "jpg" else ext.upper()
        thumb.save(thumb_io, format=fmt)
        return InMemoryUploadedFile(
            thumb_io, "ImageField", filename, fmt, sys.getsizeof(thumb_io), None
        )


class CmsPromotionsCreateView(CmsPromotionsBaseView, View):
    def get(self, request, *args, **kwargs):
        typef = self.request.GET.get("type") or ""
        typef = typef if typef == "page_blocker" else "toaster"
        form = self.get_form_class(typef)
        return render(request, self.template_name, {"form": form})

    def post(self, request, *args, **kwargs):
        promotion_type = request.POST.get("type")
        FormClass = self.get_form_class(promotion_type)
        form = FormClass(request.POST, request.FILES)
        if form.is_valid():
            promo = form.save(commit=False)
            if promo.type == "toaster" and request.FILES.get("image"):
                promo.image = self.save_image_thumbnail(request.FILES["image"])
            promo.save()
            messages.success(request, "CmsPromotions created successfully.")
            return redirect("admin-panel:cms-promotions")
        messages.error(request, "Please correct the errors below.")
        return render(request, self.template_name, {"form": form})
        

class CmsPromotionsEditView(CmsPromotionsBaseView, View):
    def get(self, request, pk, *args, **kwargs):
        promotion = get_object_or_404(CmsPromotions, pk=pk)
        FormClass = self.get_form_class(promotion.type)
        form = FormClass(instance=promotion)
        return render(request, self.template_name, {"form": form, "promotion": promotion})

    def post(self, request, pk, *args, **kwargs):
        promotion = get_object_or_404(CmsPromotions, pk=pk)
        FormClass = self.get_form_class(promotion.type)
        form = FormClass(request.POST, request.FILES, instance=promotion)
        if form.is_valid():
            promo = form.save(commit=False)
            if promo.type == "toaster" and request.FILES.get("image"):
                promo.image = self.save_image_thumbnail(request.FILES["image"])
            promo.save()
            messages.success(request, "CmsPromotions updated successfully.")
            return redirect("admin-panel:cms-promotions")
        messages.error(request, "Please correct the errors below.")
        return render(request, self.template_name, {"form": form, "promotion": promotion})


class CmsPromotionsToggleDisableView(View):
    """Toggle disabled flag."""
    def post(self, request, pk, *args, **kwargs):
        promotion = get_object_or_404(CmsPromotions, pk=pk)
        promotion.disabled = not promotion.disabled
        promotion.save(update_fields=["disabled"])
        text = "disabled" if promotion.disabled else "enabled"
        messages.success(request, f"CmsPromotions '{promotion.title}' {text}.")
        return redirect("admin-panel:cms-promotions")



class EditAdminBannerView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/edit_admin_banner.html"
    allowed_roles = ("admin", "superadmin")
    date_format = "%d/%m/%Y %H:%M"
    context_object_name = "banner"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def get(self, request, *args, **kwargs):
        banner_id = self.request.GET.get("banner_id", "")
        admin_banner = AdminBanner.objects.get(id=banner_id)
        admin_id = self.request.user.id if request.user.role == 'admin' else self.request.user.admin.id
        form = AdminBannerForm(instance=admin_banner)
        desktop_homepage_banner_count = AdminBanner.objects.filter(admin_id=admin_id,banner_type="HOMEPAGE",banner_category="DESKTOP").count()
        desktop_betslip_banner_count = AdminBanner.objects.filter(admin_id=admin_id,banner_type="BETSLIP",banner_category="DESKTOP").count()
        mobile_homepage_banner_count = AdminBanner.objects.filter(admin_id=admin_id,banner_type="HOMEPAGE",banner_category="MOBILE_RESPONSIVE").count()
        mobile_betslip_banner_count = AdminBanner.objects.filter(admin_id=admin_id,banner_type="BETSLIP",banner_category="MOBILE_RESPONSIVE").count()
        mobile_app_homepage_banner_count = AdminBanner.objects.filter(admin_id=admin_id,banner_type="HOMEPAGE",banner_category="MOBILE_APP").count()
        mobile_app_betslip_banner_count = AdminBanner.objects.filter(admin_id=admin_id,banner_type="BETSLIP",banner_category="MOBILE_APP").count()


        return render(request, template_name=self.template_name,
                      context={
                               "form": form, 
                               "title" : admin_banner.title,
                               "banner" : admin_banner.banner,
                               "banner_category": admin_banner.banner_category,
                               "banner_type" : admin_banner.banner_type,
                               "banner_id" : admin_banner.id,
                               "banner": admin_banner,
                               "desktop_homepage_banner_count":desktop_homepage_banner_count,
                               "desktop_betslip_banner_count": desktop_betslip_banner_count,
                               "mobile_homepage_banner_count": mobile_homepage_banner_count,
                               "mobile_betslip_banner_count":mobile_betslip_banner_count,
                               "mobile_app_homepage_banner_count":mobile_app_homepage_banner_count,
                               "mobile_app_betslip_banner_count":mobile_app_betslip_banner_count,}
                      )

    def post(self, request, *args, **kwargs):
        try:
            title = request.POST.get("title", None)
            banner = request.FILES.get('banner', None)
            banner_type = request.POST.get("banner_type", None)
            banner_category = request.POST.get('banner_category', None)
            banner_id = request.GET.get('banner_id', None)
            content = request.POST.get("banner_content")
            header = request.POST.get("banner_header")
            redirect_url = request.POST.get("redirect_url")
            button_text = request.POST.get("button_text")
            banner_obj = AdminBanner.objects.filter(id=banner_id).first()
            if banner:
                filename_format = banner.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                banner_thumbnail = Image.open(banner)
                banner_thumbnail.thumbnail((100, 100))
                banner_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                banner_thumbnail.save(banner_thumbnail_io, format=format, filename=filename)
                banner_thumbnail_inmemory = InMemoryUploadedFile(banner_thumbnail_io,
                                                                    'FileField',
                                                                    filename,
                                                                    format,
                                                                    sys.getsizeof(banner_thumbnail_io), None)
                banner.name = filename
                banner_obj.banner_thumbnail = banner_thumbnail_inmemory
                banner_obj.banner = banner
            banner_obj.title = title
            banner_obj.banner_type = banner_type
            banner_obj.banner_category = banner_category
            banner_obj.header = header
            banner_obj.content = content
            banner_obj.redirect_url = redirect_url
            banner_obj.button_text = button_text
            banner_obj.save()
            messages.success(request, "Banner updated successfully")

        except Exception as e:
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:admin-banner')


class SocialLinkView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ("admin", "superadmin")
    template_name = "admin/cms/social/links.html"
    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request):
        try:
            if request.user.role in ['admin', 'superadmin']:
                social_links = SocialLink.objects.all()
                return render(request, template_name=self.template_name,
                              context={
                                  "social_links": social_links,
                                  "admin": request.user.id,
                              })
            else:
                return render(request, template_name=self.template_name,
                              context={"error": "Not An Unauthorized User"},
                              status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FooterPageAjax(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        search = request.POST.get("search")
        footer_pages = FooterPages.objects.all().values("pages_id")
        pages = CmsPages.objects.all().exclude(id__in=footer_pages)
        if search:
            pages = pages.annotate(title_lower=Lower("title")).filter(
                title__icontains=search.lower()
            )
        pages = pages.values("id", "title")[0:10]
        results = []
        for page in pages:
            results.append({"value": page["id"], "text": page["title"]})
        return self.render_json_response(results)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)




'''Casino Report view ''' 
class CasinoBetslipReportView(CheckRolesMixin, ListView):
    template_name = "report/casino_betslip_report.html"
    model = GSoftTransactions
    queryset = GSoftTransactions.objects.order_by("-created").all()
    context_object_name = "casinobetslipreport"
    paginate_by = 20
    allowed_roles = ("admin", "superadmin", "dealer", "agent")
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        queryset = super().get_queryset()
        try:
            if self.request.GET.getlist("players", None):
                queryset = self.queryset.filter(user__in = self.request.GET.getlist("players"))

            if self.request.GET.get("from"):
                # start_date = datetime.datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%d-%m-%Y")
                start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
                queryset = queryset.filter(created__gte=start_date)
            else:
                # by default show results from first day of month
                current_date = timezone.now()
                first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
                queryset = queryset.filter(created__gte=first_day_of_month)

            if self.request.GET.get("to"):
                end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
                queryset = queryset.filter(created__date__lte=end_date)

            if self.request.GET.getlist("dealers"):
                dealers = self.request.GET.getlist("dealers")
                queryset = queryset.filter(user__dealer__in=dealers)

            if self.request.GET.getlist("agents"):
                agents = self.request.GET.getlist("agents")
                queryset = queryset.filter(user__agent__in=agents)

            if self.request.GET.get("provider"):
                games = CasinoGameList.objects.filter(vendor_name=self.request.GET.get("provider"))
                queryset = queryset.filter(Q(game_id__in=games.values('game_id')))

            if self.request.GET.get("games"):
                queryset = queryset.filter(Q(game_id=self.request.GET.get("provider")))


        except Exception as e:
            return queryset
        return queryset

    def get_context_data(self, **kwargs):
        # by default show results from first day of month
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

        context = super().get_context_data(**kwargs)
        context["from"] = self.request.GET.get("from", first_day_of_month)
        context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))

        if self.request.GET.getlist("dealers"):
            dealers = self.request.GET.getlist("dealers")
            context["selected_dealers"] = Dealer.objects.filter(id__in=dealers)

        if self.request.GET.getlist("agents"):
            agents = self.request.GET.getlist("agents")
            context["selected_agents"] = Agent.objects.filter(id__in=agents)

        return context


class CreateFooterPageView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/cms/footer/create_footer.html"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["category_key"] = self.request.GET.get("category_key", "")
        context["categories"] = FooterCategory.objects.all()
        if self.request.GET.get("category_key", None):
            category_key = self.request.GET.get("category_key")
            context["selected_category"] = FooterCategory.objects.get(name=category_key)
            context["selected_pages"] = CmsPages.objects.filter(
                id__in=FooterPages.objects.filter(category__name=category_key).values("pages_id")
            )
        return context

    def post_ajax(self, request, *args, **kwargs):
        category_key = request.POST.get("category_key", None)
        page_ids = request.POST.getlist("pages[]", None)
        try:
            if page_ids and category_key:
                page_ids.remove('')
                if FooterPages.objects.filter(category__id=category_key).exists():
                    FooterPages.objects.filter(category__id=category_key).delete()
                for page_id in page_ids:
                    footer_obj = FooterPages()
                    footer_obj.category = FooterCategory.objects.get(id=category_key)
                    footer_obj.pages = CmsPages.objects.get(id=page_id)
                    footer_obj.save()
                return self.render_json_response({"status": "Success", "message": "Created"}, status=201)
            else:
                return self.render_json_response({"status": "error", "message": "Both Fields Required"}, status=400)
        except Exception as e:
            print(f"Error in create footer page : {e}")
            return self.render_json_response({"status": "error", "message": "Something went wrong"}, status=500)


class FooterPageAjax(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        search = request.POST.get("search")
        footer_pages = FooterPages.objects.all().values("pages_id")
        pages = CmsPages.objects.all().exclude(id__in=footer_pages)
        if search:
            pages = pages.annotate(title_lower=Lower("title")).filter(
                title__icontains=search.lower()
            )
        pages = pages.values("id", "title")[0:10]
        results = []
        for page in pages:
            results.append({"value": page["id"], "text": page["title"]})
        return self.render_json_response(results)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class FooterPageView(CheckRolesMixin, ListView):
    template_name = "admin/cms/footer/footer.html"
    model = FooterPages
    queryset = FooterPages.objects.order_by("-created").all()
    context_object_name = "footer"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = []
        response = {}
        for page in FooterPages.objects.all():
            if page.category.id in category:
                response[page.category.name].append(page.pages.title)
            else:
                category.append(page.category.id)
                response[page.category.name] = [page.pages.title]
        context["footer_pages"] = response
        return context


class EditFooterPageView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/cms/footer/update_footer.html"
    allowed_roles = ("admin", "superadmin")
    date_format = "%d/%m/%Y %H:%M"
    context_object_name = "footer_pages"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        page_id = self.request.GET.get("page_id", "")
        category = []
        response = {}
        pages = FooterPages.objects.filter(category__name=page_id)
        for page in pages:
            if page.category.id in category:
                response[page.category.name].append(page.pages.title)
            else:
                category.append(page.category.id)
                response[page.category.name] = [page.pages.title]
        return render(request, template_name=self.template_name,
                      context={"pages": response,}
                      )

    def post(self, request, *args, **kwargs):
        try:
            title = request.POST.get("title", None)
            logo = request.FILES.get('logo', None)
            link_id = request.GET.get('link_id', None)
            social_link = SocialLink.objects.filter(id=link_id).first()
            social_link.logo = logo
            social_link.title = title
            social_link.url = request.POST.get("url")
            social_link.save()
            messages.success(request, "Social Link  updated successfully")

        except Exception as e:
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:social-link')


class DeleteFooterPageView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        page_id = self.request.POST.get("page_id")
        try:
            page = FooterPages.objects.filter(category__name=page_id)
            page.delete()
            return self.render_json_response(
                {
                    "status": "Success",
                    "message": _("Page Deleted Successfully")
                },
                status=200
            )

        except Exception as e:
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Page not found")
                },
                status=404
            )


class CreateSocialLinkView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/cms/social/create_link.html"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
                form = SocialLinkForm()
                return render(request, template_name=self.template_name,
                      context={"form": form}
                      )

    def post(self, request, *args, **kwargs):
        try:
            if not request.POST.get("title").strip():
                return self.render_json_response({"status": "error", "message": "Title should not be empty"})
            logo = request.FILES.get('logo')
            social_link = SocialLink()
            social_link.logo = logo
            social_link.title = request.POST.get("title")
            social_link.url = request.POST.get("url")
            social_link.admin = self.request.user
            social_link.save()
            messages.success(request, "Social link stored successfully")
        except Exception as e:
            if(type(e) != ValueError):
                messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:social-link')


class DeleteSocialLinkView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):

    allowed_roles = ("admin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        page_id = self.request.POST.get("page_id")
        try:
            page = SocialLink.objects.get(id=page_id)
            page.delete()
            return self.render_json_response(
                {
                    "status": "Success",
                    "message": _("Social Link Deleted Successfully")
                    },
                status=200
            )

        except Exception as e:
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Social Link Not Found")
                    },
                status=404
            )


class PagesView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ["admin", "superadmin"]
    template_name = "admin/cms/pages/page.html"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request):
        try:
            admin_page = CmsPages.objects.filter()
            return render(request, template_name=self.template_name,
                            context={
                                "admin_page": admin_page,
                                "admin": request.user.id,
                            })
        except Exception as e:
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PagesContentView(CheckRolesMixin, View, views.JSONResponseMixin, views.AjaxResponseMixin):
    allowed_roles = ["admin", "superadmin"]
    template_name = "admin/cms/pages/page.html"

    def get(self, request, *args, **kwargs):
        page_id = request.GET.get("page_id", None)
        page = CmsPages.objects.filter(id=page_id).first()

        if not page:
            return self.render_json_response({"status": "error", "message": "Invalid page ID"}, 400)

        return self.render_json_response({
            "title": page.title,
            "content": page.page_content,
        })


class CreatePageView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/cms/pages/create_page.html"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        form = CMSPagesForm()
        return render(request, template_name=self.template_name,
                      context={"form": form}
                      )

    def post(self, request, *args, **kwargs):
        try:
            if not request.POST.get("title").strip():
                return self.render_json_response({"status": "error", "message": "Title should not be empty"})
            elif CmsPages.objects.filter(title=request.POST.get("title")).exists():
                messages.error(request, f"Page with title '{request.POST.get('title')}' already exists")
                return redirect('admin-panel:pages')

            page = request.FILES.get('page')
            images = request.FILES.getlist('images')
            page_obj = CmsPages()
            if page:     
                filename_format = page.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                page_thumbnail = Image.open(page)
                page_thumbnail.thumbnail((750, 400))
                page_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                page_thumbnail.save(page_thumbnail_io, format=format, filename=filename)
                page_thumbnail_inmemory = InMemoryUploadedFile(page_thumbnail_io,
                                                                 'FileField',
                                                                 filename,
                                                                 format,
                                                                 sys.getsizeof(page_thumbnail_io), None)
                page.name = filename
                page_obj.page_thumbnail = page_thumbnail_inmemory
                page_obj.page = page

            page_obj.is_form = True if request.POST.get('is_redirect') == 'is_form' else False
            page_obj.is_redirect =True if request.POST.get("is_redirect") == "is_redirect" else False
            page_obj.is_page =True if request.POST.get('is_redirect')==None or request.POST.get('is_redirect') =='is_form' else False
            page_obj.title = request.POST.get("title")
            page_obj.form_name = request.POST.get("form_name")
            page_obj.redirect_url = request.POST.get("redirect_url")
            page_obj.page_content = request.POST.get("page_content")
            page_obj.more_info = request.POST.get("more_info")
            page_obj.meta_description = request.POST.get("meta_description")
            page_obj.json_metadata = request.POST.get("json_metadata")
            page_obj.preview_type = request.POST.get("preview_type")
            page_obj.save()

            if images:
                for image in images:
                    PageMedia.objects.create(page=page_obj, media=image)
            messages.success(request, "Page content stored successfully")
        except Exception as e:
            print(traceback.format_exc())
            if(type(e) != ValueError):
                messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:pages')


class DeletePage(CheckRolesMixin, views.JSONResponseMixin,
                                 views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        page_id = self.request.POST.get("page_id")
        try:
            page = CmsPages.objects.get(id=page_id)
            page.delete()
            return self.render_json_response(
                {
                    "status": "Success",

                    "message": _("Page Deleted Successfully")
                },
                status=200
            )

        except Exception as e:
            return self.render_json_response(
                {
                    "status": "Error",

                    "message": _("Logo not found")
                },
                status=404
            )


class TogglePage(CheckRolesMixin, views.JSONResponseMixin,
                                 views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        page_id = self.request.POST.get("page_id")
        try:
            page = CmsPages.objects.get(id=page_id)
            comp = "enabled" if page.hidden else "disabled"
            page.hidden = not page.hidden
            page.save()
            return self.render_json_response(
                {
                    "status": "Success",

                    "message": "Page succesfully "  + comp
                },
                status=200
            )

        except Exception as e:
            return self.render_json_response(
                {
                    "status": "Error",

                    "message": _("Logo not found")
                },
                status=404
            )


class EditSocialLinkAjax(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/cms/social/update_link.html"
    allowed_roles = ("admin", "superadmin")
    date_format = "%d/%m/%Y %H:%M"
    context_object_name = "social_link"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        template_id = self.request.GET.get("link_id", "")
        social_link = SocialLink.objects.get(id=template_id)
        form = EditSocialLinkForm(instance=social_link)

        return render(request, template_name=self.template_name,
                      context={"form": form,
                               "title": social_link.title,
                               "logo": social_link.logo,
                               "url": social_link.url,
                               "link_id": social_link.id}
                      )

    def post(self, request, *args, **kwargs):
        try:
            title = request.POST.get("title", None)
            logo = request.FILES.get('logo', None)
            link_id = request.GET.get('link_id', None)
            social_link = SocialLink.objects.filter(id=link_id).first()
            if logo:
                social_link.logo = logo
            social_link.title = title
            social_link.url = request.POST.get("url")
            social_link.save()
            messages.success(request, "Social Link  updated successfully")

        except Exception as e:
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:social-link')


class EditPageAjax(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/cms/pages/update_page.html"
    allowed_roles = ("admin", "superadmin")
    date_format = "%d/%m/%Y %H:%M"
    context_object_name = "crm_template"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        template_id = self.request.GET.get("template_id", "")
        if not template_id:
            messages.error(request, "please provide template id")
            return redirect('admin-panel:pages')
        about_detail = CmsPages.objects.filter(id=template_id).first()
        if not about_detail:
            messages.error(request, "Invalid Id")
            return redirect('admin-panel:pages')

        form = CMSPagesForm(instance=about_detail)
        page_thumbnail = about_detail.page_thumbnail if about_detail else ''

        return render(request, template_name=self.template_name,
                      context={"page_thumbnail": page_thumbnail,
                               "form": form, 
                               "title" : about_detail.title,
                               "page" : about_detail.page,
                               "page_thumbnail" : about_detail.page_thumbnail,
                               "page_content" : about_detail.page_content,
                               "template_id" : about_detail.id,
                               "is_form": about_detail.is_form,
                               "is_redirect": about_detail.is_redirect,
                               "redirect_url":about_detail.redirect_url,
                               "form_name":about_detail.form_name,
                               "is_form":about_detail.is_form,
                               "is_redirect":about_detail.is_redirect,
                               "preview_type":about_detail.preview_type,
                               "media":about_detail.media.all(),
                               "is_page":about_detail.is_page

                               }
                      )

    def post(self, request, *args, **kwargs):
        try:
            title = request.POST.get("title", None)
            page = request.FILES.get('page', None)
            page_content = request.POST.get("page_content", None)
            template_id = request.GET.get('template_id', None)
            images = request.FILES.getlist('images')
            page_obj = CmsPages.objects.filter(id=template_id).first()
            if page:
                filename_format = page.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                page_thumbnail = Image.open(page)
                page_thumbnail.thumbnail((750, 400))
                page_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                page_thumbnail.save(page_thumbnail_io, format=format, filename=filename)
                page_thumbnail_inmemory = InMemoryUploadedFile(page_thumbnail_io,
                                                                 'FileField',
                                                                 filename,
                                                                 format,
                                                                 sys.getsizeof(page_thumbnail_io), None)
                page.name = filename
                page_obj.page_thumbnail = page_thumbnail_inmemory
                page_obj.page = page

            page_obj.is_form = True if request.POST.get('is_redirect') == 'is_form' else False
            page_obj.is_redirect =True if request.POST.get("is_redirect") == "is_redirect" else False
            page_obj.is_page =True if request.POST.get("is_redirect") == "is_page" else False
            page_obj.title = title
            page_obj.form_name = request.POST.get("form_name")
            page_obj.redirect_url = request.POST.get("redirect_url")
            page_obj.page_content = page_content
            page_obj.more_info = request.POST.get("more_info")
            page_obj.meta_description = request.POST.get("meta_description")
            page_obj.json_metadata = request.POST.get("json_metadata")
            page_obj.preview_type = request.POST.get("preview_type")
            page_obj.save()

            if page_obj.preview_type == "none":
                media = PageMedia.objects.filter(page=page_obj)
                PageMedia.bulk_delete_media(media)
            elif images:
                for image in images:
                    PageMedia.objects.create(page=page_obj, media=image)
            messages.success(request, "Page content updated successfully")

        except Exception as e:
            if(type(e) != ValueError):
                messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:pages')

    def put_ajax(self, request, *args, **kwargs):
        try:
            data = parse_qs(self.request.body.decode('utf-8'))
            id = data['id'][0]

            if not id:
                return JsonResponse({"status": "error", "message": _("ID is required")}, status=400)

            page_media = PageMedia.objects.filter(id=id).first()
            if not page_media:
                return JsonResponse({"status": "error", "message": _("Media not found")}, status=400)
            page_media.media.delete(save=False)
            page_media.delete()
            return JsonResponse({"status": "success"})
        except Exception as e:
            print(e)
            return self.render_json_response({
                "status": "error",
                "message": _("Internal Error")
            },status=500)


class CategoryView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ("admin", "superadmin")
    template_name = "admin/cms/footer/category/category.html"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request):
        try:
            if request.user.role in ['admin', 'superadmin']:
                admin_page = FooterCategory.objects.filter()
                return render(request, template_name=self.template_name,
                              context={
                                  "admin_page": admin_page,
                                  "admin": request.user.id,
                              })
            else:
                return render(request, template_name=self.template_name,
                              context={"error": "Not An Unauthorized User"},
                              status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateCategoryView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/cms/footer/category/create_category.html"
    allowed_roles = ("admin", "superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        form = FooterCategoryForm()
        return render(request, template_name=self.template_name,
                      context={"form": form}
                      )

    def post(self, request, *args, **kwargs):
        try:
            if not request.POST.get("name").strip():
                return self.render_json_response({"status": "error", "message": "Name should not be empty"})
            if FooterCategory.objects.filter(name__icontains=request.POST.get("name")).exists():
                messages.error(request, "This Category Already Exists")
                return redirect('admin-panel:category')

            page_obj = FooterCategory()
            page_obj.name = request.POST.get("name")
            page_obj.position = request.POST.get("position")
            page_obj.save()
            messages.success(request, "Category content stored successfully")
        except Exception as e:
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:category')


class DeleteCategory(CheckRolesMixin, views.JSONResponseMixin,
                                 views.AjaxResponseMixin, View):
    allowed_roles = ("admin","superadmin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        page_id = self.request.POST.get("page_id")
        try:
            page = FooterCategory.objects.get(id=page_id)
            page.delete()
            return self.render_json_response(
                {
                    "status": "Success",
                    "message": _("Category Deleted Successfully")
                },
                status=200
            )

        except Exception as e:
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Logo not found")
                },
                status=404
            )


class EditCategoryAjax(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/cms/footer/category/update_category.html"
    allowed_roles = ("admin", "superadmin")
    date_format = "%d/%m/%Y %H:%M"
    context_object_name = "crm_template"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        try:
            template_id = self.request.GET.get("template_id", "")
            about_detail = FooterCategory.objects.get(id=template_id)
            form = FooterCategoryForm(instance=about_detail)
            return render(request, template_name=self.template_name,
                          context={
                              "form": form,
                              "name": about_detail.name,
                              "position": about_detail.position,
                              "category_id": about_detail.id
                          }
                          )
        except Exception as e:
            messages.error(request, "Something Went Wrong")
        return render(request, template_name=self.template_name, context={})

    def post(self, request, *args, **kwargs):
        try:
            name = request.POST.get("name")
            category_id = request.POST.get("category_id")
            page_obj = FooterCategory.objects.get(id=category_id)
            page_obj.name = name
            page_obj.position = request.POST.get("position", 0)
            page_obj.save()
            messages.success(request, "Category content updated successfully")
        except Exception as e:
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:category')


class DetailSocialLinkAjax(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/cms/social/details_link.html"
    allowed_roles = ("superadmin",)
    date_format = "%d/%m/%Y %H:%M"
    context_object_name = "social_link"
    permissions = (("can_read", "Can read"),)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        template_id = self.request.GET.get("link_id", "")
        social_link = SocialLink.objects.get(id=template_id)
        form = DetailSocialLinkForm(instance=social_link)

        return render(request, template_name=self.template_name,
                      context={"form": form,
                               "title": social_link.title,
                               "logo": social_link.logo,
                               "url": social_link.url,
                               "link_id": social_link.id}
                      )


class NotificationView(CheckRolesMixin, TemplateView):
    template_name = "admin/crm_cms/notification.html"
    allowed_roles = ("superadmin", "admin")


class CasinoManagementView(CheckRolesMixin, ListView):
    allowed_roles = ["admin",]
    template_name = "admin/casino-management.html"
    paginate_by = 20
    model = CasinoManagement
    queryset = CasinoManagement.objects.all().order_by("game__game_name")
    context_object_name = "casinogames"
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        queryset = super().get_queryset()
        brands = self.request.GET.get("brand_id")
        game_ids = self.request.GET.get("game_id")
        category = self.request.GET.get("category", None)
        device_type = self.request.GET.get("device_type", None)

        # if brands and len(brands) > 0:
        #     brands = [x for x in brands.split(",") ]
        #     if brands and len(brands) > 0 :
        #         queryset = queryset.filter(game__vendor_name__in=brands)
        #     return queryset

        queryset = queryset.filter(admin=self.request.user)

        if game_ids and len(game_ids) > 0 :
            game_ids = [int(x) for x in game_ids.split(",") if x.isdigit()]
            print(game_ids)
            queryset = queryset.filter(id__in=game_ids)

        if category:
            category = category.split(",")
            queryset = queryset.filter(game__game_category__in=category)

        if device_type and device_type.lower()=="mobile":
            queryset = queryset.filter(game__is_mobile_supported=True)
        elif device_type and device_type.lower()=="desktop":
            queryset = queryset.filter(game__is_desktop_supported=True)

        queryset = queryset.filter(admin = self.request.user)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        games = self.request.GET.get("game_id", None)

        casino_categories = CasinoGameList.objects.all().distinct("game_category").values_list("game_category", flat=True)
        context["casino_categories"] = casino_categories
        if games:
            game_ids = [int(x) for x in games.split(",") if x.isdigit()]
            casino_games = CasinoGameList.objects.filter(id__in=game_ids)
            context["selected_games"] = casino_games
        context["selected_categories"] = self.request.GET.get("category", "").split(",")
        context["selected_device_type"] = self.request.GET.get("device_type")
        print(context)
        return context


class CasinoManagementProviderView(CheckRolesMixin, ListView):
    '''
    URL: admin/casino-management-provider-list/
    Shows the panel to activate or deactivate providers
    '''

    allowed_roles = ["admin",]
    template_name = "admin/provider_casino_management.html"
    paginate_by = 20
    model = CasinoManagement
    queryset = CasinoManagement.objects.all()
    context_object_name = "casinogames"
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        queryset = super().get_queryset()
        brands = self.request.GET.get("brand_id")
        if brands:
            brands = [int(x) for x in brands.split(",") if x.isdigit()]
            queryset = queryset.filter(admin=self.request.user)

            if brands and len(brands) > 0 :
                brand_filter = [int(x) for x in brands]
                print(brand_filter)
                queryset = queryset.filter(game__id__in=brand_filter)
            return queryset

        queryset = queryset.filter(admin=self.request.user).distinct("game__vendor_name")

        return queryset


class ProviderView(CheckRolesMixin, ListView):
    allowed_roles = ["admin",]
    template_name = "admin/edit_provider_casino_management.html"
    model = Providers
    context_object_name = "provider"

    def get_queryset(self):
        provider_name = self.request.GET.get("provider_name")
        if not provider_name:
            return Providers.objects.none()

        provider = Providers.objects.filter(name=provider_name)
        if provider.exists():
            return provider.first()

        if CasinoGameList.objects.filter(vendor_name=provider_name).exists():
            return Providers.objects.create(name=provider_name)

        return Providers.objects.none()


class EditProviderView(APIView):
    allowed_roles = ["admin",]
    permission_classes = [IsAdmin]

    def post(self, request):
        # set variables
        id = self.request.POST.get("id")
        logo = self.request.FILES.get("logo")

        # Request check
        if not logo:
            return Response({"message" : "Should upload an image (logo)"}, status=status.HTTP_400_BAD_REQUEST)

        if not id:
            return Response({"message" : "Must pass id in the body"}, status=status.HTTP_400_BAD_REQUEST)

        # Provider checks (if exists id)
        provider = Providers.objects.filter(id=id)
        if not provider.exists():
            return Response({"message" : "The selected id is not valid"}, status=status.HTTP_400_BAD_REQUEST)

        # Format check
        filename_format = logo.name.split(".")
        name, format = filename_format[-2], filename_format[-1]
        format = 'JPEG' if format.lower() == 'jpg' else format.upper()
        allow_format = ['JPEG', 'WEBP', 'PNG']
        if not format in allow_format:
            return Response({"message" : "The IMG should be of type " + ', '.join(allow_format) + " o JPG"}, status=status.HTTP_400_BAD_REQUEST)

        # Save the logo
        provider = provider.first()
        provider.logo = logo
        provider.save()

        return Response({"success" : True,"message" : "The provider was modified"}, status=status.HTTP_200_OK)


class CasinoCategoryHeaderManagementView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ["admin",]
    template_name = "admin/casino_category_header_management.html"

    def get(self, request, *args, **kwargs):
        casinocategories = CasinoHeaderCategory.objects.all().order_by("position")
        return render(request, template_name=self.template_name, context={"casinocategories": casinocategories})


    def post(self, request, *args, **kwargs):
        try:
            category_id = self.request.POST.get("category_id")
            image = self.request.FILES.get("image")
            image_type = self.request.POST.get("image_type")
            if not category_id.isdigit() or not CasinoHeaderCategory.objects.filter(id=category_id).exists():
                return self.render_json_response({
                    "status": "error",
                    "message": _("Category not found"),
                },status=400)
            elif not image:
                return self.render_json_response({
                    "status": "error",
                    "message": _("Please provide valid image"),
                },status=400)

            casino_category = CasinoHeaderCategory.objects.filter(id=category_id).first()
            if image_type == "dark":
                old_image = casino_category.image_dark
                casino_category.image_dark = image
            else:
                old_image = casino_category.image
                casino_category.image = image
            casino_category.save()

            if old_image and os.path.isfile(old_image.path):
                default_storage.delete(old_image.path)

            return self.render_json_response({
                "status": "success",
                "message": _("Image Updated"),
                "url": casino_category.image.url if image_type == "light" else casino_category.image_dark.url,
            },status=200)
        except Exception as e:
            print(traceback.format_exc())
            print(e)
            return self.render_json_response({
                "status": "error",
                "message": _("Internal Error")
            },status=200)


    def put_ajax(self, request, *args, **kwargs):
        try:
            data = parse_qs(self.request.body.decode('utf-8'))
            category_id = data['category_id'][0]
            new_position = data['position'][0]

            if not new_position.lower() in ["ascending", "descending"]:
                if category_id and category_id.isdigit() and not CasinoHeaderCategory.objects.filter(id=category_id).exists():
                    return self.render_json_response({
                        "status": "error",
                        "message": _("Category not found"),
                    },status=400)
                elif not new_position or (not new_position.isdigit() and new_position not in ["last", "active_last"]):
                    return self.render_json_response({
                        "status": "error",
                        "message": _("Please provide valid position"),
                    },status=400)
                else:
                    category_id = int(category_id)
                    new_position = int(new_position) if new_position not in ["last", "active_last"] else new_position
            else:
                order_by = "num_games" if new_position.lower() == "ascending" else "-num_games"
                categories = CasinoHeaderCategory.objects.filter(is_active=True).values_list("name", flat=True)
                casino_categories = CasinoGameList.objects.filter(game_category__in=categories).values('game_category').annotate(num_games=Count('id')).order_by(order_by).values_list("game_category", flat=True)
                for position, category in enumerate(casino_categories):
                    CasinoHeaderCategory.objects.filter(name=category).update(position=position+1)

                return self.render_json_response({
                    "status": "success",
                    "title": _("Categories updated"),
                    "message": f"Categories updated in {new_position.lower()} order",
                },status=200)

            casino_category = CasinoHeaderCategory.objects.filter(id=category_id).first()
            if new_position == "last":
                categories = CasinoHeaderCategory.objects.filter(position__gt=casino_category.position)
                category = CasinoHeaderCategory.objects.order_by("position").last()
                categories.update(position=F("position")-1)
                new_position = category.position if category else 1
            elif new_position == "active_last":
                categories = CasinoHeaderCategory.objects.filter(is_active=False, position__lt=casino_category.position)
                category = CasinoHeaderCategory.objects.filter(is_active=True, position__lt=casino_category.position).order_by("position").last()
                categories.update(position=F("position")+1)
                new_position = category.position + 1 if category else 1
            elif new_position > casino_category.position:
                categories = CasinoHeaderCategory.objects.filter(position__gt=casino_category.position, position__lte=new_position)
                categories.update(position=F("position")-1)
            else:
                categories = CasinoHeaderCategory.objects.filter(position__lt=casino_category.position, position__gte=new_position)
                categories.update(position=F("position")+1)

            casino_category.position = new_position
            casino_category.save()

            return self.render_json_response({
                "status": "success",
                "title": _("Position updated"),
                "message": f"Position updated to {new_position}",
            },status=200)
        except Exception as e:
            print(e)
            return self.render_json_response({
                "status": "error",
                "message": _("Internal Error")
            },status=200)


class CasinoHeaderCategoryStatus(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin")

    def post_ajax(self, request, *args, **kwargs):
        id = request.POST.get("category_id")
        casino_header = CasinoHeaderCategory.objects.filter(id=id).first()
        if not casino_header:
            return self.render_json_response({"status": "error", "message": "Invalid ID"})
        casino_header.is_active = not casino_header.is_active
        casino_header.save()
        message = "Category Enabled" if casino_header.is_active else "Category Disabled"
        return self.render_json_response({"status": "Success", "message": message})


class SpinToWinProviderStatus(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    '''accounts/manage-spin-to-win-provider-status/'''
    allowed_roles = ("admin")

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        provider = request.POST.get("provider")

        casino_obj = CasinoManagement.objects.filter(
            admin = self.request.user, 
            game__vendor_name= provider,
        )

        if casino_obj.exists() and casino_obj.first().enabled:
            casino_obj.update(enabled = False)
            message = "Provider disabled"
        elif casino_obj.exists():
            casino_obj.update(enabled= True)
            message = "Provider enabled"

        return self.render_json_response({"status": "Success", "message": message})


class SpinToWinGameStatus(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin")

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        game_id = request.POST.get("game_id")
        switch_field = request.POST.get("switch")
        casino_obj = CasinoManagement.objects.filter(admin=self.request.user, game__game_id=game_id).first()
        if switch_field=="top_pick":
            casino_obj.is_top_pick = not casino_obj.is_top_pick
            casino_obj.save()
            message = "Game marked as top pick" if casino_obj.is_top_pick else "Game removed from top picks"
        else:
            casino_obj.game_enabled = not casino_obj.game_enabled
            message = "Game enabled" if casino_obj.game_enabled else "Game disabled"

        casino_obj.save()

        return self.render_json_response({"status": "Success", "message": message})

class CasinoProviderAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "dealer", "superadmin", "tenant_manager")

    def post_ajax(self, request, *args, **kwargs):
        search = self.request.POST.get("search", "").strip()
        # admin_id = self.request.POST.get("adminId", None)
        brands = CasinoGameList.objects.distinct("vendor_name")
        if search:
            brands = brands.annotate(vendor_name_lower=Lower("vendor_name")).filter(
                vendor_name_lower__icontains=search.lower()
            )
        results = []
        for brand in brands:
            results.append(
                    {
                        "value": brand.id,
                        "text": brand.vendor_name
                    }
                )
        return self.render_json_response(results)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

class CasinoGameAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "dealer", "superadmin", "tenant_manager")

    def post_ajax(self, request, *args, **kwargs):
        search = self.request.POST.get("search", "").strip()
        # admin_id = self.request.POST.get("adminId", None)
        games = CasinoManagement.objects.filter(admin = self.request.user)
        if search:
            games = games.filter(game__game_name__icontains = search)

        results = []
        for game in games:
            results.append(
                {
                    "value": game.id,
                    "text": game.game.game_name
                }
            )
        return self.render_json_response(results)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

class AdminSponserView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ["admin", ]
    template_name = "admin/ads_sponser.html"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request):
        try:
            if request.user.role == 'admin':
                admin_banners = AdminAdsBanner.objects.filter(admin_id=request.user.id)
                return render(request, template_name=self.template_name,
                              context={
                                  "admin_banners": admin_banners,
                                  "admin": request.user.id,
                              })
            else:
                return render(request, template_name=self.template_name,
                            #   context={"error": "Not An Unauthorized User"},
                              status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateAdminSponserView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ["admin", "superadmin",]
    template_name = "admin/create_ads_sponser.html"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request):
        try:
            if request.user.role == 'admin':
                form = AdminBannerForm()
                desktop_homepage_banner_count = AdminAdsBanner.objects.filter(admin_id=request.user.id,banner_type="HOMEPAGE",banner_category="DESKTOP").count()
                desktop_betslip_banner_count = AdminAdsBanner.objects.filter(admin_id=request.user.id,banner_type="BETSLIP",banner_category="DESKTOP").count()
                mobile_homepage_banner_count = AdminAdsBanner.objects.filter(admin_id=request.user.id,banner_type="HOMEPAGE",banner_category="MOBILE_RESPONSIVE").count()
                mobile_betslip_banner_count = AdminAdsBanner.objects.filter(admin_id=request.user.id,banner_type="BETSLIP",banner_category="MOBILE_RESPONSIVE").count()
                mobile_app_homepage_banner_count = AdminAdsBanner.objects.filter(admin_id=request.user.id,banner_type="HOMEPAGE",banner_category="MOBILE_APP").count()
                mobile_app_betslip_banner_count = AdminAdsBanner.objects.filter(admin_id=request.user.id,banner_type="BETSLIP",banner_category="MOBILE_APP").count()


                return render(request, template_name=self.template_name,
                              context={"form": form,
                                       "admin": request.user.id ,
                                       "desktop_homepage_banner_count":desktop_homepage_banner_count,
                                       "desktop_betslip_banner_count": desktop_betslip_banner_count,
                                       "mobile_homepage_banner_count": mobile_homepage_banner_count,
                                       "mobile_betslip_banner_count":mobile_betslip_banner_count,
                                       "mobile_app_homepage_banner_count": mobile_app_homepage_banner_count,
                                       "mobile_app_betslip_banner_count": mobile_app_betslip_banner_count,
                              })
            else:
                return render(request, template_name=self.template_name,
                            #   context={"error": "Not An Unauthorized User"},
                              status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            if request.user.role == 'admin':
                form = AdminBannerForm(request.POST, request.FILES)
                banner = request.FILES.get('banner')
                if form.is_valid():
                    filename_format = banner.name.split(".")
                    name, format = filename_format[-2], filename_format[-1]
                    filename = f"{name}{uuid.uuid4()}.{format}"
                    banner_thumbnail = Image.open(banner)
                    banner_thumbnail.thumbnail((100, 100))
                    banner_thumbnail_io = BytesIO()
                    format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                    banner_thumbnail.save(banner_thumbnail_io, format=format,filename=filename)
                    banner_thumbnail_inmemory = InMemoryUploadedFile(banner_thumbnail_io,
                                                                    'FileField',
                                                                     filename,
                                                                     format,
                                                                     sys.getsizeof(banner_thumbnail_io), None)
                    banner.name = filename
                    banner_category = request.POST.get('banner_category')
                    admin_banner = AdminAdsBanner(admin_id=request.user.id,
                                               banner=banner,
                                               title=form.cleaned_data['title'],
                                               banner_type=form.cleaned_data['banner_type'],
                                               banner_thumbnail = banner_thumbnail_inmemory,
                                               banner_category = banner_category,
                                               redirect_url = form.cleaned_data['redirect_url'])

                    admin_banner.save()
                    messages.success(request, "Banner created successfully")
                    return redirect('admin-panel:admin-ads')

                messages.error(request, _("Please provide valid banner details!"))
                return redirect('admin-panel:create-admin-banner')
            else:
                return render(request, template_name=self.template_name,
                              context={"error": "Not An Unauthorized User"},
                              status=status.HTTP_401_UNAUTHORIZED)

        except Exception as e:
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeleteAdminSponser(CheckRolesMixin, views.JSONResponseMixin,
                                 views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        banner_id = self.request.POST.get("banner_id")
        try:
            banner =AdminAdsBanner.objects.get(id=banner_id)
            banner.delete()
            return self.render_json_response(
                {
                    "status": "Success",
                    "message": _("Logo Deleted Successfully")
                },
                status=200
            )

        except Exception as e:
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Logo not found")
                },
                status=404
            )

class EditAdminSponserView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/edit_ads_sponser.html"
    allowed_roles = ("admin", "superadmin")
    date_format = "%d/%m/%Y %H:%M"
    context_object_name = "banner"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def get(self, request, *args, **kwargs):
        banner_id = self.request.GET.get("banner_id", "")
        admin_banner = AdminAdsBanner.objects.get(id=banner_id)
        form = AdminBannerForm(instance=admin_banner)
        desktop_homepage_banner_count = AdminAdsBanner.objects.filter(admin_id=request.user.id,banner_type="HOMEPAGE",banner_category="DESKTOP").count()
        desktop_betslip_banner_count = AdminAdsBanner.objects.filter(admin_id=request.user.id,banner_type="BETSLIP",banner_category="DESKTOP").count()
        mobile_homepage_banner_count = AdminAdsBanner.objects.filter(admin_id=request.user.id,banner_type="HOMEPAGE",banner_category="MOBILE_RESPONSIVE").count()
        mobile_betslip_banner_count = AdminAdsBanner.objects.filter(admin_id=request.user.id,banner_type="BETSLIP",banner_category="MOBILE_RESPONSIVE").count()
        mobile_app_homepage_banner_count = AdminAdsBanner.objects.filter(admin_id=request.user.id,banner_type="HOMEPAGE",banner_category="MOBILE_APP").count()
        mobile_app_betslip_banner_count = AdminAdsBanner.objects.filter(admin_id=request.user.id,banner_type="BETSLIP",banner_category="MOBILE_APP").count()


        return render(request, template_name=self.template_name,
                      context={
                               "form": form, 
                               "title" : admin_banner.title,
                               "banner" : admin_banner.banner,
                               "banner_category": admin_banner.banner_category,
                               "banner_type" : admin_banner.banner_type,
                               "redirect_url" : admin_banner.redirect_url,
                               "banner_id" : admin_banner.id,
                               "desktop_homepage_banner_count":desktop_homepage_banner_count,
                               "desktop_betslip_banner_count": desktop_betslip_banner_count,
                               "mobile_homepage_banner_count": mobile_homepage_banner_count,
                               "mobile_betslip_banner_count":mobile_betslip_banner_count,
                               "mobile_app_homepage_banner_count":mobile_app_homepage_banner_count,
                               "mobile_app_betslip_banner_count":mobile_app_betslip_banner_count,}
                      )

    def post(self, request, *args, **kwargs):
        try:
            title = request.POST.get("title", None)
            banner = request.FILES.get('banner', None)
            banner_type = request.POST.get("banner_type", None)
            redirect_url = request.POST.get("redirect_url",None)
            banner_category = request.POST.get('banner_category', None) 
            banner_id = request.GET.get('banner_id', None)
            banner_obj = AdminAdsBanner.objects.filter(id=banner_id).first()
            if banner:
                filename_format = banner.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                banner_thumbnail = Image.open(banner)
                banner_thumbnail.thumbnail((100, 100))
                banner_thumbnail_io = BytesIO()
                format = 'JPEG' if format.lower() == 'jpg' else format.upper()
                banner_thumbnail.save(banner_thumbnail_io, format=format, filename=filename)
                banner_thumbnail_inmemory = InMemoryUploadedFile(banner_thumbnail_io,
                                                                    'FileField',
                                                                    filename,
                                                                    format,
                                                                    sys.getsizeof(banner_thumbnail_io), None)
                banner.name = filename
                banner_obj.banner_thumbnail = banner_thumbnail_inmemory
                banner_obj.banner = banner
            banner_obj.title = title
            banner_obj.redirect_url = redirect_url
            banner_obj.banner_type = banner_type
            banner_obj.banner_category = banner_category
            banner_obj.save()
            messages.success(request, "Banner updated successfully")

        except Exception as e:
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:admin-ads')


class CreateAffiliates(CheckRolesMixin, views.JSONResponseMixin, ListView):
    model = Users
    paginate_by = 10
    template_name = "admin/affiliate/affiliates.html"
    allowed_roles = ("admin")
    context_object_name = "affiliates"
    queryset = Player.objects.filter(affiliate_link__isnull=False).order_by("-created")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_queryset(self):

        user = self.request.GET.get('user_name',[])
        if user:
            self.queryset = self.queryset.filter(id=user)

        if self.request.user.role == "admin":
            self.queryset = self.queryset
            self.queryset = self.queryset.annotate(
                total_earned=Coalesce(Sum(F('transactions__bonus_amount'), filter=Q(transactions__journal_entry='bonus', transactions__bonus_type='affiliate_bonus')), 0.00)
            )
        return self.queryset        

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        dealers = self.request.GET.get('dealers', [])
        agents = self.request.GET.get('agents', [])


        if dealers:
            context["selected_dealers"] = Dealer.objects.filter(id__in=dealers.split(","))

        if agents:
            context["selected_agents"] = Agent.objects.filter(id__in=agents.split(","))
        return context        

    def post(self, request):
        try:
            commision_percentage = request.POST.get("commision_percentage", None)
            affliate_expire_date = request.POST.get("affliate_expire_date", None)
            no_of_deposits = request.POST.get("no_of_deposits", 1)
            all_deposits  = True if request.POST.get("all_deposits") == 'true' else False
            is_redeemable = True if request.POST.get("redeemable") == 'true' else False
            is_lifetime_affiliate = True if request.POST.get("lifetime_affiliate") == 'true' else False
            user_id = request.POST.get("user_id", None)
            user = Player.objects.filter(id=user_id).first()
            if user:
                user.affiliation_percentage = commision_percentage
                user.is_redeemable_amount = is_redeemable
                if affliate_expire_date:
                    user.affliate_expire_date = datetime.strptime(affliate_expire_date,'%d/%m/%Y')
                if all_deposits:
                    user.is_bonus_on_all_deposits = True
                else:
                    user.no_of_deposit_counts = int(no_of_deposits)                    
                    user.is_lifetime_affiliate = is_lifetime_affiliate

                user.save()
            else:
                return self.render_json_response({"title":"Error","icon":"error","message": "User not Found!"}, status.HTTP_400_BAD_REQUEST)    
            return self.render_json_response({"title":"Success","icon":"success","message": "Affiliate Links Assigned"}, status.HTTP_200_OK)

        except Exception as e:
            print(e)
            return self.render_json_response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class AffiliatedPlayersAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("get",)
    allowed_roles = ("admin", "dealer")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_ajax(self, request, *args, **kwargs):
        user_id = request.GET.get("user_id", None)
        player = Player.objects.filter(id=user_id,affiliate_link__isnull=False).first()

        results = []

        results.append({"player_id": player.id, 
                            'affiliate_link':player.affiliate_link,
                            'commision':player.affiliation_percentage,
                            "username": player.username, 
                            "agent": player.agent.username, 
                            "email": player.email,
                            "balance": player.balance})

        return self.render_json_response({"data": results})

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class BetBonusView(CheckRolesMixin, ListView):
    """
    Sign Up bonus view - Renamed from welcome bonus percentage
    Ref: https://trello.com/c/xoCgHWtk
    """
    template_name = "admin/bonuses/bet_bonus.html"
    model = PromoCodes
    queryset = PromoCodes.objects.order_by("-created").all()
    context_object_name = "bonuses"
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(
            dealer=self.request.user.id, bonus__bonus_type="bet_bonus"
        )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            bonus_obj = BonusPercentage.objects.get(dealer=self.request.user.id, bonus_type="bet_bonus")

            context["bet_bonus"] = bonus_obj.percentage
            context["maximum_limit"] = bonus_obj.bet_bonus_limit
            context["per_day_limit"] = bonus_obj.bet_bonus_per_day_limit
            promo_obj = PromoCodes.objects.filter(bonus=bonus_obj, is_expired=False).last()
            # context["losing_promo_code"] = promo_obj.promo_code if promo_obj else 0
            # context["losing_start_date"] = promo_obj.start_date.strftime(self.date_format) if promo_obj else timezone.now().strftime(self.date_format)
            # context["losing_end_date"] = promo_obj.end_date.strftime(self.date_format) if promo_obj else timezone.now().strftime(self.date_format)
            context["bonus_type"] = bonus_obj.bonus_type if promo_obj else "bet_bonus"
            # context["promo_code_usage_limit"] = promo_obj.usage_limit if promo_obj else 0
            context["promo_code_user_limit"] = -1
        except BonusPercentage.DoesNotExist:
            context["bet_bonus"] = 0
            # context["losing_start_date"] = timezone.now().strftime(self.date_format)
            # context["losing_end_date"] = timezone.now().strftime(self.date_format)
            context["promo_code_usage_limit"] = 1
            context["promo_code_user_limit"] = -1

        return context

class PendingWithdrawalsview(CheckRolesMixin, ListView):
    template_name = "admin/pendingwithdrawals.html"

    model = CoinFlowTransaction
    queryset = CoinFlowTransaction.objects.filter(
        transaction_type= CoinFlowTransaction.TransactionType.withdraw_request,
    ).order_by("-modified").all()

    context_object_name = "casinobetslipreport"
    paginate_by = 20
    allowed_roles = ["admin", "agent"]
    date_format = "%d/%m/%Y"



    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def get_queryset(self):
        queryset = super().get_queryset()
        user = Users.objects.get(username=self.request.user)

        try:
            if(self.request.GET.getlist("players", None)):
                queryset = queryset.filter(user__id__in=self.request.GET.getlist("players"))

            # if self.request.GET.get("status") and self.request.GET.get("status") != "all":
            #     queryset = queryset.filter(status=self.request.GET.get("status"))

            # if self.request.GET.get("type"):
            #     queryset = queryset.filter(type = self.request.GET.get("type"))


            if self.request.GET.get("from"):
                start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
                queryset = queryset.filter(created__gte=start_date)
            else:
                # by default show results from first day of month
                current_date = timezone.now()
                first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
                queryset = queryset.filter(created__gte=first_day_of_month)

            if self.request.GET.get("to"):
                end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
                queryset = queryset.filter(created__date__lte=end_date)
            return queryset
        except Exception as e:
            return queryset


    def get_context_data(self, **kwargs):
        # by default show results from first day of month
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

        context = super().get_context_data(**kwargs)
        context["type"] = self.request.GET.get("type", None)
        context["status"] = self.request.GET.get("status", None)
        context["username"] = self.request.GET.get("username", "")
        context["from"] = self.request.GET.get("from", first_day_of_month)
        context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))
        
        context["payment_status"] = self.request.GET.get("payment_status", None)
        context["transaction_type"] = self.request.GET.get("transaction_type", None)
        context["selected_players"] = self.request.GET.getlist("players", [])

        return context


class ApproveWithdrawalRequest(CheckRolesMixin, views.JSONResponseMixin,
                                 views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        trans_id = request.POST.get('trans_id')
        new_status = request.POST.get('status')
        try:
            if new_status == 'cancelled':
                withdrawal_request = WithdrawalRequests.objects.get(id=trans_id)
                withdrawal_request.status = new_status
                player=withdrawal_request.user
                player.balance += withdrawal_request.amount  
                player.save()
                try:
                    Transactions.objects.update_or_create(
                    user=player,
                    journal_entry="debit",
                    amount=withdrawal_request.amount,
                    status="charged",
                    merchant=request.user,
                    previous_balance=player.balance-int(withdrawal_request.amount),
                    new_balance=player.balance,
                    description=f'withdrawal refund for cancelled amount {withdrawal_request.amount}',
                    reference=generate_reference(player),
                    bonus_type= None,
                    bonus_amount=0
                )
                    withdrawal_request.save()
                    send_player_balance_update_notification(player)
                except Exception as e:
                    print(e)
                Thread(target=transaction_mail,
                        args=(withdrawal_request.id)).start()
            elif new_status == 'approved':
                check = createnowpaymentswithdrawal(trans_id)       
                print(check,"approval_check")
                withdrawal_request = WithdrawalRequests.objects.get(id=trans_id)
                withdrawal_request.status = new_status
                player=withdrawal_request.user

                try:
                    if check==True:
                            withdrawal_request.save()
                            return JsonResponse({'status': 'success', 'message': 'Status updated successfully.'})
                    elif check==False:
                            player=withdrawal_request.user
                            player.balance += withdrawal_request.amount  
                            player.save()
                            withdrawal_request = WithdrawalRequests.objects.get(id=trans_id)
                            withdrawal_request.status = 'REJECTED'
                            withdrawal_request.save()
                            try:
                                Transactions.objects.update_or_create(
                                    user=player,
                                    journal_entry="debit",
                                    amount=withdrawal_request.amount,
                                    status="charged",
                                    merchant=request.user,
                                    previous_balance=player.balance-int(withdrawal_request.amount),
                                    new_balance=player.balance,
                                    description=f'withdrawal refund for cancelled amount {withdrawal_request.amount}',
                                    reference=generate_reference(player),
                                    bonus_type= None,
                                    bonus_amount=0
                                )
                                send_player_balance_update_notification(player)
                            except Exception as e:
                                pass 

                            Thread(target=transaction_mail,
                            args=(withdrawal_request.id,)).start()
                            return JsonResponse({'status': 'error', 'message': 'Something went wrong'})
                    else:
                        withdrawal_request.status = check
                        withdrawal_request.save()
                        player=withdrawal_request.user
                        player.balance += withdrawal_request.amount  
                        player.save()
                        try:
                            Transactions.objects.update_or_create(
                                user=player,
                                journal_entry="debit",
                                amount=withdrawal_request.amount,
                                status="charged",
                                merchant=request.user,
                                previous_balance=player.balance-int(withdrawal_request.amount),
                                new_balance=player.balance,
                                description=f'withdrawal refund for cancelled amount {withdrawal_request.amount}',
                                reference=generate_reference(player),
                                bonus_type= None,
                                bonus_amount=0
                            )
                            send_player_balance_update_notification(player)
                        except Exception as e:
                            pass

                        Thread(target=transaction_mail,
                        args=(withdrawal_request.id,)).start() 
                        return JsonResponse({'status': 'error', 'message':check})

                except Exception as e:
                    print(e)         


            return JsonResponse({'status': 'success', 'message': 'Status updated successfully.'})
        except WithdrawalRequests.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Withdrawal request not found.'})


class NowPaymentsReportView(CheckRolesMixin, ListView):
    template_name = "report/nowpayments_report.html"
    model = GSoftTransactions
    queryset = NowPaymentsTransactions.objects.order_by("-created").all()
    withdrawal_amounts = WithdrawalRequests.objects.filter(transaction_id=OuterRef('pk')).values('amount')
    queryset = queryset.annotate(withdrawal_amount=Subquery(withdrawal_amounts))

    context_object_name = "casinobetslipreport"
    paginate_by = 20
    allowed_roles = ("admin", "superadmin", "dealer", "agent")
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        queryset = super().get_queryset()
        try:
            if self.request.GET.getlist("players", None):
                queryset = self.queryset.filter(user__in = self.request.GET.getlist("players"))

            if self.request.GET.get("from"):
                # start_date = datetime.datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%d-%m-%Y")
                start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
                queryset = queryset.filter(created__gte=start_date)
            else:
                # by default show results from first day of month
                current_date = timezone.now()
                first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
                queryset = queryset.filter(created__gte=first_day_of_month)

            if self.request.GET.get("to"):
                end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
                queryset = queryset.filter(created__date__lte=end_date)

            if self.request.GET.getlist("dealers"):
                dealers = self.request.GET.getlist("dealers")
                queryset = queryset.filter(user__dealer__in=dealers)

            if self.request.GET.getlist("agents"):
                agents = self.request.GET.getlist("agents")
                queryset = queryset.filter(user__agent__in=agents)

            if self.request.GET.get("payment_status"):
                queryset = queryset.filter(payment_status=self.request.GET.get("payment_status"))

            if self.request.GET.get("transaction_type"):
                queryset = queryset.filter(transaction_type=self.request.GET.get("transaction_type"))


        except Exception as e:
            return queryset
        return queryset

    def get_context_data(self, **kwargs):
        # by default show results from first day of month
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

        context = super().get_context_data(**kwargs)
        context["from"] = self.request.GET.get("from", first_day_of_month)
        context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))
        context["payment_status"] = self.request.GET.get("payment_status", None)
        context["transaction_type"] = self.request.GET.get("transaction_type", None)

        return context

class CoinFlowReportView(CheckRolesMixin, ListView):
    template_name = "report/coinflow_report.html"
    model = CoinFlowTransaction
    queryset = CoinFlowTransaction.objects.exclude(
        transaction_type=CoinFlowTransaction.TransactionType.withdraw_request,
    ).order_by("-created").all()

    context_object_name = "casinobetslipreport"
    paginate_by = 20
    allowed_roles = ("agent", "admin", "superadmin")
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        queryset = super().get_queryset()
        try:
            if self.request.GET.getlist("players", None):
                queryset = self.queryset.filter(user__in = self.request.GET.getlist("players"))

            if self.request.GET.get("from"):
                # start_date = datetime.datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%d-%m-%Y")
                start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
                queryset = queryset.filter(created__gte=start_date)
            else:
                # by default show results from first day of month
                current_date = timezone.now()
                first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
                queryset = queryset.filter(created__gte=first_day_of_month)

            if self.request.GET.get("to"):
                end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
                queryset = queryset.filter(created__date__lte=end_date)

            if self.request.GET.getlist("dealers"):
                dealers = self.request.GET.getlist("dealers")
                queryset = queryset.filter(user__dealer__in=dealers)

            if self.request.GET.getlist("agents"):
                agents = self.request.GET.getlist("agents")
                queryset = queryset.filter(user__agent__in=agents)

            if self.request.GET.get("payment_status"):
                queryset = queryset.filter(status=self.request.GET.get("payment_status"))

            if self.request.GET.get("transaction_type"):
                queryset = queryset.filter(transaction_type=self.request.GET.get("transaction_type"))


        except Exception as e:
            return queryset
        return queryset

    def get_context_data(self, **kwargs):
        # by default show results from first day of month
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

        context = super().get_context_data(**kwargs)
        context["from"] = self.request.GET.get("from", first_day_of_month)
        context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))
        context["payment_status"] = self.request.GET.get("payment_status", None)
        context["transaction_type"] = self.request.GET.get("transaction_type", None)

        return context

class WithdrawalCurrenciesView(CheckRolesMixin, ListView):
    allowed_roles = ["admin",]
    template_name = "admin/withdrawal_currencies.html"
    paginate_by = 20
    model = WithdrawalCurrency
    queryset = WithdrawalCurrency.objects.all()
    context_object_name = "withdrawal_currencies"
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        queryset = super().get_queryset()
        currency = self.request.GET.get("currency_id")
        if currency and len(currency) > 0:
            currency = [int(x) for x in currency.split(",") if x.isdigit()]

            if currency and len(currency) > 0 :
                currency_filter = [int(x) for x in currency]
                print(currency_filter)
                queryset = queryset.filter(id__in=currency_filter)
            return queryset

        return queryset

class WithdrawalCurrencyStatus(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin")

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        currency = request.POST.get("currency")
        print(currency)
        currency_obj = WithdrawalCurrency.objects.filter(
            id=currency,
        )


        if currency_obj.exists() and currency_obj.first().enabled:
            currency_obj.update(enabled = False)
            message = "Currency disabled"
        elif currency_obj.exists():
            currency_obj.update(enabled= True)
            message = "Currency enabled"

        return self.render_json_response({"status": "Success", "message": message})


class WithdrawalCurrencyAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "dealer", "superadmin", "tenant_manager")

    def post_ajax(self, request, *args, **kwargs):
        search = self.request.POST.get("search", "").strip()
        print(search)
        # admin_id = self.request.POST.get("adminId", None)
        currencies = WithdrawalCurrency.objects.all()
        if search:
            currencies = currencies.annotate(currency_name_lower=Lower("name")).filter(
                currency_name_lower__icontains=search.lower()
            )
        results = []
        for currency in currencies:
            results.append(
                    {
                        "value": currency.id,
                        "text": currency.name
                    }
                )
        return self.render_json_response(results)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class CreateNotes(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", )

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        try:
            note = request.POST.get("note").strip()
            dealer_id = request.POST.get("dealer_id")

            if note == '':
                return self.render_json_response({"status": "error", "message": "Please type the notes first."})

            user = Users.objects.get(id=dealer_id)
            user_note = UserNotes.objects.create(user=user, notes=note, admin=request.user)

            if user_note:
                message = _("Note has been saved successfully.")

            return self.render_json_response({"status": "success", "message": message})

        except:
            return self.render_json_response({"status": "error", "message": "Something went wrong"})


class DeleteNoteAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin",)

    def post_ajax(self, request, *args, **kwargs):
        try:
            note_id = request.POST.get("note_id", None)

            if note_id is None:
                return self.render_json_response({"status": "error", "message": "Something Went Wrong."})
            note = UserNotes.objects.get(id=note_id)

            note.delete()
            # return self.render_json_response({"status": "success", "message": " Player Note Deleted Successfully."})
            return JsonResponse({'success': True})

        except:
           return self.render_json_response({"status": "error", "message": "Something went wrong"})


    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class UpdateNoteAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin",)

    def post_ajax(self, request, *args, **kwargs):
        try:

            note_content = request.POST.get("note", None).strip()
            note_id = request.POST.get("note_id", None)
            if note_content == "":
                return self.render_json_response({"status": "error", "message": "Please enter the notes first."})

            note = UserNotes.objects.get(id=note_id)
            note.notes = note_content
            note.save()
            return self.render_json_response({"status": "success", "message": "Note Updated Successfully."})
            # return JsonResponse({'success': True})

        except:
           return self.render_json_response({"status": "error", "message": "Something went wrong"})


    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class ComingSoonPermissionView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("superadmin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        admin = Admin.objects.get(id=request.POST.get("admin_id"))
        enabled = request.POST.get("enabled")

        if enabled == "true":
            admin.is_coming_soon_enabled = True
        else:
            admin.is_coming_soon_enabled = False

        admin.save()

        return self.render_json_response({"status":"Success","message": _("Coming Soon Page permission updated")})


class ComingSoonPageView(CheckRolesMixin, TemplateView, View):
    template_name = "admin/cms/coming_soon.html"
    allowed_roles = ("admin")
    http_method_names = ("get",)

    def get(self, request, *args, **kwargs):
        admin_obj = Admin.objects.get(id=request.user.id)
        if admin_obj.coming_soon_scheduled and admin_obj.coming_soon_scheduled < timezone.now():
            admin_obj.is_coming_soon_enabled = False
            admin_obj.save()
        return render(request, template_name=self.template_name,
            context={
                "scheduled_at": admin_obj.coming_soon_scheduled,
                "bonus": admin_obj.coming_soon_bonus,
            })


class ComingSoonAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y %H:%M"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        admin = Admin.objects.get(id=self.request.user.id)
        bonus = self.request.POST.get("bonus", None)
        scheduled_at = self.request.POST.get("scheduled_at", None)
        enabled = self.request.POST.get("enabled", None) 
        if scheduled_at:
            scheduled_at = timezone.datetime.strptime(
                scheduled_at, self.date_format
            )
            admin.coming_soon_scheduled = scheduled_at

        if bonus:
            admin.coming_soon_bonus = bonus
        if enabled:
            enabled = True if enabled == 'true' else False
            admin.is_coming_soon_enabled = enabled

        admin.save()



        return self.render_json_response({"status": "success", "message": _("Coming Soon Page Updated Successfully")})


class PendingAffiliateRequests(CheckRolesMixin, views.JSONResponseMixin, ListView):
    template_name = "admin/affiliate_requests.html"
    allowed_roles = ("admin")
    context_object_name = "PendingAffiliates"
    model = AffiliateRequests
    queryset = AffiliateRequests.objects.order_by("-modified").all()
    date_format = "%d/%m/%Y"



    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def get_queryset(self):
        queryset = super().get_queryset()
        user = Users.objects.get(username=self.request.user)

        if(self.request.GET.getlist("players", None)):

            queryset = queryset.filter(user__id__in=self.request.GET.getlist("players"))


        if self.request.GET.get("status") and self.request.GET.get("status") != "all":
            queryset = queryset.filter(status=self.request.GET.get("status"))

        if self.request.GET.get("type"):
            queryset = queryset.filter(type = self.request.GET.get("type"))


        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__gte=start_date)
        else:
            # by default show results from first day of month
            current_date = timezone.now()
            first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
            queryset = queryset.filter(created__gte=first_day_of_month)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__date__lte=end_date)
        return queryset

    def get_context_data(self, **kwargs):
        # by default show results from first day of month
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

        context = super().get_context_data(**kwargs)
        context["type"] = self.request.GET.get("type", None)
        context["status"] = self.request.GET.get("status", None)
        context["username"] = self.request.GET.get("username", "")
        context["from"] = self.request.GET.get("from", first_day_of_month)
        context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))

        return context



class StaffsView(CheckRolesMixin, FormMixin, ListView):
    model = Staff
    paginate_by = 20
    template_name = "admin/staff/staffs.html"
    form_class = AgentModelForm
    allowed_roles = ["agent","admin","dealer"]
    context_object_name = "staffs"
    date_format = "%d/%m/%Y"
    queryset = Staff.objects.all()


    ORDER_MAPPING = {
        "1": "-last_login",
        "2": "balance",
        "3": "-balance",
        "4": "locked",
        "5": "-locked",
        "6": "created",
        "7": "-created",
    }

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def time_zone_converter(self,date_time_obj,Inverse_Time_flag):

        try:
            current_timezone = self.request.session['time_zone']
        except:
            current_timezone='en'
        if(current_timezone=="en"):
            return date_time_obj
        elif(current_timezone=='ru'):
            current_timezone='Europe/Moscow'
        elif(current_timezone=='tr'):
            current_timezone='Turkey'    
        else:
            current_timezone='Europe/Berlin'
        timee=date_time_obj.replace(tzinfo=None)
        if(Inverse_Time_flag):
            new_tz=pytz.timezone(current_timezone)
            old_tz=pytz.timezone("EST")
        else:
            old_tz=pytz.timezone(current_timezone)
            new_tz=pytz.timezone("EST")
        new_timezone_timestamp = old_tz.localize(timee).astimezone(new_tz)

        return new_timezone_timestamp


    def get_queryset(self):
        # self.queryset = self.queryset.annotate(total_chathistory=Count('staff_chathistory'))
        if self.request.user.role == 'admin':
            self.queryset =self.queryset
        if self.request.user.role == 'dealer':
            self.queryset =self.queryset.filter(dealer__id = self.request.user.id)
        if self.request.user.role == 'agent':
            self.queryset =self.queryset.filter(agent__id = self.request.user.id)
        user_name = self.request.GET.get("user_name",None)
        print(user_name)
        order = self.request.GET.get("order", "7")

        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
            self.queryset = self.queryset.filter(created__gte=start_date)


        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
            self.queryset = self.queryset.filter(created__date__lte=end_date)
        if user_name:
            print("here")
            self.queryset = self.queryset.filter(username=user_name)
            print(self.queryset)
        return self.queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        first_day_of_month_UTC = timezone.now()
        first_day_of_month=self.time_zone_converter(first_day_of_month_UTC,True).replace(day=1,hour=0,minute=0)
        current_time=timezone.now()
        current_time=self.time_zone_converter(current_time,True)
        context["username"] = self.request.GET.get("user_name", "")
        context["to"] = self.request.GET.get("to", current_time.strftime(self.date_format))
        context["from"] = self.request.GET.get("from", first_day_of_month.strftime(self.date_format))
        return context


class UpdateStaff(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("agent",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL) 

    def post_ajax(self, request, *args, **kwargs):
        user_name = request.POST.get("username", "")
        password = request.POST.get("password", "")

        pattern = re.compile("[A-Za-z0-9]*$")
        if not pattern.fullmatch(user_name):
            return self.render_json_response(
                {"status": "Failed", "message": "Username must be Alphanumeric"}
            )

        if len(user_name) < 4:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("The username has to be at least 4 characters"),
                }
            )

        if len(password) < 5:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("The password has to be at least 5 characters"),
                }
            )

        staff = Staff.objects.get(username__iexact=user_name)
        staff.password = make_password(password)
        staff.role = "staff"
        staff.is_staff = True
        staff.is_superuser = False
        staff.is_active = True
        staff.save()

        return self.render_json_response({"status": "Success", "message": _("Staff has been edited.")})

class ApproveAffiliateRequest(CheckRolesMixin, views.JSONResponseMixin,
                                 views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)
    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        id = request.POST.get('trans_id')
        new_status = request.POST.get('status')
        try:
            if new_status == 'cancelled':
                affiliate_request = AffiliateRequests.objects.get(id=id)
                affiliate_request.status = new_status  
                affiliate_request.save()

            elif new_status == 'approved':
                affiliate_request = AffiliateRequests.objects.get(id=id)
                affiliate_request.status = new_status
                player=affiliate_request.user
                player.no_of_deposit_counts = affiliate_request.no_of_deposit_counts
                player.is_bonus_on_all_deposits = affiliate_request.is_bonus_on_all_deposits
                player.affliate_expire_date = datetime.now() + timedelta(affiliate_request.no_of_days)
                player.is_lifetime_affiliate = affiliate_request.is_lifetime_affiliate
                player.save()
                affiliate_request.save()
            return JsonResponse({'status': 'success', 'message': 'Status updated successfully.'})    

        except Exception as e:
                print(e)         
                return JsonResponse({'status': 'error', 'message': 'Something went wrong'})



class CreateStaff(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("agent",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)    

    def post_ajax(self, request, *args, **kwargs):
        user_name = request.POST.get("username", "").lower()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if Users.objects.filter(username__iexact=user_name).exists():
            return self.render_json_response({"status": "Failed", "message": _("Username already exists")})

        pattern = re.compile("[A-Za-z0-9]*$")
        if not pattern.fullmatch(user_name):
            return self.render_json_response(
                {"status": "Failed", "message": _("Username must be Alphanumeric")}
            )

        if len(user_name) < 4:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("The username has to be at least 4 characters"),
                }
            )

        if len(password) < 5:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("The password has to be at least 5 characters"),
                }
            )

        if password != confirm_password:
            return self.render_json_response(
                {
                    "status": "Failed",
                    "message": _("Confirm password does not match password."),
                }
            )

        staff = Staff()
        staff.username = user_name
        staff.password = make_password(password)
        staff.agent = request.user
        staff.dealer = request.user.dealer
        staff.admin = request.user.admin
        staff.role = "staff"
        staff.is_staff = True
        staff.is_superuser = False
        staff.is_active = True
        staff.save()


        return self.render_json_response({"status": "Success", "message": "Staff created"})



class DefaultAffiliateSetingsView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"
    def post_ajax(self, request, *args, **kwargs):
        try:
            percentage = self.request.POST.get("percentage", None)
            no_of_days = self.request.POST.get("no_of_days", None)
            deposit_count = self.request.POST.get("deposit_count", None)
            default_val = DefaultAffiliateValues.objects.first()
            if default_val:
                if no_of_days:
                    default_val.default_no_of_days = no_of_days
                if deposit_count:
                    default_val.default_no_of_deposit_counts = deposit_count
                if percentage:
                    default_val.default_affiliation_percentage = percentage
                default_val.save()
            else:
                default_val = DefaultAffiliateValues()
                if no_of_days:
                    default_val.default_no_of_days = no_of_days
                if deposit_count:
                    default_val.default_no_of_deposit_counts = deposit_count
                if percentage:
                    default_val.default_affiliation_percentage = percentage
                default_val.save()

            return self.render_json_response({"status": "success", "message": _("Changes Done")})
        except Exception as e:
            print(e)
            return self.render_json_response({"status": "error", "message": _("Something Went Wrong")})


class DefaultSettingsView(CheckRolesMixin, ListView):

    template_name = "admin/affiliate/default_affiliate_settings.html"
    model = DefaultAffiliateValues
    queryset = DefaultAffiliateValues.objects.order_by("-created").all()
    context_object_name = "affiliate"
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"


    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            default_obj = self.queryset.first()

            if default_obj:

                context["no_of_days"] = default_obj.default_no_of_days
                context["deposit_count"] = default_obj.default_no_of_deposit_counts
                context["percentage"] = default_obj.default_affiliation_percentage
            else:
                context["no_of_days"] = 0
                context["deposit_count"] = 0
                context["percentage"] = 0



        except DefaultAffiliateValues.DoesNotExist:
            context["no_of_days"] = 0
            context["deposit_count"] = 0
            context["percentage"] = 0
        return context

class StaffWalletAndTransactionsView(CheckRolesMixin, ListView, views.JSONResponseMixin, views.AjaxResponseMixin, View):

    template_name = "admin/staff_wallet_and_transactions.html"
    context_object_name = "stafftransactions"
    allowed_roles = ("staff")
    date_format = "%d/%m/%Y"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_queryset(self):
        queryset = NowPaymentsTransactions.objects.filter(user=self.request.user,transaction_type='WITHDRAWAL').order_by("-created").all()
        withdrawal_amounts = WithdrawalRequests.objects.filter(transaction_id=OuterRef('pk')).values('amount')
        queryset = queryset.annotate(withdrawal_amount=Subquery(withdrawal_amounts))
        myset = {
            "nowp": queryset,
            "tips": Transactions.objects.filter(description__icontains=self.request.user.username).order_by("-created").all()
        }
        return myset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context["wallet_address"] = self.request.user.wallet_address
            context["wallet_currency"] = self.request.user.wallet_currency
            context["saved_currencies"] = self.request.user.staff_currencies
            context['currencies']  =  list(WithdrawalCurrency.objects.values_list('code', flat=True))
            return context
        except Exception as e:
            print("Exception",e)
            return context

    def post_ajax(self, request, *args, **kwargs):
        try:
            wallet_address = request.POST.get("wallet_address")
            wallet_currency = request.POST.get("wallet_currency")

            user = Users.objects.filter(id=self.request.user.id).first()
            if user:
                user.wallet_address = wallet_address
                user.wallet_currency = wallet_currency
                currencies ={
                    wallet_currency: wallet_address,
                }
                # if wallet_currency in user.staff_currencies:
                #     existing_currencies = user.staff_currencies
                existing_currencies = user.staff_currencies if user.staff_currencies else {}

                existing_currencies.update(currencies)
                user.staff_currencies = existing_currencies
                user.save()
                return self.render_json_response({"status": "Success", "message": "Wallet Details Updated Successfully"}, 200)

        except:
            print(traceback.format_exc(), flush=True)
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})



class ChatRoomView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/chats/chat_room.html"
    allowed_roles = ("staff")
    date_format = "%Y-%m-%d %H:%M:%S.%f%z"
    context_object_name = "messages"
    queryset = ChatMessage.objects.all().order_by('-sent_time')

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def get(self, request, *args, **kwargs):
        staff_agent = request.user.agent
        players_in_queue  = Queue.objects.filter(Q(pick_by=request.user) | Q(pick_by__isnull=True), user__agent=staff_agent,is_active = True)
        players_in_queue_count = players_in_queue.count()
        recent_ten_players_in_queue = players_in_queue.order_by('created')[:10]
        players_in_queue = [ {
            'id' : entry.user.id,
            'name' : entry.user.username,
            'queue_id':entry.id}
        for entry in recent_ten_players_in_queue]
        game_codes = list(OffMarketGames.objects.values_list('code', flat=True))
        game_names = list(OffMarketGames.objects.values_list('title', flat=True))
        game_data = list(zip(game_codes, game_names))
        print(game_data)


        return render(request,template_name=self.template_name,
                context={
                        'players_count_in_queue' : players_in_queue_count,
                        'players_in_queue' : players_in_queue,
                        'game_data': game_data


                    })
    def post_ajax(self, request, *args, **kwargs):
        try:

            operation = self.request.POST.get('type',None)
            if operation == 'players_count_in_queue':
                staff_agent = request.user.agent
                is_staff_active = request.user.is_staff_active
                players_in_queue  = Queue.objects.filter(Q(pick_by=request.user) | Q(pick_by__isnull=True) ,user__agent=staff_agent,is_active=True)
                players_in_queue_count = players_in_queue.count()
                recent_ten_players_in_queue = players_in_queue.order_by('created')[:10]
                players_in_queue = [ {
                    'id' : entry.user.id,
                    'name' : entry.user.username,
                    'queue_id':entry.id
                }
                for entry in recent_ten_players_in_queue]
                return self.render_json_response({"status": "Success", "players_count_in_queue": players_in_queue_count,'players_in_queue':players_in_queue,"is_staff_active":is_staff_active}, 200)

            elif operation == 'toggle_status':
                staff_status =  True if self.request.POST.get('staff_status') == 'true' else False
                staff = Users.objects.filter(id=self.request.user.id).first()
                if staff:
                    staff.is_staff_active = staff_status
                    staff.save()
                    return self.render_json_response({"status": "Success", "room_name": "P5Chat"}, 200)

            elif operation == 'add_player':
                username = self.request.POST.get('username')
                game_code = self.request.POST.get('code') 
                player_username = self.request.POST.get('user')
                player_id = int(player_username.replace("P", "").replace("Chat", ""))

                success, message = RefujiClient.create_user(
                    player_id=player_id,
                    game_code=game_code,
                    username=username,
                )

                if not success:
                    return self.render_json_response(
                        {"status": "Failed", "message": _(message)}
                    )

                return self.render_json_response(
                    {"status": "success", "message": _("Account Created Successfully")},
                    status=status.HTTP_200_OK,
                )

            elif operation == 'reconnect':
                return self.render_json_response({"status": "Success"}, 200)
            elif operation == 'recent_messages':
                chatroom_name = self.request.POST.get("chatroom_name", None)
                chat_messages = ChatMessage.objects.filter(room__name=chatroom_name,created__date = datetime.now().date()).order_by('created')
                staff = Users.objects.filter(id=self.request.user.id).first()
                messages = []
                for message in chat_messages:
                    messages.append({
                        'message': message.file.name if message.is_file else message.message_text,
                        'sender': message.sender.username,
                        'sent_time': message.sent_time,
                        'is_file': str(message.is_file).capitalize(),
                        'file': message.file.name,
                        "staff":staff.username
                    })

                return self.render_json_response({"status": "Success", "messages": messages}, status=200)

            elif operation == 'update_queue_status':
                queue_id = self.request.POST.get("queue_id", None)
                queue_entry = Queue.objects.filter(id=queue_id).update(pick_by = request.user)
                return self.render_json_response({"status": "Success"}, 200)

            else:
                # chatroom,is_created = ChatRoom.objects.get_or_create(name='P5Chat')
                staff_agent = request.user.agent
                queue_entry = Queue.objects.filter(user__agent=staff_agent,is_active=True).order_by('created').first()
                if queue_entry:
                    roomname = f'P{queue_entry.user.id}Chat'
                    chatroom,is_created = ChatRoom.objects.get_or_create(name=roomname)
                    # queue_entry.is_active = True  # None means the player query entry is in chat
                    # queue_entry.pick_by = request.user
                    # queue_entry.is_remove = True
                    # queue_entry.save()
                    return self.render_json_response({"status": "Success", "room_name": chatroom.name}, 200)
                else:
                    return self.render_json_response({"status":"Error","message": "No Player Available to Chat"}, 405)

            return self.render_json_response({"status": "Error"}, 405)
        except:
            return self.render_json_response({"status": "Error"}, 500)





class LeaveRoomview(TemplateView,View):
    def post(self, request, *args, **kwargs):
        try:
            player_id = self.request.POST.get('user_id',None)
            que = Queue.objects.filter(user_id =int(player_id)).update(is_remove = False,is_active=False,pick_by = None)
            return JsonResponse({"status": "Queue status isupdated"})
        except:
            return JsonResponse({"status": "Error"}, 500)




class ChatHistoryView(CheckRolesMixin, ListView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/chats/chat_history.html"
    model = ChatHistory
    queryset = ChatHistory.objects.order_by("-created").all()
    context_object_name = "chathistories"
    allowed_roles = ("staff","agent","dealer","admin")
    date_format = "%d/%m/%Y"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def time_zone_converter(self, date_time_obj, Inverse_Time_flag):

        try:
            current_timezone = self.request.session.get("time_zone", "en")
        except Exception:
            current_timezone = "en"
        if current_timezone == "en":
            return date_time_obj
        elif current_timezone == "ru":
            current_timezone = "Europe/Moscow"
        elif current_timezone == "tr":
            current_timezone = "Turkey"
        else:
            current_timezone = "Europe/Berlin"
        timee = date_time_obj.replace(tzinfo=None)
        if Inverse_Time_flag:
            new_tz = pytz.timezone(current_timezone)
            old_tz = pytz.timezone("EST")
        else:
            old_tz = pytz.timezone(current_timezone)
            new_tz = pytz.timezone("EST")
        new_timezone_timestamp = old_tz.localize(timee).astimezone(new_tz)
        return new_timezone_timestamp


    def get_queryset(self):
        queryset = super().get_queryset()
        from_date =  self.request.GET.get('from', "")
        to_date = self.request.GET.get('to', "")
        player_search = self.request.GET.get('player_search', "")
        staff_search = self.request.GET.get('staff_search', "")
        current_date = timezone.now()
        first_day_of_month_UTC = current_date.replace(day=1, hour=0, minute=0, second=0)
        first_day_of_month = self.time_zone_converter(first_day_of_month_UTC, True).replace(
            day=1, hour=0, minute=0, second=0
        )
        if self.request.GET.get("from"):
            from_date = datetime.strptime(self.request.GET.get("from"), self.date_format)
            from_date = self.time_zone_converter(from_date, False)
        else:
            from_date=first_day_of_month
            first_day_of_month_UTC = self.time_zone_converter(first_day_of_month, False).replace(tzinfo=None)
        if self.request.GET.get("to"):
            to_date = datetime.strptime(self.request.GET.get("to"), self.date_format)
            to_date = self.time_zone_converter(to_date, False)
        else:
            to_date = timezone.now().replace(tzinfo=None)
        if(from_date == to_date):
            to_date = to_date + timedelta(days=1)

        if player_search.strip() != '':
            self.queryset = self.queryset.filter(player__username=player_search.strip())
        if staff_search.strip() != '':
            self.queryset = self.queryset.filter(staff__username=staff_search.strip())

        self.queryset = self.queryset.filter(created__range=(from_date, to_date))



        return self.queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            current_date = datetime.now()
            current_time = self.time_zone_converter(timezone.now(), True)
            first_day_of_month_UTC = current_date.replace(day=1, hour=0, minute=0, second=0)
            first_day_of_month = self.time_zone_converter(first_day_of_month_UTC, True).replace(
                day=1, hour=0, minute=0, second=0
            )

            if(self.request.GET.get("from")):
                context["from"] = self.request.GET.get("from")
            else:
                context["from"] = first_day_of_month.strftime(self.date_format)
            if(self.request.GET.get("to")):
                context["to"] = self.request.GET.get("to")
            else:
                context["to"] = current_time.strftime(self.date_format)

            context['player_search'] = self.request.GET.get("player_search",'')
            context['staff_search'] = self.request.GET.get("staff_search",'')

            context['timezone'] = Admin.objects.first().timezone 

            return context
        except Exception as e:
            print("Exception",e)
            return context

class CreateWithdrawalRequest(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("staff",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL) 

    def post_ajax(self, request, *args, **kwargs):
        try:
            amount = request.POST.get("amount", "")
            address = request.POST.get("address", "")
            currency = request.POST.get("currency", "")
            address_validation = validate_address(address,currency)
            if not address_validation:
                return self.render_json_response(
                    {
                        "status": "Failed",
                        "message": _("Invalid Address"),
                    }
                )
            user = Users.objects.filter(id=request.user.id).first()
            if Decimal(amount) > request.user.balance:
                return self.render_json_response(
                    {
                        "status": "Failed",
                        "message": _("amount is greater than available balance"),
                    }
                )
            WithdrawalRequests.objects.create(
                user = user,
                amount=amount,
                address=address,
                currency = currency
                )
            user.balance = user.balance-Decimal(amount)
            user.save()

            return self.render_json_response({"status": "Success", "message": _("Withdrawal Request Created.")})
        except Exception as e:
            print(e)
            return self.render_json_response({"status": "Error", "message": _("Something went wrong")})


class ChatHistoryTabView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/chats/chat_history_tab.html"
    allowed_roles = ("staff","dealer","agent","admin")
    date_format = "%Y-%m-%d %H:%M:%S.%f%z"
    context_object_name = "messages"
    queryset = ChatMessage.objects.all().order_by('-sent_time')


    def get(self, request, *args, **kwargs):
        chat_history_id = request.GET.get('ch_id')
        if chat_history_id:
            chat_history = ChatHistory.objects.filter(id=chat_history_id).first()
            if chat_history:
                messages = chat_history.chats
                staff = chat_history.staff
                player = chat_history.player
                chat_history_id = chat_history.id
                return render(request,template_name=self.template_name,
                        context={
                            "messages":messages,
                            "staff":staff,
                            "player":player,
                            "chathistory_id":chat_history_id,
                            "created_date" : chat_history.created
                            })
        return render(request,template_name=self.template_name,
                        context={

                            })


class UserCashtag(CheckRolesMixin, views.JSONResponseMixin, ListView):
    model = Users
    paginate_by = 10
    template_name = "admin/player/players.html"
    allowed_roles = ("admin")
    context_object_name = "cashtag"
    queryset = Player.objects.filter(affiliate_link__isnull=False).order_by("-created")



    # def get_queryset(self):

    #     user = self.request.GET.get('user_name',[])
    #     if user:
    #         self.queryset = self.queryset.filter(id=user)

    #     if self.request.user.role == "admin":
    #         self.queryset = self.queryset
    #         self.queryset = self.queryset.annotate(
    #             total_earned=Coalesce(Sum(F('transactions__bonus_amount'), filter=Q(transactions__journal_entry='bonus', transactions__bonus_type='affiliate_bonus')), 0.00)
    #         )
    #     return self.queryset        

    # def get_context_data(self, **kwargs):
    #     context = super().get_context_data(**kwargs)

    #     dealers = self.request.GET.get('dealers', [])
    #     agents = self.request.GET.get('agents', [])


    #     if dealers:
    #         context["selected_dealers"] = Dealer.objects.filter(id__in=dealers.split(","))

    #     if agents:
    #         context["selected_agents"] = Agent.objects.filter(id__in=agents.split(","))
    #     return context        

    def post(self, request):
        try:
            cashtag = request.POST.get("cashtag", None)
            user_id = request.POST.get("player_id", None)
            user = Player.objects.filter(id=user_id).first()
            if user:
                if user.cashtag!=cashtag:
                    if Player.objects.filter(cashtag=cashtag).exists(): 
                        return self.render_json_response({"title":"Error","icon":"error","message": "Cashtag Already Exists!"}, status.HTTP_400_BAD_REQUEST) 
                    else:
                        user.cashtag = cashtag
                        user.save()
                        return self.render_json_response({"title":"Success","icon":"success","message": "Cashtag Updated Succesfully"}, status.HTTP_200_OK)
                else:
                    user.cashtag = cashtag
                    user.save()
                    return self.render_json_response({"title":"Success","icon":"success","message": "Cashtag Updated Succesfully"}, status.HTTP_200_OK)
            else:
                return self.render_json_response({"title":"Error","icon":"error","message": "User not Found!"}, status.HTTP_400_BAD_REQUEST)    

        except Exception as e:
            print(e)
            return self.render_json_response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)




class OffMarketGamessView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ["admin", ]
    template_name = "offmarkets/games.html"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request):
        try:
            if request.user.role == 'admin':
                offmarket_games = OffMarketGames.objects.all().order_by('-created')
                return render(request, template_name=self.template_name,
                              context={
                                  "offmarket_games": offmarket_games,
                                  "admin": request.user.id,
                              })
            else:
                return render(request, template_name=self.template_name,
                            #   context={"error": "Not An Unauthorized User"},
                              status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class CreateOffMarketGameView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ["admin", "superadmin",]
    template_name = "offmarkets/create_game.html"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request):
        try:
            if request.user.role == 'admin':
                form = OffMarketGameForm()


                return render(request, template_name=self.template_name,
                              context={"form": form
                              })
            else:
                return render(request, template_name=self.template_name,
                            #   context={"error": "Not An Unauthorized User"},
                              status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            if request.user.role == 'admin':
                form = OffMarketGameForm(request.POST, request.FILES)
                game_img = request.FILES.get('url')
                game_code = request.POST.get('code')
                game_user = request.POST.get('game_user')
                game_pass = request.POST.get('game_pass')
                if OffMarketGames.objects.filter(code=game_code.strip()).exists():
                        messages.error(request, _("Game Code already exists"))
                        return redirect('admin-panel:create-offmarket-game')
                if form.is_valid():
                    game_code = form.cleaned_data['code']
                    if OffMarketGames.objects.filter(code=game_code.strip()).exists():
                        messages.error(request, _("Game already exists"))
                        return redirect('admin-panel:create-offmarket-game')

                    filename_format = game_img.name.split(".")
                    name, format = filename_format[-2], filename_format[-1]
                    filename = f"{name}{uuid.uuid4()}.{format}"
                    game_img.name = filename

                    game_img = Image.open(game_img)                    
                    game_img_io = BytesIO()

                    format = 'JPEG' if format.lower() == 'jpg' else format.upper()

                    game_img.save(game_img_io, format=format,optimize=True)
                    game_img_io_inmemory = InMemoryUploadedFile(
                        game_img_io,
                        'FileField',
                        filename,
                        format,
                        sys.getsizeof(game_img_io),
                        None
                    )
                    game_obj = OffMarketGames(
                        url=game_img_io_inmemory,
                        title=form.cleaned_data['title'],
                        coming_soon= form.cleaned_data['coming_soon'],
                        game_status =  form.cleaned_data['game_status'],
                        code = form.cleaned_data['code'],
                        bonus_percentage = form.cleaned_data['bonus_percentage'],
                        download_url = form.cleaned_data['download_url'],
                        game_user = form.cleaned_data['game_user'],
                        game_pass = form.cleaned_data['game_pass']
                    )
                    game_obj.save()
                    messages.success(request, "Game successfully Added")
                    return redirect('admin-panel:offmarket-games')

                messages.error(request, _("Please provide valid game details!"))
                return redirect('admin-panel:create-offmarket-game')
            else:
                return render(request, template_name=self.template_name,
                              context={"error": "Not An Unauthorized User"},
                              status=status.HTTP_401_UNAUTHORIZED)

        except Exception as e:
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class EditOffMarketGameView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "offmarkets/edit_game.html"
    allowed_roles = ("admin", "staff")
    date_format = "%d/%m/%Y %H:%M"
    context_object_name = "games"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def get(self, request, *args, **kwargs):
        game_id = self.request.GET.get("game_id", "")
        game_obj = OffMarketGames.objects.filter(id=game_id).first()
        form = OffMarketGameForm(instance=game_obj)


        return render(
            request,
            template_name=self.template_name,
            context={
                "form": form,
                "game" : game_obj
            }
        )

    def post(self, request, *args, **kwargs):
        try:
            title = request.POST.get("title", None)
            code = request.POST.get("code", None)
            bonus_percentage = request.POST.get("bonus_percentage", None)

            game_img = request.FILES.get('url', None)
            game_id = request.GET.get('game_id', None)
            coming_soon = True if request.POST.get('coming_soon', None) == 'on' else False 
            game_status = True if request.POST.get('game_status', None) == 'on' else False
            is_api_prefix = True if request.POST.get('is_api_prefix', None) == 'on' else False
            download_url = request.POST.get('download_url', None)
            game_user = request.POST.get('game_user', None)
            game_pass = request.POST.get('game_pass', None)
            game_obj = OffMarketGames.objects.filter(id=game_id).first()
            if game_user and game_obj.game_user != game_user and OffMarketGames.objects.filter(game_user=game_user).exists():
                    messages.error(request, _("Game Login ID already exists"))
                    return redirect('admin-panel:offmarket-games')

            if code and game_obj.code != code and OffMarketGames.objects.filter(code=code.strip()).exists():
                messages.error(request, _("Game Code already exists"))
                return redirect('admin-panel:offmarket-games')
            if game_img:
                filename_format = game_img.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                game_img.name = filename

                game_img = Image.open(game_img)                
                game_img_io = BytesIO()

                format = 'JPEG' if format.lower() == 'jpg' else format.upper()                
                game_img.save(game_img_io, format=format,optimize=True)
                game_img_io_inmemory = InMemoryUploadedFile(game_img_io,
                                                                'FileField',
                                                                 filename,
                                                                 format,
                                                                 sys.getsizeof(game_img_io), None)

                game_obj.url = game_img_io_inmemory

            game_obj.title = title
            game_obj.code = code
            game_obj.bonus_percentage = bonus_percentage
            game_obj.coming_soon = coming_soon
            game_obj.game_status = game_status
            game_obj.download_url = download_url
            game_obj.is_api_prefix = is_api_prefix
            game_obj.game_user = game_user
            game_obj.game_pass = game_pass
            game_obj.save()
            messages.success(request, "Game Details updated successfully")
            return redirect('admin-panel:offmarket-games')


        except Exception as e:
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:offmarket-games')



class UserGamesView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("get",)
    allowed_roles = ("admin", "dealer", "superadmin","agent","staff")


    def get_ajax(self, request, *args, **kwargs):
        context=dict()
        game_id = request.GET.get("game_id")
        if game_id:
            UserGames.objects.filter(id=game_id).delete()
        player_id = request.GET.get("player_id")
        print(player_id)
        player_games = list(UserGames.objects.filter(user=player_id).values('id', 'username','game__title', 'game__id', 'game__code'))
        dic = {}
        dic['role'] = request.user.role
        dic['player_games'] = player_games
        return JsonResponse(dic)


class CreateUserGamesView(CheckRolesMixin,views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "agent")

    def post_ajax(self, request, *args, **kwargs):
        try:
            username=request.POST.get("username", "")
            game=request.POST.get("game", "")
            user=request.POST.get("user", "")

            if UserGames.objects.filter(game=game, user_id = user).exists():
                return self.render_json_response({
                    "status": "Failed", 
                    "message": _("User Already have Account For this Game")
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            if UserGames.objects.filter(username=username, game=game).exists():
                return self.render_json_response({
                    "status": "Failed", 
                    "message": _("Username Already Exists")
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            usergame=UserGames()
            usergame.user_id=user
            usergame.game_id=game
            usergame.username=username

            usergame.save()

            return self.render_json_response({"status": "Success", "message": "Usergame created"}, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error in create usergame api : {e}")
            return self.render_json_response({"status": "Failed", "message": "Something went wrong!"}, status=status.HTTP_400_BAD_REQUEST)


class EditUserGamesView(CheckRolesMixin,views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "agent","staff")

    def post(self, request, *args, **kwargs):
        try:
            usergame_id = request.POST.get("usergame_id", "")
            username = request.POST.get("username", "")
            offmarket_game_id = request.POST.get("offmarket_game_id", "")
            user = request.POST.get("user", "")
            if UserGames.objects.filter(
                username=username,
                game__id=offmarket_game_id
            ).exclude(id = usergame_id).exists():
                return self.render_json_response({
                    "status": "Failed", 
                    "message": _("Username already exists")
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            usergame_obj = UserGames.objects.filter(id=usergame_id).first()
            usergame_obj.username=username
            usergame_obj.save()

            return self.render_json_response({"status": "Success", "message": "UserGame Updated"}, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error in create usergame api : {e}")
            return self.render_json_response({"status": "Failed", "message": "Something went wrong!"}, status=status.HTTP_400_BAD_REQUEST)


class StaffAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "dealer", "superadmin","agent")


    def post_ajax(self, request, *args, **kwargs):
        term = request.POST.get("search")
        staffs = Staff.objects.all()

        agents = Agent.objects.all()
        dealer_ids = request.POST.getlist("dealer[]", None)
        agent_ids = request.POST.getlist("agent[]",None)
        if term:
            staffs = staffs.annotate(username_lower=Lower("username")).filter(
                username_lower__istartswith=term.lower()
            ).order_by('username')
        if request.user.role=='dealer':
            agents=agents.filter(dealer=self.request.user)
            staffs=staffs.filter(agent_id__in=agents)

        if request.user.role == "agent":
            staffs = staffs.filter(agent=self.request.user)

        elif agent_ids:
            staffs = staffs.filter(agent_id__in=agent_ids)

        elif dealer_ids:

            agents=agents.filter(dealer_id__in=dealer_ids)
            staffs=staffs.filter(agent_id__in=agents)

        staffs = staffs.values("id", "username")[0:10]

        results = []
        for staff in staffs:
            results.append({"value": staff["id"], "text": staff["username"]})

        return self.render_json_response(results)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)



class CsrQueryView(CheckRolesMixin, ListView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/unresolved_queries.html"
    model = CsrQueries
    queryset = CsrQueries.objects.order_by("-created").all()
    context_object_name = "chathistories"
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def time_zone_converter(self, date_time_obj, Inverse_Time_flag):

        try:
            current_timezone = self.request.session.get("time_zone", "en")
        except Exception:
            current_timezone = "en"
        if current_timezone == "en":
            return date_time_obj
        elif current_timezone == "ru":
            current_timezone = "Europe/Moscow"
        elif current_timezone == "tr":
            current_timezone = "Turkey"
        else:
            current_timezone = "Europe/Berlin"
        timee = date_time_obj.replace(tzinfo=None)
        if Inverse_Time_flag:
            new_tz = pytz.timezone(current_timezone)
            old_tz = pytz.timezone("EST")
        else:
            old_tz = pytz.timezone(current_timezone)
            new_tz = pytz.timezone("EST")
        new_timezone_timestamp = old_tz.localize(timee).astimezone(new_tz)
        return new_timezone_timestamp


    def get_queryset(self):
        queryset = super().get_queryset()
        from_date =  self.request.GET.get('from', "")
        to_date = self.request.GET.get('to', "")
        player_search = self.request.GET.get('player_search', "")
        staff_search = self.request.GET.get('staff_search', "")
        current_date = timezone.now()
        first_day_of_month_UTC = current_date.replace(day=1, hour=0, minute=0, second=0)
        first_day_of_month = self.time_zone_converter(first_day_of_month_UTC, True).replace(
            day=1, hour=0, minute=0, second=0
        )

        if(self.request.GET.getlist("players", None)):
            self.queryset = self.queryset.filter(user__id__in=self.request.GET.getlist("players"))
        if self.request.GET.get("from"):
            from_date = datetime.strptime(self.request.GET.get("from"), self.date_format)
            from_date = self.time_zone_converter(from_date, False)
        else:
            from_date=first_day_of_month
            first_day_of_month_UTC = self.time_zone_converter(first_day_of_month, False).replace(tzinfo=None)
        if self.request.GET.get("to"):
            to_date = datetime.strptime(self.request.GET.get("to"), self.date_format)
            to_date = self.time_zone_converter(to_date, False)
        else:
            to_date = timezone.now().replace(tzinfo=None)
        if(from_date == to_date):
            to_date = to_date + timedelta(days=1)

        if player_search.strip() != '':
            self.queryset = self.queryset.filter(player__username=player_search.strip())
        if staff_search.strip() != '':
            self.queryset = self.queryset.filter(staff__username=staff_search.strip())

        self.queryset = self.queryset.filter(created__range=(from_date, to_date))



        return self.queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            current_date = datetime.now()
            current_time = self.time_zone_converter(timezone.now(), True)
            first_day_of_month_UTC = current_date.replace(day=1, hour=0, minute=0, second=0)
            first_day_of_month = self.time_zone_converter(first_day_of_month_UTC, True).replace(
                day=1, hour=0, minute=0, second=0
            )

            if(self.request.GET.get("from")):
                context["from"] = self.request.GET.get("from")
            else:
                context["from"] = first_day_of_month.strftime(self.date_format)
            if(self.request.GET.get("to")):
                context["to"] = self.request.GET.get("to")
            else:
                context["to"] = current_time.strftime(self.date_format)

            context['player_search'] = self.request.GET.get("player_search",'')
            context['staff_search'] = self.request.GET.get("staff_search",'')

            context['timezone'] = Admin.objects.first().timezone 

            return context
        except Exception as e:
            print("Exception",e)
            return context


class QueryStatus(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin")

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        id = request.POST.get("provider")
        query_obj = CsrQueries.objects.filter(id=id)


        if query_obj.exists() and query_obj.first().is_active:
            query_obj.update(is_active = False)
            message = "Query Marked As Resolved"
        elif query_obj.exists():
            query_obj.update(is_active= True)
            message = "Query Status Changed To Unresolved"

        return self.render_json_response({"status": "Success", "message": message})


class DeleteOffmarketGame(CheckRolesMixin, views.JSONResponseMixin,
                                 views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        game_id = self.request.POST.get("game_id")
        try:
            game = OffMarketGames.objects.get(id=game_id)
            game.delete()
            return self.render_json_response(
                {
                    "status": "Success",
                    "message": _("Game Deleted Successfully")
                },
                status=200
            )

        except Exception as e:
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Logo not found")
                },
                status=404
            )

class OffmarketPendingWithdrawalsview(CheckRolesMixin, views.JSONResponseMixin, ListView):
    template_name = "offmarkets/offmarket_withdrawal_requests.html"
    allowed_roles = ("admin","agent")
    context_object_name = "PendingWithdrawals"
    model = OffmarketWithdrawalRequests
    queryset = OffmarketWithdrawalRequests.objects.order_by("-modified").all()
    date_format = "%d/%m/%Y"


    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def get_queryset(self):
        queryset = super().get_queryset()
        user = Users.objects.get(username=self.request.user)

        if(self.request.GET.getlist("players", None)):

            queryset = queryset.filter(user__id__in=self.request.GET.getlist("players"))


        if self.request.GET.get("status") and self.request.GET.get("status") != "all":
            queryset = queryset.filter(status=self.request.GET.get("status"))

        if self.request.GET.get("type"):  
            queryset = queryset.filter(type = self.request.GET.get("type"))

        if user.role=='agent':
            queryset = queryset.filter(user__agent = user)


        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__gte=start_date)
        else:
            # by default show results from first day of month
            current_date = timezone.now()
            first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
            queryset = queryset.filter(created__gte=first_day_of_month)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__date__lte=end_date)
        return queryset

    def get_context_data(self, **kwargs):
        # by default show results from first day of month
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

        context = super().get_context_data(**kwargs)
        context["type"] = self.request.GET.get("type", None)
        context["status"] = self.request.GET.get("status", None)
        context["username"] = self.request.GET.get("username", "")
        context["from"] = self.request.GET.get("from", first_day_of_month)
        context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))

        return context


class ApproveOffmarketWithdrawalRequest(CheckRolesMixin, views.JSONResponseMixin,
                                 views.AjaxResponseMixin, View):
    allowed_roles = ("admin","agent")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):        
        trans_id = request.POST.get('trans_id')
        new_status = request.POST.get('status')
        try:
            if new_status == 'cancelled':
                withdrawal_request = OffmarketWithdrawalRequests.objects.filter(id=trans_id).first()
                withdrawal_request.status = 'rejected'
                withdrawal_request.save()
                Thread(target=rejection_mail,
                            args=(withdrawal_request.id,)).start()
            elif new_status == 'approved':
                request = OffmarketWithdrawalRequests.objects.filter(id=trans_id).first() 
                game = OffMarketGames.objects.filter(code=request.code).first()
                user = request.user
                user.balance = user.balance + Decimal(request.amount)
                user.save()
                obj ,created =  OffMarketTransactions.objects.update_or_create(
                                user = request.user,
                                amount = request.amount,
                                game_name = request.code,
                                status = 'Completed',
                                transaction_type = "WITHDRAW",
                                journal_entry = 'credit',
                                description = f'withdraw of {request.amount} from game {request.code}',
                                game_name_full = game.title
                                )      
                request.status = 'approved'
                request.transaction = obj
                request.save()
            return JsonResponse({'status': 'success', 'message': 'Status updated successfully.'})
        except OffmarketWithdrawalRequests.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Withdrawal request not found.'})


class EditOffmarketTransactionGame(APIView):
    http_method_names = ["post"]
    def post(self, request):
        try:
            if not request.user.is_authenticated:
                return Response({"message" : "please log in"})
            
            transaction_id = request.POST.get("transaction_id",None)
            user_status = request.POST.get("user_status",None)
            tnx_type = request.POST.get("type",None)
            
            success, error = RefujiClient.edit_transaction(
                transaction_id=transaction_id,
                user_status=user_status,
                txn_type=tnx_type,
                user = request.user
            )
            
            return Response({ "message": "Request Submitted Successfully" if success else error}, 
                            status.HTTP_200_OK if success else 400)

        except:
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeleteOffmarketTransaction(APIView):
    http_method_names = ["post"]

    def post(self, request):
        transaction_id = request.POST.get("transaction_id",None)
        success, error = RefujiClient.delete_transaction(transaction_id=transaction_id)
        return Response(
            {"message" : "Transaction deleted." if success else error},
            200 if success else 400
        )

class AlchemyPayReportView(CheckRolesMixin, ListView):
    template_name = "report/alchemypay_report.html"
    model = AlchemypayOrder
    queryset = AlchemypayOrder.objects.order_by("-created").all()
    context_object_name = "alchemypay"
    allowed_roles = ("admin", "superadmin", "dealer", "agent")
    date_format = "%d/%m/%Y"
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()

        user = Users.objects.get(username=self.request.user)
        if self.request.GET.get("status-id") and self.request.GET.get("status-id") != "all":
            status = self.request.GET.get("status-id")
            queryset = queryset.filter(status=status)

        if self.request.GET.get("transaction-type") and self.request.GET.get("transaction-type") != "all":
            transaction_type=self.request.GET.get("transaction-type")
            queryset = queryset.filter(payment_method=transaction_type)

        if(self.request.GET.getlist("players", None)):
            queryset = queryset.filter(user__id__in=self.request.GET.getlist("players"))

        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__gte=start_date)
        else:
            # by default show results from first day of month
            current_date = timezone.now()
            first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
            queryset = queryset.filter(created__gte=first_day_of_month)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__date__lte=end_date)
        return queryset

    def get_context_data(self, **kwargs):
        # by default show results from first day of month
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)
        context = super().get_context_data(**kwargs)
        context["status"] = self.request.GET.get("status", None)
        context["transaction_type"] = self.request.GET.get("transaction_type", None)
        context["from"] = self.request.GET.get("from", first_day_of_month)
        context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))
        return context


from apps.users.consumers import active_rooms
from django.http import JsonResponse
def is_room_active(request):
    room_name = request.GET.get('room_name')
    is_active = room_name in active_rooms
    return JsonResponse({'is_active': is_active})


def Check_staff(request):
    room_deatils  = list(Queue.objects.filter(pick_by = request.user).values('pick_by_id','user__username'))
    room_deatils = []
    return JsonResponse(room_deatils,safe=False)




class SpintheWheelView(CheckRolesMixin, ListView):
    template_name = "admin/cms/spin_the_wheel.html"
    model = SpintheWheelDetails
    queryset = SpintheWheelDetails.objects.all()
    context_object_name = "spins"
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(
            admin=self.request.user
        )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        return context




class AddSpinDetailsView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        admin = Admin.objects.get(id=self.request.user.id)
        value = self.request.POST.get("value", 0)
        if value:
            try:
                spin_count = SpintheWheelDetails.objects.all().count()
                if spin_count >= 5:
                    return self.render_json_response({"status": "error", "message": _("Only 5 Wheels Details allowed, Please delete any existing detail.")})
                value = int(value)
                tempvar = string.ascii_lowercase+string.digits
                code = ''.join(random.sample(tempvar, 20))
                SpintheWheelDetails.objects.create(
                    admin=admin,
                    value=int(value),
                    code=code
                )

                return self.render_json_response({"status": "success", "message": _("Details Added Successfully")})
            except:
                return self.render_json_response({"status": "error", "message": _("Something Went Wrong")})
        else:
            return self.render_json_response({"status": "error", "message": _("Something Went Wrong")})

class MinimumSpinAmountView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin")
    date_format = "%d/%m/%Y"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        admin = Admin.objects.get(id=self.request.user.id)
        value = self.request.POST.get("value", 0)
        if value:
            try:  
                value = int(value)
                admin.minimum_spin_deposit = Decimal(round(value))
                admin.save()

                return self.render_json_response({"status": "success", "message": _("Updated Added Successfully")})
            except:
                return self.render_json_response({"status": "error", "message": _("Something Went Wrong")})
        else:
            return self.render_json_response({"status": "error", "message": _("Something Went Wrong")})


class RemoveSpinDetailsView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ["post"]
    allowed_roles = ("admin")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        try:
            spin_id = self.request.POST.get("spin_id")
            spin_obj = SpintheWheelDetails.objects.filter(id=int(spin_id))

            spin_obj.delete()

            response = { "message":"Details deleted succesfully", "status": "success" }

        except Exception as err:
            print(err)
            response = { "error": "failed" }

        return self.render_json_response(response)

class CashDeatilsView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ["post", "get", "put", "delete"]
    allowed_roles = ("staff")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        try:
            cash_name = self.request.POST.get("cash_name")
            player_id = self.request.POST.get("player_id")

            if cash_name == "" or cash_name.isspace():
                return self.render_json_response({ "message":"Invalid CashApp ID, It can not be blank or space.", "status": "error" }, status=400)

            if CashAppDeatils.objects.filter(name = cash_name).exists():
                cashapp_obj = CashAppDeatils.objects.filter(name = cash_name, user_id=player_id).first()
                if cashapp_obj and not cashapp_obj.is_active:
                    CashAppDeatils.objects.filter(name = cash_name, user_id=player_id).update(is_active=True)
                    response = { "message":"CashApp id activated succesfully", "status": "success" }
                else:
                    response = { "message":"CashApp Already exists", "status": "error" }
                    return self.render_json_response(response, status=400)
            else:
                spin_obj = CashAppDeatils.objects.create(
                    name = cash_name,
                    user_id = player_id
                )
                response = { "message":"CashApp id added succesfully", "status": "success" }
            return self.render_json_response(response)
        except Exception as err:
            print(err)
            response = {"message": "something went wrong", "status":"error", "error": "failed" }
            return self.render_json_response(response, status=500)


    def get_ajax(self, request, *args, **kwargs):
        try:
            player_id = self.request.GET.get("player_id")
            response = list(CashAppDeatils.objects.filter(user_id = int(player_id), is_active=True).values())
        except Exception as err:
            print(err)
            response = { "error": "failed" }

        return self.render_json_response(response)

    def put_ajax(self, request, *args, **kwargs):
        try:
            data = json.loads(self.request.body.decode('utf-8'))
            cash_name = data.get("cash_name")
            cashapp_id = data.get("cashapp_id")
            if CashAppDeatils.objects.filter(name = cash_name).exclude(id = int(cashapp_id)).first():
                response = { "message":"CashApp Already exists", "status": "error" }
                return self.render_json_response(response, status=400)
            else:
                spin_obj = CashAppDeatils.objects.filter(id= int(cashapp_id)).update(
                    name = cash_name,
                )
                response = { "message":"CashApp id updated succesfully", "status": "success" }
            return self.render_json_response(response)
        except Exception as err:
            print(err)
            response = {"message": "something went wrong", "status":"error", "error": "failed" }
            return self.render_json_response(response, status=500)

    def delete_ajax(self, request, *args, **kwargs):
        try:
            data = json.loads(self.request.body.decode('utf-8'))
            cashapp_id = data.get("cashapp_id")
            spin_obj = CashAppDeatils.objects.filter(id= cashapp_id).delete()
            response = { "message":"CashApp id deleted succesfully", "status": "success" }
        except Exception as err:
            print(err)
            response = { "error": "failed" }
        return self.render_json_response(response)

class CashAppReportView(CheckRolesMixin, ListView):
    template_name = "report/cash_app.html"
    model = Transactions
    queryset = Transactions.objects.order_by("-created").all()

    context_object_name = "transactionreport"
    paginate_by = 20
    allowed_roles = ("admin", "superadmin", "dealer", "agent")
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(payment_method = 'cashapp')
        try:
            if self.request.GET.getlist("players", None):
                queryset = self.queryset.filter(user__in = self.request.GET.getlist("players"))

            if self.request.GET.get("from"):
                # start_date = datetime.datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%d-%m-%Y")
                start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
                queryset = queryset.filter(created__gte=start_date)
            else:
                # by default show results from first day of month
                current_date = timezone.now()
                first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
                queryset = queryset.filter(created__gte=first_day_of_month)

            if self.request.GET.get("to"):
                end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
                queryset = queryset.filter(created__date__lte=end_date)

            if self.request.GET.getlist("dealers"):
                dealers = self.request.GET.getlist("dealers")
                queryset = queryset.filter(user__dealer__in=dealers)

            if self.request.GET.getlist("agents"):
                agents = self.request.GET.getlist("agents")
                queryset = queryset.filter(user__agent__in=agents)

            if self.request.GET.get("payment_status"):
                queryset = queryset.filter(status=self.request.GET.get("payment_status"))



        except Exception as e:
            return queryset
        return queryset

    def get_context_data(self, **kwargs):
        # by default show results from first day of month
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

        context = super().get_context_data(**kwargs)
        context["from"] = self.request.GET.get("from", first_day_of_month)
        context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))
        context["payment_status"] = self.request.GET.get("payment_status", None)

        return context

from django.core.management import call_command
import threading

class PaymentUpdateCashapp(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ["get"]
    allowed_roles = ("admin", "superadmin", "dealer", "agent","staff")
    def get_ajax(self, request, *args, **kwargs):
        try:
            threading.Thread(target=self.run_update_cashapp_payment).start()
            response =  { "message":"Payments are updated within 10 to 20 minutes.", "status": "success" }
        except Exception as err:
            print(err)
            response = { "error": "failed" }
        return self.render_json_response(response)

    def run_update_cashapp_payment(self):
        try:
            # Run your management command here
            call_command('update_cashapp_payment')
        except Exception as err:
            print(err)



class CashappQrView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/cashapp_qr/cashapp.html"
    allowed_roles = ("admin",)

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        form = CashappDetailForm()
        user=CashappQr.objects.filter(user=self.request.user, is_active=True).last()
        return render(request, template_name=self.template_name, context={"form": form,"image":user.image})

    def post(self, request, *args, **kwargs):
        try:
            cashapp_obj = CashappQr.objects.filter(user=self.request.user).last()
            if cashapp_obj:
                cashapp_obj.is_active = False
                cashapp_obj.save()
            new_cashapp_obj = CashappQr.objects.create(
                is_active=request.POST.get("is_active", True),
                image=request.FILES.get('image'),
                user=self.request.user
            )
            messages.success(request, "Cashapp details stored successfully")
        except Exception as e:
            print(e)
            messages.error(request, "Something Went Wrong")
        return redirect('admin-panel:cashapp-detail')



class ChatInboxView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/chat_support/chat_room.html"
    allowed_roles = ("staff","admin",'agent',"dealer")
    date_format = "%Y-%m-%d %H:%M:%S.%f%z"
    context_object_name = "messages"
    queryset = ChatMessage.objects.all().order_by('-sent_time')

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def get(self, request, *args, **kwargs):
        request_type = request.GET.get('request_type', '')

        if request_type == "recent_messages":
            chatroom_id = request.GET.get('chatroom_id')
            page = request.GET.get('page', 1)
            per_page = request.GET.get('per_page', 10)
            message_from = request.GET.get('message_from', None)
            is_history = request.GET.get('is_history', False)

            chat_room = ChatRoom.objects.filter(id=chatroom_id).first()
            if message_from:
                messages = ChatMessage.objects.filter(room_id=chatroom_id, id__lt=message_from).order_by("-created")
            else:
                messages = ChatMessage.objects.filter(room_id=chatroom_id).order_by("-created")

            if is_history in [True, 'true'] and chat_room.pick_by != self.request.user:
                messages = messages.filter(created__lte=timezone.now()-timedelta(hours=72))

            paginator = Paginator(messages, per_page)
            try:
                temp = []
                messages = paginator.page(page)
                for message in messages.object_list:
                    if message.is_tip and message.tip_user.id == self.request.user.id:
                        temp.append({
                            'id': message.id,
                            'message': message.file.name if message.is_file else message.message_text,
                            "sender_id": message.sender.id,
                            'sender': message.sender.role,
                            'sent_time': message.sent_time,
                            'is_file': str(message.is_file).capitalize(),
                            'file': message.file.name,
                            "staff": self.request.user.username,
                            "type": message.type,
                            "is_tip" : message.is_tip,
                            "tip_user": message.tip_user.id,
                            "is_comment":message.is_comment
                       })
                    elif not message.is_tip:
                        temp.append({
                            'id': message.id,
                            'message': message.file.name if message.is_file else message.message_text,
                            "sender_id": message.sender.id,
                            'sender': message.sender.role,
                            'sent_time': message.sent_time,
                            'is_file': str(message.is_file).capitalize(),
                            'file': message.file.name,
                            "staff": self.request.user.username,
                            "type": message.type,
                            "is_comment":message.is_comment
                       })

            except PageNotAnInteger:
                messages = paginator.page(1)
            except EmptyPage:
                messages = paginator.page(paginator.num_pages)

            response_data = {'messages': temp}
            return self.render_json_response(response_data)

        chats = ChatRoom.objects.filter(    
            Q(pick_by=self.request.user)|Q(pick_by=None),
            Q(player__agent=self.request.user.agent) | Q(player__agent=self.request.user) | Q(player__admin=self.request.user) | Q(player__dealer=self.request.user)
        ).annotate(
            last_message_timestamp=Max('messages__created'),
            unread_messages_count=Count('messages', filter=Q(messages__is_read=False, messages__sender__role="player",messages__type =ChatMessage.MessageType.message))
        ).filter(
            ~Q(last_message_timestamp=None),
            last_message_timestamp__gte=timezone.now()-timedelta(hours=72)
        ).order_by("-last_message_timestamp")

        if request_type == "chat_count":
            chat_count = chats.filter(unread_messages_count__gt=0).count() if self.request.user.is_staff_active else 0
            response_data = {'chat_count': chat_count, "is_staff_active": self.request.user.is_staff_active}
            return self.render_json_response(response_data)

        chat_count = chats.count()

        game_data = list(OffMarketGames.objects.filter(
            game_status=True,
        ).values_list('id', "code", "title"))
        print(game_data)

        return render(request,template_name=self.template_name, context={
            "players_count_in_queue": chat_count,
            "players_in_queue": chats,
            "game_data": game_data
        })


    def post_ajax(self, request, *args, **kwargs):
        try:
            operation = self.request.POST.get('type',None)
            if operation == 'mark_message_as_read':
                chatroom_id = self.request.POST.get('chatroom_id')
                ChatMessage.objects.filter(room__id=chatroom_id, sender__role="player").update(is_read=True)
                return self.render_json_response({"status": "Success", 'chats': "Message marked as read"}, 200)
            elif operation == 'toggle_status':
                staff = Users.objects.filter(id=self.request.user.id).first()
                if staff:
                    staff.is_staff_active = not staff.is_staff_active
                    staff.save()
                    if not staff.is_staff_active:
                        chat_rooms_id = list(ChatRoom.objects.filter(pick_by=self.request.user).values_list("id", flat=True))
                        ChatRoom.objects.filter(pick_by=self.request.user).update(pick_by=None)
                        chats = ChatRoom.objects.filter(id__in=chat_rooms_id).annotate(
                            unread_messages_count=Count('messages', filter=Q(messages__is_read=False, messages__sender__role="player"))
                        ).values(
                            "pick_by",
                            "unread_messages_count",
                            chat_id=F("id"),
                            user_id=F("player_id"),
                            username=F("player__username"),
                        )

                        send_message_to_chatlist(self.request.user, message= {
                            "type": "add_new_chats",
                            "chats": list(chats),
                            "chat_rooms_id": chat_rooms_id,
                        })

                        send_live_status_to_player(staff,list(chats))

                    return self.render_json_response({"status": "Success", "is_staff_active":staff.is_staff_active}, 200)

            elif operation == 'add_player':
                username = self.request.POST.get('username')
                game_code = self.request.POST.get('code') 
                player_id = self.request.POST.get('user_id')


                game = OffMarketGames.objects.filter(code=game_code).first()
                player = Users.objects.filter(id=player_id).first()
                if len(username)<5:
                    return self.render_json_response({"status": "Failed", "message": _("Username Must be greater than 5 characters")})
                elif not game:
                    return self.render_json_response({"status": "Failed", "message": _("Game Does Not Exist")})
                elif UserGames.objects.filter(game=game, user=player).exists():
                    return self.render_json_response({"status": "Failed", "message": _("User Already have Account For this Game")})
                elif UserGames.objects.filter(game=game, username=username).exists():
                    return self.render_json_response({"status": "Failed", "message": _("Username Already Exists")})
                user = UserGames()
                user.game = game
                user.username =  username
                user.user = player
                user.save()
                return self.render_json_response({"status": "success", "message": _("Account Created Successfully"),"game_name":game.title},status=status.HTTP_200_OK)

            elif operation == 'update_chat_status':
                chat_id = self.request.POST.get("chat_id", None)
                assign = self.request.POST.get("assign", False)
                chatroom = ChatRoom.objects.filter(id=chat_id).last()
                if chatroom.pick_by is not None and chatroom.pick_by != self.request.user:
                    return self.render_json_response({"status": "already_picked", "message":"Player already picked", "chat_id":chatroom.id}, 405)

                chatroom.pick_by = self.request.user if assign in [True, "true"] else None
                chatroom.save()
                chat_message = ChatMessage.objects.filter(~Q(sender__role="player"), room=chatroom, type="join").first()
                sent_join = True if not chat_message or chat_message.sender != self.request.user else False
                return self.render_json_response({"status": "Success", "sent_join":sent_join}, 200)
            elif operation == 'remove_chat_from_list':
                chat_id = self.request.POST.get("chat_id", None)
                pick_id = self.request.POST.get("pick_id", None)
                send_message_to_chatlist(self.request.user, message= {
                    "type": "remove_chat_from_list",
                    "chat_id": chat_id,
                    "pick_by": pick_id,
                })
                return self.render_json_response({"status": "Success"}, 200)

            else:
                chat_id = self.request.POST.get("chat_id", None)
                chatroom = ChatRoom.objects.filter(id=chat_id).last()
                if chatroom:
                    if chatroom.pick_by is None:
                        chatroom.pick_by = self.request.user
                        chatroom.save()
                    return self.render_json_response({"status": "Success", "room_name": chatroom.name}, 200)

            return self.render_json_response({"status": "Error"}, 405)
        except Exception as e:
            print(e)
            tb = traceback.format_exc()
            print(tb)
            return self.render_json_response({"status": "Error"}, 500)



class ChatInboxHistoryListView(CheckRolesMixin, ListView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/chat_support/chat_history.html"
    model = ChatRoom
    queryset = ChatRoom.objects.filter(~Q(player=None))
    context_object_name = "chathistories"
    allowed_roles = ("staff","agent","dealer","admin")
    date_format = "%d/%m/%Y"

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def time_zone_converter(self, date_time_obj, Inverse_Time_flag):
        try:
            current_timezone = self.request.session.get("time_zone", "en")
        except Exception:
            current_timezone = "en"
        if current_timezone == "en":
            return date_time_obj
        elif current_timezone == "ru":
            current_timezone = "Europe/Moscow"
        elif current_timezone == "tr":
            current_timezone = "Turkey"
        else:
            current_timezone = "Europe/Berlin"
        timee = date_time_obj.replace(tzinfo=None)
        if Inverse_Time_flag:
            new_tz = pytz.timezone(current_timezone)
            old_tz = pytz.timezone("EST")
        else:
            old_tz = pytz.timezone(current_timezone)
            new_tz = pytz.timezone("EST")
        new_timezone_timestamp = old_tz.localize(timee).astimezone(new_tz)
        return new_timezone_timestamp


    def get_queryset(self):
        queryset = super().get_queryset()

        queryset = queryset.filter(messages__created__lte=timezone.now()-timedelta(hours=72)).distinct()

        if self.request.user.role == "staff":
            self.queryset = queryset.filter(messages__sender = self.request.user)
        else:
            self.queryset = queryset.filter(
                Q(player__admin=self.request.user)|Q(player__dealer=self.request.user)|Q(player__agent=self.request.user)
            )

        if self.request.GET.getlist("players", None):
            self.queryset = queryset.filter(player_id__in=self.request.GET.getlist("players"))
        if self.request.GET.getlist("staff", None):
            self.queryset = queryset.filter(pick_by__in=self.request.GET.getlist("staff"))

        self.queryset = self.queryset.distinct().annotate(
            last_message_timestamp=Max('messages__created'),
        )

        return self.queryset


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            selected_players = self.request.GET.getlist("players", None)
            if selected_players:
                context["selected_players"] = Users.objects.filter(role="player", id__in = selected_players)
            else:
                context["selected_players"] = None

            selected_staff = self.request.GET.getlist("staff", None)
            if selected_staff:
                context["selected_staff"] = Users.objects.filter(role="staff", id__in = selected_staff)
            else:
                context["selected_staff"] =  None

            context['players'] = selected_players
            context['timezone'] = Admin.objects.first().timezone

            return context
        except Exception as e:
            print("Exception", e)
            return context


class ChatInboxHistoryDetailView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/chat_support/chat_history_tab.html"
    allowed_roles = ("staff","dealer","agent","admin")
    date_format = "%Y-%m-%d %H:%M:%S.%f%z"
    context_object_name = "messages"


    def get(self, request, *args, **kwargs):
        chat_history_id = request.GET.get('ch_id')
        if chat_history_id:
            chat_history = ChatRoom.objects.filter(id=chat_history_id).first()
            if chat_history:
                chat_history_id = chat_history.id
                last_three_days = timezone.now() - timedelta(hours=72)

                return render(request,template_name=self.template_name, context={
                    "chatroom":chat_history,
                    "chathistory_id":chat_history.id,
                    "created_date" : chat_history.created,
                    "can_start_chat" : True if chat_history.pick_by in [self.request.user, None] or chat_history.messages.first().created < last_three_days else False,
                })
        return render(request,template_name=self.template_name, context={})

class CashAppListView(CheckRolesMixin, ListView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/cash_app.html"
    model = CashAppDeatils
    queryset = CashAppDeatils.objects.all().order_by("-created")
    context_object_name = "cashapps"
    allowed_roles = ("staff","agent")
    date_format = "%d/%m/%Y"
    paginate_by=20

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)


    def get_queryset(self):
        queryset = super().get_queryset()
        player_search = self.request.GET.get('player_search', "")
        status = self.request.GET.get('status', "all")

        agent = self.request.user if self.request.user.role == "agent" else self.request.user.agent
        queryset = queryset.filter(user__agent = agent, is_active=True)

        if player_search.strip() != '':
            queryset = queryset.filter(user__username__istartswith=player_search.strip())

        if status != "all":
            queryset = queryset.filter(status=status)

        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__gte=start_date)
        else:
            # by default show results from first day of month
            current_date = timezone.now()
            first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
            queryset = queryset.filter(created__gte=first_day_of_month)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
            queryset = queryset.filter(created__date__lte=end_date)

        return queryset


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            current_date = timezone.now()
            first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

            context["player_search"] = self.request.GET.get('player_search', "")
            context["status"] = self.request.GET.get('status', None)
            context['timezone'] = Admin.objects.first().timezone
            context["from"] = self.request.GET.get("from", first_day_of_month)
            context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))
            return context
        except Exception as e:
            print("Exception", e)
            return context

    def post(self, *args, **kwargs):
        try:
            cashapp_id = self.request.POST.get("cashapp_id")
            status = self.request.POST.get("status")
            cashapp = CashAppDeatils.objects.get(id=cashapp_id)
            if cashapp.status == "pending":
                cashapp.status = status
                cashapp.approved_by = self.request.user
                cashapp.save()
            else:
                return self.render_json_response({
                    "success":False, 
                    "approved_by":cashapp.approved_by.username, 
                    "cashapp_status":cashapp.status, 
                    "message":f"Cashapp already {cashapp.status} by {cashapp.approved_by.username}"
                }, 200)
            return self.render_json_response({"success":True, "message":f"Cashapp {status.capitalize()}"}, 200)
        except CashAppDeatils.DoesNotExist:
            return self.render_json_response({"success":False, "message":"Invalid request"}, 400)
        except Exception as e:
            print(e)
            return self.render_json_response({"success":False, "message":"Internal error"}, 500)




class BonusTransactionReportView(CheckRolesMixin, ListView):
    template_name = "report/bonus_transactions_report.html"
    model = Transactions
    queryset = Transactions.objects.filter(journal_entry=BONUS).order_by("-created")
    context_object_name = "transactionreport"
    allowed_roles = ("admin", "superadmin", "dealer", "agent")
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        transaction_queryset = super().get_queryset()
        transaction_queryset = transaction_queryset.annotate(
            bonus_name=Replace('bonus_type', Value('_'), Value(' ')),
        )
        offmarket_queryset = OffMarketTransactions.objects.filter(bonus__gt= 0).annotate(
            bonus_amount=F("bonus"),
            bonus_name=Value("Offmarket bonus", output_field=CharField())
        )

        if self.request.user.role == "dealer":
            transaction_queryset = transaction_queryset.filter(Q(user=self.request.user) | Q(merchant=self.request.user) | Q(merchant__dealer=self.request.user))
            offmarket_queryset = offmarket_queryset.filter(user__dealer=self.request.user)
        elif self.request.user.role == "agent":
            transaction_queryset = transaction_queryset.filter(Q(user=self.request.user) | Q(merchant=self.request.user))
            offmarket_queryset = offmarket_queryset.filter(user__agent=self.request.user)

        if self.request.GET.get("username"):
            transaction_queryset = transaction_queryset.annotate(
                user_username_lower=Lower("user__username"),
                merchant_username_lower=Lower("merchant__username"),
            ).filter(
                Q(user_username_lower=self.request.GET.get("username").split(",").lower())
                | Q(merchant_username_lower=self.request.GET.get("username").split(",").lower())
            )
            offmarket_queryset = offmarket_queryset.filter(
                user__username__iexact=self.request.GET.get("username").split(",").lower()
            )

        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
            transaction_queryset = transaction_queryset.filter(created__gte=start_date)
            offmarket_queryset = offmarket_queryset.filter(created__gte=start_date)
        else:
            # by default show results from first day of month
            current_date = timezone.now()
            first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
            transaction_queryset = transaction_queryset.filter(created__gte=first_day_of_month)
            offmarket_queryset = offmarket_queryset.filter(created__gte=first_day_of_month)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
            transaction_queryset = transaction_queryset.filter(created__date__lte=end_date)
            offmarket_queryset = offmarket_queryset.filter(created__date__lte=end_date)


        if(self.request.GET.getlist("players", None)):
            transaction_queryset = transaction_queryset.filter(user__id__in=self.request.GET.getlist("players"))
            offmarket_queryset = offmarket_queryset.filter(user__id__in=self.request.GET.getlist("players"))

        if self.request.GET.getlist("dealers"):
            dealers = self.request.GET.getlist("dealers")
            transaction_queryset = transaction_queryset.filter(user__dealer__in=dealers)
            offmarket_queryset = offmarket_queryset.filter(user__dealer__in=dealers)

        if self.request.GET.getlist("agents"):
            agents = self.request.GET.getlist("agents")
            transaction_queryset = transaction_queryset.filter(user__agent__in=agents)
            offmarket_queryset = offmarket_queryset.filter(user__agent__in=agents)


        if self.request.GET.get("bonus-type") and self.request.GET.get("bonus-type") != "all":
            transaction_queryset = transaction_queryset.filter(bonus_type=self.request.GET.get("bonus-type"))
            if self.request.GET.get("bonus-type") != "offmarket_bonus":
                offmarket_queryset = []


        queryset = list(chain(transaction_queryset, offmarket_queryset))
        queryset = sorted(queryset, key=attrgetter('created'), reverse=True)
        return queryset

    def get_context_data(self, **kwargs):
        # by default show results from first day of month
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

        context = super().get_context_data(**kwargs)
        context["bonus_type"] = self.request.GET.get("bonus-type", None)
        context["username"] = self.request.GET.get("username", "")
        context["from"] = self.request.GET.get("from", first_day_of_month)
        context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))
        context["duration"] = self.request.GET.get("duration", None)

        if self.request.GET.getlist("dealers"):
            dealers = self.request.GET.getlist("dealers")
            context["selected_dealers"] = Dealer.objects.filter(id__in=dealers)

        if self.request.GET.getlist("agents"):
            agents = self.request.GET.getlist("agents")
            context["selected_agents"] = Agent.objects.filter(id__in=agents)

        return context

class OffMarketGameView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ["get"]
    date_format = "%d/%m/%Y"
    allowed_roles = ("superadmin", "admin", "dealer", "agent","staff")
    def get_ajax(self, request, *args, **kwargs):
        user_id = kwargs.get('user_id')
        response = list(UserGames.objects.filter(user_id  = user_id ).values('game_id',"game__title"))
        return self.render_json_response(response)


class OffMarketCreditAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    http_method_names = ("post",)
    allowed_roles = ("admin", "dealer", "superadmin", "agent","staff")
    input_fields = ("value", "player_id", "type","game_id")

    # def handle_no_permission(self):
    #     return HttpResponseRedirect(settings.LOGIN_URL)

    def post_ajax(self, request, *args, **kwargs):
        try:
            user = Users.objects.filter(id=request.POST["player_id"]).first()
            amount = float(request.POST["value"])
            deposit_id = str(request.POST.get("payment_id", None))
            if user.balance < Decimal(amount):
                return self.render_json_response({"status":"Failed","message": "Insufficient Funds"}, 400)
            elif deposit_id.strip() in [None, 'None', ""] or len(deposit_id)<5:
                return self.render_json_response({"status":"Failed","message": "Invalid Payment ID"}, 400)
            elif OffMarketTransactions.objects.filter(txn_id=deposit_id).exists():
                return self.render_json_response({"status":"Failed","message": "Payment ID Already Exists"}, 400)

            amount = Decimal(amount)

            success, error = RefujiClient.deposit(
                user=user,
                game_code=game_code,
                amount=amount,
                promo_code=None,
                force_update=True
            )

            message = "Request Submitted Successfully" if success else error

            return self.render_json_response({
                    "status" : "Success" if success else "Failed",
                    "message": message
                },
                ( 200 if success else 400)
            )
        except Exception as e:
            print(e)
            return self.render_json_response({"status":"Failed","message": "Something Went Wrong"}, 500)

        return self.render_json_response(response_data)

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class CasinoCategoryView(CheckRolesMixin, APIView):
    allowed_roles = ["admin",]

    def get(self, *args, **kwargs):
        search = self.request.GET.get("search")
        casino_categories = CasinoManagement.objects.select_related("game").filter(admin=self.request.user)
        if search:
            casino_categories = casino_categories.filter(game__game_category__icontains=search)

        casino_categories = casino_categories.distinct("game__game_category").annotate(
            value=F('game__game_category'),
            text=F('game__game_category')
        ).values('value', 'text')

        return Response(casino_categories)


    def post(self, *args, **kwargs):
        try:
            game_id = self.request.POST.get("game_id")
            category_name = self.request.POST.get("category_name")
            is_edit = self.request.POST.get("is_edit", False)
            is_bulk_change = self.request.POST.get("is_bulk_change", False)

            if is_edit in ['true', True]:
                CasinoGameList.objects.filter(game_category=game_id).update(game_category=category_name)
            elif is_bulk_change in ['true', True]:
                game_ids = self.request.POST.getlist("game_id[]")
                CasinoGameList.objects.filter(id__in=game_ids).update(game_category=category_name)
            else:
                casino_game = CasinoManagement.objects.get(id=game_id).game
                casino_game.game_category = category_name
                casino_game.save()

            if not CasinoHeaderCategory.objects.filter(name=category_name).exists():
                casino_header = CasinoHeaderCategory.objects.order_by("position").last()
                position = casino_header.position + 1 if casino_header else 1
                CasinoHeaderCategory.objects.create(name=category_name, position=position)

            return Response({"success":True, "message":f"Category updated successfully"}, 200)
        except CasinoManagement.DoesNotExist:
            return Response({"success":False, "message":"Invalid request"}, 400)
        except Exception as e:
            print(e)
            return Response({"success":False, "message":"Internal error"}, 500)


class TournamentListView(CheckRolesMixin, ListView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ["admin", ]
    model = Tournament
    queryset = Tournament.objects.all().order_by("-id")
    template_name = "admin/tournament/tournament_list.html"
    context_object_name = "tournaments"
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.GET.get("status")
        tournament_start_date = self.request.GET.get("tournament_start_date")
        tournament_end_date = self.request.GET.get("tournament_end_date")
        selected_tournaments = self.request.GET.getlist("selected_tournaments")

        current_date = timezone.now()
        if selected_tournaments:
            queryset = queryset.filter(id__in=selected_tournaments)

        if status=="active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)

        if tournament_start_date:
            queryset = queryset.filter(start_date__date__gte=tournament_start_date)
        if tournament_end_date:
            queryset = queryset.filter(end_date__date__lte=tournament_end_date)

        # queryset = queryset.annotate(
        #     is_tournament_end=Case(
        #         When(end_date__lt=current_date, then=True),
        #         default=False,
        #         output_field=BooleanField()
        #     )
        # )

        return queryset


    def get_context_data(self, **kwargs):  
        context = super().get_context_data(**kwargs)
        context["admin"] = self.request.user.id if self.request.user.role=="admin" else self.request.user.admin.id
        context["selected_status"] = self.request.GET.get("status")
        context["selected_start_date"] = self.request.GET.get("tournament_start_date")
        context["selected_end_date"] = self.request.GET.get("tournament_end_date")
        context["users_timezone"] = self.request.session.get("client_timezone")

        selected_tournaments = self.request.GET.getlist("selected_tournaments")
        if selected_tournaments:
            context["selected_tournaments"] = Tournament.objects.filter(id__in=selected_tournaments)

        return context


    def post_ajax(self, request, *args, **kwargs):
        search = request.POST.get("search")
        if search:
            tournaments = list(Tournament.objects.filter(name__istartswith=search).annotate(
                value=F('id'),
                text=F('name'),
            ).values("value", "text"))

        return self.render_json_response(tournaments)


class TournamentDetailView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ["admin", ]
    template_name = "admin/tournament/tournament_detail.html"

    def get(self, request):
        try:
            current_date = timezone.now()
            tournament_id = self.request.GET.get("id")
            if not tournament_id:
                messages.error(request, "Invalid Tournament ID")
                return redirect('admin-panel:tournaments')

            tournament = Tournament.objects.filter(id=tournament_id).first()
            if not tournament:
                messages.error(request, "Invalid Tournament ID")
                return redirect('admin-panel:tournaments')

            prize_type = tournament.tournamentprize_set.first().get_type_display()
            is_registration_closed = True if current_date > tournament.registration_end_date else False

            won_users = tournament.usertournament_set.filter(Q(win_prize__isnull=False)&~Q(win_prize="")).order_by("-win_points", "last_win_at")

            return render(
                request,
                template_name=self.template_name,
                context={
                    "tournament": tournament,
                    "prize_type": prize_type,
                    "won_users": won_users,
                    "is_registration_closed": is_registration_closed,
                    "admin": request.user.id,
                    "is_tournament_end": True if current_date > tournament.end_date else False,
                    "users_timezone": self.request.session.get("client_timezone"),
                    "are_no_tournament_winner": not any(list(tournament.usertournament_set.filter(win_points__gt=0).values_list("id"))),
                }
            )
        except Exception as e:
            print(e)
            return render(request, template_name=self.template_name,
                          context={"error": str(e)},
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateTournamentView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/tournament/create_tournament.html"
    allowed_roles = ("admin",)

    def get(self, request, *args, **kwargs):
        admin = self.request.user if self.request.user.role=="admin" else self.request.user.admin
        casino_games = CasinoManagement.objects.select_related("game").filter(admin=admin, enabled=True)
        return render(request, template_name=self.template_name, context={"casino_games":casino_games, "current_date": timezone.now().strftime('%Y-%m-%dT%H:%M')})

    def create_tournament_prize(self, tournament):
        number_of_winners = int(self.request.POST.get("number_of_winners"))
        prize_type = self.request.POST.get("prize_type")

        for i in range(1, number_of_winners+1):
            winner_prize = self.request.POST.get(f"winner{i}")
            tournament_prize = TournamentPrize.objects.create(
                tournament = tournament,
                rank = i,
                type = prize_type,
            )
            if prize_type == "cash":
                tournament_prize.amount = winner_prize
            else:
                tournament_prize.non_cash_prize = winner_prize
            tournament_prize.save()


    def post(self, request, *args, **kwargs):
        try:
            if not self.request.POST.get("tournament_name").strip():
                return self.render_json_response({"status": "error", "message": "Tournament name should not be empty"}, 400)

            image = self.request.FILES.get("tournament_image")
            number_of_winners = int(self.request.POST.get("number_of_winners"))
            is_tournament_enabled = True if self.request.POST.get("is_tournament_enabled") == "on" else False
            is_player_limit_enabled = True if self.request.POST.get("is_player_limit_enabled") == "on" else False
            is_rebuy_enabled = True if self.request.POST.get("is_rebuy_enabled") == "on" else False
            name = self.request.POST.get("tournament_name")
            description = self.request.POST.get("tournament_description")
            start_date = self.request.POST.get("tournament_start_date")
            end_date = self.request.POST.get("tournament_end_date")
            registration_end_date = self.request.POST.get("registration_end_date")
            entry_fees = self.request.POST.get("tournament_fees")
            jackpot_amount = self.request.POST.get("tournament_jackpot_amount")
            initial_credit = self.request.POST.get("tournament_initial_credit")
            min_player_limit = self.request.POST.get("min_player_limit")
            max_player_limit = self.request.POST.get("max_player_limit")
            rebuy_fees = self.request.POST.get("tournament_rebuy_fees")
            rebuy_limit = self.request.POST.get("tournament_rebuy_limit")
            game_ids = json.loads(self.request.POST.get("selectedGames"))

            none_validation = [is_tournament_enabled, is_player_limit_enabled, is_rebuy_enabled, name, description, start_date, end_date, registration_end_date, entry_fees, jackpot_amount, initial_credit, min_player_limit]
            positive_number_validation = [entry_fees, jackpot_amount, initial_credit, min_player_limit]
            positive_number_validation += list(range(1, number_of_winners+1))

            if (None in none_validation or '' in none_validation) or (is_rebuy_enabled and None in [rebuy_fees, rebuy_limit]) or is_player_limit_enabled and max_player_limit in [None, ""]:
                return self.render_json_response({"status": "error", "message": "All fields are required"}, 400)
            elif any(Decimal(num) <= 0 for num in positive_number_validation) or (is_rebuy_enabled and any(Decimal(num) <= 0 for num in [rebuy_fees, rebuy_limit] if num is not None)) or is_player_limit_enabled and max_player_limit and int(max_player_limit)<=0:
                return self.render_json_response({"status": "error", "message": "All numeric fields should be positive integer"}, 400)
            elif len(game_ids)==0:
                return self.render_json_response({"status": "error", "message": "Atleast one game should be selected"}, 400)

            tournament = Tournament.objects.create(
                name = name,
                description = description,
                start_date = start_date,
                end_date = end_date,
                registration_end_date = registration_end_date,
                entry_fees = entry_fees,
                jackpot_amount = jackpot_amount,
                initial_credit = initial_credit,
                is_player_limit_enabled = is_player_limit_enabled,
                min_player_limit = min_player_limit,
                max_player_limit = max_player_limit,
                is_rebuy_enabled = is_rebuy_enabled,
                rebuy_fees = rebuy_fees,
                rebuy_limit = rebuy_limit,
                image = image,
                is_active = is_tournament_enabled,
            )

            casino_games = CasinoManagement.objects.filter(id__in=game_ids)
            tournament.games.add(*casino_games)

            self.create_tournament_prize(tournament)
            return self.render_json_response({"success":True, "message": "Tournament Created Successfully"}, 200)
        except Exception as e:
            tb = traceback.format_exc()
            print(tb)
            print(e)
            return self.render_json_response({"success":False, "message": "Internal error"}, 500)


class EditTournamentView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/tournament/edit_tournament.html"
    allowed_roles = ("admin", "superadmin")
    date_format = "%d/%m/%Y %H:%M"
    context_object_name = "crm_template"


    def get(self, request, *args, **kwargs):
        tournament_id = self.request.GET.get("id")
        tournament = Tournament.objects.filter(id=tournament_id).first() if tournament_id.isdigit() else None
        if not tournament:
            messages.error(request, "Invalid Tournament ID")
            return redirect('admin-panel:tournaments')
        elif tournament.end_date <= timezone.now():
            messages.error(request, "Tournament already end, You can not edit it now.")
            return redirect('admin-panel:tournaments')

        tournament_prizes = tournament.tournamentprize_set.all()
        number_of_winners = tournament_prizes.count()
        admin = self.request.user if self.request.user.role=="admin" else self.request.user.admin
        casino_games = CasinoManagement.objects.select_related("game").filter(admin=admin, enabled=True)
        selected_games = list(tournament.games.values_list("id", flat=True))
        distributed_amount = tournament_prizes.filter(type="cash").aggregate(total_amount=Coalesce(Sum('amount'), Value(0))).get("total_amount")
        prize_type = tournament_prizes.order_by("-created").first().type
        # is_tournament_started = tournament.start_date < timezone.now() and tournament.usertournament_set.count() >= tournament.min_player_limit
        is_tournament_started = tournament.start_date < timezone.now() and tournament.tournamenttransaction_set.filter(type=TournamentTransaction.TransactionType.bet).exists()
        return render(request, template_name=self.template_name, context={
            "tournament":tournament,
            "number_of_winners": number_of_winners,
            "casino_games": casino_games,
            "selected_games": selected_games,
            "distributed_amount": distributed_amount,
            "prize_type": prize_type,
            "is_tournament_started":is_tournament_started,
            "current_date": timezone.now().strftime('%Y-%m-%dT%H:%M'),
        })


    def update_tournament_prize(self, tournament):
        number_of_winners = int(self.request.POST.get("number_of_winners"))
        prize_type = self.request.POST.get("prize_type")

        tournament_prizes = tournament.tournamentprize_set.filter(rank__lte=number_of_winners).order_by("rank")
        for tournament_prize in tournament_prizes:
            winner_prize = self.request.POST.get(f"winner{tournament_prize.rank}")
            if prize_type == "cash":
                tournament_prize.amount = winner_prize
            else:
                tournament_prize.non_cash_prize = winner_prize

            tournament_prize.type = prize_type
            tournament_prize.save()

        last_rank = tournament_prizes.last().rank if tournament_prizes.last() else 0
        if number_of_winners > last_rank:
            for rank in range(last_rank+1, number_of_winners+1):
                winner_prize = self.request.POST.get(f"winner{rank}")
                tournament_prize = TournamentPrize.objects.create(
                    tournament = tournament,
                    rank = rank,
                    type = prize_type,
                )
                if prize_type == "cash":
                    tournament_prize.amount = winner_prize
                else:
                    tournament_prize.non_cash_prize = winner_prize
                tournament_prize.save()


        tournament.tournamentprize_set.filter(rank__gt=number_of_winners).delete()


    def post(self, request, *args, **kwargs):
        try:
            tournament_id = self.request.POST.get("id")
            tournament = Tournament.objects.filter(id=tournament_id).first()
            if not tournament:
                return self.render_json_response({"status": "error", "message": "Invalid tournament ID"}, 400)

            image = self.request.FILES.get("tournament_image")
            number_of_winners = int(self.request.POST.get("number_of_winners"))
            is_tournament_enabled = True if self.request.POST.get("is_tournament_enabled") == "on" else False
            is_player_limit_enabled = True if self.request.POST.get("is_player_limit_enabled") == "on" else False
            is_rebuy_enabled = True if self.request.POST.get("is_rebuy_enabled") == "on" else False
            name = self.request.POST.get("tournament_name")
            description = self.request.POST.get("tournament_description")
            start_date = self.request.POST.get("tournament_start_date")
            end_date = self.request.POST.get("tournament_end_date")
            registration_end_date = self.request.POST.get("registration_end_date")
            entry_fees = self.request.POST.get("tournament_fees")
            jackpot_amount = self.request.POST.get("tournament_jackpot_amount")
            initial_credit = self.request.POST.get("tournament_initial_credit")
            min_player_limit = self.request.POST.get("min_player_limit")
            max_player_limit = self.request.POST.get("max_player_limit")
            rebuy_fees = self.request.POST.get("tournament_rebuy_fees")
            rebuy_limit = self.request.POST.get("tournament_rebuy_limit")
            game_ids = json.loads(self.request.POST.get("selectedGames"))

            none_validation = [is_tournament_enabled, is_player_limit_enabled, is_rebuy_enabled, name, description, start_date, end_date, registration_end_date, entry_fees, jackpot_amount, initial_credit, min_player_limit]
            positive_number_validation = [entry_fees, jackpot_amount, initial_credit, min_player_limit]
            positive_number_validation += list(range(1, number_of_winners+1))


            if (None in none_validation or '' in none_validation) or (is_rebuy_enabled and None in [rebuy_fees, rebuy_limit]) or is_player_limit_enabled and max_player_limit in [None, ""]:
                return self.render_json_response({"status": "error", "message": "All fields are required"}, 400)
            elif any(Decimal(num) <= 0 for num in positive_number_validation) or (is_rebuy_enabled and any(Decimal(num) <= 0 for num in [rebuy_fees, rebuy_limit] if num is not None)) or is_player_limit_enabled and max_player_limit and int(max_player_limit)<=0:
                return self.render_json_response({"status": "error", "message": "All numeric fields should be positive integer"}, 400)
            elif len(game_ids)==0:
                return self.render_json_response({"status": "error", "message": "Atleast one game should be selected"}, 400)

            tournament.name = name
            tournament.description = description
            tournament.start_date = start_date
            tournament.end_date = end_date
            tournament.registration_end_date = registration_end_date
            tournament.entry_fees = entry_fees
            tournament.jackpot_amount = jackpot_amount
            tournament.initial_credit = initial_credit
            tournament.is_player_limit_enabled = is_player_limit_enabled
            tournament.min_player_limit = min_player_limit
            tournament.is_rebuy_enabled = is_rebuy_enabled
            tournament.is_active = is_tournament_enabled

            if is_rebuy_enabled:
                tournament.rebuy_fees = rebuy_fees
                tournament.rebuy_limit = rebuy_limit
            if is_player_limit_enabled:
                tournament.max_player_limit = max_player_limit
            if image:
                tournament.image = image

            casino_games = CasinoManagement.objects.filter(id__in=game_ids)
            tournament.games.clear()
            tournament.games.add(*casino_games)
            tournament.save()

            self.update_tournament_prize(tournament)

            return self.render_json_response({"success":True, "message": "Tournament Updated Successfully"}, 200)
        except Exception as e:
            print(traceback.format_exc())
            if(type(e) != ValueError):
                messages.error(request, "Something Went Wrong")
            return self.render_json_response({"success":False, "message": "Internal error"}, 500)


class EmailTemplateView(CheckRolesMixin, ListView):
    model = EmailTemplateDetails
    date_format = "%d/%m/%Y"
    template_name = "admin/crm_cms/email_template.html"
    allowed_roles = ("admin", "superadmin")
    context_object_name = "templates"
    queryset = EmailTemplateDetails.objects.all()

    def get_queryset(self):
        return self.queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


class AddEmailTemplateView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin")

    def post_ajax(self, request, *args, **kwargs):
        category = self.request.POST.get("category", None)
        template_id = self.request.POST.get("template_id", None)

        if not category or not template_id:
            return self.render_json_response({"status": "error", "message": _("Incomplete Entries")})

        if EmailTemplateDetails.objects.filter(category=category).exists():
            return self.render_json_response({"status": "error", "message": _("Category Already Exists")})

        elif EmailTemplateDetails.objects.filter(template_id=template_id).exists():
            return self.render_json_response({"status": "error", "message": _("Template ID Already Exists")})

        EmailTemplateDetails.objects.create(
            category=category,
            admin=self.request.user,
            template_id=template_id
        )

        return self.render_json_response({"status": "success", "message": _("Email Template Added Successfully")})


class ManageEmailTemplateAjax(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin", "superadmin")

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post_ajax(self, request, *args, **kwargs):
        try:
            template_id = request.POST.get("template_id")
            template_obj = EmailTemplateDetails.objects.get(id=template_id)
            response_msg = ""
            if request.POST.get("is_delete") == "true":
                template_obj.delete()
                response_msg = "Deleted Sucessfully"
                return self.render_json_response({"status": "Success", "message": response_msg}, 200)
        except:
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})


class EditEmailTemplateAjax(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/crm_cms/edit_email_template.html"
    allowed_roles = ("admin", "superadmin")
    date_format = "%d/%m/%Y %H:%M"
    context_object_name = "template"

    def get_context_data(self, **kwargs):
        template_id = self.request.GET.get("template_id", None)
        context = super().get_context_data(**kwargs)
        crm_obj = EmailTemplateDetails.objects.get(id=template_id)
        context["category"] = crm_obj.category
        context["template_id"] = crm_obj.template_id
        context["t_id"] = crm_obj.id
        return context

    def post_ajax(self, request, *args, **kwargs):
        try:
            template_id = request.POST.get("template_id", None)
            t_id = request.POST.get("t_id", None)

            if not template_id:
                return self.render_json_response({"status": "error", "message": _("Incomplete Entries")})

            elif EmailTemplateDetails.objects.filter(template_id=template_id).exists():
                return self.render_json_response({"status": "error", "message": _("Template ID Already Exists")})

            crm_obj = EmailTemplateDetails.objects.filter(id=t_id).first()
            crm_obj.template_id = template_id
            crm_obj.save()

            return self.render_json_response({"status": "Success", "message": "Success"})

        except Exception as e:
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})


class CmsImageUploadView(APIView):

    def post(self, *args, **kwargs):
        try:
            if self.request.FILES.get('file'):
                image_file = self.request.FILES['file']

                filename, extension = os.path.splitext(image_file.name)
                filename = f"{filename}_{uuid.uuid4()}{extension}"

                with open(os.path.join(settings.MEDIA_ROOT, filename), 'wb+') as destination:
                    for chunk in image_file.chunks():
                        destination.write(chunk)

                response_data = {
                    'status': 'Success',
                    'url': f"{settings.BE_DOMAIN}/media/{filename}"
                }
                return Response(response_data)
            else:
                response_data = {'status': 'error', 'message': 'No file provided'}
                return Response(response_data, status=400)
        except Exception as e:
            print(e)
            return Response({'status': 'error', 'message': 'Internal error'}, status=500)


class CmsBonusDetailListView(CheckRolesMixin, TemplateView, View):
    allowed_roles = ["admin", ]
    template_name = "admin/bonus_content/bonus_contents.html"

    def get(self, request):
        try:
            if request.user.role == 'admin':
                bonus_contents = CmsBonusDetail.objects.filter(admin_id=request.user.id).order_by("-created")
                show_create = not sorted(CmsBonusDetail.BonusType.labels.keys()) == sorted(list(bonus_contents.values_list("bonus_type", flat=True)))
                return render(request, template_name=self.template_name, context={
                    "bonus_contents": bonus_contents,
                    "admin": request.user.id,
                    "show_create_button": show_create
                })
            else:
                return render(request, template_name=self.template_name, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return render(request, template_name=self.template_name, context={"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateCmsBonusDetailView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ["admin",]
    template_name = "admin/bonus_content/add_bonus_content.html"

    def get(self, request):
        try:
            if request.user.role == 'admin':
                available_bonuses = CmsBonusDetail.BonusType.labels
                available_bonuses_keys = set(CmsBonusDetail.BonusType.labels.keys())
                stored_details = set(CmsBonusDetail.objects.values_list("bonus_type", flat=True))

                if sorted(list(available_bonuses_keys)) == sorted(list(stored_details)):
                    messages.error(request, _("All types of bonus details are already added!"))
                    return redirect('admin-panel:bonus-details')

                allowed_to_create = list(available_bonuses_keys - stored_details)
                promo_codes = None
                if len(allowed_to_create)>0:
                    promo_codes = PromoCodes.objects.filter(
                        bonus__bonus_type=allowed_to_create[0],
                        is_expired = False,
                        end_date__gte = timezone.now().date()
                    ).values_list("promo_code", flat=True)

                bonuses = {bonus:available_bonuses.get(bonus) for bonus in allowed_to_create}

                return render(request, template_name=self.template_name, context={
                    "admin": self.request.user.id,
                    "available_bonuses": bonuses,
                    "promo_codes": promo_codes,
                })
            else:
                return render(request, template_name=self.template_name, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            print(traceback.format_exc())
            return render(request, template_name=self.template_name, context={"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def post_ajax(self, request, *args, **kwargs):
        try:
            bonus_type = request.POST.get("bonus_type", None)
            promo_code = request.POST.get("promo_code", None)
            content = request.POST.get("bonus_content", None)
            meta_description = request.POST.get("meta_description", None)
            json_metadata = request.POST.get("json_metadata", None)

            if CmsBonusDetail.objects.filter(bonus_type=bonus_type).exists():
                return self.render_json_response({"status": "error", "message": _(f"Details for {bonus_type} already exists.")})

            bonus_detail = CmsBonusDetail()
            bonus_detail.bonus_type = bonus_type
            bonus_detail.promo_code = promo_code
            bonus_detail.content = content
            bonus_detail.meta_description = meta_description
            bonus_detail.json_metadata = json_metadata
            bonus_detail.admin = self.request.user
            bonus_detail.save()

            return self.render_json_response({"status": "success", "message": "Bonus details saved successfully."})
        except Exception as e:
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})


class EditCmsBonusDetailView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/bonus_content/edit_bonus_content.html"
    allowed_roles = ["admin",]
    date_format = "%d/%m/%Y %H:%M"


    def get(self, request, *args, **kwargs):
        bonus_id = self.request.GET.get("bonus_id", "")
        try:
            if request.user.role == 'admin':
                bonus_detail = CmsBonusDetail.objects.filter(id=bonus_id).first()
                if not bonus_detail:
                    messages.error(request, _("Please provide valid id!"))
                    return redirect('admin-panel:bonus-details')

                promo_codes = None
                if bonus_detail.bonus_type in [CmsBonusDetail.BonusType.welcome_bonus, CmsBonusDetail.BonusType.deposit_bonus]:
                    promo_codes = list(PromoCodes.objects.filter(
                        bonus__bonus_type = bonus_detail.bonus_type,
                        is_expired = False,
                        end_date__gte = timezone.now().date()
                    ).values_list("promo_code", flat=True))
                    if bonus_detail.promo_code not in promo_codes:
                        promo_codes.insert(0, bonus_detail.promo_code)

                return render(request, template_name=self.template_name, context={
                    "admin": self.request.user.id,
                    "bonus_detail": bonus_detail,
                    "promo_codes": promo_codes
                })
            else:
                return render(request, template_name=self.template_name, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            print(traceback.format_exc())
            messages.error(request, _("Something went wrong!"))
            return redirect('admin-panel:bonus-details')



    def post_ajax(self, request, *args, **kwargs):
        try:
            bonus_id = request.POST.get("bonus_id", None)
            promo_code = request.POST.get("promo_code", None)
            content = request.POST.get("bonus_content", None)
            meta_description = request.POST.get("meta_description", None)
            json_metadata = request.POST.get("json_metadata", None)

            if not CmsBonusDetail.objects.filter(id=bonus_id).exists():
                return self.render_json_response({"status": "error", "message": _(f"Invalid ID.")})

            bonus_detail = CmsBonusDetail.objects.get(id=bonus_id)
            bonus_detail.promo_code = promo_code
            bonus_detail.content = content
            bonus_detail.meta_description = meta_description
            bonus_detail.json_metadata = json_metadata
            bonus_detail.admin = self.request.user
            bonus_detail.save()

            return self.render_json_response({"status": "Success", "message": "Bonus details successfully updated."})
        except Exception as e:
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})


class DeleteCmsBonusDetailView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ["admin",]

    def post_ajax(self, request, *args, **kwargs):
        bonus_id = self.request.POST.get("bonus_id")
        try:
            bonus_detail = CmsBonusDetail.objects.get(id=bonus_id)
            bonus_detail.delete()
            return self.render_json_response(
                {
                    "status": "Success",
                    "message": _("Bonus Deleted Successfully")
                },
                status=200
            )

        except Exception as e:
            print(traceback.format_exc())
            return self.render_json_response(
                {
                    "status": "Error",
                    "message": _("Not found")
                },
                status=404
            )


class PromoCodeAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ["admin", "superadmin"]

    def get_ajax(self, request):
        try:
            bonus_type = self.request.GET.get("bonus_type", None)
            promo_codes = list(PromoCodes.objects.filter(
                bonus__bonus_type = bonus_type,
                is_expired = False,
                end_date__gte = timezone.now().date()
            ).values_list("promo_code", flat=True))
            return self.render_json_response(promo_codes)
        except Exception as e:
            return self.render_json_response({"status": "error", "message": "Something Went Wrong"})


class RolesView(CheckRolesMixin, ListView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    model = Role
    paginate_by = 20
    template_name = "admin/roles/roles.html"
    allowed_roles = ("admin",)
    context_object_name = "roles"
    date_format = "%d/%m/%Y"
    queryset = Role.objects.all()

    ORDER_MAPPING = {
        "1": "created",
        "2": "-created",
    }

    def time_zone_converter(self,date_time_obj,Inverse_Time_flag):
        try:
            current_timezone = self.request.session['time_zone']
        except:
            current_timezone='en'
        if(current_timezone=="en"):
            return date_time_obj
        elif(current_timezone=='ru'):
            current_timezone='Europe/Moscow'
        elif(current_timezone=='tr'):
            current_timezone='Turkey'    
        else:
            current_timezone='Europe/Berlin'
        timee=date_time_obj.replace(tzinfo=None)
        if(Inverse_Time_flag):
            new_tz=pytz.timezone(current_timezone)
            old_tz=pytz.timezone("EST")
        else:
            old_tz=pytz.timezone(current_timezone)
            new_tz=pytz.timezone("EST")
        new_timezone_timestamp = old_tz.localize(timee).astimezone(new_tz)
        return new_timezone_timestamp

    def get_queryset(self):
        role_id = self.request.GET.getlist("role_name")
        order = self.request.GET.get("order", "3")
        role = self.kwargs.get('role')

        self.queryset = self.queryset.filter(admin=self.request.user)
        if role:
            self.queryset = self.queryset.filter(name=role)

        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format)
            self.queryset = self.queryset.filter(created__gte=start_date)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format)
            self.queryset = self.queryset.filter(created__date__lte=end_date)

        if role_id:
            self.queryset = self.queryset.filter(id__in=role_id)
        if order and order in self.ORDER_MAPPING.keys():
            self.queryset = self.queryset.order_by(self.ORDER_MAPPING[order])
        else:
            self.queryset = self.queryset.order_by("-created")

        return self.queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_date = timezone.now()
        first_day_of_month_UTC = current_date
        first_day_of_month=self.time_zone_converter(first_day_of_month_UTC,True)
        first_day_of_month=first_day_of_month.replace(day=1, hour=0, minute=0)
        current_time=timezone.now()
        current_time=self.time_zone_converter(current_time,True)
        role_id = self.request.GET.getlist("role_name")
        permissions = Permission.objects.filter(~Q(code="can_view_dashboard"))
        grouped_permissions = defaultdict(list)
        for permission in permissions:
            grouped_permissions[permission.group].append(permission)

        context["to"] = self.request.GET.get("to", current_time.strftime(self.date_format))
        context["from"] = self.request.GET.get("from", first_day_of_month.strftime(self.date_format))
        context["order"] = self.request.GET.get("order", "2")
        context["grouped_permissions"] = dict(grouped_permissions)
        context["selected_roles"] = Role.objects.filter(id__in=role_id)

        if self.request.user.role in ("admin", "superadmin", "dealer"):
            context["username"] = self.request.GET.get("user_name", "")

        return context

    def post_ajax(self, request, *args, **kwargs):
        search = request.POST.get("search")
        result = []
        if search:
            roles = Role.objects.filter(name__istartswith=search.lower()).order_by('name')
            # roles = roles.values(value=F("id"), text=F("name"))[:10]
            for role in roles[:10]:
                result.append({"value": role.id, "text": role.name.title().replace("_", " ")})

        return self.render_json_response(result)


class CreateRoleView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    template_name = "admin/roles/create_role.html"
    allowed_roles = ("admin",)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        permissions = Permission.objects.filter(~Q(code="can_view_dashboard"))
        grouped_permissions = defaultdict(list)
        for permission in permissions:
            grouped_permissions[permission.group].append(permission)

        context["grouped_permissions"] = dict(grouped_permissions)
        return context

    def post(self, request, *args, **kwargs):
        try:
            available_permissions = list(Permission.objects.values_list("code", flat=True))
            role = self.request.POST.get("role", "")
            allowed_permissions = self.request.POST.get("allowed_permissions", "").split(",")

            pattern = re.compile("[A-Za-z0-9]*$")

            if not role:
                return self.render_json_response({"status": "error", "message": _("All fields are required")}, 400)
            elif Role.objects.filter(name=role.lower().replace(" ", "_")).exists():
                return self.render_json_response({"status": "Failed", "message": _("Role already exists")}, 400)
            elif len(role) < 4:
                return self.render_json_response({"status": "Failed","message": _("The role has to be at least 4 characters")}, 400)
            elif not all([permission in available_permissions or permission=="" for permission in allowed_permissions]):
                return self.render_json_response({"status": "Failed","message": _("Invalid Permission.")}, 400)

            role = Role.objects.create(
                admin=self.request.user,
                name=role.lower().replace(" ", "_"),
            )

            allowed_permissions.append("can_view_dashboard")
            permissions_to_add = [Permission.objects.get(code=permission) for permission in allowed_permissions if permission!=""]                

            role.permissions.add(*permissions_to_add)
            return self.render_json_response({"success":True, "message": "Role Added Successfully"}, 200)
        except Exception as e:
            tb = traceback.format_exc()
            print(tb)
            print(e)
            return self.render_json_response({"success":False, "message": "Internal error"}, 500)


class UpdateRoleView(CheckRolesMixin, TemplateView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)

    def post(self, request, *args, **kwargs):
        try:
            id = self.request.POST.get("id", "")
            role_name = self.request.POST.get("role", "")

            if not role_name:
                return self.render_json_response({"status": "error", "message": _("All fields are required")}, 400)
            elif not Role.objects.filter(id=id).exists():
                return self.render_json_response({"status": "error", "message": _("Invalid ID")}, 400)
            elif Role.objects.filter(name=role_name.lower().replace(" ", "_")).exists():
                return self.render_json_response({"status": "Failed", "message": _("Role already exists")}, 400)
            elif len(role_name) < 4:
                return self.render_json_response({"status": "Failed","message": _("The role has to be at least 4 characters")}, 400)

            role = Role.objects.get(id=id)
            role.name = role_name.lower().replace(" ", "_")
            role.save()
            return self.render_json_response({"success":True, "message": "Role Updated Successfully"}, 200)
        except Exception as e:
            tb = traceback.format_exc()
            print(tb)
            print(e)
            return self.render_json_response({"success":False, "message": "Internal error"}, 500)

    def put_ajax(self, request, *args, **kwargs):
        try:
            data = parse_qs(self.request.body.decode('utf-8'))
            permission_to_update = data.get('permission[]')
            role_id = data.get('role_id')[0]
            status = data.get("status")[0]
            available_permissions = list(Permission.objects.values_list("code", flat=True))

            if not Role.objects.filter(id=role_id).exists():
                return self.render_json_response({
                    "status": "error",
                    "message": _("Role Not Found"),
                },status=400)
            elif not all(permission in available_permissions for permission in permission_to_update):
                return self.render_json_response({
                    "status": "error",
                    "message": _("Invalid Permission"),
                },status=400)

            role = Role.objects.get(id=role_id)
            for permission in permission_to_update:
                permission = Permission.objects.get(code=permission)
                if status in [True, "True", "true"]:
                    role.permissions.add(permission)
                else:
                    role.permissions.remove(permission)

            return self.render_json_response({
                "status": "success",
                "title": _("Permission updated"),
            },status=200)
        except Exception as e:
            print(traceback.format_exc())
            print(e)
            return self.render_json_response({
                "status": "error",
                "message": _("Internal Error")
            },status=500)


class UserListByRoleView(CheckRolesMixin, ListView, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    model = Users
    paginate_by = 20
    template_name = "admin/roles/users_list.html"
    allowed_roles = ("admin",)
    context_object_name = "users"
    date_format = "%d/%m/%Y"
    queryset = Users.objects.filter(~Q(role__in=["superadmin", "admin", "masteragent", "agent", "player"]))

    ORDER_MAPPING = {
        "1": "-last_login",
        "2": "created",
        "3": "-created",
    }

    def time_zone_converter(self,date_time_obj,Inverse_Time_flag):
        try:
            current_timezone = self.request.session['time_zone']
        except:
            current_timezone='en'
        if(current_timezone=="en"):
            return date_time_obj
        elif(current_timezone=='ru'):
            current_timezone='Europe/Moscow'
        elif(current_timezone=='tr'):
            current_timezone='Turkey'    
        else:
            current_timezone='Europe/Berlin'
        timee=date_time_obj.replace(tzinfo=None)
        if(Inverse_Time_flag):
            new_tz=pytz.timezone(current_timezone)
            old_tz=pytz.timezone("EST")
        else:
            old_tz=pytz.timezone(current_timezone)
            new_tz=pytz.timezone("EST")
        new_timezone_timestamp = old_tz.localize(timee).astimezone(new_tz)
        return new_timezone_timestamp

    def get_queryset(self):
        role = self.kwargs.get('role')
        user_id = self.request.GET.getlist("user_id")
        order = self.request.GET.get("order", "3")

        self.queryset = self.queryset.filter(role=role, admin=self.request.user)
        if self.request.GET.get("from"):
            start_date = datetime.strptime(self.request.GET.get("from"), self.date_format)
            self.queryset = self.queryset.filter(created__gte=start_date)
        else:
            first_day_of_month = self.time_zone_converter(timezone.now(), True)
            first_day_of_month = first_day_of_month.replace(day=1, hour=0, minute=0)
            self.queryset = self.queryset.filter(created__gte=first_day_of_month)

        if self.request.GET.get("to"):
            end_date = datetime.strptime(self.request.GET.get("to"), self.date_format)
            self.queryset = self.queryset.filter(created__date__lte=end_date)

        if user_id:
            self.queryset = self.queryset.filter(id__in=user_id)
        if order and order in self.ORDER_MAPPING.keys():
            self.queryset = self.queryset.order_by(self.ORDER_MAPPING[order])
        else:
            self.queryset = self.queryset.order_by("last_login")

        return self.queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_date = timezone.now()
        first_day_of_month_UTC = current_date
        first_day_of_month=self.time_zone_converter(first_day_of_month_UTC,True)
        first_day_of_month=first_day_of_month.replace(day=1, hour=0, minute=0)
        current_time=timezone.now()
        current_time=self.time_zone_converter(current_time,True)
        role_id = self.request.GET.getlist("role_name")

        context["to"] = self.request.GET.get("to", current_time.strftime(self.date_format))
        context["from"] = self.request.GET.get("from", first_day_of_month.strftime(self.date_format))
        context["order"] = self.request.GET.get("order", "3")
        context["user_role"] = self.kwargs.get('role').title().replace("_", " ")
        context["permissions"] = Permission.objects.all()
        context["selected_roles"] = Role.objects.filter(id__in=role_id)

        if self.request.user.role in ("admin", "superadmin", "dealer"):
            context["username"] = self.request.GET.get("user_name", "")

        return context

    def post_ajax(self, request, *args, **kwargs):
        role = self.kwargs.get('role', "").lower().replace(" ", "_")
        search = request.POST.get("search")
        roles=[]
        if search:
            roles = Users.objects.filter(role=role.lower(), username__istartswith=search.lower()).order_by('username')
            roles = roles.values(value=F("id"), text=F("username"))[:10]

        return self.render_json_response(list(roles))


class CreateUserByRole(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)

    def post_ajax(self, request, *args, **kwargs):
        try:
            role = self.kwargs.get("role", "").lower().replace(" ", "_")
            username = request.POST.get("username", "").lower()
            first_name = request.POST.get("first_name", "")
            last_name = request.POST.get("last_name", "")
            password = request.POST.get("password", "")
            confirm_password = request.POST.get("confirm_password", "")

            pattern = re.compile("[A-Za-z0-9]*$")
            none_validation = [username, role, first_name, last_name, password, confirm_password]
            print(role)

            if None in none_validation or '' in none_validation:
                return self.render_json_response({"status": "error", "message": _("All fields are required")}, 400)
            elif not pattern.fullmatch(username):
                return self.render_json_response({"status": "Failed", "message": _("Username must be Alphanumeric")}, 400)
            elif Users.objects.filter(username__iexact=username).exists():
                return self.render_json_response({"status": "Failed", "message": _("Username already exists")}, 400)
            elif len(username) < 4:
                return self.render_json_response({"status": "Failed","message": _("The username has to be at least 4 characters")}, 400)
            elif len(password.strip()) < 5:
                return self.render_json_response({"status": "Failed","message": _("Password should not contain empty space")}, 400)
            elif len(password) < 5:
                return self.render_json_response({"status": "Failed","message": _("The password has to be at least 5 characters")}, 400)
            elif password != confirm_password:
                return self.render_json_response({"status": "Failed","message": _("Passwords do not match.")}, 400)
            elif not role in list(Role.objects.values_list("name", flat=True)):
                return self.render_json_response({"status": "Failed","message": _("Invalid role.")}, 400)

            user = Users.objects.create(
                username = username,
                first_name = first_name,
                last_name = last_name,
                password = make_password(password),
                timezone = self.request.user.timezone,
                currency = self.request.user.currency,
                role = role,
                admin = self.request.user,
                is_staff = False,
                is_superuser = False,
                is_active = True,
            )

            return self.render_json_response({"status": "Success","message": _("User Created Successfully.")}, 200)
        except Exception as e:
            print(traceback.format_exc())
            print(e)
            return self.render_json_response({
                "status": "error",
                "message": _("Internal Error")
            },status=500)


class UpdateUserByRole(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin",)

    def post_ajax(self, request, *args, **kwargs):
        try:
            username = request.POST.get("username", "").lower()
            password = request.POST.get("password", "")
            confirm_password = request.POST.get("confirm_password", "")
            none_validation = [username, password, confirm_password]

            if None in none_validation or '' in none_validation:
                return self.render_json_response({"status": "error", "message": _("All fields are required")}, 400)
            elif not Users.objects.filter(username__iexact=username).exists():
                return self.render_json_response({"status": "error","message": _("User Not Found"),},status=400)
            elif len(password) < 5:
                return self.render_json_response({"status": "error","message": _("The password has to be at least 5 characters")}, 400)
            elif password != confirm_password:
                return self.render_json_response({"status": "error","message": _("Passwords do not match.")}, 400)

            user = Users.objects.get(username=username)
            user.password = make_password(password)
            user.save()
            return self.render_json_response({
                "status": "success",
                "message": _("Password Updated"),
            },status=200)
        except Exception as e:
            print(traceback.format_exc())
            print(e)
            return self.render_json_response({
                "status": "error",
                "message": _("Internal Error")
            },status=500)



class FortunepandasGamesManagementView(CheckRolesMixin, ListView):
    allowed_roles = ["admin",]
    template_name = "admin/fortunepandas-management.html"
    paginate_by = 20
    model = FortunePandasGameManagement
    queryset = FortunePandasGameManagement.objects.all().order_by("game__game_name")
    context_object_name = "fortunepandas_games"
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        queryset = super().get_queryset()
        game_ids = self.request.GET.get("game_id")
        category = self.request.GET.get("category", None)

        queryset = queryset.filter(admin=self.request.user)

        if game_ids and len(game_ids) > 0 :
            game_ids = [int(x) for x in game_ids.split(",") if x.isdigit()]
            print(game_ids)
            queryset = queryset.filter(id__in=game_ids)

        if category:
            category = category.split(",")
            queryset = queryset.filter(game__game_category__in=category)

        queryset = queryset.filter(admin = self.request.user)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        games = self.request.GET.get("game_id", None)
        if games:
            game_ids = [int(x) for x in games.split(",") if x.isdigit()]
            games = FortunePandasGameManagement.objects.filter(id__in=game_ids)
            context["selected_games"] = games
        context["selected_categories"] = self.request.GET.get("category", "").split(",")
        context["selected_device_type"] = self.request.GET.get("device_type")
        return context


class FortunepandasGameAjaxView(CheckRolesMixin, APIView):
    http_method_names = ("get",)
    allowed_roles = ("admin", "dealer", "superadmin", "tenant_manager")

    def get(self, request, *args, **kwargs):
        search = self.request.GET.get("search", "").strip()
        games = FortunePandasGameManagement.objects.filter(admin = self.request.user)
        if search:
            games = games.filter(game__game_name__icontains = search)

        results = []
        games = games.values(
            value=F("id"),
            text=F("game__game_name")
        )
        return Response(games)


class FortunepandasCategoryView(CheckRolesMixin, APIView):
    allowed_roles = ["admin",]

    def get(self, *args, **kwargs):
        search = self.request.GET.get("search")
        categories = FortunePandasGameManagement.objects.select_related("game").filter(admin=self.request.user)
        if search:
            categories = categories.filter(game__game_category__icontains=search)

        categories = categories.distinct("game__game_category").annotate(
            value=F('game__game_category'),
            text=F('game__game_category')
        ).values('value', 'text')

        return Response(categories)


class FortunepandasGameStatus(CheckRolesMixin, APIView):
    allowed_roles = ("admin")

    def get(self, request, *args, **kwargs):
        game_id = self.request.GET.get("game_id")
        casino_obj = FortunePandasGameManagement.objects.filter(admin=self.request.user, game__game_id=game_id).first()
        casino_obj.enabled = not casino_obj.enabled
        message = "Game enabled" if casino_obj.game_enabled else "Game disabled"
        casino_obj.save()

        return self.render_json_response({"status": "Success", "message": message})


class MnetReportView(CheckRolesMixin, ListView):
    template_name = "report/mnet_report.html"
    model = MnetTransaction
    queryset = MnetTransaction.objects.order_by("-created").all()
    context_object_name = "mnet_transactions"
    paginate_by = 20
    allowed_roles = ("admin", "superadmin", "dealer", "agent")
    date_format = "%d/%m/%Y"

    def get_queryset(self):
        queryset = super().get_queryset()
        try:
            if self.request.user.role == "admin":
                queryset = self.queryset.filter(user__admin = self.request.user)
            elif self.request.user.role == "dealer":
                queryset = self.queryset.filter(user__dealer = self.request.user)
            elif self.request.user.role == "agent":
                queryset = self.queryset.filter(user__agent = self.request.user)
            elif self.request.user.role != "superadmin":
                queryset = self.queryset.filter(user__admin = self.request.user.admin)

            if self.request.GET.getlist("players", None):
                queryset = self.queryset.filter(user__in = self.request.GET.getlist("players"))

            if self.request.GET.get("from"):
                start_date = datetime.strptime(self.request.GET.get("from"), self.date_format).strftime("%Y-%m-%d")
                queryset = queryset.filter(created__gte=start_date)
            else:
                # by default show results from first day of month
                current_date = timezone.now()
                first_day_of_month = current_date.replace(day=1, hour=0, minute=0)
                queryset = queryset.filter(created__gte=first_day_of_month)

            if self.request.GET.get("to"):
                end_date = datetime.strptime(self.request.GET.get("to"), self.date_format).strftime("%Y-%m-%d")
                queryset = queryset.filter(created__date__lte=end_date)

            if self.request.GET.getlist("dealers"):
                dealers = self.request.GET.getlist("dealers")
                queryset = queryset.filter(user__dealer__in=dealers)

            if self.request.GET.getlist("agents"):
                agents = self.request.GET.getlist("agents")
                queryset = queryset.filter(user__agent__in=agents)

            if self.request.GET.get("payment_status"):
                queryset = queryset.filter(status=self.request.GET.get("payment_status"))

            if self.request.GET.get("transaction_type"):
                queryset = queryset.filter(transaction_type=self.request.GET.get("transaction_type"))

            return queryset
        except Exception as e:
            return queryset

    def get_context_data(self, **kwargs):
        current_date = timezone.now()
        first_day_of_month = current_date.replace(day=1, hour=0, minute=0).strftime(self.date_format)

        context = super().get_context_data(**kwargs)
        context["payment_status"] = self.request.GET.get("payment_status")
        context["transaction_type"] = self.request.GET.get("transaction_type")
        context["from"] = self.request.GET.get("from", first_day_of_month)
        context["to"] = self.request.GET.get("to", timezone.now().strftime(self.date_format))
        return context


class MaintenanceModeAjaxView(CheckRolesMixin, views.JSONResponseMixin, views.AjaxResponseMixin, View):
    allowed_roles = ("admin")

    def post_ajax(self, request, *args, **kwargs):
        admin = self.request.user
        maintenance_message = self.request.POST.get("maintenance_message", None)
        enabled = self.request.POST.get("enabled", None) 
        if maintenance_message:
            admin.maintenance_mode_message = maintenance_message
        if enabled:
            enabled = True if enabled == 'true' else False
            admin.is_maintenance_mode_enabled = enabled

        admin.save()

        return self.render_json_response({"status": "success", "message": _("Maintenance Mode Details Updated Successfully")})
