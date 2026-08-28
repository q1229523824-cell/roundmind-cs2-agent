"""组装比赛仓库与 LangGraph 工作流的应用运行时。"""

from __future__ import annotations

from threading import RLock

from chapter07_cs2_coach.coach_llm import CoachService
from chapter07_cs2_coach.database import (
    MatchOwnershipConflictError,
    MatchRepositoryProtocol,
    repository_from_environment,
)
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
    """本地和测试使用的进程内仓库。"""

    backend_name = "memory"

    def __init__(self) -> None:
        self._matches: dict[str, MatchRecord] = {}
        self._owners: dict[str, str | None] = {}
        self._lock = RLock()

    def check_connection(self) -> None:
        """进程内仓库无需外部依赖，创建成功即为可用。"""

    def save(self, match: MatchRecord, owner_id: str | None = None) -> MatchRecord:
        with self._lock:
            existing_owner = self._owners.get(match.match_id)
            if existing_owner is not None and existing_owner != owner_id:
                raise MatchOwnershipConflictError("该比赛 ID 已被其他账户使用。")
            self._matches[match.match_id] = match
            if owner_id is not None or match.match_id not in self._owners:
                self._owners[match.match_id] = owner_id
        return match

    def get(self, match_id: str) -> MatchRecord | None:
        with self._lock:
            return self._matches.get(match_id)

    def list(self) -> list[MatchRecord]:
        with self._lock:
            return list(self._matches.values())

    def get_for_owner(self, match_id: str, owner_id: str) -> MatchRecord | None:
        with self._lock:
            return (
                self._matches.get(match_id)
                if self._owners.get(match_id) == owner_id
                else None
            )

    def list_for_owner(self, owner_id: str) -> list[MatchRecord]:
        with self._lock:
            return [
                match
                for match_id, match in self._matches.items()
                if self._owners.get(match_id) == owner_id
            ]


class CS2CoachRuntime:
    def __init__(
        self,
        *,
        repository: MatchRepositoryProtocol | None = None,
        workflow: CS2CoachWorkflow | None = None,
        coach_service: CoachService | None = None,
    ) -> None:
        self.repository: MatchRepositoryProtocol = repository or MatchRepository()
        self.workflow = workflow or CS2CoachWorkflow()
        self.coach_service = coach_service or CoachService()

    @classmethod
    def create(
        cls,
        *,
        use_llm_planner: bool = False,
        enable_critic: bool = True,
    ) -> "CS2CoachRuntime":
        planner = DeepSeekToolPlanner() if use_llm_planner else RuleBasedToolPlanner()
        repository = repository_from_environment() or MatchRepository()
        runtime = cls(
            repository=repository,
            workflow=CS2CoachWorkflow(planner, enable_critic=enable_critic),
            coach_service=CoachService.from_environment(),
        )
        runtime.repository.save(SAMPLE_MATCH)
        return runtime

    def add_match(self, match: MatchRecord, owner_id: str | None = None) -> MatchRecord:
        return self.repository.save(match, owner_id)

    def analyze(
        self, *, match_id: str, question: str, owner_id: str | None = None
    ) -> AnalysisResponse:
        match = (
            self.repository.get_for_owner(match_id, owner_id)
            if owner_id is not None
            else self.repository.get(match_id)
        )
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
            agent_runs=result.get("agent_runs", []),
            critic_trigger_reasons=result.get("critic_reasons", []),
            knowledge_references=result.get("knowledge_references", []),
            decision_cards=result.get("decision_cards", []),
            contact_decision_cards=result.get("contact_decision_cards", []),
            personal_contact_contrasts=build_personal_contact_contrasts(match),
            confidence=result.get("confidence", "low"),
        )

    def player_profile(
        self,
        *,
        player_steamid: str,
        map_name: str | None = None,
        owner_id: str | None = None,
    ) -> PlayerProfileResponse:
        return build_player_profile(
            self.repository.list_for_owner(owner_id) if owner_id else self.repository.list(),
            player_steamid=player_steamid,
            map_name=map_name,
        )

    def coach_chat(
        self,
        *,
        player_steamid: str,
        map_name: str,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
        owner_id: str | None = None,
    ) -> CoachChatResponse:
        return self.coach_service.answer(
            self.repository.list_for_owner(owner_id) if owner_id else self.repository.list(),
            player_steamid=player_steamid,
            map_name=map_name,
            question=question,
            conversation_history=conversation_history,
        )
