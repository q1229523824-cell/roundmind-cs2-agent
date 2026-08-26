"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const MAX_DEMO_MB = 500;
const MAX_DEMO_BYTES = MAX_DEMO_MB * 1024 * 1024;

type Round = {
  number: number;
  won: boolean;
  kills: number;
  assists: number;
  died: boolean;
  damage: number;
  opening_duel: "won" | "lost" | "none";
  was_traded: boolean;
  utility_damage: number;
  enemies_flashed: number;
  equipment_value: number;
  clutch_attempted: boolean;
  clutch_won: boolean;
};

type Match = {
  match_id: string;
  player_name: string;
  player_steamid?: string | null;
  map_name: string;
  team_score: number;
  opponent_score: number;
  rounds: Round[];
};

type Evidence = {
  finding: string;
  rounds: number[];
  metric: string;
  severity: "high" | "medium" | "positive";
  suggestion: string;
};

type KnowledgeReference = {
  knowledge_id: string;
  title: string;
  principle: string;
  source: string;
  matched_topics: string[];
  score: number;
};

type DecisionCard = {
  round_number: number;
  tick: number;
  location: string;
  side: "T" | "CT";
  classification: string;
  risk_score: number;
  risk_level: "high" | "medium" | "low";
  verdict: "high_risk" | "review" | "reasonable";
  situation: string;
  factors: string[];
  better_action: string;
  knowledge_ids: string[];
  confidence: "high" | "medium" | "low";
};

type DecisionAction =
  | "continue_contact"
  | "disengage_reset"
  | "wait_for_support"
  | "create_utility_condition";

type ContactCandidateAction = {
  action: DecisionAction;
  label: string;
  risk_score: number;
  rationale: string;
  assumptions: string[];
  recommended: boolean;
};

type ContactDecisionCard = {
  round_number: number;
  tick: number;
  location: string;
  side: "T" | "CT";
  observed_outcome: "kill" | "death" | "disengaged";
  weapon: string;
  first_damage_by_player: boolean;
  condition_risk_score: number;
  risk_level: "high" | "medium" | "low";
  factors: string[];
  candidate_actions: ContactCandidateAction[];
  preferred_action: DecisionAction;
  confidence: "high" | "medium" | "low";
};

type CalibrationSummary = {
  total: number;
  agreements: number;
  agreement_rate: number | null;
};

type AgentAnalysis = {
  answer: string;
  summary: Record<string, string | number>;
  evidence: Array<Omit<Evidence, "rounds"> & { round_numbers: number[] }>;
  tools_used: string[];
  execution_trace: string[];
  knowledge_references: KnowledgeReference[];
  decision_cards: DecisionCard[];
  contact_decision_cards: ContactDecisionCard[];
  confidence: "high" | "medium" | "low";
};

type DemoJob = {
  job_id: string;
  status: "queued" | "discovering" | "awaiting_player" | "parsing" | "finalizing" | "completed" | "failed" | "cancelled";
  progress: number;
  player_name: string | null;
  player_steamid: string | null;
  available_players: string[];
  player_options: Array<{ name: string; steamid: string }>;
  match: Match | null;
  analysis: AgentAnalysis | null;
  error: string | null;
};

type CoachChatResponse = {
  mode: "offline" | "llm";
  answer: string;
  model_name: string | null;
  evidence_refs: string[];
  knowledge_ids: string[];
  follow_up_questions: string[];
  validation_warnings: string[];
  remembered_turns: number;
};

type CoachMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: CoachChatResponse;
};

type CoachHistoryResponse = {
  messages: Array<Pick<CoachMessage, "role" | "content">>;
  remembered_turns: number;
  error?: string;
};

function r(
  number: number,
  won: number,
  kills: number,
  assists: number,
  died: number,
  damage: number,
  opening: Round["opening_duel"] = "none",
  traded = 0,
  utility = 0,
  flashes = 0,
  equipment = 5000,
  clutch = 0,
): Round {
  return {
    number,
    won: Boolean(won),
    kills,
    assists,
    died: Boolean(died),
    damage,
    opening_duel: opening,
    was_traded: Boolean(traded),
    utility_damage: utility,
    enemies_flashed: flashes,
    equipment_value: equipment,
    clutch_attempted: Boolean(clutch),
    clutch_won: false,
  };
}

