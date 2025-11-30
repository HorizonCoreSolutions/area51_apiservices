from datetime import datetime
from ckeditor.fields import RichTextField
from tinymce.models import HTMLField

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import UserManager as BuiltInUserManager
from djchoices import ChoiceItem, DjangoChoices
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import MinLengthValidator, MinValueValidator, MaxLengthValidator, RegexValidator
from decimal import Decimal
from django.conf import settings
from djchoices import ChoiceItem, DjangoChoices
from django.urls import reverse
from apps.core.models import AbstractBaseModel
from django.contrib.auth.models import PermissionsMixin
import requests

USER_ROLES = (
    ("player", _("Player")),
    ("agent", _("Agent")),
    ("dealer", _("Dealer")),
    ("manager", _("Manager")),
    ("admin", _("Admin")),
    ("superadmin", _("Super Admin")),
    ("staff", _("Staff"))
)

TIMEZONES = (
    ("EST", _("EST")),
)

QT_STATUS_CHOICES = (
    ("STAGING", _("STAGING")),
    ("PRODUCTION", _("PRODUCTION")),
    ("DISABLED", _("DISABLED")),
)

BANNER_TYPE_CHOICES = (
    ("HOMEPAGE", _("HOMEPAGE")),
    ("TOURNAMENT", _("TOURNAMENT")),
    ("BETSLIP", _("BETSLIP")),
)
BANNER_CATEGORY_CHOICES = (
    ("DESKTOP", _("DESKTOP")),
    ("MOBILE_RESPONSIVE", _("MOBILE RESPONSIVE")),
    ("MOBILE_APP", _("MOBILE APP")),
)


CONFIGS_CHOICES = (("transaction_delay", _("transaction delay")),)

CURRENCY_CHOICES = (
    ("EUR", _("EUR")),
    ("TRY", _("TRY")),
    ("RUB", _("RUB")),
    ("USD", _("USD")),
)


OTP_SERVICE_CHOICES = (
    ("twilio", _("Twilio OTP Service")),
)

BONUSES = (
    ("welcome_bonus", _("Welcome Bonus")),
    ("referral_bonus", _("Referral Bonus")),
    ("losing_bonus", _("Losing Bonus")),
    ("deposit_bonus", _("Deposit Bonus")),

)
FORM_CHOICES = (
    ("none", _("None")),
    ("contact-form", _("Contact Form")),
    )


DEFAULT_TRANSACTION_DELAY = 5
DEFAULT_AFFILIATE_COMMISION_PERCENTAGE = 40
DEFAULT_AFFILIATE_DURATION_IN_DAYS = 60
DEFAULT_AFFLIATE_DEPOSIT_COUNT = 1

MAX_SINGLE_BET = 250
MAX_SINGLE_BET_OTHER_SPORTS = 250
MIN_BET = 5
MAX_MULTIPLE_BET = 250
MAX_WIN_AMOUNT = 15000
MAX_SPEND_AMOUNT = 4000
MAX_ODD = 3000
MAX_BET_AMOUNT_PER_MATCH = 5000
MAX_SAME_BET_COUNT = 3
MAX_MULTI_TWO_EVENTS_AMOUNT = 150
MAX_MULTI_THREE_EVENTS_AMOUNT = 150
MAX_MULTI_FOUR_EVENTS_AMOUNT = 150
CASHOUT_PERCENTAGE = 0.24
CASHBACK_PERCENTAGE = 0.10
CASHBACK_TIME_LIMIT = 24
LIVE_CASINO_LIMIT = 100
PAYMENT_COEFFICIENT = 1
CASHBACK_CRON = "cashback_cron"
IS_CASHBACK_ENABLED = True
MAX_BET_ON_EVENT = 5
CASHBACK_PERCENTAGE = 0.00
CASHBACK_TIME_LIMIT = 24
MIN_AMOUNT_REQUIRED_FOR_JACKPOT = 50
JACKPOT_AMOUNT = 500.00000
JACKPOT_TIME_LIMIT = 5
BETSLIP_BONUS_PERCENTAGE = 10.00

# Constants
VERIFICATION_PENDING = 0
VERIFICATION_APPROVED = 1
VERIFICATION_PROCESSING = 2
VERIFICATION_REJECTED = -1
VERIFICATION_FAILED = -2
VERIFICATION_CANCELED = -3
VERIFICATION_EXPIRED = -4

# Choices tuple
VERIFICATION_STATUS_CHOICES = (
    (VERIFICATION_PENDING, 'Pending'),       # Neutral state
    (VERIFICATION_APPROVED, 'Approved'),     # Success
    (VERIFICATION_PROCESSING, 'Processing'), # Processing
    (VERIFICATION_REJECTED, 'Rejected'),     # Manual rejection
    (VERIFICATION_FAILED, 'Failed'),         # System or process failure
    (VERIFICATION_CANCELED, 'Canceled'),     # User/admin canceled
    (VERIFICATION_EXPIRED, 'Expired'),       # Timeout or expiration
)


EVENT_REGISTRATION = "registration"
EVENT_KYC = "kyc"

# Like im not sure this is the best way
BONUS_EVENTS = {
    EVENT_REGISTRATION: "User Registration",
    EVENT_KYC: "KYC validation",
}

BONUS_EVENTS_CHOICES = [(k, v) for k, v in BONUS_EVENTS.items()]


class CoinflowAuthState(DjangoChoices):
    pending = ChoiceItem('PNDG', 'pending')
    created = ChoiceItem('CRTD', 'created')
    verified = ChoiceItem('VRFD', 'verified')


def get_default_country():
    return Country.objects.get(code_cca2="US").id if Country.objects.filter(code_cca2="US").exists() else None


class UserManager(BuiltInUserManager):
    def create_superuser(self, username, password, **extra_fields):
        return Users.objects.create(
            password=make_password(password),
            username=username,
            role="superadmin",
            is_active=True,
            is_superuser=True,
            is_staff=True,
        )

    def get_queryset(self):
        return super().get_queryset()


