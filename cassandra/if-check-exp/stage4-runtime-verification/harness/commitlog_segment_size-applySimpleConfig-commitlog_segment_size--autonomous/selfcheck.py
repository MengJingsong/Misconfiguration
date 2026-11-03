#!/usr/bin/env python3
"""Independent self-check (results §5) of commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous.
Re-reads the raw files (not summary.txt, not readings.txt) and re-evaluates every frozen relation of B2f/B2h and B3f/B3h.
usage: selfcheck.py <unit log dir> <cluster run dir>
"""
import csv, glob, os, re, sys

U, K = sys.argv[1], sys.argv[2]
MIB = 1 << 20
res = []


def check(name, ok, note):
    res.append((name, ok))
    print('%-58s %s  %s' % (name, 'HOLDS' if ok else 'FAILS', note))


# ---------------- unit: ConfigProbe (raw p1-*.out) ----------------
def p1(tag):
    for l in open(os.path.join(U, 'p1-%s.out' % tag), errors='replace'):
        if l.startswith('OK ') or l.startswith('REJECT '):
            return l.strip()
    return ''

exp = {'0MiB': ('REJECT', 'commitlog_segment_size must be positive, but was 0MiB'),
       '2048MiB': ('REJECT', 'commitlog_segment_size must be smaller than 2048, but was 2048MiB'),
       '512KiB': ('REJECT', 'Invalid data storage: 512KiB'),
       '1MiB': ('OK', 'getCommitLogSegmentSize=1048576'), '32MiB': ('OK', 'getCommitLogSegmentSize=33554432'),
       '2047MiB': ('OK', 'getCommitLogSegmentSize=2146435072'),
       '1MiB-mms': ('OK', 'getMaxMutationSize=524288'), '32MiB-mms': ('OK', 'getMaxMutationSize=16777216'),
       '2047MiB-mms': ('OK', 'getMaxMutationSize=1073217536')}
for tag, (kind, text) in exp.items():
    l = p1(tag)
    check('unit P1 %s' % tag, l.startswith(kind) and text in l, l[:110])

# ---------------- unit: mechanism (raw stage4.out) ----------------
lines = [l.rstrip('\n') for l in open(os.path.join(U, 'stage4.out'))]
def kv(l):
    return dict(re.findall(r'(\w[\w.]*)=(\S+)', l))
