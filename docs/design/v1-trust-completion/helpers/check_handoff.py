#!/usr/bin/env python3
"""Validate handoff bookkeeping, not security truth or hardware observations."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CODE_STATES = {"planned","in_progress","patch_ready","applied","validated","committed","complete","blocked","superseded"}
BOUNDARY_STATES = {"pending","in_progress","awaiting_evidence","complete","blocked","superseded"}
RESULT_STATES = {"not_run","passed","failed","blocked","unverified","not_applicable"}

def unique_object(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON value: "+value)))

def validate(manifest, progress, evidence):
    errors = []
    def need(condition, message):
        if not condition:
            errors.append(message)
    if not all(isinstance(item, dict) for item in (manifest, progress, evidence)):
        return ["manifest/progress/evidence roots must be objects"]
    need(manifest.get("schema_version") == 1, "unsupported manifest schema")
    need(progress.get("schema_version") == 1, "unsupported progress schema")
    need(evidence.get("schema_version") == 1, "unsupported evidence schema")
    need(progress.get("manifest_id") == manifest.get("manifest_id"), "progress manifest identity mismatch")
    cards_list = manifest.get("cards", [])
    if not isinstance(cards_list, list) or any(not isinstance(card,dict) for card in cards_list):
        return errors + ["manifest cards must be an array of objects"]
    cards = {card.get("id"):card for card in cards_list}
    need(len(cards) == len(cards_list), "duplicate card ID")
    gate_list = manifest.get("gates", [])
    if not isinstance(gate_list,list) or any(not isinstance(gate,dict) for gate in gate_list):
        return errors + ["manifest gates must be an array of objects"]
    gates = {gate.get("id"):gate for gate in gate_list}
    need(len(gates) == len(gate_list), "duplicate gate ID")
    records = evidence.get("records", [])
    if not isinstance(records,list) or any(not isinstance(item,dict) for item in records):
        return errors + ["evidence records must be an array of objects"]
    ev = {item.get("id"):item for item in records}
    need(len(ev) == len(records), "duplicate evidence ID")
    for eid,item in ev.items():
        need(isinstance(eid,str) and bool(eid), "empty evidence ID")
        need(item.get("result") in RESULT_STATES, f"{eid}: invalid evidence result")
        subject = item.get("subject_commit")
        if subject is not None:
            need(isinstance(subject,str) and bool(COMMIT_RE.fullmatch(subject)), f"{eid}: invalid subject commit")
        digest = item.get("source_projection_sha256")
        if digest is not None:
            need(isinstance(digest,str) and bool(DIGEST_RE.fullmatch(digest)), f"{eid}: invalid source projection")
        reuse = item.get("reuse_approved_for")
        if reuse is not None:
            need(isinstance(reuse,str) and bool(COMMIT_RE.fullmatch(reuse)), f"{eid}: invalid reuse subject")
            need(bool(item.get("reuse_rationale")) and bool(item.get("reuse_reviewed_by")),
                 f"{eid}: evidence reuse needs a rationale and reviewer")
    items = progress.get("items")
    gate_progress = progress.get("gates")
    if not isinstance(items,dict) or not isinstance(gate_progress,dict):
        return errors + ["progress items and gates must be objects"]
    need(set(items) == set(cards), "progress item IDs do not match manifest cards")
    need(set(gate_progress) == set(gates), "progress gate IDs do not match manifest gates")

    def check_refs(refs, owner, passed=False):
        if not isinstance(refs,list):
            errors.append(f"{owner}: evidence_ids must be an array")
            return []
        resolved = []
        for ref in refs:
            need(ref in ev, f"{owner}: unknown evidence ID {ref}")
            if ref in ev:
                resolved.append(ev[ref])
                if passed:
                    need(ev[ref].get("result") == "passed", f"{owner}: non-passing evidence cannot close criterion")
        return resolved

    # Dependency graph must remain a DAG, including deliberate future child cards.
    for cid,card in cards.items():
        need(isinstance(cid,str) and bool(re.fullmatch(r"P[0-9]{2}[a-z]?",cid)), f"{cid}: invalid plan card ID")
        for group in card.get("test_groups",[]):
            need(group in manifest.get("test_groups",{}), f"{cid}: unknown test group {group}")
        deps = card.get("depends_on", [])
        if not isinstance(deps,list):
            errors.append(f"{cid}: dependencies must be an array")
            continue
        for dep in deps:
            need(dep in cards and dep != cid, f"{cid}: invalid dependency {dep}")
        for gid in card.get("closure_gates", []):
            need(gid in gates, f"{cid}: unknown closure gate {gid}")
    visiting, visited = set(), set()
    def visit(cid):
        if cid in visiting:
            errors.append("card dependency cycle at " + str(cid))
            return
        if cid in visited:
            return
        visiting.add(cid)
        for dep in cards[cid].get("depends_on", []):
            if dep in cards:
                visit(dep)
        visiting.remove(cid)
        visited.add(cid)
    for cid in cards:
        visit(cid)

    for gid,gate in gates.items():
        state = gate_progress.get(gid, {})
        if not isinstance(state,dict):
            errors.append(f"{gid}: gate state must be an object")
            continue
        need(state.get("status") in RESULT_STATES, f"{gid}: invalid gate state")
        if gate.get("required_subject_commit") and state.get("subject_commit"):
            need(state["subject_commit"]==gate["required_subject_commit"], f"{gid}: wrong required baseline subject")
        checks = {item["id"]:item for item in gate.get("checks", [])}
        need(len(checks)==len(gate.get("checks", [])), f"{gid}: duplicate gate check ID")
        outcomes = state.get("checks", {})
        need(isinstance(outcomes,dict) and set(outcomes) == set(checks), f"{gid}: gate checks mismatch")
        if not isinstance(outcomes,dict):
            continue
        for check_id,definition in checks.items():
            outcome = outcomes.get(check_id,{})
            if not isinstance(outcome,dict):
                errors.append(f"{check_id}: outcome must be an object")
                continue
            need(outcome.get("status") in RESULT_STATES, f"{check_id}: invalid outcome")
            refs = check_refs(outcome.get("evidence_ids",[]), check_id, outcome.get("status")=="passed")
            if outcome.get("status")=="passed":
                need(bool(refs), f"{check_id}: passed check lacks evidence")
                subject = state.get("subject_commit")
                need(isinstance(subject,str) and bool(COMMIT_RE.fullmatch(subject)), f"{gid}: passed check requires gate subject commit")
                need(any(item.get("machine_role") in definition["machine_roles"]
                         and item.get("level") in definition["levels"]
                         and (item.get("subject_commit")==subject or item.get("reuse_approved_for")==subject)
                         for item in refs), f"{check_id}: evidence level/machine/subject does not satisfy this gate check")
        if state.get("status")=="passed":
            need(all(outcomes.get(key,{}).get("status")=="passed" for key in checks),
                 f"{gid}: cannot pass with an unresolved required check")
            need(state.get("review",{}).get("status")=="accepted"
                 and bool(state.get("review",{}).get("by")), f"{gid}: accepted review required")
    for cid,card in cards.items():
        item = items.get(cid,{})
        if not isinstance(item,dict):
            errors.append(f"{cid}: progress item must be an object")
            continue
        need(item.get("code_status") in CODE_STATES, f"{cid}: invalid code status")
        need(item.get("boundary_status") in BOUNDARY_STATES, f"{cid}: invalid boundary status")
        criteria = {criterion["id"]:criterion for criterion in card.get("acceptance_criteria",[])}
        need(len(criteria)==len(card.get("acceptance_criteria",[])), f"{cid}: duplicate criterion ID")
        outcomes = item.get("criteria",{})
        need(isinstance(outcomes,dict) and set(outcomes)==set(criteria), f"{cid}: acceptance criteria mismatch")
        if not isinstance(outcomes,dict):
            continue
        for key,outcome in outcomes.items():
            if not isinstance(outcome,dict):
                errors.append(f"{key}: outcome must be an object")
                continue
            need(outcome.get("status") in RESULT_STATES, f"{key}: invalid criterion result")
            refs = check_refs(outcome.get("evidence_ids",[]),key,outcome.get("status")=="passed")
            if outcome.get("status")=="passed":
                need(bool(refs), f"{key}: passed criterion lacks evidence")
        patch = item.get("patch")
        if patch is not None:
            need(isinstance(patch,dict), f"{cid}: patch metadata must be an object")
            if isinstance(patch,dict):
                need(bool(DIGEST_RE.fullmatch(str(patch.get("sha256","")))), f"{cid}: invalid patch digest")
                need(bool(COMMIT_RE.fullmatch(str(patch.get("base_commit","")))), f"{cid}: invalid patch base")
                need(bool(patch.get("file")), f"{cid}: missing patch filename")
        complete = item.get("code_status")=="complete" or item.get("boundary_status")=="complete"
        if complete:
            need(bool(COMMIT_RE.fullmatch(str(item.get("subject_code_commit","")))), f"{cid}: completed item requires actual code commit")
            need(bool(DIGEST_RE.fullmatch(str(item.get("tested_source_projection","")))), f"{cid}: completed item requires tested source projection")
            need(all(outcomes.get(key,{}).get("status")=="passed" for key in criteria), f"{cid}: completion has unresolved criteria")
            for key,outcome in outcomes.items():
                refs = [ev[ref] for ref in outcome.get("evidence_ids",[]) if ref in ev]
                need(any(record.get("subject_commit")==item.get("subject_code_commit")
                         or record.get("reuse_approved_for")==item.get("subject_code_commit") for record in refs),
                     f"{key}: completed criterion evidence is not bound to the code subject")
            need(item.get("review",{}).get("status")=="accepted" and bool(item.get("review",{}).get("by")),
                 f"{cid}: accepted reviewer record required")
            for gid in card.get("closure_gates",[]):
                need(gate_progress.get(gid,{}).get("status")=="passed", f"{cid}: closure gate {gid} is not passed")
            for dep in card.get("depends_on",[]):
                need(items.get(dep,{}).get("code_status") in {"committed","complete","superseded"},
                     f"{cid}: dependency {dep} lacks completed implementation")
        if item.get("code_status")=="superseded" or item.get("boundary_status")=="superseded":
            need(bool(item.get("superseded_by")) and bool(item.get("reason")), f"{cid}: supersession needs replacement and reason")
    final = items.get("P25",{})
    if final.get("boundary_status")=="complete":
        need(all(item.get("boundary_status") in {"complete","superseded"} for item in items.values()),
             "P25: full goal cannot close with an unresolved card boundary")
        need(all(state.get("status")=="passed" for state in gate_progress.values()),
             "P25: full goal cannot close with an unresolved gate")
    active = progress.get("active_card")
    need(active is None or active in cards, "unknown active card")
    return errors

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--repo", type=Path, help="Optional pinned source tree for checking existing read paths")
    args = parser.parse_args(argv)
    try:
        manifest = read_json(args.pack/"manifest.json")
        progress = read_json(args.pack/"progress.json")
        evidence = read_json(args.pack/"evidence-records.json")
        errors = validate(manifest,progress,evidence)
        if args.repo:
            for card in manifest["cards"]:
                for path in card["read_paths"]:
                    if not (args.repo/path).exists():
                        errors.append(f"{card['id']}: existing read path is absent: {path}")
    except (OSError,ValueError,KeyError,TypeError,RecursionError) as exc:
        print("INVALID: " + str(exc))
        return 2
    if errors:
        for error in errors:
            print("INVALID: " + error)
        return 1
    complete = sum(item["boundary_status"]=="complete" for item in progress["items"].values())
    passed = sum(item["status"]=="passed" for item in progress["gates"].values())
    print(f"Handoff structure valid: {len(manifest['cards'])} cards, {complete} boundaries complete, {passed}/{len(manifest['gates'])} gates passed.")
    print("This validates bookkeeping only; it does not authenticate evidence or prove a security boundary.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
