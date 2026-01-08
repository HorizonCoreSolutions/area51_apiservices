import datetime
import math
from decimal import Decimal
import pytz

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.fields import empty

from apps.bets.models import BONUS,DEPOSIT, WITHDRAW,Transactions, WageringRequirement
from apps.casino.models import *
# from apps.pulls.management.commands import firestore

from django.db.models import Sum
from apps.users.models import (
    UserBets,
)

class Transactionandinerializer(serializers.ModelSerializer):
    amount = serializers.SerializerMethodField()
    trans_type = serializers.SerializerMethodField()
    journal_entry = serializers.SerializerMethodField()

    class Meta:
        model = Transactions
        fields = ("id", "created", "amount", "journal_entry", "trans_type")

    @staticmethod
    def get_amount(obj):
        if obj.journal_entry == BONUS:
            return Decimal(obj.bonus_amount)
        else:
            return Decimal(obj.amount)
    
    @staticmethod
    def get_trans_type(obj):
        description = obj.description
        if obj.journal_entry in [WITHDRAW, DEPOSIT, BONUS]:
            return ""
        if "cashout" in description.lower():
            return "Cashout"
        elif (
            ("refunded" in description.lower())
            or ("refund" in description.lower())
            or ("cancel" in description.lower())
            or ("cancelled" in description.lower())
        ):
            return "Refunded"
        elif "tip" in description.lower():
            return 'tip'
        else:
            return ""
        
    @staticmethod
    def get_journal_entry(obj):
        if obj.journal_entry == 'debit':
            return 'Credit'
        elif obj.journal_entry == "credit":
            return 'Debit'
        else:
            return obj.journal_entry.capitalize()



class UserBetsSerializer(serializers.ModelSerializer):
    journal_entry = serializers.SerializerMethodField()
    trans_type = serializers.SerializerMethodField()

    class Meta:
        model = UserBets
        fields = ("id", "created", "cash_in", "cash_out",
                  "balance", "journal_entry", "trans_type")

    @staticmethod
    def get_journal_entry(obj):
        return "credit"

    @staticmethod
    def get_trans_type(obj):
        return "Casino"



class GamePoolBetsSerializer(serializers.ModelSerializer):
    action_type = serializers.SerializerMethodField()
    request_type = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    game_name = serializers.SerializerMethodField()
    bonus_amount = serializers.SerializerMethodField()
    total_bet_win = serializers.SerializerMethodField()

    class Meta:
        model = GSoftTransactions
        fields = ("id", "created", "amount", "action_type", "request_type", "game_name", "bonus_amount", "total_bet_win")

    @staticmethod
    def get_amount(obj):
        if obj.request_type == GSoftTransactions.RequestType.wager:
            return -(obj.amount or 0)
        return obj.amount or 0

    @staticmethod
    def get_request_type(obj):
        if obj.transaction_type:
            return obj.transaction_type.title()
        if obj.request_type == GSoftTransactions.RequestType.wager:
            return "Debit"
        return "Credit"

    # @staticmethod
    # def get_trans_type(obj):
    #     if 'LIVECASINO' in obj.category:
    #         return "Live Casino"
    #     else:
    #         return "Slot"

    @staticmethod
    def get_action_type(obj):
        return obj.action_type
    
    @staticmethod
    def get_game_name(obj):
        casino_game = CasinoGameList.objects.filter(game_id=obj.game_id).first()
        return casino_game.game_name if casino_game else None
    
    @staticmethod
    def get_bonus_amount(obj):
        if obj.request_type == GSoftTransactions.RequestType.wager:
            return -(obj.bonus_bet_amount or 0)
        return obj.bonus_bet_amount or 0
    
    @staticmethod
    def get_total_bet_win(obj):
        total = round((Decimal(obj.bonus_bet_amount or 0) + Decimal(obj.amount or 0)), 2)
        return -total if obj.request_type == GSoftTransactions.RequestType.wager else total


class WageringRequirementsSerializer(serializers.ModelSerializer):
    class Meta:
        model = WageringRequirement
        fields = ("created", "balance", "played", "limit", "description")
