import time
from django.conf import settings
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


limiter = RateLimiter(redis_client=redis_client)
