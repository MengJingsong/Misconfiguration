#!/usr/bin/env python3
"""Independent self-check of run 1, repair_disk_headroom_reject_ratio (results §5). Re-parses the raw excerpts in this folder:
  cluster/N1-hdr.trace, cluster/N2-hdr.trace     the Byteman lines of each node (whole run)
  cluster/N1-log.txt, cluster/N2-log.txt         system.log + debug.log lines of the check, the coordinator, streams, validation
  cluster/<label>/summary.txt                    only for each trigger's name, planned U0, r and the nodetool repair id
  cluster/overshoot/samples.csv                  arm O's sampler
  unit/*.out                                     the unit tier's STAGE4 lines
It recomputes u_plan = ceil5(U0 / C), the verdict u + r > 1, the ERROR percentages, and "nothing started" from the debug lines in
a 3 s window after each refusal, without using the run script's EXPECTED lines. Exit 1 on any failure."""
import csv, datetime, os, re, sys
from decimal import Decimal, ROUND_UP

D = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
CAP = 1073741824
ok_n = bad_n = 0


def chk(name, cond, detail=''):
    global ok_n, bad_n
    ok_n += bool(cond); bad_n += (not cond)
    print(f'{"ok  " if cond else "FAIL"} {name} {detail}'[:400])


def ceil5(x):
    return float(Decimal(x).quantize(Decimal('0.00001'), rounding=ROUND_UP))


# ---------------- raw node files
trace = {}
for n in ('N1', 'N2'):
    ev = []
    for l in open(f'{D}/cluster/{n}-hdr.trace'):
        m = re.match(r'HDR (usage|verdict) session=(\S+) (?:usage=(\S+) ratio=(\S+)|admit=(\w+)) ms=(\d+)', l)
        if m:
            ev.append(dict(kind=m[1], id=m[2], usage=float(m[3]) if m[3] else None, ratio=float(m[4]) if m[4] else None,
                           admit=(m[5] == 'true') if m[5] else None, ms=int(m[6])))
    trace[n] = ev


def utc_ms(s):
    return int(datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)


logs = {}
for n in ('N1', 'N2'):
    ls = []
    for l in open(f'{D}/cluster/{n}-log.txt', errors='replace'):
        m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d,\d{3})', l)
        if m:
            ls.append((utc_ms(m[1]), l.rstrip()))
    logs[n] = ls
STARTED = re.compile(r'merkle tree|Prepared AEService|\[Stream #|anticompact|snapshot', re.I)

# ---------------- triggers (name, plan, id) from the run's summaries
trig = []
for label in ('setup', 'sweep-p', 'sweep-k', 'types'):
    for l in open(f'{D}/cluster/{label}/summary.txt'):
        m = re.match(r'TRIGGER (.*?): knob (\S+) r=(\S+) U0=(\S+) .* id=(\S+) \|', l)
        if m:
            trig.append(dict(label=label, name=m[1], knob=None if m[2] == 'None' else m[2], r=float(m[3]),
                             U0=None if m[4] == 'None' else int(m[4]), id=m[5]))
chk('trigger count: setup 1, sweep-p 12, sweep-k 12, types 12', [sum(t['label'] == x for t in trig) for x in ('setup', 'sweep-p', 'sweep-k', 'types')] == [1, 12, 12, 12])


def lines_for(n, tid):
    return [e for e in trace[n] if e['id'] == tid]


refused_ids = []
for t in trig:
    tag = f'{t["label"]} {t["name"]}'
    per = {n: lines_for(n, t['id']) for n in ('N1', 'N2')}
    # the verdict follows the operand, u + r > 1, on every node that checked
    for n in ('N1', 'N2'):
        us = [e for e in per[n] if e['kind'] == 'usage']; vs = [e for e in per[n] if e['kind'] == 'verdict']
        if us:
            chk(f'{tag} {n}: verdict = not(u + r > 1) for u={us[0]["usage"]} r={us[0]["ratio"]}', len(us) == 1 and len(vs) == 1 and vs[0]['admit'] == (not (us[0]['usage'] + us[0]['ratio'] > 1)))
    if t['knob'] is None:
        chk(f'{tag}: both nodes checked and admitted (control)', all(len(per[n]) == 2 and per[n][1]['admit'] for n in ('N1', 'N2')))
        continue
    k = t['knob']; other = 'N2' if k == 'N1' else 'N1'
    uk = [e for e in per[k] if e['kind'] == 'usage']
    u_plan = ceil5(Decimal(t['U0']) / Decimal(CAP))
    chk(f'{tag}: knob node {k} operand u={uk[0]["usage"] if uk else None} within 0.0005 of ceil5(U0/C)={u_plan}, ratio {t["r"]}',
        uk and abs(uk[0]['usage'] - u_plan) <= 0.0005 and uk[0]['ratio'] == t['r'])
    admit_pred = not (u_plan + t['r'] > 1)
    vk = [e for e in per[k] if e['kind'] == 'verdict']
    chk(f'{tag}: {k} verdict {"admit" if admit_pred else "refuse"} as planned', vk and vk[0]['admit'] == admit_pred)
    if not admit_pred:
        refused_ids.append((t, uk[0]['usage'], vk[0]['ms']))
        if k == 'N1':
            chk(f'{tag}: coordinator refusal — node 2 never asked (no HDR line)', not per['N2'])
        else:
            chk(f'{tag}: participant refusal — node 1 checked and admitted', len(per['N1']) == 2 and per['N1'][1]['admit'])
        err = [l for _, l in logs[k] if f'#{t["id"]}]] Rejecting incoming repair, disk usage (' in l]
        u = uk[0]['usage']
        pref = '[[preview repair #' if ('preview' in t['name'] or 'validate' in t['name']) else '[[repair #'
        want = f'{pref}{t["id"]}]] Rejecting incoming repair, disk usage ({u * 100:.2f}%) above threshold ({(1 - t["r"]) * 100:.2f}%)'
        chk(f'{tag}: one ERROR line on {k}: "{want[-75:]}"', len(err) == 1 and want in err[0])
        chk(f'{tag}: no ERROR line of this check on {other}', not [l for _, l in logs[other] if f'#{t["id"]}]] Rejecting incoming repair, disk usage (' in l])
        t0 = vk[0]['ms']
        started = [l for n in ('N1', 'N2') for ms, l in logs[n] if t0 <= ms <= t0 + 3000 and STARTED.search(l)]
        chk(f'{tag}: nothing started in the 3 s after the refusal (no merkle/AEService/stream/snapshot/anticompaction line)', not started, started[:1])

