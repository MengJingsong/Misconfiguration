#!/usr/bin/env python3
"""Independent self-check of run 1, max_mutation_size-validateSize-MAX_MUTATION_SIZE.
Re-parses the RAW files on the node (session.log: every jmx.sh output and client line in order; system.log; the unit .out files),
recomputes each reading without the run script's code, checks it against the frozen §9a prediction, and compares with readings.csv.
usage (on the node): python3 selfcheck.py [~/stage4-logs/mms]      exit 0 iff every load-bearing check holds."""
import csv, json, os, re, sys

B = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/stage4-logs/mms')
VAL = {'1m': 1048576, '4m': 4194304, 'default': 16777216}
GUARD = re.compile(r'Rejected an oversized mutation \((\d+)/(\d+)\)')
fails, n = [], 0


def ck(name, cond, info=''):
    global n
    n += 1
    print(('ok   ' if cond else 'FAIL ') + name + ('  ' + str(info) if info else ''))
    if not cond:
        fails.append(name)


def events(run):
    """ordered list of ('jmx', attr, value) and ('client', args, status, body) from the raw session.log"""
    ev, lines = [], open(f'{B}/{run}/session.log', errors='replace').read().splitlines()
    i = 0
    while i < len(lines):
        l = lines[i]
        m = re.search(r'\+ \S*jmx\.sh "([^"]+)" (\w+)$', l)
        if m:
            j, val = i + 1, None
            while j < len(lines) and not lines[j].strip().startswith('rc='):
                if lines[j].strip():
                    nums = re.findall(r'-?\d+', lines[j])
                    val = int(nums[-1]) if nums else val
                j += 1
            ev.append(('jmx', m.group(2), val)); i = j; continue
        m = re.search(r'\+ send-mutation\.py (.*)$', l)
        if m and i + 1 < len(lines):
            r = lines[i + 1]
            st = 'OK' if r.startswith('OK ') else r.split(' ')[1] if r.startswith('ERR ') else '?'
            body = r[3:] if st == 'OK' else r.split(' ', 2)[2] if r.startswith('ERR ') else '{}'
            try:
                body = json.loads(body)
            except Exception:
                body = {}
            ev.append(('client', m.group(1).split(), st, body)); i += 2; continue
        i += 1
    return ev


def writes(run):
    """each insert/batch with the two JMX reads just before and just after it"""
    ev, out = events(run), []
    for idx, e in enumerate(ev):
        if e[0] == 'client' and e[1][0] in ('insert', 'batch'):
            before = [x for x in ev[:idx] if x[0] == 'jmx'][-2:]
            after = [x for x in ev[idx + 1:] if x[0] == 'jmx'][:2]
            g = {x[1]: x[2] for x in before}; h = {x[1]: x[2] for x in after}
            T, M = (None, None)
            mm = GUARD.search(e[3].get('message', '') or '')
            if mm:
                T, M = int(mm.group(1)), int(mm.group(2))
            out.append(dict(args=e[1], st=e[2], body=e[3], T=T, M=M,
                            dc=(h.get('ActiveContentSize') - g.get('ActiveContentSize')) if None not in (h.get('ActiveContentSize'), g.get('ActiveContentSize')) else None,
                            dov=(h.get('Count') - g.get('Count')) if None not in (h.get('Count'), g.get('Count')) else None))
    return out


def readbacks(run):
    return {int(e[1][1]): e[3] for e in events(run) if e[0] == 'client' and e[1][0] == 'readback'}


def csv_rows(run):
    return [r for r in csv.DictReader(open(f'{B}/{run}/readings.csv')) if r['step'] and not r['step'].startswith(('idle', 'readback'))]


