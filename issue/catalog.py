from dataclasses import dataclass
from uuid import uuid4

from issue.coverage import derive_coverage
from issue.envelope import encode_envelope
from issue.evidence import derive_piece_body
from storage import SQLiteFile


@dataclass(frozen=True)
class IssuedPiece:
    issue_id: str
    raw: bytes


class IssueCatalog:
    def __init__(self, path):
        self.database = SQLiteFile(path)

    def initialize(self):
        self.database.initialize('''
            CREATE TABLE IF NOT EXISTS issued_pieces (
                issue_id TEXT PRIMARY KEY,
                revision_id TEXT NOT NULL,
                piece TEXT NOT NULL,
                raw BLOB NOT NULL,
                UNIQUE (revision_id, piece)
            );
        ''')

    def save(self, revision_id, piece, body):
        if body['revision'] != revision_id or body['piece'] != piece:
            raise ValueError('catalog identity must match body identity')
        with self.database.session(write=True) as connection:
            row = connection.execute(
                'SELECT issue_id, raw FROM issued_pieces WHERE revision_id = ? AND piece = ?',
                (revision_id, piece),
            ).fetchone()
            if row is not None:
                return IssuedPiece(*row)
            issue_id = uuid4().hex
            raw = encode_envelope(issue_id, body)
            connection.execute(
                'INSERT INTO issued_pieces (issue_id, revision_id, piece, raw) VALUES (?, ?, ?, ?)',
                (issue_id, revision_id, piece, raw),
            )
        return IssuedPiece(issue_id, raw)

    def load(self, issue_id):
        if not isinstance(issue_id, str) or not issue_id:
            raise ValueError('expected an issue ID')
        with self.database.session() as connection:
            row = connection.execute(
                'SELECT issue_id, raw FROM issued_pieces WHERE issue_id = ?', (issue_id,)
            ).fetchone()
        if row is None:
            raise KeyError(issue_id)
        return IssuedPiece(*row)


def issue(revisions, catalog, revision_id=None, piece=None, *, issue_id=None):
    if issue_id is not None:
        if revision_id is not None or piece is not None:
            raise ValueError('reissue requires only the original issue ID')
        return catalog.load(issue_id)
    if revisions is None or revision_id is None or not isinstance(piece, str) or not piece:
        raise ValueError('issue requires a revision and a piece')
    revision = revisions.load(revision_id)
    coverage = derive_coverage(revision)
    body = derive_piece_body(revision, coverage, piece)
    return catalog.save(revision_id, piece, body)
