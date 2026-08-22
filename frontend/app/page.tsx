"use client";

import { useEffect, useMemo, useState } from "react";

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

type AgentAnalysis = {
  answer: string;
  summary: Record<string, string | number>;
  evidence: Array<Omit<Evidence, "rounds"> & { round_numbers: number[] }>;
  tools_used: string[];
  execution_trace: string[];
  confidence: "high" | "medium" | "low";
};

type DemoJob = {
  job_id: string;
  status: "queued" | "discovering" | "awaiting_player" | "parsing" | "completed" | "failed";
  progress: number;
  player_name: string | null;
  available_players: string[];
  match: Match | null;
  analysis: AgentAnalysis | null;
  error: string | null;
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
  const [availablePlayers, setAvailablePlayers] = useState<string[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadStatus, setUploadStatus] = useState("");
  const [remoteAnalysis, setRemoteAnalysis] = useState<AgentAnalysis | null>(null);
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

  useEffect(() => {
    fetch("/api/config")
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((config: { backendUrl?: string }) => setApiBase((config.backendUrl ?? "").replace(/\/$/, "")))
      .catch(() => setApiBase(""));
  }, []);

  async function upload(file?: File) {
    if (!file) return;
    setError("");
    setRemoteAnalysis(null);
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
      const current = await pollDemoJob(job, true);
      setPendingDemoJobId(current.job_id);
      setAvailablePlayers(current.available_players);
      setUploadProgress(current.progress);
      setUploadStatus(`已找到 ${current.available_players.length} 名玩家，请选择复盘对象`);
    } catch (reason) {
      setUploadProgress(null);
      setUploadStatus("");
      setError(reason instanceof Error ? reason.message : "Demo 处理失败");
    }
  }

  async function pollDemoJob(job: DemoJob, stopAtPlayerSelection = false) {
    let current = job;
    for (let attempt = 0; attempt < 180 && current.status !== "completed"; attempt += 1) {
      if (current.status === "failed") throw new Error(current.error ?? "Demo 解析失败");
      if (current.status === "awaiting_player" && stopAtPlayerSelection) return current;
      setUploadProgress(Math.max(35, current.progress));
      setUploadStatus(current.status === "discovering"
        ? "正在读取 Demo 中的玩家名单…"
        : "服务器正在解析回合与玩家事件…");
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      const response = await fetch(`${apiBase}/api/demo-jobs/${current.job_id}`);
      if (!response.ok) throw new Error("无法查询 Demo 解析进度");
      current = await response.json();
    }
    if (current.status !== "completed" || !current.match) throw new Error("Demo 解析超时，请稍后重试");
    return current;
  }

  async function selectDemoPlayer(playerName: string) {
    setSelectedPlayer(playerName);
    if (!playerName || !pendingDemoJobId) return;
    setError("");
    setUploadStatus(`正在解析 ${playerName} 的回合事件…`);
    try {
      const response = await fetch(`${apiBase}/api/demo-jobs/${pendingDemoJobId}/player`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          player_name: playerName,
          question: question.trim() || "请综合复盘这场比赛",
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "无法选择玩家");
      const completed = await pollDemoJob(body);
      setMatch(completed.match as Match);
      setRemoteAnalysis(completed.analysis);
      setQuery(question.trim() || "综合复盘");
      setUploadProgress(100);
      setUploadStatus("Demo 解析完成，临时文件已删除");
      setPendingDemoJobId("");
    } catch (reason) {
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

  return <main>
    <nav><a href="#top" className="brand"><b>R</b> ROUNDMIND</a><span className="status">● {apiBase ? "DEMO API READY" : "BROWSER DEMO"}</span></nav>
    <section className="hero" id="top">
      <p className="eyebrow">EVIDENCE-BASED MATCH REVIEW</p>
      <h1>别只看战绩。<br/><em>找出真正丢分的习惯。</em></h1>
      <p className="intro">RoundMind 会选择合适的分析工具，追踪关键回合，并把冷冰冰的数据转化成下一场就能执行的训练重点。</p>
      <div className="heroStats"><div><strong>5</strong><span>分析工具</span></div><div><strong>{MAX_DEMO_MB}MB</strong><span>Demo 上限</span></div><div><strong>0</strong><span>默认模型费用</span></div></div>
    </section>
    <section className="workspace">
      <aside className="controls">
        <p className="eyebrow">01 / MATCH INPUT</p><h2>开始一次复盘</h2>
        <p className="fieldLabel">比赛数据</p><div className="selectLike">{match.player_name} · {match.map_name} · {match.team_score}:{match.opponent_score}</div>
        <label htmlFor="player-select">选择要复盘的玩家</label>
        <select id="player-select" value={selectedPlayer} disabled={!availablePlayers.length || !pendingDemoJobId} onChange={(event) => selectDemoPlayer(event.target.value)}>
          <option value="">上传 Demo 后自动读取玩家名单</option>
          {availablePlayers.map((player) => <option value={player} key={player}>{player}</option>)}
        </select>
        <label className="upload" htmlFor="match-file">＋<strong>上传 CS2 Demo 或 JSON</strong><small>.dem 最大 {MAX_DEMO_MB} MB · 解析后自动删除</small><input id="match-file" type="file" accept=".dem,.json,application/json" onChange={(event) => upload(event.target.files?.[0])}/></label>
        {uploadProgress !== null && <div className="progress" aria-label={`处理进度 ${uploadProgress}%`}><i style={{ width: `${uploadProgress}%` }}/></div>}
        {uploadStatus && <p className="uploadStatus">{uploadStatus}</p>}
        {error && <p className="error">{error}</p>}
        <label htmlFor="question">你最想弄清什么？</label>
        <textarea id="question" rows={5} value={question} onChange={(event) => setQuestion(event.target.value)}/>
        <div className="chips"><button onClick={() => setQuestion("为什么我杀了很多人还是输了？")}>击杀没转化？</button><button onClick={() => setQuestion("分析我的首杀、首死和补枪问题。")}>首轮交火</button><button onClick={() => setQuestion("我的道具和经济决策有什么问题？")}>道具与经济</button></div>
        <button className="primary" onClick={runAgent}>运行复盘 Agent <span>↗</span></button>
      </aside>
      <article className="report">
        <header><div><p className="eyebrow">02 / COACH REPORT</p><h2>{match.player_name} · {match.map_name}</h2></div><span className="confidence">置信度 {confidence}</span></header>
        <div className="metrics"><div><span>SCORE</span><strong>{stats.score}</strong></div><div><span>K / D / A</span><strong>{stats.kills} / {stats.deaths} / {stats.assists}</strong></div><div><span>ADR</span><strong>{stats.adr}</strong></div><div><span>KAST</span><strong>{stats.kast}%</strong></div><div><span>ROUNDS</span><strong>{stats.rounds}</strong></div></div>
        <div className="reportGrid"><section><h3>教练结论</h3><p className="lead">{remoteAnalysis?.answer || `${match.player_name} 在 ${match.map_name} 打出 ${stats.kills}/${stats.deaths}/${stats.assists}，ADR ${stats.adr}，KAST ${stats.kast}%。`}</p>{evidence.map((item, index) => <div className="finding" key={item.finding}><b>{index + 1}. {item.finding}</b><p>证据：{item.metric}；相关回合：{item.rounds.map((round) => `R${round}`).join("、") || "全场统计"}。</p><p>训练建议：{item.suggestion}</p></div>)}<p className="focus">下一场先只跟踪最高优先级问题，避免一次同时修改太多习惯。</p></section><aside><h3>证据卡片</h3>{evidence.map((item) => <div className={`evidence ${item.severity}`} key={item.metric}><span>{item.severity.toUpperCase()}</span><p>{item.metric}</p><i>{item.rounds.map((round) => `R${round}`).join(" · ") || "全场统计"}</i></div>)}</aside></div>
        <details><summary>查看 Agent 执行轨迹</summary><ol>{trace.map((step) => <li key={step}>{step}</li>)}</ol></details>
      </article>
    </section>
    <footer><span>ROUNDMIND / MVP 01</span><span>程序计算事实 · Agent 选择工具 · 审核节点约束结论</span></footer>
  </main>;
}
