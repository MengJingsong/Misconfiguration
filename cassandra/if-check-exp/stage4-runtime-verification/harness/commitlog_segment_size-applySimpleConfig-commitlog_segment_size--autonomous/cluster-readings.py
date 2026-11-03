#!/usr/bin/env python3
"""Builds the cluster-tier readings (B3f (i)-(vii), B3h (a)-(c), INFO) of
commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous from the raw files of one cluster-run directory.
usage: cluster-readings.py <cluster-run dir>   -> prints the readings (the run writes them to readings.txt)
"""
import csv, os, re, sys

R = sys.argv[1]
MIB = 1048576


def rd(p):
    try:
        return open(p, errors='replace').read()
    except OSError:
        return ''


def files_check(D, S):
    rows = [l.split() for l in open(os.path.join(D, 'seg.files'))]
    by_ts = {}
    for ts, name, size, alloc in rows:
        by_ts.setdefault(int(ts), {})[name] = (int(size), int(alloc))
    tss = sorted(by_ts)
    bad, zero_then_s, eq, below = [], 0, 0, 0
    alloc_eq = alloc_zero = alloc_other = alloc_over = 0
    ids = set()
    minsize = None
    maxsize = 0
    for i, ts in enumerate(tss):
        for name, (size, alloc) in by_ts[ts].items():
            m = re.match(r'CommitLog-\d+-(\d+)\.log$', name)
            if m:
                ids.add(int(m.group(1)))
            minsize = size if minsize is None else min(minsize, size)
            maxsize = max(maxsize, size)
            if size < S:
                below += 1
            if size == S:
                eq += 1
            elif size == 0 and i + 1 < len(tss) and by_ts[tss[i + 1]].get(name, (None,))[0] == S:
                zero_then_s += 1
            else:
                bad.append((ts, name, size))
            if alloc == S:
                alloc_eq += 1
            elif alloc == 0:
                alloc_zero += 1
            else:
                alloc_other += 1
            if alloc > size:
                alloc_over += 1
    span = (max(ids) - min(ids) + 1) if ids else 0
    return dict(file_samples=len(rows), samples=len(tss), eqS=eq, zero_then_S=zero_then_s, bad=len(bad), bad_examples=bad[:3],
                below_S=below, min_size=minsize, max_size=maxsize, distinct=len(ids), id_span=span,
                alloc_eqS=alloc_eq, alloc_zero=alloc_zero, alloc_other=alloc_other, alloc_gt_apparent=alloc_over)


def jmx_check(D, S):
    rows = [r for r in csv.DictReader(l for l in open(os.path.join(D, 'jmx.csv')) if not l.startswith('#'))]
    n = len(rows)
    cap_mult = sum(1 for r in rows if int(r['mapped_capacity']) > 0 and int(r['mapped_capacity']) % S == 0)
    cap_zero = sum(1 for r in rows if int(r['mapped_capacity']) == 0)
    cnt_eq = sum(1 for r in rows if int(r['mapped_capacity']) == int(r['mapped_count']) * S)
    tot_mult = sum(1 for r in rows if int(r['total_commitlog_size']) % S == 0)
    mx_tot = max(int(r['total_commitlog_size']) for r in rows) if rows else 0
    mx_cnt = max(int(r['mapped_count']) for r in rows) if rows else 0
    return dict(samples=n, mapped_cap_pos_multiple=cap_mult, mapped_cap_zero=cap_zero, cap_eq_count_x_S=cnt_eq,
                cap_eq_frac=(cnt_eq / n if n else 0), total_multiple_S=tot_mult, max_total_bytes=mx_tot, max_total_MiB=mx_tot / MIB,
                max_mapped_count=mx_cnt, oversized_first=rows[0]['oversized_count'] if rows else '-',
                oversized_last=rows[-1]['oversized_count'] if rows else '-')


summ = rd(os.path.join(R, 'summary.txt'))
for arm in ('z0', 'z2048'):
    for l in summ.splitlines():
        if l.startswith('REFUSAL %s ' % arm) or l.startswith('REFUSAL-LINES %s ' % arm):
            print(l)
    D = os.path.join(R, arm)
    if os.path.isdir(D):
        out = rd(os.path.join(D, 'node.out'))
        print('NODEOUT %s exception_line=%s' % (arm, [l for l in out.splitlines() if 'encountered during startup' in l][:1]))

for arm, smib in (('s8', 8), ('s32', 32), ('s64', 64), ('lz4', 8), ('sd', 8)):
    D = os.path.join(R, arm)
    if not os.path.isdir(D):
        continue
    S = smib * MIB
    st = rd(os.path.join(D, 'settings.txt'))
    sets = dict((m.group(1), m.group(2).strip()) for m in re.finditer(r'^\s*(\w+)\s*\|\s*(.*?)\s*$', st, re.M))
    print('== %s S=%d' % (arm, S))
    print('READBACK %s commitlog_segment_size=%s max_mutation_size=%s commitlog_total_space=%s disk_access_mode=%s native_max_message=%s compression=%s'
          % (arm, sets.get('commitlog_segment_size'), sets.get('max_mutation_size'), sets.get('commitlog_total_space'), sets.get('disk_access_mode'),
             sets.get('native_transport_max_message_size'), sets.get('commitlog_compression')))
    sl = rd(os.path.join(D, 'system.log'))
    print('MODE %s %s' % (arm, re.findall(r'commitlog_disk_access_mode resolved to: \w+', sl)[:1]))
    s = rd(os.path.join(D, 'stress.log'))
    tp = re.findall(r'^Total partitions\s*:\s*([\d,]+)', s, re.M); te = re.findall(r'^Total errors\s*:\s*([\d,]+)', s, re.M)
    print('STRESS %s partitions=%s errors=%s' % (arm, tp[:1], te[:1]))
    print('FILES %s %s' % (arm, files_check(D, S)))
    print('JMX %s %s' % (arm, jmx_check(D, S)))
    for l in rd(os.path.join(D, 'big.txt')).splitlines():
        print('BIG %s %s' % (arm, l[4:] if l.startswith('BIG ') else l))
