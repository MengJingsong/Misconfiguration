#!/usr/bin/env python3
"""Independent self-check (step 4): re-parses the raw files (U-lines.txt; each run's base.csv, run.csv, nmt*.txt, client.txt, times.txt,
yaml.diff, run.log) WITHOUT reduce.py and evaluates the frozen verdict lines U1-U5 and C1-C7 of the case file.
usage: selfcheck.py UNIT_DIR CLUSTER_DIR"""
import csv, glob, os, re, statistics, sys
MiB = 1 << 20
ud, cd = sys.argv[1], sys.argv[2]
def kv(line):
    d = {}
    for p in line.strip().split(',')[2:]:
        if '=' in p:
            k, v = p.split('=', 1); d[k] = v
    return d
print('== UNIT ==')
arms = []
for l in open(os.path.join(ud, 'U-lines.txt')):
    l = l.strip(); name = l.split(',')[1]
    d = kv(l); arms.append((name, d, l))
def I(d, k): return int(d[k])
ok = {}
A = [(n, d) for n, d, _ in arms if n == 'A']
S = I(A[0][1], 'S'); res = []
for n, d in A:
    L, Q, C = I(d, 'L'), I(d, 'Q'), I(d, 'C'); pl = I(d, 'plateau'); adm = I(d, 'admittedBytes')
    c = (L - S < pl <= L) and (0 <= adm - pl <= C * Q) and I(d, 'maxUsing') <= L and I(d, 'final') == 0 and I(d, 'ok') == I(d, 'offered')
    res.append(c); print('A L=%d Q=%d plateau=%d adm-plateau=%d (C*Q=%d) maxUsing<=L:%s -> %s' % (L, Q, pl, adm - pl, C * Q, I(d, 'maxUsing') <= L, c))
inc = True
for Q in (1 << 20, 65536):
    ps = [I(d, 'plateau') for n, d in A if I(d, 'Q') == Q]; inc &= ps == sorted(ps) and len(set(ps)) == len(ps)
print('plateaus increase with L at each Q:', inc, '| spread at Q=1MiB (max-min):', max(I(d, 'plateau') for n, d in A if I(d, 'Q') == 1 << 20) - min(I(d, 'plateau') for n, d in A if I(d, 'Q') == 1 << 20), 'S=', S)
g = {n: d for n, d, _ in arms if n != 'A'}
B = g['B']; thr_ok = I(B, 'plateau') <= I(B, 'L') and I(B, 'overloaded') > 0 and I(B, 'entered') + I(B, 'overloaded') == I(B, 'offered') and I(B, 'ok') == I(B, 'entered')
print('B throw: plateau<=L %s, overloaded=%s, entered+overloaded=offered %s -> %s' % (I(B, 'plateau') <= I(B, 'L'), B['overloaded'], I(B, 'entered') + I(B, 'overloaded') == I(B, 'offered'), thr_ok))
Cc = g['C']; run_ok = 8 * MiB - S < I(Cc, 'afterSignalUsing') <= 8 * MiB
print('C runtime: afterSet=%s (unchanged=%s) afterSignal=%s in (8MiB-S,8MiB]: %s' % (Cc['afterSetUsing'], Cc['afterSetUsing'] == Cc['plateau'], Cc['afterSignalUsing'], run_ok))
print('S sentinel equal:', g['S']['limit'] == g['S']['maxMemoryOver40'])
D, E = g['D'], g['E']; S4 = I(D, 'S')
print('D v4 default: plateau=%d L=%d over=%d bytes = %.2f messages; plateau>=L %s' % (I(D, 'plateau'), I(D, 'L'), I(D, 'plateau') - I(D, 'L'), (I(D, 'plateau') - I(D, 'L')) / S4, I(D, 'plateau') >= I(D, 'L')))
print('E v4 throw: plateau<=L %s overloaded=%s' % (I(E, 'plateau') <= I(E, 'L'), E['overloaded']))
Xa, Xb, Xc = g['Xa'], g['Xb'], g['Xc']
ca = 1 * MiB - S < I(Xa, 'plateau') <= 1 * MiB and I(Xa, 'globalUsing') == I(Xa, 'plateau')
cb = I(Xb, 'final') == 0 and I(Xb, 'maxUsing') < I(Xb, 'L')
cc = I(Xc, 'admittedBytes') <= I(Xc, 'C') * I(Xc, 'Q') and I(Xc, 'plateau') == 0
print('controls: a(global 1MiB) %s  b(unblocked) %s  c(L=0) %s' % (ca, cb, cc))
allfinal = all(I(d, 'final') == 0 for n, d, _ in arms if n != 'S')
print('all arms final=0:', allfinal)
U3 = all(res) and inc and thr_ok and run_ok and g['S']['limit'] == g['S']['maxMemoryOver40'] and I(D, 'plateau') >= I(D, 'L') and I(E, 'plateau') <= I(E, 'L') and ca and cb and cc and allfinal
print('UNIT U3 holds:', U3)

print('\n== CLUSTER ==')
def rows(path):
    with open(path) as fh: return [r for r in csv.DictReader(fh) if r['t_ms'].strip().isdigit()]
