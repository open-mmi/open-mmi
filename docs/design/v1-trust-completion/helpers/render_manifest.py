#!/usr/bin/env python3
"""Render commit cards from manifest.json, or check that generated cards match."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

def slug(card):
    return re.sub(r"[^a-z0-9]+","-",card["title"].lower()).strip("-")

def card_filename(card):
    return card["id"]+"-"+slug(card)+".md"

def bullets(items):
    return "\n".join("- "+item for item in items)

def render_card(card):
    dependencies = ", ".join(card["depends_on"]) or "No new-code prerequisite; inspect the actual baseline first."
    gates = ", ".join(card["closure_gates"]) or "No hardware gate for this specification-only card; required review still applies."
    existing = "\n".join("- "+path for path in card["read_paths"])
    proposed = "\n".join("- "+path for path in card["proposed_paths"]) or "None specified. Add a file only when the bounded implementation needs it, and record it."
    criteria = "\n".join("- [ ] **"+item["id"]+"** — "+item["text"] for item in card["acceptance_criteria"])
    return f"""# {card['id']} — {card['title']}

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: {card['phase']}
- Implementation prerequisites: {dependencies}
- Boundary closure gates: {gates}
- Required review: {card['required_review']}
- Suggested signed commit subject: {card['suggested_commit_subject']}
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

{card['boundary']}

## Minimum current-source read set

{existing}

## Proposed new paths — these do not yet exist merely because listed

{proposed}

## Required implementation

{bullets(card['implementation'])}

## Required behavioral and negative tests

{bullets(card['required_behavioral_tests'])}

Test command groups: **{' '.join(card['test_groups'])}**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

{criteria}

## Explicit exclusions

{bullets(card['out_of_scope'])}

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
"""

def render_index(cards):
    rows = ["# Commit index", "", "| ID | Commit boundary | Phase | Depends on | Closure |",
            "| --- | --- | --- | --- | --- |"]
    for card in cards:
        rows.append("| "+card["id"]+" | ["+card["title"]+"](commits/"+card_filename(card)+") | "+card["phase"]+" | "+(", ".join(card["depends_on"]) or "Baseline")+" | "+(", ".join(card["closure_gates"]) or "Review")+" |")
    rows.extend(["","These are implementation dependencies; pending hardware gates block closure/promotion, not explicitly approved independent DEV preparation.",
                 "All source paths are relative to the actual repository checkout. Proposed paths are labeled in each card.",""])
    return "\n".join(rows)

def render_gates(gates):
    rows = ["# Required qualification check IDs", "",
            "Generated from manifest.json. Read GATES.md for procedures and EVIDENCE_PROTOCOL.md for evidence rules.", "",
            "These are required checks, not completed results. Update progress.json only after actual observation and review.", ""]
    for gate in gates:
        rows.extend(["## "+gate["id"]+" — "+gate["title"],""])
        if gate.get("required_subject_commit"):
            rows.extend(["Pinned subject: "+gate["required_subject_commit"],""])
        for check in gate["checks"]:
            rows.extend(["- [ ] **"+check["id"]+"** — "+check["requirement"],
                         "  Required machine: "+", ".join(check["machine_roles"])+
                         "; evidence level: "+", ".join(check["levels"])+"."])
        rows.append("")
    return "\n".join(rows)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check",action="store_true")
    args = parser.parse_args(argv)
    manifest = json.loads((args.pack/"manifest.json").read_text(encoding="utf-8"))
    outputs = {args.pack/"INDEX.md":render_index(manifest["cards"]),
               args.pack/"GATE_CHECKLIST.md":render_gates(manifest["gates"])}
    outputs.update({args.pack/"commits"/card_filename(card):render_card(card) for card in manifest["cards"]})
    mismatches = []
    for path,text in outputs.items():
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                mismatches.append(str(path))
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text,encoding="utf-8")
    if mismatches:
        for path in mismatches:
            print("Generated handoff document differs: "+path)
        return 1
    print(("Checked" if args.check else "Rendered")+f" {len(outputs)} handoff documents.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
