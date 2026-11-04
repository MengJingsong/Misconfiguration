#!/usr/bin/env python3
"""Independent re-parse of run-1 raw files (shares no code with the test or cluster-run.py). usage: selfcheck.py <.../run1>
Unit: re-derives accept/reject per cell, flatness of snapshot bytes/manifest/schema over L, physical delta, heap range, N control from the 'STAGE4 case' lines.
Cluster: re-derives the same from the 'SNAP' lines in summary.txt and cross-reads log.txt (rc of each nodetool snapshot, error text) and listsnapshots-*.out."""
import collections, os, re, sys
R = sys.argv[1]; bad = 0
def rep(ok, m):
    global bad; bad += (not ok); print(('ok   ' if ok else 'FAIL ') + m)
cells = collections.defaultdict(list)
for l in open(f'{R}/unit/test.out'):
    m = re.match(r'STAGE4 case N=(\d+) validation=(\w+) L=(\d+) rep=(\d+) outcome=(\S+) snapFileBytes=(-?\d+) snapFiles=(-?\d+) snapEntries=(-?\d+) manifest=(-?\d+) schema=(-?\d+) physDeltaBytes=(-?\d+) dirsDelta=(-?\d+) heapDelta=(-?\d+) msg=(\S*)', l)
    if m:
        N, v, L, rp, oc, fb, nf, ne, mf, sc, pd, dd, hd, msg = m.groups()
        cells[(int(N), v, int(L))].append(dict(oc=oc, fb=int(fb), mf=int(mf), sc=int(sc), pd=int(pd), hd=int(hd), msg=msg))
rep(len(cells) == 20 and all(len(x) == 3 for x in cells.values()), f'unit: {len(cells)} (N,validation,L) cells x3 reps = {sum(len(x) for x in cells.values())} lines')
for (N, v, L), xs in sorted(cells.items()):
    acc = all(x['oc'] == 'accepted' for x in xs); rej = all(x['oc'] != 'accepted' for x in xs)
    if L <= 255: rep(acc, f'unit N={N} v={v} L={L}: accepted x3')
    elif v == 'true': rep(rej and all(x['oc'] == 'threw:IllegalArgumentException' and x['msg'].startswith('Snapshot_name_must_not_be_more_than_255') and x['fb'] == -1 for x in xs), f'unit N={N} v=true L={L}: IAE with line-2187 text, no dir')
    else: rep(rej and all(x['oc'] == 'threw:FSWriteError' and x['fb'] == -1 and 'Unable_to_create_directory' in x['msg'] for x in xs), f'unit N={N} v=false L={L}: FSWriteError (OS), no dir')
for N in (1000, 100000):
    for v in ('false', 'true'):
        a = {L: [x for x in cells[(N, v, L)]] for L in (1, 100, 255)}
        rep(len({x['fb'] for L in a for x in a[L]}) == 1 and len({x['mf'] for L in a for x in a[L]}) == 1 and len({x['sc'] for L in a for x in a[L]}) == 1, f'unit N={N} v={v}: snapFileBytes/manifest/schema identical in all 9 reps of L=1,100,255')
        pds = {x['pd'] for L in a for x in a[L]}; rep(max(pds) - min(pds) <= 65536, f'unit N={N} v={v}: physical delta across L=1,100,255 range {max(pds)-min(pds)} B (<= 64 KiB), values {sorted(pds)}')
        m = {L: sum(x['hd'] for x in a[L]) / 3 for L in a}; print(f'     heap mean delta N={N} v={v}: ' + ' '.join(f'L{L}={m[L]:.0f}' for L in m) + f' ; all reps range {max(x["hd"] for L in a for x in a[L])-min(x["hd"] for L in a for x in a[L])}')
        rep(abs(m[255] - m[1]) < 1 << 20, f'unit N={N} v={v}: |mean heap(255)-mean heap(1)| = {abs(m[255]-m[1]):.0f} B < 1 MiB')
