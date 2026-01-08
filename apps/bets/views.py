import datetime


from apps.bets.filters import (
    LiveCasinoTransactionFilters,
    TransactionFilters,
)
from apps.bets.serializers import (
    GamePoolBetsSerializer,
    Transactionandinerializer,
    WageringRequirementsSerializer,
)
from apps.bets.utils import validate_date
from apps.casino.models import *
from apps.core.pagination import PageNumberPagination
from apps.core.permissions import IsPlayer
from apps.core.rest_any_permissions import AnyPermissions
# from apps.pulls.management.commands.firestore import toogle_placing_bets

from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from rest_framework import viewsets

from .models import (
    BONUS,
    CASHBACK,
    CREDIT,
    DEBIT,
    DEPOSIT,
    WITHDRAW,
    Transactions,
    WageringRequirement,
)



class TransactionsView(viewsets.ModelViewSet):
    queryset = Transactions.objects.filter(
        journal_entry__in=(WITHDRAW, DEPOSIT, CREDIT, DEBIT, CASHBACK, BONUS,'tip')
    )
    serializer_class = Transactionandinerializer
    http_method_names = [
        "get",
    ]
    filter_class = TransactionFilters
    pagination_class = PageNumberPagination
    permission_classes = [AnyPermissions]
    any_permission_classes = [
        IsPlayer,
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        transaction_filter_dict = {}
        translation_language = self.request.query_params.get("language",'en')
        if(translation_language in ['nl','ru','de','tr','fr']):
            activate(translation_language)
        else:
            activate('en')
      

        from_date = self.request.query_params.get("from_date", None)
        to_date = self.request.query_params.get("to_date", None)
        activity_type = self.request.query_params.get("type", None)  
        if activity_type:
            if activity_type==BONUS:
                transaction_filter_dict = {"journal_entry":BONUS,}
            elif activity_type==DEBIT:
                transaction_filter_dict = {"journal_entry":DEBIT,}
            elif activity_type==CREDIT:
                transaction_filter_dict = {"journal_entry":CREDIT,}
            elif activity_type==DEPOSIT:
                transaction_filter_dict = {"journal_entry":DEPOSIT,}
            elif activity_type==WITHDRAW:
                transaction_filter_dict = {"journal_entry":WITHDRAW,}
           
            

        transaction_filter_dict["user"] = self.request.user

        timezone_offset = self.request.query_params.get("timezone_offset", None)
        if from_date and validate_date(from_date):
            from_date = datetime.datetime.strptime(
                from_date + " 00:00:00", "%Y-%m-%d %H:%M:%S"
            )
            if timezone_offset:
                timezone_offset = float(timezone_offset)
                if timezone_offset < 0:
                    transaction_filter_dict[
                        "created__gte"
                    ] = from_date + datetime.timedelta(
                        minutes=(-(timezone_offset) * 60)
                    )
                else:
                    transaction_filter_dict[
                        "created__gte"
                    ] = from_date - datetime.timedelta(minutes=(timezone_offset * 60))
            else:
                transaction_filter_dict["created__date__gte"] = from_date

        if to_date and validate_date(to_date):
            to_date = datetime.datetime.strptime(
                to_date + " 23:59:59", "%Y-%m-%d %H:%M:%S"
            )
            if timezone_offset:
                timezone_offset = float(timezone_offset)
                if timezone_offset < 0:
                    transaction_filter_dict[
                        "created__lte"
                    ] = to_date + datetime.timedelta(minutes=(-(timezone_offset) * 60))
                else:
                    transaction_filter_dict[
                        "created__lte"
                    ] = to_date - datetime.timedelta(minutes=(timezone_offset * 60))
            else:
                transaction_filter_dict["created__date__lte"] = to_date

        queryset = queryset.filter(**transaction_filter_dict).exclude(Q(description__istartswith="tip") | Q(bonus_type= 'spin_wheel')).order_by("-created")

        return queryset


class CasinoTransactionsView(viewsets.ModelViewSet):
    queryset = GSoftTransactions.objects.all()
    serializer_class = GamePoolBetsSerializer
    http_method_names = [
        "get",
    ]
    filter_class = LiveCasinoTransactionFilters
    pagination_class = PageNumberPagination
    permission_classes = [AnyPermissions]
    any_permission_classes = [
        IsPlayer,
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        translation_language = self.request.query_params.get("language", "en")
        if translation_language in ["nl", "ru", "de", "tr", "fr"]:
            activate(translation_language)
        else:
            activate("en")

        from_date = self.request.query_params.get("from_date", None)
        to_date = self.request.query_params.get("to_date", None)
        type = self.request.query_params.get("type", None)
        game_name = self.request.query_params.get("game_name", None)

        transaction_filter_dict = {"user": self.request.user, "is_tournament_transaction": False}
        if type:
            if type == "debit":
                transaction_filter_dict["action_type__in"] = [GSoftTransactions.ActionType.bet, GSoftTransactions.ActionType.rollback]
                queryset = queryset.filter(
                    Q(transaction_type=GSoftTransactions.TransactionType.debit) | Q(transaction_type__isnull=True)
                )
            else:
                transaction_filter_dict["action_type__in"] = [GSoftTransactions.ActionType.win, GSoftTransactions.ActionType.rollback]
                queryset = queryset.filter(
                    Q(transaction_type=GSoftTransactions.TransactionType.credit) | Q(transaction_type__isnull=True)
                )
                
        if game_name:
            game_ids = list(CasinoGameList.objects.filter(game_name__icontains=game_name).values_list("game_id", flat=True))
            transaction_filter_dict["game_id__in"] = game_ids

        timezone_offset = self.request.query_params.get("timezone_offset", None)

        if from_date and validate_date(from_date):
            from_date = datetime.datetime.strptime(
                from_date + " 00:00:00", "%Y-%m-%d %H:%M:%S"
            )
            if timezone_offset:
                timezone_offset = float(timezone_offset)
                if timezone_offset < 0:
                    transaction_filter_dict[
                        "created__gte"
                    ] = from_date + datetime.timedelta(
                        minutes=(-(timezone_offset) * 60)
                    )
                else:
                    transaction_filter_dict[
                        "created__gte"
                    ] = from_date - datetime.timedelta(minutes=(timezone_offset * 60))
            else:
                transaction_filter_dict["created__date__gte"] = from_date

        if to_date and validate_date(to_date):
            to_date = datetime.datetime.strptime(
                to_date + " 23:59:59", "%Y-%m-%d %H:%M:%S"
            )
            if timezone_offset:
                timezone_offset = float(timezone_offset)
                if timezone_offset < 0:
                    transaction_filter_dict[
                        "created__lte"
                    ] = to_date + datetime.timedelta(minutes=(-(timezone_offset) * 60))
                else:
                    transaction_filter_dict[
                        "created__lte"
                    ] = to_date - datetime.timedelta(minutes=(timezone_offset * 60))
            else:
                transaction_filter_dict["created__date__lte"] = to_date

        queryset = queryset.filter(**transaction_filter_dict).order_by("-created")

        return queryset

class WageringRequirementsView(viewsets.ModelViewSet):
    queryset = WageringRequirement.objects.none()
    serializer_class = WageringRequirementsSerializer
    http_method_names = [
        "get",
    ]
    permission_classes = [AnyPermissions]
    any_permission_classes = [
        IsPlayer,
    ]

    def get_queryset(self):
        queryset = WageringRequirement.objects.filter(
            user=self.request.user,
            balance__gt=0,
            active=True
        )

        from_date = self.request.query_params.get("from_date", None)
        to_date = self.request.query_params.get("to_date", None)

        transaction_filter_dict = {"user": self.request.user}

        timezone_offset = self.request.query_params.get("timezone_offset", None)

        if from_date and validate_date(from_date):
            from_date = datetime.datetime.strptime(
                from_date + " 00:00:00", "%Y-%m-%d %H:%M:%S"
            )
            if timezone_offset:
                timezone_offset = float(timezone_offset)
                if timezone_offset < 0:
                    transaction_filter_dict[
                        "created__gte"
                    ] = from_date + datetime.timedelta(
                        minutes=(-(timezone_offset) * 60)
                    )
                else:
                    transaction_filter_dict[
                        "created__gte"
                    ] = from_date - datetime.timedelta(minutes=(timezone_offset * 60))
            else:
                transaction_filter_dict["created__date__gte"] = from_date

        if to_date and validate_date(to_date):
            to_date = datetime.datetime.strptime(
                to_date + " 23:59:59", "%Y-%m-%d %H:%M:%S"
            )
            if timezone_offset:
                timezone_offset = float(timezone_offset)
                if timezone_offset < 0:
                    transaction_filter_dict[
                        "created__lte"
                    ] = to_date + datetime.timedelta(minutes=(-(timezone_offset) * 60))
                else:
                    transaction_filter_dict[
                        "created__lte"
                    ] = to_date - datetime.timedelta(minutes=(timezone_offset * 60))
            else:
                transaction_filter_dict["created__date__lte"] = to_date

        queryset = queryset.filter(**transaction_filter_dict).order_by("-created")

        return queryset
