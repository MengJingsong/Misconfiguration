#!/usr/bin/env python3
"""Cluster-tier readings table and row matching (B3f/B3g/B3h as amended 2026-10-24; B3h (a) as re-amended after run 1, read from <arm>/flush.txt when present) from the raw files of each arm.
usage: cluster-readings.py <cluster log dir>"""
import csv, os, re, sys
L = sys.argv[1]; MIB = 1 << 20; S = 32 * MIB; ROW = 16384
def rd(p):
    return open(p, errors='replace').read() if os.path.exists(p) else ''
def setting(D, name):
    m = re.search(r'^\s*%s\s*\|\s*(\S+)' % name, rd(os.path.join(D, 'settings.txt')), re.M)
    return m.group(1) if m else None
def mib(v):
    m = re.match(r'(\d+)MiB$', v or ''); return int(m.group(1)) if m else None
def stress(D):
    t = rd(os.path.join(D, 'stress.log'))
    e = re.search(r'^Total errors\s*:\s*([\d,]+)', t, re.M); p = re.search(r'^Total partitions\s*:\s*([\d,]+)', t, re.M)
    return (int(e.group(1).replace(',', '')) if e else None, int(p.group(1).replace(',', '')) if p else None)
def count(D):
    m = re.search(r'^\s*(\d+)\s*$', rd(os.path.join(D, 'count.txt')), re.M); return int(m.group(1)) if m else None
def scan(D):
    return dict(x.split('=', 1) for x in rd(os.path.join(D, 'logscan.txt')).split() if '=' in x)
def samp(D):
    p = os.path.join(D, 'sampler.csv')
    if not os.path.exists(p): return None
    r = list(csv.DictReader(open(p)))
    ev = rd(os.path.join(D, 'sampler.events')).splitlines()
    return dict(n=len(r), max_lb=max(int(x['link_bytes']) for x in r), max_links=max(int(x['links']) for x in r),
                max_idx=max(int(x['idx_bytes']) for x in r), max_alloc=max(int(x['link_alloc_bytes']) for x in r),
                gap=max(int(x['gap_ms']) for x in r), deleted=sum(1 for l in ev if ' - ' in l),
                final_links=int(r[-1]['links']), final_lb=int(r[-1]['link_bytes']))
def statvfs(D):
    m = re.search(r'total_bytes=(\d+).*expected_default_MiB=(\d+)', rd(os.path.join(D, 'statvfs.txt'))); return (int(m.group(1)), int(m.group(2))) if m else (None, None)
