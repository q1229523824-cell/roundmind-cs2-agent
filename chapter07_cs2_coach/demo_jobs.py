"""线程安全的 Demo 解析任务管理器。"""

from __future__ import annotations

from concurrent.futures import Executor, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock, Timer
from uuid import uuid4

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


class DemoQueueFullError(RuntimeError):
    """限制公开服务的并发临时文件与 CPU 消耗。"""


class DemoJobStateError(RuntimeError):
    """Demo 任务当前状态不允许选择玩家。"""


@dataclass
class _DemoJob:
    job_id: str
    filename: str
    player_name: str | None
    player_steamid: str | None
    question: str
    path: Path | None = None
    object_key: str | None = None
    owner_id: str | None = None
    status: str = "queued"
    progress: int = 10
    match: MatchRecord | None = None
    analysis: AnalysisResponse | None = None
    available_players: list[str] = field(default_factory=list)
    player_options: list[DemoPlayerOption] = field(default_factory=list)
    error: str | None = None
    selection_timer: Timer | None = field(default=None, repr=False)


class DemoJobManager:
    """在受控线程池中解析 Demo，并保证临时文件最终被清理。"""

    def __init__(
        self,
        runtime: CS2CoachRuntime,
        *,
        parser: CS2DemoMatchParser | None = None,
        executor: Executor | None = None,
        object_store: DemoObjectStoreProtocol | None = None,
        max_pending_jobs: int = 2,
        max_workers: int = 1,
        player_selection_timeout_seconds: float = 15 * 60,
    ) -> None:
        if max_pending_jobs < 1:
            raise ValueError("max_pending_jobs 必须至少为 1。")
        if max_workers < 1:
            raise ValueError("max_workers 必须至少为 1。")
        self._runtime = runtime
        self._parser = parser or CS2DemoMatchParser()
        self._executor = executor or ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="roundmind-demo"
        )
        self.object_store = object_store or object_store_from_environment()
        self._jobs: dict[str, _DemoJob] = {}
        self._lock = RLock()
        self._max_pending_jobs = max_pending_jobs
        self.max_pending_jobs = max_pending_jobs
        self.max_workers = max_workers
        self._player_selection_timeout_seconds = player_selection_timeout_seconds

    def ensure_capacity(self) -> None:
        """在接收大文件前执行快速准入检查；入队时仍会再次做硬限制。"""
        with self._lock:
            if self._pending_count_unlocked() >= self._max_pending_jobs:
                raise DemoQueueFullError("Demo 解析队列已满，请稍后重试。")

    def pending_count(self) -> int:
        with self._lock:
            return self._pending_count_unlocked()

    def submit(
        self,
        *,
        path: Path,
        filename: str,
        player_name: str | None = None,
        player_steamid: str | None = None,
        question: str,
        owner_id: str | None = None,
    ) -> DemoJobResponse:
        job = _DemoJob(
            job_id=uuid4().hex,
            path=path,
            filename=filename,
            player_name=player_name,
            player_steamid=player_steamid,
            question=question,
            owner_id=owner_id,
        )
        self._enqueue(job)
        return self.get(job.job_id)

    def submit_upload(
        self,
        *,
        path: Path,
        filename: str,
        player_name: str | None = None,
        player_steamid: str | None = None,
        question: str,
        owner_id: str | None = None,
    ) -> DemoJobResponse:
        """把已校验上传转入对象存储，再创建只引用对象键的任务。"""

        key: str | None = None
        try:
            key = self.object_store.put(path)
            job = _DemoJob(
                job_id=uuid4().hex,
                object_key=key,
                filename=filename,
                player_name=player_name,
                player_steamid=player_steamid,
                question=question,
                owner_id=owner_id,
            )
            self._enqueue(job)
            return self.get(job.job_id)
        except Exception:
            if key is not None:
                self.object_store.delete(key)
            raise

    def select_player(
        self,
        job_id: str,
        *,
        player_name: str,
        player_steamid: str | None,
        question: str,
        owner_id: str | None = None,
    ) -> DemoJobResponse:
        with self._lock:
            job = self._jobs.get(job_id)
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
                    or (
                        not player_steamid
                        and option.name.casefold() == player_name.casefold()
                    )
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
            if job.selection_timer is not None:
                job.selection_timer.cancel()
                job.selection_timer = None
        self._executor.submit(self._run, job_id)
        return self.get(job_id)

    def get(self, job_id: str, owner_id: str | None = None) -> DemoJobResponse:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if owner_id is not None and job.owner_id != owner_id:
                raise KeyError(job_id)
            return DemoJobResponse(
                job_id=job.job_id,
                status=job.status,  # type: ignore[arg-type]
                progress=job.progress,
                filename=job.filename,
                player_name=job.player_name,
                player_steamid=job.player_steamid,
                available_players=list(job.available_players),
                player_options=list(job.player_options),
                match=job.match,
                analysis=job.analysis,
                error=job.error,
            )

    def _discover_players(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "discovering"
            job.progress = 25
        try:
            with self._materialized(job) as path:
                options = self._parser.list_player_options(path)
            timer = Timer(
                self._player_selection_timeout_seconds,
                self._expire_selection,
                args=(job_id,),
            )
            timer.daemon = True
            with self._lock:
                job.available_players = [item.name for item in options]
                job.player_options = options
                job.status = "awaiting_player"
                job.progress = 45
                job.selection_timer = timer
            timer.start()
        except DemoParseError as error:
            self._fail(job, str(error))
            self._delete_source(job)
        except Exception:
            self._fail(job, "服务器读取 Demo 玩家名单时发生未知错误。")
            self._delete_source(job)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "parsing"
            job.progress = 55
            player_name = job.player_name
            player_steamid = job.player_steamid
        try:
            if not player_name:
                raise DemoParseError("尚未选择要复盘的玩家。")
            with self._materialized(job) as path:
                match = self._parser.parse(path, player_name, player_steamid)
            with self._lock:
                job.progress = 80
            self._runtime.add_match(match, job.owner_id)
            analysis = self._runtime.analyze(
                match_id=match.match_id,
                question=job.question,
                owner_id=job.owner_id,
            )
            with self._lock:
                job.match = match
                job.analysis = analysis
                job.status = "completed"
                job.progress = 100
        except DemoParseError as error:
            self._fail(job, str(error))
        except Exception:
            self._fail(job, "服务器解析 Demo 时发生未知错误，请换一个文件重试。")
        finally:
            if job.selection_timer is not None:
                job.selection_timer.cancel()
                job.selection_timer = None
            self._delete_source(job)

    def _fail(self, job: _DemoJob, message: str) -> None:
        with self._lock:
            job.error = message
            job.status = "failed"
            job.progress = 100

    def _expire_selection(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "awaiting_player":
                return
            job.error = "玩家选择已超时，请重新上传 Demo。"
            job.status = "failed"
            job.progress = 100
            job.selection_timer = None
        self._delete_source(job)

    def _enqueue(self, job: _DemoJob) -> None:
        with self._lock:
            pending = self._pending_count_unlocked()
            if pending >= self._max_pending_jobs:
                raise DemoQueueFullError("Demo 解析队列已满，请稍后重试。")
            while len(self._jobs) >= 100:
                terminal_id = next(
                    (
                        key
                        for key, item in self._jobs.items()
                        if item.status in {"completed", "failed"}
                    ),
                    None,
                )
                if terminal_id is None:
                    break
                del self._jobs[terminal_id]
            self._jobs[job.job_id] = job
        target = self._run if job.player_name else self._discover_players
        self._executor.submit(target, job.job_id)

    def _pending_count_unlocked(self) -> int:
        return sum(
            item.status in {"queued", "discovering", "awaiting_player", "parsing"}
            for item in self._jobs.values()
        )

    @contextmanager
    def _materialized(self, job: _DemoJob):
        if job.path is not None:
            yield job.path
            return
        if job.object_key is None:
            raise FileNotFoundError("Demo 任务没有可读取的数据源。")
        with self.object_store.materialize(job.object_key) as path:
            yield path

    def _delete_source(self, job: _DemoJob) -> None:
        if job.path is not None:
            job.path.unlink(missing_ok=True)
        elif job.object_key is not None:
            self.object_store.delete(job.object_key)
