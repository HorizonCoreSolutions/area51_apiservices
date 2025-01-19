from django.core.management.base import BaseCommand
from django.db.models import Q
from apps.users.models import Permission

class Command(BaseCommand):
    help = 'Populate the Permission model with predefined permissions'
    
    permissions_to_add = {
        "can_view_dashboard": "dashboard",
        "can_view_tournament": "tournament",
        "can_add_tournament": "tournament",
        "can_edit_tournament": "tournament",
        "can_view_balance_transfer_report": "report",
        "can_view_offmarket_report": "report",
        "can_view_casino_report": "report",
        "can_view_nowpayments_report": "report",
        "can_view_alchemy_pay_report": "report",
        "can_view_cashapp_report": "report",
        "can_view_bonus_report": "report",
        "can_view_mnet_report": "report",
        "can_view_website_header": "website header",
        "can_edit_website_header": "website header",
        "can_view_banner": "cms",
        "can_add_banner": "cms",
        "can_edit_banner": "cms",
        "can_delete_banner": "cms",
        "can_view_pages": "cms",
        "can_add_pages": "cms",
        "can_edit_pages": "cms",
        "can_delete_pages": "cms",
        "can_view_promotions": "cms",
        "can_add_promotions": "cms",
        "can_edit_promotions": "cms",
        "can_delete_promotions": "cms",
        "can_view_email_notification": "crm",
        "can_add_email_notification": "crm",
        "can_edit_email_notification": "crm",
        "can_delete_email_notification": "crm",
        "can_send_email_notification": "crm",
    }

    def handle(self, *args, **kwargs):
        added_permissions = []
        for perm_code, group in self.permissions_to_add.items():
            name = perm_code.replace('_', ' ').title()
            description = f"Permission to {name.lower().replace('can ', '')}"
            permission, created = Permission.objects.get_or_create(
                code=perm_code,
                defaults={'name': name, 'description': description, "group":group}
            )
            if created:
                print(f'Permission "{permission.name}" added.')
            else:
                print(f'Permission "{permission.name}" already exists.')
            added_permissions.append(perm_code)
                
        Permission.objects.filter(~Q(code__in=added_permissions)).delete()
