from app.errors import DomainError
from app.pipeline import calculate
from app.store import get_run, latest, save
from app.modules.m8_trace import rules, store

def resolve_run(run_id):
    if run_id:
        return get_run(run_id)
    run = latest()
    return run if run else save(calculate())

def start(run_id, lot, transfers_csv, max_steps=None):
    """发起追溯；同一批次+批号+转移记录复用已有追溯，不重复生成召回单。"""
    run = resolve_run(run_id)
    rid = run['manifest']['run_id']
    text = transfers_csv or ''
    transfers, issues = rules.parse_transfers(text)
    ident = rules.trace_id(rid, lot, rules.transfers_digest(text))
    existing = store.load(ident)
    if existing:
        return present(existing, reused=True)
    state = rules.initial_state(run, lot, transfers, issues, rules.transfers_digest(text))
    store.insert_trace(ident, rid, lot, state)
    advance(ident, run, max_steps)
    return present(store.load(ident), reused=False)

def resume(ident, max_steps=None):
    """从最近检查点续跑；已完成的追溯直接返回，不产生新召回单。"""
    trace = store.load(ident)
    if trace is None:
        raise DomainError('NOT_FOUND', '追溯不存在', 404)
    if trace['status'] == '完成':
        return present(trace, reused=True)
    run = get_run(trace['run_id'])
    advance(ident, run, max_steps)
    return present(store.load(ident), reused=False)

def load_trace(ident):
    trace = store.load(ident)
    if trace is None:
        raise DomainError('NOT_FOUND', '追溯不存在', 404)
    return present(trace, reused=True)

def advance(ident, run, max_steps):
    """逐炉次推进并落检查点；max_steps限制本次调用处理炉次数，中断后可续跑。"""
    done = 0
    while True:
        trace = store.load(ident)
        state = trace['state']
        batch = rules.step(run, state)
        if batch is None:
            if trace['status'] != '完成':
                store.save_step(ident, state, '完成', [])
            return
        recalls = []
        disposition = state['dispositions'][batch]
        if disposition['处置'] == '召回':
            recalls.append((batch, {'炉次': batch, '批号': state['lot'], '处置': '召回',
                                    '依据': disposition['依据'], '签核': state['签核']}))
        status = '完成' if not state['frontier'] else '进行中'
        store.save_step(ident, state, status, recalls)
        if status == '完成':
            return
        done += 1
        if max_steps is not None and done >= max_steps:
            return

def present(trace, reused):
    state = trace['state']
    return {
        'trace_id': trace['id'],
        'run_id': trace['run_id'],
        'lot': trace['lot'],
        'status': trace['status'],
        'reused': reused,
        '签核': state['签核'],
        'summary': rules.summarize(state),
        'paths': state['paths'],
        'dispositions': state['dispositions'],
        'frontier': state['frontier'],
        'visited': state['visited'],
        'steps_done': state['steps_done'],
        'transfers': state['transfers'],
        'transfer_issues': state['transfer_issues'],
        'recalls': store.recalls(trace['id']),
        'created_at': trace['created_at'],
        'updated_at': trace['updated_at'],
    }
