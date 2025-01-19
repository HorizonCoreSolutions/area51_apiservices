from django.contrib import admin

from apps.users.forms import UserModelForm
from .models import Player, Dealer, Manager, Admin, Agent, SuperAdmin


class PlayerAdmin(admin.ModelAdmin):
    empty_value_display = '-empty-'
    form = UserModelForm

    def has_module_permission(self, request):
        if not request.user.is_anonymous:
            if request.user.role not in ('dealer', 'manager', 'admin', 'agent', 'superadmin'):
                return False
            return True
        return False


class DealerAdmin(admin.ModelAdmin):
    empty_value_display = '-empty-'
    form = UserModelForm

    def has_module_permission(self, request):
        if not request.user.is_anonymous:
            if request.user.role not in ('admin', 'superadmin'):
                return False
            return True
        return False


class ManagerAdmin(admin.ModelAdmin):
    empty_value_display = '-empty-'
    form = UserModelForm

    def has_module_permission(self, request):
        if not request.user.is_anonymous:
            if request.user.role not in ('admin', 'superadmin', 'dealer', 'agent'):
                return False
            return True
        return False


class AdminAdmin(admin.ModelAdmin):
    empty_value_display = '-empty-'
    search_fields = ['username']
    form = UserModelForm

    def has_module_permission(self, request):
        if not request.user.is_anonymous:
            if request.user.role not in ('superadmin',):
                return False
            return True
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.exclude(id=request.user.id)


class SuperAdminAdmin(admin.ModelAdmin):
    empty_value_display = '-empty-'
    search_fields = ['username']
    form = UserModelForm

    def has_module_permission(self, request):
        if not request.user.is_anonymous:
            if request.user.role not in ('superadmin',):
                return False
            return True
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.exclude(id=request.user.id)


class AgentAdmin(admin.ModelAdmin):
    empty_value_display = '-empty-'
    form = UserModelForm

    def has_module_permission(self, request):
        if not request.user.is_anonymous:
            if request.user.role not in ('dealer', 'admin', 'superadmin'):
                return False
            return True
        return False


admin.site.register(Player, PlayerAdmin)
admin.site.register(Dealer, DealerAdmin)
admin.site.register(Manager, ManagerAdmin)
admin.site.register(Admin, AdminAdmin)
admin.site.register(SuperAdmin, SuperAdminAdmin)
admin.site.register(Agent, AgentAdmin)