const DEMO: Match = {
  match_id: "demo-mirage-001",
  player_name: "Learner",
  map_name: "de_mirage",
  team_score: 10,
  opponent_score: 12,
  rounds: [
    r(1, 1, 2, 0, 0, 168, "won", 0, 0, 0, 800),
    r(2, 1, 1, 1, 0, 103, "none", 0, 18, 1, 3600),
    r(3, 0, 0, 0, 1, 31, "lost", 0, 0, 0, 4200),
    r(4, 0, 1, 0, 1, 94, "none", 1),
    r(5, 1, 2, 0, 0, 157, "none", 0, 22, 2),
    r(6, 0, 0, 0, 1, 18, "lost", 0, 0, 0, 3900),
    r(7, 0, 1, 0, 1, 112, "none", 0, 0, 0, 2000),
    r(8, 1, 1, 1, 0, 89, "none", 0, 35, 2),
    r(9, 0, 2, 0, 1, 173, "none", 0, 0, 0, 4900, 1),
    r(10, 0, 0, 0, 1, 26, "lost"),
    r(11, 1, 2, 0, 0, 149, "won", 0, 12, 1),
    r(12, 1, 1, 0, 0, 101, "none", 0, 0, 0, 1000),
    r(13, 0, 0, 0, 1, 42, "none", 0, 0, 0, 3350),
    r(14, 0, 2, 0, 1, 181, "none", 0, 0, 0, 5100, 1),
    r(15, 1, 2, 0, 0, 154, "none", 0, 41, 2),
    r(16, 0, 0, 0, 1, 23, "lost"),
    r(17, 1, 1, 1, 0, 97, "none", 0, 28, 1),
    r(18, 0, 1, 0, 1, 105, "none", 1),
    r(19, 0, 2, 0, 1, 165, "none", 0, 0, 0, 5250, 1),
    r(20, 1, 2, 0, 0, 142, "won", 0, 16),
    r(21, 0, 0, 0, 1, 37, "lost", 0, 0, 0, 2400),
    r(22, 1, 1, 1, 0, 91, "none", 0, 32, 2),
  ],
};

const labels: Record<string, string> = {
  opening: "首轮交火",
  trade: "补枪距离",
  utility: "道具效率",
  economy: "经济决策",
  clutch: "残局转化",
};

const actionLabels: Record<DecisionAction, string> = {
  continue_contact: "继续接触",
  disengage_reset: "脱离重置",
  wait_for_support: "等待支援",
  create_utility_condition: "创造道具条件",
};

const outcomeLabels = {
  kill: "最终击杀",
  death: "最终死亡",
  disengaged: "主动脱离",
};

function contactCardKey(matchId: string, card: ContactDecisionCard): string {
  return `${matchId}:${card.round_number}:${card.tick}:${card.side}:${card.location}`;
}

function chooseTools(question: string): string[] {
  const rules: [string, string[]][] = [
    ["opening", ["首杀", "首死", "突破", "对枪", "开局"]],
    ["trade", ["补枪", "白给", "单摸", "站位", "死亡"]],
    ["utility", ["道具", "闪光", "手雷", "烟雾", "辅助"]],
    ["economy", ["经济", "起枪", "强起", "eco", "购买"]],
    ["clutch", ["残局", "击杀", "杀很多", "转化", "输"]],
  ];
  const selected = rules
    .filter(([, words]) => words.some((word) => question.toLowerCase().includes(word)))
    .map(([name]) => name);
  if (selected.length) return selected;
  if (/综合|全面|改进|复盘/.test(question)) return rules.map(([name]) => name);
  return ["opening", "trade", "clutch"];
}

function summarize(match: Match) {
  const kills = match.rounds.reduce((sum, round) => sum + round.kills, 0);
  const assists = match.rounds.reduce((sum, round) => sum + round.assists, 0);
  const deaths = match.rounds.filter((round) => round.died).length;
  const damage = match.rounds.reduce((sum, round) => sum + round.damage, 0);
  const kast = match.rounds.filter(
    (round) => round.kills || round.assists || !round.died || round.was_traded,
  ).length;
  return {
    score: `${match.team_score}:${match.opponent_score}`,
    kills,
    assists,
    deaths,
    adr: (damage / match.rounds.length).toFixed(1),
    kast: ((kast / match.rounds.length) * 100).toFixed(1),
    rounds: match.rounds.length,
  };
}

