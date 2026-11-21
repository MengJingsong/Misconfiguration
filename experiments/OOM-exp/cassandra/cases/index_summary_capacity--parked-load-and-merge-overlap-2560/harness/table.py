#!/usr/bin/env python3
# R18: one row per arm for §3 (R10's table.py plus the memory.stat ceiling terms): table.py <arm dir>...
import csv, re, sys, os, datetime, collections
def kb(s, key):
    m = re.search(key + r': +(\d+) kB', s); return int(m.group(1)) // 1024 if m else None
M = 2 ** 20
for d in sys.argv[1:]:
    d = d.rstrip('/'); n = os.path.basename(d); S = open(d + '/summary.txt').read(); t0 = int(open(d + '/t0.txt').read())
    if 'I0 (median' not in S:
        print(f"{n} | INVALID/incomplete: {' / '.join(l[26:] for l in S.splitlines() if 'INVALID' in l)}"); continue
    rows = [r for r in csv.DictReader(open(d + '/sampler.csv')) if r['rss_anon_kb']]
    I0 = int(re.search(r'I0 .* = (\d+) kB', S).group(1)) // 1024
    line = lambda tag: next((l for l in S.splitlines() if f'rss {tag}:' in l), '')
    pP = kb(line('postP'), 'RssAnon'); pR = kb(line('postR'), 'RssAnon'); p30 = kb(line(r'\+30'), 'RssAnon')
    tQ = re.search(r'import Q start (\d+)', S); tQ = (int(tQ.group(1)) - t0) / 1000 if tQ else None
    qrc = re.search(r'import Q end \d+ rc (\d+)', S); qrc = qrc.group(1) if qrc else '-'
    cs = re.search(r'compaction started: .*?(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d,\d+)', S)
    peak = max(rows, key=lambda r: int(r['rss_anon_kb'])); pk = int(peak['rss_anon_kb']) // 1024; pkt = (int(peak['epoch_ms']) - t0) / 1000
    # peak after the Q import began, before the compaction start (pre-merge)
    cst = (datetime.datetime.strptime(cs.group(1), '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000 - t0) / 1000 if cs else None
    pre = [int(r['rss_anon_kb']) // 1024 for r in rows if tQ is not None and (int(r['epoch_ms']) - t0) / 1000 >= tQ and (cst is None or (int(r['epoch_ms']) - t0) / 1000 < cst)]
    last = (int(rows[-1]['epoch_ms']) - t0) / 1000
    ev = [r for r in csv.DictReader(open(d + '/sampler.csv')) if r['ev_max']]
    evmax = ev[-1]['ev_max'] if ev else ''; kill = ev[-1]['ev_oom_kill'] if ev else ''
    dm = open(d + '/dmesg-block.txt').read() if os.path.exists(d + '/dmesg-block.txt') else ''
    comm = re.search(r'\] (\S+) invoked oom-killer', dm); ar = re.search(r'anon-rss:(\d+)kB, file-rss:(\d+)kB', dm)
    cga = re.search(r'\] anon (\d+)', dm); fm = re.search(r'file_mapped (\d+)', dm)
    prog = ''
    if os.path.exists(d + '/cstats.txt'):
        for l in open(d + '/cstats.txt'):
            m = re.search(r'Compaction r10 isx \d+ \d+ bytes ([\d.]+)%', l)
            if m: prog = f"{(int(l.split('|')[0]) - t0) / 1000:.0f}s {m.group(1)}%"
    cd = re.search(r'compaction done: .*in ([\d,]+)ms', S)
    Ks = re.findall(r'Index summary off heap memory used: (\d+)', S)
    alive = re.search(r'alive at end: (\d)', S); alive = alive.group(1) if alive else '?'
    pool = re.search(r'memory pool size of (\d+) MB', S); pool = pool.group(1) if pool else '?'
    # memory.stat: file_mapped at idle (median over t0+120..t0+140 s window near the idle snap) and in the last live row
    ms_ = [r for r in csv.DictReader(open(d + '/memstat.csv')) if r['anon']] if os.path.exists(d + '/memstat.csv') else []
    idle = re.search(r'\[(\S+ \S+)\] I0 \(median', S)
    fmi = ''
    if ms_:
        t_i = int(re.search(r'memstat idle \(last row\): (\d+)', S).group(1)) if 'memstat idle' in S else None
        ri = [r for r in ms_ if t_i and int(r['epoch_ms']) <= t_i]
        if ri: r = ri[-1]; fmi = f"idle fm {int(r['file_mapped'])/M:.1f} pt {int(r['pagetables'])/M:.1f} ks {int(r['kernel_stack'])/M:.1f} slab {int(r['slab'])/M:.1f} sock {int(r['sock'])/M:.1f}"
        r = ms_[-1]; fml = f"last fm {int(r['file_mapped'])/M:.1f} pt {int(r['pagetables'])/M:.1f} ks {int(r['kernel_stack'])/M:.1f} slab {int(r['slab'])/M:.1f} anon {int(r['anon'])/M:.1f} cur {int(r['cg_current'])/M:.1f} @t0+{(int(r['epoch_ms'])-t0)/1000:.0f}"
    else: fml = ''
    alt = re.search(r'readback: .*?(\d+) \| (\d+)', S[S.find('alter start'):]) if 'alter start' in S else None
    inval = [l[26:90] for l in S.splitlines() if 'INVALID' in l]
    print(f"{n} | pool {pool} | I0 {I0} | postP {pP} (Δ{pP - I0 if pP else '-'}) | postR {pR} | Qimp t0+{tQ} rc {qrc} | preMergePeak {max(pre) if pre else '-'} | "
          f"alter {alt.group(1) if alt else '-'} | compaction {f'start t0+{cst:.1f}' if cs else 'none'} done {cd.group(1) if cd else '-'} | last cstats {prog} | "
          f"peak {pk} (Δ{pk - I0}) at t0+{pkt:.1f} | last row t0+{last:.1f} | +30 {p30} | ev.max {evmax} oom_kill {kill} alive {alive} | "
          f"kill: {comm.group(1) if comm else '-'} anon-rss {round(int(ar.group(1))/1024,1) if ar else '-'} file-rss {round(int(ar.group(2))/1024,1) if ar else '-'} "
          f"cg.anon {round(int(cga.group(1))/M,1) if cga else '-'} file_mapped {round(int(fm.group(1))/M,1) if fm else '-'} | {fmi} | {fml} | K {Ks} | {'INVALID ' + str(inval) if inval else ''}")
