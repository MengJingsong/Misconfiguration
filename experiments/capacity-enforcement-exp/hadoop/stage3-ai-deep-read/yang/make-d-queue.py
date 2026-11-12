#!/usr/bin/env python3
"""Build Yang's band-D queue (queue.csv) from stage-1 CSVs + stage-2 bands.csv.

Since 2026-11-11 bands.csv also holds the stage-1 extension units (uids E:/C:); they are not in
this queue. Do not re-run this script without excluding them.

Usage (repo root):  experiments/capacity-enforcement-exp/hadoop/stage3-ai-deep-read/yang/make-d-queue.py
Needs codeql-queries/results/hadoop/*.csv (gitignored; regenerate per machine, see
hadoop/stage1-codeql-preprocessing/README.md). Deterministic: same inputs -> same queue.csv.
NEVER regenerate over a queue.csv that has filled-in status columns; write to a new file and merge.

Why a score. Band D = "no resource-bound semantics" (8,935 units, 92% of the corpus). Reading
each as a case is not feasible, and almost all of them are correctly D. The queue therefore orders D
units by how likely stage 2 was to have misbanded them, so a second independent reading (recheck)
finds the promotable ones early. The score is a *prioritisation heuristic*, not a verdict:
nothing is promoted or dropped because of it.
"""
import csv, os, random, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, *['..'] * 5))
RES = os.path.join(REPO, 'codeql-queries', 'results', 'hadoop')
BANDS = os.path.join(REPO, 'experiments', 'capacity-enforcement-exp', 'hadoop', 'stage2-ai-preprocessing', 'bands.csv')
OUT = os.path.join(HERE, 'queue.csv')
SEED = 20261106
TIER3_SAMPLE = 0.05            # fraction of tier 3 put in the sample

# Resource-shaped vocabulary, matched on camelCase/underscore tokens of lhs, rhs, method.
STRONG = {'max', 'maximum', 'limit', 'limits', 'capacity', 'cap', 'quota', 'threshold', 'bytes',
          'buffer', 'buf', 'memory', 'mem', 'heap', 'queue', 'backlog', 'pending', 'retain',
          'retention', 'budget', 'watermark', 'overflow', 'oversize', 'exceed', 'exceeds'}
WEAK = {'size', 'len', 'length', 'count', 'num', 'number', 'total', 'remaining', 'available',
        'free', 'used', 'usage', 'cache', 'pool', 'entries', 'containers', 'blocks', 'replicas',
        'apps', 'capacity', 'resource', 'resources', 'vcores', 'disk', 'space', 'batch', 'chunk'}
# Operands that say "not a resource bound".
BORING = {'id', 'version', 'status', 'state', 'code', 'type', 'time', 'timeout', 'ms', 'millis',
          'interval', 'period', 'timestamp', 'stamp', 'port', 'tx', 'txid', 'index', 'idx', 'pos',
          'offset', 'off', 'compare', 'equals', 'hash', 'generation', 'layout', 'snapshot'}
LITERAL = re.compile(r'^(-?\d+[lL]?|null|true|false|0x[0-9a-fA-F]+|"[^"]*"|\'.\')$')


def toks(s):
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', s)
    return {t.lower() for t in re.findall(r'[A-Za-z]+', s)}


def score(r):
    """Returns (score, signals). Higher = read earlier."""
    t_l, t_r, t_m = toks(r['lhs']), toks(r['rhs']), toks(r.get('method', ''))
    allt = t_l | t_r
    sig, s = [], 0
    strong = (allt | t_m) & STRONG
    weak = allt & WEAK
    if strong: s += 3 + min(len(strong), 2) - 1; sig.append('strong:' + ','.join(sorted(strong)))
    if weak: s += 1 + (1 if len(weak) > 1 else 0); sig.append('weak:' + ','.join(sorted(weak)))
    if r['opClass'] == 'magnitude': s += 1; sig.append('magnitude')
    lit = bool(LITERAL.match(r['rhs'].strip()) or LITERAL.match(r['lhs'].strip()))
    if not lit: s += 1; sig.append('rhs-not-literal')
    if re.search(r'\bConf|conf|Configuration|DFS_|YARN_|_KEY|_DEFAULT', r['lhs'] + r['rhs']):
        s += 2; sig.append('config-operand')
    bor = (allt & BORING) - strong
    if bor and not strong: s -= 2; sig.append('boring:' + ','.join(sorted(bor)))
    if r.get('helper'): s += 1; sig.append('helper')
    return s, ';'.join(sig)


def main():
    nar = list(csv.DictReader(open(os.path.join(RES, 'NarrowedIfStatements.csv'))))
    hel = list(csv.DictReader(open(os.path.join(RES, 'HelperGuardedIfStatements.csv'))))
    seen = {}
    for r in nar:                      # same uid rule as make-stage2-batches.py
        k = (r['path'], r['line']); seen[k] = seen.get(k, 0) + 1
        r['uid'] = '%s:%s#%d' % (r['path'], r['line'], seen[k])
    by_h = {}
    for r in hel: by_h.setdefault('helper:' + r['helper'], []).append(r)
    D = {x['uid']: x for x in csv.DictReader(open(BANDS)) if x['band'] == 'D'}

    units = []
    for r in nar:
        if r['uid'] in D:
            units.append((r['uid'], 'row', r, D[r['uid']]['reason']))
    for h, rs in by_h.items():
        if h in D:
            r = dict(rs[0]); r['uid'] = h
            units.append((h, 'helper', r, D[h]['reason']))
    missing = set(D) - {u[0] for u in units}
    if missing: sys.exit('D units not found in stage-1 CSVs (stale CSV?): %d, e.g. %s' % (len(missing), sorted(missing)[:3]))

    scored = []
    for uid, kind, r, reason in units:
        s, sig = score(r)
        text = '%s | %s.%s | %s %s %s' % (r['moduleDir'], r['declaringType'].split('.')[-1], r['method'], r['lhs'], r['op'], r['rhs'])
        scored.append(dict(uid=uid, kind=kind, score=s, signals=sig, d_reason=reason, text=text))
    scored.sort(key=lambda x: (-x['score'], x['uid']))
    for x in scored:
        x['tier'] = 1 if x['score'] >= 6 else 2 if x['score'] >= 4 else 3
    rng = random.Random(SEED)
    t3 = [x for x in scored if x['tier'] == 3]
    sample = {x['uid'] for x in rng.sample(t3, int(round(len(t3) * TIER3_SAMPLE)))}
    # queue order: tier 1, tier 2, then the tier-3 sample (random order); the rest of tier 3 is
    # listed after, marked `reserve`, to be pulled only if the sample's promote rate says so.
    q = [x for x in scored if x['tier'] == 1] + [x for x in scored if x['tier'] == 2]
    s3 = [x for x in t3 if x['uid'] in sample]; rng.shuffle(s3)
    rest = [x for x in t3 if x['uid'] not in sample]
    for x in s3: x['tier'] = '3-sample'
    for x in rest: x['tier'] = '3-reserve'
    q += s3 + rest
    cols = ['order', 'uid', 'kind', 'tier', 'score', 'signals', 'd_reason', 'text',
            'recheck', 'promoted_band', 'case_file', 'stage4']
    with open(OUT, 'w', newline='') as f:
        w = csv.DictWriter(f, cols); w.writeheader()
        for i, x in enumerate(q, 1):
            x['order'] = i
            for c in cols[8:]: x[c] = ''
            w.writerow(x)
    import collections
    print('units', len(q), dict(collections.Counter(str(x['tier']) for x in q)))


if __name__ == '__main__':
    main()