function analyze(match: Match, tools: string[]): Evidence[] {
  const evidence: Evidence[] = [];
  if (tools.includes("opening")) {
    const won = match.rounds.filter((x) => x.opening_duel === "won").map((x) => x.number);
    const lost = match.rounds.filter((x) => x.opening_duel === "lost").map((x) => x.number);
    const rate = (won.length / (won.length + lost.length || 1)) * 100;
    if (lost.length >= 4 && rate < 45) evidence.push({
      finding: "首轮交火承担较多，但成功率偏低，队伍过早进入人数劣势。",
      rounds: lost,
      metric: `${won.length} 胜 ${lost.length} 负 · ${rate.toFixed(1)}%`,
      severity: "high",
      suggestion: "接触前要求队友给闪或保持两秒内可补枪距离；防守方减少重复 peek。",
    });
  }
  if (tools.includes("trade")) {
    const deaths = match.rounds.filter((x) => x.died).length;
    const rounds = match.rounds
      .filter((x) => x.died && !x.was_traded && !x.clutch_attempted)
      .map((x) => x.number);
    if (rounds.length >= 5) evidence.push({
      finding: "多数死亡没有形成及时补枪，是本场最高优先级问题。",
      rounds,
      metric: `${deaths} 次死亡中 ${rounds.length} 次未被补枪`,
      severity: "high",
      suggestion: "每次接触前确认最近队友位置，把“能否在两秒内被补枪”作为出手条件。",
    });
  }
  if (tools.includes("utility")) {
    const rounds = match.rounds
      .filter((x) => x.utility_damage >= 20 || x.enemies_flashed >= 2)
      .map((x) => x.number);
    const average = match.rounds.reduce((sum, x) => sum + x.utility_damage, 0) / match.rounds.length;
    const flashes = match.rounds.reduce((sum, x) => sum + x.enemies_flashed, 0);
    evidence.push({
      finding: "道具能在部分关键回合为队伍创造有效交火条件。",
      rounds,
      metric: `场均道具伤害 ${average.toFixed(1)} · 闪白 ${flashes} 次`,
      severity: "positive",
      suggestion: "固定掌握两颗进攻闪与两颗拖延道具，并记录是否真正帮助队友接敌。",
    });
  }
  if (tools.includes("economy")) {
    const rounds = match.rounds
      .filter((x) => x.equipment_value >= 1800 && x.equipment_value < 4000 && x.died && !x.won)
      .map((x) => x.number);
    if (rounds.length >= 2) evidence.push({
      finding: "多个非长枪局投入装备后快速阵亡，购买目标不够统一。",
      rounds,
      metric: `${rounds.length} 个中等投入回合失利且阵亡`,
      severity: "medium",
      suggestion: "购买前明确保经济、集中强起还是为队友起枪，避免个人半起后单独接触。",
    });
  }
  if (tools.includes("clutch")) {
    const rounds = match.rounds.filter((x) => x.clutch_attempted).map((x) => x.number);
    const wins = match.rounds.filter((x) => x.clutch_won).length;
    if (rounds.length) evidence.push({
      finding: "部分击杀发生在低胜率残局，击杀数没有完全转化为回合胜利。",
      rounds,
      metric: `残局 ${rounds.length} 次 · 获胜 ${wins} 次`,
      severity: "medium",
      suggestion: "先评估时间、拆包条件和逐个击破路线；时间不足时把保枪纳入决策。",
    });
  }
  const order = { high: 0, medium: 1, positive: 2 };
  return evidence.sort((a, b) => order[a.severity] - order[b.severity]);
}

function isMatch(value: unknown): value is Match {
  if (!value || typeof value !== "object") return false;
  const match = value as Partial<Match>;
  return Boolean(match.match_id && match.player_name && match.map_name && match.rounds?.length);
}

