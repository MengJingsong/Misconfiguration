#!/usr/bin/env python3
"""Cluster-tier analysis (B3d, B3g). Usage: analyze.py <clusterdir>  -> prints a table and writes summary.txt there.
Reads, per arm dir <arm>-r<rep>: du.csv (ts_ms,commitlog_bytes,nfiles,tmpfs_used,data_bytes), jmx.csv, times.txt, counts.txt,
warnline.txt, segment-deletions.txt, stress.out. Peak = max apparent-size bytes of the commit log directory over the whole
sample file (includes the 4096 B directory entry). MiB = 1048576 B."""
import sys, os, re, glob

MIB = 1048576.0
SEG = 32.0


def load(d):
    rows = []
    for ln in open(os.path.join(d, 'du.csv')):
        p = ln.strip().split(',')
        if len(p) >= 5 and p[1].isdigit():
            rows.append((int(p[0]), int(p[1]), int(p[2]), int(p[3])))
    t = dict(kv.split('=') for kv in open(os.path.join(d, 'times.txt')).read().split())
    return rows, {k: int(v) if v.isdigit() else v for k, v in t.items()}


def main(root):
    out = []
    res = {}
    for d in sorted(glob.glob(os.path.join(root, '*-r[0-9]'))):
        if not os.path.exists(os.path.join(d, 'DONE')):
            out.append('%s: NOT DONE' % os.path.basename(d))
            continue
        arm = os.path.basename(d)
        rows, t = load(d)
        limit = 1024 if t['ARM'] == 'unset' else int(t['ARM'])
        peak = max(r[1] for r in rows) / MIB
        peakfiles = max(r[2] for r in rows)
        maxvol = max(r[3] for r in rows) / MIB
        T1, TS = t['T1'], t['TS']
        settle = [r[1] for r in rows if r[0] >= TS - 2000 and r[0] <= TS][-1] / MIB
        # during-write peak (T0..T1+5s) vs after
        wpeak = max(r[1] for r in rows if t['T0'] <= r[0] <= T1 + 5000) / MIB
        counts = dict(l.split(None, 1) for l in open(os.path.join(d, 'counts.txt')) if not l.startswith('REASON'))
        dirty = int(counts['COMMITLOG_DIRTY_standard1'].split()[0])
        memlim = int(counts['MEMTABLE_LIMIT_any'].split()[0])
        dels = sum(1 for _ in open(os.path.join(d, 'segment-deletions.txt')))
        jmx = [int(l.split(',')[1]) for l in open(os.path.join(d, 'jmx.csv')) if re.match(r'^\d+,\d+$', l.strip())]
        jpeak = max(jmx) / MIB if jmx else float('nan')
        so = open(os.path.join(d, 'stress.out')).read()
        errs = re.search(r'Total errors\s*:\s*(\d+)', so)
        rate = re.search(r'Op rate\s*:\s*([\d,]+)', so)
        res[arm] = dict(limit=limit, peak=peak, settle=settle, dirty=dirty, memlim=memlim, dels=dels, jpeak=jpeak,
                        errs=int(errs.group(1)) if errs else None, maxvol=maxvol, wpeak=wpeak)
        out.append('%-10s limit=%5d MiB peak(du)=%8.1f MiB (%.2fx limit, +%.0f MiB; %d files) write-phase peak=%8.1f jmx peak=%8.1f settle=%8.1f '
                   'COMMITLOG_DIRTY=%d MEMTABLE_LIMIT=%d seg-deletions=%d errors=%s rate=%s maxtmpfs=%.0f MiB'
                   % (arm, limit, peak, peak / limit, peak - limit, peakfiles, wpeak, jpeak, settle, dirty, memlim, dels,
                      res[arm]['errs'], rate.group(1) if rate else '?', maxvol))
    # B3g reading per rep
    out.append('')
    for rep in (1, 2):
        a = {k: res.get('%s-r%d' % (k, rep)) for k in ('unset', '256', '128', '8192')}
        if not all(a.values()):
            continue
        peaks = {k: v['peak'] for k, v in a.items()}
        within = {k: peaks[k] <= a[k]['limit'] + 100 for k in ('unset', '256', '128')}
        ordered = peaks['128'] < peaks['256'] < peaks['unset']
        out.append('rep %d: peaks %s; within limit+100 MiB: %s; ordered 128<256<unset: %s; control 8192 peak %.0f MiB; MEMTABLE_LIMIT flushes %s'
                   % (rep, {k: round(v) for k, v in peaks.items()}, within, ordered, peaks['8192'],
                      {k: v['memlim'] for k, v in a.items()}))
    open(os.path.join(root, 'summary.txt'), 'w').write('\n'.join(out) + '\n')
    print('\n'.join(out))


main(sys.argv[1])
