#!/usr/bin/env python3
"""Cluster tier driver for sai-SegmentRowIdOrdinalPairs-add-capacity--autonomous (B3e). One node, own ports (storage 7028, native 9350, JMX 7328,
Byteman 9328, loopback 127.0.28.1), tree ~/s4-sr (built with `ant jar`; ant is never run here).
usage: SR_RUN=run1 cluster-run.py value <default|1000|64000> [--first]      --first wipes the data dirs, loads ks.t / ks.mt, runs the memtable control
Output: ~/stage4-logs/sr/<run>/<label>/ (summary.txt = EXPECTED lines and readings, sr-trace.out = the Byteman lines, traces, jvm-args, system.log).
The node is stopped on any exit. Nothing here judges a result: EXPECTED lines state whether a reading met the frozen B3f prediction; the AI judges."""
import json, os, re, subprocess, sys, time, resource

HARNESS = os.path.dirname(os.path.abspath(__file__))
C = os.path.expanduser('~/s4-sr'); ROOT = os.path.expanduser('~/s4-sr-run')
RUN = os.environ.get('SR_RUN', 'run1')
BM = C + '/build/lib/jars/byteman-4.0.20.jar'
PORTS = (7028, 7328, 9350, 9328)
DEFAULT = 16000
resource.setrlimit(resource.RLIMIT_NOFILE, (100000, 100000))

arg = sys.argv[2] if len(sys.argv) > 2 else 'default'
FIRST = '--first' in sys.argv
LIMIT = DEFAULT if arg == 'default' else int(arg)
LABEL = arg
D = os.path.expanduser(f'~/stage4-logs/sr/{RUN}/{LABEL}'); os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a'); SUMMARY = open(D + '/summary.txt', 'a')
TRACE = D + '/sr-trace.out'
PID = None
# K: bytes the Byteman rule machinery adds between entry and exit, from calibrate.sh (same rules, SrMem, no node). The readings keep the raw value.
K = int([l.split()[1] for l in open(os.path.expanduser(f'~/stage4-logs/sr/{RUN}/calib/calib.txt')) if l.startswith('K_MODE')][0])
def near(allocs, base):
    return bool(allocs) and all(0 <= a - base - K <= 1024 for a in allocs)

def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'; print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()
def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)
def node_env():
    return dict(os.environ, CASSANDRA_CONF=ROOT + '/conf', CASSANDRA_LOG_DIR=ROOT + '/logs', CASSANDRA_HOME=C)
def sh(cmd, timeout=600, check=True, env=None):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env or node_env(), cwd=C)
    out = (r.stdout or '') + (r.stderr or '')
    SESSION.write(out[-4000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-600:]}')
    return r.returncode, out
NT = 'bin/nodetool -h 127.0.0.1 -p 7328 '
def ports_busy():
    _, o = sh("ss -ltn | awk '{print $4}'", check=False)
    return [p for p in PORTS if re.search(r':%d$' % p, o, re.M)]
def own_pid():
    r = subprocess.run("ps -eo pid,args | grep '[o]rg.apache.cassandra.service.CassandraDaemon' | awk '{print $1}'", shell=True, capture_output=True, text=True)
    for p in r.stdout.split():
        try:
            if ROOT + '/conf' in open(f'/proc/{p}/cmdline').read(): return p
        except OSError: pass
    return None
def stop_node():
    global PID
    PID = PID or own_pid()
    if PID and os.path.exists(f'/proc/{PID}'):
        sh(NT + 'stopdaemon', check=False, timeout=120)
        for _ in range(90):
            if not os.path.exists(f'/proc/{PID}'): break
            time.sleep(1)
        if os.path.exists(f'/proc/{PID}'):
            log(f'kill -9 {PID}'); subprocess.run(['kill', '-9', PID]); time.sleep(3)
    if os.path.exists(ROOT + '/logs/system.log'): sh(f'cp {ROOT}/logs/system.log {D}/system.log', check=False)
def finish(rc):
    stop_node()
    note(f'node stopped; our pid {PID} alive: {bool(PID and os.path.exists(f"/proc/{PID}"))}; ports still busy: {ports_busy()}')
    sys.exit(rc)
def fail(msg):
    note('FAIL: ' + msg); finish(1)
def expect(desc, cond):
    note(f'EXPECTED: {desc} -- {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}'); return cond

