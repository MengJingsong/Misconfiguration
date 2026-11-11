#!/usr/bin/env python3
"""Readings table for the cluster tier (B3f, as amended 2026-10-26) of SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous.
usage: summarize.py <cluster log dir>   -> prints one line per query and writes <dir>/readings.txt
Reads summary.txt (QUERY lines), bm-<tag>.txt (Byteman lines of the query's node.out slice), heap.tsv and gc.log."""
import datetime, os, re, statistics, sys

D = sys.argv[1]
MiB = 1048576.0


def kv(s):
    return dict(re.findall(r'(\w+)=([^\s|\]]*)', s))


def gc_events(path):
    ev = []
    if not os.path.exists(path):
        return ev
    for ln in open(path, errors='replace'):
        m = re.match(r'\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[-+]\d{4})\]\[[\d.]+s\] GC\((\d+)\) Pause (.*?) (\d+)M->(\d+)M\((\d+)M\)', ln)
        if m:
            t = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S.%f%z')
            ev.append((int(t.timestamp() * 1000), int(m.group(2)), m.group(3), int(m.group(4)), int(m.group(5))))
    return ev


heap = []
for ln in open(os.path.join(D, 'heap.tsv')):
    if ln.startswith('#'):
        continue
    f = ln.split()
    heap.append((int(f[0]), int(f[1]), int(f[3]), int(f[4])))
gcs = gc_events(os.path.join(D, 'gc.log'))
out = []
for ln in open(os.path.join(D, 'summary.txt')):
    if not ln.startswith('QUERY ') or 'SKIPPED' in ln:
        if ln.startswith('QUERY ') and 'SKIPPED' in ln:
            out.append(ln.strip())
        continue
    tag = ln.split()[1]
    parts = ln.split(' | ')
    w = kv(parts[1]); r = kv(parts[2]); b = kv(parts[3]); a = kv(parts[4])
    p1, p2, p3 = int(w['probe_start_ms']), int(w['probe_end_ms']), int(w['post_end_ms'])
    pre = [h[1] for h in heap if p1 - 2000 <= h[0] < p1]
    win = [h for h in heap if p1 <= h[0] <= p3]
    base = statistics.median(pre) if pre else float('nan')
    halloc = (max(h[1] for h in win) - base) / MiB if win else float('nan')
    gcin = [g for g in gcs if p1 <= g[0] <= p3 and 'System.gc()' not in g[2]]
    expl = [g for g in gcs if g[0] < p1 and 'System.gc()' in g[2]]
    gbase = expl[-1][4] if expl else None
    hlive = (max(g[4] for g in gcin) - gbase) if (gcin and gbase is not None) else None
    bm = [l.strip() for l in open(os.path.join(D, 'bm-%s.txt' % tag))] if os.path.exists(os.path.join(D, 'bm-%s.txt' % tag)) else []
    resp = [int(kv(l)['remaining']) for l in bm if l.startswith('BM-RESP') and 'table=g.t ' in l]
    cap = [int(kv(l)['capacity']) for l in bm if l.startswith('BM-RESP') and 'table=g.t ' in l]
    pages = [int(kv(l)['rows']) for l in bm if l.startswith('BM-PAGE') and 'table=g.t ' in l]
    d_tc = int(a['table_coord_reads']) - int(b['table_coord_reads'])
    d_lr = int(a['local_reads']) - int(b['local_reads'])
    d_cr = int(a['coord_reads']) - int(b['coord_reads'])
    s = ('%s outcome=%s rows=%s pages=%s | reads table_coord=%d local=%d (global=%d) | M1 n=%d max=%d min=%d sum=%d maxcap=%d | '
         'M2 n=%d rows=%s | H_alloc=%.0fMiB H_live=%s gcs_in_window=%d [%s] | elapsed_ms=%d'
         % (tag, r.get('outcome'), r.get('rows'), r.get('pages'), d_tc, d_lr, d_cr, len(resp), max(resp or [0]), min(resp or [0]), sum(resp),
            max(cap or [0]), len(pages), ','.join(map(str, pages)) if len(pages) <= 12 else '%d..(%d pages, max %d)' % (pages[0], len(pages), max(pages)),
            halloc, ('%dMiB' % hlive) if hlive is not None else 'n/a', len(gcin),
            '; '.join('GC(%d) %s %dM->%dM' % (g[1], g[2], g[3], g[4]) for g in gcin), int(r.get('q_end_ms', 0)) - int(r.get('q_start_ms', 0))))
    out.append(s)
open(os.path.join(D, 'readings.txt'), 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))
