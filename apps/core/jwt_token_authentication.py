import jwt

from django.utils.encoding import smart_text
from django.contrib.auth import get_user_model
from django.utils.translation import ugettext as _
from rest_framework import exceptions
from rest_framework.authentication import (
    BaseAuthentication, get_authorization_header
)

from rest_framework import status
from rest_framework_jwt.settings import api_settings
from rest_framework_jwt.authentication import JSONWebTokenAuthentication
from apps.users.models import Users

jwt_decode_handler = api_settings.JWT_DECODE_HANDLER
jwt_get_username_from_payload = api_settings.JWT_PAYLOAD_GET_USERNAME_HANDLER


class CustomJSONWebTokenAuthentication(JSONWebTokenAuthentication):
    """
    Clients should authenticate by passing the token key in the "Authorization"
    HTTP header, prepended with the string specified in the setting
    `JWT_AUTH_HEADER_PREFIX`. For example:
        Authorization: JWT eyJhbGciOiAiSFMyNTYiLCAidHlwIj
    """
    def get_jwt_value(self, request):
        auth = get_authorization_header(request).split()
        auth_header_prefix = api_settings.JWT_AUTH_HEADER_PREFIX.lower()
        if not auth:
            if api_settings.JWT_AUTH_COOKIE:
                return request.COOKIES.get(api_settings.JWT_AUTH_COOKIE)
            return None

        if smart_text(auth[0].lower()) != auth_header_prefix:
            return None

        if len(auth) == 1:
            msg = _('Invalid Authorization header. No credentials provided.')
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = _('Invalid Authorization header. Credentials string '
                    'should not contain spaces.')
            raise exceptions.AuthenticationFailed(msg)
        else:
            token = auth[1].decode('utf-8')
            try:
                payload = jwt_decode_handler(token)
            except:
                raise exceptions.AuthenticationFailed('Signature has expired')
            is_allowed_user = True
            try:
                user_token = Users.objects.get(id=payload['user_id']).access_token
                if user_token == token:
                    is_allowed_user = True
                else:
                    is_allowed_user = False
            except Users.DoesNotExist:
                is_allowed_user = False
            # try:
            #     is_blackListed = BlackListedToken.objects.get(user__id=payload['user_id'], token=token)
            #     if is_blackListed:
            #         is_allowed_user = False
            # except BlackListedToken.DoesNotExist:
            #     is_allowed_user = True
            if not is_allowed_user:
                msg = 'repeated_login'
                raise exceptions.AuthenticationFailed(msg)

        return auth[1]

    def authenticate_credentials(self, payload):
        """
        Returns an active user that matches the payload's user id and email.
        """
        User = get_user_model()
        username = jwt_get_username_from_payload(payload)
        try:
            username = username[6:]
        except:
            msg = _('Invalid payload.')
            raise exceptions.AuthenticationFailed(msg)

        if not username:
            msg = _('Invalid payload.')
            raise exceptions.AuthenticationFailed(msg)

        try:
            user = User.objects.get_by_natural_key(username)
        except User.DoesNotExist:
            msg = _('Invalid signature.')
            raise exceptions.AuthenticationFailed(msg)

        if not user.is_active:
            msg = _('User account is disabled.')
            raise exceptions.AuthenticationFailed(msg)

        return user