def wait_up(timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not os.path.exists(f'/proc/{PID}'): return 'exited'
        _, st = sh(NT + 'statusbinary', check=False, timeout=60)
        if re.search(r'^running', st.strip(), re.M):
            _, ns = sh(NT + 'status', check=False, timeout=60)
            if re.search(r'^UN', ns, re.M): return 'up'
        time.sleep(5)
    return 'timeout'

def start():
    global PID
    busy = ports_busy()
    if busy: fail(f'ports in use before start: {busy}')
    if own_pid(): fail('our node is already running')
    note(sh(f'{HARNESS}/make-node-yaml.sh {ROOT}')[1].strip().replace('\n', ' | '))
    sh(f'cp {ROOT}/conf/cassandra.yaml {D}/cassandra.yaml')
    if FIRST: sh(f'rm -rf {ROOT}/data {ROOT}/commitlog {ROOT}/hints {ROOT}/saved_caches {ROOT}/cdc_raw {ROOT}/logs')
    sh(f'mkdir -p {ROOT}/logs {ROOT}/helper/classes && javac -d {ROOT}/helper/classes {HARNESS}/SrHelper.java && jar cf {ROOT}/helper/sr.jar -C {ROOT}/helper/classes .')
    env = dict(node_env(), MAX_HEAP_SIZE='4G'); env.pop('HEAP_NEWSIZE', None)
    prop = '' if LIMIT == DEFAULT else f'-Dcassandra.sai.vector_search.max_materialized_keys={LIMIT} '
    env['JVM_EXTRA_OPTS'] = (prop + f'-Dstage4.sr.out={TRACE} -Xbootclasspath/a:{ROOT}/helper/sr.jar '
                             f'-javaagent:{BM}=script:{HARNESS}/sr.btm,listener:true,port:9328 '
                             f'-XX:StartFlightRecording=filename={D}/sr.jfr,settings=profile,dumponexit=true')
    note('JVM_EXTRA_OPTS=' + env['JVM_EXTRA_OPTS'])
    pid_file = f'{D}/cassandra.pid'
    if os.path.exists(pid_file): os.remove(pid_file)
    sh(f'bin/cassandra -p {pid_file} > {D}/startup.log 2>&1', env=env)
    for _ in range(60):
        if os.path.exists(pid_file) and open(pid_file).read().strip(): break
        time.sleep(0.5)
    PID = open(pid_file).read().strip(); time.sleep(2)
    args = open(f'/proc/{PID}/cmdline').read().split('\0'); open(f'{D}/jvm-args.txt', 'w').write('\n'.join(args))
    note(f'JVM args: -Xmx4G {"-Xmx4G" in args}; G1 {any("UseG1GC" in a for a in args)}; -ea {"-ea" in args}; byteman {any("byteman-4.0.20.jar" in a for a in args)}')
    if '-Xmx4G' not in args or not any('UseG1GC' in a for a in args): fail('JVM lacks -Xmx4G or G1')
    if '-ea' not in args: fail('JVM lacks -ea (the default jvm-server.options has it)')
    if prop and prop.strip() not in args: fail('JVM lacks the property')
    if not prop and any('max_materialized_keys' in a for a in args): fail('default run carries the property')
    st = wait_up(300); note(f'node {PID}: {st}')
    if st != 'up': fail('node did not come up')
    _, out = sh(f'jcmd {PID} VM.system_properties', check=False, timeout=60)
    m = re.search(r'cassandra\.sai\.vector_search\.max_materialized_keys=(\S+)', out); got = m.group(1) if m else None
    note(f'VM.system_properties: max_materialized_keys={got} (set {prop.strip() or "none: default 16000"})')
    if (prop and got != str(LIMIT)) or (not prop and got is not None): fail('property read back differs: invalid run')

def client(*a, timeout=900):
    rc, out = sh(f'python3 {HARNESS}/query.py ' + ' '.join(map(str, a)), check=False, timeout=timeout)
    line = [l for l in out.splitlines() if l.startswith(('OK ', 'ERR '))]
    if not line: fail(f'client printed nothing parseable: {out[-300:]}')
    return line[-1].startswith('OK '), json.loads(line[-1][3:] if line[-1].startswith('OK ') else line[-1][4:])

def sr_lines(t0, t1):
    out = []
    if os.path.exists(TRACE):
        for l in open(TRACE):
            m = re.match(r'SR ts=(\d+) thr=(\S+) cap=(\d+) arrlen=(\d+) alloc_ctor=(\d+) caller=(\S+)', l)
            if m and t0 <= int(m.group(1)) <= t1:
                out.append(dict(ts=int(m.group(1)), cap=int(m.group(3)), arrlen=int(m.group(4)), alloc=int(m.group(5)), caller=m.group(6)))
    return out

def cell(name, mode, expect_cap, reads_ok_note, **kw):
    """One traced query, then 200 untraced; compare the Byteman lines in the 200-query window with expect_cap (None = no line expected)."""
    args = [mode] + [x for k, v in kw.items() for x in (f'--{k.replace("_", "-")}', v)]
    ok, tr = client(*args, '--trace')
    ev = tr.get('trace_events', [])
    pick = [e for e in ev if re.search(r'Search range covers|SAI materialized|Switching to ORDER BY|brute force', e)]
    note(f'[{name}] trace: ' + ' | '.join(pick))
    open(D + f'/trace-{name}.json', 'w').write(json.dumps(tr))
    ok2, r = client(*args, '--n', 200)
    lines = sr_lines(r['start_ms'], r['end_ms'])
    caps = sorted(set(l['cap'] for l in lines)); allocs = sorted(set(l['alloc'] for l in lines)); arr = sorted(set(l['arrlen'] for l in lines))
    callers = sorted(set(l['caller'] for l in lines))
    note(f'[{name}] client ok={ok2} errors={r["errors"]} short={r["short"]} SR_lines={len(lines)} caps={caps} arrlen={arr} alloc_ctor={allocs} callers={callers}')
    return ok2, ev, lines, caps, allocs, arr

def hybrid_cells():
    M = {1: 500, 2: 10000, 3: 20000, 4: 50000}
    for g, m in M.items():
        ok, ev, lines, caps, allocs, arr = cell(f'hybrid-g{g}', 'hybrid', None, '', table='t', grp=g, limit=10)
        if m <= LIMIT:
            expect(f'L={LIMIT} M={m}: one int[] of 16+8M={16+8*m} B (+K={K} rule overhead, up to 1 KiB extra) per query ({len(lines)} lines for 200 queries, cap {caps}, alloc_ctor {allocs}, arrlen {arr})',
                   len(lines) == 200 and caps == [m] and near(allocs, 16 + 8 * m) and arr == [2 * m])
        else:
            expect(f'L={LIMIT} M={m}: no allocation from this class, fallback message in trace (SR lines {len(lines)})',
                   len(lines) == 0 and any('Switching to ORDER BY then post filter' in e for e in ev))

def range_cells():
    for rows, limit in ((100, 100), (1000, 100), (5000, 100), (30000, 100), (30000, 10)):
        ok, ev, lines, caps, allocs, arr = cell(f'range-{rows}-lim{limit}', 'range', None, '', rows=rows, limit=limit)
        m = [re.search(r'covers (\d+) rows; max brute force rows is (\d+)', e) for e in ev]; m = [x for x in m if x]
        if not m: note(f'[range-{rows}-lim{limit}] no "Search range covers" trace line'); continue
        n, mb = int(m[0].group(1)), int(m[0].group(2))
        if n <= mb:
            expect(f'range {rows} LIMIT {limit}: nRows {n} <= {mb}: 16+8n={16+8*n} B per query (lines {len(lines)}, cap {caps}, alloc {allocs}, caller {sorted(set(l["caller"] for l in lines))})',
                   len(lines) == 200 and caps == [n] and near(allocs, 16 + 8 * n))
        else:
            expect(f'range {rows} LIMIT {limit}: nRows {n} > {mb}: no allocation from this class (lines {len(lines)})', len(lines) == 0)

def main():
    mode = sys.argv[1]
    if mode != 'value': sys.exit('usage: cluster-run.py value <default|1000|64000> [--first]')
    note(f'=== value {LABEL} (max_materialized_keys={LIMIT}) {time.strftime("%F %T")} first={FIRST}')
    try:
        start()
        if FIRST:
            rc, out = sh(f'python3 {HARNESS}/load.py', check=False, timeout=1800)
            line = [l for l in out.splitlines() if l.startswith('OK ')]
            if not line: fail('load failed: ' + out[-400:])
            note('load: ' + line[0]); j = json.loads(line[0][3:])
            expect('count by grp = 500/10000/20000/50000', j['count_by_grp'] == {'1': 500, '2': 10000, '3': 20000, '4': 50000} or j['count_by_grp'] == {1: 500, 2: 10000, 3: 20000, 4: 50000})
            _, ts = sh(NT + 'tablestats ks.t', check=False); note('tablestats SSTable count: ' + ' '.join(re.findall(r'SSTable count: \d+', ts)))
        # warm-up (not a reading): 50 per shape
        for g in (1, 2, 3, 4): client('hybrid', '--table', 't', '--grp', g, '--n', 50)
        client('range', '--rows', 1000, '--limit', 100, '--n', 50)
        open(TRACE, 'a').write('')   # lines before this point are warm-up; windows by timestamp exclude them
        hybrid_cells()
        if FIRST:
            ok, ev, lines, caps, allocs, arr = cell('memtable-control', 'hybrid', None, '', table='mt', grp=1, limit=10)
            expect(f'memtable control (ks.mt unflushed, grp=1): no SR lines ({len(lines)})', len(lines) == 0)
        if LABEL == 'default': range_cells()
        sh(f'jcmd {PID} JFR.dump filename={D}/sr-dump.jfr', check=False, timeout=120)
        _, o = sh(f'jfr print --events jdk.ObjectAllocationOutsideTLAB,jdk.ObjectAllocationInNewTLAB {D}/sr-dump.jfr | grep -c SegmentRowIdOrdinalPairs', check=False, timeout=300)
        note(f'JFR (supplementary, TLAB-sampled): allocation events with SegmentRowIdOrdinalPairs in the stack: {o.strip()}')
    except Exception as e:  # noqa: BLE001
        note(f'EXCEPTION {type(e).__name__}: {e}'); finish(1)
    finish(0)
main()
