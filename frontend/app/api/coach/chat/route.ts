import {
  appendCoachExchange,
  clearCoachHistory,
  loadCoachHistory,
} from "../../../../db/coach-sessions";

type CoachRequest = {
  playerSteamid?: string;
  mapName?: string;
  question?: string;
};

const SESSION_COOKIE = "roundmind_coach_session";

function cookieValue(request: Request, name: string): string | null {
  const cookies = request.headers.get("cookie") ?? "";
  for (const part of cookies.split(";")) {
    const [key, ...value] = part.trim().split("=");
    if (key === name) return decodeURIComponent(value.join("="));
  }
  return null;
}

function sessionId(request: Request): { value: string; created: boolean } {
  const existing = cookieValue(request, SESSION_COOKIE);
  if (existing && /^[a-f0-9-]{36}$/.test(existing)) {
    return { value: existing, created: false };
  }
  return { value: crypto.randomUUID(), created: true };
}

async function anonymousPlayerRef(steamid: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(steamid));
  const hex = [...new Uint8Array(digest)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
  return `player_${hex.slice(0, 12)}`;
}

function parseIdentity(payload: CoachRequest) {
  const playerSteamid = payload.playerSteamid?.trim() ?? "";
  const mapName = payload.mapName?.trim() ?? "";
  if (!playerSteamid || playerSteamid.length > 32) {
    throw new Error("缺少有效的玩家 SteamID");
  }
  if (!mapName || mapName.length > 80) throw new Error("缺少有效地图名称");
  return { playerSteamid, mapName };
}

function parsePayload(payload: CoachRequest) {
  const identity = parseIdentity(payload);
  const question = payload.question?.trim() ?? "";
  if (!question || question.length > 1000) throw new Error("问题应为 1–1000 个字符");
  return { ...identity, question };
}

function withSessionCookie(response: Response, request: Request, id: string) {
  const secure = new URL(request.url).protocol === "https:" ? "; Secure" : "";
  response.headers.append(
    "Set-Cookie",
    `${SESSION_COOKIE}=${encodeURIComponent(id)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000${secure}`,
  );
  return response;
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const payload = parseIdentity({
      playerSteamid: url.searchParams.get("playerSteamid") ?? undefined,
      mapName: url.searchParams.get("mapName") ?? undefined,
    });
    const session = sessionId(request);
    const playerRef = await anonymousPlayerRef(payload.playerSteamid);
    const messages = await loadCoachHistory(session.value, playerRef, payload.mapName);
    return withSessionCookie(
      Response.json({ messages, remembered_turns: Math.floor(messages.length / 2) }),
      request,
      session.value,
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "无法读取历史会话";
    return Response.json({ error: message }, { status: 400 });
  }
}

export async function POST(request: Request) {
  try {
    const payload = parsePayload((await request.json()) as CoachRequest);
    const backendUrl = (process.env.ROUNDMIND_API_URL ?? "").replace(/\/$/, "");
    if (!backendUrl) {
      return Response.json({ error: "教练后端尚未连接" }, { status: 503 });
    }
    const session = sessionId(request);
    const playerRef = await anonymousPlayerRef(payload.playerSteamid);
    const history = await loadCoachHistory(session.value, playerRef, payload.mapName);
    const authorization = request.headers.get("authorization");
    const backendResponse = await fetch(`${backendUrl}/api/coach/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(authorization ? { Authorization: authorization } : {}),
      },
      body: JSON.stringify({
        player_steamid: payload.playerSteamid,
        map_name: payload.mapName,
        question: payload.question,
        conversation_history: history,
      }),
      signal: AbortSignal.timeout(45_000),
    });
    const result = await backendResponse.json() as { answer?: string; detail?: string };
    if (!backendResponse.ok || !result.answer) {
      return Response.json(
        { error: result.detail ?? "教练暂时无法回答" },
        { status: backendResponse.status || 502 },
      );
    }
    await appendCoachExchange(
      session.value,
      playerRef,
      payload.mapName,
      payload.question,
      result.answer,
    );
    return withSessionCookie(
      Response.json({ ...result, remembered_turns: Math.min(6, history.length / 2 + 1) }),
      request,
      session.value,
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "教练请求失败";
    return Response.json({ error: message }, { status: 400 });
  }
}

export async function DELETE(request: Request) {
  try {
    const payload = parseIdentity((await request.json()) as CoachRequest);
    const session = sessionId(request);
    const playerRef = await anonymousPlayerRef(payload.playerSteamid);
    await clearCoachHistory(session.value, playerRef, payload.mapName);
    return withSessionCookie(
      Response.json({ status: "cleared" }),
      request,
      session.value,
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "无法清空会话";
    return Response.json({ error: message }, { status: 400 });
  }
}
