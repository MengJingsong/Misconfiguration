#!/usr/bin/env python3
"""R22 stage-2 per-run analysis (from R17's analyze.py; blob 12 MiB, three blob clients, humongous regions). usage: python3 -I analyze.py <run dir> [...] -> one JSON object per run.
Reads logs/driver.log (W window, stop reason), logs/poll.log (JMX 1 s), logs/hot.csv + blob0..2.csv (client cumulative per second),
logs/gc.log (pauses, STW fraction per 60 s window), hist/*.txt (jcmd GC.class_histogram), logs/rss.log, OOM lines.
Derived (design §2.6): mu_h = r22.rt applied writes/s over W (WriteLatency count), blob applies/s, backlog_blob(t) =
blob requests sent (sum of the three clients) - r22.blob applied (x 12 MiB bytes, x 16 MiB regions = U_D3), its peak and least-squares slope, time to OOM, STW max over 60 s,
max share of hot writes timed out per 60 s."""
import glob, json, os, re, sys
from datetime import datetime

MB = 1024 * 1024
BLOB = 12582912
REGION = 16 * MB
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
    for k in ('fill', 'hot', 'blob0', 'blob1', 'blob2'):
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
                d_ = dict(zip(hdr, map(int, p)))
                if d_['wl_rt'] >= 0 and d_['wl_blob'] >= 0 and d_['active'] >= 0:  # JMX failures give -1: skip the row
                    rows.append(d_)
    except Exception:
        pass
    hot = csv_cum(os.path.join(L, 'hot.csv'))
    bparts = [csv_cum(os.path.join(L, 'blob%d.csv' % j)) for j in range(3)]
    blob = {}
    if all(bparts):
        for t in sorted(set().union(*[set(b) for b in bparts])):
            vs = [at(b, t) for b in bparts]
            if all(vs):
                blob[t] = [sum(v[i] for v in vs) for i in range(6)]
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
                'cl_size_max_MiB': round(max(x['cl_size'] for x in w) / MB), 'cl_size_last_MiB': round(z['cl_size'] / MB)}
            e40 = [x for x in w if x['epoch_ms'] >= (ws + 40) * 1000]
            if e40:
                r['poll_W']['at_W40'] = {'active': e40[0]['active'], 'pending': e40[0]['pending']}
            r['poll_W']['after_W30_active_mean'] = round(sum(x['active'] for x in w if x['epoch_ms'] >= (ws + 30) * 1000) / max(1, len([x for x in w if x['epoch_ms'] >= (ws + 30) * 1000])), 1)
            r['poll_W']['after_W30_pending_max'] = max([x['pending'] for x in w if x['epoch_ms'] >= (ws + 30) * 1000] or [None])
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
                    last300 = [(x_, y_) for x_, y_ in zip(xs, bl) if x_ >= xs[-1] - 300]
                    s300 = slope([a_ for a_, _ in last300], [b_ for _, b_ in last300]) if len(last300) > 30 else None
                    first180 = [(x_, y_) for x_, y_ in zip(xs, bl) if x_ <= 180]
                    s180 = slope([a_ for a_, _ in first180], [b_ for _, b_ in first180]) if len(first180) > 30 else None
                    r['backlog'] = {'blob_peak': max(bl), 'blob_peak_MiB_bytes': round(max(bl) * BLOB / MB), 'blob_peak_MiB_regions': round(max(bl) * REGION / MB),
                                    'blob_last': bl[-1],
                                    'blob_slope_regions_MiB_s': round(s * REGION / MB, 1) if s is not None else None,
                                    'blob_slope_first180_regions_MiB_s': round(s180 * REGION / MB, 1) if s180 is not None else None,
                                    'blob_slope_last300_per_s': round(s300, 3) if s300 is not None else None,
                                    'hot_peak': max(hl), 'hot_last': hl[-1],
                                    'blob_at_60s_steps': [bl[i] for i in range(0, len(bl), 60)]}
            if blob and hot:
                b0, b1 = at(blob, int(ws)), at(blob, int(we or 1e12))
                h0, h1 = at(hot, int(ws)), at(hot, int(we or 1e12))
                b0 = b0 or [0] * 6
                h0 = h0 or [0] * 6
                if b1 and h1 and r.get('W_s'):
                    r['issued_W'] = {'blob_issued': b1[0] - b0[0], 'blob_capped': b1[1] - b0[1], 'blob_ok': b1[2] - b0[2], 'blob_timeouts': b1[3] - b0[3],
                                     'blob_errors': b1[4] - b0[4], 'blob_issued_per_s': round((b1[0] - b0[0]) / r['W_s'], 2),
                                     'hot_issued': h1[0] - h0[0], 'hot_burst': h1[1] - h0[1], 'hot_ok': h1[2] - h0[2], 'hot_timeouts': h1[3] - h0[3],
                                     'hot_errors': h1[4] - h0[4], 'lambda_h_per_s': round((h1[0] - h0[0]) / r['W_s'], 2)}
                    per_min = []
                    t = int(ws)
                    while t + 60 <= int(we or 0):
                        a0, a1 = at(blob, t), at(blob, t + 60)
                        c0, c1 = at(hot, t), at(hot, t + 60)
                        if a0 and a1 and c0 and c1:
                            per_min.append({'blob_issued': a1[0] - a0[0], 'blob_capped': a1[1] - a0[1], 'hot_issued': c1[0] - c0[0],
                                            'hot_done': (c1[2] - c0[2]) + (c1[3] - c0[3]), 'hot_to': c1[3] - c0[3]})
                        t += 60
                    r['per_minute'] = per_min
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
        # heap dump = the only >= 10 s gap between GC events in W (a safepoint for the whole dump); OOM time = start of that gap
        gaps = [(b_['t'] - a_['t'], a_['t']) for a_, b_ in zip(w, w[1:]) if b_['t'] - a_['t'] >= 10]
        if gaps:
            r['gc_gap_ge10s'] = [{'at_W_s': round(t_ - ws, 1), 'len_s': round(g_, 1)} for g_, t_ in gaps]
        if w:
            r['last_gc_event_at_W_s'] = round(w[-1]['t'] - ws, 1)
        r['gc_W'] = {'pauses': len(w), 'full': len(full), 'full_after_MiB_last5': [e['after'] for e in full[-5:]],
                     'after_max_MiB': max((e['after'] for e in w), default=None), 'stw_frac_max60': round(best, 3),
                     'stw_frac_W': round(sum(e['ms'] for e in w) / 1000.0 / max(1.0, t1 - ws), 3), 'pause_max_ms': max((e['ms'] for e in w), default=None)}
    hum = []
    for f in sorted(glob.glob(os.path.join(L, 'gc.log*'))):
        for l in open(f, errors='replace'):
            m = re.search(r'Humongous regions: (\d+)->(\d+)', l)
            if m:
                hum.append(int(m.group(1)))
    if hum:
        r['humongous_regions_max'] = max(hum)
        r['humongous_regions_last'] = hum[-1]
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
                    m = re.search(r'(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d:\d\d),(\d+)', l)
                    if m and first is None and ws:
                        first = datetime.strptime(m.group(1) + ' ' + m.group(2) + ' +0000', '%Y-%m-%d %H:%M:%S %z').timestamp() + int(m.group(3)) / 1000.0  # logback writes UTC on pc72
        except Exception:
            pass
    r['oom_lines'] = oom[:6]
    try:
        so = open(os.path.join(L, 'stdout.txt'), errors='replace').read()
        m = re.search(r'Heap dump file created \[(\d+) bytes in ([\d.]+) secs\]', so)
        if m:
            r['heap_dump'] = {'bytes': int(m.group(1)), 'secs': float(m.group(2))}
    except Exception:
        pass
    if first and ws:
        r['oom_at_W_s'] = round(first - ws, 1)
    try:
        rs = [int(l.split()[1]) for l in open(os.path.join(L, 'rss.log')) if len(l.split()) == 2]
        r['rssanon_max_MiB'] = round(max(rs) / 1024) if rs else None
    except Exception:
        pass
    r['hprof'] = [os.path.basename(x) + ' %d MiB' % (os.path.getsize(x) // MB) for x in glob.glob(os.path.join(run, '*.hprof'))]
    # Cassandra's printed OOM histogram (system.log, after the OOM line)
    try:
        txt = open(os.path.join(L, 'system.log'), errors='replace').read()
        i = txt.find('java.lang.OutOfMemoryError')
        if i >= 0:
            seg = txt[i:i + 400000]
            tmp = os.path.join(run, 'hist', 'oom-printed.txt')
            if not os.path.exists(tmp):
                with open(tmp, 'w') as fo:
                    fo.write(seg)
            hp = hist(tmp)
            if hp.get('total') and 'L0' in H and H['L0'].get('total'):
                b0 = H['L0']
                arr = sum(hp.get(c, 0) for c in ARR.values())
                arr0 = sum(b0.get(c, 0) for c in ARR.values())
                r['hist_oom_printed'] = {'total_MiB': round(hp['total'] / MB, 1), 'B_MiB': round(hp['B'] / MB, 1), 'B_above_L0_MiB': round((hp['B'] - b0['B']) / MB, 1),
                                         'U_D1_MiB': round((arr - arr0) / MB, 1), 'Mutation': hp['Mutation'], 'PartitionUpdate': hp['PartitionUpdate'], 'SP': hp['SP']}
    except Exception as e:
        r['hist_oom_printed'] = 'n/a: %s' % e
    try:
        r['done'] = open(os.path.join(run, 'DONE')).read().strip()
    except Exception:
        r['done'] = None
    return r


for a in sys.argv[1:]:
    print(json.dumps(analyze(a)))
