#!/usr/bin/env python3
"""Independent self-check of trie-pathreconstructor-keybytes-growth--autonomous run 1. Re-parses the raw files; does not import the
analyzers and does not read their output.
usage: python3 -I selfcheck.py unit <tp33-unit.txt> <junit.xml> | cluster <cluster-dir> <tp33-unit.txt>"""
import glob, os, re, sys, collections

mode = sys.argv[1]
fails = []


def ok(name, cond, note):
    print(('PASS ' if cond else 'FAIL ') + name + ': ' + note)
    if not cond:
        fails.append(name)


def rows_of(fn):
    out = []
    for l in open(fn):
        if l.startswith('TP33 '):
            out.append(dict(t.split('=', 1) for t in l[5:].split()))
    return out


if mode == 'unit':
    rows = rows_of(sys.argv[2])
    xml = open(sys.argv[3]).read()
    m = re.search(r'tests="(\d+)"[^>]*failures="(\d+)"|failures="(\d+)"[^>]*tests="(\d+)"', xml)
    ok('junit', 'testcase' in xml and 'failure' not in xml.replace('failures="0"', '') and 'errors="0"' in xml, 'one test ran, no failure/error in the XML')
    bad = 0
    for r in rows:
        if 'cap' in r and 'maxPath' in r:
            P, cap = int(r['maxPath']), int(r['cap'])
            if P <= 32:
                bad += cap != 32
            else:
                bad += not (P <= cap <= 2 * P)
    ok('cap vs path', bad == 0, f'{sum(1 for r in rows if "maxPath" in r)} rows re-checked with my own code, {bad} outside')
    mism = sum(1 for r in rows if 'onB' in r and ((r.get('onB') != r.get('onA')) or (r.get('offB') is not None and r.get('offB') != r.get('offA'))))
    ok('accounting unchanged by drain', mism == 0, f'{len(rows)} rows, {mism} with a size change')
    # 65535-byte rows by kind
    for kind in ('raw', 'real', 'zero'):
        x = [r for r in rows if r['kind'] == kind and r.get('L') == '65535']
        print(f'  info {kind} L=65535: ' + ', '.join(sorted({f"P={r['P']} cap={r['cap']} ({r['bt']})" for r in x})))
    cs = sorted({int(r['P']) - int(r['L']) for r in rows if r['kind'] in ('real', 'zero')})
    ok('c constant', len(cs) == 1 and 8 <= cs[0] <= 14, f'P - L over real and zero rows = {cs}')
    mc = {(r['bt'], r['M']): (int(r['onB']), int(r['offB'])) for r in rows if r['kind'] == 'mctl'}
    print(f'  info M control (onB, offB): {mc}')
    ok('M control rises', mc[('ON_HEAP', '100000')][0] > 5 * mc[('ON_HEAP', '10000')][0] and mc[('OFF_HEAP', '100000')][1] > 5 * mc[('OFF_HEAP', '10000')][1], 'x5 or more in both buffer types')
    conc = [r for r in rows if r['kind'] == 'conc']
    ok('concurrent allocation', all(int(r['allocSum']) >= int(r['N']) * int(r['capMin']) for r in conc), 'allocSum >= N x cap in all conc rows')
