from flask import Blueprint, request, jsonify
from app.errors import DomainError
from app.modules.m8_trace import service
from app.numeric import serial

bp = Blueprint('m8', __name__)

def checked_steps(value):
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DomainError('STEPS', '每步处理炉次数必须为正整数')
    return value

@bp.route('/api/trace', methods=['POST'])
def start():
    body = request.get_json(silent=True) or {}
    lot = body.get('lot')
    if not isinstance(lot, str) or not lot.strip():
        raise DomainError('LOT', '必须提供追溯批号')
    transfers = body.get('transfers_csv')
    if transfers is not None and not isinstance(transfers, str):
        raise DomainError('TYPE', '转移记录必须是CSV文本')
    run_id = body.get('run_id')
    if run_id is not None and not isinstance(run_id, str):
        raise DomainError('TYPE', 'run_id必须是字符串')
    result = service.start(run_id, lot.strip(), transfers, checked_steps(body.get('max_steps')))
    return jsonify(serial(result))

@bp.route('/api/trace/<ident>')
def detail(ident):
    return jsonify(serial(service.load_trace(ident)))

@bp.route('/api/trace/<ident>/resume', methods=['POST'])
def resume(ident):
    body = request.get_json(silent=True) or {}
    return jsonify(serial(service.resume(ident, checked_steps(body.get('max_steps')))))

@bp.route('/api/trace/<ident>/recalls')
def recalls(ident):
    return jsonify(serial(service.load_trace(ident)['recalls']))