# ---------------- unit tier
print('## unit')
for lab, M in (('256k', 262144), ('1m', 1048576), ('2m', 2097152), ('default', 2621440)):
    t = open(f'{B}/unit/{lab}.out').read()
    notes = dict(re.findall(r'STAGE4 note (\S+) (.*)', t))
    mism = re.findall(r'STAGE4 check (\S+) .* MISMATCH', t)
    ck(f'unit {lab}: no MISMATCH and done line', not mism and 'STAGE4 done mismatches=0' in t, mism)
    ck(f'unit {lab}: T(p*) = M and T(p*+1) = M+1', int(notes['T_p_star']) == M and int(notes['T_p_star_plus_1']) == M + 1)
    d = int(notes['add.at_limit.position_delta'])
    ck(f'unit {lab}: accepted add moves position by M or M+8', d in (M, M + 8), d)
    ck(f'unit {lab}: message carries (M+1/M)', f'({M + 1}/{M})' in notes['validate.over_limit.message'])
    for c in ('add.over_limit.position_delta 0 0', 'add.over_limit.meter_delta 1 1', 'add.over_limit.content_size_delta 0 0', 'counter.meter_delta 0 0'):
        ck(f'unit {lab}: {c.split()[0]} as predicted', f'STAGE4 check {c} ok' in t)
ck('unit range: no STAGE4 line (no test body ran)', not os.path.exists(f'{B}/unit/range.out') or 'STAGE4' not in open(f'{B}/unit/range.out').read())
rl = open(f'{B}/unit/range.ant.log', errors='replace').read()
ck('unit range: ConfigurationException with the §9a message', 'commitlog_segment_size must be at least twice the size of max_mutation_size / 1024' in rl)
ul = open(f'{B}/unit/upstream.ant.log', errors='replace').read()
m = re.search(r'GroupCommitLogTest\S* Tests run: (\d+), Failures: (\d+), Errors: (\d+)', ul)
ck('upstream GroupCommitLogTest green', m and m.group(2) == '0' and m.group(3) == '0', m.group(0) if m else None)

# ---------------- cluster, Phase 1
print('## cluster Phase 1')
largest = {}
for lab, M in VAL.items():
    w = {x['args'][1]: x for x in writes(lab) if x['args'][0] == 'insert'}
    rb = readbacks(lab)
    k = w['1']['T'] - int(w['1']['args'][2])
    ck(f'{lab}: calibration refused by the guard with M = value set', w['1']['M'] == M, (w['1']['T'], w['1']['M']))
    ck(f'{lab}: control 1 KiB rise in 1044..1536', 1044 <= w['0']['dc'] <= 1536, w['0']['dc'])
    a = w['2']
    ck(f'{lab}: A exact payload = M - k accepted', a['st'] == 'OK' and int(a['args'][2]) == M - k)
    ck(f'{lab}: A content rise = M + 8 (+ <64 KiB)', M + 8 <= a['dc'] < M + 8 + 65536, a['dc'])
    ck(f'{lab}: A meter unchanged', a['dov'] == 0)
    largest[lab] = a['dc'] - 8
    for pk in ('3', '4', '5'):
        x = w[pk]
        extra = x['T'] - int(x['args'][2]) - k if x['T'] else None
        ck(f'{lab}: B pk{pk} InvalidRequest, guard (T/M), M = value', x['st'] == 'InvalidRequest' and x['M'] == M, (x['T'], x['M']))
        ck(f'{lab}: B pk{pk} T - payload - k ' + ('= 0' if pk == '3' else 'in 0..4'), extra == 0 if pk == '3' else 0 <= extra <= 4, extra)
        ck(f'{lab}: B pk{pk} meter +1, content < 64 KiB', x['dov'] == 1 and abs(x['dc']) < 65536, (x['dov'], x['dc']))
    ck(f'{lab}: readback 0 = 1024, 2 = M - k', rb[0].get('length') == 1024 and rb[2].get('length') == M - k)
    ck(f'{lab}: no row for 1,3,4,5', all(rb[p].get('exists') is False for p in (1, 3, 4, 5)))
    # agreement with the run script's readings.csv
    rows = {r['command']: r for r in csv_rows(lab)}
    same = all(str(x['dc']) == rows[' '.join(x['args'])]['cs_delta'] for x in w.values())
    ck(f'{lab}: content deltas equal readings.csv', same)
