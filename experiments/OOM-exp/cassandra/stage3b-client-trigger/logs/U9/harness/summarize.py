#!/usr/bin/env python3
"""U9 per-lifetime summary: summarize.py <run dir> [...]
One block per lifetime: result.txt, merged row at the endpoint (last nodetool compactionstats 'completed' bytes of the
ks tables / mean row size from the pre-compaction listing), peak heap used (jcmd GC.heap_info samples), peak G1
humongous regions x region size (default GC log, heap*=trace), baseline used, hprof U9 line, first DataOutputBuffer stack."""
import glob, os, re, sys

def mib(v, u):
    return float(v) * {'K': 1 / 1024, 'M': 1, 'G': 1024}[u]

for rd in sys.argv[1:]:
    res = open(os.path.join(rd, 'result.txt')).read() if os.path.exists(os.path.join(rd, 'result.txt')) else ''
    print(f'=== {os.path.basename(rd)}')
    print(res.strip())
    kv = dict(re.findall(r'^(\w+)=(\S+)', res, re.M))
    R = int(kv.get('R', '0'))
    # mean row size from the pre listing (Data.db of all sstables of t1)
    data = 0
    for f in glob.glob(os.path.join(rd, 'listing-pre-*.txt')):
        for line in open(f):
            if line.rstrip().endswith('-Data.db'):
                data += int(line.split()[4])
    ntab = len(glob.glob(os.path.join(rd, 'listing-pre-*.txt'))) or 1
    row = data / (R * ntab) if R and data else 65660
    # last compactionstats reading
    last = {}; lastt = None
    if os.path.exists(os.path.join(rd, 'cstats.log')):
        blk = None
        for line in open(os.path.join(rd, 'cstats.log')):
            if line.startswith('=== '):
                blk = float(line.split()[1]); continue
            m = re.search(r'\bks\s+(t\d)\s+(\d+)\s+(\d+)\s+bytes', line)
            if m:
                last[m.group(1)] = (int(m.group(2)), int(m.group(3)), blk); lastt = blk
    for t, (c, tot, ts) in sorted(last.items()):
        print(f'last_cstats {t}: completed={c} total={tot} ({100*c/tot:.1f}%) at {ts:.0f} -> merged row ~ {c/row:.0f} (row {row:.0f} B)')
    # heap samples
    peak = 0; base = None
    if os.path.exists(os.path.join(rd, 'heap.csv')):
        for line in open(os.path.join(rd, 'heap.csv')):
            m = re.search(r'used (\d+)K', line)
            if m: peak = max(peak, int(m.group(1)) / 1024)
    b = open(os.path.join(rd, 'baseline.txt')).read() if os.path.exists(os.path.join(rd, 'baseline.txt')) else ''
    m = re.search(r'total (\d+)K, used (\d+)K', b)
    if m: base = int(m.group(2)) / 1024
    # humongous
    hum = 0; reg = 16; heap_after = []
    for f in sorted(glob.glob(os.path.join(rd, 'logs', 'gc.log*'))):
        for line in open(f, errors='replace'):
            m = re.search(r'Heap Region Size: (\d+)M', line)
            if m: reg = int(m.group(1))
            m = re.search(r'Humongous regions: (\d+)->(\d+)', line)
            if m: hum = max(hum, int(m.group(1)), int(m.group(2)))
    print(f'baseline_used={base and round(base)} MiB  peak_sampled_used={peak:.0f} MiB  peak_humongous={hum} regions x {reg} MiB = {hum*reg} MiB')
    for name in ('hprofhist.txt',):
        p = os.path.join(rd, name)
        if os.path.exists(p):
            for line in open(p):
                if line.startswith('U9') or line.startswith('total shallow') or 'DataOutputBuffer' in line:
                    print('hprof: ' + line.rstrip())
    p = os.path.join(rd, 'hprofstacks.txt')
    if os.path.exists(p):
        lines = open(p).read().split('--- thread')
        if len(lines) > 1:
            print('stack (first trace with DataOutputBuffer):' + ('\n'.join(('--- thread' + lines[1]).splitlines()[:40])))
    p = os.path.join(rd, 'gcwin.txt')
    if os.path.exists(p): print('gcwin: ' + open(p).read().strip())
