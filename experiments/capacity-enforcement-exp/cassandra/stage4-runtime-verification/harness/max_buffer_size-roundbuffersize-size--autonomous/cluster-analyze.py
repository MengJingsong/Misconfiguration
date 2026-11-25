# Case B3e/B3f analysis (amendment A5): medians of base / during(compacting only) / after, deltas, per-reader.
import sys, os, statistics
R = sys.argv[1]  # run1 dir
runs = sys.argv[2:]
MiB = 1 << 20
def parse(path):
    d = {}
    if not os.path.exists(path): return d
    for l in open(path):
        f = l.split()
        if len(f) >= 4: d.setdefault(int(f[0]), {})[f[2]] = f[3]
    return d
print('| run | K | n base | n during (compacting) / total | ΔUsedSize | ΔUsed/K | ΔOverflowSize | ΔDirect MemoryUsed | after Used (median) |')
print('|---|---|---|---|---|---|---|---|---|')
for label in runs:
    O = os.path.join(R, 'cluster-' + label)
    K = int(label.split('-k')[1].split('-')[0])
    base, dur, aft = parse(O + '/base.txt'), parse(O + '/during.txt'), parse(O + '/after.txt')
    # harness defect H3: the COMPACTING flag written by cluster-run.sh used a case-sensitive regex that misses
    # "Major compaction p t"; derive it from the raw compactionstats text saved with every during sample.
    import re
    flags, ts = {}, None
    if os.path.exists(O + '/compactionstats.txt'):
        for l in open(O + '/compactionstats.txt'):
            if l.startswith('== '):
                ts = int(l.split()[1]); flags[ts] = 'no'
            elif ts is not None and re.search(r'compaction\s+p\s+t\s+\d+\s+\d+\s+bytes', l, re.I):
                flags[ts] = 'yes'
    for t in dur:
        if t in flags: dur[t]['COMPACTING'] = flags[t]
    def med(d, key, only=None):
        vals = [int(v[key]) for ts, v in d.items() if key in v and v[key].lstrip('-').isdigit() and (only is None or only(v))]
        return (statistics.median(vals), len(vals)) if vals else (None, 0)
    comp = lambda v: v.get('COMPACTING') == 'yes'
    out = {}
    for key in ('UsedSize', 'OverflowSize', 'DirectMemoryUsed'):
        b, nb = med(base, key); d, nd = med(dur, key, comp); a, na = med(aft, key)
        out[key] = (b, d, a, nb, nd)
    ndt = sum(1 for v in dur.values() if 'COMPACTING' in v)
    def dlt(k):
        b, d = out[k][0], out[k][1]
        return None if b is None or d is None else d - b
    du, do, dd = dlt('UsedSize'), dlt('OverflowSize'), dlt('DirectMemoryUsed')
    fmt = lambda x: 'n/a' if x is None else '%d B (%.3f MiB)' % (x, x / MiB)
    print('| %s | %d | %d | %d / %d | %s | %s | %s | %s | %s |' % (label, K, out['UsedSize'][3], out['UsedSize'][4], ndt, fmt(du),
          'n/a' if du is None else '%d B (%.1f KiB)' % (du / K, du / K / 1024), fmt(do), fmt(dd), fmt(out['UsedSize'][2])))
    for key in ('UsedSize', 'OverflowSize', 'DirectMemoryUsed'):
        print('<!-- %s %s: base median %s, during median %s, after median %s -->' % (label, key, out[key][0], out[key][1], out[key][2]))
