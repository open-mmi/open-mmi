"""Small semantic helpers for dashboard source and CSS contract tests."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_repo_text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def read_dashboard_styles() -> str:
    from tools.verify_css_split import CSS_MODULES, STATIC

    return "".join((STATIC / name).read_text(encoding="utf-8") for name in CSS_MODULES)


def marked_block(source: str, start: str, end: str) -> str:
    left = source.find(start)
    right = source.find(end, left + len(start))
    if left < 0 or right < 0:
        raise AssertionError(f"Missing marked block: {start} ... {end}")
    return source[left : right + len(end)]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def js_object_with_id(source: str, object_id: str) -> str:
    pattern = re.compile(
        r"\{(?=[^{}]*\bid\s*:\s*['\"]"
        + re.escape(object_id)
        + r"['\"])[^{}]*\}",
        re.S,
    )
    match = pattern.search(source)
    if not match:
        raise AssertionError(f"No flat JavaScript object with id={object_id!r}")
    return match.group(0)


def js_string_property(object_source: str, name: str) -> str:
    match = re.search(
        rf"\b{re.escape(name)}\s*:\s*(['\"])(.*?)\1",
        object_source,
        re.S,
    )
    if not match:
        raise AssertionError(f"Missing string property {name!r}")
    return match.group(2)


def js_bool_property(object_source: str, name: str) -> bool:
    match = re.search(rf"\b{re.escape(name)}\s*:\s*(true|false)\b", object_source)
    if not match:
        raise AssertionError(f"Missing boolean property {name!r}")
    return match.group(1) == "true"


def implemented_source_ids(source: str) -> set[str]:
    candidates: list[set[str]] = []
    for match in re.finditer(r"\[(?P<body>[^\[\]]*)\]\.includes\(\s*active\s*\)", source, re.S):
        values = set(re.findall(r"['\"]([a-z0-9_-]+)['\"]", match.group("body"), re.I))
        if values:
            candidates.append(values)
    if not candidates:
        raise AssertionError("Could not find implemented media-source membership check")
    return max(candidates, key=len)


def javascript_function_body(source: str, name: str) -> str:
    match = re.search(rf"\bfunction\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", source)
    if not match:
        raise AssertionError(f"Missing JavaScript function {name}()")
    opening = source.find("{", match.start())
    closing = _matching_brace(source, opening)
    return source[opening + 1 : closing]


def at_rule_block(source: str, header_pattern: str) -> str:
    match = re.search(header_pattern + r"\s*\{", source, re.I)
    if not match:
        raise AssertionError(f"Missing CSS at-rule matching {header_pattern!r}")
    opening = source.find("{", match.start())
    closing = _matching_brace(source, opening)
    return source[opening + 1 : closing]


def css_rule_bodies(source: str, selector: str) -> list[str]:
    wanted = normalize_space(selector)
    clean = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    bodies: list[str] = []
    for match in re.finditer(r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}", clean, re.S):
        selectors = [normalize_space(part) for part in match.group("selectors").split(",")]
        if wanted in selectors:
            bodies.append(match.group("body"))
    return bodies


def css_properties(source: str, selector: str) -> dict[str, str]:
    bodies = css_rule_bodies(source, selector)
    if not bodies:
        raise AssertionError(f"Missing CSS selector {selector!r}")
    properties: dict[str, str] = {}
    for body in bodies:
        for name, value in re.findall(r"([\w-]+)\s*:\s*([^;{}]+)\s*;", body):
            properties[name.lower()] = normalize_space(value).lower()
    return properties


def _matching_brace(source: str, opening: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = opening
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if char == "*" and nxt == "/":
                block_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char == "/" and nxt == "/":
            line_comment = True
            index += 2
            continue
        if char == "/" and nxt == "*":
            block_comment = True
            index += 2
            continue
        if char in "'\"`":
            quote = char
            index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise AssertionError("Unbalanced brace block")
