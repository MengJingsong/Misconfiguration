#!/usr/bin/env python3
"""Readings table and EXPECTED lines for B2f (amended 2026-10-28) from ~/s4-b34/logs/maxblock/unit/<label>/*.out.   usage: analyze_unit.py <unit-dir> [out-file]"""
import glob, os, re, sys

d = sys.argv[1]
out = open(sys.argv[2], 'w') if len(sys.argv) > 2 else sys.stdout
fails = 0


def kv(line):
    return dict(re.findall(r'(\w+)=("[^"]*"|\S+)', line))


rows = {}
for f in sorted(glob.glob(d + '/*.out')):
    tag = os.path.basename(f)[:-4]
    r = {}
    for l in open(f, errors='replace'):
        if l.startswith('STAGE4 '):
            r[l.split()[1]] = dict(kv(l), _raw=l)
    rows[tag] = r


def P(s):
    print(s, file=out)


def expect(name, cond, detail=''):
    global fails
    P(f'EXPECTED {name}: {"OK" if cond else "MISMATCH"} {detail}')
    if not cond:
        fails += 1


SHIFT = {64: 6, 128: 7, 16384: 14, 1048576: 20, 67108864: 26, 134217728: 27, 268435456: 28}
for arm, maxb in (('stock', 134217728), ('patched', 268435456)):
    for rep in ('1', '2', '3'):
        for bs in (32, 96, 64, 128, 16384, 1048576, 67108864, 134217728, 268435456):
            ok_range = 64 <= bs <= maxb
            pow2 = (bs & (bs - 1)) == 0
            for kind in ('plain', 'mono'):
                r = rows.get(f'{arm}-r{rep}-writer_{kind}_{bs}_{arm}')
                if r is None:
                    expect(f'{arm} r{rep} writer {kind} {bs} present', False); continue
                if ok_range and pow2:
                    a = r.get('writer-accepted')
                    expect(f'{arm} r{rep} {kind} {bs}: accepted, long[] = 8bs+16 (ctorAlloc in [8bs+16, 8bs+16+2000]), length == bs',
                           bool(a) and int(a['blockValuesLen']) == bs and 8 * bs + 16 <= int(a['ctorAlloc']) <= 8 * bs + 16 + 2000, f"{a and (a['ctorAlloc'], a['blockValuesLen'])}")
                else:
                    j = r.get('writer-rejected')
                    want = 'power of two' if (ok_range and not pow2) else 'must be >= 64'
                    expect(f'{arm} r{rep} {kind} {bs}: IllegalArgumentException with the {want} message and no long[] ({8 * bs} B) allocated',
                           bool(j) and want in j['message'] and int(j['ctorAlloc']) < 100000, f"{j and (j['message'], j['ctorAlloc'])}")
            for bsx in (bs,):
                c = rows.get(f'{arm}-r{rep}-check_{bsx}')
                if c is not None and 'check' in c:
                    k = c['check']
                    if ok_range and pow2:
                        expect(f'{arm} r{rep} check {bsx}: returns shift {SHIFT.get(bsx)}', ' accepted ' in k['_raw'] and int(k['shift']) == SHIFT[bsx], str(k.get('shift')))
                    else:
                        expect(f'{arm} r{rep} check {bsx}: rejected', ' rejected ' in k['_raw'], k.get('message', ''))
# stock vs patched at the production sizes: identical allocation
for kind in ('plain', 'mono'):
    for bs in (128, 16384):
        for rep in ('1', '2', '3'):
            s = rows[f'stock-r{rep}-writer_{kind}_{bs}_stock']; p = rows[f'patched-r{rep}-writer_{kind}_{bs}_patched']
            expect(f'{kind} {bs} r{rep}: stock and MAX_BLOCK_SIZE=2^28 builds allocate the same (ctorAlloc exactly; total allocation within 1 %, the noise between repetitions of one arm)',
                   s['writer-accepted']['ctorAlloc'] == p['writer-accepted']['ctorAlloc'] and abs(int(s['writer-wrote']['totalAlloc']) - int(p['writer-wrote']['totalAlloc'])) <= 0.01 * int(s['writer-wrote']['totalAlloc']) and s['writer-wrote']['flushes'] == p['writer-wrote']['flushes'],
                   f"stock {s['writer-accepted']['ctorAlloc']}/{s['writer-wrote']['totalAlloc']} patched {p['writer-accepted']['ctorAlloc']}/{p['writer-wrote']['totalAlloc']}")
# the positive control pair
a27 = rows['stock-r1-writer_plain_134217728_stock'].get('writer-accepted'); r28 = rows['stock-r1-writer_plain_268435456_stock'].get('writer-rejected')
expect('control pair (stock): 2^27 accepted with ~1 GiB, 2^28 rejected with no large allocation', bool(a27) and int(a27['ctorAlloc']) >= 1 << 30 and bool(r28) and int(r28['ctorAlloc']) < 100000,
       f"{a27 and a27['ctorAlloc']} / {r28 and r28['ctorAlloc']}")
a28 = rows['patched-r1-writer_plain_268435456_patched'].get('writer-accepted')
expect('patched bound: 2^28 accepted with ~2 GiB', bool(a28) and int(a28['ctorAlloc']) >= 2 << 30, str(a28 and a28['ctorAlloc']))
# linear in blockSize
lin = [(bs, int(rows[f'stock-r1-writer_plain_{bs}_stock']['writer-accepted']['ctorAlloc'])) for bs in (64, 128, 16384, 1048576, 67108864, 134217728)]
expect('allocation linear in blockSize (alloc / bs within 8.0 .. 8.2 for bs >= 16384)', all(8.0 <= a / b <= 8.2 for b, a in lin if b >= 16384), str([(b, round(a / b, 4)) for b, a in lin]))
# reader
for arm in ('stock', 'patched'):
    for rep in ('1', '2', '3'):
        for kind in ('plain', 'mono'):
            g = lambda bs: rows[f'{arm}-r{rep}-reader_{kind}_{bs}_1000000000']['reader']
            bad = g(99)
            expect(f'{arm} r{rep} {kind} reader forged 99: rejected before any numBlocks array (alloc < 1 MB: the exception only)', 'IllegalArgumentException' in bad['outcome'] and int(bad['alloc']) < 1_000_000, f"alloc={bad['alloc']}")
            big = g(268435456)
            if arm == 'stock':
                expect(f'{arm} r{rep} {kind} reader forged 2^28: rejected before any numBlocks array (alloc < 1 MB)', 'IllegalArgumentException' in big['outcome'] and int(big['alloc']) < 1_000_000, f"{big['outcome']} alloc={big['alloc']}")
            else:
                expect(f'{arm} r{rep} {kind} reader forged 2^28 passes the raised check', 'IllegalArgumentException' not in big['outcome'], big['outcome'])
            ok = g(64)
            expect(f'{arm} r{rep} {kind} reader forged 64 (valueCount 1e9, 15.6M blocks): check passes, then arrays of ~15.6M entries are allocated (> 50 MB)', 'IllegalArgumentException' not in ok['outcome'] and int(ok['alloc']) > 50_000_000, f"{ok['outcome']} alloc={ok['alloc']}")
up = [l for l in open(os.path.join(d, 'summary.txt')) if 'upstream' in l]
P('INFO ' + (up[0].strip() if up else 'no upstream line'))
expect('upstream SAICodecUtilsTest passed', bool(up) and 'exit=0' in up[0] and 'Failures: 0, Errors: 0' in up[0])
P(f'SUMMARY mismatches={fails} runs={len(rows)}')
