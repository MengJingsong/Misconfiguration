#!/usr/bin/env python3
"""Cluster-tier readings and EXPECTED lines for the amended B3f/B3g (2026-10-28). Same file in the three SAI case folders and (with --sasi) the SASI folder; the
case comes from the folder name or CASE=. usage: analyze_cluster.py [log-root] [out-file]"""
import glob, json, math, os, re, sys

HERE = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
KEY = os.environ.get('CASE') or {'block_size-add-blockindex--autonomous': 'blockindex', 'block_size-writeposting-blocksize--autonomous': 'postings',
                                 'block_packed_max_block_size-checkblocksize-blocksize--autonomous': 'maxblock', 'tokens_per_block-add-pos--autonomous': 'tpb'}[HERE]
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(f'~/s4-b34/logs/{KEY}/cluster')
out = open(sys.argv[2], 'w') if len(sys.argv) > 2 else sys.stdout
fails = 0
MIB = 1 << 20


def P(s):
    print(s, file=out)


def expect(name, cond, detail=''):
    global fails
    P(f'EXPECTED {name}: {"OK" if cond else "MISMATCH"} {detail}')
    if not cond:
        fails += 1


summary = open(ROOT + '/summary.txt', errors='replace').read().splitlines()


def arm_lines(label):
    on, res = False, []
    for l in summary:
        if l.startswith(f'ARM {label} start'):
            on = True; res = []
        if on:
            res.append(l)
        if on and l.startswith(f'ARM {label} STOPPED'):
            break
    return res


def comp(name):
    m = re.search(r'(?:SAI|SI)\+aa\+(?:(.+?)\+)?([A-Za-z]+)\.db$', name)
    return (m.group(1) or '', m.group(2)) if m else ('', name)


def read_files(path):
    r = {}
    if os.path.exists(path):
        for l in open(path):
            if '\t' in l:
                n, s = l.rstrip('\n').split('\t'); r[n] = int(s)
    return r


def gauges(csv):
    rows = [l.split(',') for l in open(csv).read().splitlines()[1:] if l.count(',') == 5]
    return dict(seg_used_peak=max(int(r[1]) for r in rows), heap_peak=max(int(r[4]) for r in rows), samples=len(rows)) if rows else dict(seg_used_peak=-1, heap_peak=-1, samples=0)


arms = {}
for dpath in sorted(glob.glob(ROOT + '/*/')):
    label = os.path.basename(dpath.rstrip('/'))
    a = dict(label=label, dir=dpath)
    a['files_build'] = read_files(f'{dpath}files-{label}-after-build.txt')
    a['files_rebuild'] = read_files(f'{dpath}files-{label}-after-rebuild.txt')
    g = f'{dpath}gauges-{label}.csv'
    a['g'] = gauges(g) if os.path.exists(g) else None
    rs = f'{dpath}rss-{label}.csv'
    a['rss_peak_kb'] = max([int(l.split(',')[1]) for l in open(rs).read().splitlines()[1:] if ',' in l] or [0]) if os.path.exists(rs) else None
    a['ledger'] = [l.split() for l in open(dpath + 'ledger.txt')] if os.path.exists(dpath + 'ledger.txt') else []
    a['flush_lines'] = len([l for l in open(dpath + 'flush-lines.txt') if 'Global limit' in l]) if os.path.exists(dpath + 'flush-lines.txt') else None
    a['errors'] = open(dpath + 'errors.txt', errors='replace').read() if os.path.exists(dpath + 'errors.txt') else ''
    a['lines'] = arm_lines(label)
    a['verify'] = [l for l in a['lines'] if l.startswith('VERIFY')]
    a['jar'] = open(dpath + 'jar.txt').read().strip().replace('\n', ' | ') if os.path.exists(dpath + 'jar.txt') else ''
    arms[label] = a


def total(a, which='files_build', pred=lambda c: True):
    return sum(s for n, s in a[which].items() if pred(comp(n)))


NUMERIC = {'RowToToken', 'RowToPartition', 'PartitionToSize', 'PartitionKeyBlockOffsets', 'ClusteringKeyBlockOffsets'}

