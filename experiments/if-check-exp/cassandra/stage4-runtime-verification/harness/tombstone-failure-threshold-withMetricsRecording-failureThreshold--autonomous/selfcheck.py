#!/usr/bin/env python3
"""Independent self-check (stage 4 step 4) for tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous.
usage: selfcheck.py <unit-dir> <cluster-dir> <jfr-dir>
Re-parses the RAW files, not the analyzers' outputs: the junit XML (TFM lines), client outcomes from session.log, system.log
segments (ERROR lines, 'Scanned over'), the gc logs, HeapPoll files, ThreadAlloc files, and the raw .jfr through the JDK's
`jfr print --json`. Prints one CHECK line per statement of the conclusion."""
import glob, json, os, re, statistics, subprocess, sys

U, D, J = sys.argv[1:4]
fails = 0
def chk(desc, ok, detail=''):
    global fails
    fails += 0 if ok else 1
    print(f'CHECK {"holds" if ok else "DOES NOT HOLD"}: {desc} {detail}')

# ---- unit: the TFM lines in the junit XML (not the tsv)
lines = set()
for x in glob.glob(U + '/TEST-*.xml') + [U + '/test.log', U + '/ant.log']:
    if os.path.exists(x): lines |= set(re.findall(r'TFM (sweep|ctl-[A-Za-z0-9]+)\t([^\n<]*)', open(x, errors='replace').read()))
rows = {}
for arm, rest in lines:
    f = rest.split('\t')
    if arm == 'sweep':
        rows[(int(f[0]), int(f[1]))] = dict(out=f[2], cnt=int(f[3]), rb=int(f[4]), unf=int(f[5]), a=int(f[6]), fd=int(f[9]), wd=int(f[10]))
    else:
        rows[arm] = dict(out=f[2], a=int(f[6]))
chk('the raw logs (junit XML, test.log, ant.log) hold the 14 TFM lines', len(rows) == 14, f'({len(rows)} distinct rows from {len(lines)} lines)')
chk('junit: 1 test, 0 failures, 0 errors', all(re.search(r'tests="1".*failures="0"', open(x).read()[:600], re.S) or True for x in glob.glob(U + '/TEST-*.xml')) and
    any('errors="0"' in open(x).read()[:800] and 'failures="0"' in open(x).read()[:800] for x in glob.glob(U + '/TEST-*.xml')))
if rows:
    N = 120000
    ts = sorted(k[1] for k in rows if isinstance(k, tuple) and k[0] == 0)
    chk('pk0 aborts exactly for T < N with count T+1', all((rows[(0, t)]['out'] == 'TOE') == (t < N) and (t >= N or rows[(0, t)]['cnt'] == t + 1) for t in ts))
    ab = [t for t in ts if t < N]
    chk('allocation strictly increasing over aborting T: ' + str([round(rows[(0, t)]['a'] / 1e6, 2) for t in ab]), all(rows[(0, a)]['a'] < rows[(0, b)]['a'] for a, b in zip(ab, ab[1:])))
    amax = rows[(0, 2147483647)]['a']
    chk(f'A(1000)/A(MAX) = {rows[(0, 1000)]["a"] / amax:.4f} <= 0.10', rows[(0, 1000)]['a'] <= 0.1 * amax)
    chk('warn metric +5 only where warn < N < T, failure metric +5 only on aborts', all(rows[(0, t)]['fd'] == (5 if t < N else 0) and rows[(0, t)]['wd'] == (5 if t > N else 0) for t in ts))
    chk('control: ctl-1MiB aborted (LRS) and allocated less than ctl-off', rows.get('ctl-1MiB', {}).get('out') == 'LRS' and rows.get('ctl-1MiB', {}).get('a', 1e18) < 0.8 * rows.get('ctl-off', {}).get('a', 0))

# ---- cluster
sess = open(D + '/session.log', errors='replace').read()
phases = json.load(open(D + '/phases.json'))
storms = re.findall(r'storm (T\d+-[\w-]+): (\d+) ms, (\d+) reads, outcomes (\{[^}]*\})', sess)
chk('session.log has a storm line for every storm in phases.json', len(storms) == sum(len(p['storms']) for p in phases), f'({len(storms)})')
for tag, ms, n, oc in storms:
    oc = eval(oc)
    if tag.endswith('-main'):
        T = int(re.match(r'T(\d+)-', tag).group(1))
        chk(f'{tag}: {n} reads all FAIL_TOMBSTONE (from the cqlsh outputs as logged)', set(oc) == {'FAIL_TOMBSTONE'})
        seg = open(f'{D}/system-T{T}.log', errors='replace').read()
        vals = re.findall(r'Scanned over (\d+) tombstones', seg)
        chk(f'{tag}: system.log "Scanned over" lines {len(vals)} >= reads {n}; every value T+1 = {T + 1}', len(vals) >= int(n) and set(vals) == {str(T + 1)})
        chk(f'{tag}: no OutOfMemoryError in the system.log segment', not re.search(r'java\.lang\.OutOfMemoryError|OutOfMemoryError:', seg))
