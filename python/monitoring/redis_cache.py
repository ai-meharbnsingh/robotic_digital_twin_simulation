"""
RedisCache — caches robot positions and frequently accessed data in Redis.

Real Redis client. Graceful degradation if Redis is unavailable.
No MagicMock. No faking.
"""

import json
from typing import Any, Optional

import redis.asyncio as aioredis


class RedisCache:
    """
    Caches robot positions and fleet state in Redis for fast reads.
    Graceful degradation: all methods return None/empty if Redis unavailable.
    """

    def __init__(self, redis_url: str):
        """
        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379).
        """
        self.redis_url = redis_url
        self._client: Optional[aioredis.Redis] = None
        self._available = False

    async def connect(self) -> bool:
        """
        Connect to Redis.

        Returns:
            True if connection succeeded.
        """
        try:
            self._client = aioredis.from_url(
                self.redis_url,
                socket_connect_timeout=3,
                decode_responses=True,
            )
            pong = await self._client.ping()
            self._available = pong is True
            return self._available
        except Exception:
            self._available = False
            return False

    async def set_robot_position(self, robot_id: str, pose: dict[str, float], ttl_s: int = 30) -> bool:
        """
        Cache a robot's position.

        Args:
            robot_id: Robot identifier.
            pose: {x, y, theta} position.
            ttl_s: Time to live in seconds.

        Returns:
            True if cached successfully.
        """
        if not self._available or self._client is None:
            return False

        try:
            key = f"robot:pos:{robot_id}"
            await self._client.setex(key, ttl_s, json.dumps(pose))
            return True
        except Exception:
            return False

    async def get_robot_position(self, robot_id: str) -> Optional[dict[str, float]]:
        """
        Get a cached robot position.

        Returns:
            Position dict or None if not cached / Redis unavailable.
        """
        if not self._available or self._client is None:
            return None

        try:
            key = f"robot:pos:{robot_id}"
            data = await self._client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception:
            return None

    async def set_fleet_snapshot(self, snapshot: dict[str, Any], ttl_s: int = 10) -> bool:
        """Cache fleet-wide snapshot."""
        if not self._available or self._client is None:
            return False

        try:
            await self._client.setex("fleet:snapshot", ttl_s, json.dumps(snapshot, default=str))
            return True
        except Exception:
            return False

    async def get_fleet_snapshot(self) -> Optional[dict[str, Any]]:
        """Get cached fleet snapshot."""
        if not self._available or self._client is None:
            return None

        try:
            data = await self._client.get("fleet:snapshot")
            if data:
                return json.loads(data)
            return None
        except Exception:
            return None

    @property
    def is_available(self) -> bool:
        return self._available

    async def close(self):
        """Close Redis connection."""
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
