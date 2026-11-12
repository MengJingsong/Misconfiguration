#!/usr/bin/env python3
"""Per-arm summary table for the R3 recheck. Usage: python3 -I arm_table.py /mydata/oom-recheck/R3/logs arm1 arm2 ..."""
import glob, os, re, sys
L = sys.argv[1]
def rd(p):
    try: return open(p, errors='replace').read()
    except OSError: return ''
hdr = ['arm', 'heap_space_OOM(syslog)', 'jvm_oom_report', 'jvm_fate', 'final_forcedGC_MiB(%)', 'max_afterFullGC_MiB',
       'fullGCs', 'gc_pause_s', 'write_ops/s', 'write_err', 'counter_ops/s', 'counter_err', 'stress_rc', 'workload_s',
       'K_counter', 'K_mem_flush', 'ERROR_lines', 'dmesg', 'dump']
print('\t'.join(hdr))
for arm in sys.argv[2:]:
    d = os.path.join(L, arm); s = rd(d + '/summary.txt')
    syslog = rd(d + '/node-logs/system.log'); stdout = rd(d + '/stdout.txt')
    gcl = ''.join(rd(p) for p in sorted(glob.glob(d + '/node-logs/gc.log*')))
    noom = len(re.findall(r'OutOfMemoryError: Java heap space', syslog))
    jrep = 'yes' if re.search(r'^java.lang.OutOfMemoryError: Java heap space', stdout, re.M) else 'no'
    fate = 'alive at end' if 'node alive at end' in s else ('GONE' if 'GONE' in s else '?')
    m = re.search(r'heap final:\s+garbage-first heap\s+total \d+K, used (\d+)K', s)
    fin = '%.1f (%.0f%%)' % (int(m.group(1)) / 1024, int(m.group(1)) / 1024 / 10.24) if m else '-'
    fulls = re.findall(r'Pause Full \([^)]*\) (\d+)M->(\d+)M', gcl)
    maxfull = max((int(b) for a, b in fulls), default=0)
    pauses = sum(float(x) for x in re.findall(r'Pause [^\n]*?(\d+\.\d+)ms', gcl)) / 1000
    def st(name, key):
        t = rd(d + '/stress-%s.txt' % name)
        if not t: return '-'
        m = re.search(key + r'\s+:\s+([\d,]+)', t)
        return m.group(1).replace(',', '') if m else ('FAIL' if 'FAILURE' in t else 'none')
    rc = re.search(r'stress rc (write=\S+ counter=\S+)', s)
    ws = re.search(r'workloads done at .*\((\d+) s\)', s)
    kc = re.findall(r'Counter Cache : entries (\d+), size ([\d.]+ \w+), capacity (\d+ MiB)', s)
    km = re.search(r'memtable K \(flush lines, max on-heap\): (.*)', s)
    errs = rd(d + '/error-count.txt').strip()
    dm = rd(d + '/dmesg-oom.txt').strip().count('\n') + (1 if rd(d + '/dmesg-oom.txt').strip() else 0)
    dump = re.search(r'heap dumps: (.*)', s)
    print('\t'.join(map(str, [arm, noom, jrep, fate, fin, maxfull, len(fulls), '%.1f' % pauses,
        st('write', 'Op rate'), st('write', 'Total errors'), st('counter', 'Op rate'), st('counter', 'Total errors'),
        rc.group(1) if rc else '-', ws.group(1) if ws else '-', '/'.join(kc[-1]) if kc else '-',
        km.group(1) if km else '-', errs, dm, dump.group(1) if dump else '-'])))
