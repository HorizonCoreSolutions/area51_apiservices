import datetime
from email.policy import default
import json
from queue import Empty
import random
import re
import string

import uuid
from django.forms import CharField
import pytz

import requests
import urllib

# from rest_framework.authtoken.models import Token
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from api_services.settings.base import DOMAIN_URL
from apps.admin_panel.utils import create_casino_account_id
from rest_framework import serializers
from rest_framework_jwt.serializers import JSONWebTokenSerializer
from rest_framework_jwt.settings import api_settings
from apps.bets.models import Transactions
from cryptography.fernet import Fernet
import base64
from apps.core.exceptions import DeactivatedUserException, NotActiveUserException
from apps.users.models import (AdminBanner, CashAppDeatils, ChatMessage, CmsPromotionDetails,
                               FortunePandasGameList, FortunePandasGameManagement, MAX_MULTIPLE_BET, MAX_SINGLE_BET,
                               MAX_SINGLE_BET_OTHER_SPORTS, MAX_SPEND_AMOUNT, MIN_BET, OffMarketGames, PromoCodes,
                               ResponsibleGambling, Country)
from apps.users.utils import check_otp
import logging
logger = logging.getLogger('django')

from .models import DEFAULT_AFFILIATE_COMMISION_PERCENTAGE, DEFAULT_AFFILIATE_DURATION_IN_DAYS, Admin, DefaultAffiliateValues, OffMarketTransactions, Player, UserGames, Users, BonusPercentage , SpintheWheelDetails, CashappQr 

jwt_payload_handler = api_settings.JWT_PAYLOAD_HANDLER
jwt_encode_handler = api_settings.JWT_ENCODE_HANDLER


class CountrySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    code_cca2 = serializers.CharField(max_length=10)
    code_ccn3 = serializers.CharField(max_length=10)
    code_cca3 = serializers.CharField(max_length=10)
    flag = serializers.CharField(max_length=10)  # Stores emoji flag
    flag_url = serializers.SerializerMethodField()
    localized_name = serializers.SerializerMethodField()
    class Meta:
        model = Country
        fields = "__all__"

    def get_localized_name(self, obj):
        lang_code = str(self.context.get("lang_code", "en")).lower()
        return obj.translated_name.get(lang_code, obj.name)  # Default to English

    @staticmethod
    def get_flag_url(obj):
        return DOMAIN_URL + obj.flag_url


