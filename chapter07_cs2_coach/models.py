"""CS2 复盘项目使用的结构化比赛模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RoundRecord(BaseModel):
    """玩家在一个回合内的可复核事实。"""

    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1, le=100)
    side: Literal["T", "CT"]
    won: bool
    kills: int = Field(default=0, ge=0, le=5)
    assists: int = Field(default=0, ge=0, le=5)
    died: bool = False
    damage: int = Field(default=0, ge=0, le=1000)
    opening_duel: Literal["won", "lost", "none"] = "none"
    was_traded: bool = False
    utility_damage: int = Field(default=0, ge=0, le=500)
    enemies_flashed: int = Field(default=0, ge=0, le=5)
    equipment_value: int = Field(default=0, ge=0, le=20000)
    clutch_attempted: bool = False
    clutch_won: bool = False
    note: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def validate_round_logic(self) -> "RoundRecord":
        if self.was_traded and not self.died:
            raise ValueError("只有本回合死亡时才能标记为被队友补枪。")
        if self.clutch_won and not self.clutch_attempted:
            raise ValueError("残局获胜必须同时标记为参与残局。")
        return self


class EngagementRecord(BaseModel):
    """一次死亡前的可复核局势快照，不对玩家意图做主观猜测。"""

    model_config = ConfigDict(extra="forbid")

    round_number: int = Field(ge=1, le=100)
    tick: int = Field(ge=0)
    classification: Literal[
        "isolated_advance",
        "isolated_contact",
        "supported_contact",
        "uncertain_support",
        "last_alive",
    ]
    location: str = Field(min_length=1, max_length=80)
    side: Literal["T", "CT"]
    position_x: float
    position_y: float
    position_z: float
    health: int = Field(ge=0, le=100)
    armor: int = Field(ge=0, le=100)
    weapon: str = Field(default="unknown", min_length=1, max_length=80)
    alive_teammates: int = Field(ge=0, le=4)
    alive_enemies: int = Field(ge=0, le=5)
    nearest_teammate_distance: int | None = Field(default=None, ge=0, le=100000)
    nearby_support: bool
    moved_distance_5s: int = Field(ge=0, le=100000)
    effective_team_flashes_5s: int = Field(ge=0, le=20)
    was_traded: bool


class MatchRecord(BaseModel):
    """一次分析所需的最小比赛数据。"""

    model_config = ConfigDict(extra="forbid")

    match_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    player_name: str = Field(min_length=1, max_length=80)
    player_steamid: str | None = Field(default=None, min_length=1, max_length=32)
    map_name: str = Field(min_length=1, max_length=80)
    team_name: str = Field(min_length=1, max_length=80)
    opponent_name: str = Field(min_length=1, max_length=80)
    team_score: int = Field(ge=0, le=100)
    opponent_score: int = Field(ge=0, le=100)
    rounds: list[RoundRecord] = Field(min_length=1, max_length=100)
    engagements: list[EngagementRecord] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_round_numbers(self) -> "MatchRecord":
        numbers = [item.number for item in self.rounds]
        if len(numbers) != len(set(numbers)):
            raise ValueError("回合编号不能重复。")
        if self.team_score + self.opponent_score != len(self.rounds):
            raise ValueError("双方比分之和必须等于回合记录数。")
        actual_wins = sum(item.won for item in self.rounds)
        if actual_wins != self.team_score:
            raise ValueError("回合胜负记录与本方比分不一致。")
        if any(item.round_number not in numbers for item in self.engagements):
            raise ValueError("接战快照必须引用现有回合。")
        return self


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_id: str = Field(min_length=1, max_length=80)
    question: str = Field(
        default="请综合分析这场比赛，找出最值得优先改进的问题。",
        min_length=1,
        max_length=1000,
    )


class Evidence(BaseModel):
    finding: str
    round_numbers: list[int]
    metric: str
    severity: Literal["high", "medium", "positive"]
    suggestion: str


class KnowledgeReference(BaseModel):
    """一次本地战术知识检索命中，可用于报告引用和离线评测。"""

    model_config = ConfigDict(extra="forbid")

    knowledge_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    principle: str = Field(min_length=1, max_length=600)
    source: str = Field(min_length=1, max_length=200)
    matched_topics: list[str] = Field(default_factory=list, max_length=10)
    score: int = Field(ge=0, le=100)


class DecisionCard(BaseModel):
    """一次关键接战的事实、风险与可执行改进建议。"""

    model_config = ConfigDict(extra="forbid")

    round_number: int = Field(ge=1, le=100)
    tick: int = Field(ge=0)
    location: str = Field(min_length=1, max_length=80)
    side: Literal["T", "CT"]
    classification: Literal[
        "isolated_advance",
        "isolated_contact",
        "supported_contact",
        "uncertain_support",
        "last_alive",
    ]
    risk_score: int = Field(ge=0, le=100)
    risk_level: Literal["high", "medium", "low"]
    verdict: Literal["high_risk", "review", "reasonable"]
    situation: str = Field(min_length=1, max_length=240)
    factors: list[str] = Field(min_length=1, max_length=10)
    better_action: str = Field(min_length=1, max_length=400)
    knowledge_ids: list[str] = Field(default_factory=list, max_length=5)
    confidence: Literal["high", "medium", "low"]


class AnalysisResponse(BaseModel):
    match_id: str
    answer: str
    summary: dict[str, int | float | str]
    evidence: list[Evidence]
    tools_used: list[str]
    execution_trace: list[str]
    knowledge_references: list[KnowledgeReference] = Field(default_factory=list)
    decision_cards: list[DecisionCard] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]


class DemoJobResponse(BaseModel):
    """异步 Demo 解析任务的公开状态。"""

    job_id: str
    status: Literal[
        "queued", "discovering", "awaiting_player", "parsing", "completed", "failed"
    ]
    progress: int = Field(ge=0, le=100)
    filename: str
    player_name: str | None = None
    player_steamid: str | None = None
    available_players: list[str] = Field(default_factory=list, max_length=20)
    player_options: list["DemoPlayerOption"] = Field(default_factory=list, max_length=20)
    match: MatchRecord | None = None
    analysis: AnalysisResponse | None = None
    error: str | None = None


class DemoPlayerSelection(BaseModel):
    """为已上传的 Demo 选择要复盘的玩家。"""

    model_config = ConfigDict(extra="forbid")

    player_name: str = Field(min_length=1, max_length=80)
    player_steamid: str | None = Field(default=None, min_length=1, max_length=32)
    question: str = Field(
        default="请综合分析这场比赛，找出最值得优先改进的问题。",
        min_length=1,
        max_length=1000,
    )


class DemoPlayerOption(BaseModel):
    """Demo 中可选择的稳定玩家身份。"""

    name: str = Field(min_length=1, max_length=80)
    steamid: str = Field(min_length=1, max_length=32)
