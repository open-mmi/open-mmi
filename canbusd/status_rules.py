from typing import Any, Dict, Iterable, List, Optional


def parse_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 16) if value.lower().startswith("0x") else int(value)
    return int(value)


def _set_path(dst: Dict[str, Any], path: str, value: Any) -> None:
    parts = [p for p in path.split(".") if p]
    if not parts:
        return

    cur = dst
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _join_path(prefix: Optional[str], key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def parse_status_rules(items: Iterable[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    grouped: Dict[int, List[Dict[str, Any]]] = {}

    for item in items:
        rule = dict(item)
        cid = parse_int(rule["id"])
        rule["id"] = cid

        if "byte" in rule:
            rule["byte"] = int(rule["byte"])

        grouped.setdefault(cid, []).append(rule)

    return grouped


def _rule_byte(rule: Dict[str, Any], data: bytes, dlc: int) -> Optional[int]:
    byte_index = int(rule.get("byte", 0))
    if dlc <= byte_index:
        return None
    return data[byte_index]


def _evaluate_signed_magnitude(rule: Dict[str, Any], data: bytes, dlc: int) -> Dict[str, Any]:
    update: Dict[str, Any] = {}

    magnitude_cfg = rule.get("magnitude", {})
    sign_cfg = rule.get("sign_bit", {})

    low_byte = int(magnitude_cfg.get("low_byte", rule.get("bytes", [0, 1])[0]))
    high_byte = int(magnitude_cfg.get("high_byte", rule.get("bytes", [0, 1])[1]))

    sign_byte = int(sign_cfg.get("byte", high_byte))
    required = max(low_byte, high_byte, sign_byte)

    if dlc <= required:
        return update

    high_mask = parse_int(magnitude_cfg.get("high_mask", "0x7F"))
    sign_mask = parse_int(sign_cfg.get("mask", "0x80"))

    low = data[low_byte]
    high = data[high_byte]
    sign_raw = data[sign_byte]

    raw_full = (high << 8) | low
    magnitude = ((high & high_mask) << 8) | low

    center = rule.get("center")
    if center is not None and raw_full == parse_int(center):
        value = 0.0
    else:
        scale = float(rule.get("scale", 1))
        offset = float(rule.get("offset", 0))
        positive_when_set = sign_cfg.get("positive", "right") != "left"

        sign_is_set = bool(sign_raw & sign_mask)
        is_positive = sign_is_set if positive_when_set else not sign_is_set

        value = (magnitude * scale) + offset
        if not is_positive:
            value = -value

    if "round" in rule:
        value = round(value, int(rule["round"]))

    _set_path(update, rule["path"], value)

    if rule.get("raw_path"):
        _set_path(update, rule["raw_path"], raw_full)

    if rule.get("magnitude_raw_path"):
        _set_path(update, rule["magnitude_raw_path"], magnitude)

    if rule.get("direction_path"):
        if value > 0:
            direction = sign_cfg.get("positive", "right")
        elif value < 0:
            direction = "left" if sign_cfg.get("positive", "right") == "right" else "right"
        else:
            direction = "center"
        _set_path(update, rule["direction_path"], direction)

    return update


def evaluate_rule(rule: Dict[str, Any], data: bytes, dlc: int) -> Dict[str, Any]:
    kind = rule.get("type", "raw")
    update: Dict[str, Any] = {}

    if kind in ("signed_magnitude", "steering_angle"):
        return _evaluate_signed_magnitude(rule, data, dlc)

    raw = _rule_byte(rule, data, dlc)
    if raw is None:
        return update

    raw_path = rule.get("raw_path")
    if raw_path:
        _set_path(update, raw_path, raw)

    if kind == "raw":
        _set_path(update, rule["path"], raw)

    elif kind == "percent":
        value = max(0, min(100, raw))
        _set_path(update, rule["path"], value)

    elif kind == "bool":
        true_value = parse_int(rule["true"])
        false_value = parse_int(rule.get("false", 0)) if "false" in rule else None

        if raw == true_value:
            _set_path(update, rule["path"], True)
        elif false_value is not None and raw == false_value:
            _set_path(update, rule["path"], False)

    elif kind == "enum":
        values = {parse_int(k): v for k, v in rule.get("values", {}).items()}
        if raw in values:
            _set_path(update, rule["path"], values[raw])
        elif "default" in rule:
            _set_path(update, rule["path"], rule["default"])

    elif kind == "bitfield":
        prefix = rule.get("path")
        bools: Dict[str, bool] = {}

        for name, mask in rule.get("fields", {}).items():
            value = bool(raw & parse_int(mask))
            bools[name] = value
            _set_path(update, _join_path(prefix, name), value)

        for name, expected in rule.get("equals", {}).items():
            value = raw == parse_int(expected)
            bools[name] = value
            _set_path(update, _join_path(prefix, name), value)

        if rule.get("any"):
            _set_path(update, _join_path(prefix, rule["any"]), any(bools.values()))

        if rule.get("raw"):
            raw_key = rule["raw"] if isinstance(rule["raw"], str) else "raw"
            _set_path(update, _join_path(prefix, raw_key), raw)

    return update


def evaluate_status_rules(rules: Iterable[Dict[str, Any]], data: bytes, dlc: int) -> Dict[str, Any]:
    update: Dict[str, Any] = {}

    for rule in rules:
        partial = evaluate_rule(rule, data, dlc)
        _deep_merge(update, partial)

    return update


def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = value
    return dst
