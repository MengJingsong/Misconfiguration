#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of tombstone_failure_threshold-countTombstone-tombstones--autonomous
(frozen sha256 9e62de3a..., audit amendments R1-R6, 2026-10-21).
usage: cluster-run.py all | down
  all   B3e: set up $RUN (B3a + R3), start a node at T = 1,000,000, create the schema, write ingest.cql (R1: pk 0 is
        N cell tombstones written with UPDATE ... SET v = null; pk 1 is NLIVE live rows), load it with cqlsh -f, flush,
        traced check read, du. Then for each T (default 1M, 300k, 100k, 20k, 1k): stop, set T in the yaml, start
        (fresh lifetime), confirm T with sjk, traced warm-up read, TombstoneFailures; then for pk 0 (and pk 1 in the
        T = 1k and 1M lifetimes, R4): 30 s idle jstat, ThreadAlloc before (R5), JFR start, the C x R cqlsh storm with
        jstat -gc every 250 ms alongside, JFR stop, ThreadAlloc after, metrics. Then stop the node.
  down  stop this harness's node.
Logs: ~/stage4-logs/tft/<TFT_RUN>/cluster/ (session.log, phases.json, reads.csv, jstat-*.txt, alloc-*.txt, jfr-*.tsv,
metrics.txt, warm-*.out, scanned-*.txt, system-*.log segments, gc-*.log copies). The analysis is cluster-analyze.py.
Env: TFT_RUN (run1), TFT_DIR (/local/tft-run), TFT_N (200000), TFT_NLIVE (20000), TFT_TS (1000000,300000,100000,20000,1000),
TFT_CTRL (1000,1000000), TFT_C (8), TFT_R (5), TFT_IDLE_S (30), CASSANDRA_HOME (~/cassandra-tft)."""
import json, os, re, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-tft')
H = os.path.dirname(os.path.abspath(__file__))
RUNNAME = os.environ.get('TFT_RUN', 'run1')
RUN = os.environ.get('TFT_DIR', '/local/tft-run')
N = int(os.environ.get('TFT_N', 200000))
NLIVE = int(os.environ.get('TFT_NLIVE', 20000))
TS = [int(x) for x in os.environ.get('TFT_TS', '1000000,300000,100000,20000,1000').split(',')]
CTRL = [int(x) for x in os.environ.get('TFT_CTRL', '1000,1000000').split(',')]
CC = int(os.environ.get('TFT_C', 8)); RR = int(os.environ.get('TFT_R', 5))
IDLE_S = int(os.environ.get('TFT_IDLE_S', 30))
JMX = 7299
LOGS = f'{HOME}/stage4-logs/tft/{RUNNAME}/cluster'
MODE = sys.argv[1] if len(sys.argv) > 1 else ''
if MODE not in ('all', 'down'):
    sys.exit(__doc__)
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
PHASES = []
ENV = dict(os.environ, CASSANDRA_CONF=RUN + '/conf', CASSANDRA_LOG_DIR=RUN + '/logs', MAX_HEAP_SIZE='8G', HEAP_NEWSIZE='800M')


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, flush=True)
    SESSION.write(line + '\n'); SESSION.flush()


def now_ms():
    return int(time.time() * 1000)


def sh(cmd, timeout=900, check=True, quiet=False):
    log('+ ' + cmd)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=ENV, cwd=C)
    except subprocess.TimeoutExpired:
        log(f'  TIMEOUT after {timeout} s')
        if check:
            raise RuntimeError('timeout: ' + cmd)
        return 124, ''
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'rc={r.returncode}: {cmd}\n{out[-1500:]}')
    return r.returncode, out


def daemons():
    _, out = sh("ps -eo pid,args | grep -E '^ *[0-9]+ [^ ]*java .*CassandraDaemon' || true", check=False, quiet=True)
    return [l for l in out.splitlines() if l.strip()]


def node_pid():
    try:
        pid = int(open(RUN + '/cassandra.pid').read().strip())
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except (OSError, ValueError):
        return None


def nodetool(args, timeout=120, check=False):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} {args}', timeout=timeout, check=check, quiet=True)


def sjk_get(bean, field):
    rc, out = nodetool(f'sjk mx -b "{bean}" -mg -f {field}')
    nums = re.findall(r'^\s*([0-9][0-9.E+-]*)\s*$', out, re.M)
    return nums[-1] if nums else 'ERR:' + out.strip()[-200:]


def stop_node():
    pid = node_pid()
    if pid is None:
        return
    log(f'stopping node pid {pid}')
    sh(f'kill {pid}', check=False)
    for _ in range(180):                      # wait on the process itself: the pid file goes before the JVM exits
        if not os.path.exists(f'/proc/{pid}'):
            log('node stopped'); return
        time.sleep(1)
    sh(f'kill -9 {pid}', check=False); time.sleep(2)


def make_conf(T, label):
    """B3a conf for one lifetime; a key already in the shipped yaml is removed first, so none appears twice."""
    conf = RUN + '/conf'
    sh(f'rm -rf {conf} && cp -r {C}/conf {conf}')
    lines = {
        'cluster_name': "'tft'",
        'data_file_directories': f'\n    - {RUN}/data',
        'commitlog_directory': f'{RUN}/commitlog', 'hints_directory': f'{RUN}/hints',
        'saved_caches_directory': f'{RUN}/saved_caches', 'cdc_raw_directory': f'{RUN}/cdc_raw',
        'listen_address': '127.0.0.1', 'rpc_address': '127.0.0.1',
        'seed_provider': '\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: "127.0.0.1:7100"',
        'storage_port': '7100', 'ssl_storage_port': '7101', 'native_transport_port': '9142',
        'read_request_timeout': '120000ms', 'range_request_timeout': '120000ms',
        'native_transport_timeout': '180s',                       # R3
        'tombstone_warn_threshold': '1000', 'tombstone_failure_threshold': str(T),
    }
    out, skip = [], False
    for l in open(C + '/conf/cassandra.yaml').read().splitlines():
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in lines
            if skip:
                continue
        elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == ''):
            continue
        else:
            skip = False
        out.append(l)
    out.append('# ---- stage4 tft (B3a, R3) ----')
    out += [f'{k}: {v}' for k, v in lines.items()]
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n')
    env = open(conf + '/cassandra-env.sh').read()
    assert env.count('JMX_PORT="7199"') == 1
    open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"'))
    with open(conf + '/jvm11-server.options', 'a') as f:
        f.write(f'\n# stage4 tft (B3a)\n-Xlog:gc*,gc+heap=debug:file={RUN}/logs/gc-{label}.log:time,uptime:filecount=10,filesize=50M\n')
    log(f'conf for T={T} label={label}: ' + '; '.join(f'{k}={v.strip()}' for k, v in lines.items() if '\n' not in v))


def start_node(label):
    if node_pid() is not None or daemons():
        raise RuntimeError('a CassandraDaemon is already running: ' + str(daemons()))
    sh(f'bash -c "ulimit -n 100000; bin/cassandra -p {RUN}/cassandra.pid > {RUN}/logs/start-{label}.out 2>&1"')   # R3
    t0 = time.time()
    while time.time() - t0 < 240:
        time.sleep(3)
        if node_pid() is None and time.time() - t0 > 15:
            raise RuntimeError('daemon died during start')
        rc, out = nodetool('status', timeout=60)
        if re.search(r'^UN\s+127\.0\.0\.1', out, re.M):
            rc2, out2 = nodetool('statusbinary', timeout=60)
            if 'running' in out2:
                log(f'node up ({label}) after {time.time() - t0:.0f} s, pid {node_pid()}')
                return node_pid()
    raise RuntimeError('node did not come up')


def cqlsh(stmt, timeout=600, out=None):
    cmd = f'bin/cqlsh 127.0.0.1 9142 --request-timeout=180 -e "{stmt}"'
    if out:
        cmd += f' > {out} 2>&1'
    return sh(cmd, timeout=timeout, check=False)


def ck(i):
    return f'{i:08d}'.ljust(1000, 'x')


def ingest():
    path = RUN + '/ingest.cql'
    with open(path, 'w') as f:
        for b in range(0, N, 20):                                  # R1: no row marker
            f.write('BEGIN UNLOGGED BATCH\n')
            for i in range(b, min(b + 20, N)):
                f.write(f"UPDATE ks.t SET v = null WHERE pk = 0 AND ck = '{ck(i)}';\n")
            f.write('APPLY BATCH;\n')
        for b in range(0, NLIVE, 20):
            f.write('BEGIN UNLOGGED BATCH\n')
            for i in range(b, min(b + 20, NLIVE)):
                f.write(f"INSERT INTO ks.t (pk, ck, v) VALUES (1, '{ck(i)}', '');\n")
            f.write('APPLY BATCH;\n')
    log(f'ingest.cql: {os.path.getsize(path)} B')
    t0 = time.time()
    rc, out = sh(f'bin/cqlsh 127.0.0.1 9142 --request-timeout=120 -f {path} > {LOGS}/ingest.out 2>&1', timeout=7200, check=False)
    log(f'ingest rc={rc} in {time.time() - t0:.0f} s; errors in output: {sum(1 for l in open(LOGS + "/ingest.out") if "rror" in l)}')
    nodetool(f'flush ks t', timeout=600, check=True)


def syslog_size():
    try:
        return os.path.getsize(RUN + '/logs/system.log')
    except OSError:
        return 0


def syslog_segment(off, dest):
    with open(RUN + '/logs/system.log', 'rb') as f:
        f.seek(off); data = f.read()
    open(dest, 'wb').write(data)
    return data.decode(errors='replace')


def storm(T, pk, pid):
    tag = f'T{T}-pk{pk}'
    jidle = f'{LOGS}/jstat-idle-{tag}.txt'
    sh(f'java -cp {RUN}/tools HeapPoll {JMX} 250 {IDLE_S * 4} > {jidle}', timeout=IDLE_S + 60, check=False)   # D3
    sh(f'java -cp {RUN}/tools ThreadAlloc {JMX} > {LOGS}/alloc-before-{tag}.txt', check=False)
    jfr = f'{RUN}/jfr/{tag}.jfr'
    sh(f'jcmd {pid} JFR.start name=tft settings=profile filename={jfr}', check=False)
    js = subprocess.Popen(f'exec java -cp {RUN}/tools HeapPoll {JMX} 250 0 > {LOGS}/jstat-storm-{tag}.txt', shell=True, env=ENV)   # D3
    time.sleep(1.5)
    reads, lock = [], threading.Lock()

    def worker(w):
        for r in range(RR):
            out = f'{RUN}/client/c_{tag}_{w}_{r}.out'
            t0 = now_ms()
            subprocess.run(f'bin/cqlsh 127.0.0.1 9142 --request-timeout=180 -e "CONSISTENCY ONE; SELECT * FROM ks.t WHERE pk={pk};" 2>&1 | tail -c 3000 > {out}',
                           shell=True, cwd=C, env=ENV)
            t1 = now_ms()
            txt = open(out, errors='replace').read()
            m = re.search(r'\((\d+) rows\)', txt)
            oc = ('FAIL_TOMBSTONE' if ('READ_TOO_MANY_TOMBSTONES' in txt or "'0x0001'" in txt) else 'FAIL_OTHER') if ('ReadFailure' in txt or 'Error' in txt) else (f'OK:{m.group(1)}' if m else 'UNKNOWN')
            with lock:
                reads.append((T, pk, w, r, t0, t1, oc))
    t_start = now_ms()
    th = [threading.Thread(target=worker, args=(w,)) for w in range(CC)]
    [t.start() for t in th]; [t.join() for t in th]
    t_end = now_ms()
    time.sleep(1)
    js.terminate(); js.wait()
    sh(f'jcmd {pid} JFR.stop name=tft', check=False)
    sh(f'java -cp {RUN}/tools ThreadAlloc {JMX} > {LOGS}/alloc-after-{tag}.txt', check=False)
    with open(LOGS + '/reads.csv', 'a') as f:
        for x in sorted(reads, key=lambda x: x[4]):
            f.write(','.join(map(str, x)) + '\n')
    oc = {}
    for x in reads:
        oc[x[6]] = oc.get(x[6], 0) + 1
    log(f'storm {tag}: {t_end - t_start} ms, outcomes {oc}')
    sh(f'java -cp {RUN}/tools JfrBuf {jfr} > {LOGS}/jfr-{tag}.tsv', timeout=900, check=False)
    return dict(tag=tag, T=T, pk=pk, start_ms=t_start, end_ms=t_end, outcomes=oc)


def lifetime(T):
    label = f'T{T}'
    make_conf(T, label)
    off = syslog_size()
    pid = start_node(label)
    ph = dict(label=label, T=T, pid=pid, syslog_offset=off, storms=[])
    ph['T_read'] = sjk_get('org.apache.cassandra.db:type=StorageService', 'TombstoneFailureThreshold')
    log(f'T confirmed by sjk: {ph["T_read"]}')
    cqlsh('CONSISTENCY ONE; TRACING ON; SELECT * FROM ks.t WHERE pk=0;', out=f'{LOGS}/warm-{label}.out')
    bean = 'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name='
    ph['failures_after_warmup'] = sjk_get(bean + 'TombstoneFailures', 'Count')
    for pk in [0] + ([1] if T in CTRL else []):
        st = storm(T, pk, pid)
        st['failures_after'] = sjk_get(bean + 'TombstoneFailures', 'Count')
        st['scanned_hist_max'] = sjk_get(bean + 'TombstoneScannedHistogram', 'Max')
        ph['storms'].append(st)
        log(f'metrics {st["tag"]}: TombstoneFailures {st["failures_after"]}, TombstoneScannedHistogram.Max {st["scanned_hist_max"]}')
    seg = syslog_segment(off, f'{LOGS}/system-{label}.log')
    sc = re.findall(r'Scanned over (\d+) tombstones', seg)
    open(f'{LOGS}/scanned-{label}.txt', 'w').write('\n'.join(sc) + '\n')
    ph['scanned_lines'] = len(sc); ph['scanned_values'] = sorted(set(sc))
    ph['oom'] = bool(re.search(r'java\.lang\.OutOfMemoryError|OutOfMemoryError:', seg))
    log(f'{label}: system.log "Scanned over" lines {len(sc)} values {ph["scanned_values"]}; OOM {ph["oom"]}')
    stop_node()
    sh(f'cp {RUN}/logs/gc-{label}.log {LOGS}/ 2>/dev/null; true', check=False)
    PHASES.append(ph)
    json.dump(PHASES, open(LOGS + '/phases.json', 'w'), indent=1)


def main():
    if MODE == 'down':
        stop_node(); log('daemons left: ' + str(daemons())); return
    log(f'cluster-run {RUNNAME}: RUN={RUN} N={N} NLIVE={NLIVE} TS={TS} CTRL={CTRL} C={CC} R={RR} IDLE_S={IDLE_S} clone={C}')
    _, out = sh('git describe --tags; git rev-parse --short HEAD; java -version 2>&1 | head -1; uname -r; df -h ' + os.path.dirname(RUN.rstrip('/')), check=False)
    _, ss = sh('ss -ltn', check=False, quiet=True)
    busy = [p for p in ('7100', '7101', '9142', '7299') if re.search(rf':{p}\s', ss)]
    if busy or daemons():
        raise RuntimeError(f'ports busy {busy} or daemons {daemons()}')
    sh(f'rm -rf {RUN} && mkdir -p {RUN}/data {RUN}/commitlog {RUN}/hints {RUN}/saved_caches {RUN}/cdc_raw {RUN}/logs {RUN}/jfr {RUN}/client {RUN}/tools')
    sh(f'javac -d {RUN}/tools {H}/ThreadAlloc.java {H}/JfrBuf.java {H}/HeapPoll.java')
    open(LOGS + '/reads.csv', 'w').write('T,pk,worker,rep,start_ms,end_ms,outcome\n')
    make_conf(1000000, 'setup')
    start_node('setup')
    cqlsh("CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1}; "
          "CREATE TABLE ks.t (pk int, ck text, v text, PRIMARY KEY (pk, ck));", out=f'{LOGS}/schema.out')
    ingest()
    cqlsh('CONSISTENCY ONE; TRACING ON; SELECT * FROM ks.t WHERE pk=0;', out=f'{LOGS}/check-trace.out')
    tr = re.findall(r'Read (\d+) live rows and (\d+) tombstone cells', open(f'{LOGS}/check-trace.out', errors='replace').read())
    _, du = sh(f'du -sb {RUN}/data', check=False)
    log(f'B3e step 4: trace {tr}; data {du.split()[0] if du else "?"} B')
    nodetool('tablestats ks.t > ' + LOGS + '/tablestats.txt', timeout=120)
    stop_node()
    sh(f'cp {RUN}/logs/gc-setup.log {LOGS}/ 2>/dev/null; true', check=False)
    for T in TS:
        lifetime(T)
    log('all lifetimes done')


try:
    main()
except Exception as e:
    log(f'ABORT: {e!r}')
    raise
finally:
    if MODE == 'all':
        stop_node()
        log('daemons left: ' + str(daemons()))
        open(LOGS + '/done', 'w').write(time.strftime('%F %T') + '\n')
