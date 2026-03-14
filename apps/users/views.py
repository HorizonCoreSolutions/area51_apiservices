import re
import sys
import json
import redis
import random
import string
import requests
import traceback
from decimal import Decimal
from threading import Thread
from compat import render_to_string

from datetime import datetime,timedelta
from django.utils import timezone
from rest_framework.request import Request

from apps.bets.repository import get_react_bonus_amount
from apps.core.file_logger import SimpleLogger
from apps.users import promo_handler
from apps.users.services.spin_wheel import get_price, process_spin_transaction, get_spin_status
from apps.core.concurrency import limiter
from pyhanko_certvalidator import ValidationError

from apps.casino.clients import RefujiClient
from apps.acuitytec.acuitytec import AcuityTecAPI
from apps.acuitytec.tasks import register_or_update_user
from apps.admin_panel.tasks import newuser_email, queries_email
from apps.bets.utils import generate_reference
from apps.bets.models import CASHBACK, CHARGED
from django.db.models import F, Q
import pytz
from collections import defaultdict
from itertools import chain
from operator import attrgetter

import  base64
from django.utils.translation import activate, gettext_lazy as _
from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import exceptions as rest_exceptions
from django.http import JsonResponse

from rest_framework.views import APIView
import traceback
from twilio.base.exceptions import TwilioRestException


from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from twilio.rest import Client
from cryptography.fernet import Fernet
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image
import uuid
from django.core.files.base import ContentFile
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from apps.casino.custom_pagination import CustomPagination

from apps.casino.tasks import task_update_offmarket_transaction
from apps.core.permissions import IsAdmin, IsAgent, IsDealer, IsManager, IsPlayer, IsSuperAdmin
from apps.core.rest_any_permissions import AnyPermissions
from apps.core.utils.network import get_user_ip_from_request
from apps.core.views import APIViewContext
from django.db import transaction

from apps.users.tasks import redeam_user_event
from apps.users.utils import send_player_balance_update_notification, UTC_OFFSET_PATTERN, get_tz_offset
from apps.users.filters import PlayerFilters
from apps.users.models import (Admin, CashappQr, CmsBonusDetail, CmsFAQ, CmsPrivacyPolicy, CookiePolicy,
                               EmailTemplateDetails, FooterCategory, FooterPages, FortunePandasGameList,
                               FortunePandasGameManagement, Introduction, MAX_MULTI_FOUR_EVENTS_AMOUNT,
                               MAX_MULTI_THREE_EVENTS_AMOUNT, MAX_MULTI_TWO_EVENTS_AMOUNT, MAX_MULTIPLE_BET, MAX_ODD,
                               MAX_SINGLE_BET, MAX_SINGLE_BET_OTHER_SPORTS, MAX_SPEND_AMOUNT, MAX_WIN_AMOUNT, MIN_BET,
                               PlayerBettingLimit, SettingsLimits, SocialLink, SpintheWheelDetails,
                               TermsConditinos, Country, EVENT_REGISTRATION)
from apps.users.serializers import (
    # UserUpdateSerializer, 
    AdminBannerSerializer,
    CashAppDetailSerializer,
    CashappQrSerializer,
    ChangePasswordSerializer,
    CmsPromotionSerializer,
    CmsPromotionsSerializer,
    FortunePandasGameListSerializer,
    FortunePandasManagementGameListSerializer,
    GetOtpSerializer,
    LoginSerializer,
    OffmarketTransactionsSerializer,
    PlayerSerializer,
    SignUpSerializer,
    SpintheWheelDetailsSerializer,
    TransactionsSerializer, CountrySerializer
)

from apps.users.serializers import (# UserUpdateSerializer, AffiliateSerializer,
    ChangePasswordSerializer, GetOtpSerializer,
    LoginSerializer, MessageSerializer, OffmarketTransactionsSerializer, PlayerSerializer,
    SignUpSerializer)

from django.contrib.auth.hashers import make_password
from apps.users.models import Player, Agent, Dealer, AdminBanner, CmsAboutDetails, CmsPromotionDetails
from apps.users.utils import check_otp, create_otp, create_otp_password,encrypt, is_only_one
from apps.admin_panel.templatetags.navigate import is_active
from apps.users.fortunepandas import FortunePandaAPI
from .models import ( VERIFICATION_APPROVED, VERIFICATION_PENDING, VERIFICATION_PROCESSING, AdminAdsBanner,CASHBACK_PERCENTAGE, AffiliateRequests, BonusPercentage, ChatHistory, ChatMessage, ChatRoom, CmsPromotions, CsrQueries, OffMarketGames, OffMarketTransactions, OffmarketWithdrawalRequests,
                    Player, Queue, Staff, SuperAdminSetting, UserGames,
                      Users, CmsContactDetails,ResponsibleGambling,
                      CmsPages,CashAppDeatils
                      )
from apps.bets.models import  Transactions,SPIN_WHEEL,CREDIT
from django.db.models import BooleanField, Case, When, Value
from datetime import datetime as dt 

TWILIO_SID = settings.TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN = settings.TWILIO_AUTH_TOKEN
TWILIO_VERIFY_SERVICE_SID = settings.TWILIO_VERIFY_SERVICE_SID
from django.contrib.postgres.fields import JSONField
from django.db.models import OuterRef, Subquery
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING, cast

logger = SimpleLogger(name='UserViews', log_file='logs/user_views.log').get_logger()

class PlayerViewSet(viewsets.ModelViewSet):
    queryset = Users.objects.filter(role="player").order_by("-id")
    serializer_class = PlayerSerializer
    any_permission_classes = []
    http_method_names = ["get", "post", "patch"]
    filter_class = PlayerFilters
    pagination_class = None

    def get_permissions(self):
        """
        Instantiates any_permission_classes attribute the list of permissions that this view requires.
        """
        if self.action in ("create",):
            self.any_permission_classes = [IsAdmin, IsSuperAdmin, IsDealer, IsAgent]
        else:
            self.any_permission_classes = [IsAdmin, IsSuperAdmin, IsDealer, IsAgent, IsPlayer, IsManager]

        return [AnyPermissions()]

    def get_queryset(self):
        dealer = self.request.query_params.get("dealer", False)
        agents = self.request.query_params.get("agents", False)
        sort_by = self.request.query_params.get("sort_by", False)

        queryset = super().get_queryset()

        if dealer:
            queryset = queryset.filter(dealer_id=dealer)

        if agents:
            agents_list = agents.split(",")
            agents_id_list = []
            for agent in agents_list:
                try:
                    agent = int(agent)
                    agents_id_list.append(agent)
                except Exception as e:
                    pass

            if agents_id_list:
                queryset = queryset.filter(agent_id__in=agents_id_list)

        if sort_by:

            if sort_by == "Recent Login":
                queryset = queryset.order_by("-last_login")
            elif sort_by == "Credit Ascending":
                queryset = queryset.order_by("balance")
            elif sort_by == "Credit Descending":
                queryset = queryset.order_by("-balance")
            elif sort_by == "Profit Ascending":
                queryset = queryset.order_by("locked")
            elif sort_by == "Profit Descending":
                queryset = queryset.order_by("-locked")
        else:
            queryset = queryset.order_by("-id")
        data = Transactions.objects.filter(journal_entry = 'bonus',bonus_type = SPIN_WHEEL,created__date = datetime.now().date(),user = self.request.user).first()
        if self.request.user.role == "player":
            queryset = queryset.filter(id=self.request.user.id).annotate(
                    custom_spin=Value(data is not None, output_field=BooleanField())
                )
            queryset = queryset.annotate(cashapp=Value((list(CashAppDeatils.objects.filter(user_id=self.request.user.id, is_active=True).values('id','name','is_active'))), output_field=JSONField()))
            return queryset
        elif self.request.user.role == "dealer":
            return queryset.filter(dealer=self.request.user, role="player")
        elif self.request.user.role == "agent":
            return queryset.filter(agent=self.request.user, role="player")
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["lang_code"] = "US"

        return context
#player api

class LoginAPIView(APIViewContext):
    serializer_class = LoginSerializer
    permission_classes = (AllowAny,)

    def post(self, request):
        translation_language = request.data.get("language",'en')
        if(translation_language in ['nl','ru','de','tr','fr']):
            activate(translation_language)
        else:
            activate('en')
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            response = serializer.validated_data
            user = Users.objects.filter(id=response["user"].pk).first()

            ip = AcuityTecAPI.get_ip_from_request(request=request)
            data = AcuityTecAPI.parse_user_to_geo(user=user, ip=ip)

            if not response["user"].username in settings.ACUITYTEC_EXCEPTIONS:
                result_geo = AcuityTecAPI.is_geo_verified(**data)

                if result_geo['status'] == -1:
                    return Response(result_geo['message'], status.HTTP_401_UNAUTHORIZED)

            if user.is_currently_active and not settings.MULTI_DEVICE_LOGIN_ENABLED:
                if user.last_activity_time < timezone.now()-timedelta(minutes=15):  
                    user.last_activity_time = timezone.now()
                    user.save()
                    return Response(
                        {
                            "auth_token": response["token"],
                            "pk": response["user"].pk,
                            "role": response["user"].role,
                            "username": response["user"].username,
                            "last_login": response["user"].last_login,
                        },
                        status.HTTP_200_OK,
                    )
                else:    
                    return Response({"message": _("You are already logged in on another device")},status.HTTP_400_BAD_REQUEST,)
            else:
                user.last_activity_time = timezone.now()
                user.is_currently_active = True
                user.save()
                return Response(
                        {
                            "auth_token": response["token"],
                            "pk": response["user"].pk,
                            "role": response["user"].role,
                            "username": response["user"].username,
                            "last_login": response["user"].last_login,
                        },
                        status.HTTP_200_OK,
                    )


        return Response(serializer.errors, status.HTTP_401_UNAUTHORIZED)


class ChangePassword(APIViewContext):

    serializer_class = ChangePasswordSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        """
        Check user's old password and change it. All authenticated users can perform this action.

        :param request: old_password, password
        :return: 200 Success. 400 invalid current password.
        """
        user = self.request.user
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Check old password
            if not user.check_password(serializer.data.get("old_password")):
                return Response(
                    {"message": _("Invalid current password")},
                    status.HTTP_400_BAD_REQUEST,
                )

            user.set_password(serializer.data.get("password"))
            user.save()

            return Response("Success.", status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyToken(APIView):
    permission_classes = (AllowAny,)
    http_method_names = [
        "post",
    ]

    def post(self, request):
        token = request.data.get("token", None)
        username = request.data.get("username", None)
        is_allowed_user = True
        if token:
            try:
                user_token = Users.objects.get(user__username=username).access_token
                if token != user_token:
                    is_allowed_user = False
            except Exception:
                is_allowed_user = True
            # try:
            #     is_blackListed = BlackListedToken.objects.get(
            #         user__username=username,
            #         token=token
            #     )
            #     if is_blackListed:
            #         is_allowed_user = False
            # except BlackListedToken.DoesNotExist:
            #     is_allowed_user = True
        else:
            return Response(
                {"message": _("Invalid Token")},
                status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"username": username, "is_allowed_user": is_allowed_user},
            status.HTTP_200_OK,
        )

