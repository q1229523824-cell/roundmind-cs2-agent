import {
  decisionCalibrationSummary,
  type DecisionAction,
  loadDecisionAnnotations,
  saveDecisionAnnotation,
} from "../../../db/decision-annotations";

const ACTIONS = new Set<DecisionAction>([
  "continue_contact",
  "disengage_reset",
  "wait_for_support",
  "create_utility_condition",
]);
const OUTCOMES = new Set(["kill", "death", "disengaged"]);

type AnnotationRequest = {
  playerSteamid?: string;
  mapName?: string;
  cardKey?: string;
  cardKeys?: string[];
  observedOutcome?: string;
  agentAction?: string;
  humanAction?: string;
  reason?: string;
};

async function digest(value: string): Promise<string> {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(bytes)]
    .map((item) => item.toString(16).padStart(2, "0"))
    .join("");
}

async function playerRef(steamid: string): Promise<string> {
  return `player_${(await digest(steamid)).slice(0, 12)}`;
}

async function scenarioRef(player: string, key: string): Promise<string> {
  return `scenario_${(await digest(`${player}:${key}`)).slice(0, 20)}`;
}

function identity(payload: AnnotationRequest) {
  const playerSteamid = payload.playerSteamid?.trim() ?? "";
  const mapName = payload.mapName?.trim() ?? "";
  if (!playerSteamid || playerSteamid.length > 32) throw new Error("缺少有效玩家身份");
  if (!mapName || mapName.length > 80) throw new Error("缺少有效地图名称");
  return { playerSteamid, mapName };
}

function action(value: string | undefined, field: string): DecisionAction {
  if (!value || !ACTIONS.has(value as DecisionAction)) throw new Error(`${field} 无效`);
  return value as DecisionAction;
}

export async function PUT(request: Request) {
  try {
    const payload = (await request.json()) as AnnotationRequest;
    const parsed = identity(payload);
    const keys = (payload.cardKeys ?? []).filter(
      (item): item is string => typeof item === "string" && item.length > 0 && item.length <= 180,
    ).slice(0, 12);
    const player = await playerRef(parsed.playerSteamid);
    const refs = await Promise.all(keys.map((key) => scenarioRef(player, key)));
    const rows = await loadDecisionAnnotations(player, refs);
    const labels = Object.fromEntries(rows.map((row) => [row.scenario_ref, row.human_action]));
    const selections: Record<string, DecisionAction> = {};
    refs.forEach((ref, index) => {
      if (labels[ref]) selections[keys[index]] = labels[ref];
    });
    return Response.json({ selections, summary: await decisionCalibrationSummary(parsed.mapName) });
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "无法读取标注" },
      { status: 400 },
    );
  }
}

export async function POST(request: Request) {
  try {
    const payload = (await request.json()) as AnnotationRequest;
    const parsed = identity(payload);
    const cardKey = payload.cardKey?.trim() ?? "";
    if (!cardKey || cardKey.length > 180) throw new Error("决策卡编号无效");
    if (!OUTCOMES.has(payload.observedOutcome ?? "")) throw new Error("交火结果无效");
    const agentAction = action(payload.agentAction, "Agent 动作");
    const humanAction = action(payload.humanAction, "人工动作");
    const reason = payload.reason?.trim() ?? "";
    if (reason.length > 300) throw new Error("标注原因不能超过 300 字");
    const player = await playerRef(parsed.playerSteamid);
    await saveDecisionAnnotation({
      playerRef: player,
      mapName: parsed.mapName,
      scenarioRef: await scenarioRef(player, cardKey),
      observedOutcome: payload.observedOutcome as "kill" | "death" | "disengaged",
      agentAction,
      humanAction,
      reason,
    });
    return Response.json({
      saved: true,
      summary: await decisionCalibrationSummary(parsed.mapName),
    });
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "无法保存标注" },
      { status: 400 },
    );
  }
}
