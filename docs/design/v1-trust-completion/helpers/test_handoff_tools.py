"""Behavioral checks of the handoff helpers, with no target/vehicle access."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import capture_state
import check_handoff
import render_manifest

PACK = Path(__file__).resolve().parents[1]
SHA = "1" * 40
OTHER_SHA = "2" * 40
DIGEST = "sha256:" + "a" * 64

class HandoffValidationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = check_handoff.read_json(PACK/"manifest.json")
        self.progress = check_handoff.read_json(PACK/"progress.json")
        self.evidence = check_handoff.read_json(PACK/"evidence-records.json")
        # Helpers must continue to test the format after real progress is recorded.
        for item in self.progress["items"].values():
            item.update(code_status="planned", boundary_status="pending", patch=None)
            for outcome in item["criteria"].values():
                outcome.update(status="not_run", evidence_ids=[])
        for gate in self.progress["gates"].values():
            gate.update(status="not_run", subject_commit=None, review={"status":"pending","by":None})
            for outcome in gate["checks"].values():
                outcome.update(status="not_run", evidence_ids=[])

    def errors(self):
        return check_handoff.validate(self.manifest,self.progress,self.evidence)

    def assertInvalid(self, phrase):
        self.assertTrue(any(phrase in value for value in self.errors()), self.errors())

    def passing_record(self, eid="E-TEST", subject=SHA, machine="tablet", level="installed-integration"):
        record = {"id":eid,"result":"passed","subject_commit":subject,
                  "source_projection_sha256":DIGEST,"machine_role":machine,"level":level}
        self.evidence["records"].append(record)
        return record

    def test_initial_structurally_valid(self):
        self.assertEqual([],self.errors())

    def test_planned_work_cannot_be_closed_without_evidence(self):
        self.progress["items"]["P01"]["boundary_status"]="complete"
        self.assertInvalid("completion has unresolved criteria")
        self.assertInvalid("closure gate G1 is not passed")

    def test_unknown_evidence_rejected(self):
        self.progress["items"]["P01"]["criteria"]["P01-A01"].update(status="passed",evidence_ids=["missing"])
        self.assertInvalid("unknown evidence ID")

    def test_failed_evidence_cannot_close_criterion(self):
        self.evidence["records"].append({"id":"E-FAIL","result":"failed"})
        self.progress["items"]["P01"]["criteria"]["P01-A01"].update(status="passed",evidence_ids=["E-FAIL"])
        self.assertInvalid("non-passing evidence")

    def test_duplicate_evidence_rejected(self):
        record=self.passing_record()
        self.evidence["records"].append(copy.deepcopy(record))
        self.assertInvalid("duplicate evidence ID")

    def test_dependency_cycle_rejected(self):
        self.manifest["cards"][0]["depends_on"]=["P02"]
        self.assertInvalid("dependency cycle")

    def test_gate_requires_all_checks_and_review(self):
        self.progress["gates"]["G1"]["status"]="passed"
        self.assertInvalid("unresolved required check")
        self.assertInvalid("accepted review required")

    def test_unit_result_cannot_pass_installed_gate(self):
        self.passing_record(machine="dev",level="unit-tested")
        self.progress["gates"]["G1"]["subject_commit"]=SHA
        self.progress["gates"]["G1"]["checks"]["G1-01"].update(status="passed",evidence_ids=["E-TEST"])
        self.assertInvalid("evidence level/machine/subject")

    def test_correct_gate_evidence_accepted(self):
        self.passing_record()
        self.progress["gates"]["G1"]["subject_commit"]=SHA
        self.progress["gates"]["G1"]["checks"]["G1-01"].update(status="passed",evidence_ids=["E-TEST"])
        self.assertEqual([],self.errors())

    def test_machine_and_subject_must_match_on_same_record(self):
        self.passing_record(eid="E-WRONG-SUBJECT",subject=OTHER_SHA)
        self.passing_record(eid="E-WRONG-MACHINE",machine="dev",level="unit-tested")
        self.progress["gates"]["G1"]["subject_commit"]=SHA
        self.progress["gates"]["G1"]["checks"]["G1-01"].update(
            status="passed",evidence_ids=["E-WRONG-SUBJECT","E-WRONG-MACHINE"])
        self.assertInvalid("evidence level/machine/subject")

    def test_reused_evidence_requires_review_and_scope(self):
        record=self.passing_record(subject=OTHER_SHA)
        record["reuse_approved_for"]=SHA
        self.assertInvalid("evidence reuse needs")
        record.update(reuse_rationale="Only evidence-record documentation changed.",reuse_reviewed_by="fixture reviewer")
        self.assertEqual([],self.errors())

    def test_g0_cannot_silently_change_subject(self):
        self.progress["gates"]["G0"]["subject_commit"]=OTHER_SHA
        self.assertInvalid("wrong required baseline subject")

    def test_patch_needs_real_digest_and_base(self):
        self.progress["items"]["P01"]["patch"]={"file":"example.patch","sha256":"TODO","base_commit":"TODO"}
        self.assertInvalid("invalid patch digest")
        self.assertInvalid("invalid patch base")

    def test_acceptance_id_cannot_disappear(self):
        self.progress["items"]["P01"]["criteria"].pop("P01-A01")
        self.assertInvalid("acceptance criteria mismatch")

    def test_supersession_needs_reason_and_replacement(self):
        self.progress["items"]["P01"]["code_status"]="superseded"
        self.assertInvalid("supersession needs")

    def test_final_goal_requires_every_boundary_and_gate(self):
        self.progress["items"]["P25"]["boundary_status"]="complete"
        self.assertInvalid("full goal cannot close with an unresolved card")
        self.assertInvalid("full goal cannot close with an unresolved gate")

    def test_unknown_test_group_rejected(self):
        self.manifest["cards"][0]["test_groups"].append("T_INVENTED")
        self.assertInvalid("unknown test group")

    def test_json_duplicate_keys_and_nonfinite_values_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"bad.json"
            for value in ['{"id":1,"id":2}','{"id":NaN}']:
                path.write_text(value)
                with self.assertRaises(ValueError):
                    check_handoff.read_json(path)

class GeneratedDocumentTests(unittest.TestCase):
    def test_current_cards_and_index_match_manifest(self):
        self.assertEqual(0,render_manifest.main(["--pack",str(PACK),"--check"]))

    def test_drift_is_detected_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"manifest.json").write_bytes((PACK/"manifest.json").read_bytes())
            self.assertEqual(0,render_manifest.main(["--pack",str(root)]))
            (root/"INDEX.md").write_text("unreviewed drift\n")
            self.assertEqual(1,render_manifest.main(["--pack",str(root),"--check"]))
            self.assertEqual("unreviewed drift\n",(root/"INDEX.md").read_text())

class SourceIdentityTests(unittest.TestCase):
    def test_source_changes_affect_hash_but_handoff_record_does_not(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            subprocess.run(["git","init","-q",str(root)],check=True)
            (root/"ui").mkdir()
            source=root/"ui"/"example.py"
            source.write_text("value = 1\n")
            first,entries=capture_state.source_identity(root)
            self.assertEqual(["ui/example.py"],[entry["path"] for entry in entries])
            note=root/capture_state.EXCLUDED_PREFIX/"HANDOFF_LATEST.md"
            note.parent.mkdir(parents=True)
            note.write_text("progress only\n")
            self.assertEqual(first,capture_state.source_identity(root)[0])
            source.write_text("value = 2\n")
            self.assertNotEqual(first,capture_state.source_identity(root)[0])

    def test_symlinks_are_hashed_as_links_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            subprocess.run(["git","init","-q",str(root)],check=True)
            (root/"ui").mkdir()
            (root/"ui"/"link").symlink_to("missing-target")
            first,entries=capture_state.source_identity(root)
            self.assertEqual("symlink",entries[0]["type"])
            (root/"ui"/"link").unlink()
            (root/"ui"/"link").symlink_to("different-target")
            self.assertNotEqual(first,capture_state.source_identity(root)[0])

if __name__=="__main__":
    unittest.main()
