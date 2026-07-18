"""Read-only Linux runtime thermal, clock, and power diagnostics."""

from __future__ import annotations

import datetime as _datetime
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_SYS_ROOT = Path("/sys")
DEFAULT_PROC_ROOT = Path("/proc")
_RELEVANT_TRIP_TYPES = {"active", "passive", "hot", "critical"}


def _inside_root(path: Path, root: Path) -> bool:
    try:
        resolved_path = path.resolve()
        resolved_root = root.resolve()
    except OSError:
        return False
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def _read_text(path: Path, root: Path) -> Optional[str]:
    if not _inside_root(path, root):
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _read_int(path: Path, root: Path) -> Optional[int]:
    value = _read_text(path, root)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _khz_to_mhz(value: Optional[int]) -> Optional[float]:
    if value is None or value < 0:
        return None
    return round(value / 1000.0, 1)


def _millidegrees_to_c(value: Optional[int]) -> Optional[float]:
    if value is None or value <= -100000 or value >= 250000:
        return None
    return round(value / 1000.0, 2)


def _power_supply_temp_to_c(value: Optional[int]) -> Optional[float]:
    # Linux power_supply class temperatures use tenths of a degree Celsius.
    if value is None or value <= -1000 or value >= 2500:
        return None
    return round(value / 10.0, 1)


def _microunits(value: Optional[int], scale: float = 1_000_000.0) -> Optional[float]:
    if value is None:
        return None
    return round(value / scale, 4)


def _cpu_sort_key(path: Path) -> Tuple[int, str]:
    suffix = path.name[3:]
    return (int(suffix), path.name) if suffix.isdigit() else (10**9, path.name)


def _read_load(proc_root: Path) -> Optional[float]:
    value = _read_text(proc_root / "loadavg", proc_root)
    if value is None:
        return None
    try:
        return round(float(value.split()[0]), 2)
    except (IndexError, ValueError):
        return None


def _collect_cpu(sys_root: Path, proc_root: Path) -> Dict[str, Any]:
    cpu_root = sys_root / "devices/system/cpu"
    entries: List[Dict[str, Any]] = []
    for cpu_dir in sorted(cpu_root.glob("cpu[0-9]*"), key=_cpu_sort_key):
        cpufreq = cpu_dir / "cpufreq"
        current = _khz_to_mhz(_read_int(cpufreq / "scaling_cur_freq", sys_root))
        minimum = _khz_to_mhz(_read_int(cpufreq / "scaling_min_freq", sys_root))
        maximum = _khz_to_mhz(_read_int(cpufreq / "scaling_max_freq", sys_root))
        governor = _read_text(cpufreq / "scaling_governor", sys_root)
        if current is None and minimum is None and maximum is None and governor is None:
            continue
        entries.append(
            {
                "cpu": cpu_dir.name,
                "current_mhz": current,
                "minimum_mhz": minimum,
                "maximum_mhz": maximum,
                "governor": governor,
            }
        )

    currents = [entry["current_mhz"] for entry in entries if entry["current_mhz"] is not None]
    minimums = [entry["minimum_mhz"] for entry in entries if entry["minimum_mhz"] is not None]
    maximums = [entry["maximum_mhz"] for entry in entries if entry["maximum_mhz"] is not None]
    governors = sorted({entry["governor"] for entry in entries if entry["governor"]})
    load_1m = _read_load(proc_root)

    near_minimum_values: List[bool] = []
    for entry in entries:
        current = entry["current_mhz"]
        minimum = entry["minimum_mhz"]
        maximum = entry["maximum_mhz"]
        if current is None or minimum is None:
            continue
        span = max(0.0, (maximum or minimum) - minimum)
        tolerance = max(50.0, span * 0.05)
        near_minimum_values.append(current <= minimum + tolerance)

    online_count = len(entries)
    load_high = bool(
        load_1m is not None
        and online_count > 0
        and load_1m >= max(1.0, online_count * 0.75)
    )

    pstate_root = sys_root / "devices/system/cpu/intel_pstate"
    pstate: Dict[str, Any] = {}
    for name in ("status", "no_turbo", "min_perf_pct", "max_perf_pct"):
        raw = _read_text(pstate_root / name, sys_root)
        if raw is None:
            continue
        if name in {"no_turbo", "min_perf_pct", "max_perf_pct"}:
            try:
                pstate[name] = int(raw)
            except ValueError:
                pstate[name] = raw
        else:
            pstate[name] = raw

    return {
        "online_count": online_count,
        "current_mhz": currents,
        "average_mhz": round(statistics.fmean(currents), 1) if currents else None,
        "current_min_mhz": min(currents) if currents else None,
        "current_max_mhz": max(currents) if currents else None,
        "minimum_mhz": min(minimums) if minimums else None,
        "maximum_mhz": max(maximums) if maximums else None,
        "governors": governors,
        "load_1m": load_1m,
        "load_high": load_high,
        "near_minimum": bool(near_minimum_values) and all(near_minimum_values),
        "cpus": entries,
        "intel_pstate": pstate,
    }


