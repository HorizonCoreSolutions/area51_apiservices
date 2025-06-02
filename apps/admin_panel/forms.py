from xml.dom import ValidationErr
from django.forms import ModelForm, Select
from django import forms
from jsonschema import ValidationError
from apps.users.models import (Admin, AdminBanner, Agent, CashappQr, CmsAboutDetails, CmsFAQ,
    CmsPages, CmsPrivacyPolicy, CmsPromotionDetails, CookiePolicy, Dealer, FooterCategory,
    Introduction, OffMarketGames, Player, SettingsLimits, SocialLink, Staff, TermsConditinos,
    UserGames, Users)
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
from tinymce.widgets import TinyMCE


FORM_CHOICES = (
    ("none", _("None")),
    ("contact-form", _("Contact Form")),
    )


class PlayerModelForm(ModelForm):
    username = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': "au-input--full form-control", 'placeholder': _("Enter Username"), 'autocomplete': 'new-username'}),
        required=True,
        validators=[
            RegexValidator(
                regex='^[a-zA-Z0-9]*$',
                message='Username must be Alphanumeric',
                code='invalid_username'
            ),
        ],
        initial=""
    )
    email=forms.EmailField(required=True,max_length=32,validators=[], widget=forms.EmailInput(attrs={'class': "au-input--full form-control", 'placeholder': _("Enter Email")}))
    dob = forms.DateField(required=True,widget=forms.DateInput(attrs={'class': "au-input--full form-control", 'type': 'date','placeholder': _("DOB")},format = '%d-%m-%Y'))
    state = forms.CharField(required=True,max_length=32, widget=forms.TextInput(attrs={'class': "au-input--full form-control", 'placeholder': _("Enter State")}))
    city = forms.CharField(required=True,max_length=32, widget=forms.TextInput(attrs={'class': "au-input--full form-control", 'placeholder': _("Enter City")}))
    country_code = forms.CharField(min_length=1,max_length=5,required=True,widget=forms.TextInput(attrs={'class': "au-input--full form-control",'placeholder': _("Enter Country Code")}))
    phone_number = forms.CharField(min_length=4,max_length=12,required=True,widget=forms.TextInput(attrs={'class': "au-input--full form-control",'placeholder': _("Enter Mobile No")}))
    complete_address = forms.CharField(required=True,max_length=50,widget=forms.TextInput(attrs={'class': "au-input--full form-control", 'placeholder': _("Enter Complete Address")}))
    password = forms.CharField(max_length=32, widget=forms.PasswordInput(attrs={'class': "au-input--full form-control","id":'id_password', 'placeholder': _("Enter Password"), 'autocomplete': 'new-password'}))
    first_name=forms.CharField(required=True,max_length=32,widget=forms.TextInput(attrs={'class': "au-input--full form-control", 'placeholder': _("Enter First Name")}))
    last_name=forms.CharField(required=True,max_length=32,widget=forms.TextInput(attrs={'class': "au-input--full form-control", 'placeholder': _("Enter Last Name")}))
    confirm_password = forms.CharField(max_length=32, widget=forms.PasswordInput(attrs={'class': "au-input--full form-control",'id':'id_cnf_password', 'placeholder': _("Confirm Password"), 'autocomplete': 'new-password'}))
    # profile_pic=forms.FileInput(widget=forms.FileInput(attrs={'class': 'form-control','required':'true' ,'id':'id_profile','accept':'image/png,image/jpeg,image/jpg'}))
    # user_id_proof=forms.FileInput(widget=forms.FileInput(attrs={'class': 'form-control','required':'true' ,'id':'id_user_id_proof','accept':'image/png,image/jpeg,image/jpg'}))
    zip_code = forms.CharField(min_length=4,max_length=12,required=True,widget=forms.TextInput(attrs={'class': "au-input--full form-control",'placeholder': _("Enter zipcode")}))

    class Meta:
        model = Player
        fields = ("dealer", "agent", "username" , "state" , "city" , "dob" , "password","email","country_code","phone_number", "complete_address","first_name","last_name", "zip_code","profile_pic")
      
        widgets = {
            'profile_pic': forms.FileInput(attrs={'class': 'form-control-sm','id':'id_profile_pic','required':'true','onchange': 'show_profile_pic(this)','accept':'image/png,image/jpeg,image/jpg'}),
        #     'user_id_proof': forms.FileInput(attrs={'class': 'form-control','id':'id_user_id_proof','required':'true','accept':'image/png,image/jpeg,image/jpg'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['dealer'].widget = Select(attrs={
            'id': 'select-dealer',
            'class': 'form-control',
            'style': 'height: 40px;margin-bottom: 10px; width:100%;'
        })
        self.fields['agent'].widget = Select(attrs={
            'id': 'select-agent',
            'class': 'form-control',
            'style': 'height: 40px;margin-bottom: 10px; width:100%;'
        })
        instance = kwargs.get("instance")
        if instance:
            self.fields["username"].widget.attrs['readonly'] = True
            self.initial_dealer = instance.dealer
            self.initial_agent = instance.agent

    def save(self, commit=True):
        user = super().save(commit=commit)
        user.set_password(self.cleaned_data["password"])
        user.save()
        return user


