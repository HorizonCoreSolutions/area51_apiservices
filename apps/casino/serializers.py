import re
from datetime import datetime, timedelta
from django.conf import settings
from apps.users.models import FortunePandasGameManagement, OffMarketGames
from rest_framework import serializers

from apps.bets.models import Transactions
from apps.casino.utils import get_user_tournament_rank
from .models import (CasinoGameList, CasinoHeaderCategory, CasinoManagement, Tournament, TournamentPrize,
    TournamentTransaction, UserTournament)
from .models import CasinoGameList,PlayerFavouriteCasinoGames
from django.contrib.auth.models import AnonymousUser
from django.db.models import Sum,  F, Window
from django.db.models.functions import RowNumber
from django.utils import timezone


MODE_CHOICES = (
    ("demo", "DEMO"),
    ("real_only", "REAL_ONLY"),
    ("real", "REAL"),
)
DEVICE_CHOICES = (
    ("desktop", "desktop"),
    ("mobile", "mobile")
)
LAUNCH_TARGET_CHOICES = (
    ("BLANK", "BLANK"),
    ("SELF", "SELF"),
    ("PARENT", "PARENT"),
    ("TOP", "TOP"),
)
BET_LIMIT_CODE_CHOICES = (
    ("1", "max 30 EUR (300 CNY)"),
    ("2", "max 60 EUR (600 CNY)"),
    ("3", "max 90 EUR (900 CNY)"),
    ("4", "max 120 EUR (1200 CNY)"),
    ("5", "max 240 EUR"),

)
JURISDICTION_CHOICES=(
    ("MT", "Malta Gambling Authority"),
    ("UK", "UK Gambling Commission"),
    ("GG", "Alderney Gambling Control Commission"),
    ("DK", "Denmark Gambling Authority"),
    ("GI", "Gibraltar"),
    ("RO", "Romania"),
    ("SE", "Swedish Gambling Authority"),
    ("PH", "Philippine Amusement and Gaming Corporation (PAGCOR)"),
    ("CW", "Curacao eGaming License"),
)


GAME_TYPES_LIST = ['SLOT_GAMES', "TABLE_GAMES", "INSTANT_WIN", "BINGO_GAMES", "SCRATCH_CARDS",
                   "SHOOTING_GAMES", "CASUAL_GAMES", "VIRTUAL_SPORTS",
                   "VIRTUAL_GAMES", "LIVE_CASINO", "ESPORTS"]


def list_of_string_validation(data):
    for val in data[0].strip('][').split(', ')[0].split(','):
        val = val.replace('"', '')
        if val not in GAME_TYPES_LIST:
            raise serializers.ValidationError("Game Type provided is not a valid game-type")
    return data


def comma_separated_string_validation(data):
    if not re.match(r'^[A-Z]+(,[A-Z]+)*$', data):
        raise serializers.ValidationError("Invalid input format")


class WithdrawAndDepositSerializer(serializers.Serializer):
    txnType = serializers.CharField(required=True)
    txnId = serializers.CharField(required=True)
    playerId = serializers.CharField(required=True)
    gameId = serializers.CharField(required=True)
    roundId = serializers.CharField(required=True)
    currency = serializers.CharField(required=True)
    amount = serializers.FloatField(required=True, min_value=0)
    bonusBetAmount = serializers.FloatField(required=False)
    bonusType = serializers.CharField(required=False)
    bonusPromoCode = serializers.CharField(required=False)
    jpContribution = serializers.FloatField(required=False)
    device = serializers.CharField(required=False)
    clientType = serializers.CharField(required=False)
    clientRoundId = serializers.CharField(required=False)
    category = serializers.CharField(required=False)
    created = serializers.CharField(required=True)
    completed = serializers.CharField(required=True)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class RollbackSerializer(serializers.Serializer):
    betId = serializers.CharField(required=True)
    txnId = serializers.CharField(required=True)
    playerId = serializers.CharField(required=True)
    roundId = serializers.CharField(required=True)
    amount = serializers.FloatField(required=True, min_value=0)
    currency = serializers.CharField(required=True)
    gameId = serializers.CharField(required=True)
    device = serializers.CharField(required=False)
    clientType = serializers.CharField(required=False)
    clientRoundId = serializers.CharField(required=False)
    category = serializers.CharField(required=False)
    created = serializers.CharField(required=True)
    completed = serializers.CharField(required=True)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


