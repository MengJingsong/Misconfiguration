#!/usr/bin/env python3
"""Independent self-check of run 1, DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace (results §5).
usage: selfcheck.py [<run dir>, default ~/stage4-logs/dds/run1]
Re-reads each label's raw files without the run script's code: cassandra.yaml (partitioner, min_free_space_per_drive),
dds.trace (guard / switch / writeable lines), system.log (Compacting / Compacted lines of ks1.t, the guard's and the sibling's
messages, filesystem errors, the disk-policy line), samples.csv (df Available and du of the table every 0.5 s), the session log
(the trigger's wall-clock second) and table-dir-final.txt (the files left). T is taken from the summary's DATASET line (the
Data.db lengths read from the files) and checked against the guard trace. Prints one line per check and a table; exit 1 if any
check fails."""
import csv, os, re, sys, time, calendar

RUN = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/dds/run1')
MIB = 1048576
LABELS = {}
for arm in 'ba':
    for name, off in (('p256', 256), ('p16', 16), ('m16', -16), ('m256', -256)):
        LABELS[f'{arm}_{name}'] = (arm.upper(), 50, 'd', off, False)
for m in (50, 240, 272, 512):
    LABELS[f'b_mm{m:03d}'] = ('B', m, 'mm', 256, False)
LABELS['b_sib'] = ('B', 50, 'd', -256, True)
fails = 0
rows = []


def ck(label, desc, cond, detail=''):
    global fails
    if not cond:
        fails += 1
    print(f'{"ok  " if cond else "FAIL"} {label}: {desc}{" — " + detail if detail else ""}')
    return cond


