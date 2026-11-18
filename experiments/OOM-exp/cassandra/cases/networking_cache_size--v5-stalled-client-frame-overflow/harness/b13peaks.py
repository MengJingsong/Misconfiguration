#!/usr/bin/env python3
# b13peaks.py <armdir>: per-arm readings (case §2.6) from samples.csv, nmt.csv, cg.csv, ss.csv, load.log, probe.csv,
# first-oom.txt, memory.events.final, V-flags.txt. Writes readings.json; prints one summary line (last line).
# idle = the 10 s before LOAD_START. U_F = JDK direct MemoryUsed - idle median. K = net Size - net OverflowSize.
# held responses = (U_F peak - (K_peak - K_idle)) / 3.50 MiB (overflow frames); responses produced = dBytesSent / 3,670,300.
# dU_N = (NMT Other - JDK MemoryUsed) - idle median of the same.
import csv, json, os, re, sys, statistics, bisect
R = sys.argv[1]; MiB = 1048576.0; RESP = 3670300
def rows(fn):
    p = os.path.join(R, fn)
    if not os.path.exists(p): return []
    with open(p) as f: return list(csv.DictReader(f))
def num(x):
    try: return float(x)
    except: return None
def txt(fn):
    p = os.path.join(R, fn); return open(p, errors='replace').read() if os.path.exists(p) else ''
smp = [r for r in rows('samples.csv') if num(r.get('direct_used')) is not None and num(r['direct_used']) >= 0]
nmt = rows('nmt.csv'); cg = rows('cg.csv'); ssr = rows('ss.csv'); probe = rows('probe.csv')
load = txt('load.log')
m = re.search(r'LOAD_START (\d+)', load); ls = int(m.group(1)) if m else None
m = re.search(r'SENT_ALL (\d+) (\d+)', load); sent_all = (int(m.group(1)), int(m.group(2))) if m else None
waves = re.findall(r'WAVE (\d+) (\d+)', load)
out = {'sent_total': int(waves[-1][1]) if waves else 0, 'sent_all_s': round((sent_all[0] - ls) / 1000, 1) if sent_all and ls else None}
mf = re.search(r'MaxDirectMemorySize=(\d+)', txt('V-flags.txt')); D = int(mf.group(1)) if mf else None
out['D_MiB'] = round(D / MiB) if D else None
idle = [r for r in smp if ls and ls - 11000 <= int(r['epoch_ms']) < ls]
after = [r for r in smp if ls and int(r['epoch_ms']) >= ls]
def med(col, rs=idle):
    v = [num(r[col]) for r in rs if num(r[col]) is not None and num(r[col]) >= 0]; return statistics.median(v) if v else None
def pk(col, rs=after):
    v = [num(r[col]) for r in rs if num(r[col]) is not None and num(r[col]) >= 0]; return max(v) if v else None
def mib(x): return round(x / MiB, 1) if x is not None else None
d0 = med('direct_used'); out['direct_idle_MiB'] = mib(d0)
dp = pk('direct_used'); out['direct_peak_MiB'] = mib(dp)
out['U_F_peak_MiB'] = mib(dp - d0) if dp is not None and d0 is not None else None
for r in smp: r['K'] = (num(r['net_size']) - num(r['net_overflow'])) if num(r['net_size']) is not None and num(r['net_overflow']) is not None and num(r['net_size']) >= 0 else -1
out['K_idle_MiB'] = mib(med('K')); out['K_peak_MiB'] = mib(pk('K'))
out['net_capacity_MiB'] = mib(pk('net_capacity'))
out['overflow_peak_MiB'] = mib(pk('net_overflow')); out['net_used_peak_MiB'] = mib(pk('net_used'))
out['cc_size_peak_MiB'] = mib(pk('cc_size'))
out['requests_size_peak_MiB'] = round(pk('requests_size') / MiB, 3) if pk('requests_size') is not None else None
out['heap_peak_MiB'] = mib(pk('heap_used'))
out['ntr_active_peak'] = pk('ntr_active'); out['ntr_pending_peak'] = pk('ntr_pending'); out['paused_peak'] = pk('paused_conns')
def delta(col):
    v = [num(r[col]) for r in after if num(r[col]) is not None and num(r[col]) >= 0]
    b = [num(r[col]) for r in idle if num(r[col]) is not None and num(r[col]) >= 0]
    return (v[-1] - (b[-1] if b else v[0])) if v else None