# Player Game History API serializer
class PlayerGameHistorySerializer(serializers.Serializer):
    playerId = serializers.CharField(required=True)
    currency = serializers.CharField(required=True, max_length=3)
    country = serializers.CharField(required=True, max_length=2)
    gender = serializers.CharField(required=False, max_length=1)
    birthDate = serializers.DateField(required=False)
    lang = serializers.CharField(required=False, max_length=5)
    timeZone = serializers.CharField(required=False)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


# Game Lobby API serializer
class GameLobbySerializer(serializers.Serializer):
    playerId = serializers.CharField(required=True)
    displayName = serializers.CharField(required=False)
    currency = serializers.CharField(required=True, max_length=3)
    country = serializers.CharField(required=True, max_length=2)
    gender = serializers.CharField(required=False, max_length=1)
    birthDate = serializers.DateField(required=False)
    lang = serializers.CharField(required=True, max_length=5)
    mode = serializers.ChoiceField(required=True, choices=MODE_CHOICES)
    device = serializers.ChoiceField(required=True, choices=DEVICE_CHOICES)
    walletSessionId = serializers.CharField(required=True)
    gameLaunchTarget = serializers.ChoiceField(required=False, choices=LAUNCH_TARGET_CHOICES)
    gameTypes = serializers.ListField(child=serializers.CharField(), validators=[list_of_string_validation], allow_empty=True)
    betLimitCode = serializers.ChoiceField(required=False, choices=BET_LIMIT_CODE_CHOICES)
    jurisdiction = serializers.ChoiceField(required=False, choices=JURISDICTION_CHOICES)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class GameLauncherSerializer(serializers.Serializer):
    gameId = serializers.CharField(required=True)
    playerId = serializers.CharField(required=True, max_length=34)
    displayName = serializers.CharField(required=False, max_length=50)
    currency = serializers.CharField(required=True, max_length=3)
    country = serializers.CharField(required=True, max_length=2)
    gender = serializers.CharField(required=False, max_length=1)
    birthDate = serializers.DateTimeField(required=False)
    lang = serializers.CharField(required=True, max_length=5)
    mode = serializers.ChoiceField(required=True, choices=MODE_CHOICES)
    device = serializers.ChoiceField(required=True, choices=DEVICE_CHOICES)
    returnUrl = serializers.CharField(required=False)
    walletSessionId = serializers.CharField(required=True)
    betLimitCode = serializers.ChoiceField(required=False, choices=BET_LIMIT_CODE_CHOICES)
    jurisdiction = serializers.ChoiceField(required=False, choices=JURISDICTION_CHOICES)
    ipAddress = serializers.CharField(required=False)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class MostPopularGamesSerializer(serializers.Serializer):

    currencies = serializers.CharField(validators=[comma_separated_string_validation], required=True)
    size = serializers.IntegerField(required=False, min_value=1, max_value=50, default=10)
    page = serializers.IntegerField(required=False, default=0)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class GameTransactionSerializer(serializers.Serializer):
    playerId = serializers.CharField(required=True)
    fromDate = serializers.DateTimeField(required=True)
    toDate = serializers.DateTimeField(required=True)
    size = serializers.IntegerField(required=False, min_value=1, max_value=1000, default=500)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass



class GameListSerializer(serializers.ModelSerializer):
    is_favourite = serializers.SerializerMethodField()
 
    class Meta:
        model = CasinoGameList
        fields = ['game_id', 'game_name', 'game_type','game_image', 'game_category','vendor_name', 'is_favourite']


    def get_is_favourite(self, instance):
        user = self.context.get("user")
        if user != AnonymousUser: 
            try:
                player_games = PlayerFavouriteCasinoGames.objects.filter(user=user).first()
                if player_games and instance.game_id in player_games.game_list:
                    return True
            except :
                return False
        return False
    
   
           
           