arms = ['b256', 'b1024', 'bdef', 'n256', 'n1024', 'ndef']
print('| arm | knob (yaml) | read-back cdc_total_space | A MiB | statvfs total → expected default | stress errors / partitions | rows in table | accepted MiB (rows × 16 KiB) | WARN Rejecting / ERROR entries | Freed up lines | max link bytes (MiB) | max links | max idx bytes | links deleted (sampler) | max gap ms | B3f window | matched B3g row |')
print('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
rows = {}
for a in arms:
    D = os.path.join(L, a)
    if not os.path.isdir(D): print('| %s | not run |' % a); rows[a] = 'missing'; continue
    yaml = {'b256': '256MiB', 'n256': '256MiB', 'b1024': '1024MiB', 'n1024': '1024MiB', 'bdef': '0MiB', 'ndef': '0MiB'}[a]
    rb = setting(D, 'cdc_total_space'); A = mib(rb); tot, exp = statvfs(D)
    err, parts = stress(D); cnt = count(D); sc = scan(D); sm = samp(D)
    blk = a.startswith('b'); AB = A * MIB if A else 0
    acc = cnt * ROW if cnt is not None else None
    warn = int(sc.get('warn_rejecting', 0)); fu = int(sc.get('freed_up', 0))
    default_ok = None
    if yaml == '0MiB': default_ok = (A == exp)
    if blk:
        win = 'errors > 0, WARN; accepted in [%d, %d] MiB; max ≤ %d MiB' % (A - 128, A + 32, A + 32) if A else '-'
        if default_ok is False: row = '4 default derivation differs (Refuted)'
        elif sm['max_lb'] > AB + 2 * S: row = '2 cap not binding (Refuted)'
        elif (err or 0) == 0: row = '3 rejection path not reached (recheck)'
        elif sm['max_lb'] > AB + S: row = '5 overshoot > 1 segment (Not confirmed)'
        elif acc is not None and acc < AB - 4 * S: row = '6 cap below knob (Not confirmed)'
        elif warn >= 1 and acc is not None and AB - 4 * S <= acc <= AB + S and sm['max_lb'] <= AB + S: row = '1 claim confirmed'
        else: row = 'no row'
    else:
        win = '0 errors, no WARN; ≥ 1 Freed up and deleted link; max ≤ %d MiB' % (A + 32) if A else '-'
        if default_ok is False: row = '4 default derivation differs (Refuted)'
        elif (err or 0) > 0 or warn > 0: row = '7 failures in non-blocking (Refuted)'
        elif sm['max_lb'] > AB + 2 * S: row = '2 cap not binding (Refuted)'
        elif fu == 0 or sm['deleted'] == 0: row = '8 no deletion evidence (Invalid)'
        elif sm['max_lb'] > AB + S: row = '5 overshoot > 1 segment (Not confirmed)'
        else: row = '1 claim confirmed'
    rows[a] = row
    print('| %s | %s | %s | %s | %s → %s | %s / %s | %s | %s | %s / %s | %s | %d (%.2f) | %d | %d | %d | %d | %s | %s |' % (
        a, yaml, rb, A, tot, exp, err, parts, cnt, '%.1f' % (acc / MIB) if acc is not None else '-', warn, sc.get('error_entries'),
        fu, sm['max_lb'], sm['max_lb'] / MIB, sm['max_links'], sm['max_idx'], sm['deleted'], sm['gap'], win, row))
ctl = {}
D = os.path.join(L, 'ctl-plain')
if os.path.isdir(D):
    err, parts = stress(D); sc = scan(D); sm = samp(D); A = mib(setting(D, 'cdc_total_space'))
    fl = re.search(r'flush=(\S+) .*start_ms=(\d+) end_ms=(\d+) exit=(\d+)', rd(os.path.join(D, 'flush.txt')))
    if fl:   # re-run (B3h (a) amended 2026-10-24): max links over every sample from flush return + 30 s to the sampler's stop
        r = list(csv.DictReader(open(os.path.join(D, 'sampler.csv'))))
        post = [int(x['links']) for x in r if int(x['ts_ms']) >= int(fl.group(3)) + 30000]
        pf = max(post) if post else 99; pfn = 'post-flush max links (nodetool flush [%s], exit %s, %d ms; %d samples from return + 30 s)' % (fl.group(1), fl.group(4), int(fl.group(3)) - int(fl.group(2)), len(post))
        ok = fl.group(4) == '0' and bool(post)
    else:    # run 1 (flush ks): the last sample
        pf = sm['final_links']; pfn = 'links at the last sample (after flush + 30 s)'; ok = True
    ok = ok and err == 0 and int(sc.get('warn_rejecting', 0)) == 0 and sm['max_lb'] <= A * MIB + S and pf <= 2
    ctl['ctl-plain'] = ok
    print('\nctl-plain (cdc=false, 256MiB blocking): stress errors %s / partitions %s, rows %s, WARN Rejecting %s, max link bytes %d (%.1f MiB, bound %d MiB), %s %d (last sample %d) -> %s'
          % (err, parts, count(D), sc.get('warn_rejecting'), sm['max_lb'], sm['max_lb'] / MIB, A + 32, pfn, pf, sm['final_links'], 'holds' if ok else 'FAILS'))
D = os.path.join(L, 'ctl-cdcoff')
if os.path.isdir(D):
    err, parts = stress(D); sc = scan(D); sm = samp(D)
    ok = err == 0 and sm['max_links'] == 0 and int(sc.get('warn_rejecting', 0)) == 0
    ctl['ctl-cdcoff'] = ok
    print('ctl-cdcoff (cdc_enabled false, 256MiB blocking): read-back cdc_enabled=%s cdc_total_space=%s; stress errors %s / partitions %s, rows %s, max links %d -> %s'
          % (setting(D, 'cdc_enabled'), setting(D, 'cdc_total_space'), err, parts, count(D), sm['max_links'], 'holds' if ok else 'FAILS'))
D = os.path.join(L, 'startup-cdcoff-0')
if os.path.isdir(D):
    rb = setting(D, 'cdc_total_space'); ok = rb == '0MiB'; ctl['startup-cdcoff-0'] = ok
    print('startup-cdcoff-0 (cdc_enabled false, 0MiB): read-back cdc_enabled=%s cdc_total_space=%s, Small-cdc warnings %s -> %s' % (setting(D, 'cdc_enabled'), rb, scan(D).get('small_cdc'), 'holds' if ok else 'FAILS'))
v = list(rows.values())
if any('Refuted' in x for x in v): tier = 'Refuted'
elif all(x.startswith('1 ') for x in v) and ctl and all(ctl.values()) and len(ctl) == 3: tier = 'Confirmed (row 1)'
elif any('Invalid' in x for x in v) or not all(ctl.values()): tier = 'Invalid'
else: tier = 'Not confirmed'
print('\narm rows: %s; controls: %s\nTIER (B3g amended rule): %s' % (rows, ctl, tier))
