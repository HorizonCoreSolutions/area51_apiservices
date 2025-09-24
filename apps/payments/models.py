from django.db import models
from decimal import Decimal
from apps.core.models import AbstractBaseModel
from apps.users.models import Users
from django.db import models
from django.utils.translation import gettext_lazy as _
from djchoices import ChoiceItem, DjangoChoices
# Create your models here.



# Store Coin Payments IPN request details .

class CoinWithdrawal(AbstractBaseModel):

    class StatusType(DjangoChoices):
        pending = ChoiceItem("pending", "pending")
        processing = ChoiceItem("processing", "processing")
        complete = ChoiceItem("complete", "complete")
        rollback = ChoiceItem("rollback", "rollback")
        failed = ChoiceItem("failed", "failed")

    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False, default=None, null=True)
    coin_withdraw_id = models.CharField(max_length=500, default=None, blank=True, null=True)
    amount = models.FloatField(_("amount"), default=0.0000, null=True, blank=True)
    currency = models.CharField(max_length=5, default=None, blank=True, null=True)
    currency2 = models.CharField(max_length=5, default=None, blank=True, null=True)
    address = models.CharField(max_length=500, default=None, blank=True, null=True)
    status = models.CharField(max_length=20, choices=StatusType, default=0, blank=True, null=True)


class NowPaymentsTransactions(AbstractBaseModel):

    class StatusType(DjangoChoices):
        pending = ChoiceItem("pending", "pending")
        processing = ChoiceItem("processing", "processing")
        complete = ChoiceItem("complete", "complete")
        rollback = ChoiceItem("rollback", "rollback")
        failed = ChoiceItem("failed", "failed")
        sending = ChoiceItem("sending", "sending")
        rejected = ChoiceItem("rejected", "rejected")
        waiting = ChoiceItem("waiting", "waiting")
        finished = ChoiceItem("finished", "finished")
        expired = ChoiceItem("expired", "expired")
        confirmed = ChoiceItem("confirmed", "confirmed")
        refunded = ChoiceItem("refunded", "refunded")
        sending = ChoiceItem("sending", "sending")
        partially_paid = ChoiceItem("partially_paid", "partially_paid")
        
    user =  models.ForeignKey(Users, on_delete=models.CASCADE, blank=False, default=None, null=True) 
    payment_id = models.CharField(max_length=100)
    payment_status = models.CharField(max_length=20)
    pay_address = models.CharField(max_length=100)
    price_amount = models.DecimalField(max_digits=15, decimal_places=8)
    price_currency = models.CharField(max_length=10)
    pay_amount = models.DecimalField(max_digits=15, decimal_places=8, blank=True, null=True)
    pay_currency = models.CharField(max_length=10)
    ipn_callback_url = models.URLField(max_length=200)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(blank=True, null=True)
    purchase_id = models.CharField(max_length=100,default=None,null=True)
    address = models.CharField(max_length=100, blank=True, null=True)
    batch_withdrawal_id = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, blank=True, null=True)
    requested_at = models.DateTimeField(blank=True, null=True)
    transaction_type = models.CharField(max_length=20, blank=True, null=True)
    invoice_id = models.CharField(max_length=100,default=None,null=True)
    applied_promo_code = models.CharField(_("Applied Promo Code"), max_length=50, null=True, blank=True, default=None)
   



class WithdrawalRequests(AbstractBaseModel):

    class StatusType(DjangoChoices):
        pending = ChoiceItem("pending", "PENDING")
        in_process = ChoiceItem("cancelled", "CANCELLED")
        done = ChoiceItem("approved", "APPROVED")

    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False, null=True)
    amount = models.DecimalField(max_digits=15, decimal_places=8)
    currency = models.CharField(max_length=100,blank=True, null=True)
    address = models.CharField(max_length=100)
    status = models.CharField(max_length=100, choices=StatusType,blank=True, null=True,default=StatusType.pending)
    transaction = models.ForeignKey(NowPaymentsTransactions, on_delete=models.SET_NULL, blank=True, null=True, default=None)
    
    
class WithdrawalCurrency(AbstractBaseModel):
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=100)
    enabled = models.BooleanField(default=True)
    wallet_regex = models.CharField(max_length=100, null=True, blank=True)
    priority = models.IntegerField()
    extra_id_exists = models.BooleanField(default=False)
    extra_id_regex = models.CharField(max_length=100, null=True, blank=True)
    logo_url = models.CharField(max_length=200)
    track = models.BooleanField(default=True)
    cg_id = models.CharField(max_length=100)
    is_maxlimit = models.BooleanField(default=False)
    network = models.CharField(max_length=50,null=True, blank=True)
    smart_contract = models.CharField(max_length=100, null=True, blank=True)
    network_precision = models.IntegerField(null=True, blank=True)
    


