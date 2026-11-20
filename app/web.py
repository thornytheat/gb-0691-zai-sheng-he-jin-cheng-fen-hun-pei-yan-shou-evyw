from flask import Blueprint, render_template, request
from app.config import TITLE, MODULES, SHORT, SAMPLE, TRACE_SAMPLE, TRANSFERS_SAMPLE
from app.pipeline import calculate
from app.store import latest, save, get_run
bp=Blueprint('web',__name__)
@bp.route('/')
@bp.route('/work/<int:stage>')
def work(stage=1):
    if stage<1 or stage>8:
        from flask import abort
        abort(404)
    run=get_run(request.args['run_id']) if request.args.get('run_id') else latest()
    if run is None: run=save(calculate())
    if stage==8:
        from app.modules.m8_trace.service import load_trace
        from app.modules.m8_trace.store import list_traces
        trace=load_trace(request.args['trace_id']) if request.args.get('trace_id') else None
        return render_template('m8.html', title=TITLE, modules=MODULES, short=SHORT, run=run, stage=8,
                               trace=trace, traces=list_traces(),
                               demo_ops=TRACE_SAMPLE.read_text(encoding='utf-8-sig'),
                               demo_transfers=TRANSFERS_SAMPLE.read_text(encoding='utf-8-sig'))
    current=run['stages'][str(stage)]
    return render_template('m'+str(stage)+'.html', title=TITLE, modules=MODULES, short=SHORT, run=run, current=current, stage=stage, sample=SAMPLE.read_text(encoding='utf-8-sig'))
