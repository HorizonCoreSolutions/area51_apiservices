from django.conf.urls import url

from .views import (Casino25APIView, Casino25CallBackAPIView, Casino25GameList,
    Casino25GameListAdmin, CasinoHeaderCategoryAPIView, GameSearchView, GetBalance, GetCasinoCategory,
    GetCasinoCategoryGameListAdmin, GetCasinoGameList, GetCasinoGameListAdmin,
    GetCasinoProviderGameList, GetCasinoProviderGameListAdmin, GetCasinoProviders,
    GetNewCasinoGameList, GetOffMarketGamesView, GetPlayerOffMarketGamesView,
    GetPlayersFavCasinoGames, ScoreboardApiView, SearchView, TournamentDetailApiView,
    TournamentListApiView, TournamentOptApiView, TournamentTransactionListApiView,
    UpdatePlayersFavCasinoGames, UploadGsoftGames, UserTournamentHistoryListApiView,
    VerifySessions, Casino25CategoryWiseGameList, Casino25ProviderWiseGameList,
    CPGamesQueryBalanceApiView)

app_name = "Casino"

cpgames_urls = [
    url("get", CPGamesQueryBalanceApiView.as_view(), name="cpg_get_balance"),
]

urlpatterns = [
    url(r"^(?P<player_id>\w+)/session", VerifySessions.as_view(), name="verify_session"),
    url(r"^(?P<player_id>\w+)/balance", GetBalance.as_view(), name="get_balance"),
    # url(r"get-casino-games", GetCasinoGameList.as_view(), name="get-casino-games"),
    url(r"get-casino-games", GetCasinoGameList.as_view(), name="get-casino-games"),
    url(r"admin-casino-games", GetCasinoGameListAdmin.as_view(), name="admin-casino-games"),
    # url(r"get-category-casino-games", GetNewCasinoGameList.as_view(), name="get-casino-games"),
    # url(r"admin-category-casino-games", GetCasinoCategoryGameListAdmin.as_view(), name="admin-category-casino-games"),
    url(r"get-category-casino-games", Casino25GameList.as_view(), name="get-casino-games"),
    url(r"admin-category-casino-games", Casino25GameListAdmin.as_view(), name="admin-category-casino-games"),
    url(r"update-favourite-casino-games", UpdatePlayersFavCasinoGames.as_view(), name="update-favourite-casino-games"),
    url(r"get-favourite-casino-games", GetPlayersFavCasinoGames.as_view(), name="get-favourite-casino-games"),
    url(r"get-game-search", GameSearchView.as_view(), name="get-game-search"),
    url(r"game-search", SearchView.as_view(), name="game-search"),
    url(r"upload-games", UploadGsoftGames.as_view(), name="upload-games"),
    url(r"get-casino-vendor", GetCasinoProviders.as_view(), name="get-casino-vendor"),
    url(r"get-provider-casino-games", GetCasinoProviderGameList.as_view(), name="get-casino-games"),
    url(r"admin-provider-casino-games", GetCasinoProviderGameListAdmin.as_view(), name="admin-provider-casino-games"),
    url(r"get-casino-category", GetCasinoCategory.as_view(), name="get-casino-category"),
    url(r"category-wise-games", Casino25CategoryWiseGameList.as_view(), name="category-wise-games"),
    url(r"provider-wise-games", Casino25ProviderWiseGameList.as_view(), name="provider-wise-games"),
    url(r"get-offmarket-games", GetOffMarketGamesView.as_view(), name="get-offmarket-games"),
    url(r"get-player-offmarket-games", GetPlayerOffMarketGamesView.as_view(), name="get-player-offmarket-games"),
    url(r"casino25callback", Casino25CallBackAPIView.as_view(), name="callback-casino25"),
    url(r"casino25", Casino25APIView.as_view(), name="start-game-api"),
    url(r"casino-headers", CasinoHeaderCategoryAPIView.as_view(), name="casino-headers"),
    url(r"tournaments/(?P<pk>\d+)?/$", TournamentDetailApiView.as_view(), name="tournament-detail"),
    url(r"tournaments", TournamentListApiView.as_view(), name="tournaments"),
    url(r"tournament-register", TournamentOptApiView.as_view(), name="tournament-register"),
    url(r"tournament-transactions", TournamentTransactionListApiView.as_view(), name="tournament-transactions"),
    url(r"tournament-history", UserTournamentHistoryListApiView.as_view(), name="tournament-history"),
    url(r"tournament-scoreboard/(?P<pk>\d+)?/$", ScoreboardApiView.as_view(), name="tournament-scoreboard"),
    


]