class Permission(AbstractBaseModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    group = models.CharField(max_length=100)

    def __str__(self):
        return self.name


# Model for saving roles other than default available role
class Role(AbstractBaseModel):
    admin = models.ForeignKey("users.Users", on_delete=models.CASCADE, blank=False, related_name="roles")
    name = models.CharField(max_length=100, unique=True)
    permissions = models.ManyToManyField(Permission, related_name='roles')

    def __str__(self):
        return self.name

    def get_name(self):
        return self.name.title().replace("_", " ")

    def has_permissions(self, permission_code):
        return self.permissions.filter(code=permission_code).exists()


class Users(AbstractBaseUser, AbstractBaseModel, PermissionsMixin):
    is_staff = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=True)
    password = models.CharField(
        _("password"),
        max_length=128,
        blank=True,
        default=None,
        null=True,
        validators=[
            MinLengthValidator(limit_value=5, message="The password has to be at least 5 characters")
        ],
    )
    role = models.CharField(_("user type"), choices=USER_ROLES, max_length=30, null=False, blank=False)
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )
    username = models.CharField(
        _("username"),
        max_length=50,
        blank=True,
        default=None,
        null=True,
        unique=True,
        validators=[
            MinLengthValidator(limit_value=4, message="The username has to be at least 4 characters")
        ],
    )
    balance = models.DecimalField(
        _("balance"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )
    bonus_balance = models.DecimalField(
        _("Bonus balance"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )
    spin_wheel_balance = models.DecimalField(
        _("Spin Wheel balance"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )
    pending = models.DecimalField(
        _("pending"), max_digits=15, decimal_places=4, default=0.0000, null=False, blank=False
    )
    locked = models.DecimalField(
        _("locked"), max_digits=15, decimal_places=4, default=0.0000, null=False, blank=False
    )
    timezone = models.CharField(
        _("timezone"), choices=TIMEZONES, max_length=30, null=False, blank=False, default="EST"
    )
    agent = models.ForeignKey(
        "users.Users",
        on_delete=models.CASCADE,
        blank=False,
        default=None,
        null=True,
        related_name="user_agent",
    )
    dealer = models.ForeignKey(
        "users.Users",
        on_delete=models.CASCADE,
        blank=False,
        default=None,
        null=True,
        related_name="user_dealer",
    )
    admin = models.ForeignKey(
        "users.Users",
        on_delete=models.CASCADE,
        blank=False,
        default=None,
        null=True,
        related_name="user_admin",
    )
    staff = models.ForeignKey(
        "users.Users",
        on_delete=models.CASCADE,
        blank=False,
        default=None,
        null=True,
        related_name="user_staff",
    )
    # casino callback key to identify player
    callback_key = models.CharField(_("callback key"), max_length=255, default=None, null=True, blank=True)
    casino_account_id = models.CharField(_("casino account id"), max_length=255, default=None,null=True, blank=True)
    is_casino_enabled = models.BooleanField(_("is_casino_enabled"), null=False, default=True)
    is_live_casino_enabled = models.BooleanField(_("is_casino_enabled"), null=False, default=False)
    currency = models.CharField(
        _("currency"), max_length=250, choices=CURRENCY_CHOICES, null=False, default="USD"
    )
    system_id = models.CharField(_("system id"), max_length=250, null=True, blank=True, default=None)
    access_token = models.CharField(
        _("access token"), max_length=500, null=True, blank=True, default=None, unique=True
    )
    casino_token = models.CharField(
        _("casino token"), max_length=500, null=True, blank=True, default=None, unique=True
    )
    error_msg = models.CharField(_(""), max_length=250, null=True, blank=True, default=None)
    expires_in = models.DateTimeField(_("token expires time"), null=True, blank=True, default=None, unique=True)
    cashback_amount = models.DecimalField(
        _("cashback_amount"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )
    is_otp_enabled = models.BooleanField(_("OTP Service Status"), default=False)
    payment_token_expiry_in = models.DateTimeField(
        _("payment token expires time"), null=True, blank=True, default=None, unique=True)
    payment_access_token = models.CharField(
        _("payment access token"), max_length=500, null=True, blank=True, default=None, unique=True
    )

    is_welcome_bonus_enabled = models.BooleanField(_("Welcome Bonus Status"), default=False)
    is_referral_bonus_enabled = models.BooleanField(_("Referral Bonus Status"), default=False)
    is_losing_bonus_enabled = models.BooleanField(_("Losing Bonus Status"), default=False)
    is_jackpot_enabled = models.BooleanField(_("Jackpot Status"), null=False, default=False)
    country_code = models.CharField(_("country_code"), max_length=5, null=True, blank=True, default=None)
    is_betslip_bonus_enabled = models.BooleanField(_("is_betslip_bonus_enabled"), null=False, default=True)
    is_special_agent = models.BooleanField(_("Is Special Agent"), default=False, null=False, blank=False)
    is_special_agent_enabled = models.BooleanField(_("Special Agent"), default=False, null=False)
    betslip_bonus_percentage = models.FloatField(
        _("betslip bonus percentage"),
        default=BETSLIP_BONUS_PERCENTAGE,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    cashback_status = models.BooleanField(_("cashback_status"), null=False, default=IS_CASHBACK_ENABLED)
    cashback_percentage = models.DecimalField(_("Cashback Percentage"), decimal_places=2, default=CASHBACK_PERCENTAGE,
        max_digits=15, null=True, blank=True, validators=[MinValueValidator(Decimal("0.00"))])
    cashback_time_limit = models.IntegerField(_("Cashback Time Limit"), default=CASHBACK_TIME_LIMIT, null=True,
        blank=True)
    is_affiliate_player_enabled = models.BooleanField(_("Affiliate Player"), null=False, default=True)
    email = models.CharField(_("email"),max_length=500, null=True, default=None)
    dob = models.CharField(_("dob"),max_length=500, null=True, default=None)
    full_name = models.CharField(_("full_name"),max_length=350,default=None,null=True)
    last_name = models.CharField(_("last_name"),max_length=350,default=None,null=True)
    first_name = models.CharField(_("first_name"),max_length=350,default=None,null=True)
    state = models.CharField(_("state"),max_length=500, null=True, default='')
    city = models.CharField(_("city"),max_length=500, null=True, default='')
    complete_address = models.CharField(_("complete_address"),max_length=500, null=True, default=None)
    phone_number = models.CharField(_("phone number"), max_length=20, null=True, default=None)
                                    # validators=[
                                    #     RegexValidator(
                                    #         regex=r'^\+?1?\d{7,19}$',  # Regex for international phone numbers
                                    #         message="Phone number must be entered in the format: '+999999999'. Up to 19 digits allowed."
                                    #     )
                                    # ])
    profile_pic = models.FileField(upload_to='admin/profile_pic/',max_length=500, default=None,null=True)
    user_id_proof = models.FileField(upload_to='admin/user_id_proof/',default=None,null=True)
    # url = models.URLField(_("url"), max_length=250, null=True, blank=True, default=None)
    is_account_cancelled = models.BooleanField(default=False, null=True)
    max_spending_limit_expire_time = models.DateTimeField(default=None, null=True,blank=True)
    max_spending_limit = models.IntegerField(_("max spending limit for player"), default=MAX_SPEND_AMOUNT)
    is_blackout = models.BooleanField(default=False, null=True)
    blackout_expire_time = models.DateTimeField(
        _("user will not able to login/participate in paid games during the blackout time"),
        null=True,
        blank=True, default=None,
        unique=True)
    applied_promo_code = models.CharField(_("applied promo code"), max_length=50, null=True, default=None)
    is_deposit_bonus_enabled = models.BooleanField(_("Deposit Bonus Status"), default=False)
    referred_by = models.ForeignKey(
        "users.Users",
        on_delete=models.CASCADE,
        blank=True,
        default=None,
        null=True,
        related_name="user_referred_by",
    )
    referral_code = models.CharField(max_length=500, null=True, blank=True, default=None, unique=True)
    zip_code = models.IntegerField(_("zip_code"), null=True, blank=True, default=None)
    is_verified = models.BooleanField(default=False, null=True)
    document_verified = models.IntegerField(null=True, blank=True, default=VERIFICATION_PENDING, choices=VERIFICATION_STATUS_CHOICES)
    document_number = models.CharField(_("Document Number"), max_length=150, null=True, blank=True, default=None)
    phone_verified = models.IntegerField(null=True, blank=True, default=VERIFICATION_PENDING, choices=VERIFICATION_STATUS_CHOICES)
    coinflow_state = models.CharField(max_length=5, null=False, blank=False, default=str(CoinflowAuthState.pending), choices=CoinflowAuthState.choices)
    country = models.CharField(_("country"), max_length=100, default="US")
    country_obj = models.ForeignKey(
        "users.Country",
        on_delete=models.SET_NULL,
        blank=False,
        null=True,
        related_name="players",
    )
    affiliate_link = models.CharField(_("affiliate_link"), max_length=260, null=True, blank=True)
    affiliated_by = models.ForeignKey(
        "users.Users",
        on_delete=models.CASCADE,
        blank=True,
        default=None,
        null=True,
        related_name="user_affiliated_by",
    )
    affiliation_percentage = models.FloatField(_("affiliation_percentage"),default=40.00,null=True, blank=True)
    is_redeemable_amount = models.BooleanField(_("is_redeemable_amount"), null=False, default=False)
    is_coming_soon_enabled = models.BooleanField(default=False, null=True)
    coming_soon_scheduled = models.DateTimeField(default=None, null=True, blank=True)
    coming_soon_bonus = models.CharField(_("Coming Soon bonus"),max_length=500, null=True, blank=True, default=None)
    is_maintenance_mode_enabled = models.BooleanField(default=False, null=True)
    maintenance_mode_message = models.CharField(_("maintenance mode message"),max_length=500, null=True, blank=True, default=None)
    no_of_deposit_counts = models.IntegerField(_("no of deposit counts"), null=True, blank=True, default=DEFAULT_AFFLIATE_DEPOSIT_COUNT)
    is_bonus_on_all_deposits = models.BooleanField(default=False, null=True)
    affliate_expire_date = models.DateTimeField(default=None, null=True, blank=True)
    is_lifetime_affiliate = models.BooleanField(_("is_lifetime_affiliate"), null=False, default=False)
    wallet_address = models.CharField(_("Wallet Address"),max_length=500, null=True, blank=True, default=None)
    wallet_currency = models.CharField(_("Wallet Currency"),max_length=500, null=True, blank=True, default=None)
    is_staff_active = models.BooleanField(_("is_staff_active"), null=False, default=False)
    staff_currencies = JSONField(default=None, null=True, blank=True)
    cashtag = models.CharField(_("cashtag"),max_length=50,null=True, blank=True, default=None)
    current_session_token = models.CharField(max_length=100, blank=True, null=True)
    last_activity_time = models.DateTimeField(default=None, null=True, blank=True)
    is_currently_active = models.BooleanField(default=False, null=True, blank=True)
    alchemypay_address = models.CharField(max_length=100, blank=True, null=True)
    fortune_pandas_password = models.CharField(max_length=100, blank=True, null=True)
    fortune_pandas_api_key = models.CharField(max_length=100, blank=True, null=True)
    is_registered_in_fortune_pandas = models.BooleanField(default=False)
    fortune_pandas_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, null=False, blank=False)
    mnet_password = models.CharField(max_length=128,blank=True,null=True)
    mnet_payout_balance = models.DecimalField(
        _("payout balance"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )

    weekly_dl = models.DecimalField(
        max_digits=15, decimal_places=2, default=None, null=True, blank=False
    )
    daily_dl = models.DecimalField(
        max_digits=15, decimal_places=2, default=None, null=True, blank=False
    )

    VERIFICATION_FIELDS = {
        'document_verified' : 'Document/Passport/Government ID"',
        'phone_verified' : 'Phone number',
    }

    USERNAME_FIELD = "username"

    objects = UserManager()

    def get_is_verified(self):
        """
        Returns True if all given fields are exactly 1.
        """
        return all(getattr(self, field, None) == 1 for field in self.VERIFICATION_FIELDS)

    def set_is_verified(self, value: int):
        self.is_verified = (value == 1)

        for field in self.VERIFICATION_FIELDS:
            setattr(self, field, value)
        return

    def verification_steps_left(self):
        return [label for field, label in self.VERIFICATION_FIELDS.items() if getattr(self, field, None) != 1]

    def ensure_country_obj(self):
        if not self.country:
            self.country = 'US'

        if not self.country_obj and self.country:
            try:
                self.country_obj = Country.objects.get(code_cca2=self.country)
            except Country.DoesNotExist:
                print(f"User: {self.username} is not using Country objs")


    def clean(self):
        from django.core.exceptions import ValidationError
        import re
        patter=r'^\+?1?\d{7,19}$'
        match=re.match(patter, self.phone_number)
        if not match:
            raise ValidationError("Invalid phone number")

    def has_permissions(self, permission_code):
        role = Role.objects.filter(name=self.role).first()
        if role:
            return role.permissions.filter(code=permission_code).exists()
        return False

    def save(self, *args, **kwargs):
        self.is_verified = (self.phone_verified == 1 and self.document_verified == 1)

        if self.role == "player":
            self.is_staff = False
            self.is_superuser = False

        if self.role != "superadmin" and self.pk is None:
            self.system_id = self.set_system_id(self)

        self.modified = timezone.now()
        return super().save(*args, **kwargs)

    @staticmethod
    def set_system_id(user):
        if user.role:
            if user.role == "dealer":
                last_user = Dealer.objects.order_by("-id").first()
                system_id = "D"
            elif user.role == "agent":
                last_user = Agent.objects.order_by("-id").first()
                system_id = "S"
            elif user.role == "manager":
                last_user = Manager.objects.order_by("-id").first()
                system_id = "M"
            elif user.role == "admin":
                last_user = Admin.objects.exclude(id=user.id).order_by("-id").first()
                system_id = "A"
            else:
                last_user = Player.objects.order_by("-id").first()
                system_id = "P"

            start_year = 2020

            if user.role != "player":
                this_year = datetime.today().year
            else:
                this_year = user.agent.created.year

            system_id = system_id + str(this_year - start_year + 1) + "."

            if last_user:
                if last_user.system_id:
                    index_of_separator = last_user.system_id.find(".") + 1

                    if last_user.system_id[:index_of_separator] == system_id:
                        last_system_id_last_numbers = last_user.system_id[index_of_separator:]

                        new_system_id_last_numbers = int(last_system_id_last_numbers) + 1

                        new_system_id_last_numbers_length = len(str(new_system_id_last_numbers))

                        numbers_count_for_user = 4
                        if user.role == "player":
                            numbers_count_for_user = 6

                        while new_system_id_last_numbers_length < numbers_count_for_user:
                            system_id = system_id + "0"
                            new_system_id_last_numbers_length = new_system_id_last_numbers_length + 1

                        system_id = system_id + str(new_system_id_last_numbers)
                    else:
                        if user.role != "player":
                            system_id = system_id + "0001"
                        else:
                            system_id = system_id + "000001"
                else:
                    if user.role != "player":
                        system_id = system_id + "0001"
                    else:
                        system_id = system_id + "000001"
            else:
                if user.role != "player":
                    system_id = system_id + "0001"
                else:
                    system_id = system_id + "000001"

            return system_id
        return None

    def __getattribute__(self, name):
        if name == "is_active":
            value = super().__getattribute__(name)
            country = super().__getattribute__("country_obj")
            country = country.enabled if country else True
            return value and country
        return super().__getattribute__(name)

class ResponsibleGambling(AbstractBaseModel):
    user = models.OneToOneField(Users, on_delete=models.CASCADE,primary_key=True, related_name="responsible_gambling")
    max_spending_limit = models.IntegerField(_("max spending limit for player"), default=MAX_SPEND_AMOUNT)
    daily_spendings = models.IntegerField(default=0)
    max_spending_limit_expire_time = models.DateTimeField(default=None, null=True,blank=True)
    is_max_spending_limit_set_by_admin  = models.BooleanField(default=False)
    is_account_cancelled = models.BooleanField(default=False, null=True)
    is_blackout = models.BooleanField(default=False, null=True)
    blackout_expire_time = models.DateTimeField(
        _("user will not able to login/participate in paid games during the blackout time"),
        null=True,
        blank=True, default=None)
    blackout_expire_hours = models.IntegerField(_("blackout expire hours"), null=True,blank=True)


class Country(AbstractBaseModel):
    name = models.CharField(max_length=255)
    translated_name = JSONField(default=dict)  # Store translations
    code_cca2 = models.CharField(max_length=10, unique=True)
    code_ccn3 = models.CharField(max_length=10, unique=True)
    code_cca3 = models.CharField(max_length=10, unique=True)
    flag = models.CharField(max_length=10)  # Stores emoji flag
    flag_url = models.CharField(max_length=255)
    timezone = models.CharField(max_length=50)
    currency_code = models.CharField(max_length=10)
    currency_name = models.CharField(max_length=255)
    currency_symbol = models.CharField(max_length=10)

    enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class BlackListedToken(models.Model):
    token = models.CharField(max_length=500)
    user = models.ForeignKey(Users, related_name="token_user", on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("token", "user")


class UserBets(AbstractBaseModel):
    # cash_in = models.BigIntegerField(default=0)
    # cash_out = models.BigIntegerField(default=0)
    cash_in = models.FloatField(default=0.0)
    cash_out = models.FloatField(default=0.0)
    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False, default=None, null=True)
    date = models.DateTimeField(default=None, null=True, blank=False)
    game_id = models.BigIntegerField(default=None, null=True, blank=False)
    balance = models.FloatField(default=0.0)




class PlayerManager(models.Manager):
    def get_queryset(self):
        return super(PlayerManager, self).get_queryset().filter(role="player")


class Player(Users):
    objects = PlayerManager()

    class Meta:
        proxy = True


class AgentManager(models.Manager):
    def get_queryset(self):
        return super(AgentManager, self).get_queryset().filter(role="agent")


class Agent(Users):
    objects = AgentManager()

    class Meta:
        proxy = True


class AdminManager(models.Manager):
    def get_queryset(self):
        return super(AdminManager, self).get_queryset().filter(role="admin")


class Admin(Users):
    objects = AdminManager()

    class Meta:
        proxy = True


class DealerManager(models.Manager):
    def get_queryset(self):
        return super(DealerManager, self).get_queryset().filter(role="dealer")


class Dealer(Users):
    objects = DealerManager()

    class Meta:
        proxy = True


class ManagerManager(models.Manager):
    def get_queryset(self):
        return super(ManagerManager, self).get_queryset().filter(role="manager")


class Manager(Users):
    objects = ManagerManager()

    class Meta:
        proxy = True


class SuperAdminManager(models.Manager):
    def get_queryset(self):
        return super(SuperAdminManager, self).get_queryset().filter(role="superadmin")


class SuperAdmin(Users):
    objects = SuperAdminManager()

    class Meta:
        proxy = True


class Configs(AbstractBaseModel):
    name = models.CharField(_("config name"), max_length=250, choices=CONFIGS_CHOICES, unique=True)
    value = models.IntegerField(_("config value"), default=DEFAULT_TRANSACTION_DELAY)



class CronInfo(AbstractBaseModel):
    agent = models.OneToOneField(Users, on_delete=models.CASCADE, default=None, blank=True, null=True)
    last_run_time = models.DateTimeField(default=None, blank=True, null=True)
    cron_name = models.CharField(_("cron name"), max_length=250, null=True, blank=True, default=CASHBACK_CRON)


class SuperAdminSetting(models.Model):
    is_bet_disabled = models.BooleanField(default=False, null=True)


class AccountDetails(AbstractBaseModel):
    user = models.OneToOneField(Users, on_delete=models.CASCADE, primary_key=True)
    access_token = models.CharField(_("access_token"), max_length=250, null=True, blank=True)
    public_key = models.CharField(_("public_key"), max_length=250, null=True, blank=True)


class OtpCredsInfo(AbstractBaseModel):
    service_name = models.CharField(_("OTP Service Name"), max_length=250, null=True,
        blank=True, default=None, choices=OTP_SERVICE_CHOICES
    )
    service_creds = models.BinaryField(_("OTP Service Creds"), null=True, blank=True, default=None)
    admin = models.ForeignKey(Users, on_delete=models.CASCADE, default=None, null=True)

    class Meta:
        unique_together = ('admin', 'service_name')


class BonusPercentage(AbstractBaseModel):
    dealer = models.ForeignKey(Users, on_delete=models.CASCADE, default=None, null=True)
    percentage = models.FloatField(_("percentage"), default=None, null=True, blank=True, validators=[MinValueValidator(Decimal("0.00"))])
    bonus_type = models.CharField(_("bonus type"), max_length=40, choices=BONUSES, null=True, blank=True, default="welcome_bonus")
    deposit_bonus_limit = models.IntegerField(_("deposit_bonus"), default=1, null=False, blank=False, validators=[MinValueValidator(1)])
    referral_bonus_limit = models.IntegerField(_("referral_bonus"), default=1, null=False, blank=False, validators=[MinValueValidator(1)])
    welcome_bonus_limit = models.IntegerField(_("welcome_bonus"), default=1, null=False, blank=False, validators=[MinValueValidator(1)])
    losing_bonus_limit = models.IntegerField(_("losing_bonus"), default=1, null=False, blank=False, validators=[MinValueValidator(1)])
    bet_bonus_limit = models.IntegerField(_("bet_bonus"), default=1, null=False, blank=False, validators=[MinValueValidator(1)])
    bet_bonus_per_day_limit = models.IntegerField(_("bet_bonus_per_day_limit"), default=1, null=False, blank=False, validators=[MinValueValidator(1)])
    deposit_bonus_per_day_limit = models.IntegerField(_("deposit_bonus_per_day_limit"), default=1, null=False, blank=False, validators=[MinValueValidator(1)])

    class Meta:
        unique_together = ("dealer", "bonus_type")


class PromoCodes(AbstractBaseModel):

    # Currently used for checking when the bonus will be given for signup bonuses
    class BonusDistributionMethod(DjangoChoices):
        deposit = ChoiceItem("deposit", "Deposit")
        mixture = ChoiceItem("mixture", "Mixture")
        instant = ChoiceItem("instant", "Instant")

    dealer = models.ForeignKey(Users, on_delete=models.CASCADE, default=None, null=True)
    bonus = models.ForeignKey(BonusPercentage, on_delete=models.CASCADE, default=None, null=True)
    # When the Bonus percentage is automated, this is going to be used as a promo event_type
    promo_code = models.CharField(_("Promo Code"), max_length=50, null=True, blank=True, default=None)
    start_date = models.DateField(_("Start Date"), auto_now=False, null=True, blank=True, default=None)
    end_date = models.DateField(_("End Date"), auto_now=False, null=True, blank=True, default=None)
    # When the Bonus percentage is automated, this is going to be used as a promo event_type
    # When 1 it is GC, when it is SC
    # Both of this should be treated as integers.
    bonus_percentage = models.FloatField(
        _("bonus percentage"), default=None, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))]
    )
    gold_percentage = models.FloatField(
        _("gold percentage"), default=None, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))]
    )
    is_expired = models.BooleanField(_("Is Expired"), default=False)
    usage_limit = models.IntegerField(_("usage limit"), default=1, null=False, blank=False, validators=[MinValueValidator(1)])
    limit_per_user = models.IntegerField(_("User usage limit"), default=1, null=False, blank=False, validators=[MinValueValidator(1)])
    max_bonus_limit = models.IntegerField(_("Max bonus amount limit"), default=1, null=False, blank=False, validators=[MinValueValidator(1)])
    bonus_distribution_method = models.CharField(max_length=100, choices=BonusDistributionMethod,blank=True, null=True,default=BonusDistributionMethod.deposit)
    instant_bonus_amount = models.DecimalField(
        _("Instant Bonus Amount"), max_digits=15, decimal_places=2,
        default=0.00, null=False, blank=False
    )
    gold_bonus = models.DecimalField(
        _("Gold Coins Bonus Amount"), max_digits=15, decimal_places=2,
        default=0.00, null=False, blank=False
    )

    class Meta:
        unique_together = ("bonus", "promo_code", "start_date", "end_date")


