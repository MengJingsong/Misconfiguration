#!/usr/bin/env python3
"""Independent self-check of run 1 of hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize--autonomous (step 4).
usage: selfcheck.py <logs-root>     (default ~/stage4-logs/hu/run1)
It does NOT use the harness's own EXPECTED/ok lines. It re-parses the raw files and recomputes every relation from the
audit amendments R1, R2, R5 with its own code:
  unit    <root>/unit/test.out: the STAGE4 block / hint / counters lines (raw headers Z, C parsed from the hint file by the test,
          the reader's buffer capacity read by reflection, the pool counters read from the pool);
  cluster <root>/cluster/<cell>/hu.trace (Byteman line-141 rule, A), hints-blocks.json (raw block headers parsed by the cluster
          script from the .hints files before the replay), samples-jmx.csv, cell.json is NOT read.
Prints one line per check: "SC <part> <name> expected=.. actual=.. ok|FAIL" and a table of the relations the conclusion cites."""
import glob, json, os, re, sys
from collections import defaultdict

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/hu/run1')
MIB, KIB = 1 << 20, 1 << 10
res = {'ok': 0, 'fail': 0}


def sc(part, name, exp, act):
    ok = str(exp) == str(act)
    res['ok' if ok else 'fail'] += 1
    print(f'SC {part} {name} expected={exp} actual={act} {"ok" if ok else "FAIL"}')
    return ok


def cap(z):
    return 4096 if z <= 4096 else z + z // 20


# ---------------------------------------------------------------- unit
def kv(line):
    return dict(re.findall(r'(\w[\w.]*)=(\S+)', line))


