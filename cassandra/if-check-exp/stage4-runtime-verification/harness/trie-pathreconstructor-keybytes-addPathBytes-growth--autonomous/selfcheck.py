#!/usr/bin/env python3
"""Independent re-parse of the raw files (results section 5). Does not import or reuse analyze_*.py or result.json's derived fields:
it re-reads tp-events.txt, tp-stats.txt, system.log, flush-lines.txt, evidence/ and the unit ant.log directly.
Usage: selfcheck.py <run1-dir>   (contains unit/ and cluster/<label>/)"""
import sys, os, re, glob, json
run = sys.argv[1]
ok = bad = 0
def chk(c, m):
    global ok, bad
    if c: ok += 1
    else: bad += 1
    print(('OK   ' if c else 'BAD  ') + m)
# ---------------- unit: RESULT lines in the raw ant log (the copy of ant.log's grep) against results.csv, then recompute the relations
ul = [re.sub(r'^.*?RESULT,', '', l).strip() for l in open(run + '/unit/result-lines.txt') if 'RESULT,' in l]
cs = [l.strip() for l in open(run + '/unit/results.csv')]
chk(ul == cs and len(cs) == 72, 'unit: results.csv (%d rows) is identical to the RESULT lines of the test run (%d)' % (len(cs), len(ul)))
probes = [re.search(r'PROBE,(\d+),(\d+)', l).groups() for l in open(run + '/unit/result-lines.txt') if 'PROBE,' in l]
chk(len(probes) == 72, 'unit: one PROBE line per cell (%d)' % len(probes))
chk('Tests run: 1, Failures: 0, Errors: 0' in open(run + '/unit/ant-tail.txt').read(), 'unit: JUnit reports Tests run: 1, Failures: 0, Errors: 0')
cells = {}
for l, pr in zip(cs, probes):
    f = l.split(','); kv = {x.split('=')[0]: int(x.split('=')[1]) for x in f[2:]}
    chk_cap = kv['capacity'] == int(pr[1])
    if not chk_cap: chk(False, 'unit: PROBE capacity %s != row capacity %d' % (pr[1], kv['capacity']))
    cells.setdefault((f[0], f[1], kv['L'], kv['N']), []).append(kv['capacity'])
    # the doubling policy: capacity is >= path length and <= 2*path + 16, and 32 when the path fits the initial array
    L = kv['L']
    if kv['N'] > 0 and L <= 32: chk(kv['capacity'] == 32, 'unit: L=%d fits the initial 32-byte array, capacity %d' % (L, kv['capacity']))
    if kv['N'] > 0 and L > 32: chk(L <= kv['capacity'] <= 2 * L + 16 and kv['capacity'] > 32, 'unit: %s L=%d N=%d capacity %d in (32, [L, 2L+16])' % (f[1], L, kv['N'], kv['capacity']))
chk(all(len(set(v)) == 1 and len(v) == 3 for v in cells.values()), 'unit: three identical repeats in each of %d cells' % len(cells))
for L in (16, 1000):
    for b in ('ON_HEAP', 'OFF_HEAP'):
        chk(len({cells[('nsweep', b, L, N)][0] for N in (1, 1000, 100000)}) == 1, 'unit: capacity independent of N at L=%d %s' % (L, b))
chk(all(cells[('lsweep', 'ON_HEAP', L, 1000)] == cells[('lsweep', 'OFF_HEAP', L, 1000)] for L in (16, 1000, 20000, 65535, 131070)), 'unit: ON_HEAP and OFF_HEAP capacities equal at every L')
sz = {}
for l in cs:
    f = l.split(','); kv = {x.split('=')[0]: int(x.split('=')[1]) for x in f[2:]}
    if f[0] == 'nsweep' and f[4] == 'rep=1': sz[(f[1], kv['L'], kv['N'])] = kv['sizeOnHeap'] if f[1] == 'ON_HEAP' else kv['sizeOffHeap']
for L in (16, 1000):
    for b in ('ON_HEAP', 'OFF_HEAP'):
        v = [sz[(b, L, N)] for N in (1, 1000, 100000)]
        chk(v[0] < v[1] < v[2] and v[2] > v[1], 'unit: trie size grows with N at L=%d %s: %s' % (L, b, v))