class PromoCodesLogs(AbstractBaseModel):
    promocode = models.ForeignKey(PromoCodes, on_delete=models.CASCADE, default=None, null=True)
    date = models.DateTimeField(_("Date"), null=False, blank=False, editable=False)
    # When none, means user has claimed it tho has not used it
    transfer = models.DecimalField(
        _("transfer"), max_digits=15, decimal_places=4, default=Decimal('0.0000'), null=True, blank=True
    )
    transfer_gold = models.DecimalField(
        _("transfer"), max_digits=15, decimal_places=4, default=Decimal('0.0000'), null=True, blank=True
    )
    log = models.CharField(max_length=2048, null=False, blank=False, editable=False)
    user = models.ForeignKey(Users, on_delete=models.CASCADE, default=None, null=True)

    transaction = models.OneToOneField(
        "apps.bets.Transactions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="promo_log"
    )


class AdminBanner(AbstractBaseModel):
    admin = models.ForeignKey(Users, on_delete=models.CASCADE, default=None, null=True)
    title = models.CharField(_("title"), max_length=250, null=True, blank=True, default=None)
    banner = models.FileField(upload_to='admin/banner/')
    banner_category = models.CharField(_("Banner Category"), max_length=100,null=True, blank=True,default='DESKTOP',choices=BANNER_CATEGORY_CHOICES)
    banner_type = models.CharField(_("banner type"), max_length=100, null=False, blank=False, default='HOMEPAGE', choices=BANNER_TYPE_CHOICES)
    banner_thumbnail = models.FileField(upload_to='admin/banner/thumbnail/', null=True, blank=True)
    redirect_url = models.URLField(_("redirect url"), max_length=250, null=True, blank=True, default=None)
    url = models.URLField(_("url"), max_length=250, null=True, blank=True, default=None)
    clicks = models.IntegerField(_("clicks"), default=0, null=True, blank=True)
    content = HTMLField(blank=True, null=True,max_length=2000)
    header = HTMLField(blank=True, null=True,max_length=2000)
    button_text = models.CharField(_("button text"), max_length=250, null=True, blank=True, default="Play Now")