# staircase: for every ratio both arms admit A and refuse B
for label in ('sweep-p', 'sweep-k'):
    for r in (0.0, 0.2, 0.5, 0.8):
        a = [t for t in trig if t['label'] == label and t['name'].endswith(f' A r={r}')]
        b = [t for t in trig if t['label'] == label and t['name'].endswith(f' B r={r}')]
        chk(f'{label} r={r}: U0 = L - 4 MiB admitted, U0 = L + 4 MiB refused, L = (1 - r) C', len(a) == 1 and len(b) == 1
            and a[0]['U0'] == round((1 - r) * CAP) - 4194304 and b[0]['U0'] == round((1 - r) * CAP) + 4194304
            and b[0]['id'] in {x[0]['id'] for x in refused_ids} and a[0]['id'] not in {x[0]['id'] for x in refused_ids})
chk('phase T: all 12 kinds refused', sum(1 for t in trig if t['label'] == 'types' and t['id'] in {x[0]['id'] for x in refused_ids}) == 12)

# ---------------- arm V
vlog = [l for _, l in logs['N2'] if 'above threshold (-50.00%)' in l]
chk('arm V: node 2 (yaml 1.5) refused with threshold (-50.00%)', len(vlog) == 1, vlog[:1])
vs = open(f'{D}/cluster/valid/summary.txt').read()
chk('arm V: the JMX write of 1.5 failed with the range text', 'SETFAIL' in vs and 'Value must be >= 0 and <= 1 for repair_disk_headroom_reject_ratio' in vs)

# ---------------- arm O
acc = [(ms, int(re.search(r'newStreamTotalBytes=(\d+)', l)[1])) for ms, l in logs['N2'] if 'Accepting incoming files' in l and 'hdr.t' in l]
chk('arm O: node 2 logged Accepting twice (preview, repair) with the same bytes in 268.4-269.5 MB', len(acc) == 2 and acc[0][1] == acc[1][1] and 268.4e6 <= acc[0][1] <= 269.5e6, acc)
S = acc[-1][1] if acc else None
rows = list(csv.DictReader(open(f'{D}/cluster/overshoot/samples.csv')))
w = [int(r['walk_N2']) for r in rows]
L = CAP // 2; U0 = L - 4194304
chk('arm O: sampler starts at U0 (walk within 1 MiB) and crosses L', w and abs(w[0] - U0) < 1048576 and max(w) > L, f'first {w[:1]} max {max(w) if w else None}')
chk('arm O: no second HDR usage line on node 2 while the stream ran', all(int(r['hdr_lines_N2']) <= 1 for r in rows))
U1 = w[-1]
chk(f'arm O: node 2 grew by S +/- 1 MiB (U1 - U0 = {U1 - U0}, S = {S})', S is not None and abs((U1 - U0) - S) <= 1048576)
chk(f'arm O: overshoot past the line U1 - L = {U1 - L} B (S - 4 MiB = {S - 4194304 if S else None})', S is not None and abs((U1 - L) - (S - 4194304)) <= 1048576)
n1 = [int(r['walk_N1']) for r in rows]
chk('arm O: node 1 data directory changed by < 1 MiB during the repair', max(n1) - min(n1) < 1048576)
ov = [e for e in trace['N2'] if e['kind'] == 'usage' and e['ratio'] == 0.5 and 0.49 < e['usage'] < 0.5]
chk('arm O: the admitted check read u = 0.49610 +/- 0.0005 at r = 0.5', any(abs(e['usage'] - 0.4961) <= 0.0005 for e in ov))
re74 = [l for _, l in logs['N2'] if re.search(r'disk usage \(74\.6\d%\) above threshold \(50\.00%\)', l)]
chk('arm O: the re-check at 0.5 refused with (74.6x%) above (50.00%)', len(re74) == 1, re74[:1])
ok02 = [e for e in trace['N2'] if e['kind'] == 'usage' and e['ratio'] == 0.2 and 0.7 < e['usage'] < 0.75]   # arm O's U1/C, not the sweep's 0.79-0.80
chk('arm O: the re-check at 0.2 read u > 0.7 and was admitted', len(ok02) >= 1 and all(not (e['usage'] + 0.2 > 1) for e in ok02))

# ---------------- unit tier
tot = mm = 0
for f in sorted(os.listdir(f'{D}/unit')):
    if f.endswith('.out'):
        ls = open(f'{D}/unit/{f}').read().splitlines()
        c = [l for l in ls if l.startswith('STAGE4 check')]
        tot += len(c); mm += sum(1 for l in c if 'MISMATCH' in l)
chk(f'unit: {tot} harness checks, 0 MISMATCH', tot == 135 and mm == 0, f'{tot}/{mm}')
print(f'TOTAL ok {ok_n} fail {bad_n}')
sys.exit(1 if bad_n else 0)
