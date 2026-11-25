from issue.envelope import decode_envelope, encode_envelope
from receipt.intake import receive
from reports.history import read
from survey.reference import online
from tests.fixtures import CenterCase, independent_pieces, local_loop_survey, outlet_survey, read_sample


class ReviewTests(CenterCase):
    def test_outlet_after_return(self):
        revision, _, ids = self.receive_revision(outlet_survey(), ['A', 'B'])
        expected = {'kind': 'outlet', 'outlet': 'O', 'hops': 4}
        self.assertEqual(online(self.revisions, revision, 'S').as_record(), expected)
        self.shut_source()
        result = self.sign(revision, list(reversed(ids.values())))
        self.assert_outcome(result, expected)
        self.assertEqual(read(self.reports, result.report_id), result)

    def test_seam_hops(self):
        revision, issued, ids = self.receive_revision(outlet_survey(), ['B', 'A'])
        _, alpha = decode_envelope(issued['A'].raw)
        _, beta = decode_envelope(issued['B'].raw)
        first = alpha['routes'][alpha['starts']['S']]
        bridge = beta['routes'][beta['incoming'][first['port']]['route']]
        last = alpha['routes'][alpha['incoming'][bridge['port']]['route']]
        self.assertEqual([first['hops'], bridge['hops'], last['hops']], [2, 1, 1])
        self.assertEqual([first['piece'], bridge['piece'], last['outlet']], ['B', 'A', 'O'])
        self.shut_source()
        self.assert_outcome(self.sign(revision, ids.values()), {'kind': 'outlet', 'outlet': 'O', 'hops': 4})

    def test_start_at_outlet(self):
        revision, _, ids = self.receive_revision(outlet_survey(), ['A', 'B'])
        expected = {'kind': 'outlet', 'outlet': 'O', 'hops': 0}
        self.assertEqual(online(self.revisions, revision, 'AtO').as_record(), expected)
        self.shut_source()
        self.assert_outcome(self.sign(revision, ids.values(), 'AtO'), expected)

    def test_local_loop_from_member(self):
        revision, _, ids = self.receive_revision(local_loop_survey(), ['A'])
        expected = {'kind': 'loop', 'entry_hops': 0, 'loop_length': 3}
        self.assertEqual(online(self.revisions, revision, 'Member').as_record(), expected)
        self.shut_source()
        self.assert_outcome(self.sign(revision, ids.values(), 'Member'), expected)

    def test_tail_to_loop(self):
        revision, _, ids = self.receive_revision(local_loop_survey(), ['A'])
        expected = {'kind': 'loop', 'entry_hops': 1, 'loop_length': 3}
        self.assertEqual(online(self.revisions, revision, 'Tail').as_record(), expected)
        self.shut_source()
        self.assert_outcome(self.sign(revision, ids.values(), 'Tail'), expected)

    def test_loop_entry_before_seam(self):
        prepared = []
        for name, entry in (('early.json', 1), ('control.json', 2)):
            draft = read_sample(name)
            revision, issued, ids = self.receive_revision(draft, ['A', 'B'])
            expected = {'kind': 'loop', 'entry_hops': entry, 'loop_length': 3}
            self.assertEqual(online(self.revisions, revision, 'S').as_record(), expected, name)
            for fixed in issued.values():
                for cell, _, _ in draft['cells']:
                    self.assertNotIn(cell.encode(), fixed.raw)
            prepared.append((revision, ids, expected))
        self.shut_source()
        for revision, ids, expected in prepared:
            with self.subTest(expected=expected):
                bundle = self.sign(revision, ids.values())
                self.assert_outcome(bundle, expected)
                self.assertEqual(bundle.provenance, tuple(sorted(ids.items())))
                self.assertEqual(read(self.reports, bundle.report_id), bundle)

    def test_equal_public_segments(self):
        early, early_issued, early_ids = self.receive_revision(read_sample('early.json'), ['A', 'B'])
        control, late_issued, late_ids = self.receive_revision(read_sample('control.json'), ['A', 'B'])
        early_bodies = {piece: decode_envelope(fixed.raw)[1] for piece, fixed in early_issued.items()}
        late_bodies = {piece: decode_envelope(fixed.raw)[1] for piece, fixed in late_issued.items()}
        for piece in ('A', 'B'):
            for field in ('coverage', 'starts', 'incoming', 'routes'):
                self.assertEqual(early_bodies[piece][field], late_bodies[piece][field], (piece, field))
        alpha, beta = early_bodies['A'], early_bodies['B']
        start_id = alpha['starts']['S']
        first = alpha['routes'][start_id]
        away = beta['routes'][beta['incoming'][first['port']]['route']]
        return_id = alpha['incoming'][away['port']]['route']
        back = alpha['routes'][return_id]
        self.assertEqual([first['hops'], away['hops'], back['hops']], [2, 1, 2])
        self.assertEqual(first['port'], back['port'])
        self.assertIn([*sorted((start_id, return_id)), 1, 1], alpha['joins'])
        self.assertFalse(late_bodies['A']['joins'])
        self.shut_source()
        self.assert_outcome(self.sign(early, early_ids.values()), {'kind': 'loop', 'entry_hops': 1, 'loop_length': 3})
        self.assert_outcome(self.sign(control, late_ids.values()), {'kind': 'loop', 'entry_hops': 2, 'loop_length': 3})

    def test_independent_valid_pieces(self):
        self.shut_source()
        for revision, early, entry in (('field-early', True, 1), ('field-control', False, 2)):
            with self.subTest(revision=revision):
                raw = independent_pieces(revision, early=early)
                ids = [receive(self.inventory, piece) for piece in reversed(raw)]
                result = self.sign(revision, ids)
                self.assert_outcome(result, {'kind': 'loop', 'entry_hops': entry, 'loop_length': 3})
                self.assertEqual(result.provenance, (('A', ids[1]), ('B', ids[0])))

    def test_unresolved_join_between_pieces(self):
        self.shut_source()
        a, b = independent_pieces('field-missing-seam', early=True)
        issue_id, body = decode_envelope(b)
        body['incoming']['other-port'] = body['incoming'].pop('outgoing')
        ids = [receive(self.inventory, raw) for raw in (a, encode_envelope(issue_id, body))]
        with self.assertRaisesRegex(ValueError, 'unresolved seam'):
            self.sign('field-missing-seam', ids)
        self.assertEqual(self.center_counts(), (2, 0, 0, 0))
