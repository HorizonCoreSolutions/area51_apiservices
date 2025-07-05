import uuid
from django.db import models
from django.utils import timezone
from djchoices import ChoiceItem, DjangoChoices

from apps.core.models import AbstractBaseModel
from apps.users.models import Users

class VerificationStateChoise(DjangoChoices):
    pending = ChoiceItem("PENDING", "pending")
    accepted = ChoiceItem("ACCEPTED", "accepted")
    declined = ChoiceItem("DECLINED", "declined")
    secure = ChoiceItem("SECURE", "secure")
    expired = ChoiceItem("EXPIRED", "expired")
    
    
class DocumentTypeChoise(DjangoChoices):
    passport = ChoiceItem('PASSPORT', 'passport')
    id_card = ChoiceItem('ID_CARD', 'id_card')
    driving_license = ChoiceItem('DRIVING_LICENSE', 'driving_license')
# Create your models here.

class AcuitytecUser(AbstractBaseModel):

    user = models.OneToOneField(Users, on_delete=models.CASCADE, related_name='acuitytec_account')

    has_been_validated = models.BooleanField(default=False)
    last_validated = models.DateTimeField(null=True, blank=True)

    is_validated = models.BooleanField(default=False)
    actual_state = models.CharField(blank=True, default=None, null=True, choices=VerificationStateChoise.choices, max_length=500)

    login_ip = models.CharField(blank=True, default=None, null=True, max_length=500)
    validated_amount = models.PositiveIntegerField(default=0, null=False, blank=False)

    updated = models.DateTimeField(auto_now_add=True)


class VerificationItem(AbstractBaseModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Users, on_delete=models.CASCADE, related_name='acuitytec_urls')
    reference_id = models.CharField(max_length=500, blank=True, null=True)
    document_type = models.CharField(
        max_length=500, 
        blank=True,
        null=True,
        choices=DocumentTypeChoise.choices,
        default=DocumentTypeChoise.id_card # type: ignore
    )
    url = models.URLField(blank=True, null=True)
    status = models.CharField(
        max_length=500,
        choices=VerificationStateChoise.choices,
        default=VerificationStateChoise.pending, # type: ignore
        null=True,
        blank=True,
    )