for v in ('false', 'true'):
    s, b = cells[(1000, v, 100)][0]['fb'], cells[(100000, v, 100)][0]['fb']; rep(b >= 5 * s, f'unit control v={v}: snapshot bytes {b} (100k) vs {s} (1k) = {b/s:.1f}x')
# cluster
C = f'{R}/cluster'; S = open(f'{C}/summary.txt').read().splitlines(); LG = open(f'{C}/log.txt').read()
snaps = []
for l in S:
    m = re.match(r'SNAP (\S+) N=(\d+) v=(\w+) L=(\d+) rc=(-?\d+) snapFileBytes=(-?\d+) files=(-?\d+) manifest=(-?\d+) schema=(-?\d+) physDelta=(-?\d+) heapDelta=(-?\d+) rssDelta=(-?\d+)', l)
    if m: snaps.append(m.groups())
main = [s for s in snaps if not s[0].startswith('noise')]
print(f'cluster: {len(snaps)} SNAP lines ({len(main)} in the designed run)')
def get(tag, L): return [s for s in main if s[0] == tag and int(s[3]) == L][0]
for L in (1, 100, 255): rep(get('N200k', L)[4] == '0', f'cluster N=200k L={L}: nodetool rc 0')
rep(get('N200k', 256)[4] != '0' and get('N200k', 256)[5] == '-1', 'cluster N=200k L=256 (v=true): nonzero rc, no snapshot dir')
rep(len({get('N200k', L)[5] for L in (1, 100, 255)}) == 1 and len({(get('N200k', L)[7], get('N200k', L)[8]) for L in (1, 100, 255)}) == 1, f'cluster N=200k: snapFileBytes/manifest/schema identical for L=1,100,255 ({get("N200k",1)[5]} B)')
rep(len({get('N200k', L)[9] for L in (1, 100, 255)}) == 1, 'cluster N=200k: physical delta identical for L=1,100,255 (' + get('N200k', 1)[9] + ' B)')
rep(get('N2M', 100)[5] == get('N2M', 255)[5] and get('N2M', 100)[9] == get('N2M', 255)[9], f'cluster N=2M: snapFileBytes {get("N2M",100)[5]} and physical delta {get("N2M",100)[9]} identical for L=100,255')
rep(int(get('N2M', 100)[5]) >= 5 * int(get('N200k', 100)[5]), f'cluster control: snapshot bytes {get("N2M",100)[5]} (2M) vs {get("N200k",100)[5]} (200k) = {int(get("N2M",100)[5])/int(get("N200k",100)[5]):.1f}x')
vf = [s for s in snaps if s[0] == 'valfalse']
rep(len(vf) == 2 and [s[4] != '0' for s in vf] == [True, False] and vf[0][5] == '-1', 'cluster validation=false: L=256 fails (no dir), L=255 succeeds')
rep('Snapshot name must not be more than 255 characters long' in LG, 'log.txt contains the line-2187 text (from the validation=true L=256 call)')
rep(len(re.findall(r'Unable to create directory .*/snapshots/a{256}', LG)) >= 1 or 'Unable to create directory' in LG, 'log.txt contains the OS-level "Unable to create directory" error (validation=false L=256)')
rep(len(re.findall(r'Total errors\s*:\s*0', open(f'{C}/stress-200000.out').read() + open(f'{C}/stress-2000000.out').read())) == 2, 'stress: Total errors 0 in both loads')
for L in (1, 100, 255):
    t = open(f'{C}/listsnapshots-N200k-L{L}.out').read(); print('     listsnapshots N=200k L=%d: %s' % (L, [l for l in t.splitlines() if l.startswith('a')][:1]))
print('rc-derived heap deltas (B), main run:', {(s[0], s[3]): s[10] for s in main})
print('RESULT', 'ALL OK' if not bad else f'{bad} FAIL')
