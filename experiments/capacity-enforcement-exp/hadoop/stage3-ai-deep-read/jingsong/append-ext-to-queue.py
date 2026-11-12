#!/usr/bin/env python3
"""Append the band A, B, C units of the stage-1 extension (2026-11-11) to the END of Jingsong's queue.csv.

The extension units have uids starting `E:` (enforcement rows and method verdicts) or `C:`
(capacity-set rows); their bands are in ../../stage2-ai-preprocessing/bands.csv. Existing queue rows
are never changed or reordered (PROCEDURE.md: never skip or reorder rows); new rows get the next
`order` numbers, in band order A, B, C, then by uid. Units already in the queue are skipped, so a
second run appends nothing. The extension anchors (batch `ext-anchors`) are marked `anchor=yes`,
as the `if` anchors are, and are skipped by "start the next batch of N".

`make-abc-queue.py` must not be re-run after this: it rebuilds the queue from the `if` corpus only.

Usage (repo root): experiments/capacity-enforcement-exp/hadoop/stage3-ai-deep-read/jingsong/append-ext-to-queue.py
Needs codeql-queries/results/hadoop/{EnforcementPlaces,CapacitySetPlaces}.csv (gitignored).
"""
import csv
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, *['..'] * 5))
RES = os.path.join(REPO, 'codeql-queries', 'results', 'hadoop')
BANDS = os.path.join(REPO, 'experiments/capacity-enforcement-exp/hadoop/stage2-ai-preprocessing/bands.csv')
QUEUE = os.path.join(HERE, 'queue.csv')

spec = importlib.util.spec_from_file_location('mk', os.path.join(REPO, 'codeql-queries', 'scripts', 'make-stage2-batches.py'))
mk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mk)
units = {u['id']: u for u in mk.load_extension(RES, mk.SYSTEMS['hadoop']) if u['id'].startswith(('E:', 'C:'))}

with open(QUEUE, newline='') as f:
    rd = csv.DictReader(f)
    cols = rd.fieldnames
    queue = list(rd)
have = {r['uid'] for r in queue}
last = max(int(r['order']) for r in queue)

new = [b for b in csv.DictReader(open(BANDS))
       if b['uid'].startswith(('E:', 'C:')) and b['band'] in ('A', 'B', 'C') and b['uid'] not in have]
missing = [b['uid'] for b in new if b['uid'] not in units]
if missing:
    raise SystemExit('units not in the stage-1 CSVs (stale CSV?): %d, e.g. %s' % (len(missing), missing[0]))
new.sort(key=lambda b: ('ABC'.index(b['band']), b['batch'] == 'ext-anchors', b['uid']))

with open(QUEUE, 'a', newline='') as f:
    w = csv.DictWriter(f, cols, lineterminator='\n')
    for i, b in enumerate(new, last + 1):
        u = units[b['uid']]
        row = {c: '' for c in cols}
        row.update(order=i, uid=b['uid'], kind=u['kind'], band=b['band'],
                   anchor='yes' if b['batch'] == 'ext-anchors' else '',
                   stage2_reason=b['reason'], text=u['text'])
        w.writerow(row)
by = {}
for b in new:
    by[b['band']] = by.get(b['band'], 0) + 1
print('appended %d units (orders %d-%d): %s' % (len(new), last + 1, last + len(new), by))
