#!/usr/bin/env python3
# R10: per-arm summary from arms/<arm>/{summary.txt,sampler.csv,smaps.csv,cstats.txt}. Usage: analyze.py <arm dir>...
import csv, re, sys, statistics, collections
def ts(S, pat):
    m = re.search(pat, S); return int(m.group(1)) if m else None
for d in sys.argv[1:]:
    d = d.rstrip('/'); name = d.split('/')[-1]
    S = open(d + '/summary.txt').read()
    t0 = int(open(d + '/t0.txt').read())
    rows = [r for r in csv.DictReader(open(d + '/sampler.csv'))]
    live = [r for r in rows if r['rss_anon_kb']]
    m = re.search(r'I0 \(median RssAnon last 30 s\) = (\d+) kB', S); I0 = int(m.group(1)) / 1024 if m else float('nan')
    tP = ts(S, r'import P start (\d+)'); tQ = ts(S, r'import Q start (\d+)')
    def peak(a, b):
        v = [(int(r['rss_anon_kb']), int(r['epoch_ms'])) for r in live if a <= int(r['epoch_ms']) < b]
        return (max(v)[0] / 1024, (max(v)[1] - t0) / 1000) if v else (float('nan'), None)
    END = int(live[-1]['epoch_ms']) + 1 if live else t0
    pk, pkt = peak(t0, END + 1)
    pP = peak(tP, tQ or END + 1)[0] if tP else float('nan')
    pQ = peak(tQ, END + 1)[0] if tQ else float('nan')
    cga = max((int(r['cg_anon']) for r in rows if r['cg_anon']), default=0) / 2**20
    ev = [r for r in rows if r['ev_oom_kill']]
    kills = ev[-1]['ev_oom_kill'] if ev else 'n/a'; evmax = ev[-1]['ev_max'] if ev else 'n/a'
    alive = re.search(r'alive at end: (\d)', S); alive = alive.group(1) if alive else '?'
    pool = re.search(r'memory pool size of (\d+) MB', S); pool = pool.group(1) if pool else '?'
    # compaction timing from system.log lines in summary
    cs = re.search(r'\[(\S+ \S+)\] compaction started', S); cdn = re.search(r'compaction done: .*in ([\d,]+)ms', S)
    # last compactionstats progress
    prog = ''
    try:
        for line in open(d + '/cstats.txt'):
            t, _, r = line.rstrip('\n').partition('|')
            mm = re.search(r'Compaction r10 isx (\d+) (\d+) bytes ([\d.]+)%', r)
            if mm: prog = f"{(int(t)-t0)/1000:.0f}s:{mm.group(3)}%"
    except FileNotFoundError: pass
    # smaps at the sample nearest the peak: anon mappings >= 8 MiB except the Java heap reservation (>= 900 MiB)
    snap = collections.defaultdict(list)
    try:
        for r in csv.DictReader(open(d + '/smaps.csv')):
            snap[int(r['epoch_ms'])].append((int(r['size_kb']), int(r['rss_kb'])))
    except FileNotFoundError: pass
    sm = ''
    if snap and pkt is not None:
        tpk = t0 + int(pkt * 1000); k = min(snap, key=lambda x: abs(x - tpk))
        blocks = sorted([b for b in snap[k] if b[0] < 900 * 1024], reverse=True)
        sm = (f"smaps@{(k-t0)/1000:.0f}s: n={len(blocks)} sumSize={sum(b[0] for b in blocks)/1024:.0f}MiB sumRss={sum(b[1] for b in blocks)/1024:.0f}MiB "
              f"top={[(round(b[0]/1024,1), round(b[1]/1024,1)) for b in blocks[:12]]}")
    kb = re.findall(r'Index summary off heap memory used: (\d+)', S)
    print(f"{name}: pool={pool}MB I0={I0:.0f} peakRssAnon={pk:.0f}@{pkt}s dU={pk-I0:.0f} peakP={pP:.0f} (dP={pP-I0:.0f}) peakQwin={pQ:.0f} (dQwin={pQ-I0:.0f}) "
          f"cgAnonPeak={cga:.0f} ev_max={evmax} oom_kill={kills} alive={alive} lastprog={prog} compaction_ms={cdn.group(1) if cdn else 'n/a'} "
          f"K_summary_bytes={kb} | {sm}")
