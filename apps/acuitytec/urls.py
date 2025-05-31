from django.conf.urls import url
from django.urls import path

from .views import GetVerificationLinkView

app_name = "acuitytec"


urlpatterns = [
    path('url', GetVerificationLinkView.as_view(), name='get-link')
]
