#!/usr/bin/env python3
"""selfcheck.py [run dir, default ~/stage4-logs/mta/run1]: independent re-parse of the raw run-1 files of
maxTasksQueued-addTask-taskPermits--autonomous (does not import the run scripts). Prints 'CHECK <id>: holds|DOES NOT HOLD - detail'."""
import glob, json, os, re, statistics, sys
R = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/mta/run1')
MIB = 1 << 20
n_ok = n_bad = 0


def chk(i, cond, detail):
    global n_ok, n_bad
    n_ok += bool(cond); n_bad += (not cond)
    print(f'CHECK {i}: {"holds" if cond else "DOES NOT HOLD"} - {detail}')


# ---------------- unit: re-read each out-*.txt (not summary.txt)
P = {}
D = {}
for f in glob.glob(f'{R}/unit/out-*.txt'):
    for l in open(f, errors='replace'):
        if l.startswith('PROBE'):
            d = dict(kv.split('=', 1) for kv in l.split()[1:]); P[(d['mode'], int(d['c']), int(d['P']), int(d['N']))] = d
        elif l.startswith('DRAIN') and 'skipped' not in l:
            d = dict(kv.split('=', 1) for kv in l.split()[1:]); D[(d['mode'], int(d['c']), int(d['P']), int(d['N']))] = d
sep = {k: v for k, v in P.items() if k[0] == 'sep'}
chk('U1', len(sep) == 16, f'16 sep configurations present ({len(sep)})')
chk('U2', all(int(v['maxTasksQueued']) == 2147483647 and int(v['rejected']) == 0 for v in sep.values()), 'maxTasksQueued 2147483647 and rejected 0 in all 16')
nonoom = {k: v for k, v in sep.items() if int(v['ooms']) == 0}
chk('U3', all(int(v['pending']) == k[3] == int(v['submitted']) and int(v['activeBefore']) == k[1] for k, v in nonoom.items()),
    f'pending == submitted == N and c blockers active in all {len(nonoom)} non-OOM configurations')
oom = {k: v for k, v in sep.items() if int(v['ooms']) == 1}
chk('U4', sorted(oom) == [('sep', 1, 1024, 4000000), ('sep', 8, 1024, 4000000)] and all(v['thrown'] == 'OutOfMemoryError' and int(v['pending']) in (int(v['submitted']), int(v['submitted']) + 1) for v in oom.values()),
    'only the two P=1024 N=4e6 configurations ran out of memory; pending == submitted in both: ' + ', '.join(f'c={k[1]} submitted {v["submitted"]} pending {v["pending"]}' for k, v in sorted(oom.items())))
bad = []
for c in (1, 8):
    for p in (64, 1024):
        vals = [float(sep[('sep', c, p, n)]['bytesPerTask']) for n in (10**5, 10**6, 4 * 10**6) if ('sep', c, p, n) in nonoom]
        m = statistics.mean(vals)
        if not all(abs(v - m) <= 0.1 * m for v in vals) or not all(20 <= v - p <= 300 for v in vals):
            bad.append((c, p, vals))
chk('U5', not bad, 'bytes/task within ±10 % of the mean and k in [20, 300] for every (c, P); k values: ' +
    ', '.join(f'P={p}: {float(sep[("sep", 1, p, 10**6)]["bytesPerTask"]) - p:.1f}' for p in (64, 1024)))
chk('U6', all(0.9 <= float(sep[('sep', 1, p, n)]['bytesPerTask']) / float(sep[('sep', 8, p, n)]['bytesPerTask']) <= 1.1 for p in (64, 1024) for n in (10**5, 10**6) ) and
    0.9 <= float(sep[('sep', 1, 64, 4 * 10**6)]['bytesPerTask']) / float(sep[('sep', 8, 64, 4 * 10**6)]['bytesPerTask']) <= 1.1, 'c=1 / c=8 bytes per task in [0.9, 1.1]')
chk('U7', all(int(D[k]['pendingAfter']) == 0 and float(D[k]['liveAfterMiB']) <= 64 for k in D), f'drain: pendingAfter 0 and live after <= 64 MiB in all {len(D)} drains')
tpe = {k: v for k, v in P.items() if k[0] == 'tpe'}
chk('U8', len(tpe) == 2 and all(int(v['pending']) == 1000 and int(v['rejected']) == 999000 and float(v['liveMiB']) <= 4 for v in tpe.values()), 'control: queue 1000, 999000 rejected, live heap <= 4 MiB in both')
blk = {k: float(v['maxBlockS']) for k, v in sep.items() if float(v['maxBlockS']) >= 5}
chk('U9-miss', not blk, f'(recorded miss if it does not hold) blocks >= 5 s only in: {blk}')
for c in (1, 8):
    pa = 0.0; n = 0
    for l in open(f'{R}/unit/gc-sep-c{c}-P1024-N4000000.log'):
        m = re.search(r'Pause .* ([\d.]+)ms$', l)
        if m: pa += float(m.group(1)); n += 1
    tot = float(oom[('sep', c, 1024, 4000000)]['totalS'])
    chk(f'U10-c{c}', pa / 1000 >= 0.8 * tot, f'GC pauses in the OOM JVM total {pa / 1000:.1f} s ({n} pauses) against the submit loop {tot:.1f} s (inferred: the long blocks are GC thrash near the heap limit)')

