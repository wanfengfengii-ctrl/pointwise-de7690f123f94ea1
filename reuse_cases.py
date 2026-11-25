import json
import unittest

from issue.envelope import decode_envelope
from reports.history import read
from reports.store import ReportStore
from survey.reference import online
from tests.fixtures import CenterCase


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
