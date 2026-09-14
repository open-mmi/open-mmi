"""Read-only dashboard adapter for the privileged trust status coordinator."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from open_mmi_trust.inspector import FAIL, PASS, UNVERIFIED
from ui import trust_status_coordinator


_VALID_STATUSES = frozenset({PASS, FAIL, UNVERIFIED})
_EXPECTED_ENVELOPE_KEYS = frozenset(
    {"ok", "api_version", "status", "report", "error"}
)
_UNAVAILABLE_ERROR = "Trust inspection evidence is unavailable."
_MALFORMED_ERROR = "Trust inspection evidence is malformed."


def _unverified(error: str) -> dict[str, Any]:
    return {
        "api_version": trust_status_coordinator.API_VERSION,
        "status": UNVERIFIED,
        "report": None,
        "error": error,
    }


def trust_status_payload(
    coordinator_client: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return fresh trust evidence obtained only through the fixed coordinator."""

    collect = coordinator_client or trust_status_coordinator.client_status

    try:
        envelope = collect()
    except Exception:
        return _unverified(_UNAVAILABLE_ERROR)

    if not isinstance(envelope, Mapping):
        return _unverified(_MALFORMED_ERROR)
    if set(envelope) != _EXPECTED_ENVELOPE_KEYS:
        return _unverified(_MALFORMED_ERROR)
    if envelope.get("api_version") != trust_status_coordinator.API_VERSION:
        return _unverified(_MALFORMED_ERROR)

    ok = envelope.get("ok")
    status = envelope.get("status")
    report = envelope.get("report")
    error = envelope.get("error")

    if ok is True:
        if (
            status not in _VALID_STATUSES
            or not isinstance(report, Mapping)
            or report.get("status") != status
            or error is not None
        ):
            return _unverified(_MALFORMED_ERROR)
        return {
            "api_version": trust_status_coordinator.API_VERSION,
            "status": status,
            "report": dict(report),
            "error": None,
        }

    if ok is False:
        if (
            status != UNVERIFIED
            or report is not None
            or not isinstance(error, str)
            or not error
        ):
            return _unverified(_MALFORMED_ERROR)
        return _unverified(_UNAVAILABLE_ERROR)

    return _unverified(_MALFORMED_ERROR)