class CmsAboutDetails(AbstractBaseModel):
    title = models.CharField(max_length=250, null=True, blank=True, default=None)
    more_info = models.CharField(max_length=250, null=True, blank=True, default=None)
    banner = models.FileField(upload_to='about/banner/', null=True, blank=True, default=None)
    banner_thumbnail = models.FileField(upload_to='about/banner/thumbnail/', null=True, blank=True)
    page_content = RichTextField(blank=True, null=True)


class CmsContactDetails(AbstractBaseModel):
    first_name = models.CharField(max_length=100, null=True, blank=True, default=None)
    last_name = models.CharField(max_length=100, null=True, blank=True, default=None)
    email = models.CharField(max_length=100, null=True, blank=True, default=None)
    phone = models.CharField(max_length=100, null=True, blank=True, default=None)
    query = models.CharField(max_length=300, null=True, blank=True, default=None)
    status = models.CharField(max_length=50, null=True, blank=True, default="Active")


class CmsPromotions(AbstractBaseModel):
    TYPE_CHOICES = [
        ("toaster", "Toaster"),
        ("page_blocker", "Page Blocker"),
    ]

    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    url = models.URLField(max_length=250, blank=True, default="")
    title = HTMLField(max_length=350, blank=True, default="")
    content = HTMLField(max_length=5000) 
    image = models.ImageField(upload_to="promotion/images/", blank=True, null=True)
    button_text = models.CharField(max_length=150, blank=True, default="")

    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    disabled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.get_type_display()} - {self.title}"

    @property
    def is_active(self):
        from django.utils import timezone
        now = timezone.now()
        return (not self.disabled) and (self.start_date <= now <= self.end_date)


