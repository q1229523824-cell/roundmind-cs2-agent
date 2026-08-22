const elements = {
  matchSelect: document.querySelector("#match-select"),
  question: document.querySelector("#question"),
  analyzeButton: document.querySelector("#analyze-button"),
  playerSelect: document.querySelector("#player-select"),
  matchFile: document.querySelector("#match-file"),
  uploadProgress: document.querySelector("#upload-progress"),
  uploadProgressBar: document.querySelector("#upload-progress i"),
  uploadMessage: document.querySelector("#upload-message"),
  uploadHint: document.querySelector("#upload-hint"),
  empty: document.querySelector("#empty-state"),
  loading: document.querySelector("#loading-state"),
  loadingCopy: document.querySelector("#loading-copy"),
  report: document.querySelector("#report"),
  error: document.querySelector("#error-state"),
  reportTitle: document.querySelector("#report-title"),
  confidence: document.querySelector("#confidence"),
  metrics: document.querySelector("#metrics"),
  answer: document.querySelector("#answer"),
  evidenceList: document.querySelector("#evidence-list"),
  traceList: document.querySelector("#trace-list"),
};

const MAX_DEMO_BYTES = 500 * 1024 * 1024;
let pendingDemoJobId = null;

if (["127.0.0.1", "localhost"].includes(window.location.hostname)) {
  elements.uploadHint.textContent = ".dem 最大 500 MB · 仅在本机处理，不会上传到 Render";
}

const loadingMessages = [
  "正在读取基础统计…",
  "规划器正在选择分析工具…",
  "正在核对关键回合证据…",
  "审核节点正在检查结论…",
];

function setView(name) {
  elements.empty.classList.toggle("hidden", name !== "empty");
  elements.loading.classList.toggle("hidden", name !== "loading");
  elements.report.classList.toggle("hidden", name !== "report");
  elements.error.classList.toggle("hidden", name !== "error");
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `请求失败（${response.status}）`);
  }
  return response.json();
}

function fillMatches(matches, selectedId) {
  elements.matchSelect.innerHTML = "";
  matches.forEach((match) => {
    const option = document.createElement("option");
    option.value = match.match_id;
    option.textContent = `${match.player_name} · ${match.map_name} · ${match.team_score}:${match.opponent_score}`;
    option.selected = match.match_id === selectedId;
    elements.matchSelect.append(option);
  });
}

function fillPlayers(players) {
  elements.playerSelect.innerHTML = '<option value="">请选择一名玩家</option>';
  players.forEach((player) => {
    const option = document.createElement("option");
    option.value = player.steamid;
    option.dataset.playerName = player.name;
    option.textContent = `${player.name} · Steam …${player.steamid.slice(-6)}`;
    elements.playerSelect.append(option);
  });
  elements.playerSelect.disabled = players.length === 0;
}

function setUploadProgress(progress) {
  const visible = progress !== null;
  elements.uploadProgress.classList.toggle("hidden", !visible);
  elements.uploadProgress.setAttribute("aria-hidden", String(!visible));
  elements.uploadProgressBar.style.width = `${progress ?? 0}%`;
}

function uploadDemo(file) {
  if (file.size > MAX_DEMO_BYTES) throw new Error("Demo 文件不能超过 500 MB。");

  const form = new FormData();
  form.append("file", file);
  form.append("question", elements.question.value.trim() || "请综合复盘这场比赛");
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/api/demo-jobs");
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) setUploadProgress(Math.round(event.loaded / event.total * 30));
    };
    request.onload = () => {
      try {
        const body = JSON.parse(request.responseText);
        if (request.status >= 200 && request.status < 300) resolve(body);
        else reject(new Error(body.detail || "Demo 上传失败"));
      } catch {
        reject(new Error("服务器返回了无法识别的响应"));
      }
    };
    request.onerror = () => reject(new Error("无法连接 Demo 解析服务"));
    request.send(form);
  });
}

async function waitForDemo(job, stopAtPlayerSelection = false) {
  let current = job;
  for (let attempt = 0; attempt < 180 && current.status !== "completed"; attempt += 1) {
    if (current.status === "failed") throw new Error(current.error || "Demo 解析失败");
    if (current.status === "awaiting_player" && stopAtPlayerSelection) return current;
    setUploadProgress(Math.max(35, current.progress));
    elements.uploadMessage.textContent = current.status === "discovering"
      ? "正在读取 Demo 中的玩家名单…"
      : "服务器正在解析回合与玩家事件…";
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    current = await api(`/api/demo-jobs/${current.job_id}`);
  }
  if (current.status !== "completed" || !current.match) {
    throw new Error("Demo 解析超时，请稍后重试。");
  }
  return current;
}

async function finishDemo(completed) {
  const match = completed.match;
  if (!match) throw new Error("Demo 解析完成但未返回比赛数据。");
  setUploadProgress(100);
  elements.uploadMessage.textContent = "Demo 解析完成，临时文件已删除。";
  fillMatches(await api("/api/matches"), match.match_id);
  if (completed.analysis) renderResult(completed.analysis);
}

