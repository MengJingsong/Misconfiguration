#!/usr/bin/env python3
"""Unit-tier analyzer of file_cache_size-chunkcache-weightedsize--autonomous.
usage: unit-analyze.py <dir with unit-32.log unit-33.log unit-64.log unit-128.log unit-256.log unit-probe.log>
The test's printf output reaches the junit log split into fragments (one SubstituteLogger line per write); this joins the
fragments and re-splits on 'O05 ', then checks every B2f prediction and B2g row (thresholds as frozen; AM7 EVID line)."""
import re, sys, os
D = sys.argv[1]
CHUNK = 65536
MiB = 1 << 20

def records(path):
    frags = []
    for ln in open(path, errors='replace'):
        m = re.search(r'SubstituteLogger\.java:\d+ - (.*)$', ln.rstrip('\n'))
        if m:
            frags.append(m.group(1))
    text = ''.join(frags)
    out = []
    for part in re.split(r'(?=O05 )', text):
        if not part.startswith('O05 '):
            continue
        kind = part.split()[1]
        kv = {k: (int(v) if re.fullmatch(r'-?\d+', v) else v) for k, v in re.findall(r'(\w+)=([^\s]+)', part)}
        out.append((kind.split('=')[0], kv))
    return out

res = {}
for name in ('32', '33', '64', '128', '256', 'probe'):
    p = os.path.join(D, f'unit-{name}.log')
    res[name] = records(p)
    ok = 'Tests run: 1, Failures: 0, Errors: 0' in open(p).read()
    print(f'== unit-{name}.log  junit ok={ok}  records={len(res[name])}')

def final(name):
    return next(kv for k, kv in res[name] if k == 'FINAL')
def evid(name):
    return next(kv for k, kv in res[name] if k == 'EVID')
def series(name):
    return [kv for k, kv in res[name] if k.startswith('pass')]

checks = []
def check(label, cond, detail):
    checks.append((label, cond)); print(f'EXPECTED {"PASS" if cond else "FAIL"}: {label} -- {detail}')

# N = 32: gate
inst = [kv for k, kv in res['32'] if k.startswith('instance')]
txt32 = open(os.path.join(D, 'unit-32.log')).read()
check('N=32 prints instance=null (gate, B2h)', 'O05 instance=null' in txt32, 'O05 instance=null present' if 'O05 instance=null' in txt32 else 'absent')

rows = []
for n, cap_pred, ent_pred in ((33, 1048576, 16), (64, 33554432, 512), (128, 100663296, 1536), (256, 234881024, 3584)):
    f = final(str(n)); e = evid(str(n)); s = series(str(n))
    print(f'N={n}: FINAL {f}; EVID {e}')
    w0 = [x['w'] for x in s if x['pass'] == 0]; w1 = [x['w'] for x in s if x['pass'] == 1]
    print(f'   pass0 sampled w (every 256 chunks): {w0}')
    print(f'   pass1 sampled w: {w1}')
    print(f'   pass0/1 sampled poolSize max {max(x["poolSize"] for x in s)} overflow max {max(x["overflow"] for x in s)}')
    check(f'N={n} cacheSize == {cap_pred}', f['cacheSize'] == cap_pred, f"cacheSize={f['cacheSize']}")
    check(f'N={n} maxW <= cacheSize + 65536', f['maxW'] <= cap_pred + CHUNK, f"maxW={f['maxW']}")
    check(f'N={n} final entries <= {ent_pred}', f['entries'] <= ent_pred, f"entries={f['entries']}")
    check(f'N={n} final w within 10% of cacheSize', abs(f['w'] - cap_pred) <= 0.10 * cap_pred, f"w={f['w']} ({f['w']/cap_pred:.3f} of cap)")
    if n == 64:
        check('N=64 final w >= 0.9 x cap', f['w'] >= 0.9 * cap_pred, f"w={f['w']}")
    check(f'N={n} poolSize <= {n} MiB (FINAL)', f['poolSize'] <= n * MiB, f"poolSize={f['poolSize']} ({f['poolSize']/MiB:.1f} MiB)")
    check(f'N={n} pool sampled max <= {n} MiB', max(x['poolSize'] for x in s) <= n * MiB, f"max sampled poolSize={max(x['poolSize'] for x in s)}")
    check(f'N={n} overflow 0 (FINAL and every sample)', f['overflow'] == 0 and all(x['overflow'] == 0 for x in s), f"final overflow={f['overflow']}")
    check(f'N={n} not "maxW grows with file size" (Refuted row)', f['maxW'] < 2 * cap_pred + 4 * CHUNK, f"maxW={f['maxW']}, file weight per pass {(2*n+64)*MiB}")
    check(f'N={n} first pass rises from 0 toward the cap (positive control)', w0[0] <= CHUNK and max(w0) >= 0.9 * cap_pred, f"first sample w={w0[0]}, max pass-0 sample {max(w0)}")
    check(f'N={n} second pass stays at the cap (flat)', all(x <= cap_pred + CHUNK for x in w1) and min(w1) >= 0.9 * cap_pred, f"pass-1 w range {min(w1)}..{max(w1)}")
    chunks = (2 * n + 64) * 16
    # AM7: loads (misses) far above the final entry count; every load beyond the final entries was removed from the cache.
    # (A first draft of this check also required misses >= 2 x chunks per pass and > 10 x entries; that was an analyzer
    #  threshold, not a frozen row, and is reported separately below as INFO.)
    check(f'N={n} EVID: removed entries = misses - final entries > 2 x entries (eviction ran; AM7)', e['misses'] - f['entries'] > 2 * f['entries'], f"misses={e['misses']} requests={e['requests']} removed>={e['misses']-f['entries']} entries={f['entries']}")
    print(f"INFO N={n}: rebuffer calls = {2*chunks}; requests = {e['requests']} ({e['requests']/(2*chunks):.2f} per rebuffer); misses/entries = {e['misses']/f['entries']:.1f}")
    rows.append((n, f['cacheSize'], f['maxW'], f['w'], f['entries'], f['poolSize'], f['overflow'], e['misses'], e['requests']))

# probe
f = final('probe'); e = evid('probe'); s = series('probe')
print(f'PROBE: FINAL {f}; EVID {e}')
print(f'   probe pass0 samples (i, w, poolSize, overflow): {[(x["i"], x["w"], x["poolSize"], x["overflow"]) for x in s if x["pass"]==0]}')
print(f'   probe pass1 samples (i, w, poolSize, overflow): {[(x["i"], x["w"], x["poolSize"], x["overflow"]) for x in s if x["pass"]==1]}')
cap = 33554432
check('probe maxW <= 32 MiB + 65536', f['maxW'] <= cap + CHUNK, f"maxW={f['maxW']}")
check('probe held == 1024', f['held'] == 1024, f"held={f['held']}")
check('probe poolSize reaches 64 MiB pooled (sizeInBytes - overflow >= 64 MiB)', f['poolSize'] - f['overflow'] >= 64 * MiB, f"poolSize={f['poolSize']} overflow={f['overflow']} pooled={f['poolSize']-f['overflow']}")
check('probe overflow > 0', f['overflow'] > 0, f"overflow={f['overflow']}")
check('probe overflow about >= 32 MiB while held (B2f probe magnitude)', f['overflow'] >= 32 * MiB, f"overflow={f['overflow']} ({f['overflow']/MiB:.1f} MiB)")

print('\nTABLE n cacheSize maxW w entries poolSize overflow misses requests')
for r in rows: print('TABLE', *r)
print(f'\nSUMMARY {sum(1 for _, c in checks if c)} PASS, {sum(1 for _, c in checks if not c)} FAIL')
