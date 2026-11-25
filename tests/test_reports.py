from hashlib import sha256
import json
import sqlite3

from receipt.inventory import ReceiptInventory
from reports.history import read
from reports.store import ReportStore
from review.assessment import review
from survey.intake import parse_survey
from tests.fixtures import CenterCase, outlet_survey, redirect


class ReportTests(CenterCase):
    def test_failed_publication(self):
        revision, _, ids = self.receive_revision(outlet_survey(), ['A', 'B'])
        self.shut_source()
        old = self.sign(revision, ids.values())
        before = self.center_counts()
        with self.reports.transaction() as connection:
            connection.execute('''
                CREATE TRIGGER block_new_reports BEFORE INSERT ON reports
                BEGIN SELECT RAISE(ABORT, 'reports unavailable'); END
            ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'reports unavailable'):
            self.sign(revision, ids.values())
        self.assertEqual(self.center_counts(), before)
        self.assertEqual(read(ReportStore(self.center_db), old.report_id), old)

    def test_commit_after_report_write(self):
        revision, _, ids = self.receive_revision(outlet_survey(), ['A', 'B'])
        self.shut_source()
        old = self.sign(revision, ids.values())
        before = self.center_counts()
        with self.reports.transaction() as connection:
            connection.execute('''
                CREATE TRIGGER block_first_receipt BEFORE INSERT ON first_receipts
                WHEN EXISTS (SELECT 1 FROM reports WHERE report_id = NEW.report_id)
                     AND (SELECT count(*) FROM report_sources WHERE report_id = NEW.report_id) = 2
                BEGIN SELECT RAISE(ABORT, 'report and sources already written'); END
            ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'report and sources already written'):
            self.sign(revision, ids.values())
        self.assertEqual(self.center_counts(), before)
        reopened = ReportStore(self.center_db)
        self.assertEqual(read(reopened, old.report_id), old)
        with self.assertRaises(KeyError):
            read(reopened, old.report_id + 1)

    def test_failed_sqlite_commit(self):
        revision, _, ids = self.receive_revision(outlet_survey(), ['A', 'B'])
        self.shut_source()
        old = self.sign(revision, ids.values())
        before = self.center_counts()
        with self.reports.transaction() as connection:
            connection.execute('CREATE TABLE missing_parent (id INTEGER PRIMARY KEY)')
            connection.execute('''
                CREATE TABLE deferred_check (
                    id INTEGER REFERENCES missing_parent(id) DEFERRABLE INITIALLY DEFERRED
                )
            ''')
            connection.execute('''
                CREATE TRIGGER fail_at_commit AFTER INSERT ON first_receipts
                BEGIN INSERT INTO deferred_check(id) VALUES (NEW.report_id); END
            ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
            self.sign(revision, ids.values())
        self.assertEqual(self.center_counts(), before)
        self.assertEqual(read(ReportStore(self.center_db), old.report_id), old)

    def test_correction_and_reopen(self):
        self.check_correction_and_reopen()

    def test_reopen_original_provenance(self):
        old, new = self.check_correction_and_reopen()
        self.assertEqual({piece for piece, _ in old.provenance}, {piece for piece, _ in new.provenance})
        self.assertTrue({rid for _, rid in old.provenance}.isdisjoint(rid for _, rid in new.provenance))

    def check_correction_and_reopen(self):
        draft = parse_survey(outlet_survey('O1'))
        old_revision, old_issued, old_ids = self.receive_revision(draft, ['A', 'B'])
        redirect(draft, 'return_private', 'outlet_alt')
        new_revision, new_issued, new_ids = self.receive_revision(draft, ['B', 'A'])
        self.shut_source()
        old = self.sign(old_revision, old_ids.values())
        new = review(ReceiptInventory(self.center_db), ReportStore(self.center_db),
                     'Qingqu', new_revision, new_ids.values(), 'S')
        reopened = ReportStore(self.center_db)
        original_receipts = ReceiptInventory(self.center_db)
        for revision, issuance, ids, report, outlet in (
            (old_revision, old_issued, old_ids, old, 'O1'),
            (new_revision, new_issued, new_ids, new, 'O2'),
        ):
            saved = read(reopened, report.report_id)
            self.assertEqual(saved.report, report.report)
            self.assertEqual(saved.first_receipt, report.first_receipt)
            self.assertEqual(saved.provenance, tuple(sorted(ids.items())))
            self.assertEqual(json.loads(saved.report)['revision'], revision)
            self.assert_outcome(saved, {'kind': 'outlet', 'outlet': outlet, 'hops': 4})
            self.assertEqual(json.loads(saved.first_receipt), {
                'report_id': report.report_id,
                'report_sha256': sha256(saved.report).hexdigest(),
                'sources': ids,
            })
            for piece, receipt_id in saved.provenance:
                self.assertEqual(original_receipts.load(receipt_id).raw, issuance[piece].raw)
        self.assertEqual(self.center_counts(), (4, 2, 4, 2))
        return old, new
