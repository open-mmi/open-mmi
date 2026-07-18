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
import pwd
import socket
import socketserver
import stat
import shutil
import subprocess
import tempfile
import uuid
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from ui import update_policy
from ui.web_dashboard import update_status


API_VERSION = 1
STATE_SCHEMA_VERSION = 2
DEFAULT_STATE_FILE = Path("/var/lib/open-mmi/update-state.json")
DEFAULT_SOCKET = Path("/run/open-mmi/update-coordinator.sock")
DEFAULT_LOCK = Path("/run/open-mmi/update.lock")
DEFAULT_STAGING_ROOT = Path("/var/lib/open-mmi/staging")
DEFAULT_GROUP = "open-mmi-update"
ACTIVE_STATES = {"preparing", "downloading", "validating", "installing", "restarting", "checking-health", "rolling-back"}
TERMINAL_STATES = {"idle", "prepared", "complete", "failed"}
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
        "candidate_commit": "",
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
    for key in ("stage", "target_version", "previous_version", "candidate_commit", "error"):
        if not isinstance(payload.get(key), str):
            raise CoordinatorError("Coordinator state value is invalid")
    if not isinstance(payload.get("recovered"), bool):
        raise CoordinatorError("Coordinator recovery state is invalid")
    transaction_id = payload.get("transaction_id")
    if transaction_id is not None and (
        not isinstance(transaction_id, str)
        or not transaction_id.startswith("prepare-")
        or len(transaction_id) != 40
        or any(character not in "0123456789abcdef" for character in transaction_id[8:])
    ):
        raise CoordinatorError("Coordinator transaction identifier is invalid")
    candidate_commit = payload.get("candidate_commit")
    if candidate_commit and (
        len(candidate_commit) != 40
        or any(character not in "0123456789abcdef" for character in candidate_commit.lower())
    ):
        raise CoordinatorError("Coordinator candidate commit is invalid")
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
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("schema_version") == 1:
            expected = set(initial_state()) - {"candidate_commit"}
            if set(payload) != expected:
                raise CoordinatorError("Coordinator state schema is invalid")
            payload = dict(payload, schema_version=STATE_SCHEMA_VERSION, candidate_commit="")
        return _validate_state(payload)
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
        return write_state(state, path)
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


def _public_response(state: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "ok": True,
        "api_version": API_VERSION,
        "preparation_enabled": True,
        "execution_enabled": False,
        "installation_enabled": False,
        "state": dict(state),
    }


def _safe_remove_staging(path: Path, staging_root: Path) -> None:
    try:
        resolved = path.resolve()
        root = staging_root.resolve()
    except OSError:
        return
    if resolved.parent != root or not path.name.startswith("prepare-"):
        raise CoordinatorError("Coordinator staging path is invalid")
    if path.exists():
        shutil.rmtree(path)


def _secure_staging_tree(path: Path) -> None:
    for root, directories, files in os.walk(path, topdown=False, followlinks=False):
        for name in files:
            item = Path(root) / name
            os.lchown(item, 0, 0)
            if not item.is_symlink():
                os.chmod(item, item.stat().st_mode & ~0o022)
        for name in directories:
            item = Path(root) / name
            os.lchown(item, 0, 0)
            if not item.is_symlink():
                os.chmod(item, item.stat().st_mode & ~0o022)
    os.lchown(path, 0, 0)
    os.chmod(path, 0o700)


