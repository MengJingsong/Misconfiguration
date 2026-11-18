#!/usr/bin/env python3
# b9peaks.py <armdir>: per-arm readings from samples.csv, nmt.csv, cg.csv, load.log, first-oom.txt, memory.events.final.
# X0 = median over the 10-s idle baseline (before BURST_START) of (NMT Other - JDK direct MemoryUsed);
# dU_netty(t) = NMT Other(t) - JDK MemoryUsed(nearest sample) - X0; dU_peak = max after BURST_START.
# U_fail = 'used' in the Netty OutOfDirectMemoryError message. K = Client.RequestsSize. S = 15 MiB.
# Prints a JSON blob to readings.json and one summary line (last line of stdout).
import csv, json, os, re, sys, statistics, bisect
R = sys.argv[1]; MiB = 1048576.0; S = 15728640
def rows(fn):
    p = os.path.join(R, fn)
    if not os.path.exists(p): return []
    with open(p) as f: return list(csv.DictReader(f))
def num(x):
    try: return float(x)
    except: return None
smp = rows('samples.csv'); nmt = rows('nmt.csv'); cg = rows('cg.csv')
load = open(os.path.join(R, 'load.log')).read() if os.path.exists(os.path.join(R, 'load.log')) else ''
m = re.search(r'BURST_START (\d+)', load); bs = int(m.group(1)) if m else None
m = re.search(r'BURST_DONE (\d+)', load); bd = int(m.group(1)) if m else None
out = {'burst_start': bs, 'burst_done_s': round((bd - bs) / 1000, 1) if bs and bd else None}
# nearest JDK direct sample
st = [int(r['epoch_ms']) for r in smp if num(r['direct_used']) is not None and num(r['direct_used']) >= 0]
sd = [num(r['direct_used']) for r in smp if num(r['direct_used']) is not None and num(r['direct_used']) >= 0]
def jdk_at(t):
    if not st: return 0.0
    i = bisect.bisect_left(st, t); c = [j for j in (i - 1, i) if 0 <= j < len(st)]
    return sd[min(c, key=lambda j: abs(st[j] - t))]
def other_bytes(r):
    o = num(r.get('other_committed_kb'))
    return o * 1024 if o is not None else None
base = [other_bytes(r) - jdk_at(int(r['epoch_ms'])) for r in nmt if bs and bs - 11000 <= int(r['epoch_ms']) < bs and other_bytes(r) is not None]
X0 = statistics.median(base) if base else None
out['X0_MiB'] = round(X0 / MiB, 1) if X0 is not None else None
du = [(int(r['epoch_ms']), other_bytes(r) - jdk_at(int(r['epoch_ms'])) - X0) for r in nmt if bs and X0 is not None and int(r['epoch_ms']) >= bs and other_bytes(r) is not None]
if du:
    tpk, vpk = max(du, key=lambda x: x[1]); out['dU_peak_MiB'] = round(vpk / MiB, 1); out['dU_peak_at_s'] = round((tpk - bs) / 1000, 1)
else: out['dU_peak_MiB'] = None
out['nmt_samples_after_burst'] = len(du)
after = [r for r in smp if bs and int(r['epoch_ms']) >= bs and num(r['heap_used']) is not None]
before = [r for r in smp if bs and bs - 11000 <= int(r['epoch_ms']) < bs and num(r['heap_used']) is not None]
def pk(col, rs=after):
    v = [num(r[col]) for r in rs if num(r[col]) is not None]; return max(v) if v else None