bs = delta('bytes_sent'); out['responses_produced'] = round(bs / RESP, 1) if bs is not None else None
out['timed_out_before_proc'] = delta('timed_out_before_proc'); out['req_dispatched'] = delta('req_dispatched')
out['net_misses'] = delta('net_misses')
if dp is not None and d0 is not None:
    out['held_resp_est'] = round((dp - d0) / (3.5 * MiB), 1)
# last sample before the OOM (or the last sample)
fo = txt('first-oom.txt')
fol = fo.splitlines()
oi = next((i for i, l in enumerate(fol) if ('OutOfMemoryError:' in l or 'OutOfDirectMemoryError' in l) and 'CompileCommand' not in l), None)
oomline = fol[oi] if oi is not None else ''
TS = r'(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d:\d\d),(\d+)'
hdr = next((fol[j] for j in range(oi, -1, -1) if re.search(TS, fol[j])), '') if oi is not None else ''
mt = re.search(TS, hdr)
out['first_oom_header'] = hdr[:200]; out['first_oom_line'] = oomline[:200]
args = txt('args.txt'); ma = re.search(r'^(\d+) OOM line seen', args, re.M); t_seen = int(ma.group(1)) if ma else None
t_oom = None
if mt:
    import calendar, time as _t
    # system.log time is UTC on this build (e.g. 2026-11-18T13:17:13,786)
    t_oom = int(calendar.timegm(_t.strptime(mt.group(1) + ' ' + mt.group(2), '%Y-%m-%d %H:%M:%S')) * 1000 + int(mt.group(3)))
out['oom_at_s'] = round((t_oom - ls) / 1000, 1) if t_oom and ls else None
ref = t_oom or (int(after[-1]['epoch_ms']) if after else None)
pre = [r for r in after if ref and int(r['epoch_ms']) <= ref]
last = pre[-1] if pre else (after[-1] if after else None)
if last:
    out['last_direct_MiB'] = mib(num(last['direct_used'])); out['last_K_MiB'] = mib(last['K'])
    out['last_overflow_MiB'] = mib(num(last['net_overflow'])); out['last_net_used_MiB'] = mib(num(last['net_used']))
    out['last_U_F_MiB'] = mib(num(last['direct_used']) - d0) if d0 is not None else None
    out['last_frac_of_D'] = round(num(last['direct_used']) / D, 3) if D else None
    out['last_used_frac_of_D'] = round(num(last['net_used']) / D, 3) if D else None
    out['last_sample_before_oom_s'] = round((int(last['epoch_ms']) - ls) / 1000, 1) if ls else None
# Send-Q
sq = [num(r['srv_sendq_sum']) for r in ssr if ls and int(r['epoch_ms']) >= ls and num(r['srv_sendq_sum']) is not None]
out['sendq_sum_peak_MiB'] = mib(max(sq)) if sq else None
rq = [num(r['cli_recvq_sum']) for r in ssr if ls and int(r['epoch_ms']) >= ls and num(r['cli_recvq_sum']) is not None]
out['cli_recvq_sum_peak_MiB'] = mib(max(rq)) if rq else None
# Netty domain N
st = [int(r['epoch_ms']) for r in smp]; sd = [num(r['direct_used']) for r in smp]
def jdk_at(t):
    if not st: return 0.0
    i = bisect.bisect_left(st, t); c = [j for j in (i - 1, i) if 0 <= j < len(st)]
    return sd[min(c, key=lambda j: abs(st[j] - t))]
