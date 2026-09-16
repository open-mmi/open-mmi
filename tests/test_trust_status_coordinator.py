from __future__ import annotations

import inspect
import json
import socket
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from open_mmi_trust.inspector import FAIL, PASS, UNVERIFIED
from ui import trust_status_coordinator as coordinator


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ui" / "trust_status_coordinator.py"
UNIT = ROOT / "systemd" / "system" / "open-mmi-trust-status.service"


class FakeClientSocket:
    def __init__(self, chunks=(), *, connect_error=None, recv_error=None):
        self.chunks = list(chunks)
        self.connect_error = connect_error
        self.recv_error = recv_error
        self.sent = b""
        self.closed = False

    def settimeout(self, _timeout):
        return None

    def connect(self, _path):
        if self.connect_error is not None:
            raise self.connect_error

    def sendall(self, data):
        self.sent += data

    def recv(self, size):
        if self.recv_error is not None:
            error = self.recv_error
            self.recv_error = None
            raise error
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        if len(chunk) > size:
            self.chunks.insert(0, chunk[size:])
            return chunk[:size]
        return chunk

    def close(self):
        self.closed = True


class TrustStatusCoordinatorTests(unittest.TestCase):
    def test_exact_status_request_returns_privileged_inspector_report(self) -> None:
        for status in (PASS, FAIL, UNVERIFIED):
            with self.subTest(status=status):
                report = {"status": status, "checks": [], "manifest": {"available": True}}
                response = coordinator.response_for_request(
                    {"api_version": 1, "action": "status"},
                    inspector=lambda report=report: report,
                )
                self.assertTrue(response["ok"])
                self.assertEqual(response["status"], status)
                self.assertEqual(response["report"], report)
                self.assertIsNone(response["error"])

    def test_schema_is_fixed_and_has_no_mutation_action(self) -> None:
        calls = 0

        def inspector():
            nonlocal calls
            calls += 1
            return {"status": PASS, "checks": []}

        invalid = (
            None,
            {},
            {"api_version": 1, "action": "status", "path": "/var/lib/open-mmi/trust"},
            {"api_version": 1, "action": "acknowledge"},
            {"api_version": 1, "action": "bootstrap"},
            {"api_version": 2, "action": "status"},
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                response = coordinator.response_for_request(payload, inspector=inspector)
                self.assertFalse(response["ok"])
        self.assertEqual(calls, 0)

    def test_inspector_failure_is_sanitized_and_unverified(self) -> None:
        def broken():
            raise RuntimeError("/private/root/path must not leak")

        response = coordinator.response_for_request(
            {"api_version": 1, "action": "status"},
            inspector=broken,
        )
        self.assertFalse(response["ok"])
        self.assertEqual(response["status"], UNVERIFIED)
        self.assertIsNone(response["report"])
        self.assertNotIn("/private/root/path", response["error"])

    def test_local_socket_client_round_trip(self) -> None:
        with TemporaryDirectory() as temporary:
            socket_path = Path(temporary) / "trust-status.sock"
            report = {"status": PASS, "checks": [], "manifest": {"available": True}}
            with coordinator.TrustStatusServer(
                socket_path,
                inspector=lambda: report,
            ) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    response = coordinator.client_status(socket_path)
                finally:
                    server.shutdown()
                    thread.join(timeout=5)
            self.assertTrue(response["ok"])
            self.assertEqual(response["report"], report)

    def test_socket_service_reads_fixture_store_without_exposing_path_control(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            socket_path = root / "trust-status.sock"
            store_path = root / "owner-state.json"
            report = {
                "status": PASS,
                "checks": [],
                "manifest": {"available": True, "digest": "sha256:fixture"},
            }
            store_path.write_text(json.dumps(report), encoding="utf-8")
            store_path.chmod(0o600)

            def inspector():
                return json.loads(store_path.read_text(encoding="utf-8"))

            with coordinator.TrustStatusServer(socket_path, inspector=inspector) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    response = coordinator.client_status(socket_path)
                finally:
                    server.shutdown()
                    thread.join(timeout=5)

            self.assertTrue(response["ok"])
            self.assertEqual(response["report"], report)
            self.assertNotIn(str(store_path), json.dumps(response))

            rejected = coordinator.response_for_request(
                {
                    "api_version": 1,
                    "action": "status",
                    "path": str(store_path),
                },
                inspector=inspector,
            )
            self.assertFalse(rejected["ok"])

    def test_server_rejects_duplicate_json_fields_before_inspection(self) -> None:
        with TemporaryDirectory() as temporary:
            socket_path = Path(temporary) / "trust-status.sock"
            inspector = mock.Mock(return_value={"status": PASS, "checks": []})
            with coordinator.TrustStatusServer(socket_path, inspector=inspector) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.settimeout(2)
                try:
                    client.connect(str(socket_path))
                    client.sendall(
                        b'{"api_version":1,"api_version":1,"action":"status"}\n'
                    )
                    raw = b""
                    while b"\n" not in raw:
                        raw += client.recv(4096)
                finally:
                    client.close()
                    server.shutdown()
                    thread.join(timeout=5)

            response = json.loads(raw.split(b"\n", 1)[0].decode("utf-8"))
            self.assertFalse(response["ok"])
            inspector.assert_not_called()

    def test_client_rejects_malformed_truncated_and_duplicate_responses(self) -> None:
        invalid_responses = (
            b'{"ok":true,"ok":false}\n',
            b'{"ok":}\n',
            b'{"ok":true}',
            b'{"ok":true}\n{"second":true}\n',
        )
        for raw in invalid_responses:
            with self.subTest(raw=raw):
                fake = FakeClientSocket((raw,))
                with mock.patch.object(coordinator.socket, "socket", return_value=fake):
                    with self.assertRaises(coordinator.TrustStatusCoordinatorError):
                        coordinator.client_status(Path("/tmp/fake-trust-status.sock"))
                self.assertTrue(fake.closed)

    def test_client_rejects_oversized_response(self) -> None:
        fake = FakeClientSocket((b"x" * 17,))
        with (
            mock.patch.object(coordinator, "MAX_RESPONSE_BYTES", 16),
            mock.patch.object(coordinator.socket, "socket", return_value=fake),
        ):
            with self.assertRaises(coordinator.TrustStatusCoordinatorError):
                coordinator.client_status(Path("/tmp/fake-trust-status.sock"))
        self.assertTrue(fake.closed)

    def test_client_timeout_allows_complete_local_inspection_window(self) -> None:
        self.assertGreaterEqual(coordinator.DEFAULT_TIMEOUT_SECONDS, 10.0)

    def test_client_transport_failures_are_unavailable(self) -> None:
        cases = (
            FakeClientSocket(connect_error=FileNotFoundError("missing socket")),
            FakeClientSocket(connect_error=PermissionError("denied socket")),
            FakeClientSocket(recv_error=TimeoutError("timed out")),
        )
        for fake in cases:
            with self.subTest(error=type(fake.connect_error or fake.recv_error).__name__):
                with mock.patch.object(coordinator.socket, "socket", return_value=fake):
                    with self.assertRaises(coordinator.TrustStatusUnavailableError):
                        coordinator.client_status(Path("/tmp/fake-trust-status.sock"))
                self.assertTrue(fake.closed)

    def test_source_imports_inspector_but_no_trust_mutation_primitive(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("inspect_system", source)
        for forbidden in (
            "_record_accepted_manifest",
            "_record_lineage_baseline",
            "_record_state_transition",
            "_record_integrity_state",
            "_write_provenance_root",
            "_authorize_prepared_expansion",
            "activate_acknowledged_expansion",
            "_create_authorization",
            "_revoke_authorization",
            "subprocess",
            "urllib",
            "requests",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_systemd_unit_is_root_read_only_and_network_denied(self) -> None:
        unit = UNIT.read_text(encoding="utf-8")
        for required in (
            "User=root",
            "Group=open-mmi-update",
            "ExecStart=/opt/open-mmi/venv/bin/python -I -m ui.trust_status_coordinator serve",
            "NoNewPrivileges=true",
            "PrivateDevices=true",
            "ProtectSystem=strict",
            "RestrictAddressFamilies=AF_UNIX",
            "IPAddressDeny=any",
            "ReadWritePaths=/run/open-mmi",
        ):
            self.assertIn(required, unit)
        self.assertNotIn("AF_INET", unit)
        self.assertNotIn("EnvironmentFile=", unit)

    def test_service_has_only_serve_cli_action(self) -> None:
        parser_source = inspect.getsource(coordinator.build_parser)
        self.assertIn('add_parser("serve"', parser_source)
        for forbidden in ("acknowledge", "accept", "bootstrap", "reconcile", "authorize", "revoke"):
            self.assertNotIn(forbidden, parser_source)


if __name__ == "__main__":
    unittest.main()
