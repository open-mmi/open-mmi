#!/usr/bin/env python3
"""Read-only USB media discovery, browsing, and descriptor-safe streaming.

This module owns the removable-media filesystem boundary. It deliberately has
no dependency on the dashboard HTTP handler; ``server.py`` supplies a handler
only when streaming audio or artwork to a client.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict

USB_AUDIO_EXTENSIONS = {
    ".aac",
    ".flac",
    ".m4a",
    ".mp3",
    ".oga",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
}
USB_ARTWORK_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
USB_ARTWORK_NAMES = (
    "cover.jpg",
    "cover.jpeg",
    "cover.png",
    "cover.webp",
    "folder.jpg",
    "folder.jpeg",
    "folder.png",
    "folder.webp",
    "front.jpg",
    "front.jpeg",
    "front.png",
    "front.webp",
    "album.jpg",
    "album.jpeg",
    "album.png",
    "album.webp",
)
USB_STREAM_CHUNK_BYTES = 64 * 1024
USB_MAX_ROOTS = 32
USB_MAX_RESULTS = 120
USB_DEFAULT_SCAN_LIMIT = 10000


def _usb_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _usb_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _usb_split_paths(value: str) -> list[Path]:
    paths: list[Path] = []
    for raw in str(value or "").split(os.pathsep):
        raw = raw.strip()
        if raw:
            paths.append(Path(raw).expanduser())
    return paths


def _usb_discovery_bases() -> list[Path]:
    configured = os.getenv("OPEN_MMI_USB_DISCOVERY_ROOTS", "").strip()
    if configured:
        return _usb_split_paths(configured)
    username = os.getenv("USER", "").strip() or Path.home().name
    return [Path("/run/media") / username, Path("/media") / username]


def _usb_root_id(path: Path) -> str:
    import hashlib

    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]


def _usb_safe_label(path: Path) -> str:
    label = path.name.strip() or "USB media"
    return "".join(ch for ch in label if ch >= " " and ch not in "\r\n")[:96] or "USB media"


def _usb_candidate_root(path: Path, origin: str) -> Dict[str, Any] | None:
    try:
        if origin == "discovered" and path.is_symlink():
            return None
        resolved = path.resolve(strict=True)
        if not resolved.is_dir() or not os.access(resolved, os.R_OK | os.X_OK):
            return None
    except (OSError, RuntimeError):
        return None
    return {
        "id": _usb_root_id(resolved),
        "path": resolved,
        "label": _usb_safe_label(resolved),
        "origin": origin,
    }


def _usb_roots() -> list[Dict[str, Any]]:
    roots: list[Dict[str, Any]] = []
    seen: set[Path] = set()

    for configured in _usb_split_paths(os.getenv("OPEN_MMI_USB_MEDIA_ROOTS", "")):
        candidate = _usb_candidate_root(configured, "configured")
        if candidate and candidate["path"] not in seen:
            roots.append(candidate)
            seen.add(candidate["path"])

    if _usb_bool_env("OPEN_MMI_USB_AUTO_DISCOVER", True):
        for base in _usb_discovery_bases():
            try:
                if base.is_symlink() or not base.is_dir():
                    continue
                children = sorted(base.iterdir(), key=lambda item: item.name.casefold())
            except OSError:
                continue
            for child in children:
                candidate = _usb_candidate_root(child, "discovered")
                if candidate and candidate["path"] not in seen:
                    roots.append(candidate)
                    seen.add(candidate["path"])
                if len(roots) >= USB_MAX_ROOTS:
                    return roots
    return roots[:USB_MAX_ROOTS]


import collections as _usb_collections
import hmac as _usb_hmac
import threading as _usb_threading

_USB_ID_SECRET = os.urandom(32)
_USB_ID_REGISTRY: Any = _usb_collections.OrderedDict()
_USB_ID_LOCK = _usb_threading.Lock()
USB_ID_REGISTRY_MAX = 20000


def _usb_normalize_relative(relative: str | Path = "") -> Path:
    text = str(relative).replace(os.sep, "/").strip("/")
    if text in {"", "."}:
        return Path()
    value = Path(text)
    if value.is_absolute() or any(part in {"", ".", ".."} for part in value.parts):
        raise ValueError("Invalid USB media path")
    return value


def _usb_encode_id(root_id: str, relative: str | Path = "") -> str:
    import hashlib

    if not re.fullmatch(r"[0-9a-f]{16}", str(root_id or "")):
        raise ValueError("Invalid USB media root ID")
    normalized = _usb_normalize_relative(relative)
    relative_text = normalized.as_posix() if normalized.parts else ""
    digest = _usb_hmac.new(
        _USB_ID_SECRET,
        f"{root_id}\0{relative_text}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:40]
    token = f"u{digest}"
    with _USB_ID_LOCK:
        _USB_ID_REGISTRY[token] = (root_id, relative_text)
        _USB_ID_REGISTRY.move_to_end(token)
        while len(_USB_ID_REGISTRY) > USB_ID_REGISTRY_MAX:
            _USB_ID_REGISTRY.popitem(last=False)
    return token


def _usb_decode_id(value: Any) -> tuple[str, Path]:
    token = str(value or "").strip()
    if not re.fullmatch(r"u[0-9a-f]{40}", token):
        raise ValueError("Invalid USB media ID")
    with _USB_ID_LOCK:
        registered = _USB_ID_REGISTRY.get(token)
        if registered is not None:
            _USB_ID_REGISTRY.move_to_end(token)
    if registered is None:
        raise FileNotFoundError("USB media item expired; refresh the library")
    root_id, relative_text = registered
    return root_id, _usb_normalize_relative(relative_text)


def _usb_root_map() -> Dict[str, Dict[str, Any]]:
    return {root["id"]: root for root in _usb_roots()}


def _usb_reject_symlink_components(root: Path, relative: Path) -> None:
    current = root
    for part in relative.parts:
        current = current / part
        try:
            is_symlink = current.is_symlink()
        except OSError as exc:
            raise FileNotFoundError("USB media path is unavailable") from exc
        if is_symlink:
            raise PermissionError("USB media symlinks are not followed")


def _usb_resolve_id(value: Any) -> tuple[Dict[str, Any], Path, Path]:
    root_id, relative = _usb_decode_id(value)
    root = _usb_root_map().get(root_id)
    if not root:
        raise FileNotFoundError("USB media root is unavailable")
    root_path = root["path"]
    _usb_reject_symlink_components(root_path, relative)
    candidate = root_path.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root_path)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise FileNotFoundError("USB media item is unavailable") from exc
    return root, relative, resolved


def _usb_include_entry(name: str) -> bool:
    return _usb_bool_env("OPEN_MMI_USB_INCLUDE_HIDDEN", False) or not name.startswith(".")


def _usb_artwork_path(audio_path: Path) -> Path | None:
    for name in USB_ARTWORK_NAMES:
        candidate = audio_path.parent / name
        try:
            if candidate.is_symlink():
                continue
            if candidate.is_file() and os.access(candidate, os.R_OK):
                return candidate
        except OSError:
            continue
    return None


def _usb_track_metadata(path: Path) -> Dict[str, Any]:
    title = path.stem.replace("_", " ").strip() or path.name
    artist = "USB media"
    album = path.parent.name or "USB media"
    duration: float | None = None

    if _usb_bool_env("OPEN_MMI_USB_READ_METADATA", False):
        try:
            import mutagen  # type: ignore

            media = mutagen.File(str(path), easy=True)
            if media is not None:
                tags = media.tags or {}
                title = str((tags.get("title") or [title])[0]).strip() or title
                artist = str((tags.get("artist") or [artist])[0]).strip() or artist
                album = str((tags.get("album") or [album])[0]).strip() or album
                length = getattr(getattr(media, "info", None), "length", None)
                if length is not None and float(length) >= 0:
                    duration = round(float(length), 3)
        except Exception:
            pass

    return {
        "name": title[:256],
        "artist": artist[:256],
        "album": album[:256],
        "duration_seconds": duration,
    }


def _usb_format_audio(root: Dict[str, Any], path: Path) -> Dict[str, Any]:
    relative = path.relative_to(root["path"])
    item_id = _usb_encode_id(root["id"], relative)
    metadata = _usb_track_metadata(path)
    artwork = _usb_artwork_path(path)
    try:
        stat = path.stat()
    except OSError:
        stat = None
    return {
        "id": item_id,
        "source": "usb",
        "kind": "audio",
        **metadata,
        "image_url": (
            f"/api/usb/art/{_usb_encode_id(root['id'], artwork.relative_to(root['path']))}"
            if artwork is not None
            else None
        ),
        "size_bytes": stat.st_size if stat else None,
        "modified_at": stat.st_mtime if stat else None,
        "file_type": path.suffix.lower().lstrip(".") or None,
    }


def _usb_format_directory(root: Dict[str, Any], path: Path) -> Dict[str, Any]:
    relative = path.relative_to(root["path"])
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = None
    return {
        "id": _usb_encode_id(root["id"], relative),
        "source": "usb",
        "kind": "directory",
        "name": path.name or root["label"],
        "artist": "Folder",
        "album": root["label"],
        "duration_seconds": None,
        "image_url": None,
        "modified_at": modified,
    }


def _usb_format_root(root: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _usb_encode_id(root["id"]),
        "source": "usb",
        "kind": "directory",
        "name": root["label"],
        "artist": "USB media root",
        "album": "Read-only local media",
        "duration_seconds": None,
        "image_url": None,
    }


def _usb_sort_items(items: list[Dict[str, Any]], media_filter: str) -> list[Dict[str, Any]]:
    selected = str(media_filter or "browse").strip().lower()
    if selected == "recent":
        return sorted(
            items,
            key=lambda item: (
                item.get("kind") != "directory",
                -(float(item.get("modified_at") or 0)),
                str(item.get("name") or "").casefold(),
            ),
        )
    if selected == "az":
        return sorted(items, key=lambda item: str(item.get("name") or "").casefold())
    return sorted(
        items,
        key=lambda item: (
            item.get("kind") != "directory",
            str(item.get("name") or "").casefold(),
        ),
    )


def _usb_search_terms(value: str) -> tuple[str, ...]:
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return tuple(part for part in re.split(r"[\W_]+", normalized) if part)


def _usb_search_matches(terms: tuple[str, ...], *values: object) -> bool:
    if not terms:
        return True
    haystack = " ".join(_usb_search_terms(" ".join(str(value or "") for value in values)))
    return all(term in haystack for term in terms)


def _usb_scan_directory(
    root: Dict[str, Any],
    directory: Path,
    query: str,
    limit: int,
) -> tuple[list[Dict[str, Any]], bool]:
    query_terms = _usb_search_terms(query)
    recursive = bool(query_terms)
    scan_limit = _usb_int_env(
        "OPEN_MMI_USB_SCAN_LIMIT", USB_DEFAULT_SCAN_LIMIT, 100, 100000
    )
    items: list[Dict[str, Any]] = []
    stack = [directory]
    scanned = 0
    truncated = False

    while stack and len(items) < limit:
        current = stack.pop()
        entries = []
        try:
            with os.scandir(current) as iterator:
                for entry in iterator:
                    if scanned >= scan_limit:
                        truncated = True
                        stack.clear()
                        break
                    scanned += 1
                    entries.append(entry)
        except OSError:
            continue
        entries.sort(key=lambda entry: entry.name.casefold(), reverse=recursive)
        for entry in entries:
            if not _usb_include_entry(entry.name):
                continue
            try:
                if entry.is_symlink():
                    continue
                path = Path(entry.path)
                try:
                    relative_search_path = path.relative_to(root["path"]).as_posix()
                except ValueError:
                    relative_search_path = entry.name
                if entry.is_dir(follow_symlinks=False):
                    if recursive:
                        stack.append(path)
                        if _usb_search_matches(
                            query_terms, entry.name, relative_search_path
                        ):
                            items.append(_usb_format_directory(root, path))
                    else:
                        items.append(_usb_format_directory(root, path))
                elif (
                    entry.is_file(follow_symlinks=False)
                    and path.suffix.lower() in USB_AUDIO_EXTENSIONS
                    and _usb_search_matches(
                        query_terms,
                        entry.name,
                        path.stem,
                        path.parent.name,
                        relative_search_path,
                    )
                ):
                    items.append(_usb_format_audio(root, path))
            except (OSError, ValueError):
                continue
            if len(items) >= limit:
                break
    return items, truncated

def _usb_breadcrumbs(root: Dict[str, Any], relative: Path) -> list[Dict[str, str]]:
    crumbs = [{"id": _usb_encode_id(root["id"]), "label": root["label"]}]
    current = Path()
    for part in relative.parts:
        current /= part
        crumbs.append({"id": _usb_encode_id(root["id"], current), "label": part})
    return crumbs


def _usb_browse_payload(
    directory_id: str = "",
    query: str = "",
    limit: int = 60,
    media_filter: str = "browse",
) -> Dict[str, Any]:
    roots = _usb_roots()
    try:
        bounded_limit = max(1, min(int(limit), USB_MAX_RESULTS))
    except (TypeError, ValueError):
        bounded_limit = 60
    selected_filter = str(media_filter or "browse").strip().lower()
    if selected_filter not in {"browse", "az", "recent"}:
        selected_filter = "browse"

    if not roots:
        return {
            "configured": False,
            "source": "usb",
            "filter": selected_filter,
            "directory_id": "",
            "parent_id": None,
            "breadcrumbs": [],
            "title": "USB media",
            "items": [],
            "error": "No readable USB media roots were found",
        }

    if not directory_id:
        if query:
            all_items: list[Dict[str, Any]] = []
            truncated = False
            for root in roots:
                remaining = bounded_limit - len(all_items)
                if remaining <= 0:
                    break
                found, root_truncated = _usb_scan_directory(
                    root, root["path"], query, remaining
                )
                all_items.extend(found)
                truncated = truncated or root_truncated
            return {
                "configured": True,
                "source": "usb",
                "filter": selected_filter,
                "directory_id": "",
                "parent_id": None,
                "breadcrumbs": [],
                "title": "USB search results",
                "items": _usb_sort_items(all_items, selected_filter),
                "truncated": truncated,
            }
        return {
            "configured": True,
            "source": "usb",
            "filter": selected_filter,
            "directory_id": "",
            "parent_id": None,
            "breadcrumbs": [],
            "title": "USB media roots",
            "items": [_usb_format_root(root) for root in roots],
            "truncated": False,
        }

    root, relative, directory = _usb_resolve_id(directory_id)
    if not directory.is_dir():
        raise ValueError("USB media directory is not a folder")
    items, truncated = _usb_scan_directory(root, directory, query, bounded_limit)
    parent_id = ""
    if relative.parts:
        parent_relative = relative.parent
        parent_id = _usb_encode_id(root["id"], parent_relative)
    return {
        "configured": True,
        "source": "usb",
        "filter": selected_filter,
        "directory_id": _usb_encode_id(root["id"], relative),
        "parent_id": parent_id,
        "breadcrumbs": _usb_breadcrumbs(root, relative),
        "title": directory.name or root["label"],
        "items": _usb_sort_items(items, selected_filter),
        "truncated": truncated,
    }


def _usb_status_payload() -> Dict[str, Any]:
    roots = _usb_roots()
    count = len(roots)
    return {
        "configured": count > 0,
        "source": "usb",
        "status": "ready" if count else "unconfigured",
        "state_label": (
            f"{count} USB root" if count == 1 else f"{count} USB roots" if count else "not configured"
        ),
        "title": "USB Media",
        "subtitle": (
            "Browse read-only local media"
            if count
            else "Connect media under /run/media or /media, or set OPEN_MMI_USB_MEDIA_ROOTS"
        ),
        "read_only": True,
        "root_count": count,
        "roots": [{"id": root["id"], "label": root["label"]} for root in roots],
        "auto_discovery": _usb_bool_env("OPEN_MMI_USB_AUTO_DISCOVER", True),
    }


def _usb_parse_range(value: str | None, size: int) -> tuple[int, int] | None:
    if not value:
        return None
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or size <= 0:
        raise ValueError("Invalid byte range")
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise ValueError("Invalid byte range")
    if not start_text:
        suffix = int(end_text)
        if suffix <= 0:
            raise ValueError("Invalid byte range")
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(start_text)
        end = int(end_text) if end_text else size - 1
    if start < 0 or start >= size or end < start:
        raise ValueError("Range is outside the file")
    return start, min(end, size - 1)


def _usb_content_type(path: Path) -> str:
    import mimetypes

    explicit = {
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".mp3": "audio/mpeg",
        ".oga": "audio/ogg",
        ".ogg": "audio/ogg",
        ".opus": "audio/ogg",
        ".wav": "audio/wav",
        ".webm": "audio/webm",
    }
    return explicit.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _usb_open_file(item_id: str, *, artwork: bool = False):
    import errno
    import stat

    root_id, relative = _usb_decode_id(item_id)
    root = _usb_root_map().get(root_id)
    if not root:
        raise FileNotFoundError("USB media root is unavailable")
    if not relative.parts:
        raise FileNotFoundError("USB media file was not found")

    allowed = USB_ARTWORK_EXTENSIONS if artwork else USB_AUDIO_EXTENSIONS
    if relative.suffix.lower() not in allowed:
        raise FileNotFoundError("USB media file was not found")

    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory is None:
        raise RuntimeError("Descriptor-safe USB access is unavailable on this platform")
    cloexec = getattr(os, "O_CLOEXEC", 0)

    descriptors = []
    file_fd = None
    try:
        current_fd = os.open(
            str(root["path"]), os.O_RDONLY | directory | nofollow | cloexec
        )
        descriptors.append(current_fd)
        for part in relative.parts[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | directory | nofollow | cloexec,
                dir_fd=current_fd,
            )
            descriptors.append(next_fd)
            current_fd = next_fd
        file_fd = os.open(
            relative.parts[-1],
            os.O_RDONLY | nofollow | cloexec,
            dir_fd=current_fd,
        )
        opened = os.fstat(file_fd)
        if not stat.S_ISREG(opened.st_mode):
            raise FileNotFoundError("USB media file was not found")
        source = os.fdopen(file_fd, "rb", closefd=True)
        file_fd = None
        return root, relative, source, opened
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise PermissionError("USB media symlinks are not followed") from exc
        if exc.errno == errno.ENOENT:
            raise FileNotFoundError("USB media file was not found") from exc
        raise
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _usb_send_file(handler: Any, item_id: str, *, artwork: bool = False) -> None:
    started = False
    try:
        _root, relative, source, opened = _usb_open_file(item_id, artwork=artwork)
        path = Path(relative.name)
        size = opened.st_size
        with source:
            try:
                byte_range = _usb_parse_range(handler.headers.get("Range"), size)
            except ValueError:
                handler.send_response(416)
                handler.send_header("Content-Range", f"bytes */{size}")
                handler.send_header("Content-Length", "0")
                handler.end_headers()
                return
            start, end = byte_range if byte_range else (0, max(0, size - 1))
            length = end - start + 1 if size else 0

            handler.send_response(206 if byte_range else 200)
            started = True
            handler.send_header(
                "Content-Type",
                _usb_content_type(path) if not artwork else ({
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                }.get(path.suffix.lower(), "application/octet-stream")),
            )
            handler.send_header("Content-Length", str(length))
            handler.send_header("Accept-Ranges", "bytes")
            if byte_range:
                handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            handler.send_header("Cache-Control", "private, max-age=60" if artwork else "no-store")
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.send_header("Cross-Origin-Resource-Policy", "same-origin")
            handler.send_header("Referrer-Policy", "no-referrer")
            handler.end_headers()
            if length:
                source.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = source.read(min(USB_STREAM_CHUNK_BYTES, remaining))
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
                    remaining -= len(chunk)
    except ValueError as exc:
        if not started:
            handler.send_error(400, str(exc))
    except PermissionError as exc:
        if not started:
            handler.send_error(403, str(exc))
    except FileNotFoundError as exc:
        if not started:
            handler.send_error(404, str(exc))
    except (BrokenPipeError, ConnectionResetError):
        return
    except (OSError, RuntimeError):
        if not started:
            handler.send_error(500, "USB media file could not be read")
