#!/usr/bin/env python3
"""Build Jingsong's queue.csv: every band A, B, C unit of hadoop stage 2, in read order A, B, C.

Usage (repo root): experiments/capacity-enforcement-exp/hadoop/stage3-ai-deep-read/jingsong/make-abc-queue.py
Needs codeql-queries/results/hadoop/*.csv (gitignored). Within a band the order is: the 18 anchors
last (already source-read, see stage2 anchors.md), then units grouped by source file so siblings
are written up together. Do not regenerate over a queue.csv with filled-in status columns.
"""
import csv, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, *['..'] * 5))
RES = os.path.join(REPO, 'codeql-queries', 'results', 'hadoop')
BANDS = os.path.join(REPO, 'experiments/capacity-enforcement-exp/hadoop/stage2-ai-preprocessing/bands.csv')
ANCH = os.path.join(REPO, 'experiments/capacity-enforcement-exp/hadoop/stage2-ai-preprocessing/anchors.md')

nar = list(csv.DictReader(open(os.path.join(RES, 'NarrowedIfStatements.csv'))))
hel = list(csv.DictReader(open(os.path.join(RES, 'HelperGuardedIfStatements.csv'))))
seen = {}
for r in nar:
    k = (r['path'], r['line']); seen[k] = seen.get(k, 0) + 1
    r['uid'] = '%s:%s#%d' % (r['path'], r['line'], seen[k])
info = {r['uid']: ('row', r) for r in nar}
for r in hel: info.setdefault('helper:' + r['helper'], ('helper', r))
anchor_src = open(ANCH).read()
bands = [x for x in csv.DictReader(open(BANDS)) if x['band'] in 'ABC']
miss = [x['uid'] for x in bands if x['uid'] not in info]
if miss: sys.exit('units not in stage-1 CSVs (stale CSV?): %d, e.g. %s' % (len(miss), miss[:3]))
anchors = {x['uid'] for x in bands if x['model'] == 'source-read'}
def key(x):
    kind, r = info[x['uid']]
    return ('ABC'.index(x['band']), x['uid'] in anchors, r['path'], int(r['line']), x['uid'])
bands.sort(key=key)
cols = ['order', 'uid', 'kind', 'band', 'anchor', 'stage2_reason', 'text', 'case_file', 'estimate', 'stage4']
with open(os.path.join(HERE, 'queue.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, cols); w.writeheader()
    for i, x in enumerate(bands, 1):
        kind, r = info[x['uid']]
        w.writerow(dict(order=i, uid=x['uid'], kind=kind, band=x['band'],
                        anchor='yes' if x['uid'] in anchors else '', stage2_reason=x['reason'],
                        text='%s | %s.%s | %s %s %s' % (r['moduleDir'], r['declaringType'].split('.')[-1], r['method'], r['lhs'], r['op'], r['rhs']),
                        case_file='', estimate='', stage4=''))
print('units', len(bands), 'anchors', len(anchors))
