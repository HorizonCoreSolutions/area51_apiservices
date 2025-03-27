import base64
import datetime
import json
import os
import boto3
import uuid
import asyncio
from datetime import timedelta

from django.utils import timezone
from django.db.models import Q, Count, F, Max
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from urllib.parse import parse_qs
from asgiref.sync import sync_to_async

from apps.users.models import CashAppDeatils, ChatHistory, ChatMessage, ChatRoom, Users
from apps.users.utils import send_active_chat_count, send_message_to_chatlist

import time
from apps.casino.models import Tournament


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            self.room_name = self.scope['url_route']['kwargs']['room_name']
            self.room_group_name = 'notification_%s' % self.room_name
            print(self.room_group_name)
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )

            await self.accept()
        except Exception as e:
            print(e)

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    # async def receive(self, text_data):
    #     # text_data_json = json.loads(text_data)
    #     # message = text_data_json['message']
    #     print(f"message == {text_data}")

    #     # Send message to room group
    #     await self.channel_layer.group_send(
    #         self.room_group_name,
    #         {
    #             'type': 'send_notification',
    #             'message': json.dumps(text_data)
    #         }
    #     )

    # Receive message from room group
    async def send_notification(self, event):
        title = json.loads(event['title'])
        message = json.loads(event['message'])
        # Send message to WebSocket
        await self.send(text_data=json.dumps(
            {"title": title, "message":message}
        ))

active_rooms = set() 

