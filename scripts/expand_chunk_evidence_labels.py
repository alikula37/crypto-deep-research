"""Draft exact-span alternative sources; never mark automated additions human-reviewed.

Dated report queries keep their explicit source. Generic analysis/news questions
may be supported by the same evidence in another source under the same coin filter.
This structural expansion still requires a human to check semantic relevance.
"""
import argparse
import json
from pathlib import Path

from crypto_deep_research.rag.tuning import evidence_alternatives, normalize

parser = argparse.ArgumentParser()
parser.add_argument('dataset', type=Path)
parser.add_argument('--sources', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
sources = json.loads(args.sources.read_text())
rows = [json.loads(line) for line in args.dataset.read_text().splitlines() if line.strip()]
expanded = 0
for row in rows:
    if row['split'] != 'dev' or row.get('category') not in {'analysis', 'news'}:
        continue
    required = []
    for item in row['evidence']:
        variants = {(v['parent_id'], v['text']) for v in evidence_alternatives(item)}
        original = set(variants)
        for _, quote in original:
            for source in sources:
                if row.get('coin') and row['coin'] != source['coin']:
                    continue
                if normalize(quote) in normalize(source['text']):
                    variants.add((source['id'], quote))
        required.append({'alternatives': [{'parent_id': parent, 'text': quote}
                                         for parent, quote in sorted(variants)]}
                        if len(variants) > 1 else item)
        if variants != original:
            expanded += 1
            row['label_status'] = 'agent-drafted-needs-human-review'
            row['label_method'] = 'exact-span-alternative-sources'
        row['relevant_parent_ids'] = sorted(set(row['relevant_parent_ids']) | {v[0] for v in variants})
    row['evidence'] = required
args.output.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
print(f'{expanded} evidence units expanded; no human approval inferred')
