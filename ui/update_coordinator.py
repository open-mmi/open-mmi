"""Persistent, fixed-protocol boundary for privileged update coordination.

This slice deliberately enables status only.  It does not execute Git,
installers, service actions, rollback, or any caller-selected operation.
"""

from __future__ import annotations

import argparse
import fcntl
import grp
import json
import os
import socket
import socketserver
import stat
import tempfile
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


API_VERSION = 1
STATE_SCHEMA_VERSION = 1
DEFAULT_STATE_FILE = Path("/var/lib/open-mmi/update-state.json")
DEFAULT_SOCKET = Path("/run/open-mmi/update-coordinator.sock")
DEFAULT_LOCK = Path("/run/open-mmi/update.lock")
DEFAULT_GROUP = "open-mmi-update"
ACTIVE_STATES = {"preparing", "downloading", "validating", "installing", "restarting", "checking-health", "rolling-back"}
TERMINAL_STATES = {"idle", "complete", "failed"}
ALLOWED_STATES = ACTIVE_STATES | TERMINAL_STATES
MAX_REQUEST_BYTES = 4096


class CoordinatorError(RuntimeError):
    pass


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def initial_state() -> Dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "state": "idle",
        "transaction_id": None,
        "started_at": None,
        "updated_at": _timestamp(),
        "completed_at": None,
        "stage": "idle",
        "target_version": "",
        "previous_version": "",
        "error": "",
        "recovered": False,
    }


def _validate_state(payload: object) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise CoordinatorError("Coordinator state root must be an object")
    allowed = set(initial_state())
    if set(payload) != allowed or payload.get("schema_version") != STATE_SCHEMA_VERSION:
        raise CoordinatorError("Coordinator state schema is invalid")
    state = str(payload.get("state") or "")
    if state not in ALLOWED_STATES:
        raise CoordinatorError("Coordinator transaction state is invalid")
    for key in ("stage", "target_version", "previous_version", "error"):
        if not isinstance(payload.get(key), str):
            raise CoordinatorError("Coordinator state value is invalid")
    if not isinstance(payload.get("recovered"), bool):
        raise CoordinatorError("Coordinator recovery state is invalid")
    return dict(payload)


def _trusted_state_file(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode) and metadata.st_uid == 0 and not metadata.st_mode & 0o022


def read_state(path: Path = DEFAULT_STATE_FILE) -> Dict[str, Any]:
    if not path.exists():
        return initial_state()
    if path == DEFAULT_STATE_FILE and not _trusted_state_file(path):
        raise CoordinatorError("Coordinator state file is untrusted")
    try:
        return _validate_state(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError("Coordinator state file is invalid") from exc


def write_state(payload: Mapping[str, Any], path: Path = DEFAULT_STATE_FILE) -> Dict[str, Any]:
    if os.geteuid() != 0 and path == DEFAULT_STATE_FILE:
        raise CoordinatorError("Writing production coordinator state requires root")
    validated = _validate_state(dict(payload))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as temporary:
            temporary_name = temporary.name
            json.dump(validated, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        raise CoordinatorError("Could not persist coordinator state") from exc
    return validated


def recover_interrupted_state(path: Path = DEFAULT_STATE_FILE) -> Dict[str, Any]:
    if not path.exists():
        return write_state(initial_state(), path)
    state = read_state(path)
    if state["state"] not in ACTIVE_STATES:
        return state
    state.update({
        "state": "failed", "stage": "recovery", "updated_at": _timestamp(),
        "completed_at": _timestamp(), "error": "Coordinator restarted during an active transaction",
        "recovered": True,
    })
    return write_state(state, path)


class TransactionLock(AbstractContextManager["TransactionLock"]):
    def __init__(self, path: Path = DEFAULT_LOCK):
        self.path = path
        self.handle: Optional[Any] = None

    def __enter__(self) -> "TransactionLock":
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        self.handle = self.path.open("a+", encoding="utf-8")
        os.chmod(self.path, 0o600)
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise CoordinatorError("Another update transaction is active") from exc
        return self

    def __exit__(self, *args: object) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


def response_for_request(payload: object, state_path: Path = DEFAULT_STATE_FILE) -> Dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {"api_version", "action"}:
        return {"ok": False, "error": "Invalid coordinator request schema"}
    if payload.get("api_version") != API_VERSION:
        return {"ok": False, "error": "Unsupported coordinator API version"}
    if payload.get("action") != "status":
        return {"ok": False, "error": "Coordinator action is not enabled"}
    try:
        state = read_state(state_path)
    except CoordinatorError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "api_version": API_VERSION, "execution_enabled": False, "state": state}


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if not raw or len(raw) > MAX_REQUEST_BYTES:
            response = {"ok": False, "error": "Invalid coordinator request size"}
        else:
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                payload = None
            response = response_for_request(payload, self.server.state_path)  # type: ignore[attr-defined]
        self.wfile.write((json.dumps(response, sort_keys=True) + "\n").encode("utf-8"))


class CoordinatorServer(socketserver.UnixStreamServer):
    allow_reuse_address = False
    def __init__(self, socket_path: Path, state_path: Path):
        self.socket_path = socket_path
        self.state_path = state_path
        socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        try:
            existing = socket_path.lstat()
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if not stat.S_ISSOCK(existing.st_mode) or existing.st_uid != 0:
                raise CoordinatorError("Coordinator socket path is occupied by an untrusted object")
            socket_path.unlink()
        super().__init__(str(socket_path), _Handler)
        os.chmod(socket_path, 0o660)
        try:
            os.chown(socket_path, 0, grp.getgrnam(DEFAULT_GROUP).gr_gid)
        except KeyError as exc:
            self.server_close()
            raise CoordinatorError("Coordinator access group is unavailable") from exc

    def server_close(self) -> None:
        super().server_close()
        try:
            metadata = self.socket_path.lstat()
            if stat.S_ISSOCK(metadata.st_mode) and metadata.st_uid == 0:
                self.socket_path.unlink()
        except OSError:
            pass


def client_status(socket_path: Path = DEFAULT_SOCKET) -> Dict[str, Any]:
    request = json.dumps({"api_version": API_VERSION, "action": "status"}).encode("utf-8") + b"\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(3.0)
            connection.connect(str(socket_path))
            connection.sendall(request)
            response = connection.makefile("rb").readline(MAX_REQUEST_BYTES + 1)
        payload = json.loads(response.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError("Coordinator is unavailable") from exc
    if not isinstance(payload, dict):
        raise CoordinatorError("Coordinator returned an invalid response")
    return payload


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Open MMI privileged update coordinator")
    parser.add_argument("command", choices=("serve", "status"))
    args = parser.parse_args(argv)
    if args.command == "status":
        print(json.dumps(client_status(), indent=2, sort_keys=True))
        return 0
    if os.geteuid() != 0:
        raise SystemExit("open-mmi-update-coordinator: serve requires root")
    recover_interrupted_state()
    with CoordinatorServer(DEFAULT_SOCKET, DEFAULT_STATE_FILE) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