class PlayerSerializer(serializers.Serializer):
    dealer = serializers.PrimaryKeyRelatedField(
        queryset=Users.objects.filter(is_deleted=False, role="dealer"),
        required=True,
        write_only=True,
    )

    agent = serializers.PrimaryKeyRelatedField(
        queryset=Users.objects.filter(is_deleted=False, role="agent"),
        required=True,
        write_only=True,
    )
    password = serializers.CharField(max_length=255, required=True, write_only=True)
    username = serializers.CharField(max_length=255, required=True)
    zip_code = serializers.CharField(max_length=255, required=True)
    dob=serializers.DateField()
    state=serializers.CharField(max_length=20)
    city=serializers.CharField(max_length=20)
    casino_account_id=serializers.CharField(max_length=20)
    complete_address=serializers.CharField(max_length=100)
    phone_number=serializers.CharField(max_length=255)
    profile_pic=serializers.SerializerMethodField()
    user_id_proof=serializers.SerializerMethodField()
    first_name=serializers.CharField()
    last_name=serializers.CharField()
    email=serializers.EmailField(max_length=50)
    is_live_casino_enabled = serializers.SerializerMethodField()
    credit = serializers.SerializerMethodField()
    profit = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    user_hash = serializers.SerializerMethodField()
    is_betslip_bonus_enabled = serializers.SerializerMethodField()
    betslip_bonus_percentage = serializers.SerializerMethodField()
    is_account_cancelled = serializers.SerializerMethodField()
    max_spending_limit = serializers.SerializerMethodField()
    is_blackout = serializers.SerializerMethodField()
    blackout_expire_time = serializers.SerializerMethodField()
    bonus_amount = serializers.SerializerMethodField()
    referral_code = serializers.SerializerMethodField()
    referral_reward_percentage = serializers.SerializerMethodField()
    blackout_expire_hours = serializers.SerializerMethodField()
    remaining_spending_limit = serializers.SerializerMethodField()
    max_spending_limit_expire_time  = serializers.SerializerMethodField()
    is_max_spending_limit_set_by_admin = serializers.SerializerMethodField()
    affiliate_link = serializers.CharField(max_length=250)
    is_active = serializers.BooleanField(default=False)
    phone_verified = serializers.IntegerField()
    document_verified = serializers.IntegerField()
    is_verified = serializers.SerializerMethodField()
    no_of_deposit_counts = serializers.IntegerField()
    is_bonus_on_all_deposits = serializers.BooleanField(default=False)
    affliate_expire_date = serializers.DateTimeField()
    is_lifetime_affiliate = serializers.BooleanField(default=False)
    user_games  = serializers.SerializerMethodField()
    custom_spin = serializers.BooleanField(default=False)
    spin_wheel_balance = serializers.SerializerMethodField()
    main_balance = serializers.SerializerMethodField()
    withdrawal_balance = serializers.SerializerMethodField()
    cashapp = serializers.SerializerMethodField(default=[],required = False)
    unread_message_count  = serializers.SerializerMethodField()
    country_code = serializers.CharField(max_length=255,required=False)
    registered_tournament_count = serializers.SerializerMethodField()
    fortune_pandas_balance = serializers.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    mnet_url = serializers.SerializerMethodField()
    coinflow_state = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()


    @staticmethod
    def get_coinflow_state(obj):
        trans_layer ={
            'PNDG' : 0,
            'CRTD' : 1,
            'VRFD' : 2
        }
        return trans_layer[obj.coinflow_state]


    def get_country(self, obj):
        lang = self.context.get("lang_code", "en")
        if obj.country_obj:
            data = CountrySerializer(obj.country_obj, context={"lang": lang}).data
            return data
        logger.warning(f"User: {obj.username} is not using Country objs")
        return CountrySerializer(Country.objects.filter(code_cca2=obj.country).first(), context={"lang": lang}).data
    
    @staticmethod
    def get_cashapp(obj):
        if (obj.cashapp):
            obj.cashapp = json.loads(obj.cashapp)
            return obj.cashapp
        return []
    
    @staticmethod
    def get_profile_pic(obj):
        if(obj.profile_pic):
         return f'{settings.BE_DOMAIN}{obj.profile_pic.url}'
        return ""
         
    @staticmethod
    def get_user_id_proof(obj):
        if(obj.user_id_proof):
          return obj.user_id_proof.url
        return ""

    @staticmethod
    def get_max_spending_limit_expire_time(obj):
        responsible_gambling = ResponsibleGambling.objects.get_or_create(user=obj)[0]
        return responsible_gambling.max_spending_limit_expire_time

    @staticmethod
    def get_is_account_cancelled(obj):
        responsible_gambling = ResponsibleGambling.objects.get_or_create(user=obj)[0]
        return responsible_gambling.is_account_cancelled

    @staticmethod
    def get_max_spending_limit(obj):
        responsible_gambling = ResponsibleGambling.objects.get_or_create(user=obj)[0]
        return responsible_gambling.max_spending_limit

    @staticmethod
    def get_is_blackout(obj):
        responsible_gambling = ResponsibleGambling.objects.get_or_create(user=obj)[0]
        return responsible_gambling.is_blackout

    @staticmethod
    def get_is_max_spending_limit_set_by_admin(obj):
        responsible_gambling = ResponsibleGambling.objects.get_or_create(user=obj)[0]
        return responsible_gambling.is_max_spending_limit_set_by_admin
    
    @staticmethod
    def get_remaining_spending_limit(obj):
        responsible_gambling = ResponsibleGambling.objects.get_or_create(user=obj)[0]
        if responsible_gambling.max_spending_limit_expire_time and responsible_gambling.max_spending_limit_expire_time.astimezone(pytz.utc) < datetime.datetime.now(datetime.timezone.utc):
            responsible_gambling.daily_spendings = 0
            responsible_gambling.max_spending_limit = MAX_SPEND_AMOUNT
            responsible_gambling.max_spending_limit_expire_time = None
            responsible_gambling.save()
        return responsible_gambling.max_spending_limit - responsible_gambling.daily_spendings

    @staticmethod
    def get_blackout_expire_time(obj):
        return obj.responsible_gambling.blackout_expire_time

    @staticmethod
    def get_is_live_casino_enabled(obj):
        return obj.agent.is_live_casino_enabled

    @staticmethod
    def get_currency(obj):
        return obj.dealer.currency if obj.dealer else ""

    @staticmethod
    def get_referral_code(obj):
        referral_code = obj.referral_code if obj.referral_code else ""

        return referral_code

    @staticmethod
    def get_referral_reward_percentage(obj):
        try:
            referral_percentage = BonusPercentage.objects.filter(bonus_type="referral_bonus").first()
            if referral_percentage:
                referral_reward_percentage = referral_percentage.percentage
            referral_reward_percentage = 0
        except Exception as e:
            referral_reward_percentage = 0 
            print(e)
        return referral_reward_percentage

    @staticmethod
    def get_is_verified(obj):
        return obj.is_verified

    @staticmethod
    def get_is_betslip_bonus_enabled(obj):
        return obj.agent.is_betslip_bonus_enabled

    @staticmethod
    def get_betslip_bonus_percentage(obj):
        return obj.agent.betslip_bonus_percentage

    @staticmethod
    def get_credit(obj):
        balance = obj.balance
        return balance 

    @staticmethod
    def get_user_hash(obj):
        if not obj.callback_key:
            obj.callback_key = str(uuid.uuid4())
            obj.save()
        return obj.callback_key

    @staticmethod
    def get_profit(obj):
        return obj.pending

    @staticmethod
    def get_bonus_amount(obj):
        return obj.bonus_balance
    
    @staticmethod
    def get_spin_wheel_balance(obj):
        return obj.spin_wheel_balance
    
    @staticmethod
    def get_user_games(obj):
        user_games = UserGames.objects.filter(user=obj).values('game__code','game__id','username')
        return user_games
    
    @staticmethod
    def get_blackout_expire_hours(obj):
        return obj.responsible_gambling.blackout_expire_hours

    @staticmethod
    def get_main_balance(obj):
        return obj.balance + obj.bonus_balance + obj.fortune_pandas_balance

    @staticmethod
    def get_withdrawal_balance(obj):
        return obj.balance

    def create(self, validated_data):
        dealer = validated_data.pop("dealer", None)
        agent = validated_data.pop("agent", None)
        password = validated_data.pop("password", None)
        username = validated_data.pop("username", "").lower()
        user = Users.objects.create(
            password=password,
            username=username,
            role="player",
            is_active=True,
            is_staff=False,
            is_superuser=False,
            dealer=dealer,
            agent=agent,
        )
        user.ensure_country_obj()
        user.save()
        return user

    def validate(self, attrs):
        role = attrs.get("role", None)
        username = attrs.get("username", "").lower()
        dealer = attrs.get("dealer", None)
        agent = attrs.get("agent", None)

        if self.instance:
            if role:
                if self.instance.id == self.context["request"].user.id:
                    raise serializers.ValidationError(_("You can not change your role."))

            if username:
                if Users.objects.filter(username__iexact=username).exclude(id=self.instance.id).exists():
                    raise serializers.ValidationError(_("Username already exists."))
        else:
            if Users.objects.filter(username__iexact=username).exists():
                raise serializers.ValidationError(_("Username already exists."))

        return attrs

    @staticmethod
    def validate_password(password):
        password = make_password(password)

        return password
    
    @staticmethod
    def get_unread_message_count(obj):
        return ChatMessage.objects.filter(~Q(sender__role="player"), room__player=obj, is_read=False).count()
    
    @staticmethod
    def get_registered_tournament_count(obj):
        return obj.usertournament_set.count()
    
    @staticmethod
    def get_mnet_url(obj):
        password = urllib.parse.quote(obj.mnet_password)
        return f"{settings.MNET_PAYMENT_URL}?CustomerPIN={obj.username}&Password={password}"


