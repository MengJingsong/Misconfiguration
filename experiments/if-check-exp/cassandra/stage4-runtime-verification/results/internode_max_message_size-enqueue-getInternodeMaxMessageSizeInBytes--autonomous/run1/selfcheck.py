#!/usr/bin/env python3
"""Self-check of run 1 (results §5) for internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.
Independent of cluster-run.py's joining and of its phases.json: it re-reads the raw files and recomputes every figure the
conclusion uses.
  unit:    probe.out "STAGE4 case" lines -> for every case, the B2f prediction recomputed from size and limit
           (accepted with +size/+1/+1/+0 iff size <= limit; else OversizedMessageException naming size and limit, +0
           everywhere); the control limit accepts all; size40 == size50.
  cluster: per lifetime, keys-<phase>.csv (the client's own log) gives the write outcomes and the phase window
           (first send .. last done); samples-A.csv / samples-B.csv give the baseline (median of the 10 s before the
           first send, minus 1 s) and the peaks in [window start, window end + 5 s], at 200 ms and at the first sample of
           each second; <node>-system.log gives the exceeds-maximum lines (size, limit) inside each window.
usage: selfcheck.py <run dir: ~/stage4-logs/ime/run1>"""
import csv, calendar, glob, os, re, statistics, sys, time

RUN = sys.argv[1]
MIB = 1 << 20
BIG, SMALL = 2 * MIB, 256 * 1024
LIMITS = {'L1M': MIB, 'L1MC': MIB, 'L8M': 8 * MIB, 'DEF': 128 * MIB}
ok_all = True
nchecks = nfail = 0


def check(name, cond, detail=''):
    global ok_all, nchecks, nfail
    nchecks += 1
    if not cond:
        nfail += 1
        ok_all = False
    print(f'{"ok  " if cond else "FAIL"} {name} {detail}')


# ------------------------------------------------------------------ unit
pu = f'{RUN}/unit/probe.out'
cases = []
for l in open(pu):
    if l.startswith('STAGE4 case'):
        kv = dict(re.findall(r'(\w+)=("[^"]*"|\S+)', l))
        cases.append(kv)
check('unit: 24 case lines (3 L x 4 S, and the 3 controls)', len(cases) == 24, f'n={len(cases)}')
for c in cases:
    size, lim = int(c['size']), int(c['limit'])
    tag = f'unit limit={lim} S={c["S"]} size={size}'
    d = (int(c['dPendingBytes']), int(c['dPendingCount']), int(c['dSubmitted']), int(c['dOverloaded']))
    check(tag + ' size40 == size50 == size', int(c['size40']) == int(c['size50']) == size)
    if size > lim:
        msg = c.get('msg', '').strip('"')
        check(tag + ' refused, named, nothing added', c['outcome'] == 'OversizedMessageException' and d == (0, 0, 0, 0)
              and msg == f'Message of size {size} bytes exceeds allowed maximum of {lim} bytes', f'{c["outcome"]} {d}')
    else:
        check(tag + ' accepted with +size, +1, +1, +0', c['outcome'] == 'accepted' and d == (size, 1, 1, 0),
              f'{c["outcome"]} {d}')
ctl = [c for c in cases if int(c['limit']) == 2147483646]
check('unit: control accepts all 12', len(ctl) == 12 and all(c['outcome'] == 'accepted' for c in ctl))
lim_cases = [c for c in cases if int(c['limit']) != 2147483646]
check('unit: exactly the S > L cases refused (6 of 12)', sorted(c['S'] for c in lim_cases if c['outcome'] != 'accepted')
      == sorted(['L+1', '2L'] * 3))


# ------------------------------------------------------------------ cluster
def read_samples(f):
    rows = list(csv.reader(open(f)))
    head, out = rows[0], []
    for r in rows[1:]:
        if len(r) == len(head) and r[0].isdigit():
            out.append({h: (float(v) if v not in ('', 'ERR') else None) for h, v in zip(head, r)})
    return out


def log_events(f):
    exc, cur = [], None
    for l in open(f, errors='replace'):
        m = re.match(r'^[A-Z]+\s+\[[^\]]*\]\s+(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d:\d\d),(\d{3})', l)
        if m:
            cur = calendar.timegm(time.strptime(m.group(1) + ' ' + m.group(2), '%Y-%m-%d %H:%M:%S')) * 1000 + int(m.group(3))
        e = re.search(r'Message of size (\d+) bytes exceeds allowed maximum of (\d+) bytes', l)
        if e:
            exc.append((int(e.group(1)), int(e.group(2)), cur))
    return exc


