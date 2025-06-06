from django.conf.urls import url
from django.urls import path

from .views import GetVerificationLinkView, CallbackAcuitytecView, GetVerifycationStatus

app_name = "acuitytec"


urlpatterns = [
    path('url', GetVerificationLinkView.as_view(), name='get-link'),
    path('callback', CallbackAcuitytecView.as_view(), name='acuitytec-callback'),
    path('verify', GetVerifycationStatus.as_view(), name='acuitytec-verify'),
]