def _user_service_check(source: Mapping[str, str]) -> Dict[str, Any]:
    from ui import update_readiness
    try:
        owner = Path(source["repository_path"]).stat()
        account = pwd.getpwuid(owner.st_uid)
        groups = os.getgrouplist(account.pw_name, owner.st_gid)
        environment = os.environ.copy()
        environment.update({
            "HOME": account.pw_dir, "USER": account.pw_name, "LOGNAME": account.pw_name,
            "XDG_RUNTIME_DIR": f"/run/user/{owner.st_uid}",
        })
        result = subprocess.run(
            ["systemctl", "--user", "show", *update_readiness.REQUIRED_SERVICES,
             "--property=Id,ActiveState,SubState,NRestarts", "--value"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
            timeout=update_readiness.SYSTEMCTL_TIMEOUT_SECONDS, env=environment,
            user=owner.st_uid, group=owner.st_gid, extra_groups=groups,
        )
    except (KeyError, OSError, ValueError, subprocess.TimeoutExpired):
        return {"state": "unknown"}
    if result.returncode != 0:
        return {"state": "unknown"}
    restarts = [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]
    return {"state": "block" if restarts and max(restarts) > update_readiness.MAX_SERVICE_RESTARTS else "pass"}


def _preparation_readiness(source: Mapping[str, str]) -> None:
    status = update_status.status_payload()
    if status.get("readiness", {}).get("blockers"):
        raise CoordinatorError("Managed installation is not ready for preparation")
    from ui import update_readiness
    diagnostics = update_readiness.runtime_diagnostics.runtime_diagnostics_payload()
    owner = Path(source["repository_path"]).stat()
    try:
        config_dir = Path(pwd.getpwuid(owner.st_uid).pw_dir) / ".config/open-mmi"
    except KeyError as exc:
        raise CoordinatorError("Managed source owner cannot be resolved") from exc
    required_checks = (
        update_readiness._disk_check(Path("/opt/open-mmi")),
        update_readiness._command_check(),
        update_readiness._configuration_check(config_dir),
        _user_service_check(source),
    )
    hardware_checks = (
        update_readiness._power_check(diagnostics.get("power", {})),
        update_readiness._thermal_check(diagnostics.get("thermal", {})),
    )
    if any(check["state"] != "pass" for check in required_checks) or any(
        check["state"] == "block" for check in hardware_checks
    ):
        raise CoordinatorError("System readiness does not permit candidate preparation")


def _candidate(source: Mapping[str, str], channel: str) -> tuple[str, str, str]:
    if channel == "development":
        commit = update_status._remote_commit(source)
        if commit == source["installed_commit"]:
            raise CoordinatorError("No update candidate is available")
        return commit[:12], commit, ""
    tag, commit, key = update_status._remote_release(source, channel)
    state, available, error = update_status._release_comparison(source, channel, tag, commit, key)
    if state != "update-available" or available is not True:
        raise CoordinatorError(error or "No approved forward update candidate is available")
    return tag, commit, tag


def _prepare_candidate(
    state_path: Path = DEFAULT_STATE_FILE,
    lock_path: Path = DEFAULT_LOCK,
    staging_root: Path = DEFAULT_STAGING_ROOT,
) -> Dict[str, Any]:
    source, source_state = update_status._read_source_descriptor()
    policy, _ = update_policy.read_policy()
    if not source or source_state != "configured" or not policy:
        raise CoordinatorError("Managed update source or policy is unavailable")
    channel = str(policy["channel"])
    repository = update_status._repository_snapshot(source, source_state, channel)
    if repository["state"] != "ready":
        raise CoordinatorError("Managed update source is not ready")
    _preparation_readiness(source)

    transaction_id = f"prepare-{uuid.uuid4().hex}"
    stage = staging_root / transaction_id
    state = initial_state()
    state.update({
        "state": "preparing", "stage": "preparing", "transaction_id": transaction_id,
        "started_at": _timestamp(), "updated_at": _timestamp(),
        "previous_version": source["installed_version"],
    })
    with TransactionLock(lock_path):
        write_state(state, state_path)
        try:
            target_version, candidate_commit, release_tag = _candidate(source, channel)
            state.update({
                "state": "downloading", "stage": "downloading", "updated_at": _timestamp(),
                "target_version": target_version, "candidate_commit": candidate_commit,
            })
            write_state(state, state_path)

            staging_root.mkdir(parents=True, exist_ok=True, mode=0o711)
            os.chmod(staging_root, 0o711)
            stage.mkdir(mode=0o700)
            owner = Path(source["repository_path"]).stat()
            os.chown(stage, owner.st_uid, owner.st_gid)
            remote_url = update_status._remote_url(source)
            if not remote_url:
                raise CoordinatorError("Managed update remote is unavailable")
            try:
                clone = update_status._run_git(
                    Path(source["repository_path"]),
                    ("clone", "--no-checkout", "--origin", "origin", "--", remote_url, str(stage)),
                    timeout=60.0,
                )
            except Exception as exc:
                raise CoordinatorError("Candidate download failed") from exc
            if clone.returncode != 0:
                raise CoordinatorError("Candidate download failed")

            state.update({"state": "validating", "stage": "validating", "updated_at": _timestamp()})
            write_state(state, state_path)
            if not update_status._git_success(stage, "cat-file", "-e", f"{candidate_commit}^{{commit}}"):
                raise CoordinatorError("Candidate commit is unavailable after download")
            if not update_status._git_success(stage, "cat-file", "-e", f"{source['installed_commit']}^{{commit}}"):
                raise CoordinatorError("Installed commit is absent from candidate history")
            if not update_status._git_success(stage, "merge-base", "--is-ancestor", source["installed_commit"], candidate_commit):
                raise CoordinatorError("Candidate is not a proven forward update")
            if release_tag:
                resolved_tag = update_status._git_output(stage, "rev-parse", f"refs/tags/{release_tag}^{{}}")
                if resolved_tag.lower() != candidate_commit:
                    raise CoordinatorError("Release tag identity changed during preparation")
            if not update_status._git_success(stage, "checkout", "--detach", candidate_commit):
                raise CoordinatorError("Candidate checkout could not be staged")
            _secure_staging_tree(stage)
            state.update({
                "state": "prepared", "stage": "prepared", "updated_at": _timestamp(),
                "completed_at": _timestamp(), "error": "",
            })
            return write_state(state, state_path)
        except Exception as exc:
            _safe_remove_staging(stage, staging_root)
            state.update({
                "state": "failed", "stage": "preparation", "updated_at": _timestamp(),
                "completed_at": _timestamp(), "error": str(exc) if isinstance(exc, CoordinatorError) else "Candidate preparation failed",
            })
            write_state(state, state_path)
            raise CoordinatorError(state["error"]) from exc


def response_for_request(
    payload: object,
    state_path: Path = DEFAULT_STATE_FILE,
    lock_path: Path = DEFAULT_LOCK,
    staging_root: Path = DEFAULT_STAGING_ROOT,
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"ok": False, "error": "Invalid coordinator request schema"}
    action = payload.get("action")
    expected = {"api_version", "action"} if action == "status" else {"api_version", "action", "confirm"}
    if set(payload) != expected:
        return {"ok": False, "error": "Invalid coordinator request schema"}
    if payload.get("api_version") != API_VERSION:
        return {"ok": False, "error": "Unsupported coordinator API version"}
    if action not in {"status", "prepare"}:
        return {"ok": False, "error": "Coordinator action is not enabled"}
    if action == "prepare" and payload.get("confirm") is not True:
        return {"ok": False, "error": "Candidate preparation requires confirmation"}
    try:
        state = read_state(state_path) if action == "status" else _prepare_candidate(state_path, lock_path, staging_root)
    except CoordinatorError as exc:
        return {"ok": False, "error": str(exc)}
    return _public_response(state)


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


class CoordinatorServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    allow_reuse_address = False
    daemon_threads = True
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
    return _client_request({"api_version": API_VERSION, "action": "status"}, socket_path)


def client_prepare(socket_path: Path = DEFAULT_SOCKET) -> Dict[str, Any]:
    return _client_request({"api_version": API_VERSION, "action": "prepare", "confirm": True}, socket_path, timeout=90.0)


def _client_request(payload: Mapping[str, Any], socket_path: Path, timeout: float = 3.0) -> Dict[str, Any]:
    request = json.dumps(dict(payload)).encode("utf-8") + b"\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(str(socket_path))
            connection.sendall(request)
            response = connection.makefile("rb").readline(MAX_REQUEST_BYTES + 1)
        payload = json.loads(response.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError("Coordinator is unavailable") from exc
    if not isinstance(payload, dict):
        raise CoordinatorError("Coordinator returned an invalid response")
    if payload.get("ok") is not True:
        error = str(payload.get("error") or "Coordinator request failed")
        raise CoordinatorError(error)
    return payload


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Open MMI privileged update coordinator")
    parser.add_argument("command", choices=("serve", "status", "prepare"))
    args = parser.parse_args(argv)
    if args.command == "status":
        print(json.dumps(client_status(), indent=2, sort_keys=True))
        return 0
    if args.command == "prepare":
        print(json.dumps(client_prepare(), indent=2, sort_keys=True))
        return 0
    if os.geteuid() != 0:
        raise SystemExit("open-mmi-update-coordinator: serve requires root")
    recover_interrupted_state()
    with CoordinatorServer(DEFAULT_SOCKET, DEFAULT_STATE_FILE) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