class LoginSerializer(JSONWebTokenSerializer):
    def validate(self, attrs):
        from django.utils import timezone
        credentials = {"username": attrs.get("username").lower(), "password": attrs.get("password")}

        if all(credentials.values()):
            try:
                if not Users.objects.filter(username=attrs.get("username").lower()).exists():
                    raise serializers.ValidationError(
                        _(f"Invalid username")
                    )
                user = authenticate(**credentials)
                if user and user.is_currently_active:
                  if user.last_activity_time > timezone.now()-datetime.timedelta(minutes=15):  
                       raise serializers.ValidationError(
                                _(f" You are already logged in on another device")
                            )
                  
                if user:
                    # if user.role != "player":
                    #     raise serializers.ValidationError("Only player are allowed")
                    # Auth Token System
                    # token = Token.objects.get(user=user)
                    # if token:
                    #     token.delete()
                    #     token = Token.objects.create(user=user)
                    # user.last_login = datetime.datetime.now()
                    # user.save()
                    # return {"token": token.key, "user": user}
                    # jwt token system
           
                    if user.role =="player":
                        responsible_gambling = ResponsibleGambling.objects.get_or_create(user=user)[0]
                        if responsible_gambling.is_account_cancelled:
                            raise serializers.ValidationError(
                                _(f"You Account is in cancelled state. Please contact your admin.")
                            )
                    

                    code = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
                    user.username = code + user.username
                    payload = jwt_payload_handler(user)
                    token = jwt_encode_handler(payload)
                    user.username = user.username[6:]
                    existing_token = user.access_token
                    user.access_token = token
                    user.last_login = timezone.now()

                    user.save()
                    return {"token": token, "user": user}
                else:
                    msg = _("Incorrect password. Please try again.")
                    raise serializers.ValidationError(msg)
            except NotActiveUserException:
                msg = _("Your account has been deactivated. Please contact your agent.")
                raise serializers.ValidationError(msg)
            except DeactivatedUserException:
                msg = _("Your account is deactivated")
                raise serializers.ValidationError(msg)
        else:
            msg = _('Must include "{username_field}" and "password".')
            msg = msg.format(username_field=self.username_field)
            raise serializers.ValidationError(msg)