class AgentModelForm(ModelForm):
    username = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': "au-input--full form-control", 'placeholder': _("Username"), 'autocomplete': 'new-username'}),
        required=True,
        validators=[
            RegexValidator(
                regex='^[a-zA-Z0-9]*$',
                message='Username must be Alphanumeric',
                code='invalid_username'
            ),
        ]

    )
    password = forms.CharField(max_length=32, widget=forms.PasswordInput(attrs={'class': "au-input--full form-control", 
        'placeholder': _("Password"), 'autocomplete': 'new-password','id':'id_password'}))
    confirm_password = forms.CharField(max_length=32, widget=forms.PasswordInput(attrs={'class': "au-input--full form-control", "id" : "id_cnf_password",
        'placeholder': _("Confirm Password"), 'autocomplete': 'new-password'}))

    class Meta:
        model = Agent
        fields = ("dealer", "username", "password")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dealer'].widget = Select(attrs={
            'id': 'select-dealer',
            'class': 'form-control',
            'style': 'height: 40px;margin-bottom: 10px; width:100%;'
        })
        instance = kwargs.get("instance")
        if instance:
            self.fields["username"].widget.attrs['readonly'] = True
            self.initial_dealer = instance.dealer

    def save(self, commit=True):
        user = super().save(commit=commit)
        user.set_password(self.cleaned_data["password"])
        user.save()
        return user


class DealerModelForm(ModelForm):
    username = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': "au-input--full form-control", 'placeholder': _("Username"), 'autocomplete': 'new-username'}),
        required=True,
        validators=[
            RegexValidator(
                regex='^[a-zA-Z0-9]*$',
                message='Username must be Alphanumeric',
                code='invalid_username'
            ),
        ],
        initial=""

    )
    password = forms.CharField(max_length=32, widget=forms.PasswordInput(attrs={'class': "au-input--full form-control",
        'placeholder': _("Password"), 'autocomplete': 'new-password'}))
    confirm_password = forms.CharField(max_length=32, widget=forms.PasswordInput(attrs={'class': "au-input--full form-control",
        'placeholder': _("Confirm Password"), 'autocomplete': 'new-password','id':'id_cnf_password'}))

    class Meta:
        model = Dealer
        fields = ("username", "password", "timezone", "currency")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance")
        if instance:
            self.fields["username"].widget.attrs['readonly'] = True

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password", "")
        confirm_password = cleaned_data.get("confirm_password", "")
        if password != confirm_password:
            raise forms.ValidationError(_('Password and Confirm Password does not match.'))
        return cleaned_data

    def save(self, commit=True):
        print("Inside save")
        user = super().save(commit=commit)
        user.set_password(self.cleaned_data["password"])
        user.save()
        return user


class AdminModelForm(ModelForm):
    username = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': "au-input--full form-control" ,'placeholder': _("Username")}),
        required=True,
        validators=[
            RegexValidator(
                regex='^[a-zA-Z0-9]*$',
                message='Username must be Alphanumeric',
                code='invalid_username'
            ),
        ]

    )
    password = forms.CharField(max_length=32, widget=forms.PasswordInput(attrs={'class': "au-input--full form-control",
        'placeholder': _("Password"), 'autocomplete': 'new-password'}))
   
    class Meta:
        model = Admin
        fields = ("username", "password")

    def clean(self):
        cleaned_data = super().clean()
        user_name = cleaned_data.get("username", "").lower()
        password = cleaned_data.get("password", "")

        if len(user_name) < 4:
            raise forms.ValidationError(_('The username has to be at least 4 characters'))
        
        if Users.objects.filter(username__iexact=user_name).exists():
            self.add_error("username", "The username already exists")
            raise forms.ValidationError(_('The username already exists'))

        if len(password) < 5:
            raise forms.ValidationError(_('The password has to be at least 5 characters'))

        cleaned_data["username"] = user_name
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=commit)
        user.set_password(self.cleaned_data["password"])
        user.save()
        return user


