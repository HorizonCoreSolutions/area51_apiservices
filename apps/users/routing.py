from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/notifications/(?P<room_name>\w+)/$', consumers.NotificationConsumer),
    # re_path(r'ws/cschat/(?P<room_name>\w+)/$', consumers.CustomerSupportChat),
    re_path(r'ws/cschat/(?P<room_name>\w+)/$', consumers.ChatSupportConsumer),
    re_path(r'ws/chatlist/$', consumers.ChatListConsumer),

    re_path(r'ws/getplayerbalance/$', consumers.BalanceUpdateConsumer),
    re_path(r'ws/tournament_scoreboard/$', consumers.TournamentScoreboardConsumer),
    re_path(r'ws/active_chat_count/$', consumers.ActiveChatCountUpdate),
    

]
