from apps.users.models import Users
from apps.users import promo_handler


user = Users.objects.get(username="alba")

for _ in range(100):
    promo_handler.redeam_code(
            user=user,
            amount_dep=None,
            bonus_type="welcome",
            promo_code="albaIsTheBest",
            )
