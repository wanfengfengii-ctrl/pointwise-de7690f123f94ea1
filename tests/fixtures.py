from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from issue.catalog import IssueCatalog, issue
from issue.envelope import encode_envelope
from receipt.intake import receive
from receipt.inventory import ReceiptInventory
from reports.store import ReportStore
from review.assessment import review
from survey.revision_store import RevisionStore
from survey.revisions import freeze


ROOT = Path(__file__).resolve().parents[1]


def read_sample(name):
    return json.loads((ROOT / 'samples' / name).read_text(encoding='utf-8'))


def outlet_survey(main_outlet='O', unused=False):
    data = {
        'survey': 'Qingqu', 'pieces': ['A', 'B'],
        'cells': [
            ['start_private', 'A', True], ['approach_private', 'A', True],
            ['bridge_private', 'B', True], ['return_private', 'A', True],
            ['outlet_main', 'A', True], ['outlet_alt', 'A', True],
            ['detour_private', 'B', True], ['missing_private', 'B', False],
        ],
        'links': [
            ['start_private', 'approach_private'], ['approach_private', 'bridge_private'],
            ['bridge_private', 'return_private'], ['return_private', 'outlet_main'],
            ['detour_private', 'return_private'],
        ],
        'starts': [['S', 'start_private'], ['AtO', 'outlet_main']],
        'outlets': [[main_outlet, 'outlet_main'], ['O2', 'outlet_alt']],
    }
    if unused:
        data['pieces'].append('C')
    return data


def redirect(draft, source, target):
    draft.links[:] = [(cell, target if cell == source else old) for cell, old in draft.links]


def local_loop_survey():
    return {
        'survey': 'Qingqu', 'pieces': ['A'],
        'cells': [[cell, 'A', True] for cell in ['a', 'b', 'c', 'tail']],
        'links': [['a', 'b'], ['b', 'c'], ['c', 'a'], ['tail', 'b']],
        'starts': [['Member', 'a'], ['Tail', 'tail']],
        'outlets': [],
    }


def independent_pieces(revision, *, early):
    common = {'survey': 'Qingqu', 'revision': revision, 'coverage': ['A', 'B']}
    alpha = {
        **common, 'piece': 'A', 'starts': {'S': 'start'},
        'incoming': {'return': {'from_piece': 'B', 'route': 'returning'}},
        'routes': {
            'start': {'kind': 'seam', 'piece': 'B', 'port': 'outgoing', 'hops': 2},
            'returning': {'kind': 'seam', 'piece': 'B', 'port': 'outgoing', 'hops': 2},
        },
        'joins': [['returning', 'start', 1, 1]] if early else [],
    }
    beta = {
        **common, 'piece': 'B', 'starts': {},
        'incoming': {'outgoing': {'from_piece': 'A', 'route': 'across'}},
        'routes': {'across': {'kind': 'seam', 'piece': 'A', 'port': 'return', 'hops': 1}},
        'joins': [],
    }
    return [encode_envelope(f'{revision}-{body["piece"]}', body) for body in (alpha, beta)]


class CenterCase(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'station'
        self.source.mkdir()
        self.source_db = self.source / 'station.sqlite'
        self.center_db = self.root / 'center.sqlite'
        self.revisions = RevisionStore(self.source_db)
        self.catalog = IssueCatalog(self.source_db)
        self.inventory = ReceiptInventory(self.center_db)
        self.reports = ReportStore(self.center_db)
        for store in (self.revisions, self.catalog, self.inventory, self.reports):
            store.initialize()

    def receive_revision(self, draft, pieces):
        revision = freeze(self.revisions, draft)
        issued = {piece: issue(self.revisions, self.catalog, revision, piece) for piece in pieces}
        ids = {piece: receive(self.inventory, fixed.raw) for piece, fixed in issued.items()}
        return revision, issued, ids

    def shut_source(self):
        self.source.rename(self.root / 'closed-station')
        self.assertFalse(self.source_db.exists())

    def sign(self, revision, ids, start='S'):
        return review(self.inventory, self.reports, 'Qingqu', revision, ids, start)

    def center_counts(self):
        with closing(sqlite3.connect(self.center_db)) as connection:
            return tuple(connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                         for table in ('received_pieces', 'reports', 'report_sources', 'first_receipts'))

    def source_counts(self):
        with closing(sqlite3.connect(self.source_db)) as connection:
            return tuple(connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                         for table in ('revisions', 'issued_pieces'))

    def assert_outcome(self, bundle, expected):
        document = json.loads(bundle.report)
        self.assertEqual(document['report_id'], bundle.report_id)
        self.assertEqual(document['outcome'], expected)