class CustomerSupportChat(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            query_params = parse_qs(self.scope['query_string'].decode())
            print(query_params)
            self.room_name = self.scope['url_route']['kwargs']['room_name']
            if query_params.get('player_id'):
                self.player_id = query_params.get('player_id')[0]
                roomname = f'P{self.player_id}Chat'
                chatroom = await sync_to_async(ChatRoom.objects.filter(name=roomname).first)()

                print("CHATROOM ",chatroom)
                if not chatroom:
                    await sync_to_async(ChatRoom.objects.create)(name=roomname)
                    # await self.close(code=401)

            print("SCOPE",self.scope)
            print("USER",self.scope['user'])

            self.room_group_name = self.room_name

            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )

            await self.accept()
            active_rooms.add(self.room_name)
        except Exception as e:
            print("ERROR",e)    

    async def disconnect(self, close_code=None):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        active_rooms.discard(self.room_group_name)

    async def get_chatroom(self, room):
        print("inside get_chatroom")
        chatroom = await sync_to_async(ChatRoom.objects.filter(name=room).first)()
        return chatroom

    async def create_chatroom(self, room):
        chatroom = await sync_to_async(ChatRoom.objects.create)(name=room)
        print("ROOM CREATED", chatroom)
        return chatroom
    
    # async def edit_cashapp_detail(self, cashapp_id, cash_app):
    #     await sync_to_async(CashAppDeatils.objects.filter(id = cashapp_id).update)(name=cash_app)

    # async def delete_cashapp_detail(self, cashapp_id):
    #     await sync_to_async(CashAppDeatils.objects.filter(id = cashapp_id).update)(is_active=False)

    async def create_chat_message(self, chatroom, message, sender,is_file):
        try:
            if is_file:
                file = message
                # Get the file URL using Django's default storage
                message = default_storage.url(message)
            else:
                file=None
            chat_message = ChatMessage(
                room=chatroom,
                message_text=message,
                sent_time=datetime.datetime.now(),
                sender=sender,
                is_file=is_file,
                file = file
            )
            await sync_to_async(chat_message.save)()
            return chat_message
        except Exception as e:
            print("Exception : ",e)

    async def receive(self, text_data):
        is_file = False
        message = json.loads(text_data)

        if message:
            if message.get('type') == 'typing':
                typing_message = message.get('message')
                sender_id = message.get('sender_id')
                is_player_sender = message.get('is_player_sender',False)
            elif message.get('type') == 'offmarket_signup':
                sender_id = message.get('sender_id')
                is_player_sender = message.get('is_player_sender',False)
                username = message.get('username')
                game_code = message.get('game_code')
            elif message.get('type') == 'join_message':
                join_message = message.get('message')
                sender_id = message.get('sender_id')
                is_player_sender = message.get('is_player_sender',False)
            elif message.get('type') == 'end_message':
                end_message = message.get('message')
                sender_id = message.get('sender_id')
                is_player_sender = message.get('is_player_sender',False)
        
            elif message.get('file'):
                file_data  = message['file']
                file_name = file_data.get('name')
                file_type = file_data.get('type')
                file_content = file_data.get('content')
                file_content_decoded = base64.b64decode(file_content)

                try:
                    last_dot_index = file_name.rfind('.')
                    name = file_name[:last_dot_index] 
                    format = file_name[last_dot_index + 1:]
                    file_name = f"{name}_{uuid.uuid4()}.{format}"
                    is_uploaded = await self.upload_file_to_default_storage(file_name,file_content_decoded)
                    if is_uploaded:
                        recevied_message = is_uploaded
                    is_player_sender = file_data.get('is_player_sender',False)
                    sender_id = file_data.get('sender_id')
                    is_file = True
                except Exception as e:
                    print(f"Error uploading file to S3: {e}")
            # elif message.get('type') == 'cashapp_signup':
            #     sender_id = message.get('sender_id')
            #     is_player_sender = message.get('is_player_sender',False)
            #     cash_app = message.get('cash_app')
            
            # elif message.get('type') == 'cashapp_edit':
            #     sender_id = message.get('sender_id')
            #     is_player_sender = message.get('is_player_sender',False)
            #     cash_app = message.get('cash_app')
            #     cashapp_id = message.get('cashapp_id')
            
            # elif message.get('type') == 'cashapp_delete':
            #     sender_id = message.get('sender_id')
            #     is_player_sender = message.get('is_player_sender',False)
            #     cashapp_id = message.get('cashapp_id')

            else:
                recevied_message = message.get('message')
                is_player_sender = message.get('is_player_sender',False)
                sender_id = message.get('sender_id')

        
        if message.get('type') == 'typing':
            await self.channel_layer.group_send(
                self.room_group_name , {
                    "type": "send_notification",
                    "message": json.dumps({
                        "type": "typing",
                        "sender_id": sender_id,
                        "message": typing_message,
                        "is_player_sender" : is_player_sender,
                        "player_id": self.player_id,
                        "sent_time":time.time() ,
                                                                
                })
                }
            )
        elif message.get('type') == 'offmarket_signup':
            await self.channel_layer.group_send(
                self.room_group_name , {
                    "type": "send_notification",
                    "message": json.dumps({
                        "type": "offmarket_signup",
                        "sender_id": sender_id,
                        "username": username,
                        "game_code": game_code,
                        "is_player_sender" : is_player_sender,
                        "player_id": self.player_id,
                        "sent_time":time.time() ,                                                    
                })
                }
            )
        # elif message.get('type') == 'cashapp_signup':
        #     await self.channel_layer.group_send(
        #         self.room_group_name , {
        #             "type": "send_notification",
        #             "message": json.dumps({
        #                 "type": "cashapp_signup",
        #                 "sender_id": sender_id,
        #                 "cash_app": cash_app,
        #                 "is_player_sender" : is_player_sender,
        #                 "player_id": self.player_id,
        #                 "sent_time":time.time(),                                                    
        #         })
        #         }
        #     )
        # elif message.get('type') == 'cashapp_edit':
        #     # await self.edit_cashapp_detail(cashapp_id, cash_app)
        #     await self.channel_layer.group_send(
        #         self.room_group_name , {
        #             "type": "send_notification",
        #             "message": json.dumps({
        #                 "type": "cashapp_edit",
        #                 "sender_id": sender_id,
        #                 "cash_app": cash_app,
        #                 "is_player_sender" : is_player_sender,
        #                 "player_id": self.player_id,
        #                 "sent_time":time.time(), 
        #                 "cashapp_id" : cashapp_id
        #         })
        #         }
        #     )
        # elif message.get('type') == 'cashapp_delete':
        #     # await self.delete_cashapp_detail(cashapp_id)
        #     await self.channel_layer.group_send(
        #         self.room_group_name , {
        #             "type": "send_notification",
        #             "message": json.dumps({
        #                 "type": "cashapp_delete",
        #                 "sender_id": sender_id,
        #                 "cashapp_id": cashapp_id,
        #                 "is_player_sender" : is_player_sender,
        #                 "player_id": self.player_id,
        #                 "sent_time":time.time(),                                                    
        #         })
        #         }
        #     )
        elif message.get('type') == 'join_message':
            await self.channel_layer.group_send(
                self.room_group_name , {
                    "type": "send_notification",
                    "message": json.dumps({
                        "type": "join_message",
                        "sender_id": sender_id,
                        "message": join_message,
                        "is_player_sender" : is_player_sender,
                        "player_id": self.player_id,
                        "sent_time":time.time(),                                                    
                })
                }
            )
        elif message.get('type') == 'end_message':
            await self.channel_layer.group_send(
                self.room_group_name , {
                    "type": "send_notification",
                    "message": json.dumps({
                        "type": "end_message",
                        "sender_id": sender_id,
                        "message": end_message,
                        "is_player_sender" : is_player_sender,
                        "player_id": self.player_id,
                        "sent_time":time.time() ,                                                    
                })
                }
            )
        elif message.get('type') == 'message':

            if is_player_sender:
                message_sender = await self.get_sender(sender_id)
            else:
                message_sender = await self.get_receiver(sender_id)

            chatroom = await self.get_chatroom(self.room_group_name)
            print(self.room_group_name)
            print("receved message", recevied_message)
            if chatroom:
                chat_message = await self.create_chat_message(chatroom, recevied_message, message_sender,is_file)
            else:
                chatroom =  await self.create_chatroom(self.room_group_name)
                chat_message = await self.create_chat_message(chatroom, recevied_message, message_sender,is_file)
            file_extension = None
            if is_file:
                message_text = chat_message.file.name
                file_extension = message_text.split('.')[-1]
            else:
                message_text = chat_message.message_text
            
                
            await self.channel_layer.group_send(
                self.room_group_name , {
                    "type": "send_notification",
                    "message": json.dumps({
                        "type" : "message",
                        "message": message_text,
                        "sender_id": chat_message.sender.id,
                        "sent_time": time.time(),
                        "is_file" : chat_message.is_file,
                        "file_extension" : file_extension,
                        "player_id": self.player_id,
                        "chat_sent_time": chat_message.sent_time.strftime("%Y-%m-%d %H:%M:%S.%f%z"),                                                   
                })
                }
            )
    async def send_notification(self, event):
        message = json.loads(event['message'])
        await self.send(text_data=json.dumps(message))
        
    async def get_sender(self, user_id):
        sender = await sync_to_async(Users.objects.filter(id=user_id).first)()
        print("SENDER ",sender)
        return sender

    async def get_receiver(self, user_id):
        receiver = await sync_to_async(Users.objects.filter(id=user_id).first)()
        print("Receiver ",receiver)
        return receiver
    
    async def upload_file_to_default_storage(self,filename,file_content):
        file_directory = 'csr/chats/'
        file_path = os.path.join(file_directory, filename)
        # Save the file content using Django's default storage
        file_path = default_storage.save(file_path, ContentFile(file_content))
        # Get the file URL using Django's default storage
        # file_url = default_storage.url(file_path)
        file_path = f'{settings.BE_DOMAIN}/media/{file_path}'

        print("FILE PATH",file_path)
        return file_path
    