class AdminBannerForm(ModelForm):   
    
    class Meta:
        model = AdminBanner
        fields = ['admin', 'banner','title','banner_type','redirect_url', "button_text"]
        widgets = {
            'banner': forms.FileInput(attrs={'class': 'form-control','onchange': 'read_admin_banner_url(this)','required':'true' ,'id':'id_banner','accept':'image/png,image/jpeg,image/jpg'}),
            'title' : forms.TextInput(attrs={'class': 'form-control','required':'true','placeholder':'Enter Title','id':'banner_title','onkeypress':'validate_title()', "onpaste":"return false","ondrag":"return false","ondrop":"return false"}),
            # 'banner_type' : forms.Select(attrs={'class': 'form-control','required':'true','id':'banner_type','onchange':'change_banner_type_label()'}),
            'redirect_url' : forms.TextInput(attrs={'class': 'form-control','id':'redirect_url', 'required':'true', 'placeholder':'Enter Redirect URL','onchange':'validateURL()'},),
            'button_text' : forms.TextInput(attrs={'class': 'form-control', 'id':'button_text', 'required':'true', 'placeholder':'Enter Button Text',},),
        }




class AboutForm(ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'placeholder': 'Enter Title',
                   'maxlength': 100,
                   'id': 'id_title',
                   'onchange': 'validateTitle()'
                   }
        )
    )
    more_info = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'placeholder': 'Enter Some More Info',
                   'maxlength': 100,
                   
                   }
        ), required=False
    )
    banner = forms.FileField(
        widget=forms.FileInput(
            attrs={'class': 'form-control pl-0 border-0',
                   'onchange': 'read_about_banner_url(this)',
                   'id': 'id_banner',
                   'accept': 'image/png,image/jpeg,image/jpg'
                   }
        ), required=False
    )

    class Meta:
        model = CmsAboutDetails
        fields = ('title', 'page_content', 'more_info', 'banner', 'banner_thumbnail')


class PromotionForm(ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'placeholder': 'Enter Title',
                   'maxlength': 100,
                   'id': 'id_title',
                   'onchange':'validateTitle()'
                   }
        )
    )
    more_info = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'placeholder': 'Enter Some More Info',
                   'maxlength': 100,
                   }
        ), required=False
    )
    page = forms.FileField(
        widget=forms.FileInput(
            attrs={'class': 'form-control pl-0 border-0',
                   'onchange': 'read_promotion_page_url(this)',
                   'id': 'id_banner',
                   'accept': 'image/png,image/jpeg,image/jpg'
                   }
        ), required=False
    )
    
    class Meta:
        model = CmsPromotionDetails
        fields = ('title', 'page_content', 'more_info', 'page', 'page_thumbnail', 'meta_description', 'json_metadata')
        widgets = {
            'meta_description': forms.Textarea(attrs={'rows': 11, 'style': 'width: 100%;'}),
            'json_metadata': forms.Textarea(attrs={'rows': 11, 'style': 'width: 100%;'}),
        }


class PrivacyPolicyForm(ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'placeholder': 'Enter Title',
                   'maxlength': 100
                   }
        )
    )
    more_info = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'placeholder': 'Enter Some More Info',
                   'maxlength': 100,
                   }
        ), required=False
    )
    banner = forms.FileField(
        widget=forms.FileInput(
            attrs={'class': 'form-control pl-0 border-0',
                   'onchange': 'read_promotion_banner_url(this)',
                   'id': 'id_banner',
                   'accept': 'image/png,image/jpeg,image/jpg'
                   }
        ), required=False
    )

    class Meta:
        model = CmsPrivacyPolicy
        fields = ('title', 'page_content', 'more_info', 'banner', 'banner_thumbnail')


