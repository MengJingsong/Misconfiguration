#!/usr/bin/env python3
"""Independent re-parse of raw-all.csv; expectations re-derived from the chunk arithmetic (chunk j holds 256<<j bytes; starts at 256*(2^j-1))."""
import csv, sys
hdr = 'mode type i rep call N S pos0 pos1 soh0 soh1 ret0 ret1 nullb cap d0 d1 heap exc R'.split()
R = []
for l in csv.reader(open(sys.argv[1])):
    if not l or l[0].startswith('#'): continue
    r = dict(zip(hdr, l))
    for k in hdr:
        if k not in ('mode', 'type', 'call', 'exc'): r[k] = int(r[k])
    R.append(r)
ok = bad = 0
def hold(name, c):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print('FAIL', name)
def chunk_start(j): return 256 * (2 ** j - 1)
for r in R:
    if r['mode'] != 'sweep' or r['rep'] == 0 or r['call'] == 'F': continue
    i = r['i']; t = f"{r['type']} i={i} {r['call']} rep{r['rep']}"
    hold(t + ' N and S derive from i', r['N'] == 256 * 2 ** i and r['S'] == chunk_start(i))
    if r['call'] == 'A':
        hold(t + ' positions', r['pos0'] == chunk_start(i) - 32 and r['pos1'] == chunk_start(i))
        hold(t + ' retained == all earlier chunks', r['ret1'] == sum(256 * 2 ** j for j in range(i)))
    else:
        hold(t + ' positions', r['pos0'] == chunk_start(i) and r['pos1'] == chunk_start(i) + 32)
        hold(t + ' retained grows by exactly one chunk of N', r['ret1'] - r['ret0'] == r['N'] and r['cap'] == r['N'])
        if r['type'] == 'ON_HEAP':
            hold(t + ' allocation within [N, N+512]', r['N'] <= r['heap'] <= r['N'] + 512)
        else:
            hold(t + ' direct gauge moved by N, thread bytes small', r['d1'] - r['d0'] == r['N'] and r['heap'] < 1024)
c = {r['call']: r for r in R if r['mode'] == 'control'}
hold('control i=22 chunk is 1 GiB and held', c['B']['cap'] == 2 ** 30 and c['B']['ret1'] == chunk_start(23))
hold('control: S_23 is the hard limit 2^31-256', chunk_start(23) == 2 ** 31 - 256 == c['C1']['pos1'])
hold('control: the call at S_23 raised and left the position', c['C2']['exc'] == 'SpaceExhaustedException' and c['C2']['pos0'] == c['C2']['pos1'] and c['C2']['heap'] < 4096)
print('SELFCHECK %d hold, %d fail' % (ok, bad))
sys.exit(1 if bad else 0)
