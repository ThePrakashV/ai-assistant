import time

import redis

from app.core.config import settings
from app.orchestrator.models import TaskRecord

INDEX_KEY = "nova:tasks:index"      # sorted set: task ids (created time padi)
RETRY_SECONDS = 5.0                 # Redis poiduchu na evlo sec ku oru dhadavai thirumba try


def _task_key(task_id: str) -> str:
    return f"nova:task:{task_id}"


def _parse(payload: str | None) -> TaskRecord | None:
    """Thappaana / pazhaya data irundha andha oru record ah skip pannum (Redis ah off pannaadhu)."""
    if not payload:
        return None
    try:
        return TaskRecord.model_validate_json(payload)
    except ValueError:
        return None


class TaskStore:
    """Order board. Redis irundha adhula (vera process kooda paakkalam), illana in-memory.

    Redis poiduchu na in-memory ku maarum, 5 sec ku oru dhadavai thirumba connect panna try pannum.
    """

    def __init__(self) -> None:
        self._redis = None
        self._next_retry = 0.0
        self._warned = False
        self._mem: dict[str, str] = {}
        self._order: list[str] = []
        self._connect()

    # ---------- Connection ----------
    def _connect(self) -> bool:
        try:
            client = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=2,
            )
            client.ping()
            self._redis = client
            if self._warned:
                print("[Tasks] Redis thirumba connect aachu.")
            self._warned = False
            return True
        except Exception:
            self._redis = None
            self._next_retry = time.time() + RETRY_SECONDS
            if not self._warned:
                print(
                    f"[Tasks] Redis kidaikkala ({settings.redis_url}). In-memory store use pannurom, "
                    f"{int(RETRY_SECONDS)} sec ku oru dhadavai thirumba try pannum."
                )
                self._warned = True
            return False

    def _client(self):
        if self._redis is None and time.time() >= self._next_retry:
            self._connect()
        return self._redis

    def _fail(self) -> None:
        self._redis = None
        self._next_retry = time.time() + RETRY_SECONDS
        if not self._warned:
            print("[Tasks] Redis connection poiduchu. In-memory ku maaridrom, thirumba try pannum.")
            self._warned = True

    @property
    def backend(self) -> str:
        return "redis" if self._client() else "in-memory"

    # ---------- API ----------
    def save(self, task: TaskRecord) -> None:
        payload = task.model_dump_json()

        client = self._client()
        if client:
            try:
                pipe = client.pipeline()
                pipe.set(_task_key(task.id), payload, ex=settings.task_ttl_seconds)
                pipe.zadd(INDEX_KEY, {task.id: task.created})
                pipe.zremrangebyrank(INDEX_KEY, 0, -(settings.tasks_keep + 1))  # pazhaya tasks thookidum
                pipe.execute()
                return
            except (redis.RedisError, OSError):
                self._fail()

        self._mem[task.id] = payload
        if task.id not in self._order:
            self._order.append(task.id)
        for old_id in self._order[: -settings.tasks_keep]:
            self._mem.pop(old_id, None)
        self._order = self._order[-settings.tasks_keep :]

    def get(self, task_id: str) -> TaskRecord | None:
        client = self._client()
        if client:
            try:
                return _parse(client.get(_task_key(task_id)))
            except (redis.RedisError, OSError):
                self._fail()
        return _parse(self._mem.get(task_id))

    def recent(self, limit: int = 50) -> list[TaskRecord]:
        """Puthu task modhalil."""
        client = self._client()
        if client:
            try:
                ids = client.zrevrange(INDEX_KEY, 0, limit - 1)
                values = client.mget([_task_key(task_id) for task_id in ids]) if ids else []
                return [task for task in (_parse(value) for value in values) if task]
            except (redis.RedisError, OSError):
                self._fail()

        payloads = [self._mem[task_id] for task_id in reversed(self._order[-limit:]) if task_id in self._mem]
        return [task for task in (_parse(payload) for payload in payloads) if task]

    def clear(self) -> None:
        client = self._client()
        if client:
            try:
                ids = client.zrange(INDEX_KEY, 0, -1)
                keys = [_task_key(task_id) for task_id in ids] + [INDEX_KEY]
                client.delete(*keys)
            except (redis.RedisError, OSError):
                self._fail()
        self._mem.clear()
        self._order.clear()