class CasinoManagementSerializer(serializers.ModelSerializer):
    is_favourite = serializers.SerializerMethodField()
    game_id = serializers.CharField(source='game.game_id')
    game_name = serializers.CharField(source='game.game_name')
    game_type = serializers.CharField(source='game.game_type')
    game_image = serializers.CharField(source='game.game_image')
    game_category = serializers.CharField(source='game.game_category')
    vendor_name = serializers.CharField(source='game.vendor_name')
    enabled = serializers.NullBooleanField()
    game_enabled = serializers.NullBooleanField()

    class Meta:
        model = CasinoManagement
        fields = ['admin', 'enabled','game_enabled', 'game_id', 'game_name', 'game_type', 'game_image', 'game_category', 'vendor_name', 'is_favourite']
    
    def get_is_favourite(self, instance):
        user = self.context.get("user")
        if user != AnonymousUser: 
            try:
                player_games = PlayerFavouriteCasinoGames.objects.filter(user=user).first()
                if player_games and instance.game_id in player_games.game_list:
                    return True
            except :
                return False
        return False
    
class OffMarketGamesSerializer(serializers.ModelSerializer):

    url = serializers.SerializerMethodField()
   
    class Meta:
        model = OffMarketGames
        fields = ['title', 'url','code', 'bonus_percentage', 'game_status', 'coming_soon', 'download_url']

    @staticmethod
    def get_url(obj):
        file_path = obj.url.name
        url =  f'{settings.BE_DOMAIN}/media/{file_path}'
        return url
    

class Casino25GameListSerializer(serializers.ModelSerializer):
    is_favourite = serializers.SerializerMethodField()
    game_image = serializers.SerializerMethodField()
    game_provider = serializers.CharField(source='vendor_name')
 
    class Meta:
        model = CasinoGameList
        fields = ['game_id', 'game_name', 'game_image', 'game_category', "game_provider", 'is_favourite']

    def get_is_favourite(self, instance):
        user = self.context.get("user")
        if user != AnonymousUser: 
            try:
                player_games = PlayerFavouriteCasinoGames.objects.filter(user=user).first()
                if player_games and instance.game_id in player_games.game_list:
                    return True
            except :
                return False
        return False
    
    def get_game_image(self, instance):
        return f"{settings.CASINO_25_IMAGE_URL}/{instance.game_id}.jpg"
    

class Casino25CasinoManagementSerializer(serializers.ModelSerializer):
    is_favourite = serializers.SerializerMethodField()
    game_id = serializers.CharField(source='game.game_id')
    game_name = serializers.CharField(source='game.game_name')
    game_category = serializers.CharField(source='game.game_category')
    game_provider = serializers.CharField(source='game.vendor_name')
    is_mobile_supported = serializers.CharField(source='game.is_mobile_supported')
    is_desktop_supported = serializers.CharField(source='game.is_desktop_supported')
    game_image = serializers.SerializerMethodField()
    enabled = serializers.NullBooleanField()
    game_enabled = serializers.NullBooleanField()
    is_top_pick = serializers.NullBooleanField()

    class Meta:
        model = CasinoManagement
        fields = ['admin', 'enabled','game_enabled', "is_top_pick", 'game_id', 'game_name', 'game_image', 'game_category', "game_provider", 'is_favourite', "is_desktop_supported", "is_mobile_supported"]
    
    def get_is_favourite(self, instance):
        user = self.context.get("user")
        if user != AnonymousUser: 
            try:
                player_games = PlayerFavouriteCasinoGames.objects.filter(user=user).first()
                if player_games and instance.game.game_id in player_games.game_list:
                    return True
            except :
                return False
        return False
    
    def get_game_image(self, instance):
        return f"{settings.CASINO_25_IMAGE_URL}/{instance.game.game_id}.jpg"