class CmsPromotionDetails(AbstractBaseModel):
    admin = models.ForeignKey(Users, on_delete=models.CASCADE, default=None, null=True)
    title = models.CharField(max_length=250, null=True, blank=True, default=None)
    more_info = models.CharField(max_length=250, null=True, blank=True, default=None)
    page = models.FileField(upload_to='promotion/page/', null=True, blank=True, default=None)
    page_thumbnail = models.FileField(upload_to='promotion/page/thumbnail/', null=True, blank=True)
    page_content = HTMLField(blank=True, null=True,max_length=2000,)
    url = models.URLField(_("url"), max_length=250, null=True, blank=True, default=None)
    meta_description = models.TextField(null=True, blank=True)
    json_metadata = models.TextField(null=True, blank=True)

    def get_page_content(self):
        return self.page_content.replace('../../media/', f"{settings.BE_DOMAIN}/media/")


@receiver(models.signals.post_delete, sender=CmsPromotionDetails)
def remove_file_from_s3(sender, instance, using, **kwargs):
    instance.page.delete(save=False)
    instance.page_thumbnail.delete(save=False)


@receiver(models.signals.post_save, sender=CmsPromotionDetails)
def save_promotion_page_url(sender,instance,*args, **kwargs):
    CmsPromotionDetails.objects.filter(id=instance.id).update(url=f'{settings.BE_DOMAIN}{instance.page.url}')



