import time
import uuid
from django.conf import settings
from django.utils import timezone
from redis import Redis, ConnectionPool

pool = ConnectionPool(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=0)
redis_client = Redis(connection_pool=pool)


class RateLimiter:
    def __init__(self, redis_client: Redis):
        self.redis = redis_client

        # Fixed window Lua (1 command, atomic)
        self.fixed_script = self.redis.register_script("""
        local current = redis.call("INCR", KEYS[1])
        if current == 1 then
            redis.call("EXPIRE", KEYS[1], ARGV[1])
        end
        return current <= tonumber(ARGV[2]) and 1 or 0
        """)

        # Sliding window Lua (1 command, atomic)
        self.sliding_script = self.redis.register_script("""
        local now = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local cutoff = now - window

        redis.call("ZREMRANGEBYSCORE", KEYS[1], 0, cutoff)
        local count = redis.call("ZCARD", KEYS[1])

        if count < limit then
            redis.call("ZADD", KEYS[1], now, now)
            redis.call("EXPIRE", KEYS[1], window)
            return 1
        else
            return 0
        end
        """)
            
    def is_key_locked(self, key: str) -> int:
        """
        returns 0 when key is not locked any other way
        the return will mean the amount of seconds the
        user has to wait before using any promo code.
        """
        now = int(timezone.now().timestamp())
        raw = self.redis.get(f"lock:{key}")
        if raw is None:
            return 0  # no lock
        try:
            expiry = int(raw) # type: ignore
        except (ValueError, TypeError):
            return 0
        remaining = expiry - now
        return remaining if remaining > 0 else 0

    def lock_key(self, key: str, timeout: int = 3600) -> bool:
        expiry = int(timezone.now().timestamp()) + timeout
        return bool(self.redis.set(f"lock:{key}", expiry, ex=timeout, nx=True))

    def allow(self,
              key: str,
              limit: int,
              window: int,
              sliding: bool = False) -> bool:
        if sliding:
            now = int(time.time())
            result = self.sliding_script(keys=[key], args=[now, window, limit])
        else:
            result = self.fixed_script(keys=[key], args=[window, limit])
        return bool(result)

    def time_left(self, key: str) -> int:
        """
        Returns how many seconds are left until the rate limit resets.
        For both fixed and sliding windows.
        """
        ttl: Optional[int] = self.redis.ttl(key)  # type: ignore
        # -2 = key does not exist, -1 = key exists but has no TTL
        if ttl is None or ttl < 0:
            return 0
        return ttl

# TODO:
# Configurable retry interval
# Currently hardcoded time.sleep(0.2). You might make it configurable or use exponential backoff.
# Error handling on release
# The Lua script returns 0 if the lock is gone or expired. Consider logging this situation for debugging.
# Timeout flexibility
# Right now, __enter__ uses timeout=10 even though class TTL is 30. Make this consistent or allow override in lock(key, timeout).
# Optional non-blocking mode
# You could expose block=False as an option in lock(key) for fire-and-forget scenarios.

class RedisDynamicLock:
    def __init__(self, redis_client, ttl=30):
        self.redis = redis_client
        self.ttl = ttl

        # register the release Lua script once
        self.release_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        self.release_sha = self.redis.script_load(self.release_script)

    class _LockContext:
        def __init__(self, parent, key):
            self.parent = parent
            self.key = f"lock:{key}"
            self.token = str(uuid.uuid4())

        def acquire(self, block=True, timeout: int=30):
            end = time.time() + timeout
            while time.time() < end:
                if self.parent.redis.set(self.key, self.token, nx=True, ex=self.parent.ttl):
                    return True
                if not block:
                    return False
                time.sleep(0.2)
            return False

        def release(self):
            # call the pre-registered script by SHA
            self.parent.redis.evalsha(self.parent.release_sha, 1, self.key, self.token)

        def __enter__(self):
            if not self.acquire(block=True, timeout=30):
                raise TimeoutError(f"Could not acquire lock {self.key}")
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.release()
            return False

    def lock(self, key):
        return self._LockContext(self, key)


dynamic_lock = RedisDynamicLock(redis_client=redis_client, ttl=30)
limiter = RateLimiter(redis_client=redis_client)
