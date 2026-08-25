CREATE TABLE `decision_annotations` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`player_ref` text NOT NULL,
	`map_name` text NOT NULL,
	`scenario_ref` text NOT NULL,
	`observed_outcome` text NOT NULL,
	`agent_action` text NOT NULL,
	`human_action` text NOT NULL,
	`reason` text DEFAULT '' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `decision_annotations_player_scenario_idx` ON `decision_annotations` (`player_ref`,`scenario_ref`);--> statement-breakpoint
CREATE INDEX `decision_annotations_map_idx` ON `decision_annotations` (`map_name`,`id`);