P('== arm | total SAI bytes after build / after rebuild | numeric-values bytes | per-index bytes | heap peak MiB | seg gauge peak MiB | RSS peak MiB | ledger lengths | verify')
for l, a in ([] if KEY == 'tpb' else arms.items()):
    tb, tr = total(a), total(a, 'files_rebuild')
    num = total(a, pred=lambda c: c[1] in NUMERIC)
    idx = total(a, pred=lambda c: c[0] != '')
    lens = {}
    for x in a['ledger']:
        if x[0] in ('BPW', 'PW'):
            lens[x[1]] = lens.get(x[1], 0) + 1
    g = a['g']
    P(f"{l:10} | {tb} / {tr} | {num} | {idx} | {g and g['heap_peak'] / MIB:.0f} | {g and g['seg_used_peak'] / MIB:.1f} | {a['rss_peak_kb'] and a['rss_peak_kb'] / 1024:.0f} | {lens} | {a['verify'][-1][:110] if a['verify'] else 'none'}")
    P('    components: ' + ', '.join(f"{(comp(n)[0] + '/' if comp(n)[0] else '') + comp(n)[1]}={s}" for n, s in sorted(a['files_build'].items())))

# ---- checks common to the SAI cases
for l, a in ([] if KEY == 'tpb' else arms.items()):
    if KEY == 'maxblock' and l.startswith('M8k'):
        continue
    expect(f'{l}: node ran the arm\'s jar (jar md5 recorded)', bool(a['jar']), a['jar'][:90])
    expect(f'{l}: verify queries match the seed (count v>=0 == rows; txt terms == rows/100)', bool(a['verify']) and all(v.rstrip().endswith('OK') for v in a['verify']), a['verify'][-1][:140] if a['verify'] else 'none')
    expect(f'{l}: no ERROR lines in system.log', not re.search(r'^ERROR', a['errors'], re.M), a['errors'][:160].replace('\n', ' | '))
    expect(f'{l}: initial build and rebuild produce the same component bytes', total(a) == total(a, 'files_rebuild'), f"{total(a)} vs {total(a, 'files_rebuild')}")


def sets(a):
    return [x for x in a['ledger'] if x[0] == ('BPW' if KEY in ('blockindex', 'maxblock') else 'PW')]


def lens(a):
    c = {}
    for x in sets(a):
        c[int(x[1])] = c.get(int(x[1]), 0) + 1
    return c


def ratio(x, y):
    return x / y if y else float('nan')


if KEY == 'blockindex':
    A, A2, B, C, A7, K = (arms.get(k) for k in ('A-3M', 'A2-3M', 'B-num64', 'C-num1m', 'A-750k', 'ctl-seg16'))
    for lab, a, want in (('A-3M', A, {128: 2, 16384: 3}), ('A2-3M', A2, {128: 2, 16384: 3}), ('A-750k', A7, {128: 2, 16384: 3}), ('ctl-seg16', K, {128: 2, 16384: 3}), ('B-num64', B, {64: 5}), ('C-num1m', C, {1048576: 5})):
        if not a: continue
        n = len(sets(a)); c = lens(a)
        k = n // 5
        expect(f'{lab}: ledger = whole sets of five writers with exactly the arm\'s lengths {want}', n >= 5 and n % 5 == 0 and c == {L: m * k for L, m in want.items()}, f'{n} lines {c}')
        per_set = sum(L * 8 for L, m in want.items() for _ in range(m))
        P(f'INFO {lab}: scratch long[] bytes per SSTable writer set = {per_set} ({per_set / 1024:.0f} KiB); sets constructed {k}')
    if A and B and C:
        ta, tb, tc = total(A), total(B), total(C)
        expect('total SAI bytes within 10 % across A / B (64) / C (2^20)', max(ta, tb, tc) <= 1.10 * min(ta, tb, tc), f'{ta} {tb} {tc}')
        nonnum = lambda a: total(a, pred=lambda c: c[1] not in NUMERIC)
        expect('non-numeric components (per-index files, key blocks) within 2 % across A / B / C', max(map(nonnum, (A, B, C))) <= 1.02 * min(map(nonnum, (A, B, C))), f'{nonnum(A)} {nonnum(B)} {nonnum(C)}')
        for nm, x in (('B', B), ('C', C)):
            led = (5 * 8 * (64 if nm == 'B' else 1 << 20)) - 395264
            gh = x['g']['heap_peak'] - A['g']['heap_peak']
            allowed = abs(led) + 0.02 * (4 << 30)
            expect(f'peak heap of {nm} differs from A by no more than the ledger difference ({led} B) + 2 % of 4 GiB', abs(gh) <= allowed, f'diff {gh / MIB:.1f} MiB allowed {allowed / MIB:.1f} MiB')
        if A2:
            P(f"INFO noise A vs A2: total {total(A)} / {total(A2)}; heap peak {A['g']['heap_peak'] / MIB:.0f} / {A2['g']['heap_peak'] / MIB:.0f} MiB")
    if A and A7:
        r = ratio(total(A), total(A7))
        expect('SAI bytes grow with rows: 3M / 750k within 3.4 .. 4.6 (rows ratio 4)', 3.4 <= r <= 4.6, f'{r:.2f}')
        expect('A-3M ledger-independent: metadata grows with rows (numeric-values bytes 3M / 750k within 3.4 .. 4.6)', 3.4 <= ratio(total(A, pred=lambda c: c[1] in NUMERIC), total(A7, pred=lambda c: c[1] in NUMERIC)) <= 4.6)
