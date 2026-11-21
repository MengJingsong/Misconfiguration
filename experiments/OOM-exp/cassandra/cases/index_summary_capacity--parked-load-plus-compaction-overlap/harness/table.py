#!/usr/bin/env python3
# R10: one row per arm for §3: table.py <arm dir>...
import csv, re, sys, os, datetime
def kb(s, key):
    m = re.search(key + r': +(\d+) kB', s); return int(m.group(1)) // 1024 if m else None
for d in sys.argv[1:]:
    d = d.rstrip('/'); n = os.path.basename(d); S = open(d + '/summary.txt').read(); t0 = int(open(d + '/t0.txt').read())
    rows = [r for r in csv.DictReader(open(d + '/sampler.csv')) if r['rss_anon_kb']]
    I0 = int(re.search(r'I0 .* = (\d+) kB', S).group(1)) // 1024
    line = lambda tag: next((l for l in S.splitlines() if f'rss {tag}:' in l), '')
    pP = kb(line('postP'), 'RssAnon'); pR = kb(line('postR'), 'RssAnon'); p120 = kb(line('+120'), 'RssAnon')
    tQ = re.search(r'import Q start (\d+)', S); tQ = (int(tQ.group(1)) - t0) / 1000 if tQ else None
    qrc = re.search(r'import Q end \d+ rc (\d+)', S); qrc = qrc.group(1) if qrc else '-'
    cs = re.search(r'compaction started: .*?(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d,\d+)', S)
    peak = max(rows, key=lambda r: int(r['rss_anon_kb'])); pk = int(peak['rss_anon_kb']) // 1024; pkt = (int(peak['epoch_ms']) - t0) / 1000
    last = (int(rows[-1]['epoch_ms']) - t0) / 1000
    ev = [r for r in csv.DictReader(open(d + '/sampler.csv')) if r['ev_max']]
    evmax = ev[-1]['ev_max'] if ev else ''; kill = ev[-1]['ev_oom_kill'] if ev else ''
    dm = open(d + '/dmesg-block.txt').read() if os.path.exists(d + '/dmesg-block.txt') else ''
    comm = re.search(r'Comm: (.+?) +Tainted', dm); ar = re.search(r'anon-rss:(\d+)kB, file-rss:(\d+)kB', dm)
    cga = re.search(r'\] anon (\d+)', dm); fm = re.search(r'file_mapped (\d+)', dm)
    prog = ''
    if os.path.exists(d + '/cstats.txt'):
        for l in open(d + '/cstats.txt'):
            m = re.search(r'Compaction r10 isx \d+ \d+ bytes ([\d.]+)%', l)
            if m: prog = f"{(int(l.split('|')[0]) - t0) / 1000:.0f}s {m.group(1)}%"
    cst = (datetime.datetime.strptime(cs.group(1), '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000 - t0) / 1000 if cs else None
    cd = re.search(r'compaction done: .*in ([\d,]+)ms', S)
    Ks = re.findall(r'Index summary off heap memory used: (\d+)', S)
    alive = re.search(r'alive at end: (\d)', S).group(1)
    print(f"{n} | I0 {I0} | postP {pP} (Δ{pP - I0 if pP else '-'}) | postR {pR} | Qimp t0+{tQ} rc {qrc} | compaction {f'start t0+{cst:.1f}' if cs else 'none'} done {cd.group(1) if cd else '-'} | last cstats {prog} | "
          f"peak {pk} (Δ{pk - I0}) at t0+{pkt:.1f} | last row t0+{last:.1f} | +120 {p120} | ev.max {evmax} oom_kill {kill} alive {alive} | "
          f"kill: {comm.group(1) if comm else '-'} anon-rss {int(ar.group(1))/1024 if ar else '-'} file-rss {int(ar.group(2))/1024 if ar else '-'} cg.anon {int(cga.group(1))/2**20 if cga else '-'} file_mapped {int(fm.group(1))/2**20 if fm else '-'} | K {Ks}")
