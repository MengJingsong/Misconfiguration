#!/usr/bin/env python3
"""Self-check (results §5) of run 1, internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.
Re-parses the raw files on the run node with its own code (not the run scripts' summaries) and tests them against the frozen
B2f/B2g and B3f/B3g text, typed in here. usage: python3 selfcheck.py [~/stage4-logs/sq2/run1]   exit 1 if a load-bearing check fails.
Load-bearing = the checks the matched rows rest on; "sub" = a sub-prediction, reported but not load-bearing."""
import json, os, re, statistics, sys

R = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/stage4-logs/sq2/run1')
MIB = 1 << 20
fails, subs, n = [], [], 0


def chk(kind, name, cond, detail=''):
    global n
    n += 1
    print(f'{"ok  " if cond else "FAIL"} [{kind}] {name} {detail}')
    if not cond:
        (fails if kind == 'load' else subs).append(name)


# ---------------- unit tier ----------------
U = R + '/unit'
summ = open(U + '/summary.txt').read()
chk('load', 'ConnectionTest controls pass', re.search(r'ConnectionTest: rc=0;.*Tests run: 2, Failures: 0, Errors: 0', summ) is not None)
for i in (1, 2, 3):
    t = open(f'{U}/probe-{i}.out').read()
    P = {}
    for l in t.splitlines():
        if l.startswith('PROBE '):
            kv = dict(re.findall(r'(\w+)=([-\w.\[\],]+)', l))
            P.setdefault(l.split()[1] + ' ' + kv.get('C', ''), []).append(kv)
    for C, nexp in ((65536, 327), (1048576, 1310), (4194304, 4456)):
        f = P[f'U1-full {C}'][0]; r = P[f'U1-released {C}'][0]; s = P[f'U1-stress {C}'][0]
        chk('load', f'rep{i} U1 C={C} successes/pending/endpoint/global exact',
            int(f['successes']) == nexp and int(f['pending']) == nexp * 1000 and int(f['endpointUsing']) == nexp * 1000 - C
            and int(f['globalUsing']) == nexp * 1000 - C, str(f))
        chk('load', f'rep{i} U1 C={C} release: 0 violations, endpoint 0 first at pending in (C-1000, C], final 0,0,0',
            int(r['violations']) == 0 and C - 1000 < int(r['endpointFirstZeroAtPending']) <= C
            and (r['pending'], r['endpointUsing'], r['globalUsing']) == ('0', '0', '0'))
        chk('load', f'rep{i} U1-stress C={C}: 0 barrier violations, 0 cycles not back to 0',
            int(s['barrierViolations']) == 0 and int(s['nonZeroAfterRelease']) == 0)
        chk('load', f'rep{i} U1-stress C={C}: no downward drift (last total within 4096 of first, both <= C+Re)',
            abs(int(s['totalLast']) - int(s['totalFirst'])) <= 4096 and int(s['totalMax']) <= C + 262144)
        chk('sub', f'rep{i} U1-stress C={C}: A1 band (every cycle in [C+Re-4095, C+Re])', int(s['bandViolations']) == 0,
            f'bandViolations={s["bandViolations"]} totalMin={s["totalMin"]}')
    hd, pd = {}, {}
    for C in (8 << 20, 32 << 20, 128 << 20):
        u = P[f'U2 {C}'][0]; c = P[f'U2-closed {C}'][0]
        p, ss, ep, gl, cnt, M, ov = (int(u[k]) for k in ('pending', 's', 'endpointUsing', 'globalUsing', 'count', 'M', 'overloaded'))
        chk('load', f'rep{i} U2 C={C}: pending in (C+1MiB-s, C+1MiB]', C + MIB - ss < p <= C + MIB, f'pending={p}')
        chk('load', f'rep{i} U2 C={C}: endpoint == global == pending - C', ep == gl == p - C)
        chk('load', f'rep{i} U2 C={C}: overloaded == M - accepted > 0', ov == M - cnt and ov > 0)
        chk('load', f'rep{i} U2 C={C}: after close 0,0,0', (c['pending'], c['endpointUsing'], c['globalUsing']) == ('0', '0', '0'))
        hd[C] = int(u['heapDelta']); pd[C] = p
        chk('sub', f'rep{i} U2 C={C}: heapDelta/pending in [1.0, 1.15]', 1.0 <= hd[C] / p <= 1.15, f'{hd[C]/p:.4f}')
        exp = {8 << 20: 9.2, 32 << 20: 33.2, 128 << 20: 129.2}[C]
        chk('sub', f'rep{i} U2 C={C}: heapDelta about {exp} MiB +-5 %', abs(hd[C] / MIB - exp) <= 0.05 * exp, f'{hd[C]/MIB:.2f} MiB')
    for C in (32 << 20, 128 << 20):
        sc = (hd[C] / hd[8 << 20]) / (pd[C] / pd[8 << 20])
        chk('load', f'rep{i} U2 heap scales with pending, C={C} vs 8 MiB (B2g: within 0.8-1.25)', 0.8 <= sc <= 1.25, f'{sc:.4f}')
    m0 = P['U2-control-M0 8388608'][0]
    chk('sub', f'rep{i} B2h M=0 control heapDelta within +-2 MiB', abs(int(m0['heapDelta'])) <= 2 * MIB, m0['heapDelta'])
    for C in (8 << 20, 32 << 20):
        u = P[f'U3 {C}'][0]; c = P[f'U3-closed {C}'][0]
        p, ss = int(u['pending']), int(u['s'])
        chk('load', f'rep{i} U3 C={C}: attempts>=2, pending in (C-s, C], reserves 0, overloaded>0, closed 0',
            int(u['attempts']) >= 2 and C - ss < p <= C and u['endpointUsing'] == '0' and u['globalUsing'] == '0'
            and int(u['overloaded']) > 0 and (c['pending'], c['endpointUsing'], c['globalUsing']) == ('0', '0', '0'))
        chk('sub', f'rep{i} U3 C={C}: heapDelta/pending in [1.0, 1.15]', 1.0 <= int(u['heapDelta']) / p <= 1.15,
            f'{int(u["heapDelta"])/p:.4f}')