elif KEY == 'postings':
    A, A2, B, C, A7, K = (arms.get(k) for k in ('P128-3M', 'P128b-3M', 'P32-3M', 'P512-3M', 'P128-750k', 'ctl-seg16'))
    for lab, a, bs in (('P128-3M', A, 128), ('P128b-3M', A2, 128), ('P128-750k', A7, 128), ('ctl-seg16', K, 128), ('P32-3M', B, 32), ('P512-3M', C, 512)):
        if not a: continue
        c = lens(a)
        expect(f'{lab}: every PostingsWriter has deltaBuffer length {bs}', len(sets(a)) > 0 and set(c) == {bs}, f'{c}')
    post = lambda a: total(a, pred=lambda c: c[1] == 'PostingLists')
    if A and B and C:
        P(f'INFO PostingLists bytes: P32 {post(B)} P128 {post(A)} P128b {post(A2) if A2 else None} P512 {post(C)}; ratios {ratio(post(B), post(A)):.3f} {ratio(post(C), post(A)):.3f}')
        expect('PostingLists bytes of P32 and P512 within 5 % of P128 (B5.6)', abs(post(B) - post(A)) <= 0.05 * post(A) and abs(post(C) - post(A)) <= 0.05 * post(A), f'{post(B)} {post(A)} {post(C)}')
        for nm, x in (('P32', B), ('P512', C)):
            led = 8 * (32 if nm == 'P32' else 512) - 8 * 128
            gh = x['g']['heap_peak'] - A['g']['heap_peak']
            allowed = abs(led) * 4 + 0.02 * (2 << 30)
            expect(f'peak heap of {nm} differs from P128 by no more than the ledger difference + 2 % of 2 GiB', abs(gh) <= allowed, f'diff {gh / MIB:.1f} MiB allowed {allowed / MIB:.1f} MiB')
        tot = [total(x) for x in (A, B, C)]
        P(f'INFO total SAI bytes P128/P32/P512: {tot}')
    if A and A2:
        P(f"INFO noise P128 vs P128b: PostingLists {post(A)} / {post(A2)}; heap peak {A['g']['heap_peak'] / MIB:.0f} / {A2['g']['heap_peak'] / MIB:.0f} MiB")
    if A and A7:
        r = ratio(post(A), post(A7))
        expect('posting bytes grow with rows: 3M / 750k within 3.4 .. 4.6', 3.4 <= r <= 4.6, f'{r:.2f}')
