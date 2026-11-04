#!/usr/bin/env python3
"""Independent self-check for hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous. usage: python3 -I selfcheck.py <run root, e.g. ~/stage4-logs/ec/run1b-unit-and-run1-cluster dir>
  selfcheck.py <unit dir> <cluster dir>
Re-parses the RAW files only (unit: test.out STAGE4 block/page/result lines; cluster: produce.out block lines, ec.trace, SNAPSHOT lines of summary.txt,
pos.json, A-system.log) and evaluates every frozen prediction (B2f/B3f with the 2026-10-26 amendments) with its own code. Prints PASS/FAIL lines."""
import glob, json, os, re, sys

KIB, MIB = 1024, 1 << 20
unit, cluster = sys.argv[1], sys.argv[2]
res = []


def rec(name, ok, detail):
    res.append(ok)
    print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + detail)


# ---------------- unit
cases = {}
for l in open(unit + '/test.out', errors='replace'):
    m = re.match(r'STAGE4 (block|result|page|case) (\S+) (.*)', l)
    if not m:
        continue
    kind, label, rest = m.groups()
    c = cases.setdefault(label, {'blocks': [], 'pages': []})
    kv = dict(re.findall(r'([\w.]+)=(\S+)', rest))
    if kind == 'block':
        c['blocks'].append((int(kv['enc']), int(kv['plain'])))
    elif kind == 'result':
        c['result'] = {k: int(v) for k, v in kv.items()}
    elif kind == 'page':
        c['pages'].append({k: v for k, v in kv.items()})


def maxenc(l):
    return max(e for e, _ in cases[l]['blocks'])


def tl(l):
    return cases[l]['result']['tl_capacity_after']


for r in (1, 2, 3):
    l = f's1_{r}'
    rec(f'S1 {l}: retained == max encrypted block length (exact relation, R4)', tl(l) == maxenc(l), f'{tl(l)} vs {maxenc(l)}')
    rec(f'S1 {l}: amended band [254 KiB, 263,213 B]', 254 * KIB <= tl(l) <= 262144 + 1069, f'{tl(l)} B = {tl(l)/1024:.2f} KiB')
    rec(f'S1 {l}: original band [256 KiB, 258 KiB]', 256 * KIB <= tl(l) <= 258 * KIB, f'{tl(l)}')
    rec(f'S1 {l}: capacity above 240 KiB (the 256 KiB-class block) and below 1 MiB', 240 * KIB < tl(l) < MIB, f'{tl(l)}')
    for s, (lo, hi) in (('s2', (MIB, MIB + 8 * KIB)), ('s3', (8 * MIB, 8 * MIB + 40 * KIB)), ('s4', (15 * MIB, 15 * MIB + 70 * KIB))):
        l = f'{s}_{r}'
        rec(f'{s.upper()} {l}: retained in [{lo}, {hi}] and == max enc', lo <= tl(l) <= hi and tl(l) == maxenc(l), f'{tl(l)} (max enc {maxenc(l)})')
        rec(f'{s.upper()} {l}: larger than 256 KiB and than 1 MiB-class max_mutation_size default 16 MiB for S2-S4? (> 256 KiB)', tl(l) > 256 * KIB + 2 * KIB, f'{tl(l)}')
    l = f's6_{r}'
    rec(f'S6 {l}: retained < 4 KiB', tl(l) < 4 * KIB, f'{tl(l)}')
    pg = cases[l]['pages']
    rbuf = max(int(p['reader.buffer.capacity']) for p in pg)
    rec(f'S6 {l}: reader buffer about 250 KiB (>= 240 KiB)', rbuf >= 240 * KIB, f'{rbuf}')
rec('S3 deterministic across 3 repeats (same size)', len({tl(f's3_{r}') for r in (1, 2, 3)}) == 1, str([tl(f's3_{r}') for r in (1, 2, 3)]))
k = [tl('s3_1'), tl('s3_mm4096'), tl('s3_mm1024')]
rec('K2: S3 capacity identical at max_mutation_size 16 MiB / 4 MiB / 1 MiB', len(set(k)) == 1, str(k))
mm = {l: [x for x in open(unit + '/test.out') if f'STAGE4 case {l} ' in x] for l in ('s3_1', 's3_mm4096', 's3_mm1024')}
rec('K2: the three JVMs really ran with 16777216 / 4194304 / 1048576', all(('max_mutation_size=%d' % v) in mm[l][0] for l, v in (('s3_1', 16777216), ('s3_mm4096', 4194304), ('s3_mm1024', 1048576))), '')
rec('S5: forged header read failed, retained capacity stays 0', cases['s5']['result']['failed'] == 1 and tl('s5') == 0, str(cases['s5']['result']))
rec('S5: >= 512 MiB allocated on the reading thread', cases['s5']['result']['thread_allocated_bytes'] >= 512 * MIB, str(cases['s5']['result']['thread_allocated_bytes']))
ns = [x for x in open(unit + '/test.out') if x.startswith('STAGE4 info noshrink after file') or 'STAGE4 check noshrink' in x]
rec('no shrink after a smaller second read (same thread)', any('no shrink' in x and x.rstrip().endswith('ok') for x in ns), ' | '.join(x.strip()[-110:] for x in ns[-4:]))
rec('C1: write-side cap rejects 600 KiB hint', any('write-side cap' in x and x.rstrip().endswith('ok') for x in open(unit + '/test.out')), '')
rec('C1: 600 KiB block read, retained == its block', tl('c1') == maxenc('c1') > 600 * KIB, f'{tl("c1")}')
rec('all harness-internal unit checks OK', not any(x.rstrip().endswith('MISMATCH') for x in open(unit + '/test.out')), '')