m1 = open(U + '/ant-mut-M1.log').read(); m2 = open(U + '/ant-mut-M2.log').read()
chk('load', 'mutant M1 compiled (bytecode loads bytes, lload_3) and fails U1 with UnrecoverableIllegalStateException',
    'M1 bytecode at releaseCapacity:  52: lload_3' in summ and 'UnrecoverableIllegalStateException' in m1 and 'Errors: 1' in m1)
chk('load', 'mutant M2 compiled (guard removed) and fails U1 (AssertionError in Concurrent.release)',
    'mutant M2 diff: 2 changed lines: + if (true)' in summ and 'AssertionFailedError' in m2 and 'ResourceLimits$Concurrent.release' in m2)

# ---------------- cluster tier ----------------
CL = R + '/cluster'
COLS = None


def jmx(path):
    global COLS
    rows = []
    for l in open(path):
        f = l.strip().split(',')
        if f[0] == 'ms':
            COLS = f; continue
        if len(f) == len(COLS) and f[0].isdigit():
            rows.append({k: (int(v) if v.lstrip('-').isdigit() else None) for k, v in zip(COLS, f)})
    return rows


def vt(path):
    rows, cols = [], None
    for l in open(path):
        f = l.strip().split(',')
        if f[0] == 'ms':
            cols = f; continue
        if cols and len(f) == len(cols) and f[1] == '127.0.0.2':
            rows.append({k: (int(v) if v.isdigit() else v) for k, v in zip(cols, f)})
    return rows


