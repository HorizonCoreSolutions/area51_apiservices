from typing import Any, Dict, List
from apps.users.models import SpintheWheelDetails, Users

def edit_spin_wheel_details(
    admin: Users,
    details: List[Dict[str, Any]]
) -> List[SpintheWheelDetails]:
    return SpintheWheelDetails.objects.filter(admin=admin)

def create_spin_wheel_details(admin: Users, value: int, code: str) -> SpintheWheelDetails:
    return SpintheWheelDetails.objects.create(admin=admin, value=value, code=code)

def delete_spin_wheel_details(admin: Users, code: str) -> bool:
    return bool(SpintheWheelDetails.objects.filter(admin=admin, code=code).delete())