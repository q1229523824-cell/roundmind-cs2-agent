"""线程安全的 Demo 解析任务管理器。"""

from __future__ import annotations

from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from uuid import uuid4

from chapter07_cs2_coach.demo_parser import CS2DemoMatchParser, DemoParseError
from chapter07_cs2_coach.models import AnalysisResponse, DemoJobResponse, MatchRecord
from chapter07_cs2_coach.runtime import CS2CoachRuntime


class DemoQueueFullError(RuntimeError):
    """限制公开服务的并发临时文件与 CPU 消耗。"""


@dataclass
class _DemoJob:
    job_id: str
    filename: str
    player_name: str
    question: str
    path: Path
    status: str = "queued"
    progress: int = 10
    match: MatchRecord | None = None
    analysis: AnalysisResponse | None = None
    error: str | None = None


class DemoJobManager:
    """在受控线程池中解析 Demo，并保证临时文件最终被清理。"""

    def __init__(
        self,
        runtime: CS2CoachRuntime,
        *,
        parser: CS2DemoMatchParser | None = None,
        executor: Executor | None = None,
        max_pending_jobs: int = 2,
    ) -> None:
        self._runtime = runtime
        self._parser = parser or CS2DemoMatchParser()
        self._executor = executor or ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="roundmind-demo"
        )
        self._jobs: dict[str, _DemoJob] = {}
        self._lock = RLock()
        self._max_pending_jobs = max_pending_jobs

    def submit(
        self,
        *,
        path: Path,
        filename: str,
        player_name: str,
        question: str,
    ) -> DemoJobResponse:
        job = _DemoJob(
            job_id=uuid4().hex,
            path=path,
            filename=filename,
            player_name=player_name,
            question=question,
        )
        with self._lock:
            pending = sum(
                item.status in {"queued", "parsing"} for item in self._jobs.values()
            )
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
        self._executor.submit(self._run, job.job_id)
        return self.get(job.job_id)

    def get(self, job_id: str) -> DemoJobResponse:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return DemoJobResponse(
                job_id=job.job_id,
                status=job.status,  # type: ignore[arg-type]
                progress=job.progress,
                filename=job.filename,
                player_name=job.player_name,
                match=job.match,
                analysis=job.analysis,
                error=job.error,
            )

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "parsing"
            job.progress = 35
        try:
            match = self._parser.parse(job.path, job.player_name)
            with self._lock:
                job.progress = 80
            self._runtime.add_match(match)
            analysis = self._runtime.analyze(
                match_id=match.match_id,
                question=job.question,
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
            job.path.unlink(missing_ok=True)

    def _fail(self, job: _DemoJob, message: str) -> None:
        with self._lock:
            job.error = message
            job.status = "failed"
            job.progress = 100
