#!/usr/bin/env python3
"""Stage 4, cluster tier, networking_cache_size-allocateMoreChunks-memoryUsageThreshold (case 9b-9e, amended 2026-10-15).
usage: cluster-run.py <run> build | instrument | value <16|32|64|100|default> | leak

One node from $CASSANDRA_HOME (default ~/cassandra-run3), CASSANDRA_CONF ~/stage4-ncs/conf, data under ~/stage4-ncs/ (kept between
lifetimes), heap 4G, -XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=8G and the Byteman agent with net.btm.
  build       default yaml: ks1.t with 8 rows of 1 MiB (protocol 4), flush, one Data.db, 8 rows
  instrument  16 MiB: a shakedown (not a reading): stall-client.py 8
  value <v>   one lifetime: control (idle 30 s), A (R=4), M (R=48), B (R=192), after-B 15 s
  leak        arm L at the default: 64 x 1 MB INSERTs over v5, residuals, GC.run
Writes summary.txt (EXPECTED lines), phases.csv, samples.csv, bm.trace, ss/, nmt/, session.log to ~/stage4-logs/ncs/<run>/<label>/.
Exit 1: a set-up or instrument check failed. The node is stopped on any exit."""
import csv, glob, os, re, statistics, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run3')
HARNESS = os.path.dirname(os.path.abspath(__file__))
N_DIR = HOME + '/stage4-ncs'
BM = C + '/build/lib/jars/byteman-4.0.20.jar'
MIB = 1048576
FRAME = 131070

if len(sys.argv) < 3 or sys.argv[2] not in ('build', 'instrument', 'value', 'leak') or (sys.argv[2] == 'value' and len(sys.argv) < 4):
    sys.exit(__doc__)
RUN, mode = sys.argv[1], sys.argv[2]
VAL = sys.argv[3] if mode == 'value' else ('16' if mode == 'instrument' else 'default')
label = f'{mode}-{VAL}' if mode == 'value' else mode
D = f'{HOME}/stage4-logs/ncs/{RUN}/{label}'
if os.path.exists(D):
    os.rename(D, D + '.' + time.strftime('%Y%m%d-%H%M%S', time.localtime(os.path.getmtime(D))))
os.makedirs(D + '/ss'); os.makedirs(D + '/nmt')
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
PH = csv.writer(open(D + '/phases.csv', 'w'))
PH.writerow(['phase', 'epoch', 'made', 'refuse', 'overflow', 'overflow_bytes', 'ovfadd', 'ovfsub', 'payload_full', 'payload_small', 'encoded', 'freed',
             'size', 'used', 'overflow_gauge', 'pooled_gauge', 'misses', 'direct_used', 'cc_size'])
TRACE = D + '/bm.trace'
SAMPLES = D + '/samples.csv'
STOP_SAMPLER = D + '/sampler.stop'
SYSTEM_LOG = N_DIR + '/logs/system.log'
SAMPLER = None


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=600, check=True, env=None, quiet=False):
    if not quiet:
        log('+ ' + (cmd if isinstance(cmd, str) else ' '.join(cmd)))
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout, env=env, cwd=C)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet or r.returncode != 0:
        SESSION.write(out[-4000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-800:]}')
    return r.returncode, out


def pid():
    r = subprocess.run("pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon'", shell=True, capture_output=True, text=True)
    return int(r.stdout.split()[0]) if r.returncode == 0 else None


def stop_node():
    global SAMPLER
    if SAMPLER:
        open(STOP_SAMPLER, 'w').close()
        try:
            SAMPLER.wait(timeout=10)
        except Exception:
            SAMPLER.kill()
        SAMPLER = None
    if pid():
        sh('bin/nodetool stopdaemon', check=False, quiet=True, timeout=120)
        for _ in range(90):
            if not pid():
                break
            time.sleep(1)
        if pid():
            log('stopdaemon did not stop the node: kill -9')
            subprocess.run("pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon'", shell=True)
            time.sleep(2)


