from django import forms
from django.contrib.auth.hashers import make_password
from django.forms import ModelForm

from apps.admin_panel.validators import UserNameValidator

from .models import Users, CmsPromotions


DATETIME_INPUT_FORMATS = ['%d/%m/%Y %H:%M:%S'] 


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

class ToasterCmsPromotionsForm(forms.ModelForm):
    start_date = forms.DateTimeField(
        input_formats=DATETIME_INPUT_FORMATS,
        widget=forms.TextInput(attrs={
            'class': 'form-control datetimepicker',
            'placeholder': 'Select start date',
            'autocomplete': 'off',
            'readonly': 'true',
        })
    )
    end_date = forms.DateTimeField(
        input_formats=DATETIME_INPUT_FORMATS,
        widget=forms.TextInput(attrs={
            'class': 'form-control datetimepicker',
            'placeholder': 'Select end date',
            'autocomplete': 'off',
            'readonly': 'true',
        })
    )
    
    class Meta:
        model = CmsPromotions
        fields = '__all__'
        # exclude = ["title"]  # no rich text for toaster
        widgets = {
            "type": forms.HiddenInput(attrs={"value": "toaster"}),
            "start_date": forms.TextInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': 'Select start date',
                'autocomplete': 'off',
                'readonly': 'true',  # optional, to prevent manual typing
            }),
            "end_date": forms.TextInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': 'Select end date',
                'autocomplete': 'off',
                'readonly': 'true',
            }),
        }

class PageBlockerCmsPromotionsForm(forms.ModelForm):
    start_date = forms.DateTimeField(
        input_formats=DATETIME_INPUT_FORMATS,
        widget=forms.TextInput(attrs={
            'class': 'form-control datetimepicker',
            'placeholder': 'Select start date',
            'autocomplete': 'off',
            'readonly': 'true',
        })
    )
    end_date = forms.DateTimeField(
        input_formats=DATETIME_INPUT_FORMATS,
        widget=forms.TextInput(attrs={
            'class': 'form-control datetimepicker',
            'placeholder': 'Select end date',
            'autocomplete': 'off',
            'readonly': 'true',
        })
    )

    class Meta:
        model = CmsPromotions
        exclude = ["image"]  # no image for page blocker
        widgets = {
            "type": forms.HiddenInput(attrs={"value": "page_blocker"}),
            "start_date": forms.TextInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': 'Select start date',
                'autocomplete': 'off',
                'readonly': 'true',
            }),
            "end_date": forms.TextInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': 'Select end date',
                'autocomplete': 'off',
                'readonly': 'true',
            }),
        }