import pytest
from app.config import TRACE_SAMPLE, TRANSFERS_SAMPLE
from app.modules.m8_trace import rules
from app.errors import DomainError

@pytest.fixture
def ops(): return TRACE_SAMPLE.read_text(encoding='utf-8-sig')
@pytest.fixture
def transfers(): return TRANSFERS_SAMPLE.read_text(encoding='utf-8-sig')
@pytest.fixture
def traced_run(client, ops): return client.post('/api/run', json={'csv': ops}).get_json()

def start(client, run_id, transfers, **kw):
    payload = {'run_id': run_id, 'lot': '00001', 'transfers_csv': transfers}
    payload.update(kw)
    return client.post('/api/trace', json=payload)

def test_propagation_direct_and_reblend(client, traced_run, transfers):
    t = start(client, traced_run['manifest']['run_id'], transfers).get_json()
    assert t['status'] == '完成'
    assert set(t['dispositions']) == {'F-1108', 'F-1109', 'F-1110', 'F-1112'}
    assert 'F-1111' not in t['dispositions']  # 未沾料炉次不进追溯
    assert t['paths']['F-1108'][0]['途径'] == '直接投料'
    assert t['paths']['F-1109'][0]['途径'] == '直接投料'
    assert t['paths']['F-1110'][0]['途径'] == '复配转入' and 'F-1109' in t['paths']['F-1110'][0]['细节']
    assert t['paths']['F-1112'][0]['途径'] == '复配转入' and 'F-1110' in t['paths']['F-1112'][0]['细节']

def test_dispositions_with_basis(client, traced_run, transfers):
    t = start(client, traced_run['manifest']['run_id'], transfers).get_json()
    d = t['dispositions']
    assert d['F-1109']['处置'] == '召回'
    assert any('超出限值' in b for b in d['F-1109']['依据'])
    assert d['F-1110']['处置'] == '冻结待复测'
    assert any('不能判定合格' in b for b in d['F-1110']['依据'])
    assert d['F-1108']['处置'] == '可以留用'
    assert d['F-1112']['处置'] == '可以留用'

def test_interval_only_heat_not_treated_as_qualified(client, traced_run, transfers):
    t = start(client, traced_run['manifest']['run_id'], transfers).get_json()
    f1110 = t['dispositions']['F-1110']
    assert f1110['处置'] != '可以留用'  # 只有成分区间，不能直接当成合格
    assert any(r['验收'] == '待补测' for r in f1110['验收'])

def test_summary_shows_quality_and_sales_scope(client, traced_run, transfers):
    s = start(client, traced_run['manifest']['run_id'], transfers).get_json()['summary']
    assert s == {'沾料炉次': 4, '召回': 1, '冻结待复测': 1, '可以留用': 2, '待处理': 0}

def test_rerun_never_duplicates_recall_orders(client, traced_run, transfers):
    rid = traced_run['manifest']['run_id']
    first = start(client, rid, transfers).get_json()
    again = start(client, rid, transfers).get_json()
    assert again['reused'] is True and again['trace_id'] == first['trace_id']
    assert len(first['recalls']) == 1 and len(again['recalls']) == 1
    assert [r['id'] for r in again['recalls']] == [r['id'] for r in first['recalls']]
    assert again['recalls'][0]['炉次'] == 'F-1109'

def test_resume_after_interruption(client, traced_run, transfers):
    rid = traced_run['manifest']['run_id']
    t1 = start(client, rid, transfers, max_steps=2).get_json()
    assert t1['status'] == '进行中' and set(t1['dispositions']) == {'F-1108', 'F-1109'}
    assert len(t1['recalls']) == 1  # F-1109已判定并开单
    t2 = client.post('/api/trace/%s/resume' % t1['trace_id'], json={'max_steps': 1}).get_json()
    assert t2['status'] == '进行中' and set(t2['dispositions']) == {'F-1108', 'F-1109', 'F-1110'}
    t3 = client.post('/api/trace/%s/resume' % t1['trace_id'], json={}).get_json()
    assert t3['status'] == '完成'
    assert set(t3['dispositions']) == {'F-1108', 'F-1109', 'F-1110', 'F-1112'}
    assert len(t3['recalls']) == 1  # 续跑不重复开单
    t4 = client.post('/api/trace/%s/resume' % t1['trace_id'], json={}).get_json()
    assert t4['status'] == '完成' and t4['reused'] is True and len(t4['recalls']) == 1

