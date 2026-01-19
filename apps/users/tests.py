# tests/test_promocodes.py
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch
import fakeredis

from django.test import TestCase, override_settings
from django.utils import timezone

# Modules under test
import apps.core.concurrency as concurrency_module
import apps.users.promo_handler as promo_module

from apps.users.models import Users, Agent, BonusPercentage, PromoCodes, PromoCodesLogs
from apps.bets.models import Transactions


class TestLimiter:
    """Test double for RateLimiter that doesn't use Lua scripts"""
    def __init__(self, redis_client):
        self.redis = redis_client

    def allow(self, key, window, limit, sliding=False):
        """
        Simple rate limiting without Lua scripts.
        Parameters match real RateLimiter signature: key, limit, window, sliding
        But for simplicity we accept them in different order for backward compatibility
        """
        current = self.redis.get(key)
        if current is None:
            self.redis.set(key, 1, ex=window)
            return True
        current = int(current)
        if current >= limit:
            return False
        self.redis.incr(key)
        return True

    def lock_key(self, key, timeout: int=3600):
        """
        Lock a key for a specific duration.
        Mimics RateLimiter.lock_key behavior.
        Returns True if lock was acquired, False if already locked.
        """
        lock_key = f"lock:{key}"
        # Use SET with NX (only set if not exists)
        result = self.redis.set(lock_key, 1, ex=timeout, nx=True)
        return bool(result)

    def ban(self, key, ban_time):
        """Ban a key for a specific duration (alias for lock_key)"""
        self.lock_key(key, timeout=ban_time)

    def is_banned(self, key):
        """Check if a key is banned"""
        return self.redis.get(f"lock:{key}") is not None

    def is_key_locked(self, key):
        """
        Check if a key is locked.
        Returns 0 when key is not locked, otherwise returns seconds remaining.
        Mimics the real RateLimiter.is_key_locked behavior.
        """
        lock_key = f"lock:{key}"
        raw = self.redis.get(lock_key)
        if raw is None:
            return 0
        # Check TTL to determine remaining time
        ttl = self.redis.ttl(lock_key)
        if ttl is None or ttl < 0:
            return 0
        return ttl

    def time_left(self, key, limit, window, sliding=False):
        """
        Returns how many seconds are left until the rate limit resets.
        Mimics RateLimiter.time_left behavior.
        """
        ttl = self.redis.ttl(key)
        if ttl is None or ttl < 0:
            return 0
        
        # Check if limit has been reached
        current = self.redis.get(key)
        try:
            count = int(current or 0)
        except ValueError:
            count = 0
        
        if count < limit:
            return 0  # under limit, no enforced wait
        
        return ttl


# Create single instances to be shared across all tests
_fake_redis = fakeredis.FakeStrictRedis()
_test_limiter = TestLimiter(redis_client=_fake_redis)


