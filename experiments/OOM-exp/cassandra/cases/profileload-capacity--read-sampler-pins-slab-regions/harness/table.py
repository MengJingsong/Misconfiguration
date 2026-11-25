#!/usr/bin/env python3
"""B25: one line per lifetime from analyze.py (run on the node). usage: table.py <label> ..."""
import json, subprocess, sys, os

H = os.path.dirname(os.path.abspath(__file__))
for lb in sys.argv[1:]:
    try:
        d = json.loads(subprocess.run(['python3', '-I', f'{H}/analyze.py', lb], capture_output=True, text=True).stdout)
    except Exception as e:
        print(lb, 'ERR', e); continue
    ep = d.get('endpoint') or {}
    per = d['per_session']
    oomk = next((p['k'] for p in per if p.get('endpoint') == 'oom'), None)
    if oomk is None and isinstance(d.get('tail'), dict) and d['tail'].get('endpoint') == 'oom':
        oomk = 'tail'
    dm = d.get('dumps') or {}
    dd = {k: {x: v.get(x) for x in ('R_s', 'reachable_regions', 'K_pool_allocated', 'K_pool_reclaiming', 'uncounted_regions', 'counted')}
          for k, v in dm.items()}
    print(json.dumps({'label': lb, 'args': d['args'][2:], 'settings_ok': d['settings_ok'], 'endpoint': ep.get('endpoint') if isinstance(ep, dict) else ep,
                      'oom_session': oomk, 'sessions_done': ep.get('sessions_done') if isinstance(ep, dict) else None,
                      'n_k_median': d['n_k_median'], 'n_k_ge256': d['n_k_ge256_frac'], 'nt_ok': d['nt_all_ok'],
                      'floors': [p['floor_MiB'] for p in per], 'slope': d.get('floor_slope_MiB_per_session'), 'floor_max': d['floor_max_MiB'],
                      'K_pool_max': max([p['K_pool_max_MiB'] or 0 for p in per] or [0]), 'mem_events': d['mem_events'],
                      'oom_lines': [l for l in ((d.get('oom') or {}).get('stdout_lines') or []) if len(l) < 200], 'syslog_err': d.get('system_log_errors'),
                      'MDM': d['MaxDirectMemorySize'], 'dumps': dd}))