def fail(msg):
    note('FAIL: ' + msg)
    stop_node()
    sys.exit(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def start_node():
    if pid():
        fail('a CassandraDaemon is already running')
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {VAL}')
    note(y.strip().splitlines()[-1])
    _, ts = sh(f'java -classpath {BM}:build/classes/main:"build/lib/jars/*":"lib/*" org.jboss.byteman.check.TestScript {HARNESS}/net.btm', check=False)
    if 'TestScript: no errors' not in ts:
        fail('Byteman TestScript reports errors')
    jopts = f'-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=8G -javaagent:{BM}=script:{HARNESS}/net.btm -Dstage4.byteman.out={TRACE}'
    env = dict(os.environ, CASSANDRA_CONF=N_DIR + '/conf', CASSANDRA_LOG_DIR=N_DIR + '/logs', MAX_HEAP_SIZE='4G', JVM_EXTRA_OPTS=jopts)
    env.pop('HEAP_NEWSIZE', None)
    sh(f'mv {N_DIR}/logs {N_DIR}/logs.{int(time.time())} 2>/dev/null; mkdir -p {N_DIR}/logs')
    sh(f'bin/cassandra -p {N_DIR}/cassandra.pid > {D}/startup.log 2>&1', env=env)
    t0 = time.time()
    while time.time() - t0 < 300:
        if not pid() and time.time() - t0 > 5:
            fail('the node died during start')
        _, st = sh('bin/nodetool statusbinary', check=False, quiet=True)
        _, ns = sh('bin/nodetool status', check=False, quiet=True)
        if re.search(r'^running\s*$', st, re.M) and re.search(r'^UN', ns, re.M):
            note(f'node up after {time.time() - t0:.0f} s, pid {pid()}')
            return
        time.sleep(2)
    fail('node did not come up in 300 s')


def start_sampler():
    global SAMPLER
    sh(f'mkdir -p {D}/cls && javac -d {D}/cls {HARNESS}/PoolSampler.java')
    SAMPLER = subprocess.Popen(['java', '-cp', D + '/cls', 'PoolSampler', SAMPLES, STOP_SAMPLER, '1000'], cwd=C,
                               stdout=open(D + '/sampler.out', 'w'), stderr=subprocess.STDOUT)
    time.sleep(3)


def samples(t0=0, t1=1e18):
    rows = []
    try:
        for r in csv.DictReader(open(SAMPLES)):
            if r['t1_ms'] == 'ERR':
                continue
            t = int(r['t0_ms']) / 1000
            if t0 <= t <= t1:
                rows.append({k: int(v) for k, v in r.items()})
    except FileNotFoundError:
        pass
    return rows


def dump(fresh=True):
    """The latest dump line's counters; fresh: trigger one first (nodetool version reads ReleaseVersion over JMX; the sampler also
    reads it every second)."""
    if fresh:
        sh('bin/nodetool version', check=False, quiet=True)
        time.sleep(0.3)
    last = None
    try:
        for l in open(TRACE):
            if l.startswith('dump '):
                last = l
    except FileNotFoundError:
        pass
    if not last:
        return None
    d = {k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', last)}
    return d


def made_at(epoch):
    n = 0
    try:
        for l in open(TRACE):
            m = re.match(r'made n=(\d+) ms=(\d+)', l)
            if m and int(m.group(2)) / 1000 <= epoch:
                n = int(m.group(1))
    except FileNotFoundError:
        pass
    return n


def phase(name):
    d = dump() or {}
    s = samples(time.time() - 3)
    r = s[-1] if s else {}
    PH.writerow([name, f'{time.time():.3f}'] + [d.get(k) for k in ('made', 'refuse', 'overflow', 'overflow_bytes', 'ovfadd_bytes', 'ovfsub_bytes',
                                                                   'payload_full', 'payload_small', 'encoded', 'freed')]
                + [r.get(k) for k in ('size', 'used', 'overflow', 'pooled', 'misses', 'direct_used', 'cc_size')])
    note(f'PHASE {name}: counters {d}; gauges {r}')
    return d, r


def nmt(tag):
    _, o = sh(f'jcmd {pid()} VM.native_memory summary', check=False, quiet=True)
    open(f'{D}/nmt/{tag}.txt', 'w').write(o)
    m = re.search(r'-\s+Other \(reserved=\d+KB, committed=(\d+)KB\)', o)
    note(f'NMT {tag}: Other committed {m.group(1) if m else None} KB')


def ss(tag):
    _, srv = sh("ss -tnm state established '( sport = :9042 )'", check=False, quiet=True)
    _, cli = sh("ss -tnm state established '( dport = :9042 )'", check=False, quiet=True)
    open(f'{D}/ss/{tag}.txt', 'w').write(srv + '\n----client----\n' + cli)
    sendq = sum(int(m.group(2)) for m in re.finditer(r'^\s*(\d+)\s+(\d+)\s+\S+:9042\s', srv, re.M))
    recvq = sum(int(m.group(1)) for m in re.finditer(r'^\s*(\d+)\s+(\d+)\s+\S+\s+\S+:9042\s*$', cli, re.M))
    return sendq, recvq


def stall(name, R, hold):
    stop = f'{D}/stop-{name}'
    d0, _ = phase(f'{name}-before')
    t0 = time.time()
    p = subprocess.Popen(['python3', f'{HARNESS}/stall-client.py', str(R), stop], cwd=C, stdout=open(f'{D}/client-{name}.out', 'w'), stderr=subprocess.STDOUT)
    log(f'+ stall-client.py {R} {stop} (background)')
    target = d0.get('payload_full', 0) + 8 * R
    framed = None
    while time.time() - t0 < 30:
        d = dump(fresh=False) or {}
        if d.get('payload_full', 0) >= target:
            framed = time.time() - t0
            break
        if p.poll() is not None:
            break
        time.sleep(0.5)
    if framed is None:
        note(f'RUNBOOK DEFECT {name}: payload_full did not rise by {8 * R} within 30 s (9c: a wait over 30 s is a runbook defect)')
    time.sleep(hold)
    dpk, rpk = phase(f'{name}-peak')
    sq, rq = ss(name)
    if name == 'B':
        nmt('B-peak')
    t_peak = time.time()
    open(stop, 'w').close()
    try:
        p.wait(timeout=30)
    except subprocess.TimeoutExpired:
        p.kill()
    time.sleep(10)
    dafter, rafter = phase(f'{name}-after')
    win = samples(t0, t_peak)
    o_peak = max([r['overflow'] for r in win] or [0])
    direct_rise = max([r['direct_used'] - r['cc_size'] for r in win] or [0]) - IDLE['direct']
    S = sq + rq
    held = dpk.get('encoded', 0) - dpk.get('freed', 0)
    res = dict(R=R, framed=framed, P=8 * MIB * dpk.get('made', 0), P_after=8 * MIB * dafter.get('made', 0), O_peak=o_peak, O_after=rafter.get('overflow'),
               refuse=dpk.get('refuse', 0) - d0.get('refuse', 0), n_o=dpk.get('overflow', 0) - d0.get('overflow', 0),
               o_bytes=dpk.get('overflow_bytes', 0) - d0.get('overflow_bytes', 0), held=held, held_after=dafter.get('encoded', 0) - dafter.get('freed', 0),
               full=dpk.get('payload_full', 0) - d0.get('payload_full', 0), sendq=sq, recvq=rq, S=S, direct_rise=direct_rise,
               misses=rpk.get('misses', 0) - (samples(t0 - 3, t0) or [{'misses': 0}])[-1]['misses'],
               client=open(f'{D}/client-{name}.out').read().strip().replace('\n', ' | '))
    note(f'SCENARIO {name}: ' + ' '.join(f'{k}={v}' for k, v in res.items()))
    return res


IDLE = {}


def lifetime_value():
    global IDLE
    start_node()
    sysctl = sh('sysctl net.ipv4.tcp_wmem net.ipv4.tcp_rmem', check=False, quiet=True)[1].strip().replace('\n', '; ')
    line = [l for l in open(SYSTEM_LOG) if 'Global buffer pool limit is' in l]
    note(f'STARTUP LINE {line[-1].strip() if line else None}; sysctl {sysctl}')
    _, o = sh(['python3', f'{HARNESS}/send-cql.py', 'probe'])
    note(o.strip())
    start_sampler()
    T = 128 * MIB if VAL == 'default' else int(VAL) * MIB
    Tq = (T // (8 * MIB)) * 8 * MIB
    cap = (samples() or [{}])[-1].get('capacity')
    expect(f'Capacity gauge = T ({T})', cap == T)
    expect(f'startup line names {T // MIB}.000MiB for networking', bool(line) and f'{T // MIB}.000MiB for networking' in line[-1])
    nmt('idle')
    t0 = time.time()
    time.sleep(30)
    d_idle, r_idle = phase('idle')
    idle = samples(t0, time.time())
    IDLE = dict(direct=statistics.median([r['direct_used'] - r['cc_size'] for r in idle]) if idle else 0, P=8 * MIB * d_idle.get('made', 0))
    note(f'IDLE: P {IDLE["P"]}; direct - cc median {IDLE["direct"]}; overflow {[r["overflow"] for r in idle][-1:] if idle else None}')
    expect('idle: P = 8 MiB (one slab), O = 0', IDLE['P'] == 8 * MIB and idle and all(r['overflow'] == 0 for r in idle))
    a = stall('A', 4, 10)
    expect('A: no refusal, O = 0 throughout, P unchanged from idle (<= 16 MiB)', a['refuse'] == 0 and a['O_peak'] == 0 and a['P'] <= 16 * MIB)
    m = stall('M', 48, 20)
    D_m = 48 * MIB
    if T <= 32 * MIB:
        expect(f'M: P = T\' ({Tq}) and P + O_peak within [D - S - 1 MiB, D + 1 MiB]', m['P'] == Tq and D_m - m['S'] - MIB <= m['P'] + m['O_peak'] <= D_m + MIB)
    else:
        expect(f'M: P after M within [48, 56] MiB (64 at most), O = 0, no refusal — not T\' ({Tq})',
               48 * MIB <= m['P'] <= 56 * MIB and m['O_peak'] == 0 and m['refuse'] == 0)
        expect(f'M: P - P_idle within 2 MiB of 40-48 MiB (not {Tq - IDLE["P"]})', 40 * MIB - 2 * MIB <= m['P'] - IDLE['P'] <= 48 * MIB + 2 * MIB)
    b = stall('B', 192, 20)
    D_b = 192 * MIB
    PB = b['P']
    expect(f'B: P = T\' ({Tq}) exactly, never above', PB == Tq and made_at(time.time()) * 8 * MIB <= Tq)
    expect(f'B: P + O_peak within [D - S - 1 MiB, D + 1 MiB] = [{D_b - b["S"] - MIB}, {D_b + MIB}]', D_b - b['S'] - MIB <= PB + b['O_peak'] <= D_b + MIB)
    expect('B: refusals > 0, Misses >= overflow allocations', b['refuse'] > 0 and b['misses'] >= b['n_o'])
    expect(f'B: O_peak = 131,070 x n_o of full frames + < 1 KiB per response', b['O_peak'] <= b['o_bytes'] and b['o_bytes'] - FRAME * (b['o_bytes'] // FRAME) <= 1024 * 192)
    expect(f'B: direct rise within [D - S - 10 MiB, D + 10 MiB] = [{D_b - b["S"] - 10 * MIB}, {D_b + 10 * MIB}]', D_b - b['S'] - 10 * MIB <= b['direct_rise'] <= D_b + 10 * MIB)
    expect('B: held frames during the stall well above zero (the client did not read)', b['held'] > 64)
    t0 = time.time()
    time.sleep(15)
    d_aft, r_aft = phase('after-B')
    after = samples(t0, time.time())
    nmt('after-B')
    direct_after = statistics.median([r['direct_used'] - r['cc_size'] for r in after]) if after else None
    full_overflowed = d_aft.get('overflow', 0)
    note(f'AFTER B: held {d_aft.get("encoded", 0) - d_aft.get("freed", 0)}; P {8 * MIB * d_aft.get("made", 0)}; O {r_aft.get("overflow")}; '
         f'direct - cc median {direct_after} (rise {direct_after - IDLE["direct"] if direct_after is not None else None}); overflow allocations in the lifetime {full_overflowed}')
    expect('after B: held frames 0', d_aft.get('encoded', 0) - d_aft.get('freed', 0) == 0)
    expect('after B: P unchanged', 8 * MIB * d_aft.get('made', 0) == PB)
    expect(f'after B: O within a few KiB of zero (−6 B per overflowed full frame)', r_aft.get('overflow') is not None and -64 * 1024 <= r_aft['overflow'] <= 0)
    expect(f'after B: direct rise = T\' - P_idle ({Tq - IDLE["P"]}) ± 2 MiB', direct_after is not None and abs((direct_after - IDLE['direct']) - (Tq - IDLE['P'])) <= 2 * MIB)
    info = [l for l in open(SYSTEM_LOG) if 'Maximum memory usage reached' in l and 'networking' in l]
    note(f'INFO lines for networking: {len(info)}; failed to allocate: {sum(1 for l in open(SYSTEM_LOG) if "failed to allocate chunk" in l)}')
    note(f'RESULT value {VAL}: T {T} T\' {Tq} | A P {a["P"]} O {a["O_peak"]} | M P {m["P"]} O {m["O_peak"]} S {m["S"]} | B P {PB} O {b["O_peak"]} '
         f'S {b["S"]} direct_rise {b["direct_rise"]} | after direct_rise {direct_after - IDLE["direct"] if direct_after is not None else None}')


def lifetime_instrument():
    start_node()
    _, o = sh(['python3', f'{HARNESS}/send-cql.py', 'probe'])
    note(o.strip())
    start_sampler()
    cap = (samples() or [{}])[-1].get('capacity')
    note(f'INSTRUMENT: Capacity {cap}')
    time.sleep(5)
    phase('idle')
    global IDLE
    IDLE = dict(direct=0, P=0)
    r = stall('S', 8, 5)
    ok = r['full'] >= 64 and r['held'] > 0 and r['sendq'] > 0 and r['held_after'] == 0
    note(f'INSTRUMENT CHECK {"passed" if ok else "FAILED"}: full frames +{r["full"]}, held {r["held"]} (after {r["held_after"]}), Send-Q {r["sendq"]}, Recv-Q {r["recvq"]}')
    if not ok:
        fail('instrument check failed')


def lifetime_build():
    sh(f'rm -rf {N_DIR}/data {N_DIR}/commitlog {N_DIR}/hints {N_DIR}/saved_caches {N_DIR}/cdc_raw')
    start_node()
    _, o = sh(['python3', f'{HARNESS}/send-cql.py', 'build'])
    note(o.strip())
    sh('bin/nodetool flush ks1 t')
    files = glob.glob(f'{N_DIR}/data/ks1/t-*/*-Data.db')
    note(f'BUILD: Data.db files {files}')
    if len(files) != 1 or '8 rows' not in o:
        fail('build check failed: need one Data.db and 8 rows')


def lifetime_leak():
    start_node()
    start_sampler()
    t0 = time.time()
    time.sleep(30)
    d0, r0 = phase('L-idle')
    _, o = sh(['python3', f'{HARNESS}/send-cql.py', 'big-insert', '64'], timeout=900)
    note(o.strip())
    time.sleep(30)
    d1, r1 = phase('L-after-30s')
    sh(f'jcmd {pid()} GC.run', check=False)
    time.sleep(10)
    d2, r2 = phase('L-after-GC')
    ovf_res = r1.get('overflow', 0) - r0.get('overflow', 0)
    pooled_res = (r1.get('used', 0) - r1.get('overflow', 0)) - (r0.get('used', 0) - r0.get('overflow', 0))
    added = d1.get('ovfadd_bytes', 0) - d0.get('ovfadd_bytes', 0)
    subtracted = d1.get('ovfsub_bytes', 0) - d0.get('ovfsub_bytes', 0)
    note(f'ARM L: OverflowSize residual {ovf_res}; UsedSize - OverflowSize residual {pooled_res}; overflow added {added} subtracted {subtracted} '
         f'(short by {added - subtracted}); direct {r0.get("direct_used")} -> {r1.get("direct_used")} -> after GC {r2.get("direct_used")}; '
         f'OverflowSize after GC {r2.get("overflow")}')
    expect('arm L: every insert acknowledged', 'acknowledged 64 of 64' in o)
    expect('arm L (leak as derived): OverflowSize residual = 58,724,288 B exactly', ovf_res == 58724288)
    expect('arm L (leak as derived): UsedSize - OverflowSize residual = 5,373,952 B ± 64 x 2,048', abs(pooled_res - 5373952) <= 64 * 2048)
    expect('arm L: overflow subtracted short of added by 58,724,288 B', added - subtracted == 58724288)
    expect('arm L: direct falls back after GC.run while OverflowSize does not', r2.get('direct_used', 0) < r1.get('direct_used', 0) and r2.get('overflow') == r1.get('overflow'))


try:
    note(f'RUN {RUN} LABEL {label}; date {time.strftime("%F %T %Z")}; host {os.uname().nodename}')
    note('CLONE ' + sh('git describe --tags && git rev-parse --short HEAD')[1].replace('\n', ' ').strip() + ' | HARNESS md5 ' +
         sh(f'cd {HARNESS} && md5sum *.btm *.py *.sh *.java | md5sum')[1].split()[0])
    {'build': lifetime_build, 'instrument': lifetime_instrument, 'value': lifetime_value, 'leak': lifetime_leak}[mode]()
    note('DONE')
except SystemExit:
    raise
except Exception as e:
    import traceback
    note(f'FAIL (exception): {e!r}')
    SESSION.write(traceback.format_exc()); SESSION.flush()
    sys.exit(1)
finally:
    stop_node()
    subprocess.run(f'cp {N_DIR}/logs/system.log {N_DIR}/conf/cassandra.yaml {D}/ 2>/dev/null', shell=True)
