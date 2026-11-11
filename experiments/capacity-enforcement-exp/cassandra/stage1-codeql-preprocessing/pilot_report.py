#!/usr/bin/env python3
"""Stage-1 extension pilot (2026-11-11): counts and recall of the new queries on Cassandra.

Reads the four stage-1 CSVs from codeql-queries/results/cassandra/ (gitignored; regenerate with
codeql-queries/scripts/run-query.sh) and the case files in ../stage3-ai-deep-read/cases/, and prints:

1. rows and distinct places per pattern of EnforcementPlaces.csv and CapacitySetPlaces.csv,
   and how many places are new (their path:line is not a row of the `if` corpus);
2. recall: for every case file, whether its target (autonomous "Entry pointer", guided
   "Capacity check") is a row of the old `if` corpus, of the new enforcement rows, or of the
   capacity-set rows, exactly or within +-WINDOW lines.

Usage: python3 pilot_report.py [--system cassandra|hadoop] [--window N] [--list]
(Hadoop, 2026-11-11: results from codeql-queries/results/hadoop/, case files from
hadoop/stage3-ai-deep-read/<person>/cases/.)
"""
import argparse
import collections
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
EXP = os.path.abspath(os.path.join(HERE, '..', '..'))
SYSTEMS = {
    'cassandra': {'tag': 'cassandra-5.0.9',
                  'cases': [os.path.join(EXP, 'cassandra', 'stage3-ai-deep-read', 'cases')]},
    'hadoop': {'tag': 'rel/release-3.4.2',
               'cases': [os.path.join(EXP, 'hadoop', 'stage3-ai-deep-read', p, 'cases')
                         for p in ('jingsong', 'yang')]},
}
SYSTEM = 'cassandra'
RES = os.path.join(REPO, 'codeql-queries', 'results', 'cassandra')

# README §3.7.2 order: the first context of a comparison is its primary one.
CONTEXT_ORDER = ['ternary', 'loop-condition', 'switch-selector', 'lambda', 'assert', 'return',
                 'argument', 'assignment', 'declaration', 'field-initializer']


def load(name):
    path = os.path.join(RES, name)
    if not os.path.exists(path):
        sys.exit('missing %s: run the stage-1 queries first' % path)
    with open(path) as fh:
        return list(csv.DictReader(fh))


def case_targets(system=None):
    cfg = SYSTEMS[system or SYSTEM]
    out = {}
    files = [(d, fn) for d in cfg['cases'] if os.path.isdir(d) for fn in sorted(os.listdir(d))]
    for d, fn in files:
        if not fn.endswith('.md'):
            continue
        text = open(os.path.join(d, fn)).read()
        m = re.search(r'^\| Entry pointer \| `([^`:]+):(\d+)', text, re.M)
        if not m:
            # a permalink: [`File.java:NN`](https://github.com/.../blob/cassandra-5.0.9/<path>#LNN)
            m = re.search(r'^\| (?:Entry pointer|\*\*Capacity check\*\*) \|[^\n]*?'
                          r'blob/' + re.escape(cfg['tag']) + r'/([^#)\s]+)#L(\d+)', text, re.M)
        out[fn] = (m.group(1), int(m.group(2))) if m else None
    return out


def index(rows, extra_line=None):
    idx = collections.defaultdict(set)
    for r in rows:
        idx[r['path']].add(int(r['line']))
        if extra_line and r.get(extra_line):
            idx[r['path']].add(int(r[extra_line]))
    return idx


