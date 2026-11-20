import csv, io, hashlib
from app.errors import DomainError
from app.numeric import number

TRACE_RULE_VERSION = '2026.11.20.1'
TRANSFER_HEADERS = ['from_batch', 'to_batch', 'lot', 'mass']

def transfers_digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def trace_id(run_id, lot, transfers_sha):
    key = 'TRACE|%s|%s|%s|%s' % (TRACE_RULE_VERSION, run_id, lot, transfers_sha)
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]

def parse_transfers(text):
    """解析复配转移记录，返回(有效转移, 隔离行)。空文本返回两空。"""
    transfers, issues = [], []
    if not text or not text.strip():
        return transfers, issues
    reader = csv.reader(io.StringIO(text.lstrip('\ufeff'), newline=''), strict=True)
    try:
        head = next(reader, None)
    except csv.Error:
        raise DomainError('STRUCTURE', '转移记录表头损坏')
    if head is None:
        return transfers, issues
    head = [x.strip() for x in head]
    if set(head) != set(TRANSFER_HEADERS) or len(head) != len(TRANSFER_HEADERS):
        raise DomainError('HEADER', '转移记录字段缺失或重复')
    seen = set()
    try:
        for cells in reader:
            if not cells or all(not x.strip() for x in cells):
                continue
            line = reader.line_num
            if len(cells) != len(head):
                issues.append({'行号': line, '原值': '|'.join(cells), '原因码': 'COLUMNS', '原因': '列数不符'})
                continue
            row = dict(zip(head, [x.strip() for x in cells]))
            try:
                if not row['from_batch'] or not row['to_batch'] or not row['lot']:
                    raise DomainError('MISSING', '炉次或批号为空')
                if row['from_batch'] == row['to_batch']:
                    raise DomainError('RANGE', '转出炉次与转入炉次相同')
                mass = number(row['mass'])
                if mass <= 0:
                    raise DomainError('RANGE', '转移重量必须大于零')
                key = (row['from_batch'], row['to_batch'], row['lot'], str(mass))
                if key in seen:
                    issues.append({'行号': line, '原值': '|'.join(cells), '原因码': 'DUPLICATE', '原因': '相同转移重复'})
                    continue
                seen.add(key)
                transfers.append({'from_batch': row['from_batch'], 'to_batch': row['to_batch'],
                                  'lot': row['lot'], 'mass': str(mass), '行号': line})
            except DomainError as e:
                issues.append({'行号': line, '原值': '|'.join(cells), '原因码': e.code, '原因': e.message})
    except csv.Error:
        raise DomainError('STRUCTURE', '转移记录引号未闭合或记录截断')
    return transfers, issues

def direct_heats(run, lot):
    """批号直接投入的炉次及投料证据（采信的来料记录）。"""
    hits = {}
    for r in run['normalized']:
        if r['lot'] == lot:
            hits.setdefault(r['batch'], []).append(r['行号'])
    return hits

def initial_state(run, lot, transfers, issues, transfers_sha):
    hits = direct_heats(run, lot)
    paths = {}
    for batch in sorted(hits):
        lines = '、'.join(str(n) for n in hits[batch])
        paths[batch] = [{'途径': '直接投料',
                         '细节': '批号%s在炉次%s投料%d条（原始行号%s）' % (lot, batch, len(hits[batch]), lines)}]
    return {
        'run_id': run['manifest']['run_id'],
        'lot': lot,
        'trace_rule_version': TRACE_RULE_VERSION,
        'transfers_sha': transfers_sha,
        'transfers': transfers,
        'transfer_issues': issues,
        '签核': {'run_id': run['manifest']['run_id'],
                'rule_version': run['manifest']['rule_version'],
                'decision': run['decision'],
                'revision': run['revision']},
        'frontier': sorted(hits),
        'visited': [],
        'paths': paths,
        'dispositions': {},
        'steps_done': 0,
    }

def judge(acceptance_rows):
    """按验收结论裁定炉次处置，返回(处置, 依据列表)。区间跨越限值不得当作合格。"""
    if not acceptance_rows:
        return '冻结待复测', ['炉次无验收结论（沾料记录未进入混配验收），不能判定合格']
    bad = [r for r in acceptance_rows if r['验收'] == '不合格']
    if bad:
        return '召回', ['元素%s含量区间[%s,%s]%%超出限值[%s,%s]%%，验收不合格，必须召回'
                       % (r['元素'], r['含量下界_pct'], r['含量上界_pct'], r['下限_pct'], r['上限_pct']) for r in bad]
    pending = [r for r in acceptance_rows if r['验收'] == '待补测']
    if pending:
        return '冻结待复测', ['元素%s仅有区间[%s,%s]%%，跨越限值[%s,%s]%%，不能判定合格，冻结待复测'
                           % (r['元素'], r['含量下界_pct'], r['含量上界_pct'], r['下限_pct'], r['上限_pct']) for r in pending]
    return '可以留用', ['元素%s含量区间[%s,%s]%%在限值[%s,%s]%%内，验收通过，可以留用'
                     % (r['元素'], r['含量下界_pct'], r['含量上界_pct'], r['下限_pct'], r['上限_pct']) for r in acceptance_rows]

def step(run, state):
    """处理frontier中一个炉次并就地推进state，返回炉次号；无可处理返回None。"""
    if not state['frontier']:
        return None
    batch = state['frontier'].pop(0)
    rows = [r for r in run['acceptance'] if r['炉次'] == batch]
    disposition, basis = judge(rows)
    state['dispositions'][batch] = {'处置': disposition, '依据': basis, '验收': rows}
    state['visited'].append(batch)
    downstream = sorted((t for t in state['transfers'] if t['from_batch'] == batch),
                        key=lambda t: (t['to_batch'], t['行号']))
    known = set(state['visited']) | set(state['frontier'])
    for t in downstream:
        to = t['to_batch']
        entry = {'途径': '复配转入',
                 '细节': '炉次%s复配转入%s，批号%s，%skg（转移记录行号%s）' % (batch, to, t['lot'], t['mass'], t['行号'])}
        state['paths'].setdefault(to, [])
        if entry not in state['paths'][to]:
            state['paths'][to].append(entry)
        if to not in known:
            state['frontier'].append(to)
            known.add(to)
    state['frontier'].sort()
    state['steps_done'] += 1
    return batch

def summarize(state):
    dispositions = state['dispositions']
    return {
        '沾料炉次': len(dispositions) + len(state['frontier']),
        '召回': sum(1 for d in dispositions.values() if d['处置'] == '召回'),
        '冻结待复测': sum(1 for d in dispositions.values() if d['处置'] == '冻结待复测'),
        '可以留用': sum(1 for d in dispositions.values() if d['处置'] == '可以留用'),
        '待处理': len(state['frontier']),
    }
