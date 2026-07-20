import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from canbusd import status_bus
from canbusd.status_bus import StatusBus


class StatusBusTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "runtime" / "status.json"
        self.bus = StatusBus(self.path, clock=lambda: 1234.5)

    def test_publish_deep_merges_and_writes_atomic_snapshot(self):
        self.bus.publish({"vehicle": {"present": True, "speed_kmh": 10}})
        snapshot = self.bus.publish({"vehicle": {"speed_kmh": 12}, "doors": {"boot": False}})

        self.assertEqual(
            snapshot,
            {
                "vehicle": {"present": True, "speed_kmh": 12},
                "doors": {"boot": False},
            },
        )
        payload = json.loads(self.path.read_text())
        self.assertEqual(payload["updated_at"], 1234.5)
        self.assertEqual(payload["state"], snapshot)
        self.assertEqual(list(self.path.parent.glob(".status.json.*.tmp")), [])

    def test_publish_replaces_a_damaged_existing_snapshot(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not valid json")

        self.bus.publish({"vehicle": {"present": False}})

        payload = json.loads(self.path.read_text())
        self.assertEqual(payload["state"], {"vehicle": {"present": False}})

    def test_runtime_evidence_is_separate_from_decoded_state_and_persists(self):
        runtime = {
            "api_version": 1,
            "state": "ready",
            "errors": [],
            "vehicle": {
                "source": "maintained",
                "id": "seat_1p",
                "revision": "sha256:" + "a" * 64,
            },
            "bindings": {
                "source": "maintained",
                "id": "default",
                "revision": "sha256:" + "b" * 64,
            },
            "active_bus": "comfort",
            "interface": "can0",
        }

        returned = self.bus.publish_runtime(runtime)
        runtime["interface"] = "can9"
        returned["interface"] = "can8"
        self.bus.publish({"vehicle": {"speed_kmh": 12}})

        payload = json.loads(self.path.read_text())
        self.assertEqual(payload["runtime"]["interface"], "can0")
        self.assertEqual(payload["state"], {"vehicle": {"speed_kmh": 12}})
        self.assertEqual(self.bus.runtime_snapshot()["interface"], "can0")

        self.bus.reset(persist=True)
        payload = json.loads(self.path.read_text())
        self.assertEqual(payload["state"], {})
        self.assertEqual(payload["runtime"]["interface"], "can0")

    def test_snapshots_and_subscribers_cannot_mutate_internal_state(self):
        update = {"vehicle": {"speed_kmh": 20}}
        received = []

        def mutate(snapshot):
            received.append(snapshot)
            snapshot["vehicle"]["speed_kmh"] = 999

        self.bus.subscribe(mutate)
        returned = self.bus.publish(update)
        update["vehicle"]["speed_kmh"] = 40
        returned["vehicle"]["speed_kmh"] = 50

        self.assertEqual(received[0]["vehicle"]["speed_kmh"], 999)
        self.assertEqual(self.bus.snapshot()["vehicle"]["speed_kmh"], 20)

        external = self.bus.snapshot()
        external["vehicle"]["speed_kmh"] = 60
        self.assertEqual(self.bus.snapshot()["vehicle"]["speed_kmh"], 20)

    def test_subscriber_failure_is_logged_and_isolated(self):
        received = []

        def broken(_snapshot):
            raise RuntimeError("subscriber failed")

        self.bus.subscribe(broken)
        self.bus.subscribe(received.append)

        with self.assertLogs("canbusd.status_bus", level="ERROR") as logs:
            self.bus.publish({"vehicle": {"present": True}})

        self.assertEqual(received, [{"vehicle": {"present": True}}])
        self.assertIn("Status subscriber failed", "\n".join(logs.output))

    def test_persistence_failure_does_not_drop_in_memory_or_subscriber_update(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"updated_at": 1, "state": {"old": true}}\n')
        received = []
        self.bus.subscribe(received.append)

        with (
            mock.patch("canbusd.status_bus.os.replace", side_effect=OSError("read only")),
            self.assertLogs("canbusd.status_bus", level="ERROR") as logs,
        ):
            result = self.bus.publish({"vehicle": {"present": True}})

        self.assertEqual(result, {"vehicle": {"present": True}})
        self.assertEqual(self.bus.snapshot(), result)
        self.assertEqual(received, [result])
        self.assertIn("Failed to persist status snapshot", "\n".join(logs.output))
        self.assertEqual(json.loads(self.path.read_text())["state"], {"old": True})
        self.assertEqual(list(self.path.parent.glob(".status.json.*.tmp")), [])

    def test_reset_clears_memory_but_keeps_last_snapshot_for_stale_consumers(self):
        self.bus.publish({"vehicle": {"present": True}})
        before = self.path.read_text()

        self.bus.reset()

        self.assertEqual(self.bus.snapshot(), {})
        self.assertEqual(self.path.read_text(), before)

    def test_persisted_reset_replaces_old_profile_state_and_notifies(self):
        received = []
        self.bus.subscribe(received.append)
        self.bus.publish({"legacy_profile": {"field": True}})

        self.bus.reset(persist=True, notify=True)

        self.assertEqual(self.bus.snapshot(), {})
        self.assertEqual(json.loads(self.path.read_text())["state"], {})
        self.assertEqual(received[-1], {})

    def test_unsubscribe_reports_membership(self):
        subscriber = lambda _snapshot: None
        self.bus.subscribe(subscriber)
        self.assertTrue(self.bus.unsubscribe(subscriber))
        self.assertFalse(self.bus.unsubscribe(subscriber))

    def test_reset_isolates_subscriber_and_persistence_failures(self):
        def broken(_snapshot):
            raise RuntimeError("reset subscriber failed")

        self.bus.publish({"vehicle": {"present": True}})
        self.bus.subscribe(broken)
        with (
            mock.patch.object(self.bus, "_write_status_file", side_effect=OSError("read only")),
            self.assertLogs("canbusd.status_bus", level="ERROR") as logs,
        ):
            self.bus.reset(persist=True, notify=True)

        output = "\n".join(logs.output)
        self.assertIn("Failed to persist cleared status snapshot", output)
        self.assertIn("Status subscriber failed during reset", output)
        self.assertEqual(self.bus.snapshot(), {})

    def test_default_path_and_module_api_remain_configurable(self):
        with mock.patch.dict(status_bus.os.environ, {"XDG_RUNTIME_DIR": "/run/user/123"}, clear=True):
            self.assertEqual(
                status_bus._default_status_path(),
                Path("/run/user/123/open-mmi/status.json"),
            )
        with mock.patch.dict(status_bus.os.environ, {}, clear=True):
            self.assertEqual(status_bus._default_status_path(), Path("/tmp/open-mmi-status.json"))

        replacement = StatusBus(self.path, clock=lambda: 2.0)
        with (
            mock.patch.object(status_bus, "_default_bus", replacement),
            mock.patch.object(status_bus, "STATUS_PATH", self.path),
        ):
            received = []
            status_bus.subscribe(received.append)
            status_bus.publish({"vehicle": {"present": True}})
            status_bus.publish_runtime({"state": "ready"})
            self.assertEqual(status_bus.snapshot(), {"vehicle": {"present": True}})
            self.assertEqual(status_bus.runtime_snapshot(), {"state": "ready"})
            self.assertTrue(status_bus.unsubscribe(received.append))
            status_bus.reset(persist=True)
            status_bus._write_status_file({"manual": True})

        self.assertEqual(json.loads(self.path.read_text())["state"], {"manual": True})
        self.assertEqual(json.loads(self.path.read_text())["runtime"], {"state": "ready"})

    def test_directory_fsync_is_best_effort(self):
        with mock.patch("canbusd.status_bus.os.open", side_effect=OSError("unsupported")):
            self.bus._fsync_parent_directory()

    def test_publish_rejects_non_mapping_updates(self):
        with self.assertRaisesRegex(TypeError, "dictionary"):
            self.bus.publish([])  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "dictionary"):
            self.bus.publish_runtime([])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