@override_settings(BONUS_MULTIPLIER=5000)
class PromoCodesTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fake_redis = _fake_redis
        
        # Replace limiter in BOTH modules before any tests run
        concurrency_module.limiter = _test_limiter
        promo_module.limiter = _test_limiter

    def setUp(self):
        # Ensure redis is clean between tests
        self.fake_redis.flushall()

        # Create a single Agent
        self.agent = Agent.objects.create(
            username="agent1",
            password="secret",
            role="agent",
            balance=Decimal("0.00"),
            bonus_balance=Decimal("0.00"),
        )

        # Player user that references the agent
        self.user = Users.objects.create(
            username="player1",
            password="secret",
            role="player",
            agent=self.agent,
            balance=Decimal("100.00"),
            bonus_balance=Decimal("0.00"),
        )

        # Create BonusPercentage rows
        self.bp_welcome = BonusPercentage.objects.create(
            dealer=None,
            percentage=10.0,
            bonus_type="welcome_bonus",
            deposit_bonus_limit=1,
            referral_bonus_limit=1,
            welcome_bonus_limit=1,
            losing_bonus_limit=1,
            bet_bonus_limit=1,
            bet_bonus_per_day_limit=1,
            deposit_bonus_per_day_limit=1,
        )

        self.bp_deposit = BonusPercentage.objects.create(
            dealer=None,
            percentage=10.0,
            bonus_type="deposit_bonus",
            deposit_bonus_limit=1,
            referral_bonus_limit=1,
            welcome_bonus_limit=1,
            losing_bonus_limit=1,
            bet_bonus_limit=1,
            bet_bonus_per_day_limit=1,
            deposit_bonus_per_day_limit=1,
        )

        now_date = timezone.now().date()

        # Instant promo
        self.promo_instant = PromoCodes.objects.create(
            dealer=None,
            bonus=self.bp_welcome,
            promo_code="INSTANT100",
            start_date=now_date - timedelta(days=1),
            end_date=now_date + timedelta(days=1),
            bonus_percentage=0.0,
            gold_percentage=0.0,
            is_expired=False,
            usage_limit=10,
            limit_per_user=5,
            max_bonus_limit=1000,
            bonus_distribution_method=PromoCodes.BonusDistributionMethod.instant,
            instant_bonus_amount=Decimal("50.00"),
            gold_bonus=Decimal("10.00"),
        )

        # Mixture promo
        self.promo_mixture = PromoCodes.objects.create(
            dealer=None,
            bonus=self.bp_deposit,
            promo_code="MIX10",
            start_date=now_date - timedelta(days=1),
            end_date=now_date + timedelta(days=1),
            bonus_percentage=10.0,
            gold_percentage=5.0,
            is_expired=False,
            usage_limit=10,
            limit_per_user=5,
            max_bonus_limit=1000,
            bonus_distribution_method=PromoCodes.BonusDistributionMethod.mixture,
            instant_bonus_amount=Decimal("0.00"),
            gold_bonus=Decimal("5.00"),
        )

        # Deposit promo
        self.promo_deposit = PromoCodes.objects.create(
            dealer=None,
            bonus=self.bp_deposit,
            promo_code="DEP10",
            start_date=now_date - timedelta(days=1),
            end_date=now_date + timedelta(days=1),
            bonus_percentage=10.0,
            gold_percentage=1.0,
            is_expired=False,
            usage_limit=10,
            limit_per_user=5,
            max_bonus_limit=1000000,
            bonus_distribution_method=PromoCodes.BonusDistributionMethod.deposit,
            instant_bonus_amount=Decimal("0.00"),
            gold_bonus=Decimal("2.00"),
        )

        # Limited usage promo
        self.promo_limited = PromoCodes.objects.create(
            dealer=None,
            bonus=self.bp_welcome,
            promo_code="LIMITED",
            start_date=now_date - timedelta(days=1),
            end_date=now_date + timedelta(days=1),
            is_expired=False,
            usage_limit=1,
            limit_per_user=1,
            max_bonus_limit=1000,
            bonus_distribution_method=PromoCodes.BonusDistributionMethod.instant,
            instant_bonus_amount=Decimal("5.00"),
            gold_bonus=Decimal("1.00"),
        )

        # Patch helper functions
        self.generate_ref_patch = patch(
            "apps.users.promo_handler.generate_reference",
            return_value="REF-TEST-123"
        )
        self.notify_patch = patch(
            "apps.users.promo_handler.send_player_balance_update_notification",
            return_value=None
        )
        self.generate_ref_patch.start()
        self.notify_patch.start()

    def tearDown(self):
        self.generate_ref_patch.stop()
        self.notify_patch.stop()
        self.fake_redis.flushall()

    def test_valid_promo_instant_redeem_creates_transaction_and_not_updates_balance(self):
        success, msg = promo_module.redeem_code(
            user=self.user,
            promo_code="INSTANT100",
            amount_dep=None,
            bonus_type="welcome",
        )
        self.assertTrue(success)
        self.assertEqual(msg, "OK")

        self.user.refresh_from_db()
        # New balance will be sent to WR
        self.assertEqual(self.user.balance, Decimal("100.00"))
        self.assertEqual(self.user.bonus_balance, Decimal("10.00"))

        tx = Transactions.objects.filter(user=self.user, journal_entry="bonus").first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal("50.00"))
        self.assertEqual(tx.bonus_amount, Decimal("10.00"))
        self.assertEqual(tx.status, "charged")

        log = PromoCodesLogs.objects.filter(
            user=self.user,
            promocode=self.promo_instant
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.transfer, Decimal("50.00"))
        self.assertEqual(log.transfer_gold, Decimal("10.00"))

    def test_valid_promo_mixture_redeem_not_updates_balance(self):
        success, msg = promo_module.redeem_code(
            user=self.user,
            promo_code="MIX10",
            amount_dep=Decimal("10.00"),
            bonus_type="deposit",
        )
        self.assertTrue(success, msg or "redeem returned False")
        self.assertEqual(msg, "OK")

        self.user.refresh_from_db()
        # Bonus know will be added to the wr
        self.assertEqual(self.user.balance, Decimal("100.00"))
        self.assertEqual(self.user.bonus_balance, Decimal("5.00"))

        tx = Transactions.objects.filter(
            user=self.user,
            journal_entry="bonus"
        ).order_by("-id").first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal("1.00"))
        self.assertEqual(tx.bonus_amount, Decimal("5.00"))

    def test_valid_promo_deposit_redeem_not_updates_balance_and_bonus_multiplier(self):
        amount_dep = Decimal("20.00")
        success, msg = promo_module.redeem_code(
            user=self.user,
            promo_code="DEP10",
            amount_dep=amount_dep,
            bonus_type="deposit",
        )
        self.assertTrue(success, msg or "redeem returned False")
        self.assertEqual(msg, "OK")

        self.user.refresh_from_db()
        # New balance will be sent to WR
        self.assertEqual(self.user.balance, Decimal("100.00"))

        tx = Transactions.objects.filter(
            user=self.user,
            journal_entry="bonus"
        ).order_by("-id").first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal("2.00"))
        expected_bonus_amount = Decimal("2.00") * Decimal(str(5000))
        self.assertEqual(tx.bonus_amount, expected_bonus_amount)

    def test_verify_code_expired(self):
        now_date = timezone.now().date()
        _expired = PromoCodes.objects.create(
            dealer=None,
            bonus=self.bp_welcome,
            promo_code="OLD",
            start_date=now_date - timedelta(days=10),
            end_date=now_date - timedelta(days=5),
            is_expired=False,
            usage_limit=1,
            limit_per_user=1,
            max_bonus_limit=1000,
            bonus_distribution_method=PromoCodes.BonusDistributionMethod.deposit,
            instant_bonus_amount=Decimal("0.00"),
            gold_bonus=Decimal("0.00"),
        )

        promo_obj, msg = promo_module.verify_code(promo_code="OLD", user=self.user)
        self.assertIsNone(promo_obj)
        self.assertEqual(msg, "Promo-code Expired")

    def test_usage_limit_reached_prevents_redeem(self):
        # Create a promo with usage_limit=1, then create a log to consume it
        p = PromoCodes.objects.create(
            dealer=None,
            bonus=self.bp_welcome,
            promo_code="LIMITED2",
            start_date=timezone.now().date() - timedelta(days=1),
            end_date=timezone.now().date() + timedelta(days=1),
            is_expired=False,
            usage_limit=1,
            limit_per_user=1,
            max_bonus_limit=1000,
            bonus_distribution_method=PromoCodes.BonusDistributionMethod.instant,
            instant_bonus_amount=Decimal("5.00"),
            gold_bonus=Decimal("1.00"),
        )

        PromoCodesLogs.objects.create(
            promocode=p,
            date=timezone.now(),
            transfer=Decimal("5.00"),
            transfer_gold=Decimal("1.00"),
            log="used",
            user=self.user,
        )

        success, msg = promo_module.redeem_code(
            user=self.user,
            promo_code="LIMITED2",
            amount_dep=None,
            bonus_type="welcome",
        )
        self.assertFalse(success)
        self.assertEqual(msg, "Promo-code use limit exceeded")

        p.refresh_from_db()
        self.assertTrue(p.is_expired)

    def test_invalid_amount_for_deposit_or_mixture(self):
        # MIX10 is mixture and requires amount_dep > 0
        success, msg = promo_module.redeem_code(
            user=self.user,
            promo_code="MIX10",
            amount_dep=None,
            bonus_type="deposit",
        )
        self.assertFalse(success)
        self.assertEqual(msg, "Invalid deposit amount.")

        success2, msg2 = promo_module.redeem_code(
            user=self.user,
            promo_code="DEP10",
            amount_dep=Decimal("0.00"),
            bonus_type="deposit",
        )
        self.assertFalse(success2)
        self.assertEqual(msg2, "Invalid deposit amount.")

    def test_rate_limit_behavior_on_failed_attempts(self):
        # Ensure redis is clean
        self.fake_redis.flushall()

        # Try invalid promo repeatedly; should eventually get locked
        lock_seen = False
        last_msg = None
        for _ in range(10):
            _promo_obj, msg = promo_module.verify_code(
                promo_code="DOES_NOT_EXIST",
                user=self.user
            )
            last_msg = msg
            if msg and msg.startswith("Too many attempts"):
                lock_seen = True
                break

        self.assertTrue(lock_seen, f"Expected lock message; last msg: {last_msg}")

        # Verify the lock key exists in fakeredis
        key = promo_module._generate_key(user=self.user, ip=None)
        lock_key = f"lock:{key}"
        raw = self.fake_redis.get(lock_key)
        self.assertIsNotNone(
            raw,
            "Expected lock entry in redis after rate-limit reached"
        )