"""User-owned vehicle catalogue creation from immutable maintained templates.

The dashboard may create a new custom profile or bindings document only beneath
its fixed user catalogue root. Maintained catalogue content is read-only and is
accepted solely as a revision-bound starting template.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from ui import vehicle_configuration, vehicle_setup


API_VERSION = 1
COPY_ACTION = "copy-maintained-template"
_KIND_LIMITS = {
    "profile": vehicle_setup.MAX_PROFILE_BYTES,
    "bindings": vehicle_setup.MAX_BINDINGS_BYTES,
}


class VehicleCatalogueError(RuntimeError):
    """A custom catalogue request failed closed."""


class VehicleCatalogueConflictError(VehicleCatalogueError):
    """A revision changed or the requested custom destination already exists."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def _unique_json_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise VehicleCatalogueError(f"Duplicate catalogue JSON field: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise VehicleCatalogueError(f"Invalid catalogue JSON number: {value}")


def _validate_identifier(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not vehicle_setup.IDENTIFIER_RE.fullmatch(value):
        raise VehicleCatalogueError(f"{field} is invalid")
    return value


def _normalize_copy_request(payload: object) -> tuple[str, dict[str, str], str]:
    if not isinstance(payload, Mapping) or set(payload) != {
        "kind",
        "id",
        "template_source",
        "template_id",
        "template_revision",
    }:
        raise VehicleCatalogueError("Invalid custom catalogue copy schema")
    kind = payload.get("kind")
    if kind not in _KIND_LIMITS:
        raise VehicleCatalogueError("Custom catalogue kind must be profile or bindings")
    if payload.get("template_source") != "maintained":
        raise VehicleCatalogueError("Only maintained catalogue items may be used as templates")
    template_id = _validate_identifier(
        payload.get("template_id"),
        field="Maintained template id",
    )
    revision = payload.get("template_revision")
    if not isinstance(revision, str) or not vehicle_configuration.REVISION_RE.fullmatch(revision):
        raise VehicleCatalogueError("Maintained template revision is invalid")
    custom_id = _validate_identifier(payload.get("id"), field="Custom catalogue id")
    return str(kind), {
        "source": "maintained",
        "id": template_id,
        "revision": revision,
    }, custom_id


def _read_template(
    roots: vehicle_setup.CatalogueRoots,
    kind: str,
    template: Mapping[str, str],
) -> tuple[bytes, str]:
    path = vehicle_setup.resolve_catalogue_path(
        roots,
        kind,
        "maintained",
        template["id"],
    )
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        maximum = _KIND_LIMITS[kind]
        if not stat.S_ISREG(metadata.st_mode):
            raise VehicleCatalogueError("Maintained template must be a regular file")
        if (
            metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_nlink != 1
            or metadata.st_mode & 0o022
        ):
            raise VehicleCatalogueError("Maintained template is untrusted")
        if metadata.st_size > maximum:
            raise VehicleCatalogueError("Maintained template exceeds the size limit")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
    except OSError as exc:
        raise VehicleCatalogueError("Maintained template cannot be read") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(content) > _KIND_LIMITS[kind]:
        raise VehicleCatalogueError("Maintained template exceeds the size limit")
    actual_revision = "sha256:" + hashlib.sha256(content).hexdigest()
    if actual_revision != template["revision"]:
        raise VehicleCatalogueConflictError(
            "Maintained template changed; refresh Vehicle Setup before copying",
            "template-stale",
        )
    try:
        document = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VehicleCatalogueError("Maintained template is not valid UTF-8 JSON") from exc
    validation = (
        vehicle_setup.validate_profile(document)
        if kind == "profile"
        else vehicle_setup.validate_bindings(document)
    )
    if validation.get("valid") is not True:
        raise VehicleCatalogueError("Maintained template is not valid")
    return content, actual_revision


def _ensure_user_directory(path: Path, *, create: bool = True) -> None:
    if not path.is_absolute():
        raise VehicleCatalogueError("Custom catalogue root must be absolute")
    try:
        if create:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        metadata = path.lstat()
    except OSError as exc:
        raise VehicleCatalogueError("Custom catalogue directory is unavailable") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        raise VehicleCatalogueError("Custom catalogue directory is untrusted")


def _remove_new_file(directory: Path, name: str) -> None:
    directory_fd = -1
    try:
        directory_fd = os.open(
            directory,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        os.unlink(name, dir_fd=directory_fd)
        os.fsync(directory_fd)
    except OSError:
        pass
    finally:
        if directory_fd >= 0:
            os.close(directory_fd)


def _display_name(identifier: str) -> str:
    words = identifier.replace("-", "_").split("_")
    return " ".join(word.capitalize() for word in words if word) or identifier


def _provenance_content(
    kind: str,
    custom_id: str,
    template: Mapping[str, str],
) -> bytes:
    try:
        from ui.web_dashboard import versioning

        build_id = versioning.resolve_build_id()
    except Exception:
        build_id = "unknown"
    payload = {
        "schema_version": 1,
        "kind": kind,
        "id": custom_id,
        "display_name": _display_name(custom_id),
        "template": {
            "source": "maintained",
            "id": template["id"],
            "open_mmi_version": build_id,
            "revision": template["revision"],
        },
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _provenance_destination(
    root: Path,
    kind: str,
) -> Path:
    provenance_root = root / ".open-mmi-provenance"
    _ensure_user_directory(provenance_root)
    directory = provenance_root / kind
    _ensure_user_directory(directory)
    return directory


def _path_present(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise VehicleCatalogueError("Custom catalogue destination cannot be inspected") from exc
    return True


def _write_new_file(directory: Path, name: str, content: bytes) -> None:
    _ensure_user_directory(directory)
    directory_fd = -1
    temporary_name = f".open-mmi-copy-{uuid.uuid4().hex}.tmp"
    try:
        directory_fd = os.open(
            directory,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            existing = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            raise VehicleCatalogueConflictError(
                "A custom catalogue item with that id already exists",
                "custom-exists",
            )
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        try:
            view = memoryview(content)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short custom catalogue write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.link(
                temporary_name,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise VehicleCatalogueConflictError(
                "A custom catalogue item with that id already exists",
                "custom-exists",
            ) from exc
        os.unlink(temporary_name, dir_fd=directory_fd)
        os.fsync(directory_fd)
    except VehicleCatalogueError:
        raise
    except OSError as exc:
        raise VehicleCatalogueError("Custom catalogue item could not be created") from exc
    finally:
        if directory_fd >= 0:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except OSError:
                pass
            os.close(directory_fd)


def copy_maintained_template(
    payload: object,
    *,
    roots: Optional[vehicle_setup.CatalogueRoots] = None,
) -> dict[str, Any]:
    """Create one revision-bound custom copy without modifying maintained files."""

    kind, template, custom_id = _normalize_copy_request(payload)
    selected_roots = roots or vehicle_setup.default_roots()
    content, revision = _read_template(selected_roots, kind, template)
    _ensure_user_directory(selected_roots.custom)

    provenance = _provenance_content(kind, custom_id, template)
    provenance_name = f"{custom_id}.json"
    provenance_path = (
        selected_roots.custom
        / ".open-mmi-provenance"
        / kind
        / provenance_name
    )
    if kind == "profile":
        destination = selected_roots.custom / "vehicles" / custom_id
        content_path = destination / "config.json"
    else:
        destination = selected_roots.custom / "bindings"
        content_path = destination / f"{custom_id}.json"
    if _path_present(content_path) or _path_present(provenance_path) or (
        kind == "profile" and _path_present(destination)
    ):
        raise VehicleCatalogueConflictError(
            "A custom catalogue item with that id already exists",
            "custom-exists",
        )

    provenance_directory = _provenance_destination(selected_roots.custom, kind)

    if kind == "profile":
        profiles = selected_roots.custom / "vehicles"
        _ensure_user_directory(profiles)
        destination = profiles / custom_id
        try:
            destination.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise VehicleCatalogueConflictError(
                "A custom catalogue item with that id already exists",
                "custom-exists",
            ) from exc
        except OSError as exc:
            raise VehicleCatalogueError("Custom profile directory could not be created") from exc
        try:
            _ensure_user_directory(destination, create=False)
            _write_new_file(destination, "config.json", content)
            _write_new_file(provenance_directory, provenance_name, provenance)
        except BaseException:
            _remove_new_file(destination, "config.json")
            _remove_new_file(provenance_directory, provenance_name)
            try:
                destination.rmdir()
            except OSError:
                pass
            raise
    else:
        bindings = selected_roots.custom / "bindings"
        _ensure_user_directory(bindings)
        binding_name = f"{custom_id}.json"
        try:
            _write_new_file(bindings, binding_name, content)
            _write_new_file(provenance_directory, provenance_name, provenance)
        except BaseException:
            _remove_new_file(bindings, binding_name)
            _remove_new_file(provenance_directory, provenance_name)
            raise

    return {
        "ok": True,
        "api_version": API_VERSION,
        "action": COPY_ACTION,
        "kind": kind,
        "template": dict(template),
        "custom": {
            "source": "custom",
            "id": custom_id,
            "revision": revision,
        },
    }