def mib(x): return round(x / MiB, 1) if x is not None else None
K = pk('K_requests_size'); out['K_peak_MiB'] = mib(K); out['K_peak_frames'] = round(K / S, 1) if K is not None else None
out['K_last_MiB'] = mib(num(after[-1]['K_requests_size'])) if after else None
out['paused_peak'] = pk('paused_conns'); out['connected_peak'] = pk('connected_clients')
out['heap_peak_MiB'] = mib(pk('heap_used')); out['jdk_direct_peak_MiB'] = mib(pk('direct_used'))
out['jdk_direct_base_MiB'] = mib(statistics.median([num(r['direct_used']) for r in before])) if before else None
out['ntr_active_peak'] = pk('ntr_active'); out['ntr_pending_peak'] = pk('ntr_pending')
def delta(col):
    v = [num(r[col]) for r in after if num(r[col]) is not None and num(r[col]) >= 0]
    b = [num(r[col]) for r in before if num(r[col]) is not None and num(r[col]) >= 0]
    return (v[-1] - (b[-1] if b else v[0])) if v else None
out['write_timeouts'] = delta('write_timeouts'); out['timed_out_before_proc'] = delta('timed_out_before_proc')
out['conn_paused_events'] = delta('conn_paused_count'); out['req_dispatched'] = delta('req_dispatched')
d5 = [num(r['req_dispatched']) for r in smp if bs and bs <= int(r['epoch_ms']) <= bs + 5000 and num(r['req_dispatched']) is not None and num(r['req_dispatched']) >= 0]
b0 = [num(r['req_dispatched']) for r in before if num(r['req_dispatched']) is not None and num(r['req_dispatched']) >= 0]
out['decode_rate_5s'] = round((d5[-1] - (b0[-1] if b0 else d5[0])) / 5.0, 1) if d5 else None
# RSS
cb = [num(r['rss_anon_kb']) for r in cg if bs and bs - 11000 <= int(r['epoch_ms']) < bs and num(r['rss_anon_kb']) is not None]
ca = [num(r['rss_anon_kb']) for r in cg if bs and int(r['epoch_ms']) >= bs and num(r['rss_anon_kb']) is not None]
out['dRssAnon_peak_MiB'] = round((max(ca) - statistics.median(cb)) / 1024, 1) if ca and cb else None
# death time: last sample with heap reading
alive = [int(r['epoch_ms']) for r in smp if num(r['heap_used']) is not None and num(r['heap_used']) >= 0]
# first OOM
fo = open(os.path.join(R, 'first-oom.txt')).read() if os.path.exists(os.path.join(R, 'first-oom.txt')) else ''
ev = open(os.path.join(R, 'memory.events.final')).read() if os.path.exists(os.path.join(R, 'memory.events.final')) else ''
mk = re.search(r'^oom_kill (\d+)', ev, re.M); oomkill = int(mk.group(1)) if mk else 0
mu = re.search(r'failed to allocate (\d+) byte\(s\) of direct memory \(used: (\d+), max: (\d+)\)', fo)
out['U_fail_MiB'] = mib(int(mu.group(2))) if mu else None; out['netty_max_MiB'] = mib(int(mu.group(3))) if mu else None
first = fo.splitlines()
oomline = next((l for l in first if 'OutOfMemoryError' in l or 'OutOfDirectMemoryError' in l), '')
if oomkill > 0: cls = 'KILL'
elif 'OutOfDirectMemoryError' in oomline:
    cls = 'NETTY-REQ' if ('cumulate' in fo or 'ByteToMessageDecoder' in fo) else 'NETTY-OTHER'
elif 'Direct buffer memory' in oomline: cls = 'JDK-DIRECT'
elif 'Java heap space' in oomline or 'GC overhead' in oomline: cls = 'HEAP'
elif oomline: cls = 'OOM-OTHER'
else: cls = 'NONE'
mt = re.search(r'^(?:\w+\s+)?\[([^\]]+)\]\s+(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+)', oomline)
out['first_oom_thread'] = mt.group(1) if mt else None
out['class'] = cls; out['oom_kill'] = oomkill
if cls != 'NONE' and bs and alive:
    out['last_alive_after_burst_s'] = round((max(alive) - bs) / 1000, 1)
mf = re.search(r'FINAL (.*)', load); out['client_final'] = mf.group(1) if mf else None
json.dump(out, open(os.path.join(R, 'readings.json'), 'w'), indent=1)
print(' '.join(f'{k}={v}' for k, v in out.items() if k not in ('burst_start', 'client_final')))
