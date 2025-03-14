import binascii
from decimal import Decimal
import hashlib
import random
import string
import redis
import json
import base64
import traceback
from Crypto.Cipher import AES
from Crypto import Random

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from django.conf  import settings
from django.db import transaction
from django.db.models import F, Q, Count, Value, CharField, Window
from django.db.models.functions import Concat, DenseRank, RowNumber

from apps.bets.models import Transactions
from apps.bets.utils import generate_reference
from apps.users.models import ChatRoom, OffMarketGames, OffMarketTransactions, Users
from apps.casino.models import Tournament, UserTournament
from apps.casino.utils import get_user_tournament_rank

redis_client = redis.Redis(host=settings.REDIS_HOST,port=settings.REDIS_PORT,db=0)




def create_otp(cache_key=None):
    otp = ''.join(random.choice(string.digits) for _ in range(6))
    cache_key = hashlib.sha256(otp.encode()).hexdigest()
    redis_client.set(cache_key, otp, ex=600)
    return otp

def create_otp_password(username,cache_key=None):
    generated_otp =''.join(random.choice(string.digits) for _ in range(6))
    otp = username + generated_otp
    cache_key = hashlib.sha256(otp.encode()).hexdigest()
    redis_client.set(cache_key, otp, ex=600)
    return generated_otp


def check_otp(otp):
    try:
        cache_key = hashlib.sha256(otp.encode()).hexdigest()
        correct_otp = redis_client.get(cache_key)
        if not correct_otp:
            return False
        if otp != correct_otp.decode():
            return False
        try:
            redis_client.delete(cache_key)
        except Exception as e:
            print(f"Redis OTP delete exception: {e}")
        return True
    except Exception as e:
        print("Check OTP Exception", e)
        return False





refuj_key = settings.ENCRYPTION_KEY

def encrypt(data: dict) -> str:
    global refuj_key
    data_json_64 = base64.b64encode(json.dumps(data).encode('ascii'))
    try:
        key = binascii.unhexlify(refuj_key)
        iv = Random.get_random_bytes(AES.block_size)
        cipher = AES.new(key, AES.MODE_GCM, iv)
        encrypted, tag = cipher.encrypt_and_digest(data_json_64)
        encrypted_64 = base64.b64encode(encrypted).decode('ascii')
        iv_64 = base64.b64encode(iv).decode('ascii')
        tag_64 = base64.b64encode(tag).decode('ascii')
        json_data = {'iv': iv_64, 'data': encrypted_64, 'tag': tag_64}
        return base64.b64encode(json.dumps(json_data).encode('ascii')).decode('ascii')
    except:  # noqa
        return ''
    
@transaction.atomic
def refund_transactions(id):
            try:  
                transaction = OffMarketTransactions.objects.filter(id=id).first()
                user=transaction.user
                game = OffMarketGames.objects.filter(title=transaction.game_name_full).first()
                try:
                    OffMarketTransactions.objects.update_or_create(
                                user = user,
                                amount = transaction.amount-transaction.bonus,
                                game_name = transaction.game_name,
                                status = 'Completed',
                                transaction_type = "REFUND",
                                journal_entry = 'debit',
                                description = f'refund for Failed deposit amount {transaction.amount}',
                                game_name_full = game.title
                                ) 
                except Exception as e:
                    print(e)
            except Exception as e:
                print(e)


