CREATE TABLE `coach_messages` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`session_id` text NOT NULL,
	`player_ref` text NOT NULL,
	`map_name` text NOT NULL,
	`role` text NOT NULL,
	`content` text NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `coach_messages_session_idx` ON `coach_messages` (`session_id`,`player_ref`,`map_name`,`id`);