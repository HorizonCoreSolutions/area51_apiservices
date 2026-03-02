import pytz
from dateutil.parser import parse
import json
from typing import Callable, Dict
from decimal import Decimal
from rest_framework.permissions import IsAuthenticated
import traceback
import uuid
from datetime import datetime, timedelta
import requests
from itertools import chain
from rest_framework.generics import ListAPIView
from django.conf import settings
from django.http.response import HttpResponse
from django.http import JsonResponse
from django.db.models import Count, F, Window, Q, Sum
from django.db import transaction
from django.utils import timezone
from django.db.models.functions import RowNumber

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.casino.custom_pagination import CustomPagination
from apps.casino.models import (CasinoGameList, CasinoHeaderCategory, CasinoManagement, PlayerFavouriteCasinoGames, Providers,
    Tournament, TournamentTransaction, UserTournament, GSoftTransactions)
from apps.core.pagination import PageNumberPagination
from apps.core.permissions import *
from apps.users.models import (FortunePandasGameList, FortunePandasGameManagement, OffMarketGames, OffMarketTransactions,
    Player, UserGames, Users)
from apps.casino.cpgames import CPgames
from apps.casino.casino25 import Casino25
from apps.casino.onegamehub import OneGameHub
from apps.bets.models import CHARGED, DEBIT, Transactions
from apps.bets.utils import generate_reference
from .serializers import (Casino25CasinoManagementSerializer,
    Casino25CategoryWiseGameListSerializer, Casino25GameListSerializer,
    Casino25ProviderWiseGameListSerializer, CasinoHeaderCategorySerializer,
    CasinoManagementSerializer, FavouriteCasinoGameListSerializer,
    FavouriteGameListSerializer, GameListSerializer, GameLobbySerializer,
    GameTransactionSerializer, MostPopularGamesSerializer, OffMarketGamesSerializer,
    PlayerGameHistorySerializer, ProviderSerializer, RollbackSerializer, TournamentDetailSerializer,
    TournamentListSerializer, TournamentTransactionListSerializer,
    UserTournamentHistoryListSerializer, WithdrawAndDepositSerializer)
from .utils import (ValidateRequest,
                    ErrorResponseMsg,
                    return_possible_game_error,
                    GSoftUtils)
from apps.core.utils.network import get_user_ip_from_request, save_request
from .gsoft import GsoftCasino


