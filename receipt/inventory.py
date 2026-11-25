from receipt.validation import VerifiedPiece, validate_piece
from storage import SQLiteFile


class ReceiptInventory:
    def __init__(self, path):
        self.database = SQLiteFile(path)

    def initialize(self):
        self.database.initialize('''
            CREATE TABLE IF NOT EXISTS received_pieces (
                receipt_id INTEGER PRIMARY KEY,
                issue_id TEXT NOT NULL UNIQUE,
                raw BLOB NOT NULL
            );
        ''')

    def register(self, piece: VerifiedPiece):
        with self.database.session(write=True) as connection:
            row = connection.execute(
                'SELECT receipt_id, raw FROM received_pieces WHERE issue_id = ?', (piece.issue_id,)
            ).fetchone()
            if row is not None:
                receipt_id, original = row
                if original != piece.raw:
                    raise ValueError(f'conflicting bytes for issue {piece.issue_id}')
                return receipt_id
            cursor = connection.execute(
                'INSERT INTO received_pieces (issue_id, raw) VALUES (?, ?)',
                (piece.issue_id, piece.raw),
            )
            receipt_id = cursor.lastrowid
        return receipt_id

    def load(self, receipt_id):
        if type(receipt_id) is not int or not 1 <= receipt_id <= 2**63 - 1:
            raise ValueError('expected a positive SQLite receipt ID')
        with self.database.session() as connection:
            row = connection.execute(
                'SELECT raw FROM received_pieces WHERE receipt_id = ?', (receipt_id,)
            ).fetchone()
        if row is None:
            raise KeyError(receipt_id)
        return validate_piece(row[0])
