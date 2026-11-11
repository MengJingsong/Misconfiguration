#!/usr/bin/env python3
"""Self-check of run 1 (results §5) for batch_size_fail_threshold-verifyBatchSize-failThreshold--guided. Independent of
SendBatches' joining and of analyze.py: re-reads the raw Byteman trace in file order, cuts it into requests (each request
outside the control writes exactly one dec and one exe line; exe is the last), assigns them to the arms in the order the
run scripts sent them (11 arms x 20, the control writes nothing), and recomputes per arm the median dec + exe, the
median bst, the siz operand and threshold, and the rej count. It also counts the disallow log lines and, for the cluster
tier, re-reads the JMX poll files for the networking pool.
usage: selfcheck.py <tier> <trace> <log> [<poll dir>]"""
import glob, os, re, statistics, sys

tier, trace, logf = sys.argv[1], sys.argv[2], sys.argv[3]
polls = sys.argv[4] if len(sys.argv) > 4 else None
ARMS = ['ctl16k'] + [f't{t}k-b{b}m' for t in (50, 500, 5120) for b in (1, 4, 16)]
FAIL = {'ctl16k': 50 * 1024, **{f't{t}k-b{b}m': t * 1024 for t in (50, 500, 5120) for b in (1, 4, 16)}}
lines = [l.split() for l in open(trace) if l[:4] in ('dec ', 'exe ', 'bst ', 'siz ', 'rej ')]
reqs, cur = [], []
for p in lines:
    cur.append(p)
    if p[0] == 'exe':
        reqs.append(cur); cur = []
print(f'{tier}: {len(lines)} trace lines, {len(reqs)} requests (expected {len(ARMS) * 20}), {len(cur)} lines left over')
ok = len(reqs) == len(ARMS) * 20 and not cur


def val(p, key):
    for t in p[1:]:
        if t.startswith(key + '='):
            return int(t.split('=')[1])
    return None


for i, a in enumerate(ARMS):
    rs = reqs[i * 20:(i + 1) * 20]
    kinds = {tuple(sorted(x[0] for x in r)) for r in rs}
    tot = [sum(val(x, 'bytes') for x in r if x[0] in ('dec', 'exe')) for r in rs]
    bst = [val(x, 'bytes') for r in rs for x in r if x[0] == 'bst']
    siz = {(val(x, 'size'), val(x, 'fail')) for r in rs for x in r if x[0] == 'siz'}
    rej = sum(1 for r in rs for x in r if x[0] == 'rej')
    good = all(f == FAIL[a] for _, f in siz) and len(siz) == 1 and rej == (20 if next(iter(siz))[0] > FAIL[a] else 0)
    ok &= good
    print(f'{a}: kinds {sorted(kinds)}; median dec+exe {statistics.median(tot):.0f}; median bst {statistics.median(bst):.0f}; '
          f'siz {sorted(siz)}; rej {rej} {"ok" if good else "MISMATCH"}')
n = sum(1 for l in open(logf, errors='replace') if 'exceeding specified threshold' in l and 'see batch_size_fail_threshold' in l)
r = sum(1 for p in lines if p[0] == 'rej')
print(f'disallow log lines {n}, rej lines {r} {"ok" if n == r == 140 else "MISMATCH"}')
ok &= n == r == 140
if polls:
    for f in sorted(glob.glob(polls + '/poll-*.csv')):
        rows = [l.strip().split(',') for l in open(f)]
        rows = [[int(x) for x in p] for p in rows if len(p) == 5 and 'ERR' not in p]
        print(f'{os.path.basename(f)}: {len(rows)} samples; heap used max {max(r[1] for r in rows)}; pool UsedSize '
              f'{rows[0][2]} -> max {max(r[2] for r in rows)} -> last {rows[-1][2]}; OverflowSize last {rows[-1][4]}')
print('SELFCHECK', 'ok' if ok else 'MISMATCH')
