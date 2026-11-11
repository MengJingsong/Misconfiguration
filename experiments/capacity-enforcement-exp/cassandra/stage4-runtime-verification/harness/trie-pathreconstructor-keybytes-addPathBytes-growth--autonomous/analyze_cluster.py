#!/usr/bin/env python3
"""Cluster-tier analysis against B3f / B3g. Usage: analyze_cluster.py <cluster-dir>  (one subdirectory per label)"""
import sys, os, re, json, glob
run = sys.argv[1]
def parse_stats(s):
    d = dict(re.findall(r'([\w.$]+)=(\d+)', s or '')); return {k: int(v) for k, v in d.items()}
def iterators(path):
    """Group growth events into iterator chains: a chain starts at oldCap == 32 (initial capacity) and each next event has oldCap == previous newCap with the same identity."""
    chains = []; cur = {}
    for l in open(path):
        seq, ts, phase, site, cls, ident, old, need, new = l.strip().split(',')
        old, need, new = int(old), int(need), int(new)
        c = cur.get(ident)
        if old == 32 or c is None or c['cap'] != old:
            c = dict(ident=ident, phase=phase, cls=cls, sites=[], caps=[], cap=32); chains.append(c); cur[ident] = c
        c['sites'].append(int(site)); c['caps'].append(new); c['cap'] = new
    return chains
rows = []
for d in sorted(glob.glob(run + '/*/result.json')):
    r = json.load(open(d)); lab = r['label']; L = os.path.dirname(d)
    ch = iterators(L + '/tp-events.txt')
    st = parse_stats(r['stats_final']); base = parse_stats(r['stats_baseline'])
    ctors = sum(v for k, v in st.items() if k.startswith('ctor.')); bctors = sum(v for k, v in base.items() if k.startswith('ctor.'))
    samples = [int(s['onheap']) for s in r['samples'] if str(s.get('onheap', '')).isdigit()]
    fl = [l for l in r['flush_log'] if 'Enqueuing flush of ks.t,' in l]
    usage = []   # on-heap Usage (MiB) of ks.t memtables at each flush enqueue (exact, from the flush line)
    for l in fl:
        m = re.search(r'Usage: ([\d.]+)(\w+) \(\d+%\) on-heap', l)
        if m: usage.append(float(m.group(1)) * {'B': 1 / 1048576.0, 'KiB': 1 / 1024.0, 'MiB': 1.0, 'GiB': 1024.0}[m.group(2)])
    lim = sum('MEMTABLE_LIMIT' in l for l in fl); usr = sum('USER_FORCED' in l for l in fl)
    caps = [c['cap'] for c in ch]; tot = sum(sum(c['caps']) for c in ch)
    byphase = {}
    for c in ch: byphase.setdefault(c['phase'], []).append(c['cap'])
    acc = {a['tag']: a for a in r['accounting']}
    rows.append(dict(label=lab, kind=r['kind'], hs=r['heap_space'], write=r['write'], scan=r['scan'], iters=ctors, base_iters=bctors, base_events=base.get('events'), growth_chains=len(ch), caps=caps, byphase=byphase, scratch_total=tot,
                     copies=st.get('copies'), usage=usage, copybytes=st.get('copybytes'), peak_onheap=max(samples) if samples else None, n_samples=len(samples), flush_limit=lim, flush_user=usr,
                     before_scan=acc['before_scan'], errors=r['errors'], jfr=r.get('jfr'), events=st.get('events')))
print('%-8s %-6s %9s %5s %6s %-34s %12s %13s %7s %7s %12s' % ('label', 'hs', 'rows', 'iters', 'chains', 'final caps per phase (min..max,n)', 'scratch(B)', 'peak onheap', 'limitfl', 'userfl', 'copybytes'))
for r in rows:
    ph = '; '.join('%s:%d..%d,n=%d' % (p, min(v), max(v), len(v)) for p, v in sorted(r['byphase'].items())) or 'none'
    print('%-8s %-6s %9d %5d %6d %-34s %12d %13s %7d %7d %12s' % (r['label'], r['hs'], r['write']['rows'], r['iters'], r['growth_chains'], ph, r['scratch_total'], r['peak_onheap'], r['flush_limit'], r['flush_user'], r['copybytes']))
ok = True
def chk(c, m):
    global ok
    print(('OK   ' if c else 'FAIL ') + m); ok = ok and c
for r in rows:
    chk(r['write']['err'] == 0 and r['write']['ok'] == r['write']['rows'], '%s: all %d writes succeeded' % (r['label'], r['write']['rows']))
    chk(r['scan']['err'] is None and r['scan']['rows'] > 0, '%s: scan ran, %d rows read' % (r['label'], r['scan']['rows']))
    chk(r['base_events'] == 0, '%s: idle baseline had 0 growth events (ctors %d)' % (r['label'], r['base_iters']))
    chk(r['errors']['log_ERROR_lines'] == 0, '%s: no ERROR lines in system.log' % r['label'])
    chk(r['iters'] >= 2, '%s: at least the flush made iterators (%d)' % (r['label'], r['iters']))
A = [r for r in rows if r['kind'] == 'A']; B = [r for r in rows if r['kind'] == 'B']
for r in A: chk(r['growth_chains'] == 0, '%s (Run A): no growth event at all, so every iterator stayed at capacity 32 (%d iterators)' % (r['label'], r['iters']))
bc = [c for r in B for c in r['caps']]
if bc: chk(min(bc) >= 60010 - 20 and max(bc) <= 2 * 60030 + 16, 'Run B final capacities all within [~path, 2 x path + 16]: min %d max %d' % (min(bc), max(bc)))
for hs in sorted({r['hs'] for r in B}):
    v = sorted({c for r in B if r['hs'] == hs for c in r['caps']}); print('     Run B %s distinct final capacities: %s' % (hs, v))
for kind in ('A', 'B'):
    for rep in ('r1', 'r2'):
        a = [r for r in rows if r['kind'] == kind and r['label'].endswith(rep) and r['hs'] == '128MiB']; b = [r for r in rows if r['kind'] == kind and r['label'].endswith(rep) and r['hs'] == '512MiB']
        if a and b:
            a, b = a[0], b[0]
            ua, ub = max(a['usage']), max(b['usage'])
            chk(a['flush_limit'] > b['flush_limit'] and ua < ub, '%s%s control: limit-driven flushes 128MiB=%d > 512MiB=%d; largest memtable at a flush (Usage on flush line) %.1f MiB < %.1f MiB (sampled peaks %d vs %d B are coarse)' % (kind, rep, a['flush_limit'], b['flush_limit'], ua, ub, a['peak_onheap'], b['peak_onheap']))
for r in B:
    per = sorted({sum(c['caps']) for c in iterators(os.path.join(run, r['label'], 'tp-events.txt'))})
    mn = min(r['usage']) if r['usage'] else 0
    print('     %s per-iterator scratch (sum of new capacities): %s B; smallest memtable at a flush %.1f MiB -> largest per-iterator scratch is %.3f %% of it; heap 2048 MiB -> %.4f %%' % (r['label'], per, mn, 100.0 * max(per) / (mn * 1048576) if mn else float('nan'), 100.0 * max(per) / (2048 * 1048576)))
print('ALL OK' if ok else 'SOME FAILED')
