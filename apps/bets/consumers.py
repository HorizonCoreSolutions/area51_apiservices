import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer, JsonWebsocketConsumer

from apps.users.models import Player


class MarketDeltaConsumer(JsonWebsocketConsumer):
    group_name = 'players'

    def connect(self):
        print("CONECTED!!!!!!!!!!!!!!!!!!!!")
        async_to_sync(self.channel_layer.group_add)(
            self.group_name,
            self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        print("Closed websocket with code: ", close_code)
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name,
            self.channel_name
        )
        self.close()

    # Receive message from WebSocket
    def receive(self, text_data):
        print('received message')
        # Send message to room group
        # async_to_sync(self.channel_layer.group_send)(
        #     self.group_name,
        #     {
        #         'type': 'chat_messages',
        #         'message': message
        #     }
        # )

        self.send_json(text_data)

    def market_delta(self, event):
        self.send_json(
            {
                'type': 'market.delta',
                'content': event['content']
            }
        )

    # Receive message from room group
    def chat_message(self, event):
        print("zzzzzzzzzzzzzzzzzzzzzzzz")

        message = event['message']

        # Send message to WebSocket
        self.send(text_data=json.dumps({
            'message': message
        }))

        self.send_json(
            {
                'type': 'players.event',
                'content': event['content']
            }
        )


class SinglePlayerConsumer(JsonWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_name = None

    def connect(self):
        url_route = self.scope.get("url_route")
        if url_route:
            player_username = url_route.get("kwargs", {}).get("player_slug")
            if player_username and Player.objects.filter(username=player_username).exists():
                self.group_name = player_username
                print("CONECTED SINGLE_______________________")
                async_to_sync(self.channel_layer.group_add)(
                    self.group_name,
                    self.channel_name
                )
                self.accept()
                return
        self.close()

    def disconnect(self, close_code):
        print("Closed SINGLE websocket with code: ", close_code)
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name,
            self.channel_name
        )
        self.close()

    # Receive message from WebSocket
    def receive(self, text_data):
        print('received message')
        print(text_data)
        # Send message to room group
        # async_to_sync(self.channel_layer.group_send)(
        #     self.group_name,
        #     {
        #         'type': 'chat_messages',
        #         'message': message
        #     }
        # )
        print("Received event: {}".format(text_data))

    def player_message(self, event):
        self.send_json(
            {
                'type': 'player.message',
                'content': event['content']
            }
        )