summ = {}
for rd in sorted(glob.glob(os.path.join(cd, 'r[0-9]*'))):
    lab = os.path.basename(rd)
    if 'INVALID' in lab: continue     # failed attempts (no load sent) are kept on the node but are not readings
    base, run = rows(rd + '/base.csv'), rows(rd + '/run.csv')
    bd = statistics.median(int(r['direct_used']) for r in base)
    rs = [int(r['requests_size']) for r in run]; pa = [int(r['paused']) for r in run]; du = [int(r['direct_used']) for r in run]
    cl = open(rd + '/client.txt').read()
    m = re.search(r"RESULT.*\{(.*)\}", cl); cnt = dict(re.findall(r"'([\w:]+)': (\d+)", m.group(1))) if m else {}
    yd = open(rd + '/yaml.diff').read()
    knob = re.findall(r'native_transport_max_request_data_in_flight(?:_per_ip)?: \S+', yd)
    summ[lab] = dict(peak=max(rs), paused=max(pa), dd=(max(du) - bd) / MiB, ok=int(cnt.get('ok', 0)), conn=int(cnt.get('connected', 0)),
                     errs=sum(int(v) for k, v in cnt.items() if k.startswith(('err', 'connect_err'))), knob=knob, rows=run)
    print('%-22s peak=%d (%.3f MiB) paused_max=%d dDirect=%.1f MiB ok=%s connected=%s errs=%s knob=%s' % (lab, max(rs), max(rs) / MiB, max(pa), (max(du) - bd) / MiB,
          cnt.get('ok'), cnt.get('connected'), summ[lab]['errs'], knob))

# ---- cluster verdict lines (frozen B3g) ----
Sb = 4194304 + 100        # upper bound of one request's body (4 MiB blob + key + framing); the measured per-message count is printed below
r = lambda p: [k for k in summ if k.startswith(p)][0]
v5 = [r('r1'), r('r2'), r('r3')]; v4 = [r('r4'), r('r5'), r('r6')]
Ls = {'r1': 8 * MiB, 'r2': 32 * MiB, 'r3': 128 * MiB, 'r4': 8 * MiB, 'r5': 32 * MiB, 'r6': 128 * MiB}
per_msg = {k: summ[k]['peak'] / round(summ[k]['peak'] / 4128836) for k in v5}
print('\nper-message counted bytes implied by v5 peaks (S - 64KiB queue):', {k: round(v) for k, v in per_msg.items()})
band = all(Ls[k[:2]] - Sb < summ[k]['peak'] <= Ls[k[:2]] for k in v5)
incr = summ[v5[0]]['peak'] < summ[v5[1]]['peak'] < summ[v5[2]]['peak']
paused_ge1 = all(summ[k]['paused'] >= 1 for k in v5)
allok = all(summ[k]['ok'] == 512 and summ[k]['conn'] == 64 and summ[k]['errs'] == 0 for k in v5)
dd = [summ[k]['dd'] for k in v5]; dd_up = dd[2] > dd[0]
r7 = summ[r('r7')]; c7 = 16 * MiB - Sb < r7['peak'] <= 16 * MiB
print('V5 band L-S<peak<=L:', band, '| increasing:', incr, '| PausedConnections max>=1 in each:', paused_ge1, [summ[k]['paused'] for k in v5], '| 512/512 ok:', allok)
print('V5 direct rise r1,r2,r3 (MiB):', [round(x, 1) for x in dd], '| r3>r1:', dd_up, '| positive control r7 in (16MiB-S,16MiB]:', c7, r7['peak'])
mins = {k: min(int(x['paused']) for x in summ[k]['rows']) for k in summ}
print('PausedConnections min per run (negative = gauge accounting error):', mins)
print('V4 peaks:', [summ[k]['peak'] for k in v4], 'all in [L, L+64*S]:', all(Ls[k[:2]] <= summ[k]['peak'] <= Ls[k[:2]] + 64 * Sb for k in v4), '| V4 paused max:', [summ[k]['paused'] for k in v4], '| V4 direct rise:', [round(summ[k]['dd'], 1) for k in v4])
r8 = summ[r('r8')]; print('r8 global peak %d: > 32MiB %s, <= 2*32MiB %s' % (r8['peak'], r8['peak'] > 32 * MiB, r8['peak'] <= 64 * MiB))
r9 = summ[r('r9')]; rows9 = r9['rows']
js = open(os.path.join(cd, r('r9'), 'jmxset.txt')).read(); tset = int(re.search(r'after=\d+ t=(\d+)', js).group(1))
tm = dict(x.split('=') for x in open(os.path.join(cd, r('r9'), 'times.txt')).read().split())
late = [int(x['requests_size']) for x in rows9 if int(x['epoch_ms']) >= tset + 60000 and int(x['epoch_ms']) <= int(tm['client_end_ms'])]
print('r9: samples >=60 s after the JMX set within load: %d, max %d (<= 8 MiB: %s), knob after set: %s' % (len(late), max(late), max(late) <= 8 * MiB, re.search(r'after=(\d+)', js).group(1)))
conn_ok = all(summ[k]['conn'] == 64 for k in summ)
print('all runs connected 64/64:', conn_ok)
row = 'C1' if not (conn_ok and c7) else ('C2' if (any(summ[k]['peak'] > Ls[k[:2]] for k in v5) or not incr) else ('C3' if (band and incr and paused_ge1 and allok and dd_up) else ('C4' if (band and incr and not dd_up) else 'C7 (no matching row: C3 fails on the PausedConnections clause)' if (band and incr and allok and dd_up and not paused_ge1) else 'C7')))
print('CLUSTER verdict line by the frozen rules:', row)
