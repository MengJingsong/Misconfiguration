#!/usr/bin/env python3
"""Independent re-parse for the self-check of batch_size_warn_threshold-verifyBatchSize-size--autonomous (results §5).
usage: selfcheck.py unit <test.out> <warn-size.trace> | selfcheck.py cluster <cluster dir>
Differs from analyze.py on purpose: Byteman lines are joined to each REQUEST by the request's own ms0..ms1 interval (not to an arm window),
warn/rej/ERROR counts come from regexes over the raw logs, and medians are taken from the per-request joins."""
import collections, glob, os, re, statistics, sys

def reqs_of(path):
    out = []
    for l in open(path):
        if l.startswith('req '):
            m = re.match(r'req arm=(\S+) k=(\d+) type=(\S+) parts=(\d+) rows=(\d+) nominal=(\d+) outcome=(\S+) warns=(\d+) wsize=(-?\d+) ms0=(\d+) ms1=(\d+)', l)
            out.append(dict(arm=m[1], k=int(m[2]), parts=int(m[4]), outcome=m[7], warns=int(m[8]), wsize=int(m[9]), ms0=int(m[10]), ms1=int(m[11])))
    return out

def trace_of(path):
    t = collections.defaultdict(list)
    for l in open(path):
        m = re.match(r'(bst|siz|rej) thread=\S+ (?:bytes=(-?\d+) )?ms=(\d+)(?: (.*))?', l)
        if m:
            t[m[1]].append((int(m[3]), int(m[2]) if m[2] else None, m[4] or ''))
    for v in t.values():
        v.sort()
    return t

def join(reqs, t):
    """Pairs by order: in each arm the k-th request gets the k-th bst, siz and (when it threw) rej line in time order, taken from the
    lines between the arm's first ms0 and last ms1 + 50. d['paired'] is True when the counts match (bst, siz == requests; rej == the number of errors) and every
    paired line's ms lies in [ms0, ms1] of its request (1 ms clock resolution: equality allowed)."""
    arms = collections.OrderedDict()
    for r in reqs:
        arms.setdefault(r['arm'], []).append(r)
    res = []
    for a, rs in arms.items():
        lo, hi = rs[0]['ms0'], rs[-1]['ms1'] + 50
        lines = {tag: [x for x in t[tag] if lo <= x[0] <= hi] for tag in ('bst', 'siz', 'rej')}
        nerr = sum(1 for r in rs if r['outcome'] != 'ok')
        counts_ok = len(lines['bst']) == len(rs) and len(lines['siz']) == len(rs) and len(lines['rej']) == nerr
        errs = [r for r in rs if r['outcome'] != 'ok']
        for k, r in enumerate(rs):
            d = dict(r)
            d['bst'] = [lines['bst'][k]] if counts_ok else []
            d['siz'] = [lines['siz'][k]] if counts_ok else []
            d['rej'] = []
            if counts_ok and r['outcome'] != 'ok':
                d['rej'] = [lines['rej'][errs.index(r)]]
            d['paired'] = counts_ok and all(r['ms0'] <= x[0] <= r['ms1'] for tag in ('bst', 'siz') for x in d[tag])
            res.append(d)
    return res

def say(s): print(s)

def unit(f, tr):
    reqs = reqs_of(f); t = trace_of(tr); J = join(reqs, t)
    by = collections.defaultdict(list)
    for d in J: by[d['arm']].append(d)
    rows = {m[1]: int(m[2]) for l in open(f) for m in [re.match(r'STAGE4 rows arm=(\S+) count=(\d+)', l)] if m}
    say('arm | requests | counts match and every paired line is inside the request interval | warned reqs | errors | rej | size | bst median | rows')
    meds = {}
    for a, v in by.items():
        one = all(d['paired'] for d in v)
        sz = {int(re.search(r'size=(\d+)', d['siz'][0][2])[1]) for d in v if d['siz']}
        b = [d['bst'][0][1] for d in v if d['bst']]
        meds[a] = statistics.median(b)
        say(f"{a} | {len(v)} | {one} | {sum(1 for d in v if d['warns'])} | {sum(1 for d in v if d['outcome']!='ok')} | {sum(len(d['rej']) for d in v)} | {sorted(sz)} | {meds[a]:.0f} | {rows.get(a)}")
    for p in ('p20', 'p200'):
        lo = [meds[f'w{w}-{p}'] for w in (1, 5)]; hi = [meds[f'w{w}-{p}'] for w in (1024, 65536)]
        say(f'{p}: warned-arm bst medians {lo}, silent-arm {hi}: difference {statistics.mean(lo)-statistics.mean(hi):.0f} B = {100*(statistics.mean(lo)-statistics.mean(hi))/statistics.mean(lo):.1f} % of the warned arms; per mutation {(statistics.mean(lo)-statistics.mean(hi))/(20 if p=="p20" else 200):.0f} B')
    # first-use effect: spread inside an arm
    for a in ('w1-p20', 'w1024-p20'):
        b = sorted(d['bst'][0][1] for d in by[a]); say(f'{a}: bst min {b[0]} median {statistics.median(b):.0f} max {b[-1]}')

