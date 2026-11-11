#!/usr/bin/env python3
"""Independent self-check (results §5) for fs.s3a.prefetch.block.count-acquireHelper-size--autonomous, run 1.
Re-parses the raw files (surefire output, per-run TSVs, throttle/status files, the cluster log's array counts, RandomReads
output, OOM dumps) without the run scripts' summaries, and evaluates the frozen rows A4 (unit) and A9 (cluster) in order.
Usage: python3 -I selfcheck.py <run-dir>   (prints a report; exit 0)"""
import csv, glob, os, re, subprocess, sys

RUN = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
MiB = 1 << 20
out = []


def say(s):
    out.append(s); print(s)


# ------------------------------------------------------------------ unit (A4)
say('== unit tier (A4 rows, in order)')
sf = glob.glob(f'{RUN}/src/hadoop-tools/hadoop-aws/target/surefire-reports/*TestPrefetchPoolBound-output.txt')[0]
rep = open(glob.glob(f'{RUN}/src/hadoop-tools/hadoop-aws/target/surefire-reports/*TestPrefetchPoolBound.txt')[0]).read()
say('surefire: ' + re.search(r'Tests run:.*', rep).group(0))
U = {}
ctl = []
for line in open(sf):
    r = line.strip().split(',')
    if r[0] == 'IFCHK' and r[1] == 'count':
        c = int(r[2])
        U[c] = dict(zip('printedSize poolSize seqMax rndMax hookMax seqDen rndDen atFull crc mism hb hp ha'.split(),
                        map(int, r[3:16])))
    elif r[0] == 'IFCHK-CTL':
        ctl.append(line.strip())
for c in sorted(U):
    u = U[c]
    say(f'c={c} size {u["printedSize"]}/{u["poolSize"]} max seq/rnd/hook {u["seqMax"]}/{u["rndMax"]}/{u["hookMax"]} '
        f'denials seq/rnd/atFull {u["seqDen"]}/{u["rndDen"]}/{u["atFull"]} crc {u["crc"]} mism {u["mism"]} '
        f'heap before/peak/after MiB {u["hb"]/MiB:.2f}/{u["hp"]/MiB:.2f}/{u["ha"]/MiB:.2f}')
for l in ctl:
    say(l[:200])
fails = 'Failures: 0, Errors: 0' not in rep
inv = (fails or len({u['crc'] for u in U.values()}) != 1 or any(u['mism'] for u in U.values())
       or any(u['printedSize'] != c + 1 for c, u in U.items())
       or not any('PrefetchOptions=rejected' in x and 'intOption=rejected' in x for x in ctl))
ref = any(max(u['seqMax'], u['rndMax'], u['hookMax']) > u['poolSize'] for u in U.values()) or \
    len({max(u['seqMax'], u['hookMax']) for u in U.values()}) == 1
notsat = any(max(u['seqMax'], u['hookMax']) < c + 1 for c, u in U.items())
nodis = all(u['rndDen'] == 0 for u in U.values())
D = {c: u['hp'] - u['hb'] for c, u in U.items()}
excess = {c: (D[c] - D[1]) / MiB - (c - 1) for c in U}
heapnot = any(e > 4 for e in excess.values())
say('D(c)-D(1)-(c-1) MiB: ' + ', '.join(f'{c}:{e:+.2f}' for c, e in sorted(excess.items())))
say('peak-after vs (c+1)-4: ' + ', '.join(f'{c}:{(u["hp"]-u["ha"])/MiB:.2f}>={c-3}' for c, u in sorted(U.items())))
say('denialsAtFull == rndDenials: ' + str(all(u['atFull'] == u['rndDen'] for u in U.values())))
row = ('(i) Invalid' if inv else '(ii) Refuted' if ref else '(iii) Not confirmed - not saturated' if notsat else
       '(iv) Not confirmed - disallow never observed' if nodis else '(v) Not confirmed - counter capped, heap not'
       if heapnot else '(vi) Confirmed')
say(f'unit flags: invalid={inv} refuted={ref} notsat={notsat} nodisallow={nodis} heapnot={heapnot} -> {row}')

# ------------------------------------------------------------------ cluster (A9)
say('== cluster tier (A9 rows, in order)')
O = f'{RUN}/out'
log = open(f'{RUN}/logs/cluster/cluster-run.log').read()


def tsvmax(name):
    rows = list(csv.DictReader(open(f'{O}/{name}.tsv'), delimiter='\t'))
    return (max(int(r['B_bytes']) for r in rows) if rows else None), len(rows)


def arrays(name):
    m = re.findall(rf'\] {re.escape(name)}: .*?len33554432=(\d+) len16777216=(\d+)', log)
    return tuple(map(int, m[-1])) if m else None


def rd(name, ext):
    f = f'{O}/{name}.{ext}'
    return open(f).read().strip() if os.path.exists(f) else 'missing'