elif KEY == 'maxblock':
    S7, S15, S3, M1, M8, K = (arms.get(k) for k in ('S-750k', 'S-1500k', 'S-3M', 'M1m-3M', 'M8k-750k', 'ctl-seg16'))
    for lab, a in (('S-750k', S7), ('S-1500k', S15), ('S-3M', S3), ('M1m-3M', M1), ('ctl-seg16', K)):
        if not a: continue
        c = lens(a); k = len(sets(a)) // 5
        expect(f'{lab}: ledger = whole sets of five writers, only lengths 128 (x2) and 16384 (x3), largest 16384', len(sets(a)) % 5 == 0 and len(sets(a)) >= 5 and c == {128: 2 * k, 16384: 3 * k}, f'{c}')
        mx = [x for x in a['ledger'] if x[0] == 'CHK']
        P(f"INFO {lab}: checkBlockSize calls {len(mx)}; max argument bound seen {set(x[3] for x in mx)}")
    if S3 and M1:
        expect('S-3M and M1m-3M (MAX_BLOCK_SIZE 2^27 vs 2^20) give identical component bytes', S3['files_build'].keys() == M1['files_build'].keys() and all(S3['files_build'][k] == M1['files_build'][k] for k in S3['files_build']), f'{total(S3)} vs {total(M1)}')
        P(f"INFO heap peak S-3M {S3['g']['heap_peak'] / MIB:.0f} MiB, M1m-3M {M1['g']['heap_peak'] / MIB:.0f} MiB; S-3M repeat not run (noise from ctl/other arms only)")
        expect('heap peak of M1m-3M within 2 % of 4 GiB of S-3M (same writers, 40 B ledger identical)', abs(M1['g']['heap_peak'] - S3['g']['heap_peak']) <= 0.02 * (4 << 30), f"{(M1['g']['heap_peak'] - S3['g']['heap_peak']) / MIB:.1f} MiB")
    if S7 and S15 and S3:
        t7, t15, t3 = total(S7), total(S15), total(S3)
        expect('SAI bytes follow rows 1 : 2 : 4 within 15 %', abs(t15 / t7 - 2) <= 0.3 and abs(t3 / t7 - 4) <= 0.6, f'{t7} {t15} {t3} ratios {t15 / t7:.2f} {t3 / t7:.2f}')
    if M8:
        ch = [x for x in M8['ledger'] if x[0] == 'CHK']
        iae = re.findall(r'IllegalArgumentException[^\n]*', M8['errors'])
        sl = ''
        p = os.path.expanduser(f'~/s4-b34/cl/maxblock/node/logs/system.log')
        P(f"INFO M8k-750k: ledger lines {len(M8['ledger'])}, CHK calls {len(ch)} (bounds {set(x[3] for x in ch)}), BPW lengths {lens(M8)}; verify {M8['verify'][-1][:100] if M8['verify'] else 'none'}; SAI bytes {total(M8)}")
        P('INFO M8k-750k: IllegalArgumentException lines in errors.txt: ' + (' || '.join(iae[:3])[:300] if iae else 'none'))
        expect('M8k-750k: the 2^13 bound rejects the monotonic writer (16384 > 8192) with the range message', bool(re.search(r'blockSize must be >= 64 and <= 8192, got 16384', M8['errors'] + ''.join(' '.join(x) for x in M8['ledger']))) or any(x[1] == '16384' and x[3] == '8192' for x in ch if len(x) > 3), '')
elif KEY == 'tpb':
    pass

# ---- positive control (SAI cases)
if KEY in ('blockindex', 'postings', 'maxblock'):
    base = {'blockindex': 'A-3M', 'postings': 'P128-3M', 'maxblock': 'S-3M'}[KEY]
    A, K = arms.get(base), arms.get('ctl-seg16')
    if A and K:
        P(f"INFO control: ctl-seg16 seg gauge peak {K['g']['seg_used_peak'] / MIB:.1f} MiB (limit 16) vs {base} {A['g']['seg_used_peak'] / MIB:.1f} MiB (limit 1024); memory-limit flush lines {K['flush_lines']} vs {A['flush_lines']}; heap peaks {K['g']['heap_peak'] / MIB:.0f} vs {A['g']['heap_peak'] / MIB:.0f} MiB")
        expect('control (i): segment buffer peak in the 16MiB arm <= 20 MiB', K['g']['seg_used_peak'] <= 20 * MIB, f"{K['g']['seg_used_peak'] / MIB:.1f} MiB")
        expect('control (ii): the default arm reached more than 32 MiB (the limit was driven)', A['g']['seg_used_peak'] > 32 * MIB, f"{A['g']['seg_used_peak'] / MIB:.1f} MiB")
        expect('control (iii) (B5.8, amended 2026-10-28): more memory-limit flush lines in the 16MiB arm than in the default arm', (K['flush_lines'] or 0) > (A['flush_lines'] or 0), f"{K['flush_lines']} vs {A['flush_lines']}")
        P(f"INFO control (iii) as frozen in B5.5 (flush lines only in the 16MiB arm): {'met' if (K['flush_lines'] or 0) > 0 and (A['flush_lines'] or 0) == 0 else 'NOT met'} ({K['flush_lines']} vs {A['flush_lines']}); replaced by B5.8, see the results file runbook defect 1")

