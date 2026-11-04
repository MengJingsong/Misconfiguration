#!/usr/bin/env python3
"""Independent self-check of run 1 for max_mutation_size-applySimpleConfig-max_mutation_size--autonomous.
Re-reads the raw files (p1-*.out, stage4.out, TEST-*.xml; per cluster arm node.out, system.log, settings.txt, req.txt, stress.log,
jmx-stress.csv), not summary.txt, and re-evaluates every frozen relation of B2f/B2h and B3f/B3h (frozen sha256 e69f7208...).
usage: selfcheck.py <unit log dir> <cluster log dir>
"""
import glob, os, re, sys

U, K = sys.argv[1], sys.argv[2]
res = []


def rel(name, ok, note=''):
    res.append((name, bool(ok), note))


def rd(p):
    try:
        return open(p, errors='replace').read()
    except OSError:
        return ''


def kv(line):
    return dict(re.findall(r'(\w[\w.]*)=(\S+)', line))


# ---------------- unit, ConfigProbe ----------------
P1 = {'8MiB-4096KiB': 'OK getMaxMutationSize=4194304', '8MiB-unset': 'OK getMaxMutationSize=4194304',
      '32MiB-16384KiB': 'OK getMaxMutationSize=16777216', '32MiB-unset': 'OK getMaxMutationSize=16777216',
      '8MiB-4097KiB': 'REJECT ConfigurationException: commitlog_segment_size must be at least twice the size of max_mutation_size / 1024',
      '32MiB-16385KiB': 'REJECT ConfigurationException: commitlog_segment_size must be at least twice the size of max_mutation_size / 1024'}
for tag, exp in P1.items():
    lines = [l for l in rd(os.path.join(U, 'p1-%s.out' % tag)).splitlines() if l.startswith(('OK ', 'REJECT '))]
    got = lines[0] if lines else '(none)'
    rel('U P1 %s' % tag, got.startswith(exp), got[:150])

# ---------------- unit, mechanism ----------------
S4 = rd(os.path.join(U, 'stage4.out')).splitlines()
MV = {'1024KiB': 1048576, '1026KiB': 1050624, '2048KiB': 2097152, 'unset': 2621440}
for lab, M in MV.items():
    L = [l for l in S4 if l.startswith('STAGE4 %s ' % lab)]
    x = rd(os.path.join(U, 'TEST-%s.xml' % lab))
    m = re.search(r'tests="(\d+)".*?failures="(\d+)"|failures="(\d+)".*?tests="(\d+)"', x)
    rel('U %s test ran (TEST xml: 1 test, 0 failures, 0 errors)' % lab,
        re.search(r'errors="0"', x) and re.search(r'failures="0"', x) and re.search(r'tests="1"', x))
    run = [kv(l) for l in L if ' run ' in l]
    rel('U %s (i) read-back' % lab, run and run[0].get('S') == '5242880' and run[0].get('getMaxMutationSize') == str(M)
        and run[0].get('IMutation.MAX_MUTATION_SIZE') == str(M), str(run[:1]))
    ins = {kv(l)['what']: (kv(l), l) for l in L if ' insert ' in l}
    a, al = ins.get('A', ({}, ''))
    rel('U %s (ii) A accepted' % lab, a.get('blob') == str(M - 1024) and a.get('outcome') == 'ACCEPTED' and a.get('delta_count') == '0'
        and a.get('row_present') == 'true', al[:200])
    b, bl = ins.get('B', ({}, ''))
    mm = re.search(r'Rejected an oversized mutation \((\d+)/(\d+)\)', bl)
    rel('U %s (iii) B refused by the mutation check' % lab,
        b.get('blob') == str(M + 1024) and b.get('outcome') == 'REFUSED' and b.get('is_ire') == 'true' and b.get('mems_in_chain') == 'true'
        and mm and int(mm.group(2)) == M and int(mm.group(1)) > M and b.get('delta_count') == '1'
        and 0 <= int(b.get('allocated', '99999')) < 4096 and b.get('row_present') == 'false',
        'total=%s allocated=%s' % (mm.group(1) if mm else None, b.get('allocated')))
    srch = [ins[k] for k in sorted(ins) if k.startswith('search')]
    bd = [kv(l) for l in L if ' boundary ' in l]
    last = srch[-1][0] if srch else {}
    rel('U %s (iv) boundary: refusal at total M+1 within 6 tries' % lab,
        bd and bd[0].get('converged') == 'true' and len(srch) <= 6 and last.get('outcome') == 'REFUSED'
        and last.get('total') == str(M + 1) and last.get('delta_count') == '1' and last.get('row_present') == 'false',
        'tries=%d last_total=%s' % (len(srch), last.get('total')))
    e, el = ins.get('edge', ({}, ''))
    rel('U %s (iv) blob x-1 (total M) accepted' % lab,
        e.get('outcome') == 'ACCEPTED' and e.get('delta_count') == '0' and e.get('row_present') == 'true'
        and bd and int(e.get('blob', -1)) == int(bd[0].get('x', -9)) - 1,
        'edge blob=%s allocated=%s (INFO: = M is %s)' % (e.get('blob'), e.get('allocated'), e.get('allocated') == str(M)))
    d = {kv(l)['what']: (kv(l), l) for l in L if ' direct ' in l}
    o, ol = d.get('over', ({}, ''))
    rel('U %s (v) direct CommitLog.add over M refused at CommitLog.add' % lab,
        o.get('outcome') == 'REFUSED' and o.get('mems_in_chain') == 'true' and 'Mutation.validateSize<CommitLog.add' in o.get('frames', '')
        and o.get('delta_count') == '1' and 0 <= int(o.get('allocated', '99999')) < 4096 and int(o.get('total', 0)) > M,
        'total=%s frames=%s allocated=%s' % (o.get('total'), o.get('frames'), o.get('allocated')))
    un, ul = d.get('under', ({}, ''))
    rel('U %s (v) direct CommitLog.add under M accepted' % lab, un.get('outcome') == 'ACCEPTED' and un.get('delta_count') == '0',
        'INFO allocated=%s serialized+12=%s' % (un.get('allocated'), un.get('total')))
    wl = [kv(l) for l in L if ' workload ' in l]
    rel('U %s (vi) 50 near-limit inserts' % lab, wl and wl[0].get('ok') == '50' and wl[0].get('failed') == '0'
        and wl[0].get('delta_count') == '0' and int(wl[0].get('seg_advance', 0)) >= 2, str(wl[:1]))
