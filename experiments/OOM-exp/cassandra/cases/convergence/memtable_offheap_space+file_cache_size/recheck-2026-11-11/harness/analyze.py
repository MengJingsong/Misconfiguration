# R1 recheck per-arm digest. Usage: python3 -I analyze.py <arm-dir> [...]
import sys, os, re, csv
MiB = 1024 * 1024
def rd(p):
    try: return open(p, errors='replace').read()
    except Exception: return ''
for d in sys.argv[1:]:
    name = os.path.basename(d.rstrip('/'))
    S = rd(os.path.join(d, 'summary.txt'))
    rss = [(m.group(1), int(m.group(2))) for m in re.finditer(r'^rss (\S+): .*?RssAnon: (\d+) kB', S, re.M)]
    idle = next((v for t, v in rss if t == 'idle'), None)
    rows = []
    try:
        with open(os.path.join(d, 'pools.csv')) as f:
            for r in csv.DictReader(f):
                if r['rss_anon_kB'] and r['rss_anon_kB'].isdigit(): rows.append(r)
    except Exception: pass
    def num(r, k):
        try: return int(float(r[k]))
        except Exception: return 0
    peak_s = max([v for t, v in rss] or [0])
    pr = max(rows, key=lambda r: num(r, 'rss_anon_kB')) if rows else None
    peak_p = num(pr, 'rss_anon_kB') if pr else 0
    peak = max(peak_s, peak_p)
    print(f'== {name}')
    print(f'  idle RssAnon {idle/1024 if idle else 0:.0f} MiB; peak RssAnon {peak/1024:.0f} MiB = {100*peak/1024/3500:.1f}% of 3500 (summary {peak_s/1024:.0f}, poller {peak_p/1024:.0f})')
    if rows:
        mx = lambda k: max(num(r, k) for r in rows)
        print(f'  max over arm: memtable offheap K {mx("mt_offheap_all_B")/MiB:.0f} MiB; JDK direct {mx("jdk_direct_used_B")/MiB:.0f} MiB; chunk pool size {mx("bp_chunk_size_B")/MiB:.0f} MiB (overflow max {mx("bp_chunk_overflow_B")/MiB:.0f}); chunk cache {mx("cc_size_B")/MiB:.0f} MiB; blocked_on_alloc {mx("blocked_on_alloc")}')
        full = [r for r in rows if r['heap_used_B']]
        last = full[-1] if full else rows[-1]
        print(f'  last poller row {last["ts"]}: RssAnon {num(last,"rss_anon_kB")/1024:.0f} MiB, cg_anon {num(last,"cg_anon_B")/MiB:.0f}, heap {num(last,"heap_used_B")/MiB:.0f}, direct {num(last,"jdk_direct_used_B")/MiB:.0f}, chunk pool {num(last,"bp_chunk_size_B")/MiB:.0f}, cache {num(last,"cc_size_B")/MiB:.0f} ({last["cc_entries"]} entries), memtable K {num(last,"mt_offheap_all_B")/MiB:.0f} (memks {num(last,"memks_offheap_all_B")/MiB:.0f}), memks writes {last["memks_writes"]}, pending flush {last["pending_flush"]}, blocked {last["blocked_on_alloc"]}')
    fl = rd(os.path.join(d, 'memtable-flush-lines.txt')).splitlines()
    mfl = [l for l in fl if 'memks' in l]
    if mfl:
        pcts = [re.search(r'\((\d+)%\) off-heap', l) for l in mfl]
        print(f'  memks flushes {len(mfl)}; off-heap % at enqueue: {[int(p.group(1)) for p in pcts if p]}')
    for w in ('preload', 'cachefill', 'memburst'):
        t = rd(os.path.join(d, f'stress-{w}.txt'))
        if t:
            g = lambda k: (re.search(k + r'\s*:\s*([^\n\[]+)', t) or [None, '-'])[1].strip()
            print(f'  stress {w}: op rate {g("Op rate")}, partitions {g("Total partitions")}, errors {g("Total errors")}, time {g("Total operation time")}')
    for l in re.findall(r'^(burst (?:start|end) .*|.*node GONE.*|ERROR lines.*|node alive at end)$', S, re.M): print('  ' + l)
    k = rd(os.path.join(d, 'dmesg-this-arm.txt')).strip()
    if k:
        for l in k.splitlines(): print('  dmesg: ' + l[:260])
    # burst decomposition (arms with a burst): pre-burst row vs last full row vs kernel kill record
    mb = re.search(r'^burst start (\S+ \S+)', S, re.M)
    if mb and rows:
        import time, datetime
        t0 = datetime.datetime.strptime(mb.group(1), '%Y-%m-%d %H:%M:%S').timestamp() * 1000
        pre = [r for r in rows if r['heap_used_B'] and int(r['epoch_ms']) <= t0]
        full = [r for r in rows if r['heap_used_B']]
        if pre and full:
            p, l = pre[-1], full[-1]
            f = lambda r, k, s=MiB: num(r, k) / s
            print(f'  pre-burst {p["ts"]}: RssAnon {f(p,"rss_anon_kB",1024):.0f}, direct {f(p,"jdk_direct_used_B"):.0f}, chunk pool {f(p,"bp_chunk_size_B"):.0f}, cache {f(p,"cc_size_B"):.0f}, memtable K {f(p,"mt_offheap_all_B"):.0f}, heap {f(p,"heap_used_B"):.0f}')
            print(f'  last full {l["ts"]} (+{(int(l["epoch_ms"])-t0)/1000:.0f}s): RssAnon {f(l,"rss_anon_kB",1024):.0f}, direct {f(l,"jdk_direct_used_B"):.0f}, chunk pool {f(l,"bp_chunk_size_B"):.0f}, cache {f(l,"cc_size_B"):.0f}, memtable K {f(l,"mt_offheap_all_B"):.0f}, heap {f(l,"heap_used_B"):.0f}, memks writes {l["memks_writes"]}')
            ka = re.search(r'anon-rss:(\d+)kB', rd(os.path.join(d, 'dmesg-block.txt')))
            if ka:
                a = int(ka.group(1)) / 1024
                dd = f(l,"jdk_direct_used_B") - f(p,"jdk_direct_used_B")
                print(f'  kill anon-rss {a:.0f} MiB; RssAnon growth pre-burst -> kill {a - f(p,"rss_anon_kB",1024):.0f} MiB (Δdirect to last row {dd:.0f}); memtable U bound = this + glibc-retained reusable memory (case file)')
