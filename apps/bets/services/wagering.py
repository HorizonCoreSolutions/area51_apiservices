from asyncio import current_task
import math
from decimal import Decimal
from django.conf import settings
from django.db.models import Sum
from apps.users.models import Users
from apps.bets.utils import serialize_wr_data, generate_reference
from typing import Dict, List, Optional, Tuple, cast
from apps.core.file_logger import SimpleLogger
from apps.bets.models import WageringRequirement, Transactions

logger = SimpleLogger(name="Wagering", log_file="logs/wagering.log").get_logger()


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
    c_balance = cast(Decimal, wagrec.balance)
    if c_balance <= 0 or wagrec.betable:
        return amount, Decimal('0.00')

    c_played = cast(Decimal, wagrec.played)
    c_limit = cast(Decimal, wagrec.limit)
    c_result = cast(Decimal, wagrec.result or 0)

    current = c_played + amount
    c_multiplier = c_limit / cast(Decimal, wagrec.amount)

    if current >= c_limit:
        wagrec.balance = Decimal('0.00')
        wagrec.result = c_balance
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
    c_played = Decimal(wagrec.played or 0)
    rest = min(c_balance, amount, limit - c_played)
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


def __reduce_adjust(user: Users, adjust: Decimal) -> Decimal:
    WageringRequirement.objects.select_for_update().filter(
        user__id=user.id,
        betable=False,
        balance__gt=Decimal(0),
        active=True,
    ).order_by('created')
    for wagrec in wagrecs:
        if wagrec.balance > 0:
            adjust = adjust + wagrec.balance
            wagrec.balance = Decimal(0)
            wagrec.save()
        if adjust > 0:
            wagrec.balance = adjust
            wagrec.save()
            break
    return adjust


def __single_wr_bet_cancel(
    wagrec: WageringRequirement,
    taken: Decimal,
    balance: Decimal,
    adjust: Decimal,
) -> Tuple[Decimal, Decimal]:
    """
    Args:
        wagrec (WageringRequirement):
        amount (Decimal): 
        balance (Decimal):
    Returns:
        Decimal (new_balance):

    """

    nplayed = cast(Decimal, wagrec.played) - taken
    if nplayed < 0:
        nplayed = Decimal(0)
        logger.warning(
            f"Played out of {wagrec.id}. " # type: ignore
            f"Played {wagrec.played} - {taken} < 0 "
        )

    if wagrec.result or wagrec.played == wagrec.limit:
        old_result = cast(Decimal, wagrec.result or Decimal(0))
        balance -= old_result
        wr_balance = old_result + taken

        if balance < 0:
            wr_balance += balance
            if wr_balance < 0:
                adjust += wr_balance
                wr_balance = Decimal(0)
            balance = Decimal(0)

        wagrec.balance = wr_balance
        wagrec.result = None
    else:
        wagrec.balance += taken
        wagrec.result = None

    wagrec.active = True
    wagrec.played = nplayed

    wagrec.save()

    partial_adjust = min(balance, abs(adjust))
    balance = balance - partial_adjust
    adjust = adjust + partial_adjust
    return balance, adjust


def __cancel_wr_clear(user: Users, data: Tuple[Decimal, Decimal]) -> Tuple[Decimal, Decimal]:
    debit = Decimal('0.00')
    restore = min(cast(Decimal, user.balance), data[0])
    if data[1] == 0:
        return cast(Decimal, user.balance), Decimal('0.00')

    differential = data[1] % settings.REACTOR_MULTIPLIER
    wagrec = WageringRequirement.objects.select_for_update().filter(
        user__id=user.id,
        betable=False,
        balance__gt=Decimal(0),
        active=True,
    ).order_by('created').first()
    user.balance = round(cast(Decimal, user.balance) - restore, 2)
    if user.balance < 0:
        user.balance = Decimal('0.00')
    debit = data[0] - restore
    if not wagrec:
        new_bonus = data[0]
        if data[1] > settings.REACTOR_MULTIPLIER * data[0]:
            new_bonus += Decimal(1)
            if  user.balance > 1:
                user.balance -= Decimal(1)
            else:
                debit += Decimal(1) - max(user.balance, Decimal(0))
                user.balance = Decimal('0.00')
        wagrec = WageringRequirement.objects.create(
            user=user,
            betable=False,
            amount=new_bonus,
            balance=new_bonus,
            played=settings.REACTOR_MULTIPLIER - differential,
            limit=settings.REACTOR_MULTIPLIER * restore,
            active=True,
            result=None,
        )
    else:
        wagrec.balance += data[0]
        step = wagrec.played - differential
        if data[1] > settings.REACTOR_MULTIPLIER * data[0]:
            wagrec.balance += Decimal(1)
            if  user.balance > 1:
                user.balance -= Decimal(1)
            else:
                debit += Decimal(1) - max(user.balance, Decimal(0))
                user.balance = Decimal('0.00')
        else:
            wagrec.played = step
        wagrec.save()
    user.save()
    return cast(Decimal, user.balance), debit


