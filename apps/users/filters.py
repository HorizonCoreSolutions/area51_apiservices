from django_filters import rest_framework as filters
from django.utils.translation import gettext_lazy as _

from apps.users.models import Users

SORT_BY_CHOICES = (
    ("Recent Login", _("Recent Login")),
    ("Credit Ascending", _("Credit Ascending")),
    ("Credit Descending", _("Credit Descending")),
    ("Profit Ascending", _("Profit Ascending")),
    ("Profit Descending", _("Profit Descending"))
)


class PlayerFilters(filters.FilterSet):
    class Meta:
        model = Users
        fields = {}

    dealer = filters.NumberFilter(method='stub', label='filter by dealer id')
    agents = filters.CharFilter(method='stub', label='filter by agents')
    sort_by = filters.ChoiceFilter(choices=SORT_BY_CHOICES, method='stub')
    username = filters.CharFilter(method='filter_username', label='filter by dealer id')

    @staticmethod
    def stub(queryset, name, value):
        return queryset

    @staticmethod
    def filter_username(queryset, name, value):
        return queryset.filter(username__icontains=value)
