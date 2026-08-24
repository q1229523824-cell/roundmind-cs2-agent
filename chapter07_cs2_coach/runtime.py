"""组装比赛仓库与 LangGraph 工作流的应用运行时。"""

from __future__ import annotations

from threading import RLock

from chapter07_cs2_coach.coach_llm import CoachService
from chapter07_cs2_coach.models import (
    AnalysisResponse,
    CoachChatResponse,
    MatchRecord,
    PlayerProfileResponse,
)
from chapter07_cs2_coach.player_profile import build_player_profile
from chapter07_cs2_coach.personal_baseline import build_personal_contact_contrasts
from chapter07_cs2_coach.sample_data import SAMPLE_MATCH
from chapter07_cs2_coach.workflow import (
    CS2CoachWorkflow,
    DeepSeekToolPlanner,
    RuleBasedToolPlanner,
)


class MatchRepository:
    """MVP 使用的进程内仓库；以后可替换 PostgreSQL 而不改变 Agent。"""

    def __init__(self) -> None:
        self._matches: dict[str, MatchRecord] = {}
        self._lock = RLock()

    def save(self, match: MatchRecord) -> MatchRecord:
        with self._lock:
            self._matches[match.match_id] = match
        return match

    def get(self, match_id: str) -> MatchRecord | None:
        with self._lock:
            return self._matches.get(match_id)

    def list(self) -> list[MatchRecord]:
        with self._lock:
            return list(self._matches.values())


class CS2CoachRuntime:
    def __init__(
        self,
        *,
        repository: MatchRepository | None = None,
        workflow: CS2CoachWorkflow | None = None,
        coach_service: CoachService | None = None,
    ) -> None:
        self.repository = repository or MatchRepository()
        self.workflow = workflow or CS2CoachWorkflow()
        self.coach_service = coach_service or CoachService()

    @classmethod
    def create(cls, *, use_llm_planner: bool = False) -> "CS2CoachRuntime":
        planner = DeepSeekToolPlanner() if use_llm_planner else RuleBasedToolPlanner()
        runtime = cls(
            workflow=CS2CoachWorkflow(planner),
            coach_service=CoachService.from_environment(),
        )
        runtime.repository.save(SAMPLE_MATCH)
        return runtime

    def add_match(self, match: MatchRecord) -> MatchRecord:
        return self.repository.save(match)

    def analyze(self, *, match_id: str, question: str) -> AnalysisResponse:
        match = self.repository.get(match_id)
        if match is None:
            raise KeyError(f"比赛不存在：{match_id}")
        result = self.workflow.graph.invoke({"match": match, "question": question.strip()})
        return AnalysisResponse(
            match_id=match_id,
            answer=result["answer"],
            summary=result["summary"],
            evidence=result.get("evidence", []),
            tools_used=result.get("tools_used", []),
            execution_trace=result.get("execution_trace", []),
            knowledge_references=result.get("knowledge_references", []),
            decision_cards=result.get("decision_cards", []),
            personal_contact_contrasts=build_personal_contact_contrasts(match),
            confidence=result.get("confidence", "low"),
        )

    def player_profile(
        self, *, player_steamid: str, map_name: str | None = None
    ) -> PlayerProfileResponse:
        return build_player_profile(
            self.repository.list(),
            player_steamid=player_steamid,
            map_name=map_name,
        )

    def coach_chat(
        self,
        *,
        player_steamid: str,
        map_name: str,
        question: str,
    ) -> CoachChatResponse:
        return self.coach_service.answer(
            self.repository.list(),
            player_steamid=player_steamid,
            map_name=map_name,
            question=question,
        )
