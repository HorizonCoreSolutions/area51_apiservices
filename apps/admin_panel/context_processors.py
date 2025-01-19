from apps.users.models import Role

def header_roles(request):
    if request.user.is_authenticated:
        return {'header_roles': Role.objects.filter(admin=request.user)}
    return {'header_roles': []}
