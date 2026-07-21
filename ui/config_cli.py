"""Command-line configuration interface for Open MMI."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from canbusd import action_registry as vehicle_actions
from canbusd import profile_catalogue, profile_replay
from canbusd import event_registry as vehicle_events
from canbusd import status_registry as vehicle_statuses

from ui import (
    launcher,
    update_coordinator,
    update_readiness,
    vehicle_config_coordinator,
    vehicle_profile_conformance,
    vehicle_profile_scaffold,
    vehicle_setup,
)
from ui.configuration import (
    ConfigurationError,
    JELLYFIN_ENV_KEYS,
    dashboard_env_path,
    jellyfin_environment_status,
    jellyfin_values_from_payload,
    read_environment_file,
    restart_dashboard,
    write_environment_file,
)
from ui.web_dashboard import jellyfin, update_status


def _print(payload: Mapping[str, Any]) -> None:
    print(json.dumps(dict(payload), indent=2, sort_keys=True))


def _jellyfin_test(values: Mapping[str, str]) -> dict[str, Any]:
    config = jellyfin._jellyfin_config_from_mapping(values)
    return jellyfin._jellyfin_test_connection(config)


def _setup_jellyfin() -> dict[str, str]:
    existing = read_environment_file()
    current = jellyfin_environment_status(existing)
    url = input(f"Jellyfin URL [{current.get('url') or ''}]: ").strip() or str(current.get("url") or "")
    default_mode = current.get("auth_mode") or "username"
    mode = input(f"Authentication mode (username/token) [{default_mode}]: ").strip().lower() or str(default_mode)
    payload: dict[str, Any] = {
        "url": url,
        "auth_mode": mode,
        "user_id": input(f"User ID [{current.get('user_id') or ''}]: ").strip() or current.get("user_id", ""),
        "library_id": input(f"Library ID [{current.get('library_id') or ''}]: ").strip() or current.get("library_id", ""),
        "insecure_tls": input("Allow insecure TLS? [y/N]: ").strip().lower() in {"y", "yes"},
        "allow_global": input("Allow unscoped global API-key access? [y/N]: ").strip().lower() in {"y", "yes"},
    }
    if mode == "token":
        payload["username"] = input(f"Scope username [{current.get('username') or ''}]: ").strip() or current.get("username", "")
        payload["token"] = getpass.getpass("API token (leave blank to keep existing): ")
    else:
        payload["username"] = input(f"Username [{current.get('username') or ''}]: ").strip() or current.get("username", "")
        payload["password"] = getpass.getpass("Password (leave blank to keep existing): ")
    return jellyfin_values_from_payload(payload, existing)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Configure Open MMI")
    groups = parser.add_subparsers(dest="group", required=True)

    launcher_parser = groups.add_parser("launcher", help="configure launcher and graphical autostart")
    launcher_commands = launcher_parser.add_subparsers(dest="command", required=True)
    launcher_commands.add_parser("status")
    default = launcher_commands.add_parser("default")
    default.add_argument("ui", choices=("web", "tui"))
    autostart = launcher_commands.add_parser("autostart", aliases=("startup",))
    autostart.add_argument("state", choices=("enable", "disable"))

    jellyfin_parser = groups.add_parser("jellyfin", help="configure Jellyfin")
    jellyfin_commands = jellyfin_parser.add_subparsers(dest="command", required=True)
    jellyfin_commands.add_parser("status")
    jellyfin_commands.add_parser("setup")
    jellyfin_commands.add_parser("test")
    jellyfin_commands.add_parser("clear")
    jellyfin_commands.add_parser("import-env")

    dashboard_parser = groups.add_parser("dashboard", help="manage dashboard service")
    dashboard_commands = dashboard_parser.add_subparsers(dest="command", required=True)
    for action in ("status", "start", "stop", "restart", "enable", "disable"):
        dashboard_commands.add_parser(action)

    updates_parser = groups.add_parser("updates", help="inspect trusted update policy")
    updates_commands = updates_parser.add_subparsers(dest="command", required=True)
    updates_commands.add_parser("status")
    updates_commands.add_parser("check")
    updates_commands.add_parser("readiness")
    updates_commands.add_parser("coordinator")
    updates_commands.add_parser("prepare")
    updates_commands.add_parser("install")
    channel = updates_commands.add_parser("channel")
    channel.add_argument("channel", choices=("stable", "beta", "nightly"))

    vehicle_setup_parser = groups.add_parser(
        "vehicle-setup",
        help="inspect vehicle profiles, bindings and CAN runtime selection",
    )
    vehicle_setup_commands = vehicle_setup_parser.add_subparsers(
        dest="command",
        required=True,
    )
    vehicle_setup_commands.add_parser("status")
    vehicle_setup_commands.add_parser("catalogue")
    vehicle_events_parser = vehicle_setup_commands.add_parser(
        "events",
        help="inspect the canonical vehicle-event registry",
    )
    vehicle_events_parser.add_argument("event", nargs="?")
    vehicle_events_parser.add_argument(
        "--search",
        metavar="TEXT",
        help="search canonical events by human wording",
    )
    vehicle_events_parser.add_argument(
        "--check",
        metavar="EVENT",
        help="explain whether to reuse, migrate or propose an event",
    )
    vehicle_actions_parser = vehicle_setup_commands.add_parser(
        "actions",
        help="inspect the canonical vehicle-action registry",
    )
    vehicle_actions_parser.add_argument("action", nargs="?")
    vehicle_actions_parser.add_argument(
        "--search",
        metavar="TEXT",
        help="search canonical actions by human wording",
    )
    vehicle_actions_parser.add_argument(
        "--check",
        metavar="ACTION",
        help="explain whether to reuse, migrate or propose an action",
    )
    vehicle_statuses_parser = vehicle_setup_commands.add_parser(
        "statuses",
        help="inspect the canonical persistent vehicle-status registry",
    )
    vehicle_statuses_parser.add_argument("path", nargs="?")
    vehicle_statuses_parser.add_argument(
        "--search",
        metavar="TEXT",
        help="search canonical status paths by human wording",
    )
    vehicle_statuses_parser.add_argument(
        "--check",
        metavar="PATH",
        help="explain whether to reuse, migrate or propose a status path",
    )
    vehicle_conform = vehicle_setup_commands.add_parser(
        "conform",
        help="check maintained vehicle-profile identity, evidence and registry conformance",
    )
    vehicle_conform.add_argument(
        "profiles",
        nargs="*",
        help="maintained profile identifiers; omit to check the complete catalogue",
    )
    vehicle_conform.add_argument(
        "--root",
        type=Path,
        help="repository or installed Open MMI root; defaults to the maintained catalogue root",
    )
    vehicle_replay = vehicle_setup_commands.add_parser(
        "replay",
        help="replay deterministic mapping fixtures for one maintained profile",
    )
    vehicle_replay.add_argument("profile")
    vehicle_replay.add_argument(
        "--root",
        type=Path,
        help="repository or installed Open MMI root; defaults to the maintained catalogue root",
    )
    vehicle_scaffold = vehicle_setup_commands.add_parser(
        "scaffold",
        help="create and register an experimental maintained-profile source scaffold",
    )
    vehicle_scaffold.add_argument("--brand", required=True)
    vehicle_scaffold.add_argument("--model", required=True)
    vehicle_scaffold.add_argument("--generation", required=True)
    vehicle_scaffold.add_argument("--platform", required=True)
    vehicle_scaffold.add_argument("--year-from", type=int, required=True)
    vehicle_scaffold.add_argument("--year-to", type=int, required=True)
    vehicle_scaffold.add_argument("--id", dest="profile_id")
    vehicle_scaffold.add_argument("--display-name")
    vehicle_scaffold.add_argument("--maintainer", action="append")
    vehicle_scaffold.add_argument("--market-alias", action="append")
    vehicle_scaffold.add_argument("--default-bus", default="comfort")
    vehicle_scaffold.add_argument("--interface", default="can0")
    vehicle_scaffold.add_argument("--bitrate", type=int)
    vehicle_scaffold.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="source checkout root; defaults to the current directory",
    )
    vehicle_scaffold.add_argument("--dry-run", action="store_true")
    vehicle_setup_commands.add_parser(
        "coordinator",
        help="inspect the privileged vehicle configuration coordinator",
    )
    vehicle_preview = vehicle_setup_commands.add_parser(
        "preview",
        help="validate a non-mutating vehicle setup plan",
    )
    vehicle_preview.add_argument("vehicle")
    vehicle_preview.add_argument("bindings")
    vehicle_preview.add_argument(
        "--vehicle-source",
        choices=("maintained", "custom"),
        default="maintained",
    )
    vehicle_preview.add_argument(
        "--bindings-source",
        choices=("maintained", "custom"),
        default="maintained",
    )
    vehicle_preview.add_argument("--bus", required=True)
    vehicle_preview.add_argument("--interface", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.group == "launcher":
            path = launcher.default_config_path()
            if args.command == "status":
                _print(launcher.status_payload(launcher.load_config(path), path))
            elif args.command == "default":
                launcher.save_default_ui(args.ui, path)
                _print({"ok": True, "default_ui": args.ui, "config_path": str(path)})
            else:
                enabled = args.state == "enable"
                launcher.configure_open_at_login(enabled)
                _print({
                    "ok": True,
                    "open_at_login": launcher.open_at_login_enabled(),
                    "autostart_path": str(launcher.default_autostart_path()),
                })
            return 0

        if args.group == "dashboard":
            if args.command == "status":
                path = launcher.default_config_path()
                status = launcher.status_payload(launcher.load_config(path), path)
                _print({
                    "service": status["service"],
                    "service_active": status["service_active"],
                    "service_enabled": status["service_enabled"],
                    "dashboard_reachable": status["dashboard_reachable"],
                })
            elif args.command == "restart":
                restart_dashboard()
                _print({"ok": True, "service": "open-mmi-dashboard.service", "action": "restart"})
            else:
                launcher.configure_dashboard_service(args.command)
                _print({"ok": True, "service": "open-mmi-dashboard.service", "action": args.command})
            return 0

        if args.group == "updates":
            if args.command == "status":
                _print(update_status.status_payload())
            elif args.command == "check":
                _print(update_status.check_for_updates())
            elif args.command == "readiness":
                _print(update_readiness.readiness_payload(update_status.status_payload()))
            elif args.command == "coordinator":
                _print(update_coordinator.client_status())
            elif args.command == "prepare":
                _print(update_coordinator.client_prepare())
            elif args.command == "install":
                _print(update_coordinator.client_install())
            else:
                _print({"ok": True, **update_status.configure_channel(args.channel)})
            return 0

        if args.group == "vehicle-setup":
            if args.command == "coordinator":
                _print(vehicle_config_coordinator.client_status())
            elif args.command == "catalogue":
                _print(vehicle_setup.catalogue_payload())
            elif args.command == "conform":
                root = args.root or vehicle_setup.default_roots().maintained
                report = vehicle_profile_conformance.catalogue_report(
                    root, identifiers=args.profiles or None
                )
                _print(report)
                return 0 if report["valid"] else 1
            elif args.command == "replay":
                root = (args.root or vehicle_setup.default_roots().maintained).expanduser().resolve()
                resolved = profile_catalogue.resolve_profile(root, args.profile)
                fixture_path = Path(resolved["path"]).parent / "fixtures" / "mappings.v1.json"
                report = profile_replay.replay_files(Path(resolved["path"]), fixture_path)
                report["requested_profile"] = args.profile
                report["profile_id"] = resolved["id"]
                report["profile_path"] = resolved["relative_path"]
                report["fixture_path"] = fixture_path.relative_to(root).as_posix()
                _print(report)
                return 0 if report["valid"] else 1
            elif args.command == "scaffold":
                _print(
                    vehicle_profile_scaffold.scaffold_profile(
                        args.root,
                        brand=args.brand,
                        model=args.model,
                        generation=args.generation,
                        platform=args.platform,
                        year_from=args.year_from,
                        year_to=args.year_to,
                        profile_id=args.profile_id,
                        display_name=args.display_name,
                        maintainers=args.maintainer,
                        market_aliases=args.market_alias,
                        default_bus=args.default_bus,
                        interface=args.interface,
                        bitrate=args.bitrate,
                        dry_run=args.dry_run,
                    )
                )
            elif args.command == "events":
                selected = sum(
                    value is not None
                    for value in (args.event, args.search, args.check)
                )
                if selected > 1:
                    raise ValueError(
                        "choose one event, --search query, or --check event"
                    )
                if args.search is not None:
                    _print(vehicle_events.search_events(args.search))
                elif args.check is not None:
                    _print(vehicle_events.contribution_check(args.check))
                elif args.event:
                    _print(vehicle_events.event_definition(args.event))
                else:
                    _print(vehicle_events.registry_payload())
            elif args.command == "actions":
                selected = sum(
                    value is not None
                    for value in (args.action, args.search, args.check)
                )
                if selected > 1:
                    raise ValueError(
                        "choose one action, --search query, or --check action"
                    )
                if args.search is not None:
                    _print(vehicle_actions.search_actions(args.search))
                elif args.check is not None:
                    _print(vehicle_actions.contribution_check(args.check))
                elif args.action:
                    _print(vehicle_actions.action_definition(args.action))
                else:
                    _print(vehicle_actions.registry_payload())
            elif args.command == "statuses":
                selected = sum(
                    value is not None
                    for value in (args.path, args.search, args.check)
                )
                if selected > 1:
                    raise ValueError(
                        "choose one status path, --search query, or --check path"
                    )
                if args.search is not None:
                    _print(vehicle_statuses.search_statuses(args.search))
                elif args.check is not None:
                    _print(vehicle_statuses.contribution_check(args.check))
                elif args.path:
                    _print(vehicle_statuses.status_definition(args.path))
                else:
                    _print(vehicle_statuses.registry_payload())
            elif args.command == "preview":
                _print(
                    vehicle_config_coordinator.client_preview(
                        {
                            "vehicle": {
                                "source": args.vehicle_source,
                                "id": args.vehicle,
                            },
                            "bindings": {
                                "source": args.bindings_source,
                                "id": args.bindings,
                            },
                            "runtime": {
                                "active_bus": args.bus,
                                "buses": {
                                    args.bus: {"interface": args.interface}
                                },
                            },
                        }
                    )
                )
            else:
                _print(vehicle_setup.status_payload())
            return 0

        if args.command == "status":
            _print(jellyfin_environment_status())
            return 0
        if args.command == "clear":
            write_environment_file({})
            _print({"ok": True, "configured": False, "path": str(dashboard_env_path())})
            return 0
        if args.command == "setup":
            values = _setup_jellyfin()
            result = _jellyfin_test(values)
            write_environment_file(values)
            _print({"ok": True, "test": result, **jellyfin_environment_status(values)})
            return 0
        if args.command == "import-env":
            values = {key: os.environ.get(key, "") for key in JELLYFIN_ENV_KEYS}
            payload = jellyfin._jellyfin_config_from_mapping(values)
            if not payload.get("configured"):
                raise ConfigurationError("current environment does not contain complete Jellyfin credentials")
            _jellyfin_test(values)
            write_environment_file({key: value for key, value in values.items() if value})
            _print({"ok": True, **jellyfin_environment_status(values)})
            return 0
        values = read_environment_file()
        result = _jellyfin_test(values)
        _print({"ok": True, **result})
        return 0
    except (ConfigurationError, launcher.LauncherError, update_coordinator.CoordinatorError, vehicle_config_coordinator.CoordinatorError, update_status.UpdateStatusError, vehicle_actions.VehicleActionRegistryError, vehicle_events.VehicleEventRegistryError, profile_catalogue.VehicleProfileCatalogueError, profile_replay.VehicleProfileReplayError, vehicle_statuses.VehicleStatusRegistryError, vehicle_profile_conformance.VehicleProfileConformanceError, vehicle_profile_scaffold.VehicleProfileScaffoldError, vehicle_setup.VehicleSetupError, RuntimeError, ValueError) as exc:
        print(f"open-mmi-config: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
