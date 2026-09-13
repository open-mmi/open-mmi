#!/usr/bin/env python3
"""Read-only Git/source identity capture. Output JSON; never deploy or alter Git."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EXCLUDED_PREFIX = "docs/design/v1-trust-completion/"
SOURCE_ROOTS = {
    ".github","actions","bindings","canbusd","docs","independent_checker",
    "open_mmi_telemetry","open_mmi_trust","packaging","powerd","scripts",
    "systemd","tests","tools","udev","ui","vehicles"
}
SOURCE_FILES = {
    "README.md","SECURITY.md","CONTRIBUTING.md","CHANGELOG.md","LICENSE",
    "pyproject.toml","package.json","package-lock.json","playwright.config.js"
}

def git(repo, *args, binary=False):
    result = subprocess.run(["git","-C",str(repo),*args],check=True,stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,timeout=30)
    return result.stdout if binary else result.stdout.decode("utf-8",errors="strict").rstrip("\n")

def display_path(value):
    """Abbreviate this user's home in exported paths; retain real paths for I/O."""
    path = Path(value)
    home = Path.home()
    for prefix in (home, home.resolve()):
        try:
            relative = path.relative_to(prefix)
        except ValueError:
            continue
        return str(Path("~") / relative)
    return str(path)

def failure_message(exc):
    """Describe an inspection failure without printing its command or filename."""
    if isinstance(exc,subprocess.CalledProcessError):
        return f"Git inspection failed with exit status {exc.returncode}."
    if isinstance(exc,subprocess.TimeoutExpired):
        return "Git inspection timed out."
    if isinstance(exc,OSError):
        return exc.strerror or type(exc).__name__
    return str(exc)

def source_identity(repo):
    raw = git(repo,"ls-files","--cached","--others","--exclude-standard","-z",binary=True)
    entries = []
    for name in sorted(set(part.decode("utf-8") for part in raw.split(b"\0") if part)):
        if name.startswith(EXCLUDED_PREFIX):
            continue
        if name.split("/",1)[0] not in SOURCE_ROOTS and name not in SOURCE_FILES:
            continue
        path = repo/name
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            entries.append({"path":name,"type":"deleted"})
            continue
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISLNK(metadata.st_mode):
            data = os.readlink(path).encode("utf-8")
            kind = "symlink"
            digest = hashlib.sha256(data).hexdigest()
        elif stat.S_ISREG(metadata.st_mode):
            kind = "file"
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
        else:
            raise ValueError("unsupported source entry type: " + name)
        entries.append({"path":name,"type":kind,"mode":mode,"sha256":"sha256:"+digest})
    normalized = json.dumps(entries,sort_keys=True,separators=(",",":")).encode("utf-8")
    return "sha256:"+hashlib.sha256(normalized).hexdigest(), entries

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",type=Path,default=Path.cwd())
    parser.add_argument("--machine",required=True,choices=["dev","tablet","isolated_vm","ci","assistant-workspace","independent_host"])
    parser.add_argument("--include-file-hashes",action="store_true")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    try:
        actual = Path(git(repo,"rev-parse","--show-toplevel")).resolve()
        if actual != repo:
            raise ValueError("--repo must identify the repository top level")
        digest,entries = source_identity(repo)
        payload = {
            "schema_version":1,
            "captured_at":datetime.now(timezone.utc).isoformat(),
            "machine_role":args.machine,
            "repo":display_path(repo),
            "branch":git(repo,"branch","--show-current") or "DETACHED",
            "head":git(repo,"rev-parse","HEAD"),
            "status_short":git(repo,"status","--short"),
            "python_executable":display_path(sys.executable),
            "python_version":platform.python_version(),
            "platform":platform.platform(),
            "source_projection_sha256":digest,
            "projection_files":len(entries),
            "projection_note":"Known source/test/build roots plus selected root files; excludes this handoff directory. Not installed-runtime attestation.",
            "installed_identity":"not_inspected",
            "tests":"not_run"
        }
        if args.include_file_hashes:
            payload["file_hashes"] = entries
        print(json.dumps(payload,indent=2,sort_keys=True))
        return 0
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print("State capture failed: "+failure_message(exc),file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