class FavouriteCasinoGameListSerializer(serializers.ModelSerializer):
    is_favourite = serializers.SerializerMethodField()
    game_image = serializers.SerializerMethodField()
 
    class Meta:
        model = CasinoGameList
        fields = ['game_id', 'game_name', 'game_type','game_image', 'game_category', 'is_favourite']


    def get_is_favourite(self, instance):
        user = self.context.get("user")
        if user != AnonymousUser: 
            try:
                player_games = PlayerFavouriteCasinoGames.objects.filter(user=user).first()
                if player_games and instance.game_id in player_games.game_list:
                    return True
            except :
                return False
        return False
    
    def get_game_image(self, instance):
        return f"{settings.CASINO_25_IMAGE_URL}/{instance.game_id}.jpg"
    

class FavouriteGameListSerializer(serializers.ModelSerializer):
    is_favourite = serializers.BooleanField(default=True)
    game_id = serializers.CharField(source='game.game_id')
    game_name = serializers.CharField(source='game.game_name')
    game_category = serializers.CharField(source='game.game_category')
    game_image = serializers.SerializerMethodField()
    game_type = serializers.SerializerMethodField()

    class Meta:
        model = FortunePandasGameManagement
        fields = ['admin', 'game_id', 'game_name', 'game_image', 'game_category', "game_type", "is_favourite"]
    
    def get_game_image(self, obj):
        if isinstance(obj, FortunePandasGameManagement):
            return f'{settings.BE_DOMAIN}{obj.game.game_image.url}'
        else:
            return f"{settings.CASINO_25_IMAGE_URL}/{obj.game.game_id}.jpg"
    
    def get_game_type(self, obj):
        if isinstance(obj, FortunePandasGameManagement):
            return "fortunepanda"
        else:
            return "casino"
        

class CasinoHeaderCategorySerializer(serializers.ModelSerializer):
    image_light = serializers.SerializerMethodField()
    image_dark = serializers.SerializerMethodField()

    class Meta:
        model = CasinoHeaderCategory
        fields = ['id', "position", 'name', 'image_light', 'image_dark']
    
    
    def get_image_light(self, instance):
        if instance.image:
            url = instance.image.url 
            return f"{settings.BE_DOMAIN}{url}"
        else:
            None

    def get_image_dark(self, instance):
        if instance.image_dark:
            url = instance.image_dark.url 
            return f"{settings.BE_DOMAIN}{url}"
        else:
            None


class TournamentListSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    is_registered = serializers.SerializerMethodField()
    total_registered_player = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    is_registration_open = serializers.SerializerMethodField()
    supported_device = serializers.SerializerMethodField()

    class Meta:
        model = Tournament
        fields = [
            "id", "name", "start_date", "end_date", "registration_end_date", "is_registration_open", "status", "supported_device",
            "entry_fees", "jackpot_amount" ,"image" ,"is_active", "is_registered", "total_registered_player"
        ]

    def get_image(self, instance):
        return f"{settings.BE_DOMAIN}{instance.image.url}"
    
    def get_is_registered(self, instance):
        return UserTournament.objects.filter(tournament=instance, user=self.context.get("request").user).exists() if self.context.get("request").user.is_authenticated else False
    
    def get_total_registered_player(self, instance):
        return instance.usertournament_set.count()
    
    def get_status(self, instance):
        if instance.end_date < timezone.now():
            return "End"
        elif instance.start_date > timezone.now() and instance.end_date > timezone.now():
            return "Upcoming"
        elif instance.start_date < timezone.now() and instance.end_date > timezone.now():
            return "Live"
        
    def get_is_registration_open(self, instance):
        return instance.registration_end_date > timezone.now()
    
    def get_supported_device(self, instance):
        games = instance.games.all()
        mobile_supported_count = games.filter(game__is_mobile_supported=True).count()
        desktop_supported_count = games.filter(game__is_desktop_supported=True).count()
        if mobile_supported_count > 0 and desktop_supported_count>0:
            return "Universal"
        elif mobile_supported_count > 0 and desktop_supported_count==0:
            return "Mobile"
        
        return "Desktop"