def _trip_group(trips: Sequence[Dict[str, Any]], temperature: float, exceeded: bool) -> Optional[Dict[str, Any]]:
    candidates = [trip for trip in trips if trip["temperature_c"] <= temperature] if exceeded else [
        trip for trip in trips if trip["temperature_c"] > temperature
    ]
    if not candidates:
        return None
    target = max(trip["temperature_c"] for trip in candidates) if exceeded else min(
        trip["temperature_c"] for trip in candidates
    )
    types = sorted({trip["type"] for trip in candidates if trip["temperature_c"] == target})
    return {
        "temperature_c": target,
        "types": types,
        "margin_c": round(target - temperature, 2),
    }


def _zone_state(temperature: float, trips: Sequence[Dict[str, Any]]) -> Tuple[str, Optional[Dict[str, Any]]]:
    exceeded = [trip for trip in trips if trip["temperature_c"] <= temperature]
    exceeded_types = {trip["type"] for trip in exceeded}
    if "critical" in exceeded_types:
        return "critical", _trip_group(trips, temperature, True)
    if "hot" in exceeded_types:
        return "hot", _trip_group(trips, temperature, True)
    if exceeded_types.intersection({"active", "passive"}):
        return "thermal-limit-active", _trip_group(trips, temperature, True)

    upcoming = _trip_group(trips, temperature, False)
    if upcoming and upcoming["margin_c"] <= 3.0:
        return "warm", upcoming
    if upcoming:
        return "normal", upcoming
    if trips:
        return "normal", _trip_group(trips, temperature, True)
    return "temperature-only", None


def _thermal_severity(state: str) -> int:
    return {
        "critical": 5,
        "hot": 4,
        "thermal-limit-active": 3,
        "warm": 2,
        "normal": 1,
        "temperature-only": 0,
    }.get(state, -1)


def _collect_thermal(sys_root: Path) -> Dict[str, Any]:
    thermal_root = sys_root / "class/thermal"
    zones: List[Dict[str, Any]] = []
    for zone_dir in sorted(thermal_root.glob("thermal_zone*"), key=lambda path: path.name):
        if not _inside_root(zone_dir, sys_root):
            continue
        temperature = _millidegrees_to_c(_read_int(zone_dir / "temp", sys_root))
        if temperature is None:
            continue
        zone_type = _read_text(zone_dir / "type", sys_root) or zone_dir.name
        trips: List[Dict[str, Any]] = []
        for trip_temp_file in sorted(zone_dir.glob("trip_point_*_temp"), key=lambda path: path.name):
            prefix = trip_temp_file.name[: -len("_temp")]
            trip_type = (_read_text(zone_dir / f"{prefix}_type", sys_root) or "").lower()
            trip_temperature = _millidegrees_to_c(_read_int(trip_temp_file, sys_root))
            if trip_type not in _RELEVANT_TRIP_TYPES or trip_temperature is None:
                continue
            trips.append({"type": trip_type, "temperature_c": trip_temperature})
        trips.sort(key=lambda trip: (trip["temperature_c"], trip["type"]))
        state, relevant_trip = _zone_state(temperature, trips)
        zones.append(
            {
                "zone": zone_dir.name,
                "type": zone_type,
                "temperature_c": temperature,
                "state": state,
                "relevant_trip": relevant_trip,
                "trips": trips,
            }
        )

    selected: Optional[Dict[str, Any]] = None
    if zones:
        selected = sorted(
            zones,
            key=lambda zone: (
                -_thermal_severity(zone["state"]),
                abs((zone["relevant_trip"] or {"margin_c": 9999})["margin_c"]),
                -zone["temperature_c"],
                zone["type"],
            ),
        )[0]

    cooling_devices: List[Dict[str, Any]] = []
    for device_dir in sorted(thermal_root.glob("cooling_device*"), key=lambda path: path.name):
        if not _inside_root(device_dir, sys_root):
            continue
        device_type = _read_text(device_dir / "type", sys_root)
        current = _read_int(device_dir / "cur_state", sys_root)
        maximum = _read_int(device_dir / "max_state", sys_root)
        if device_type is None and current is None and maximum is None:
            continue
        cooling_devices.append(
            {
                "device": device_dir.name,
                "type": device_type or device_dir.name,
                "current_state": current,
                "maximum_state": maximum,
            }
        )

    return {
        "summary": selected["state"] if selected else "unavailable",
        "selected_zone": selected["type"] if selected else None,
        "temperature_c": selected["temperature_c"] if selected else None,
        "relevant_trip": selected["relevant_trip"] if selected else None,
        "zones": zones,
        "cooling_devices": cooling_devices,
    }