class FAQForm(ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'placeholder': 'Enter Title',
                   'maxlength': 100
                   }
        )
    )
    more_info = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'placeholder': 'Enter Some More Info',
                   'maxlength': 100,
                   }
        ), required=False
    )
    banner = forms.FileField(
        widget=forms.FileInput(
            attrs={'class': 'form-control pl-0 border-0',
                   'onchange': 'read_promotion_banner_url(this)',
                   'id': 'id_banner',
                   'accept': 'image/png,image/jpeg,image/jpg'
                   }
        ), required=False
    )

    class Meta:
        model = CmsFAQ
        fields = ('title', 'page_content', 'more_info', 'banner', 'banner_thumbnail')


class TermsConditinosForm(ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'placeholder': 'Enter Title',
                   'maxlength': 100
                   }
        )
    )
    more_info = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'placeholder': 'Enter Some More Info',
                   'maxlength': 100,
                   }
        ), required=False
    )
    banner = forms.FileField(
        widget=forms.FileInput(
            attrs={'class': 'form-control pl-0 border-0',
                   'onchange': 'read_promotion_banner_url(this)',
                   'id': 'id_banner',
                   'accept': 'image/png,image/jpeg,image/jpg'
                   }
        ), required=False
    )

    class Meta:
        model = TermsConditinos
        fields = ('title', 'page_content', 'more_info', 'banner', 'banner_thumbnail')



class CookiePolicyForm(ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'placeholder': 'Enter Title',
                   'maxlength': 100
                   }
        )
    )
    more_info = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'placeholder': 'Enter Some More Info',
                   'maxlength': 100,
                   }
        ), required=False
    )
    banner = forms.FileField(
        widget=forms.FileInput(
            attrs={'class': 'form-control pl-0 border-0',
                   'onchange': 'read_promotion_banner_url(this)',
                   'id': 'id_banner',
                   'accept': 'image/png,image/jpeg,image/jpg'
                   }
        ), required=False
    )

    class Meta:
        model = CookiePolicy
        fields = ('title', 'page_content', 'more_info', 'banner', 'banner_thumbnail')


class IntroductionForm(ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'placeholder': 'Enter Title',
                   'maxlength': 100
                   }
        )
    )
    more_info = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'placeholder': 'Enter Some More Info',
                   'maxlength': 100,
                   }
        ), required=False
    )
    banner = forms.FileField(
        widget=forms.FileInput(
            attrs={'class': 'form-control pl-0 border-0',
                   'onchange': 'read_promotion_banner_url(this)',
                   'id': 'id_banner',
                   'accept': 'image/png,image/jpeg,image/jpg'
                   }
        ), required=False
    )

    class Meta:
        model = Introduction
        fields = ('title', 'page_content', 'more_info', 'banner', 'banner_thumbnail')


class SettingsLimitsForm(ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'placeholder': 'Enter Title',
                   'maxlength': 100
                   }
        )
    )
    more_info = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'placeholder': 'Enter Some More Info',
                   'maxlength': 100,
                   }
        ), required=False
    )
    banner = forms.FileField(
        widget=forms.FileInput(
            attrs={'class': 'form-control pl-0 border-0',
                   'onchange': 'read_promotion_banner_url(this)',
                   'id': 'id_banner',
                   'accept': 'image/png,image/jpeg,image/jpg'
                   }
        ), required=False
    )

    class Meta:
        model = SettingsLimits
        fields = ('title', 'page_content', 'more_info', 'banner', 'banner_thumbnail')


class SocialLinkForm(ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'placeholder': 'Enter Title',
                   'maxlength': 100,
                   'onchange':'validateTitle()'
                   }
        )
    )
    logo = forms.FileField(
        widget=forms.FileInput(
            attrs={'class': 'form-control w-100',
                   'onchange': 'read_social_link_logo(this)',
                   'id': 'id_logo',
                   'required': 'false',
                   'accept': '.svg',
                   'placeholder': 'Add Logo',
                   }
        ), required=False
    )
    url = forms.URLField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'false',
                   'placeholder': 'Enter URL',
                   'maxlength': 300,
                   'id':'redirect_url',
                   'onchange': 'validateUrl()'
                   }
        )
    )
    

    class Meta:
        model = SocialLink
        fields = ('title', 'logo', 'url')
    
        
