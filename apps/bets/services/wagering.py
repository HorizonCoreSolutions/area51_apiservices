from typing import Tuple
from decimal import Decimal
from django.db.models import Sum
from apps.users.models import Users
from apps.bets.models import WageringRequirement


def get_wagering_balance(user: Users) -> Decimal:
    data = WageringRequirement.objects.filter(
        result__isnull=True,
        user_id=user.id,
        active=True,
    ).aggregate(
        total=Sum('balance')
    )
    wr = Decimal(data.get('total') or 0)
    return wr


def __single_wr_bet(
    wagrec: WageringRequirement,
    amount: Decimal
) -> Tuple[Decimal, Decimal, Decimal]:
    """Es una funcion para hacer que apostar sea más fácil y no tener que hacerlo en otro lado

    Args:
        amount (Decimal): cantidad que el usuario va a apostar

    Returns:
        Tuple[Decimal, Decimal, Decimal]: 
        - Reminent amount of money to bet
        - Amount of money to be return to the main balance
        - Amount bet on this WR
    """
    give = Decimal('0')
    if not wagrec.betable:
        return amount, give, give
    rest = min(wagrec.balance, amount, wagrec.limit - wagrec.balance)
    wagrec.balance = round(wagrec.balance - rest, 2)
    wagrec.played += rest

    if wagrec.played >= wagrec.limit:
        wagrec.result = wagrec.balance
        give = wagrec.balance
        wagrec.balance = Decimal('0.00')
        wagrec.active = False
    
    elif wagrec.balance <= 0:
        wagrec.result = Decimal('0.00')
        wagrec.active = False

    wagrec.save()
    return amount - rest, give, rest


def __single_wr_pay(wagrec: WageringRequirement, amount: Decimal) -> Tuple[Decimal]:
    """Function to return (precalculated) amount of money

    Args:
        amount (Decimal): Amount to be pay for the user

    Returns:
        Tuple[Decimal]: Amount of money to be return to the main balance
    """
    
    give = Decimal('0.00')
    if not wagrec.betable:
        return give,
    
    if not wagrec.active:
        if wagrec.played >= wagrec.limit:
            # If limit has been pass money should be given to main balance
            return (give, )

        # The WR should be re activated
        # Here the amount should be 0
        if (wagrec.result or 0) == 0:
            wagrec.active = True
            wagrec.balance = amount
            wagrec.result = None
    else:
        wagrec.balance += amount
    
    wagrec.save()
    return (give,)


def retrieve(wagrec):
    return