function renderMetrics(summary) {
  const items = [
    ["SCORE", summary.score],
    ["K / D / A", `${summary.kills} / ${summary.deaths} / ${summary.assists}`],
    ["ADR", summary.adr],
    ["KAST", `${summary.kast_percent}%`],
    ["ROUNDS", summary.rounds],
  ];
  elements.metrics.innerHTML = items
    .map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
}

function renderResult(result) {
  elements.reportTitle.textContent = `${result.summary.player} · ${result.summary.map}`;
  elements.confidence.textContent = `置信度 ${result.confidence.toUpperCase()}`;
  renderMetrics(result.summary);
  elements.answer.textContent = result.answer;
  elements.evidenceList.innerHTML = "";
  result.evidence.slice(0, 4).forEach((item) => {
    const card = document.createElement("div");
    card.className = `evidence-card ${item.severity}`;
    const rounds = item.round_numbers.length
      ? item.round_numbers.map((number) => `R${number}`).join(" · ")
      : "全场统计";
    card.innerHTML = `<span class="tag">${item.severity.toUpperCase()}</span><p>${item.metric}</p><p class="rounds">${rounds}</p>`;
    elements.evidenceList.append(card);
  });
  elements.traceList.innerHTML = result.execution_trace
    .map((step) => `<li>${step}</li>`)
    .join("");
  setView("report");
}

async function analyze() {
  const matchId = elements.matchSelect.value;
  const question = elements.question.value.trim();
  if (!matchId || !question) return;
  elements.analyzeButton.disabled = true;
  setView("loading");
  let loadingIndex = 0;
  const timer = window.setInterval(() => {
    loadingIndex = (loadingIndex + 1) % loadingMessages.length;
    elements.loadingCopy.textContent = loadingMessages[loadingIndex];
  }, 650);
  try {
    const result = await api("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ match_id: matchId, question }),
    });
    renderResult(result);
  } catch (error) {
    elements.error.textContent = error.message;
    setView("error");
  } finally {
    window.clearInterval(timer);
    elements.loadingCopy.textContent = loadingMessages[0];
    elements.analyzeButton.disabled = false;
  }
}

elements.analyzeButton.addEventListener("click", analyze);
document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.question.value = button.dataset.question;
    elements.question.focus();
  });
});

elements.matchFile.addEventListener("change", async () => {
  const file = elements.matchFile.files[0];
  if (!file) return;
  try {
    if (file.name.toLowerCase().endsWith(".dem")) {
      pendingDemoJobId = null;
      fillPlayers([]);
      setUploadProgress(0);
      elements.uploadMessage.textContent = "正在上传 Demo…";
      const discovered = await waitForDemo(await uploadDemo(file), true);
      pendingDemoJobId = discovered.job_id;
      const options = discovered.player_options?.length
        ? discovered.player_options
        : (discovered.available_players || []).map((name) => ({ name, steamid: name }));
      fillPlayers(options);
      setUploadProgress(discovered.progress);
      elements.uploadMessage.textContent = `已找到 ${discovered.available_players.length} 名玩家，请选择复盘对象。`;
    } else if (file.name.toLowerCase().endsWith(".json")) {
      const form = new FormData();
      form.append("file", file);
      elements.uploadMessage.textContent = "正在校验 JSON…";
      const match = await api("/api/upload-json", { method: "POST", body: form });
      elements.uploadMessage.textContent = `已加载 ${match.map_name}，可以开始复盘。`;
      fillMatches(await api("/api/matches"), match.match_id);
    } else {
      throw new Error("只接受 .dem 或 .json 文件。");
    }
  } catch (error) {
    setUploadProgress(null);
    elements.uploadMessage.textContent = error.message;
  } finally {
    elements.matchFile.value = "";
  }
});

elements.playerSelect.addEventListener("change", async () => {
  const playerSteamid = elements.playerSelect.value;
  const playerName = elements.playerSelect.selectedOptions[0]?.dataset.playerName;
  if (!pendingDemoJobId || !playerName || !playerSteamid) return;
  elements.playerSelect.disabled = true;
  try {
    elements.uploadMessage.textContent = `正在解析 ${playerName} 的回合事件…`;
    const job = await api(`/api/demo-jobs/${pendingDemoJobId}/player`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        player_name: playerName,
        player_steamid: playerSteamid,
        question: elements.question.value.trim() || "请综合复盘这场比赛",
      }),
    });
    await finishDemo(await waitForDemo(job));
    pendingDemoJobId = null;
  } catch (error) {
    setUploadProgress(null);
    elements.uploadMessage.textContent = error.message;
    elements.playerSelect.disabled = false;
  }
});

async function initialize() {
  try {
    const matches = await api("/api/matches");
    fillMatches(matches, matches[0]?.match_id);
    if (matches.length) await analyze();
  } catch (error) {
    elements.error.textContent = error.message;
    setView("error");
  }
}

initialize();