def hit(idx, path, line, window):
    lines = idx.get(path, ())
    if line in lines:
        return 'exact'
    if any(abs(line - x) <= window for x in lines):
        return 'near'
    return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--system', default='cassandra', choices=sorted(SYSTEMS))
    ap.add_argument('--window', type=int, default=3)
    ap.add_argument('--list', action='store_true', help='list the cases each source misses')
    a = ap.parse_args()
    global SYSTEM, RES
    SYSTEM = a.system
    RES = os.path.join(REPO, 'codeql-queries', 'results', a.system)

    narrowed = load('NarrowedIfStatements.csv')
    helper = load('HelperGuardedIfStatements.csv')
    enf = load('EnforcementPlaces.csv')
    cap = load('CapacitySetPlaces.csv')

    old_lines = {(r['path'], int(r['line'])) for r in narrowed + helper}

    # primary pattern per enforcement place (one comparison can have several contexts)
    def rank(p):
        if p.startswith('comparison/'):
            return CONTEXT_ORDER.index(p.split('/', 1)[1])
        return 100
    prim = {}
    for r in enf:
        key = (r['path'], int(r['line']), r['pattern'].split('/')[0], r['lhs'], r['op'], r['rhs'], r['detail'] if not r['pattern'].startswith('comparison') else '')
        if key not in prim or rank(r['pattern']) < rank(prim[key]['pattern']):
            prim[key] = r
    enf_units = list(prim.values())

    print('== Enforcement places (EnforcementPlaces.csv) ==')
    print('rows %d, units (one per comparison/call, primary context) %d' % (len(enf), len(enf_units)))
    cnt = collections.Counter(r['pattern'] for r in enf_units)
    new = collections.Counter(r['pattern'] for r in enf_units if (r['path'], int(r['line'])) not in old_lines)
    print('%-34s %7s %7s' % ('pattern', 'units', 'new'))
    for p, n in cnt.most_common():
        print('%-34s %7d %7d' % (p, n, new[p]))
    places = {(r['path'], int(r['line'])) for r in enf_units}
    print('distinct places (path:line) %d, of which not in the if corpus %d' % (
        len(places), len(places - old_lines)))

    print('\n== Capacity-set places (CapacitySetPlaces.csv) ==')
    print('rows %d' % len(cap))
    cnt = collections.Counter(r['pattern'] if r['pattern'] != 'create' else 'create/' + (
        'array' if r['detail'].startswith('new ') and r['detail'].endswith('[]') else 'library') for r in cap)
    for p, n in cnt.most_common():
        print('%-34s %7d' % (p, n))
    src = collections.Counter(r['sizeSource'] for r in cap)
    print('sizeSource: ' + ', '.join('%s %d' % kv for kv in src.most_common(9)))
    fields = {r['target'] for r in cap if r['target']}
    print('distinct fields with a capacity-set place %d' % len(fields))

    print('\n== Recall against the case files (window +-%d) ==' % a.window)
    targets = case_targets()
    missing = [f for f, t in targets.items() if t is None]
    idx_old = index(narrowed + helper, extra_line='helperLine')
    idx_enf = index(enf)
    idx_cap = index(cap)
    tally = collections.Counter()
    lists = collections.defaultdict(list)
    for fn, t in targets.items():
        if t is None:
            continue
        o = hit(idx_old, t[0], t[1], a.window)
        e = hit(idx_enf, t[0], t[1], a.window)
        c = hit(idx_cap, t[0], t[1], a.window)
        tally['cases'] += 1
        tally['old ' + (o or 'miss')] += 1
        tally['new-enforcement ' + (e or 'miss')] += 1
        tally['capacity-set ' + (c or 'miss')] += 1
        if not o:
            tally['old miss -> recovered by new'] += bool(e or c)
            lists['old miss, new hit' if (e or c) else 'missed by all'].append('%s  %s:%d' % (fn, t[0].split('/')[-1], t[1]))
        if not (o or e or c):
            tally['missed by all'] += 1
    for k in ['cases', 'old exact', 'old near', 'old miss', 'old miss -> recovered by new', 'missed by all',
              'new-enforcement exact', 'new-enforcement near', 'capacity-set exact', 'capacity-set near']:
        print('%-34s %5d' % (k, tally[k]))
    if missing:
        print('case files without a parsable target: %d' % len(missing))
    if a.list:
        for k, v in lists.items():
            print('\n-- %s (%d)' % (k, len(v)))
            print('\n'.join(sorted(v)))


if __name__ == '__main__':
    main()
