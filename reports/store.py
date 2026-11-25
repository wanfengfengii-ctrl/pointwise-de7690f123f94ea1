from dataclasses import dataclass

from storage import SQLiteFile


@dataclass(frozen=True)
class ReportBundle:
    report_id: int
    report: bytes
    provenance: tuple[tuple[str, int], ...]
    first_receipt: bytes


class ReportStore:
    def __init__(self, path):
        self.database = SQLiteFile(path)

    def initialize(self):
        self.database.initialize('''
            CREATE TABLE IF NOT EXISTS reports (
                report_id INTEGER PRIMARY KEY,
                payload BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS report_sources (
                report_id INTEGER NOT NULL REFERENCES reports(report_id),
                piece TEXT NOT NULL,
                receipt_id INTEGER NOT NULL REFERENCES received_pieces(receipt_id),
                PRIMARY KEY (report_id, piece),
                UNIQUE (report_id, receipt_id)
            );
            CREATE TABLE IF NOT EXISTS first_receipts (
                report_id INTEGER PRIMARY KEY REFERENCES reports(report_id),
                payload BLOB NOT NULL
            );
        ''')

    def transaction(self):
        return self.database.session(write=True)

    def reserve_report_id(self, connection):
        # The caller holds the write transaction across numbering and insertion.
        latest = connection.execute('SELECT MAX(report_id) FROM reports').fetchone()[0]
        return (latest or 0) + 1

    def save_bundle(self, connection, bundle: ReportBundle):
        connection.execute(
            'INSERT INTO reports (report_id, payload) VALUES (?, ?)',
            (bundle.report_id, bundle.report),
        )
        connection.executemany(
            'INSERT INTO report_sources (report_id, piece, receipt_id) VALUES (?, ?, ?)',
            ((bundle.report_id, piece, receipt_id) for piece, receipt_id in bundle.provenance),
        )
        connection.execute(
            'INSERT INTO first_receipts (report_id, payload) VALUES (?, ?)',
            (bundle.report_id, bundle.first_receipt),
        )

    def load_bundle(self, report_id):
        if type(report_id) is not int or not 1 <= report_id <= 2**63 - 1:
            raise ValueError('expected a positive SQLite report ID')
        with self.database.session() as connection:
            row = connection.execute('''
                SELECT reports.payload, first_receipts.payload
                FROM reports JOIN first_receipts USING (report_id)
                WHERE report_id = ?
            ''', (report_id,)).fetchone()
            if row is None:
                raise KeyError(report_id)
            provenance = tuple(connection.execute('''
                SELECT piece, receipt_id FROM report_sources
                WHERE report_id = ? ORDER BY piece
            ''', (report_id,)))
        return ReportBundle(report_id, row[0], provenance, row[1])
