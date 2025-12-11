import json
import math
import traceback
from decimal import Decimal
from typing import Tuple

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.postgres.fields import JSONField
from djchoices import ChoiceItem, DjangoChoices
from django.core.validators import MinValueValidator


from apps.core.models import AbstractBaseModel
from apps.users.models import Users,CashAppDeatils


# Journal Entryes
CHARGED = "Charged"
FAILED_CHARGE = "Failed Charge"
DEBIT = "debit"
CREDIT = "credit"
DEPOSIT = "deposit"
WITHDRAW = "withdraw"
CASHBACK = "cashback"
BONUS = "bonus"
PAY = "pay"
BONUS_CREDIT = "bonus_credit"
PENDING = "pending"
ROLLBACK = "rollback"

SPIN_WHEEL = 'spin_wheel'
# STATUSES = (
#     ("pending_charge", _("Pending Charge")),
#     ("failed_charge", _("Failed Charge")),
#     ("charged", _("Charged")),
#     ("pending_pay", _("Pending Pay")),
#     ("failed_reject", _("Failed Reject")),
# )

STATUSES = (
    ("pending_charge", _("Pending Charge")),
    ("failed_charge", _("Failed Charge")),
    ("charged", _("Charged")),
    ("pending_pay", _("Pending Pay")),
    ("failed_reject", _("Failed Reject")),
    ("chargeback_opened", _("Chargeback Opened")),
    ("chargeback_disputed", _("Chargeback Disputed")),
    ("chargeback_lost", _("Chargeback Lost")),
    ("chargeback_won", _("Chargeback Won")),
    ("refunded", _("Refunded")),
    ("processing_ach", _("Processing ACH")),
    ("expired", _("Expired")),
    ("pending_review", _("Pending Review")),
)


class Transactions(AbstractBaseModel):
    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False)
    merchant = models.ForeignKey(
        Users, on_delete=models.CASCADE, null=True, default=None, related_name="merchant_user"
    )
    amount = models.DecimalField(
        _("amount"), max_digits=15, decimal_places=4, default=0.0000, null=False, blank=False
    )
    journal_entry = models.CharField(
        _("journal_entry"), max_length=500, null=False, blank=False, default=None
    )
    status = models.CharField(
        _("status"), choices=STATUSES, max_length=500, null=False, blank=False, default=None
    )
    previous_balance = models.DecimalField(
        _("previous_balance"), max_digits=15, decimal_places=4, default=0.0000, null=False, blank=False
    )
    new_balance = models.DecimalField(
        _("new_balance"), max_digits=15, decimal_places=4, default=0.0000, null=False, blank=False
    )
    reference = models.CharField(
        _("reference"), max_length=500, null=False, blank=False, default=None, unique=True
    )
    description = models.CharField(_("description"), max_length=500, null=False, blank=False, default=None)
    payment_id = models.CharField(
        _("payment_id"), max_length=500, null=True, blank=True, default=None)
    txn_id = models.CharField(_("txn_id"), max_length=500, null=True, blank=True, default=None)
    address = models.CharField(max_length=150, verbose_name=_('Address'), null=True, blank=True, default=None)
    confirms_needed = models.PositiveSmallIntegerField(verbose_name=_('Confirms needed'), null=True,
                                                       blank=True, default=None)
    qrcode_url = models.URLField(verbose_name=_('QR Code Url'), null=True, blank=True, default=None)
    status_url = models.URLField(verbose_name=_('Status Url'), null=True, blank=True, default=None)
    checkout_url = models.URLField(verbose_name=_('Checkout Url'), null=True, blank=True, default=None)
    timeout = models.DateTimeField(verbose_name=_('Valid until'), null=True, blank=True, default=None)
    bonus_type= models.CharField(
        _("bonus_type"), max_length=500,null=True, blank=True, default=None
    )
    bonus_amount=models.DecimalField(
        _("bonus_amount"), max_digits=15, decimal_places=4, default=0.0000, null=False, blank=False
    )
    payment_method = models.CharField(max_length=150, verbose_name=_('Payment Method'), null=True, blank=True, default='Other')
    trans_id = models.CharField(max_length=150, verbose_name=_('C ash App transation'), null=True, blank=True)
    cashapp = models.ForeignKey(CashAppDeatils, on_delete=models.CASCADE, blank=True,null=True,default=None)
    


class ChartStats(AbstractBaseModel):
    user = models.ForeignKey(Users, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField(default=None, null=True, blank=True)
    sports_book_profit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, null=False, blank=False)
    per_sports_bet_count = JSONField(default=None, null=True, blank=False)
    per_sports_profit = JSONField(default=None, null=True, blank=False)
    per_sports_winning = JSONField(default=None, null=True, blank=False)


class WageringRequirement(AbstractBaseModel):
    """_summary_

    Args:
        AbstractBaseModel (_type_): _description_
        
    I'm sorry if you are reading this, but I'm writing this so you can get a better understand on this model
    
    1) amount and balance should start at the same value
    2) as the user plays it should be reduced from balance
       - on each bet the value of the bet should be added to played
    3) once the user has played more than the limit the balance should be given to the user
    """
    user = models.ForeignKey(Users, on_delete=models.CASCADE, related_name="wagering_requirements")
    accreditable = models.ForeignKey(Users, on_delete=models.CASCADE, null=True, default=None, related_name="accreditable_wagerings")

    # the amount the user has deposited
    amount = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    # the amount of bonus it has (like if player 5 and amount 5, here should be 5)
    balance = models.DecimalField(max_digits=10, decimal_places=2)
    # The amount the user has played
    played = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    limit = models.DecimalField(max_digits=10, decimal_places=2)

    result = models.DecimalField(max_digits=10, decimal_places=2, null=True, default=None)
    active = models.BooleanField(default=True, db_index=True)
    betable = models.BooleanField(db_index=True)