from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from unittest import mock

import open_mmi_trust.inspector as trust_inspector
from open_mmi_trust.inspector import FAIL, PASS, UNVERIFIED
from ui.web_dashboard import server, trust_status


ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / "ui" / "web_dashboard" / "trust_status.py"


def coordinator_envelope(
    status: str,
    *,
    report: object | None = None,
    ok: bool = True,
    error: object | None = None,
    api_version: int = 1,
):
    if report is None and ok:
        report = {
            "status": status,
            "manifest": {"available": True},
            "checks": [],
        }
    return {
        "ok": ok,
        "api_version": api_version,
        "status": status,
        "report": report,
        "error": error,
    }


class TrustStatusProviderTests(unittest.TestCase):
    def test_preserves_coordinator_status_without_reclassification(self):
        for status in (PASS, FAIL, UNVERIFIED):
            with self.subTest(status=status):
                report = {
                    "status": status,
                    "manifest": {"available": True},
                    "checks": [],
                }

                payload = trust_status.trust_status_payload(
                    lambda: coordinator_envelope(status, report=report)
                )

                self.assertEqual(payload["api_version"], 1)
                self.assertEqual(payload["status"], status)
                self.assertEqual(payload["report"], report)
                self.assertIsNone(payload["error"])

    def test_production_default_uses_coordinator_client(self):
        response = coordinator_envelope(PASS)
        with mock.patch.object(
            trust_status.trust_status_coordinator,
            "client_status",
            return_value=response,
        ) as client:
            payload = trust_status.trust_status_payload()

        client.assert_called_once_with()
        self.assertEqual(payload["status"], PASS)

    def test_client_failures_are_sanitized_and_unverified(self):
        secret = "/root/private-owner-state"
        failures = (
            PermissionError(secret),
            TimeoutError(secret),
            trust_status.trust_status_coordinator.TrustStatusUnavailableError(secret),
            trust_status.trust_status_coordinator.TrustStatusCoordinatorError(secret),
        )

        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                def broken(failure=failure):
                    raise failure

                payload = trust_status.trust_status_payload(broken)

                self.assertEqual(payload["status"], UNVERIFIED)
                self.assertIsNone(payload["report"])
                self.assertEqual(
                    payload["error"],
                    "Trust inspection evidence is unavailable.",
                )
                self.assertNotIn(secret, payload["error"])

    def test_coordinator_failure_is_sanitized_and_unverified(self):
        secret = "/var/lib/open-mmi/trust/private.json"
        payload = trust_status.trust_status_payload(
            lambda: coordinator_envelope(
                UNVERIFIED,
                report=None,
                ok=False,
                error=secret,
            )
        )

        self.assertEqual(payload["status"], UNVERIFIED)
        self.assertIsNone(payload["report"])
        self.assertEqual(
            payload["error"],
            "Trust inspection evidence is unavailable.",
        )
        self.assertNotIn(secret, payload["error"])

    def test_malformed_coordinator_envelopes_are_unverified(self):
        valid = coordinator_envelope(PASS)
        malformed = (
            None,
            {},
            {**valid, "api_version": 2},
            {**valid, "ok": "yes"},
            {**valid, "status": "GREEN"},
            {**valid, "report": []},
            {**valid, "status": PASS, "report": {"status": FAIL}},
            {**valid, "error": "must be null on success"},
            {**valid, "extra": True},
            coordinator_envelope(PASS, ok=False, report=None, error="failure"),
            coordinator_envelope(
                UNVERIFIED,
                ok=False,
                report={"status": UNVERIFIED},
                error="failure",
            ),
            coordinator_envelope(UNVERIFIED, ok=False, report=None, error=None),
        )

        for envelope in malformed:
            with self.subTest(envelope=envelope):
                payload = trust_status.trust_status_payload(
                    lambda envelope=envelope: envelope
                )
                self.assertEqual(payload["status"], UNVERIFIED)
                self.assertIsNone(payload["report"])
                self.assertEqual(
                    payload["error"],
                    "Trust inspection evidence is malformed.",
                )

    def test_provider_routes_only_through_coordinator(self):
        source = PROVIDER.read_text(encoding="utf-8")
        self.assertNotIn("inspect_system", source)
        self.assertIn("trust_status_coordinator.client_status", source)

    def test_provider_has_no_trust_mutation_or_remote_dependency(self):
        source = PROVIDER.read_text(encoding="utf-8")

        for forbidden in (
            "accepted_state",
            "transition_gate",
            "release_provenance",
            "_write_accepted_state",
            "_record_acknowledged_expansion",
            "activate_acknowledged_expansion",
            "acknowledge",
            "postJson",
            "requests",
            "urllib",
            "socket",
            "subprocess",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_ordinary_get_routes_through_coordinator_not_local_inspector(self):
        response = coordinator_envelope(PASS)
        handler = object.__new__(server.DashboardHandler)
        handler.path = "/api/trust/status"
        handler._send_json = mock.Mock()

        with (
            mock.patch.object(
                server.system_settings_backend,
                "_handle_get",
                return_value=False,
            ),
            mock.patch.object(
                trust_status.trust_status_coordinator,
                "client_status",
                return_value=response,
            ) as client,
            mock.patch.object(
                trust_inspector,
                "inspect_system",
                side_effect=AssertionError("local Inspector must not be called"),
            ) as inspector,
        ):
            handler.do_GET()

        client.assert_called_once_with()
        inspector.assert_not_called()
        handler._send_json.assert_called_once()
        self.assertEqual(handler._send_json.call_args.args[0]["status"], PASS)

    def test_trust_post_routes_are_unavailable(self):
        for path in (
            "/api/trust/status",
            "/api/trust/accept",
            "/api/trust/acknowledge",
        ):
            with self.subTest(path=path):
                handler = object.__new__(server.DashboardHandler)
                handler.path = path
                handler.send_error = mock.Mock()
                with mock.patch.object(
                    server.system_settings_backend,
                    "_handle_post",
                    return_value=False,
                ):
                    handler.do_POST()
                handler.send_error.assert_called_once_with(404)

    def test_server_exposes_trust_status_on_get_only(self):
        get_source = inspect.getsource(server.DashboardHandler.do_GET)
        post_source = inspect.getsource(server.DashboardHandler.do_POST)

        self.assertIn(
            'parsed.path == "/api/trust/status"',
            get_source,
        )
        self.assertIn(
            "trust_status_backend.trust_status_payload()",
            get_source,
        )
        self.assertNotIn("/api/trust/", post_source)

    def test_provider_is_independent_of_dashboard_handler(self):
        self.assertFalse(hasattr(trust_status, "DashboardHandler"))
        source = PROVIDER.read_text(encoding="utf-8")
        self.assertNotIn("from ui.web_dashboard.server", source)
        self.assertNotIn("import server", source)

    def test_trust_ui_is_required_in_built_and_installed_package(self):
        wheel_verifier = (
            ROOT / "tools" / "verify_wheel.py"
        ).read_text(encoding="utf-8")
        ci = (
            ROOT / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            '"ui/web_dashboard/trust_status.py"',
            wheel_verifier,
        )
        self.assertIn(
            '"ui/web_dashboard/static/trust-status.js"',
            wheel_verifier,
        )

        self.assertIn(
            '"dashboard_trust_status": Path(trust_status.__file__)',
            ci,
        )
        self.assertIn(
            '"frontend_trust_status": '
            'Path(ui.web_dashboard.__file__).parent / "static" / "trust-status.js"',
            ci,
        )


if __name__ == "__main__":
    unittest.main()
