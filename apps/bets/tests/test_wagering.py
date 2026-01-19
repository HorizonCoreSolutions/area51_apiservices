from decimal import Decimal
from typing import TYPE_CHECKING, Dict, Optional, Tuple, cast
# from unittest.mock import MagicMock, patch

from django.db import transaction
from django.test import TestCase, TransactionTestCase

from apps.bets.models import WageringRequirement
from apps.bets.services.wagering import (
    get_wagering_balance,
    get_wagering_requirements,
    clear_wr,
    bet_wr,
    platform_bet,
    platform_pay,
    platform_cancel_bet_wr,
    platform_playable_balance,
)
from apps.bets.utils import serialize_wr_data
from apps.users.models import Agent, Users


class WageringTestMixin:
    """Mixin with helper methods for wagering tests."""
    
    def create_user(self, username: str = "testuser", balance: Decimal = Decimal("100.00")) -> Users:
        """Create a test user with the given balance."""

        agent, _ = Agent.objects.update_or_create(
            username="agent2",
            defaults={
                "password": "secret",
                "role": "agent",
                "balance": Decimal("0.00"),
                "bonus_balance": Decimal("0.00"),
            }
        )

        user = Users.objects.create(
            username=username,
            password="secret",
            role="player",
            email=f"{username}@test.com",
            agent=agent,
            balance=balance,
            bonus_balance=Decimal("0.00"),
        )
        return user
    
    def create_wagering_requirement(
        self,
        user: Users,
        amount: Decimal = Decimal("10.00"),
        balance: Decimal = Decimal("10.00"),
        played: Decimal = Decimal("0.00"),
        limit: Decimal = Decimal("100.00"),
        active: bool = True,
        betable: bool = True,
        result: Optional[Decimal] = None,
    ) -> WageringRequirement:
        """Create a wagering requirement for the given user."""
        return WageringRequirement.objects.create(
            user=user,
            amount=amount,
            balance=balance,
            played=played,
            limit=limit,
            active=active,
            betable=betable,
            result=result,
        )


class GetWageringBalanceTests(TestCase, WageringTestMixin):
    """Tests for get_wagering_balance function."""
    
    def test_no_wagering_requirements_returns_zero(self):
        """When user has no wagering requirements, balance should be 0."""
        user = self.create_user()
        result = get_wagering_balance(user)
        self.assertEqual(result, Decimal("0"))
    
    def test_single_active_wagering_requirement(self):
        """Should return balance of single active wagering requirement."""
        user = self.create_user()
        self.create_wagering_requirement(user, balance=Decimal("50.00"))
        
        result = get_wagering_balance(user)
        self.assertEqual(result, Decimal("50.00"))
    
    def test_multiple_active_wagering_requirements(self):
        """Should return sum of all active wagering requirements."""
        user = self.create_user()
        self.create_wagering_requirement(user, balance=Decimal("30.00"))
        self.create_wagering_requirement(user, balance=Decimal("20.00"))
        
        result = get_wagering_balance(user)
        self.assertEqual(result, Decimal("50.00"))
    
    def test_inactive_wagering_requirements_excluded(self):
        """Inactive wagering requirements should not be counted."""
        user = self.create_user()
        self.create_wagering_requirement(user, balance=Decimal("30.00"), active=True)
        self.create_wagering_requirement(user, balance=Decimal("20.00"), active=False)
        
        result = get_wagering_balance(user)
        self.assertEqual(result, Decimal("30.00"))
    
    def test_completed_wagering_requirements_excluded(self):
        """Wagering requirements with result set should not be counted."""
        user = self.create_user()
        self.create_wagering_requirement(user, balance=Decimal("30.00"), result=None)
        self.create_wagering_requirement(user, balance=Decimal("20.00"), result=Decimal("15.00"))
        
        result = get_wagering_balance(user)
        self.assertEqual(result, Decimal("30.00"))
    
    def test_non_betable_wagering_requirements_excluded(self):
        """Non-betable wagering requirements should not be counted."""
        user = self.create_user()
        self.create_wagering_requirement(user, balance=Decimal("30.00"), betable=False)
        self.create_wagering_requirement(user, balance=Decimal("20.00"), betable=True)
        
        result = get_wagering_balance(user)
        self.assertEqual(result, Decimal("20.00"))


class GetWageringRequirementsTests(TransactionTestCase, WageringTestMixin):
    """Tests for get_wagering_requirements function."""
    
    @transaction.atomic
    def test_returns_active_wagering_requirements_with_balance(self):
        """Should return only active WRs with balance > 0."""
        user = self.create_user()
        wr1 = self.create_wagering_requirement(user, balance=Decimal("30.00"), active=True)
        _wr2 = self.create_wagering_requirement(user, balance=Decimal("0.00"), active=True)
        _wr3 = self.create_wagering_requirement(user, balance=Decimal("20.00"), active=False)
        
        result = list(get_wagering_requirements(user))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, wr1.id)
    
    @transaction.atomic
    def test_orders_by_created_at(self):
        """Results should be ordered by created_at."""
        user = self.create_user()
        wr1 = self.create_wagering_requirement(user, balance=Decimal("10.00"))
        wr2 = self.create_wagering_requirement(user, balance=Decimal("20.00"))
        
        result = list(get_wagering_requirements(user))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].id, wr1.id)
        self.assertEqual(result[1].id, wr2.id)
    
    @transaction.atomic
    def test_only_returns_users_wagering_requirements(self):
        """Should only return WRs for the specified user."""
        user1 = self.create_user(username="user1")
        user2 = self.create_user(username="user2")
        wr1 = self.create_wagering_requirement(user1, balance=Decimal("30.00"))
        _wr2 = self.create_wagering_requirement(user2, balance=Decimal("20.00"))
        
        result = list(get_wagering_requirements(user1))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, wr1.id)