def test_signed_acceptance_evidence_remains_traceable(client, traced_run, transfers):
    rid = traced_run['manifest']['run_id']
    assert client.post('/api/review', json={'id': rid, 'revision': 1, 'decision': '通过'}).status_code == 200
    t = start(client, rid, transfers).get_json()
    assert t['签核'] == {'run_id': rid, 'rule_version': traced_run['manifest']['rule_version'], 'decision': '通过', 'revision': 2}
    cu = [r for r in t['dispositions']['F-1109']['验收'] if r['元素'] == 'Cu']
    assert cu and cu[0]['验收'] == '不合格' and cu[0]['上限_pct'] == '12.5'
    recall = t['recalls'][0]
    assert recall['依据']['签核']['decision'] == '通过' and recall['依据']['签核']['revision'] == 2
    again = client.get('/api/trace/%s' % t['trace_id']).get_json()
    assert again['签核']['decision'] == '通过' and again['recalls'][0]['id'] == recall['id']
    evidence = client.get('/api/evidence.csv?run_id=' + rid).data.decode('utf-8-sig')
    assert rid in evidence and '验收' in evidence

def test_recall_list_endpoint(client, traced_run, transfers):
    t = start(client, traced_run['manifest']['run_id'], transfers).get_json()
    recalls = client.get('/api/trace/%s/recalls' % t['trace_id']).get_json()
    assert len(recalls) == 1 and recalls[0]['炉次'] == 'F-1109'

def test_lot_not_present_completes_empty(client, traced_run, transfers):
    t = client.post('/api/trace', json={'run_id': traced_run['manifest']['run_id'], 'lot': '99999', 'transfers_csv': transfers}).get_json()
    assert t['status'] == '完成' and t['summary']['沾料炉次'] == 0 and t['recalls'] == []

def test_trace_page_renders(client):
    assert client.get('/work/8').status_code == 200

def test_trace_page_shows_selected_trace(client, traced_run, transfers):
    t = start(client, traced_run['manifest']['run_id'], transfers).get_json()
    page = client.get('/work/8?run_id=%s&trace_id=%s' % (t['run_id'], t['trace_id'])).data.decode()
    assert '召回单' in page and 'F-1109' in page and '判断依据' in page

def test_unknown_trace_is_404(client):
    assert client.get('/api/trace/absent').status_code == 404
    assert client.post('/api/trace/absent/resume', json={}).status_code == 404
    assert client.get('/work/8?trace_id=absent').status_code == 404

def test_unknown_run_is_404(client):
    assert client.post('/api/trace', json={'run_id': 'absent', 'lot': '00001'}).status_code == 404

def test_missing_lot_is_422(client, traced_run):
    assert client.post('/api/trace', json={'run_id': traced_run['manifest']['run_id']}).status_code == 422

def test_bad_max_steps_is_422(client, traced_run, transfers):
    rid = traced_run['manifest']['run_id']
    assert start(client, rid, transfers, max_steps=0).status_code == 422
    assert start(client, rid, transfers, max_steps='x').status_code == 422

def test_transfer_issues_isolated_not_fatal(client, traced_run):
    dirty = 'from_batch,to_batch,lot,mass\nF-1109,F-1110,00003,50\nF-1109,F-1109,00003,10\nbad,row\n'
    t = start(client, traced_run['manifest']['run_id'], dirty).get_json()
    assert t['status'] == '完成' and 'F-1110' in t['dispositions']
    codes = {i['原因码'] for i in t['transfer_issues']}
    assert codes == {'RANGE', 'COLUMNS'}

def test_parse_transfers_header_rejected():
    with pytest.raises(DomainError):
        rules.parse_transfers('a,b,c\n1,2,3\n')

def test_parse_transfers_duplicate_isolated():
    transfers, issues = rules.parse_transfers('from_batch,to_batch,lot,mass\nA,B,L,1\nA,B,L,1\n')
    assert len(transfers) == 1 and issues[0]['原因码'] == 'DUPLICATE'

def test_non_object_json_rejected(client):
    assert client.post('/api/trace', json=[]).status_code == 400
