from django.contrib.auth.backends import ModelBackend

from apps.core.exceptions import NotActiveUserException, DeactivatedUserException


class BaseUserAuthentication(ModelBackend):
    """
    Override authentication backend for signing in with email or phone number
    """

    def user_can_authenticate(self, user):
        """
        Reject users with is_active=False. Custom user models that don't have
        that attribute are allowed.
        """
        is_active = getattr(user, "is_active", None)
        if not is_active:
            raise NotActiveUserException

        is_deleted = getattr(user, "is_deleted")
        if is_deleted:
            raise DeactivatedUserException

        return is_active
