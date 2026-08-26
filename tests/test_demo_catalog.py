from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from chapter07_cs2_coach.demo_catalog import (
    DemoInspection,
    build_demo_catalog,
    infer_source,
    write_catalog_csv,
    write_catalog_json,
)
from chapter07_cs2_coach.demo_parser import DemoParseError
from chapter07_cs2_coach.models import DemoPlayerOption


class DemoCatalogTests(unittest.TestCase):
    def test_builds_catalog_and_deduplicates_by_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "first.dem").write_bytes(b"same-demo")
            nested = root / "nested"
            nested.mkdir()
            (nested / "copy.dem").write_bytes(b"same-demo")

            def inspect(_: Path) -> DemoInspection:
                return DemoInspection(
                    header={
                        "map_name": "de_dust2",
                        "server_name": "FACEIT Server",
                        "client_name": "SourceTV Demo",
                        "demo_version_name": "valve_demo_2",
                        "patch_version": "14175",
                    },
                    players=[DemoPlayerOption(name="Learner", steamid="7656119")],
                )

            catalog = build_demo_catalog(root, inspector=inspect)

            self.assertEqual(catalog.stats.files, 2)
            self.assertEqual(catalog.stats.unique_files, 1)
            self.assertEqual(catalog.stats.duplicates, 1)
            first, duplicate = catalog.entries
            self.assertEqual(first.status, "metadata_ready")
            self.assertEqual(first.map_name, "de_dust2")
            self.assertEqual(first.source, "FACEIT")
            self.assertEqual(first.source_confidence, "high")
            self.assertEqual(first.patch_version, "14175")
            self.assertEqual(first.demo_type, "server_demo")
            self.assertEqual(duplicate.status, "duplicate")
            self.assertEqual(duplicate.duplicate_of, "first.dem")
            self.assertEqual(duplicate.demo_id, first.demo_id)
            self.assertIsNone(first.match_date)

    def test_records_controlled_failure_without_path_details(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "broken.dem").write_bytes(b"broken")

            def fail(_: Path) -> DemoInspection:
                raise DemoParseError("secret absolute path")

            catalog = build_demo_catalog(root, inspector=fail)

            self.assertEqual(catalog.stats.failed, 1)
            self.assertEqual(catalog.entries[0].status, "failed")
            self.assertNotIn("secret", catalog.entries[0].error or "")

    def test_writes_json_and_excel_friendly_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "match.dem").write_bytes(b"demo")
            inspection = DemoInspection(
                header={"map_name": "de_mirage", "client_name": "SourceTV Demo"},
                players=[DemoPlayerOption(name="玩家一", steamid="123")],
            )
            catalog = build_demo_catalog(root, inspector=lambda _: inspection)
            json_path = root / "out" / "catalog.json"
            csv_path = root / "out" / "catalog.csv"

            write_catalog_json(catalog, json_path)
            write_catalog_csv(catalog, csv_path)

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["entries"][0]["player_count"], 1)
            with csv_path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["players"], "玩家一")
            self.assertEqual(rows[0]["map_name"], "de_mirage")

    def test_source_inference_does_not_guess_unknown_source(self) -> None:
        source, confidence, evidence = infer_source(
            file_name="match_001.dem",
            server_name="Counter-Strike 2",
            client_name="SourceTV Demo",
        )
        self.assertEqual((source, confidence, evidence), ("unknown", "unknown", None))


if __name__ == "__main__":
    unittest.main()
