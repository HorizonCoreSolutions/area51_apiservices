"""aqua_security URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf import urls
from django.conf.urls import url
from django.urls import include, path
from django.views.generic import RedirectView
from django.views.static import serve
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions, routers

from apps.admin_panel.views import LoginView, LogoutView, change_language, change_timezone
from apps.bets.views import (
    CasinoTransactionsView,
    TransactionsView,
)
from apps.casino.views import (
    SingleGameWithHash,
    GameListCustom,
    PlayerGameHistory,
    GameLobby,
    MostPopularGames,
    GameTransaction,
    GsoftCasinoView
)
from apps.core.custom_refresh_token import refresh_jwt_token
from apps.core.urls import generate_url, generate_url_desktop
from apps.payments.views import WebhookView
from apps.users.views import (PlayerViewSet,
                              AdminPublicDetailsView,
                              AdminBannerClicksView, GetSocialLinkView,
                              GetFooterLinks)

# Desktop Router

# from rest_framework_jwt.views import refresh_jwt_token


router = routers.DefaultRouter()

schema_view_yasg = get_schema_view(
    openapi.Info(
        title="Snippets API",
        default_version="v1",
        description="Aqua Security backend",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@snippets.local"),
        license=openapi.License(name="BSD License"),
    ),
    validators=["flex"],
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    url(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    # url(r'^$', RedirectView.as_view(url=settings.API_VERSION_URL)),
    url(r"^$", LoginView.as_view(), name="login"),
    generate_url(
        r"swagger/$", schema_view_yasg.with_ui("swagger", cache_timeout=None), name="schema-swagger-ui"
    ),
    generate_url(
        r"swagger(?P<format>\.json|\.yaml)$",
        schema_view_yasg.without_ui(cache_timeout=None),
        name="schema-json",
    ),
    url(r"^jet/dashboard/", include("jet.dashboard.urls", "jet-dashboard")),
    url(r"^jet/", include("jet.urls", "jet")),
    url(r"^login/", LoginView.as_view(), name="login"),
    generate_url(r"api-token-refresh/", refresh_jwt_token, name="refresh-token"),
    url(r"^logout/", LogoutView.as_view(), name="logout"),
    generate_url(r"users/", include(("apps.users.urls", "apps.users"), namespace="users-api")),
    generate_url(r"betslip/", include(("apps.bets.urls", "apps.bets"), namespace="bets-api")),
    generate_url(r"acuitytec/", include(("apps.acuitytec.urls", "apps.acuitytec"), namespace="acuitytec-api")),
    generate_url(r"coinflow/callback", WebhookView.as_view(), name='coinflow-api'),
    url(r"^api-auth/", include("rest_framework.urls", namespace="rest_framework")),
    url(r"^admin/", include(("apps.admin_panel.urls", "apps.admin"), namespace="admin-panel")),
    path("change_language/", change_language, name="change_language"),
    path("change_timzone/", change_timezone, name="change_timezone"),
    # GamePool casino provider views
    url(r"^casino/game-list/", GameListCustom.as_view(), name="game-list"),
    url(r"^casino/single-game/", SingleGameWithHash.as_view(), name="single-game"),
    path("game/history/", PlayerGameHistory.as_view(), name="player-game-history"),
    path("game/lobby/", GameLobby.as_view(), name="player-game-lobby"),
    path("game/most-popular/", MostPopularGames.as_view(), name="most-popular-game"),
    path("game/transactions/", GameTransaction.as_view(), name="game-transactions"),
    url(r"^accounts/", include(("apps.casino.urls", "apps.casino"), namespace="casino-api")),
    url(r"^payments/", include(("apps.payments.urls", "apps.payments"), namespace="pix_payment_apis")),
    url(r"^admin_public_details/", AdminPublicDetailsView.as_view(), name="admin-public-details"),
    url(r"^adminbanner-clicks/", AdminBannerClicksView.as_view(), name="adminbanner-clicks"),


    url(r'^ckeditor/', include('ckeditor_uploader.urls')),
    url(r'^social-links/', GetSocialLinkView.as_view(), name="social-links"),
    url(r'^footer-links/', GetFooterLinks.as_view(), name="footer-links"),
    url(r'^GSoft/', GsoftCasinoView.as_view(), name="gsoft-casino"),
    url(r'^tinymce/', include('tinymce.urls')),

    path('', include('django_prometheus.urls')),
]


# urlpatterns.append(path('admin/', admin.site.urls),),

if settings.LOCAL:
    import debug_toolbar
    from django.conf.urls.static import static

    urlpatterns += [url(r"^debug/", include(debug_toolbar.urls))]
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

router = routers.DefaultRouter()
router.register(r"players", PlayerViewSet, base_name="users")
router.register(r"transactions", TransactionsView, base_name="transactions")
router.register(r"casino-transactions", CasinoTransactionsView, base_name="casino_transactions")


urlpatterns.append(generate_url("", include(router.urls)))

# Desktop Urls