class ChatListConsumer(AsyncWebsocketConsumer):
    room_name = "chatlist"

    async def connect(self):
        try:
            self.user = None
            query_params = parse_qs(self.scope['query_string'].decode())
            if query_params.get('user_id'):
                self.user_id = int(query_params.get('user_id')[0])
                self.user_id_str = str(self.user_id)
                self.user = await sync_to_async(Users.objects.filter(id=self.user_id).first)()

            if not self.user:
                await self.close(code=401)

            user_id = self.user.id
            self.room_name = f"{self.room_name}_{user_id}"
            self.room_group_name = self.room_name
            
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()

            await self.send_initial_chat_list()
        except Exception as e:
            print("ERROR",e)


    async def send_initial_chat_list(self):
        chats = await self.get_chat_list()
        message = {"message": {"type": "add_new_chats", "chats": chats}}
        await self.send(text_data=json.dumps(message))


    @database_sync_to_async
    def get_chat_list(self):
        chats = []
        if self.user.role in ['staff','agent']:
            chats = ChatRoom.objects.filter(pick_by=None, player__agent__in=[self.user, self.user.agent])
        elif self.user.role == 'admin':
            chats = ChatRoom.objects.filter(pick_by=None, player__admin = self.user)
        else:
            chats = ChatRoom.objects.filter(pick_by=None, player__dealer =self.user)
        
        if chats:
            chats = chats.annotate(
                last_message_timestamp=Max('messages__created'),
                unread_messages_count=Count('messages', filter=Q(messages__is_read=False, messages__sender__role="player"), messages__type =ChatMessage.MessageType.message)
            ).filter(
                ~Q(last_message_timestamp=None),
                last_message_timestamp__gte=timezone.now()-timedelta(hours=72)
            ).order_by("-last_message_timestamp").values(
                "pick_by",
                "unread_messages_count",
                chat_id=F("id"),
                user_id=F("player_id"),
                username=F("player__username"),
            )
        
        return list(chats)


    async def disconnect(self, close_code=None):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        print("disconnecting", close_code)

    
    async def receive(self, text_data):
        await self.channel_layer.group_send(
            self.room_group_name , {
                "type": "chatlist_message",
                "message": text_data
            }
        )

        
    async def chatlist_message(self, event):
        message = json.loads(event["message"])
        pick_by = message.pop("pick_by", None)

        if message.get("type")=="remove_chat_from_list" and pick_by not in [self.user_id, self.user_id_str]:
            await self.send(text_data=json.dumps({"message": message}))
        elif message.get("type")=="re_arrange" and pick_by in [self.user_id, self.user_id_str, None]:
            await self.send(text_data=json.dumps({"message": message}))
        elif message.get("type")=="add_new_chats":
            await self.send(text_data=json.dumps({"message": message}))
            
        await sync_to_async(send_active_chat_count)(self.user_id)


class ChatSupportConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            query_params = parse_qs(self.scope['query_string'].decode())
            self.room_name = self.scope['url_route']['kwargs']['room_name']
            self.room_group_name = self.room_name
            if query_params.get('player_id'):
                self.player_id = query_params.get('player_id')[0]
            self.chatroom = await self.get_or_create_chatroom(self.room_name,self.player_id)
            print("CHATROOM ",self.chatroom)

            if not self.chatroom:
                await self.close(code=401)
            
            
            
            print("SCOPE",self.scope)
            print("USER",self.scope['user'])
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )

            await self.accept()
            await self.channel_layer.group_send(
                    self.room_group_name , {
                        "type": "send_notification",
                        "message": json.dumps({
                            "type": "live_status",
                            "sender_id": self.chatroom.pick_by.id if self.chatroom.pick_by else None,
                            "is_active": True  if (self.chatroom and self.chatroom.pick_by and self.chatroom.pick_by.is_staff_active) else False,
                            "is_player_sender" : False,
                            "player_id": self.player_id,
                            "sent_time":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f%z"),
                            "username": "Admin" if (self.chatroom.pick_by and self.chatroom.pick_by.role == 'admin') else "Agent" if (self.chatroom.pick_by and self.chatroom.pick_by.role == 'agent') else (self.chatroom.pick_by.username if self.chatroom.pick_by else None)

                    })
                    }
                )
            

        except Exception as e:
            print("ERROR",e)


    async def disconnect(self, close_code=None):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )


    async def get_or_create_chatroom(self, room,player_id):
        chatroom = await sync_to_async(ChatRoom.objects.filter(name=room,player_id = player_id).last)()
        if not chatroom:
            chatroom = await sync_to_async(ChatRoom.objects.create)(name=room,player_id = player_id )
            print("ROOM CREATED", chatroom)
        return chatroom


    async def create_chat_message(self, message, sender,is_file, type,tip,tip_user,is_comment = False):
        try:
            if is_file:
                file = message
                # Get the file URL using Django's default storage
                message = default_storage.url(message)
            else:
                file=None
            if tip:
                tip = True
            else:
                tip = False
            if is_comment:
                is_comment = True
            else:
                is_comment = False
            if tip_user:
                chat_message = ChatMessage(
                    room= self.chatroom,
                    message_text= message,
                    sent_time= datetime.datetime.now(),
                    sender= sender,
                    is_file= is_file,
                    file= file,
                    type= type,
                    is_tip = tip,
                    tip_user_id = tip_user,
                    is_comment = is_comment
                )
            else:
                chat_message = ChatMessage(
                    room= self.chatroom,
                    message_text= message,
                    sent_time= datetime.datetime.now(),
                    sender= sender,
                    is_file= is_file,
                    file= file,
                    type= type,
                    is_tip = tip,
                    is_comment = is_comment
                )
            await sync_to_async(chat_message.save)()
            return chat_message
        except Exception as e:
            print("Exception : ",e)

    
    @database_sync_to_async
    def mark_message_as_read(self, is_player_sender):
        if is_player_sender:
            ChatMessage.objects.filter(~Q(sender__role="player"), room=self.chatroom).update(is_read=True)
        else:
            ChatMessage.objects.filter(sender__role="player", room=self.chatroom).update(is_read=True)

    
    @database_sync_to_async
    def is_join_message_created(self, is_player_sender, sender_id):
        if is_player_sender:
            return ChatMessage.objects.filter(sender__role="player", room=self.chatroom, type="join").exists()
        else:
            chat_message = ChatMessage.objects.filter(~Q(sender__role="player"), room=self.chatroom, type="join").first()
            return False if not chat_message or chat_message.sender.id != sender_id else True

    
    async def receive(self, text_data):
        is_file = False
        message = json.loads(text_data)
        if message:
            if message.get('type') == 'typing':
                typing_message = message.get('message')
                sender_id = message.get('sender_id')
                is_player_sender = message.get('is_player_sender',False)
            elif message.get('type') == 'offmarket_signup':
                sender_id = message.get('sender_id')
                is_player_sender = message.get('is_player_sender',False)
                username = message.get('username')
                game_code = message.get('game_code')
            elif message.get('type') == 'join_message':
                join_message = message.get('message')
                sender_id = message.get('sender_id')
                is_player_sender = message.get('is_player_sender',False)
                
            elif message.get('type') == 'mark_message_as_read':
                sender_id = message.get('sender_id')
                is_player_sender = message.get('is_player_sender',False)
            elif message.get('type') == 'live_status':
                sender_id = message.get('sender_id')
                is_player_sender = message.get('is_player_sender',False)
                is_active = message.get('is_active',False)
            elif message.get('file'):
                file_data  = message['file']
                file_name = file_data.get('name')
                file_type = file_data.get('type')
                file_content = file_data.get('content')
                file_content_decoded = base64.b64decode(file_content)
                tip = message.get('is_tip')
                is_comment = message.get('is_comment')
                tip_user = message.get('tip_user')
                try:
                    last_dot_index = file_name.rfind('.')
                    name = file_name[:last_dot_index] 
                    format = file_name[last_dot_index + 1:]
                    file_name = f"{name}_{uuid.uuid4()}.{format}"
                    is_uploaded = await self.upload_file_to_default_storage(file_name,file_content_decoded)
                    if is_uploaded:
                        recevied_message = is_uploaded
                    is_player_sender = file_data.get('is_player_sender',False)
                    sender_id = file_data.get('sender_id')
                    is_file = True
                except Exception as e:
                    print(f"Error uploading file to S3: {e}")
            else:
                recevied_message = message.get('message')
                is_player_sender = message.get('is_player_sender',False)
                sender_id = message.get('sender_id')
                tip = message.get('is_tip')
                tip_user = message.get('tip_user')
                is_comment = message.get('is_comment')

        
        if message.get('type') == 'typing':
            await self.channel_layer.group_send(
                self.room_group_name , {
                    "type": "send_notification",
                    "message": json.dumps({
                        "type": "typing",
                        "sender_id": sender_id,
                        "message": typing_message,
                        "is_player_sender" : is_player_sender,
                        "player_id": self.player_id,
                        "sent_time":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f%z"),                                        
                })
                }
            )
        elif message.get('type') == 'live_status':
                sender_id = message.get('sender_id')
                is_player_sender = message.get('is_player_sender',False)
                await self.channel_layer.group_send(
                    self.room_group_name , {
                        "type": "send_notification",
                        "message": json.dumps({
                            "type": "live_status",
                            "sender_id": sender_id,
                            "is_active": is_active,
                            "is_player_sender" : is_player_sender,
                            "player_id": self.player_id,
                            "sent_time":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f%z"),
                    })
                    }
                )
        elif message.get('type') == 'offmarket_signup':
            message_sender = await self.get_sender(sender_id)
            off_market_message = f"{game_code}-{username}"
            await self.create_chat_message(off_market_message, message_sender, is_file, "offmarket_signup",False,None)
            await self.channel_layer.group_send(
                self.room_group_name , {
                    "type": "send_notification",
                    "message": json.dumps({
                        "type": "offmarket_signup",
                        "sender_id": sender_id,
                        "username": username,
                        "game_code": game_code,
                        "is_player_sender" : is_player_sender,
                        "player_id": self.player_id,
                        "sent_time":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f%z")                                                    
                })
                }
            )
        elif message.get('type') == 'join_message':
            message_sender = await self.get_sender(sender_id)
            if not await self.is_join_message_created(is_player_sender, sender_id):
                await self.create_chat_message(join_message, message_sender, is_file, "join",False,None)

                await self.channel_layer.group_send(
                    self.room_group_name , {
                        "type": "send_notification",
                        "message": json.dumps({
                            "type": "join_message",
                            "sender_id": sender_id,
                            "message": join_message,
                            "is_player_sender" : is_player_sender,
                            "player_id": self.player_id,
                            "sent_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f%z")                                                  
                    })
                    }
                )
            else:
                return
        elif message.get('type') == 'mark_message_as_read':
            await self.mark_message_as_read(is_player_sender)
        elif message.get('type') == 'message':

            if is_player_sender:
                message_sender = await self.get_sender(sender_id)
            else:
                message_sender = await self.get_receiver(sender_id)

            print(self.room_group_name)
            print("receved message", recevied_message)
            chat_message = await self.create_chat_message(recevied_message, message_sender, is_file, "message",tip,tip_user,is_comment)
            file_extension = None
            if is_file:
                message_text = chat_message.file.name
                file_extension = message_text.split('.')[-1]
            else:
                message_text = chat_message.message_text
            
                
            await self.channel_layer.group_send(
                self.room_group_name , {
                    "type": "send_notification",
                    "message": json.dumps({
                        "type" : "message",
                        "message": message_text,
                        "sender_id": chat_message.sender.id,
                        "sent_time": chat_message.sent_time.strftime("%Y-%m-%d %H:%M:%S.%f%z"),
                        "is_file" : chat_message.is_file,
                        "file_extension" : file_extension,
                        "player_id": self.player_id,
                        "is_player_sender" : is_player_sender,
                        "is_tip": chat_message.is_tip,
                        "tip_user":chat_message.tip_user.id if chat_message.tip_user else None,
                        "is_comment":chat_message.is_comment,
                        "user_balance": str((Users.objects.filter(id = self.chatroom.pick_by.id).first()).balance) if self.chatroom.pick_by else None
                    })
                }
            )

        if message.get("type") not in ["mark_message_as_read", "typing",'join_message','offmarket_signup']:
            self.chatroom.refresh_from_db()
            user = await self.get_sender(sender_id)
            await sync_to_async(send_message_to_chatlist)(user,{
                "type": "re_arrange",
                "chat_id": self.chatroom.id,
                "user_id": self.chatroom.player.id,
                "username": self.chatroom.player.username,
                "pick_by": self.chatroom.pick_by.id if self.chatroom.pick_by else None,
            },self.chatroom)


    async def send_notification(self, event):
        message = json.loads(event['message'])
        await self.send(text_data=json.dumps(message))

        
    async def get_sender(self, user_id):
        sender = await sync_to_async(Users.objects.filter(id=user_id).first)()
        print("SENDER ",sender)
        return sender


    async def get_receiver(self, user_id):
        receiver = await sync_to_async(Users.objects.filter(id=user_id).first)()
        print("Receiver ",receiver)
        return receiver
    
    
    async def upload_file_to_default_storage(self,filename,file_content):
        file_directory = 'csr/chats/'
        file_path = os.path.join(file_directory, filename)
        # Save the file content using Django's default storage
        file_path = default_storage.save(file_path, ContentFile(file_content))
        # Get the file URL using Django's default storage
        # file_url = default_storage.url(file_path)
        file_path = f'{settings.BE_DOMAIN}/media/{file_path}'

        print("FILE PATH",file_path)
        return file_path


class BalanceUpdateConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'balance_update'
        try:
            query_params = parse_qs(self.scope['query_string'].decode())
            if query_params.get('player_id'):
                self.player_id = query_params.get('player_id')[0]
                self.player = await sync_to_async(Users.objects.filter(id=self.player_id).first)()
                if not self.player: 
                    await self.close(code=401)

            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
        except Exception as e:
            print("ERROR", e)

    async def disconnect(self, close_code=None):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data=None):
        print("hello")

    async def send_notification(self, event):
        try:
            message = json.loads(event['message'])
            if message['user'] == self.player.id:
                await self.send(text_data=json.dumps(message))
        except Exception as e:
            print("ERROR", e)


class TournamentScoreboardConsumer(AsyncWebsocketConsumer):
    
    async def connect(self):
        try:
            query_params = parse_qs(self.scope['query_string'].decode())
            if query_params.get('tournament_id'):
                self.tournament_id = query_params.get('tournament_id')[0]
                self.tournament = await sync_to_async(Tournament.objects.filter(id=self.tournament_id).first)()
                if not self.tournament: 
                    await self.close(code=401)
                self.room_group_name = f"{self.tournament.id}_scoreboard"

            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
        except Exception as e:
            print("ERROR", e)


    async def disconnect(self, close_code=None):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )


    async def receive(self, text_data=None):
        print("Message Recived on Tornament Scorboard Websocket")


    async def send_notification(self, event):
        try:
            message = json.loads(event['message'])
            await self.send(text_data=json.dumps(message))
        except Exception as e:
            print("ERROR", e)


