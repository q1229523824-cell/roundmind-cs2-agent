"""Redis 状态 + Celery 调度的分布式 Demo 任务实现。"""

from __future__ import annotations

import json
import os
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from chapter07_cs2_coach.demo_jobs import DemoJobStateError, DemoQueueFullError
from chapter07_cs2_coach.demo_parser import CS2DemoMatchParser, DemoParseError
from chapter07_cs2_coach.models import (
    AnalysisResponse,
    DemoJobResponse,
    DemoPlayerOption,
    MatchRecord,
)
from chapter07_cs2_coach.object_storage import (
    DemoObjectStoreProtocol,
    object_store_from_environment,
)
from chapter07_cs2_coach.runtime import CS2CoachRuntime


DISCOVER_TASK = "roundmind.discover_demo_players"
PARSE_TASK = "roundmind.parse_demo"


class DistributedJobConfigurationError(RuntimeError):
    pass


class DistributedDemoJob(BaseModel):
    job_id: str
    object_key: str
    filename: str
    question: str
    player_name: str | None = None
    player_steamid: str | None = None
    status: str = "queued"
    progress: int = Field(default=10, ge=0, le=100)
    available_players: list[str] = Field(default_factory=list)
    player_options: list[DemoPlayerOption] = Field(default_factory=list)
    match: MatchRecord | None = None
    analysis: AnalysisResponse | None = None
    error: str | None = None
    owner_id: str | None = None

    def response(self) -> DemoJobResponse:
        return DemoJobResponse.model_validate(
            self.model_dump(exclude={"object_key", "question", "owner_id"})
        )


class DemoJobStoreProtocol(Protocol):
    backend_name: str

    def save(self, job: DistributedDemoJob) -> None: ...

    def get(self, job_id: str) -> DistributedDemoJob | None: ...

    def pending_count(self) -> int: ...


class RedisDemoJobStore:
    """将任务公开状态和 Worker 所需元数据作为有 TTL 的 JSON 保存。"""

    backend_name = "redis"

    def __init__(
        self,
        redis_url: str,
        *,
        ttl_seconds: int = 24 * 60 * 60,
        client: object | None = None,
    ) -> None:
        if not redis_url.strip():
            raise DistributedJobConfigurationError("REDIS_URL 不能为空。")
        if client is None:
            try:
                import redis
            except ImportError as error:  # pragma: no cover
                raise DistributedJobConfigurationError(
                    "分布式任务模式需要安装 redis。"
                ) from error
            client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._prefix = "roundmind:demo-job:"

    def save(self, job: DistributedDemoJob) -> None:
        self._client.setex(
            self._key(job.job_id),
            self._ttl_seconds,
            job.model_dump_json(),
        )

    def get(self, job_id: str) -> DistributedDemoJob | None:
        payload = self._client.get(self._key(job_id))
        return DistributedDemoJob.model_validate_json(payload) if payload else None

    def pending_count(self) -> int:
        count = 0
        for key in self._client.scan_iter(match=f"{self._prefix}*"):
            payload = self._client.get(key)
            if not payload:
                continue
            status = json.loads(payload).get("status")
            if status in {"queued", "discovering", "awaiting_player", "parsing"}:
                count += 1
        return count

    def _key(self, job_id: str) -> str:
        return f"{self._prefix}{job_id}"


class TaskDispatcherProtocol(Protocol):
    def send(self, task_name: str, job_id: str) -> None: ...


class CeleryTaskDispatcher:
    def __init__(self, celery_app: object) -> None:
        self._app = celery_app

    def send(self, task_name: str, job_id: str) -> None:
        self._app.send_task(task_name, args=[job_id])