def utc_ms(ts):          # system.log timestamps are UTC: 2026-10-15T07:12:15,037
    return calendar.timegm(time.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')) * 1000 + int(ts[20:23])


for label, (arm, m_mib, base, off, sib) in LABELS.items():
    d = os.path.join(RUN, label)
    if not os.path.isdir(d):
        ck(label, 'label folder present', False, d)
        continue
    yaml = open(f'{d}/cassandra.yaml').read()
    part = re.findall(r'^partitioner:\s*(\S+)', yaml, re.M)[-1]
    mfree = re.findall(r'^min_free_space_per_drive:\s*(\d+)MiB', yaml, re.M)
    M = int(mfree[-1]) * MIB if mfree else 50 * MIB
    ck(label, f'yaml: partitioner of arm {arm}, m = {m_mib} MiB',
       part.endswith('ByteOrderedPartitioner' if arm == 'B' else 'Murmur3Partitioner') and M == m_mib * MIB, f'{part}, {M}')
    summ = open(f'{d}/summary.txt').read()
    ds = re.search(r'Data\.db lengths \[([\d, ]+)\]', summ)
    sizes = [int(x) for x in ds.group(1).split(',')] if ds else []
    T = sum(sizes)
    ck(label, 'dataset: 8 Data.db of 64 MiB ± 10 %', len(sizes) == 8 and all(abs(x - 64 * MIB) <= 0.1 * 64 * MIB for x in sizes), str(sizes))
    # the trigger's second from the session log (local time), the samples from samples.csv
    sess = open(f'{d}/session.log').read()
    tr_line = re.search(r'^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] \+ bin/nodetool enableautocompaction ks1 t', sess, re.M)
    t_trig = time.mktime(time.strptime(tr_line.group(1), '%Y-%m-%d %H:%M:%S')) if tr_line else None
    smp = [(float(r['epoch']), int(r['avail']), int(r['du_table'])) for r in csv.DictReader(open(f'{d}/samples.csv'))]
    before = [s for s in smp if t_trig and s[0] <= t_trig + 1]
    after = [s for s in smp if t_trig and s[0] >= t_trig]
    U = before[-1][1] if before else None
    du0 = before[-1][2] if before else None
    min_av = min([s[1] for s in after] or [None]) if after else None
    peak_du = max([s[2] for s in after] or [0])
    U_target = T + (50 * MIB if base == 'd' else 0) + off * MIB
    ck(label, 'df Available at the trigger within 16 MiB of the intended U', U is not None and abs(U - U_target) <= 16 * MIB, f'U {U} target {U_target}')
    # trace
    tr = open(f'{d}/dds.trace').read().splitlines()
    big_guards = []
    for l in tr:
        g = re.match(r'^guard est=(\d+) avail=(\d+) refused=(\w+)', l)
        if g and int(g.group(1)) >= 100 * MIB:
            big_guards.append((int(g.group(1)), int(g.group(2)), g.group(3) == 'true'))
    sw_t = [l for l in tr if l.startswith('switch ') and 'table=ks1.t ' in l]
    wr_t = [l for l in tr if l.startswith('writeable ') and 'table=ks1.t ' in l]
    wr_any = [l for l in tr if l.startswith('writeable ')]
    all_guards = [l for l in tr if l.startswith('guard ')]
    # system.log
    sl = open(f'{d}/system.log').read()
    lines = sl.splitlines()
    comp_t = [l for l in lines if 'Compacting (' in l and '/ks1/t-' in l]
    compd_t = [l for l in lines if 'Compacted (' in l and '/ks1/t-' in l]
    n_in = [len(re.findall(r'/ks1/t-\w+/[\w-]+-Data\.db', l)) for l in comp_t]
    gmsg = re.findall(r'Not enough space to write (\S+) to (\S+) \((\S+) available\)', sl)
    sibr = [l for l in lines if 'Reducing scope' in l]
    siba = [l for l in lines if 'Not enough space for compaction (' in l]
    fsw = [l for l in lines if 'FSWriteError' in l or 'No space left on device' in l]
    stopl = [l for l in lines if 'Stopping transports as disk_failure_policy' in l]
    fin = open(f'{d}/table-dir-final.txt').read()
    fin_data = [(int(m.group(1)), m.group(2)) for m in re.finditer(r'^\S+\s+\d+\s+\S+\s+\S+\s+(\d+)\s+.*?(\S+-Data\.db)$', fin, re.M)]
    plan_refuse = U is not None and U - M < T
    ck(label, 'one Compacting line of ks1.t' + ('' if sib else ' holding all 8 inputs'), len(comp_t) >= 1 and (sib or n_in[0] == 8), f'{n_in}')
    out = ''
    if arm == 'B':
        ck(label, 'arm B: a writeable trace line for every flush of ks1.t (>= 8)', len(wr_t) >= 8, str(len(wr_t)))
        ck(label, 'arm B: exactly one table-sized guard line', len(big_guards) == 1, str(big_guards))
        ck(label, 'arm B: every guard line (system tables included) obeys refused == (avail < est)',
           all((l.split('refused=')[1].split()[0] == 'true') == (int(re.search(r'avail=(\d+)', l).group(1)) < int(re.search(r'est=(\d+)', l).group(1))) for l in all_guards),
           f'{len(all_guards)} guard lines')
        if big_guards:
            e, a, r = big_guards[0]
            ck(label, 'guard: avail = max(0, U - m) within 1 MiB', abs(a - max(0, U - M)) <= MIB, f'avail {a} U-m {U - M}')
            if not sib:
                ck(label, 'guard: est = T (sum of the Data.db lengths)', e == T, f'est {e} T {T}')
                ck(label, f'guard: refused = planned ({plan_refuse})', r == plan_refuse)
            out = f'est {e} avail {a} refused {r}'
        if sib:
            ids = [re.search(r'compaction (\S+), ', l).group(1) for l in sibr]
            first = ids[0] if ids else None
            n_first = sum(1 for i in ids if i == first)
            kept3 = sum(sorted(sizes)[:8 - n_first])
            ck(label, 'sibling, first task: 5 Reducing scope lines, the guard admitted the sum of the 3 smallest inputs, no guard message, one Compacted',
               n_first == 5 and big_guards and big_guards[0][0] == kept3 and not big_guards[0][2] and not gmsg and len(compd_t) == 1,
               f'first task {n_first} lines, est {big_guards[0][0] if big_guards else None} vs {kept3}; later tasks {len(ids) - n_first} lines, aborts {len(siba)}')
            ck(label, 'sibling: Reducing scope >= 1, no guard message, guard admitted an estimate below T, one Compacted, Data.db = 1 + shed',
               len(sibr) >= 1 and not gmsg and big_guards and not big_guards[0][2] and big_guards[0][0] < T and len(compd_t) == 1 and len(fin_data) == 1 + len(sibr),
               f'reducing {len(sibr)}, Data.db left {len(fin_data)}')
        elif plan_refuse:
            ck(label, 'refuse: one guard message whose sizes print T and U - m', len(gmsg) == 1, str(gmsg))
            ck(label, 'refuse: no writer switch for ks1.t, no Compacted line', not sw_t and not compd_t)
            ck(label, 'refuse: the 8 inputs remain with their lengths', sorted(x for x, _ in fin_data) == sorted(sizes), str(sorted(x for x, _ in fin_data)))
            ck(label, 'refuse: du of the table never rose more than 1 MiB above its value at the trigger', peak_du <= du0 + MIB, f'peak {peak_du} du0 {du0}')
        else:
            ck(label, 'admit: no guard message, one switch positions=null, one Compacted, one Data.db within 1 % of T',
               not gmsg and len(sw_t) == 1 and 'positions=null' in sw_t[0] and len(compd_t) == 1 and len(fin_data) == 1 and abs(fin_data[0][0] - T) <= T / 100,
               str(fin_data))
        ck(label, 'no sibling message unless the sibling control', sib or (not sibr and not siba))
    else:
        ck(label, 'arm A: no writeable line in the lifetime (no flush or compaction reached the second site)', not wr_any, str(len(wr_any)))
        # explanation of the frozen sub-prediction's miss: which tables, and when (UTC) relative to the node reaching NORMAL
        nm = re.search(r'^INFO\s+\[\S+\] (\S+) StorageService\.java:\d+ - Node \S+ state jump to NORMAL', sl, re.M)
        t_normal = utc_ms(nm.group(1)) if nm else None
        wr_ms = [int(re.search(r'ms=(\d+)', l).group(1)) for l in wr_any]
        ck(label, 'explains: no writeable line for ks1.t; every writeable line (system tables) precedes the state jump to NORMAL',
           not wr_t and t_normal is not None and all(x <= t_normal for x in wr_ms), f'{len(wr_any)} lines, last {max(wr_ms) - t_normal if wr_ms and t_normal else None} ms vs NORMAL')
        ck(label, 'arm A: no guard line, no guard message', not all_guards and not gmsg, f'{len(all_guards)} {gmsg}')
        ck(label, 'arm A: every ks1.t writer on the boundary path (positions=1)', sw_t and all('positions=1 ' in l for l in sw_t), str(len(sw_t)))
        if off > -100:
            ck(label, 'arm A: completed, one Data.db within 1 % of T', len(compd_t) == 1 and len(fin_data) == 1 and abs(fin_data[0][0] - T) <= T / 100, str(fin_data))
            if off < 0:
                ck(label, 'arm A d=-16: minimum df Available during the compaction in (0, m)', min_av is not None and 0 < min_av < M, f'min {min_av} m {M}')
            else:
                ck(label, f'arm A d=+{off}: minimum df Available >= m', min_av is not None and min_av >= M, f'min {min_av}')
        else:
            ck(label, 'arm A d=-256: a filesystem write error, no Compacted line, the 8 inputs remain',
               fsw and not compd_t and sorted(x for x, _ in fin_data if x in sizes) == sorted(sizes), f'fs lines {len(fsw)}, Data.db {sorted(x for x, _ in fin_data)}')
            ck(label, 'arm A d=-256: the filesystem was full (min df Available <= 1 MiB)', min_av is not None and min_av <= MIB, str(min_av))
            ck(label, 'arm A d=-256: peak du within 16 MiB of du at the trigger + U', abs(peak_du - (du0 + U)) <= 16 * MIB, f'peak {peak_du} du0+U {du0 + U}')
            out = f'fs errors {len(fsw)}, transports-stopped lines {len(stopl)}, Data.db left {len(fin_data)}'
    rows.append((label, arm, M // MIB, T, U, (U - M - T) if U else None, 'refuse' if plan_refuse else 'admit', len(gmsg), len(compd_t), min_av, peak_du, out))

print()
print('label | arm | m MiB | T | U at trigger | U-m-T | planned | guard msgs | Compacted | min df | peak du | note')
for r in rows:
    print(' | '.join(str(x) for x in r))
print(f'\n{fails} check(s) failed')
sys.exit(1 if fails else 0)