class CashbackView(APIView):

    permission_classes = (AllowAny,)
    http_method_names = [
        "get",
        "post",
    ]

    def get(self, request):
        player_id = request.GET.get("user_id", None)
        if player_id:
            player = Player.objects.filter(id=player_id).first()
            if player:
                is_cashback_available = False
                cashback_percentage = CASHBACK_PERCENTAGE * 100
                if (player.cashback_amount > 0) and player.cashback_status:
                    is_cashback_available = True
                if hasattr(player.agent, "agentbetlimits"):
                    cashback_percentage = player.agent.agentbetlimits.cashback_percentage * 100
                return Response(
                    {
                        "is_cashback_available": is_cashback_available,
                        "cashback_amount": player.cashback_amount,
                        "cashback_percentage": cashback_percentage,
                    },
                    status.HTTP_200_OK,
                )
        return Response(
            {"message": _("Invalid User")},
            status.HTTP_400_BAD_REQUEST,
        )

    def post(self, request):
        from apps.bets.models import Transactions
        player_id = request.data.get("user_id", None)
        if player_id:
            player = Player.objects.filter(id=player_id).first()
            if player and (player.cashback_amount > 0):
                transaction_obj = Transactions()
                transaction_obj.user = player
                transaction_obj.reference = generate_reference(player)
                transaction_obj.previous_balance = player.balance
                transaction_obj.amount = player.cashback_amount

                player.balance += player.cashback_amount
                player.cashback_amount = 0
                player.save()

                transaction_obj.status = CHARGED
                transaction_obj.new_balance = player.balance
                transaction_obj.journal_entry = CASHBACK
                transaction_obj.merchant = None
                transaction_obj.betslip = None
                transaction_obj.description = (
                    f"cashback_amount- {player.cashback_amount} for user-{player.username}"
                )
                transaction_obj.save()
                return Response(
                    {"message": _("Cashback added to your balance"), "balance": player.balance},
                    status.HTTP_200_OK,
                )
        return Response(
            {"message": _("Invalid User or Cashback Not available")},
            status.HTTP_400_BAD_REQUEST,
        )


