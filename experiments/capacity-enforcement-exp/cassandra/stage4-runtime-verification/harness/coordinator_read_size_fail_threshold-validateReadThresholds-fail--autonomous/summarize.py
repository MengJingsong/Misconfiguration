#!/usr/bin/env python3
"""Per-start digest for cluster-run.sh (B3d, amended 2026-10-25). usage: summarize.py <logdir> <start label>
Prints READING lines (one per read phase) from: phases.txt, <start>/gc.log, <start>/vrt.trace, <start>/read-P*/w*.json|lines,
<start>/meters-*.txt. Not the self-check (selfcheck.py re-derives everything independently)."""
import datetime, glob, json, os, re, statistics, sys

L, CUR = sys.argv[1], sys.argv[2]
D = os.path.join(L, CUR)


def wall_ms(stamp):
    return int(datetime.datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000)


phases = [l.split() for l in open(os.path.join(L, 'phases.txt')) if l.startswith(CUR + ' ')]
idle = next((p for p in phases if p[1] == 'idle'), None)
reads = [p for p in phases if p[1] == 'read']
kv = lambda toks: dict(t.split('=', 1) for t in toks if '=' in t)

young, full, hum = [], [], {}
gcfiles = sorted(glob.glob(os.path.join(D, 'gc.log.*'))) + [os.path.join(D, 'gc.log')]  # JVM rotates at 20 MB (fix 2026-10-25)
for gcf in [g for g in gcfiles if os.path.exists(g)]:
    for line in open(gcf, errors='replace'):
        m = re.match(r'\[([^\]]+)\]', line)
        if not m:
            continue
        try:
            t = wall_ms(m.group(1))
        except ValueError:
            continue
        g = re.search(r'GC\((\d+)\) Pause Young .*? (\d+)M->(\d+)M\((\d+)M\)', line)
        if g:
            young.append((t, int(g.group(1)), int(g.group(3))))
        g = re.search(r'GC\((\d+)\) Pause Full .*? (\d+)M->(\d+)M\((\d+)M\)', line)
        if g:
            full.append((t, int(g.group(1)), int(g.group(3))))
        g = re.search(r'GC\((\d+)\) Humongous regions: (\d+)->(\d+)', line)
        if g:
            hum[int(g.group(1))] = int(g.group(3))
base_B = base_b = None
if idle:
    tg = int(kv(idle)['t_gc'])
    f = [x for x in full if x[0] >= tg]
    if f:
        base_B, base_b = f[0][2], hum.get(f[0][1])
print('BASELINE %s full_gc_after_idle B=%sM humongous=%s (full GCs in log: %d)' % (CUR, base_B, base_b, len(full)))

trace = []
tf = os.path.join(D, 'vrt.trace')
if os.path.exists(tf):
    for line in open(tf, errors='replace'):
        m = re.search(r'ms=(\d+)', line)
        if m:
            trace.append((int(m.group(1)), line.strip()))


def med(xs):
    return statistics.median(xs) if xs else None


