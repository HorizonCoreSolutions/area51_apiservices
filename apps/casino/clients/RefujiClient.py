import random
import string
import secrets
import requests
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from typing import Optional, Tuple
from apps.users.utils import encrypt
from apps.casino.tasks import task_update_offmarket_transaction
from apps.admin_panel.utils import off_market_refund_transactions
from apps.users.models import OffMarketGames, OffMarketTransactions, UserGames, Users


def generate_deposit_id(username: str, length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    rand_part = ''.join(secrets.choice(alphabet) for _ in range(length))
    return f"#{username}{rand_part}".upper()


@transaction.atomic
def deposit(
    user: Users,
    game_code: str,
    amount: Decimal,
    promo_code: Optional[str],
    force_update: bool = False,
) -> Tuple[bool, Optional[str]]:
    """Deposit transaction on refuji api

    Args:
        user (Users): User which credit will be reducted from
        game_code (str): game code
        amount (Decimal): amount in USD
        force_update (bool): Only for admin porpuses
        promo_code (Optional[str]): Promo code, only for users

    Returns:
        Tuple[bool, Optional[str]]: success, "error message"
    """
    user = Users.objects.select_for_update().get(id=user.id)
    game = OffMarketGames.objects.filter(code=game_code).first()
    user_game = UserGames.objects.filter(game=game,user=user).first()

    if not (user and game and user_game):
        return False, "Game or account not found"
    
    username = user.username or ""

    deposit_id = generate_deposit_id(username=username)
    bonus_amount = (Decimal(game.bonus_percentage) / 100) * amount
    total_amount = bonus_amount + amount
    
    request_payload = {
        "deposit_id": deposit_id,
        "gaming_site": game_code,
        "amount": str(amount),
        "bonus": str(bonus_amount),
        "secret_key": settings.OFF_MARKET_SECRETKEY,
        **( {
            "api_username": encrypt(game.game_user),
            "api_password": encrypt(game.game_pass),
        } if game.is_api_prefix else {
            "game_user": encrypt(game.game_user),
            "game_pass": encrypt(game.game_pass),
        }),
        "customer_username": user_game.username,
        "area51_username" : encrypt(username),
    }

    messages = ['Promo Code Is Invalid',
                'Promo Code Expired',
                'Promo Code Already Claimed']

    if promo_code is not None:
        request_payload.update({
            "promo_code" : promo_code,
            "username" : encrypt("a51" + (user.username or ""))
            # Usuario de area51
        })

    try:
        response = requests.post(
            url=settings.OFFMARKET_API_URL + 'add_credit',
            json=request_payload,
            timeout=30,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
        )
    except Exception as e:
        return False, "Service is not available. Please try again later."
        

    if response.status_code != 201:
        try:
            message = response.json().get("message")
            return False, message
        except ValueError:
            return False, "Request Not Processed"
    
    user.balance = user.balance - Decimal(amount) 
    user.save()

    deposit = OffMarketTransactions()
    deposit.user = user
    deposit.amount = total_amount
    deposit.status = 'Pending'
    deposit.txn_id = deposit_id
    deposit.game_name = game_code
    deposit.journal_entry = 'credit'
    deposit.transaction_type = 'DEPOSIT'
    deposit.description = f'deposit {amount} by {user.username} in game {game_code}'
    deposit.game_name_full = game.title
    deposit.bonus = bonus_amount
    deposit.save()
    
    if force_update:
        complete_request_payload = {
            "deposit_id": deposit_id,
            "status": "Completed",
            "secret_key": settings.OFF_MARKET_SECRETKEY,
        }
        response = requests.put(
            settings.OFFMARKET_API_URL + 'update',
            params=complete_request_payload,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            }
        )
        if response.status_code == 200:
            deposit.status="Completed"
            deposit.save()

    task_update_offmarket_transaction.apply_async(
        args=[deposit.id],  # type: ignore
        countdown=19
    )  # type: ignore
    return True, None


def withdraw():
    pass

@transaction.atomic
def create_user(
    player_id: int,
    game_code: str,
    username: str,
    create_on_refuji: bool = False
) -> Tuple[bool, Optional[str]]:
    """Create a new game account for a player.

    Args:
        player_id (int): ID of the player (Users.id)
        game_code (str): Game code from OffMarketGames
        username (str): Desired username for the account

    Returns:
        Tuple[bool, Optional[str]]: success, error message
    """

    if len(username) < 5:
        return False, "Username must be greater than 5 characters"

    game = OffMarketGames.objects.filter(code=game_code).first()
    if not game:
        return False, "Game does not exist"

    if UserGames.objects.filter(game=game, username=username).exists():
        return False, "Username already exists"

    player = Users.objects.filter(id=player_id).first()
    if not player:
        return False, "Player not found"

    if UserGames.objects.filter(game=game, user=player).exists():
        return False, "User already has an account for this game"

    user_game = UserGames()
    user_game.game = game
    user_game.username = username
    user_game.user = player
    user_game.save()

    return True, None

def edit_transaction(
    transaction_id: str,
    user_status: str,
    txn_type: str,
    user: Users,
) -> Tuple[bool, Optional[str]]:
    """Edit offmarket transaction status on Refuji API.

    Args:
        transaction_id (str): Local DB transaction ID
        user_status (str): Desired status
        txn_type (str): Type of transaction (e.g. Pending, Completed, Failed)
        user (Users): Requesting user

    Returns:
        Tuple[bool, Optional[str]]: success, error message
    """
    transaction = OffMarketTransactions.objects.filter(id=transaction_id).first()
    if not transaction:
        return False, "Transaction not found"

    # Normalize status
    if txn_type != "Pending":
        user_status = "Completed" if user_status == "Failed" else "Failed"

    deposit_id = transaction.txn_id
    request_payload = {
        "deposit_id": deposit_id,
        "status": user_status,
        "secret_key": settings.OFF_MARKET_SECRETKEY,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.put(
            settings.OFFMARKET_API_URL + "update",
            params=request_payload,
            headers=headers,
            timeout=30,
        )
    except Exception:
        return False, "Service is not available. Please try again later."

    if response.status_code != 200:
        return False, "Request Not Processed"

    # Update DB
    transaction.status = user_status
    transaction.save()

    # Refund if failed
    if user_status == "Failed":
        off_market_refund_transactions(transaction.id) # type: ignore

    return True, None


def delete_transaction(transaction_id: str) -> Tuple[bool, Optional[str]]:
    transaction = OffMarketTransactions.objects.filter(
        id=transaction_id
    ).first()

    if not transaction:
        return False, "Transaction not found"

    deposit_id=transaction.txn_id
    request_payload = {
        "deposit_id": deposit_id,
        "secret_key": settings.OFF_MARKET_SECRETKEY,
    }
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    response = requests.delete(
        settings.OFFMARKET_API_URL + 'delete',
        params=request_payload,
        headers=headers
    )
    if response.status_code == 200:
        transaction.delete()
    return True, None