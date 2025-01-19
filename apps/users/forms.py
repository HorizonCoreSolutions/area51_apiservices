from django import forms
from django.contrib.auth.hashers import make_password
from django.forms import ModelForm

from apps.admin_panel.validators import UserNameValidator

from .models import Users


class UserModelForm(ModelForm):
   
    class Meta:
        model = Users
        fields = ('role', 'username', 'is_active', 'is_deleted', 'balance', 'pending', 'locked', 'timezone', 'password','dob' ,'state', 'complete_address','email','full_name','profile_pic','user_id_proof','phone_number')

    def clean(self):
        self.cleaned_data = super().clean()
        if not self.instance.pk:
            self.cleaned_data["password"] = make_password(self.cleaned_data["password"])
        return self.cleaned_data

    def save(self, commit=True):

        user = super().save(commit=commit)
        return user
