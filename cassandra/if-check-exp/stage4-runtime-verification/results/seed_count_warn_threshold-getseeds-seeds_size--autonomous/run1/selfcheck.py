#!/usr/bin/env python3
"""Self-check of run 1 (seed_count_warn_threshold-getseeds-seeds_size--autonomous): re-parses unit/run.out and cluster/*/summary.txt + excerpt.txt."""
import os, re, sys
here = os.path.dirname(os.path.abspath(__file__)); ok = True
def chk(n, c, d=''):
    global ok; ok &= bool(c); print(('PASS ' if c else 'FAIL ') + n + ('  ' + d if d else ''))
U = {}
for l in open(here + '/unit/run.out'):
    if l.startswith('STAGE4 final'):
        d = dict(re.findall(r'(\w+)=(\S+)', l)); U.setdefault((d['arm'], int(d['k_in_yaml']), 'low' if d['threshold'].startswith('unset') else 'high'), []).append(d)
chk('unit: 27 cells', sum(len(v) for v in U.values()) == 27)
for k in (25, 1000, 20000):
    lo, hi, p = U[('U', k, 'low')], U[('U', k, 'high')], U[('P', k, 'low')]
    chk(f'K={k}: arm U returned==K in all 6 cells', all(int(d['returned']) == k for d in lo + hi))
    chk(f'K={k}: WARN only when T below K', all(d['warn_lines'] == '1' for d in lo) and all(d['warn_lines'] == '0' for d in hi))
    chk(f'K={k}: deepBytes identical across T', len({d['deepBytes'] for d in lo + hi}) == 1, lo[0]['deepBytes'])
    chk(f'K={k}: arm P returned==20 and deepBytes small', all(int(d['returned']) == 20 for d in p) and int(p[0]['deepBytes']) < int(lo[0]['deepBytes']), f"P {p[0]['deepBytes']} U {lo[0]['deepBytes']}")
    chk(f'K={k}: databaseDescriptorGetSeeds == returned', all(d['databaseDescriptorGetSeeds'] == d['returned'] for d in lo + hi + p))
d1, d2 = int(U[('U', 1000, 'low')][0]['deepBytes']), int(U[('U', 20000, 'low')][0]['deepBytes'])
chk('deepBytes 20000:1000 within 15 % of 20', abs(d2 / d1 / 20 - 1) < 0.15, f'{d2 / d1:.2f}')
chk('K=20000: arm P deepBytes < 1/100 of arm U', int(U[('P', 20000, 'low')][0]['deepBytes']) * 100 < d2)
hp = lambda a, k, t: [int(d['heapPerCopy']) for d in U[(a, k, t)]]
chk('K=20000: heapPerCopy U equal across T within 20 %', abs(sum(hp('U', 20000, 'low')) / sum(hp('U', 20000, 'high')) - 1) < 0.2)
chk('K=20000: heapPerCopy P < 1/100 of U', max(hp('P', 20000, 'low')) * 100 < min(hp('U', 20000, 'low')), f"P {hp('P', 20000, 'low')}")
chk('K=1000: heapPerCopy U equal across T within 20 %', abs(sum(hp('U', 1000, 'low')) / sum(hp('U', 1000, 'high')) - 1) < 0.2)
# cluster
C = {}
for t in sorted(os.listdir(here + '/cluster')):
    f = f'{here}/cluster/{t}/summary.txt'
    if not os.path.exists(f) or t == 'down': continue
    x = open(f).read(); h = re.search(r'HISTO live_bytes=(\d+) InetAddressAndPort=(\d+) \((\d+) B\) OutboundConnections=(\d+)', x)
    gs = open(f'{here}/cluster/{t}/excerpt.txt').read()
    C[t] = dict(warn=int(re.search(r'WARN lines=(\d+)', x).group(1)), live=int(h.group(1)), ia=int(h.group(2)), oc=int(h.group(4)), seeds=int([l for l in gs.split('\n') if re.fullmatch(r'\d+', l.strip())][1]), rb=re.search(r'READBACK jvm threshold property: (\S+)', x).group(1))
chk('cluster: 6 starts', len(C) == 6)
for t, d in C.items(): print('INFO', t, d)
for K, lo, hi in ((25, 'U-k25-tdef', 'U-k25-t50'), (1000, 'U-k1000-tdef', 'U-k1000-t2000')):
    a, b = C[lo], C[hi]
    chk(f'K={K}: WARN present (T default) / absent (T=2K)', a['warn'] > 0 and b['warn'] == 0)
    chk(f'K={K}: live, InetAddressAndPort, OutboundConnections equal within 25 % across T', all(abs(a[x] / b[x] - 1) < 0.25 for x in ('live', 'ia', 'oc')))
    chk(f'K={K}: nodetool getseeds lists K-1 peers (self excluded) in both', a['seeds'] == K - 1 and b['seeds'] == K - 1, f"{a['seeds']} {b['seeds']}")
    chk(f'K={K}: OutboundConnections == K-1 (every seed contacted)', a['oc'] == K - 1 and b['oc'] == K - 1, f"{a['oc']} {b['oc']}")
chk('K=1000 more than K=25 (live bytes, outbound)', C['U-k1000-tdef']['live'] > C['U-k25-tdef']['live'] + 20_000_000 and C['U-k1000-tdef']['oc'] > 30 * C['U-k25-tdef']['oc'] / 1.2)
p = C['P-k1000-tdef']
chk('arm P K=1000: getseeds lists 19 peers (cap 20 minus self)', p['seeds'] == 19, str(p['seeds']))
chk('arm P K=1000: OutboundConnections <= 21 and far below U', p['oc'] <= 21 and p['oc'] * 10 < C['U-k1000-tdef']['oc'], str(p['oc']))
chk('arm P K=1000: live bytes below U by > 30 MB', C['U-k1000-tdef']['live'] - p['live'] > 30_000_000, str(C['U-k1000-tdef']['live'] - p['live']))
print('ALL PASS' if ok else 'SOME FAIL'); sys.exit(0 if ok else 1)