class SingleWRBetTests(TransactionTestCase, WageringTestMixin):
    """Tests for __single_wr_bet function (tested through bet_wr)."""
    
    def test_bet_reduces_balance(self):
        """Betting should reduce WR balance."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user, balance=Decimal("50.00"), played=Decimal("0.00"), limit=Decimal("100.00")
        )
        
        _result = bet_wr(user, Decimal("10.00"), [wr])
        
        wr.refresh_from_db()
        self.assertEqual(wr.balance, Decimal("40.00"))
        self.assertEqual(wr.played, Decimal("10.00"))
    
    def test_bet_not_betable_skipped(self):
        """Non-betable WRs should be skipped."""
        user = self.create_user(balance=Decimal("100.00"))
        wr = self.create_wagering_requirement(
            user, balance=Decimal("50.00"), betable=False
        )
        
        _result = bet_wr(user, Decimal("10.00"), [wr])
        
        wr.refresh_from_db()
        self.assertEqual(wr.balance, Decimal("50.00"))
        self.assertEqual(wr.played, Decimal("0.00"))
    
    def test_bet_completes_wr_when_limit_reached(self):
        """WR should be deactivated when limit is reached."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user, balance=Decimal("50.00"), played=Decimal("90.00"), limit=Decimal("100.00")
        )
        
        _result = bet_wr(user, Decimal("10.00"), [wr])
        
        wr.refresh_from_db()
        self.assertEqual(wr.active, False)
        self.assertIsNotNone(wr.result)
    
    def test_bet_returns_none_if_insufficient_funds(self):
        """Should return None if total balance is insufficient."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(user, balance=Decimal("5.00"))
        
        result = bet_wr(user, Decimal("10.00"), [wr])
        
        self.assertIsNone(result)
    
    def test_bet_with_multiple_wrs(self):
        """Betting should use multiple WRs in order."""
        user = self.create_user(balance=Decimal("0.00"))
        wr1 = self.create_wagering_requirement(
            user, balance=Decimal("5.00"), played=Decimal("0.00"), limit=Decimal("100.00")
        )
        wr2 = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("0.00"), limit=Decimal("100.00")
        )
        
        _result = bet_wr(user, Decimal("8.00"), [wr1, wr2])
        
        wr1.refresh_from_db()
        wr2.refresh_from_db()
        self.assertEqual(wr1.balance, Decimal("0.00"))
        self.assertEqual(wr1.played, Decimal("5.00"))
        self.assertEqual(wr2.balance, Decimal("7.00"))
        self.assertEqual(wr2.played, Decimal("3.00"))


class SingleWRClearTests(TransactionTestCase, WageringTestMixin):
    """Tests for __single_wr_clear function (tested through clear_wr)."""
    
    def test_clear_completes_when_limit_reached(self):
        """Clearing should complete WR and return balance when limit is reached."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user,
            balance=Decimal("10.00"),
            played=Decimal("90.00"),
            limit=Decimal("100.00"),
            betable=False,
        )
        
        clear_wr(user, Decimal("15.00"), [wr])
        
        wr.refresh_from_db()
        user.refresh_from_db()
        
        self.assertEqual(wr.active, False)
        self.assertEqual(wr.balance, Decimal("0.00"))
        self.assertEqual(user.balance_reactor, Decimal("10.00"))  # Balance returned to reactor pool
    
    def test_clear_partial_progress(self):
        """Clearing should update played without completing if limit not reached."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("15.00"),
            balance=Decimal("10.00"),
            played=Decimal("0.00"),
            limit=Decimal("225.00"),
            betable=False,
        )
        
        clear_wr(user, Decimal("15.00"), [wr])
        
        wr.refresh_from_db()
        self.assertEqual(wr.played, Decimal("15.00"))
        self.assertEqual(wr.result, Decimal("1.00"))
        self.assertEqual(wr.balance, Decimal("9.00"))
        self.assertEqual(wr.active, True)


class SingleWRPayTests(TransactionTestCase, WageringTestMixin):
    """Tests for __single_wr_pay function (tested through platform_pay)."""
    
    @transaction.atomic
    def test_pay_adds_to_wr_balance_if_active(self):
        """Payment should add to WR balance when active."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("10.00"),
            limit=Decimal("100.00"),
            played=Decimal("5.00"),
            betable=True,
        )
        
        data = {wr.id: (Decimal("1.00"), Decimal("5.00"))}
        data = serialize_wr_data(data)
        platform_pay(user, Decimal("10.00"), data)
        
        wr.refresh_from_db()
        # Payment should be proportional: 10.00 * 1.00 (100%) = 10.00
        self.assertEqual(wr.balance, Decimal("20.00"))

    @transaction.atomic
    def test_pay_returns_to_wallet_if_limit_passed(self):
        """Payment should go to wallet if WR limit was already passed."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user,
            balance=Decimal("0.00"),
            played=Decimal("100.00"),
            limit=Decimal("100.00"),
            active=False,
            result=Decimal("10.00"),
        )
        
        data = {wr.id: (Decimal("1.00"), Decimal("10.00"))}
        data = serialize_wr_data(data)
        platform_pay(user, Decimal("20.00"), data)
        
        user.refresh_from_db()
        # Payment should go directly to wagering pool
        self.assertGreater(user.balance_wagering, Decimal("0.00"))


class PlatformBetTests(TransactionTestCase, WageringTestMixin):
    """Tests for platform_bet function."""

    @transaction.atomic
    def test_small_bets(self):
        """Platform bet should return the correct amount of money to be bet."""
        user = self.create_user(balance=Decimal("100.00"))
        wr_betable = self.create_wagering_requirement(
            user, balance=Decimal("20.00"), betable=True
        )
        wr_clearable = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), betable=False
        )
        
        result = platform_bet(user, Decimal("0.50"))
        
        self.assertIsNotNone(result)
        if result is not None:
            result = result[0]
            # Only betable WR should be in result
            self.assertIn(str(wr_betable.id), result.keys())
            self.assertEqual(Decimal(result[str(wr_betable.id)][1]), Decimal("0.50"))
            self.assertNotIn(str(wr_clearable.id), result.keys())
    
    @transaction.atomic
    def test_platform_bet_separates_bettable_and_clearable(self):
        """Platform bet should separate betable and clearable WRs."""
        user = self.create_user(balance=Decimal("100.00"))
        wr_betable = self.create_wagering_requirement(
            user, balance=Decimal("20.00"), betable=True
        )
        wr_clearable = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), betable=False
        )
        
        result = platform_bet(user, Decimal("15.00"))
        
        self.assertIsNotNone(result)
        if result is not None:
            result = result[0]
            # Only betable WR should be in result
            self.assertIn(str(wr_betable.id), result.keys())
            self.assertNotIn(str(wr_clearable.id), result.keys())
    
    @transaction.atomic
    def test_platform_bet_returns_none_if_insufficient_funds(self):
        """Should return None if insufficient total funds."""
        user = self.create_user(balance=Decimal("0.00"))
        _wr = self.create_wagering_requirement(user, balance=Decimal("5.00"))
        
        result = platform_bet(user, Decimal("10.00"))
        
        self.assertIsNone(result)
    
    @transaction.atomic
    def test_platform_bet_clears_non_betable_wrs(self):
        """Non-betable WRs should be cleared on bet."""
        user = self.create_user(balance=Decimal("100.00"))
        _wr_betable = self.create_wagering_requirement(
            user, balance=Decimal("20.00"), betable=True
        )
        wr_clearable = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("95.00"), limit=Decimal("100.00"), betable=False
        )
        
        platform_bet(user, Decimal("10.00"))
        
        wr_clearable.refresh_from_db()
        self.assertEqual(wr_clearable.active, False)
    
    @transaction.atomic
    def test_platform_bet_uses_user_balance(self):
        """Platform bet should use user balance if no betable WRs are available."""
        user = self.create_user(balance=Decimal("100.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("10.00"),
            played=Decimal("0.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        
        result = platform_bet(user, Decimal("30.00"))
        
        wr.refresh_from_db()
        self.assertIsNotNone(result)
        if result is not None:
            self.assertIn(str(wr.id), result[0].keys())
            self.assertEqual(wr.played, Decimal("10.00"))
            self.assertEqual(wr.balance, Decimal("00.00"))
            self.assertEqual(user.balance, Decimal("80.00"))


class PlatformPayTests(TransactionTestCase, WageringTestMixin):
    """Tests for platform_pay function."""
    
    @transaction.atomic
    def test_platform_pay_distributes_winnings(self):
        """Platform pay should distribute winnings to WRs based on data."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user,
            balance=Decimal("10.00"),
            played=Decimal("10.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        
        # Data format: {wr_id: (ratio, amount_bet)}
        data = {wr.id: (Decimal("1.00"), Decimal("10.00"))}
        
        result = platform_pay(user, Decimal("20.00"), serialize_wr_data(data))
        
        self.assertIsNotNone(result)
        wr.refresh_from_db()
        # Won amount proportional to ratio of betted amount: 20.00 * 1.00 (100%) = 20.00
        # Balance = 10.00 + 20.00 = 30.00
        self.assertEqual(wr.balance, Decimal("30.00"))
    
    @transaction.atomic
    def test_platform_pay_handles_adjustment(self):
        """Platform pay should handle any adjustment differences."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("10.00"), limit=Decimal("100.00")
        )
        
        data = {wr.id: (Decimal("0.50"), Decimal("5.00"))}
        
        platform_pay(user, Decimal("20.00"), serialize_wr_data(data))
        
        wr.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(wr.balance, Decimal("20.00"))
        self.assertEqual(user.balance_wagering, Decimal("10.00"))

    @transaction.atomic
    def test_platform_pay_handles_adjustment_with_multiple_wrs(self):
        """Platform pay should handle any adjustment differences with multiple WRs."""
        user = self.create_user(balance=Decimal("0.00"))
        wr1 = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("10.00"), limit=Decimal("100.00")
        )
        wr2 = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("10.00"), limit=Decimal("100.00")
        )
        data = {
            wr1.id: (Decimal("0.40"), Decimal("10.00")),
            wr2.id: (Decimal("0.40"), Decimal("5.00")),
        }
        
        platform_pay(user, Decimal("20.00"), serialize_wr_data(data))
        
        wr1.refresh_from_db()
        wr2.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(wr1.balance, Decimal("18.00"))
        self.assertEqual(wr2.balance, Decimal("18.00"))
        self.assertEqual(user.balance_wagering, Decimal("4.00"))

    @transaction.atomic
    def test_platform_pay_handles_adjustment_with_multiple_wrs_and_different_ratios(self):
        """Platform pay should handle any adjustment differences with multiple WRs and different ratios."""
        user = self.create_user(balance=Decimal("0.00"))
        wr1 = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("10.00"), limit=Decimal("100.00")
        )
        wr2 = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("10.00"), limit=Decimal("100.00")
        )
        data = {
            wr1.id: (Decimal("0.50"), Decimal("5.00")),
            wr2.id: (Decimal("0.25"), Decimal("5.00")),
        }
        
        platform_pay(user, Decimal("20.00"), serialize_wr_data(data))
        
        user.refresh_from_db()
        wr1.refresh_from_db()
        wr2.refresh_from_db()
        self.assertEqual(wr1.balance, Decimal("20.00"))
        self.assertEqual(wr2.balance, Decimal("15.00"))
        self.assertEqual(user.balance_wagering, Decimal("5.00"))
    
    @transaction.atomic
    def test_platform_pay_handles_adjustment_with_multiple_wrs_and_odd_ratios(self):
        """Platform pay should handle any adjustment differences with multiple WRs and odd ratios."""
        user = self.create_user(balance=Decimal("0.00"))
        wr1 = self.create_wagering_requirement(
            user,
            amount=Decimal("21.00"),
            balance=Decimal("0.00"),
            played=Decimal("10.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        wr2 = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("0.00"),
            played=Decimal("10.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        data = {
            wr1.id: (Decimal("1.00")/ Decimal("3.00"), Decimal("21.00")),
            wr2.id: (Decimal("1.00")/ Decimal("7.00"), Decimal("9.00")),
        }
        
        platform_pay(user, Decimal("30.00"), serialize_wr_data(data))
        
        user.refresh_from_db()
        wr1.refresh_from_db()
        wr2.refresh_from_db()
        total_balance = (
            cast(Decimal, wr1.balance)
            + cast(Decimal, wr2.balance)
            + cast(Decimal, user.balance_wagering)
        )
        self.assertEqual(total_balance, Decimal("30.00"))

class IntegrationTests(TransactionTestCase, WageringTestMixin):
    """Integration tests for the full wagering workflow."""
    
    @transaction.atomic
    def test_full_betting_and_payout_workflow(self):
        """Test complete workflow: bet -> win -> payout."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("10.00"),
            played=Decimal("0.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        
        # Place a bet
        bet_amount = Decimal("10.00")
        bet_data = platform_bet(user, bet_amount)
        
        self.assertIsNotNone(bet_data)
        if TYPE_CHECKING:
            bet_data = ({}, Decimal("0.00"))
        data, _betted = bet_data
        
        self.assertIn(str(wr.id), data.keys())
        
        wr.refresh_from_db()
        self.assertEqual(wr.balance, Decimal("0.00"))
        self.assertEqual(wr.played, Decimal("10.00"))
        
        # Win and get payout
        won_amount = Decimal("25.00")
        platform_pay(user, won_amount, data)
        
        wr.refresh_from_db()
        user.refresh_from_db()
        
        # Winnings should be added to WR balance
        self.assertEqual(wr.balance, Decimal("25.00"))
    
    @transaction.atomic
    def test_wr_completion_releases_funds(self):
        """When WR limit is reached, balance should be released to user."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("10.00"),
            played=Decimal("95.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        
        # Place bet that reaches limit
        _bet_data = platform_bet(user, Decimal("5.00"))
        
        wr.refresh_from_db()
        user.refresh_from_db()
        
        self.assertEqual(wr.active, False)
        self.assertIsNotNone(wr.result)
    
    @transaction.atomic
    def test_multiple_wrs_processed_in_order(self):
        """Multiple WRs should be processed in creation order."""
        user = self.create_user(balance=Decimal("100.00"))
        
        wr1 = self.create_wagering_requirement(
            user, balance=Decimal("5.00"), played=Decimal("0.00"), limit=Decimal("100.00")
        )
        wr2 = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("0.00"), limit=Decimal("100.00")
        )
        
        # Bet more than first WR balance
        _bet_data = platform_bet(user, Decimal("8.00"))
        
        wr1.refresh_from_db()
        wr2.refresh_from_db()
        
        # First WR should be fully used
        self.assertEqual(wr1.balance, Decimal("0.00"))
        self.assertEqual(wr1.played, Decimal("5.00"))
        
        # Second WR should have remainder
        self.assertEqual(wr2.balance, Decimal("7.00"))
        self.assertEqual(wr2.played, Decimal("3.00"))
    
    @transaction.atomic
    def test_cancel_multiple_wrs_processed_in_order(self):
        """Multiple WRs should be processed in creation order."""
        user = self.create_user(balance=Decimal("100.00"))
        
        wr1 = self.create_wagering_requirement(
            user, balance=Decimal("5.00"), played=Decimal("0.00"), limit=Decimal("100.00")
        )
        wr2 = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("0.00"), limit=Decimal("100.00")
        )
        
        # Bet more than first WR balance
        data = platform_bet(user, Decimal("8.00"))
        
        self.assertIsNotNone(data)
        if TYPE_CHECKING:
            data = ({}, Decimal("0.00"))
        data, _adjustment = data
        
        wr1.refresh_from_db()
        wr2.refresh_from_db()

        # First WR should be fully used
        self.assertEqual(wr1.balance, Decimal("0.00"))
        self.assertEqual(wr1.played, Decimal("5.00"))
        
        # Second WR should have remainder
        self.assertEqual(wr2.balance, Decimal("7.00"))
        self.assertEqual(wr2.played, Decimal("3.00"))

        platform_cancel_bet_wr(user, data)
        
        wr1.refresh_from_db()
        wr2.refresh_from_db()

        # First WR should be fully used
        self.assertEqual(wr1.balance, Decimal("5.00"))
        self.assertEqual(wr1.played, Decimal("0.00"))
        
        # Second WR should have remainder
        self.assertEqual(wr2.balance, Decimal("10.00"))
        self.assertEqual(wr2.played, Decimal("0.00"))

    @transaction.atomic
    def test_cancel_multiple_wrs_processed_in_order_with_debit_large_wr(self):
        """Multiple WRs should be processed in creation order."""
        user = self.create_user(balance=Decimal("1.00"))
        
        wr1 = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("99.00"), limit=Decimal("100.00")
        )
        wr2 = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("0.00"), limit=Decimal("100.00")
        )

        playable_balance = platform_playable_balance(user)
        self.assertEqual(playable_balance, Decimal("21.00"))
        
        # Bet more than first WR balance
        data = platform_bet(user, Decimal("12.00"))
        
        self.assertIsNotNone(data)
        if TYPE_CHECKING:
            data = ({}, Decimal("0.00"))
        data, _adjustment = data
        
        wr1.refresh_from_db()
        wr2.refresh_from_db()
        user.refresh_from_db()

        # First WR should be fully used
        self.assertEqual(wr1.balance, Decimal("0.00"))
        self.assertEqual(wr1.played, Decimal("100.00"))
        
        # Second WR should have remainder
        self.assertEqual(wr2.balance, Decimal("0.00"))
        self.assertEqual(wr2.played, Decimal("10.00"))

        self.assertEqual(user.balance, Decimal("0.00"))
        self.assertEqual(user.balance_wagering, Decimal("9.00"))

        user.balance = Decimal("0.00")
        user.balance_wagering = Decimal("0.00")
        user.save()

        platform_cancel_bet_wr(user, data)

        wr1.refresh_from_db()
        wr2.refresh_from_db()
        user.refresh_from_db()

        playable_balance = platform_playable_balance(user)
        # after a 9 SC withdrawal
        self.assertEqual(playable_balance, Decimal("12.00"))

        self.assertEqual(user.balance, Decimal("0.00"))
        # First WR should be partially restored
        self.assertEqual(wr1.balance, Decimal("2.00"))
        self.assertEqual(wr1.played, Decimal("99.00"))
        
        # Second WR should have remainder
        self.assertEqual(wr2.balance, Decimal("10.00"))
        self.assertEqual(wr2.played, Decimal("0.00"))

    @transaction.atomic
    def test_cancel_multiple_wrs_processed_in_order_with_debit(self):
        """Multiple WRs should be processed in creation order."""
        user = self.create_user(balance=Decimal("1.00"))
        
        wr1 = self.create_wagering_requirement(
            user, balance=Decimal("30.00"), played=Decimal("99.00"), limit=Decimal("100.00")
        )
        wr2 = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("0.00"), limit=Decimal("100.00")
        )

        playable_balance = platform_playable_balance(user)
        self.assertEqual(playable_balance, Decimal("41.00"))
        
        # Bet more than first WR balance
        data = platform_bet(user, Decimal("32.00"))
        
        self.assertIsNotNone(data)
        if TYPE_CHECKING:
            data = ({}, Decimal("0.00"))
        data, _adjustment = data
        
        wr1.refresh_from_db()
        wr2.refresh_from_db()
        user.refresh_from_db()

        self.assertEqual(user.balance, Decimal("-20.00"))
        self.assertEqual(user.balance_wagering, Decimal("29.00"))

        user.balance = Decimal("0.00")
        user.balance_wagering = Decimal("0.00")
        user.save()

        platform_cancel_bet_wr(user, data)
        
        wr1.refresh_from_db()
        wr2.refresh_from_db()
        user.refresh_from_db()

        playable_balance = platform_playable_balance(user)
        self.assertEqual(user.balance, Decimal("0.00"))
        self.assertEqual(playable_balance, Decimal("32.00"))

    @transaction.atomic
    def test_cancel_single_wrs_processed_with_debit(self):
        """Multiple WRs should be processed in creation order."""
        user = self.create_user(balance=Decimal("0.00"))
        
        wr1 = self.create_wagering_requirement(
            user, balance=Decimal("100.00"), played=Decimal("99.00"), limit=Decimal("100.00")
        )

        playable_balance = platform_playable_balance(user)
        self.assertEqual(playable_balance, Decimal("100.00"))
        
        # Bet more than first WR balance
        data = platform_bet(user, Decimal("1.00"))
        
        self.assertIsNotNone(data)
        if TYPE_CHECKING:
            data = ({}, Decimal("0.00"))
        data, _adjustment = data
        
        wr1.refresh_from_db()
        user.refresh_from_db()

        self.assertEqual(user.balance, Decimal("0.00"))
        self.assertEqual(user.balance_wagering, Decimal("99.00"))

        user.balance = Decimal("0.00")
        user.balance_wagering = Decimal("0.00")
        user.save()

        platform_cancel_bet_wr(user, data)
        
        wr1.refresh_from_db()
        user.refresh_from_db()

        playable_balance = platform_playable_balance(user)
        self.assertEqual(user.balance, Decimal("0.00"))
        self.assertEqual(playable_balance, Decimal("1.00"))


class PlatformCancelBetWRTests(TransactionTestCase, WageringTestMixin):
    """Tests for platform_cancel_bet_wr function."""
    
    def _create_cancel_data(
        self,
        wr_data: Dict[int, Tuple[Decimal, Decimal]],
        from_wallet: Tuple[Decimal, Decimal] = (Decimal("0.00"), Decimal("0.00")),
        wr_clear: Tuple[Decimal, Decimal] = (Decimal("0.00"), Decimal("0.00")),
    ) -> Dict[str, Tuple[str, str]]:
        """Helper to create cancel data structure."""
        data = serialize_wr_data(wr_data)
        data["from_wallet"] = (str(from_wallet[0]), str(from_wallet[1]))
        data["wr_clear"] = (str(wr_clear[0]), str(wr_clear[1]))
        return data
    
    @transaction.atomic
    def test_cancel_restores_single_wr_balance(self):
        """Cancelling a bet should restore the WR balance."""
        user = self.create_user(balance=Decimal("100.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("5.00"),
            played=Decimal("5.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        
        # Cancel data: wr_id -> (ratio, amount_taken)
        cancel_data = self._create_cancel_data(
            wr_data={wr.id: (Decimal("1.00"), Decimal("5.00"))},
            from_wallet=(Decimal("0.00"), Decimal("0.00")),
        )
        
        platform_cancel_bet_wr(user, cancel_data)
        
        wr.refresh_from_db()
        user.refresh_from_db()
        
        # Balance should be restored
        self.assertEqual(wr.balance, Decimal("10.00"))
        self.assertEqual(wr.played, Decimal("0.00"))
        self.assertTrue(wr.active)
    
    @transaction.atomic
    def test_cancel_restores_wallet_amount(self):
        """Cancelling should restore the amount taken from wallet."""
        user = self.create_user(balance=Decimal("50.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("0.00"),
            played=Decimal("10.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        
        # Bet was 20: 10 from WR + 10 from wallet
        cancel_data = self._create_cancel_data(
            wr_data={wr.id: (Decimal("0.50"), Decimal("10.00"))},
            from_wallet=(Decimal("10.00"), Decimal("10.00")),
        )
        
        platform_cancel_bet_wr(user, cancel_data)
        
        user.refresh_from_db()
        
        # User balance should include the returned wallet amount
        self.assertGreaterEqual(user.balance, Decimal("50.00"))
    
    @transaction.atomic
    def test_cancel_multiple_wrs(self):
        """Cancelling should restore multiple WRs."""
        user = self.create_user(balance=Decimal("100.00"))
        wr1 = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("5.00"),
            played=Decimal("5.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        wr2 = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("7.00"),
            played=Decimal("3.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        
        cancel_data = self._create_cancel_data(
            wr_data={
                wr1.id: (Decimal("0.625"), Decimal("5.00")),
                wr2.id: (Decimal("0.375"), Decimal("3.00")),
            },
        )
        
        platform_cancel_bet_wr(user, cancel_data)
        
        wr1.refresh_from_db()
        wr2.refresh_from_db()
        
        # Both WRs should have their balances restored
        self.assertEqual(wr1.balance, Decimal("10.00"))
        self.assertEqual(wr1.played, Decimal("0.00"))
        self.assertEqual(wr2.balance, Decimal("10.00"))
        self.assertEqual(wr2.played, Decimal("0.00"))
    
    @transaction.atomic
    def test_cancel_reactivates_completed_wr(self):
        """Cancelling should reactivate a WR that was completed."""
        user = self.create_user(balance=Decimal("100.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("0.00"),
            played=Decimal("100.00"),
            limit=Decimal("100.00"),
            active=False,
            result=Decimal("5.00"),
            betable=True,
        )
        
        # Cancel the bet that completed the WR
        cancel_data = self._create_cancel_data(
            wr_data={wr.id: (Decimal("1.00"), Decimal("10.00"))},
        )
        
        platform_cancel_bet_wr(user, cancel_data)
        
        wr.refresh_from_db()
        
        # WR should be reactivated
        self.assertTrue(wr.active)
        self.assertIsNone(wr.result)
    
    @transaction.atomic
    def test_cancel_handles_depleted_wr(self):
        """Cancelling should handle WRs that were depleted (balance = 0)."""
        user = self.create_user(balance=Decimal("100.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("0.00"),
            played=Decimal("10.00"),
            limit=Decimal("100.00"),
            active=False,
            result=Decimal("0.00"),
            betable=True,
        )
        
        cancel_data = self._create_cancel_data(
            wr_data={wr.id: (Decimal("1.00"), Decimal("10.00"))},
        )
        
        platform_cancel_bet_wr(user, cancel_data)
        
        wr.refresh_from_db()
        
        # WR should be reactivated with balance restored
        self.assertTrue(wr.active)
        self.assertEqual(wr.played, Decimal("0.00"))
    
    @transaction.atomic
    def test_cancel_only_from_wallet(self):
        """Cancelling should work when bet was only from wallet."""
        user = self.create_user(balance=Decimal("90.00"))
        
        # No WRs involved, bet was purely from wallet
        cancel_data = self._create_cancel_data(
            wr_data={},
            from_wallet=(Decimal("10.00"), Decimal("10.00")),
        )
        
        platform_cancel_bet_wr(user, cancel_data)
        
        user.refresh_from_db()
        
        # User balance should have the wallet amount restored
        self.assertEqual(user.balance, Decimal("100.00"))


class SingleWRBetCancelTests(TransactionTestCase, WageringTestMixin):
    """Tests for __single_wr_bet_cancel function (tested through platform_cancel_bet_wr)."""
    
    def _create_cancel_data(
        self,
        wr_data: Dict[int, Tuple[Decimal, Decimal]],
        from_wallet: Tuple[Decimal, Decimal] = (Decimal("0.00"), Decimal("0.00")),
        wr_clear: Tuple[Decimal, Decimal] = (Decimal("0.00"), Decimal("0.00")),
    ) -> Dict[str, Tuple[str, str]]:
        """Helper to create cancel data structure."""
        data = serialize_wr_data(wr_data)
        data["from_wallet"] = (str(from_wallet[0]), str(from_wallet[1]))
        data["wr_clear"] = (str(wr_clear[0]), str(wr_clear[1]))
        return data
    
    @transaction.atomic
    def test_cancel_reduces_played_amount(self):
        """Cancelling should reduce the played amount."""
        user = self.create_user(balance=Decimal("100.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("20.00"),
            balance=Decimal("15.00"),
            played=Decimal("5.00"),
            limit=Decimal("200.00"),
            betable=True,
        )
        
        cancel_data = self._create_cancel_data(
            wr_data={wr.id: (Decimal("1.00"), Decimal("5.00"))},
        )
        
        platform_cancel_bet_wr(user, cancel_data)
        
        wr.refresh_from_db()
        
        self.assertEqual(wr.played, Decimal("0.00"))
    
    @transaction.atomic
    def test_cancel_clears_result_field(self):
        """Cancelling should clear the result field."""
        user = self.create_user(balance=Decimal("100.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("0.00"),
            played=Decimal("50.00"),
            limit=Decimal("100.00"),
            active=True,
            result=Decimal("5.00"),
            betable=True,
        )
        
        cancel_data = self._create_cancel_data(
            wr_data={wr.id: (Decimal("1.00"), Decimal("10.00"))},
        )
        
        platform_cancel_bet_wr(user, cancel_data)
        
        wr.refresh_from_db()
        
        self.assertIsNone(wr.result)
    
    @transaction.atomic
    def test_cancel_handles_played_greater_than_taken(self):
        """Cancelling should handle when played > taken (partial cancel)."""
        user = self.create_user(balance=Decimal("100.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("20.00"),
            balance=Decimal("10.00"),
            played=Decimal("15.00"),
            limit=Decimal("200.00"),
            betable=True,
        )
        
        # Cancel only 5 of the 15 played
        cancel_data = self._create_cancel_data(
            wr_data={wr.id: (Decimal("1.00"), Decimal("5.00"))},
        )
        
        platform_cancel_bet_wr(user, cancel_data)
        
        wr.refresh_from_db()
        
        # Played should be reduced by taken amount
        self.assertEqual(wr.played, Decimal("10.00"))


class CancelWRClearTests(TransactionTestCase, WageringTestMixin):
    """Tests for __cancel_wr_clear function (tested through platform_cancel_bet_wr)."""
    
    def _create_cancel_data(
        self,
        wr_data: Dict[int, Tuple[Decimal, Decimal]],
        from_wallet: Tuple[Decimal, Decimal] = (Decimal("0.00"), Decimal("0.00")),
        wr_clear: Tuple[Decimal, Decimal] = (Decimal("0.00"), Decimal("0.00")),
    ) -> Dict[str, Tuple[str, str]]:
        """Helper to create cancel data structure."""
        data = serialize_wr_data(wr_data)
        data["from_wallet"] = (str(from_wallet[0]), str(from_wallet[1]))
        data["wr_clear"] = (str(wr_clear[0]), str(wr_clear[1]))
        return data
    
    @transaction.atomic
    def test_cancel_with_wr_clear_zero(self):
        """Cancelling with zero wr_clear should not affect clearable WRs."""
        user = self.create_user(balance=Decimal("100.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("5.00"),
            played=Decimal("5.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        
        cancel_data = self._create_cancel_data(
            wr_data={wr.id: (Decimal("1.00"), Decimal("5.00"))},
            wr_clear=(Decimal("0.00"), Decimal("0.00")),
        )
        
        platform_cancel_bet_wr(user, cancel_data)
        
        user.refresh_from_db()
        
        # Balance should reflect only the WR restoration
        self.assertGreaterEqual(user.balance, Decimal("0.00"))
    
    @transaction.atomic
    def test_cancel_with_non_zero_wr_clear(self):
        """Cancelling with non-zero wr_clear should handle clearable WRs."""
        user = self.create_user(balance=Decimal("100.00"))
        wr_betable = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("5.00"),
            played=Decimal("5.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        _wr_clearable = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("8.00"),
            played=Decimal("10.00"),
            limit=Decimal("100.00"),
            betable=False,
        )
        
        # wr_clear represents (amount_cleared, played_amount)
        cancel_data = self._create_cancel_data(
            wr_data={wr_betable.id: (Decimal("1.00"), Decimal("5.00"))},
            wr_clear=(Decimal("2.00"), Decimal("10.00")),
        )
        
        platform_cancel_bet_wr(user, cancel_data)
        
        user.refresh_from_db()
        
        # User should have a valid balance after cancellation
        self.assertGreaterEqual(user.balance, Decimal("0.00"))


class CancelIntegrationTests(TransactionTestCase, WageringTestMixin):
    """Integration tests for the full cancel workflow."""
    
    def _create_cancel_data(
        self,
        wr_data: Dict[int, Tuple[Decimal, Decimal]],
        from_wallet: Tuple[Decimal, Decimal] = (Decimal("0.00"), Decimal("0.00")),
        wr_clear: Tuple[Decimal, Decimal] = (Decimal("0.00"), Decimal("0.00")),
    ) -> Dict[str, Tuple[str, str]]:
        """Helper to create cancel data structure."""
        data = serialize_wr_data(wr_data)
        data["from_wallet"] = (str(from_wallet[0]), str(from_wallet[1]))
        data["wr_clear"] = (str(wr_clear[0]), str(wr_clear[1]))
        return data
    
    @transaction.atomic
    def test_bet_then_cancel_restores_original_state(self):
        """Full workflow: bet -> cancel should restore original state."""
        user = self.create_user(balance=Decimal("50.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("10.00"),
            played=Decimal("0.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        
        original_wr_balance = wr.balance
        original_wr_played = wr.played
        original_user_balance = user.balance
        
        # Place a bet
        bet_amount = Decimal("15.00")
        bet_data = platform_bet(user, bet_amount)
        
        self.assertIsNotNone(bet_data)
        if bet_data is None:
            return
        
        data, _adjustment = bet_data
        
        # Verify bet was placed
        wr.refresh_from_db()
        user.refresh_from_db()
        self.assertNotEqual(wr.balance, original_wr_balance)
        self.assertEqual(wr.balance, Decimal("0.00"))
        self.assertEqual(user.balance, Decimal("45.00"))
        
        # Cancel the bet
        platform_cancel_bet_wr(user, data)
        
        wr.refresh_from_db()
        user.refresh_from_db()
        
        # State should be restored (approximately, due to rounding)
        self.assertEqual(wr.balance, original_wr_balance)
        self.assertEqual(wr.played, original_wr_played)
        self.assertEqual(user.balance, original_user_balance)
    
    @transaction.atomic
    def test_cancel_preserves_total_funds(self):
        """Cancelling should preserve total funds in the system."""
        user = self.create_user(balance=Decimal("100.00"))
        wr1 = self.create_wagering_requirement(
            user,
            amount=Decimal("20.00"),
            balance=Decimal("20.00"),
            played=Decimal("0.00"),
            limit=Decimal("200.00"),
            betable=True,
        )
        wr2 = self.create_wagering_requirement(
            user,
            amount=Decimal("15.00"),
            balance=Decimal("15.00"),
            played=Decimal("0.00"),
            limit=Decimal("150.00"),
            betable=True,
        )
        
        initial_total = (
            cast(Decimal, user.balance) +
            cast(Decimal, user.balance_wagering) +
            cast(Decimal, user.balance_reactor) +
            cast(Decimal, wr1.balance) +
            cast(Decimal, wr2.balance)
        )
        
        # Place a bet
        bet_data = platform_bet(user, Decimal("25.00"))
        
        self.assertIsNotNone(bet_data)
        if bet_data is None:
            return
        
        data, _adjustment = bet_data
        
        # Build cancel data
        wr_cancel_data = {}
        from_wallet = (Decimal("0.00"), Decimal("0.00"))
        
        for key, value in data.items():
            if key == "from_wallet":
                from_wallet = (Decimal(value[0]), Decimal(value[1]))
            elif key != "wr_clear":
                wr_cancel_data[int(key)] = (Decimal(value[0]), Decimal(value[1]))
        
        cancel_data = self._create_cancel_data(
            wr_data=wr_cancel_data,
            from_wallet=from_wallet,
        )
        
        # Cancel the bet
        platform_cancel_bet_wr(user, cancel_data)
        
        wr1.refresh_from_db()
        wr2.refresh_from_db()
        user.refresh_from_db()
        
        final_total = (
            cast(Decimal, user.balance) +
            cast(Decimal, user.balance_wagering) +
            cast(Decimal, user.balance_reactor) +
            cast(Decimal, wr1.balance) +
            cast(Decimal, wr2.balance)
        )
        
        # Total funds should be preserved
        self.assertEqual(initial_total, final_total)
    
    @transaction.atomic
    def test_cancel_mixed_wr_and_wallet_bet(self):
        """Cancelling a bet from both WR and wallet should restore both."""
        user = self.create_user(balance=Decimal("50.00"))
        wr = self.create_wagering_requirement(
            user,
            amount=Decimal("10.00"),
            balance=Decimal("10.00"),
            played=Decimal("0.00"),
            limit=Decimal("100.00"),
            betable=True,
        )
        
        # Bet 20: should take 10 from WR, 10 from wallet
        bet_data = platform_bet(user, Decimal("20.00"))
        
        self.assertIsNotNone(bet_data)
        if bet_data is None:
            return
        
        data, _adjustment = bet_data
        
        wr.refresh_from_db()
        user.refresh_from_db()
        
        # Verify WR was depleted and wallet was used
        self.assertEqual(wr.balance, Decimal("0.00"))
        self.assertEqual(user.balance, Decimal("40.00"))
        
        # Build cancel data
        wr_cancel_data = {}
        from_wallet = (Decimal("0.00"), Decimal("0.00"))
        
        for key, value in data.items():
            if key == "from_wallet":
                from_wallet = (Decimal(value[0]), Decimal(value[1]))
            elif key != "wr_clear":
                wr_cancel_data[int(key)] = (Decimal(value[0]), Decimal(value[1]))
        
        cancel_data = self._create_cancel_data(
            wr_data=wr_cancel_data,
            from_wallet=from_wallet,
        )
        
        # Cancel
        platform_cancel_bet_wr(user, cancel_data)
        
        wr.refresh_from_db()
        user.refresh_from_db()
        
        # Both should be restored
        self.assertEqual(wr.balance, Decimal("10.00"))
        self.assertEqual(user.balance, Decimal("50.00"))

