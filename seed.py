import argparse
import hashlib
import json
from pathlib import Path
from werkzeug.security import generate_password_hash
from db import connect

SIZES = {'small': (10,10,500,300), 'work': (200,30,200000,50000)}

def seed(size):
    n_spec,n_services,n_slots,n_bookings = SIZES[size]
    with connect() as conn:
        conn.execute(Path('schema.sql').read_text(encoding='utf-8'))
        conn.execute('TRUNCATE bookings, slots, specialists, services, app_users RESTART IDENTITY CASCADE')
        # Fixed salt: this is a local educational demo, not a production user store.
        # Deterministic SHA-256 hash is used only for the explicitly documented demo account.
        password_hash = 'demo-sha256:' + hashlib.sha256(b'demo').hexdigest()
        conn.execute('INSERT INTO app_users VALUES(1,%s,%s)', ('demo',password_hash))
        conn.execute("INSERT INTO services SELECT i, 'Услуга '||i, CASE WHEN i%%2=0 THEN 60 ELSE 30 END, (i-1)%%5 FROM generate_series(1,%s) i",(n_services,))
        conn.execute("INSERT INTO specialists SELECT i, 'Специалист '||i, (i-1)%%5 FROM generate_series(1,%s) i",(n_spec,))
        # Each specialist has adjacent one-hour slots; assignment is deterministic.
        conn.execute("""INSERT INTO slots SELECT i,(i-1)%%%s+1,
          timestamp '2026-11-01 09:00:00' + ((i-1)/%s)*interval '1 hour',
          timestamp '2026-11-01 10:00:00' + ((i-1)/%s)*interval '1 hour'
          FROM generate_series(1,%s) i""",(n_spec,n_spec,n_spec,n_slots))
        conn.execute("""INSERT INTO bookings(user_id,service_id,slot_id,status)
          SELECT 1, ((i-1)%%%s)%%5+1, i,
          CASE WHEN i%%5=0 THEN 'cancelled' ELSE 'active' END
          FROM generate_series(1,%s) i""", (n_spec,n_bookings))
        conn.execute('ANALYZE')
        counts={t:conn.execute(f'SELECT count(*) AS n FROM {t}').fetchone()['n'] for t in ('app_users','services','specialists','slots','bookings')}
        digest=conn.execute("SELECT md5(string_agg(id::text||':'||slot_id||':'||status,',' ORDER BY id)) AS hash FROM bookings").fetchone()['hash']
    result={'size':size,'counts':counts,'booking_digest':digest}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('size', choices=SIZES)
    seed(parser.parse_args().size)
