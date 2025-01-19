from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.urls import resolve


class CheckRolesMixin(LoginRequiredMixin, UserPassesTestMixin):
    view_permissions = {
        'DashboardView': {
            'get': lambda user: True,
        },
        'HomeView': {
            'get': lambda user: True,
        },
        'TournamentListView': {
            'get': lambda user: user.has_permissions("can_view_tournament"),
            'post': lambda user: user.has_permissions("can_view_tournament"),
        },
        'TournamentDetailView': {
            'get': lambda user: user.has_permissions("can_view_tournament"),
        },
        'CreateTournamentView': {
            'get': lambda user: user.has_permissions("can_add_tournament"),
            'post': lambda user: user.has_permissions("can_add_tournament"),
        },
        'EditTournamentView': {
            'get': lambda user: user.has_permissions("can_edit_tournament"),
            'post': lambda user: user.has_permissions("can_edit_tournament"),
        },
        "CasinoCategoryHeaderManagementView":{
            'get': lambda user: user.has_permissions("can_view_website_header"),
            'post': lambda user: user.has_permissions("can_edit_website_header"),
            'put': lambda user: user.has_permissions("can_edit_website_header"),
        },
        "CasinoHeaderCategoryStatus":{
            'post': lambda user: user.has_permissions("can_edit_website_header"),
        },
        "TransactionReportView":{
            'get': lambda user: user.has_permissions("can_view_balance_transfer_report"),
        },
        "OffMarketReportView":{
            'get': lambda user: user.has_permissions("can_view_offmarket_report"),
        },
        "CasinoBetslipReportView":{
            'get': lambda user: user.has_permissions("can_view_casino_report"),
        },
        "NowPaymentsReportView":{
            'get': lambda user: user.has_permissions("can_view_nowpayments_report"),
        },
        "AlchemyPayReportView":{
            'get': lambda user: user.has_permissions("can_view_alchemy_pay_report"),
        },
        "CashAppReportView":{
            'get': lambda user: user.has_permissions("can_view_cashapp_report"),
        },
        "BonusTransactionReportView":{
            'get': lambda user: user.has_permissions("can_view_bonus_report"),
        },
        "MnetReportView":{
            'get': lambda user: user.has_permissions("can_view_mnet_report"),
        },
        "AdminBannersView":{
            'get': lambda user: user.has_permissions("can_view_banner"),
        },
        "CreateAdminBannerView":{
            'get': lambda user: user.has_permissions("can_add_banner"),
            'post': lambda user: user.has_permissions("can_add_banner"),
        },
        "EditAdminBannerView":{
            'get': lambda user: user.has_permissions("can_edit_banner"),
            'post': lambda user: user.has_permissions("can_edit_banner"),
        },
        "DeleteAdminBanner":{
            'post': lambda user: user.has_permissions("can_delete_banner"),
        },
        "PagesView":{
            'get': lambda user: user.has_permissions("can_view_pages"),
        },
        "CreatePageView":{
            'get': lambda user: user.has_permissions("can_add_pages"),
            'post': lambda user: user.has_permissions("can_add_pages"),
        },
        "EditPageAjax":{
            'get': lambda user: user.has_permissions("can_edit_pages"),
            'post': lambda user: user.has_permissions("can_edit_pages"),
        },
        "DeletePage":{
            'post': lambda user: user.has_permissions("can_delete_pages"),
        },
        "PromotionPageView":{
            'get': lambda user: user.has_permissions("can_view_promotions"),
        },
        "CreatePromotionPageView":{
            'get': lambda user: user.has_permissions("can_add_promotions"),
            'post': lambda user: user.has_permissions("can_add_promotions"),
        },
        "EditPromotionPageAjax":{
            'get': lambda user: user.has_permissions("can_edit_promotions"),
            'post': lambda user: user.has_permissions("can_edit_promotions"),
        },
        "DeletePromotionPage":{
            'post': lambda user: user.has_permissions("can_delete_promotions"),
        },
        "CRMView":{
            'get': lambda user: user.has_permissions("can_view_email_notification"),
        },
        "CreateCrmTemplateView":{
            'get': lambda user: user.has_permissions("can_add_email_notification"),
            'post': lambda user: user.has_permissions("can_add_email_notification"),
        },
        "EditCrmTemplateAjax":{
            'get': lambda user: user.has_permissions("can_edit_email_notification"),
            'post': lambda user: user.has_permissions("can_edit_email_notification"),
        },
        "ManageCrmTemplateAjax":{
            'post': lambda user: user.has_permissions("can_edit_crm") or user.has_permissions("can_delete_email_notification"),
        },
        "SendTemplateAjax":{
            'post': lambda user: user.has_permissions("can_send_email_notification"),
        }
    }

    def test_func(self):
        user_role = self.request.user.role
        is_allowed = user_role in self.allowed_roles
        match = resolve(self.request.path_info)
        view_func = match.func

        if user_role not in ["superadmin", "admin", "dealer", "agent", "staff"] and hasattr(view_func, 'view_class'):
            view_class = view_func.view_class
            method = self.request.method.lower()  # Normalize method to lowercase

            if self.has_permission(view_class, method):
                return True

            raise PermissionDenied()
        
        return is_allowed

    def has_permission(self, view_class, method):
        """Determine if the user has permission to access the view method."""
        # Get the view class name
        view_class_name = view_class.__name__

        # Check if we have permissions for the view class and method
        if view_class_name in self.view_permissions:
            method_permissions = self.view_permissions[view_class_name]
            if method in method_permissions:
                return method_permissions[method](self.request.user)

        return False