def get_wagering_requirements(user: Users) -> List[WageringRequirement]:
    return WageringRequirement.objects.select_for_update().filter(
        user_id=user.id,
        balance__gt=0,
        active=True,
    ).order_by('created').all()


def clear_wr(user: Users, amount: Decimal, wagrecs: List[WageringRequirement]) -> Tuple[Decimal, Decimal]:
    total_to_return = Decimal('0.00')
    for wagrec in wagrecs:
        reminder, to_return = __single_wr_clear(wagrec, amount)
        amount = reminder
        if to_return > 0:
            total_to_return += to_return
        if reminder <= 0:
            break
    if total_to_return > 0:
        Transactions.objects.create(
            user=user,
            journal_entry="bonus",
            amount=total_to_return,
            status="charged",
            previous_balance=user.balance,
            new_balance=cast(Decimal, user.balance) + total_to_return,
            description="Reactor Bonus",
            reference=generate_reference(user),
            bonus_type="Reactor",
            bonus_amount=total_to_return,
        )
    user.balance += total_to_return
    user.save()
    return total_to_return, amount


def bet_wr(
    user: Users,
    amount: Decimal,
    wagrecs: List[WageringRequirement]
) -> Optional[Tuple[Dict[str, Tuple[str, str]], Decimal]]:
    total = sum((cast(Decimal, wagrec.balance) for wagrec in wagrecs), Decimal('0.00')) + cast(Decimal, user.balance or 0)
    if total < amount:
        return None
    
    total_betted = amount
    total_to_return = Decimal('0.00')

    wr_ids = {}
    for wagrec in wagrecs:
        reminder, to_return, betted = __single_wr_bet(wagrec, amount)
        amount = reminder
        if to_return > 0:
            total_to_return += to_return
        if betted > 0:
            wr_ids[wagrec.id] = (Decimal(math.floor((betted / total_betted) * 100) / 100), betted)
        if reminder <= 0:
            amount = Decimal('0.00')
            break

    wr_ids["from_wallet"] = (amount, amount)

    user.balance -= amount
    user.balance += total_to_return
    user.save()
    return serialize_wr_data(wr_ids), total_to_return - amount


def platform_cancel_bet_wr(
    user: Users,
    data: Dict[str, Tuple[str, str]]
):
    wr_clear = data.pop("wr_clear", ('0.00', '0.00'))
    relative_amount = Decimal(data.pop("from_wallet", ('0.00', ))[0]) or Decimal('0.00')

    wr_clear = (Decimal(wr_clear[0]), Decimal(wr_clear[1]))

    balance, debit = __cancel_wr_clear(user, wr_clear)

    adjust = -abs(debit)
    balance += relative_amount

    padjust = min(balance, abs(adjust))
    balance = balance - padjust
    adjust = adjust + padjust

    objects = WageringRequirement.objects.select_for_update().filter(id__in=data.keys())

    for wagrec in objects:
        balance, adjust = __single_wr_bet_cancel(
            wagrec,
            Decimal(data[str(wagrec.id)][1]),
            balance,
            adjust,
        )
    
    if adjust < 0:
        adjust = __reduce_adjust(user, adjust)
    
    if balance + adjust < 0:
        logger.warning(f"User: {user.id}-{user.username} had withdraw some balance need to pay us {abs(balance + adjust)}")
        balance = Decimal('0.00')

    user.balance = balance
    user.save()
    return None


def platform_playable_balance(user: Users) -> Decimal:
    return get_wagering_balance(user) + cast(Decimal, user.balance)


def platform_bet(
    user: Users,
    amount: Decimal
) -> Optional[Tuple[Dict[str, Tuple[str, str]], Decimal]]:
    """
    Function to bet on the platform

    Args:
        user (Users): User to be bet on
        amount (Decimal): Amount betted from the users.balance (only for the record keeping)

    Returns:
        Optional[Tuple[Dict, Decimal]]: Data of the wagering requirements and the amount betted from the users.balance (only for the record keeping)
    """
    wagrecs = get_wagering_requirements(user)
    clerables = [wagrec for wagrec in wagrecs if not wagrec.betable]
    bettables = [wagrec for wagrec in wagrecs if wagrec.betable]
    data = bet_wr(user, amount, bettables)
    if data is None:
        return None
    if clerables:
        clear_wr(user, amount, clerables)
    return data


def platform_pay(
    user: Users,
    won: Decimal,
    data: Dict[str, Tuple[str, str]]
) -> Optional[Decimal]:
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
    # data = deserialize_wr_data(data)
    data.pop("from_wallet", None)
    data.pop("wr_clear", None)
    objects = WageringRequirement.objects.select_for_update().filter(id__in=data.keys())
    total_to_pay = Decimal('0.00')
    paid = Decimal('0.00')
    for wagrec in objects:
        to_pay = Decimal(math.floor(Decimal(data[str(wagrec.id)][0]) * won * 10)/10)
        paid += to_pay
        to_wallet = __single_wr_pay(wagrec, to_pay)
        total_to_pay += to_wallet
    adjustment = won - paid
    user.balance += total_to_pay + adjustment
    user.save()
    return total_to_pay + adjustment
