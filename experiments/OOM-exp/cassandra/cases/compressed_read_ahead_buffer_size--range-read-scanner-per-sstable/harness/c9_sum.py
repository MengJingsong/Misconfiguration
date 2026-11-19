#!/usr/bin/env python3
"""C9 per-run summary (design §2.5 step 6, §2.6). usage: c9_sum.py <rundir>
First line: one-line outcome for runs/summary.txt. Then: B0, peaks, last samples, client totals, OOM excerpt, histogram lines."""
import csv, glob, os, re, sys
from collections import Counter

d = sys.argv[1]
name = os.path.basename(d.rstrip('/'))
notes = open(d + '/notes.txt').read() if os.path.exists(d + '/notes.txt') else ''
MiB = 2 ** 20
rows = []
try:
    for r in csv.DictReader(open(d + '/samples.csv')):
        try:
            rows.append({k: int(v) for k, v in r.items()})
        except (ValueError, TypeError):
            pass
except OSError:
    pass
t_load = int(open(d + '/t_load.txt').read()) if os.path.exists(d + '/t_load.txt') else 0
idle = [r for r in rows if t_load - 10000 <= r['ms'] < t_load and r['direct_count'] >= 0]
load = [r for r in rows if r['ms'] >= t_load and r['direct_count'] >= 0]
out = []
b0c = b0u = 0
if idle:
    b0c = min(r['direct_count'] for r in idle); b0u = min(r['direct_used'] for r in idle)
    out.append(f'B0 (idle 10 s before load): direct Count {b0c}, MemoryUsed {b0u / MiB:.1f} MiB, chunk-cache size {idle[-1]["cc_size"] / MiB:.1f} MiB, '
               f'networking size {idle[-1]["net_size"] / MiB:.1f} MiB, heap used {idle[-1]["heap_used"] / MiB:.0f} MiB, live sstables {idle[-1]["live_sstables"]}')
