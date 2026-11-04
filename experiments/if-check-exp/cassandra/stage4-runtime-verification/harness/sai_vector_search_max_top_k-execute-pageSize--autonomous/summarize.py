#!/usr/bin/env python3
"""Readings table for the cluster tier of sai_vector_search_max_top_k-execute-pageSize--autonomous (amended B3d).
usage: summarize.py <cluster log dir>  -> writes <dir>/readings.txt and prints it.
Heap delta = peak heap_used in [probe_start, probe_end + 3 s] - median heap_used in [probe_start - 2 s, probe_start), from heap-V<V>.tsv.
Humongous = the 'Humongous regions: a->b' value a of the first GC in gc.log* after probe_end and within 5 s of post_end
(the next query's explicit GC; None for the last query of a phase)."""
import glob, os, re, statistics, sys
from datetime import datetime

d = sys.argv[1]
MiB = 1048576.0
heap = {}
for f in glob.glob(os.path.join(d, 'heap-V*.tsv')):
    v = int(re.search(r'heap-V(\d+)\.tsv', f).group(1))
    rows = []
    for line in open(f):
        if line.startswith('#') or not line.strip():
            continue
        t, u, c, y, o = line.split()
        rows.append((int(t), int(u), int(y), int(o)))
    heap[v] = rows
gcs = []  # (epoch_ms, humongous_before)
pend = {}
for f in sorted(glob.glob(os.path.join(d, 'gc.log*'))):
    for line in open(f, errors='replace'):
        m = re.match(r'\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3})([+-]\d{4})\]\[[^\]]*\](?:\[info\]\[gc,heap\s*\])? GC\((\d+)\) Humongous regions: (\d+)->(\d+)', line)
        if m:
            ts = datetime.strptime(m.group(1) + m.group(2), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000
            gcs.append((ts, int(m.group(4)), f, int(m.group(3))))
gcs.sort()
out = []
qs = {}
for line in open(os.path.join(d, 'summary.txt')):
    if not line.startswith('QUERY V'):
        continue
    tag = line.split()[1]
    v, L, r = re.match(r'V(\d+)-L(\d+)-r(\d+)', tag).groups()
    v, L = int(v), int(L)
    g = lambda k: re.search(k + r'=(\S+)', line).group(1)
    ps, pe = int(g('probe_start_ms')), int(g('probe_end_ms'))
    hs = heap.get(v, [])
    pre = [u for t, u, y, o in hs if ps - 2000 <= t < ps]
    win = [(t, u, y, o) for t, u, y, o in hs if ps <= t <= pe + 3000]
    if pre and win:
        base = statistics.median(pre)
        peak = max(u for t, u, y, o in win)
        delta = peak - base
        ngc = (win[-1][2] - win[0][2]) + (win[-1][3] - win[0][3])
        # include a GC between the last pre sample and the first window sample
        lastpre = [x for x in hs if x[0] < ps][-1]
        ngc += (win[0][2] - lastpre[2]) + (win[0][3] - lastpre[3])
    else:
        base = peak = delta = float('nan'); ngc = -1
    pst = int(g('post_end_ms'))
    hum = next((h for ts, h, f, n in gcs if pe < ts <= pst + 5000), None)  # the next query's explicit GC, same JVM
    m = re.search(r'err=\[(.*?)\] warntext', line)
    rec = dict(v=v, L=L, r=int(r), outcome=g('outcome'), rows=int(g('rows')), more=g('has_more'), vbytes=int(g('value_bytes')),
               tw=int(g('topk_warnings')), err=m.group(1) if m else '', delta=delta, base=base, npre=len(pre), nwin=len(win),
               gcs=ngc, hum=hum, ms=pe - ps)
    qs.setdefault((v, L), []).append(rec)
    out.append('Q %s outcome=%s rows=%d has_more=%s value_bytes=%d topk_warnings=%d delta_B=%d delta_MiB=%.1f base_MiB=%.1f '
               'npre=%d nwin=%d gcs=%d humongous_next_gc=%s client_ms=%d err=[%s]' % (
                   tag, rec['outcome'], rec['rows'], rec['more'], rec['vbytes'], rec['tw'], delta, delta / MiB, base / MiB,
                   len(pre), len(win), ngc, hum, rec['ms'], rec['err'][:160]))
out.append('')
out.append('V L | outcomes | rows | has_more | topk_warnings | delta MiB r1,r2,r3 | median delta B (MiB)')
for (v, L), rs in sorted(qs.items()):
    ds = [x['delta'] for x in rs]
    med = statistics.median(ds)
    out.append('%d %d | %s | %s | %s | %s | %s | %d (%.1f)' % (v, L, ','.join(x['outcome'] for x in rs), ','.join(str(x['rows']) for x in rs),
               ','.join(x['more'] for x in rs), ','.join(str(x['tw']) for x in rs), ','.join('%.0f' % (x / MiB) for x in ds), med, med / MiB))
open(os.path.join(d, 'readings.txt'), 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))
