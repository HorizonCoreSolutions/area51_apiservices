from django.db import models
from djchoices import ChoiceItem, DjangoChoices

from apps.users.models import Users

# Create your models here.

class AcuitytecUser(models.Model):
    class VerificationState(DjangoChoices):
        pending = ChoiceItem("PENDING", "pending")
        validated = ChoiceItem("VALIDATED", "validated")
        negated = ChoiceItem("NEGATED", "negated")
        secure = ChoiceItem("SECURE", "secure")

    user = models.OneToOneField(Users, on_delete=models.CASCADE, related_name='acuitytec_account')
    
    has_been_validated = models.BooleanField(default=False)
    last_validated = models.DateTimeField(null=True, blank=True)
    
    is_validated = models.BooleanField(default=False)
    actual_state = models.CharField(blank=True, default=None, null=True, choices=VerificationState.choices, max_length=500)
    
    login_ip = models.CharField(blank=True, default=None, null=True)
    
    validated_amount = models.PositiveIntegerField(default=0, null=False, blank=False)