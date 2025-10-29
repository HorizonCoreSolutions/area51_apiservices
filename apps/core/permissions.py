from rest_framework import permissions

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")

class IsFavCasinoEnabled(permissions.BasePermission):
    """
    to send fav casino games for AnonymousUser and authenticated users 
    """
    def has_permission(self, request, view):
        if view.request.user.is_authenticated and request.user.role == "player" and not request.user.is_deleted:
            return True
        return True
    
class BasePermission(permissions.BasePermission):
    """
    Defining permission methods
    """

    @staticmethod
    def is_player(request):
        return request.user.is_authenticated and request.user.role == "player"

    @staticmethod
    def is_agent(request):
        return request.user.is_authenticated and request.user.role == "agent"

    @staticmethod
    def is_dealer(request):
        return request.user.is_authenticated and request.user.role == "dealer"

    @staticmethod
    def is_manager(request):
        return request.user.is_authenticated and request.user.role == "manager"

    @staticmethod
    def is_admin(request):
        return request.user.is_authenticated and request.user.role == "admin"

    @staticmethod
    def is_superadmin(request):
        return request.user.is_authenticated and request.user.role == "superadmin"


class IsAdmin(BasePermission):
    """
    Checking if user has permission of admin
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "admin" and not request.user.is_deleted


class IsPlayer(BasePermission):
    """
    Checking if user has permission of player
    """

    def has_permission(self, request, view):
        return view.request.user.is_authenticated and request.user.role == "player" and not request.user.is_deleted


class IsDealer(BasePermission):
    """
    Checking if user has permission of dealer
    """

    def has_permission(self, request, view):
        return (
            view.request.user.is_authenticated and request.user.role == "dealer" and not request.user.is_deleted
        )


class IsAgent(BasePermission):
    """
    Checking if user has permission of agent
    """

    def has_permission(self, request, view):
        return (
            view.request.user.is_authenticated and request.user.role == "agent" and not request.user.is_deleted
        )


class IsManager(BasePermission):
    """
    Checking if user has permission of manager
    """

    def has_permission(self, request, view):
        return (
            view.request.user.is_authenticated and request.user.role == "manager" and not request.user.is_deleted
        )


class IsSuperAdmin(BasePermission):
    """
    Checking if user has permission of super admin
    """

    def has_permission(self, request, view):
        return (
            view.request.user.is_authenticated and request.user.role == "superadmin" and not request.user.is_deleted
        )


class IsBackOffice(BasePermission):
    """
    Checking if user has permission of super admin
    """

    def has_permission(self, request, view):
        return (
            view.request.user.is_authenticated
            and request.user.role in {"admin", "agent", "superadmin"}
            and not request.user.is_deleted
        )


class IsCasinoEnabled(BasePermission):
    """
    Checking if casino is enabled for dealer and his players
    """
    def has_permission(self, request, view):

        # The casino should be enabled fot both player's dealer and agent
        if view.request.user.is_authenticated and request.user.role == "player":
            if all([
                view.request.user.dealer.is_casino_enabled,
                view.request.user.agent.is_casino_enabled
            ]):
                return True
        return False
