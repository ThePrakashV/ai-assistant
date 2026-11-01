import json

import redis

from app.core.config import settings

MAX_STORED = 40  # Redis la max evlo messages vechikkanum
_warned = False


class ShortTermMemory:
    """Whiteboard. Recent chat history. Redis irundha adhula, illana in-memory list la."""

    def __init__(self, session_id: str) -> None:
        global _warned
        self.key = f"nova:session:{session_id}:history"
        self._local: list[dict] = []
        self._redis = None

        try:
            client = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            client.ping()
            self._redis = client
        except Exception:
            if not _warned:
                print("[Memory] Redis kidaikkala. In-memory history use pannurom (restart na poidum).")
                _warned = True

    @property
    def backend(self) -> str:
        return "redis" if self._redis else "in-memory"

    def get(self, limit: int = 20) -> list[dict]:
        if self._redis:
            try:
                items = self._redis.lrange(self.key, -limit, -1)
                return [json.loads(item) for item in items]
            except Exception:
                self._redis = None  # Redis poiduchu, in-memory ku maaridrom
        return self._local[-limit:]

    def append(self, role: str, content: str) -> None:
        message = {"role": role, "content": content}
        if self._redis:
            try:
                self._redis.rpush(self.key, json.dumps(message, ensure_ascii=False))
                self._redis.ltrim(self.key, -MAX_STORED, -1)
                self._redis.expire(self.key, settings.redis_ttl_seconds)
                return
            except Exception:
                self._redis = None
        self._local.append(message)
        self._local = self._local[-MAX_STORED:]

    def clear(self) -> None:
        if self._redis:
            try:
                self._redis.delete(self.key)
            except Exception:
                self._redis = None
        self._local.clear()