class SignUpSerializer(serializers.ModelSerializer):
    confirm_password = serializers.CharField(max_length=255, required=True, write_only=True)
    agent_id = serializers.CharField(max_length=5, required=False, write_only=False)
    affiliate_code = serializers.CharField(required=False, write_only=True)
    otp = serializers.CharField(required=False, write_only=True)

    class Meta:
        model = Player
        fields = ["username", "password", "confirm_password", "agent_id","first_name","last_name","email","state", 'city',"dob","phone_number","complete_address","zip_code","profile_pic","user_id_proof","affiliated_by","affiliate_code","affliate_expire_date",'otp',"country_code", 'country', 'country_obj', "applied_promo_code"]
        extra_kwargs = {
            "password": {"write_only": True},
            "confirm_password": {"write_only": True},
        }

    def validate(self, data):
        if not data.get("password") or not data.get("confirm_password"):
            raise serializers.ValidationError("Please enter a password and " "confirm it.")
        if data.get("password") != data.get("confirm_password"):
            raise serializers.ValidationError("Those passwords don't match.")

        if not data.get("username"):
            raise serializers.ValidationError("Username must not be null.")
        
        pattern = re.compile("[A-Za-z0-9]*$")
        if not pattern.fullmatch(data.get("username")):
            raise serializers.ValidationError("username must be alphanumeric")
        
        if Users.objects.filter(email=data.get("email")).exists(): 
            raise serializers.ValidationError("email already exists")
        
        if Users.objects.filter(username__iexact=data.get("username").lower()).exists():
            raise serializers.ValidationError("User already exists.")
        
        # if Users.objects.filter(phone_number=data.get("phone_number")).exists():
        #     raise serializers.ValidationError("Phone number already exists.")
        
        if data.get("applied_promo_code"): 
            promo_code = PromoCodes.objects.filter(promo_code=data.get("applied_promo_code"), bonus__bonus_type="welcome_bonus").first()
            if not promo_code:
                raise serializers.ValidationError("Invalid promo code.")
            elif promo_code.is_expired or promo_code.end_date < timezone.now().date():
                raise serializers.ValidationError("Promo code expired.")
        
        if data.get('otp'):
            checkotp = check_otp(data.get('otp'))
            if not checkotp:
                raise serializers.ValidationError("Please enter valid OTP.")
        else:
            raise serializers.ValidationError("Please provide valid OTP.")
   
        # if not data.get("zip_code"):
        #     raise serializers.ValidationError("Please enter Zip code.")
        
        # if len(str(data.get("zip_code"))) !=5:
        #     raise serializers.ValidationError("Please enter valid Zip code.")
        
        return data
        
        
    
    def create(self, validated_data):
        from django.utils import timezone
        if validated_data.get("agent_id"):
            agent_obj = Users.objects.filter(role="agent", pk=validated_data.get("agent_id")).first() 
            dealer_obj = Users.objects.filter(role="dealer", pk=agent_obj.dealer.id).first()
        else:
            agent_obj = Users.objects.filter(role="agent").first()
            dealer_obj = Users.objects.filter(role="dealer").first()
        affiliated_by=None
        if validated_data.get("affiliate_code"):
                key = str(settings.SECRET_KEY)[0:32]
                fernet_key = base64.urlsafe_b64encode(key.encode())
                fernet_obj = Fernet(fernet_key)
                user_id = fernet_obj.decrypt(bytes(validated_data.get("affiliate_code"), 'utf-8'))
                affiliated_by = Users.objects.filter(pk=user_id.decode()).first()
                print(affiliated_by.username)
        affiliate_code = validated_data.pop('affiliate_code', None)
        default_val = DefaultAffiliateValues.objects.first()
        admin = Admin.objects.filter().first()
        validated_data.pop("confirm_password")
        if validated_data.get('otp'):
            validated_data.pop("otp")
        player = super().create(validated_data)
        player.username = validated_data.get("username").lower()
        player.set_password(validated_data["password"])
        player.country_code = validated_data.pop("country_code", "")
        player.phone_number = validated_data.pop("phone_number", "")
        player.country = validated_data.pop("country", "")
        player.country_obj = validated_data.pop("country_obj", None)
        player.agent = agent_obj
        player.dealer = dealer_obj
        player.admin = admin
        player.role = "player"
        player.affiliated_by = affiliated_by
        player.is_staff = False
        player.is_superuser = False
        player.is_active = True
        player.last_activity_time = timezone.now()
        player.casino_account_id = create_casino_account_id()
        player.mnet_password = make_password(f"{validated_data.get('username')}{random.randint(1000, 9999)}")[:30]
        if default_val:
            player.affliate_expire_date = datetime.datetime.now() + datetime.timedelta(default_val.default_no_of_days)
            player.no_of_deposit_counts = default_val.default_no_of_deposit_counts
        else:
            player.no_of_deposit_counts = 1
            player.is_lifetime_affiliate = True

        # player.zip_code = int(validated_data.get("zip_code"))

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
        player.affiliation_percentage = DEFAULT_AFFILIATE_COMMISION_PERCENTAGE
        player.is_redeemable_amount = True
        # player.affliate_expire_date = datetime.datetime.now() + datetime.timedelta(days=DEFAULT_AFFILIATE_DURATION_IN_DAYS)
        # player.is_lifetime_affiliate = True
        player.save()
        #########################  Affiliate Changes End  ########################

        return player


