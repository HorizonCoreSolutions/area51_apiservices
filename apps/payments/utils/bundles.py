from typing import List
from django.db.models import Case, Count, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from apps.users.models import Users
from apps.payments.models import Bundle, BundleUsage


def get_bundles(user: Users) -> List[Bundle]:
    """
    Return enabled bundles that the user can still purchase.
    
    Filters out bundles where:
    - User has reached limit_per_user
    - Global usage has reached limit_total
    
    Optimized: only counts usage when limits are set (not null).
    """
    # Subquery for user's usage count on each bundle
    user_usage_subquery = (
        BundleUsage.objects.filter(bundle=OuterRef("pk"), user=user)
        .values("bundle")
        .annotate(cnt=Count("id"))
        .values("cnt")
    )

    # Subquery for total usage count on each bundle
    total_usage_subquery = (
        BundleUsage.objects.filter(bundle=OuterRef("pk"))
        .values("bundle")
        .annotate(cnt=Count("id"))
        .values("cnt")
    )

    return list(
        Bundle.objects.filter(enabled=True)
        .annotate(
            # Only compute user_usage when limit_per_user is set
            user_usage=Case(
                When(
                    limit_per_user__isnull=False,
                    then=Coalesce(Subquery(user_usage_subquery), Value(0)),
                ),
                default=Value(0),
                output_field=IntegerField(),
            ),
            # Only compute total_usage when limit_total is set
            total_usage=Case(
                When(
                    limit_total__isnull=False,
                    then=Coalesce(Subquery(total_usage_subquery), Value(0)),
                ),
                default=Value(0),
                output_field=IntegerField(),
            ),
        )
        .filter(
            Q(limit_per_user__isnull=True) | Q(user_usage__lt=F("limit_per_user"))
        )
        .filter(
            Q(limit_total__isnull=True) | Q(total_usage__lt=F("limit_total"))
        )
        .order_by("price")
    )