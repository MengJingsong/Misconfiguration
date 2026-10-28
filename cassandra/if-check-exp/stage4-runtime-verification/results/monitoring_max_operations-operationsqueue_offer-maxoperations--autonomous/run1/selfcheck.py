#!/usr/bin/env python3
"""Self-check of run 1 (monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous): re-parses unit/run.out and cluster/*/summary.txt."""
import os, re, sys
here = os.path.dirname(os.path.abspath(__file__)); ok = True
def chk(n, c, d=''):
    global ok; ok &= bool(c); print(('PASS ' if c else 'FAIL ') + n + ('  ' + d if d else ''))
rows = [{k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', l)} for l in open(here + '/unit/run.out') if l.startswith('STAGE4 final')]
chk('unit: 18 cells', len(rows) == 18)
for r in rows:
    n, m = r['N'], r['M']; exp = 0 if n == 0 else (m if n < 0 else n); dr = 0 if n <= 0 else m - n
    chk(f"unit rep{r['rep']} N={n} M={m}: queues, Failed/Slow instances == {exp}, Stub == 2x, dropped == {dr}",
        r['queueFailed'] == r['queueSlow'] == r['FailedOperation_instances'] == r['SlowOperation_instances'] == exp and r['Stub_instances'] == 2 * exp and r['droppedFailed'] == r['droppedSlow'] == dr)
for r in rows:
    if r['N'] == 1000 and r['M'] == 10000: chk('unit N=1000 liveDelta ~ 2 x N x 1.2 KiB (2.4 MB +-10 %)', abs(r['liveDelta'] / 2.4e6 - 1) < 0.1, str(r['liveDelta']))
    if r['N'] == -1 and r['M'] == 10000: chk('unit N=-1 liveDelta ~ 24.3 MB', abs(r['liveDelta'] / 24.3e6 - 1) < 0.05, str(r['liveDelta']))
C = {}
for t in sorted(os.listdir(here + '/cluster')):
    f = f'{here}/cluster/{t}/summary.txt'
    if not os.path.exists(f) or t == 'down': continue
    x = open(f).read(); hs = []
    for m in re.finditer(r'HISTO (\S+) live_bytes=(\d+) FailedOperation=(\d+) FailedOperation_bytes=\d+ SlowOperation=(\d+) SlowOperation_bytes=\d+ SinglePartitionReadCommand=(\d+)', x):
        hs.append(dict(tag=m.group(1), live=int(m.group(2)), f=int(m.group(3)), s=int(m.group(4)), c=int(m.group(5))))
    C[t] = dict(h=hs, n=int(re.search(r'READBACK jvm property: (-?\d+)', x).group(1)), drain=int(re.search(r'DRAIN-WARN lines.*=(\d+)', x).group(1)),
                logn=int(re.search(r'max operations (-?\d+)', x).group(1)), yaml='read_request_timeout: 1ms slow_query_log_timeout: 1ms' in x)
chk('cluster: 6 starts of 4 samples', len(C) == 6 and all(len(v['h']) == 4 for v in C.values()))
for t, v in C.items():
    chk(f'{t}: property == log line == name; yaml timeouts 1ms; no drain line', v['n'] == v['logn'] == int(re.search(r'N(m?)(\d+)', t).group(2)) * (-1 if 'm1' in t else 1) and v['yaml'] and v['drain'] == 0)
    n = v['n']
    if n >= 0:
        chk(f'{t}: no sample has Failed or Slow > N', all(h['f'] <= n and h['s'] <= n for h in v['h']), str([(h['f'], h['s']) for h in v['h']]))
chk('N=0: zero instances at every sample', all(h['f'] == 0 and h['s'] == 0 for h in C['N0-r1']['h']))
for t in ('N50-r1', 'N50-r2'): chk(f'{t}: saturated at 50 (Failed and Slow) from 80 s', all(h['f'] == 50 and h['s'] == 50 for h in C[t]['h'][1:]))
chk('N=5000: Slow saturated at 5000 from 80 s', all(h['s'] == 5000 for h in C['N5000-r1']['h'][1:]))
print('INFO N=5000 Failed (never reaches 5000):', [h['f'] for h in C['N5000-r1']['h']])
for t in ('Nm1-r1', 'Nm1-r2'):
    h = C[t]['h']; chk(f'{t}: Failed and Slow strictly grow across samples', all(h[i]['f'] < h[i + 1]['f'] and h[i]['s'] < h[i + 1]['s'] for i in range(1, 3)), str([(x['f'], x['s']) for x in h]))
    chk(f'{t}: Slow exceeds 5000 cap by >= 5x; Failed exceeds 50 cap by >= 50x', h[3]['s'] >= 5 * 5000 and h[3]['f'] >= 50 * 50)
    print(f'INFO {t}: prediction "Failed > 5000, Slow > 40000 at the end": Failed {h[3]["f"]} ({"met" if h[3]["f"] > 5000 else "MISSED"}), Slow {h[3]["s"]} ({"met" if h[3]["s"] > 40000 else "MISSED"})')
fin = {t: C[t]['h'][3]['live'] for t in C}
chk('live bytes: N=-1 above N=50 by > 10 MB; N=5000 above N=50 by 2-6 MB', min(fin['Nm1-r1'], fin['Nm1-r2']) - max(fin['N50-r1'], fin['N50-r2']) > 10e6 and 2e6 < fin['N5000-r1'] - max(fin['N50-r1'], fin['N50-r2']) < 6e6, str(fin))
chk('SinglePartitionReadCommand (pinned) <= Failed+Slow+1024 in every sample', all(h['c'] <= h['f'] + h['s'] + 1024 for v in C.values() for h in v['h']))
print('ALL PASS' if ok else 'SOME FAIL'); sys.exit(0 if ok else 1)
