import math
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from apps.users.models import Users
from typing import Any, Dict, List, Literal, Optional, Tuple, Union, cast
from apps.core.file_logger import SimpleLogger
from django.db.models import F, Sum, Case, When, DecimalField, Q
from apps.bets.models import BONUS, CHARGED, CREDIT, WageringRequirement, Transactions
from apps.bets.utils import serialize_wr_data, generate_reference

logger = SimpleLogger(name="Wagering", log_file="logs/wagering.log").get_logger()


def get_wagering_balance(user: Users, bonus: bool) -> Decimal:
    data = WageringRequirement.objects.filter(
        result__isnull=True,
        user_id=user.id,
        betable=True,
        active=True,
        **({"limit": F("amount")} if not bonus else {})
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
    rest = min(c_balance, amount)
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
    wagrecs = WageringRequirement.objects.select_for_update().filter(
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
    balance_wagering: Decimal,
    adjust: Decimal,
) -> Tuple[Decimal, Decimal, Decimal]:
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
        if old_result > 0:
            if balance_wagering >= old_result:
                balance_wagering -= old_result
            else:
                shortfall = old_result - balance_wagering
                balance_wagering = Decimal(0)
                balance -= shortfall
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
    return balance, balance_wagering, adjust


def __cancel_wr_clear(user: Users, data: Tuple[Decimal, Decimal]) -> Tuple[Decimal, Decimal]:
    debit = Decimal('0.00')
    if data[1] == 0:
        return cast(Decimal, user.balance), Decimal('0.00')

    differential = data[1] % settings.REACTOR_MULTIPLIER
    wagrec = WageringRequirement.objects.select_for_update().filter(
        user__id=user.id,
        betable=False,
        balance__gt=Decimal(0),
        active=True,
    ).order_by('created').first()

    remaining = data[0]
    reactor_used = min(cast(Decimal, user.balance_reactor), remaining)
    user.balance_reactor = round(cast(Decimal, user.balance_reactor) - reactor_used, 2)
    remaining -= reactor_used

    wallet_used = min(cast(Decimal, user.balance), remaining)
    user.balance = round(cast(Decimal, user.balance) - wallet_used, 2)
    remaining -= wallet_used
    debit = remaining
    restore = data[0] - debit

    extra_bonus = Decimal(0)
    if data[1] > settings.REACTOR_MULTIPLIER * data[0]:
        extra_bonus = Decimal(1)
        remaining_extra = extra_bonus
        reactor_used = min(cast(Decimal, user.balance_reactor), remaining_extra)
        user.balance_reactor = round(cast(Decimal, user.balance_reactor) - reactor_used, 2)
        remaining_extra -= reactor_used
        wallet_used = min(cast(Decimal, user.balance), remaining_extra)
        user.balance = round(cast(Decimal, user.balance) - wallet_used, 2)
        remaining_extra -= wallet_used
        debit += remaining_extra

    if not wagrec:
        new_bonus = data[0] + extra_bonus
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
        wagrec.balance += data[0] + extra_bonus
        step = wagrec.played - differential
        if extra_bonus == 0:
            wagrec.played = step
        wagrec.save()
    user.save()
    return cast(Decimal, user.balance), debit


def get_wagering_requirements(user: Users, bonus: bool = True) -> List[WageringRequirement]:
    qs = WageringRequirement.objects.select_for_update().filter(
        user_id=user.id,
        balance__gt=0,
        active=True,
    )
    if not bonus:
        qs = qs.filter(Q(limit=F("amount")) | Q(betable=False))
    
    return qs.order_by('created').all()


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
        user.balance_reactor += total_to_return
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
    bypass_return = Decimal('0.00')

    wr_ids = {}
    for wagrec in wagrecs:
        reminder, to_return, betted = __single_wr_bet(wagrec, amount)
        amount = reminder
        if to_return > 0:
            if wagrec.amount == wagrec.limit:
                bypass_return += to_return
            else:
                total_to_return += to_return
        if betted > 0:
            wr_ids[wagrec.id] = (Decimal(math.floor((betted / total_betted) * 100) / 100), betted)
        if reminder <= 0:
            amount = Decimal('0.00')
            break

    wr_ids["from_wallet"] = (amount, amount)

    user.balance -= amount
    user.balance += bypass_return
    user.balance_wagering += total_to_return
    user.save()
    return serialize_wr_data(wr_ids), total_to_return - amount


def platform_cancel_bet_wr(
    user: Users,
    data: Dict[str, Tuple[str, str]],
    shortfall: Decimal = Decimal('0.00')
):
    starting_balance = cast(Decimal, user.balance)
    wr_clear = data.pop("wr_clear", ('0.00', '0.00'))
    relative_amount = Decimal(data.pop("from_wallet", ('0.00', ))[0]) or Decimal('0.00')

    wr_clear = (Decimal(wr_clear[0]), Decimal(wr_clear[1]))

    balance, debit = __cancel_wr_clear(user, wr_clear)
    balance_wagering = cast(Decimal, user.balance_wagering)

    adjust = -abs(debit) - abs(shortfall)
    balance += relative_amount

    padjust = min(balance, abs(adjust))
    balance = balance - padjust
    adjust = adjust + padjust

    objects = WageringRequirement.objects.select_for_update().filter(id__in=data.keys())

    for wagrec in objects:
        balance, balance_wagering, adjust = __single_wr_bet_cancel(
            wagrec,
            Decimal(data[str(wagrec.id)][1]),
            balance,
            balance_wagering,
            adjust,
        )
    
    if adjust < 0:
        adjust = __reduce_adjust(user, adjust)
    
    if balance + adjust < 0:
        logger.warning(f"User: {user.id}-{user.username} had withdraw some balance need to pay us {abs(balance + adjust)}")
        balance = Decimal('0.00')

    user.balance = balance
    user.balance_wagering = balance_wagering
    user.save()
    debit_amount = max(Decimal('0.00'), starting_balance - cast(Decimal, user.balance))
    if debit_amount > 0:
        Transactions.objects.create(
            user=user,
            journal_entry="debit",
            amount=debit_amount,
            status="charged",
            previous_balance=starting_balance,
            new_balance=cast(Decimal, user.balance),
            description="Wagering cancel adjustment",
            reference=generate_reference(user),
            bonus_type=None,
            bonus_amount=Decimal('0.00'),
        )
    return None


def platform_playable_balance(user: Users, bonus: bool = False) -> Decimal:
    return get_wagering_balance(user, bonus=bonus) + cast(Decimal, user.balance)


def platform_bet(
    user: Users,
    amount: Decimal,
    bonus: bool = True,
    clear: bool = True
) -> Optional[Tuple[Dict[str, Tuple[str, str]], Decimal]]:
    """
    Function to bet on the platform

    Args:
        user (Users): User to be bet on
        amount (Decimal): Amount betted from the users.balance (only for the record keeping)

    Returns:
        Optional[Tuple[Dict, Decimal]]: Data of the wagering requirements and the amount betted from the users.balance (only for the record keeping)
    """
    wagrecs = get_wagering_requirements(user, bonus=bonus)
    clerables = [wagrec for wagrec in wagrecs if not wagrec.betable]
    bettables = [wagrec for wagrec in wagrecs if wagrec.betable]
    data = bet_wr(user, amount, bettables)
    if data is None:
        return None
    if len(clerables) > 0 and clear:
        clear_wr(user, amount, clerables)
    return data


def platform_pay(
    user: Users,
    won: Decimal,
    data: Dict[str, Tuple[str, str]]
) -> Optional[Tuple[Decimal, Dict[str, Tuple[str, str]]]]:
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

    wr_data = {}
    from_wallet = data.pop("from_wallet", None)

    data.pop("wr_clear", None)
    objects = WageringRequirement.objects.select_for_update().filter(id__in=data.keys())

    total_to_pay = Decimal('0.00')
    paid = Decimal('0.00')
    wallet_bet_amount = Decimal(from_wallet[0]) if from_wallet else Decimal('0.00')
    total_bet_amount = wallet_bet_amount + sum(
        (Decimal(values[1]) for values in data.values()),
        Decimal('0.00'),
    )
    wallet_ratio = (
        wallet_bet_amount / total_bet_amount
        if total_bet_amount > 0
        else Decimal('0.00')
    )
    wallet_to_pay = Decimal(math.floor(wallet_ratio * won * 10) / 10)
    for wagrec in objects:
        ratio = Decimal(data[str(wagrec.id)][0])
        amount = Decimal(math.floor(ratio * won * 10) / 10)
        wr_data[str(wagrec.id)] = (ratio, amount)
        paid += amount
        total_to_pay += __single_wr_pay(wagrec, amount)

    paid_total = paid + wallet_to_pay
    adjustment = won - paid_total
    wallet_adjustment = adjustment if wallet_bet_amount > 0 else Decimal('0.00')
    pool_adjustment = adjustment if wallet_bet_amount == 0 else Decimal('0.00')

    wr_data["to_wallet"] = (str(wallet_to_pay), str(wallet_to_pay))
    wr_data["to_wagering"] = (str(total_to_pay), str(total_to_pay))
    user.balance += wallet_to_pay + wallet_adjustment
    user.balance_wagering += total_to_pay + pool_adjustment
    user.save()
    return wallet_to_pay + wallet_adjustment, wr_data


def __single_wr_cancel_pay(wagrec: WageringRequirement, amount: Decimal) -> Decimal:
    """Reverse of __single_wr_pay - deducts the payout from a WR.

    Args:
        wagrec (WageringRequirement): The wagering requirement to deduct from
        amount (Decimal): Amount to deduct

    Returns:
        Decimal: Amount that couldn't be deducted from WR (shortfall)
    """
    if not wagrec.betable:
        return Decimal('0.00')

    current_balance = cast(Decimal, wagrec.balance or Decimal('0.00'))

    if current_balance >= amount:
        # Can fully deduct from WR balance
        wagrec.balance = current_balance - amount
        if wagrec.balance <= 0:
            wagrec.active = False
            wagrec.result = Decimal('0.00')
        wagrec.save()
        return Decimal('0.00')
    else:
        # Can only partially deduct - there's a shortfall
        shortfall = amount - current_balance
        wagrec.balance = Decimal('0.00')
        wagrec.active = False
        wagrec.result = Decimal('0.00')
        wagrec.save()
        return shortfall


def platform_cancel_pay(
    user: Users,
    pay_data: Dict[str, Tuple[str, str]]
) -> Decimal:
    """
    Reverses the effect of platform_pay.
    Deducts the payout amounts from WRs, wallet, and wagering pool.

    Args:
        user (Users): User whose payout is being cancelled
        pay_data (Dict): The wr_data returned from platform_pay, containing:
            - {wr_id: (ratio, amount)} for each WR that received payout
            - "to_wallet": (amount, amount) - amount added to wallet
            - "to_wagering": (amount, amount) - amount added to wagering pool

    Returns:
        Decimal: Total shortfall (amount that couldn't be deducted, if any)
    """
    total_shortfall = Decimal('0.00')

    # Extract wallet and wagering amounts
    to_wallet_data = pay_data.pop("to_wallet", ('0.00', '0.00'))
    to_wagering_data = pay_data.pop("to_wagering", ('0.00', '0.00'))

    wallet_amount = Decimal(to_wallet_data[0])
    wagering_amount = Decimal(to_wagering_data[0])

    # Deduct from WR balances
    wr_ids = [k for k in pay_data.keys() if k not in ("to_wallet", "to_wagering")]
    if wr_ids:
        objects = WageringRequirement.objects.select_for_update().filter(id__in=wr_ids)
        for wagrec in objects:
            wr_payout = Decimal(pay_data[str(wagrec.id)][1])
            shortfall = __single_wr_cancel_pay(wagrec, wr_payout)
            total_shortfall += shortfall

    # Deduct from user's wagering pool
    current_wagering = cast(Decimal, user.balance_wagering or Decimal('0.00'))
    if current_wagering >= wagering_amount:
        user.balance_wagering = current_wagering - wagering_amount
    else:
        # Shortfall from wagering pool goes to balance deduction
        wagering_shortfall = wagering_amount - current_wagering
        user.balance_wagering = Decimal('0.00')
        wallet_amount += wagering_shortfall

    # Deduct from user's balance (wallet)
    current_balance = cast(Decimal, user.balance or Decimal('0.00'))
    if current_balance >= wallet_amount:
        user.balance = current_balance - wallet_amount
    else:
        # Can't fully deduct - user may have spent some winnings
        balance_shortfall = wallet_amount - current_balance
        user.balance = Decimal('0.00')
        total_shortfall += balance_shortfall
        logger.warning(
            f"User {user.id}-{user.username} cancel_pay shortfall: {balance_shortfall}. User may have spent some winnings."
        )

    user.save()
    return total_shortfall


def get_user_wagering_snapshot(user: Users, calculate_reactor: bool = False) -> Dict[str, Any]:
    base_qs = WageringRequirement.objects.filter(
        user_id=user.id,
        claimed=False,
        active=True,
    )

    totals = base_qs.aggregate(
        bonus_total=Sum(
            Case(
                When(
                    Q(betable=True) & ~Q(limit=F("amount")) & Q(result__isnull=True),
                    then=F("balance"),
                ),
                default=Decimal("0.00"),
                output_field=DecimalField(),
            )
        ),
        wagering_total=Sum(
            Case(
                When(
                    Q(betable=True) & Q(result__isnull=True) & Q(limit=F("amount")),
                    then=F("balance"),
                ),
                default=Decimal("0.00"),
                output_field=DecimalField(),
            )
        ),
        reactor_total=Sum(
            Case(
                When(
                    betable=False,
                    then=F("balance"),
                ),
                default=Decimal("0.00"),
                output_field=DecimalField(),
            )
        ),
    )

    next_betable = (
        base_qs.filter(
            betable=True,
            result__isnull=True,
            balance__gt=0
        )
        .only("limit", "played", "balance")
        .order_by("created")
        .first()
    )

    if next_betable and (limit := next_betable.limit or Decimal("0.00")) > 0:
        played = next_betable.played or Decimal("0.00")
        percentage_active: Decimal = played / limit
        next_win = next_betable.balance or Decimal("0.00")
    else:
        percentage_active = Decimal("1.00")
        next_win = Decimal("0.00")

    percentage_reactor: Decimal = Decimal(1)
    if calculate_reactor:
        next_reactor = (
            base_qs.filter(betable=False, balance__gt=0)
            .only("played")
            .order_by("created")
            .first()
        )

        if next_reactor:
            reactor_played = next_reactor.played or Decimal("0.00")
            percentage_reactor = round((reactor_played % 30) / Decimal("30"), 4)

    return {
        "pending_reactor": user.balance_reactor or Decimal("0.00"),
        "pending_balance": user.balance_wagering or Decimal("0.00"),

        "sc_bonus": totals["bonus_total"] or Decimal("0.00"),
        "sc_playable": totals["wagering_total"] or Decimal("0.00"),
        "sc_redeamable": user.balance or Decimal("0.00"),

        "gc": user.bonus_balance or Decimal("0.00"),

        "pool_amount": totals["reactor_total"] or Decimal("0.00"),
        "percentage_active": percentage_active,
        "next_win": next_win,
        **({"percentage_reactor": percentage_reactor} if calculate_reactor else {}),
    }

@transaction.atomic
def claim_action_bonus(user: Users, action: Literal["reactor", "bonus"]):
    a = Users.objects.select_for_update().get(id=user.id)
    pre = a.balance
    t = WageringRequirement.objects.select_for_update().filter(
        claimed=False,
        betable=action == "bonus",
    )
    amount = Decimal(0)
    if action == "bonus":
        t = t.filter(Q(balance=Decimal('0.00')) | Q(active=False))
        a.balance += a.balance_wagering
        amount += a.balance_wagering
        a.balance_wagering = Decimal(0)
    if action == "reactor":
        t = t.filter(balance=Decimal('0.00'))
        a.balance += a.balance_reactor
        amount += a.balance_reactor
        a.balance_reactor = Decimal(0)
    
    if amount == 0:
        return {"status": "error", "message": "No amount to claim"}

    a.save()
    t.update(claimed=True)

    Transactions.objects.create(
        user=user,
        amount=amount,
        journal_entry=BONUS,
        status=CHARGED,
        previous_balance=pre,
        new_balance=a.balance,
        reference=generate_reference(a),

        description=f"Claimed action for {action} -> {amount}SC",
        bonus_type="Play_Bonus" if action == "bonus" else "Solar_Bonus",
        bonus_amount=0
    )
    return {"status": "ok"}