# ---------------- cluster
labs = sorted(os.path.basename(d) for d in glob.glob(run + '/cluster/*') if os.path.isdir(d))
chk(len(labs) == 8, 'cluster: 8 label directories: %s' % labs)
summary = {}
for lab in labs:
    d = run + '/cluster/' + lab
    kind = lab[0]; hs = re.match(r'[AB](\d+)', lab).group(1)
    cmd = open(d + '/evidence/cmdline.txt').read(); y = open(d + '/evidence/yaml-keys.txt').read()
    chk('-Xms2G' in cmd and '-Xmx2G' in cmd and 'byteman-4.0.20.jar=listener:false' in cmd and 'tp.btm' in cmd, '%s: live command line has -Xms2G -Xmx2G and the Byteman agent with tp.btm' % lab)
    chk(re.search(r'memtable_heap_space: %sMiB' % hs, y) and 'memtable_allocation_type: heap_buffers' in y and 'listen_address: 127.0.41.1' in y and 'native_transport_port: 9143' in y and 'storage_port: 7011' in y, '%s: yaml has heap_space %sMiB, heap_buffers, 127.0.41.1, ports 9143/7011' % (lab, hs))
    chk("memtable = 'trie'" in open(d + '/schema.txt').read() or "'trie'" in open(d + '/schema.txt').read(), '%s: DESCRIBE TABLE shows the trie memtable' % lab)
    sl = open(d + '/system.log', errors='replace').read()
    chk(len(re.findall(r'^ERROR', sl, re.M)) == 0, '%s: no ERROR lines in system.log' % lab)
    # events
    ev = [l.strip().split(',') for l in open(d + '/tp-events.txt') if l.strip()]
    bad_arith = 0
    for e in ev:
        site, old, need, new = int(e[3]), int(e[6]), int(e[7]), int(e[8])
        exp = need * 2 if site == 34 else max(need + 16, 2 * old)
        if exp != new: bad_arith += 1
    chk(bad_arith == 0, '%s: all %d growth events obey the line formula (34: 2*keyPos; 42: max(newPos+16, 2*old))' % (lab, len(ev)))
    st = dict(re.findall(r'([\w.$]+)=(\d+)', open(d + '/tp-stats.txt').read()))
    chk(int(st['events']) == len(ev), '%s: tp-stats events=%s equals lines in tp-events.txt (%d)' % (lab, st['events'], len(ev)))
    # chains: one pass per identity; a new chain starts at oldCap == 32 or when oldCap is not the identity's last new capacity
    byid = {}
    for e in ev:
        ident, old, new, ph, site = e[5], int(e[6]), int(e[8]), e[2], int(e[3])
        lst = byid.setdefault(ident, [])
        if old == 32 or not lst or lst[-1]['caps'][-1] != old: lst.append(dict(ph=ph, caps=[new]))
        else: lst[-1]['caps'].append(new)
    ch = [c for v in byid.values() for c in v]
    finals = sorted(c['caps'][-1] for c in ch)
    flog = [l for l in open(d + '/flush-lines.txt') if 'Enqueuing flush of ks.t,' in l]
    lim = sum('Reason: MEMTABLE_LIMIT' in l for l in flog); usr = sum('Reason: USER_FORCED' in l for l in flog)
    syslim = len(re.findall(r'Enqueuing flush of ks\.t, Reason: MEMTABLE_LIMIT', sl)); sysusr = len(re.findall(r'Enqueuing flush of ks\.t, Reason: USER_FORCED', sl))
    chk((lim, usr) == (syslim, sysusr), '%s: flush-lines.txt (%d limit, %d user) matches system.log (%d, %d)' % (lab, lim, usr, syslim, sysusr))
    res = json.load(open(d + '/result.json'))
    peak = max(int(s['onheap']) for s in res['samples'] if str(s.get('onheap', '')).isdigit())
    ctors = sum(int(v) for k, v in st.items() if k.startswith('ctor.'))
    base = dict(re.findall(r'([\w.$]+)=(\d+)', res['stats_baseline'])); 
    chk(int(base['events']) == 0, '%s: idle baseline (before any write) had 0 growth events' % lab)
    chk(res['write']['err'] == 0 and res['write']['ok'] == res['write']['rows'], '%s: %d of %d writes ok, 0 errors' % (lab, res['write']['ok'], res['write']['rows']))
    chk(res['scan']['err'] is None and res['scan']['rows'] == res['write']['rows'] or res['scan']['rows'] > 0 and res['scan']['err'] is None, '%s: scan read %d rows' % (lab, res['scan']['rows']))
    if kind == 'A':
        chk(len(ev) == 0, '%s (Run A): zero growth events, so every one of %d reconstructors stayed at capacity 32' % (lab, ctors))
    else:
        chk(len(ch) >= 1 and all(60000 <= f <= 2 * 60030 + 16 for f in finals), '%s (Run B): %d growing iterators, final capacities %s' % (lab, len(ch), sorted(set(finals))))
    summary[lab] = dict(limit=lim, user=usr, peak=peak, ctors=ctors, chains=len(ch), finals=sorted(set(finals)), total=sum(sum(c['caps']) for c in ch))
    # limit flush usage vs heap_space/3
    us = []
    for l in flog:
        m = re.search(r'Reason: MEMTABLE_LIMIT, Usage: ([\d.]+)(\w+)', l)
        if m: us.append(float(m.group(1)) * {'MiB': 1.0, 'KiB': 1 / 1024, 'GiB': 1024.0}.get(m.group(2), 0))
    if us: chk(all(0.25 * int(hs) <= u <= 0.5 * int(hs) for u in us), '%s: limit-flush usage MiB %s within [hs/4, hs/2] of %s MiB (threshold hs/3)' % (lab, sorted(set(round(u, 1) for u in us)), hs))
for kind in 'AB':
    for rep in ('r1', 'r2'):
        a, b = summary.get('%s128%s' % (kind, rep)), summary.get('%s512%s' % (kind, rep))
        if a and b: chk(a['limit'] > b['limit'] and a['peak'] < b['peak'], '%s%s known-cap control moves: limit flushes %d > %d, peak on-heap %d < %d' % (kind, rep, a['limit'], b['limit'], a['peak'], b['peak']))
print(json.dumps(summary, indent=1))
print('selfcheck: %d OK, %d BAD' % (ok, bad))
sys.exit(1 if bad else 0)
