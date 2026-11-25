from issue.catalog import issue
from issue.envelope import decode_envelope
from survey.intake import parse_survey
from survey.reference import online
from survey.revisions import freeze
from tests.fixtures import CenterCase, outlet_survey, redirect


class PrepareTests(CenterCase):
    def test_freeze_and_issue(self):
        draft = parse_survey(outlet_survey('O1'))
        original = freeze(self.revisions, draft)
        old_piece = issue(self.revisions, self.catalog, original, 'A')
        redirect(draft, 'return_private', 'outlet_alt')
        expected = {'kind': 'outlet', 'outlet': 'O1', 'hops': 4}
        self.assertEqual(online(self.revisions, original, 'S').as_record(), expected)
        self.assertEqual(issue(None, self.catalog, issue_id=old_piece.issue_id), old_piece)
        self.assertEqual(issue(self.revisions, self.catalog, original, 'A'), old_piece)
        self.assertEqual(self.source_counts(), (1, 1))

    def test_snapshot_after_correction(self):
        draft = parse_survey(outlet_survey('O1'))
        old = freeze(self.revisions, draft)
        original = issue(self.revisions, self.catalog, old, 'A')
        redirect(draft, 'return_private', 'outlet_alt')
        new = freeze(self.revisions, draft)
        self.assertNotEqual(old, new)
        for revision, outlet in ((old, 'O1'), (new, 'O2')):
            self.assertEqual(online(self.revisions, revision, 'S').as_record(),
                             {'kind': 'outlet', 'outlet': outlet, 'hops': 4})
        self.assertEqual(issue(None, self.catalog, issue_id=original.issue_id), original)

    def test_reissue_after_new_issue(self):
        data = outlet_survey('O1')
        old = freeze(self.revisions, data)
        first = issue(self.revisions, self.catalog, old, 'A')
        new = freeze(self.revisions, data)
        newer = issue(self.revisions, self.catalog, new, 'A')
        self.assertNotEqual(first.issue_id, newer.issue_id)
        reissued = issue(None, self.catalog, issue_id=first.issue_id)
        self.assertEqual(reissued.raw, first.raw)
        self.assertEqual(reissued.issue_id, first.issue_id)
        emitted_id, body = decode_envelope(reissued.raw)
        self.assertEqual(emitted_id, first.issue_id)
        self.assertEqual((body['revision'], body['piece']), (old, 'A'))
        self.assertEqual(self.source_counts(), (2, 2))

    def test_invalid_successor(self):
        draft = parse_survey(outlet_survey('O1'))
        valid = freeze(self.revisions, draft)
        redirect(draft, 'approach_private', 'missing_private')
        with self.assertRaisesRegex(ValueError, 'must connect valid cells'):
            freeze(self.revisions, draft)
        self.assertEqual(self.source_counts(), (1, 0))
        self.assertEqual(online(self.revisions, valid, 'S').as_record(),
                         {'kind': 'outlet', 'outlet': 'O1', 'hops': 4})

    def test_unregistered_terminal(self):
        draft = parse_survey(outlet_survey('O1'))
        valid = freeze(self.revisions, draft)
        draft.outlets.remove(('O1', 'outlet_main'))
        with self.assertRaisesRegex(ValueError, 'no successor or registered outlet'):
            freeze(self.revisions, draft)
        self.assertEqual(self.source_counts(), (1, 0))
        self.assertEqual(online(self.revisions, valid, 'S').as_record(),
                         {'kind': 'outlet', 'outlet': 'O1', 'hops': 4})

    def test_unknown_source_requests(self):
        revision = freeze(self.revisions, outlet_survey())
        with self.assertRaises(KeyError):
            online(self.revisions, 'unknown', 'S')
        with self.assertRaisesRegex(ValueError, 'unknown public start'):
            online(self.revisions, revision, 'hidden')
        with self.assertRaisesRegex(ValueError, 'outside the frozen coverage'):
            issue(self.revisions, self.catalog, revision, 'C')
        with self.assertRaises(KeyError):
            issue(None, self.catalog, issue_id='unknown')
        self.assertEqual(self.source_counts(), (1, 0))
