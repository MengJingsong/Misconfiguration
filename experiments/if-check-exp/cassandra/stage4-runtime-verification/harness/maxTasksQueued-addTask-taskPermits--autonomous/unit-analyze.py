#!/usr/bin/env python3
"""unit-analyze.py <unit log dir>: B2f / B2g checks of maxTasksQueued-addTask-taskPermits--autonomous with audit
amendments U1-U4 (2026-10-22) on out-*.txt. One 'EXPECTED: <check> — yes|NO' line per check and a tally. A NO is
recorded, not fatal; the AI judges it in the results file. No threshold here is chosen after a reading: all come from
B2f, B2h and U3/U4."""
import glob, re, sys, statistics

L = sys.argv[1]
res = {'yes': 0, 'no': 0}


def ex(desc, cond):
    res['yes' if cond else 'no'] += 1
    print(f'EXPECTED: {desc} — {"yes" if cond else "NO"}')


def parse():
    rows, drains = {}, {}
    for f in sorted(glob.glob(f'{L}/out-*.txt')):
        for l in open(f, errors='replace'):
            if l.startswith('PROBE'):
                d = dict(kv.split('=', 1) for kv in l.split()[1:])
                key = (d['mode'], int(d['c']), int(d['P']), int(d['N']))
                rows[key] = d
            elif l.startswith('DRAIN') and 'skipped' not in l:
                d = dict(kv.split('=', 1) for kv in l.split()[1:])
                drains[(d['mode'], int(d['c']), int(d['P']), int(d['N']))] = d
    return rows, drains


rows, drains = parse()
sep = {k: v for k, v in rows.items() if k[0] == 'sep'}
want = [(c, p, n) for c in (1, 8) for p in (64, 1024) for n in (10**4, 10**5, 10**6, 4 * 10**6)]
ex(f'all 16 sep configurations ran (found {len(sep)})', all(('sep',) + w in sep for w in want))
for (m, c, p, n), d in sorted(sep.items()):
    oom_arm = (p == 1024 and n == 4 * 10**6)
    tag = f'sep c={c} P={p} N={n}'
    ex(f'{tag}: c blockers active before the N submissions (activeBefore {d["activeBefore"]} == {c})', int(d['activeBefore']) == c)
    ex(f'{tag}: no RejectedExecutionException (rejected {d["rejected"]})', int(d['rejected']) == 0)
    ex(f'{tag}: maxTasksQueued == 2147483647 (read {d["maxTasksQueued"]})', int(d['maxTasksQueued']) == 2147483647)
    ex(f'{tag}: no block of 1e5 submits >= 5 s (max {d["maxBlockS"]} s)', float(d['maxBlockS']) < 5)
    if oom_arm:
        s, pend = int(d['submitted']), int(d['pending'])
        ex(f'{tag}: U-a OutOfMemoryError thrown to the submitter (ooms {d["ooms"]}, thrown {d["thrown"]}), submitted {s} < N', int(d['ooms']) == 1 and d['thrown'] == 'OutOfMemoryError' and s < n)
        ex(f'{tag}: U-a pending {pend} in {{submitted, submitted+1}} ({s})', pend in (s, s + 1))
    else:
        ex(f'{tag}: pending == N (read {d["pending"]})', int(d['pending']) == n and int(d['submitted']) == n)
        ex(f'{tag}: no OOM (ooms {d["ooms"]})', int(d['ooms']) == 0)
        dr = drains.get(('sep', c, p, n))
        ex(f'{tag}: U-d drained: pendingAfter 0 and liveAfter <= 64 MiB (read {dr and dr["pendingAfter"]}, {dr and dr["liveAfterMiB"]})',
           dr is not None and int(dr['pendingAfter']) == 0 and float(dr['liveAfterMiB']) <= 64)
for c in (1, 8):
    for p in (64, 1024):
        vals = {n: float(sep[('sep', c, p, n)]['bytesPerTask']) for n in (10**5, 10**6, 4 * 10**6) if ('sep', c, p, n) in sep and int(sep[('sep', c, p, n)]['ooms']) == 0}
        if len(vals) >= 2:
            mean = statistics.mean(vals.values())
            ex(f'c={c} P={p}: bytes/task within ±10 % of the mean {mean:.1f} for N in {sorted(vals)} ({", ".join(f"{v:.1f}" for v in vals.values())})',
               all(abs(v - mean) <= 0.10 * mean for v in vals.values()))
            ks = [v - p for v in vals.values()]
            ex(f'c={c} P={p}: k = bytes/task - P in [20, 300] ({", ".join(f"{k:.1f}" for k in ks)})', all(20 <= k <= 300 for k in ks))
for p in (64, 1024):
    for n in (10**5, 10**6, 4 * 10**6):
        a, b = sep.get(('sep', 1, p, n)), sep.get(('sep', 8, p, n))
        if a and b and int(a['ooms']) == 0 and int(b['ooms']) == 0:
            r = float(a['bytesPerTask']) / float(b['bytesPerTask'])
            ex(f'P={p} N={n}: bytes/task c=1 over c=8 = {r:.3f} in [0.9, 1.1]', 0.9 <= r <= 1.1)
tpe = {k: v for k, v in rows.items() if k[0] == 'tpe'}
ex(f'positive control ran (found {len(tpe)} tpe rows)', len(tpe) >= 1)
for (m, c, p, n), d in sorted(tpe.items()):
    tag = f'tpe c={c} P={p} N={n}'
    ex(f'{tag}: queue plateaus at 1000 (pending {d["pending"]}, submitted {d["submitted"]}) and {n - 1000} rejected (read {d["rejected"]})',
       int(d['pending']) == 1000 and int(d['submitted']) == 1000 and int(d['rejected']) == n - 1000 and d['thrown'] == 'RejectedExecutionException')
    ex(f'{tag}: retained heap flat beyond 1000 (liveMiB {d["liveMiB"]} <= 4)', float(d['liveMiB']) <= 4)
print(f'unit-analyze: {res["yes"]} yes, {res["no"]} NO')
