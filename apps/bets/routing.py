# chat/routing.py
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<room_name>\w+)/$', consumers.MarketDeltaConsumer),
    re_path(r'ws/socket.io/$', consumers.MarketDeltaConsumer),
    re_path(r'socket.io/$', consumers.MarketDeltaConsumer),
    re_path(r'ws/(?P<player_slug>\w+)/$', consumers.SinglePlayerConsumer),
]