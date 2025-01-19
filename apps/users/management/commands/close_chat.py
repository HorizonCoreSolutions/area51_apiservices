from datetime import timedelta,timezone,datetime
import json
from django.core.management.base import BaseCommand
from apps.payments.models import WithdrawalCurrency
from apps.users.models import ChatHistory, ChatMessage, ChatRoom, Users
import time
from apps.users.models import Queue

# Assuming `last_message.created` is a timezone-naive datetime object
# and you know the timezone it represents, such as 'UTC'




class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        try:
            while True:
                try:
                    chatrooms = ChatRoom.objects.all()
                    for chatroom in chatrooms:
                        chatmessages = ChatMessage.objects.filter(room=chatroom).order_by('created')
                        if chatmessages.exists():
                            last_message = chatmessages.last()
                            last_message_created = last_message.created
                            # Calculate the current time in UTC timezone
                            current_time = datetime.now(timezone.utc)

                            # Calculate the time difference
                            time_difference = current_time - last_message_created
                            if time_difference >= timedelta(minutes=5):
                                message_list = []
                                player,staff = None, None
                                for message in chatmessages:
                                    message_dict = {}
                                    message_dict['sender'] = message.sender.username
                                    message_dict['message'] = message.message_text if  message.is_file == False else message.file.name
                                    message_dict['is_file'] = str(message.is_file)
                                    message_dict['sent_time'] = message.sent_time.strftime("%Y-%m-%d %H:%M:%S.%f%z")
                                    message_list.append(message_dict)

                                    if player == None or staff == None:
                                        user = Users.objects.filter(id=message.sender.id).first()
                                        if user.role =='staff':
                                            staff = user
                                        else:
                                            player = user
                                    
                                message_json = json.dumps(message_list)
                                message_json =  json.loads(message_json)
                                if not player:
                                    player = Users.objects.filter(id = chatroom.name.replace('P', '').replace('Chat', '')).first()
                                ChatHistory.objects.create(chats=message_json,player=player,staff=staff)
                                ChatMessage.objects.filter(room=chatroom).delete()
                                ChatRoom.objects.filter(name=chatroom.name).delete()
                                if player:
                                    Queue.objects.filter(user =player).update(is_remove = False,is_active=False,pick_by = None)
                                print(f"Room Name :{chatroom.name}")
                                print(f"Created Chat History for RoomName {chatroom.name} on {datetime.now()}")
                                print("Sleeping for 15 Mintues")
                        else:
                            player = Users.objects.filter(id = chatroom.name.replace('P', '').replace('Chat', '')).first()
                            if player:
                                Queue.objects.filter(user =player).update(is_remove = False,is_active=False,pick_by = None)
                            ChatRoom.objects.filter(name=chatroom.name).delete()
                    time.sleep(60*5)
                except Exception as e:
                    print("ERROR : ",e)
                    time.sleep(60*5)
              
        except Exception as e:
            print(e)