pk = {}
if load:
    for k in ('direct_count', 'direct_used', 'cc_size', 'cc_used', 'cc_overflow', 'net_size', 'net_overflow', 'read_active', 'read_pending', 'heap_used'):
        r = max(load, key=lambda x: x[k]); pk[k] = r[k]
        out.append(f'peak {k}: {r[k] if "used" not in k and "size" not in k and "overflow" not in k else round(r[k] / MiB, 1)} at load+{(r["ms"] - t_load) / 1000:.1f}s')
    r = max(load, key=lambda x: x['direct_used'])
    out.append(f'at peak direct_used: Count {r["direct_count"]} (dCount {r["direct_count"] - b0c}), dUsed {(r["direct_used"] - b0u) / MiB:.1f} MiB, '
               f'A {r["read_active"]}, pending {r["read_pending"]}, cc_overflow {r["cc_overflow"] / MiB:.1f} MiB, cc_size {r["cc_size"] / MiB:.1f} MiB')
    out.append('last 5 samples (ms_rel, count, used MiB, cap MiB, A, pending, cc_size, cc_ovf, heap MiB):')
    for r in load[-5:]:
        out.append(f'  {(r["ms"] - t_load) / 1000:.1f} {r["direct_count"]} {r["direct_used"] / MiB:.1f} {r["direct_cap"] / MiB:.1f} {r["read_active"]} {r["read_pending"]} '
                   f'{r["cc_size"] / MiB:.1f} {r["cc_overflow"] / MiB:.1f} {r["heap_used"] / MiB:.0f}')
    # A histogram and per-command dCount at samples
    ac = Counter(r['read_active'] for r in load)
    out.append('A distribution (samples): ' + ', '.join(f'{a}:{n}' for a, n in sorted(ac.items())))
    pu = sorted(((r['direct_used'] - b0u) / r['read_active'] / MiB) for r in load if r['read_active'] > 0)
    if pu:
        out.append(f'dUsed per executing command, MiB (samples with A>0, includes the pool growth): median {pu[len(pu) // 2]:.0f}, p90 {pu[int(len(pu) * 0.9)]:.0f}')
    pa = {}
    for r in load:
        pa.setdefault(r['read_active'], []).append(r)
    for a_, rr in sorted(pa.items()):
        rr.sort(key=lambda x: x['direct_used'])
        m = rr[len(rr) // 2]
        out.append(f'  A={a_}: n={len(rr)} median dCount {m["direct_count"] - b0c} dUsed {(m["direct_used"] - b0u) / MiB:.0f} MiB; max dUsed {(rr[-1]["direct_used"] - b0u) / MiB:.0f} MiB')
    per = [((r['direct_count'] - b0c) / r['read_active']) for r in load if r['read_active'] > 0]
    if per:
        per.sort()
        out.append(f'dCount per executing command (samples with A>0): median {per[len(per) // 2]:.0f}, p90 {per[int(len(per) * 0.9)]:.0f}, max {per[-1]:.0f}')
# client
pages = 0; errs = Counter(); perw = Counter(); lat = []; scans = Counter(); first_err = None
for f in sorted(glob.glob(d + '/client/w*.csv')):
    for r in csv.DictReader(open(f)):
        try:
            if r['err']:
                errs[r['err'].split(':')[0]] += 1
                if first_err is None or int(r['ms_end']) < first_err[0]:
                    first_err = (int(r['ms_end']), r['err'])
            else:
                pages += 1; perw[r['worker']] += 1; lat.append(int(r['lat_ms']))
                if r['rows'] != '1000':
                    scans[r['worker']] += 1
        except (KeyError, ValueError):
            pass
cl = {}
if os.path.exists(d + '/client/client.txt'):
    for l in open(d + '/client/client.txt'):
        k, _, v = l.strip().partition('='); cl[k] = v
nw = int(cl.get('streams', 0) or 0)
lat.sort()
out.append(f'client: workers {nw}, workers with >=1 page {len(perw)}, pages ok {pages}, full scans completed {sum(scans.values())}, '
           f'latency median {lat[len(lat) // 2] if lat else -1} ms p99 {lat[int(len(lat) * 0.99)] if lat else -1} ms, errors {dict(errs)}')
if first_err:
    out.append(f'first client error at load+{(first_err[0] - t_load) / 1000:.1f}s: {first_err[1][:200]}')
# system.log
sl = ''
for f in ('system.log', 'debug.log'):
    if os.path.exists(d + '/' + f):
        sl = open(d + '/' + f, errors='replace').read(); break
lines = sl.splitlines()
oom_i = next((i for i, l in enumerate(lines) if l.startswith('java.lang.OutOfMemoryError')), None)
oom = None
if oom_i is not None:
    oom = lines[oom_i]
    out.append('first OOM (system.log):')
    out.extend('  ' + l for l in lines[max(0, oom_i - 1):oom_i + 28])
hist = [l for l in lines if re.search(r'^\s*\d+:\s+\d+\s+\d+\s+(java\.nio\.DirectByteBuffer|jdk\.internal\.ref\.Cleaner|java\.nio\.DirectByteBuffer\$Deallocator|org\.apache\.cassandra\.io\.util\.ThreadLocalReadAheadBuffer\S*|org\.apache\.cassandra\.io\.sstable\.format\.big\.BigTableScanner|org\.apache\.cassandra\.io\.util\.CompressedChunkReader\S*)( |$)', l)]
if hist:
    out.append('histogram lines:')
    out.extend('  ' + l for l in hist[:12])
kind = 'none'
if oom:
    kind = 'direct' if 'Direct buffer memory' in oom else ('heap' if 'Java heap space' in oom else 'other')
gone = re.search(r'NODE GONE at load\+([\d.]+)s', notes)
head = (f'{name}: {notes.splitlines()[0] if notes else ""} | OOM={kind}{" (first: " + oom.strip()[-110:] + ")" if oom else ""} | '
        f'node_gone={gone.group(1) + "s" if gone else "no"} | peak direct {pk.get("direct_used", -1) / MiB:.0f} MiB dCount {pk.get("direct_count", 0) - b0c} '
        f'A_max {pk.get("read_active", -1)} | pages {pages} workers_ok {len(perw)}/{nw} | {"VALID-GATE-FAIL" if "GATE FAILED" in notes else "gate ok"}')
print(head)
print(notes)
print('\n'.join(out))
