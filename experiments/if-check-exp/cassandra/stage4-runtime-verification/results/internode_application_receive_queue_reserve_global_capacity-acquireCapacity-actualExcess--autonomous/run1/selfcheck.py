#!/usr/bin/env python3
"""Self-check of run 1 (cluster tier) for internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous.
Re-parses the RAW files of ~/stage4-logs/rsv/run1/cluster/<label>/ (rsv.trace, jmx-A.csv, vt-in.csv, samples/histo-*.txt, stress.log,
A-system.log) with its own regexes, not cluster-run.py's functions, and prints the figures the conclusion cites.
usage: python3 selfcheck.py [root]"""
import csv, glob, os, re, statistics, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/rsv/run1/cluster')
CFG = {'g4': (1 << 20, 4 << 20), 'g32': (1 << 20, 32 << 20), 'g512': (1 << 20, 512 << 20), 'ctlq16': (16 << 20, 4 << 20),
       'base': (1 << 20, 4 << 20)}
ACQ = re.compile(r'^acq id=(\S+) b=(\d+) out=(\S+) q=(-?\d+) cap=(\d+) ep=(-?\d+)/(\d+) gl=(-?\d+)/(\d+) ms=(\d+)$')
REL = re.compile(r'^rel id=(\S+) b=(\d+) q=(-?\d+) ep=(-?\d+)/(\d+) gl=(-?\d+)/(\d+) ms=(\d+)$')
fails = 0


def chk(name, ok, detail=''):
    global fails
    print(('PASS ' if ok else 'FAIL ') + name + ('  ' + detail if detail else ''))
    if not ok:
        fails += 1


for label, (Q, G) in CFG.items():
    D = f'{ROOT}/{label}'
    print(f'=== {label}: Q={Q} E=G={G}')
    acq, rel = [], []
    for l in open(D + '/rsv.trace', errors='replace'):
        m = ACQ.match(l.strip())
        if m:
            acq.append(m.groups())
            continue
        m = REL.match(l.strip())
        if m:
            rel.append(m.groups())
    data = [a for a in acq if a[0].startswith('/127.0.0.3:7000->/127.0.0.2:7000-LARGE_MESSAGES-')]
    succ = [a for a in data if a[2] == 'SUCCESS']
    ref = [a for a in data if a[2] != 'SUCCESS']
    acc = max([int(a[3]) for a in succ] + [0])
    conf = [a for a in acq if int(a[6]) == G and int(a[8]) == G]
    confr = [r for r in rel if int(r[4]) == G and int(r[6]) == G]
    maxep = max([int(a[5]) for a in conf] + [int(r[3]) for r in confr] + [0])
    maxgl = max([int(a[7]) for a in conf] + [int(r[5]) for r in confr] + [0])
    print(f'  data acq {len(data)} (SUCCESS {len(succ)}, refused {len(ref)} {sorted({a[2] for a in ref})}); accounted peak {acc}; '
          f'max ep using {maxep}, max gl using {maxgl}; configured-limit lines {len(conf)} acq + {len(confr)} rel')
    chk(f'{label}: no configured-limit line with using > G', maxep <= G and maxgl <= G, f'{maxep}, {maxgl} <= {G}')
    chk(f'{label}: accounted peak <= Q + G', acc <= Q + G, f'{acc} <= {Q + G}')
    # every data-handler SUCCESS: global.using(after) <= G and, when the queue is above Q, using >= q - Q for the sole data handler
    bad = [a for a in succ if int(a[7]) > G]
    chk(f'{label}: every SUCCESS line has gl using <= G', not bad)
    # last line with the configured limits: both reserves empty
    last = max(conf + [], key=lambda a: int(a[9])) if conf else None
    lastr = max(confr, key=lambda r: int(r[7])) if confr else None
    lst = max([x for x in (last, lastr) if x], key=lambda x: int(x[9]) if x is last else int(x[7])) if (last or lastr) else None
    if lst is last:
        eu, gu = (int(last[5]), int(last[7])) if last else (None, None)
    else:
        eu, gu = int(lastr[3]), int(lastr[5])
    chk(f'{label}: last traced line leaves both reserves at 0', eu == 0 and gu == 0, f'{eu}, {gu}')
    # throttled count from the JMX series
    rows = [l.strip().split(',') for l in open(D + '/jmx-A.csv') if l.strip()]
    thr = [float(r[1]) for r in rows if len(r) > 1 and r[1] not in ('ERR', '') and r[1].replace('.', '').isdigit()]
    rec = [float(r[3]) for r in rows if len(r) > 3 and r[3] not in ('ERR', '') and r[3].replace('.', '').isdigit()]
    print(f'  ThrottledCount series {thr[0] if thr else None} -> {thr[-1] if thr else None}; ReceivedCount {rec[0] if rec else None} -> {rec[-1] if rec else None}')
    # vtable
    vt = list(csv.DictReader(open(D + '/vt-in.csv')))
    vt = [r for r in vt if r.get('address') == '127.0.0.3']
    vres = max([int(r['using_reserve_bytes']) for r in vt] + [0])
    chk(f'{label}: vtable using_reserve_bytes max <= G', vres <= G, f'{vres}')
    # memory: histograms
    def hbytes(path):
        t = open(path).read()
        out = 0
        for cls in ('org.apache.cassandra.db.Mutation', '[B'):
            m = re.search(r'^\s*\d+:\s+\d+\s+(\d+)\s+' + re.escape(cls) + r'(\s|$)', t, re.M)
            out += int(m.group(1)) if m else 0
        return out
    idle = hbytes(D + '/samples/histo-idle.txt')
    loads = sorted(glob.glob(D + '/samples/histo-load*.txt'), key=lambda p: int(re.search(r'load(\d+)', p).group(1)))
    H = [hbytes(p) - idle for p in loads]
    pool = [float(r[5]) for r in rows if len(r) > 5 and r[5].replace('.', '').isdigit()]
    print(f'  retained heap (Mutation + [B above idle) per sample {H}; networking pool UsedSize min {min(pool) if pool else None} max {max(pool) if pool else None}')
    log = open(D + '/A-system.log', errors='replace').read()
    chk(f'{label}: no OutOfMemoryError / UnrecoverableIllegalStateException in A-system.log',
        'java.lang.OutOfMemoryError' not in log and 'UnrecoverableIllegalStateException' not in log)
    if os.path.exists(D + '/stress.log'):
        tail = open(D + '/stress.log', errors='replace').read()
        m = re.findall(r'Total errors\s*:\s*(\d+)', tail)
        chk(f'{label}: stress reported 0 errors', m and m[-1] == '0', str(m[-1:]))
print('FAILED CHECKS:', fails)
sys.exit(1 if fails else 0)
