import math
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from django.db.models import Sum
from apps.users.models import Users
from apps.bets.models import WageringRequirement


def get_wagering_balance(user: Users) -> Decimal:
    data = WageringRequirement.objects.filter(
        result__isnull=True,
        user_id=user.id,
        betable=True,
        active=True,
    ).aggregate(
        total=Sum('balance')
    )
    wr = Decimal(data.get('total') or 0)
    return wr


def __single_wr_clear(
    wagrec: WageringRequirement,
    amount: Decimal
) -> Tuple[Decimal, Decimal]:
    """Function to clear the wagering requirement

    Args:
        wagrec (WageringRequirement): Wagering requirement to be cleared
        amount (Decimal): Amount to be cleared

    Returns:
        Decimal: Amount of money to be cleared
        Decimal: Amount of money to be returned to the main balance
    """
    c_balance = Decimal(wagrec.balance)
    if c_balance <= 0:
        return amount, Decimal('0.00')

    c_played = Decimal(wagrec.played)
    c_limit = Decimal(wagrec.limit)
    c_result = Decimal(wagrec.result or 0)

    current = c_played + amount
    c_multiplier = Decimal(wagrec.limit / wagrec.amount)

    if current >= c_limit:
        wagrec.balance = Decimal('0.00')
        wagrec.result = c_result + c_balance
        wagrec.played = c_limit
        wagrec.active = False

        amount = current - c_limit
        wagrec.save()
        return amount, c_balance

    multiplier = current // c_multiplier - c_played // c_multiplier
    given = Decimal('0.00')

    if multiplier > 0:
        given = min(Decimal("1.00") * multiplier, c_balance)
        if given == c_balance:
            wagrec.active = False
            wagrec.balance = Decimal('0.00')
        else:
            wagrec.balance = c_balance - given
        wagrec.result = c_result + given
    
    wagrec.played = current
    wagrec.save()
    return Decimal('0.00'), given


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
    c_balance = Decimal(wagrec.balance or 0)
    limit = Decimal(wagrec.limit or 0)
    rest = min(c_balance, amount, limit - c_balance)
    wagrec.balance = c_balance - rest
    wagrec.played += rest

    if wagrec.played >= limit:
        wagrec.result = wagrec.balance
        give = wagrec.balance
        wagrec.balance = Decimal('0.00')
        wagrec.active = False
    
    elif wagrec.balance <= 0:
        wagrec.result = Decimal('0.00')
        wagrec.active = False

    wagrec.save()
    return amount - rest, give, rest


def __single_wr_pay(wagrec: WageringRequirement, amount: Decimal) -> Decimal:
    """Function to return (precalculated) amount of money

    Args:
        amount (Decimal): Amount to be pay for the user

    Returns:
        Decimal: Amount of money to be return to the main balance
    """
    
    give = Decimal('0.00')
    if not wagrec.betable:
        return give
    
    if not wagrec.active:
        if wagrec.played >= wagrec.limit:
            # If limit has been pass money should be given to main balance
            return amount

        # The WR should be re activated
        # Here the amount should be 0
        if (wagrec.result or 0) == 0:
            wagrec.active = True
            wagrec.balance = amount
            wagrec.result = None
        else:
            return amount
    else:
        wagrec.balance += amount
    
    wagrec.save()
    return give


def get_wagering_requirements(user: Users) -> List[WageringRequirement]:
    return WageringRequirement.objects.select_for_update().filter(
        user_id=user.id,
        balance__gt=0,
        active=True,
    ).order_by('created').all()


def clear_wr(user: Users, amount: Decimal, wagrecs: List[WageringRequirement]) -> None:
    for wagrec in wagrecs:
        reminder, to_return = __single_wr_clear(wagrec, amount)
        amount = reminder
        if to_return > 0:
            user.balance += to_return
        if reminder <= 0:
            break
    user.save()
    return None


def bet_wr(user: Users, amount: Decimal, wagrecs: List[WageringRequirement]) -> Optional[Tuple[Dict, Decimal]]:
    total = sum((Decimal(wagrec.balance) for wagrec in wagrecs), Decimal('0.00')) + Decimal(user.balance or 0)
    if total < amount:
        return None
    
    total_betted = amount

    wr_ids = {}
    for wagrec in wagrecs:
        reminder, to_return, betted = __single_wr_bet(wagrec, amount)
        amount = reminder
        if to_return > 0:
            user.balance += to_return
            user.save()
        if betted > 0:
            wr_ids[wagrec.id] = (Decimal(math.floor((betted / total_betted) * 100) / 100), betted)
        if reminder <= 0:
            break
    user.balance -= amount
    user.save()
    return wr_ids, amount


def platfom_playable_balance(user: Users) -> Decimal:
    return get_wagering_balance(user) + user.balance


def platform_bet(user: Users, amount: Decimal) -> Optional[Tuple[Dict, Decimal]]:
    wagrecs = get_wagering_requirements(user)
    clerables = [wagrec for wagrec in wagrecs if not wagrec.betable]
    bettables = [wagrec for wagrec in wagrecs if wagrec.betable]
    data = bet_wr(user, amount, bettables)
    if data is None:
        return None
    if clerables:
        clear_wr(user, amount, clerables)
    return data


def platform_pay(user: Users, won: Decimal, data: Dict) -> Optional[Decimal]:
    """
    Function to pay the winnings to the user
    This already pays the user

    Args:
        user (Users): User to be paid
        won (Decimal): Amount to be paid
        data (Dict): Data of the wagering requirements

    Returns:
        Optional[Decimal]: This is only for the record keeping
    """
    objects = WageringRequirement.objects.filter(id__in=data.keys())
    total_to_pay = Decimal('0.00')
    paid = Decimal('0.00')
    for wagrec in objects:
        to_pay = Decimal(math.floor(data[wagrec.id][0] * won * 10)/10)
        paid += to_pay
        to_wallet = __single_wr_pay(wagrec, to_pay)
        total_to_pay += to_wallet
    adjustment = won - paid
    user.balance += total_to_pay + adjustment
    user.save()
    return total_to_pay + adjustment