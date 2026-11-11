#!/usr/bin/env python3
"""Independent self-check of the UNIT RE-RUN ("run 1b", results §7) of
commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous, at the version re-frozen after the
`Amendment 2026-10-25 (after run 1, authorised by the user) — B2f (iii)`.
Copied from selfcheck.py (2026-10-25); the cluster part is removed (the cluster tier is closed and not re-run) and relation (iii)
is evaluated as amended: (a) every listed segment holding a buffer is a MappedByteBuffer of capacity S; (b) the spare, if present,
holds a buffer; (c) p <= m <= n_active + p. Run 1's wording of (iii) is printed as INFO only.
Re-reads the raw files (p1-*.out, stage4.out; not summary.txt).
usage: selfcheck-unit-rerun.py <unit log dir>
"""
import csv, glob, os, re, sys

U = sys.argv[1]
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
    print('%-58s INFO   run-1 wording (every listed buffer mapped, cap S): %d of %d segment lines without a mapping of S' % ('unit %s (iii) as frozen in run 1' % cfg, len(notmapped), len(segs)))
    okc = True; notes = []
    for tg in ('after-workload', 'end'):
        ss = [s for s in segs if s['tag'] == tg]
        act = [s for s in ss if s['role'] == 'active']; sp = [s for s in ss if s['role'] == 'spare']
        withbuf = [s for s in ss if int(s['capacity']) != -1]
        a_bad = [s for s in withbuf if s['mapped'] != 'true' or int(s['capacity']) != S]
        nobuf_bad = [s for s in ss if int(s['capacity']) == -1 and s['mapped'] != 'false']
        b_bad = [s for s in sp if int(s['capacity']) == -1 or s['mapped'] != 'true']
        p = len(sp); m = sum(1 for s in ss if s['mapped'] == 'true')
        c_ok = p <= m <= len(act) + p and p <= 1
        ok = bool(ss) and not a_bad and not nobuf_bad and not b_bad and c_ok
        okc = okc and ok
        notes.append('%s: active=%d spare=%d m=%d nobuf=%d (a)bad=%d (b)bad=%d (c)%s caps=%s' % (tg, len(act), p, m, len(ss) - len(withbuf), len(a_bad), len(b_bad),
                     'ok' if c_ok else 'FAIL', sorted(set(int(s['capacity']) for s in withbuf))))
    check('unit %s (iii) amended (a)(b)(c)' % cfg, okc, '; '.join(notes))
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


print('\nSELFCHECK %d relations: %d hold, %d fail: %s' % (len(res), sum(1 for _, o in res if o), sum(1 for _, o in res if not o), [n for n, o in res if not o]))
