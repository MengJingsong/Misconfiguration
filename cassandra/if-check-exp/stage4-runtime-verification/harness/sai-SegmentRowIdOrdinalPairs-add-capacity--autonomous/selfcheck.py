#!/usr/bin/env python3
"""Independent self-check of the cluster tier (and unit tier) from the raw files only (no use of cluster-run.py's windows or EXPECTED lines).
usage: selfcheck.py <logroot>   (e.g. ~/stage4-logs/sr/run1). Prints tables used in results 4.1 / 5.1.
Cluster: counts SR lines per (value, cap, caller) over each sr-trace.out and fits alloc_ctor = a*arrlen + b; parses the trace-*.json fallback lines;
JFR: allocation events whose top frame is SegmentRowIdOrdinalPairs.<init> (sizes). Unit: recomputes delta - (16+8N) from unit/summary.txt."""
import collections, glob, json, os, re, subprocess, sys
root = sys.argv[1]
print('== cluster: Byteman lines per value / cap / caller')
fit = []
for v in ('default', '1000', '64000'):
    f = f'{root}/{v}/sr-trace.out'
    c = collections.Counter(); al = collections.defaultdict(list)
    for l in open(f):
        m = re.match(r'SR ts=(\d+) thr=\S+ cap=(\d+) arrlen=(\d+) alloc_ctor=(\d+) caller=(\S+)', l)
        assert m, l
        cap, arr, a, caller = int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)
        c[(cap, caller)] += 1; al[cap].append(a); assert arr == 2 * cap
        fit.append((arr, a))
    for (cap, caller), n in sorted(c.items()):
        a = al[cap]; base = 16 + 8 * cap
        print(f'  L={v:>7} cap={cap:>6} lines={n:>4} caller={caller:<45} alloc min/max={min(a)}/{max(a)} min-(16+8cap)={min(a)-base} max-(16+8cap)={max(a)-base} outliers>min+1024={sum(1 for x in a if x>min(a)+1024)}')
print('== fit alloc_ctor = s*arrlen + b over all lines (min per arrlen):')
mins = {}
for arr, a in fit: mins[arr] = min(a, mins.get(arr, 1 << 60))
xs = sorted(mins); n = len(xs); sx = sum(xs); sy = sum(mins[x] for x in xs)
sxx = sum(x * x for x in xs); sxy = sum(x * mins[x] for x in xs)
s = (n * sxy - sx * sy) / (n * sxx - sx * sx); b = (sy - s * sx) / n
print(f'  points={n} slope per int={s:.4f} (4.0 expected for 2 ints x 4 B... i.e. 8 B per pair) intercept={b:.1f} (16 + K)')
print('== trace fallback / path lines')
for v in ('default', '1000', '64000'):
    for t in sorted(glob.glob(f'{root}/{v}/trace-*.json')):
        j = json.load(open(t)); ev = [e for e in j.get('trace_events', []) if re.search(r'Switching to ORDER BY|SAI materialized|Search range covers', e)]
        print(f'  {v:>7} {os.path.basename(t)[6:-5]:<22} {ev[:1]}')
print('== JFR (real allocation size of int[] with top frame SegmentRowIdOrdinalPairs.<init>)')
for v in ('default', '1000', '64000'):
    out = subprocess.run(['jfr', 'print', '--json', '--events', 'jdk.ObjectAllocationOutsideTLAB,jdk.ObjectAllocationInNewTLAB', f'{root}/{v}/sr.jfr'],
                         capture_output=True, text=True).stdout
    ev = json.loads(out)['recording']['events']; sizes = collections.Counter(); other = 0
    for e in ev:
        fr = (e['values'].get('stackTrace') or {}).get('frames') or []
        if fr and fr[0]['method']['name'] == '<init>' and fr[0]['method']['type']['name'].endswith('SegmentRowIdOrdinalPairs'):
            sizes[(e['type'].split('.')[-1], e['values']['objectClass']['name'], e['values']['allocationSize'])] += 1
    print(f'  {v:>7} total alloc events {len(ev)}; SR-<init> events by (type, class, allocationSize): ' + str(dict(sorted(sizes.items(), key=lambda x: x[0][2]))))
print('== unit: delta - (16+8N) per (mode, flags, N), all reps')
d = collections.defaultdict(list); thrown = []
for l in open(f'{root}/unit/summary.txt'):
    if not l.startswith('RESULT'): continue
    kv = dict(x.split('=', 1) for x in l.split() if '=' in x)
    flags = re.search(r'flags=(.*?) xmx=', l).group(1)
    if 'ctor_throw' in kv: thrown.append((kv['mode'], flags, kv['N'], kv['ctor_throw'], kv.get('msg'))); continue
    N = int(kv['N']); d[(kv['mode'], flags, N)].append(int(kv['alloc_ctor_plus_new']) - (16 + 8 * N) + (0 if N else 0))
for k, vv in sorted(d.items(), key=lambda x: (x[0][1], x[0][0], x[0][2])): print(f'  {k[0]:<5} {k[1]:<28} N={k[2]:<11} extra over 16+8N: {sorted(set(vv))} reps={len(vv)}')
for t in thrown: print('  threw:', t)
