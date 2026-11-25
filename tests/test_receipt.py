import json

from issue.catalog import issue
from issue.envelope import decode_envelope, encode_envelope
from receipt.intake import receive
from receipt.validation import validate_piece
from survey.intake import parse_survey
from survey.revisions import freeze
from tests.fixtures import CenterCase, outlet_survey, redirect


class ReceiptTests(CenterCase):
    def make_piece(self):
        revision = freeze(self.revisions, outlet_survey())
        return issue(self.revisions, self.catalog, revision, 'A')

    def test_duplicate_receipt(self):
        original = self.make_piece()
        receipt_id = receive(self.inventory, original.raw)
        self.assertEqual(receive(self.inventory, bytes(bytearray(original.raw))), receipt_id)
        issue_id, body = decode_envelope(original.raw)
        body['survey'] = 'Other survey'
        replacement = encode_envelope(issue_id, body)
        with self.assertRaisesRegex(ValueError, 'conflicting bytes'):
            receive(self.inventory, replacement)
        self.assertEqual(self.inventory.load(receipt_id).raw, original.raw)
        self.assertEqual(self.center_counts(), (1, 0, 0, 0))

    def test_valid_body_conflict(self):
        original = self.make_piece()
        issue_id, body = decode_envelope(original.raw)
        route = body['routes'][body['starts']['AtO']]
        route['outlet'] = 'Amended outlet'
        conflict = encode_envelope(issue_id, body)
        self.assertEqual(validate_piece(original.raw).issue_id, validate_piece(conflict).issue_id)
        self.assertNotEqual(validate_piece(original.raw).routes, validate_piece(conflict).routes)
        first = receive(self.inventory, original.raw)
        self.assertEqual(receive(self.inventory, original.raw), first)
        with self.assertRaisesRegex(ValueError, 'conflicting bytes'):
            receive(self.inventory, conflict)
        self.assertEqual(self.inventory.load(first).raw, original.raw)
        self.assertEqual(self.center_counts(), (1, 0, 0, 0))

    def test_integrity_failure(self):
        original = self.make_piece()
        envelope = json.loads(original.raw)
        envelope['body'] = envelope['body'].replace('Qingqu', 'Wrong survey')
        with self.assertRaisesRegex(ValueError, 'body checksum mismatch'):
            receive(self.inventory, json.dumps(envelope).encode('utf-8'))
        self.assertEqual(self.center_counts(), (0, 0, 0, 0))

    def test_incomplete_selection(self):
        old, _, ids = self.receive_revision(outlet_survey(), ['A', 'B'])
        _, _, new_ids = self.receive_revision(outlet_survey(), ['A', 'B'])
        self.shut_source()
        with self.assertRaisesRegex(ValueError, 'incomplete coverage'):
            self.sign(old, [ids['A']])
        with self.assertRaisesRegex(ValueError, 'outside the requested survey revision'):
            self.sign(old, [ids['A'], new_ids['B']])
        self.assertEqual(self.center_counts(), (4, 0, 0, 0))

    def test_mixed_revision_same_coverage(self):
        draft = parse_survey(outlet_survey())
        old, old_issued, old_ids = self.receive_revision(draft, ['A', 'B'])
        redirect(draft, 'bridge_private', 'detour_private')
        new, new_issued, new_ids = self.receive_revision(draft, ['A', 'B'])
        _, old_b = decode_envelope(old_issued['B'].raw)
        _, new_b = decode_envelope(new_issued['B'].raw)
        self.assertEqual(old_b['coverage'], new_b['coverage'])
        self.assertEqual(old_b['incoming'], new_b['incoming'])
        old_route, = old_b['routes'].values()
        new_route, = new_b['routes'].values()
        self.assertEqual((old_route['piece'], old_route['port']), (new_route['piece'], new_route['port']))
        self.assertEqual((old_route['hops'], new_route['hops']), (1, 2))
        self.shut_source()
        with self.assertRaisesRegex(ValueError, 'outside the requested survey revision'):
            self.sign(old, [old_ids['A'], new_ids['B']])
        self.assertEqual(self.center_counts(), (4, 0, 0, 0))
        self.assert_outcome(self.sign(old, old_ids.values()), {'kind': 'outlet', 'outlet': 'O', 'hops': 4})
        self.assert_outcome(self.sign(new, new_ids.values()), {'kind': 'outlet', 'outlet': 'O', 'hops': 5})

    def test_missing_unused_piece(self):
        revision, _, ids = self.receive_revision(outlet_survey(unused=True), ['A', 'B', 'C'])
        self.shut_source()
        with self.assertRaisesRegex(ValueError, "missing \\['C'\\]"):
            self.sign(revision, [ids['A'], ids['B']])
        self.assertEqual(self.center_counts(), (3, 0, 0, 0))
        result = self.sign(revision, [ids['B'], ids['A'], ids['B'], ids['C']])
        self.assert_outcome(result, {'kind': 'outlet', 'outlet': 'O', 'hops': 4})
        self.assertEqual(result.provenance, tuple(sorted(ids.items())))

    def test_unknown_start(self):
        revision, _, ids = self.receive_revision(outlet_survey(), ['A', 'B'])
        self.shut_source()
        with self.assertRaisesRegex(ValueError, 'unknown public start'):
            self.sign(revision, ids.values(), 'Undeclared')
        self.assertEqual(self.center_counts(), (2, 0, 0, 0))

    def test_two_received_sources_for_one_piece(self):
        revision, issued, ids = self.receive_revision(outlet_survey(), ['A', 'B'])
        _, body = decode_envelope(issued['A'].raw)
        alternate = receive(self.inventory, encode_envelope('alternate', body))
        self.shut_source()
        with self.assertRaisesRegex(ValueError, 'ambiguous receipts'):
            self.sign(revision, [ids['A'], alternate, ids['B']])
        self.assertEqual(self.center_counts(), (3, 0, 0, 0))