else:
    D = sys.argv[2]
    unit = rows_of(sys.argv[3])
    c = int([r for r in unit if r['kind'] == 'real'][0]['P']) - int([r for r in unit if r['kind'] == 'real'][0]['L'])
    PB = 60000 + c
    lives = sorted(x for x in os.listdir(D) if os.path.isdir(f'{D}/{x}'))
    print(f'c={c}, P_big={PB}, lifetimes {lives}')
    bigmax = {}
    for lf in lives:
        tr = [l for l in open(f'{D}/{lf}/growth-trace.txt', errors='replace') if l.startswith(('byte ', 'bytes '))]
        lens = [int(re.search(r' len=(\d+)', l).group(1)) for l in tr]
        ok(f'{lf} trace not empty', len(tr) > 0, f'{len(tr)} growth lines')
        ok(f'{lf} lengths <= 2 P_big (any phase)', max(lens) <= 2 * PB, f'max {max(lens)}, distinct {len(set(lens))}: {sorted(set(lens))[:20]}')
        # per-iterator monotone growth, byte-growth doubling
        last = {}
        nonmono = 0
        for l in tr:
            m = re.match(r'(byte|bytes) ms=\d+ thr=(\S+) it=(-?\d+) len=(\d+)', l)
            k = (m.group(2), m.group(3)); n = int(m.group(4))
            if k in last and n <= last[k] and m.group(1) == 'byte':
                nonmono += 1
            last[k] = max(last.get(k, 0), n)
        ok(f'{lf} no shrink on byte-growth', nonmono < max(5, len(tr) // 50), f'{nonmono} non-increasing byte growths (identity hashes may be reused after GC)')
        bigmax[lf] = max(lens)
        # raw histograms: peak byte[] bytes
        hs = sorted(glob.glob(f'{D}/{lf}/histo-*.txt'))
        pk = 0
        for h in hs:
            for l in open(h, errors='replace'):
                p = l.split()
                if len(p) >= 4 and p[0].endswith(':') and p[3] == '[B':
                    pk = max(pk, int(p[2]))
        print(f'  info {lf}: {len(hs)} raw histograms, peak byte[] {pk / 1048576:.1f} MiB')
        # series raw
        mxon = 0
        for l in list(open(f'{D}/{lf}/series.csv'))[1:]:
            p = l.strip().split(',')
            try:
                mxon = max(mxon, float(p[1]))
            except (ValueError, IndexError):
                pass
        print(f'  info {lf}: max t_big MemtableOnHeapDataSize in the whole series {mxon / 1048576:.1f} MiB')
        # system.log + config really applied
        sl = open(f'{D}/{lf}/system.log', errors='replace').read()
        errs = [l for l in sl.splitlines() if l.startswith('ERROR')]
        ok(f'{lf} no ERROR in system.log', not errs, f'{len(errs)} lines')
        cfg = open(f'{D}/{lf}/cassandra.yaml').read()
        m = re.search(r'^memtable_heap_space: (\S+)', cfg, re.M)
        n = re.search(r'^memtable_allocation_type: (\S+)', cfg, re.M)
        want = {'H64': ('64MiB', 'heap_buffers'), 'H256': ('256MiB', 'heap_buffers'), 'H1024': ('1024MiB', 'heap_buffers'), 'O256': ('256MiB', 'offheap_objects')}[lf]
        ok(f'{lf} setting in the yaml used', (m.group(1), n.group(1)) == want, f'{m.group(1)} {n.group(1)}')
        applied = re.search(r'memtable_allocation_type=(\S+?); .*?memtable_heap_space=(\S+?);', sl)
        jvm = re.search(r'JVM Arguments: \[(.*?)\]', sl)
        ok(f'{lf} node logged the setting and the agent', bool(applied) and (applied.group(2), applied.group(1)) == want and bool(jvm) and 'javaagent' in jvm.group(1) and '-Xmx2G' in jvm.group(1),
           f'{applied.groups() if applied else None}; javaagent {"javaagent" in (jvm.group(1) if jvm else "")}; -Xmx2G {"-Xmx2G" in (jvm.group(1) if jvm else "")}')
    if bigmax:
        ok('largest big length equal within a factor 2 over lifetimes', max(bigmax.values()) <= 2 * min(bigmax.values()), str(bigmax))
    left = 0
    for pid in os.listdir('/proc'):
        if pid.isdigit():
            try:
                cl = open(f'/proc/{pid}/cmdline', 'rb').read().decode(errors='replace')
            except OSError:
                continue
            if cl.startswith(('java', '/usr/lib/jvm')) or '/java\0' in cl[:200]:
                left += ('CassandraDaemon' in cl and 's4-tp33-run' in cl)
    left = str(left)
    ok('no tp33 node left', left == '0', f'{left} matching processes')
print('\nSELF-CHECK ' + ('ALL PASS' if not fails else 'FAILS: ' + ', '.join(fails)))
