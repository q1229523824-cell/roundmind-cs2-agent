import { env } from "cloudflare:workers";

export type CoachHistoryMessage = {
  role: "user" | "assistant";
  content: string;
};

const MAX_HISTORY_MESSAGES = 12;
const MAX_HISTORY_CHARS = 18_000;

function database(): D1Database {
  if (!env.DB) throw new Error("D1 binding DB is unavailable");
  return env.DB;
}

export async function loadCoachHistory(
  sessionId: string,
  playerRef: string,
  mapName: string,
): Promise<CoachHistoryMessage[]> {
  const result = await database()
    .prepare(`
      SELECT role, content
      FROM coach_messages
      WHERE session_id = ?1 AND player_ref = ?2 AND map_name = ?3
      ORDER BY id DESC
      LIMIT ?4
    `)
    .bind(sessionId, playerRef, mapName, MAX_HISTORY_MESSAGES)
    .all<CoachHistoryMessage>();
  const ordered = result.results.reverse();
  const selected: CoachHistoryMessage[] = [];
  let usedCharacters = 0;
  for (const message of [...ordered].reverse()) {
    if (selected.length && usedCharacters + message.content.length > MAX_HISTORY_CHARS) break;
    selected.push(message);
    usedCharacters += message.content.length;
  }
  return selected.reverse();
}

export async function appendCoachExchange(
  sessionId: string,
  playerRef: string,
  mapName: string,
  question: string,
  answer: string,
): Promise<void> {
  const db = database();
  const createdAt = new Date().toISOString();
  await db.batch([
    db.prepare(`
      INSERT INTO coach_messages
        (session_id, player_ref, map_name, role, content, created_at)
      VALUES (?1, ?2, ?3, 'user', ?4, ?5)
    `).bind(sessionId, playerRef, mapName, question, createdAt),
    db.prepare(`
      INSERT INTO coach_messages
        (session_id, player_ref, map_name, role, content, created_at)
      VALUES (?1, ?2, ?3, 'assistant', ?4, ?5)
    `).bind(sessionId, playerRef, mapName, answer, createdAt),
  ]);
  await db.prepare(`
    DELETE FROM coach_messages
    WHERE session_id = ?1 AND player_ref = ?2 AND map_name = ?3
      AND id NOT IN (
        SELECT id FROM coach_messages
        WHERE session_id = ?1 AND player_ref = ?2 AND map_name = ?3
        ORDER BY id DESC LIMIT ?4
      )
  `).bind(sessionId, playerRef, mapName, MAX_HISTORY_MESSAGES).run();
}

export async function clearCoachHistory(
  sessionId: string,
  playerRef: string,
  mapName: string,
): Promise<void> {
  await database()
    .prepare(`
      DELETE FROM coach_messages
      WHERE session_id = ?1 AND player_ref = ?2 AND map_name = ?3
    `)
    .bind(sessionId, playerRef, mapName)
    .run();
}
