#!/usr/bin/env python3
"""B19 arm summary from raw files: samples.csv, client.log, cg.csv, V-logs/gc.log*, args.txt.
Prints key=value lines and a last one-line summary.  python3 -I b19peaks.py <armdir>"""
import sys, os, re, csv, glob, statistics, datetime
R = sys.argv[1]
MiB = 1048576.0
def ms_of(tag):
    for l in open(os.path.join(R, 'args.txt')):
        if l.strip().endswith(tag) or (' ' + tag) in l:
            return int(l.split()[0])
    return None
fstart = ms_of('flood start'); fend = ms_of('flood end')
cl = open(os.path.join(R, 'client.log')).read() if os.path.exists(os.path.join(R, 'client.log')) else ''
m = re.search(r'FLOOD_START (\d+)', cl); t0 = int(m.group(1)) if m else fstart
rows = list(csv.DictReader(open(os.path.join(R, 'samples.csv'))))
def num(r, k):
    try:
        v = float(r[k]); return v
    except Exception: return None
base = [num(r, 'heap_used') for r in rows if fstart and int(r['epoch_ms']) < fstart and num(r, 'heap_used') is not None and num(r, 'heap_used') >= 0]
out = {}
out['baseline_heap_MiB'] = round(statistics.median(base[-20:]) / MiB, 1) if base else None
fl = [r for r in rows if t0 and int(r['epoch_ms']) >= t0 and num(r, 'heap_used') is not None and num(r, 'heap_used') >= 0]
if fl:
    out['peak_heap_MiB'] = round(max(num(r, 'heap_used') for r in fl) / MiB, 1)
    out['peak_old_MiB'] = round(max(num(r, 'old_used') for r in fl) / MiB, 1)
    out['K_last_MiB'] = round(num(fl[-1], 'K_requests_size') / MiB, 2)
    out['K_max_MiB'] = round(max(num(r, 'K_requests_size') for r in fl) / MiB, 2)
    out['paused_max'] = int(max(num(r, 'paused_conns') for r in fl))
    pre = [r for r in rows if num(r, 'conn_paused_count') is not None and num(r, 'conn_paused_count') >= 0 and int(r['epoch_ms']) < t0]
    p0 = num(pre[-1], 'conn_paused_count') if pre else 0
    to0 = num(pre[-1], 'timed_out_before_proc') if pre else 0
    rc0 = num(pre[-1], 'range_count') if pre else 0
    out['conn_paused_delta'] = int(num(fl[-1], 'conn_paused_count') - p0)
    out['timed_out_before_proc_delta'] = int(num(fl[-1], 'timed_out_before_proc') - to0)
    out['range_completed_delta'] = int(num(fl[-1], 'range_count') - rc0)
    out['last_sample_s'] = round((int(fl[-1]['epoch_ms']) - t0) / 1000.0, 1)
    out['ntr_pending_max'] = int(max(num(r, 'ntr_pending') for r in fl))
    out['read_active_max'] = int(max(num(r, 'read_active') for r in fl))
# death time: first NA sample after t0
dead = [int(r['epoch_ms']) for r in rows if t0 and int(r['epoch_ms']) >= t0 and r['heap_used'] == 'NA']
if dead: out['jvm_gone_after_s'] = round((dead[0] - t0) / 1000.0, 1)
# client
stats = re.findall(r'STAT t=(\d+) ms=(\d+) sent=(\d+) dsent=(\d+) rows=(\d+) out=(-?\d+)', cl)
if stats:
    first5 = [int(s[3]) for s in stats[:5]]
    out['lambda_first5_per_s'] = round(sum(first5) / max(1, len(first5)), 1)
    out['lambda_overall_per_s'] = round(int(stats[-1][2]) / max(1, int(stats[-1][0])), 1)
    out['client_out_last'] = int(stats[-1][5]); out['client_out_max'] = max(int(s[5]) for s in stats)
    out['client_rows'] = int(stats[-1][4])
mb = re.search(r'BODY kind=(\S+) D_decompressed=(\d+) c_compressed_body=(\d+)', cl)
if mb: out['D'] = int(mb.group(2)); out['c'] = int(mb.group(3))
# gc log: post-GC occupancy after t0
post = []; prepost = []; full = 0; lastgc = None
pauses = []
for g in sorted(glob.glob(os.path.join(R, 'V-logs', 'gc.log*')), key=os.path.getmtime):
    for l in open(g, errors='replace'):
        mt = re.match(r'\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3})([+-]\d{4})\]', l)
        if not mt: continue
        mp = re.search(r'GC\(\d+\) (Pause [^0-9]*?) (\d+)M->(\d+)M\((\d+)M\) ([0-9.]+)ms', l)
        if not mp: continue
        ts = datetime.datetime.strptime(mt.group(1) + mt.group(2), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000
        if t0 and ts >= t0:
            post.append(int(mp.group(3))); lastgc = max(lastgc or 0, ts); pauses.append((ts, float(mp.group(5))))
            if 'Full' in mp.group(1): full += 1
        elif fstart and ts < fstart and 'Young' in mp.group(1):
            prepost.append(int(mp.group(3)))
if prepost: out['postgc_before_flood_MiB'] = prepost[-1]
if pauses and t0:
    tot = sum(d for _, d in pauses); out['stw_ms_total'] = round(tot)
    best = 0.0
    for ts0, _ in pauses:
        w = sum(d for ts, d in pauses if ts0 <= ts < ts0 + 60000); best = max(best, w / 60000.0)
    out['stw_frac_max60s'] = round(best, 3)
if post: out['postgc_max_MiB'] = max(post); out['postgc_last_MiB'] = post[-1]; out['gc_pauses'] = len(post); out['full_gcs'] = full; out['last_gc_s'] = round((lastgc - t0) / 1000.0, 2)
# cg
if os.path.exists(os.path.join(R, 'cg.csv')):
    cg = [l.strip().split(',') for l in open(os.path.join(R, 'cg.csv'))][1:]
    rs = [int(c[1]) for c in cg if c[1].isdigit()]
    if rs: out['rssanon_max_MiB'] = round(max(rs) / 1024.0, 1)
    ok = [c[3] for c in cg if c[3] != '']
    out['oom_kill'] = ok[-1] if ok else None
for k, v in out.items(): print(f'{k}={v}')
print(' '.join(f'{k}={v}' for k, v in out.items()))
