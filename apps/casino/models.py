from django.contrib.postgres.fields import JSONField
from django.db import models
from djchoices import ChoiceItem, DjangoChoices
from django.utils.translation import gettext_lazy as _

from apps.core.models import AbstractBaseModel
from apps.users.models import Admin, Users
from apps.casino.internal_utils import rename_image


class Providers(AbstractBaseModel):
    name = models.CharField(max_length=250,blank=True,null=True)
    logo = models.ImageField(upload_to=rename_image, null=True, blank=True)


class CasinoGameList(AbstractBaseModel):
    # game_list = JSONField(default=None, null=True, blank=True)
    game_name = models.CharField(max_length=250,blank=True,null=True)
    game_id = models.CharField(max_length=250,blank=True,null=True)
    game_type = models.CharField(max_length=250,blank=True,null=True)
    game_image = models.CharField(max_length=250,blank=True,null=True)
    vendor_name = models.CharField(max_length=250,blank=True,null=True)
    enabled = models.BooleanField(default=True, null=True, blank=True)
    game_category = models.CharField(max_length=250,blank=True,null=True)
    is_support_jackpot = models.BooleanField(default=False)
    jackpot_type = models.CharField(max_length=250,blank=True,null=True)
    release_date = models.CharField(max_length=250,blank=True,null=True)
    currencies_list = JSONField(default=None, null=True, blank=True)
    platform = JSONField(default=None, null=True, blank=True)
    languages_list = JSONField(default=None, null=True, blank=True)
    description = models.CharField(max_length=250,blank=True,null=True)
    section_id = models.CharField(max_length=250,blank=True,null=True)
    format = models.CharField(max_length=250,blank=True,null=True)
    tags = JSONField(default=None, null=True, blank=True)
    is_demo_supported = models.BooleanField(default=False)
    is_mobile_supported = models.BooleanField(default=False)
    is_desktop_supported = models.BooleanField(default=False)
    is_free_round_supported = models.BooleanField(default=False)

class GameImages(AbstractBaseModel):
    name = models.CharField(max_length=256, default=None, null=True, blank=False)
    url = models.URLField(max_length=200, default=None, null=True, blank=False)