class GameList(APIView):
    http_method_names = ("get",)

    # permission_classes = [IsPlayer]

    def get(self, request, **kwargs):
        game_list = CasinoGameList.objects.filter(
            modified__date__gte=(datetime.now() - timedelta(hours=12))
        )
        if not game_list:
            gamelist_url = f"{settings.CASINO_BASE_URL}v1/games"
            live_casino_games = []
            try:
                superuser = Users.objects.filter(is_superuser=True).first()
                resp = requests.get(gamelist_url, headers={"Authorization": f"Bearer {superuser.casino_token}"})
                if resp.status_code == 200:
                    game_list = resp.json()
                    if game_list.get("items"):
                        print(game_list.get("items"))
                        live_casino_games = game_list.get("items")
                    CasinoGameList.objects.filter(~Q(vendor_name="CPgames")).delete()
                    CasinoGameList.objects.create(game_list=live_casino_games)
                else:
                    return HttpResponse(json.dumps(resp.json()), status=resp.status_code)
            except:
                return HttpResponse(json.dumps(resp.json()), status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            live_casino_games = game_list.first().game_list
        return HttpResponse(json.dumps(live_casino_games), status=status.HTTP_200_OK)


class GameListCustom(APIView):
    http_method_names = ("get",)

    # permission_classes = [IsPlayer]

    def get(self, request, **kwargs):
        game_type = request.GET.get('game_type', 'slot')
        try:
            game_list = CasinoGameList.objects.first()
            casino_games = []
            if game_list:
                game_list = game_list.game_list
                if game_type == 'slot':
                    casino_games = game_list['slot']
                elif game_type == 'virtual':
                    casino_games = game_list['virtual']
                else:
                    casino_games = game_list['live_casino']
        except:
            return HttpResponse(json.dumps({'msg': 'Game List Not Found'}),
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return HttpResponse(json.dumps(casino_games), status=status.HTTP_200_OK)


class SingleGameWithHash(APIView):
    # permission_classes = [AnyPermissions]
    http_method_names = (
        "post",
        "options",
    )
    permission_classes = [IsPlayer]

    def post(self, request, **kwargs):
        game_id = request.data.get("game_id", None)
        # currency = request.data.get("currency", "EUR")
        country = request.data.get("country", "IN")
        lang = request.data.get("lang", "en_US")
        mode = request.data.get("mode", "real")  # demo/play for fun/real(Three Modes are available)
        device = request.data.get("device", "mobile")  # mobile/Desktop
        player = request.user
        if not player:
            return Response({"msg": "Invalid Player"}, status=status.HTTP_400_BAD_REQUEST)
        if player.callback_key:
            session_id = player.callback_key
        else:
            session_id = str(uuid.uuid4())
            request.user.callback_key = session_id
            request.user.save()
        casino_url = f"{settings.CASINO_BASE_URL}v1/games/{game_id}/launch-url"
        params = {
            "playerId": player.id,
            "currency": player.currency,
            "country": country,
            "lang": lang,
            "mode": mode,
            "device": device,
            "returnUrl": settings.CASINO_EXIT_URL,
            "walletSessionId": session_id
        }
        try:
            superuser = Users.objects.filter(is_superuser=True).first()
            single_game = requests.post(casino_url, headers={"Authorization": f"Bearer {superuser.casino_token}"},
                                        json=params)
            print(f"Api response: {single_game.text}")
            single_game = json.loads(single_game.text, strict=False)
            if "url" in single_game:
                return Response(single_game, status=status.HTTP_200_OK)

            return Response(single_game, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            print(e)
            return Response(
                {"msg": "Casino API response Error"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class VerifySessions(APIView):
    http_method_names = (
        "get",
    )

    def get(self, request, player_id):
        print(f"Initiate Verify Session {request.META}")
        game_id = request.GET.get('gameId', None)

        # Header Properties
        session_id = request.META.get('HTTP_WALLET_SESSION', None)
        pass_key = request.META.get('HTTP_PASS_KEY', None)

        try:
            player = Player.objects.filter(id=player_id).first()

            if not player:
                return Response(ErrorResponseMsg.PLAYER_NOT_FOUND.value, status=status.HTTP_404_NOT_FOUND)

            if not player.is_active:
                return Response(ErrorResponseMsg.ACCOUNT_BLOCKED.value, status=status.HTTP_403_FORBIDDEN)

            obj = ValidateRequest()
            valid_response = obj.validate_request(session_id, pass_key, player)
            if valid_response['status'] == 200:
                response_data = {
                    "balance": float(player.balance),
                    "currency": player.currency
                }
                print(response_data)
            else:
                print(valid_response)
                return Response(valid_response['msg'], status=valid_response['status'])
        except Exception as e:
            return Response(ErrorResponseMsg.UNKNOWN_ERROR.value, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(response_data, status=status.HTTP_200_OK)


class GetBalance(APIView):
    http_method_names = (
        "get",
    )

    def get(self, request, player_id):
        print(f"Initiate Get Balance {request.META}")
        game_id = request.GET.get('gameId', None)
        # Header Properties
        session_id = request.META.get('HTTP_WALLET_SESSION', None)
        pass_key = request.META.get('HTTP_PASS_KEY', None)

        try:
            player = Player.objects.filter(id=player_id).first()

            if not player:
                return Response(ErrorResponseMsg.PLAYER_NOT_FOUND.value, status=status.HTTP_404_NOT_FOUND)

            if not player.is_active:
                return Response(ErrorResponseMsg.ACCOUNT_BLOCKED.value, status=status.HTTP_403_FORBIDDEN)

            obj = ValidateRequest()
            valid_response = obj.validate_request(session_id, pass_key, player, check_session=False)
            if valid_response['status'] == 200:
                response_data = {
                    "balance": float(player.balance),
                    "currency": player.currency
                }
                print(response_data)
            else:
                print(valid_response)
                return Response(valid_response['msg'], status=valid_response['status'])
        except Exception as e:
            return Response(ErrorResponseMsg.UNKNOWN_ERROR.value, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(response_data, status=status.HTTP_200_OK)


# Player Game History API
class PlayerGameHistory(APIView):
    http_method_names = (
        "post",
    )

    def post(self, request, **kwargs):
        validation = PlayerGameHistorySerializer(data=request.data)
        if not validation.is_valid():
            return Response(validation.errors, status=status.HTTP_400_BAD_REQUEST)

        player_id = request.data.get("playerId", None)
        currency = request.data.get("currency", "EUR")
        country = request.data.get("country", "CN")
        gender = request.data.get("gender", None)
        birth_date = request.data.get("birthDate", None)
        lang = request.data.get("lang", None)
        time_zone = request.data.get("timeZone", None)
        url = f"{settings.CASINO_BASE_URL}v1/players/{player_id}/service-url"
        params = {
            "currency": currency,
            "country": country,
            "gender": gender,
            "birthDate": birth_date,
            "lang": lang,
            "timeZone": time_zone
        }
        try:
            superuser = Users.objects.filter(is_superuser=True).first()
            response = requests.post(url, headers={"Authorization": f"Bearer {superuser.casino_token}",
                                                   "Content-type": "application/json",
                                                   "Accept": "text/plain"},
                                     data=json.dumps(params))
            print(f"Api response: {response.text}")
            service_url = json.loads(response.text, strict=False)
            if "url" in service_url:
                return Response(service_url, status=status.HTTP_200_OK)
            return Response(return_possible_game_error(response.status_code, service_url),
                            status=response.status_code)
        except Exception as e:
            print(e)
            return Response(ErrorResponseMsg.UNKNOWN_ERROR.value, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(response, status=status.HTTP_200_OK)


class GameLobby(APIView):
    http_method_names = (
        "post",
    )

    def post(self, request, **kwargs):
        validation = GameLobbySerializer(data=request.data)
        if not validation.is_valid():
            return Response(validation.errors, status=status.HTTP_400_BAD_REQUEST)

        player_id = request.data.get("playerId", None)
        display_name = request.data.get("displayName", "CNY")
        currency = request.data.get("currency", "CN")
        country = request.data.get("country", None)
        gender = request.data.get("gender", None)
        birth_date = request.data.get("birthDate", None)
        lang = request.data.get("lang", None)
        mode = request.data.get("mode", None)
        device = request.data.get("device", None)
        wallet_session_id = request.data.get("walletSessionId", None)
        game_launch_target = request.data.get("gameLaunchTarget", None)
        game_types = request.data.get("gameTypes", None)
        bet_limit_code = request.data.get("betLimitCode", None)
        jurisdiction = request.data.get("jurisdiction", None)

        params = {
            "playerId": player_id,
            "displayName": display_name,
            "currency": currency,
            "country": country,
            "gender": gender,
            "birthDate": birth_date,
            "lang": lang,
            "mode": mode,
            "device": device,
            "walletSessionId": wallet_session_id,
            "gameLaunchTarget": game_launch_target,
            "gameTypes": game_types,
            "betLimitCode": bet_limit_code,
            "jurisdiction": jurisdiction
        }
        url = f"{settings.CASINO_BASE_URL}v1/games/lobby-url"
        try:
            superuser = Users.objects.filter(is_superuser=True).first()
            response = requests.post(url, headers={"Authorization": f"Bearer {superuser.casino_token}"}, json=params)
            print(f"Api response: {response.text}")
            service_url = json.loads(response.text, strict=False)
            if "url" in service_url:
                return Response(service_url, status=status.HTTP_200_OK)
            return Response(return_possible_game_error(response.status_code, service_url),
                            status=response.status_code)
        except Exception as e:
            print(e)
            return Response(ErrorResponseMsg.UNKNOWN_ERROR.value, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(response, status=status.HTTP_200_OK)


# Top Most Popular games
class MostPopularGames(APIView):
    http_method_names = {"get", }

    def get(self, request, **kwargs):
        print("Query Params", request.query_params)
        validation = MostPopularGamesSerializer(data=request.query_params)
        if not validation.is_valid():
            return Response(validation.errors, status=status.HTTP_400_BAD_REQUEST)
        currencies = request.query_params.get("currencies", "EUR")
        size = request.query_params.get("size", 10)
        page = request.query_params.get("page", 0)
        url = f"{settings.CASINO_BASE_URL}v1/games/most-popular?currencies={currencies}&" \
              f"size={size}&page={page}"
        print("URL", url)
        try:
            superuser = Users.objects.filter(is_superuser=True).first()
            response = requests.get(url, headers={"Authorization": f"Bearer {superuser.casino_token}"})
            if response.status_code == 200:
                response = response.json()
            else:
                print(f"Response {response}")
                return Response(return_possible_game_error(response.status_code, response.json()),
                                status=response.status_code)
        except Exception as e:
            print(e)
            return Response(ErrorResponseMsg.UNKNOWN_ERROR.value, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        print("response", response)
        return Response(response, status=status.HTTP_200_OK)


# Getting game transactions for a player or all players from QT platform.
class GameTransaction(APIView):
    http_method_name = {"get"}

    def get(self, request, **kwargs):
        print("Query Params", request.query_params)
        validation = GameTransactionSerializer(data=request.query_params)

        if not validation.is_valid():
            return Response(validation.errors, status=status.HTTP_400_BAD_REQUEST)

        player_id = request.query_params.get("playerId")
        from_date = request.query_params.get("fromDate")
        to_date = request.query_params.get("toDate")
        size = request.query_params.get("size", 500)
        time_zone = request.META.get("Time_Zone", "Asia/Shanghai")
        url = f"{settings.CASINO_BASE_URL}v1/game-transactions?playerId={player_id}&from={from_date}&to={to_date}&size={size}"
        print("url", url)
        try:
            superuser = Users.objects.filter(is_superuser=True).first()
            response = requests.get(url, headers={"Authorization": f"Bearer {superuser.casino_token}",
                                                  "Time-Zone": time_zone})
            if response.status_code == 200:
                response = response.json()
            else:
                print(f"Response Status {response}")
                return Response(return_possible_game_error(response.status_code, response.json()),
                                status=response.status_code)
        except Exception as e:
            print(e)
            return Response(ErrorResponseMsg.UNKNOWN_ERROR.value, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        print("Response", response)
        return Response(response, status=status.HTTP_200_OK)


class GsoftCasinoView(APIView):
    http_method_name = {"get"}

    def get(self, request, **kwargs):
        try:
            print("Query Params", request.query_params)
            request_type = request.query_params.get("request")
            gsoft_caino = GsoftCasino()
            if request_type == "startgame":
                success, response = gsoft_caino.start_game(request.query_params)
            elif request_type == "getaccount":
                success, response = gsoft_caino.get_player_detail(request.query_params)
            elif request_type == "getbalance":
                success, response = gsoft_caino.get_player_balance(request.query_params)
            elif request_type == "wager":
                success, response = gsoft_caino.wager(request.query_params)
            elif request_type == "result":
                success, response = gsoft_caino.result(request.query_params)
            elif request_type == "wagerAndResult":
                success, response = gsoft_caino.wager_and_result(request.query_params)
            elif request_type == "rollback":
                success, response = gsoft_caino.wager_rollback(request.query_params)
            elif request_type == "jackpot":
                success, response = gsoft_caino.jackpot(request.query_params)
            elif request_type == None:
                return JsonResponse(gsoft_caino.error_messages.get("parameter_required"), status=status.HTTP_400_BAD_REQUEST)            
            else:
                return JsonResponse({"success" : False, "message" : "Please provide valid request method name"}, status=status.HTTP_400_BAD_REQUEST)

            # status_code = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
            status_code = status.HTTP_200_OK
            return JsonResponse(response, status=status_code)
        except Exception as e:
            print(e)
            error_message = {
                "code": 1,
                "status": "Technical error",
                "message": "Technical error",
                "apiversion": "1.2"
            }
            return JsonResponse(error_message, status=status.HTTP_200_OK)

class GetCasinoGameList(APIView):
    http_method_name = ["get"]
    permission_classes = (IsFavCasinoEnabled,)

    def get(self, request, **kwargs):
        from .serializers import GameListSerializer
        page = int(request.GET.get('page', 1))
        per_page = 16
        start_index = (page - 1) * per_page
        end_index = page * per_page

        queryset = CasinoGameList.objects.all()
        category_querysets = {}


        for category in queryset.values_list('game_category', flat=True).distinct():
            category_querysets[category] = queryset.filter(game_category=category)[start_index:end_index]


        common_queryset = category_querysets.popitem()[1]
        for category_queryset in category_querysets.values():
            common_queryset = common_queryset.union(category_queryset)

        response = GameListSerializer(common_queryset, many=True, context={'user': request.user})
        return Response({'data': response.data, 'page': page})


class GetCasinoGameListAdmin(APIView):
    http_method_name = ["get"]
    permission_classes = (IsFavCasinoEnabled,)

    def get(self, request, **kwargs):
        from .serializers import CasinoManagementSerializer
        page = int(request.GET.get('page', 1))
        per_page = 16
        start_index = (page - 1) * per_page
        end_index = page * per_page
        queryset = CasinoManagement.objects.filter(admin=request.user.admin)
        category_querysets = {}


        for category in queryset.values_list('game__game_category', flat=True).distinct():
            category_querysets[category] = queryset.filter(game__game_category=category)[start_index:end_index]


        common_queryset = category_querysets.popitem()[1]
        for category_queryset in category_querysets.values():
            common_queryset = common_queryset.union(category_queryset)

        response = CasinoManagementSerializer(common_queryset, many=True, context={'user': request.user})

        return Response({'data': response.data, 'page': page})
class UpdatePlayersFavCasinoGames(APIView):
    """to add/delete fav casino games for each user(FE)."""

    http_method_name = ["post"]
    permission_classes = (IsPlayer,)

    def post(self, request, **kwargs):
        try:
            request_type = self.request.data.get("request")
            game_provider = self.request.data.get("game_provider")
            game_id = self.request.data.get("game_id")

            player, created = PlayerFavouriteCasinoGames.objects.get_or_create(
                user_id=request.user.id,
                defaults={
                    'game_list': [],
                    "fortunepandas_game_list": [],
                },
            )

            if game_provider == "fortunepanda":
                is_game_exists = FortunePandasGameManagement.objects.filter(game__game_id=game_id).exists()
                gamelist = player.fortunepandas_game_list
            else:
                is_game_exists = CasinoGameList.objects.filter(game_id=game_id).exists()
                gamelist = player.game_list

            if not is_game_exists:
                return Response({"msg": "Game do not exists", "status_code": status.HTTP_400_BAD_REQUEST})
            elif request_type == "add":
                if game_id not in gamelist:
                    gamelist.append(game_id)
                    player.save()
                response = {"msg": "Game added to favourite.", "status_code": status.HTTP_201_CREATED}
            elif request_type == "delete":
                if game_id in gamelist:
                    gamelist.remove(game_id)
                    player.save()
                    response = {"msg": "Game is removed from favourites.", "status_code": status.HTTP_201_CREATED}
                else:
                    response = {"msg": "No game is added as favourite.", "status_code": status.HTTP_404_NOT_FOUND}
            else:
                response = {"msg": "Invalid request", "status_code":status.HTTP_404_NOT_FOUND}
            return Response(response)
        except Exception as e:
            print(f"Erro in adding casino fav games {e}.")
            response = {"msg": "Some Internal error.", "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR}
            return Response(response)
        return Response({"msg": "Invalid request", "status_code":status.HTTP_404_NOT_FOUND})


class GetPlayersFavCasinoGames(APIView):
    """to get list of fav casino games for each user(FE)."""

    http_method_name = ["get"]
    permission_classes = (IsPlayer,)
    pagination_class = CustomPagination

    def get(self, request, **kwargs):
        try:
            favourites = PlayerFavouriteCasinoGames.objects.filter(user=self.request.user).first()
            if favourites:
                casino_games = CasinoManagement.objects.filter(game__game_id__in=favourites.game_list).all()
                fortunepandas_games = FortunePandasGameManagement.objects.filter(enabled=True, game__game_id__in=favourites.fortunepandas_game_list).all()
                games = list(sorted(
                    chain(casino_games, fortunepandas_games),
                    key=lambda obj: obj.game.game_name,
                ))
                paginator = self.pagination_class()
                try:
                    result_page = paginator.paginate_queryset(games, request)
                except Exception as e:
                    print(e)
                    return Response({"msg": "Something went Wrong", "status_code": status.HTTP_400_BAD_REQUEST})
                # serializer =  GameListSerializer(result_page, many=True)
                serializer = FavouriteGameListSerializer(result_page, many=True)
                return paginator.get_paginated_response(serializer.data)
            else:
                return Response({"msg": "No favourite games added.", "status_code":status.HTTP_404_NOT_FOUND})
        except Exception as e:
            print(f"Erro in getting fav games {e}.")
            response = {"msg": "Some Internal error.", "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR}
            return Response(response)


class GetNewCasinoGameList(ListAPIView):
    '''accounts/(not-defined)'''
    permission_classes = (IsFavCasinoEnabled,)
    queryset = CasinoGameList.objects.all()
    paginate_by = 20
    pagination_class = PageNumberPagination
    http_method_name = ["get"]
    serializer_class = GameListSerializer

    def get_queryset(self):
        category = self.request.GET.get("category", None)
        vendor = self.request.GET.get("vendor", None)
        search = self.request.GET.get("search", None)


        if category:
            self.queryset = self.queryset.filter(game_category=category)

        if vendor:
            self.queryset = self.queryset.filter(vendor_name=vendor)

        if search:
            self.queryset = self.queryset.filter(game_name__icontains=search)

        return self.queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        context.update({"user": user})

        return context


class GetCasinoCategoryGameListAdmin(ListAPIView):

    # permission_classes = (IsFavCasinoEnabled,)
    queryset = CasinoManagement.objects.all()
    paginate_by = 20
    pagination_class = PageNumberPagination
    http_method_name = ["get"]
    serializer_class = CasinoManagementSerializer

    def get_queryset(self):
        category = self.request.GET.get("category", None)
        vendor = self.request.GET.get("vendor", None)
        search = self.request.GET.get("search", None)


        if category:
            self.queryset = self.queryset.filter(admin=self.request.user.admin,game__game_category=category,enabled=True,game_enabled=True)

        if vendor:
            self.queryset = self.queryset.filter(admin=self.request.user.admin,game__vendor_name=vendor,enabled=True,game_enabled=True)

        if search:
            self.queryset = self.queryset.filter(admin=self.request.user.admin,game__game_name__icontains=search,enabled=True,game_enabled=True)



        return self.queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        context.update({"user": user})

        return context


class GameSearchView(APIView):
    permission_classes = (IsPlayer,)
    serializer_class = CasinoManagementSerializer

    def get(self, request, **kwargs):
        game_name = self.request.query_params.get('game_name')
        category = self.request.query_params.get('category')
        vendor = self.request.query_params.get('vendor')
        if category:
            queryset = CasinoManagement.objects.filter(admin=request.user.admin,game__game_category=category,game_enabled=True)
        if vendor:
            queryset = CasinoManagement.objects.filter(admin=request.user.admin,game__vendor_name=vendor,game_enabled=True)
        if game_name:
            queryset = CasinoManagement.objects.filter(admin=request.user.admin,game__game_name__icontains=game_name,game_enabled=True)
        if len(queryset)<1:
            queryset = []
        response =  CasinoManagementSerializer(queryset,many=True,context={
                'user': request.user })
        return Response(response.data)

class SearchView(APIView):
    serializer_class = GameListSerializer

    def get(self, request, **kwargs):
        game_name = self.request.query_params.get('game_name')
        category = self.request.query_params.get('category')
        vendor = self.request.query_params.get('vendor')
        if category:
            queryset = CasinoGameList.objects.filter(game_category=category)
        if vendor:
            queryset = CasinoGameList.objects.filter(vendor_name=vendor)
        if game_name:
            queryset = CasinoGameList.objects.filter(game_name__icontains=game_name)
        if len(queryset)<1:
            queryset=[]
        response =  GameListSerializer(queryset,many=True,context={
                'user': request.user })
        return Response(response.data)

class UploadGsoftGames(APIView):
    http_method_names = ["post"]
    def post(self, request):
        try:
            game_id = request.data.get('game_id')
            game_name = request.data.get('game_name')

            CasinoGameList.objects.create(
               game_id=game_id,
               game_name=game_name,
               game_type = "STANDARD",
               game_image = "https://s3-eu-west-1.amazonaws.com/marketing-assets-83/games-prod/new/930a1b835a011762f4449da0c3dd645ba465a477/Games Catalog image/image.jpg",
               game_category = "Slots",
               vendor_name = "Spadegaming",
            )
            CasinoManagement.objects.create(
              admin = Users.objects.filter(role='admin').first(),
              enabled = True,
              game_enabled = True,
              game = CasinoGameList.objects.filter(game_id=game_id,game_name=game_name).first()
            )

            return Response({"msg":"success","status_code":status.HTTP_200_OK})

        except Exception as e:
            print(e)

class GetCasinoProviders(APIView):
    """accounts/get-casino-vendor/"""
    http_method_name = ["get"]


    def get(self, request, **kwargs):
        device_type = self.request.GET.get("device", "desktop")

        # Only returns the games that area enables
        casino_games = CasinoGameList.objects.filter(
            casino_management__enabled=True,
            casino_management__game_enabled=True
        ).distinct()

        if device_type == "desktop":
            casino_games =  casino_games.filter(is_desktop_supported=True)
        else:
            casino_games =  casino_games.filter(is_mobile_supported=True)

        casino_providers = casino_games.values("vendor_name").annotate(
            num_games=Count("vendor_name")
        ).order_by("-num_games").values_list("vendor_name", flat=True)

        if not 'img_urls' in self.request.GET:
            return Response(casino_providers, status=status.HTTP_200_OK)

        res_providers = Providers.objects.filter(name__in=casino_providers)
        serializer = ProviderSerializer(res_providers, many=True)
        serialized_data = serializer.data

        existing_names = set(p["name"] for p in serialized_data)

        for vendor_name in casino_providers:
            if vendor_name not in existing_names:
                serialized_data.append({
                    "name": vendor_name,
                    "url": settings.BE_DOMAIN + settings.STATIC_URL + 'casino_images/baw_a51_default.webp'
                })

        return Response(
            {
                "providers" : serialized_data
            }, status=status.HTTP_200_OK
        )


class GetCasinoProviderGameList(APIView):
    http_method_name = ["get"]
    permission_classes = (IsFavCasinoEnabled,)

    def get(self, request, **kwargs):
        from .serializers import GameListSerializer
        vendor = request.query_params.get("vendor")
        casino_games = CasinoGameList.objects.filter(vendor_name=vendor)

        response =  GameListSerializer(casino_games,many=True,context={
                'user': request.user })
        return Response(response.data)

class GetCasinoProviderGameListAdmin(APIView):
    http_method_name = ["get"]
    permission_classes = (IsFavCasinoEnabled,)

    def get(self, request, **kwargs):
        from .serializers import GameListSerializer
        vendor = request.query_params.get("vendor")
        casino_games = CasinoManagement.objects.filter(admin=request.user.admin,game__vendor_name=vendor)

        response =  CasinoManagementSerializer(casino_games,many=True,context={
                'user': request.user })
        return Response(response.data)

class GetCasinoCategory(APIView):
    http_method_name = ["get"]


    def get(self, request, **kwargs):
        device_type = self.request.GET.get("device", "desktop")

        casino_games = CasinoGameList.objects.all()
        if device_type == "desktop":
            casino_games =  casino_games.filter(is_desktop_supported=True)
        else:
            casino_games =  casino_games.filter(is_mobile_supported=True)

        casino_categories = list(casino_games.values("game_category").annotate(
            num_games=Count("game_category")
        ).order_by("-num_games").values_list("game_category", flat=True))

        # if not self.request.user.is_anonymous and CasinoManagement.objects.filter(is_top_pick=True).count() > 1:
        if CasinoManagement.objects.filter(is_top_pick=True).count() > 1:
        #     casino_categories.insert(0, "Top Picks")
            casino_categories.insert(0, "Top Picks")

        return Response(casino_categories)




class GetOffMarketGamesView(APIView):
    permission_classes = ()
    serializer_class = OffMarketGamesSerializer

    def get(self, request, **kwargs):

        search = request.query_params.get("search")

        queryset = OffMarketGames.objects.filter(game_status=True)
        if search:
            queryset = queryset.filter(title__icontains=search)

        weekly_totals = {}
        if request.user.is_authenticated and request.user.role == "player":
            today = timezone.now().date()
            start_of_week = today - timedelta(days=today.weekday())
            aggregated = (
                OffMarketTransactions.objects.filter(
                    user=request.user,
                    status="Completed",
                    transaction_type="WITHDRAW",
                    journal_entry="credit",
                    created__date__gte=start_of_week,
                    created__date__lte=today,
                )
                .values("game_name")
                .annotate(total_amount=Sum("amount"))
            )
            weekly_totals = {
                row["game_name"]: row["total_amount"]
                for row in aggregated
            }

        serializer = OffMarketGamesSerializer(
            queryset,
            many=True,
            context={"weekly_totals": weekly_totals, "request": request},
        )
        return Response(serializer.data)

class GetPlayerOffMarketGamesView(APIView):
    permission_classes = (IsPlayer,)
    serializer_class = OffMarketGamesSerializer

    def get(self, request, **kwargs):
        search = self.request.query_params.get('search')
        user_games = UserGames.objects.filter(user=request.user)
        game_ids = [game.id for game in user_games]
        self.queryset = OffMarketGames.objects.filter(game_status=True,id__in=game_ids)
        if search:
            self.queryset = OffMarketGames.objects.filter(title__icontains=search)

        if len(self.queryset)<1:
            self.queryset = []
        response =  OffMarketGamesSerializer(self.queryset,many=True)
        return Response(response.data)


class Casino25APIView(APIView):
    http_method_name =["post"]
    permission_classes = (IsPlayer,)


    def post(self, request, **kwargs):
        try:
            request_type = request.data.get("method")
            tournament_id = request.data.get("tournament_id")
            user_tournament = None
            game_id = request.data.get("game_id")


            if tournament_id:
                tournament = Tournament.objects.filter(id=tournament_id).first()
                user_tournament = UserTournament.objects.filter(user=self.request.user, tournament=tournament).first()
                if not tournament:
                    return JsonResponse({"success" : False, "message" : "Invalid Tournament ID"}, status=status.HTTP_400_BAD_REQUEST)
                elif not user_tournament:
                    return JsonResponse({"success" : False, "message" : "User not registered in tournament"}, status=status.HTTP_400_BAD_REQUEST)
                elif tournament.usertournament_set.count() < tournament.min_player_limit:
                    return JsonResponse({"success" : False, "message" : f"Minimum player requirement not met. At least {tournament.min_player_limit} players are required to start the tournament"}, status=status.HTTP_400_BAD_REQUEST)
                elif game_id not in list(tournament.games.values_list("game__game_id", flat=True)):
                    return JsonResponse({"success" : False, "message" : f"Game with ID {game_id} not available in the tournament"}, status=status.HTTP_400_BAD_REQUEST)

            casino = Casino25(user=self.request.user, tournament_id=tournament_id, user_tournament=user_tournament, debug=True, request_data=request.data)
            if request_type == "startgame":
                result = (
                    CasinoGameList.objects
                    .filter(game_id=game_id)
                    .values_list(
                        "section_id",
                        "can_clear_sc",
                        "can_bonus_sc",
                    )
                    .first()
                )

                if result is None:
                    return JsonResponse({"success" : False, "message" : "Game not found"}, status=status.HTTP_400_BAD_REQUEST)

                provider, can_clear_sc, can_bonus_sc = result

                if provider == "OneGameHub":
                    one = OneGameHub()
                    success, response = one.start_game(
                        request_param=request.data,
                        ip=get_user_ip_from_request(request=self.request),
                        clear=can_clear_sc,
                        bonus=can_bonus_sc
                    )
                elif provider == "CPgames":
                    cp = CPgames()
                    success, response = cp.start_game(request.data)
                else:
                    success, response = casino.start_game()
            else:
                return JsonResponse({"success" : False, "message" : "Please provide valid request method name"}, status=status.HTTP_400_BAD_REQUEST)
            status_code = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
            # status_code = status.HTTP_200_OK
            return JsonResponse(response, status=status_code)
        except Exception as e:
            print(e)
            return JsonResponse({"success" : False, "message" : "Internal Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ModifyCasinoGamesAPIView(APIView):
    http_method_name = ["post"]
    permission_classes = (IsPlayer,)

    def post(self, request, **kwargs):
        try:
            field = request.data.get("field")
            if field not in ["can_clear_sc", "can_bonus_sc"]:
                return JsonResponse({"success" : False, "message" : "Invalid field"}, status=status.HTTP_400_BAD_REQUEST)
            value = request.data.get("value")
            if value not in ["True", "False"]:
                return JsonResponse({"success" : False, "message" : "Invalid value"}, status=status.HTTP_400_BAD_REQUEST)
            subject = request.data.get("subject")
            if subject not in ["game_id", "vendor_name"]:
                return JsonResponse({"success" : False, "message" : "Invalid subject"}, status=status.HTTP_400_BAD_REQUEST)

            subject_id = request.data.get("subject_id")
            if not subject_id:
                return JsonResponse({"success" : False, "message" : "Subject ID is required"}, status=status.HTTP_400_BAD_REQUEST)
            subject_id = str(subject_id)

            if subject == "game_id":
                games = CasinoGameList.objects.filter(game_id=subject_id)
            else:
                games = CasinoGameList.objects.filter(vendor_name=subject_id)

            if games.count() == 0:
                return JsonResponse({"success" : False, "message" : "Game not found"}, status=status.HTTP_400_BAD_REQUEST)
            
            games.update(**{field: value == "True"})
            return JsonResponse({"success" : True, "message" : "Game modified"}, status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            return JsonResponse({"success" : False, "message" : "Internal Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class Casino25CallBackAPIView(APIView):
    http_method_name = {"post"}

    def post(self, request, **kwargs):
        try:            
            request_type = request.data.get("method")
            playerName = request.data.get("params", {}).get("playerName") if request.data.get("params")  else None

            # if playerName == "102":
            #     with open("requests_log.txt", "a") as log_file:
            #         log_file.write(f"New Request:\n{json.dumps(request.data, indent=4)}\n\n")

            try:
                if "tournament" in playerName:
                    user_id = playerName.split("-")[0]
                    tournament_id = playerName.split("-")[1]
                    user = Users.objects.get(id = user_id)
                    user_tournament = UserTournament.objects.filter(tournament_id=tournament_id, user=user).first()
                else:
                    user = Users.objects.get(id = playerName)
                    tournament_id = None
                    user_tournament = None
            except:
                return JsonResponse({
                    "jsonrpc": 2.0,
                    "id": request.data.get("id", ""),
                    "error": {
                        "code": 1,
                        "message": "ErrInternalErrorCode"
                    }
                }, status=200) 

            casino = Casino25(user=user, tournament_id=tournament_id, user_tournament=user_tournament, debug=True, request_data=request.data)
            if request_type == "withdrawAndDeposit":
                success, response = casino.withdraw_and_deposit()
            elif request_type == "rollbackTransaction":
                success, response = casino.rollback_transaction()
            elif request_type == "getBalance":
                success, response = casino.get_balance()

            else:
                return JsonResponse({"success" : False, "message" : "Please provide valid request method name"}, status=status.HTTP_400_BAD_REQUEST)

            status_code = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
            # status_code = status.HTTP_200_OK
            return JsonResponse(response, status=status_code)
        except Exception as e:
            print(e)
            return JsonResponse({"success" : False, "message" : "Internal Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class Casino25GameList(ListAPIView):
    # permission_classes = (IsFavCasinoEnabled,)
    queryset = CasinoGameList.objects.filter(created__lte=timezone.now()-timedelta(hours=48)).order_by("-created")
    paginate_by = 20
    pagination_class = PageNumberPagination
    http_method_name = ["get"]
    serializer_class = Casino25GameListSerializer

    def get_queryset(self):
        category = self.request.GET.get("category", None)
        provider = self.request.GET.get("provider", None)
        search = self.request.GET.get("search", None)
        device_type = self.request.GET.get("device", "desktop")

        if category:
            self.queryset = self.queryset.filter(game_category=category)
            if category.lower() == 'top picks':
                self.queryset = CasinoGameList.objects.filter(
                    casino_management__is_top_pick=True
                ).distinct().prefetch_related("casino_management")

        if device_type == "desktop":
            self.queryset =  self.queryset.filter(is_desktop_supported=True)
        else:
            self.queryset =  self.queryset.filter(is_mobile_supported=True)

        if provider:
            self.queryset = self.queryset.filter(vendor_name=provider)

        if search:
            self.queryset = self.queryset.filter(game_name__icontains=search)
        return self.queryset


    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        context.update({"user": user})

        return context


class Casino25GameListAdmin(ListAPIView):
    # permission_classes = (IsFavCasinoEnabled, IsPlayer)
    queryset = CasinoManagement.objects.filter(game__created__lte=timezone.now()-timedelta(hours=48), enabled=True, game_enabled=True).order_by("-created")
    paginate_by = 20
    pagination_class = PageNumberPagination
    http_method_name = ["get"]
    serializer_class = Casino25CasinoManagementSerializer

    def get_queryset(self):
        category = self.request.GET.get("category", None)
        provider = self.request.GET.get("provider", None)
        search = self.request.GET.get("search", None)
        device_type = self.request.GET.get("device", "desktop")

        if device_type == "desktop":
            self.queryset = self.queryset.filter(game__is_desktop_supported=True)
        else:
            self.queryset = self.queryset.filter(game__is_mobile_supported=True)


        if category and category.lower() == "top picks":
            self.queryset = self.queryset.filter(admin=self.request.user.admin, is_top_pick=True)
        elif category:
            self.queryset = self.queryset.filter(admin=self.request.user.admin,game__game_category=category)

        if provider:
            self.queryset = self.queryset.filter(admin=self.request.user.admin,game__vendor_name=provider)

        if search:
            self.queryset = self.queryset.filter(admin=self.request.user.admin,game__game_name__icontains=search)

        return self.queryset


    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        context.update({"user": user})

        return context


class CasinoHeaderCategoryAPIView(APIView):
    http_method_name = ["get"]
    serializer_class = CasinoHeaderCategorySerializer

    def get(self, request):
        try:
            categories = CasinoHeaderCategory.objects.filter(is_active=True).order_by("position")
            serializer = self.serializer_class(categories, many=True)
            return Response(serializer.data)
        except Exception as e:
            print(e)
            return Response({"msg":"Internal Error"}, status=500)


class TournamentListApiView(ListAPIView):
    # permission_classes = [IsPlayer]
    queryset = Tournament.objects.filter(is_active=True).order_by("-created")
    pagination_class = PageNumberPagination
    http_method_name = ["get"]
    serializer_class = TournamentListSerializer

    def get_queryset(self):
        tournament_name = self.request.GET.get("tournament_name", None)
        is_registered = self.request.GET.get("is_registered", None)

        self.queryset = self.queryset.filter(end_date__gte=timezone.now())
        if tournament_name:
            self.queryset = self.queryset.filter(name__istartswith=tournament_name)
        if is_registered in [True, 'true'] and self.request.user.is_authenticated:
            user_registered_tournament = UserTournament.objects.filter(user=self.request.user).values_list("tournament_id", flat=True)
            self.queryset = self.queryset.filter(id__in=user_registered_tournament)

        return self.queryset


class TournamentDetailApiView(APIView):
    # permission_classes = [IsPlayer]

    def get(self, request, pk):
        try:
            tournament = Tournament.objects.filter(is_active=True, id=pk).first()
            if not tournament:
                return Response({"message":"Tournament with given ID not found"},404)
            serializer = TournamentDetailSerializer(tournament, context={"request":self.request})
            return Response(serializer.data)
        except Exception as e:
            print(e)
            return Response({"message": "Internal Server Error"}, 500)


class TournamentOptApiView(APIView):
    permission_classes = [IsPlayer]

    def post(self, request):
        try:
            tournament_id = self.request.data.get("tournament_id")
            is_rebuy = self.request.data.get("is_rebuy", False)
            user = self.request.user
            tournament = Tournament.objects.filter(id=tournament_id).first()

            if not tournament:
                return Response({"message":"Tournament with given ID not found"},404)
            elif not tournament.is_active:
                return Response({"message":"Tournament is not active"},400)

            total_registered_user = UserTournament.objects.filter(tournament=tournament).count()
            registered_tournament = UserTournament.objects.filter(tournament=tournament, user=self.request.user).first()

            if is_rebuy:
                if user.balance < tournament.rebuy_fees:
                    return Response({"message":"Insufficient balance"},400)
                elif tournament.start_date > timezone.now():
                    return Response({"message":"Rebuy option will be available once the tournament begins. Please wait for the tournament to start."},400)
                elif not registered_tournament:
                    return Response({"message":"Register in tournament before rebuy"},400)
                elif registered_tournament.remaining_rebuy_limit <= 0:
                    return Response({"message":"Rebuy limit exceed"},400)
                elif not tournament.is_rebuy_enabled:
                    return Response({"message":"Rebuy option is not available"},400)
            else:
                if user.balance < tournament.entry_fees:
                    return Response({"message":"Insufficient balance"},400)
                elif tournament.is_player_limit_enabled and total_registered_user >= tournament.max_player_limit:
                    return Response({"message":"Max player limit reached"},400)
                elif registered_tournament:
                    return Response({"message":"You are already registered in tournament"},400)
                elif timezone.now() > tournament.registration_end_date:
                    return Response({"message":"Registrations are closed for the tournament."},400)

            with transaction.atomic():
                if not is_rebuy:
                    UserTournament.objects.create(
                        user = self.request.user,
                        tournament = tournament,
                        remaining_rebuy_limit = tournament.rebuy_limit,
                        points = tournament.initial_credit,
                    )

                    amount = tournament.entry_fees
                    description = f'Tournament registration by {user.username} - {tournament.id} : {tournament.name}'
                    message = "Tournament registration successful"
                elif is_rebuy:
                    registered_tournament.remaining_rebuy_limit -= 1
                    registered_tournament.points += tournament.initial_credit
                    registered_tournament.save()

                    amount = tournament.rebuy_fees
                    description = f'Tournament rebuy by {user.username} - {tournament.id} : {tournament.name}'
                    message = "Rebuy successful"
                else:
                    return Response({"message": "Invalid request"}, 400)

                previous_balance = user.balance
                user.balance -= amount
                user.save()

                Transactions.objects.create(
                    user = user,
                    amount = amount,
                    journal_entry = DEBIT,
                    status = CHARGED,
                    previous_balance = previous_balance,
                    new_balance = user.balance,
                    description = description,
                    reference = generate_reference(user),
                    bonus_type = "N/A",
                    bonus_amount = 0
                )

                TournamentTransaction.objects.create(
                    user = user,
                    tournament = tournament,
                    points = tournament.initial_credit,
                    type = TournamentTransaction.TransactionType.credit
                )

                return Response({"message":message}, 200)
        except Exception as e:
            print(e)
            return Response({"message": "Internal Server Error"}, 500)


class TournamentTransactionListApiView(ListAPIView):
    permission_classes = [IsPlayer]
    queryset = TournamentTransaction.objects.all().order_by("-created")
    pagination_class = PageNumberPagination
    http_method_name = ["get"]
    serializer_class = TournamentTransactionListSerializer

    def get_queryset(self):
        transaction_type = self.request.GET.get("type")
        queryset = self.queryset.filter(user=self.request.user)
        if transaction_type:
            queryset = queryset.filter(type__iexact=transaction_type)
        return queryset


class UserTournamentHistoryListApiView(ListAPIView):
    permission_classes = [IsPlayer]
    queryset = UserTournament.objects.all().order_by("-created")
    pagination_class = PageNumberPagination
    http_method_name = ["get"]
    serializer_class = UserTournamentHistoryListSerializer

    def get_queryset(self):
        tournament_name = self.request.GET.get("tournament_name")

        queryset = self.queryset.filter(user=self.request.user, tournament__end_date__lte=timezone.now())
        if tournament_name:
            queryset = queryset.filter(tournament__name__istartswith=tournament_name)

        return queryset


class ScoreboardApiView(APIView):
    # permission_classes = [IsPlayer]

    def get(self, request, pk):
        try:
            tournament = Tournament.objects.filter(id=pk).first()
            if not tournament:
                return Response({"message": "Invalid Tournament ID"}, 400)

            user_tournaments = list(tournament.usertournament_set.annotate(
                rank=Window(expression=RowNumber(),order_by=[F('win_points').desc(),"last_win_at"])
            ).values(
                "rank",
                "win_points",
                username=F("user__username"),
            ))
            return Response({"scoreboard": user_tournaments})
        except Exception as e:
            print(e)
            return Response({"message": "Internal Server Error"}, 500)


class Casino25CategoryWiseGameList(ListAPIView):
    # Show games
    # permission_classes = (IsFavCasinoEnabled,)
    paginate_by = 20
    pagination_class = PageNumberPagination
    http_method_name = ["get"]
    serializer_class = Casino25CategoryWiseGameListSerializer

    def get_queryset(self):
        device_type = self.request.GET.get("device", "desktop")

        casino_games = CasinoGameList.objects.all()
        if device_type == "desktop":
            casino_games =  casino_games.filter(is_desktop_supported=True)
        else:
            casino_games =  casino_games.filter(is_mobile_supported=True)

        casino_categories = list(casino_games.values("game_category").annotate(
            num_games=Count("game_category")
        ).filter(num_games__gt=0).order_by("-num_games").values_list("game_category", flat=True))

        # if self.request.user.is_authenticated and CasinoManagement.objects.filter(is_top_pick=True).count() > 1:\
        if CasinoManagement.objects.filter(is_top_pick=True).count() > 1:
        #     casino_categories.insert(0, "Top Picks")
            casino_categories.insert(0, "Top Picks")
            # casino_categories[0] = top_picks.values_list(flat=True)

        return casino_categories

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        result = {data.get("category"):data.get("games") for data in serializer.data}
        return Response(result)

    def get_serializer_context(self):
        device_type = self.request.GET.get("device", "desktop")
        context = super().get_serializer_context()
        user = self.request.user
        context.update({"user": user, "device_type":device_type})

        return context


class Casino25ProviderWiseGameList(ListAPIView):
    permission_classes = (IsFavCasinoEnabled,)
    paginate_by = 20
    pagination_class = PageNumberPagination
    http_method_name = ["get"]
    serializer_class = Casino25ProviderWiseGameListSerializer

    def get_queryset(self):
        device_type = self.request.GET.get("device", "desktop")
        # Todo: REMOVE WHEN MORE PROVIDERS ARE SETUP
        casino_games = CasinoGameList.objects.filter(section_id__in=["CPgames", "OneGameHub"])
        if device_type == "desktop":
            casino_games =  casino_games.filter(is_desktop_supported=True)
        else:
            casino_games =  casino_games.filter(is_mobile_supported=True)

        casino_providers = casino_games.values("vendor_name").annotate(
            num_games=Count("vendor_name")
        ).filter(num_games__gt=0).order_by("-num_games").values_list("vendor_name", flat=True)

        return casino_providers

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        result = {data.get("provider"):data.get("games") for data in serializer.data if len(data.get("games"))>0}
        return Response(result)

    def get_serializer_context(self):
        device_type = self.request.GET.get("device", "desktop")
        context = super().get_serializer_context()
        user = self.request.user
        context.update({"user": user, "device_type":device_type})

        return context


# CPgames_views.py
# NOTE: Guide 3.1 Query Player Balance
# State: Compleated
class CPGamesQueryBalanceApiView(APIView):

    def post(self, request) -> Response:
        data = request.data.copy()
        cp = CPgames()
        if not cp.verify_request(request=data):
            print("CPgames: query balance #Signature error#")
            # Signature error 1111
            response_data = cp.parse_to_message(1111)

            return Response(data=response_data, status=status.HTTP_200_OK)

        try:
            message = json.loads(request.data.get("message"))
            sub_uid = message.get("sub_uid")
            app_id = str(request.data.get('appid', ''))
            response_data = cp.get_user_balance(sub_uid, app_id=app_id)
            return Response(data=response_data, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            # Parameter error: 1110
            data = cp.parse_to_message(1110)
            return Response(data=data, status=status.HTTP_200_OK)


class CPGamesPlacingSettingBetsApiView(APIView):
    @transaction.atomic
    def post(self, request) -> Response:
        cp = CPgames()
        data, local_status = cp.transfer_in_out(data=request.data)
        return Response(data=data, status=local_status)


class CPGamesCancelInOutApiView(APIView):
    @transaction.atomic
    def post(self, request) -> Response:
        cp = CPgames()
        data, local_status = cp.cancel_in_out(data=request.data)
        return Response(data=data, status=local_status)


class CPGamesBetApiView(APIView):
    @transaction.atomic
    def post(self, request) -> Response:
        cp = CPgames()
        data, local_status = cp.place_bet(data=request.data)
        return Response(data=data, status=local_status)


class CPGamesCancelBetApiView(APIView):
    @transaction.atomic
    def post(self, request) -> Response:
        cp = CPgames()
        data, local_status = cp.cancel_bet(data=request.data)
        return Response(data=data, status=local_status)


class CPGamesSettleBetApiView(APIView):
    @transaction.atomic
    def post(self, request) -> Response:
        cp = CPgames()
        data, local_status = cp.settle(data=request.data)
        return Response(data=data, status=local_status)


class OneGameHubApiView(APIView):
    def post(self, request) -> Response:
        save_request(service="OneGameHub", request=request)

        params = request.GET.dict()
        save_request(service="OneGameHub", request=params, is_response=True)

        ogh = OneGameHub()
        ogh_func: Dict[str, Callable] = {
            "cancel": ogh.cancel_bet,
            "win": ogh.win,
            "bet": ogh.place_bet,
            "balance": ogh.get_balance
        }

        run = ogh_func.get(params.get("action", ""),
                           lambda data: (ogh.parse_to_message("ERR001"), 401))

        data, local_status = run(params)
        save_request(service="OneGameHub", request=data, is_response=True)

        return Response(data=data, status=local_status)