# B2h control
c26 = [kv(l) for l in S4 if l.startswith('STAGE4 1026KiB ') and ' what=A ' in l]
c24 = [kv(l) for l in S4 if l.startswith('STAGE4 1024KiB ') and ' what=B ' in l]
rel('U B2h control: blob 1,049,600 refused under 1024KiB and accepted under 1026KiB',
    c26 and c24 and c26[0].get('blob') == '1049600' == c24[0].get('blob') and c26[0].get('outcome') == 'ACCEPTED'
    and c24[0].get('outcome') == 'REFUSED' and c26[0].get('row_present') == 'true')

# ---------------- cluster ----------------
a = os.path.join(K, 'a4097')
no = rd(os.path.join(a, 'node.out')) + rd(os.path.join(a, 'system.log'))
summ = rd(os.path.join(K, 'summary.txt'))
rcm = re.search(r'REFUSAL a4097 rc=(\d+) secs=(\d+)', summ)
rel('C (i) a4097 refused at start-up', rcm and rcm.group(1) == '3' and int(rcm.group(2)) <= 120 and 'Startup complete' not in no
    and 'commitlog_segment_size must be at least twice the size of max_mutation_size / 1024' in rd(os.path.join(a, 'node.out')),
    'rc=%s secs=%s' % (rcm.group(1) if rcm else None, rcm.group(2) if rcm else None))


def settings(arm):
    t = rd(os.path.join(K, arm, 'settings.txt'))
    return dict((m.group(1), m.group(2)) for m in re.finditer(r'^\s*(\w+)\s*\|\s*(\S+)', t, re.M))


def reqs(arm):
    return {kv(l)['what']: (kv(l), l) for l in rd(os.path.join(K, arm, 'req.txt')).splitlines() if l.startswith('REQ ')}


EXPM = {'m1024': '1024KiB', 'm2048': '2048KiB', 'mdef': '4096KiB'}
for arm, mv in EXPM.items():
    st = settings(arm)
    rel('C (ii) %s read-back' % arm, st.get('max_mutation_size') == mv and st.get('commitlog_segment_size') == '8MiB'
        and st.get('native_transport_max_message_size') == '64MiB', str(st))


def refused(arm, what, M):
    r, l = reqs(arm).get(what, ({}, ''))
    mm = re.search(r'Rejected an oversized mutation \((\d+)/(\d+)\)', l)
    rel('C (iii) %s %s refused by the mutation check' % (arm, what),
        r.get('outcome') == 'REFUSED' and r.get('exc') == 'InvalidRequest' and mm and int(mm.group(2)) == M and int(mm.group(1)) > M
        and r.get('delta_count') == '1' and abs(int(r.get('delta_content', '9999999'))) < 65536 and r.get('rows_present') == 'False',
        'total=%s dcount=%s dcontent=%s' % (mm.group(1) if mm else None, r.get('delta_count'), r.get('delta_content')))