# ---------------- cluster
ph = json.load(open(f'{R}/cluster/phases.json'))
ses = open(f'{R}/cluster/session.log', errors='replace').read()
chk('C1', [p['run'] for p in ph] == list('ABCD') and [(p['cap_mib'], p['w']) for p in ph] == [(256, 1), (32, 1), (256, 8), (32, 8)], 'four arms A B C D with (cap, w) = (256,1) (32,1) (256,8) (32,8)')
for p in ph:
    k = p['run']
    ex = p['extra']
    chk(f'C2-{k}', f'native_transport_max_request_data_in_flight={p["cap_mib"]}MiB' in ex and f'native_transport_max_request_data_in_flight_per_ip={p["cap_mib"]}MiB' in ex, f'yaml in-flight and per-IP both {p["cap_mib"]} MiB: {ex}')
chk('C3', len(re.findall(r'native_transport_receive_queue_capacity: 0B', ses)) >= 0 and 'native_transport_receive_queue_capacity: 0B' in open(f'{R}/cluster/summary.txt').read(), 'receive queue 0B in the yaml tail of summary.txt')
chk('C4', len(re.findall(r'-rate threads=6000 .*connectionsPerHost=16 maxPending=1024', ses)) >= 4, 'the stress command of each arm: threads=6000 connectionsPerHost=16 maxPending=1024 (session.log)')
chk('C5', len(re.findall(r'-Xmx2G|MAX_HEAP_SIZE=2G', ses + open(f'{R}/cluster/summary.txt').read())) >= 4, 'heap 2G in each lifetime')
res = {}
hp = [l.split(',') for l in open(f'{R}/cluster/samples-heap.csv').read().splitlines()[1:]]
for lt, p in enumerate(ph, 1):
    rows = []
    for l in open(f'{R}/cluster/samples-jmx-{lt}.csv').read().splitlines()[1:]:
        v = l.split(',')
        try: rows.append([int(v[0])] + [float(x) for x in v[1:6]])
        except ValueError: pass
    a, b = p['stress_start'] + 30000, p['stress_end']
    w = [r for r in rows if a <= r[0] <= b]
    pend = max(r[4] for r in w); rs = max(r[1] for r in w)
    hq = statistics.median([(int(r[2]) - max(0, int(r[4]))) for r in hp if r[1] == p['run'] and a <= int(r[0]) <= b])
    meds = statistics.median([r[4] for r in w])
    res[p['run']] = dict(P=pend, RS=rs, HQ=hq, med=meds, cap=p['cap_mib'] * MIB, mtq={r[5] for r in rows}, n=len(w), mult=sorted({int(r[4]) for r in w if r[4] > 0})[:8])
    chk(f'C6-{p["run"]}', res[p['run']]['mtq'] == {2147483647.0} and len(w) >= 100, f'MaxTasksQueued gauge only 2147483647 at {len(rows)} samples; window {len(w)} samples')
    chk(f'C7-{p["run"]}', 0.8 * res[p['run']]['cap'] <= rs <= res[p['run']]['cap'] + MIB, f'peak RequestsSize {rs / MIB:.2f} MiB for cap {p["cap_mib"]} MiB')
r = res
print('SUPPL peaks P:', {k: v['P'] for k, v in r.items()}, 'medians:', {k: v['med'] for k, v in r.items()}, 'HQ MiB:', {k: round(v['HQ'] / MIB) for k, v in r.items()})
print('SUPPL smallest nonzero pending values in the window:', {k: v['mult'] for k, v in r.items()})
rAB, rCD = r['A']['P'] / r['B']['P'], r['C']['P'] / r['D']['P']
chk('C8', not (4 <= rAB <= 12 and 4 <= rCD <= 12), f'row 1 (scales ~8x) is not satisfied: P(A)/P(B) = {rAB:.2f}, P(C)/P(D) = {rCD:.2f}')
chk('C9', not (rAB < 2 and rCD < 2), f'row 2 (same plateau, both ratios < 2) is not satisfied by the frozen statistic: {rAB:.2f}, {rCD:.2f}')
chk('C10', not all(v['P'] < 20 for v in r.values()), 'row 3 (never grows) is not satisfied: peaks ' + str([v['P'] for v in r.values()]))
chk('C11', not (r['C']['HQ'] >= 1.3 * r['A']['HQ'] and r['D']['HQ'] >= 1.3 * r['B']['HQ']), f'row 4 is not satisfied: HQ(C)/HQ(A) {r["C"]["HQ"] / r["A"]["HQ"]:.2f}, HQ(D)/HQ(B) {r["D"]["HQ"] / r["B"]["HQ"]:.2f}')
chk('C12', not (any(v['P'] * 65536 > 1.25 * v['cap'] for v in r.values())), 'row C-a is not satisfied: P x 64 KiB / cap = ' + str({k: round(v['P'] * 65536 / v['cap'], 2) for k, v in r.items()}))
print(f'selfcheck: {n_ok} hold, {n_bad} DO NOT HOLD (the "-miss" checks and the not-satisfied rows are recorded, not errors)')