class CMSPagesForm(ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'placeholder': 'Enter Title',
                   'maxlength': 100,
                   'pattern':'[A-Za-z ]+',
                   'title':'Enter Characters Only ',
                   'onchange':'validateTitle()',
                   'id':'page_title',
                   'onkeypress':'validate_title()',
                   "onpaste":"return false",
                   "ondrag":"return false",
                   "ondrop":"return false"
                   }
                  ),
        )
    
    more_info = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'placeholder': 'Enter Some More Info',
                   'maxlength': 100,
                   'onchange':'validate_more_info()'
                   }
        ), required=False
    )
    page = forms.FileField(
        widget=forms.FileInput(
            attrs={'class': 'form-control pl-0 border-0',
                   'onchange': 'read_footer_page_url(this)',
                   'id': 'id_page',
                   'accept': 'image/png,image/jpeg,image/jpg'
                   }
        ), required=False
    )
   
    form_name = forms.ChoiceField(choices = FORM_CHOICES, widget=forms.Select(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'maxlength': 100
                   }
        ))
    
    
    class Meta:
        model = CmsPages
        fields = ('title', 'page_content', 'more_info', 'page', 'page_thumbnail', 'is_form', 'is_redirect', 'redirect_url', 'form_name', 'is_page', "meta_description", "json_metadata")
        widgets = {
            'redirect_url' : forms.TextInput(attrs={'class': 'form-control','id':'redirect_url','placeholder':'Enter Redirect URL','onchange':'validateURL()'},),
            'meta_description': forms.Textarea(attrs={'rows': 11, 'style': 'width: 100%;'}),
            'json_metadata': forms.Textarea(attrs={'rows': 11, 'style': 'width: 100%;'}),
        }
        

class FooterCategoryForm(ModelForm):
    name = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'pattern':'[A-Za-z ]+',
                   'title':'Enter Characters Only ',
                   'placeholder': 'Enter Category Name',
                   'maxlength': 100,
                   'onchange':'validateName()'
                   }
        )
    )
    position = forms.IntegerField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'min':1,'max': '100',
                   'type':'number',
                   'placeholder': 'Enter Postion', 
                   'maxlength': 10,
                   'onchange':'validatePosition()'
                   }
        )
    )
    
    class Meta:
        model = FooterCategory
        fields = '__all__'


class EditSocialLinkForm(ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'placeholder': 'Enter Title',
                   'maxlength': 100,
                   'onchange':'validateTitle()'
                   }
        )
    )
    logo = forms.FileField(
        widget=forms.FileInput(
            attrs={'class': 'form-control w-100',
                   'onchange': 'read_social_link_logo(this)',
                   'id': 'id_logo',
                   'accept': '.svg',
                   'placeholder': 'Add Logo',
                   }
        ), required=False
    )
    url = forms.URLField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'false',
                   'placeholder': 'Enter URL',
                   'maxlength': 300,
                   'id':'redirect_url',
                   'onchange': 'validateUrl()'
                   }
        )
    )
    

    class Meta:
        model = SocialLink
        fields = ('title', 'logo', 'url')


class DetailSocialLinkForm(ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'true',
                   'placeholder': 'Enter Title',
                   'maxlength': 100,
                   'readonly':'readonly',
                   'onchange':'validateTitle()'
                   }
        )
    )
    logo = forms.FileField(
        widget=forms.FileInput(
            attrs={'class': 'form-control pl-0 border-0',
                   'onchange': 'read_social_link_logo(this)',
                   'id': 'id_logo',
                   'accept': 'image/png,image/jpeg,image/jpg',
                   'readonly':'readonly',
                   'placeholder': 'Add Logo',
                   }
        ), required=False
    )
    url = forms.URLField(
        widget=forms.TextInput(
            attrs={'class': 'form-control',
                   'required': 'false',
                   'placeholder': 'Enter URL',
                   'maxlength': 300,
                   'id':'redirect_url',
                   'readonly':'readonly',
                   'onchange': 'validateUrl()'
                   }
        )
    )
    

    class Meta:
        model = SocialLink
        fields = ('title', 'logo', 'url')
        

