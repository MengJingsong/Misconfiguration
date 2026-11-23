#!/usr/bin/env python3
"""U15 stage-2 per-run analysis (design §2.6). usage: python3 -I analyze.py <run dir> [...] -> one JSON object per run (also written to
<run>/analysis.json). Reads logs/driver.log (W window, stop, stall check), logs/poll.log (JMX 1 s), logs/data0..3.csv + poison.json,
logs/gc.log*, logs/flushes.txt + system.log (flush lines, AssertionErrors), hist/*.txt, logs/rss.log, logs/oom-grep.txt.
Derived: memtable switches of u15.t with W-relative times; K_all (u15.t live + flushing) max; applied (u15.t WriteLatency count) per s;
backlog(t) = data writes issued (sum of 4 clients) - (applied - applied_W0 - poison_ok); its peak and slopes; time to node death;
Old after each Pause Full; max STW share over 60 s windows."""
import glob, json, os, re, sys
from datetime import datetime

MB = 1024 * 1024


def poll(p):
    rows = []
    try:
        lines = open(p).read().splitlines()
    except Exception:
        return rows
    if not lines:
        return rows
    h = lines[0].split()
    for l in lines[1:]:
        v = l.split()
        if len(v) == len(h) and v[0].isdigit():
            rows.append(dict(zip(h, map(int, v))))
    return rows


def csv_cum(p):
    rows = {}
    try:
        for l in open(p).read().splitlines()[1:]:
            v = list(map(int, l.split(',')))
            rows[v[0]] = v[1:]
    except Exception:
        pass
    return rows


def at(series, t):
    """last value at or before second t of a {sec: row} dict"""
    ks = [k for k in series if k <= t]
    return series[max(ks)] if ks else None