def send_message_to_chatlist(user, message, chat_room=None):
    if user.role == 'player':
        # only 're_arrange' type message recived from player side
        if chat_room and chat_room.pick_by:
            room_group_name = f"chatlist_{chat_room.pick_by.id}"
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'chatlist_message',
                    'message': json.dumps(message),
                }
            )
        else:
            users = Users.objects.filter(
                Q(id = user.admin.id) | Q(id = user.dealer.id, role="dealer") | Q(id = user.agent.id, role="agent") | Q(agent = user.agent, role="staff"),
                is_staff_active = True
            )
            for administrative_user in users:
                room_group_name = f"chatlist_{administrative_user.id}"
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    room_group_name,
                    {
                        'type': 'chatlist_message',
                        'message': json.dumps(message),
                    }
                )
    else:
        # message of types 're_arrange', 'add_new_chats' and 'remove_chat_from_list' received from administrator side
        if message.get("type") == "remove_chat_from_list":
            chat_id = message.get("chat_id")
            chatroom = ChatRoom.objects.filter(id=chat_id).last()
            player = chatroom.player
            room_group_names = list(Users.objects.filter(
                ~Q(id=chatroom.pick_by.id),
                Q(id = player.admin.id) | Q(id = player.dealer.id, role="dealer") | Q(id = player.agent.id, role="agent") | Q(agent = player.agent, role="staff"),
                is_staff_active = True
            ).annotate(
                room_group_name=Concat(Value('chatlist_'), F('id'), output_field=CharField())
            ).values_list("room_group_name", flat=True))

            for room_group_name in room_group_names:
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    room_group_name,
                    {
                        'type': 'chatlist_message',
                        'message': json.dumps(message),
                    }
                )
            return
        elif message.get("type") == "re_arrange":
            room_group_name = f"chatlist_{chat_room.pick_by.id}"
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'chatlist_message',
                    'message': json.dumps(message),
                }
            )
            return

        # Handle type 'add_new_chats'
        if user.role == 'admin':
            users = Users.objects.filter(
                admin_id = user.id,
                is_staff_active = True,
                role__in = ["dealer", "agent", "staff"]
            )
        elif user.role == 'dealer':
            users = Users.objects.filter(
                Q(id = user.admin.id) | Q(dealer = user.dealer, role="agent") | Q(dealer=user, role="staff"),
                is_staff_active = True
            )
        elif user.role == 'agent':
            users = Users.objects.filter(
                Q(id = user.admin.id) | Q(id = user.dealer.id, role="dealer") | Q(agent = user, role="staff"),
                is_staff_active = True
            )
        elif user.role == "staff":
            users = Users.objects.filter(
                Q(id = user.admin.id) | Q(id = user.dealer.id, role="dealer") | Q(id = user.agent.id, role="agent"),
                is_staff_active = True
            )

        for administrative_user in users:
            chat_rooms_id = message.get("chat_rooms_id")
            chatlist = ChatRoom.objects.filter(
                Q(player__admin=administrative_user)|Q(player__dealer=administrative_user)|Q(player__agent__in=[administrative_user, administrative_user.agent]),
                id__in=chat_rooms_id
            ).annotate(
                unread_messages_count=Count('messages', filter=Q(messages__is_read=False, messages__sender__role="player"))
            ).values(
                "pick_by",
                "unread_messages_count",
                chat_id=F("id"),
                user_id=F("player_id"),
                username=F("player__username"),
            )

            if chatlist.count() > 0:
                message_to_send = {
                    "type": "add_new_chats",
                    "chats": list(chatlist)
                }
                room_group_name = f"chatlist_{administrative_user.id}"
                
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    room_group_name,
                    {
                        'type': 'chatlist_message',
                        'message': json.dumps(message_to_send),
                    }
                )


def send_live_status_to_player(user, chatlist):
    for chat in chatlist:
        room_group_name = f"P{chat.get('user_id')}Chat"
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'send_notification',
                'message':json.dumps({
                            "type": "live_status",
                            "sender_id": user.id,
                            "is_active": user.is_staff_active,
                            "is_player_sender" : False,
                            "player_id": chat.get("user_id"),
                            "username":user.username
                    })
            }
        )


def send_player_balance_update_notification(user, user_tournament=None):
    try:
        room_group_name = "balance_update"
        user.refresh_from_db()
        channel_layer = get_channel_layer()

        if user_tournament:
            message = {
                "type": "tournament_balance",
                "user": user.id,
                "points": float(user_tournament.points),
                "win_points": float(user_tournament.win_points),
                "spent_points": float(user_tournament.spent_points),
            }
        else:
            message = {
                "type": "balance",
                "user": user.id,
                "bonus_balance": float(user.bonus_balance),
                "withdrawable_balance": float(user.balance),
                "total": float(user.bonus_balance) + float(user.balance)
            }

        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'send_notification',
                'message':json.dumps(message)
            }
        )
    except Exception as e:
        print("Error in send_player_balance_update_notification", e)
        print(traceback.format_exc())


def decimal_serializer(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError("Object of type {} is not JSON serializable".format(type(obj)))


def update_tournament_scorboard(tournament: Tournament, user_tournament: UserTournament):
    room_group_name = f"{tournament.id}_scoreboard"
    channel_layer = get_channel_layer()
    
    user_tournaments = list(tournament.usertournament_set.annotate(
        rank=Window(expression=RowNumber(),order_by=[F('win_points').desc(),"last_win_at"])
    ).values(
        "rank",
        "username",
        "win_points",
        username=F("user__username"),
    ))


    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': 'send_notification',
            'message':json.dumps({
                "type": "scorboard_update",
                "tournament": tournament.id,
                "scoreboard": user_tournaments,
                # "scoreboard":user_tournaments
            }, default=decimal_serializer)
        }
    )

def send_active_chat_count(user_id):
    room_group_name = "active_chat_count"
    channel_layer = get_channel_layer()
    
    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            "type": "send_count",
            "message": {
                "user":user_id
            }
        }
    )

def is_only_one(a: bool, b: bool, c: bool) -> bool:
    return (a + b + c) == 1
