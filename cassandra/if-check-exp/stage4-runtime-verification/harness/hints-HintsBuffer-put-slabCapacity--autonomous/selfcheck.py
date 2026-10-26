#!/usr/bin/env python3
"""Independent self-check of run 1 for hints-HintsBuffer-put-slabCapacity--autonomous. Re-parses the RAW files only
(hb.trace, samples-jmx.csv, hints-ls.txt, session.log client lines, STAGE4 .out files), not phases.json / summary.txt / samples.csv,
and prints the numbers the conclusion cites. usage: python3 -I selfcheck.py [run]  (default run1)."""
import glob, json, os, re, sys

RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
L = os.path.expanduser(f'~/s4-hb-logs/{RUN}')
MIB = 1 << 20

print('== unit ==')
for f in sorted(glob.glob(f'{L}/unit/*.out')):
    t = open(f).read().splitlines()
    ok = sum(1 for l in t if l.startswith('STAGE4 check') and ' ok ' in l)
    bad = [l[:200] for l in t if l.startswith('STAGE4 check') and ' MISMATCH ' in l]
    print(os.path.basename(f), 'checks ok', ok, 'MISMATCH', len(bad))
    for l in bad:
        print('   ', l)
    for l in t:
        if re.match(r'STAGE4 unit (rotation end|stall|derive direct)', l):
            print('   ', l[:330])
for f in sorted(glob.glob(f'{L}/unit/*.xml')):
    x = open(f, errors='replace').read()
    m = re.search(r'<testsuite [^>]*tests="(\d+)"[^>]*', x)
    print(os.path.basename(f), re.findall(r'(errors|failures|tests)="(\d+)"', x[:600]))

print('== cluster ==')
for d in sorted(glob.glob(f'{L}/cluster/*/')):
    arm = os.path.basename(d.rstrip('/'))
    if not os.path.exists(d + 'hb.trace'):
        continue
    ses = open(d + 'session.log', errors='replace').read()
    n = int(re.search(r'-Dcassandra.MAX_HINT_BUFFERS=(\d+)', ses).group(1))
    tr = {}
    for l in open(d + 'hb.trace', errors='replace'):
        k = l.split(' ', 1)[0]
        tr.setdefault(k, []).append(dict(re.findall(r'(\w+)=(\S+)', l)))
    created = tr.get('created', [])
    sizes = sorted({int(c['size']) for c in created})
    # baseline mark: the "trace before the workload" line time is not in raw files; use the first workload sample = hints client start
    rows = []
    for l in open(d + 'samples-jmx.csv'):
        p = l.strip().split(',')
        if len(p) == 5 and p[0].isdigit() and p[1] not in ('ERR',):
            rows.append((int(p[0]), float(p[1]), float(p[2]), float(p[3]), p[4]))
    m = re.search(r"'ms_start': (\d+), 'ms_end': (\d+)", ses)
    ms0, ms1 = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    line = f'{arm}: n={n} created={len(created)} sizes={[s / MIB for s in sizes]} waiting={len(tr.get("waiting", []))} flushrun={len(tr.get("flushrun", []))}'
    if ms0:
        base = [r for r in rows if r[0] <= ms0 - 1000]
        base = base[-1] if base else None
        k0 = sum(1 for c in created if int(c['ms']) <= ms0 - 1000)
        win = [r for r in rows if ms0 <= r[0] <= ms1 + 1000 * 40]
        peak = max(win, key=lambda r: r[1])
        S = sizes[0] if sizes else 0
        print(line, f'k0={k0} base_direct={base[1] / MIB:.2f}MiB peak_direct={peak[1] / MIB:.2f}MiB peak_delta={(peak[1] - base[1]) / MIB:.2f}MiB '
                    f'peak_pool={(peak[1] - base[1] + k0 * S) / MIB:.2f}MiB n*S={n * S / MIB:.0f}MiB')
        wk = [r for r in rows if ms0 <= r[0] <= ms1]
        h = wk[len(wk) // 2:]
        print('   second-half range of direct during the workload: %.2f MiB; samples %d' % ((max(r[1] for r in h) - min(r[1] for r in h)) / MIB, len(wk)))
        ls = open(d + 'hints-ls.txt').read().splitlines()
        tot = sum(int(l.split()[4]) for l in ls if len(l.split()) >= 9 and l.split()[4].isdigit())
        print('   hints on disk at the end (ls -l, sum of sizes): %.1f MiB; client:' % (tot / MIB), re.search(r"workload result: (\{[^}]*\})", ses).group(1)[:160] if re.search(r"workload result", ses) else '-')
    else:
        print(line)
        for l in re.findall(r'step [^\n]*', ses):
            print('   ', l[:260])
        for k in ('alloc', 'allocreject'):
            print('   ', k, [(a['hint']) for a in tr.get(k, [])])
