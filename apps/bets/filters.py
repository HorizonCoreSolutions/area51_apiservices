from django_filters import rest_framework as filters
from django.utils.translation import gettext_lazy as _

from .models import Transactions
from apps.users.models import UserBets
from apps.casino.models import *


JOURNAL_ENTRY_CHOICES = (
    ("withdraw", _("Withdraw")),
    ("deposit", _("Deposit")),
    ("credit", _("Credit")),
    ("debit", _("Debit")),
    ("deposit", _("Deposit")),
)





class TransactionFilters(filters.FilterSet):
    class Meta:
        model = Transactions
        fields = {}

    from_date = filters.DateFilter(method='stub', label='filter from date.')
    to_date = filters.DateFilter(method='stub', label='filter to date.')
    activity_type = filters.ChoiceFilter(
        method='filter_activity_type', label='filter by journal entry', choices=JOURNAL_ENTRY_CHOICES
    )

    @staticmethod
    def stub(queryset, name, value):
        return queryset

    @staticmethod
    def filter_activity_type(queryset, name, value):
        return queryset.filter(journal_entry=value)

class CasinoTransactionFilters(filters.FilterSet):
    class Meta:
        model = UserBets
        fields = {}

    from_date = filters.DateFilter(method='stub', label='filter from date.')
    to_date = filters.DateFilter(method='stub', label='filter to date.')
    activity_type = filters.ChoiceFilter(
        method='filter_activity_type', label='filter by journal entry', choices=JOURNAL_ENTRY_CHOICES
    )

    @staticmethod
    def stub(queryset, name, value):
        return queryset

    @staticmethod
    def filter_activity_type(queryset, name, value):
        return queryset.filter(journal_entry=value)

class LiveCasinoTransactionFilters(filters.FilterSet):
    class Meta:
        model = GSoftTransactions
        fields = {}

    from_date = filters.DateFilter(method='stub', label='filter from date.')
    to_date = filters.DateFilter(method='stub', label='filter to date.')
    activity_type = filters.ChoiceFilter(
        method='filter_activity_type', label='filter by journal entry', choices=JOURNAL_ENTRY_CHOICES
    )

    @staticmethod
    def stub(queryset, name, value):
        return queryset

    @staticmethod
    def filter_activity_type(queryset, name, value):
        if value == 'credit':
            return queryset.filter(type=GSoftTransactions.RequestType.wager)
        return queryset.filter(type=GSoftTransactions.RequestType.result)


