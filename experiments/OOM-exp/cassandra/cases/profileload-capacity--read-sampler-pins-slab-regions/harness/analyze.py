#!/usr/bin/env python3
"""B25 stage-2 per-lifetime analysis (design §2.5 analyze.py): from /mydata/s4/b25/logs/<label>/: per session k the reads n_k
(between nodetool start and return), nodetool rc / key check; the old-gen floor per phase = minimum heap-after-GC (gc.log, every
'Pause' line) within [s_k, s_{k+1}); the per-session step of the floor; K_pool (JMX AllMemtablesOnHeapDataSize) max per phase;
endpoint, OOM lines, dump readings (R_s, live regions, K_pool from the dump, K_s, uncounted). One JSON object per label.
usage: analyze.py <label> [<label> ...]"""
import datetime, json, re, sys

W = '/mydata/s4/b25/logs'
GC = re.compile(r'^\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)([+-]\d{4})\].*GC\(\d+\) Pause (\S+).*?(\d+)M->(\d+)M\((\d+)M\)')


def gc_points(label):
    import glob
    pts = []
    for f in sorted(glob.glob(f'{W}/{label}/gc.log*')):
        for l in open(f, errors='replace'):
            m = GC.match(l)
            if m:
                dt = datetime.datetime.strptime(m.group(1) + m.group(2), '%Y-%m-%dT%H:%M:%S.%f%z')
                pts.append((int(dt.timestamp() * 1000), m.group(3), int(m.group(4)), int(m.group(5)), int(m.group(6))))
    pts.sort()
    return pts


def sampler(label):
    rows = []
    try:
        lines = open(f'{W}/{label}/sampler.csv').read().splitlines()
    except OSError:
        return rows
    cols = lines[0].split(',')
    for l in lines[1:]:
        p = l.split(',')
        if len(p) == len(cols):
            rows.append(dict(zip(cols, p)))
    return rows


def one(label):
    s = json.load(open(f'{W}/{label}/summary.json'))
    sess = s.get('sessions') or []
    pts = gc_points(label)
    smp = sampler(label)
    out = {'label': label, 'args': s.get('args'), 'build': (s.get('build') or {}).get('jar_sha256', '')[:12],
           'settings_ok': (s.get('settings') or {}).get('ok'), 'MaxDirectMemorySize': (s.get('start') or {}).get('MaxDirectMemorySize'),
           'endpoint': s.get('endpoint') or s.get('FAIL'), 'tail': s.get('tail'), 'oom': s.get('oom'),
           'oom_first_log_lines': s.get('oom_first_log_lines'), 'system_log_errors': s.get('system_log_errors'),
           'mem_events': open(f'{W}/{label}/memory.events').read().split() if __import__('os').path.exists(f'{W}/{label}/memory.events') else None}
    bounds = [x['s_ms'] for x in sess] + [10 ** 15]
    per = []
    for i, x in enumerate(sess):
        a, b = bounds[i], bounds[i + 1]
        aft = [p[3] for p in pts if a <= p[0] < b]
        kp = [int(r['K_pool']) for r in smp if r['K_pool'].isdigit() and a <= int(r['ms']) < b]
        per.append({'k': x['k'], 'n_k': x.get('n_k'), 'rc': x.get('nt_rc'), 'keys': x.get('nt_names_keys'),
                    'floor_MiB': min(aft) if aft else None, 'gcs': len(aft), 'K_pool_max_MiB': round(max(kp) / 1048576) if kp else None,
                    'endpoint': x.get('endpoint')})
    out['per_session'] = per
    fl = [p['floor_MiB'] for p in per if p['floor_MiB'] is not None and p.get('endpoint') != 'oom']
    out['floor_steps_MiB'] = [fl[i + 1] - fl[i] for i in range(len(fl) - 1)]
    if len(fl) >= 3:
        n = len(fl); xs = list(range(n)); mx = sum(xs) / n; my = sum(fl) / n
        out['floor_slope_MiB_per_session'] = round(sum((x - mx) * (y - my) for x, y in zip(xs, fl)) / sum((x - mx) ** 2 for x in xs), 1)
    out['floor_max_MiB'] = max(fl) if fl else None
    nk = [p['n_k'] for p in per if p['n_k'] is not None and p.get('endpoint') != 'oom']
    out['n_k_median'] = sorted(nk)[len(nk) // 2] if nk else None
    out['n_k_ge256_frac'] = round(sum(1 for v in nk if v >= 256) / len(nk), 2) if nk else None
    out['nt_all_ok'] = all(p['rc'] == 0 and p['keys'] for p in per if p.get('endpoint') != 'oom' and p['rc'] is not None)
    out['dumps'] = {k[5:]: v for k, v in s.items() if k.startswith('dump ')}
    out['hist'] = {k: v for k, v in s.items() if k.startswith('hist')}
    out['last_gc'] = pts[-3:] if pts else None
    return out


if __name__ == '__main__':
    for lb in sys.argv[1:]:
        print(json.dumps(one(lb)))