export default function Home() {
  const [match, setMatch] = useState(DEMO);
  const [question, setQuestion] = useState("请综合分析这场比赛，找出最值得优先改进的问题。");
  const [query, setQuery] = useState(question);
  const [error, setError] = useState("");
  const [pendingDemoJobId, setPendingDemoJobId] = useState("");
  const [availablePlayers, setAvailablePlayers] = useState<Array<{ name: string; steamid: string }>>([]);
  const [selectedPlayer, setSelectedPlayer] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadStatus, setUploadStatus] = useState("");
  const [remoteAnalysis, setRemoteAnalysis] = useState<AgentAnalysis | null>(null);
  const [coachMessages, setCoachMessages] = useState<CoachMessage[]>([]);
  const [coachQuestion, setCoachQuestion] = useState("");
  const [coachPending, setCoachPending] = useState(false);
  const [coachMode, setCoachMode] = useState<"offline" | "llm" | null>(null);
  const [rememberedTurns, setRememberedTurns] = useState(0);
  const [coachError, setCoachError] = useState("");
  const [coachStage, setCoachStage] = useState("");
  const [copiedMessageId, setCopiedMessageId] = useState("");
  const [annotationSelections, setAnnotationSelections] = useState<Record<string, DecisionAction>>({});
  const [annotationReasons, setAnnotationReasons] = useState<Record<string, string>>({});
  const [annotationPending, setAnnotationPending] = useState("");
  const [annotationError, setAnnotationError] = useState("");
  const [calibration, setCalibration] = useState<CalibrationSummary>({ total: 0, agreements: 0, agreement_rate: null });
  const coachAbortRef = useRef<AbortController | null>(null);
  const demoPollAbortRef = useRef<AbortController | null>(null);
  const coachThreadEndRef = useRef<HTMLDivElement | null>(null);
  const tools = useMemo(() => chooseTools(query), [query]);
  const stats = useMemo(() => summarize(match), [match]);
  const localEvidence = useMemo(() => analyze(match, tools), [match, tools]);
  const evidence = remoteAnalysis
    ? remoteAnalysis.evidence.map((item) => ({ ...item, rounds: item.round_numbers }))
    : localEvidence;
  const confidence = remoteAnalysis
    ? remoteAnalysis.confidence.toUpperCase()
    : evidence.length >= 3 && evidence.some((x) => x.severity === "high")
      ? "HIGH" : evidence.length ? "MEDIUM" : "LOW";
  const localTrace = [
    "prepare · 计算基础统计",
    `planner · 选择 ${tools.map((tool) => labels[tool]).join("、")}`,
    ...tools.map((tool) => `tool · ${labels[tool]} 返回证据`),
    `reviewer · 保留 ${evidence.length} 条可追溯证据`,
    "reporter · 生成中文训练建议",
  ];
  const trace = remoteAnalysis?.execution_trace ?? localTrace;
  const decisionCards = remoteAnalysis?.decision_cards ?? [];
  const contactDecisionCards = remoteAnalysis?.contact_decision_cards ?? [];
  const knowledgeReferences = remoteAnalysis?.knowledge_references ?? [];

  useEffect(() => {
    fetch("/api/config")
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((config: { backendUrl?: string }) => setApiBase((config.backendUrl ?? "").replace(/\/$/, "")))
      .catch(() => setApiBase(""));
  }, []);

  useEffect(() => {
    if (!remoteAnalysis || !match.player_steamid) return;
    const controller = new AbortController();
    const params = new URLSearchParams({
      playerSteamid: match.player_steamid,
      mapName: match.map_name,
    });
    setCoachStage("正在恢复历史对话…");
    fetch(`/api/coach/chat?${params}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json() as CoachHistoryResponse;
        if (!response.ok) throw new Error(body.error ?? "无法恢复历史对话");
        setCoachMessages(body.messages.map((message, index) => ({
          ...message,
          id: `history-${index}`,
        })));
        setRememberedTurns(body.remembered_turns);
      })
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setCoachError(reason instanceof Error ? reason.message : "无法恢复历史对话");
      })
      .finally(() => setCoachStage(""));
    return () => controller.abort();
  }, [remoteAnalysis, match.player_steamid, match.map_name]);

  useEffect(() => {
    coachThreadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [coachMessages, coachPending, coachError]);

  useEffect(() => {
    if (!match.player_steamid || !contactDecisionCards.length) return;
    const controller = new AbortController();
    const cardKeys = contactDecisionCards.map((card) => contactCardKey(match.match_id, card));
    fetch("/api/decision-annotations", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        playerSteamid: match.player_steamid,
        mapName: match.map_name,
        cardKeys,
      }),
      signal: controller.signal,
    }).then(async (response) => {
      const body = await response.json() as {
        selections?: Record<string, DecisionAction>;
        summary?: CalibrationSummary;
        error?: string;
      };
      if (!response.ok) throw new Error(body.error ?? "无法读取校准数据");
      setAnnotationSelections(body.selections ?? {});
      if (body.summary) setCalibration(body.summary);
    }).catch((reason) => {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setAnnotationError(reason instanceof Error ? reason.message : "无法读取校准数据");
    });
    return () => controller.abort();
  }, [contactDecisionCards, match.match_id, match.map_name, match.player_steamid]);

  async function annotateDecision(card: ContactDecisionCard, humanAction: DecisionAction) {
    if (!match.player_steamid) return;
    const cardKey = contactCardKey(match.match_id, card);
    setAnnotationPending(cardKey);
    setAnnotationError("");
    try {
      const response = await fetch("/api/decision-annotations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          playerSteamid: match.player_steamid,
          mapName: match.map_name,
          cardKey,
          observedOutcome: card.observed_outcome,
          agentAction: card.preferred_action,
          humanAction,
          reason: annotationReasons[cardKey] ?? "",
        }),
      });
      const body = await response.json() as { summary?: CalibrationSummary; error?: string };
      if (!response.ok) throw new Error(body.error ?? "标注保存失败");
      setAnnotationSelections((current) => ({ ...current, [cardKey]: humanAction }));
      if (body.summary) setCalibration(body.summary);
    } catch (reason) {
      setAnnotationError(reason instanceof Error ? reason.message : "标注保存失败");
    } finally {
      setAnnotationPending("");
    }
  }

  async function upload(file?: File) {
    if (!file) return;
    setError("");
    setRemoteAnalysis(null);
    setCoachMessages([]);
    setCoachMode(null);
    setRememberedTurns(0);
    if (file.name.toLowerCase().endsWith(".dem")) {
      await uploadDemo(file);
      return;
    }
    try {
      const value: unknown = JSON.parse(await file.text());
      if (!isMatch(value)) throw new Error("JSON 缺少比赛或回合字段");
      setMatch(value);
      setUploadStatus("JSON 已在浏览器中加载");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "比赛文件无法读取");
    }
  }

  async function uploadDemo(file: File) {
    if (!apiBase) {
      setError("Demo 后端尚未连接；目前仍可上传 JSON 或体验内置比赛。");
      return;
    }
    if (file.size > MAX_DEMO_BYTES) {
      setError(`Demo 文件不能超过 ${MAX_DEMO_MB} MB。`);
      return;
    }
    setUploadProgress(0);
    setUploadStatus("正在上传 Demo…");
    setPendingDemoJobId("");
    setAvailablePlayers([]);
    setSelectedPlayer("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("question", question.trim() || "请综合复盘这场比赛");
      const job = await new Promise<DemoJob>((resolve, reject) => {
        const request = new XMLHttpRequest();
        request.open("POST", `${apiBase}/api/demo-jobs`);
        request.upload.onprogress = (event) => {
          if (event.lengthComputable) setUploadProgress(Math.round(event.loaded / event.total * 30));
        };
        request.onload = () => {
          try {
            const body = JSON.parse(request.responseText);
            if (request.status >= 200 && request.status < 300) resolve(body);
            else reject(new Error(body.detail ?? "Demo 上传失败"));
          } catch { reject(new Error("服务器返回了无法识别的响应")); }
        };
        request.onerror = () => reject(new Error("无法连接 Demo 解析服务"));
        request.send(form);
      });
      setPendingDemoJobId(job.job_id);
      const current = await pollDemoJob(job, true);
      setPendingDemoJobId(current.job_id);
      setAvailablePlayers(current.player_options?.length
        ? current.player_options
        : current.available_players.map((name) => ({ name, steamid: name })));
      setUploadProgress(current.progress);
      setUploadStatus(`已找到 ${current.available_players.length} 名玩家，请选择复盘对象`);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setUploadProgress(null);
      setUploadStatus("");
      setError(reason instanceof Error ? reason.message : "Demo 处理失败");
    }
  }

  async function pollDemoJob(job: DemoJob, stopAtPlayerSelection = false) {
    demoPollAbortRef.current?.abort();
    const controller = new AbortController();
    demoPollAbortRef.current = controller;
    let current = job;
    try {
      for (let attempt = 0; attempt < 180 && current.status !== "completed"; attempt += 1) {
        if (current.status === "failed") throw new Error(current.error ?? "Demo 解析失败");
        if (current.status === "cancelled") throw new DOMException("Demo 解析已取消", "AbortError");
        if (current.status === "awaiting_player" && stopAtPlayerSelection) return current;
        setUploadProgress(Math.max(35, current.progress));
        setUploadStatus(current.status === "discovering"
          ? "正在读取 Demo 中的玩家名单…"
          : "服务器正在解析回合与玩家事件…");
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const response = await fetch(`${apiBase}/api/demo-jobs/${current.job_id}`, { signal: controller.signal });
        if (!response.ok) throw new Error("无法查询 Demo 解析进度");
        current = await response.json();
      }
      if (current.status !== "completed" || !current.match) throw new Error("Demo 解析超时，请稍后重试");
      return current;
    } finally {
      if (demoPollAbortRef.current === controller) demoPollAbortRef.current = null;
    }
  }

  async function cancelDemoJob() {
    if (!apiBase || !pendingDemoJobId) return;
    const jobId = pendingDemoJobId;
    demoPollAbortRef.current?.abort();
    try {
      const response = await fetch(`${apiBase}/api/demo-jobs/${jobId}`, { method: "DELETE" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "无法取消 Demo 任务");
      setUploadStatus("Demo 解析已取消，临时文件已清理");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法取消 Demo 任务");
    } finally {
      setPendingDemoJobId("");
      setAvailablePlayers([]);
      setSelectedPlayer("");
      setUploadProgress(null);
    }
  }

  async function selectDemoPlayer(playerSteamid: string) {
    setSelectedPlayer(playerSteamid);
    const player = availablePlayers.find((item) => item.steamid === playerSteamid);
    if (!player || !pendingDemoJobId) return;
    setError("");
    setUploadStatus(`正在解析 ${player.name} 的回合事件…`);
    try {
      const response = await fetch(`${apiBase}/api/demo-jobs/${pendingDemoJobId}/player`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          player_name: player.name,
          player_steamid: player.steamid,
          question: question.trim() || "请综合复盘这场比赛",
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "无法选择玩家");
      const completed = await pollDemoJob(body);
      setMatch(completed.match as Match);
      setRemoteAnalysis(completed.analysis);
      setCoachMessages([]);
      setCoachMode(null);
      setRememberedTurns(0);
      setQuery(question.trim() || "综合复盘");
      setUploadProgress(100);
      setUploadStatus("Demo 解析完成，临时文件已删除");
      setPendingDemoJobId("");
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setUploadProgress(null);
      setUploadStatus("");
      setError(reason instanceof Error ? reason.message : "Demo 处理失败");
    }
  }

  async function runAgent() {
    const nextQuestion = question.trim() || "综合复盘";
    setQuery(nextQuestion);
    if (!apiBase || !match.match_id.startsWith("dem-")) {
      setRemoteAnalysis(null);
      return;
    }
    try {
      const response = await fetch(`${apiBase}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ match_id: match.match_id, question: nextQuestion }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Agent 分析失败");
      setRemoteAnalysis(body);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Agent 分析失败");
    }
  }

  async function askCoach(suggestedQuestion?: string) {
    const nextQuestion = (suggestedQuestion ?? coachQuestion).trim();
    if (!nextQuestion || coachPending) return;
    if (!apiBase || !match.player_steamid || !remoteAnalysis) {
      setError("请先上传 Demo、选择玩家并等待解析完成，再开始连续教练对话。");
      return;
    }
    const userMessage: CoachMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: nextQuestion,
    };
    setCoachMessages((current) => [...current, userMessage]);
    setCoachQuestion("");
    setCoachPending(true);
    setCoachError("");
    setCoachStage("正在整理玩家画像与比赛上下文…");
    const controller = new AbortController();
    coachAbortRef.current = controller;
    const evidenceStage = window.setTimeout(
      () => setCoachStage("正在核对回合证据与知识条目…"),
      1200,
    );
    const answerStage = window.setTimeout(
      () => setCoachStage("正在组织可执行的教练建议…"),
      3500,
    );
    try {
      const response = await fetch("/api/coach/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          playerSteamid: match.player_steamid,
          mapName: match.map_name,
          question: nextQuestion,
        }),
        signal: controller.signal,
      });
      const body = await response.json() as CoachChatResponse & { error?: string };
      if (!response.ok) throw new Error(body.error ?? "教练暂时无法回答");
      setCoachMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: "assistant",
        content: body.answer,
        response: body,
      }]);
      setCoachMode(body.mode);
      setRememberedTurns(body.remembered_turns);
    } catch (reason) {
      const wasStopped = reason instanceof DOMException && reason.name === "AbortError";
      setCoachError(wasStopped ? "本次生成已停止，你可以修改问题后重试。" : reason instanceof Error ? reason.message : "教练对话失败");
    } finally {
      window.clearTimeout(evidenceStage);
      window.clearTimeout(answerStage);
      coachAbortRef.current = null;
      setCoachPending(false);
      setCoachStage("");
    }
  }

  function stopCoach() {
    coachAbortRef.current?.abort();
  }

  async function copyCoachAnswer(message: CoachMessage) {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopiedMessageId(message.id);
      window.setTimeout(() => setCopiedMessageId(""), 1600);
    } catch {
      setCoachError("复制失败，请手动选择文本复制。");
    }
  }

  function retryLastQuestion() {
    const lastQuestion = [...coachMessages].reverse().find((message) => message.role === "user");
    if (lastQuestion) askCoach(lastQuestion.content);
  }

  async function resetCoachConversation() {
    if (!match.player_steamid) return;
    setCoachPending(true);
    setCoachError("");
    try {
      const response = await fetch("/api/coach/chat", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          playerSteamid: match.player_steamid,
          mapName: match.map_name,
        }),
      });
      const body = await response.json() as { error?: string };
      if (!response.ok) throw new Error(body.error ?? "无法清空会话");
      setCoachMessages([]);
      setCoachMode(null);
      setRememberedTurns(0);
    } catch (reason) {
      setCoachError(reason instanceof Error ? reason.message : "无法清空会话");
    } finally {
      setCoachPending(false);
    }
  }

  return <main>
    <nav><a href="#top" className="brand"><b>R</b> ROUNDMIND</a><span className="status">● {apiBase ? "DEMO API READY" : "BROWSER DEMO"}</span></nav>
    <section className="hero" id="top">
      <p className="eyebrow">EVIDENCE-BASED MATCH REVIEW</p>
      <h1>别只看战绩。<br/><em>找出真正丢分的习惯。</em></h1>
      <p className="intro">RoundMind 会选择合适的分析工具，追踪关键回合，并把冷冰冰的数据转化成下一场就能执行的训练重点。</p>
      <div className="heroStats"><div><strong>6</strong><span>分析工具</span></div><div><strong>{MAX_DEMO_MB}MB</strong><span>Demo 上限</span></div><div><strong>8</strong><span>决策评测场景</span></div><div><strong>0</strong><span>默认模型费用</span></div></div>
    </section>
    <section className="workspace">
      <aside className="controls">
        <p className="eyebrow">01 / MATCH INPUT</p><h2>开始一次复盘</h2>
        <p className="fieldLabel">比赛数据</p><div className="selectLike">{match.player_name} · {match.map_name} · {match.team_score}:{match.opponent_score}</div>
        <label htmlFor="player-select">选择要复盘的玩家</label>
        <select id="player-select" value={selectedPlayer} disabled={!availablePlayers.length || !pendingDemoJobId} onChange={(event) => selectDemoPlayer(event.target.value)}>
          <option value="">上传 Demo 后自动读取玩家名单</option>
          {availablePlayers.map((player) => <option value={player.steamid} key={player.steamid}>{player.name} · Steam …{player.steamid.slice(-6)}</option>)}
        </select>
        <label className="upload" htmlFor="match-file">＋<strong>上传 CS2 Demo 或 JSON</strong><small>.dem 最大 {MAX_DEMO_MB} MB · 解析后自动删除</small><input id="match-file" type="file" accept=".dem,.json,application/json" onChange={(event) => upload(event.target.files?.[0])}/></label>
        {uploadProgress !== null && <div className="progress" aria-label={`处理进度 ${uploadProgress}%`}><i style={{ width: `${uploadProgress}%` }}/></div>}
        {(uploadStatus || pendingDemoJobId) && <div className="uploadMeta">{uploadStatus && <p className="uploadStatus">{uploadStatus}</p>}{pendingDemoJobId && <button onClick={cancelDemoJob}>取消任务</button>}</div>}
        {error && <p className="error">{error}</p>}
        <label htmlFor="question">你最想弄清什么？</label>
        <textarea id="question" rows={5} value={question} onChange={(event) => setQuestion(event.target.value)}/>
        <div className="chips"><button onClick={() => setQuestion("为什么我杀了很多人还是输了？")}>击杀没转化？</button><button onClick={() => setQuestion("分析我的首杀、首死和补枪问题。")}>首轮交火</button><button onClick={() => setQuestion("我的道具和经济决策有什么问题？")}>道具与经济</button><button onClick={() => setQuestion("分析我的接战局势、队友距离和孤立前压决策。")}>接战决策</button></div>
        <button className="primary" onClick={runAgent}>运行复盘 Agent <span>↗</span></button>
      </aside>
      <article className="report">
        <header><div><p className="eyebrow">02 / COACH REPORT</p><h2>{match.player_name} · {match.map_name}</h2></div><span className="confidence">置信度 {confidence}</span></header>
        <div className="metrics"><div><span>SCORE</span><strong>{stats.score}</strong></div><div><span>K / D / A</span><strong>{stats.kills} / {stats.deaths} / {stats.assists}</strong></div><div><span>ADR</span><strong>{stats.adr}</strong></div><div><span>KAST</span><strong>{stats.kast}%</strong></div><div><span>ROUNDS</span><strong>{stats.rounds}</strong></div></div>
        <div className="reportGrid"><section><h3>教练结论</h3><p className="lead">{remoteAnalysis?.answer || `${match.player_name} 在 ${match.map_name} 打出 ${stats.kills}/${stats.deaths}/${stats.assists}，ADR ${stats.adr}，KAST ${stats.kast}%。`}</p>{evidence.map((item, index) => <div className="finding" key={item.finding}><b>{index + 1}. {item.finding}</b><p>证据：{item.metric}；相关回合：{item.rounds.map((round) => `R${round}`).join("、") || "全场统计"}。</p><p>训练建议：{item.suggestion}</p></div>)}<p className="focus">下一场先只跟踪最高优先级问题，避免一次同时修改太多习惯。</p></section><aside><h3>证据卡片</h3>{evidence.map((item) => <div className={`evidence ${item.severity}`} key={item.metric}><span>{item.severity.toUpperCase()}</span><p>{item.metric}</p><i>{item.rounds.map((round) => `R${round}`).join(" · ") || "全场统计"}</i></div>)}</aside></div>
        {contactDecisionCards.length > 0 && <section className="contactDecisionSection">
          <div className="sectionTitle">
            <div><p className="eyebrow">03 / ACTION COMPARISON</p><h3>当时还有哪些选择？</h3></div>
            <span>同一套事前条件同时评价击杀、死亡和脱离，不用赛后结果倒推对错</span>
          </div>
          <div className="calibrationBar">
            <div><b>{calibration.total}</b><span>人工校准样本</span></div>
            <div><b>{calibration.agreement_rate === null ? "待标注" : `${(calibration.agreement_rate * 100).toFixed(0)}%`}</b><span>与 Agent 推荐一致</span></div>
            <p>一致率低不代表玩家错了，而是提醒我们检查评分规则。建议先积累 20–30 张卡再调整阈值。</p>
          </div>
          {annotationError && <p className="annotationError">{annotationError}</p>}
          <div className="contactDecisionGrid">{contactDecisionCards.slice(0, 6).map((card) => {
            const cardKey = contactCardKey(match.match_id, card);
            const selected = annotationSelections[cardKey];
            return <article className={`contactDecisionCard ${card.risk_level}`} key={cardKey}>
              <header><div><span>R{card.round_number} · {card.side} · {outcomeLabels[card.observed_outcome]}</span><strong>{card.location} · {card.weapon}</strong></div><div className="riskScore"><b>{card.condition_risk_score}</b><small>/100 事前风险</small></div></header>
              <p className="conditionNote">{card.first_damage_by_player ? "你先造成伤害" : "对手先造成伤害"} · 置信度 {card.confidence.toUpperCase()}</p>
              <ul className="conditionFactors">{card.factors.slice(0, 3).map((factor) => <li key={factor}>{factor}</li>)}</ul>
              <div className="candidateList">{card.candidate_actions.map((candidate) => <div className={candidate.recommended ? "candidate recommended" : "candidate"} key={candidate.action}><div><b>{candidate.label}</b>{candidate.recommended && <i>AGENT 推荐</i>}</div><strong>{candidate.risk_score}</strong><p>{candidate.rationale}</p>{candidate.assumptions.map((assumption) => <small key={assumption}>前提：{assumption}</small>)}</div>)}</div>
              <div className="annotationBox"><b>你认为当时更合理的动作是？</b><div>{card.candidate_actions.map((candidate) => <button aria-pressed={selected === candidate.action} className={selected === candidate.action ? "selected" : ""} disabled={annotationPending === cardKey} key={candidate.action} onClick={() => annotateDecision(card, candidate.action)}>{actionLabels[candidate.action]}</button>)}</div><input maxLength={300} value={annotationReasons[cardKey] ?? ""} placeholder="可选：写一句判断原因，再点击动作保存" onChange={(event) => setAnnotationReasons((current) => ({ ...current, [cardKey]: event.target.value }))}/>{selected && <small>已保存：{actionLabels[selected]}{selected === card.preferred_action ? " · 与 Agent 一致" : " · 将用于检查规则"}</small>}</div>
            </article>;
          })}</div>
        </section>}
        {decisionCards.length > 0 && <section className="decisionSection"><div className="sectionTitle"><div><p className="eyebrow">04 / DEATH REVIEW</p><h3>死亡前接战复盘卡</h3></div><span>保留更完整的炸弹、人数和烟雾局势解释</span></div><div className="decisionGrid">{decisionCards.slice(0, 6).map((card) => <article className={`decisionCard ${card.risk_level}`} key={`${card.round_number}-${card.tick}`}><header><div><span>R{card.round_number} · {card.side}</span><strong>{card.location}</strong></div><div className="riskScore"><b>{card.risk_score}</b><small>/100</small></div></header><div className="riskTrack" aria-label={`风险分 ${card.risk_score}`}><i style={{ width: `${card.risk_score}%` }}/></div><p className="situation">{card.situation}</p><ul>{card.factors.slice(0, 3).map((factor) => <li key={factor}>{factor}</li>)}</ul><p className="better"><b>更优动作</b>{card.better_action}</p><footer><span>置信度 {card.confidence.toUpperCase()}</span><span>{card.knowledge_ids.join(" · ") || "仅比赛事实"}</span></footer></article>)}</div>{knowledgeReferences.length > 0 && <details className="knowledgePanel"><summary>查看本次引用的 {knowledgeReferences.length} 条 Dust2 战术知识</summary><ol>{knowledgeReferences.map((item) => <li key={item.knowledge_id}><b>[{item.knowledge_id}] {item.title}</b><p>{item.principle}</p><small>{item.source} · 匹配分 {item.score}</small></li>)}</ol></details>}</section>}
        <section className="coachSection">
          <div className="sectionTitle coachTitle">
            <div><p className="eyebrow">05 / CONTINUOUS COACH</p><h3>围绕这名玩家继续追问</h3></div>
            <div className="coachStatus"><span>{coachMode === "llm" ? "DEEPSEEK" : coachMode === "offline" ? "OFFLINE" : "READY"}</span><small>已记忆 {rememberedTurns} 轮</small></div>
          </div>
          {!remoteAnalysis || !match.player_steamid ? <div className="coachEmpty"><b>先完成一次 Demo 解析</b><p>选择玩家后，教练会带着比赛证据、角色画像和历史问答与你连续交流。</p></div> : <>
            <div className="coachThread" aria-live="polite">
              {coachMessages.length === 0 && <div className="coachWelcome"><span>RM</span><p>比赛上下文已经就绪。你可以让教练展开某条结论、制定训练计划，或解释具体回合。历史最多保留 6 轮。</p></div>}
              {coachMessages.map((message) => <article className={`chatBubble ${message.role}`} key={message.id}><span>{message.role === "user" ? "YOU" : "COACH"}</span><p>{message.content}</p>{message.response && <><div className="chatRefs">{message.response.evidence_refs.map((item) => <i key={item}>{item}</i>)}{message.response.knowledge_ids.map((item) => <i key={item}>{item}</i>)}</div>{message.response.validation_warnings.map((warning) => <small className="chatWarning" key={warning}>{warning}</small>)}</>}{message.role === "assistant" && <div className="chatActions"><button onClick={() => copyCoachAnswer(message)}>{copiedMessageId === message.id ? "已复制" : "复制回答"}</button></div>}</article>)}
              {coachPending && <div className="coachTyping"><i/><i/><i/><span>{coachStage || "教练正在处理"}</span><button onClick={stopCoach}>停止</button></div>}
              {!coachPending && coachStage && <div className="coachTyping"><i/><i/><i/><span>{coachStage}</span></div>}
              {coachError && <div className="coachInlineError"><span>{coachError}</span><button onClick={retryLastQuestion} disabled={coachPending || !coachMessages.some((message) => message.role === "user")}>重试上一问</button></div>}
              <div ref={coachThreadEndRef}/>
            </div>
            {coachMessages.at(-1)?.response?.follow_up_questions?.length ? <div className="followUps">{coachMessages.at(-1)?.response?.follow_up_questions.map((item) => <button key={item} onClick={() => askCoach(item)} disabled={coachPending}>{item}</button>)}</div> : null}
            <div className="coachComposer"><textarea aria-label="继续询问教练" rows={3} value={coachQuestion} placeholder="例如：把第一点展开，并给我一个三天练习方案" onChange={(event) => setCoachQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); askCoach(); } }}/><button onClick={() => askCoach()} disabled={coachPending || !coachQuestion.trim()}>发送 <span>↗</span></button></div>
            <div className="coachPrivacy"><span>匿名会话 · 不保存 Demo 和 SteamID · Enter 发送 / Shift + Enter 换行</span><button onClick={resetCoachConversation} disabled={coachPending || !coachMessages.length}>清空对话</button></div>
          </>}
        </section>
        <details><summary>查看 Agent 执行轨迹</summary><ol>{trace.map((step) => <li key={step}>{step}</li>)}</ol></details>
      </article>
    </section>
    <footer><span>ROUNDMIND / MVP 01</span><span>程序计算事实 · Agent 选择工具 · 审核节点约束结论</span></footer>
  </main>;
}
