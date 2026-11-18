#!/usr/bin/env python3
# C4: per-arm summary from arms/<arm>/{summary.txt,sampler.csv}. Usage: analyze.py <arm dir>...
import csv, re, sys, statistics
for d in sys.argv[1:]:
    S = open(d + '/summary.txt').read()
    rows = [r for r in csv.DictReader(open(d + '/sampler.csv'))]
    ti0 = int(re.search(r'import start (\d+)', S).group(1)); m = re.search(r'import end (\d+) rc (\d+)', S)
    ti1, rc = int(m.group(1)), m.group(2)
    idle = [int(r['rss_anon_kb']) for r in rows if r['rss_anon_kb'] and ti0 - 30000 <= int(r['epoch_ms']) < ti0]
    I0 = statistics.median(idle) / 1024
    live = [r for r in rows if r['rss_anon_kb']]
    peak = max(int(r['rss_anon_kb']) for r in live) / 1024
    cga = max(int(r['cg_anon']) for r in rows if r['cg_anon']) / 2**20
    cgc = max(int(r['cg_current']) for r in rows if r['cg_current']) / 2**20
    last = live[-1]; ev = [r for r in rows if r['ev_oom_kill']]
    kills = ev[-1]['ev_oom_kill'] if ev else 'n/a'; evmax = ev[-1]['ev_max'] if ev else 'n/a'
    alive = re.search(r'alive at end: (\d)', S).group(1)
    pool = re.search(r'memory pool size of (\d+) MB', S); pool = pool.group(1) if pool else '?'
    ts = re.findall(r'Index summary off heap memory used: (\d+)', S)
    print(f"{d.rstrip('/').split('/')[-1]}: pool={pool}MB I0={I0:.0f}MiB peakRssAnon={peak:.0f}MiB dU={peak-I0:.0f}MiB "
          f"cgAnonPeak={cga:.0f}MiB cgCurPeak={cgc:.0f}MiB import_rc={rc} import_s={(ti1-ti0)/1000:.1f} "
          f"last_rss_row_after_import_start_s={(int(last['epoch_ms'])-ti0)/1000:.1f} ev_max={evmax} oom_kill={kills} alive={alive} "
          f"K_summary_bytes={ts[-1] if ts else 'n/a'}")