def cluster(D):
    reqs = reqs_of(D + '/requests.txt'); t = trace_of(D + '/trace-all.txt'); J = join(reqs, t)
    by = collections.defaultdict(list)
    for d in J: by[d['arm']].append(d)
    say('phase | requests | paired ok | warned | errors | rej | bst median | bst mean of the lowest 90 %')
    med = {}
    for a, v in by.items():
        b = sorted(d['bst'][0][1] for d in v if d['bst'])
        low = b[:int(len(b) * 0.9)] or b
        med[a] = statistics.median(b)
        say(f"{a} | {len(v)} | {all(d['paired'] for d in v)} | {sum(1 for d in v if d['warns'])} | {sum(1 for d in v if d['outcome']!='ok')} | {sum(len(d['rej']) for d in v)} | {med[a]:.0f} | {statistics.mean(low):.0f}")
    for k in ('W1a', 'W1b', 'W2a', 'W2b'):
        a, b = med[f'L1-{k}'], med[f'L2-{k}']
        n = 50 if k.startswith('W1') else 20480
        say(f'L1-{k} vs L2-{k}: {a:.0f} vs {b:.0f}: +{a-b:.0f} B = {100*(a-b)/a:.1f} % of L1; {(a-b)/n:.0f} B per mutation')
    for k, ref in (('L1live-W1', 'L2-W1a'), ('L1live-W2', 'L2-W2a')):
        say(f'{k} vs {ref}: {med[k]:.0f} vs {med[ref]:.0f}: {100*(med[k]-med[ref])/med[ref]:.1f} %')
    for f in sorted(glob.glob(D + '/system-*.log')):
        txt = open(f, errors='replace').read()
        w = len(re.findall(r'(?m)^WARN .*Batch for \[ks\.t\] is of size', txt)); e = len(re.findall(r'(?m)^ERROR .*Batch for \[ks\.t\] is of size', txt))
        u = len(re.findall(r'(?m)^WARN .*Unlogged batch covering', txt)); oom = len(re.findall(r'OutOfMemory', txt))
        say(f'{os.path.basename(f)}: WARN "Batch for" {w}, ERROR "Batch for" {e}, WARN "Unlogged batch covering" {u}, OutOfMemory {oom}')
    # post-GC occupancy from the raw GC logs, per phase window (UTC)
    import csv, datetime
    win = {}
    for l in open(D + '/requests.txt'):
        m = re.match(r'arm (\S+) (begin|end) ms=(\d+)', l)
        if m: win.setdefault(m[1], {})[m[2]] = int(m[3])
    for r in csv.DictReader(open(D + '/phases.csv')):
        p = r['phase']; g = D + f"/gc-{r['lifetime']}.log"
        if not os.path.exists(g): g = D + '/gc-L1.log'
        vals = []
        for l in open(g):
            m = re.match(r'\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)\+0000\] GC\(\d+\) Pause (?:Young|Full|Remark|Cleanup).*? (\d+)M->(\d+)M\(', l)
            if m:
                ts = datetime.datetime.strptime(m[1], '%Y-%m-%dT%H:%M:%S.%f').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000
                if win[p]['begin'] <= ts <= win[p]['end'] + 1000: vals.append(int(m[3]))
        say(f"{p}: post-GC occupancy after {len(vals)} pauses, max {max(vals) if vals else None} MiB, median {statistics.median(vals) if vals else None}; disk {r['disk_bytes']}; writes {int(r['writes_after'])-int(r['writes_before'])}")

if __name__ == '__main__':
    unit(sys.argv[2], sys.argv[3]) if sys.argv[1] == 'unit' else cluster(sys.argv[2])