class CrmDetails(AbstractBaseModel):
    subject = models.CharField(max_length=250, null=True, blank=True, default=None)
    category = models.CharField(max_length=250, null=True, blank=True, default=None)
    scheduled_at = models.DateTimeField()
    content = models.CharField(max_length=2000, null=True, blank=True, default=None)
    status = models.CharField(max_length=50, null=True, blank=True, default=None)
    emails = models.CharField(max_length=2000, null=True, blank=True, default=None)

    def get_crm_content(self):
        return self.content.replace('../../media/', f"{settings.BE_DOMAIN}/media/")


@receiver(models.signals.post_delete, sender=AdminBanner)
def remove_file_from_s3(sender, instance, using, **kwargs):
    instance.banner.delete(save=False)
    instance.banner_thumbnail.delete(save=False)


@receiver(models.signals.post_save, sender=AdminBanner)
def save_banner_url(sender,instance,*args, **kwargs):
    AdminBanner.objects.filter(id=instance.id).update(url=instance.banner.url)


class CmsPrivacyPolicy(AbstractBaseModel):
    title = models.CharField(max_length=250, null=True, blank=True, default=None)
    more_info = models.CharField(max_length=250, null=True, blank=True, default=None)
    banner = models.FileField(upload_to='privacypolicy/banner/', null=True, blank=True, default=None)
    banner_thumbnail = models.FileField(upload_to='privacypolicy/banner/thumbnail/', null=True, blank=True)
    page_content = RichTextField(blank=True, null=True)


class CmsFAQ(AbstractBaseModel):
    title = models.CharField(max_length=250, null=True, blank=True, default=None)
    more_info = models.CharField(max_length=250, null=True, blank=True, default=None)
    banner = models.FileField(upload_to='faq/banner/', null=True, blank=True, default=None)
    banner_thumbnail = models.FileField(upload_to='faq/banner/thumbnail/', null=True, blank=True)
    page_content = RichTextField(blank=True, null=True)


class TermsConditinos(AbstractBaseModel):
    title = models.CharField(max_length=250, null=True, blank=True, default=None)
    more_info = models.CharField(max_length=250, null=True, blank=True, default=None)
    banner = models.FileField(upload_to='termscondition/banner/', null=True, blank=True, default=None)
    banner_thumbnail = models.FileField(upload_to='termscondition/banner/thumbnail/', null=True, blank=True)
    page_content = RichTextField(blank=True, null=True)


class CookiePolicy(AbstractBaseModel):
    title = models.CharField(max_length=250, null=True, blank=True, default=None)
    more_info = models.CharField(max_length=250, null=True, blank=True, default=None)
    banner = models.FileField(upload_to='cookiepolicy/banner/', null=True, blank=True, default=None)
    banner_thumbnail = models.FileField(upload_to='cookiepolicy/banner/thumbnail/', null=True, blank=True)
    page_content = RichTextField(blank=True, null=True)


class Introduction(AbstractBaseModel):
    title = models.CharField(max_length=250, null=True, blank=True, default=None)
    more_info = models.CharField(max_length=250, null=True, blank=True, default=None)
    banner = models.FileField(upload_to='introduction/banner/', null=True, blank=True, default=None)
    banner_thumbnail = models.FileField(upload_to='introduction/banner/thumbnail/', null=True, blank=True)
    page_content = RichTextField(blank=True, null=True)


class SettingsLimits(AbstractBaseModel):
    title = models.CharField(max_length=250, null=True, blank=True, default=None)
    more_info = models.CharField(max_length=250, null=True, blank=True, default=None)
    banner = models.FileField(upload_to='settingslimits/banner/', null=True, blank=True, default=None)
    banner_thumbnail = models.FileField(upload_to='settingslimits/banner/thumbnail/', null=True, blank=True)
    page_content = RichTextField(blank=True, null=True)


class SocialLink(AbstractBaseModel):
    admin = models.ForeignKey(Users, on_delete=models.CASCADE, default=None, null=True)
    title = models.CharField(max_length=250, null=True, blank=True, default=None)
    logo = models.FileField(upload_to='social/logo/', null=True, blank=True, default=None)
    url = models.URLField(_("url"), max_length=250, null=True, blank=True, default=None)


@receiver(models.signals.post_delete, sender=SocialLink)
def remove_file_from_s3(sender, instance, using, **kwargs):
    instance.logo.delete(save=False)


class CmsPages(AbstractBaseModel):
    class PreviewType(DjangoChoices):
        none = ChoiceItem("none", "None")
        single = ChoiceItem("single", "SINGLE")
        slider = ChoiceItem("slider", "SLIDER")

    title = models.CharField(max_length=250, null=False, blank=False, unique=True)
    more_info = models.CharField(max_length=250, null=True, blank=True, default=None)
    page = models.FileField(upload_to='about/page/', null=True, blank=True, default=None)
    page_thumbnail = models.FileField(upload_to='about/page/thumbnail/', null=True, blank=True)
    page_content = HTMLField(blank=True, null=True)
    slug = models.CharField(max_length=250, null=True, unique=True, blank=True)   
    is_form = models.BooleanField(_("is_form"), default=False)
    form_name = models.CharField(max_length=250, choices=FORM_CHOICES ,null=True, blank=True, default=None)
    is_redirect = models.BooleanField(_("is_redirect"), default=False)
    redirect_url = models.URLField(_("redirect url"), max_length=250, null=True, blank=True, default=None)
    is_page = models.BooleanField(_("is_page"), default=True)
    meta_description = models.TextField(null=True, blank=True)
    json_metadata = models.TextField(null=True, blank=True)
    preview_type = models.CharField(max_length=100, choices=PreviewType, blank=True, null=True, default=PreviewType.none)
    hidden = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        self.slug = self.title.lower().replace(" " ,"_")
        return super().save(*args, **kwargs)

    def get_page_content(self):
        return self.page_content.replace('../../media/', f"{settings.BE_DOMAIN}/media/")


class PageMedia(AbstractBaseModel):
    page =  models.ForeignKey(CmsPages, on_delete=models.CASCADE, related_name="media")
    media = models.FileField(upload_to='about/page/', null=True, blank=True, default=None)

    @classmethod
    def bulk_delete_media(cls, instances):
        for instance in instances:
            if instance.media:
                instance.media.delete(save=False)

        cls.objects.filter(id__in=list(instances.values_list("id", flat=True))).delete()

