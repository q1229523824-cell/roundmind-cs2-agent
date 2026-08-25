import { index, integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const coachMessages = sqliteTable("coach_messages", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  sessionId: text("session_id").notNull(),
  playerRef: text("player_ref").notNull(),
  mapName: text("map_name").notNull(),
  role: text("role", { enum: ["user", "assistant"] }).notNull(),
  content: text("content").notNull(),
  createdAt: text("created_at").notNull(),
}, (table) => [
  index("coach_messages_session_idx").on(
    table.sessionId,
    table.playerRef,
    table.mapName,
    table.id,
  ),
]);

export const decisionAnnotations = sqliteTable("decision_annotations", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  playerRef: text("player_ref").notNull(),
  mapName: text("map_name").notNull(),
  scenarioRef: text("scenario_ref").notNull(),
  observedOutcome: text("observed_outcome", {
    enum: ["kill", "death", "disengaged"],
  }).notNull(),
  agentAction: text("agent_action").notNull(),
  humanAction: text("human_action").notNull(),
  reason: text("reason").notNull().default(""),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
}, (table) => [
  uniqueIndex("decision_annotations_player_scenario_idx").on(
    table.playerRef,
    table.scenarioRef,
  ),
  index("decision_annotations_map_idx").on(table.mapName, table.id),
]);
