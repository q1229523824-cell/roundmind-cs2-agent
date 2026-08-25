import { env } from "cloudflare:workers";

export type DecisionAction =
  | "continue_contact"
  | "disengage_reset"
  | "wait_for_support"
  | "create_utility_condition";

export type StoredDecisionAnnotation = {
  scenario_ref: string;
  human_action: DecisionAction;
  agent_action: DecisionAction;
};

function database(): D1Database {
  if (!env.DB) throw new Error("D1 binding DB is unavailable");
  return env.DB;
}

export async function saveDecisionAnnotation(input: {
  playerRef: string;
  mapName: string;
  scenarioRef: string;
  observedOutcome: "kill" | "death" | "disengaged";
  agentAction: DecisionAction;
  humanAction: DecisionAction;
  reason: string;
}): Promise<void> {
  const timestamp = new Date().toISOString();
  await database().prepare(`
    INSERT INTO decision_annotations
      (player_ref, map_name, scenario_ref, observed_outcome, agent_action,
       human_action, reason, created_at, updated_at)
    VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?8)
    ON CONFLICT(player_ref, scenario_ref) DO UPDATE SET
      observed_outcome = excluded.observed_outcome,
      agent_action = excluded.agent_action,
      human_action = excluded.human_action,
      reason = excluded.reason,
      updated_at = excluded.updated_at
  `).bind(
    input.playerRef,
    input.mapName,
    input.scenarioRef,
    input.observedOutcome,
    input.agentAction,
    input.humanAction,
    input.reason,
    timestamp,
  ).run();
}

export async function loadDecisionAnnotations(
  playerRef: string,
  scenarioRefs: string[],
): Promise<StoredDecisionAnnotation[]> {
  if (!scenarioRefs.length) return [];
  const results = await database().batch<StoredDecisionAnnotation>(
    scenarioRefs.map((scenarioRef) => database().prepare(`
      SELECT scenario_ref, human_action, agent_action
      FROM decision_annotations
      WHERE player_ref = ?1 AND scenario_ref = ?2
      LIMIT 1
    `).bind(playerRef, scenarioRef)),
  );
  return results.flatMap((result) => result.results);
}

export async function decisionCalibrationSummary(mapName: string): Promise<{
  total: number;
  agreements: number;
  agreement_rate: number | null;
}> {
  const row = await database().prepare(`
    SELECT
      COUNT(*) AS total,
      COALESCE(SUM(CASE WHEN agent_action = human_action THEN 1 ELSE 0 END), 0)
        AS agreements
    FROM decision_annotations
    WHERE map_name = ?1
  `).bind(mapName).first<{ total: number; agreements: number }>();
  const total = Number(row?.total ?? 0);
  const agreements = Number(row?.agreements ?? 0);
  return {
    total,
    agreements,
    agreement_rate: total ? agreements / total : null,
  };
}