def gc_events(p):
    ev = []
    for f in sorted(glob.glob(p + '*')):
        for l in open(f, errors='replace'):
            m = re.match(r'\[([^\]]+)\]\[([\d.]+)s\]\[\w+\s*\]\[gc\s*\] GC\((\d+)\) (Pause .*?)\s+(\d+)M->(\d+)M\((\d+)M\) ([\d.]+)ms', l)
            if m:
                t = datetime.strptime(m.group(1)[:23] + m.group(1)[23:].replace(':', ''), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp()
                ev.append({'t': t, 'kind': m.group(4).strip(), 'before': int(m.group(5)), 'after': int(m.group(6)), 'ms': float(m.group(8))})
    return ev


def slope(pts):
    if len(pts) < 3:
        return None
    n = len(pts); mx = sum(p[0] for p in pts) / n; my = sum(p[1] for p in pts) / n
    d = sum((p[0] - mx) ** 2 for p in pts)
    return round(sum((p[0] - mx) * (p[1] - my) for p in pts) / d, 2) if d else None


def hist(p):
    out = {'total_MiB': None, 'byte[]_MiB': None}
    try:
        for l in open(p, errors='replace'):
            m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
            if m:
                n, b, c = int(m.group(1)), int(m.group(2)), m.group(3)
                if c == '[B':
                    out['byte[]_MiB'] = round(b / MB, 1)
                elif c in ('org.apache.cassandra.db.Mutation', 'org.apache.cassandra.db.partitions.PartitionUpdate',
                           'org.apache.cassandra.db.memtable.SkipListMemtable') or c.startswith('org.apache.cassandra.service.StorageProxy$'):
                    out[c.split('.')[-1]] = n
            m = re.match(r'Total\s+(\d+)\s+(\d+)', l)
            if m:
                out['total_MiB'] = round(int(m.group(2)) / MB, 1)
    except Exception:
        return None
    return out


def analyze(run):
    r = {'run': os.path.basename(run)}
    drv = open(os.path.join(run, 'logs/driver.log'), errors='replace').read()
    m = re.search(r'^(\d+\.\d+) \S+ W start', drv, re.M)
    if not m:
        r['error'] = 'no W start'
        return r
    w0 = float(m.group(1))
    m = re.search(r'W stop: (.*) after (\d+) s', drv)
    r['W_stop'] = m.group(1) if m else None
    r['W_s'] = int(m.group(2)) if m else None
    m = re.search(r'stall check (W\+\d+): (.*)', drv)
    r['stall_check'] = (m.group(1) + ' ' + m.group(2)) if m else None
    for k in ('MaxDirectMemorySize', 'ParallelGCThreads', 'ConcGCThreads', 'G1HeapRegionSize', 'MaxHeapSize'):
        m = re.search(k + r'=(\d+)', drv)
        if m:
            r[k] = int(m.group(1))
    m = re.search(r'"clients_by_address": (\{[^}]*\})', drv)
    r['clients_by_address'] = json.loads(m.group(1)) if m else None
    try:
        r['settings'] = json.load(open(os.path.join(run, 'logs/settings.json')))
    except Exception:
        r['settings'] = None
    P = poll(os.path.join(run, 'logs/poll.log'))
    P = [p for p in P if p['applied'] >= 0 and p['active'] >= 0]  # JMX rows of a dying node read -1
    W = [p for p in P if p['epoch_ms'] / 1000 >= w0]
    pre = [p for p in P if p['epoch_ms'] / 1000 < w0]
    a0 = pre[-1]['applied'] if pre else (W[0]['applied'] if W else 0)
    sw0 = pre[-1]['sw'] if pre else 0
    sws = []
    last = sw0
    for p in W:
        if p['sw'] > last:
            sws.append(round(p['epoch_ms'] / 1000 - w0, 1)); last = p['sw']
    r['switches_W_rel_s'] = sws
    if W:
        r['K_all_max_MiB'] = round(max(p['K_all'] for p in W) / MB, 1)
        r['K_live_max_MiB'] = round(max(p['K_live'] for p in W) / MB, 1)
        r['K_global_max_MiB'] = round(max(p['K_global'] for p in W) / MB, 1)
        r['K_all_last_MiB'] = round(W[-1]['K_all'] / MB, 1)
        r['active_max'] = max(p['active'] for p in W)
        r['pending_max'] = max(p['pending'] for p in W)
        r['ntr_active_max'] = max(p['ntr_active'] for p in W)
        r['ntr_pending_max'] = max(p['ntr_pending'] for p in W)
        r['old_coll_max_MiB'] = round(max(p['old_coll'] for p in W) / MB, 1)
        r['cl_size_max_MiB'] = round(max(p['cl_size'] for p in W) / MB, 1)
        r['wr_timeouts'] = W[-1]['wr_timeouts'] - (pre[-1]['wr_timeouts'] if pre else 0)
        r['dropped_mut'] = W[-1]['dropped_mut']
        r['pflush_max'] = max(p['pflush'] for p in W)
        r['blocked_alloc_last'] = W[-1]['blocked_alloc']
        r['applied_W'] = W[-1]['applied'] - a0
        # time applied last increased by >= 5 in a 10 s window
        app = {int(p['epoch_ms'] / 1000 - w0): p['applied'] for p in W}
        flat = None
        for t in sorted(app):
            prev = at(app, t - 10)
            if prev is not None and app[t] - prev < 5 and t >= 10:
                flat = t - 10
                break
        r['applied_flat_from_W_s'] = flat
        r['applied_per_s_W'] = round(r['applied_W'] / max(1, (W[-1]['epoch_ms'] / 1000 - w0)), 1)
    # clients
    D = [csv_cum(os.path.join(run, 'logs/data%d.csv' % j)) for j in range(4)]
    tot = {}
    for j in range(4):
        try:
            tot['data%d' % j] = json.load(open(os.path.join(run, 'logs/data%d.json' % j)))
        except Exception:
            tot['data%d' % j] = None
    agg = {'issued': 0, 'capped': 0, 'ok': 0, 'timeouts': 0, 'errors': 0}
    for v in tot.values():
        if v:
            for k in agg:
                agg[k] += v.get(k, 0)
    r['data_totals'] = agg
    r['data_lat_ok_ms'] = [v.get('lat_ok_ms') for v in tot.values() if v]
    try:
        pj = json.load(open(os.path.join(run, 'logs/poison.json')))
        r['poison'] = {k: pj.get(k) for k in ('mode', 'bound_bytes', 'issued', 'ok', 'timeouts', 'errors', 'invalid_request', 'first_errors')}
    except Exception:
        r['poison'] = None
    PC = csv_cum(os.path.join(run, 'logs/poison.csv'))
    # backlog
    bl = []
    for p in W:
        t = int(p['epoch_ms'] / 1000)
        iss = sum((at(d, t) or [0])[0] for d in D)
        pok = (at(PC, t) or [0, 0, 0])[2]
        b = iss - (p['applied'] - a0 - pok)
        bl.append((t - w0, b))
    if bl:
        r['backlog_peak'] = max(b for _, b in bl)
        r['backlog_last'] = bl[-1][1]
        if flat is not None:
            r['backlog_slope_first20_after_stall_per_s'] = slope([x for x in bl if flat + 10 <= x[0] <= flat + 30])
        tl = bl[-1][0]
        r['backlog_slope_last120_per_s'] = slope([x for x in bl if x[0] >= tl - 120])
    # node death
    rss = []
    try:
        for l in open(os.path.join(run, 'logs/rss.log')):
            v = l.split()
            if len(v) == 2:
                rss.append((int(v[0]), int(v[1])))
    except Exception:
        pass
    if rss:
        r['rssanon_max_MiB'] = round(max(v for _, v in rss) / 1024, 1)
    oom = open(os.path.join(run, 'logs/oom-grep.txt'), errors='replace').read().strip() if os.path.exists(os.path.join(run, 'logs/oom-grep.txt')) else ''
    r['oom_lines'] = oom.splitlines()[:4]
    r['oom'] = bool(oom)
    so = os.path.join(run, 'logs', 'stdout.txt')
    r['hotspot_oom_stdout'] = 'Java heap space' in (open(so, errors='replace').read() if os.path.exists(so) else '')
    r['heapdump_line'] = (re.findall(r'Heap dump file created \[(\d+) bytes in ([\d.]+) secs\]', open(so, errors='replace').read()) if os.path.exists(so) else [])[:1]
    if r['W_stop'] == 'node death' and rss:
        r['death_W_rel_s'] = round(rss[-1][0] - w0, 1)
    # gc
    ev = [e for e in gc_events(os.path.join(run, 'logs/gc.log')) if e['t'] >= w0 - 1]
    fulls = [e for e in ev if 'Full' in e['kind']]
    r['gc_full_n'] = len(fulls)
    r['gc_full_after_MiB'] = [e['after'] for e in fulls][-6:]
    r['gc_full_first_W_rel_s'] = round(fulls[0]['t'] - w0, 1) if fulls else None
    best = 0
    for e in ev:
        s = sum(x['ms'] for x in ev if e['t'] - 60 <= x['t'] <= e['t']) / 60000
        best = max(best, s)
    r['stw_max_share_60s'] = round(best, 3)
    # flushes / assertions
    sp = os.path.join(run, 'logs', 'system.log')
    sl = open(sp, errors='replace').read() if os.path.exists(sp) else ''
    enq = re.findall(r'T(\d\d:\d\d:\d\d,\d+) ColumnFamilyStore.java:\d+ - Enqueuing flush of u15\.t, Reason: (\w+), Usage: ([\d.]+)(KiB|MiB|GiB)', sl)
    UNIT = {'KiB': 1 / 1024, 'MiB': 1, 'GiB': 1024}
    enq = [(t, why, round(float(u) * UNIT[un], 3)) for t, why, u, un in enq]
    r['enqueue_u15_t'] = enq
    r['enqueue_u15_t_n'] = len(enq)
    r['assert_65535_n'] = len(re.findall(r'java.lang.AssertionError: Attempted serializing to buffer exceeded maximum of 65535 bytes', sl))
    r['assert_lengths'] = sorted(set(re.findall(r'exceeded maximum of 65535 bytes: (\d+)', sl)))
    r['assert_site_StatsMetadata'] = len(re.findall(r'StatsMetadata\$StatsMetadataSerializer.serialize\(StatsMetadata.java:436\)', sl))
    r['flushing_largest'] = re.findall(r"Flushing largest CFS\(Keyspace='u15', ColumnFamily='t'\).*?Used total: ([\d.]+)/[\d.]+, live: ([\d.]+)/[\d.]+, flushing: ([\d.]+)/[\d.]+", sl)
    r['completed_flush_u15_t_n'] = len(re.findall(r'Completed flushing \S*/u15/t-', sl))
    m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d,\d+) JVMStabilityInspector.java:\d+ - OutOfMemory error', sl)
    if m:
        from datetime import timezone
        te = datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=timezone.utc).timestamp()
        r['oom_first_W_rel_s'] = round(te - w0, 1)
        m2 = re.search(r'ERROR \[([^\]]+)\] ' + re.escape(m.group(1)), sl)
        r['oom_first_thread'] = m2.group(1) if m2 else None
    # pool K (amendment A1): sum of enqueued usages of failed flushes + live at stall
    if W and flat is not None:
        kl = [p['K_live'] for p in W if p['epoch_ms'] / 1000 - w0 >= flat][:1]
        failed = [u for _, why, u in enq][:r['assert_65535_n']]
        r['K_pool_D1D2_MiB'] = round(sum(failed) + (kl[0] / MB if kl else 0), 1)
    r['hist'] = {os.path.basename(h): hist(h) for h in sorted(glob.glob(os.path.join(run, 'hist/L*.txt')))}
    dh = os.path.join(run, 'hist/dump-hist.txt')
    if os.path.exists(dh):
        txt = open(dh, errors='replace').read()
        r['dump'] = {
            'total': (re.search(r'total shallow (\d+) MiB', txt) or [None, None])[1],
            'byte_1MiB': (re.search(r'byte\[\] == 1,048,576 B: (\d+) arrays', txt) or [None, None])[1],
            'SP4': (re.search(r'StorageProxy\$4: (\d+)', txt) or [None, None])[1],
            'Mutation': (re.search(r'db\.Mutation: (\d+)', txt) or [None, None])[1],
            'PartitionUpdate': (re.search(r'PartitionUpdate: (\d+)', txt) or [None, None])[1],
            'SkipListMemtable': (re.search(r'SkipListMemtable: (\d+)', txt) or [None, None])[1],
            'poison_lengths': (re.search(r'poison-bound lengths: (.*)', txt) or [None, None])[1],
        }
    try:
        r['done'] = open(os.path.join(run, 'DONE')).read().strip()
    except Exception:
        r['done'] = None
    json.dump(r, open(os.path.join(run, 'analysis.json'), 'w'), indent=1)
    return r


for run in sys.argv[1:]:
    print(json.dumps(analyze(run)))
