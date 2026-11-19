#!/usr/bin/env python3
"""U11 stage-2 per-run analysis. usage: python3 -I analyze.py <run dir> [...]  -> one JSON object per run on stdout.
Reads logs/driver.log (W window), logs/poll.log (K, A, pools), logs/gc.log (pauses, humongous, STW fraction per 60 s),
hist/*.txt (jcmd GC.class_histogram: total and the RTL array classes, minus L0), logs/fill.json, logs/write.json,
OOM lines from logs/system.log / stdout.txt."""
import glob, json, os, re, sys
from datetime import datetime

ARR = {'[Lorg.apache.cassandra.db.ClusteringBound;': 'CB[]', '[J': 'long[]', '[I': 'int[]',
       'org.apache.cassandra.db.BufferClusteringBound': 'BufferClusteringBound'}
MB = 1024 * 1024


def hist(p):
    out = {'total': None}
    for l in open(p, errors='replace'):
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m and m.group(3) in ARR:
            out[ARR[m.group(3)]] = int(m.group(2))
        m = re.match(r'Total\s+(\d+)\s+(\d+)', l)
        if m:
            out['total'] = int(m.group(2))
    return out


def gc_events(p):
    ev = []
    hum = {}
    for f in sorted(glob.glob(p + '*')):
        for l in open(f, errors='replace'):
            m = re.match(r'\[([^\]]+)\]\[([\d.]+)s\]\[\w+\s*\]\[gc\s*\] GC\((\d+)\) (Pause .*?)\s+(\d+)M->(\d+)M\((\d+)M\) ([\d.]+)ms', l)
            if m:
                t = datetime.strptime(m.group(1)[:23] + m.group(1)[23:].replace(':', ''), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp()
                ev.append({'t': t, 'id': int(m.group(3)), 'kind': m.group(4).strip(), 'before': int(m.group(5)), 'after': int(m.group(6)),
                           'cap': int(m.group(7)), 'ms': float(m.group(8))})
                continue
            m = re.match(r'\[([^\]]+)\]\[([\d.]+)s\]\[\w+\s*\]\[gc[^\]]*\] GC\((\d+)\) (Pause (?:Remark|Cleanup))\s+(\d+)M->(\d+)M\((\d+)M\) ([\d.]+)ms', l)
            m2 = re.search(r'GC\((\d+)\) Humongous regions: (\d+)->(\d+)', l)
            if m2:
                hum[int(m2.group(1))] = (int(m2.group(2)), int(m2.group(3)))
    for e in ev:
        e['hum'] = hum.get(e['id'])
    return ev


def analyze(run):
    L = os.path.join(run, 'logs')
    r = {'run': os.path.basename(run)}
    drv = open(os.path.join(L, 'driver.log')).read().splitlines()
    ws = we = None
    for l in drv:
        if ' W start ' in l:
            ws = float(l.split()[0])
    for k in ('fill', 'write'):
        try:
            r[k] = json.load(open(os.path.join(L, k + '.json')))
        except Exception:
            r[k] = None
    if ws and r['write']:
        we = ws + r['write']['seconds']
    r['W_window'] = [ws, we]
    # poll
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
    if rows and ws:
        w = [x for x in rows if ws * 1000 <= x['epoch_ms'] <= (we or 1e18) * 1000]
        pre = [x for x in rows if x['epoch_ms'] < ws * 1000]
        if w:
            act = [x['active'] for x in w]
            r['poll_W'] = {'samples': len(w), 'active_max': max(act), 'active_mean': round(sum(act) / len(act), 1),
                           'active_ge30_frac': round(sum(a >= 30 for a in act) / len(act), 2),
                           'pending_max': max(x['pending'] for x in w),
                           'heap_used_max_MiB': round(max(x['eden'] + x['surv'] + x['old'] for x in w) / MB),
                           'old_max_MiB': round(max(x['old'] for x in w) / MB),
                           'old_coll_max_MiB': round(max(x['old_coll'] for x in w) / MB),
                           'K_start': w[0]['K_table'], 'K_end': w[-1]['K_table'], 'switch_start': w[0]['switch'], 'switch_end': w[-1]['switch']}
        if pre:
            r['poll_pre'] = {'K': pre[-1]['K_table'], 'old_coll_MiB': round(pre[-1]['old_coll'] / MB), 'switch': pre[-1]['switch']}
    # gc
    ev = gc_events(os.path.join(L, 'gc.log'))
    if ev and ws:
        w = [e for e in ev if ws <= e['t'] <= (we or 1e18) + 5]
        kinds = {}
        for e in w:
            kk = e['kind'].split('(')[0].strip() + ('' if '(' not in e['kind'] else ' (' + e['kind'].split('(')[1].split(')')[0] + ')')
            kinds[kk] = kinds.get(kk, 0) + 1
        full = [e for e in w if e['kind'].startswith('Pause Full')]
        stw = 0.0
        if w:
            t0, t1 = ws, (we or w[-1]['t'])
            best = 0.0
            t = t0
            while t <= max(t0, t1 - 60) + 1e-9:
                s = sum(e['ms'] for e in w if t <= e['t'] < t + 60) / 60000.0
                best = max(best, s)
                t += 1
            stw = best
            total = sum(e['ms'] for e in w) / 1000.0 / max(1.0, t1 - t0)
        r['gc_W'] = {'pauses': len(w), 'kinds': kinds, 'after_max_MiB': max((e['after'] for e in w), default=None),
                     'before_max_MiB': max((e['before'] for e in w), default=None),
                     'full_after_MiB': [e['after'] for e in full],
                     'hum_before_max': max((e['hum'][0] for e in w if e['hum']), default=None),
                     'stw_frac_max60': round(stw, 3), 'stw_frac_W': round(total, 3) if w else None,
                     'pause_max_ms': max((e['ms'] for e in w), default=None)}
    # histograms
    H = {}
    for p in sorted(glob.glob(os.path.join(run, 'hist', '*.txt'))):
        H[os.path.basename(p)[:-4]] = hist(p)
    if 'L0' in H and H['L0']['total']:
        b0 = H['L0']
        r['hist'] = {}
        for k, h in H.items():
            if not h.get('total'):
                r['hist'][k] = 'no histogram'
                continue
            arr = sum(h.get(c, 0) for c in ('CB[]', 'long[]', 'int[]'))
            arr0 = sum(b0.get(c, 0) for c in ('CB[]', 'long[]', 'int[]'))
            r['hist'][k] = {'total_MiB': round(h['total'] / MB, 1), 'arrays_MiB': round(arr / MB, 1), 'U_D1_MiB': round((arr - arr0) / MB, 1),
                            'BCB': h.get('BufferClusteringBound', 0) // 48 if False else h.get('BufferClusteringBound', 0)}
    # OOM
    oom = []
    for f in ('system.log', 'stdout.txt'):
        try:
            for l in open(os.path.join(L, f), errors='replace'):
                if 'java.lang.OutOfMemoryError' in l or 'OutOfMemoryError:' in l:
                    oom.append(f + ': ' + l.strip()[:220])
        except Exception:
            pass
    r['oom_lines'] = oom[:6]
    r['hprof'] = [os.path.basename(x) + ' %d MiB' % (os.path.getsize(x) // MB) for x in glob.glob(os.path.join(run, '*.hprof'))]
    try:
        r['done'] = open(os.path.join(run, 'DONE')).read().strip()
    except Exception:
        r['done'] = None
    return r


for a in sys.argv[1:]:
    print(json.dumps(analyze(a)))
