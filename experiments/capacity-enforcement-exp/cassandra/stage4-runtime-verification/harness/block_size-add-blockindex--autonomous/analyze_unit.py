#!/usr/bin/env python3
"""Reads ~/s4-b34/logs/blockindex/unit/<label>/*.out and prints the readings table and EXPECTED lines for B2f (amended 2026-10-28).
usage: analyze_unit.py <unit-dir> [out-file]"""
import glob, os, re, sys

d = sys.argv[1]
out = open(sys.argv[2], 'w') if len(sys.argv) > 2 else sys.stdout
fails = 0


def kv(line):
    return dict(re.findall(r'(\w+)=("[^"]*"|\S+)', line))


rows = {}
for f in sorted(glob.glob(d + '/*.out')):
    tag = os.path.basename(f)[:-4]
    r = {'exit_ok': True}
    for l in open(f, errors='replace'):
        if l.startswith('STAGE4 '):
            k = l.split()[1]
            r[k] = kv(l)
    rows[tag] = r


def P(s):
    print(s, file=out)


def expect(name, cond, detail=''):
    global fails
    P(f'EXPECTED {name}: {"OK" if cond else "MISMATCH"} {detail}')
    if not cond:
        fails += 1


P('== readings: kind bs N | ctorAlloc blockValuesLen maxBlockIndex flushes(expected) metaBytes bytesOut J_bytes_delta(after adds)')
for tag, r in rows.items():
    if 'finish' in r and tag.endswith('r1'):
        c, a, f = r['ctor'], r['adds'], r['finish']
        P(f"{c['kind']:5} bs={c['bs']:>9} N={c['N']:>10} | ctorAlloc={c['ctorAlloc']:>9} len={c['blockValuesLen']:>9} maxIdx={a['maxBlockIndex']:>9} "
          f"flushes={f['flushes']}({f['expectedFlushes']}) meta={f['metaBytes']} out={f['bytesOut']} Jdelta={a['J_bytes_delta']}")
reps = sorted({t.rsplit('-r', 1)[1] for t in rows if '-r' in t and t.rsplit('-r', 1)[1].isdigit()})
for tag, r in rows.items():
    if 'finish' in r:
        c, a, f = r['ctor'], r['adds'], r['finish']
        bs, n = int(c['bs']), int(c['N'])
        expect(f'{tag} blockValues.length == blockSize', int(c['blockValuesLen']) == bs, f"len={c['blockValuesLen']}")
        expect(f'{tag} blockIndex never exceeds blockSize', int(a['maxBlockIndex']) <= bs, f"max={a['maxBlockIndex']}")
        expect(f'{tag} flush count == ceil(N/bs)', int(f['flushes']) == (n + bs - 1) // bs, f"{f['flushes']} vs {(n + bs - 1) // bs}")
        lo, hi = 8 * bs + 16, 8 * bs + 16 + 2000
        expect(f'{tag} constructor allocation in [8bs+16, 8bs+16+2000]', lo <= int(c['ctorAlloc']) <= hi, f"{c['ctorAlloc']}")
        expect(f'{tag} retained long[] growth after N adds in [8bs+16, 8bs+16+200] (flat in N)', lo <= int(a['J_bytes_delta']) <= lo + 200, f"{a['J_bytes_delta']}")
    if 'invalid' in r:
        i = r['invalid']; bs = int(i['bs'])
        want = 'power of two' if bs == 100 else 'must be >= 64'
        expect(f'{tag} rejected with the expected message', want in i['message'], i['message'])
        expect(f'{tag} no long[] allocated for the rejected size', int(i['ctorAlloc']) < 8 * 64 + 600000 and int(i['ctorAlloc']) < 2_000_000, f"ctorAlloc={i['ctorAlloc']}")
for kind in ('plain', 'mono'):
    for rep in reps:
        a = rows.get(f'{kind}-128-full-r{rep}'); b = rows.get(f'{kind}-16384-full-r{rep}'); c = rows.get(f'{kind}-1048576-full-r{rep}')
        if a and b and c and 'finish' in a and 'finish' in b and 'finish' in c:
            m = [int(x['finish']['metaBytes']) for x in (a, b, c)]
            expect(f'{kind} r{rep}: metadata bytes fall as blocks get larger (more blocks, more metadata), not capped', m[0] > m[1] > m[2], f'meta bs128/16384/2^20 = {m}')
for tag, r in rows.items():
    if tag.startswith('ctl-') and 'control' in r:
        k = r['control']; n = int(k['N'])
        expect(f'{tag} control long[] grows with N (8 x arr_len)', abs(int(k['J_bytes_delta']) - 8 * int(k['arr_len'])) < 200, f"delta={k['J_bytes_delta']} arr_len={k['arr_len']}")
for kind in ('plain', 'mono'):
    sh = [int(rows[t]['adds']['J_bytes_delta']) for t in rows if t.startswith(f'{kind}-128-short') and 'adds' in rows[t]]
    fu = [int(rows[t]['adds']['J_bytes_delta']) for t in rows if t.startswith(f'{kind}-128-full') and 'adds' in rows[t]]
    if sh and fu:
        expect(f'{kind} bs=128: retained long[] equal for N=127 and N=167,772,160', max(sh) - min(sh + fu) < 100 and max(fu) - min(sh + fu) < 100, f'short {sh} full {fu}')
P(f'SUMMARY mismatches={fails} of {sum(1 for _ in rows)} runs read')