class FooterCategory(AbstractBaseModel):
    name = models.CharField(max_length=250, null=True, blank=True,unique=True, default=None)
    slug = models.CharField(max_length=250, null=True, blank=True, default=None)
    position = models.IntegerField(_("position"), null=True, blank=True)

    def save(self, *args, **kwargs):
        self.slug = self.name.lower().replace(" " ,"_")
        return super().save(*args, **kwargs)


class FooterPages(AbstractBaseModel):
    category = models.ForeignKey(FooterCategory, on_delete=models.CASCADE, default=None, null=True)
    pages = models.ForeignKey(CmsPages,  on_delete=models.CASCADE, default=None, null=True)


class PlayerBettingLimit(AbstractBaseModel):
    player = models.OneToOneField(Users, on_delete=models.CASCADE)
    amount = models.FloatField(_("amount"), default=None, validators=[MinValueValidator(Decimal("0.00"))])
    utilized_amount = models.FloatField(default=0.0)


class SMSDetails(AbstractBaseModel):
    subject = models.CharField(max_length=250, null=True, blank=True, default=None)
    phone_number = models.CharField(_("phone number"), max_length=300, null=True, default=None)
    scheduled_at = models.DateTimeField()
    content = models.CharField(max_length=2000, null=True, blank=True, default=None)
    status = models.CharField(max_length=50, null=True, blank=True, default=None)


class AdminAdsBanner(AbstractBaseModel):
    admin = models.ForeignKey(Users, on_delete=models.CASCADE, default=None, null=True)
    title = models.CharField(_("title"), max_length=250, null=True, blank=True, default=None)
    banner = models.FileField(upload_to='admin/banner/')
    banner_category = models.CharField(_("Banner Category"), max_length=100,null=True, blank=True,default='DESKTOP',choices=BANNER_CATEGORY_CHOICES)
    banner_type = models.CharField(_("banner type"), max_length=100, null=False, blank=False, default='HOMEPAGE', choices=BANNER_TYPE_CHOICES)
    banner_thumbnail = models.FileField(upload_to='admin/banner/thumbnail/', null=True, blank=True)
    redirect_url = models.URLField(_("redirect url"), max_length=250, null=True, blank=True, default=None)
    url = models.URLField(_("url"), max_length=250, null=True, blank=True, default=None)
    clicks = models.IntegerField(_("clicks"), default=0, null=True, blank=True)


@receiver(models.signals.post_delete, sender=AdminAdsBanner)
def remove_file_from_s3(sender, instance, using, **kwargs):
    instance.banner.delete(save=False)
    instance.banner_thumbnail.delete(save=False)


@receiver(models.signals.post_save, sender=AdminAdsBanner)
def save_adsbanner_url(sender,instance,*args, **kwargs):
    AdminAdsBanner.objects.filter(id=instance.id).update(url=instance.banner.url)

class UserNotes(AbstractBaseModel):
    user = models.ForeignKey(Users, on_delete=models.CASCADE)
    notes = models.TextField(max_length=500, blank=False, null=False)
    admin = models.ForeignKey(Users, on_delete=models.CASCADE, related_name='notes')


class AffiliateRequests(AbstractBaseModel):

    class StatusType(DjangoChoices):
        pending = ChoiceItem("pending", "PENDING")
        in_process = ChoiceItem("cancelled", "CANCELLED")
        done = ChoiceItem("approved", "APPROVED")

    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False, null=True)
    no_of_days = models.IntegerField()
    no_of_deposit_counts = models.IntegerField()
    is_bonus_on_all_deposits = models.BooleanField(default=False, null=True)
    is_lifetime_affiliate = models.BooleanField(default=False, null=True)
    status = models.CharField(max_length=100, choices=StatusType,blank=True, null=True,default=StatusType.pending)


class DefaultAffiliateValues(AbstractBaseModel):

    default_no_of_days = models.IntegerField(default=0)
    default_no_of_deposit_counts = models.IntegerField(default=0)
    default_affiliation_percentage = models.FloatField(_("affiliation_percentage"),default=0,null=True, blank=True)


class StaffManager(models.Manager):
    def get_queryset(self):
        return super(StaffManager, self).get_queryset().filter(role="staff")


class Staff(Users):
    objects = StaffManager()

    class Meta:
        proxy = True


class ChatRoom(AbstractBaseModel):
    name = models.CharField(max_length=255)
    player = models.ForeignKey(Users, on_delete=models.CASCADE, default=None, null=True, blank=True, related_name="chat")
    pick_by = models.ForeignKey(Users, on_delete=models.CASCADE, default=None, null=True, blank=True)

    # other fields for the chat room (e.g. description, members, etc.)


class ChatMessage(AbstractBaseModel):
    class MessageType(DjangoChoices):
        message = ChoiceItem('message', 'Message')
        offmarket_signup = ChoiceItem('offmarket_signup', 'Offmarket Signup')
        join = ChoiceItem('join', 'Join')

    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(Users, on_delete=models.CASCADE)
    message_text = models.TextField()
    sent_time = models.DateTimeField(auto_now_add=True)
    is_file = models.BooleanField(default=False)
    file = models.FileField(upload_to='csr/chats/',null=True,blank=True,default=None,max_length=500)
    is_tip = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)
    type = models.CharField(null=True, blank=True, choices = MessageType.choices, max_length=500)
    tip_user = models.ForeignKey(Users, on_delete=models.CASCADE,related_name="received_by_tip",default=None, null=True, blank=True)
    is_comment = models.BooleanField(default=False)


    class Meta:
        ordering = ['-sent_time']

    def __str__(self):
        return f"{self.sender.username} - {self.message_text}"


