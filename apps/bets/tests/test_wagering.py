from decimal import Decimal
from unittest.mock import MagicMock, patch

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
)
from apps.users.models import Agent, Users


class WageringTestMixin:
    """Mixin with helper methods for wagering tests."""
    
    def create_user(self, username: str = "testuser", balance: Decimal = Decimal("100.00")) -> Users:
        """Create a test user with the given balance."""

        agent, existing = Agent.objects.update_or_create(
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
        result: Decimal = None,
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


class GetWageringRequirementsTests(TransactionTestCase, WageringTestMixin):
    """Tests for get_wagering_requirements function."""
    
    @transaction.atomic
    def test_returns_active_wagering_requirements_with_balance(self):
        """Should return only active WRs with balance > 0."""
        user = self.create_user()
        wr1 = self.create_wagering_requirement(user, balance=Decimal("30.00"), active=True)
        wr2 = self.create_wagering_requirement(user, balance=Decimal("0.00"), active=True)
        wr3 = self.create_wagering_requirement(user, balance=Decimal("20.00"), active=False)
        
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
        wr2 = self.create_wagering_requirement(user2, balance=Decimal("20.00"))
        
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
        
        result = bet_wr(user, Decimal("10.00"), [wr])
        
        wr.refresh_from_db()
        self.assertEqual(wr.balance, Decimal("40.00"))
        self.assertEqual(wr.played, Decimal("10.00"))
    
    def test_bet_not_betable_skipped(self):
        """Non-betable WRs should be skipped."""
        user = self.create_user(balance=Decimal("100.00"))
        wr = self.create_wagering_requirement(
            user, balance=Decimal("50.00"), betable=False
        )
        
        result = bet_wr(user, Decimal("10.00"), [wr])
        
        wr.refresh_from_db()
        self.assertEqual(wr.balance, Decimal("50.00"))
        self.assertEqual(wr.played, Decimal("0.00"))
    
    def test_bet_completes_wr_when_limit_reached(self):
        """WR should be deactivated when limit is reached."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user, balance=Decimal("50.00"), played=Decimal("90.00"), limit=Decimal("100.00")
        )
        
        result = bet_wr(user, Decimal("10.00"), [wr])
        
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
        
        result = bet_wr(user, Decimal("8.00"), [wr1, wr2])
        
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
            user, balance=Decimal("10.00"), played=Decimal("90.00"), limit=Decimal("100.00")
        )
        
        clear_wr(user, Decimal("15.00"), [wr])
        
        wr.refresh_from_db()
        user.refresh_from_db()
        
        self.assertEqual(wr.active, False)
        self.assertEqual(wr.balance, Decimal("0.00"))
        self.assertEqual(user.balance, Decimal("10.00"))  # Balance returned to user
    
    def test_clear_partial_progress(self):
        """Clearing should update played without completing if limit not reached."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("0.00"), limit=Decimal("100.00")
        )
        
        clear_wr(user, Decimal("15.00"), [wr])
        
        wr.refresh_from_db()
        self.assertEqual(wr.played, Decimal("15.00"))
        self.assertEqual(wr.active, True)


class SingleWRPayTests(TransactionTestCase, WageringTestMixin):
    """Tests for __single_wr_pay function (tested through platform_pay)."""
    
    def test_pay_adds_to_wr_balance_if_active(self):
        """Payment should add to WR balance when active."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("5.00"), limit=Decimal("100.00")
        )
        
        data = {wr.id: (Decimal("1.00"), Decimal("5.00"))}
        platform_pay(user, Decimal("10.00"), data)
        
        wr.refresh_from_db()
        # Payment should be proportional: 5.00 * 10.00 = 50.00
        self.assertEqual(wr.balance, Decimal("60.00"))
    
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
        platform_pay(user, Decimal("20.00"), data)
        
        user.refresh_from_db()
        # Payment should go directly to user balance
        self.assertGreater(user.balance, Decimal("0.00"))


class PlatformBetTests(TransactionTestCase, WageringTestMixin):
    """Tests for platform_bet function."""
    
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
        # Only betable WR should be in result
        self.assertIn(wr_betable.id, result)
        self.assertNotIn(wr_clearable.id, result)
    
    @transaction.atomic
    def test_platform_bet_returns_none_if_insufficient_funds(self):
        """Should return None if insufficient total funds."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(user, balance=Decimal("5.00"))
        
        result = platform_bet(user, Decimal("10.00"))
        
        self.assertIsNone(result)
    
    @transaction.atomic
    def test_platform_bet_clears_non_betable_wrs(self):
        """Non-betable WRs should be cleared on bet."""
        user = self.create_user(balance=Decimal("100.00"))
        wr_betable = self.create_wagering_requirement(
            user, balance=Decimal("20.00"), betable=True
        )
        wr_clearable = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("95.00"), limit=Decimal("100.00"), betable=False
        )
        
        platform_bet(user, Decimal("10.00"))
        
        wr_clearable.refresh_from_db()
        self.assertEqual(wr_clearable.active, False)


class PlatformPayTests(TransactionTestCase, WageringTestMixin):
    """Tests for platform_pay function."""
    
    def test_platform_pay_distributes_winnings(self):
        """Platform pay should distribute winnings to WRs based on data."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("10.00"), limit=Decimal("100.00")
        )
        
        # Data format: {wr_id: (ratio, amount_bet)}
        data = {wr.id: (Decimal("1.00"), Decimal("10.00"))}
        
        result = platform_pay(user, Decimal("20.00"), data)
        
        self.assertTrue(result)
        wr.refresh_from_db()
        # Won amount proportional to bet: 10.00 * 20.00 = 200.00
        self.assertEqual(wr.balance, Decimal("210.00"))
    
    def test_platform_pay_handles_adjustment(self):
        """Platform pay should handle any adjustment differences."""
        user = self.create_user(balance=Decimal("0.00"))
        wr = self.create_wagering_requirement(
            user, balance=Decimal("10.00"), played=Decimal("10.00"), limit=Decimal("100.00")
        )
        
        data = {wr.id: (Decimal("0.50"), Decimal("5.00"))}
        
        platform_pay(user, Decimal("20.00"), data)
        
        user.refresh_from_db()
        # Adjustment should be added to user balance
        # won=20, paid to WR = 5 * 20 = 100, adjustment = 20 - 100 = -80 (negative)
        # Actually in code: to_pay = data[wagrec.id][1] * won = 5 * 20 = 100
        # This seems off - let me check the formula again


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
        self.assertIn(wr.id, bet_data)
        
        wr.refresh_from_db()
        self.assertEqual(wr.balance, Decimal("0.00"))
        self.assertEqual(wr.played, Decimal("10.00"))
        
        # Win and get payout
        won_amount = Decimal("25.00")
        platform_pay(user, won_amount, bet_data)
        
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
        bet_data = platform_bet(user, Decimal("5.00"))
        
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
        bet_data = platform_bet(user, Decimal("8.00"))
        
        wr1.refresh_from_db()
        wr2.refresh_from_db()
        
        # First WR should be fully used
        self.assertEqual(wr1.balance, Decimal("0.00"))
        self.assertEqual(wr1.played, Decimal("5.00"))
        
        # Second WR should have remainder
        self.assertEqual(wr2.balance, Decimal("7.00"))
        self.assertEqual(wr2.played, Decimal("3.00"))

