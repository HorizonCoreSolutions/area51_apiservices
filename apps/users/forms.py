from django import forms
from django.contrib.auth.hashers import make_password
from django.forms import ModelForm

from apps.admin_panel.validators import UserNameValidator

from .models import Users, CmsPromotions


DATETIME_INPUT_FORMATS = ['%d/%m/%Y %H:%M'] 
DATETIME_FORMAT = '%d/%m/%Y %H:%M'

class UserModelForm(ModelForm):
   
    class Meta:
        model = Users
        fields = ('role', 'username', 'is_active', 'is_deleted', 'balance', 'pending', 'locked', 'timezone', 'password','dob' ,'state','city', 'complete_address','email','first_name','last_name','profile_pic','user_id_proof','phone_number')

    def clean(self):
        self.cleaned_data = super().clean()
        if not self.instance.pk:
            self.cleaned_data["password"] = make_password(self.cleaned_data["password"])
        return self.cleaned_data

    def save(self, commit=True):

        user = super().save(commit=commit)
        return user


class BaseCmsPromotionsForm(forms.ModelForm):
    start_date = forms.DateTimeField(
        input_formats=DATETIME_INPUT_FORMATS,
        widget=forms.TextInput(attrs={
            'class': 'form-control datetimepicker',
            'placeholder': 'Select start date',
            'autocomplete': 'off',
            'readonly': 'true',
            'data-format': 'd/m/Y H:i',  # JS uses this, Python ignores
        })
    )
    end_date = forms.DateTimeField(
        input_formats=DATETIME_INPUT_FORMATS,
        widget=forms.TextInput(attrs={
            'class': 'form-control datetimepicker',
            'placeholder': 'Select end date',
            'autocomplete': 'off',
            'readonly': 'true',
            'data-format': 'd/m/Y H:i',
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Format the initial values for display
        for field in ['start_date', 'end_date']:
            if self.instance and getattr(self.instance, field):
                self.fields[field].initial = getattr(self.instance, field).strftime(DATETIME_FORMAT)


class ToasterCmsPromotionsForm(BaseCmsPromotionsForm):
    class Meta:
        model = CmsPromotions
        fields = '__all__'
        widgets = {
            "type": forms.HiddenInput(attrs={"value": "toaster"}),
        }


class PageBlockerCmsPromotionsForm(BaseCmsPromotionsForm):
    class Meta:
        model = CmsPromotions
        exclude = ["image"]
        widgets = {
            "type": forms.HiddenInput(attrs={"value": "page_blocker"}),
        }