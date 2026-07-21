"""Safe maintained vehicle-profile scaffolding for source checkouts.

The scaffold command creates an experimental, non-claiming profile envelope and
registers its stable identity in the checked maintained catalogue. It deliberately
does not invent CAN mappings, qualification evidence, or hardware support.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import stat
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from canbusd import profile_catalogue
from ui import vehicle_profile_conformance, vehicle_setup


MAX_DISPLAY_BYTES = 128
MAX_COMPONENT_BYTES = 48
MAX_MAINTAINERS = 16
MAX_MARKET_ALIASES = 32
COMPONENT_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
BUS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
INTERFACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,14}$")


class VehicleProfileScaffoldError(ValueError):
    """Raised when a maintained profile cannot be scaffolded safely."""


def _bounded_display(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise VehicleProfileScaffoldError(f"{field} must be text")
    result = value.strip()
    if (
        not result
        or len(result.encode("utf-8")) > MAX_DISPLAY_BYTES
        or any(ord(character) < 32 for character in result)
    ):
        raise VehicleProfileScaffoldError(
            f"{field} must be a non-empty bounded human-readable value"
        )
    if "/" in result or "\\" in result or result.startswith("~") or ".." in result:
        raise VehicleProfileScaffoldError(f"{field} must not contain path syntax")
    return result


def _slug(value: str, *, field: str) -> str:
    display = _bounded_display(value, field=field)
    ascii_text = (
        unicodedata.normalize("NFKD", display)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    result = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if (
        not result
        or not COMPONENT_RE.fullmatch(result)
        or len(result.encode("utf-8")) > MAX_COMPONENT_BYTES
    ):
        raise VehicleProfileScaffoldError(
            f"{field} cannot be converted to a safe lowercase path component"
        )
    return result


def _text_list(
    values: Optional[Iterable[str]],
    *,
    field: str,
    maximum: int,
    default: Optional[Sequence[str]] = None,
) -> list[str]:
    source = list(values) if values is not None else list(default or ())
    if len(source) > maximum:
        raise VehicleProfileScaffoldError(
            f"{field} may contain at most {maximum} values"
        )
    result = [_bounded_display(value, field=field) for value in source]
    if len(set(result)) != len(result):
        raise VehicleProfileScaffoldError(f"{field} must not contain duplicates")
    return result


def _year_range(year_from: int, year_to: int) -> tuple[int, int]:
    if (
        isinstance(year_from, bool)
        or isinstance(year_to, bool)
        or not isinstance(year_from, int)
        or not isinstance(year_to, int)
        or not 1886 <= year_from <= year_to <= 2100
    ):
        raise VehicleProfileScaffoldError(
            "model years must be an ordered inclusive range from 1886 to 2100"
        )
    return year_from, year_to


def _checked_root(root: Path) -> tuple[Path, Path, Path]:
    source_root = root.expanduser().resolve()
    vehicles = source_root / "vehicles"
    catalogue_path = vehicles / "catalogue.v1.json"
    template = vehicles / "_template"

    for path, label, expected_directory in (
        (vehicles, "vehicles root", True),
        (template, "vehicle template", True),
        (catalogue_path, "maintained vehicle catalogue", False),
    ):
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise VehicleProfileScaffoldError(
                f"{label} is missing from the source checkout: {path}"
            ) from exc
        valid = stat.S_ISDIR(metadata.st_mode) if expected_directory else stat.S_ISREG(metadata.st_mode)
        if not valid or stat.S_ISLNK(metadata.st_mode):
            expected = "directory" if expected_directory else "regular file"
            raise VehicleProfileScaffoldError(f"{label} must be a non-symlink {expected}")

    for relative in (
        "config.template.json",
        "fixtures/README.md",
        "evidence/README.md",
        "notes/README.md",
    ):
        path = template / relative
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise VehicleProfileScaffoldError(
                f"vehicle template is incomplete: {path}"
            ) from exc
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise VehicleProfileScaffoldError(
                f"vehicle template file must be a non-symlink regular file: {path}"
            )
    return source_root, catalogue_path, template


def _reject_symlink_parents(base: Path, destination: Path) -> None:
    try:
        relative = destination.relative_to(base)
    except ValueError as exc:
        raise VehicleProfileScaffoldError(
            "scaffold destination escapes the maintained vehicles tree"
        ) from exc
    current = base
    for part in relative.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise VehicleProfileScaffoldError(
                f"cannot inspect scaffold destination component: {current}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise VehicleProfileScaffoldError(
                f"scaffold destination contains a symlink: {current}"
            )


def _profile_document(
    *,
    profile_id: str,
    display_name: str,
    manufacturer: str,
    model: str,
    generation: str,
    platform: str,
    market_aliases: Sequence[str],
    year_from: int,
    year_to: int,
    maintainers: Sequence[str],
    default_bus: str,
    interface: str,
    bitrate: Optional[int],
) -> dict[str, Any]:
    bus: dict[str, Any] = {
        "interface": interface,
        "capture_point": "TODO: document the physical capture point.",
        "provisioning": "manual",
        "bring_up": False,
        "notes": "Experimental scaffold only; confirm bus details from real captures.",
    }
    if bitrate is not None:
        if isinstance(bitrate, bool) or not isinstance(bitrate, int) or not 1 <= bitrate <= 10_000_000:
            raise VehicleProfileScaffoldError(
                "bitrate must be between 1 and 10000000"
            )
        bus["bitrate"] = bitrate

    return {
        "schema_version": 1,
        "metadata": {
            "id": profile_id,
            "display_name": display_name,
            "manufacturer": manufacturer,
            "model": model,
            "generation": generation,
            "platform": platform,
            "market_aliases": list(market_aliases),
            "model_years": {"from": year_from, "to": year_to},
            "maturity": "experimental",
            "license": "GPL-3.0-only",
            "maintainers": list(maintainers),
            "qualification": {
                "level": "none",
                "last_tested": None,
                "scope": [],
                "evidence": [],
            },
            "limitations": [
                "This scaffold does not claim any confirmed CAN mappings or hardware support."
            ],
        },
        "default_bus": default_bus,
        "can_buses": {default_bus: bus},
        "rules": [],
        "presence": [],
        "status": [],
    }


def _profile_readme(
    *,
    display_name: str,
    profile_id: str,
    relative_directory: str,
    year_from: int,
    year_to: int,
) -> str:
    return f"""# {display_name}