class StaffModelForm(ModelForm):
    username = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': "au-input--full form-control", 'placeholder': _("Username"), 'autocomplete': 'new-username'}),
        required=True,
        validators=[
            RegexValidator(
                regex='^[a-zA-Z0-9]*$',
                message='Username must be Alphanumeric',
                code='invalid_username'
            ),
        ]

    )
    password = forms.CharField(max_length=32, widget=forms.PasswordInput(attrs={'class': "au-input--full form-control", 
        'placeholder': _("Password"), 'autocomplete': 'new-password','id':'id_password'}))
    confirm_password = forms.CharField(max_length=32, widget=forms.PasswordInput(attrs={'class': "au-input--full form-control", "id" : "id_cnf_password",
        'placeholder': _("Confirm Password"), 'autocomplete': 'new-password'}))

    class Meta:
        model = Staff
        fields = ("agent", "username", "password")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dealer'].widget = Select(attrs={
            'id': 'select-dealer',
            'class': 'form-control',
            'style': 'height: 40px;margin-bottom: 10px; width:100%;'
        })
        instance = kwargs.get("instance")
        if instance:
            self.fields["username"].widget.attrs['readonly'] = True
            self.initial_dealer = instance.dealer

    def save(self, commit=True):
        user = super().save(commit=commit)
        user.set_password(self.cleaned_data["password"])
        user.save()
        return user
    

class OffMarketGameForm(ModelForm):   
    class Meta:
        model = OffMarketGames
        fields = ['title', 'url','code','bonus_percentage','game_status','coming_soon','download_url','game_user','game_pass']
        widgets = {
            'url': forms.FileInput(attrs={'class': 'form-control','onchange': 'read_game_url(this)','required':'true' ,'id':'id_game','accept':'image/png,image/jpeg,image/jpg'}),
            'title' : forms.TextInput(
                attrs={'class': 'form-control'
                       ,'required':'true',
                       'placeholder':'Enter Game Name',
                       'id':'banner_title',
                       'onkeypress':'validate_title()',
                        "onpaste":"return false",
                        "ondrag":"return false",
                        "ondrop":"return false"}),
            'code' : forms.TextInput(attrs={'class': 'form-control','placeholder':'Enter Game Initial','required':'true','id':'game_code'}),
            'bonus_percentage': forms.NumberInput(attrs={'class': 'form-control','required':'true','id':'bonus_percentage','placeholder':'Enter Bonus Percentage','onkeypress':'validate_bonus_percentage(this)', "onpaste":"return false"}),
            'game_status': forms.CheckboxInput(attrs={'class': 'form-check-input','required':'true','id':'game_status'}),
            'coming_soon': forms.CheckboxInput(attrs={'class': 'form-check-input','id':'coming_soon','required':'true'}),
            'download_url': forms.TextInput(attrs={'class': 'form-control','required':'true','placeholder':'Enter Download URL','id':'download_url','onchange':'validate_download_url()'}),
            'game_user' : forms.TextInput(attrs={'class': 'form-control','placeholder':'Enter Game Login ID','required':'true','id':'game_user','maxlength':'10','autofill':False,'autocomplete': 'new-password'}),
            'game_pass' : forms.TextInput(attrs={'class': 'form-control','placeholder':'Enter Game Password','required':'true','id':'game_pass','maxlength':'10','autofill':False,'autocomplete': 'new-password'}),
        }
        

class CashappDetailForm(ModelForm):
    class Meta:
        model = CashappQr
        fields = ('is_active', 'image')
        widgets = {
            'image': forms.FileInput({'class': 'form-control','onchange': 'read_admin_banner_url(this)','required':'true' ,'id':'id_banner','accept':'image/png,image/jpeg,image/jpg'}),
        }


class UserGamesForm(forms.ModelForm):
    class Meta:
        model = UserGames
        fields = ['user', 'game', 'username']

    def __init__(self, *args, **kwargs):
        super(UserGamesForm, self).__init__(*args, **kwargs)

        # Check if the instance is not provided (indicating a new UserGame)
        if self.instance:
            self.fields['username'].widget.attrs['class'] = 'form-control'
            self.fields['username'].widget.attrs['placeholder'] = 'Enter username'
            self.fields['game'].widget.attrs['class'] = 'form-control'
            self.fields['game'].empty_label = 'Select game'  # Add a placeholder for the game field

            games = OffMarketGames.objects.all()
            choices = [(game.id, f"{game.title} - {game.code}") for game in games]

            blank_option = (None, 'Select game')

            self.fields['game'].choices = [blank_option] + choices