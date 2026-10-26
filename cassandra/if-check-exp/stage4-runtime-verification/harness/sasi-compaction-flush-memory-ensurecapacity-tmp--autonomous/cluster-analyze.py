#!/usr/bin/env python3
"""Cluster-tier analysis. Usage: python3 -I cluster-analyze.py <outdir> [<outdir> ...]   (each has summary.json, histo-<arm>.jsonl, pool.csv, lts-trace.txt, segments-<arm>.txt)
Raw-file driven; prints a table per arm. No verdict here."""
import sys, os, re, json, csv, collections
def trace_groups(path):
    cur = {}; gs = []
    for l in open(path):
        m = re.match(r'(\w+) ms=(\d+) thr=(\S+) alen=(\d+)(?: tmplen=(\d+))?', l)
        if not m: continue
        k, ms, thr, alen, tl = m.group(1), int(m.group(2)), m.group(3), int(m.group(4)), m.group(5)
        if k == 'SORT_BEGIN':
            g = dict(alen=alen, thr=thr, t0=ms, t1=None, tmps=[]); cur[thr] = g; gs.append(g)
        elif k == 'SORT_END': cur[thr]['t1'] = ms
        elif k in ('TMP_INIT', 'TMP_GROW'): cur[thr]['tmps'].append(int(tl))
    return gs
def overlap(gs):
    ev = []
    for g in gs:
        if g['t1'] is None: continue
        ev += [(g['t0'], 1), (g['t1'], -1)]
    cur = mx = 0
    for t, d in sorted(ev, key=lambda x: (x[0], x[1])):
        cur += d; mx = max(mx, cur)
    return mx
for out in sys.argv[1:]:
    s = json.load(open(out + '/summary.json'))
    print('== %s  heap=%s xmx=%s error=%s' % (out, s['heap'], s.get('xmx'), s.get('error')))
    gs_all = trace_groups(out + '/lts-trace.txt') if os.path.exists(out + '/lts-trace.txt') else []
    pool = list(csv.DictReader(open(out + '/pool.csv'))) if os.path.exists(out + '/pool.csv') else []
    for a in s['arm_results']:
        name = a['arm']; M = a['cap']; L = a['L']
        t0, t1 = a['t_compact_start'], a['t_compact_end'] + 6000
        hs = []
        p = out + '/histo-%s.jsonl' % name
        if os.path.exists(p):
            for l in open(p):
                try: h = json.loads(l)
                except Exception: continue
                if 'total_bytes' in h and h['total_bytes']: hs.append(h)
        base = a['baseline']['total_bytes']; basej = a['baseline'].get('[J', 0)
        pk = max([h['total_bytes'] for h in hs], default=0); pkj = max([h.get('[J', 0) for h in hs], default=0)
        win = [g for g in gs_all if t0 <= g['t0'] <= t1 and g['thr'].startswith('SASI-General')]
        sizes = sorted([g['alen'] for g in win], reverse=True)
        big = win and max(win, key=lambda g: g['alen'])
        gact = max([int(r['general_active']) for r in pool if t0 <= int(r['epoch_ms']) <= t1], default=-1)
        heapmax = max([int(r['heap_used']) for r in pool if t0 <= int(r['epoch_ms']) <= t1], default=-1)
        cl = a.get('compact_log', {})
        nseg = cl.get('Flushed index segment', 0)
        mib = None if M == 'def' else int(M)
        print('arm %-6s mode=%-8s M=%-4s L=%-4s compact_rc=%s secs=%.0f alive=%s' % (name, a['mode'], M, L, a.get('compact_rc'), (a['t_compact_end'] - a['t_compact_start']) / 1000, a.get('node_alive')))
        print('   baseline live %.1f MiB, peak live %.1f MiB, increment %.1f MiB%s, samples %d; peak [J %.1f MiB (baseline %.1f)' % (
            base / 1048576, pk / 1048576, (pk - base) / 1048576, '' if not mib else ' = %.2f x M' % ((pk - base) / 1048576 / mib), len(hs), pkj / 1048576, basej / 1048576))
        print('   log: Flushed index segment=%s Index flush to=%s OOM=%s Failed=%s' % (nseg, cl.get('Index flush to'), cl.get('OutOfMemoryError'), cl.get('Failed to build index segment')))
        if win:
            print('   SASI-General sorts in window: %d, largest alen=%d (8*alen=%.1f MiB) tmp max=%.1f MiB, sizes top3=%s, max concurrent sorts (trace)=%d, max SASI-General active (pool.csv)=%d, max heap used (pool.csv) %.1f MiB' % (
                len(win), big['alen'], 8 * big['alen'] / 1048576, 8 * max(big['tmps'] or [0]) / 1048576, sizes[:3], overlap(win), gact, heapmax / 1048576))
        else:
            print('   no SASI-General sorts in window; max SASI-General active=%d, max heap used %.1f MiB' % (gact, heapmax / 1048576))
        print('   sstables at compaction %d, index files after: %s' % (len(a.get('sstables', [])), [x[1] for x in a.get('si_after', [])]))