This directory is an **experimental maintained-profile scaffold**. It records the
intended identity and contribution layout, but it does not claim that Open MMI
currently supports this vehicle or that any CAN mapping has been confirmed.

## Identity

- Stable profile ID: `{profile_id}`
- Maintained path: `{relative_directory}/config.json`
- Model years: {year_from}–{year_to}
- Maturity: `experimental`
- Qualification: `none`

## Before adding mappings

1. Record the real capture point, interface and bitrate in `config.json`.
2. Keep provisional CAN observations in `notes/`.
3. Reuse canonical events and status paths where their meanings match.
4. Add deterministic `fixtures/mappings.v1.json` coverage before candidate status.
5. Add reviewable evidence without VINs, credentials or personal data.
6. Run `open-mmi-config vehicle-setup conform --root .`.
7. Regenerate `docs/vehicle-catalogue.md` and the capability matrix.

A scaffold is not evidence of reverse engineering, compatibility or hardware
qualification.
"""


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def scaffold_profile(
    root: Path,
    *,
    brand: str,
    model: str,
    generation: str,
    platform: str,
    year_from: int,
    year_to: int,
    profile_id: Optional[str] = None,
    display_name: Optional[str] = None,
    maintainers: Optional[Iterable[str]] = None,
    market_aliases: Optional[Iterable[str]] = None,
    default_bus: str = "comfort",
    interface: str = "can0",
    bitrate: Optional[int] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create and register one experimental maintained-profile scaffold."""

    source_root, catalogue_path, template = _checked_root(root)
    vehicles = source_root / "vehicles"

    manufacturer = _bounded_display(brand, field="brand")
    model_name = _bounded_display(model, field="model")
    generation_name = _bounded_display(generation, field="generation")
    platform_name = _bounded_display(platform, field="platform")
    brand_slug = _slug(brand, field="brand")
    model_slug = _slug(model, field="model")
    generation_slug = _slug(generation, field="generation")
    platform_slug = _slug(platform, field="platform")
    year_from, year_to = _year_range(year_from, year_to)

    generated_id = f"{brand_slug}-{model_slug}-{generation_slug}-{platform_slug}"
    selected_id = profile_id or generated_id
    if not isinstance(selected_id, str) or not profile_catalogue.IDENTIFIER_RE.fullmatch(selected_id):
        raise VehicleProfileScaffoldError(
            "profile ID must be a lowercase identifier of at most 64 characters"
        )

    selected_display_name = _bounded_display(
        display_name
        or f"{manufacturer} {model_name} {generation_name} ({platform_name})",
        field="display name",
    )
    selected_maintainers = _text_list(
        maintainers,
        field="maintainer",
        maximum=MAX_MAINTAINERS,
        default=("Open MMI contributors",),
    )
    selected_aliases = _text_list(
        market_aliases,
        field="market alias",
        maximum=MAX_MARKET_ALIASES,
    )
    if not isinstance(default_bus, str) or not BUS_RE.fullmatch(default_bus):
        raise VehicleProfileScaffoldError("default bus must be a valid identifier")
    if not isinstance(interface, str) or not INTERFACE_RE.fullmatch(interface):
        raise VehicleProfileScaffoldError("interface must be a valid Linux interface name")

    generation_directory = f"{generation_slug}-{platform_slug}"
    relative_directory = f"vehicles/{brand_slug}/{model_slug}/{generation_directory}"
    relative_config = f"{brand_slug}/{model_slug}/{generation_directory}/config.json"
    destination = source_root / relative_directory
    _reject_symlink_parents(vehicles, destination)
    if destination.exists() or destination.is_symlink():
        raise VehicleProfileScaffoldError(
            f"profile destination already exists: {destination}"
        )

    existing_tree = profile_catalogue.verify_tree(source_root)
    if not existing_tree["valid"]:
        raise VehicleProfileScaffoldError(
            "maintained catalogue must be valid before scaffolding: "
            + "; ".join(existing_tree["issues"])
        )
    catalogue = profile_catalogue.load_catalogue(catalogue_path)
    original_catalogue = catalogue_path.read_bytes()
    original_catalogue_mode = stat.S_IMODE(catalogue_path.stat().st_mode)
    for canonical_id, entry in catalogue["profiles"].items():
        if selected_id == canonical_id or selected_id in entry["aliases"]:
            raise VehicleProfileScaffoldError(
                f"profile identity is already registered: {selected_id}"
            )
    updated_catalogue = copy.deepcopy(catalogue)
    updated_catalogue["profiles"][selected_id] = {
        "path": relative_config,
        "aliases": [],
    }
    try:
        normalized_catalogue = profile_catalogue.normalize_catalogue(updated_catalogue)
    except profile_catalogue.VehicleProfileCatalogueError as exc:
        raise VehicleProfileScaffoldError(str(exc)) from exc

    document = _profile_document(
        profile_id=selected_id,
        display_name=selected_display_name,
        manufacturer=manufacturer,
        model=model_name,
        generation=generation_name,
        platform=platform_name,
        market_aliases=selected_aliases,
        year_from=year_from,
        year_to=year_to,
        maintainers=selected_maintainers,
        default_bus=default_bus,
        interface=interface,
        bitrate=bitrate,
    )
    metadata_validation = vehicle_profile_conformance.validate_metadata(
        document, expected_id=selected_id
    )
    profile_validation = vehicle_setup.validate_profile(document)
    if not metadata_validation["valid"] or not profile_validation["valid"]:
        raise VehicleProfileScaffoldError(
            "generated scaffold did not pass profile validation"
        )

    created = [
        f"{relative_directory}/config.json",
        f"{relative_directory}/README.md",
        f"{relative_directory}/fixtures/README.md",
        f"{relative_directory}/evidence/README.md",
        f"{relative_directory}/notes/README.md",
    ]
    result = {
        "ok": True,
        "dry_run": bool(dry_run),
        "profile_id": selected_id,
        "relative_directory": relative_directory,
        "catalogue_path": "vehicles/catalogue.v1.json",
        "created": created,
        "next_steps": [
            "Review the generated identity and bus placeholders.",
            "Add only evidence-backed CAN mappings and reverse-engineering notes.",
            "Run open-mmi-config vehicle-setup conform --root .",
            "Run python tools/generate_vehicle_catalogue_docs.py",
        ],
    }
    if dry_run:
        return result

    temporary_root = Path(tempfile.mkdtemp(prefix=".scaffold-", dir=vehicles))
    staged_profile = temporary_root / "profile"
    staged_catalogue = temporary_root / "catalogue.v1.json"
    moved_profile = False
    catalogue_replaced = False
    try:
        staged_profile.mkdir()
        _write_json(staged_profile / "config.json", document)
        (staged_profile / "README.md").write_text(
            _profile_readme(
                display_name=selected_display_name,
                profile_id=selected_id,
                relative_directory=relative_directory,
                year_from=year_from,
                year_to=year_to,
            ),
            encoding="utf-8",
        )
        for directory in ("fixtures", "evidence", "notes"):
            target = staged_profile / directory
            target.mkdir()
            shutil.copyfile(template / directory / "README.md", target / "README.md")
        _write_json(staged_catalogue, normalized_catalogue)
        staged_catalogue.chmod(stat.S_IMODE(catalogue_path.stat().st_mode))

        destination.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_parents(vehicles, destination)
        if destination.exists() or destination.is_symlink():
            raise VehicleProfileScaffoldError(
                f"profile destination appeared during scaffolding: {destination}"
            )
        os.replace(staged_profile, destination)
        moved_profile = True
        os.replace(staged_catalogue, catalogue_path)
        catalogue_replaced = True
        final_tree = profile_catalogue.verify_tree(source_root)
        if not final_tree["valid"]:
            raise VehicleProfileScaffoldError(
                "generated scaffold left an invalid catalogue tree: "
                + "; ".join(final_tree["issues"])
            )
    except Exception as exc:
        if catalogue_replaced:
            restore_path = temporary_root / "catalogue.restore.json"
            restore_path.write_bytes(original_catalogue)
            restore_path.chmod(original_catalogue_mode)
            os.replace(restore_path, catalogue_path)
        if moved_profile and destination.exists() and not destination.is_symlink():
            shutil.rmtree(destination)
        if isinstance(exc, VehicleProfileScaffoldError):
            raise
        raise VehicleProfileScaffoldError(
            f"could not create vehicle profile scaffold: {exc}"
        ) from exc
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)

    return result