class TournamentPrizeSerializer(serializers.ModelSerializer):
    prize = serializers.SerializerMethodField()

    class Meta:
        model = TournamentPrize
        fields = ["id", "rank", "type", "prize"]

    def get_prize(self, instance):
        return instance.amount if instance.type == "cash" else instance.non_cash_prize


class TournamentDetailSerializer(serializers.ModelSerializer):
    is_player_limit_enabled = serializers.NullBooleanField()
    is_rebuy_enabled = serializers.NullBooleanField()
    image = serializers.SerializerMethodField()
    games = Casino25CasinoManagementSerializer(many=True)
    total_registered_player = serializers.SerializerMethodField()
    scoreboard = serializers.SerializerMethodField()
    tournament_prizes = TournamentPrizeSerializer(source='tournamentprize_set', many=True)
    rebuy_left = serializers.SerializerMethodField()
    is_registered = serializers.SerializerMethodField()
    points = serializers.SerializerMethodField()
    spent_points = serializers.SerializerMethodField()
    win_points = serializers.SerializerMethodField()
    rank = serializers.SerializerMethodField()
    supported_device = serializers.SerializerMethodField()

    class Meta:
        model = Tournament
        fields = [
            "id", "name", "description", "start_date", "end_date", "registration_end_date", "entry_fees", "jackpot_amount", "initial_credit", 
            "supported_device", "is_player_limit_enabled", "min_player_limit", "max_player_limit", "is_rebuy_enabled", "points", "spent_points", "win_points", "rank",
            "rebuy_fees" ,"rebuy_limit", "rebuy_left", "image" ,"is_active", "is_registered", "total_registered_player", "games", "tournament_prizes", "scoreboard",
        ]

    def get_image(self, instance):
        return f"{settings.BE_DOMAIN}{instance.image.url}"
    
    def get_total_registered_player(self, instance):
        return instance.usertournament_set.count()
    
    def get_scoreboard(self, instance):
        user_tournaments = list(instance.usertournament_set.annotate(
            rank=Window(expression=RowNumber(),order_by=[F('win_points').desc(),"last_win_at"])
        ).values(
            "rank",
            "win_points",
            username=F("user__username"),
        ))
        return user_tournaments
    
    def get_is_registered(self, instance):
        return instance.usertournament_set.filter(user=self.context.get("request").user).exists() if self.context.get("request").user.is_authenticated else False
    
    def get_rebuy_left(self, instance):
        if self.context.get("request").user.is_authenticated:
            user_tournament = instance.usertournament_set.filter(user=self.context.get("request").user).first()
            return user_tournament.remaining_rebuy_limit if user_tournament else instance.rebuy_limit
        else:
            return instance.rebuy_limit
        
    def get_points(self, instance):
        if self.context.get("request").user.is_authenticated:
            user_tournament = instance.usertournament_set.filter(user=self.context.get("request").user).first()
            return user_tournament.points if user_tournament else 0
        else:
            return instance.initial_credit
            
    def get_spent_points(self, instance):
        if self.context.get("request").user.is_authenticated:
            user_tournament = self.get_user_tournament(instance)
            return user_tournament.spent_points if user_tournament else 0
        else:
            return 0
            
    def get_win_points(self, instance):
        if self.context.get("request").user.is_authenticated:
            user_tournament = self.get_user_tournament(instance)
            return user_tournament.win_points if user_tournament else 0
        else:
            return 0
        
    def get_rank(self, instance):
        if self.context.get("request").user.is_authenticated:
            user_tournament = self.get_user_tournament(instance)
            return get_user_tournament_rank(user_tournament) if user_tournament else 0
        else:
            return 0
        
    def get_user_tournament(self, instance):
        return instance.usertournament_set.filter(user=self.context.get("request").user).first()
        
    def get_supported_device(self, instance):
        games = instance.games.all()
        mobile_supported_count = games.filter(game__is_mobile_supported=True).count()
        desktop_supported_count = games.filter(game__is_desktop_supported=True).count()
        if mobile_supported_count > 0 and desktop_supported_count>0:
            return "Universal"
        elif mobile_supported_count > 0 and desktop_supported_count==0:
            return "Mobile"
        
        return "Desktop"
        

