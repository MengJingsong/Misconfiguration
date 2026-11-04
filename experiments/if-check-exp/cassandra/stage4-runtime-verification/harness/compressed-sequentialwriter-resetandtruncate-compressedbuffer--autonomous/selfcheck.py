#!/usr/bin/env python3
"""Independent self-check (step 4): re-parses the raw files (unit-readings.txt, the Byteman traces, session logs) without using
cluster-run.py's analysis, and recomputes each frozen prediction (B2f/B3f) from the raw lines.
usage: python3 -I selfcheck.py <logs-dir>     (default ~/s4-cs-logs; the run directory is <logs>/run1)"""
import glob, os, re, sys

L = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/s4-cs-logs')
R = L + '/run1'
res = []


def check(name, ok, detail=''):
    res.append(ok)
    print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + detail if detail else ''))


def bound(n):
    return 4 + n + n // 255 + 16


def kv(line):
    return dict(re.findall(r'(\w+)=(\S+)', line))


# ---- unit tier
rows = [kv(l) for l in open(L + '/unit-readings.txt') if l.startswith('READING')]
for r in rows:
    for k in ('chunk', 'compressedCapBefore', 'compressedCapAfter', 'bufferCap', 'markChunkOffset', 'fileLenBeforeReset', 'fileLenAfterReset', 'posAtMark', 'posAfter'):
        r[k] = int(r[k])
check('unit: 17 cells read', len(rows) == 17, str(len(rows)))
lz = [r for r in rows if r['cell'] == 'lz4']
check('unit: 8 lz4 cells, every chunk x {random, zeros}', sorted((r['chunk'], r['data']) for r in lz) == sorted((c, d) for c in (4096, 16384, 65536, 1048576) for d in ('random', 'zeros')))
check('unit: lz4 capacity before == after == 4+n+n/255+16, same object, direct, buffer == chunk',
      all(r['compressedCapBefore'] == r['compressedCapAfter'] == bound(r['chunk']) and r['sameObject'] == 'true' and r['isDirect'] == 'true' and r['bufferCap'] == r['chunk'] for r in lz))
check('unit: lz4 normal cells passed :233 (file shrank to the mark chunk offset)', all(r['fileLenAfterReset'] == r['markChunkOffset'] < r['fileLenBeforeReset'] for r in lz))
by = {r['chunk']: r['compressedCapBefore'] for r in lz}
check('unit: capacity ratios to 4 KiB: 3.99 / 15.9 / 254.8 and to chunk within 1.0-1.01',
      abs(by[16384] / by[4096] - 3.985) < .01 and abs(by[65536] / by[4096] - 15.93) < .05 and abs(by[1048576] / by[4096] - 254.8) < .5 and all(1.0 < v / c <= 1.01 for c, v in by.items()))
e = [r for r in rows if r['cell'] == 'lz4-early']
check('unit: early-return control: file length unchanged, same object', len(e) == 1 and e[0]['fileLenAfterReset'] == e[0]['fileLenBeforeReset'] and e[0]['sameObject'] == 'true')
mf = [r for r in rows if r['cell'] == 'mock-force']
check('unit: mock-force: before == chunk/2, after == chunk exactly, new object, file shrank',
      len(mf) == 4 and all(r['compressedCapBefore'] == r['chunk'] // 2 and r['compressedCapAfter'] == r['chunk'] and r['sameObject'] == 'false' and r['fileLenAfterReset'] == r['markChunkOffset'] < r['fileLenBeforeReset'] for r in mf))
mr = [r for r in rows if r['cell'] == 'mock-ratio0.5']
check('unit: mock-ratio0.5: before == after == 2 x chunk, same object (no fire)', len(mr) == 4 and all(r['compressedCapBefore'] == r['compressedCapAfter'] == 2 * r['chunk'] and r['sameObject'] == 'true' for r in mr))
check('unit: no assertion failures in the test', 'failures=0' in [l for l in open(L + '/unit-readings.txt') if l.startswith('SUMMARY')][0])

# ---- cluster tier
def trace(path):
    out = []
    for l in open(path, errors='replace'):
        k = l.split(' ', 1)[0]
        if k in ('init', 'reset', 'r2', 'r2f', 'r3', 'closed'):
            d = kv(l.strip()); d['kind'] = k; out.append(d)
    return out


for arm, kb, ntab in (('C4', 4, 1), ('C16', 16, 1), ('C256', 256, 1), ('C1024', 1024, 1), ('W4', 1024, 4)):
    ev = trace(f'{R}/{arm}/cs.trace')
    ks = [e for e in ev if e['kind'] == 'init' and '/data/ks/' in e['path']]
    n = kb * 1024
    check(f'{arm}: {len(ks)} ks writers = {ntab * 4} flush + {ntab} compaction; buffer == {n}; compressed == {bound(n)}; direct',
          len(ks) == ntab * 5 and all(int(e['buffer']) == n and int(e['compressed']) == bound(n) and e['direct'] == 'true' for e in ks))
    check(f'{arm}: no r2 anywhere in the trace', not any(e['kind'] == 'r2' for e in ev))
    if arm == 'W4':
        ms = sorted(int(e['ms']) for e in ks)
        comp = ms[-4:]
        closed = {e['w']: int(e['ms']) for e in ev if e['kind'] == 'closed'}
        cw = [e for e in ks if int(e['ms']) in comp]
        iv = [(int(e['ms']), closed.get(e['w'])) for e in cw]
        check('W4: the 4 compaction writers overlap in time (max init < min cleanup)', all(b is not None for _, b in iv) and max(a for a, _ in iv) < min(b for _, b in iv), str(iv))
ev = trace(f'{R}/U/cs.trace')
check('U: no ks writer constructed (uncompressed)', not any(e['kind'] == 'init' and '/data/ks/' in e['path'] for e in ev))
check('U: the same trace does show system-table writers (the rule was live)', any(e['kind'] == 'init' for e in ev))
for d in sorted(glob.glob(R + '/S[12]-*')):
    t = trace(d + '/cs-scrub.trace')
    name = os.path.basename(d)
    sw = {e['w'] for e in t if e['kind'] == 'init' and '/data/ks/scr' in e['path']}
    r2 = [e for e in t if e['kind'] == 'r2']
    r3 = [e for e in t if e['kind'] == 'r3']
    print(f'  {name}: scrub-output writers {len(sw)}, r2 {len(r2)}, r3 {len(r3)}, r2f {sum(1 for e in t if e["kind"] == "r2f")}')
    if not r2:
        print(f'  {name}: line 247 not reached (sub-step n/a for this offset)')
        continue
    if name.startswith('S1'):
        check(f'{name}: r2 cap == {bound(16384)} >= chunkSize; r3 same identity; no grow',
              all(int(a['compressedCap']) == bound(16384) >= int(a['chunkSize']) and a['id'] == b['id'] and int(b['compressedCap']) == bound(16384) for a, b in zip(r2, r3)) and len(r2) == len(r3))
    else:
        check(f'{name}: forced 64 -> r3 cap == chunkSize exactly, new identity',
              len(r2) == len(r3) and all(int(b['compressedCap']) == int(a['chunkSize']) and a['id'] != b['id'] for a, b in zip(r2, r3)))
print('SELFCHECK', 'ALL PASS' if all(res) else 'FAILURES', sum(res), '/', len(res))
