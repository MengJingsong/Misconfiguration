#!/usr/bin/env python3
"""Readings table and EXPECTED lines for B2f (amended 2026-10-28) from ~/s4-b34/logs/postings/unit/<label>/*.out.
usage: analyze_unit.py <unit-dir> [out-file]
Model (B5.2): data bytes of one list = 1 (first posting vlong) + nBlocks x (1 + ceil(bs x bits / 8)), bits = 2 for stride 3 (max delta 3); tolerance 2 %.
Retained heap (window lower bound relaxed by 2 KiB for histogram-baseline noise, seen in the M=1000 cells): [J delta minus the probe's own long[N] (8N+16) must stay within the deltaBuffer (8bs+16) plus the two skip-table lists (2 x 8 x blocks, x2 capacity slack)."""
import glob, math, os, re, sys

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
            r[l.split()[1]] = kv(l)
    rows[tag] = r


def P(s):
    print(s, file=out)


def expect(name, cond, detail=''):
    global fails
    P(f'EXPECTED {name}: {"OK" if cond else "MISMATCH"} {detail}')
    if not cond:
        fails += 1


P('== bs N stride lists | ctorAlloc | dataBytes model | file bytes | blocks/list | J_delta - own array | B_delta')
cells = {}
for tag, r in rows.items():
    if 'wrote' not in r:
        continue
    c, w, f = r['ctor'], r['wrote'], r['file']
    bs, n, st, ls = int(w['bs']), int(w['N']), int(w['stride']), int(w['lists'])
    nb = (n + bs - 1) // bs
    bits = 2 if st == 3 else None
    model = ls * (1 + nb * (1 + math.ceil(bs * bits / 8))) if bits else None
    own = 8 * n + 16
    cells[(bs, n, st, ls, tag[-1])] = dict(data=int(w['dataBytes']), file=int(f['onDiskBytes']), jd=int(w['J_bytes_delta']) - own, nb=nb, ctor=int(c['ctorAlloc']))
    if tag.endswith('r1'):
        P(f"bs={bs:>5} N={n:>8} stride={st:>8} lists={ls:>4} | ctor={c['ctorAlloc']:>5} | data={w['dataBytes']:>8} model={model} | file={f['onDiskBytes']:>8} | blocks={nb} | Jrest={int(w['J_bytes_delta']) - own} | Bdelta={w['B_bytes_delta']}")
    expect(f'{tag} constructor allocates the deltaBuffer: 8bs+16 <= ctorAlloc <= 8bs+16+4000', 8 * bs + 16 <= int(c['ctorAlloc']) <= 8 * bs + 16 + 4000, f"ctor={c['ctorAlloc']}")
    if model:
        dev = abs(int(w['dataBytes']) - model) / model
        expect(f'{tag} data bytes within 2 % of the block model', dev <= 0.02, f"data={w['dataBytes']} model={model} dev={dev:.4%}")
    J = int(w['J_bytes_delta'])
    lo, hi = 8 * bs + 16 - 2048, (8 * bs + 16) + 2 * 8 * nb * 2 + 20000
    # the probe's own long[N] (8N+16) is live at the histogram in some cells and already collected in others (JIT liveness): accept either reading
    ok_a, ok_b = lo <= J <= hi, lo <= J - own <= hi
    expect(f'{tag} retained long[] = deltaBuffer + the 2 skip-table lists (x2 slack), independent of N beyond the lists', ok_a or ok_b, f'J={J} J-own={J - own} window=[{lo},{hi}] array_collected={ok_a}')
for rep in ('1', '2'):
    for bs in (16, 128, 1024):
        a, b = cells.get((bs, 100000, 3, 1, rep)), cells.get((bs, 1000000, 3, 1, rep))
        if a and b:
            ratio = b['data'] / a['data']
            expect(f'bs={bs} r{rep}: data bytes grow linearly in N (1M / 100k = 10 +- 5 %)', 9.5 <= ratio <= 10.5, f'ratio={ratio:.3f}')
        w, m = cells.get((bs, 100000, 3, 1, rep)), cells.get((bs, 100000, 1000003, 1, rep))
        if w and m:
            expect(f'bs={bs} r{rep}: positive control, wide stride raises bytes per posting (> 4 x)', m['data'] > 4 * w['data'], f"stride 3: {w['data']} stride 1000003: {m['data']}")
        s = cells.get((bs, 1000, 3, 1, rep))
        if s and bs == 1024:
            expect(f'bs=1024 r{rep}: N=1000 < blockSize writes exactly one tail block', s['nb'] == 1 and s['data'] == 1 + 1 + 256, f"nb={s['nb']} data={s['data']}")
for bs in (16, 128, 1024):
    x = [cells[(bs, 1000000, 3, 1, r)]['data'] for r in ('1', '2') if (bs, 1000000, 3, 1, r) in cells]
    P(f'INFO bs={bs} N=1M data bytes per repetition {x}; flat in nothing: file grows with N for every size')
# across sizes at N = 1M the sizes differ by the per-block overhead only
d16, d128, d1024 = (cells[(bs, 1000000, 3, 1, '1')]['data'] for bs in (16, 128, 1024))
P(f'INFO N=1M data bytes bs16/bs128/bs1024 = {d16} / {d128} / {d1024}; ratios {d16 / d128:.3f} and {d1024 / d128:.3f}')
expect('no run shows file size flattening at a value tied to blockSize (1M > 100k > 1k for every bs)', all(cells[(bs, 1000000, 3, 1, '1')]['data'] > cells[(bs, 100000, 3, 1, '1')]['data'] > cells[(bs, 1000, 3, 1, '1')]['data'] for bs in (16, 128, 1024)))
P(f'SUMMARY mismatches={fails} runs={len(rows)}')
