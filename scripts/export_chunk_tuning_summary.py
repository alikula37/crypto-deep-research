"""Export the compact, recorded experiment for the explanation page (no live benchmark)."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('report', type=Path)
parser.add_argument('--output', type=Path, default=Path('web/src/fixtures/chunk-tuning-summary.json'))
args = parser.parse_args()
report = json.loads(args.report.read_text())
summary = {name: report[name] for name in (
    'created_at', 'n_queries', 'k', 'corpus', 'embedding', 'selection', 'test_evaluated')}
summary['label_statuses'] = report['dataset']['label_statuses']
summary['runs'] = [{name: run[name] for name in ('key', 'settings', 'metrics', 'index', 'cost')}
                   for run in report['runs']]
args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
print(args.output)