def accepted(arm, what, tag='(iv)'):
    r, l = reqs(arm).get(what, ({}, ''))
    rel('C %s %s %s accepted' % (tag, arm, what),
        r.get('outcome') == 'ACCEPTED' and r.get('delta_count') == '0' and int(r.get('delta_content', '-9999999')) >= int(r.get('blob', 0)) - 65536
        and set(r.get('rows_present', 'False').split('/')) == {'True'},
        'blob=%s dcontent=%s' % (r.get('blob'), r.get('delta_content')))


refused('m1024', 'over', 1048576); accepted('m1024', 'under')
refused('m2048', 'over', 2097152); accepted('m2048', 'under')
refused('mdef', 'over', 4194304); accepted('mdef', 'under', '(vii)')
# (v) logged / unlogged batch at m1024
r, l = reqs('m1024').get('logged', ({}, ''))
sl = rd(os.path.join(K, 'm1024', 'system.log'))
bm = re.search(r'Failed to apply mutation locally[^\n]*\n[^\n]*MutationExceededMaxSizeException: Rejected an oversized mutation \((\d+)/1048576\) for keyspace: system\.', sl)
rel('C (v) m1024 logged batch refused at CommitLog.add (batchlog)',
    r.get('outcome') == 'REFUSED' and r.get('exc') == 'WriteFailure' and r.get('delta_count') == '1' and bm
    and r.get('rows_present') == 'False/False' and abs(int(r.get('delta_content', '9999999'))) < 65536
    and 'at org.apache.cassandra.db.commitlog.CommitLog.add' in sl,
    'batchlog total=%s dcontent=%s' % (bm.group(1) if bm else None, r.get('delta_content')))
r, l = reqs('m1024').get('unlogged', ({}, ''))
rel('C (v) m1024 unlogged batch accepted', r.get('outcome') == 'ACCEPTED' and r.get('delta_count') == '0' and r.get('rows_present') == 'True/True')
# (vi) stress
stl = rd(os.path.join(K, 'm1024', 'stress.log'))
tp = re.search(r'Total partitions\s*:\s*([\d,]+)', stl); te = re.search(r'Total errors\s*:\s*([\d,]+)', stl)
js = [l.split(',') for l in rd(os.path.join(K, 'm1024', 'jmx-stress.csv')).splitlines() if l[:1].isdigit()]
ov = {x[1] for x in js}
rel('C (vi) m1024 stress 2,000 partitions, 0 errors, OverSizedMutations unchanged',
    tp and tp.group(1).replace(',', '') == '2000' and te and te.group(1).replace(',', '') == '0' and len(ov) == 1 and len(js) >= 2,
    'partitions=%s errors=%s samples=%d oversized_values=%s' % (tp.group(1) if tp else None, te.group(1) if te else None, len(js), sorted(ov)))
# B3h control
accepted('m2048', 'control_1M+4K', 'B3h')
r, l = reqs('m2048').get('control_logged', ({}, ''))
rel('C B3h m2048 logged batch accepted', r.get('outcome') == 'ACCEPTED' and r.get('delta_count') == '0' and r.get('rows_present') == 'True/True')
# Invalid guard: no refusal in a counted arm by another check
other = sum(rd(os.path.join(K, x, 'req.txt')).count(s) for x in ('m1024', 'm2048', 'mdef') for s in ('CQL Message of size', 'Batch too large'))
rel('C no request in m1024/m2048/mdef refused by the transport or the batch-size guard', other == 0, 'count=%d' % other)

# INFO (not relations)
info = []
for arm, what in (('mdef', 'info_1M+4K'), ('tdef', 'info_over'), ('tdef', 'info_under')):
    r, l = reqs(arm).get(what, ({}, ''))
    info.append('INFO %s %s outcome=%s exc=%s dcount=%s msg=%s' % (arm, what, r.get('outcome'), r.get('exc'), r.get('delta_count'),
                                                                 (re.search(r'msg=(.*)', l).group(1)[:160] if l else '')))
info.append('INFO tdef settings %s' % settings('tdef'))

for n, ok, note in res:
    print('%-5s %s%s' % ('HOLDS' if ok else 'FAILS', n, ('  [' + note + ']') if note else ''))
for i in info:
    print(i)
print('TOTAL %d relations, %d hold, %d fail' % (len(res), sum(1 for r in res if r[1]), sum(1 for r in res if not r[1])))