class SignUpView(APIViewContext):
    serializer_class = SignUpSerializer
    http_method_names = [
        "post",
    ]

    def post(self, request: Request) -> Response:
        data = request.data.copy()

        if str(request.data.get('tyc') or '') != "1":
            return Response(
                {"message": "You must accept the TYC."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if str(request.data.get('confirm_age') or '') != "1":
            return Response(
                {"message": "You must confirm you are 18+."},
                status=status.HTTP_400_BAD_REQUEST
            )

        country_code = request.data.get('country_code', '')
        phone_number = request.data.get('phone_number', '') 

        if country_code == '' or phone_number == "":
            data.pop('country_code', None)
            data.pop('phone_number', None)

        cca2 = "US"

        if not cca2:
            return Response(
                {"message" : "code_ccs2 has not been provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        data.pop("country", None)
        data.pop('code_cca2', None)

        country = Country.objects.filter(
            code_cca2=cca2.upper()
        ).first()

        if not country:
            return Response(
                {"message" : "code_cca2 is not valid"},
                status=status.HTTP_400_BAD_REQUEST
            )

        data["country_obj"] = country.id
        data["country"] = country.code_cca2

        if Users.objects.filter(
            username__iexact=request.data.get("username")
        ).exists():
            return Response(
                {"message": _("User already exists.")},
                status.HTTP_400_BAD_REQUEST
            )

        try:
            serializer = self.get_serializer(data=data)
        except:
            serializer = SignUpSerializer(
                data=data,
                context=self.get_serializer_context(),
            )

        if not serializer.is_valid():
            non_field_errors = serializer.errors.get('non_field_errors', None) #type: ignore
            if non_field_errors:
                return Response(
                    {"message": non_field_errors[0]},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return Response(
                {"message": "Invalid account."},
                status=status.HTTP_400_BAD_REQUEST
            )

        player: Users = cast(Users, serializer.save())

        Thread(
            target=newuser_email,
            args=(player.username, player.email)
        ).start()

        redeam_user_event.apply_async(
            args=(EVENT_REGISTRATION, player.id),
            countdown=10
        )  # type: ignore

        if player.applied_promo_code:
            promo_handler.redeem_code(
                user=player,
                amount_dep=None,
                bonus_type='welcome',
                promo_code=str(player.applied_promo_code)
            )

        return Response(
            {"message": _("User Created Successfully")},
            status=status.HTTP_201_CREATED
        )


'''User Update Api'''
class UserUpdateView(APIViewContext):
    permission_classes = (IsAuthenticated,)
    http_method_names = ["post"]

    def decode_base64_image(self, base64_string: str) -> Tuple[str, ContentFile]:
        format, imgstr = base64_string.split(';base64,')
        ext = format.split('/')[-1]
        img_data = base64.b64decode(imgstr)
        return format, ContentFile(img_data, name=f'temp.{ext}')

    def create_thumbnail(self, image_file, filename: str, ext: str):
        thumbnail = Image.open(image_file)
        thumbnail.thumbnail((500, 400))
        buffer = BytesIO()
        fmt = 'JPEG' if ext.lower() == 'jpg' else ext.upper()
        thumbnail.save(buffer, format=fmt, filename=filename)
        return InMemoryUploadedFile(buffer, 'FileField', filename, fmt, sys.getsizeof(buffer), None)

    def post(self, request):
        try:
            player = request.user
            if not player:
                return Response({"message": "User not found", },status.HTTP_400_BAD_REQUEST)

            if player.document_verified == VERIFICATION_APPROVED:
                return Response({"message": "User Updated Successfully."},status.HTTP_200_OK)

            # Handle user personal data
            cca2 = "US"
            phone_number = request.data.get("phone_number")
            country_code = request.data.get("country_code")
            cashtag = request.data.get("cashtag")

            # Handle profile picture
            profile_pic_data = request.data.get("profile_pic")
            profile_pic = player.profile_pic

            if(profile_pic_data and not profile_pic_data.startswith("https")):
                format, profile_pic = self.decode_base64_image(profile_pic_data)
                filename_format = profile_pic.name.split(".")
                name, format = filename_format[-2], filename_format[-1]
                filename = f"{name}{uuid.uuid4()}.{format}"
                profile_pic.name = filename
                player.profile_pic = profile_pic
                # page_thumbnail_inmemory = self.create_thumbnail(image_file=profile_pic, filename=filename, ext=format)
                # user.profile_pic_thumbnail = page_thumbnail_inmemory

            if request.data.get("profile_pic", "https").startswith("https"):
                profile_pic = player.profile_pic

            if Country.objects.filter(code_cca2=cca2).exists():
                player.country = cca2
                player.country_obj = Country.objects.get(code_cca2=cca2)

            if phone_number and country_code:
                # if Users.objects.filter(phone_number=phone_number, country_code=country_code).exclude(Q(username=request.data.get('username')) | Q(phone_verified=1)).exists():
                #     return Response({"message": "Phone number belongs to another user."}, status.HTTP_400_BAD_REQUEST)
                player.country_code = country_code
                player.phone_number = phone_number
                try:
                    player.clean()
                except ValueError:
                    return Response({"title":"Error","icon":"error","message": "The number used is not valid"}, status.HTTP_400_BAD_REQUEST)


            if cashtag and player.cashtag!=cashtag:
                if Player.objects.filter(cashtag=cashtag).exists(): 
                    return Response({"title":"Error","icon":"error","message": "Cashtag Already Exists!"}, status.HTTP_400_BAD_REQUEST)

            update_fields = {
                "first_name": request.data.get("first_name"),
                "last_name": request.data.get("last_name"),
                "email": request.data.get("email"),
                "zip_code": request.data.get("zip_code"),
                "state": request.data.get("state"),
                "city": request.data.get("city"),
                "dob": request.data.get("dob"),
                "complete_address": request.data.get("complete_address"),
                "profile_pic": profile_pic,
                "cashtag": cashtag,
            }

            for field, value in update_fields.items():
                if value is not None:
                    setattr(player, field, value)

            # player.document_verified = VERIFICATION_PROCESSING if player.document_verified == VERIFICATION_PROCESSING else VERIFICATION_PENDING

            player.save()

            # ip = get_user_ip_from_request(request=request)
            # register_or_update_user.delay(ip, timezone.now().isoformat(), player.id)
            return Response({"message": "User Updated Successfully"},status.HTTP_200_OK)

        except Exception as e:
            print(f"Error in update-user-details : {e}")
            return Response({"message": "something went wrong", },status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetOTPView(APIViewContext):
    serializer_class = GetOtpSerializer
    permission_classes = (AllowAny,)
    http_method_names = ["post"]

    def post(self, request):
        try:
            data = request.data.copy()
            if request.user.is_authenticated:
                print(request.user.username)
                data["username"] = request.user.username

            if not data.get("username"):
                return Response({"message": "username must not be null."}, status.HTTP_400_BAD_REQUEST)
            if not data.get("phone_number"):
                return Response({"message": "phone_number must not be null."}, status.HTTP_400_BAD_REQUEST)
            if not data.get("country_code"):
                return Response({"message": "country_code must not be null."}, status.HTTP_400_BAD_REQUEST)

            # Declare variables for a better readability
            sign_up = bool(data.get("is_sign_up", False))
            forgot_psw = bool(data.get("is_forgot_password", False))
            verify_number = bool(data.get("is_verify_number", False))

            if not is_only_one(sign_up, forgot_psw, verify_number):
                return Response(
                    {"message": "Only one action can be made per OTP"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            users_with_same_phone = Users.objects.filter(
                phone_number=data.get("phone_number"),
                country_code=data.get("country_code"),
            )
            user_with_same_name = Users.objects.filter(username__iexact=data.get("username").lower())
            user_forgotten_pwd = Users.objects.none()
            if data.get("is_forgot_password"):
                user_forgotten_pwd = Users.objects.filter(username__iexact=data.get("username").lower(),
                                        phone_number=data.get("phone_number"),
                                        country_code=data.get("country_code"))
            if verify_number:
                users_with_same_phone = Users.objects.filter(
                    phone_number=data.get("phone_number"),
                    country_code=data.get("country_code"),
                ).exclude(username=data.get("username"))

                for user in users_with_same_phone:
                    print(user.username)

            # Check age
            # if sign_up:
            if False:
                dob = request.data.get('dob')
                if dob is None:
                    return Response({"message": "You must submit your dob"}, status.HTTP_400_BAD_REQUEST)
                try:
                    dob_date = dt.strptime(dob, "%Y-%m-%d").date()
                except ValueError:
                    return Response({"message": "DOB must be formatted YYYY-MM-DD"}, status.HTTP_400_BAD_REQUEST)
                today = timezone.now().date()
                age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))

                if age < 18:
                    return Response({"message": "You must be 18+ to have an account on this platform"}, status.HTTP_400_BAD_REQUEST)


            # Start of the logic
            if sign_up and user_with_same_name.exists():
                return Response(
                    {"message": _("User already exists.")}, status.HTTP_400_BAD_REQUEST
                )
            elif sign_up and users_with_same_phone.exists():
                return Response(
                    {"message": _("This mobile number already exist")},
                    status.HTTP_400_BAD_REQUEST,
                )
            elif forgot_psw and not user_forgotten_pwd.exists():
                return Response(
                    {"message": _("User with this mobile number and username doesn't exist")},
                    status.HTTP_400_BAD_REQUEST,
                )
            elif verify_number:
                if not request.user.is_authenticated:
                    return Response(
                        {"message": "User needs to be logged in"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if request.user.phone_number == data.get("phone_number") and\
                        request.user.country_code == data.get("country_code") and\
                        request.user.phone_verified == 1:
                    return Response(
                        {"message": _("You cannot change to the same phone number")},
                        status.HTTP_400_BAD_REQUEST,
                    )
                if users_with_same_phone.exists():
                    return Response(
                        {"message": _("This mobile number already exist")},
                        status.HTTP_400_BAD_REQUEST,
                    )

            serializer = self.get_serializer(data=data)
            if serializer.is_valid():
                response_data = serializer.validated_data
                try:
                    client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
                    client.verify.services(TWILIO_VERIFY_SERVICE_SID).verifications.create(
                        to="+"
                        + response_data["country_code"]
                        + response_data["phone_number"],
                        channel="sms",
                    )
                    if verify_number:
                        user = request.user
                        user.country_code = response_data["country_code"]
                        user.phone_number = response_data["phone_number"]
                        user.save()

                    return Response(
                        {
                            "message": _("OTP Sent"),
                            "phone_number": response_data["phone_number"],
                            "country_code": response_data["country_code"],
                        },
                        status.HTTP_200_OK,
                    )

                except TwilioRestException as e:
                    if e.status == 429:
                        return Response(
                            {"message": _("Too many requests for OTP. Please try again later.")},
                            status.HTTP_429_TOO_MANY_REQUESTS,
                        )
                    if e.status == 503:
                        return Response(
                            {"message": _("Service Unavailable. Please try again later.")},
                            status.HTTP_503_SERVICE_UNAVAILABLE,
                        )
                    return Response(
                        {"message": _("This mobile number does not exist.")}, status.HTTP_400_BAD_REQUEST
                    )
                except Exception as e:
                    return Response(
                        {"message": _("Something went wrong.")}, status.HTTP_400_BAD_REQUEST
                    )

            return Response({"message": serializer.errors}, status.HTTP_400_BAD_REQUEST)
        except ValidationError as e:
            print(f"Error in GET-OTP : {e}")
            return Response({"message": str(e)}, status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"Error in GET-OTP : {e}")
            return Response({"message": "something went wrong", },status.HTTP_400_BAD_REQUEST)


class OTPActionsView(APIView):
    def post(self, request):
        try:

            TWILIO_ACCOUNT_SID = settings.TWILIO_ACCOUNT_SID
            TWILIO_AUTH_TOKEN = settings.TWILIO_AUTH_TOKEN

            data = request.data.copy()
            # Declare variables for a better readability
            forgot_psw = bool(data.get("is_forgot_password", False))
            verify_number = bool(data.get("is_verify_number", False))

            if not is_only_one(False, forgot_psw, verify_number):
                return Response(
                    {"message": "Only one action can be made per OTP"},
                    status=status.HTTP_400_BAD_REQUEST
                )


            if verify_number:
                if not request.user.is_authenticated:
                    return Response(
                        {"message": "Must be logged in first"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                data["username"]= request.user.username
                data["country_code"] = request.user.country_code
                data["phone_number"] = request.user.phone_number

            try:
                client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                check = client.verify.v2.services(
                    TWILIO_VERIFY_SERVICE_SID
                ).verification_checks.create(
                    to="+" + data.get("country_code") + data.get("phone_number"),
                    code=data.get("otp"),
                )
            except Exception:
                return Response(
                    {"message": "Invalid OTP"}, status.HTTP_400_BAD_REQUEST
                )

            if check.status == "approved" and check.valid is True:
                if verify_number:
                    if not request.user.is_authenticated:
                        return Response({"message": "To verify a number you should be logged in first"}, status=status.HTTP_400_BAD_REQUEST)
                    user: Users = request.user
                    if user.phone_verified == 1:
                        return Response({"message": "User was verified"}, status=status.HTTP_202_ACCEPTED)
                    user.phone_verified = VERIFICATION_APPROVED
                    user.save()

                    return Response({"message": "User is now verified"}, status.HTTP_200_OK)

                if forgot_psw:
                    user_obj = Users.objects.filter(username__iexact=data.get("username"),
                                                    country_code=data.get("country_code"),
                                                    phone_number=data.get("phone_number")).first()
                    if not user_obj:
                        return Response({"message": "Invalid OTP"}, status.HTTP_400_BAD_REQUEST)
                    user_obj.password = make_password(data.get("new_password"))
                    user_obj.save()

                    return Response(
                        {"message": "Password Changed"},
                        status.HTTP_200_OK,
                    )
            else:
                return Response({"message": "Invalid OTP"}, status.HTTP_400_BAD_REQUEST)
        except Exception as err:
            return Response(
                {"message": f"Requested service is not allowed. {err}"},
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyOTPView(APIView):
    # Verifies the otp from number when sign in
    # MarcosAlv: I considere this deprecated and we ("I") are planing to remove it slowly ("next update")
    # MaecosAlv: This was a really slowly update. There has been 4 months

    def post(self, request):
        try:
            TWILIO_ACCOUNT_SID = settings.TWILIO_ACCOUNT_SID
            TWILIO_AUTH_TOKEN = settings.TWILIO_AUTH_TOKEN
            TWILIO_VERIFY_SERVICE_SID = settings.TWILIO_VERIFY_SERVICE_SID

            data = request.data
            user_data = request.data["user_data"]
            try:
                client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                check = client.verify.services(
                    TWILIO_VERIFY_SERVICE_SID
                ).verification_checks.create(
                    to="+"+user_data.get("country_code") + user_data.get("phone_number"),
                    code=data.get("otp"),
                )
            except Exception:
                return Response(
                    {"message": "Invalid OTP"}, status.HTTP_400_BAD_REQUEST
                )

            if check.status == "approved" and check.valid is True:
                if data.get("is_signup"):
                    if user_data.get("agent_id"):
                        agent_obj = Users.objects.filter(role="agent", pk=user_data.get("agent_id")).first()
                        dealer_obj = Users.objects.filter(role="dealer", pk=agent_obj.dealer_id).first()
                    else:
                        agent_obj = Users.objects.filter(role="agent").first()
                        dealer_obj = Users.objects.filter(role="dealer").first()

                    # Check if user is referred by?
                    referred_by = Users.objects.filter(referral_code=user_data.get("referral_code", None)).first()
                    # Affiliated
                    # Note: this is the way I think it was meant to be implemented
                    affiliated_by = request.user if request.user.is_authenticated else None

                    # Give this user referral code so that he can refer-a-friend as well
                    user_referral_code = ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(5))
                    user_referral_code = "RF-" + user_data.get("username") + user_referral_code

                    user = Users()
                    user.username = user_data.get("username", "").lower()
                    user.password = make_password(user_data.get("password"))
                    user.role = "player"
                    user.country_code = user_data.get("country_code")
                    user.phone_number = user_data.get("phone_number")
                    user.dob = user_data.get("dob")
                    user.state = user_data.get("state")
                    user.city = user_data.get("city")
                    user.first_name = user_data.get("first_name")
                    user.last_name = user_data.get("last_name")
                    user.complete_address =user_data.get("complete_address")
                    user.email = user_data.get("email", None)
                    # user.user_id_proof=user.data.get("user_id_proof")
                    # user.profile_pic=user.data.get("profile_pic")
                    user.is_staff = False
                    user.is_superuser = False
                    user.is_active = True
                    user.agent = agent_obj
                    user.dealer = dealer_obj
                    user.affiliated_by = affiliated_by
                    user.applied_promo_code = user_data.get("applied_promo_code", None)
                    user.referred_by = referred_by if referred_by else None
                    user.referral_code = user_referral_code
                    user.save()

                    # Log applied promocode details so that we can track the applied counts and other details mfor the future references
                    promo_code_a = user_data.get("applied_promo_code", None)
                    if promo_code_a:
                        promo_handler.claim_code(user=user, promo_code=promo_code_a)

                    return Response(
                        {"message": "Signup Successfull"},
                        status.HTTP_200_OK,
                    )

                elif data.get("is_forgot_password"):
                    user_obj = Users.objects.filter(username__iexact=user_data.get("username"),
                                                    country_code=user_data.get("country_code"), 
                                                    phone_number=user_data.get("phone_number")).first()
                    user_obj.password = make_password(user_data.get("new_password"))
                    user_obj.save()

                    return Response(
                        {"message": "Password Changed"},
                        status.HTTP_200_OK,
                    )
            else:
                return Response({"message": "Invalid OTP"}, status.HTTP_400_BAD_REQUEST)
        except Exception as  err:
            return Response(
                {"message": f"Requested service is not allowed. {err}"},
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AdminPublicDetailsView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["get", ]
    serializer_class = AdminBannerSerializer

    def get(self, request):
        try:
            banner_category = request.GET.get('device_type',"DESKTOP")
            banner_type = request.GET.get('banner_type',"HOMEPAGE")
            # admin_banners = defaultdict(list)
            # for banner in AdminBanner.objects.filter(banner_category=banner_category):
            #     admin_banners[banner.banner_type.lower()].append({"url": f'{settings.BE_DOMAIN}{banner.url}',})
            banners = AdminBanner.objects.filter(banner_category=banner_category, banner_type__iexact=banner_type).order_by("-created")
            if request.user.is_authenticated and request.user.is_verified:
                banners = banners.exclude(title__endswith='$')
            serializer = self.serializer_class(banners, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as err:
            print(traceback.format_exc())
            return Response({"message": str(err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminBannerClicksView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["post", ]

    def post(self, request):
        try:
            banner_url = request.data.get('banner_url',None)
            banner_obj = AdminBanner.objects.filter(url=banner_url).first()
            if banner_obj:
                banner_obj.clicks += 1
                banner_obj.save()
                return Response({"message": "Success"}, status=status.HTTP_200_OK)
            else:
                return Response({"message": "Banner not found"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as err:
            return Response({"message": str(err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)                   

class PlayerDeActiveView(APIViewContext):
    permission_classes = (IsPlayer,)
    http_method_names = ["post"]

    def post(self, request):
        is_account_cancelled = request.data.get("is_account_cancelled", False)
        try:
            player = Player.objects.filter(id=request.user.id).first()
            if player:
                agent = Agent.objects.filter(id=player.agent_id).first()
                agent_email = "" if not agent.email else f"at {agent.email}"

                responsible_gambling = ResponsibleGambling.objects.get_or_create(user=player)[0]
                if responsible_gambling.is_account_cancelled:
                    return Response({"message": _(f'Account has been already deactivated. Please contact your administrator {agent_email} to reactivate.')},
                                     status.HTTP_400_BAD_REQUEST)
                responsible_gambling.is_account_cancelled = is_account_cancelled
                responsible_gambling.save()
                return Response(
                    {"message": f'Account has been deactivated. Please contact your administrator {agent_email} to reactivate.'},
                    status.HTTP_200_OK,
                )
            return Response({"message": _("Player doesn't exist")}, status.HTTP_400_BAD_REQUEST,)
        except Exception as err:
            return Response({"message": str(err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SetPlayerMaxSpendLimitView(APIViewContext):
    permission_classes = (IsPlayer,)
    http_method_names = ["post"]

    def post(self, request):
        max_spending_limit = int(request.data.get("max_spending_limit", MAX_SPEND_AMOUNT))
        from datetime import timezone
        try:
            player = Player.objects.filter(id=request.user.id).first()
            if player:
                responsible_gambling = ResponsibleGambling.objects.get_or_create(user=player)[0]
                if responsible_gambling.max_spending_limit_expire_time:
                    if datetime.now(timezone.utc) < responsible_gambling.max_spending_limit_expire_time.astimezone(pytz.utc):
                        return Response({"message": _("Max spending limit already set for the next 24hrs.")}, status.HTTP_400_BAD_REQUEST)

                if max_spending_limit > MAX_SPEND_AMOUNT:
                    return Response({"message": _(f"Max spending limit cannot be greater than {MAX_SPEND_AMOUNT}")}, status.HTTP_400_BAD_REQUEST)

                responsible_gambling.max_spending_limit = max_spending_limit
                responsible_gambling.daily_spendings = 0
                responsible_gambling.is_max_spending_limit_set_by_admin = False
                responsible_gambling.max_spending_limit_expire_time = datetime.now(pytz.utc)+timedelta(minutes=5)

                responsible_gambling.save()
                return Response(
                    {"message": "Player spending limit successfully updated"},
                    status.HTTP_200_OK,
                )
            return Response({"message": _("Player doesn't exist")}, status.HTTP_400_BAD_REQUEST, )
        except Exception as err:
            return Response({"message": str(err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SetPlayerBlackoutView(APIViewContext):
    permission_classes = (IsPlayer,)
    http_method_names = ["post"]

    def post(self, request):
        blackout_expire_time = request.data.get("blackout_expire_time", None)
        from datetime import timezone
        try:
            player = Player.objects.filter(id=request.user.id).first()
            if player:
                if blackout_expire_time:
                    responsible_gambling = ResponsibleGambling.objects.get_or_create(user=player)[0]
                    if not responsible_gambling.is_blackout: 
                        responsible_gambling.blackout_expire_time = datetime.now(timezone.utc)+timedelta(hours=int(blackout_expire_time))
                        responsible_gambling.is_blackout = True
                        responsible_gambling.blackout_expire_hours = blackout_expire_time
                        responsible_gambling.save()
                        return Response(
                            {"message": "Player blackout successfully updated"},
                            status.HTTP_200_OK,
                        )
                    elif(responsible_gambling.is_blackout and responsible_gambling.blackout_expire_time.astimezone(pytz.utc) < datetime.now(timezone.utc)):
                            responsible_gambling.blackout_expire_time = datetime.now(timezone.utc)+timedelta(hours=int(blackout_expire_time))
                            responsible_gambling.is_blackout = True
                            responsible_gambling.blackout_expire_hours = blackout_expire_time
                            responsible_gambling.save()

                            return Response(
                                {"message": "Player blackout successfully updated"},
                                status.HTTP_200_OK,
                            )
                    return Response({"message": _("Player already in blackout")}, status.HTTP_400_BAD_REQUEST,)
                else:
                    return Response({"message": _("Blackout time not provided")}, status.HTTP_400_BAD_REQUEST,)
            return Response({"message": _("Player doesn't exist")}, status.HTTP_400_BAD_REQUEST, )
        except Exception as err:
            return Response({"message": str(err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ContactUsView(APIView):
    def post(self, request):
        try:
            data = request.data

            if not (data.get("first_name") and data.get("last_name") and data.get("email") and data.get("phone") and data.get("query")):
                return Response({"message": "All Fields Required"}, status.HTTP_400_BAD_REQUEST)

            contact_obj = CmsContactDetails()
            contact_obj.first_name = data.get("first_name", None)
            contact_obj.last_name = data.get("last_name", None)
            contact_obj.email = data.get("email", None)
            contact_obj.phone = str(data.get("country_code", "")) + str(data.get("phone", None))
            contact_obj.query = data.get("query", None)
            contact_obj.save()
            return Response({"message": "Thank you! We will get back to you soon."}, status.HTTP_200_OK)

        except:
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class AboutCmsView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ["get", ]

    def get(self, request):
        cms_obj = CmsAboutDetails.objects.first()
        response = {
            "title": cms_obj.title if cms_obj else '',
            "content": cms_obj.page_content if cms_obj else '',
            "more_info": cms_obj.more_info if cms_obj else '',
            "image_url": cms_obj.banner.url if cms_obj and cms_obj.banner else ''
        }
        return Response({"data": response}, status.HTTP_200_OK)


class PromotionCmsView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ["get", ]
    serializer_class = CmsPromotionSerializer

    def get(self, request):
        cms_obj = CmsPromotionDetails.objects.order_by('-id')
        serializer = self.serializer_class(cms_obj, many=True)
        return Response({"data": serializer.data}, status.HTTP_200_OK)


class CmsPromotionsView(APIView):
    # permission_classes = (IsAuthenticated,)
    permission_classes = (AllowAny,)
    http_method_names = ["get", ]
    serializer_class = CmsPromotionsSerializer

    def get(self, request):
        now = timezone.now()
        cms_obj = CmsPromotions.objects.filter(
            disabled=False,
            start_date__lte=now,
            end_date__gte=now
        ).order_by('-start_date')

        # Apply type filter
        promo_type = request.GET.get('type', 'toaster')
        if promo_type in ['toaster', 'page_blocker']:
            cms_obj = cms_obj.filter(type=promo_type)
        # if promo_type == 'all', no filter is applied
        serializer = self.serializer_class(cms_obj, many=True)
        return Response({"data": serializer.data}, status.HTTP_200_OK)


class CmsPrivacyPolicyView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ["get", ]

    def get(self, request):
        cms_obj = CmsPrivacyPolicy.objects.first()
        response = {
            "title": cms_obj.title if cms_obj else '',
            "content": cms_obj.page_content if cms_obj else '',
            "more_info": cms_obj.more_info if cms_obj else '',
            "image_url": cms_obj.banner.url if cms_obj and cms_obj.banner else ''
        }
        return Response({"data": response}, status.HTTP_200_OK)



class CmsFAQView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ["get", ]

    def get(self, request):
        cms_obj = CmsFAQ.objects.first()
        response = {
            "title": cms_obj.title if cms_obj else '',
            "content": cms_obj.page_content if cms_obj else '',
            "more_info": cms_obj.more_info if cms_obj else '',
            "image_url": cms_obj.banner.url if cms_obj and cms_obj.banner else ''
        }
        return Response({"data": response}, status.HTTP_200_OK)


class TermsConditinosView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ["get", ]

    def get(self, request):
        cms_obj = TermsConditinos.objects.first()
        response = {
            "title": cms_obj.title if cms_obj else '',
            "content": cms_obj.page_content if cms_obj else '',
            "more_info": cms_obj.more_info if cms_obj else '',
            "image_url": cms_obj.banner.url if cms_obj and cms_obj.banner else ''
        }
        return Response({"data": response}, status.HTTP_200_OK)


class CookiePolicyView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ["get", ]

    def get(self, request):
        cms_obj = CookiePolicy.objects.first()
        response = {
            "title": cms_obj.title if cms_obj else '',
            "content": cms_obj.page_content if cms_obj else '',
            "more_info": cms_obj.more_info if cms_obj else '',
            "image_url": cms_obj.banner.url if cms_obj and cms_obj.banner else ''
        }
        return Response({"data": response}, status.HTTP_200_OK)


class IntroductionView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ["get", ]

    def get(self, request):
        cms_obj = Introduction.objects.first()
        response = {
            "title": cms_obj.title if cms_obj else '',
            "content": cms_obj.page_content if cms_obj else '',
            "more_info": cms_obj.more_info if cms_obj else '',
            "image_url": cms_obj.banner.url if cms_obj and cms_obj.banner else ''
        }
        return Response({"data": response}, status.HTTP_200_OK)


class SettingsLimitsView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ["get", ]

    def get(self, request):
        cms_obj = SettingsLimits.objects.first()
        response = {
            "title": cms_obj.title if cms_obj else '',
            "content": cms_obj.page_content if cms_obj else '',
            "more_info": cms_obj.more_info if cms_obj else '',
            "image_url": cms_obj.banner.url if cms_obj and cms_obj.banner else ''
        }
        return Response({"data": response}, status.HTTP_200_OK)


class ValidateSignUpPromoCode(APIView):
    """
    API to validate the promo-code user will apply at the time of sign-up
    """
    permission_classes = (AllowAny,)
    http_method_names = ["post"]

    def post(self, request):

        promo_code = request.data.get("promo_code", None)
        if promo_code is None:
            return Response(
                {
                    "data": {
                        "message": "Invalid promocode",
                        "status": "Failed",
                    }
                },
                status=status.HTTP_200_OK,
            )

        user = request.user if request.user.is_authenticated else None
        ip = get_user_ip_from_request(request=request)

        is_valid, msg = promo_handler.verify_code(ip=ip, user=user, promo_code=promo_code)

        status_text = "Success" if is_valid else "Failed"
        http_status = status.HTTP_200_OK if is_valid else status.HTTP_400_BAD_REQUEST
        message = "Promo-code applied successfully" if is_valid else msg

        return Response(
            {"data": {"message": message, "status": status_text}},
            status=http_status,
        )


class ValidatePromoCode(APIView):
    """
    API to validate the promo-code user will apply at the time of deposit
    """
    permission_classes = (AllowAny,)
    http_method_names = ["post"]

    def post(self, request) -> Response:

        promo_code = request.data.get("promo_code", None)
        promo_type = request.data.get("promo_type", "deposit")
        
        amount = str(request.data.get("amount", ""))
        
        if amount and amount.isdigit():
            amount = Decimal(amount)
        else:
            amount = None

        if promo_type not in {'welcome', 'deposit'}:
            promo_type = "deposit"

        if promo_code is None:
            return Response(
                {
                    "data": {
                        "message": "Invalid promocode",
                        "status": "Failed",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user if request.user.is_authenticated else None
        ip = get_user_ip_from_request(request=request)

        pm, msg = promo_handler.verify_code(
            ip=ip,
            user=user,
            bonus_type=promo_type,
            promo_code=promo_code,
        )

        status_text = "Success" if pm else "Failed"
        http_status = status.HTTP_200_OK if pm else status.HTTP_400_BAD_REQUEST
        extra_data = {}

        if pm and amount and promo_type == "deposit":
            dm = pm.bonus_distribution_method
            bonus = Decimal("0.0")
            g_bns = Decimal("0.0")
            if dm == "deposit":
                bonus = (Decimal(pm.bonus_percentage or 0) * amount) / 100  # type: ignore
                g_bns = (Decimal(pm.gold_percentage or 0) * amount * Decimal(settings.BONUS_MULTIPLIER)) / 100  # type: ignore
            elif dm == "mixture":
                bonus = Decimal(pm.bonus_percentage or 0) * amount / 100  # type: ignore
                g_bns = pm.gold_bonus
            elif dm == "instant":
                bonus = Decimal(pm.bonus or 0)
                g_bns = pm.gold_bonus

            extra_data = {
                "amount": amount,
                "gold": amount * settings.BONUS_MULTIPLIER,
                "promo_amount": round(bonus),
                "promo_gold": round(g_bns),
            }

        message = "Promo-code is valid" if pm else msg

        return Response(
            {"data": {"message": message, "status": status_text, **extra_data}},
            status=http_status,
        )


class ValidateReferralUser(APIView):
    """
    API to validate the referred_by user at the time of sign-up
    """
    permission_classes = (AllowAny,)
    http_method_names = ["post"]

    def post(self, request):
        response = { "message":"Succesfull", "status": "success" }

        referred_user = request.data.get("referred_user", None)

        # validate the promocode
        try:
            referred_by_user = Users.objects.filter(username__iexact=referred_user).first()

            if not referred_by_user:
                response = { "message":"Invalid user, please enter valid username", "status": "Failed" }
                return Response({"data": response}, status.HTTP_404_NOT_FOUND)

            if referred_by_user.role == 'player':
                response = { "message":"Invalid user, please enter valid username", "status": "Failed" }
                return Response({"data": response}, status.HTTP_404_NOT_FOUND)

        except Exception as e:
            print(e)
            response = { "message":"Something went wrong", "status": "Failed" }

        return Response({"data": response}, status.HTTP_200_OK)


class GetSocialLinkView(APIView):
    http_method_names = ["get", ]

    def get(self, request):
        response = []
        [
            response.append({"title":slink.title,"logo": f"{settings.BE_DOMAIN}{slink.logo.url}" if slink.logo else None,"url": slink.url})
            for slink in SocialLink.objects.all().distinct()
        ]
        return Response({"social_links": response}, status.HTTP_200_OK)


class GetFooterLinks(APIView):
    http_method_names = ["get", ]

    def get(self, request):
        output = []
        category = []
        response = {}
        for page in FooterPages.objects.all().order_by('category__position'):
            if not page.pages:
                continue
            if page.category.id in category:
                response[page.category.slug].append({
                    "title": page.pages.title,
                    "slug": page.pages.slug,
                    "is_form": page.pages.is_form,
                    "form_name": page.pages.form_name,
                    "is_redirect": page.pages.is_redirect,
                    "redirect_url": page.pages.redirect_url, 
                    'is_page': page.pages.is_page
                })
            else:
                category.append(page.category.id)
                response[page.category.slug] = [{
                    "title": page.pages.title,
                    "slug": page.pages.slug,
                    "is_form": page.pages.is_form,
                    "form_name": page.pages.form_name,
                    "is_redirect": page.pages.is_redirect,
                    "redirect_url": page.pages.redirect_url, 
                    'is_page': page.pages.is_page
                }]
        for key, value in response.items():
            items = {}
            category = FooterCategory.objects.filter(slug=key).first()
            if category:
                items["category"] = {"name": category.name, "slug": category.slug, "position": category.position}
            items["pages"] = value
            output.append(items)
        return Response({"response": output}, status.HTTP_200_OK)


class FooterDeatilsView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ["get", ]

    def get(self, request):
        footer_page = FooterPages.objects.all()
        response =[]
        category =[]
        if request.GET.get('category_name'):
            footer_page = footer_page.filter(category__slug=request.GET.get('category_name'))
        elif request.GET.get('page_name'):
            footer_page = footer_page.filter(pages__slug=request.GET.get('page_name'))
        for obj in footer_page:
            if not obj.pages or not obj.category:
                continue
            if obj.category.id in category:
                response[0]["page"].append({
                    'title': obj.pages.title,
                    'page_img': obj.pages.page.url if obj.pages.page else None,
                    'page_content': obj.pages.page_content,
                    'slug': obj.pages.slug,
                    'is_form':obj.pages.is_form,
                    'form_name':obj.pages.form_name,
                    'is_redirect':obj.pages.is_redirect,
                    'redirect_url':obj.pages.redirect_url,
                    'is_page': obj.pages.is_page
                })
            else:
                category.append(obj.category.id)
                response.append({
                    'name':obj.category.name,
                    'category_slug':obj.category.slug,
                    'page':[{
                        'title':obj.pages.title,
                        'page_img':obj.pages.page.url if obj.pages.page else None,
                        'page_content':obj.pages.page_content,
                        'pages_slug':obj.pages.slug,
                        'is_form':obj.pages.is_form,
                        'form_name':obj.pages.form_name,
                        'is_redirect':obj.pages.is_redirect,
                        'redirect_url':obj.pages.redirect_url,
                        'is_page': obj.pages.is_page
                    }]
                })
        return Response({"data": response}, status.HTTP_200_OK)


class PagesDeatilsView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ["get", ]

    def get(self, request):
        pages = None
        response = []
        if request.GET.get('page_name'):
            pages = CmsPages.objects.filter(slug=request.GET.get('page_name')).first()
        if pages:
            response = {
                'title': pages.title,
                'page_img': pages.page.url if pages.page else None,
                'page_content': pages.get_page_content(),
                'pages_slug': pages.slug,
                'is_form': pages.is_form,
                'form_name': pages.form_name,
                'is_redirect': pages.is_redirect,
                'redirect_url': pages.redirect_url,
                'is_page': pages.is_page,
                'more_info':pages.more_info,
                'meta_description':pages.meta_description,
                'json_metadata':pages.json_metadata,
                'media_preview_type':pages.preview_type,
                'media': self.get_media(pages),
            }

        return Response({"data": response}, status.HTTP_200_OK)

    def get_media(self, page):
        urls = []
        all_media = page.media.all()
        for page_media in all_media:
            urls.append(f"{settings.BE_DOMAIN}{page_media.media.url}")

        return urls



class SetPlayerBettingLimitView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ["post"]

    def post(self, request):
        amount = request.data.get("amount")
        player_id = request.data.get("player_id")
        try:
            if amount:
                player = Player.objects.filter(id=player_id).first()
                if player:
                    player_betting_limit = PlayerBettingLimit.objects.filter(player=player).exists()
                    if player_betting_limit:
                        return Response({"message": _("Betting limit already set, please wait for 24 hours to reset again.")}, status.HTTP_400_BAD_REQUEST, )

                    player_betting_limit = PlayerBettingLimit.objects.create(player=player, amount=amount)

                    return Response(
                        {"message": _("Your Betting limit successfully saved for next 24 hours.")},
                        status.HTTP_200_OK,
                    )
                return Response({"message": _("Player doesn't exist")}, status.HTTP_400_BAD_REQUEST, )
            return Response({"message": _("Please provide the amount.")}, status.HTTP_400_BAD_REQUEST, )
        except Exception as err:
            return Response({"message": str(err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class Notification(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        title = request.data.get("title", None)
        message = request.data.get("content", None)

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "notification_lobby", {
                "type": "send_notification",
                "title": json.dumps(title),
                "message":  json.dumps(message),
            }
        )

        redis_db = redis.Redis(db=2, host='localhost', port=6379)
        redis_db.execute_command('SELECT', 2)
        notification = redis_db.get('notification')
        if notification:
            notification = json.loads(notification)
            notification[f"{datetime.utcnow()}"] = message
        else:
            notification = {}
            notification[f"{datetime.utcnow()}"] = message
        redis_db.set('notification',json.dumps(notification), 24*60*60)
        return Response(
            {
                "status": "Successs",
                "message": "Notification sent Successfully",
            },
            status.HTTP_200_OK,
        )


class GetSlug(APIView):
    # permission_classes = (IsPlayer,)
    http_method_names = ["get", ]

    def get(self, request):
        slugs=[]

        slugs.append(CmsPages.objects.filter(hidden=False).all().values("slug", "title"))

        return Response({"response": slugs}, status.HTTP_200_OK)



class PlayerEmailOTPsender(APIView):
    http_method_names = ["post"]
    def post(self, request):
        try:
            username = request.data.get("username")
            player = Users.objects.filter(username__iexact=username).first()
            if not player:
                return Response({"error": "No User Found", "status": status.HTTP_404_NOT_FOUND},status.HTTP_404_NOT_FOUND)
            if player:
                if not player.email: 
                    return Response({"error": "Email Not Provided Contact Agent", "status": status.HTTP_400_BAD_REQUEST},status.HTTP_400_BAD_REQUEST)
                else:
                    generated_otp =  create_otp_password(username)
                    context = {
                        "otp": generated_otp,
                        "expiration_time":"10 Mins",
                        "fe_url": settings.FE_DOMAIN,
                    }
                    sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
                    mail_template = EmailTemplateDetails.objects.filter(category='signup_otp_mail').first()
                    if mail_template:
                        mail = Mail( 
                            from_email=settings.SENDGRID_EMAIL,
                            to_emails= [player.email]
                        )
                        mail.template_id = mail_template.template_id
                        mail.dynamic_template_data = context
                        sg.send(mail)
                        return Response({"message": "Otp Sent to Your Email", "status": status.HTTP_200_OK}, status.HTTP_200_OK)

                    html_content = render_to_string("email_template.html", context)

                    message = Mail( 
                            from_email=settings.SENDGRID_EMAIL,
                            to_emails=player.email,
                            subject="OTP for Email Verification",
                            html_content=html_content)

                    sg.send(message)
                    return Response({"message": "Otp Sent to Your Email", "status": status.HTTP_200_OK}, status.HTTP_200_OK)
            else:
                return Response({"error": "Email not provided", "status": status.HTTP_404_NOT_FOUND},status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e), "status": status.HTTP_400_BAD_REQUEST},status.HTTP_400_BAD_REQUEST)


class ForgotPassword(APIView):
    http_method_names = ["post"]
    def post(self, request):
        try:

            password = request.data.get("password")
            username = request.data.get("username")
            player = Users.objects.filter(username__iexact=username).first()
            if not player:
                return Response({"error": "No User Found", "status": status.HTTP_404_NOT_FOUND},status.HTTP_404_NOT_FOUND)
            if request.data.get('otp'):
                checkotp = check_otp(request.data.get('username') + str(request.data.get('otp')))
                if not checkotp:
                   return Response({"error": "Please enter valid OTP", "status": status.HTTP_400_BAD_REQUEST},status.HTTP_400_BAD_REQUEST)
            else:
                   return Response({"error": "Please enter valid OTP", "status": status.HTTP_400_BAD_REQUEST},status.HTTP_400_BAD_REQUEST)

            player.password = make_password(password)
            player.save()
            return Response({"message": "Password Changed Successfully", "status": status.HTTP_200_OK}, status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response({"message": "Internal Error", "status": status.HTTP_500_INTERNAL_SERVER_ERROR}, status.HTTP_500_INTERNAL_SERVER_ERROR)

class AdminAdsPublicDetailsView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["post", ]

    def post(self, request):
        try:
            admin_banners = defaultdict(list)
            banner_category = request.data.get('device_type',"DESKTOP")
            for banner in AdminAdsBanner.objects.filter(banner_category=banner_category):
                admin_banners[banner.banner_type.lower()].append({"url":f'{settings.BE_DOMAIN}{banner.url}',"redirect_url":banner.redirect_url})
            return Response({"banners":admin_banners}, status=status.HTTP_200_OK)
        except Exception as err:
            return Response({"message": str(err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AffiliatedPlayers(APIView):
    http_method_names = ["post"]
    def post(self, request):
        from .serializers import AffiliateSerializer
        try:
            player = Users.objects.filter(username__iexact=request.data.get("username")).first()
            if not player:
                return Response({"error": "No User Found", "status": status.HTTP_404_NOT_FOUND},status.HTTP_404_NOT_FOUND)
            affiliated_players = Player.objects.filter(affiliated_by=player).order_by('created')  
            response =  AffiliateSerializer(affiliated_players ,many=True)
            return Response(response.data)
        except Exception as e:
            print(e)


class ComingSoonPagesDeatilsView(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ["get", ]

    def get(self, request):
        admin_obj = Admin.objects.filter().first()
        if not admin_obj:
            return Response(
                {"message": "No page detail exist."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
        if admin_obj.coming_soon_scheduled and admin_obj.coming_soon_scheduled < timezone.now():
            admin_obj.is_coming_soon_enabled = False
            admin_obj.save()

        return Response({
            "datetime": admin_obj.coming_soon_scheduled, 
            "bonus": admin_obj.coming_soon_bonus, 
            "enabled": admin_obj.is_coming_soon_enabled,
            "is_maintenance_mode_enabled": admin_obj.is_maintenance_mode_enabled,
            "maintenance_mode_message": admin_obj.maintenance_mode_message,
        }, status.HTTP_200_OK)


class AffiiateRequestView(APIView):
    permission_classes = (IsPlayer,)
    http_method_names = ["post"]
    def post(self, request):
        try:
            data = request.data
            user =  Users.objects.filter(id=request.user.id).first()
            affiliate_req = AffiliateRequests()
            affiliate_req.user = user
            affiliate_req.no_of_deposit_counts = data.get('no_of_deposit_count',None)
            affiliate_req.is_bonus_on_all_deposits = data.get('is_bonus_on_all_deposits',False)
            affiliate_req.no_of_days = data.get('days',None)
            affiliate_req.is_lifetime_affiliate = data.get('is_lifetime_affiliate',False)
            affiliate_req.status = AffiliateRequests.StatusType.pending
            affiliate_req.save()
            return Response({"message": "Thank you! Your Request is Submited."}, status.HTTP_200_OK)

        except:
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class QueueView(APIView):
    permission_classes = (IsPlayer,)
    http_method_names = ["post"]
    def post(self, request):
        try:
            data = request.data
            user = Users.objects.filter(id=request.user.id).first()
            if data.get('operation') == 'position':
                active_staff=Staff.objects.filter(agent=user.agent,is_staff_active=True).count()
                if active_staff == 0:
                    return Response({"message": "No active Staff For User"}, 400)

                player = Queue.objects.filter(user=user).first()
                if player:
                    position =  Queue.objects.filter(is_active=True,user__agent=user.agent,pick_by = None).count()
                    position_cou =  Queue.objects.filter(is_active=True,user__agent=user.agent,pick_by__isnull =False).count()
                    if position_cou >= 1:
                        position = position + 1

                    return Response({"position": position}, status.HTTP_200_OK)
                else:
                    return Response({"message": "Player Entry not found in queue"}, 400)

            if data.get('operation') == 'change_status':
                is_active = data.get('is_active')
                player_entry = Queue.objects.filter(user=user).first()
                if player_entry:
                    player_entry.is_active = is_active
                    player_entry.is_remove = is_active
                    player_entry.pick_by = None
                    player_entry.save()
                    return Response({"message": "Status Changed"}, status.HTTP_200_OK)
                else:
                    return Response({"message": "Player Entry not found in queue"}, 400)
            else:
                roomname = f"P{user.id}Chat"
                chatroom = ChatRoom.objects.filter(name=roomname).first()
                if chatroom:
                    is_chat_saved = self.save_chathistory(chatroom)
                    if is_chat_saved:
                        print(f"Chat Saved for {roomname}")
                    else:
                        print(f"Chat Not Saved for {roomname}")
                    chatroom.delete()
                chatroom = ChatRoom.objects.get_or_create(name=roomname)
                active_staff=Staff.objects.filter(agent=user.agent,is_staff_active=True).count()
                if active_staff == 0:
                    return Response({"message": "No active Staff For User"}, 400)  
                Queue.objects.filter(user=user).delete() 
                queue = Queue()
                queue.user = user
                queue.is_active = data.get('is_active',None)
                queue.is_remove = data.get('is_active',None)
                queue.pick_by = None
                queue.save()
            player = Queue.objects.filter(user=user).first()
            position = Queue.objects.filter(is_active=True,user__agent=user.agent,pick_by =None).count()
            position_cou = Queue.objects.filter(is_active=True,user__agent=user.agent,pick_by__isnull =False).count()
            if position_cou >= 1:
                position = position + 1

            return Response({"position": position}, status.HTTP_200_OK)

        except:
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)        

    def save_chathistory(self,chatroom):
        try:
            chatmessages = ChatMessage.objects.filter(room=chatroom).order_by('created')
            message_list = []
            player,staff = None, None
            for message in chatmessages:
                message_dict = {}
                message_dict['sender'] = message.sender.username
                message_dict['message'] =  message.message_text if message.is_file == False else message.file.name
                message_dict['is_file'] = str(message.is_file)
                message_dict['sent_time'] = message.sent_time.strftime("%Y-%m-%d %H:%M:%S.%f%z")
                message_list.append(message_dict)

                if player == None or staff == None:
                    user = Users.objects.filter(id=message.sender.id).first()
                    if user.role =='staff':
                        staff = user
                    else:
                        player = user

            message_json = json.dumps(message_list)
            message_json =  json.loads(message_json)
            if chatmessages.count() > 0:
                ChatHistory.objects.create(chats=message_json,player=player,staff=staff)  
                ChatMessage.objects.filter(room=chatroom).delete()
            # ChatRoom.objects.filter(name=chatroom.name).delete()
            print(ChatRoom.objects.filter(name=chatroom.name).first(),"ROOM_queue") 
            return True
        except Exception as e:
            print("Error in saving chathistory",e)
            return False


class SignUpOTP(APIView):
    http_method_names = ["post"]
    def post(self, request):
        try:
            email = str(request.data.get("email"))
            username = request.data.get("username")
            city = str(request.data.get('city'))
            cca2 = "US"
            # country_code = request.data.get("country_code")
            # phone_number = request.data.get("phone_number")
            #
            # check_phone = True

            first_name = request.data.get('first_name')
            if not first_name or first_name == '' or first_name == ' ':
                return Response({'message' : 'first name must not be null.'}, status.HTTP_400_BAD_REQUEST)

            last_name = request.data.get('last_name')
            if not last_name or last_name == '' or last_name == ' ':
                return Response({'message' : 'last name must not be null.'}, status.HTTP_400_BAD_REQUEST)
            names = [first_name, last_name]

            if not city:
                return Response({"message": "City name must not be null"}, status.HTTP_400_BAD_REQUEST)
            if not email:
                return Response({"message": "Email must not be null"}, status.HTTP_400_BAD_REQUEST)
            if not username:
                return Response({"message": "Username must not be null"}, status.HTTP_400_BAD_REQUEST)
            # if not country_code or not phone_number:
            #     check_phone = False
            if str(request.data.get('tyc')) != "1":
                return Response({"message" : "You must accept the TYC, tyc != 1"},status=status.HTTP_400_BAD_REQUEST)
            if str(request.data.get('confirm_age')) != "1":
                return Response({"message" : "You must confirm you are 18+, confirm_age != 1"},status=status.HTTP_400_BAD_REQUEST)

            # check age
            # dob = request.data.get('dob')
            # if dob is None:
            #     return Response({"message": "You must submit your dob"}, status.HTTP_400_BAD_REQUEST)
            # try:
            #     dob_date = dt.strptime(dob, "%Y-%m-%d").date()
            # except ValueError:
            #     return Response({"message": "DOB must be formatted YYYY-MM-DD"}, status.HTTP_400_BAD_REQUEST)
            # today = timezone.now().date()
            # age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))

            # if age < 18:
            #     return Response({"message": "You must be 18+ to have an account on this platform"}, status.HTTP_400_BAD_REQUEST)

            if cca2:
                country = Country.objects.filter(code_cca2=cca2.upper()).first()
                if not country:
                    return Response({"message" : "code_cca2 is not valid"},status=status.HTTP_400_BAD_REQUEST)
                cca2 = country.code_cca2
            else:
                return Response({"message" : "code_cca2 has not been provided"},status=status.HTTP_400_BAD_REQUEST)


            # TODO: ADD THE DIVING NAME PART

            pattern = re.compile("[A-Za-z0-9]*$")
            if not pattern.fullmatch(username):
                return Response({"message": "Username must be alphanumeric"}, status.HTTP_400_BAD_REQUEST)

            if Users.objects.filter(email=email).exists(): 
                return Response({"error": "Email already exists", "status": status.HTTP_400_BAD_REQUEST},status.HTTP_400_BAD_REQUEST)
            if Users.objects.filter(username__iexact=username).exists():
                return Response({"error": "User already exists", "status": status.HTTP_400_BAD_REQUEST},status.HTTP_400_BAD_REQUEST)
            # elif check_phone:
            #     if Users.objects.filter(Q(country_code=country_code), Q(phone_number=phone_number)).exists():
            #         return Response({"error": "Phone number already exists", "status": status.HTTP_400_BAD_REQUEST},status.HTTP_400_BAD_REQUEST)
            if len(username)<4:
                return Response({"error": "Username must be atleast 4 characters long", "status": status.HTTP_400_BAD_REQUEST},status.HTTP_400_BAD_REQUEST)


            ip = AcuityTecAPI.get_ip_from_request(request=request)


            # TODO: REMOVE THIS ON PROD
            ts = 1749793047.0 # Unix timestamp
            dt = datetime.fromtimestamp(ts, tz=timezone.utc) 
            if timezone.now() - dt < timedelta(days=1):
                ip = request.data.get('ip', ip)

            result = AcuityTecAPI.is_geo_verified(first_name=names[0], last_name=names[1], user_name=username, email=email, city=city, id='AREA51-NEW-user', cca2=cca2, ip=ip)

            if result['status'] == -1:
                return Response({"error": result['message'], "status": status.HTTP_400_BAD_REQUEST},status.HTTP_400_BAD_REQUEST)

            generated_otp = create_otp()
            print(generated_otp)
            context = {
                "otp": generated_otp,
                "expiration_time":"10 Mins",
                "fe_url": settings.FE_DOMAIN,
            }
            sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
            mail_template = EmailTemplateDetails.objects.filter(category='signup_otp_mail').first()
            if mail_template:
                mail = Mail(
                    from_email=settings.SENDGRID_EMAIL,
                    to_emails= [email]
                )
                mail.template_id = mail_template.template_id
                mail.dynamic_template_data = context
                sg.send(mail)
                return Response({"message": "Email sent successfully", "status": status.HTTP_200_OK}, status.HTTP_200_OK)

            html_content = render_to_string("email_signup_template.html", context)

            message = Mail( 
                    from_email=settings.SENDGRID_EMAIL,
                    to_emails=email,
                    subject="OTP for Email Verification",
                    html_content=html_content)

            sg.send(message)
            return Response({"message": "Email sent successfully", "status": status.HTTP_200_OK}, status.HTTP_200_OK)
        except Exception as e:
            logger.error(e)
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)

class TipView(APIView):
    permission_classes = (IsPlayer,)
    http_method_names = ["post"]

    @transaction.atomic
    def post(self, request):
        from apps.bets.models import Transactions

        data = request.data
        if not data.get("is_tip"):
            return Response({"message": "Deprecated functions."}, status.HTTP_400_BAD_REQUEST)

        try:
            tip_amount = Decimal(data.get('tip', 0.00))
        except Exception:
            return Response({"message": "Invalid tip amount."}, status.HTTP_400_BAD_REQUEST)

        user =  Users.objects.select_for_update().filter(id=request.user.id).first()
        staff = Users.objects.filter(id = data.get('staff')).first()
        if user is None or staff is None:
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)

        if user.balance < tip_amount:
            return Response({"message": "Not enough balance."}, status.HTTP_400_BAD_REQUEST)

        chatroom = ChatRoom.objects.filter(name=f"P{user.id}Chat", player_id=user.id).first()
        if chatroom is None:
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)

        icon_url = "https://admin.area51.global/static/images/checked-green.svg"
        tip_html = (
            f'<div class="tip-text">'
            f"Paid <strong class='tip-amount'>${tip_amount}</strong> "
            f"tip to <strong class=\"tip-username\">{staff.username}</strong> "
            f"<img src='{icon_url}' /> "
            f"</div></span>"
        )

        Transactions.objects.update_or_create(
            user=user,
            journal_entry='credit',
            amount=data.get('tip',None),
            status="charged",
            merchant=request.user,
            previous_balance=user.balance ,
            new_balance=user.balance - Decimal(tip_amount),
            description=f"Tip of {tip_amount} to {staff.username}",
            reference=generate_reference(user),
            bonus_type= None,
            bonus_amount=0
        )

        # chathistory_obj.tip_amount = tip_amount
        staff.balance = staff.balance + Decimal(tip_amount)
        user.balance = user.balance - Decimal(tip_amount)
        staff.save()
        user.save()

        ChatMessage.objects.create(
            room=chatroom,
            sender=user,
            message_text=tip_html,
            sent_time=timezone.now(),
            is_file=False,
            file=None,
            is_tip=True,
            type='message',
            tip_user=staff,
            is_comment=False
        )

        ChatHistory.objects.create(
            player=user,
            staff=staff,
            tip_amount=tip_amount
        )

        send_player_balance_update_notification(user)

        local_channel = get_channel_layer()

        async_to_sync(local_channel.group_send)(
            f"P{user.id}Chat",
            {
                "type": "send_notification",
                "message": json.dumps({
                    "type": "message",
                    "message": tip_html,
                    "sender_id": user.id,
                    "sent_time": timezone.now().strftime("%Y-%m-%d %H:%M:%S.%f%z"),
                    "is_file": False,
                    "file_extension": None,
                    "player_id": user.id,
                    "is_player_sender": True,
                    "is_tip": True,
                    "tip_user": staff.id,
                    "is_comment": False,
                    "user_balance": str(user.balance),
                }),
            }
        )

        return Response({"message":"Success"}, status.HTTP_200_OK)


class CsrQueryView(APIView):
    permission_classes = (IsPlayer,)
    http_method_names = ["post","get"]
    def post(self, request):
        try:
            data = request.data
            user = Users.objects.filter(id=request.user.id).first()
            query = CsrQueries()
            query.subject = request.data.get('subject')
            query.text = request.data.get('text')
            query.is_active = True
            query.user = user
            query.save()
            Thread(
                target=queries_email,
                args=(query.id,)
            ).start()
            return Response({"message": "request added successfully"}, status.HTTP_200_OK)

        except:
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request):
        try:
            user = Users.objects.filter(id=request.user.id).first()
            queries = CsrQueries.objects.filter(user=user,is_active=True).order_by('created').values('created',"text","subject",'id') 
            return Response({"queries": queries}, status.HTTP_200_OK)

        except:
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)

class RecentMessagesView(APIView):
    permission_classes = (IsPlayer,)
    http_method_names = ["get"]

    def get(self, request):
        try:
            user = Users.objects.filter(id=request.user.id).first()
            room=f'P{user.id}Chat'
            messages = ChatMessage.objects.filter(room__name=room).order_by('created').annotate(sender_username=F('sender__username')).values('sent_time',"sender_username","message_text",'is_file','file') 
            for message in messages:
                message['sent_time'] = message['sent_time'].timestamp()

            return Response({"messages": messages}, status.HTTP_200_OK)

        except:
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class RestrictedLoginView(APIView):
    permission_classes = (IsPlayer,)
    http_method_names = ["post"]
    def post(self, request):
        try:
            data = request.data
            user = Users.objects.filter(id=request.user.id).first()
            if not user:
                return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)
            operation = request.data.get('operation')
            if operation == 'logout':
                user.last_activity_time = timezone.now()
                user.is_currently_active = False
                user.save()
            if operation == 'last_activity_time':
                user.last_activity_time = timezone.now()
                user.is_currently_active = True
                user.save()
            return Response({"message": "Success"}, status.HTTP_200_OK)

        except:
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class OffMarketDepositView(APIView):
    permission_classes = (IsPlayer,)
    http_method_names = ["post"]

    def post(self, request):
        is_allowed = limiter.allow(
            key=f"ofm:{request.user.id}:deposit",
            sliding=True,
            window=90,
            limit=3,)

        if not is_allowed:
            return Response({"message": ("Deposit too frequent. "
                                            "Try again in a minute.")},
                            status.HTTP_429_TOO_MANY_REQUESTS)

        user = request.user
        if user is None:
            return Response({"message": "You should not see this"}, status.HTTP_400_BAD_REQUEST)

        try:
            promo_code = request.data.get('promo_code')
            game_code = request.data.get('game_code')
            amount = Decimal(request.data.get('amount'))
        except Exception as e:
            return Response({"message" : "invalid amount"}, status=status.HTTP_400_BAD_REQUEST)

        success, error = RefujiClient.deposit(
            user=user,
            amount=amount,
            game_code=game_code,
            promo_code=promo_code,
            force_update=False
        )
        code = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
        message = "Request Submitted Successfully" if success else error

        return Response({"message": message}, status=code)


class OffmarketTransaction(APIView):
    http_method_name = ["get"]
    permission_classes = (IsPlayer,)
    pagination_class = CustomPagination

    def get(self, request, **kwargs):
        from apps.bets.utils import validate_date
        try:
            player = Users.objects.filter(id=request.user.id).first()
            if not player:
                return Response({"msg": "user not found", "status_code":status.HTTP_404_NOT_FOUND})
            request_params = self.request.query_params  # type: ignore

            transaction_filter_dict: Dict[str, Any] = {"user": player}
            withdraw_transaction_filter_dict = {
                "user": player,
                "status__in": ["pending", "rejected","cancelled"]
            }

            from_date = request_params.get("from_date", None)
            to_date = request_params.get("to_date", None)
            activity_type = request_params.get("activity_type", None)
            search = request_params.get("search", None)

            if activity_type:
                transaction_filter_dict["transaction_type"] = activity_type.upper()
                if activity_type.lower() != "withdraw":
                    withdraw_transaction_filter_dict["status__in"] = ""
            if search:
                transaction_filter_dict["game_name_full__icontains"] = search
                offmarket_games_code = list((OffMarketGames.objects.filter(title__icontains=search).values_list("code", flat=True)))
                withdraw_transaction_filter_dict["code__in"] = offmarket_games_code
            timezone_offset = request_params.get("timezone_offset", None)
            if from_date and validate_date(from_date):
                from_date = datetime.strptime(
                    from_date + " 00:00:00", "%Y-%m-%d %H:%M:%S"
                )
                if timezone_offset:
                    timezone_offset = float(timezone_offset)
                    if timezone_offset < 0:
                        transaction_filter_dict[
                            "created__gte"
                        ] = from_date + timedelta(
                            minutes=(-(timezone_offset) * 60)
                        )
                    else:
                        transaction_filter_dict[
                            "created__gte"
                        ] = from_date - timedelta(minutes=(timezone_offset * 60))
                    withdraw_transaction_filter_dict["created__gte"] = transaction_filter_dict["created__gte"]
                else:
                    transaction_filter_dict["created__date__gte"] = from_date
                    withdraw_transaction_filter_dict["created__date__gte"] = from_date

            if to_date and validate_date(to_date):
                to_date = datetime.strptime(
                    to_date + " 23:59:59", "%Y-%m-%d %H:%M:%S"
                )
                if timezone_offset:
                    timezone_offset = float(timezone_offset)
                    if timezone_offset < 0:
                        transaction_filter_dict[
                            "created__lte"
                        ] = to_date + timedelta(minutes=(-(timezone_offset) * 60))
                    else:
                        transaction_filter_dict[
                            "created__lte"
                        ] = to_date - timedelta(minutes=(timezone_offset * 60))
                    withdraw_transaction_filter_dict["created__lte"] = transaction_filter_dict["created__lte"]

            offmarket_transactions = OffMarketTransactions.objects.filter(**transaction_filter_dict).order_by("-created")
            withdraw_transactions = OffmarketWithdrawalRequests.objects.filter(**withdraw_transaction_filter_dict).order_by("-created")
            combined_transactions = list(sorted(
                chain(offmarket_transactions, withdraw_transactions),
                key=lambda objects: objects.created,
                reverse=True
            ))

            paginator = self.pagination_class()
            try:
                result_page = paginator.paginate_queryset(combined_transactions, request)
            except Exception as e:
                print(e)
                return Response({"msg": "Something went Wrong", "status_code": status.HTTP_400_BAD_REQUEST})
            serializer =  OffmarketTransactionsSerializer(result_page, many=True)
            return paginator.get_paginated_response(serializer.data)

        except Exception as e:
            print(f"error in fetching data {e}.")
            response = {"msg": "Some Internal error.", "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR}
            return Response(response)


class CountriesView(APIView):

    def get(self, request):
        lang_code = request.GET.get("lang", "en")
        activate(lang_code)

        countries = Country.objects.filter(enabled=True).order_by('name')

        serializer = CountrySerializer(
            countries,
            context={"lang_code": lang_code},
            many=True
        )

        return Response({ "countries": serializer.data, "status_code": status.HTTP_200_OK}, status=status.HTTP_200_OK)


class OffMarketWithdrawView(APIView):
    permission_classes = (IsPlayer,)
    http_method_names = ["post"]
    def post(self, request):
        try:
            user = Users.objects.filter(id=request.user.id).first()
            game_code = request.data.get('game_code')
            amount = request.data.get('amount')
            withdrawal_request = OffmarketWithdrawalRequests()
            withdrawal_request.user = user
            withdrawal_request.amount = amount
            withdrawal_request.code = game_code
            withdrawal_request.amount = amount
            withdrawal_request.save()
            return Response({"message": "Request Submitted Successfully"}, status.HTTP_200_OK)
        except:
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)

class NextSpinWheel(APIView):
    permission_classes = (IsPlayer,)
    http_method_names = ["post"]
    def post(self, request):
        try:
            status_data = get_spin_status(request.user, request.data.get("tz_offset"))
            if not status_data["success"]:
                return Response(status_data, status=status.HTTP_400_BAD_REQUEST)

            return Response({
                "is_spin_available": status_data["is_available"],
                "next_spin": status_data["next_spin"],
            }, status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response({"message": "Something Went Wrong"}, status=status.HTTP_400_BAD_REQUEST)


class AddSpinWheelView(APIView):
    permission_classes = (IsPlayer,)
    http_method_names = ["post"]
    @transaction.atomic
    def post(self, request):
        try:
            user = self.request.user
            status_data = get_spin_status(user, request.data.get("tz_offset"))
            if not status_data["success"]:
                return Response(status_data, status=status.HTTP_400_BAD_REQUEST)
            
            if not status_data["is_available"]:
                return Response({"message": "Already given spin bonus"}, status.HTTP_400_BAD_REQUEST)

            offset = status_data["offset"]
            now = status_data["now"]

            # Get a random SpinWheelDetail
            try:
                spin_wheel = get_price(user)
            except ValueError:
                return Response({"message": "Wheel is not active right now."}, status=status.HTTP_400_BAD_REQUEST)

            if spin_wheel is None or user is None:
                return Response({"message": "Please try again."}, status=status.HTTP_400_BAD_REQUEST)

            serializer = SpintheWheelDetailsSerializer(spin_wheel, many=False)
            process_spin_transaction(user, spin_wheel, now, offset)

            return Response({"message": "Bonus added", "result": serializer.data}, status.HTTP_200_OK)
        except:
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)



class SpintheWheelDetailsAPIView(APIView):
    def get(self, request):
        # Hide the spin the wheel when it is not verified
        # if not request.user.is_authenticated or not request.user.is_verified:
        #     return Response(SpintheWheelDetailsSerializer(SpintheWheelDetails.objects.none(), many=True).data)
        spin_wheel_details = SpintheWheelDetails.objects.all()
        serializer = SpintheWheelDetailsSerializer(spin_wheel_details, many=True)
        return Response(serializer.data)

from apps.bets.utils import validate_date
class TransactionsAPIView(APIView):
    http_method_name = ["get"]
    permission_classes = (IsPlayer,)
    pagination_class = CustomPagination

    def get(self, request, **kwargs):

        request_params = self.request.query_params

        from_date = str(request_params.get("from_date") or "")
        to_date = str(request_params.get("to_date") or "")
        timezone_offset = str(request_params.get("timezone_offset") or "")
        bonus_type = str(request_params.get("type") or "all")
        transaction_filter_dict = {"user":self.request.user, "journal_entry": "bonus"}

        tz_offset_minutes = float(timezone_offset) * 60 if timezone_offset else 0

        if from_date and validate_date(from_date):
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
            from_dt -= timedelta(minutes=tz_offset_minutes)
            transaction_filter_dict["created__gte"] = from_dt

        if to_date and validate_date(to_date):
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            to_dt -= timedelta(minutes=tz_offset_minutes)
            transaction_filter_dict["created__lte"] = to_dt

        transaction_queryset = Transactions.objects.filter(**transaction_filter_dict).order_by("-created")
        del transaction_filter_dict["journal_entry"]

        transaction_filter_dict["bonus__gt"] = 0
        offmarket_queryset = OffMarketTransactions.objects.filter(**transaction_filter_dict).order_by("-created")

        if bonus_type and bonus_type != "all":
            transaction_queryset = transaction_queryset.filter(bonus_type=bonus_type)
            if bonus_type != "offmarket_bonus":
                offmarket_queryset = []

        transactions = list(chain(transaction_queryset, offmarket_queryset))
        transactions = sorted(transactions, key=attrgetter('created'), reverse=True)

        paginator = self.pagination_class()
        try:
            result_page = paginator.paginate_queryset(transactions, request)
        except Exception as e:
            print(e)
            return Response({"msg": "Something went Wrong", "status_code": status.HTTP_400_BAD_REQUEST})
        serializer =  TransactionsSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)


class CashAppDetailsApi(APIView):
    http_method_names = ["get","post","put","delete"]
    permission_classes = (IsPlayer,)
    pagination_class = CustomPagination

    def get(self, request, **kwargs):
        cashapp_details = CashAppDeatils.objects.filter(user=self.request.user, is_active=True)
        paginator = self.pagination_class()
        try:
            result_page = paginator.paginate_queryset(cashapp_details, request)
        except Exception as e:
            print(e)
            return Response({"msg": "Something went Wrong", "status_code": status.HTTP_400_BAD_REQUEST})
        serializer =  CashAppDetailSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, **kwargs):
        name = self.request.data.get("name", None)
        if not name:
            return Response({"message": "CA Id is mandatory."}, status.HTTP_400_BAD_REQUEST)
        if CashAppDeatils.objects.filter(name__iexact=name).exists():
            return Response({"message": "CA Id already exists."}, status.HTTP_400_BAD_REQUEST)
        CashAppDeatils.objects.create(name=name,user = self.request.user,status = CashAppDeatils.StatusType.pending,is_active=True)
        return Response({"message": "CA ID of user created successfully."}, status.HTTP_200_OK)

    def put(self, request, **kwargs):
        ca_id = self.request.data.get("ca_id", None)
        name = self.request.data.get("name", None)
        if not name or not ca_id:
            return Response({"message": "CA Id and name is mandatory."}, status.HTTP_400_BAD_REQUEST)
        if CashAppDeatils.objects.filter(name__iexact=name).exclude(id = ca_id).exists():
            return Response({"message": "CA Id already exists."}, status.HTTP_400_BAD_REQUEST)
        cas_qs = CashAppDeatils.objects.filter(id = ca_id).first()
        if cas_qs.status == CashAppDeatils.StatusType.approved:
            return Response({"message": "It cannot update because the CA ID has already been approved."}, status.HTTP_400_BAD_REQUEST)
        CashAppDeatils.objects.filter(id = ca_id).update(name=name,user = self.request.user,status = CashAppDeatils.StatusType.pending,is_active=True)
        return Response({"message": "CA Id of user Updated Successfully."}, status.HTTP_200_OK)

    def delete(self, request, **kwargs):
        ca_id = self.request.GET.get("ca_id", None)
        cas_qs = CashAppDeatils.objects.filter(id = ca_id,is_active=True).first()
        if not cas_qs:
            return Response({"message": "CA Id Doesn't exist."}, status.HTTP_400_BAD_REQUEST)
        CashAppDeatils.objects.filter(id = ca_id).update(is_active = False)
        return Response({"message": "CA Id Deleted Successfully."}, status.HTTP_200_OK)

class CashappQrListView(APIView):
    permission_classes = [IsPlayer,]
    http_method_names = ["get", ]
    def get(self,kwargs):
        try:
            # if self.request.user.is_created_admin==True:
            #     user = self.request.user.admin
            # user = self.request.user.admin if self.request.user.is_created_admin else self.request.user.agent
            cashapp_qrs = CashappQr.objects.filter(is_active=True)
            serializer = CashappQrSerializer(cashapp_qrs, many=True)
            # else:
            #     return Response(
            #         {"message": _("Only admin can requested.")}, status.HTTP_400_BAD_REQUEST
            #     )

            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                    {"message": _("Something went wrong.")}, status.HTTP_400_BAD_REQUEST
                )


class ChatSupportView(APIView):
    permission_classes = (IsPlayer,)
    http_method_names = ["get", ]
    pagination_class = CustomPagination

    def get(self, request):
        try:
            request_type = request.GET.get('request_type', '')

            if request_type == "recent_messages":
                message_before = request.GET.get('message_before', None)

                messages = ChatMessage.objects.filter(
                    ~Q(type__in=[ChatMessage.MessageType.join, ChatMessage.MessageType.offmarket_signup], sender__role="player"),
                    room__player=self.request.user,
                    sent_time__gte=timezone.now()-timedelta(hours=72),

                ).exclude(type = "join",sender__role = 'player').order_by("-created")
                messages = messages.exclude(type = 'offmarket_signup')
                if message_before:
                    messages = messages.filter(id__lt=message_before).order_by("-sent_time")

                paginator = self.pagination_class()
                result_page = paginator.paginate_queryset(messages, request)
                serializer =  MessageSerializer(result_page, many=True)
                return paginator.get_paginated_response(serializer.data)
            elif request_type == "get_chatroom":
                chatroom, created = ChatRoom.objects.get_or_create(
                    name = f"P{self.request.user.id}Chat",
                    player = self.request.user,
                )
                return Response({"success":True, "chatroom": chatroom.name}, status.HTTP_200_OK)
            elif request_type == "message_count":
                unread_message_count = ChatMessage.objects.filter(~Q(sender__role="player"), room__player=self.request.user, is_read=False,type = ChatMessage.MessageType.message).count()
                return Response({"success":True, "unread_message_count": unread_message_count}, status.HTTP_200_OK)
            else:
                return Response({"success":False, "message": "Invalid request type"}, status.HTTP_400_BAD_REQUEST)
        except rest_exceptions.NotFound as e:
            return Response({"success":False, "message": str(e)}, status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(e)
            return Response({"success":False, "message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)
class StaffDetailView(APIView):
    permission_classes = (IsPlayer,)
    http_method_names = ["get"]

    def get(self, request):
        try:
            chat = ChatRoom.objects.filter(
                player = self.request.user
            ).last()
            if chat and chat.pick_by:
                staff_detail = {
                    "id": chat.pick_by.id,
                    "username": "Admin" if chat.pick_by.role != 'staff' else chat.pick_by.username,
                }
            else:
                return Response({"message":"Not found"}, status.HTTP_200_OK)
            return Response(staff_detail, status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)
class ReadMessageView(APIView):
    permission_classes = (IsPlayer,)
    http_method_names = ["get", ]
    def get(self, request):
        try:
            ChatMessage.objects.filter(~Q(sender__role="player"), room__player=self.request.user).update(is_read=True)
            return Response({"success":True, "message": "Message reading successfully."})
        except Exception as e:
            print(e)
            return Response({"success":False, "message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)



from django.utils.translation import activate

class SetlanguageView(APIView):
    http_method_names = ["get"]
    def get(self, request):
        from apps.core.country_language import country_language_mapping
        try:
            user_ip = request.META.get('REMOTE_ADDR')
            print(user_ip,"user_ip")
            response = requests.get(f"http://api.ipstack.com/{user_ip}?access_key=your_geolocation_service_api_key")
            data = response.json()
            print(data,"data")
            country_code = data.get('country_code')            
            language = country_language_mapping.get(country_code, 'en')
            return Response({"language":language,"data":data}, status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class BonusDetailView(APIView):
    http_method_names = ["get"]
    permission_classes = [AllowAny,]

    def get(self, request):
        try:
            bonus_type = self.request.GET.get("bonus_type")

            if bonus_type not in list(CmsBonusDetail.BonusType.labels.keys()):
                return Response({"message": "Invalid bonus_type"}, status.HTTP_200_OK)

            bonus_detail = CmsBonusDetail.objects.filter(bonus_type=bonus_type).values(
                "bonus_type",
                "promo_code",
                "content",
                "meta_description",
                "json_metadata",
            )

            return Response(bonus_detail, status.HTTP_200_OK)

        except:
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class FortunePandasAPIView(APIView):
    http_method_names = ["get", "post"]
    pagination_class = CustomPagination

    def get(self, request, *args, **kwargs):
        try:
            game_name=self.request.GET.get("name")
            game_category=self.request.GET.get("category")
            if self.request.user.is_authenticated:
                games = FortunePandasGameManagement.objects.filter(admin=self.request.user.admin, enabled=True)
                serializer_class = FortunePandasManagementGameListSerializer
                if game_category:
                    games = games.filter(game__game_category__iexact=game_category)
                if game_name:
                    games = games.filter(game__game_name__icontains=game_name)
            else:
                games = FortunePandasGameList.objects.all()
                serializer_class = FortunePandasGameListSerializer
                if game_category:
                    games = games.filter(game_category__iexact=game_category)
                if game_name:
                    games = games.filter(game_name__icontains=game_name)

            paginator = self.pagination_class()
            result_page = paginator.paginate_queryset(games, self.request)
            serializer =  serializer_class(result_page, many=True)
            return paginator.get_paginated_response(serializer.data)
        except rest_exceptions.NotFound as e:
            return Response({"success":False, "message": str(e)}, status.HTTP_400_BAD_REQUEST)
        except Exception as  e:
            print("Error in Fortunepandas API", e)
            print(traceback.format_exc())
            return Response({"message": f"Internal Server Error"}, 500)


    def post(self, request, *args, **kwargs):
        try:
            request_type = self.request.GET.get("request_type")
            amount = str(self.request.data.get("amount"))
            game_id = self.request.data.get("game_id")
            current_password = self.request.data.get("current_password")
            new_password = self.request.data.get("new_password")

            if not self.request.user.is_authenticated:
                return Response({"message": "Please login before performing this request"}, status=401)
            elif request_type not in ["start_game", "recharge", "redeem", "get_balance"]:
                return Response({"message": "Invalid request type"}, 400)
            elif request_type in ["recharge", "redeem"] and (not amount or re.sub(r'\d', '', amount) not in [".", ""]):
                return Response({"message": "Please provide valid amount"}, status=400)
            elif request_type == "start_game":
                if not game_id:
                    return Response({"message": "Please provide game_id"}, status=400)
                elif not FortunePandasGameList.objects.filter(game_id=game_id).exists():
                    return Response({"memssage": "Invalid game_id"}, status=400)
            elif request_type == "recharge" and self.request.user.balance < Decimal(amount):
                return Response({"message": "Insufficient balance"}, status=400)
            elif request_type == "change_password" and (not current_password or not new_password):
                return Response({"message": "Please provide current and new password"}, status=400)

            if not self.request.user.is_registered_in_fortune_pandas:
                response = self.call_api_with_retries("register_user")
                if response.get("message") != True:
                    return Response(response, status=400)

            if request_type == "start_game":
                return self.call_api_with_retries("start_game", game_id)
            elif request_type == "recharge":
                return self.call_api_with_retries("recharge_wallet", round(Decimal(amount), 2))
            elif request_type == "redeem":
                return self.call_api_with_retries("redeem_balance", round(Decimal(amount), 2))
            elif request_type == "change_password":
                return self.call_api_with_retries("change_password", current_password, new_password)
            elif request_type == "get_balance":
                return self.call_api_with_retries("get_and_update_balance")
        except Exception as  e:
            print("Error in Fortunepandas API", e)
            print(traceback.format_exc())
            return Response({"message": f"Internal Server Error"}, 500)


    def call_api_with_retries(self, api_method, *args, **kwargs):
        MAX_RETRIES = 3
        api = FortunePandaAPI(self.request.user)
        for attempt in range(MAX_RETRIES):
            response, status = getattr(api, api_method)(*args, **kwargs)
            if response.get("message") in ["Session timeout.", "Signature error."]:
                api.update_apikey()
                continue
            elif api_method == "register_user":
                return response
            else:
                return Response(response, status)
        print(response, "fortunepandas api call error")
        return Response({"message": "Failed to complete the API request after multiple retries. Please try again later."}, status=500)


class FortunePandasCategoryAPIView(APIView):
    http_method_names = ["get",]

    def get(self, request, *args, **kwargs):
        try:
            if self.request.user.is_authenticated:
                categories = FortunePandasGameManagement.objects.filter(
                    admin=self.request.user.admin,
                    enabled=True
                ).values_list("game__game_category", flat=True).order_by("game__game_category")
            else:
                categories = FortunePandasGameList.objects.values_list("game_category", flat=True).order_by("game_category")
            return Response(list(categories.distinct()))
        except Exception as  e:
            print("Error in Fortunepandas Category API", e)
            print(traceback.format_exc())
            return Response({"message": "Internal Server Error"}, 500)

class ReactorBonusAPIView(APIView):
    http_method_names = ["get"]
    permission_classes = [IsPlayer,]

    def get(self, request):
        try:
            bonus_amount = get_react_bonus_amount(self.request.user)
            return Response(bonus_amount, status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response({"message": "Something Went Wrong"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChageDepositLimit(APIView):
    http_method_names = ["post"]
    
    @transaction.atomic
    def post(self, request):
        extra = request.user.role in ("agent", "admin", "superadmin")

        # Target user
        user_id = (request.data.get("user_id", None) or request.user.id) if extra else request.user.id
        if extra and not user_id:
            return Response({"message": "user_id required."}, status=400)

        weekly = request.data.get("weekly_dl")
        daily = request.data.get("daily_dl")
        
        try:
            weekly = Decimal(weekly) if weekly else None
            daily = Decimal(daily) if daily else None
        except ValueError:
            return Response({"message": "Limits should be numbers"}, status=400)

        # Normal users must provide both values
        if not extra and (weekly is None or daily is None):
            return Response({"message": "Weekly and daily limits should be set."}, status=400)

        try:
            user = Users.objects.only("weekly_dl", "daily_dl").get(id=user_id)
        except Users.DoesNotExist:
            return Response({"message": "User does not exist."}, status=400)

        # Normal users cannot overwrite existing limits
        if not extra and (user.weekly_dl is not None or user.daily_dl is not None):
            return Response({"message": "Limits already set."}, status=400)
        
        if weekly is None or daily is None:
            weekly = None
            daily = None

        user.weekly_dl = weekly
        user.daily_dl = daily
        user.save(update_fields=["weekly_dl", "daily_dl"])

        return Response({"message": "OK"})

class ModifyGCBonus(APIView):
    http_method_names = ["post"]

    @transaction.atomic
    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"message": "You should authenticate first"},status=401)

        if not request.user.role in ("agent", "admin", "superadmin"):
            return Response({"message": "You should authenticate first"},status=401)

        balance = request.data.get("bonus_change")
        user_id = request.data.get("user_id")

        if balance is None:
            return Response({"message", "balance is not valid"}, status=400)
        try:
            balance = round(Decimal(balance), 2)
        except Exception:
            return Response()
        try:
            user = Users.objects.select_for_update().get(id=user_id)
        except Users.DoesNotExist:
            return Response({"message": "User does not exist"}, status=404)

        if user.bonus_balance + balance < 0:
            return Response({"message", "User has not enough balance"}, status=400)
        
        user.bonus_balance += balance
        user.save(update_fields=["bonus_balance"])
        return Response({"message": "OK"}, status=200)
