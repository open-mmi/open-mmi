"""Build identity and versioned dashboard HTML helpers."""

from __future__ import annotations

import os
import re
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import quote

PACKAGE_NAME = "open-mmi"
DEFAULT_VERSION_FILE = Path("/opt/open-mmi/.version")
UNKNOWN_BUILD_ID = "unknown-dev"
_ASSET_PATTERN = re.compile(r'(?P<prefix>\b(?:href|src)=")(?P<path>/[^"?]+\.(?:css|js))(?P<suffix>")')


def _clean_build_id(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"[^A-Za-z0-9._+:-]+", "-", text).strip("-")


def _read_version_file(path: Path) -> str:
    try:
        return _clean_build_id(path.read_text(encoding="utf-8"))
    except OSError:
        return ""


def _find_repo_root(start: Path) -> Optional[Path]:
    resolved = start.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _git_build_id(repo_root: Optional[Path]) -> str:
    if repo_root is None:
        return ""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "describe", "--tags", "--always", "--dirty"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return _clean_build_id(completed.stdout)


def _package_build_id() -> str:
    try:
        package_version = metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return ""
    cleaned = _clean_build_id(package_version)
    return f"package-{cleaned}-dev" if cleaned else ""


def resolve_build_id(
    *,
    environ: Optional[Mapping[str, str]] = None,
    version_file: Optional[Path] = None,
    module_path: Optional[Path] = None,
) -> str:
    """Resolve the dashboard build identity using the documented precedence."""

    env = os.environ if environ is None else environ
    explicit = _clean_build_id(env.get("OPEN_MMI_BUILD_ID", ""))
    if explicit:
        return explicit

    configured_version_file = version_file
    if configured_version_file is None:
        configured_version_file = Path(env.get("OPEN_MMI_VERSION_FILE", str(DEFAULT_VERSION_FILE)))
    deployed = _read_version_file(configured_version_file)
    if deployed:
        return deployed

    source_path = module_path or Path(__file__)
    repository = _git_build_id(_find_repo_root(source_path.parent))
    if repository:
        return repository

    return _package_build_id() or UNKNOWN_BUILD_ID


def version_payload(build_id: str) -> dict[str, object]:
    cleaned = _clean_build_id(build_id) or UNKNOWN_BUILD_ID
    return {
        "api_version": 1,
        "build_id": cleaned,
        "frontend_id": cleaned,
        "reload_supported": cleaned != UNKNOWN_BUILD_ID,
    }


def render_index(template: str, frontend_id: str) -> str:
    """Inject one identity into the HTML metadata and every local JS/CSS URL."""

    cleaned = _clean_build_id(frontend_id) or UNKNOWN_BUILD_ID
    encoded = quote(cleaned, safe="._+:-")
    rendered = template.replace("__OPEN_MMI_FRONTEND_ID__", cleaned)

    def version_asset(match: re.Match[str]) -> str:
        return f'{match.group("prefix")}{match.group("path")}?v={encoded}{match.group("suffix")}'

    return _ASSET_PATTERN.sub(version_asset, rendered)