def _collect_power(sys_root: Path) -> Dict[str, Any]:
    power_root = sys_root / "class/power_supply"
    supplies: List[Dict[str, Any]] = []
    for supply_dir in sorted(power_root.glob("*"), key=lambda path: path.name):
        if not _inside_root(supply_dir, sys_root):
            continue
        supply_type = _read_text(supply_dir / "type", sys_root)
        if supply_type is None:
            continue
        raw_status = _read_text(supply_dir / "status", sys_root)
        supply = {
            "name": supply_dir.name,
            "type": supply_type,
            "online": None,
            "status": raw_status,
            "capacity_percent": _read_int(supply_dir / "capacity", sys_root),
            "temperature_c": _power_supply_temp_to_c(_read_int(supply_dir / "temp", sys_root)),
            "energy_wh": _microunits(_read_int(supply_dir / "energy_now", sys_root)),
            "energy_full_wh": _microunits(_read_int(supply_dir / "energy_full", sys_root)),
            "reported_power_w": _microunits(_read_int(supply_dir / "power_now", sys_root)),
            "reported_current_a": _microunits(_read_int(supply_dir / "current_now", sys_root)),
            "voltage_v": _microunits(_read_int(supply_dir / "voltage_now", sys_root)),
        }
        online = _read_int(supply_dir / "online", sys_root)
        if online is not None:
            supply["online"] = bool(online)
        supplies.append(supply)

    batteries = [supply for supply in supplies if supply["type"].lower() == "battery"]
    external = [supply for supply in supplies if supply["type"].lower() != "battery"]
    online_values = [supply["online"] for supply in external if supply["online"] is not None]
    ac_online = any(online_values) if online_values else None

    def battery_score(supply: Dict[str, Any]) -> Tuple[int, int, int, str]:
        name = str(supply.get("name") or "").upper()
        has_energy = int(supply.get("energy_wh") is not None or supply.get("energy_full_wh") is not None)
        system_name = int(name.startswith(("BAT", "BATT", "CMB")))
        has_capacity = int(supply.get("capacity_percent") is not None)
        return (has_energy, system_name, has_capacity, name)

    battery = max(batteries, key=battery_score) if batteries else None
    status = str((battery or {}).get("status") or "").strip()
    status_lower = status.lower()

    if ac_online is False:
        charging_state = "on-battery"
    elif ac_online is True and status_lower == "charging":
        charging_state = "charging"
    elif ac_online is True and status_lower in {"full", "fully charged"}:
        charging_state = "full"
    elif ac_online is True and status:
        charging_state = "not-charging"
    elif ac_online is True:
        charging_state = "ac-connected"
    else:
        charging_state = "unknown"

    return {
        "ac_online": ac_online,
        "battery_status": status or None,
        "capacity_percent": (battery or {}).get("capacity_percent"),
        "energy_wh": (battery or {}).get("energy_wh"),
        "charging_state": charging_state,
        "supplies": supplies,
    }


def runtime_diagnostics_payload(
    *,
    sys_root: Path = DEFAULT_SYS_ROOT,
    proc_root: Path = DEFAULT_PROC_ROOT,
    sampled_at: Optional[_datetime.datetime] = None,
) -> Dict[str, Any]:
    """Collect one read-only runtime sample from fixed Linux system roots."""

    moment = sampled_at or _datetime.datetime.now(_datetime.timezone.utc)
    return {
        "api_version": 1,
        "sampled_at": moment.isoformat(),
        "cpu": _collect_cpu(Path(sys_root), Path(proc_root)),
        "thermal": _collect_thermal(Path(sys_root)),
        "power": _collect_power(Path(sys_root)),
    }
