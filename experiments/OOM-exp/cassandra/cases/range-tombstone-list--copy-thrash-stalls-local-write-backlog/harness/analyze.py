#!/usr/bin/env python3
"""R17 stage-2 per-run analysis (from U11's analyze.py). usage: python3 -I analyze.py <run dir> [...] -> one JSON object per run.
Reads logs/driver.log (W window, stop reason), logs/poll.log (JMX 1 s), logs/hot.csv + blob.csv (client cumulative per second),
logs/gc.log (pauses, STW fraction per 60 s window), hist/*.txt (jcmd GC.class_histogram), logs/rss.log, OOM lines.
Derived (design §2.6): mu_h = r17.rt applied writes/s over W (WriteLatency count), blob applies/s, backlog_blob(t) =
blob requests sent - r17.blob applied (x 4 MiB = U_D3), its peak and least-squares slope, time to OOM, STW max over 60 s,
max share of hot writes timed out per 60 s."""
import glob, json, os, re, sys
from datetime import datetime

MB = 1024 * 1024
BLOB = 4194304
ARR = {'[Lorg.apache.cassandra.db.ClusteringBound;': 'CB[]', '[J': 'long[]', '[I': 'int[]'}


def hist(p):
    out = {'total': None, 'B': 0, 'Mutation': 0, 'PartitionUpdate': 0, 'SP': {}}
    for l in open(p, errors='replace'):
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m:
            n, b, c = int(m.group(1)), int(m.group(2)), m.group(3)
            if c in ARR:
                out[ARR[c]] = b
            elif c == '[B':
                out['B'] = b
            elif c == 'org.apache.cassandra.db.Mutation':
                out['Mutation'] = n
            elif c == 'org.apache.cassandra.db.partitions.PartitionUpdate':
                out['PartitionUpdate'] = n
            elif c.startswith('org.apache.cassandra.service.StorageProxy$'):
                out['SP'][c.split('.')[-1]] = n
        m = re.match(r'Total\s+(\d+)\s+(\d+)', l)
        if m:
            out['total'] = int(m.group(2))
    return out