def unit():
    path = f'{ROOT}/unit/test.out'
    cases = defaultdict(lambda: {'blocks': [], 'hints': [], 'counters': {}, 'info': []})
    for l in open(path, errors='replace'):
        m = re.match(r'STAGE4 (block|hint|counters|info|case) (\S+) (.*)', l.rstrip('\n'))
        if not m:
            continue
        kind, label, rest = m.groups()
        c = cases[label]
        if kind == 'block':
            d = kv(rest); c['blocks'].append((int(d['Z']), int(d['C'])))
        elif kind == 'hint':
            d = kv(rest); c['hints'].append({k: int(v) for k, v in d.items() if k not in ('buffer.isDirect',)})
        elif kind == 'counters':
            when, rest2 = rest.split(' ', 1)
            c['counters'][when] = {k: int(v) for k, v in kv(rest2).items() if k in ('size', 'used', 'overflow', 'pooled', 'direct', 'threshold')}
        elif kind == 'info':
            c['info'].append(rest)
    table = {}
    for label, c in sorted(cases.items()):
        m = re.match(r'f(\d+)_(lz4|deflate)_(\w+)$', label)
        if not m:
            continue
        fcs, comp, name = int(m.group(1)), m.group(2), m.group(3)
        blocks = c['blocks']
        real = [b for b in blocks if b[0] > 0]
        # capacity after each hint: independent recomputation
        cur = 4096
        caps = []
        for z, _ in blocks:
            if cur < z:
                cur = cap(z)
            if z > 0:
                caps.append(cur)
        got = [h['buffer.capacity'] for h in c['hints']]
        sc('unit', f'{label} capacity after each hint', caps, got)
        # overflow after read from first principles (all unpooled when fcs=1 or request > 131072 or Deflate)
        heap = comp == 'deflate'

        def pooled(x):
            return (not heap) and fcs >= 8 and x <= 131072
        ovf, ccap, ccap_p, bcap, bcap_init, bcap_p = 0, -1, False, 4096, True, False
        for z, cz in blocks:
            if ccap < 0 or cz > ccap:
                x = cz + cz // 20
                if ccap >= 0 and not ccap_p:
                    ovf -= ccap
                if not pooled(x):
                    ovf += x
                ccap, ccap_p = x, pooled(x)
            if bcap < z:
                x = z + z // 20
                if bcap_init:
                    ovf -= 4096
                elif not bcap_p:
                    ovf -= bcap
                if not pooled(x):
                    ovf += x
                bcap, bcap_init, bcap_p = x, False, pooled(x)
        b, a, cl = c['counters']['before'], c['counters']['after_read'], c['counters']['after_close']
        sc('unit', f'{label} overflow delta after read', ovf, a['overflow'] - b['overflow'])
        leak = ovf - (0 if ccap_p else ccap)
        sc('unit', f'{label} overflow delta after close (compressed buffer returned, reader buffer not)', leak, cl['overflow'] - b['overflow'])
        table[label] = {'fcs': fcs, 'comp': comp, 'name': name, 'Z': [z for z, _ in real], 'cap_final': bcap,
                        'ovf_read': a['overflow'] - b['overflow'], 'size_read': a['size'] - b['size'], 'thr': fcs * MIB,
                        'direct_read': a['direct'] - b['direct'], 'pooled_before': b['pooled'], 'pooled_after': a['pooled']}
    # cross-fcs: the capacity does not depend on file_cache_size
    byname = defaultdict(dict)
    for label, t in table.items():
        byname[(t['comp'], t['name'])][t['fcs']] = t
    for key, d in sorted(byname.items()):
        if len(d) == 3:
            sc('unit', f'{key} final capacity equal at fcs 1, 16, 512', 1, len({t["cap_final"] for t in d.values()}))
            exp_cap = cap(max(d[1]['Z']))
            sc('unit', f'{key} final capacity = cap(max Z) from the raw header', exp_cap, d[1]['cap_final'])
    # claim rows: blocks whose capacity exceeds 128 KiB drive Size above the 1 MiB threshold without error
    for label, t in sorted(table.items()):
        if t['fcs'] == 1 and t['comp'] == 'lz4':
            sc('unit', f'{label} fcs=1: nothing pooled, size delta = overflow delta', t['ovf_read'], t['size_read'])
            if t['cap_final'] >= MIB:
                sc('unit', f'{label} size delta exceeds the 1 MiB threshold', True, t['size_read'] > t['thr'])
    # pooled classification: capacity <= 131072 at fcs 16/512 leaves overflow at its baseline minus the initial buffer
    for label, t in sorted(table.items()):
        if t['comp'] == 'lz4' and t['fcs'] >= 16 and t['cap_final'] <= 131072 and t['cap_final'] > 4096 and len(t['Z']) == 1:
            sc('unit', f'{label} pooled request leaves overflow at -4096 (only the initial buffer put)', -4096, t['ovf_read'])
    # controls
    for label, c in sorted(cases.items()):
        m = re.match(r'f(\d+)_control$', label)
        if not m:
            continue
        fcs = int(m.group(1))
        b, h, r = c['counters']['before'], c['counters']['held400x64KiB'], c['counters']['released']
        total = 400 * 65536
        pooled_exp = 0 if fcs * MIB < 8 * MIB else min((fcs * MIB // (8 * MIB)) * 8 * MIB, -(-total // (8 * MIB)) * 8 * MIB)
        ovf_exp = (400 - (pooled_exp // (8 * MIB)) * 128 if pooled_exp else 400) * 65536
        ovf_exp = max(ovf_exp, 0)
        sc('unit', f'control fcs={fcs} pooled bytes', pooled_exp, h['pooled'] - b['pooled'])
        sc('unit', f'control fcs={fcs} overflow bytes', ovf_exp, h['overflow'] - b['overflow'])
        sc('unit', f'control fcs={fcs} pooled never above threshold', True, h['pooled'] <= fcs * MIB)
    # forged header
    f = cases.get('f16_forged')
    if f:
        z = [b[0] for b in f['blocks']]
        sc('unit', 'forged: block 1 header Z', 536870912, z[0])
        sc('unit', 'forged: reader buffer capacity', cap(536870912), f['hints'][0]['buffer.capacity'] if f['hints'] else None)
        sc('unit', 'forged: one hint read without error', 1, len(f['hints']))
    print('UT label fcs comp Zlist cap_final overflow_delta_read size_delta_read direct_delta_read')
    for label, t in sorted(table.items()):
        print('UT', label, t['fcs'], t['comp'], t['Z'], t['cap_final'], t['ovf_read'], t['size_read'], t['direct_read'])
    errs = [l for l in open(path, errors='replace') if l.startswith('STAGE4 error')]
    sc('unit', 'no STAGE4 error lines', 0, len(errs))
    return table


# ---------------------------------------------------------------- cluster
def cluster():
    cells = {}
    for d in sorted(glob.glob(f'{ROOT}/cluster/f*_b*')):
        m = re.search(r'f(\d+)_b(\d+)$', d)
        fcs, vb = int(m.group(1)), int(m.group(2))
        tag = f'f{fcs}_b{vb}'
        try:
            truth = json.load(open(f'{d}/hints-blocks.json'))
            lines = open(f'{d}/hu.trace', errors='replace').read().splitlines()
        except OSError as e:
            print(f'SC cluster {tag} missing file {e}')
            res['fail'] += 1
            continue
        raw = [(z, c) for t in truth.values() for z, c, _ in t['blocks']]
        tr = [dict(re.findall(r'(\w+)=(\S+)', l)) for l in lines if l.startswith('blk ')]
        sc('cluster', f'{tag} blk lines = raw blocks', len(raw), len(tr))
        sc('cluster', f'{tag} (Z,C) multiset trace = raw', sorted(raw), sorted((int(x['Z']), int(x['C'])) for x in tr))
        zmax = max([z for z, _ in raw] or [0])
        capmax = max([int(x['cap']) for x in tr] or [0])
        sc('cluster', f'{tag} max reader capacity = cap(max raw Z)={cap(zmax)}', cap(zmax), capmax)
        # overflow model replay (single reader per file, in trace order)
        base = None
        s = d + '/samples-jmx.csv'
        rows = [l.split(',') for l in open(s).read().splitlines()]
        t_first = int(tr[0]['ms']) if tr else None
        for r in rows:
            if len(r) == 6 and r[0].isdigit() and t_first and int(r[0]) < t_first - 5000:
                base = (int(float(r[2])), int(float(r[4])), int(float(r[1])))  # size, ovf, direct
        ovf, state = 0, {}
        bad = 0

        def pooled(x):
            return fcs >= 8 and x <= 131072
        for x in tr:
            f = x['file']
            z, c = int(x['Z']), int(x['C'])
            r = state.setdefault(f, {'cap': 4096, 'init': True, 'cp': False, 'comp': -1, 'compp': False})
            if r['comp'] < 0 or c > r['comp']:
                y = c + c // 20
                if r['comp'] >= 0 and not r['compp']:
                    ovf -= r['comp']
                if not pooled(y):
                    ovf += y
                r['comp'], r['compp'] = y, pooled(y)
            if r['cap'] < z:
                y = z + z // 20
                if r['init']:
                    ovf -= 4096
                elif not r['cp']:
                    ovf -= r['cap']
                if not pooled(y):
                    ovf += y
                r['cap'], r['init'], r['cp'] = y, False, pooled(y)
            if int(x['ovf']) - (base[1] if base else 0) != ovf:
                bad += 1
        sc('cluster', f'{tag} overflow counter minus baseline = model after every block', 0, bad)
        pk_ovf = max([int(x['ovf']) for x in tr] or [0]) - (base[1] if base else 0)
        pk_size = max([int(x['size']) for x in tr] or [0]) - (base[0] if base else 0)
        thr = {int(x['thr']) for x in tr}
        sc('cluster', f'{tag} pool threshold seen = file_cache_size', {fcs * MIB}, thr)
        cells[(fcs, vb)] = {'zmax': zmax, 'capmax': capmax, 'pk_ovf': pk_ovf, 'pk_size': pk_size, 'blocks': len(raw),
                            'nonempty': sum(1 for z, _ in raw if z > 0), 'ccapmax': max([int(x['ccap']) for x in tr] or [0])}
        if vb >= MIB and fcs == 1:
            sc('cluster', f'{tag} Size over baseline exceeds file_cache_size', True, pk_size > fcs * MIB)
        if vb >= MIB:
            sc('cluster', f'{tag} peak overflow >= cap + ccap - 4096', True, pk_ovf >= cap(zmax) + cells[(fcs, vb)]['ccapmax'] - 4096)
    # cross-cell: same B, different F. Capacity is a function of the raw Zmax only. Peak overflow adds the compressed buffer, whose
    # size (random values, a different draw per cell) varies by a few bytes (B >= 100 KiB) or a few percent (1 KiB values, where the
    # 64 reused values compress): compared within 1 % for B >= 100 KiB, reported for 1 KiB.
    for vb in sorted({k[1] for k in cells}):
        row = {f: cells[(f, vb)] for f in (1, 16, 512) if (f, vb) in cells}
        if len(row) >= 2:
            sc('cluster', f'B={vb} capacity equal across file_cache_size {sorted(row)}', 1, len({v['capmax'] for v in row.values()}))
            pk = [v['pk_ovf'] for v in row.values()]
            if vb >= 100 * KIB:
                sc('cluster', f'B={vb} peak overflow within 1 % across file_cache_size {sorted(row)} ({pk})', True, (max(pk) - min(pk)) <= 0.01 * max(pk))
            else:
                print(f'SC info B={vb} peak overflow across file_cache_size {sorted(row)}: {pk} (compressed-size draw differs per cell)')
    # control, chunk-cache reads (supplementary after D2): the pool is exercised at 512 MiB, left at its start-up size at 16 MiB
    for d in sorted(glob.glob(f'{ROOT}/cluster/control_f*')):
        fcs = int(re.search(r'control_f(\d+)', d).group(1))
        rows = [l.split(',') for l in open(f'{d}/samples-jmx.csv').read().splitlines()]
        vals = [(int(r[0]), float(r[2]), float(r[4]), float(r[5])) for r in rows if len(r) == 6 and r[0].isdigit() and 'ERR' not in r]
        pooled_pk = max(s - o for _, s, o, _ in vals)
        print(f'SC info chunk-cache read control fcs={fcs} samples={len(vals)} peak pooled part={int(pooled_pk)} thresholds={sorted({int(x[3]) for x in vals})}')
        if fcs == 16:
            sc('control-reads', 'fcs=16 chunk cache disabled (32 MiB reserve): pooled part stays at the start-up chunk', 8 * MIB, int(pooled_pk))
        else:
            sc('control-reads', f'fcs={fcs} pooled part exceeds 16 MiB', True, pooled_pk > 16 * MIB)
    # control (B3h as amended by R11): the node's own pool, 400 x 64 KiB held
    for d in sorted(glob.glob(f'{ROOT}/cluster/inject_f*')):
        fcs = int(re.search(r'inject_f(\d+)', d).group(1))
        thr = fcs * MIB
        rows = [l.split(',') for l in open(f'{d}/samples-jmx.csv').read().splitlines()]
        vals = [(int(r[0]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in rows if len(r) == 6 and r[0].isdigit() and 'ERR' not in r]
        m = re.search(r'before: size=(\d+) used=(\d+) ovf=(\d+) thr=(\d+) after: size=(\d+) used=(\d+) ovf=(\d+)', open(f'{d}/inject.log').read())
        b_size, b_used, b_ovf, b_thr, a_size, a_used, a_ovf = map(int, m.groups())
        sc('control', f'fcs={fcs} threshold in the node', thr, b_thr)
        sc('control', f'fcs={fcs} used rose by 400 x 65536', 400 * 65536, a_used - b_used)
        pooled_after = a_size - a_ovf
        if fcs == 1:
            sc('control', 'fcs=1 pooled part 0, overflow +26214400', (0, 400 * 65536), (pooled_after, a_ovf - b_ovf))
        elif fcs == 16:
            sc('control', 'fcs=16 pooled part = 16 MiB exactly', thr, pooled_after)
            sc('control', 'fcs=16 overflow = what did not fit (26214400 - (16 MiB - baseline used))', 400 * 65536 - (thr - b_used), a_ovf - b_ovf)
        else:
            sc('control', 'fcs=512 pooled part > 16 MiB and overflow unchanged', (True, 0), (pooled_after > 16 * MIB, a_ovf - b_ovf))
        sm_pooled = max(s - o for _, s, _, o, _ in vals)
        print(f'SC info inject fcs={fcs} sampler peak pooled part {int(sm_pooled)} (injected line: {pooled_after})')
    return cells


if __name__ == '__main__':
    t = unit() if os.path.exists(f'{ROOT}/unit/test.out') else None
    c = cluster() if glob.glob(f'{ROOT}/cluster/f*_b*') else None
    print(f'SC summary ok={res["ok"]} fail={res["fail"]}')
    if c:
        print('cluster table (fcs, B): zmax capmax peak_overflow peak_size blocks nonempty')
        for k, v in sorted(c.items()):
            print(k, v['zmax'], v['capmax'], v['pk_ovf'], v['pk_size'], v['blocks'], v['nonempty'])
    sys.exit(0 if res['fail'] == 0 else 1)