class GSoftTransactions(AbstractBaseModel):
    class RequestType(DjangoChoices):
        wager = ChoiceItem("WAGER", "wager")
        result = ChoiceItem("RESULT", "result")
        rollback = ChoiceItem("ROLLBACK", "rollback")
        jackpot = ChoiceItem("JACKPOT", "jackpot")

    class BonusType(DjangoChoices):
        free_round = ChoiceItem('FREE_ROUND', 'FREE_ROUND')
        feature_trigger = ChoiceItem('FEATURE_TRIGGER', 'FEATURE_TRIGGER')

    class DeviceType(DjangoChoices):
        mobile = ChoiceItem('MOBILE,', 'mobile,')
        desktop = ChoiceItem('DESKTOP', 'desktop')
        native = ChoiceItem('NATIVE', 'NATIVE')

    class ActionType(DjangoChoices):
        bet = ChoiceItem('BET', 'bet')
        win = ChoiceItem('WIN', 'win')
        lose = ChoiceItem('LOSE', 'lose')
        rollback = ChoiceItem('ROLLBACK', 'rollback')

    class GameStatus(DjangoChoices):
        pending = ChoiceItem('PENDING', 'pending')
        completed = ChoiceItem('COMPLETED', 'completed')

    class TransactionType(DjangoChoices):
        credit = ChoiceItem('CREDIT', 'credit')
        debit = ChoiceItem('DEBIT', 'debit')

    # game_id = models.CharField(max_length=500)
    # gamesession_id = models.CharField(max_length=500)
    # bet_id = models.CharField(max_length=500, blank=True, null=True)
    # transaction_id = models.CharField(max_length=500)
    # round_id = models.CharField(max_length=500)
    # device = models.CharField(blank=True, default=None, null=True, choices=DeviceType.choices, max_length=500)
    # request_type = models.CharField(blank=False, choices=RequestType.choices, max_length=500)
    # action_type = models.CharField(blank=False, choices=ActionType.choices, max_length=500)
    # game_status = models.CharField(blank=True, null=True, choices=GameStatus.choices, max_length=500)
    # frbid = models.CharField(max_length=500, blank=True, null=True)
    # time = models.DateTimeField()
    # user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False)
    # amount = models.FloatField()
    # currency = models.CharField(max_length=5, blank=True, null=True)
    # bonus_bet_amount = models.FloatField(default=None, null=True, blank=True)
    # bonus_type = models.CharField(blank=True, default=None, null=True, choices=BonusType.choices, max_length=500)
    # bonus_promo_code = models.CharField(blank=True, default=None, null=True, max_length=500)
    # jp_contribution = models.FloatField(default=None, null=True, blank=True)    
    # completed = models.CharField(max_length=500, null=True, blank=True) 

    callerId = models.CharField(max_length=500, blank=True, null=True)
    withdraw = models.FloatField(null=True,blank=True)
    deposit = models.FloatField(null=True,blank=True)
    currency = models.CharField(max_length=500, blank=True, null=True)
    transaction_id = models.CharField(max_length=500)
    gameroundref = models.CharField(max_length=500, blank=True, null=True)
    game_id = models.CharField(max_length=500,blank=True, null=True)
    source = models.CharField(max_length=500,blank=True, null=True)
    gamesession_id = models.CharField(max_length=500,blank=True, null=True)
    reason = JSONField(default=None, null=True, blank=False)
    sessionalternativeid = models.CharField(max_length=500,blank=True, null=True)
    spinDetails = JSONField(default=None, null=True, blank=False)
    bonusid = models.CharField(max_length=500,blank=True, null=True)
    chargefreerounds =models.IntegerField(null=True, blank=True)
    bet_id = models.CharField(max_length=500, blank=True, null=True)
    round_id = models.CharField(max_length=500, blank=True, null=True)
    device = models.CharField(blank=True, default=None, null=True, choices=DeviceType.choices, max_length=500)
    request_type = models.CharField(blank=False, choices=RequestType.choices, max_length=500)
    action_type = models.CharField(blank=False, choices=ActionType.choices, max_length=500)
    game_status = models.CharField(blank=True, null=True, choices=GameStatus.choices, max_length=500)
    frbid = models.CharField(max_length=500, blank=True, null=True)
    time = models.DateTimeField()
    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False, db_index=True)
    amount = models.FloatField(null=True,blank=True)
    bonus_bet_amount = models.FloatField(default=None, null=True, blank=True)
    bonus_type = models.CharField(blank=True, default=None, null=True, choices=BonusType.choices, max_length=500)
    bonus_promo_code = models.CharField(blank=True, default=None, null=True, max_length=500)
    jp_contribution = models.FloatField(default=None, null=True, blank=True)    
    completed = models.CharField(max_length=500, null=True, blank=True)
    is_tournament_transaction = models.BooleanField(default=False)
    transaction_type = models.CharField(blank=True, null=True, choices=TransactionType.choices, max_length=500)
    
    wr_data = JSONField(null=False, default=dict, blank=False)
    # WR data is a dictionary with the following keys:
    # - "wr_cancel" => Tuple[Decimal, Decimal]
    #   - first value is the amount of the Reactor Coin Consumed
    #   - second value is the amount of SC used to consume that RC
    # - [wr_id] => Tuple[Decimal, Decimal]
    #   - first value is a percentage of the total amount of the bet
    #   - second value is the amount of the WR that was set as played



class PlayerFavouriteCasinoGames(AbstractBaseModel):
    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False)
    game_list = JSONField(default=None, null=True, blank=True)
    fortunepandas_game_list = JSONField(default=list, null=True, blank=True)
    
    
