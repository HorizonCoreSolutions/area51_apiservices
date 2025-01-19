from django import template
from apps.users.models import Permission, Role

register = template.Library()

@register.filter
def has_permission(obj, perm_name):
    """ Check if the user has a specific permission """
    return obj.has_permissions(perm_name)
    
@register.filter
def has_group_permission(obj:Role, group):
    permissions = list(Permission.objects.filter(group=group).order_by("code").values_list("code", flat=True))
    allowed_permissions = list(obj.permissions.filter(group=group).order_by("code").values_list("code", flat=True))
    return permissions == allowed_permissions

@register.filter
def replace(text:str, args:str):
    old, new = args.split(',')
    return text.replace(old, new)
    
