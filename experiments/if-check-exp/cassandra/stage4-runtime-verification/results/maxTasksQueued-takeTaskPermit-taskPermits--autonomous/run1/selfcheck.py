#!/usr/bin/env python3
"""Independent self-check of run 1 for maxTasksQueued-takeTaskPermit-taskPermits--autonomous. usage: selfcheck.py <logs run dir>
Re-parses the raw files (it does not read summary.txt, analysis output or the EXPECTED lines): the unit probe logs, and for
the cluster the 1-s JMX samples (Pending, RequestsSize, MaxTasksQueued), the heap samples, the class histograms, the stress
outputs and the node's system.log (the configuration it logged at start). phases.json supplies only the time windows."""
import glob, json, os, re, statistics, sys

R = sys.argv[1]
ok = bad = 0
MIB = 1 << 20


def chk(desc, cond):
    global ok, bad
    ok += bool(cond); bad += (not cond)
    print(('ok   ' if cond else 'FAIL ') + desc)


# ------------------------------------------------------------------ unit
def probes(f):
    out = {}
    for l in open(f, errors='replace'):
        if l.startswith('PROBE kind='):
            kv = dict(re.findall(r'(\w+)=(\S+)', l))
            out['drain' if 'DRAIN' in l else int(kv['N'])] = kv
    return out


U = {}
for f in glob.glob(R + '/unit/*-P*-rep*.log'):
    k, p, r = re.match(r'(sep|control)-P(\d+)-(rep\d+)\.log', os.path.basename(f)).groups()
    U[(k, int(p), r)] = probes(f)
print('--- unit')
for (k, p, r), pts in sorted(U.items()):
    ns = sorted(n for n in pts if isinstance(n, int) and n > 0)
    if k == 'sep':
        chk(f'sep P={p} {r}: pending == N and maxQueued 2147483647 at N={ns}', all(int(pts[n]['pending']) == n and int(pts[n]['maxQueued']) == 2147483647 and pts[n]['err'] == 'none' for n in ns))
        d = {n: float(pts[n]['deltaMiB']) * MIB for n in ns}
        s2 = (d[1000000] - d[100000]) / 900000
        chk(f'sep P={p} {r}: slope 1e5->1e6 {s2:.1f} B/task in [{p + 32}, {p + 250}]', p + 32 <= s2 <= p + 250)
        chk(f'sep P={p} {r}: drain completed = last N + 1', int(pts['drain']['completed']) == ns[-1] + 1)
        slow = max(int(pts[n]['maxCallUs']) for n in ns)
        print(f'info sep P={p} {r}: slowest single execute() call {slow} us; per-point maxCallUs ' + ','.join(f'{n}:{pts[n]["maxCallUs"]}' for n in ns))
    else:
        chk(f'control P={p} {r}: accepted 10000 at every N, rejected = N - 10000, queued 10000', all(int(pts[n]['accepted']) == 10000 and int(pts[n]['rejected']) == n - 10000 and int(pts[n]['queued']) == 10000 for n in ns))
        chk(f'control P={p} {r}: heap plateau {pts[ns[0]]["deltaMiB"]} -> {pts[ns[-1]]["deltaMiB"]} MiB', float(pts[ns[-1]]['deltaMiB']) - float(pts[ns[0]]['deltaMiB']) <= 2)
for r in ('rep1', 'rep2'):
    if ('sep', 1024, r) in U and ('control', 1024, r) in U:
        a, b = float(U[('sep', 1024, r)][1000000]['deltaMiB']), float(U[('control', 1024, r)][1000000]['deltaMiB'])
        chk(f'{r}: sep P=1024 at 1e6 holds {a:.1f} MiB vs control {b:.2f} MiB (ratio {a / b:.0f})', a >= 10 * b)
chk('unit: no OutOfMemoryError in any log', all('OutOfMemoryError: ' not in open(f, errors='replace').read() for f in glob.glob(R + '/unit/*-P*-rep*.log')))
chk('unit: every JVM ran with max heap 2048 MiB', all('maxHeapMiB=2048' in open(f, errors='replace').read() for f in glob.glob(R + '/unit/*-P*-rep*.log')))

# ------------------------------------------------------------------ cluster
print('--- cluster')
C = R + '/cluster'
if not os.path.exists(C + '/phases.json'):
    print('no cluster phases'); sys.exit(0)