for p in reads:
    d = kv(p)
    P = int(d['P']); ts, te, tr = int(d['t_start']), int(d['t_end']), int(d['returned'])
    win = [x for x in young if ts + 60000 <= x[0] <= ts + 180000]
    B = [x[2] for x in win]; b = [hum[x[1]] for x in win if x[1] in hum]
    dB = (med(B) - base_B) if (B and base_B is not None) else None
    dH = (med(b) - base_b) if (b and base_b is not None) else None
    tl = [l for (t, l) in trace if ts - 2000 <= t <= tr + 2000]
    rb = [tuple(int(v) for v in re.findall(r'(?:len|cap)=(\d+)', l)) for l in tl if l.startswith('resp-buf len=')]
    full_pages = [x for x in rb if x[0] >= (P - 1) * 65536]
    aborts = sum(1 for l in tl if l.startswith('resp-buf-abort'))
    ra = [int(re.search(r'bytes=(-?\d+)', l).group(1)) for l in tl if l.startswith('read-alloc')]
    gf = sorted(set(re.search(r'size=(\d+) limit=(\d+)', l).groups() for l in tl if l.startswith('guard-fail')))
    gfn = sum(1 for l in tl if l.startswith('guard-fail'))
    la = sorted(set(int(x) for l in tl if l.startswith('local-abort') for x in re.findall(r'attempted to read (\d+) bytes', l)))
    lan = sum(1 for l in tl if l.startswith('local-abort'))
    tot = {'queries': 0, 'ok': 0, 'err': 0, 'rows': 0, 'pages': 0}; errs = {}
    for w in glob.glob(os.path.join(D, 'read-P%d' % P, 'w*.json')):
        j = json.load(open(w))
        for k in tot:
            tot[k] += j.get(k, 0)
        for k, v in j.get('errors_by_class', {}).items():
            errs[k] = errs.get(k, 0) + v

    def meter(tag):
        out = {}
        f = os.path.join(D, 'meters-%s-P%d.txt' % (tag, P))
        if os.path.exists(f):
            for line in open(f):
                parts = line.strip().split('|')
                if len(parts) == 3:
                    out[parts[0].split('name=')[-1] + '.' + parts[1]] = parts[2]
        return out
    mb, ma = meter('before'), meter('after')
    dm = {k: (int(float(ma[k])) - int(float(mb.get(k, 0)))) for k in ma if k.endswith('.Count')}
    mx = {k: ma[k] for k in ma if k.endswith('.Max')}
    print('READING %s P=%d queries=%d ok=%d err=%d rows=%d pages=%d errors=%s meters_delta=%s maxes=%s '
          'gc_window_pauses=%d delta_heap_MiB=%s delta_humongous=%s medB=%s medb=%s '
          'resp_buf_lines=%d full_pages=%d full_len_med=%s full_cap_med=%s resp_buf_abort=%d read_alloc_n=%d read_alloc_med=%s '
          'guard_fail_n=%d guard_fail_set=%s local_abort_n=%d local_abort_X=%s'
          % (CUR, P, tot['queries'], tot['ok'], tot['err'], tot['rows'], tot['pages'], json.dumps(errs, sort_keys=True).replace(' ', ''),
             json.dumps(dm, sort_keys=True).replace(' ', ''), json.dumps(mx, sort_keys=True).replace(' ', ''),
             len(win), dB, dH, med(B), med(b), len(rb), len(full_pages), med([x[0] for x in full_pages]), med([x[1] for x in full_pages]),
             aborts, len(ra), med(ra), gfn, gf[:5], lan, la[:5]))
    # Added 2026-10-28 (harness change H3): digest of the inflight lines (vrt.btm inflight rules, InFlight.java); not the self-check.
    rq = [dict(t.split('=', 1) for t in l.split()[1:] if '=' in t) for l in tl if l.startswith('inflight-req ')]
    rd = [dict(t.split('=', 1) for t in l.split()[1:] if '=' in t) for l in tl if l.startswith('inflight-read ')]
    gi = lambda xs, k: [int(x[k]) for x in xs if k in x]
    print('INFLIGHT %s P=%d req_lines=%d max_n=%s max_H=%s held_med=%s held_max=%s bufs_set=%s cmds_set=%s max_pending=%s max_orphans=%s '
          'read_lines=%d max_m=%s max_rsum=%s own_med=%s'
          % (CUR, P, len(rq), max(gi(rq, 'n'), default=None), max(gi(rq, 'H'), default=None), med(gi(rq, 'held')), max(gi(rq, 'held'), default=None),
             sorted(set(gi(rq, 'bufs'))), sorted(set(gi(rq, 'cmds'))), max(gi(rq, 'pending'), default=None), max(gi(rq, 'orphans'), default=None),
             len(rd), max(gi(rd, 'm'), default=None), max(gi(rd, 'rsum'), default=None), med(gi(rd, 'own'))))
