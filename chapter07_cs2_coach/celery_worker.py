"""Celery Worker 入口：python -m celery -A chapter07_cs2_coach.celery_worker worker。"""

from __future__ import annotations

import os

from celery import Celery

from chapter07_cs2_coach.distributed_jobs import (
    DISCOVER_TASK,
    PARSE_TASK,
    discover_demo_job,
    parse_demo_job,
)


redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
celery_app = Celery("roundmind", broker=redis_url, backend=redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=20 * 60,
    task_soft_time_limit=18 * 60,
)


@celery_app.task(name=DISCOVER_TASK)
def discover_demo_players_task(job_id: str) -> None:
    discover_demo_job(job_id)


@celery_app.task(name=PARSE_TASK)
def parse_demo_task(job_id: str) -> None:
    parse_demo_job(job_id)