def gc_events(p):
    ev = []
    for f in sorted(glob.glob(p + '*')):
        for l in open(f, errors='replace'):
            m = re.match(r'\[([^\]]+)\]\[([\d.]+)s\]\[\w+\s*\]\[gc\s*\] GC\((\d+)\) (Pause .*?)\s+(\d+)M->(\d+)M\((\d+)M\) ([\d.]+)ms', l)
            if m:
                t = datetime.strptime(m.group(1)[:23] + m.group(1)[23:].replace(':', ''), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp()
                ev.append({'t': t, 'kind': m.group(4).strip(), 'before': int(m.group(5)), 'after': int(m.group(6)), 'ms': float(m.group(8))})
    return ev


def csv_cum(p):
    rows = {}
    try:
        for l in open(p).read().splitlines()[1:]:
            v = list(map(int, l.split(',')))
            rows[v[0]] = v[1:]
    except Exception:
        pass
    return rows


def at(rows, t):
    """last cumulative row at or before second t"""
    ks = [k for k in rows if k <= t]
    return rows[max(ks)] if ks else None


def slope(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    d = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / d if d else None


def analyze(run):
    L = os.path.join(run, 'logs')
    r = {'run': os.path.basename(run)}
    drv = open(os.path.join(L, 'driver.log')).read().splitlines()
    ws = we = None
    for l in drv:
        if ' W start ' in l:
            ws = float(l.split()[0])
        if ' W stop: ' in l:
            we = float(l.split()[0])
            r['W_stop'] = l.split(' W stop: ')[1]
        m = re.search(r'-Xmx(\S+)|MaxDirectMemorySize=(\S+)', l)
        if m:
            r.setdefault('jvm', []).append(l.split()[-1])
    for k in ('fill', 'hot', 'blob', 'write'):
        try:
            r[k] = json.load(open(os.path.join(L, k + '.json')))
        except Exception:
            pass
    r['W_s'] = round(we - ws, 1) if ws and we else None
    rows = []
    try:
        lines = open(os.path.join(L, 'poll.log')).read().splitlines()
        hdr = lines[0].split()
        for l in lines[1:]:
            p = l.split()
            if len(p) == len(hdr):
                rows.append(dict(zip(hdr, map(int, p))))
    except Exception:
        pass
    hot, blob = csv_cum(os.path.join(L, 'hot.csv')), csv_cum(os.path.join(L, 'blob.csv'))
    if rows and ws:
        w = [x for x in rows if ws * 1000 <= x['epoch_ms'] <= (we or 1e18) * 1000]
        pre = [x for x in rows if x['epoch_ms'] < ws * 1000]
        if w:
            a, z = (pre[-1] if pre else w[0]), w[-1]
            dt = (z['epoch_ms'] - a['epoch_ms']) / 1000.0
            heap = [x['eden'] + x['surv'] + x['old'] for x in w]
            r['poll_W'] = {
                'samples': len(w), 'last_sample_s': round(dt, 1),
                'mu_h_per_s': round((z['wl_rt'] - a['wl_rt']) / dt, 2) if dt else None,
                'blob_applied_per_s': round((z['wl_blob'] - a['wl_blob']) / dt, 2) if dt else None,
                'hot_applied': z['wl_rt'] - a['wl_rt'], 'blob_applied': z['wl_blob'] - a['wl_blob'],
                'active_max': max(x['active'] for x in w), 'active_mean': round(sum(x['active'] for x in w) / len(w), 1),
                'pending_max': max(x['pending'] for x in w), 'pending_last': z['pending'],
                'ntr_active_max': max(x['ntr_active'] for x in w), 'ntr_pending_max': max(x['ntr_pending'] for x in w),
                'heap_used_max_MiB': round(max(heap) / MB), 'old_coll_max_MiB': round(max(x['old_coll'] for x in w) / MB),
                'old_coll_last_MiB': round(z['old_coll'] / MB),
                'K_rt_start': a['K_rt'], 'K_rt_end': z['K_rt'], 'sw_rt': [a['sw_rt'], z['sw_rt']], 'sw_blob': [a['sw_blob'], z['sw_blob']],
                'K_blob_max_MiB': round(max(x['K_blob'] for x in w) / MB),
                'hints_inprog_max': max(x['hints_inprog'] for x in w), 'hints_total_delta': z['hints_total'] - a['hints_total'],
                'dropped_mut_delta': z['dropped_mut'] - a['dropped_mut'], 'wr_timeouts_delta': z['wr_timeouts'] - a['wr_timeouts'],
                'cl_size_max_MiB': round(max(x['cl_size'] for x in w) / MB)}
            if blob:
                bl, hl, xs = [], [], []
                for x in w:
                    t = x['epoch_ms'] // 1000
                    b = at(blob, t)
                    h = at(hot, t)
                    if b is None:
                        continue
                    xs.append(x['epoch_ms'] / 1000.0 - ws)
                    bl.append(b[0] - (x['wl_blob'] - a['wl_blob']))
                    hl.append((h[0] if h else 0) - (x['wl_rt'] - a['wl_rt']))
                if bl:
                    s = slope(xs, bl)
                    r['backlog'] = {'blob_peak': max(bl), 'blob_peak_MiB': round(max(bl) * BLOB / MB), 'blob_last': bl[-1],
                                    'blob_slope_MiB_s': round(s * BLOB / MB, 1) if s is not None else None,
                                    'hot_peak': max(hl), 'hot_last': hl[-1],
                                    'blob_at_60s_steps': [bl[i] for i in range(0, len(bl), 60)]}
            if hot:
                ks = sorted(hot)
                best = 0.0
                for k0 in ks:
                    k1 = k0 + 60
                    a0, a1 = at(hot, k0), at(hot, k1)
                    if k1 > ks[-1] or not a0 or not a1:
                        break
                    done = (a1[2] - a0[2]) + (a1[3] - a0[3])
                    if done:
                        best = max(best, (a1[3] - a0[3]) / done)
                r['hot_timeout_share_max60'] = round(best, 3)
    ev = gc_events(os.path.join(L, 'gc.log'))
    if ev and ws:
        t1 = we or ev[-1]['t']
        w = [e for e in ev if ws <= e['t'] <= t1 + 5]
        full = [e for e in w if e['kind'].startswith('Pause Full')]
        best, t = 0.0, ws
        while t <= max(ws, t1 - 60) + 1e-9:
            best = max(best, sum(e['ms'] for e in w if t <= e['t'] < t + 60) / 60000.0)
            t += 1
        r['gc_W'] = {'pauses': len(w), 'full': len(full), 'full_after_MiB_last5': [e['after'] for e in full[-5:]],
                     'after_max_MiB': max((e['after'] for e in w), default=None), 'stw_frac_max60': round(best, 3),
                     'stw_frac_W': round(sum(e['ms'] for e in w) / 1000.0 / max(1.0, t1 - ws), 3), 'pause_max_ms': max((e['ms'] for e in w), default=None)}
    H = {}
    for p in sorted(glob.glob(os.path.join(run, 'hist', '*.txt'))):
        if 'hprof' in p:
            continue
        H[os.path.basename(p)[:-4]] = hist(p)
    if 'L0' in H and H['L0']['total']:
        b0 = H['L0']
        r['hist'] = {}
        for k, h in H.items():
            if not h.get('total'):
                r['hist'][k] = 'no histogram'
                continue
            arr = sum(h.get(c, 0) for c in ARR.values())
            arr0 = sum(b0.get(c, 0) for c in ARR.values())
            r['hist'][k] = {'total_MiB': round(h['total'] / MB, 1), 'B_MiB': round(h['B'] / MB, 1), 'B_above_L0_MiB': round((h['B'] - b0['B']) / MB, 1),
                            'U_D1_MiB': round((arr - arr0) / MB, 1), 'Mutation': h['Mutation'], 'PartitionUpdate': h['PartitionUpdate'], 'SP': h['SP']}
    oom = []
    first = None
    for f in ('system.log', 'stdout.txt'):
        try:
            for l in open(os.path.join(L, f), errors='replace'):
                if 'java.lang.OutOfMemoryError' in l and 'JVM Arguments' not in l:
                    oom.append(f + ': ' + l.strip()[:240])
                    m = re.search(r'(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d+)', l)
                    if m and first is None and ws:
                        first = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S').timestamp() + int(m.group(2)) / 1000.0
        except Exception:
            pass
    r['oom_lines'] = oom[:6]
    if first and ws:
        r['oom_at_W_s'] = round(first - ws, 1)
    try:
        rs = [int(l.split()[1]) for l in open(os.path.join(L, 'rss.log')) if len(l.split()) == 2]
        r['rssanon_max_MiB'] = round(max(rs) / 1024) if rs else None
    except Exception:
        pass
    r['hprof'] = [os.path.basename(x) + ' %d MiB' % (os.path.getsize(x) // MB) for x in glob.glob(os.path.join(run, '*.hprof'))]
    try:
        r['done'] = open(os.path.join(run, 'DONE')).read().strip()
    except Exception:
        r['done'] = None
    return r


for a in sys.argv[1:]:
    print(json.dumps(analyze(a)))
