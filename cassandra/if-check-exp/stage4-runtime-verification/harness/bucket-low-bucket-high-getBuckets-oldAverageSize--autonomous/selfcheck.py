#!/usr/bin/env python3
"""Independent self-check: re-derives the headline numbers from the RAW files by a different route than cluster-analyze.py / unit-analyze.py
(system.log lines instead of compactionhistory; own peak scan of samples.jsonl; tablestats; JUnit XML; readings.txt).  usage: selfcheck.py <run1 dir>"""
import sys, os, re, json, glob
R = sys.argv[1]; C = R + '/cluster'
def mib(txt):
    m = re.match(r'([\d.,]+)\s*(B|KiB|MiB|GiB)', txt); v = float(m.group(1).replace(',', ''))
    return v * {'B': 1, 'KiB': 1024, 'MiB': 1 << 20, 'GiB': 1 << 30}[m.group(2)]
out = {}
for a in ('n', 'd', 'w', 'wc'):
    d = f'{C}/{a}'
    log = open(d + '/logs/system.log').read().splitlines()
    comp = []
    for l in log:
        m = re.search(r'Compacted \(([0-9a-f-]+)\) (\d+) sstables to \[(.*?)\].*?\.\s+([\d.,]+ ?\w+) to ([\d.,]+ ?\w+) \(', l)
        if m and '/ks/standard1-' in m.group(3): comp.append((int(m.group(2)), mib(m.group(4)), mib(m.group(5))))
    tx = open(d + '/tablestats-pre.txt').read()
    live = int(re.search(r'Space used \(live\): (\d+)', tx).group(1))
    S = [json.loads(l) for l in open(d + '/samples.jsonl')]
    S = [s for s in S if 'data' in s]
    first_compact = next(s for s in S if s['phase'] == 'compact')
    base = first_compact['data']
    pk = max(s['data'] for s in S if s['phase'] in ('compact', 'hold')) - base
    pe = json.load(open(d + '/phase-end.json'))
    left = [l for l in open(d + '/exit.txt')]
    out[a] = dict(compactions=[(n, round(i / 1e6, 1), round(o / 1e6, 1)) for n, i, o in comp], live_pre_MB=round(live / 1e6, 1), base_data_MB=round(base / 1e6, 1),
                  peak_extra_MB=round(pk / 1e6, 1), peak_over_T=round(pk / base, 3), end_files=pe['end']['files'], exit=left[0].strip())
    print(a, out[a])
print('unit XML:', [ (os.path.basename(f), re.search(r'tests="(\d+)"', open(f).read()).group(1), re.search(r'failures="(\d+)"', open(f).read()).group(1), re.search(r'errors="(\d+)"', open(f).read()).group(1)) for f in glob.glob(R + '/unit/TEST-*.xml')])
