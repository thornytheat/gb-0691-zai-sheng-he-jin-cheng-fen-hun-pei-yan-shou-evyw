from pathlib import Path
RULE_VERSION = "2026.11.18.2"
TITLE = '再生合金成分混配与验收'
SHORT = 'alloy-blend'
MODULES = ['来料接收', '成分归一', '配方约束', '混配试算', '不确定区间', '验收对照', '复配批次', '追溯召回']
HEADERS = ['lot', 'batch', 'mass', 'unit', 'moisture', 'element', 'assay', 'basis', 'revision']
SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "operations.csv"
TRACE_SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "trace_operations.csv"
TRANSFERS_SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "reblend_transfers.csv"
LIMIT = 10000