class TournamentTransactionListSerializer(serializers.ModelSerializer):

    class Meta:
        model = TournamentTransaction
        fields = ["id", "tournament", "points", "type"]


class UserTournamentHistoryListSerializer(serializers.ModelSerializer):
    tournament_name = serializers.SerializerMethodField()
    total_amount_spent = serializers.SerializerMethodField()
    rank = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    prize_type = serializers.SerializerMethodField()

    class Meta:
        model = UserTournament
        fields = ["id", "rank", "tournament_name", "points", "spent_points", "win_points", "win_prize", "total_amount_spent", "image", "end_date", "prize_type"]

    def get_tournament_name(self, instance):
        return instance.tournament.name

    def get_total_amount_spent(self, instance):
        # Total amount spent in register and rebuy
        return Transactions.objects.filter(user=self.context.get("request").user, description__istartswith="tournament", description__icontains=f"{instance.tournament.id}").aggregate(total = Sum("amount")).get("total")
    
    def get_rank(self, instance):
        return get_user_tournament_rank(instance)
    
    def get_image(self, instance):
        return f"{settings.BE_DOMAIN}{instance.tournament.image.url}"
    
    def get_end_date(self, instance):
        return instance.tournament.end_date
    
    def get_prize_type(self, instance):
        return instance.tournament.tournamentprize_set.first().type


class Casino25CategoryWiseGameListSerializer(serializers.Serializer):
    category = serializers.SerializerMethodField()
    games = serializers.SerializerMethodField()
 
    def get_category(self, category):
        return category
    
    def get_games(self, category):
        if self.context.get("user").is_authenticated:
            casino_games = CasinoManagement.objects.filter(
                admin=self.context.get("user").admin, 
                enabled=True, 
                game_enabled=True,
                game__created__lte=timezone.now()-timedelta(hours=48)
            )
            if self.context.get("device_type") == "desktop":
                casino_games = casino_games.filter(game__is_desktop_supported=True)
            else:
                casino_games = casino_games.filter(game__is_mobile_supported=True)
                
            if category.lower() == "top picks":
                games = casino_games.filter(is_top_pick=True)[:20]
            else:
                games = casino_games.filter(game__game_category=category)[:20]
            return Casino25CasinoManagementSerializer(games, many=True).data
        else:
            if category.lower() == "top picks":
                games = CasinoManagement.objects.filter(enabled=True, game_enabled=True,is_top_pick=True)[:20]
                serialized_data = Casino25CasinoManagementSerializer(games, many=True).data
                filtered_data = [{key: game[key] for key in ["game_id", "game_name", "game_image", "game_category", "game_provider", "is_favourite"] if key in game} for game in
                                 serialized_data]
                return filtered_data
            else:
                games = CasinoGameList.objects.filter(game_category=category, created__lte=timezone.now()-timedelta(hours=48))[:20]
                return Casino25GameListSerializer(games, many=True).data
        

class Casino25ProviderWiseGameListSerializer(serializers.Serializer):
    provider = serializers.SerializerMethodField()
    games = serializers.SerializerMethodField()
 
    def get_provider(self, provider):
        return provider
    
    def get_games(self, provider):
        if self.context.get("user").is_authenticated:
            casino_games = CasinoManagement.objects.filter(
                admin=self.context.get("user").admin, 
                enabled=True, 
                game_enabled=True,
                game__created__lte=timezone.now()-timedelta(hours=48),
            )
            if self.context.get("device_type") == "desktop":
                casino_games = casino_games.filter(game__is_desktop_supported=True)
            else:
                casino_games = casino_games.filter(game__is_mobile_supported=True)
                
            games = casino_games.filter(game__vendor_name=provider)[:20]
            return Casino25CasinoManagementSerializer(games, many=True).data
        else:
            games = CasinoGameList.objects.filter(vendor_name=provider, created__lte=timezone.now()-timedelta(hours=48))[:20]
            return Casino25GameListSerializer(games, many=True).data
    
    