class CasinoManagement(AbstractBaseModel):
    game = models.ForeignKey(CasinoGameList,default=None, on_delete=models.CASCADE, null=True, blank=True, related_name="casino_management")
    enabled = models.BooleanField(default=True, null=True, blank=True)
    game_enabled = models.BooleanField(default=True, null=True, blank=True)
    is_top_pick = models.BooleanField(default=False, null=True, blank=True)
    admin = models.ForeignKey(Admin, on_delete=models.CASCADE,null=True, blank=True)


class CasinoHeaderCategory(AbstractBaseModel):
    name = models.CharField(max_length=500)
    position = models.IntegerField(null=True, blank=True)
    image = models.FileField(upload_to='admin/casino_category_images/', default=None, null=True)
    image_dark = models.FileField(upload_to='admin/casino_category_images/', default=None, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - {self.position}"


class Tournament(AbstractBaseModel):
    # class TournamentPeriod(DjangoChoices):
    #     daily = ChoiceItem("daily", "Daily")
    #     weekly = ChoiceItem("weekly", "Weekly")
    #     monthly = ChoiceItem("monthly", "Monthly")

    games = models.ManyToManyField(CasinoManagement)
    name = models.CharField(max_length=500)
    description = models.TextField()
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    registration_end_date = models.DateTimeField()
    entry_fees = models.DecimalField(
        _("Entry fees"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )
    jackpot_amount = models.DecimalField(
        _("Jackpot amount"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )
    initial_credit = models.DecimalField(
        _("Initial fees"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )
    is_player_limit_enabled = models.BooleanField(default=False, null=True, blank=True)
    min_player_limit = models.IntegerField(null=True, blank=True)
    max_player_limit = models.IntegerField(null=True, blank=True)
    # tournament_period = models.CharField(null=True, blank=True, choices=TournamentPeriod.choices, max_length=500)
    is_rebuy_enabled = models.BooleanField(default=False, null=True, blank=True)
    rebuy_fees = models.DecimalField(
        _("Rebuy fees"), max_digits=15, decimal_places=2, default=0.00, null=True, blank=True
    )
    rebuy_limit = models.IntegerField(default=0, null=True, blank=True)
    image = models.ImageField(upload_to='tournament/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_prize_distributed = models.BooleanField(default=False)


class TournamentPrize(AbstractBaseModel):
    class TournamentPrizeType(DjangoChoices):
        cash = ChoiceItem("cash", "Cash")
        non_cash = ChoiceItem("non_cash", "Non cash")

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, blank=False)
    rank = models.IntegerField(default=0, null=True, blank=True)
    amount = models.DecimalField(
        _("prize amount"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )
    type = models.CharField(null=True, blank=True, choices=TournamentPrizeType.choices, max_length=500)
    non_cash_prize = models.CharField(null=True, blank=True, max_length=500)


class UserTournament(AbstractBaseModel):
    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, blank=False)
    remaining_rebuy_limit = models.IntegerField(default=0, null=True, blank=True)
    points = models.DecimalField(
        _("Points"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )
    spent_points = models.DecimalField(
        _("Spent Points"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )
    win_points = models.DecimalField(
        _("Win Points"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )
    win_prize = models.CharField(_("Win Prize"), null=True, blank=True, max_length=500)
    last_win_at = models.DateTimeField(null=True, blank=True)


class TournamentTransaction(AbstractBaseModel):
    class TransactionType(DjangoChoices):
        credit = ChoiceItem('CREDIT', 'credit')
        bet = ChoiceItem('BET', 'bet')
        win = ChoiceItem('WIN', 'win')
        lose = ChoiceItem('LOSE', 'lose')
        rollback = ChoiceItem('ROLLBACK', 'rollback')

    user = models.ForeignKey(Users, on_delete=models.CASCADE, blank=False)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, blank=False)
    casino_transaction = models.ForeignKey(GSoftTransactions, on_delete=models.CASCADE, null=True, blank=True)
    points = models.DecimalField(
        _("Points"), max_digits=15, decimal_places=2, default=0.00, null=False, blank=False
    )
    type = models.CharField(null=True, blank=True, choices=TransactionType.choices, max_length=500)