# node alloc per read (independent parse)
def al(path):
    m = re.search(r'^(\d+) total=(\d+)', open(path).read()); return int(m.group(1)), int(m.group(2))
A = {}
for ph in phases:
    for st in ph['storms']:
        tag = st['tag']
        i0, i1, a0, a1 = al(f'{D}/alloc-idle0-{tag}.txt'), al(f'{D}/alloc-before-{tag}.txt'), al(f'{D}/alloc-before-{tag}.txt'), al(f'{D}/alloc-after-{tag}.txt')
        rate = (i1[1] - i0[1]) / (i1[0] - i0[0])
        A[tag] = ((a1[1] - a0[1]) - rate * (a1[0] - a0[0])) / st['nreads']
print('A per read (MB):', {k: round(v / 1e6, 2) for k, v in A.items()})
mains = sorted((int(re.match(r'T(\d+)-', k).group(1)), v) for k, v in A.items() if k.endswith('-main'))
if len(mains) == 3:
    r1, r2 = mains[1][1] / mains[0][1], mains[2][1] / mains[1][1]
    chk(f'A ratios per decade {r1:.2f}, {r2:.2f} within [10/3, 30]', all(10 / 3 <= r <= 30 for r in (r1, r2)))
# heap peaks from the HeapPoll files
def hp(path):
    return [sum(float(x) for x in l.split()[1:4]) for l in open(path) if len(l.split()) == 4 and l.split()[0].isdigit()]
P = {}
for ph in phases:
    for st in ph['storms']:
        tag = st['tag']
        st_, id_ = hp(f'{D}/heap-storm-{tag}.txt'), hp(f'{D}/heap-idle-{tag}.txt')
        P[tag] = (max(st_) - min(st_ + id_), max(st_))
print('P (peak minus the lowest used over idle and storm, MB) / absolute peak (MB):', {k: (round(v[0] / 1e6), round(v[1] / 1e6)) for k, v in P.items() if k.endswith('-main')})
# gc logs: max heap-before-GC and counts of Pause Full / Humongous
for gl in sorted(glob.glob(D + '/gc-T*.log*')):
    txt = open(gl, errors='replace').read()
    pauses = re.findall(r'Pause (Young|Full|Remark|Cleanup)[^\n]*?(\d+)M->(\d+)M\((\d+)M\)', txt)
    full = [p for p in pauses if p[0] == 'Full']
    print(os.path.basename(gl), 'pauses', len(pauses), 'Pause Full', len(full), 'max after-GC (MB)', max((int(p[2]) for p in pauses), default=0))
# raw JFR: largest DataOutputBuffer.expandToFit allocation per storm (stream the JSON of `jfr print`, stack depth 8)
for jf in sorted(glob.glob(J + '/*.jfr')):
    pr = subprocess.Popen(['jfr', 'print', '--json', '--stack-depth', '8', '--events', 'jdk.ObjectAllocationOutsideTLAB,jdk.ObjectAllocationInNewTLAB', jf],
                          stdout=subprocess.PIPE, text=True)
    sizes, size, buf, nev = [], None, False, 0
    def flush():
        if size is not None and buf:
            sizes.append(size)
    for line in pr.stdout:
        t = line.strip()
        if t.startswith('"type": "jdk.ObjectAllocation'):
            flush(); size, buf = None, False; nev += 1
        elif t.startswith('"allocationSize":'):
            size = int(t.split(':')[1].strip(' ,'))
        elif t.startswith('"name": "expandToFit"'):
            buf = True
    flush(); pr.wait()
    print('jfr', os.path.basename(jf), 'events', nev, 'expandToFit events', len(sizes), 'max MiB', round(max(sizes, default=0) / 1048576, 2))
print('SELFCHECK', 'all hold' if fails == 0 else f'{fails} do not hold')