class ActiveChatCountUpdate(AsyncWebsocketConsumer):
    room_name = "active_chat_count"

    async def connect(self):
        try:
            self.user = None
            query_params = parse_qs(self.scope['query_string'].decode())
            if query_params.get('user_id'):
                self.user_id = int(query_params.get('user_id')[0])
                self.user_id_str = str(self.user_id)
                self.user = await sync_to_async(Users.objects.filter(id=self.user_id).first)()

            if not self.user:
                await self.close(code=401)

            user_id = self.user.id
            self.room_name = f"{self.room_name}_{user_id}"
            self.room_group_name = self.room_name
            
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            
            await self.channel_layer.group_send(
                self.room_group_name , {
                    "type": "send_count",
                    "message": json.dumps({
                        "user":self.user.id,
                    })
                }
            )
        except Exception as e:
            print("ERROR",e)


    @database_sync_to_async
    def get_chat_count(self):
        chats = ChatRoom.objects.filter(    
            Q(pick_by=self.user)|Q(pick_by=None),
            Q(player__agent=self.user.agent) | Q(player__agent=self.user) | Q(player__admin=self.user) | Q(player__dealer=self.user)
        ).annotate(
            last_message_timestamp=Max('messages__created'),
            unread_messages_count=Count('messages', filter=Q(messages__is_read=False, messages__sender__role="player",messages__type =ChatMessage.MessageType.message))
        ).filter(
            ~Q(last_message_timestamp=None),
            last_message_timestamp__gte=timezone.now()-timedelta(hours=72),
            unread_messages_count__gte=1,
        ).order_by("-last_message_timestamp")
        
        return chats.count()


    async def disconnect(self, close_code=None):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        print("disconnecting", close_code)

    
    async def receive(self, text_data):
        await self.channel_layer.group_send(
            self.room_group_name , {
                "type": "send_count",
                "message": text_data
            }
        )

        
    async def send_count(self, event):
        try:
            message = json.loads(event['message'])
            if message['user'] == self.user.id:
                await self.send(text_data=json.dumps({
                    "count": await self.get_chat_count()
                }))
        except Exception as e:
            print("ERROR", e)