base, _ = tsvmax('classic-n1')
C = {}
for name in ['classic-n1', 'classic-n16', 'local', 'seq-n1', 'seq-n4', 'seq-n8', 'seq-n16', 'tight-n4', 'tight-n8',
             'small-n1', 'small-n16', 'rr-n1', 'rr-n8']:
    bm, ns = tsvmax(name)
    C[name] = dict(B=bm, ns=ns, arr=arrays(name), thr=rd(name, 'throttle'), st=rd(name, 'status'))
    err = rd(name, 'err')
    C[name]['oom_err'] = 'OutOfMemoryError' in err
    js = f'{O}/{name}.jstack'
    if os.path.exists(js) and name.startswith('tight'):
        t = open(js).read()
        mm = re.search(r'"main".*?\n\n', t, re.S)
        say(f'{name} jstack main: ' + (' / '.join(x.strip() for x in mm.group(0).splitlines()[1:7]) if mm else 'none'))
    C[name]['gauge'] = re.findall(r'stream_read_active_memory_in_use[^,;\n]*', err)[:2]
    rise = (bm - base) / MiB if bm is not None else None
    C[name]['rise'] = rise
    say(f'{name}: B_max={bm} rise={rise if rise is None else round(rise, 1)} MiB samples={ns} arrays(32M,16M)={C[name]["arr"]} '
        f'throttle=[{C[name]["thr"]}] {C[name]["st"]} oom_in_stderr={C[name]["oom_err"]} gauge={C[name]["gauge"]}')
RR = {}
for n in (1, 8):
    o = rd(f'rr-n{n}', 'out')
    say(f'rr-n{n} out: ' + ' | '.join(l[:220] for l in o.splitlines() if l.startswith('IFCHK')))
    m = re.search(r'^IFCHK-RR,(.*)$', o, re.M)
    if m:
        v = list(map(int, m.group(1).split(',')))
        RR[n] = dict(zip('n size maxCreated wait atWait bytes mism samples'.split(), v), final=True)
    else:  # A11: killed at the stop condition -> last progress line
        pl = re.findall(r'^IFCHK-RR-PROGRESS,(.*)$', o, re.M)
        if pl:
            f = pl[-1].split(',')
            v = list(map(int, f[:9]))
            RR[n] = dict(zip('n size maxCreated wait atWait iter bytes mism samples'.split(), v), final=False, last=f[9])
    say(f'rr-n{n} parsed: {RR.get(n)}')
    js = f'{O}/rr-n{n}.jstack'
    if os.path.exists(js):
        t = open(js).read()
        mm = re.search(r'"main".*?\n\n', t, re.S)
        say(f'rr-n{n} jstack main: ' + (' / '.join(x.strip() for x in mm.group(0).splitlines()[1:9]) if mm else 'none'))
oomdumps = sorted(glob.glob(f'{RUN}/dumps/java_pid*.hprof'))
for f in oomdumps:
    r = subprocess.run(['python3', '-I', f'{HERE}/hprof_count.py', f, str(32 * MiB), str(16 * MiB)], capture_output=True,
                       text=True)
    say(f'OOM dump {os.path.basename(f)} ({os.path.getmtime(f):.0f}): {r.stdout.strip()}')

full = 'bytes=2147483648'
inv = ((C['classic-n1']['arr'] or (1,))[0] > 0 or (C['classic-n16']['arr'] or (1,))[0] > 0
       or (C['classic-n16']['B'] - C['classic-n1']['B']) >= 32 * MiB
       or any(full not in C[k]['thr'] for k in ['classic-n1', 'classic-n16', 'local', 'seq-n1', 'seq-n4', 'seq-n8', 'seq-n16'])
       or any(r['mism'] for r in RR.values()) or len(RR) != 2)
seqn = {1: 'seq-n1', 4: 'seq-n4', 8: 'seq-n8', 16: 'seq-n16'}
ref = (any(C[k]['arr'][0] > n + 1 for n, k in seqn.items()) or any(r['maxCreated'] > r['size'] for r in RR.values())
       or (C['seq-n1']['arr'][0] == C['seq-n16']['arr'][0] and abs(C['seq-n1']['rise'] - C['seq-n16']['rise']) < 16))
notsat = any(C[k]['arr'][0] < n + 1 for n, k in seqn.items())
heapnot = {n: round(C[k]['rise'] - ((n + 1) * 32 + 16), 1) for n, k in seqn.items()}
heapnotb = any(v > 0 for v in heapnot.values())
nodis = all(r['wait'] == 0 for r in RR.values())
t4ok = full in C['tight-n4']['thr'] and C['tight-n4']['st'].startswith('PIPESTATUS=0')
t8oom = C['tight-n8']['oom_err']
tight = (not t4ok) or (not t8oom)
say(f'rise minus upper bound (n+1)*32+16 MiB: {heapnot}; lower: ' +
    str({n: round(C[k]['rise'] - ((n + 1) * 32 - 16), 1) for n, k in seqn.items()}))
say(f'tight: n4 completes={t4ok} n8 OOM in stderr={t8oom}')
row = ('(i) Invalid' if inv else '(ii) Refuted' if ref else '(iii) Not confirmed - not saturated' if notsat else
       '(iv) Not confirmed - counter capped, heap not' if heapnotb else '(v) Not confirmed - disallow never observed'
       if nodis else '(vi) Not confirmed - tight heap' if tight else '(vii) Confirmed')
say(f'cluster flags: invalid={inv} refuted={ref} notsat={notsat} heapnot={heapnotb} nodisallow={nodis} tight={tight} -> {row}')
say('small control (one 16 MiB array, no 32 MiB): ' + str({k: C[k]['arr'] for k in ('small-n1', 'small-n16')}))
left = subprocess.run("ps -eo pid,cmd | grep -E '[j]ava' | grep -F '" + RUN + "' | wc -l", shell=True, capture_output=True,
                      text=True).stdout.strip()
say(f'JVMs of this run still running: {left}')
open(f'{RUN}/logs/selfcheck.txt', 'w').write('\n'.join(out) + '\n')
