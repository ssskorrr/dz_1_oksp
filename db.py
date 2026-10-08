import os
import time
import psycopg
from psycopg.rows import dict_row

PREFIX = 'kirill_skorikov'
DSN = os.environ.get('DATABASE_URL', 'postgresql://postgres:changeme@127.0.0.1:55439/kirill_skorikov')

def connect():
    conn = psycopg.connect(DSN, row_factory=dict_row, options='-c max_parallel_workers_per_gather=0 -c jit=off')
    conn.execute('SET search_path TO kirill_skorikov')
    return conn

class Database:
    def __init__(self, conn):
        self.conn, self.ms, self.count = conn, 0.0, 0

    def query(self, sql, params=()):
        started = time.perf_counter()
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall() if cursor.description else []
        finally:
            self.ms += (time.perf_counter() - started) * 1000
            self.count += 1

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None