class CeleryDemoJobManager:
    """与本地 DemoJobManager 保持相同 HTTP-facing 接口。"""

    def __init__(
        self,
        *,
        store: DemoJobStoreProtocol,
        object_store: DemoObjectStoreProtocol,
        dispatcher: TaskDispatcherProtocol,
        max_pending_jobs: int = 20,
    ) -> None:
        self.store = store
        self.object_store = object_store
        self.dispatcher = dispatcher
        self.max_pending_jobs = max_pending_jobs

    def submit_upload(
        self,
        *,
        path,
        filename: str,
        player_name: str | None = None,
        player_steamid: str | None = None,
        question: str,
        owner_id: str | None = None,
    ) -> DemoJobResponse:
        if self.store.pending_count() >= self.max_pending_jobs:
            raise DemoQueueFullError("Demo 解析队列已满，请稍后重试。")
        key = self.object_store.put(path)
        job = DistributedDemoJob(
            job_id=uuid4().hex,
            object_key=key,
            filename=filename,
            player_name=player_name,
            player_steamid=player_steamid,
            question=question,
            owner_id=owner_id,
        )
        try:
            self.store.save(job)
            self.dispatcher.send(PARSE_TASK if player_name else DISCOVER_TASK, job.job_id)
        except Exception:
            self.object_store.delete(key)
            raise
        return job.response()

    def get(self, job_id: str, owner_id: str | None = None) -> DemoJobResponse:
        job = self.store.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if owner_id is not None and job.owner_id != owner_id:
            raise KeyError(job_id)
        return job.response()

    def select_player(
        self,
        job_id: str,
        *,
        player_name: str,
        player_steamid: str | None,
        question: str,
        owner_id: str | None = None,
    ) -> DemoJobResponse:
        job = self.store.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if owner_id is not None and job.owner_id != owner_id:
            raise KeyError(job_id)
        if job.status != "awaiting_player":
            raise DemoJobStateError("这个 Demo 任务当前不等待玩家选择。")
        selected = next(
            (
                option
                for option in job.player_options
                if (player_steamid and option.steamid == player_steamid)
                or (not player_steamid and option.name.casefold() == player_name.casefold())
            ),
            None,
        )
        if selected is None:
            raise DemoJobStateError("请选择 Demo 玩家列表中的昵称。")
        job.player_name = selected.name
        job.player_steamid = selected.steamid
        job.question = question
        job.status = "queued"
        job.progress = 50
        self.store.save(job)
        self.dispatcher.send(PARSE_TASK, job.job_id)
        return job.response()


def discover_demo_job(
    job_id: str,
    *,
    store: DemoJobStoreProtocol | None = None,
    object_store: DemoObjectStoreProtocol | None = None,
    parser: CS2DemoMatchParser | None = None,
) -> None:
    store = store or redis_job_store_from_environment()
    object_store = object_store or object_store_from_environment()
    parser = parser or CS2DemoMatchParser()
    job = store.get(job_id)
    if job is None:
        return
    if job.status in {"awaiting_player", "completed", "failed"}:
        return
    job.status, job.progress = "discovering", 25
    store.save(job)
    try:
        with object_store.materialize(job.object_key) as path:
            options = parser.list_player_options(path)
        job.available_players = [item.name for item in options]
        job.player_options = options
        job.status, job.progress = "awaiting_player", 45
        store.save(job)
    except DemoParseError as error:
        _fail_distributed_job(job, str(error), store, object_store)
    except Exception:
        _fail_distributed_job(
            job, "服务器读取 Demo 玩家名单时发生未知错误。", store, object_store
        )


def parse_demo_job(
    job_id: str,
    *,
    store: DemoJobStoreProtocol | None = None,
    object_store: DemoObjectStoreProtocol | None = None,
    parser: CS2DemoMatchParser | None = None,
    runtime: CS2CoachRuntime | None = None,
) -> None:
    store = store or redis_job_store_from_environment()
    object_store = object_store or object_store_from_environment()
    parser = parser or CS2DemoMatchParser()
    runtime = runtime or CS2CoachRuntime.create()
    job = store.get(job_id)
    if job is None:
        return
    if job.status in {"completed", "failed"}:
        return
    job.status, job.progress = "parsing", 55
    store.save(job)
    try:
        if not job.player_name:
            raise DemoParseError("尚未选择要复盘的玩家。")
        with object_store.materialize(job.object_key) as path:
            match = parser.parse(path, job.player_name, job.player_steamid)
        runtime.add_match(match, job.owner_id)
        job.progress = 80
        store.save(job)
        job.match = match
        job.analysis = runtime.analyze(
            match_id=match.match_id, question=job.question, owner_id=job.owner_id
        )
        job.status, job.progress = "completed", 100
        store.save(job)
    except DemoParseError as error:
        job.error, job.status, job.progress = str(error), "failed", 100
        store.save(job)
    except Exception:
        job.error = "服务器解析 Demo 时发生未知错误，请换一个文件重试。"
        job.status, job.progress = "failed", 100
        store.save(job)
    finally:
        object_store.delete(job.object_key)


def _fail_distributed_job(job, message, store, object_store) -> None:
    job.error, job.status, job.progress = message, "failed", 100
    store.save(job)
    object_store.delete(job.object_key)


def redis_job_store_from_environment() -> RedisDemoJobStore:
    return RedisDemoJobStore(os.getenv("REDIS_URL", ""))


def distributed_manager_from_environment() -> CeleryDemoJobManager:
    from chapter07_cs2_coach.celery_worker import celery_app

    return CeleryDemoJobManager(
        store=redis_job_store_from_environment(),
        object_store=object_store_from_environment(),
        dispatcher=CeleryTaskDispatcher(celery_app),
        max_pending_jobs=int(os.getenv("ROUNDMIND_MAX_PENDING_JOBS", "20")),
    )