cfgs = {'2MiB': (2 * MIB, MIB), '8MiB': (8 * MIB, 4 * MIB), '32MiB': (32 * MIB, 16 * MIB), '2MiB+mms512KiB': (2 * MIB, 524288)}
for cfg, (S, mms) in cfgs.items():
    L = [l for l in lines if l.startswith('STAGE4 %s ' % cfg)]
    run = kv([l for l in L if ' run ' in l][0])
    check('unit %s (i) read-back' % cfg, int(run['S']) == S and int(run['maxMutation']) == mms and int(run['IMutation.MAX_MUTATION_SIZE']) == mms
          and run['accessMode'] == 'mmap' and run['segmentClass'] == 'MemoryMappedSegment', 'S=%s mms=%s mode=%s' % (run['S'], run['maxMutation'], run['accessMode']))
    flines = [kv(l) for l in L if ' file tag=' in l and l.split()[2] == 'file']
    tags = sorted(set(f['tag'] for f in flines if f['tag'] != 'before-workload'))
    badf = [f for f in flines if f['tag'] in ('after-workload', 'end') and int(f['length']) != S and not (int(f['length']) == 0 and int(f.get('reread_after_1s', -1)) == S)]
    check('unit %s (ii) every file length = S' % cfg, not badf and len(tags) == 2, '%d file lines at the two readings, %d not S' % (len([f for f in flines if f['tag'] != 'before-workload']), len(badf)))
    segs = [kv(l) for l in L if l.split()[2] == 'segment' and 'tag=before' not in l]
    notmapped = [s for s in segs if s['mapped'] != 'true' or int(s['capacity']) != S]
    mapped_wrong = [s for s in segs if s['mapped'] == 'true' and int(s['capacity']) != S]
    check('unit %s (iii) every active+spare buffer mapped, cap S' % cfg, not notmapped,
          '%d segment lines; %d without a mapping of S (%d with capacity -1 = buffer null); mappings with a size other than S: %d'
          % (len(segs), len(notmapped), sum(1 for s in notmapped if s['capacity'] == '-1'), len(mapped_wrong)))
    fs = [kv(l) for l in L if l.split()[2] == 'files' and 'tag=before' not in l]
    sw = kv([l for l in L if ' workload ' in l][0])
    ok4 = all(int(f['onDiskSize']) == int(f['n']) * S for f in fs) and (int(sw['switches']) != 0 or all(int(f['onDiskSize']) // S >= 3 for f in fs))
    check('unit %s (iv) onDiskSize = n x S, k >= 3' % cfg, ok4, ' '.join('%s:n=%s,disk=%s' % (f['tag'], f['n'], f['onDiskSize']) for f in fs) + ' switches=' + sw['switches'])
    nw = int(sw['seg1']) - int(sw['seg0']) + 1
    check('unit %s (v) 4 <= n_w <= 6' % cfg, 4 <= nw <= 6 and int(sw['ok']) == int(sw['rows']) == 3 * S // 65536, 'n_w=%d (recomputed from seg ids) rows=%s ok=%s' % (nw, sw['rows'], sw['ok']))
    ins = {kv(l)['what']: kv(l) for l in L if l.split()[2] == 'insert'}
    rf, ac = ins['refused'], ins['accepted']
    m = re.search(r'oversized mutation \((\d+)/(\d+)\)', [l for l in L if 'what=refused' in l][0])
    exp_ref = (S // 2 - 65536) if mms != S // 2 else (S // 2 + 1024)
    exp_acc = (mms - 65536) if mms != S // 2 else (S // 2 - 65536)
    check('unit %s (vi) refused/accepted inserts' % cfg,
          rf['outcome'] == 'REFUSED' and rf['class'].endswith('MutationExceededMaxSizeException') and int(rf['delta']) == 1 and m is not None
          and int(m.group(2)) == mms and int(m.group(1)) > mms and int(rf['blob']) == exp_ref
          and ac['outcome'] == 'ACCEPTED' and int(ac['delta']) == 0 and ac['row_present'] == 'true' and int(ac['blob']) == exp_acc,
          'refused blob %s (%s/%s) delta %s; accepted blob %s delta %s row %s' % (rf['blob'], m.group(1) if m else '?', m.group(2) if m else '?', rf['delta'], ac['blob'], ac['delta'], ac['row_present']))

# ---------------- cluster (raw node.out, settings.txt, seg.files, jmx.csv, big.txt, stress.log) ----------------
for arm, msg in (('z0', 'commitlog_segment_size must be positive, but was 0MiB'), ('z2048', 'commitlog_segment_size must be smaller than 2048, but was 2048MiB')):
    D = os.path.join(K, arm)
    out = open(os.path.join(D, 'node.out'), errors='replace').read()
    sm = [l for l in open(os.path.join(K, 'summary.txt')) if l.startswith('REFUSAL %s ' % arm)]
    rc = re.search(r'rc=(\d+)', sm[0]).group(1) if sm else '?'
    check('cluster %s (i) start refused' % arm, msg in out and 'Startup complete' not in out and rc == '3', 'rc=%s message present=%s' % (rc, msg in out))

for arm, smib in (('s8', 8), ('s32', 32), ('s64', 64), ('lz4', 8)):
    D = os.path.join(K, arm); S = smib * MIB
    st = open(os.path.join(D, 'settings.txt')).read()
    seg = re.search(r'commitlog_segment_size\s*\|\s*(\S+)', st).group(1); mm = re.search(r'max_mutation_size\s*\|\s*(\S+)', st).group(1)
    sl = open(os.path.join(D, 'system.log'), errors='replace').read()
    mode = re.search(r'commitlog_disk_access_mode resolved to: (\w+)', sl)
    want_mode = 'standard' if arm == 'lz4' else 'mmap'
    check('cluster %s (ii) read-back' % arm, seg == '%dMiB' % smib and mm == '%dKiB' % (smib * 512) and mode and mode.group(1) == want_mode,
          'segment %s, max_mutation %s, mode %s' % (seg, mm, mode.group(1) if mode else None))
    samples = {}
    for l in open(os.path.join(D, 'seg.files')):
        ts, name, size, alloc = l.split()
        samples.setdefault(ts, {})[name] = int(size)
    order = sorted(samples, key=int)
    if arm != 'lz4':
        bad = 0; z = 0
        for i, ts in enumerate(order):
            for name, size in samples[ts].items():
                if size == S:
                    continue
                if size == 0 and i + 1 < len(order) and samples[order[i + 1]].get(name) == S:
                    z += 1
                    continue
                bad += 1
        n = sum(len(v) for v in samples.values())
        check('cluster %s (iii) every file st_size = S' % arm, bad == 0, '%d file-samples in %d samples, %d creation-instant zeros, %d other' % (n, len(order), z, bad))
        ids = sorted({int(re.search(r'-(\d+)\.log', nm).group(1)) for v in samples.values() for nm in v})
        sl_ = open(os.path.join(D, 'stress.log')).read()
        tp = re.search(r'Total partitions\s*:\s*([\d,]+)', sl_).group(1).replace(',', ''); te = re.search(r'Total errors\s*:\s*([\d,]+)', sl_).group(1).replace(',', '')
        check('cluster %s (vii) limit reached' % arm, ids[-1] - ids[0] + 1 >= 10 and tp == '2000000' and te == '0', 'id span %d, partitions %s, errors %s' % (ids[-1] - ids[0] + 1, tp, te))
    with open(os.path.join(D, 'jmx.csv')) as f:
        rows = [r for r in csv.reader(f) if r and r[0].isdigit()]
    tot = [int(r[1]) for r in rows]; cnt = [int(r[3]) for r in rows]; cap = [int(r[4]) for r in rows]
    if arm != 'lz4':
        pos = all(c > 0 and c % S == 0 for c in cap)
        eqn = sum(1 for c, n in zip(cap, cnt) if c == n * S)
        check('cluster %s (iv) mapped capacity = Count x S' % arm, pos and eqn >= 0.99 * len(rows), '%d samples; capacity positive multiple of S in all: %s; = Count x S in %d; max Count %d' % (len(rows), pos, eqn, max(cnt)))
        check('cluster %s (v) TotalCommitLogSize multiple of S' % arm, all(t % S == 0 for t in tot), '%d samples, max %.0f MiB (INFO; commitlog_total_space 1024 MiB)' % (len(tot), max(tot) / MIB))
    else:
        check('cluster lz4 control (a) mapped capacity 0', all(c == 0 for c in cap), '%d samples, max capacity %d' % (len(cap), max(cap)))
        below = sum(1 for v in samples.values() for s in v.values() if s < S)
        check('cluster lz4 control (b) some file < S', below > 0, '%d file-samples below S; max file %d (INFO)' % (below, max(s for v in samples.values() for s in v.values())))
    big = {}
    for l in open(os.path.join(D, 'big.txt')):
        d = dict(re.findall(r'(\w+)=(\S+)', l.split(' msg=')[0])); d['msg'] = l.split(' msg=', 1)[1] if ' msg=' in l else ''; big[d['what']] = d
    rf, ac = big.get('refused', {}), big.get('accepted', {})
    m = re.search(r'oversized mutation \((\d+)/(\d+)\)', rf.get('msg', ''))
    ok6 = (rf.get('outcome') == 'REFUSED' and rf.get('exc') == 'InvalidRequest' and m and int(m.group(2)) == S // 2 and rf.get('delta') == '1'
           and int(rf.get('blob', 0)) == S // 2 + MIB and ac.get('outcome') == 'ACCEPTED' and ac.get('delta') == '0' and ac.get('row_present') == 'True'
           and int(ac.get('blob', 0)) == S // 2 - MIB)
    check('cluster %s (vi)%s inserts at S/2 +- 1 MiB' % (arm, ' / control (c)' if arm == 'lz4' else ''), bool(ok6),
          'refused %s (%s) delta %s; accepted %s delta %s row %s' % (rf.get('blob'), m.group(0) if m else rf.get('msg', '')[:60], rf.get('delta'), ac.get('blob'), ac.get('delta'), ac.get('row_present')))

print('\nSELFCHECK %d relations: %d hold, %d fail: %s' % (len(res), sum(1 for _, o in res if o), sum(1 for _, o in res if not o), [n for n, o in res if not o]))
