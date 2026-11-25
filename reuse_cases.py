import json
import sqlite3
import unittest
from hashlib import sha256

from issue.catalog import compatibility_for
from issue.declaration import decode_declaration, digest_declaration, encode_declaration
from issue.envelope import decode_envelope
from receipt.intake import receive
from reports.history import read
from reports.store import ReportStore
from review.assessment import review_reuse
from survey.reference import online
from tests.fixtures import CenterCase, read_sample


PIECES = ("0", "1", "A", "B")
O2 = {"kind": "outlet", "outlet": "O2", "hops": 1}


def seam_registration(*, new_inlet=False, other_crossings=0, redirect=False):
    data = {
        "survey": "Qingqu",
        "pieces": list(PIECES),
        "cells": [["s", "A", True], ["t", "A", True],
                  ["b", "B", True], ["c", "B", True]],
        "links": [["s", "b" if redirect else "c"], ["t", "b"]],
        "starts": [["S", "s"]],
        "outlets": [["O1", "b"], ["O2", "c"]],
    }
    if new_inlet:
        data["cells"].extend([["lead", "0", True], ["a", "B", True]])
        data["links"].append(["lead", "a"])
        data["outlets"].append(["O0", "a"])
    for index in range(other_crossings):
        source, target = f"aux{index}", f"ref{index}"
        data["cells"].extend([[source, "0", True], [target, "1", True]])
        data["links"].append([source, target])
        data["outlets"].append([f"Aux{index}", target])
    return data


def outgoing_port(issued):
    _, body = decode_envelope(issued["A"].raw)
    return body["routes"][body["starts"]["S"]]["port"]


class ReuseBaseline(CenterCase):
    def test_renumbered_seam_offline_controls(self):
        configurations = ({"other_crossings": 1}, {}, {"new_inlet": True}, {"other_crossings": 2})
        records = [self.receive_revision(seam_registration(**args), PIECES) for args in configurations]
        self.assertEqual([outgoing_port(issued) for _, issued, _ in records], ["p3", "p2", "p3", "p4"])
        for revision, _, _ in records:
            self.assertEqual(online(self.revisions, revision, "S").as_record(), O2)

        r0, r1, r2, r3 = records
        mixed_r2 = {**r2[2], "A": r1[2]["A"]}
        mixed_r3 = {**r3[2], "A": r1[2]["A"], "B": r0[2]["B"]}
        self.shut_source()
        before = self.center_counts()
        for target, chosen in ((r2[0], mixed_r2), (r3[0], mixed_r3)):
            with self.assertRaisesRegex(ValueError, "outside the requested survey revision"):
                self.sign(target, chosen.values())
        self.assertEqual(self.center_counts(), before)

        for revision, _, ids in records:
            bundle = self.sign(revision, ids.values())
            self.assert_outcome(bundle, O2)
            self.assertEqual(json.loads(bundle.report)["revision"], revision)
            self.assertEqual(bundle.provenance, tuple(sorted(ids.items())))
            self.assertEqual(read(ReportStore(self.center_db), bundle.report_id), bundle)
        self.assertEqual(self.inventory.load(r1[2]["A"]).raw, r1[1]["A"].raw)


