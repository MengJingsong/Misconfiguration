#!/usr/bin/env python3
"""Build the write-up set of the stage-1 extension rows (Cassandra, 2026-11-11).

Joins the extension units (rebuilt from the gitignored stage-1 CSVs by
codeql-queries/scripts/make-stage2-batches.py --extension) with their stage-2 bands in
../stage2-ai-preprocessing/bands.csv (uids starting `E:` or `C:`), and writes
writeup-set-ext.csv: bands A, B, C in that order (band D is not read, as for the `if`
corpus), one row per unit, sorted by uid within a band.

A unit whose target line is already the target of a case file gets that file in
`case_file` and `existing case` in `stage3_record`, so it is not written up twice. A
capacity-set unit whose field name is the constraint of existing case files (by the case
file's name prefix) gets `known constraint: <prefix>` in `stage3_record`: it is a second
entry point to a constraint already traced, and its owner decides whether to write it up.

Usage: python3 make-writeup-set-ext.py [results-dir]   (default codeql-queries/results/cassandra)
"""
import csv
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
SCRIPTS = os.path.join(REPO, 'codeql-queries', 'scripts')
BANDS = os.path.join(HERE, '..', 'stage2-ai-preprocessing', 'bands.csv')
OUT = os.path.join(HERE, 'writeup-set-ext.csv')
PILOT = os.path.join(HERE, '..', 'stage1-codeql-preprocessing', 'pilot_report.py')


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def known_note(unit, known):
    m = re.search(r'\| (\w+)\.(\w+) = ', unit['text']) if unit['kind'] == 'capacity-set' else None
    if m and m.group(2).lower() in known:
        return 'known constraint: %s' % known[m.group(2).lower()]
    return ''


def main():
    results = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, 'codeql-queries', 'results', 'cassandra')
    mk = module(os.path.join(SCRIPTS, 'make-stage2-batches.py'), 'mk')
    units = {u['id']: u for u in mk.load_extension(results, mk.SYSTEMS['cassandra'])
             if u['id'].startswith(('E:', 'C:'))}
    bands = {r['uid']: r for r in csv.DictReader(open(BANDS)) if r['uid'].startswith(('E:', 'C:'))}
    missing = set(units) - set(bands)
    if missing:
        sys.exit('%d extension units have no band yet (e.g. %s)' % (len(missing), sorted(missing)[0]))

    targets = {}
    for fn, t in module(PILOT, 'pilot').case_targets().items():
        if t:
            targets.setdefault('%s:%d' % t, []).append(fn)

    known = {f.split('-')[0].lower(): f.split('-')[0]
             for f in os.listdir(os.path.join(HERE, 'cases')) if f.endswith('.md')}

    rows = []
    for uid, b in bands.items():
        if b['band'] not in ('A', 'B', 'C') or b['batch'] == 'ext-anchors':
            continue
        u = units[uid]
        first = u['target'].split(' ')[0]
        existing = targets.get(first, [])
        rows.append({'uid': uid, 'kind': u['kind'], 'band': b['band'], 'target': u['target'],
                     'text': u['text'], 'stage2_reason': b['reason'],
                     'stage3_record': 'existing case' if existing else known_note(u, known),
                     'case_file': ' '.join(f[:-3] for f in existing), 'estimate': '', 'stage4': ''})
    rows.sort(key=lambda r: ('ABC'.index(r['band']), r['uid']))
    with open(OUT, 'w', newline='') as fh:
        w = csv.DictWriter(fh, ['order', 'uid', 'kind', 'band', 'target', 'text', 'stage2_reason',
                                'stage3_record', 'case_file', 'estimate', 'stage4'], lineterminator='\n')
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow(dict(r, order=i))
    by = {}
    for r in rows:
        by[(r['band'], r['kind'])] = by.get((r['band'], r['kind']), 0) + 1
    print('wrote %d units to %s' % (len(rows), OUT))
    for k in sorted(by):
        print('  %s %-13s %d' % (k[0], k[1], by[k]))
    print('  already a case target: %d' % sum(1 for r in rows if r['case_file']))
    print('  known constraint (capacity-set): %d' % sum(1 for r in rows if r['stage3_record'].startswith('known')))


if __name__ == '__main__':
    main()