def htot(path):
    tot, mut = None, 0
    for l in open(path):
        m = re.match(r'Total\s+\d+\s+(\d+)', l)
        if m: tot = int(m.group(1))
        m = re.match(r'\s*\d+:\s+(\d+)\s+\d+\s+org\.apache\.cassandra\.db\.Mutation(\s|$)', l)
        if m: mut = int(m.group(1))
    return tot, mut


X = {}
for lab, C, G, stop in (('c4m', 4, 1, True), ('c64m', 64, 1, True), ('c256m', 256, 1, True), ('pos', 4, 128, True), ('neg', 64, 1, False)):
    D = f'{CL}/{lab}'; T = json.load(open(D + '/times.json')); C *= MIB; G *= MIB
    rows = jmx(D + '/jmx.csv'); v = vt(D + '/vt-out.csv'); p0 = T['pause']
    win = [r for r in rows if p0 + 5000 <= r['ms'] <= p0 + 25000]
    plat = statistics.median(r['SmallMessagePendingBytes' if 'SmallMessagePendingBytes' in r else 'SmallPendingBytes'] for r in win)
    tasks = statistics.median(r['SmallPendingTasks'] for r in win)
    s = plat / tasks if tasks else None
    ov = [r['SmallDroppedTasksDueToOverload'] for r in rows]
    to = max(r['SmallDroppedTasksDueToTimeout'] for r in rows)
    yaml = open(f'{D}/A-cassandra.yaml').read()
    knob_ok = (f'internode_application_send_queue_capacity: {C//MIB}MiB' in yaml and f'internode_application_send_queue_reserve_global_capacity: {G//MIB}MiB' in yaml
               and 'native_transport_timeout: 60000ms' in yaml and 'hinted_handoff_enabled: false' in yaml)
    chk('load', f'{lab}: A yaml has the label knobs, native_transport_timeout 60 s, hints off', knob_ok)
    alog = open(f'{D}/A-system.log').read()
    chk('load', f'{lab}: no "is now DOWN", no UnrecoverableIllegalStateException, no java.lang.OutOfMemoryError, no ERROR line on A',
        'is now DOWN' not in alog and 'UnrecoverableIllegalState' not in alog and 'java.lang.OutOfMemoryError' not in alog
        and not re.search(r'^ERROR', alog, re.M))
    chk('load', f'{lab}: SmallMessageDroppedTasksDueToTimeout 0 throughout (B3g expiry row excluded)', to == 0, str(to))
    ht, hm = htot(D + '/histo-plateau.txt'); hp, _ = htot(D + '/histo-pre.txt')
    near = min(rows, key=lambda r: abs(r['ms'] - T['h_plat_ms']))
    X[lab] = dict(C=C, G=G, plat=plat, s=s, ht=ht, hp=hp, hm=hm, pb=near['SmallPendingBytes'], pt=near['SmallPendingTasks'])
    if stop:
        chk('load', f'{lab}: plateau in (C+G-s, C+G] (B3f, within one message)', C + G - s < plat <= C + G, f'plateau={plat} C+G={C+G} s={s:.0f}')
        chk('load', f'{lab}: pending flat in window once reached (max over window == plateau)', max(r['SmallPendingBytes'] for r in win) == plat)
        chk('load', f'{lab}: overload drops rise after the plateau (pause+25 s > at pause)',
            min(rows, key=lambda r: abs(r['ms'] - p0 - 25000))['SmallDroppedTasksDueToOverload'] > min(rows, key=lambda r: abs(r['ms'] - p0))['SmallDroppedTasksDueToOverload'])
        vw = [r for r in v if p0 + 5000 <= r['ms'] <= p0 + 25000 and r['pending_bytes'] >= C]
        chk('load', f'{lab}: link reserve == pending - C at every vt window sample at the plateau (the release/acquire mirror)',
            len(vw) > 10 and all(r['using_reserve_bytes'] == r['pending_bytes'] - C for r in vw), f'{len(vw)} samples')
        aft = [r for r in v if r['ms'] >= T['cont'] + 15000]
        # pass 2 (fixed 2026-10-21): stress still writes until t0+90 s, so pending is small but not 0 after SIGCONT; the
        # release test is reserve == max(0, pending - C) with pending < C, and the final read (stress stopped) is 0 and 0
        chk('load', f'{lab}: after SIGCONT+15 s every vt sample has pending < C and reserve == 0 == max(0, pending - C) (no leak at :449)',
            len(aft) > 10 and all(r['pending_bytes'] < C and r['using_reserve_bytes'] == 0 for r in aft),
            f'{len(aft)} samples, max pending {max(r["pending_bytes"] for r in aft)}')
        fin = vt(D + '/vt-final.csv')
        chk('load', f'{lab}: final read after the drain (stress stopped): pending 0, reserve 0',
            fin and fin[-1]['pending_bytes'] == 0 and fin[-1]['using_reserve_bytes'] == 0, str(fin[-1] if fin else None))
        chk('load', f'{lab}: Urgent/Large pending < 1 MiB', max(r['UrgentPendingBytes'] for r in rows) < MIB and max(r['LargePendingBytes'] for r in rows) < MIB)
        chk('sub', f'{lab}: Mutation count ~ PendingTasks +- a few thousand (<= 3000)', abs(hm - near['SmallPendingTasks']) <= 3000, f'{hm} vs {near["SmallPendingTasks"]}')
    else:
        chk('load', f'{lab}: negative control pending < 1 MiB throughout and 0 drops',
            max(r['SmallPendingBytes'] for r in rows) < MIB and max(ov) == 0)
