from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from canbusd import profile_replay
from ui import config_cli, vehicle_capture_analysis


class VehicleCaptureAnalysisTests(unittest.TestCase):
    def write_capture(self, root: Path, name: str, text: str) -> Path:
        path = root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_normalize_accepts_candump_log_and_bracket_formats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.write_capture(
                root,
                "capture.log",
                """# comment
(1700000000.000001) can0 123#0011AA
(1700000000.002001) can1 00000123 [3] 00 22 BB
""",
            )

            report = vehicle_capture_analysis.normalize_capture(path)

            self.assertEqual(report["capture_id"], "open-mmi.vehicle-capture")
            self.assertEqual(report["summary"]["selected_frames"], 2)
            self.assertEqual(report["frames"][0]["timestamp_ns"], 1700000000000001000)
            self.assertEqual(report["frames"][1]["relative_us"], 2000)
            self.assertEqual(report["frames"][0]["id"], "0x123")
            self.assertEqual(report["frames"][0]["data"], "00 11 AA")
            self.assertEqual(report["source"]["name"], "capture.log")
            self.assertNotIn(str(root), json.dumps(report))

    def test_normalize_filters_bus_identifier_and_time_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.write_capture(
                root,
                "capture.log",
                """(1.000000) can0 100#00
(1.005000) can0 123#01
(1.010000) can1 123#02
""",
            )

            report = vehicle_capture_analysis.normalize_capture(
                path,
                buses=["can0"],
                can_ids=["0x123"],
                start_ms=4,
                end_ms=6,
            )

            self.assertEqual(report["summary"]["selected_frames"], 1)
            self.assertEqual(report["frames"][0]["data"], "01")

    def test_time_filter_requires_timestamped_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_capture(Path(tmp), "capture.log", "can0 123#00\n")
            with self.assertRaisesRegex(
                vehicle_capture_analysis.VehicleCaptureAnalysisError,
                "requires timestamps",
            ):
                vehicle_capture_analysis.normalize_capture(path, start_ms=0)

    def test_invalid_dlc_and_can_fd_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mismatch = self.write_capture(root, "mismatch.log", "can0 123 [2] 00\n")
            with self.assertRaisesRegex(
                vehicle_capture_analysis.VehicleCaptureAnalysisError,
                "declared DLC",
            ):
                vehicle_capture_analysis.normalize_capture(mismatch)

            can_fd = self.write_capture(root, "fd.log", "(1.0) can0 123##100\n")
            with self.assertRaisesRegex(
                vehicle_capture_analysis.VehicleCaptureAnalysisError,
                "CAN FD",
            ):
                vehicle_capture_analysis.normalize_capture(can_fd)

    def test_compare_reports_changed_bytes_and_bit_ratios(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = self.write_capture(
                root,
                "before.log",
                """(1.0) can0 123#0000
(1.1) can0 123#0000
(1.2) can0 456#AA
""",
            )
            after = self.write_capture(
                root,
                "after.log",
                """(2.0) can0 123#0100
(2.1) can0 123#0100
(2.2) can0 456#AA
""",
            )

            report = vehicle_capture_analysis.compare_captures(before, after)

            self.assertEqual(report["summary"]["changed_ids"], 1)
            change = report["changes"][0]
            self.assertEqual(change["id"], "0x123")
            self.assertEqual(change["representative_before"], "00 00")
            self.assertEqual(change["representative_after"], "01 00")
            self.assertEqual(change["changed_bytes"][0]["index"], 0)
            self.assertEqual(change["changed_bytes"][0]["score"], 1.0)
            self.assertEqual(
                change["changed_bytes"][0]["bit_deltas"],
                [
                    {
                        "bit": 0,
                        "before_one_ratio": 0.0,
                        "after_one_ratio": 1.0,
                        "delta": 1.0,
                    }
                ],
            )

    def test_compare_detects_identifiers_only_present_after_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = self.write_capture(root, "before.log", "can0 100#00\n")
            after = self.write_capture(root, "after.log", "can0 100#00\ncan0 321#AA\n")

            report = vehicle_capture_analysis.compare_captures(before, after)

            self.assertEqual(report["summary"]["changed_ids"], 1)
            self.assertEqual(report["changes"][0]["id"], "0x321")
            self.assertIsNone(report["changes"][0]["representative_before"])
            self.assertEqual(report["changes"][0]["representative_after"], "AA")

    def test_candidate_export_is_experimental_and_research_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "vehicles").mkdir()
            before = self.write_capture(root, "before.log", "can0 123#00\n")
            after = self.write_capture(root, "after.log", "can0 123#01\n")
            comparison = vehicle_capture_analysis.compare_captures(before, after)
            output = root / "candidate.json"

            result = vehicle_capture_analysis.export_candidate_fixture(
                comparison,
                output,
                profile_id="example-profile",
                root=root,
                fixture_bus="comfort",
            )
            document = json.loads(output.read_text(encoding="utf-8"))

            self.assertTrue(result["experimental"])
            self.assertTrue(document["review_required"])
            self.assertEqual(document["profile_id"], "example-profile")
            self.assertEqual(document["cases"][0]["bus"], "comfort")
            self.assertEqual(document["cases"][0]["expect"], {"events": [], "statuses": {}})
            self.assertTrue(document["cases"][0]["analysis"]["review_required"])

            empty_profile = {
                "metadata": {"id": "example-profile"},
                "default_bus": "comfort",
                "rules": [],
                "presence": [],
                "status": [],
            }
            replay = profile_replay.replay_fixture(
                empty_profile,
                document,
                expected_profile_id="example-profile",
            )
            self.assertTrue(replay["valid"], replay)

    def test_generated_outputs_cannot_enter_maintained_tree_or_overwrite_silently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vehicles = root / "vehicles"
            vehicles.mkdir()
            report = {"ok": True}

            with self.assertRaisesRegex(
                vehicle_capture_analysis.VehicleCaptureAnalysisError,
                "outside vehicles",
            ):
                vehicle_capture_analysis.write_json_report(
                    report,
                    vehicles / "capture.json",
                    root=root,
                )

            output = root / "report.json"
            vehicle_capture_analysis.write_json_report(report, output, root=root)
            with self.assertRaisesRegex(
                vehicle_capture_analysis.VehicleCaptureAnalysisError,
                "already exists",
            ):
                vehicle_capture_analysis.write_json_report(report, output, root=root)

            vehicle_capture_analysis.write_json_report(
                {"ok": False},
                output,
                root=root,
                force=True,
            )
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"ok": False})
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o644)

    def test_cli_compare_returns_machine_readable_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = self.write_capture(root, "before.log", "can0 123#00\n")
            after = self.write_capture(root, "after.log", "can0 123#01\n")
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                result = config_cli.main(
                    [
                        "vehicle-setup",
                        "capture",
                        "compare",
                        str(before),
                        str(after),
                    ]
                )

            report = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(report["analysis_id"], "open-mmi.vehicle-capture-comparison")
            self.assertEqual(report["summary"]["changed_ids"], 1)


if __name__ == "__main__":
    unittest.main()