# ---------------- cluster
for cdir in sorted(glob.glob(cluster + '/*/')):
    tag = os.path.basename(cdir.rstrip('/'))
    if tag.startswith('pos_'):
        p = json.load(open(cdir + 'pos.json'))
        sizes = [s for _, s in p['files'] if _.endswith('.hints')]
        if tag == 'pos_default':
            rec(f'{tag}: <= 3 hint files, total ~200 MiB', len(sizes) <= 3 and sum(sizes) >= 190 * MIB, f'{len(sizes)} files, total {sum(sizes)}, max {max(sizes)}')
        else:
            rec(f'{tag}: >= 40 files each <= 4 MiB + one hint', len(sizes) >= 40 and max(sizes) <= 4 * MIB + 1100 * KIB, f'{len(sizes)} files, total {sum(sizes)}, max {max(sizes)}')
        continue
    if not os.path.exists(cdir + 'cell.json'):
        rec(f'{tag}: cell.json present', False, 'missing')
        continue
    blocks = [(int(a), int(b)) for a, b in re.findall(r'STAGE4 block \S+ idx=\d+ enc=(\d+) plain=(\d+)', open(cdir + 'produce.out').read())]
    mx = max(e for e, _ in blocks)
    rows = [l.split() for l in open(cdir + 'ec.trace')] if os.path.exists(cdir + 'ec.trace') else []
    kvs = [(r[0], dict(x.split('=', 1) for x in r[1:] if '=' in x)) for r in rows]
    outs = [d for k, d in kvs if k == 'out']
    excs = [d for k, d in kvs if k == 'exc']
    ins = [d for k, d in kvs if k == 'in']
    snaps = [json.loads(l.split('SNAPSHOT ', 1)[1]) for l in open(cdir + 'summary.txt') if l.startswith('SNAPSHOT')]
    kind = tag.split('_')[0]
    if 'plain' in tag:
        rec(f'{tag}: encrypted reader never ran', not rows, f'{len(rows)} trace lines')
        rec(f'{tag}: no live byte[] >= 2 MiB', all(max(s['big_bytearrays'] or [0]) < 2 * MIB for s in snaps), '')
    elif 'forged' in tag:
        rec(f'{tag}: readBuffer exited by exception, tl unchanged', bool(excs) and excs[-1]['tl'] == ins[-1]['tl'] == '0', str(excs[-1:]))
        rec(f'{tag}: >= 512 MiB allocated by the reader thread', int(excs[-1]['alloc']) - int(ins[-1]['alloc']) >= 512 * MIB, str(int(excs[-1]['alloc']) - int(ins[-1]['alloc'])))
        rec(f'{tag}: no live byte[] >= 64 MiB', all(max(s['big_bytearrays'] or [0]) < 64 * MIB for s in snaps), '')
        log = open(cdir + 'A-system.log', errors='replace').read()
        rec(f'{tag}: log has the FSReadError / failed-to-dispatch and the gossiper stop', 'Failed to dispatch hints file' in log and 'Stopping gossiper' in log, '')
    else:
        lo, hi = {'f1': (254 * KIB, 262144 + 1069), 'f2': (8 * MIB, 8 * MIB + 40 * KIB), 'f3': (15 * MIB, 15 * MIB + 70 * KIB)}[kind]
        last = int(outs[-1]['tl'])
        rec(f'{tag}: last retained capacity in amended band [{lo},{hi}]', lo <= last <= hi, f'{last}')
        rec(f'{tag}: retained == max raw encrypted block', last == mx, f'{last} vs {mx}')
        rec(f'{tag}: exactly one reader thread, all reads ok', len({d['th'] for d in outs}) == 1 and not excs, '')
        rec(f'{tag}: tl never decreases within the file', all(int(a['tl']) <= int(b['tl']) for a, b in zip(outs, outs[1:])), '')
        for s in snaps[:2]:
            rec(f'{tag}: live heap dump {s["tag"]} holds a byte[] of exactly {mx}', mx in s['big_bytearrays'], f'threads={s["hintsdispatcher_threads"]}')
        if len(snaps) == 3:
            rec(f'{tag}: after the 1-minute thread keep-alive (+150 s) the array is gone and the thread is gone', mx not in snaps[2]['big_bytearrays'] and snaps[2]['hintsdispatcher_threads'] == 0, f'threads={snaps[2]["hintsdispatcher_threads"]}, present={mx in snaps[2]["big_bytearrays"]}')
        rb = max(int(d['rbuf']) for d in outs)
        print(f'INFO {tag}: reader buffer high-water {rb} direct={outs[0]["direct"]}; direct pool at snapshots {[s["direct_used"] for s in snaps]}')
    cj = json.load(open(cdir + 'cell.json'))
    print(f'INFO {tag}: mm={cj["mm"]} max_enc={mx} blocks={len(blocks)} dispatch_end_s={cj["dispatch_end_s"]}')
print(f'SELFCHECK {sum(res)} of {len(res)} PASS')
