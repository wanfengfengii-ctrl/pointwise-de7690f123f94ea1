from dataclasses import dataclass
import json
from uuid import uuid4

from storage import SQLiteFile
from survey.topology import ValidatedTopology


@dataclass(frozen=True)
class FrozenRevision:
    revision_id: str
    topology: ValidatedTopology


class RevisionStore:
    def __init__(self, path):
        self.database = SQLiteFile(path)

    def initialize(self):
        self.database.initialize('''
            CREATE TABLE IF NOT EXISTS revisions (
                revision_id TEXT PRIMARY KEY,
                survey TEXT NOT NULL,
                snapshot TEXT NOT NULL
            );
        ''')

    def save(self, topology: ValidatedTopology):
        revision_id = uuid4().hex
        snapshot = json.dumps({
            'pieces': topology.pieces,
            'cells': topology.cells,
            'missing': topology.missing,
            'successors': topology.successors,
            'starts': topology.starts,
            'outlets': topology.outlets,
        }, sort_keys=True, separators=(',', ':'))
        with self.database.session(write=True) as connection:
            connection.execute(
                'INSERT INTO revisions (revision_id, survey, snapshot) VALUES (?, ?, ?)',
                (revision_id, topology.survey, snapshot),
            )
        return revision_id

    def load(self, revision_id):
        if not isinstance(revision_id, str) or not revision_id:
            raise ValueError('expected a revision ID')
        with self.database.session() as connection:
            row = connection.execute(
                'SELECT survey, snapshot FROM revisions WHERE revision_id = ?', (revision_id,)
            ).fetchone()
        if row is None:
            raise KeyError(revision_id)
        survey, snapshot = row
        data = json.loads(snapshot)
        topology = ValidatedTopology(
            survey, tuple(data['pieces']), data['cells'], data['missing'],
            data['successors'], data['starts'], data['outlets'],
        )
        return FrozenRevision(revision_id, topology)
