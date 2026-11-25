from issue.catalog import IssueCatalog, issue
from receipt.intake import receive
from receipt.inventory import ReceiptInventory
from reports.history import read
from reports.store import ReportStore
from survey.intake import parse_survey
from survey.reference import online
from survey.revision_store import RevisionStore
from tests.fixtures import CenterCase, outlet_survey, redirect


class InitializeTests(CenterCase):
    def test_repeat_initialization(self):
        draft = parse_survey(outlet_survey('O1'))
        old, old_pieces, old_ids = self.receive_revision(draft, ['A', 'B'])
        first = self.sign(old, old_ids.values())
        redirect(draft, 'return_private', 'outlet_alt')
        new, new_pieces, new_ids = self.receive_revision(draft, ['A', 'B'])
        second = self.sign(new, new_ids.values())
        self.assert_outcome(first, {'kind': 'outlet', 'outlet': 'O1', 'hops': 4})
        self.assert_outcome(second, {'kind': 'outlet', 'outlet': 'O2', 'hops': 4})
        revisions = RevisionStore(self.source_db)
        catalog = IssueCatalog(self.source_db)
        inventory = ReceiptInventory(self.center_db)
        reports = ReportStore(self.center_db)
        for _ in range(2):
            for store in (revisions, catalog, inventory, reports):
                store.initialize()
        self.assertEqual(online(revisions, old, 'S').as_record(), {'kind': 'outlet', 'outlet': 'O1', 'hops': 4})
        self.assertEqual(revisions.load(new).topology.successors['return_private'], 'outlet_alt')
        self.assertEqual(online(revisions, new, 'S').as_record(), {'kind': 'outlet', 'outlet': 'O2', 'hops': 4})
        self.assertEqual(self.source_counts(), (2, 4))
        self.shut_source()
        for pieces, ids in ((old_pieces, old_ids), (new_pieces, new_ids)):
            for name, fixed in pieces.items():
                self.assertEqual(inventory.load(ids[name]).raw, fixed.raw)
                self.assertEqual(receive(inventory, fixed.raw), ids[name])
        restored_catalog = IssueCatalog(self.root / 'closed-station' / 'station.sqlite')
        for pieces in (old_pieces, new_pieces):
            for fixed in pieces.values():
                self.assertEqual(issue(None, restored_catalog, issue_id=fixed.issue_id), fixed)
        self.assertEqual(read(reports, first.report_id), first)
        self.assertEqual(read(reports, second.report_id), second)
        self.assertEqual(self.center_counts(), (4, 2, 4, 2))