class ChatHistory(AbstractBaseModel):
    player = models.ForeignKey(Player, on_delete=models.CASCADE,blank=False, null=True, related_name='player_chathistory')
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE,blank=False, null=True, related_name='staff_chathistory')
    chats = JSONField(default=None, null=True, blank=True)
    comment = models.CharField(_("Comment"), max_length=1000, null=True, blank=True, default=None)
    tip_amount = models.DecimalField(
        _("cashback_amount"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )


class Queue(AbstractBaseModel):
    user = models.ForeignKey(Users, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False, null=True, blank=True)
    is_remove = models.BooleanField(default=False, null=True, blank=True)
    pick_by = models.ForeignKey(Users, on_delete=models.CASCADE,related_name="staff_user",default=None, null=True,blank=True)


class OffMarketGames(AbstractBaseModel):
    title = models.CharField(max_length=100)
    url = models.FileField(upload_to='admin/offmarket_games/', max_length=500, default=None, null=True)
    code = models.CharField(max_length=100, unique=True, null=True, blank=True)
    bonus_percentage = models.FloatField(
        _("game bonus percentage"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    game_status = models.BooleanField(default=True)
    coming_soon = models.BooleanField(default=False)
    is_api_prefix = models.BooleanField(default=False)
    download_url = models.URLField(_("download url"), max_length=250, null=True, blank=True, default=None)
    game_user = models.CharField(max_length=15, null=True, blank=True)
    game_pass = models.CharField(max_length=15, null=True, blank=True)


class UserGames(AbstractBaseModel):
    user = models.ForeignKey(
        Users,
        on_delete=models.CASCADE, 
        related_name="games",
    )
    game = models.ForeignKey(
        OffMarketGames,
        on_delete=models.CASCADE,  
        related_name="users",
    )
    username = models.CharField(
        _("username"),
        max_length=50,
        blank=True,
        default=None,
        null=True,
        validators=[
            MaxLengthValidator(limit_value=5, message="The username cannot exceed 5 characters")
        ],
    )
    password = models.CharField(
        _("password"),
        max_length=128,
        blank=True,
        default=None,
        null=True,
        validators=[
            MinLengthValidator(limit_value=5, message="The password has to be at least 5 characters")
        ],
    )




class OffMarketTransactions(AbstractBaseModel):
    class TransactionStatus(DjangoChoices):
        failed = ChoiceItem('FAILED', 'failed')
        success = ChoiceItem('SUCCESS', 'success')
        pending = ChoiceItem('PENDING', 'pending')


    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False)
    amount = models.DecimalField(
        _("amount"), max_digits=15, decimal_places=4, default=0.0000, null=False, blank=False
    )
    journal_entry = models.CharField(
        _("journal_entry"), max_length=500, null=False, blank=False, default=None
    )
    status = models.CharField(
        _("status"),max_length=500, null=False, blank=False, default=None
    )
    description = models.CharField(_("description"), max_length=500, null=False, blank=False, default=None)
    txn_id = models.CharField(_("txn_id"), max_length=500, null=True, blank=True, default=None)
    game_name = models.CharField(_("game_name"), max_length=50)
    transaction_type = models.CharField(blank=False, choices = TransactionStatus.choices, max_length=500)
    game_name_full = models.CharField(_("game_name"), max_length=50,null=True,blank=True)
    bonus = models.DecimalField(
        _("bonus"), max_digits=15, decimal_places=4, default=0.0000, null=False, blank=False
    )


class CsrQueries(AbstractBaseModel):
    user = models.ForeignKey(Users, on_delete=models.CASCADE)
    subject = models.CharField(max_length=50, null=True, blank=True, default=None)
    text = models.CharField(max_length=150, null=True, blank=True, default=None)
    is_active = models.BooleanField(default=False,null=True,blank=True)


class OffmarketWithdrawalRequests(AbstractBaseModel):

    class StatusType(DjangoChoices):
        pending = ChoiceItem("pending", "PENDING")
        in_process = ChoiceItem("cancelled", "CANCELLED")
        done = ChoiceItem("approved", "APPROVED")

    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False, null=True)
    amount = models.DecimalField(max_digits=15, decimal_places=8)
    code = models.CharField(max_length=100,blank=True, null=True)
    status = models.CharField(max_length=100, choices=StatusType,blank=True, null=True,default=StatusType.pending)
    transaction = models.ForeignKey(OffMarketTransactions, on_delete=models.SET_NULL, blank=True, null=True, default=None)

class SpintheWheelDetails(AbstractBaseModel):
    admin = models.ForeignKey(Users, on_delete=models.CASCADE, default=None, null=True, blank=True)
    value = models.IntegerField(null=True, blank=True)
    code = models.CharField(max_length=250, null=True, blank=True, default=None)


class CashAppDeatils(AbstractBaseModel):
    class StatusType(DjangoChoices):
        pending = ChoiceItem("pending", "PENDING")
        rejected = ChoiceItem("rejected", "REJECTED")
        approved = ChoiceItem("approved", "APPROVED")
    user = models.ForeignKey(Users, on_delete=models.CASCADE,null=True, blank=True, default=None)
    name = models.CharField(max_length=100,null=True, blank=True, default=None)
    approved_by = models.ForeignKey(Users, on_delete=models.CASCADE, blank=True, null=True,related_name="created_by_agent")
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=100, choices=StatusType,blank=True, null=True,default=StatusType.pending)


class CashappQr(AbstractBaseModel):
    is_active = models.BooleanField(default=False)
    image = models.ImageField(upload_to='cashapp-qr/', null=True, blank=True)
    user = models.ForeignKey(Users, on_delete=models.CASCADE,blank=True,null=True)


class EmailTemplateDetails(AbstractBaseModel):
    admin = models.ForeignKey(Users, on_delete=models.CASCADE, default=None, null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True, default=None)
    template_id = models.CharField(max_length=100, null=True, blank=True, default=None)


    def get_category_name(self):
        categories = {
            "signup_otp_mail": "Signup OTP Mail",
            "welcome_mail": "Welcome Mail",
            "customer_query_mail": "Customer Query Mail",
            "withdrawal_approved_mail": "Withdrawal Approved Mail",
            "withdrawal_pending_mail": "Withdrawal Pending Mail",
            "withdrawal_cancelled_mail": "Withdrawal Cancelled Mail",
            "withdrawal_failed_mail": "Withdrawal Failed Mail",
            "nowpayment_finished_mail": "Payment Finished Mail",
            "nowpayment_partially_paid_mail": "Payment Partially Paid Mail",
            "nowpayment_in_progress_mail": "Payment In-Progress Mail",
            "nowpayment_failed_mail": "Payment Failed Mail",
            "nowpayment_expired_mail": "Payment Expired Mail",
            "withdrawal_rejected_mail": "Withdrawal Rejected Mail (NowPayments)",
            "offmarket_withdraw_rejection_mail": "Offmarket Withdrawal Request Rejection Mail"
        }

        return categories.get(self.category, self.category)


class CmsBonusDetail(AbstractBaseModel):
    class BonusType(DjangoChoices):
        welcome_bonus = ChoiceItem("welcome_bonus", "Joining Bonus")
        deposit_bonus = ChoiceItem("deposit_bonus", "Deposit Bonus")
        bet_bonus = ChoiceItem("bet_bonus", "Bet Bonus")

    admin = models.ForeignKey(Users, on_delete=models.CASCADE, default=None, null=True)
    bonus_type = models.CharField(max_length=100, choices=BonusType,blank=True, null=True)
    promo_code = models.CharField(_("Promo Code"), max_length=50, null=True, blank=True, default=None)
    content = HTMLField(blank=True, null=True,max_length=2000)
    meta_description = models.TextField(null=True, blank=True)
    json_metadata = models.TextField(null=True, blank=True)


class FortunePandasGameList(AbstractBaseModel):
    game_name = models.CharField(max_length=250,blank=True,null=True)
    game_id = models.CharField(max_length=250,blank=True,null=True)
    game_image = models.FileField(upload_to='fortunepandas/', null=True, blank=True, default=None)
    game_category = models.CharField(max_length=250,blank=True,null=True)
    game_type = models.CharField(max_length=250,blank=True,null=True)


class FortunePandasGameManagement(AbstractBaseModel):
    admin = models.ForeignKey(Admin, on_delete=models.CASCADE,null=True, blank=True)
    game = models.ForeignKey(FortunePandasGameList, default=None, on_delete=models.CASCADE, null=True, blank=True)
    enabled = models.BooleanField(default=True, null=True, blank=True)
