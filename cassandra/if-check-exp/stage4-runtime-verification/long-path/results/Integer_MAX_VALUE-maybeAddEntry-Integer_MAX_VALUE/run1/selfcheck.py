#!/usr/bin/env python3
"""Independent self-check of run 1, Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE (results §5).
usage: selfcheck.py [<run dir>, default ~/stage4-logs/imv/run1]
Uses none of the run script's code. Reads life1/imv.trace (writer, init, refused, built, scan lines), life1/system.log (the refusal
ERROR lines), life1/data-final.txt (`ls -laR` of the data directory: Summary.db and Data.db per table), life1/debug.log (restart),
and armE's trace, logs and listing; compares each with the frozen §9a table (copied below, not recomputed by the run script).
Exit 1 if any check fails."""
import os, re, sys

RUN = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/imv/run1')
# §9a table: table -> (L, K, N, kept, entriesLength, gauge, Summary.db, refusal keysWritten or None, ERROR lines, max skips)
PRED = {
    'c32':  (2147483647, 1000, 41610, 41610, 41942880, 42109320, 42111352, None, 0, 0),
    't8':   (8388608, 1000, 10403, 8322, 8388576, 8421864, 8423896, 8322, 1, 2081),
    't32':  (33554432, 1000, 41610, 33288, 33554304, 33687456, 33689488, 33288, 1, 8322),
    't32a': (33554432, 1000, 33288, 33288, 33554304, 33687456, 33689488, None, 0, 0),
    't32b': (33554432, 1000, 33289, 33288, 33554304, 33687456, 33689488, 33288, 1, 1),
    't32c': (33554432, 1000, 83220, 33288, 33554304, 33687456, 33689488, 33288, 1, 49932),
    't128': (134217728, 1000, 166440, 133152, 134217216, 134749824, 134751856, 133152, 1, 33288),
    'big':  (2147483647, 60000, 40000, 35786, 2147446288, 2147589432, 2147709464, 35786, 1, 4214),
}
fails = 0


def ck(desc, cond, detail=''):
    global fails
    if not cond:
        fails += 1
    print(f'{"ok  " if cond else "FAIL"} {desc}{" — " + detail if detail else ""}')
    return cond


def kv(l):
    return dict(re.findall(r'(\w+)=(\S+)', l))


def listing(path):
    """{(keyspace, table): {filename: size}} from `ls -laR`."""
    out, cur = {}, None
    for l in open(path):
        m = re.match(r'^.*/data/(ks2?)/(\w+)-[0-9a-f]+:$', l.strip())
        if m:
            cur = (m.group(1), m.group(2)); out.setdefault(cur, {})
            continue
        m = re.match(r'^\S+\s+\d+\s+\S+\s+\S+\s+(\d+)\s+\S+\s+\d+\s+\S+\s+(\S+)$', l.strip())
        if m and cur and not l.startswith('d'):
            out[cur][m.group(2)] = int(m.group(1))
    return out


d1 = os.path.join(RUN, 'life1')
tr = [l.strip() for l in open(f'{d1}/imv.trace') if l.strip()]
writers = [(i, kv(l)) for i, l in enumerate(tr) if l.startswith('writer ')]
ls = listing(f'{d1}/data-final.txt')
syslog = open(f'{d1}/system.log').read()
print(f'life1: {len(tr)} trace lines, {len(writers)} writer lines, ERROR lines "Memory capacity of index summary exceeded": '
      f'{syslog.count("Memory capacity of index summary exceeded")}')