class AlchemypayOrder(AbstractBaseModel):
    class StatusType(DjangoChoices):
        peysuccess = ChoiceItem("pay_success", "PAY_SUCCESS")
        payfail = ChoiceItem("pay_fail", "PAY_FAIL")
        finished = ChoiceItem("finished", "FINISHED")
        pending = ChoiceItem("pending", "PENDING")
    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False, null=True)
    order_no = models.CharField(max_length=20,null=True,blank=True) 
    crypto_currency = models.CharField(max_length=10)
    address = models.CharField(max_length=100)
    network = models.CharField(max_length=10)
    fiat_currency = models.CharField(max_length=10)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=30)
    pay_code = models.CharField(max_length=20,null=True,blank=True)
    country = models.CharField(max_length=4)
    pay_url = models.CharField(max_length=500)
    trace_id = models.CharField(max_length=50)
    email = models.CharField(max_length=50,null=True,blank=True)
    status = models.CharField(max_length=50,choices=StatusType,blank=True, null=True,default=StatusType.pending)
    applied_promo_code = models.CharField(_("Applied Promo Code"), max_length=50, null=True, blank=True, default=None)
    
    
class MnetTransaction(AbstractBaseModel):
    class TransactionType(DjangoChoices):
        deposit = ChoiceItem("deposit", "DEPOSIT")
        withdraw = ChoiceItem("withdraw", "WITHDRAW")
        
    class StatusType(DjangoChoices):
        requested = ChoiceItem("requested", "REQUESTED")
        pending = ChoiceItem("pending", "PENDING")
        approved = ChoiceItem("approved", "APPROVED")
        cancelled = ChoiceItem("cancelled", "CANCELLED")
        rejected = ChoiceItem("rejected", "REJECTED")
        refund = ChoiceItem("refund", "REFUND")
        chargeback = ChoiceItem("chargeback", "CHARGEBACK")

    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=50,choices=TransactionType)
    status = models.CharField(max_length=50,choices=StatusType, default=StatusType.pending)
    card_type = models.CharField(max_length=20,null=True,blank=True)
    card_number = models.CharField(max_length=20,null=True,blank=True)
    processor_name = models.CharField(max_length=20,null=True,blank=True)
    transaction_id = models.CharField(max_length=30,null=True,blank=True)
    trans_note = models.CharField(max_length=80,null=True,blank=True)
    ip_address = models.CharField(max_length=20,null=True,blank=True)
    currency = models.CharField(max_length=20,null=True,blank=True)
    descriptor = models.CharField(max_length=100,null=True,blank=True)
    error_code = models.CharField(max_length=20,null=True,blank=True)
    error_description = models.CharField(max_length=100,null=True,blank=True)
    

class CoinFlowTransaction(AbstractBaseModel):
    class TransactionType(DjangoChoices):
        deposit = ChoiceItem("deposit", _("Deposit"))
        withdraw = ChoiceItem("withdraw", _("Withdraw"))
        
    class AccountType(DjangoChoices):
        card = ChoiceItem("card", _("Card"))
        bank = ChoiceItem("bank", _("Bank"))
        
    class StatusType(DjangoChoices):
        # Common statuses
        requested = ChoiceItem("requested", _("Requested"))
        pending = ChoiceItem("pending", _("Pending"))
        processing = ChoiceItem("processing", _("Processing"))
        approved = ChoiceItem("approved", _("Approved"))
        cancelled = ChoiceItem("cancelled", _("Cancelled"))
        rejected = ChoiceItem("rejected", _("Rejected"))
        expired = ChoiceItem("expired", _("Expired"))

        # Payment outcomes
        charged = ChoiceItem("charged", _("Charged"))
        # this item was once accepted
        refunded = ChoiceItem("refunded", _("Refunded"))
        # this has never been accepted
        refund = ChoiceItem("refund", _("Refund"))
        failed = ChoiceItem("failed", _("Failed"))
        failed_fraud = ChoiceItem("failed_fraud", _("Failed Fraud"))
        paid_out = ChoiceItem("paid_out", _("Paid Out"))

        # Chargeback flow
        chargeback = ChoiceItem("chargeback", _("Chargeback"))
        chargeback_opened = ChoiceItem("chargeback_opened", _("Chargeback Opened"))
        chargeback_won = ChoiceItem("chargeback_won", _("Chargeback Won"))
        chargeback_lost = ChoiceItem("chargeback_lost", _("Chargeback Lost"))


    transaction_id = models.CharField(max_length=80,null=True,blank=True)
    signature = models.CharField(max_length=100,null=True,blank=True)
    external_id = models.CharField(max_length=80,null=True,blank=True)

    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal(0))
    currency = models.CharField(max_length=20,null=True,blank=True)
    ip_address = models.CharField(max_length=20,null=True,blank=True)
    
    pre_balance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    post_balance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    transaction_type = models.CharField(max_length=50,choices=TransactionType)
    status = models.CharField(max_length=50,choices=StatusType, default=StatusType.pending)
    account_type = models.CharField(max_length=20, choices=AccountType,null=True,blank=True)

    applied_promo_code = models.CharField(_("Applied Promo Code"), max_length=50, null=True, blank=True, default=None)
    promo_log = models.OneToOneField(
        "PromoCodesLogs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="coinflow_transaction"
    )
    confimation_needed = models.BooleanField(default=False)
    
    processor_name = models.CharField(max_length=20,null=True,blank=True)
    trans_note = models.CharField(max_length=80,null=True,blank=True)
    descriptor = models.CharField(max_length=100,null=True,blank=True)
    
    error_code = models.CharField(max_length=20,null=True,blank=True)
    error_description = models.CharField(max_length=500,null=True,blank=True)