pre = [x['hp'] for x in X.values()]; N = max(pre) - min(pre)
neg = X['neg']
k = {}
for lab in ('c4m', 'c64m', 'c256m', 'pos'):
    dH = X[lab]['ht'] - neg['ht']; X[lab]['dH'] = dH; k[lab] = dH / X[lab]['pb']
    chk('load', f'{lab}: dH clears 3N (A7)', dH > 3 * N, f'dH={dH} 3N={3*N}')
print(f'N={N} k={ {a: round(b, 3) for a, b in k.items()} }')
kk = [k['c4m'], k['c64m'], k['c256m']]
chk('load', 'B3g row 1 heap clause: single k across runs 1-3 within +-25 % (EXPECTED to fail per the run readings)',
    all(abs(x - statistics.mean(kk)) <= 0.25 * statistics.mean(kk) for x in kk))
row4 = max(kk) / min(kk) > 2
print(f'B3g row 4 trigger (k varies > 2x across C): {row4} (max/min {max(kk)/min(kk):.3f})')
sl1 = (X['c64m']['dH'] - X['c4m']['dH']) / (X['c64m']['pb'] - X['c4m']['pb'])
sl2 = (X['c256m']['dH'] - X['c64m']['dH']) / (X['c256m']['pb'] - X['c64m']['pb'])
icpt = X['c4m']['dH'] - sl2 * X['c4m']['pb']
print(f'marginal heap per counted byte: 4->64 MiB {sl1:.3f}, 64->256 MiB {sl2:.3f}; intercept {icpt/MIB:.1f} MiB; '
      f'pos predicted from line {(icpt + sl2*X["pos"]["pb"])/MIB:.1f} MiB vs measured {X["pos"]["dH"]/MIB:.1f} MiB')
chk('load', 'positive control plateau ~132 MiB while run 1 ~5 MiB', 130 * MIB < X['pos']['plat'] <= 132 * MIB and X['c4m']['plat'] <= 5 * MIB)
print(f'\n{n} checks; load-bearing FAIL: {len(fails)} {fails}\nsub-prediction misses: {len(subs)} {subs}')
sys.exit(1 if [f for f in fails if 'EXPECTED to fail' not in f] else 0)