class ChangePasswordSerializer(serializers.Serializer):
    user = None

    old_password = serializers.CharField(max_length=255, required=True)
    password = serializers.CharField(max_length=255, required=True)


class GetOtpSerializer(serializers.Serializer):
    def validate(self, attrs):
        validation_fields = ["phone_number", "country_code"]
        data = {}
        credentials = {
            "phone_number": self.context["request"].data["phone_number"],
            "country_code": self.context["request"].data["country_code"],
        }
        if all(credentials.values()):
            
            if len(credentials["phone_number"]) <= 15:
                data["phone_number"] = credentials["phone_number"]
            else:
                raise serializers.ValidationError("Phone number is not valid")
            if len(credentials["country_code"]) < 5:
                data["country_code"] = credentials["country_code"]
            else:
                raise serializers.ValidationError("Country code is not valid.")

            for field in validation_fields:
                if not credentials[field]:
                    raise serializers.ValidationError(f"{field} must not be null.")
            return data
        else:
            raise serializers.ValidationError("Must include all fields.")

class AffiliateSerializer(serializers.Serializer):
    
    username = serializers.CharField(max_length=255, required=True)
    first_name = serializers.CharField(max_length=255, required=True)
    last_name = serializers.CharField(max_length=255, required=True)
    created = serializers.DateTimeField()
    deposit_amount = serializers.SerializerMethodField()
    bonus_amount = serializers.SerializerMethodField()
    
    @staticmethod
    def get_deposit_amount(obj):
      
        transaction = Transactions.objects.filter(description__icontains=obj.username,journal_entry='bonus',description__contains=f'affiliate bonus').first()
        if transaction:
            return transaction.amount
        return 0
    
    @staticmethod
    def get_bonus_amount(obj):
        
        transaction = Transactions.objects.filter(description__icontains=obj.username,journal_entry='bonus',description__contains=f'affiliate bonus').first()
        if transaction:
            return transaction.bonus_amount
        return 0
            
