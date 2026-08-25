import tempfile
import unittest
from pathlib import Path

from chapter07_cs2_coach.distributed_jobs import (
    DISCOVER_TASK,
    PARSE_TASK,
    CeleryDemoJobManager,
    DistributedDemoJob,
    RedisDemoJobStore,
    discover_demo_job,
    parse_demo_job,
)
from chapter07_cs2_coach.models import DemoPlayerOption
from chapter07_cs2_coach.object_storage import LocalDemoObjectStore
from chapter07_cs2_coach.runtime import CS2CoachRuntime
from chapter07_cs2_coach.sample_data import SAMPLE_MATCH


class InMemoryJobStore:
    backend_name = "memory-test"

    def __init__(self):
        self.jobs = {}

    def save(self, job):
        self.jobs[job.job_id] = job.model_copy(deep=True)

    def get(self, job_id):
        job = self.jobs.get(job_id)
        return job.model_copy(deep=True) if job else None

    def pending_count(self):
        return sum(
            job.status in {"queued", "discovering", "awaiting_player", "parsing"}
            for job in self.jobs.values()
        )


class FakeDispatcher:
    def __init__(self):
        self.calls = []

    def send(self, task_name, job_id):
        self.calls.append((task_name, job_id))


class FakeRedis:
    def __init__(self):
        self.values = {}

    def setex(self, key, ttl, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def scan_iter(self, match):
        return iter(self.values)


class TinyParser:
    def list_player_options(self, path):
        self._assert_demo(path)
        return [
            DemoPlayerOption(name="Learner", steamid="1"),
            DemoPlayerOption(name="Enemy", steamid="2"),
        ]

    def parse(self, path, player_name, player_steamid):
        self._assert_demo(path)
        return SAMPLE_MATCH.model_copy(
            update={"match_id": "distributed-match", "player_steamid": player_steamid}
        )

    @staticmethod
    def _assert_demo(path):
        if not Path(path).read_bytes().startswith(b"PBDEMS2\x00"):
            raise AssertionError("invalid test demo")


class DistributedJobTests(unittest.TestCase):
    def test_redis_job_store_round_trip_and_pending_count(self):
        client = FakeRedis()
        store = RedisDemoJobStore("redis://example", client=client)
        job = DistributedDemoJob(
            job_id="job-1",
            object_key="incoming/a.dem",
            filename="match.dem",
            question="分析",
        )

        store.save(job)

        self.assertEqual(store.get("job-1"), job)
        self.assertEqual(store.pending_count(), 1)

    def test_manager_and_workers_complete_two_phase_job(self):
        with tempfile.TemporaryDirectory() as workspace:
            object_store = LocalDemoObjectStore(Path(workspace) / "objects")
            source = Path(workspace) / "upload.dem"
            source.write_bytes(b"PBDEMS2\x00demo")
            store = InMemoryJobStore()
            dispatcher = FakeDispatcher()
            manager = CeleryDemoJobManager(
                store=store,
                object_store=object_store,
                dispatcher=dispatcher,
            )

            queued = manager.submit_upload(
                path=source,
                filename="match.dem",
                question="分析首轮交火",
            )
            self.assertEqual(dispatcher.calls, [(DISCOVER_TASK, queued.job_id)])

            discover_demo_job(
                queued.job_id,
                store=store,
                object_store=object_store,
                parser=TinyParser(),
            )
            discovered = manager.get(queued.job_id)
            self.assertEqual(discovered.status, "awaiting_player")
            self.assertEqual(discovered.available_players, ["Learner", "Enemy"])

            selected = manager.select_player(
                queued.job_id,
                player_name="Learner",
                player_steamid="1",
                question="分析首轮交火",
            )
            self.assertEqual(selected.status, "queued")
            self.assertEqual(dispatcher.calls[-1], (PARSE_TASK, queued.job_id))

            parse_demo_job(
                queued.job_id,
                store=store,
                object_store=object_store,
                parser=TinyParser(),
                runtime=CS2CoachRuntime.create(),
            )
            completed = manager.get(queued.job_id)
            self.assertEqual(completed.status, "completed")
            self.assertEqual(completed.match.match_id, "distributed-match")
            self.assertFalse(any((Path(workspace) / "objects").rglob("*.dem")))

            # Celery late ack 可能造成消息重投；终态任务必须幂等返回。
            parse_demo_job(
                queued.job_id,
                store=store,
                object_store=object_store,
                parser=TinyParser(),
                runtime=CS2CoachRuntime.create(),
            )
            self.assertEqual(manager.get(queued.job_id).status, "completed")


if __name__ == "__main__":
    unittest.main()
