import json, hashlib, time
from app.store import connection as base_connection

def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

def connection():
    db = base_connection()
    db.execute('CREATE TABLE IF NOT EXISTS traces(id TEXT PRIMARY KEY, run_id TEXT NOT NULL, lot TEXT NOT NULL, status TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS recalls(id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, batch TEXT NOT NULL, basis TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(trace_id, batch))')
    return db

def insert_trace(ident, run_id, lot, state):
    with connection() as db:
        db.execute('INSERT INTO traces(id,run_id,lot,status,state,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                   (ident, run_id, lot, '进行中', json.dumps(state, ensure_ascii=False), now(), now()))

def save_step(ident, state, status, new_recalls):
    """单炉次检查点：状态与召回单同事务提交，召回单按(trace_id,炉次)幂等。"""
    with connection() as db:
        for batch, basis in new_recalls:
            rid = hashlib.sha256(('%s:%s' % (ident, batch)).encode('utf-8')).hexdigest()[:16]
            db.execute('INSERT OR IGNORE INTO recalls(id,trace_id,batch,basis,created_at) VALUES (?,?,?,?,?)',
                       (rid, ident, batch, json.dumps(basis, ensure_ascii=False), now()))
        db.execute('UPDATE traces SET state=?, status=?, updated_at=? WHERE id=?',
                   (json.dumps(state, ensure_ascii=False), status, now(), ident))

def load(ident):
    with connection() as db:
        row = db.execute('SELECT * FROM traces WHERE id=?', (ident,)).fetchone()
    if row is None:
        return None
    return {'id': row['id'], 'run_id': row['run_id'], 'lot': row['lot'], 'status': row['status'],
            'state': json.loads(row['state']), 'created_at': row['created_at'], 'updated_at': row['updated_at']}

def list_traces():
    with connection() as db:
        return [dict(r) for r in db.execute('SELECT id,run_id,lot,status,updated_at FROM traces ORDER BY rowid DESC')]

def recalls(trace_id):
    with connection() as db:
        rows = db.execute('SELECT * FROM recalls WHERE trace_id=? ORDER BY batch', (trace_id,)).fetchall()
    return [{'id': r['id'], 'trace_id': r['trace_id'], '炉次': r['batch'],
             '依据': json.loads(r['basis']), 'created_at': r['created_at']} for r in rows]