PH = {p['run']: p for p in json.load(open(C + '/phases.json'))}
S = {}
for r, ph in PH.items():
    a, b = ph['stress_start'] + 60000, ph['stress_end']
    rows = []
    for l in open(f'{C}/samples-jmx-{ph["lifetime"]}.csv').read().splitlines()[1:]:
        v = l.split(',')
        try:
            rows.append(dict(t=int(v[0]), rs=float(v[1]), heap=float(v[2]), act=float(v[3]), pend=float(v[4]), mx=float(v[5]), ntrp=float(v[6])))
        except (ValueError, IndexError):
            pass
    w = [x for x in rows if a <= x['t'] <= b]
    pend = [x['pend'] for x in w]
    hp = [l.split(',') for l in open(C + '/samples-heap.csv').read().splitlines()[1:] if l.split(',')[1] == r]
    hw = [int(h[2]) - int(h[4]) for h in hp if a <= int(h[0]) <= b]
    hb = [int(h[2]) - int(h[4]) for h in hp if ph['base'][0] <= int(h[0]) <= ph['base'][1] + 5000]
    S[r] = dict(n=len(w), P=statistics.median(pend), Pmax=max(pend), Pmin=min(pend), rsmax=max(x['rs'] for x in w) / MIB,
                H=(statistics.median(hw) - statistics.median(hb)) / MIB, nh=len(hw), mx=all(x['mx'] == 2147483647 for x in rows),
                actmax=max(x['act'] for x in rows), flat=max(pend) / max(1, min(pend)))
    print(f'{r}: ' + json.dumps({k: round(v, 2) if isinstance(v, float) else v for k, v in S[r].items()}))
    log = open(f'{C}/system-{r}.log', errors='replace').read() if os.path.exists(f'{C}/system-{r}.log') else ''
    cfg = re.search(r'concurrent_writes=(\d+)', log)
    chk(f'{r}: node log shows concurrent_writes=2' + f' ({cfg.group(1) if cfg else None})', bool(cfg) and cfg.group(1) == '2')
    for key, want in (('native_transport_max_request_data_in_flight', f'{ph["inflight_mib"]}MiB'), ('native_transport_receive_queue_capacity', '0B'), ('native_transport_max_threads', '4096')):
        m = re.search(key + r'=([^,\]]+)', log) or re.search(key + r'=(\S+)', log)
        print(f'info {r}: log {key} = {m.group(1) if m else None}')
    chk(f'{r}: no OutOfMemoryError in the node log', 'OutOfMemoryError: ' not in log)
    chk(f'{r}: MaxTasksQueued 2147483647 at all {len(rows)} 1-s samples', S[r]['mx'] and len(rows) > 300)
    chk(f'{r}: Active max {S[r]["actmax"]:.0f} <= 2', S[r]['actmax'] <= 2)
    chk(f'{r}: window has {S[r]["n"]} JMX samples (>= 280) and {S[r]["nh"]} heap samples (>= 12)', S[r]['n'] >= 280 and S[r]['nh'] >= 12)
    out = open(f'{C}/stress-{r}.out', errors='replace').read()
    m = re.search(r'Total errors\s*:\s*([\d,]+)', out); print(f'info {r}: stress total errors {m.group(1) if m else None}; "Pool is busy" lines {out.count("BusyPoolException")}')
A, B, A2 = S.get('A'), S.get('B'), S.get('A2')
if A and B and A2:
    chk(f'C1 Pn(A2) = {A2["P"]:.0f} >= 10 and Pn(A) = {A["P"]:.0f} >= 2 x Pn(A2)', A2['P'] >= 10 and A['P'] >= 2 * A2['P'])
    chk(f'C1 Pn(B) = {B["P"]:.0f} <= 0.5 x Pn(A)', B['P'] <= 0.5 * A['P'])
    chk(f'C1 RequestsSize max B = {B["rsmax"]:.2f} MiB >= 14.4 (cap reached); A = {A["rsmax"]:.1f} MiB', B['rsmax'] >= 14.4)
    chk(f'C1 Hn(A) - Hn(A2) = {A["H"] - A2["H"]:.1f} MiB >= 0.5 x dP x 32 KiB = {0.5 * (A["P"] - A2["P"]) * 32 / 1024:.1f}', A['H'] - A2['H'] >= 0.5 * (A['P'] - A2['P']) * 32 / 1024)
    chk(f'C1 Hn(A) - Hn(B) = {A["H"] - B["H"]:.1f} MiB >= 0.5 x dP x 32 KiB = {0.5 * (A["P"] - B["P"]) * 32 / 1024:.1f}', A['H'] - B['H'] >= 0.5 * (A['P'] - B['P']) * 32 / 1024)
    chk(f'C2 not triggered: Pn(A)/Pn(A2) = {A["P"] / A2["P"]:.2f} (outside +/-10 % of 1)', not (0.9 <= A['P'] / A2['P'] <= 1.1))
    for r in ('A', 'A2', 'B'):
        print(f'info {r}: plateau-flat max/min of Pending in the window = {S[r]["flat"]:.2f}')
    for r, s in (('A', A), ('B', B), ('A2', A2)):
        per = s['H'] * MIB / s['P'] / 1024
        print(f'info {r}: heap per queued mutation {per:.1f} KiB (sub-prediction >= 32 KiB: {"yes" if per >= 32 else "NO"})')
    chk(f'sub: Pn(A) = {A["P"]:.0f} >= 1000 and Pmax(A) = {A["Pmax"]:.0f} <= 2200', A['P'] >= 1000 and A['Pmax'] <= 2200)
    chk(f'sub: Pn(A2) = {A2["P"]:.0f} in [128, 282]', 128 <= A2['P'] <= 282)
    chk(f'sub: Pmax(B) = {B["Pmax"]:.0f} <= 563 and RequestsSize max B <= 16.5 MiB ({B["rsmax"]:.2f})', B['Pmax'] <= 563 and B['rsmax'] <= 16.5)
    chk(f'sub: RequestsSize max A = {A["rsmax"]:.1f} MiB < 512', A['rsmax'] < 512)
for r in PH:
    hf = f'{C}/histo-{r}-peak.txt'
    if os.path.exists(hf):
        m = {}
        for l in open(hf, errors='replace'):
            p = l.split()
            if len(p) >= 4 and p[3] in ('org.apache.cassandra.db.Mutation', '[B', 'java.util.concurrent.ConcurrentLinkedQueue$Node'):
                m[p[3]] = (int(p[1]), int(p[2]))
        print(f'info {r} histogram at peak: {m}')
print(f'selfcheck: {ok} ok, {bad} FAIL')