r = [largest[k] for k in ('1m', '4m', 'default')]
ck('dose-response: largest accepted entry = M at each value, ratio 1 : 4 : 16', r == [1048576, 4194304, 16777216], r)

# ---------------- cluster, Phase 2
print('## cluster Phase 2')
for lab, M in VAL.items():
    run = f'{lab}-batch'
    w = {x['args'][1]: x for x in writes(run) if x['args'][0] == 'batch'}
    rb = readbacks(run)
    n_ = int(0.55 * M)
    u, g = w['unlogged'], w['logged']
    ck(f'{run}: unlogged OK, rise > M', u['st'] == 'OK' and u['dc'] > M, u['dc'])
    ck(f'{run}: unlogged rows read back', rb[10].get('length') == n_ and rb[11].get('length') == n_)
    ck(f'{run}: logged WriteFailure, meter +1, content < 64 KiB', g['st'] == 'WriteFailure' and g['dov'] == 1 and abs(g['dc']) < 65536, (g['st'], g['dov'], g['dc']))
    ck(f'{run}: logged rows absent', rb[12].get('exists') is False and rb[13].get('exists') is False)
    s = open(f'{B}/{run}/system.log', errors='replace').read()
    i = s.find('Failed to apply mutation locally')
    blk = s[i:i + 1500]
    mm = GUARD.search(blk)
    ck(f'{run}: system.log refusal names system/batches at CommitLog.add, M = value',
       i >= 0 and 'keyspace: system' in blk and 'batches.' in blk and 'CommitLog.add' in blk and mm and int(mm.group(2)) == M,
       mm.group(0) if mm else None)
    ck(f'{run}: batchlog entry T > M and about 2 x 0.55 M', mm and M < int(mm.group(1)) < 1.2 * M, mm.group(1) if mm else None)

# ---------------- derived-cap control
print('## derived')
w = {x['args'][1]: x for x in writes('derived') if x['args'][0] == 'insert'}
x = w['20']
ck('derived: transport refusal text, max 16777216', 'Request is too big' in (x['body'].get('message') or '') and 'maximum allowed length 16777216' in x['body']['message'])
ck('derived: meter unchanged, content < 64 KiB', x['dov'] == 0 and abs(x['dc']) < 65536, (x['dov'], x['dc']))
ck('derived: node still serves (insert 21 OK)', w['21']['st'] == 'OK')

# ---------------- replay
print('## replay')
w = {x['args'][1]: x for x in writes('replay') if x['args'][0] == 'insert'}
rb = readbacks('replay')
k = w['29']['T'] - int(w['29']['args'][2])
s = open(f'{B}/replay/system.log', errors='replace').read()
rep = re.findall(r'Log replay complete, (\d+) replayed mutations', s)
ck('replay: 16 MiB row accepted before the kill', w['30']['st'] == 'OK' and int(w['30']['args'][2]) == 16777216 - k)
ck('replay: system.log shows a replay of the segments', bool(rep) and 'Replaying' in s, rep)
yaml_after = open(f'{B}/replay/cassandra.yaml').read()
ck('replay: restarted yaml has max_mutation_size: 1MiB', 'max_mutation_size: 1MiB' in yaml_after)
ck('replay: row 30 read back at full length after restart under 1 MiB', rb[30].get('length') == 16777216 - k, rb[30].get('length'))
ck('replay: new write of the same size refused (T/1048576)', w['31']['M'] == 1048576 and w['31']['T'] == 16777216, (w['31']['T'], w['31']['M']))

print(f'\n{n} checks, {len(fails)} failed' + (': ' + ', '.join(fails) if fails else ''))
sys.exit(1 if fails else 0)
