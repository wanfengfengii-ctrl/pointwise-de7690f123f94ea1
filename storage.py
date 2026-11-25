from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3


class SQLiteFile:
    def __init__(self, path):
        self.path = Path(path).resolve()

    def _open(self, *, create=False):
        mode = 'rwc' if create else 'rw'
        connection = sqlite3.connect(
            f'{self.path.as_uri()}?mode={mode}', uri=True, isolation_level=None
        )
        try:
            connection.execute('PRAGMA foreign_keys = ON')
        except BaseException:
            connection.close()
            raise
        return connection

    def initialize(self, schema):
        with closing(self._open(create=True)) as connection:
            connection.executescript(f'BEGIN IMMEDIATE;\n{schema}\nCOMMIT;')

    @contextmanager
    def session(self, *, write=False):
        with closing(self._open()) as connection:
            connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