class ReuseSuite(CenterCase):
    def prepare_family(self):
        configurations = (
            {"other_crossings": 1}, {}, {"new_inlet": True}, {"other_crossings": 2},
        )
        records = [self.receive_revision(seam_registration(**args), PIECES) for args in configurations]
        self.assertEqual([outgoing_port(issued) for _, issued, _ in records], ["p3", "p2", "p3", "p4"])
        return records

    def declaration(self, issued_piece, target_revision):
        return compatibility_for(self.revisions, self.catalog, issued_piece.issue_id, target_revision)

    def assert_reuse_report(self, bundle, target_revision, expected_sources, declarations):
        document = json.loads(bundle.report)
        self.assertEqual(document["survey"], "Qingqu")
        self.assertEqual(document["revision"], target_revision)
        self.assertEqual(document["outcome"], O2)
        self.assertEqual(document["sources"], expected_sources)
        expected_digests = {
            decode_declaration(raw)["piece"]: digest_declaration(raw) for raw in declarations
        }
        self.assertEqual(document["reuse_declarations"], expected_digests)
        first = json.loads(bundle.first_receipt)
        self.assertEqual(first["report_sha256"], sha256(bundle.report).hexdigest())
        self.assertEqual(first["sources"], expected_sources)
        self.assertEqual(first["reuse_declarations"], expected_digests)
        self.assertEqual(bundle.provenance, tuple(sorted(expected_sources.items())))

    def test_r2_reuses_r1_piece_a(self):
        r0, r1, r2, r3 = self.prepare_family()
        declaration = self.declaration(r1[1]["A"], r2[0])
        payload = decode_declaration(declaration)
        self.assertEqual(payload["old_issue"], r1[1]["A"].issue_id)
        self.assertEqual(payload["old_piece_sha256"], sha256(r1[1]["A"].raw).hexdigest())
        self.assertEqual(payload["target_revision"], r2[0])
        self.assertEqual(payload["seams"], {"s1": {"piece": "B", "port": "p3", "hops": 1}})
        self.shut_source()

        receipt_ids = [r1[2]["A"]] + [r2[2][piece] for piece in ("0", "1", "B")]
        bundle = review_reuse(
            self.inventory, self.reports, "Qingqu", r2[0], receipt_ids, [declaration], "S"
        )
        sources = {"A": r1[2]["A"], "0": r2[2]["0"], "1": r2[2]["1"], "B": r2[2]["B"]}
        self.assert_reuse_report(bundle, r2[0], sources, [declaration])
        self.assertEqual(read(ReportStore(self.center_db), bundle.report_id), bundle)

    def test_r3_reuses_r1_a_and_r0_b(self):
        r0, r1, r2, r3 = self.prepare_family()
        decl_a = self.declaration(r1[1]["A"], r3[0])
        decl_b = self.declaration(r0[1]["B"], r3[0])
        self.assertEqual(decode_declaration(decl_a)["seams"],
                         {"s1": {"piece": "B", "port": "p4", "hops": 1}})
        self.shut_source()

        receipt_ids = [r1[2]["A"], r0[2]["B"], r3[2]["0"], r3[2]["1"]]
        # Declaration order must not matter; receipt order must not matter.
        bundle = review_reuse(
            self.inventory, self.reports, "Qingqu", r3[0],
            reversed(receipt_ids), [decl_b, decl_a], "S"
        )
        sources = {"A": r1[2]["A"], "B": r0[2]["B"], "0": r3[2]["0"], "1": r3[2]["1"]}
        self.assert_reuse_report(bundle, r3[0], sources, [decl_a, decl_b])
        self.assertEqual(read(ReportStore(self.center_db), bundle.report_id), bundle)

    def test_same_original_serves_two_targets_independently(self):
        r0, r1, r2, r3 = self.prepare_family()
        decl_a2 = self.declaration(r1[1]["A"], r2[0])
        decl_a3 = self.declaration(r1[1]["A"], r3[0])
        decl_b3 = self.declaration(r0[1]["B"], r3[0])
        self.shut_source()

        ids_r2 = [r1[2]["A"]] + [r2[2][piece] for piece in ("0", "1", "B")]
        bundle_r2 = review_reuse(
            self.inventory, self.reports, "Qingqu", r2[0], ids_r2, [decl_a2], "S"
        )
        ids_r3 = [r1[2]["A"], r0[2]["B"], r3[2]["0"], r3[2]["1"]]
        bundle_r3 = review_reuse(
            self.inventory, self.reports, "Qingqu", r3[0], ids_r3, [decl_a3, decl_b3], "S"
        )
        self.assertEqual(json.loads(bundle_r2.report)["sources"]["A"], r1[2]["A"])
        self.assertEqual(json.loads(bundle_r3.report)["sources"]["A"], r1[2]["A"])
        self.assertNotEqual(bundle_r2.report_id, bundle_r3.report_id)
        reopened = ReportStore(self.center_db)
        self.assertEqual(read(reopened, bundle_r2.report_id), bundle_r2)
        self.assertEqual(read(reopened, bundle_r3.report_id), bundle_r3)

    def test_wrong_target_declaration_is_rejected(self):
        r0, r1, r2, r3 = self.prepare_family()
        decl_a2 = self.declaration(r1[1]["A"], r2[0])
        decl_b3 = self.declaration(r0[1]["B"], r3[0])
        self.shut_source()
        ids_r3 = [r1[2]["A"], r0[2]["B"], r3[2]["0"], r3[2]["1"]]
        before = self.center_counts()
        with self.assertRaisesRegex(ValueError, "another target revision"):
            review_reuse(
                self.inventory, self.reports, "Qingqu", r3[0], ids_r3,
                [decl_a2, decl_b3], "S"
            )
        self.assertEqual(self.center_counts(), before)

    def test_another_same_piece_receipt_cannot_impersonate(self):
        r0, r1, r2, r3 = self.prepare_family()
        # Declaration binds r1's B, but the center is handed r0's B for piece B.
        declaration = self.declaration(r1[1]["B"], r3[0])
        decl_a = self.declaration(r1[1]["A"], r3[0])
        self.shut_source()
        ids_r3 = [r1[2]["A"], r0[2]["B"], r3[2]["0"], r3[2]["1"]]
        before = self.center_counts()
        with self.assertRaisesRegex(ValueError, "selected original revision"):
            review_reuse(
                self.inventory, self.reports, "Qingqu", r3[0], ids_r3,
                [declaration, decl_a], "S"
            )
        self.assertEqual(self.center_counts(), before)

    def test_redirect_cannot_reuse_r1_piece_a(self):
        self.prepare_family()
        r1_revision, r1_issued, _ = self.receive_revision(seam_registration(), PIECES)
        redirected, _, _ = self.receive_revision(seam_registration(redirect=True), PIECES)
        self.assertEqual(online(self.revisions, redirected, "S").as_record(),
                         {"kind": "outlet", "outlet": "O1", "hops": 1})
        with self.assertRaisesRegex(ValueError, "same real inlet"):
            compatibility_for(self.revisions, self.catalog, r1_issued["A"].issue_id, redirected)

    def test_early_piece_a_cannot_serve_control(self):
        early, early_issued, _ = self.receive_revision(read_sample("early.json"), ["A", "B"])
        control, control_issued, _ = self.receive_revision(read_sample("control.json"), ["A", "B"])
        with self.assertRaisesRegex(ValueError, "first join presence changed"):
            compatibility_for(self.revisions, self.catalog, early_issued["A"].issue_id, control)
        with self.assertRaisesRegex(ValueError, "first join presence changed"):
            compatibility_for(self.revisions, self.catalog, control_issued["A"].issue_id, early)

    def test_declaration_integrity_and_coverage_rules(self):
        r0, r1, r2, r3 = self.prepare_family()
        decl_a = self.declaration(r1[1]["A"], r3[0])
        decl_b = self.declaration(r0[1]["B"], r3[0])
        self.shut_source()
        ids_r3 = [r1[2]["A"], r0[2]["B"], r3[2]["0"], r3[2]["1"]]
        before = self.center_counts()

        envelope = json.loads(decl_a)
        envelope["sha256"] = ("0" if envelope["sha256"][0] != "0" else "1") + envelope["sha256"][1:]
        tampered = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
        with self.assertRaisesRegex(ValueError, "declaration checksum mismatch"):
            review_reuse(
                self.inventory, self.reports, "Qingqu", r3[0], ids_r3,
                [tampered, decl_b], "S"
            )

        payload = decode_declaration(decl_a)
        payload["piece"] = "B"
        rebound = encode_declaration(payload)
        with self.assertRaisesRegex(ValueError, "selected original revision|more than one reuse declaration"):
            review_reuse(
                self.inventory, self.reports, "Qingqu", r3[0], ids_r3,
                [rebound, decl_b], "S"
            )

        with self.assertRaisesRegex(ValueError, "lacks a reuse declaration"):
            review_reuse(
                self.inventory, self.reports, "Qingqu", r3[0], ids_r3, [decl_a], "S"
            )
        with self.assertRaisesRegex(ValueError, "more than one reuse declaration"):
            review_reuse(
                self.inventory, self.reports, "Qingqu", r3[0], ids_r3,
                [decl_a, decl_b, decl_b], "S"
            )
        with self.assertRaisesRegex(ValueError, "reuse declarations must be bytes"):
            review_reuse(
                self.inventory, self.reports, "Qingqu", r3[0], ids_r3,
                [decl_a.decode("utf-8"), decl_b], "S"
            )
        self.assertEqual(self.center_counts(), before)

    def test_same_revision_set_uses_new_entry_with_empty_declarations(self):
        r0, r1, r2, r3 = self.prepare_family()
        self.shut_source()
        ids = [r3[2][piece] for piece in PIECES]
        bundle = review_reuse(
            self.inventory, self.reports, "Qingqu", r3[0], ids, [], "S"
        )
        document = json.loads(bundle.report)
        self.assertEqual(document["outcome"], O2)
        self.assertEqual(document["sources"], dict(r3[2]))
        self.assertEqual(document["reuse_declarations"], {})
        self.assertEqual(json.loads(bundle.first_receipt)["reuse_declarations"], {})

    def test_unknown_receipt_and_unknown_start(self):
        r0, r1, r2, r3 = self.prepare_family()
        decl_a = self.declaration(r1[1]["A"], r3[0])
        decl_b = self.declaration(r0[1]["B"], r3[0])
        self.shut_source()
        ids_r3 = [r1[2]["A"], r0[2]["B"], r3[2]["0"], r3[2]["1"]]
        with self.assertRaises(KeyError):
            review_reuse(
                self.inventory, self.reports, "Qingqu", r3[0],
                ids_r3 + [999], [decl_a, decl_b], "S"
            )
        with self.assertRaisesRegex(ValueError, "unknown public start"):
            review_reuse(
                self.inventory, self.reports, "Qingqu", r3[0],
                ids_r3, [decl_a, decl_b], "Undeclared"
            )

    def test_reuse_commit_failure_rolls_back_together(self):
        r0, r1, r2, r3 = self.prepare_family()
        decl_a = self.declaration(r1[1]["A"], r3[0])
        decl_b = self.declaration(r0[1]["B"], r3[0])
        self.shut_source()
        ids_r3 = [r1[2]["A"], r0[2]["B"], r3[2]["0"], r3[2]["1"]]
        first = review_reuse(
            self.inventory, self.reports, "Qingqu", r3[0], ids_r3, [decl_a, decl_b], "S"
        )
        before = self.center_counts()
        with self.reports.transaction() as connection:
            connection.execute("CREATE TABLE missing_parent (id INTEGER PRIMARY KEY)")
            connection.execute("""
                CREATE TABLE deferred_check (
                    id INTEGER REFERENCES missing_parent(id) DEFERRABLE INITIALLY DEFERRED
                )
            """)
            connection.execute("""
                CREATE TRIGGER fail_at_commit AFTER INSERT ON first_receipts
                BEGIN INSERT INTO deferred_check(id) VALUES (NEW.report_id); END
            """)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "FOREIGN KEY constraint failed"):
            review_reuse(
                self.inventory, self.reports, "Qingqu", r3[0], ids_r3,
                [decl_a, decl_b], "S"
            )
        self.assertEqual(self.center_counts(), before)
        self.assertEqual(read(ReportStore(self.center_db), first.report_id), first)

    def test_unknown_issue_or_revision_raises_keyerror(self):
        with self.assertRaises(KeyError):
            compatibility_for(self.revisions, self.catalog, "missing-issue", "missing-revision")
        revision, issued, _ = self.receive_revision(seam_registration(), PIECES)
        with self.assertRaises(KeyError):
            compatibility_for(self.revisions, self.catalog, issued["A"].issue_id, "missing-revision")

    def test_renumbered_loop_keeps_first_join_evidence(self):
        # A second crossing on another piece renumbers every port, while the
        # S loop keeps identical hops, real seam direction and first join offsets.
        base = {
            "survey": "Qingqu", "pieces": ["A", "B"],
            "cells": [
                ["s", "A", True], ["x", "A", True], ["p", "B", True],
                ["q", "A", True], ["back", "A", True], ["b", "B", True],
            ],
            "links": [
                ["s", "x"], ["x", "p"], ["p", "q"], ["q", "x"],
                ["back", "p"], ["b", "s"],
            ],
            "starts": [["S", "s"], ["Return", "back"]],
            "outlets": [],
        }
        renumbered = {
            "survey": "Qingqu", "pieces": ["A", "B"],
            "cells": base["cells"] + [["aux", "A", True], ["ref", "B", True]],
            "links": base["links"] + [["aux", "ref"]],
            "starts": base["starts"],
            "outlets": [["Aux", "ref"]],
        }
        old_revision, old_issued, _ = self.receive_revision(base, ["A", "B"])
        target_revision, target_issued, target_ids = self.receive_revision(renumbered, ["A", "B"])
        old_a_body = decode_envelope(old_issued["A"].raw)[1]
        new_a_body = decode_envelope(target_issued["A"].raw)[1]
        self.assertTrue(old_a_body["joins"])
        self.assertEqual(
            [row[2:] for row in old_a_body["joins"]],
            [row[2:] for row in new_a_body["joins"]],
        )
        declaration = compatibility_for(
            self.revisions, self.catalog, old_issued["A"].issue_id, target_revision
        )
        payload = decode_declaration(declaration)
        self.assertTrue(payload["seams"])
        self.assertEqual(payload["joins"], [list(row) for row in old_a_body["joins"]])
        for record in payload["seams"].values():
            self.assertEqual(record["piece"], "B")

        self.shut_source()
        old_a_receipt = receive(self.inventory, old_issued["A"].raw)
        ids = [old_a_receipt, target_ids["B"]]
        bundle = review_reuse(
            self.inventory, self.reports, "Qingqu", target_revision, ids,
            [declaration], "S"
        )
        self.assert_outcome(bundle, {"kind": "loop", "entry_hops": 1, "loop_length": 3})
        self.assertEqual(json.loads(bundle.report)["sources"],
                         {"A": old_a_receipt, "B": target_ids["B"]})
        self.assertEqual(read(ReportStore(self.center_db), bundle.report_id), bundle)

    def test_incomplete_coverage_is_rejected_without_signing(self):
        r0, r1, r2, r3 = self.prepare_family()
        decl_a = self.declaration(r1[1]["A"], r3[0])
        self.shut_source()
        before = self.center_counts()
        with self.assertRaisesRegex(ValueError, "incomplete coverage"):
            review_reuse(
                self.inventory, self.reports, "Qingqu", r3[0],
                [r1[2]["A"], r0[2]["B"], r3[2]["0"]], [decl_a], "S"
            )
        self.assertEqual(self.center_counts(), before)

    def test_same_revision_piece_cannot_carry_a_declaration(self):
        r0, r1, r2, r3 = self.prepare_family()
        declaration = self.declaration(r1[1]["A"], r3[0])
        self.shut_source()
        # Piece A is supplied from the target revision, so its declaration is invalid.
        target_ids = [r3[2][piece] for piece in PIECES]
        with self.assertRaisesRegex(ValueError, "already matches the target revision"):
            review_reuse(
                self.inventory, self.reports, "Qingqu", r3[0], target_ids,
                [declaration], "S"
            )

    def test_legacy_reports_keep_original_shape(self):
        r0, r1, r2, r3 = self.prepare_family()
        self.shut_source()
        legacy = self.sign(r3[0], [r3[2][piece] for piece in PIECES])
        document = json.loads(legacy.report)
        self.assertNotIn("sources", document)
        self.assertNotIn("reuse_declarations", document)
        self.assertEqual(set(json.loads(legacy.first_receipt)),
                         {"report_id", "report_sha256", "sources"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
