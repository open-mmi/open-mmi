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
        rule["byte"] = int(rule.get("byte", 0))

        grouped.setdefault(cid, []).append(rule)

    return grouped


def evaluate_rule(rule: Dict[str, Any], raw: int) -> Dict[str, Any]:
    kind = rule.get("type", "raw")
    update: Dict[str, Any] = {}

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
        byte_index = int(rule.get("byte", 0))
        if dlc <= byte_index:
            continue

        partial = evaluate_rule(rule, data[byte_index])
        _deep_merge(update, partial)

    return update


def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = value
    return dst