peaks = {}
for lab in ('L1M', 'L1MC', 'L8M', 'DEF'):
    d = f'{RUN}/cluster/{lab}'
    if not os.path.isdir(d):
        check(f'{lab}: lifetime folder present', False)
        continue
    smp = {n: read_samples(f'{d}/samples-{n}.csv') for n in 'AB'}
    exc = {n: log_events(f'{d}/{n}-system.log') for n in 'AB'}
    phases = ['P256K'] if lab == 'L1MC' else ['P2M']
    first = None
    for ph in phases:
        rows = [r.split(',') for r in open(f'{d}/keys-{ph}.csv').read().splitlines() if r]
        oks = sum(1 for r in rows if r[5] == 'ok')
        errs = {}
        for r in rows:
            if r[5] == 'err':
                k = r[6].split(':')[0]
                errs[k] = errs.get(k, 0) + 1
        sizes = {int(r[1]) for r in rows}
        t0, t1 = min(int(r[3]) for r in rows), max(int(r[4]) for r in rows)
        if first is None:
            first = t0
        print(f'{lab} {ph}: {len(rows)} writes, ok {oks}, errors {errs}, sizes {sizes}, window {(t1 - t0) / 1000:.1f} s')
        pk = {}
        for n in 'AB':
            base_rows = [r for r in smp[n] if first - 12000 <= r['ms'] <= first - 1000]
            win = [r for r in smp[n] if t0 <= r['ms'] <= t1 + 5000]
            secs, w1 = set(), []
            for r in win:
                s = int(r['ms']) // 1000
                if s not in secs:
                    secs.add(s); w1.append(r)
            pk[n] = {}
            for col in ('direct_used', 'pool_size', 'rss', 'heap_used'):
                b = statistics.median([r[col] for r in base_rows if r[col] is not None])
                pk[n][col] = (max(r[col] for r in win if r[col] is not None) - b,
                              max(r[col] for r in w1 if r[col] is not None) - b)
            if n == 'A':
                pv = [r['LargeMessagePendingBytes'] for r in win if r['LargeMessagePendingBytes'] is not None]
                p1 = [r['LargeMessagePendingBytes'] for r in w1 if r['LargeMessagePendingBytes'] is not None]
                pk[n]['pending'] = (max(pv), max(p1), sum(1 for v in pv if v > 0), len(pv))
                comp = [r['LargeMessageCompletedTasks'] for r in win if r['LargeMessageCompletedTasks'] is not None]
                pk[n]['completed'] = comp[-1] - comp[0] if comp else None
            print(f'  {n}: ' + ', '.join(f'{c} {v[0] / MIB:+.2f}/{v[1] / MIB:+.2f} MiB' for c, v in pk[n].items()
                                       if c in ('direct_used', 'pool_size', 'rss', 'heap_used')) +
                  (f'; pending peak {pk[n]["pending"][0] / MIB:.2f} MiB (1 s {pk[n]["pending"][1] / MIB:.2f}), '
                   f'{pk[n]["pending"][2]}/{pk[n]["pending"][3]} samples > 0; large completed in window '
                   f'+{pk[n]["completed"]:.0f}' if n == 'A' else ''))
        ex = {n: [(s, l) for s, l, t in exc[n] if t is not None and t0 - 1000 <= t <= t1 + 5000] for n in 'AB'}
        print(f'  exceeds lines in the window: A {len(ex["A"])} {sorted(set(ex["A"]))[:3]}, B {len(ex["B"])}')
        peaks[(lab, ph)] = pk
        n_all = len(rows)
        if lab == 'L1M' and ph == 'P2M':
            check(f'{lab} {ph}: every write fails', oks == 0, f'ok={oks}/{n_all}')
            check(f'{lab} {ph}: A logs exceeds lines for ~2.1e6-byte messages against 1048576, B none',
                  len(ex['A']) > 0 and all(l == MIB and BIG < s < BIG + 4096 for s, l in ex['A']) and not ex['B'],
                  f'A {len(ex["A"])}, B {len(ex["B"])}')
            check(f'{lab} {ph}: A LargeMessagePendingBytes 0 in every sample', pk['A']['pending'][0] == 0)
            for n in 'AB':
                check(f'{lab} {ph}: {n} direct and pool Size increment < 2 MiB (200 ms)',
                      max(pk[n]['direct_used'][0], pk[n]['pool_size'][0]) < BIG,
                      f'direct {pk[n]["direct_used"][0] / MIB:+.2f} pool {pk[n]["pool_size"][0] / MIB:+.2f} MiB')
        elif lab == 'L1MC':
            check(f'{lab} {ph}: every write succeeds, no exceeds line', oks == n_all and not ex['A'] and not ex['B'],
                  f'ok={oks}/{n_all}')
        else:
            check(f'{lab} {ph}: every write succeeds, no exceeds line', oks == n_all and not ex['A'] and not ex['B'],
                  f'ok={oks}/{n_all}')
            check(f'{lab} {ph}: A pending peak > 0 and <= 16 x (2 MiB + 4 KiB)',
                  0 < pk['A']['pending'][0] <= 16 * (BIG + 4096), f'{pk["A"]["pending"][0]:.0f}')

for lab in ('L8M', 'DEF'):
    if ('L1M', 'P2M') in peaks and (lab, 'P2M') in peaks:
        for n in 'AB':
            for i, rate in ((1, '1 s'), (0, '200 ms')):
                dlt = peaks[(lab, 'P2M')][n]['direct_used'][i] - peaks[('L1M', 'P2M')][n]['direct_used'][i]
                check(f'B3f {lab} vs L1M {n} direct peak ({rate}) higher by MiB to tens of MiB [1, 100) MiB',
                      MIB <= dlt < 100 * MIB, f'{dlt / MIB:+.2f} MiB')

print(f'SELFCHECK checks={nchecks} failed={nfail} -> {"ok" if ok_all else "MISMATCH (see FAIL lines)"}')