n_err_pred = 1 + sum(p[8] for p in PRED.values())        # the probe refuses once too
ck(f'life1: ERROR lines in system.log = refusing tables + the probe ({n_err_pred})', syslog.count('Memory capacity of index summary exceeded') == n_err_pred)
counts = {}
for t, (L, K, N, kept, eL, gauge, sdb, refKW, nerr, maxskip) in PRED.items():
    ws = [(i, w) for i, w in writers if f'/ks/{t}-' in w['path']]
    if not ck(f'{t}: exactly one writer line for its directory', len(ws) == 1, str(len(ws))):
        continue
    i0, w = ws[0]
    nxt = min([i for i, _ in writers if i > i0] or [len(tr)])
    seg = tr[i0:nxt]
    wid = w['id']
    init = [kv(l) for l in tr if l.startswith('init ') and kv(l)['id'] == wid]      # printed before its writer line (built in its constructor)
    ref = [kv(l) for l in seg if l.startswith('refused ') and kv(l)['id'] == wid]
    built = [kv(l) for l in seg if l.startswith('built ') and kv(l)['id'] == wid]
    ck(f'{t}: one init line, expectedKeys = N, interval 1 → 1', len(init) == 1 and int(init[0]['expectedKeys']) == N and init[0]['effective'] == '1')
    ck(f'{t}: built lines present and identical', built and all({k: v for k, v in b.items() if k != 'ms'} == {k: v for k, v in built[0].items() if k != 'ms'} for b in built), str(len(built)))
    if built:
        b = built[0]
        counts[t] = int(b['count'])
        ck(f'{t}: kept {kept}, entriesLength {eL} = capacity, keysWritten N {N}',
           int(b['count']) == kept and int(b['entriesLength']) == eL and int(b['capacity']) == eL and int(b['keysWritten']) == N, str(b))
        ck(f'{t}: entriesLength <= L', int(b['entriesLength']) <= L)
    if refKW is None:
        ck(f'{t}: no refused line', not ref)
    else:
        ck(f'{t}: one refused line at keysWritten {refKW}, length {refKW * (K + 8)}, entry {K + 8}',
           len(ref) == 1 and int(ref[0]['keysWritten']) == refKW and int(ref[0]['length']) == refKW * (K + 8) and int(ref[0]['entry']) == K + 8, str(ref))
    files = ls.get(('ks', t), {})
    sdbs = [v for k, v in files.items() if k.endswith('-Summary.db')]
    dbs = [k for k in files if k.endswith('-Data.db')]
    ck(f'{t}: one Data.db, Summary.db = {sdb}', len(dbs) == 1 and sdbs == [sdb], f'{dbs} {sdbs}')
    # the point reads (9c): ranks 0, k/4, k/2, 3k/4, k-1 (k = min(N, n*)) and the 5 highest, distinct; they are the last scan
    # lines of this table before the next writer line; skips = 0 below n*, r - n* + 1 from n* up
    k = min(N, kept)
    ranks = sorted({r for r in (0, k // 4, k // 2, 3 * k // 4, k - 1)} | set(range(N - 5, N)))
    scans = [kv(l) for l in seg if l.startswith('scan ') and f'/ks/{t}-' in l]
    reads = scans[-len(ranks):]
    skips = sorted(int(r['skips']) for r in reads)
    pred = sorted(0 if r < kept else r - kept + 1 for r in ranks)
    ck(f'{t}: {len(ranks)} point reads found, skips {pred[-5:]} (highest five)', len(reads) == len(ranks) and all(r['found'] == 'true' for r in reads) and skips == pred, str(skips))
if all(t in counts for t in ('t8', 't32', 't128')):
    ck('dose-response: n* 8,322 : 33,288 : 133,152 (1 : 4.000 : 16.000 within one entry)', [counts['t8'], counts['t32'], counts['t128']] == [8322, 33288, 133152],
       f'ratios {counts["t32"] / counts["t8"]:.4f} {counts["t128"] / counts["t8"]:.4f}')
# restart: big loads without a rebuild; reads after the restart (the last 10 scan lines of big in the whole trace)
dbg = open(f'{d1}/debug.log').read()
ck('restart: no "Index summary file is corrupted" line for big', not re.search(r'Index summary file is corrupted.*?/ks/big-', dbg))
reb = [l for l in tr if l.startswith('rebuild ') and '/ks/big-' in l and 'rebuildSummary=true' in l]
ck('restart: no summary rebuild of big in the trace', not reb, str(len(reb)))
big_after = [kv(l) for l in tr if l.startswith('scan ') and '/ks/big-' in l][-10:]
ck('restart: 10 reads of big after the restart found, skips as before', len(big_after) == 10 and all(r['found'] == 'true' for r in big_after)
   and sorted(int(r['skips']) for r in big_after) == sorted([0] * 5 + list(range(4210, 4215))), str(sorted(int(r['skips']) for r in big_after)))

# arm E
dE = os.path.join(RUN, 'armE')
if os.path.isdir(dE):
    trE = [l.strip() for l in open(f'{dE}/imv.trace') if l.strip()]
    lsE = listing(f'{dE}/data-final.txt')
    sysE = open(f'{dE}/system.log').read()
    dbgE = open(f'{dE}/debug.log').read()
    wE = [(i, kv(l)) for i, l in enumerate(trE) if l.startswith('writer ') and '/ks2/' in l]
    for t, N, e, cap, kept in (('e41', 41610, 2, 1363642920, 20805), ('e30', 30000, 1, 1966320000, 30000)):
        ws = [(i, w) for i, w in wE if f'/ks2/{t}-' in w['path']]
        if not ck(f'{t}: one writer line', len(ws) == 1):
            continue
        wid = ws[0][1]['id']
        init = [kv(l) for l in trE if l.startswith('init ') and kv(l)['id'] == wid]
        built = [kv(l) for l in trE if l.startswith('built ') and kv(l)['id'] == wid]
        ck(f'{t}: init effective {e}, entriesCapacity {cap}', init and init[0]['effective'] == str(e) and init[0]['entriesCapacity'] == str(cap), str(init))
        ck(f'{t}: built count {kept}, entriesLength {kept * 1008}', built and int(built[0]['count']) == kept and int(built[0]['entriesLength']) == kept * 1008, str(built[:1]))
    # system.log is the last lifetime's (4b); count WARN lines over the start-up logs kept in the run folder if present
    print(f'armE: WARN "is too low for" lines in the final system.log: {sysE.count("is too low for")}; '
          f'"Index summary file is corrupted" lines in the final debug.log: {dbgE.count("Index summary file is corrupted")}')
    rebs = [l for l in trE if l.startswith('rebuild ') and '/ks2/' in l and 'rebuildSummary=true' in l]
    print('armE rebuild lines:', [re.sub(r' ms=\d+', '', l)[-120:] for l in rebs])
    ck('armE: e41 rebuilt twice (lifetime 3 with the property, lifetime 4 without), e30 never',
       sum(1 for l in rebs if '/ks2/e41-' in l) == 2 and not any('/ks2/e30-' in l for l in rebs))
print(f'\n{fails} check(s) failed')
sys.exit(1 if fails else 0)