def oth(r):
    o = num(r.get('other_committed_kb')); return o * 1024 if o is not None else None
base = [oth(r) - jdk_at(int(r['epoch_ms'])) for r in nmt if ls and ls - 11000 <= int(r['epoch_ms']) < ls and oth(r) is not None]
X0 = statistics.median(base) if base else None
du = [oth(r) - jdk_at(int(r['epoch_ms'])) - X0 for r in nmt if ls and X0 is not None and int(r['epoch_ms']) >= ls and oth(r) is not None]
out['dU_N_peak_MiB'] = mib(max(du)) if du else None
cb = [num(r['rss_anon_kb']) for r in cg if ls and ls - 11000 <= int(r['epoch_ms']) < ls and num(r['rss_anon_kb']) is not None]
ca = [num(r['rss_anon_kb']) for r in cg if ls and int(r['epoch_ms']) >= ls and num(r['rss_anon_kb']) is not None]
out['dRssAnon_peak_MiB'] = round((max(ca) - statistics.median(cb)) / 1024, 1) if ca and cb else None
# class
ev = txt('memory.events.final'); mk = re.search(r'^oom_kill (\d+)', ev, re.M); oomkill = int(mk.group(1)) if mk else 0
if oomkill > 0: cls = 'KILL'
elif 'OutOfDirectMemoryError' in oomline: cls = 'NETTY'
elif 'Direct buffer memory' in oomline:
    if 'org.apache.cassandra.utils.memory.BufferPool.allocate' in fo: cls = 'NIO-NET'
    else:
        cls = 'NIO-OTHER' + ('(counts)' if out.get('last_used_frac_of_D') is not None and out['last_used_frac_of_D'] >= 0.8 else '(competing)')
elif ('Java heap space' in oomline or 'GC overhead' in oomline): cls = 'HEAP'
elif oomline: cls = 'OOM-OTHER'
else: cls = 'NONE'
out['class'] = cls; out['oom_kill'] = oomkill
mth = re.search(r'\[([^\]]+)\]', hdr); out['first_oom_thread'] = mth.group(1) if mth else None
out['forced_heap_oom'] = 'Force heap space OutOfMemoryError' in txt('V-logs/system.log')
out['task_raised'] = txt('task-raised-count.txt').strip()
# probe
def pc(rs):
    c = {}
    for r in rs: c[r['status']] = c.get(r['status'], 0) + 1
    return c
tref = t_oom or t_seen
out['probe_before'] = pc([r for r in probe if ls and int(r['epoch_ms']) >= ls and (not tref or int(r['epoch_ms']) < tref)])
out['probe_after'] = pc([r for r in probe if tref and int(r['epoch_ms']) >= tref])
out['probe_idle'] = pc([r for r in probe if ls and int(r['epoch_ms']) < ls])
alive = [int(r['epoch_ms']) for r in rows('samples.csv') if num(r.get('heap_used')) is not None and num(r['heap_used']) >= 0]
out['last_jmx_s'] = round((max(alive) - ls) / 1000, 1) if alive and ls else None
json.dump(out, open(os.path.join(R, 'readings.json'), 'w'), indent=1)
keys = ['class', 'D_MiB', 'U_F_peak_MiB', 'K_peak_MiB', 'overflow_peak_MiB', 'oom_at_s', 'last_frac_of_D', 'last_K_MiB', 'responses_produced',
        'held_resp_est', 'timed_out_before_proc', 'sendq_sum_peak_MiB', 'dU_N_peak_MiB', 'heap_peak_MiB', 'requests_size_peak_MiB',
        'ntr_pending_peak', 'sent_total', 'probe_before', 'probe_after', 'forced_heap_oom', 'task_raised', 'first_oom_thread']
print(' '.join(f'{k}={str(out.get(k)).replace(" ", "")}' for k in keys))