# ---- SASI
if KEY == 'tpb':
    sasi = {}
    for l, a in arms.items():
        d = {}
        for ln in a['lines']:
            m = re.match(r"INDEX (\w+) build (\w+) after (\d+) s; files \[\('([^']+)', (\d+)\)\]; temp-segment files seen (\d+)", ln)
            if m:
                d[m.group(1)] = dict(done=m.group(2) == 'complete', secs=int(m.group(3)), bytes=int(m.group(5)), segs=int(m.group(6)))
            m = re.match(r'GAUGES \S+ (\w): (\{.*\})', ln)
            if m:
                d.setdefault(m.group(1) + '_idx', {})['heap'] = json.loads(m.group(2))['heap_used_peak']
            m = re.match(r'VERIFY (\w+): count=(\d+) expected (\d+) (\w+)', ln)
            if m:
                d.setdefault(m.group(1), {})['verify'] = m.group(4)
        sasi[l] = d
        P(f'{l}: ' + json.dumps(d))
        expect(f'{l}: both indexes built, verify queries OK, no ERROR lines', all(v.get('done') and v.get('verify') == 'OK' for v in d.values()) and not re.search(r'^ERROR', a['errors'], re.M), json.dumps({k: (v.get('done'), v.get('verify')) for k, v in d.items()}))
    S1, S5, T1, T5, K = (sasi.get(k) for k in ('S-1M', 'S-500k', 'T124-1M', 'T124-500k', 'ctl-opt16'))
    if S1:
        c = S1['c_idx']['bytes']
        exp = (math.ceil(1_000_000 / 248) + 17) * 4096
        expect('S-1M c_idx file bytes ~ (ceil(1e6/248) leaves + ~17 interior) x 4096 = 16.6 MB within 10 % (one suffix term holds all tokens)', abs(c - exp) <= 0.10 * exp, f'{c} vs {exp} ({c / 1e6:.2f} B per token)')
    if S1 and S5:
        r = S1['c_idx']['bytes'] / S5['c_idx']['bytes']
        expect('c_idx bytes grow with rows (1M / 500k within 1.8 .. 2.2), no plateau', 1.8 <= r <= 2.2, f'{r:.2f}')
        P(f"INFO u_idx bytes (unique terms, PREFIX) 1M / 500k: {S1['u_idx']['bytes']} / {S5['u_idx']['bytes']} = {S1['u_idx']['bytes'] / S5['u_idx']['bytes']:.2f}")
    if S1 and T1:
        r = T1['c_idx']['bytes'] / S1['c_idx']['bytes']
        expect('T124-1M c_idx bytes about twice S-1M (1.8 .. 2.2): the constant sets the block count only', 1.8 <= r <= 2.2, f'{r:.2f}')
        h = abs(T1['c_idx']['heap'] - S1['c_idx']['heap']) / S1['c_idx']['heap']
        expect('c-index build peak heap of T124-1M within 20 % of S-1M (peak between GCs is noisy; reported)', h <= 0.20, f"{T1['c_idx']['heap'] / MIB:.0f} vs {S1['c_idx']['heap'] / MIB:.0f} MiB ({h:.1%})")
    if S1 and K:
        sg, kg = S1['c_idx']['segs'], K['c_idx']['segs']
        hk, hs = K['c_idx']['heap'], S1['c_idx']['heap']
        P(f"INFO control: option 16 -> {kg} temp-segment files seen, heap peak {hk / MIB:.0f} MiB; option 1024 -> {sg}, {hs / MIB:.0f} MiB")
        expect('control moves: the 16 MiB option flushes more segment files than 1024 AND the heap peak is lower', kg > sg and hk < hs, f'{kg} vs {sg}; {hk / MIB:.0f} vs {hs / MIB:.0f} MiB')
P(f'SUMMARY mismatches={fails} arms={len(arms)}')
