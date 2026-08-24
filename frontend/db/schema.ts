import { index, integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

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
