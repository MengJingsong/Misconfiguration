#!/usr/bin/env python3
"""Independent self-check of run 1, max_value_size-read-maxValueSize (stage 4, long path, 2026-10-14).

Re-parses the raw files only -- the unit test's STAGE4 lines (guard.out), the range controls' and upstream test's JUnit XML,
and per cluster run the client lines in session.log, the Byteman trace alloc.trace, the copied system.log and the raw
`nodetool tablestats` output -- and re-applies the frozen 9a predictions (section 9 hash d37c7234...). It never reads
summary.txt or readings.csv, the run script's own verdicts. Prints one line per check and a final count; exit 1 on a failure.

usage: selfcheck.py [logroot]      (default ~/stage4-logs/mvs)
"""
import calendar, glob, os, re, sys, time
import xml.etree.ElementTree as ET

ROOT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/stage4-logs/mvs')
MIB = 1048576
EPS = 65536
DEFAULT = 268435456
VALUES = {'1m': MIB, '4m': 4 * MIB, '8m': 8 * MIB}
DEFAULT_ROW = 15728640
REPLAY_ROW = 2097152
GUARD = re.compile(r'Corrupt value length (\d+) encountered, as it exceeds the maximum of (\d+)')

results = []


def chk(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(f'{"ok  " if cond else "FAIL"} {name}' + (f'  [{detail}]' if detail else ''))
    return bool(cond)


def read(p):
    with open(p, errors='replace') as f:
        return f.read()


# ------------------------------------------------------------------ parsers

def session_ops(path):
    """the client calls in session.log, in order: (epoch_s, args, ok, class, body_text) plus the raw nodetool commands"""
    ops, cmds = [], []
    lines = read(path).splitlines()
    for i, l in enumerate(lines):
        m = re.match(r'\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] \+ (.*)$', l)
        if not m:
            continue
        t = time.mktime(time.strptime(m.group(1), '%Y-%m-%d %H:%M:%S'))   # node local time, as the run script wrote it
        cmd = m.group(2)
        if cmd.startswith('send-value.py '):
            args = cmd.split()[1:]
            res = next((x for x in lines[i + 1:i + 4] if x.startswith('OK ') or x.startswith('ERR ')), 'ERR none')
            ok = res.startswith('OK ')
            cls = None if ok else res.split(' ', 2)[1]
            ln = re.search(r'"length": (\d+|null)', res)
            ops.append({'t': t, 'args': args, 'ok': ok, 'class': cls, 'line': res,
                        'length': int(ln.group(1)) if ln and ln.group(1) != 'null' else None})
        else:
            # the command's raw output follows until the next timestamped line
            out = []
            for x in lines[i + 1:]:
                if re.match(r'\[\d{4}-', x):
                    break
                out.append(x)
            cmds.append({'t': t, 'cmd': cmd, 'out': '\n'.join(out)})
    return ops, cmds


def trace(path):
    rows = []
    if os.path.exists(path):
        for l in read(path).splitlines():
            m = re.match(r'alloc class=(\S+) length=(\d+) thread=(.*) ms=(\d+)$', l.strip())
            if m:
                rows.append({'class': m.group(1), 'length': int(m.group(2)), 'thread': m.group(3), 's': int(m.group(4)) / 1000})
    return rows


def log_entries(path):
    """system.log entries: a level line plus its continuation lines; time in epoch seconds (the log is UTC)"""
    ents, cur = [], None
    for l in read(path).splitlines() if os.path.exists(path) else []:
        m = re.match(r'(ERROR|WARN|INFO|DEBUG|TRACE)\s+\[([^\]]*)\] (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3}) (\S+) - (.*)$', l)
        if m:
            cur = {'level': m.group(1), 'thread': m.group(2),
                   's': calendar.timegm(time.strptime(m.group(3), '%Y-%m-%dT%H:%M:%S')) + int(m.group(4)) / 1000,
                   'where': m.group(5), 'text': m.group(6)}
            ents.append(cur)
        elif cur is not None:
            cur['text'] += '\n' + l
    return ents


def window(ops, i, end=None):
    """[start of op i, start of the next op) in epoch seconds; the session log has whole seconds"""
    a = ops[i]['t']
    b = ops[i + 1]['t'] if i + 1 < len(ops) else (end if end is not None else a + 3600)
    return a, b


def find(ops, args, after=0):
    for i in range(after, len(ops)):
        if ops[i]['args'] == args:
            return i
    return None


# ------------------------------------------------------------------ unit tier

def unit():
    print('== unit: harness test (re-applied to the STAGE4 note lines)')
    U = f'{ROOT}/unit'
    g = read(f'{U}/guard.out')
    checks = [l for l in g.splitlines() if l.startswith('STAGE4 check ')]
    chk('unit: the harness printed its check lines, none MISMATCH', checks and not any(l.endswith('MISMATCH') for l in checks),
        f'{len(checks)} checks')
    chk('unit: STAGE4 done mismatches=0', 'STAGE4 done mismatches=0' in g)
    m = re.search(r'STAGE4 check readback.before_any_set (\d+) (\d+)', g)
    chk('unit: read-back before any set = 268435456', m and int(m.group(2)) == DEFAULT)
    notes = {}
    for l in g.splitlines():
        mm = re.match(r'STAGE4 note (\S+) (\S+)(?: root=(\S+): (.*?))? delta=(-?\d+)$', l)
        if mm:
            notes[mm.group(1)] = {'type': mm.group(2), 'root': mm.group(3), 'msg': mm.group(4) or '', 'delta': int(mm.group(5))}
    vals = {}
    for l in g.splitlines():
        mm = re.match(r'STAGE4 check (\S+) (\S+) (\S+) (ok|MISMATCH)$', l)
        if mm:
            vals[mm.group(1)] = mm.group(3)
    guard = lambda l, M: (f'Corrupt value length {l} encountered, as it exceeds the maximum of {M}, '
                          'which is set via max_value_size in cassandra.yaml')
    for M in (MIB, 4 * MIB, 8 * MIB, DEFAULT):
        p = f'M{M}.'
        chk(f'{p}read-back = M', vals.get(p + 'readback.getMaxValueSize') == str(M))
        for site in ('check.readBuffer', 'array.readArray', 'clustering'):
            a = notes.get(f'{p}{site}.l=M')
            chk(f'{p}{site} l=M: EOFException after M <= delta <= M+eps', a and a['type'] == 'java.io.EOFException'
                and M <= a['delta'] <= M + EPS, a and a['delta'])
            r = notes.get(f'{p}{site}.l=M+1')
            chk(f'{p}{site} l=M+1: guard IOException with both operands, delta < eps', r and r['type'] == 'java.io.IOException'
                and r['msg'] == guard(M + 1, M) and r['delta'] < EPS, r and r['delta'])
        r = notes.get(f'{p}check.readBuffer.l=2147483647')
        chk(f'{p}l=2^31-1: guard, delta < eps', r and r['msg'] == guard(2147483647, M) and r['delta'] < EPS)
        r = notes.get(f'{p}check.readBuffer.l=2147483648')
        chk(f'{p}l=2^31: VIntOutOfRangeException, delta < eps', r and r['type'].endswith('VIntCoding$VIntOutOfRangeException')
            and r['delta'] < EPS)
        r = notes.get(f'{p}check.readBuffer.vint=2^64-1')
        chk(f'{p}vint 2^64-1: negative-length IOException, delta < eps', r and r['type'] == 'java.io.IOException'
            and r['msg'] == 'Corrupt (negative) value length encountered' and r['delta'] < EPS)
        chk(f'{p}fixed-length control returned 4 bytes', vals.get(p + 'control.fixed_length.Int32Type_limit0.returned_bytes') == '4')
        r = notes.get(f'{p}control.limit0.BytesType_l=1')
        chk(f'{p}limit 0, l=1: guard 1/0', r and r['msg'] == guard(1, 0) and r['delta'] < EPS)
        r = notes.get(f'{p}control.skip.l=M+1')
        chk(f'{p}skip l=M+1: EOFException, not the guard, delta < eps', r and r['type'] == 'java.io.EOFException'
            and not r['msg'].startswith('Corrupt value length') and r['delta'] < EPS, r and r['delta'])
        r = notes.get(f'{p}control.sibling.readWithVIntLength.l=M+1')
        chk(f'{p}sibling l=M+1: EOFException after M+1 <= delta <= M+1+eps (bypass)', r and r['type'] == 'java.io.EOFException'
            and not r['msg'].startswith('Corrupt value length') and M + 1 <= r['delta'] <= M + 1 + EPS, r and r['delta'])
        if M == DEFAULT:
            continue
        for kind in ('mutation', 'local_response'):
            a = notes.get(f'{p}{kind}.payload=M')
            chk(f'{p}{kind} of M bytes returned, cell length M, delta >= M', a and a['type'] == 'returned' and a['delta'] >= M
                and vals.get(f'{p}{kind}.payload=M.cell_length') == str(M), a and a['delta'])
            r = notes.get(f'{p}{kind}.payload=M+1')
            chk(f'{p}{kind} of M+1: IOError caused by the guard, delta < eps', r and r['type'] == 'java.io.IOError'
                and r['root'] == 'java.io.IOException' and r['msg'] == guard(M + 1, M) and r['delta'] < EPS, r and r['delta'])
        if M == MIB:
            r = notes.get(f'{p}live.2MiB_under_1MiB')
            chk(f'{p}live: 2 MiB refused under 1 MiB', r and r['msg'] == guard(2097152, MIB))
            chk(f'{p}live: same bytes accepted after setMaxValueSize(4 MiB)', vals.get(p + 'live.2MiB_under_4MiB.cell_length') == '2097152')
    chk('unit: limit restored at the end', re.search(r'STAGE4 check restored (\d+) \1 ok', g) is not None)

    print('== unit: range controls and upstream')
    for label, msg in (('range-hi', 'max_value_size must be smaller than 2048, but was 2048MiB'),
                       ('range-zero', 'max_value_size must be positive')):
        x = read(f'{U}/{label}.TEST.xml') if os.path.exists(f'{U}/{label}.TEST.xml') else ''
        a = read(f'{U}/{label}.ant.log') if os.path.exists(f'{U}/{label}.ant.log') else ''
        o = read(f'{U}/{label}.out') if os.path.exists(f'{U}/{label}.out') else ''
        chk(f'{label}: ConfigurationException "{msg}" and no STAGE4 check line', msg in x + a and 'STAGE4 check' not in o)
    x = glob.glob(f'{U}/TEST-org.apache.cassandra.io.sstable.SSTableWriterTest.xml')
    if chk('upstream SSTableWriterTest XML present', x):
        s = ET.parse(x[0]).getroot()
        tc = [c for c in s.iter('testcase') if (c.get('name') or '').startswith('testValueTooBigCorruption')]
        chk('upstream: 5 tests, 0 failures, 0 errors', s.get('tests') == '5' and s.get('failures') == '0' and s.get('errors') == '0',
            f'tests={s.get("tests")} failures={s.get("failures")} errors={s.get("errors")}')
        chk('upstream: testValueTooBigCorruption ran and passed', tc and not any(c.tag in ('failure', 'error', 'skipped') for c in tc[0]))


# ------------------------------------------------------------------ cluster tier

def phase1(label, M):
    print(f'== cluster {label} (M={M})')
    D = f'{ROOT}/{label}'
    ops, cmds = session_ops(f'{D}/session.log')
    tr = trace(f'{D}/alloc.trace')
    ents = log_entries(f'{D}/system.log')
    B1, B2 = M + 1, M + 65536
    flushes = [c for c in cmds if c['cmd'] == 'bin/nodetool flush ks1 t']
    chk(f'{label}: two flushes of ks1.t', len(flushes) == 2)
    tflush = flushes[1]['t'] if len(flushes) == 2 else None
    # control
    i0, i99 = find(ops, ['readback', '0']), find(ops, ['readback', '99'])
    chk(f'{label} control: readback 0 = 1024, readback 99 = 307200', ops[i0]['length'] == 1024 and ops[i99]['length'] == 307200)
    n307 = sum(1 for r in tr if r['length'] == 307200)
    chk(f'{label} control: trace has >= 1 line of 307,200 and none of 1,024', n307 >= 1 and not any(r['length'] == 1024 for r in tr),
        f'{n307} of 307200')
    # idle: no trace line before the first client insert
    first_insert = ops[find(ops, ['insert', '0', '1024'])]['t']
    chk(f'{label} idle: no trace line before the first insert', not any(r['s'] < first_insert for r in tr))
    # writes
    for pk, n in (('1', M), ('2', B1), ('3', B2)):
        i = find(ops, ['insert', pk, str(n)])
        chk(f'{label} write pk {pk} ({n} B) acknowledged', i is not None and ops[i]['ok'])
    # scenario C
    md = [c for c in cmds if c['cmd'] == 'bin/nodetool tablestats ks1.t']
    mds = int(re.search(r'Memtable data size:\s*(\d+)', md[0]['out']).group(1)) if md and 'Memtable data size' in md[0]['out'] else None
    lo = 3 * M + 65537
    chk(f'{label} C: Memtable data size in [3M+65537, +eps)', mds is not None and lo <= mds < lo + EPS, f'{mds} in [{lo}, {lo + EPS})')
    t_c1 = ops[find(ops, ['readback', '1'])]['t']
    chk(f'{label} C: no trace line of M / M+1 / M+65536 before the first read of pk 1',
        not any(r['length'] in (M, B1, B2) and r['s'] < t_c1 for r in tr))
    c_reads = [i for i, o in enumerate(ops) if o['args'][0] == 'readback' and o['args'][1] in ('1', '2', '3') and o['t'] < tflush]
    post = [i for i, o in enumerate(ops) if o['args'][0] == 'readback' and o['args'][1] in ('1', '2', '3') and o['t'] > tflush]
    chk(f'{label} C: three reads before the second flush, four after (A, B1, B2, separation)', len(c_reads) == 3 and len(post) == 4,
        f'{len(c_reads)} / {len(post)}')
    pre_tr = [r for r in tr if r['s'] < tflush]
    chk(f'{label} C: readback 1 before the flush = M with exactly one trace line of M before the flush',
        ops[c_reads[0]]['ok'] and ops[c_reads[0]]['length'] == M and sum(1 for r in pre_tr if r['length'] == M) == 1)
    pre_ent = [e for e in ents if ops[c_reads[0]]['t'] <= e['s'] < tflush]
    post_ent = [e for e in ents if e['s'] >= tflush]
    for i, l in zip(c_reads[1:], (B1, B2)):
        o = ops[i]
        g = GUARD.search(o['line'])
        chk(f'{label} C: readback of {l} before the flush -> ServerError carrying {l}/{M}',
            (not o['ok']) and o['class'] == 'ServerError' and g and (int(g.group(1)), int(g.group(2))) == (l, M))
        e = [x for x in pre_ent if f'Corrupt value length {l} encountered, as it exceeds the maximum of {M}' in x['text']]
        chk(f'{label} C: system.log has the guard line for {l} under "Unexpected exception during request", no CorruptSSTableException',
            e and all('Unexpected exception during request' in x['text'] and 'CorruptSSTableException' not in x['text'] for x in e),
            f'{len(e)} entr(ies) at {sorted({x["where"] for x in e})}')
    chk(f'{label} C: no CorruptSSTableException before the second flush', not any('CorruptSSTableException' in e['text'] for e in pre_ent))
    gm = [int(m.group(2)) for e in ents for m in GUARD.finditer(e['text'])]
    chk(f'{label}: limit read back from the refusals = M', gm and set(gm) == {M}, sorted(set(gm)))
    # scenario A, B, separation
    a, b1, b2, sep = post[0], post[1], post[2], post[3]
    chk(f'{label} A: readback 1 after the flush = M', ops[a]['ok'] and ops[a]['length'] == M)
    for i, l in ((b1, B1), (b2, B2)):
        o = ops[i]
        chk(f'{label} B: readback of {l} after the flush -> ReadFailure', (not o['ok']) and o['class'] == 'ReadFailure')
        w0, w1 = window(ops, i)
        e = [x for x in ents if w0 <= x['s'] < w1 + 1 and f'Corrupt value length {l} encountered, as it exceeds the maximum of {M}' in x['text']]
        chk(f'{label} B: guard line for {l}/{M} inside a CorruptSSTableException', e and any('CorruptSSTableException' in x['text'] for x in e),
            f'{len(e)} entr(ies)')
    chk(f'{label} separation: readback 1 = M after the refused reads', ops[sep]['ok'] and ops[sep]['length'] == M)
    chk(f'{label}: the reads after the flush are pk 1, 2, 3, 1 in that order', [ops[x]['args'][1] for x in post] == ['1', '2', '3', '1'])
    post_tr = [r for r in tr if r['s'] >= tflush]
    nM = sum(1 for r in post_tr if r['length'] == M)
    chk(f'{label} A: trace lines of M after the flush >= 1 per accepted read (A and separation)', nM >= 2, f'{nM} lines')
    chk(f'{label}: no trace line of M+1 or M+65536 in the whole run', not any(r['length'] in (B1, B2) for r in tr))
    big = sorted({r['length'] for r in tr if r['length'] not in (307200, M)})
    chk(f'{label}: no other large length in the trace', not big, big)
    readable = [o['length'] for o in (ops[x] for x in post) if o['ok']]
    return max(readable) if readable else None


def default_arm():
    print('== cluster default')
    D = f'{ROOT}/default'
    ops, cmds = session_ops(f'{D}/session.log')
    tr = trace(f'{D}/alloc.trace')
    flushes = [c for c in cmds if c['cmd'] == 'bin/nodetool flush ks1 t']
    w = find(ops, ['insert', '1', str(DEFAULT_ROW)])
    chk('default: 15,728,640 B row acknowledged', w is not None and ops[w]['ok'])
    reads = [i for i, o in enumerate(ops) if o['args'] == ['readback', '1']]
    chk('default: two reads of pk 1, one each side of the second flush', len(reads) == 2 and len(flushes) == 2
        and ops[reads[0]]['t'] < flushes[1]['t'] < ops[reads[1]]['t'])
    chk('default: both reads return 15,728,640', all(ops[i]['ok'] and ops[i]['length'] == DEFAULT_ROW for i in reads))
    chk('default: no trace line of the row before its first read', not any(r['length'] == DEFAULT_ROW and r['s'] < ops[reads[0]]['t'] for r in tr))
    pre = sum(1 for r in tr if r['length'] == DEFAULT_ROW and r['s'] < flushes[1]['t'])
    post = sum(1 for r in tr if r['length'] == DEFAULT_ROW and r['s'] >= flushes[1]['t'])
    chk('default: one trace line of the row before the flush (local response), >= 1 after', pre == 1 and post >= 1, f'{pre} / {post}')
    chk('default: system.log has no "Corrupt value length"', 'Corrupt value length' not in read(f'{D}/system.log'))
    return DEFAULT_ROW


def compaction():
    print('== compaction arm (1 MiB)')
    D = f'{ROOT}/compaction'
    ops, cmds = session_ops(f'{D}/session.log')
    ents = log_entries(f'{D}/system.log')
    chk('compaction: the three writes acknowledged', all(o['ok'] for o in ops if o['args'][0] == 'insert'))
    comp = [c for c in cmds if c['cmd'].startswith('bin/nodetool compact ')]
    chk('compaction: three nodetool compact calls (ok, t, t)', [c['cmd'] for c in comp] ==
        ['bin/nodetool compact ks1 ok', 'bin/nodetool compact ks1 t', 'bin/nodetool compact ks1 t'])
    rc = [int(m.group(1)) if (m := re.search(r'rc=(-?\d+)\s*$', c['out'])) else None for c in comp]
    chk('compaction: exit codes 0 (ok), non-zero (1st t), 0 (2nd t)', rc[0] == 0 and rc[1] not in (0, None) and rc[2] == 0, rc)
    t1, t2 = comp[1]['t'], comp[2]['t']
    okc = [e for e in ents if 'Compacted' in e['text'] and '/ok-' in e['text'] and e['s'] >= comp[0]['t'] - 1]
    chk('compaction control: ks1.ok compacted (a "Compacted" line for its directory)', okc, len(okc))
    first = [e for e in ents if t1 <= e['s'] < t2 + 1 and 'Corrupt value length 1048577 encountered, as it exceeds the maximum of 1048576' in e['text']]
    chk('1st compact t: guard 1048577/1048576 in a CorruptSSTableException with a compaction frame',
        first and any('CorruptSSTableException' in e['text'] and re.search(r'at org\.apache\.cassandra\.db\.compaction\.', e['text']) for e in first),
        f'{len(first)} entr(ies)')
    chk('compact t: no "Compacted" line for ks1.t', not any('Compacted' in e['text'] and '/t-' in e['text'] for e in ents))
    second = [e for e in ents if e['s'] >= t2 and 'Corrupt value length' in e['text']]
    chk('2nd compact t: no new guard line', not second, len(second))
    # listings: written by the run script from os.listdir (no raw ls); read from compact-t-*.log windows and the notes
    s = read(f'{D}/session.log')
    lb = re.search(r"listing t before: (\[.*?\])", s); l1 = re.search(r"listing t after the 1st: (\[.*?\])", s)
    l2 = re.search(r"compact ks1 t \(2nd\).*listing after: (\[.*?\])", s)
    chk('compaction: t listing unchanged after both compactions, no _txn_ file (from the run script\'s listing lines)',
        lb and l1 and l2 and lb.group(1) == l1.group(1) == l2.group(1) and '_txn_' not in l1.group(1))
    r = [o for o in ops if o['args'] == ['readback', '1']]
    chk('compaction: readback 1 on t after the failed compaction = M', r and r[-1]['ok'] and r[-1]['length'] == MIB)


def replay():
    print('== replay arm (4 -> 1 -> 4 MiB)')
    D = f'{ROOT}/replay'
    ops, cmds = session_ops(f'{D}/session.log')
    chk('replay: 2 MiB row acknowledged and read back under 4 MiB', ops[find(ops, ['insert', '30', str(REPLAY_ROW)])]['ok']
        and ops[find(ops, ['readback', '30'])]['length'] == REPLAY_ROW)
    ls = [c for c in cmds if c['cmd'] == 'ls -l data/commitlog/']
    chk('replay: a commit-log segment before the kill', ls and 'CommitLog-' in ls[0]['out'])
    lg = read(f'{D}/replay-1m.log')
    chk('replay 1 MiB: "Corrupt value length 2097152 encountered, as it exceeds the maximum of 1048576"',
        'Corrupt value length 2097152 encountered, as it exceeds the maximum of 1048576' in lg)
    chk('replay 1 MiB: no "Startup complete" and no CQL listener', 'Startup complete' not in lg and 'Starting listening for CQL clients' not in lg)
    s = read(f'{D}/session.log')
    st = re.search(r'start replay-1m: (\w+) after', s)
    chk('replay 1 MiB: the process exited (run script start state)', st and st.group(1) == 'exited', st and st.group(1))
    chk('replay 1 MiB (9a sub-prediction): log has "Replay stopped. If you wish to override this error"',
        'Replay stopped. If you wish to override this error' in lg)
    chk('replay 1 MiB (diagnostic): log has "Exiting due to error while processing commit log during initialization"',
        'Exiting due to error while processing commit log during initialization' in lg)
    ctl = read(f'{D}/replay-ctl-4m.log')
    m = re.search(r'Log replay complete, (\d+) replayed mutations', ctl)
    chk('replay control 4 MiB: replay completes', m is not None, m and m.group(0))
    r = [o for o in ops if o['args'] == ['readback', '30']]
    chk('replay control 4 MiB: readback 30 = 2,097,152 after the restart', len(r) == 2 and r[-1]['ok'] and r[-1]['length'] == REPLAY_ROW)


def instrument():
    print('== instrument check')
    D = f'{ROOT}/instrument'
    if not chk('instrument: run folder present', os.path.isdir(D)):
        return
    ts = read(f'{D}/testscript.txt') if os.path.exists(f'{D}/testscript.txt') else ''
    chk('instrument: Byteman TestScript reports no errors', 'TestScript: no errors' in ts)
    ops, cmds = session_ops(f'{D}/session.log')
    p = [o for o in ops if o['args'] == ['probe']]
    chk('instrument: probe over protocol 4', p and all('"protocol": 4' in o['line'] for o in p))
    tr = trace(f'{D}/alloc.trace')
    chk('instrument: known-answer row traced (307,200), small row not (1,024)', any(r['length'] == 307200 for r in tr)
        and not any(r['length'] == 1024 for r in tr))
    st = [o for o in ops if o['args'] == ['settings']]
    print(f'     (secondary) system_views.settings: {st[0]["line"][:200] if st else "not run"}')


if __name__ == '__main__':
    instrument()
    unit()
    largest = {lab: phase1(lab, M) for lab, M in VALUES.items()}
    print('== dose-response')
    chk('largest value read back after the flush = M at 1, 4, 8 MiB (1 : 4 : 8)',
        all(largest[lab] == M for lab, M in VALUES.items()), largest)
    default_arm()
    compaction()
    replay()
    bad = [n for n, ok in results if not ok]
    print(f'\n{len(results) - len(bad)}/{len(results)} checks hold' + (f'; FAILED: {"; ".join(bad)}' if bad else ''))
    sys.exit(1 if bad else 0)