# class OffmarketTransactionsSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = OffMarketTransactions
#         fields = '__all__'

class OffmarketTransactionsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    created = serializers.DateTimeField()
    amount = serializers.CharField()
    status = serializers.CharField()
    transaction_type = serializers.CharField(default="WITHDRAW")
    game_name_full = serializers.SerializerMethodField(allow_null=True)
    bonus = serializers.SerializerMethodField(allow_null=True,default=0)

    def get_game_name_full(self, obj):
        if hasattr(obj, 'code') and obj.code:
            game = OffMarketGames.objects.filter(code = obj.code).first()
            return game.title if game else None
        return obj.game_name_full
    
    def get_bonus(self,obj):
        if hasattr(obj, 'bonus') and obj.bonus:
            return float(obj.bonus)
        return 0.00

class SpintheWheelDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpintheWheelDetails
        fields = ('id', 'admin', 'value', 'code')

class TransactionsSerializer(serializers.ModelSerializer):
    bonus_amount = serializers.SerializerMethodField()
    journal_entry = serializers.SerializerMethodField()

    class Meta:
        model = Transactions 
        fields = ('id','user','journal_entry','created','status','description','bonus_type','bonus_amount',)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['bonus_type'] = representation['bonus_type'].replace('_', ' ') if representation.get('bonus_type') else "offmarket bonus"
        return representation
    
    @staticmethod
    def get_bonus_amount(obj):
        if hasattr(obj, "bonus_type"):
            return obj.bonus_amount
        # for offmarket transactions
        return obj.bonus
    
    @staticmethod
    def get_journal_entry(obj):
        return obj.journal_entry.capitalize()

class CashAppDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashAppDeatils 
        fields = ('id','name','is_active','approved_by','status')


class CashappQrSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashappQr
        fields = ['user_id','is_active','image',]


class MessageSerializer(serializers.ModelSerializer):
    message = serializers.SerializerMethodField()
    is_player_sender = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ("id", "type", "message", "sender", "sent_time", "is_file", "file","is_player_sender")

    
    def get_message(self, obj):
        return obj.file.name if obj.is_file else obj.message_text
    
    def get_is_player_sender(self, obj):
        if obj.sender and hasattr(obj.sender, 'role') and obj.sender.role == 'player':
            return True
        return False


class CmsPromotionSerializer(serializers.ModelSerializer):
    page_content = serializers.SerializerMethodField()

    class Meta:
        model = CmsPromotionDetails
        fields = ('title', 'page_content', 'more_info', 'url', "meta_description", "json_metadata")

    
    def get_page_content(self, obj):
        return obj.get_page_content()


class AdminBannerSerializer(serializers.ModelSerializer):
    banner_url = serializers.SerializerMethodField()
    
    class Meta:
        model = AdminBanner
        fields = ('banner_type', 'banner_category', 'button_text', 'redirect_url', 'banner_url', 'header', "content")
        
    def get_banner_url(self, obj):
        return f'{settings.BE_DOMAIN}{obj.url}'
    
        
class FortunePandasGameListSerializer(serializers.ModelSerializer):
    game_image = serializers.SerializerMethodField()
    
    class Meta:
        model = FortunePandasGameList
        fields = ['game_id', 'game_name', 'game_image', 'game_category']
    
    def get_game_image(self, obj):
        return f'{settings.BE_DOMAIN}{obj.game_image.url}'
    

class FortunePandasManagementGameListSerializer(serializers.ModelSerializer):
    game_id = serializers.CharField(source='game.game_id')
    game_name = serializers.CharField(source='game.game_name')
    game_category = serializers.CharField(source='game.game_category')
    game_image = serializers.SerializerMethodField()
    enabled = serializers.NullBooleanField()

    class Meta:
        model = FortunePandasGameManagement
        fields = ['admin', 'enabled', 'game_id', 'game_name', 'game_image', 'game_category']
    
    def get_game_image(self, obj):
        return f'{settings.BE_DOMAIN}{obj.game.game_image.url}'
