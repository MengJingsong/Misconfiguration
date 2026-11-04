#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous
(frozen sha256 4c289eb0..., amendments A5-A7, 2026-10-26). Adapted from the closed twin's cluster-run.py.
usage: cluster-run.py all | down
  all   setup lifetime (T = MAX): schema, ingest (ks.t pk 0 = N row deletions; ks.t2 pk 0 = NT2 range deletions with 1000-char
        clusterings; ks.live pk 0 = NLIVE rows of a 1 KB v), flush, traced check that N tombstones are there (first-trigger
        check). Then for each T (default 1M, 100k, 10k): a fresh node lifetime: JMX read-back of T, traced warm-up (must fail
        with READ_TOO_MANY_TOMBSTONES, else abort), then storms: main (C clients x DUR s on ks.t pk 0), size variant (1 client
        x 3 reads on ks.t2, T in VARIANT_TS), live negative control (1 client x 3 reads on ks.live). Each storm: 30 s idle heap
        window, ThreadAlloc before, JFR, HeapPoll alongside, ThreadAlloc after, JFR listing. Then a control lifetime
        (read_thresholds_enabled true, local_read_size_fail_threshold 1MiB): 3 reads of ks.live.
  down  stop this harness's node.
Node: 127.0.1.1 (port slot 1): storage 7000, native 9042, JMX 7110 (bound on 127.0.0.1); data on tmpfs $TFM_DIR.
Logs: ~/s4-b10-tf-logs/<TFM_RUN>/cluster/.
Env: TFM_RUN (run1), TFM_DIR (/dev/shm/s4-b10-tf), TFM_N (1200000), TFM_NT2 (60000), TFM_NLIVE (30000), TFM_TS (1000000,100000,10000),
TFM_VARIANT_TS (100000,10000), TFM_C (8), TFM_DUR (300), TFM_IDLE_S (30), CASSANDRA_HOME (~/s4-b10-tf-n)."""
import json, os, re, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b10-tf-n')
H = os.path.dirname(os.path.abspath(__file__))
RUNNAME = os.environ.get('TFM_RUN', 'run1')
RUN = os.environ.get('TFM_DIR', '/dev/shm/s4-b10-tf')
N = int(os.environ.get('TFM_N', 1200000))
NT2 = int(os.environ.get('TFM_NT2', 60000))
NLIVE = int(os.environ.get('TFM_NLIVE', 30000))
TS = [int(x) for x in os.environ.get('TFM_TS', '1000000,100000,10000').split(',')]
VTS = [int(x) for x in os.environ.get('TFM_VARIANT_TS', '100000,10000').split(',')]
CC = int(os.environ.get('TFM_C', 8)); DUR = int(os.environ.get('TFM_DUR', 300))
IDLE_S = int(os.environ.get('TFM_IDLE_S', 30))
IP, JMX, NATIVE = '127.0.1.1', 7110, 9042
LOGS = f'{HOME}/s4-b10-tf-logs/{RUNNAME}/cluster'
MODE = sys.argv[1] if len(sys.argv) > 1 else ''
if MODE not in ('all', 'down'):
    sys.exit(__doc__)
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
PHASES = []
ENV = dict(os.environ, CASSANDRA_CONF=RUN + '/conf', CASSANDRA_LOG_DIR=RUN + '/logs', MAX_HEAP_SIZE='2G')
MAXT = 2147483647


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, flush=True)
    SESSION.write(line + '\n'); SESSION.flush()


def now_ms():
    return int(time.time() * 1000)


def sh(cmd, timeout=900, check=True, quiet=False):
    log('+ ' + cmd[:300])
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


def node_pid():
    try:
        pid = int(open(RUN + '/cassandra.pid').read().strip())
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except (OSError, ValueError):
        return None


def my_daemons():
    """java processes naming CassandraDaemon and this run's conf dir (other cases share the host)."""
    out = []
    for d in os.listdir('/proc'):
        if d.isdigit():
            try:
                cmd = open(f'/proc/{d}/cmdline').read().replace('\0', ' ')
            except OSError:
                continue
            if 'CassandraDaemon' in cmd and RUN in cmd:
                out.append(d)
    return out


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
    for _ in range(180):
        if not os.path.exists(f'/proc/{pid}'):
            log('node stopped'); return
        time.sleep(1)
    sh(f'kill -9 {pid}', check=False); time.sleep(2)


def make_conf(T, label, extra=None):
    conf = RUN + '/conf'
    sh(f'rm -rf {conf} && cp -r {C}/conf {conf}')
    lines = {
        'cluster_name': "'tfm'", 'num_tokens': '1', 'concurrent_reads': '4',
        'data_file_directories': f'\n    - {RUN}/data',
        'commitlog_directory': f'{RUN}/commitlog', 'hints_directory': f'{RUN}/hints',
        'saved_caches_directory': f'{RUN}/saved_caches', 'cdc_raw_directory': f'{RUN}/cdc_raw',
        'listen_address': IP, 'rpc_address': IP,
        'seed_provider': f'\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: "{IP}:7000"',
        'storage_port': '7000', 'native_transport_port': str(NATIVE),
        'read_request_timeout': '120000ms', 'range_request_timeout': '120000ms', 'native_transport_timeout': '180s',
        'autocompaction_on_startup_enabled': 'false',
        'tombstone_warn_threshold': '1000', 'tombstone_failure_threshold': str(T),
        'read_thresholds_enabled': 'false',
    }
    lines.update(extra or {})
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
    out.append('# ---- stage4 tfm (A5) ----')
    out += [f'{k}: {v}' for k, v in lines.items()]
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n')
    env = open(conf + '/cassandra-env.sh').read()
    assert env.count('JMX_PORT="7199"') == 1
    open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"'))
    with open(conf + '/jvm11-server.options', 'a') as f:
        f.write(f'\n# stage4 tfm (A5)\n-Xlog:gc*,gc+heap=debug:file={RUN}/logs/gc-{label}.log:time,uptime:filecount=10,filesize=50M\n'
                f'-XX:HeapDumpPath={HOME}/s4-b10-tf-logs/dumps\n')
    log(f'conf for T={T} label={label}: ' + '; '.join(f'{k}={v.strip()}' for k, v in lines.items() if '\n' not in v))


def start_node(label):
    if node_pid() is not None or my_daemons():
        raise RuntimeError('this harness already has a CassandraDaemon: ' + str(my_daemons()))
    sh(f'bash -c "ulimit -n 100000; bin/cassandra -p {RUN}/cassandra.pid > {RUN}/logs/start-{label}.out 2>&1"')
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(3)
        if node_pid() is None and time.time() - t0 > 20:
            raise RuntimeError('daemon died during start')
        rc, out = nodetool('status', timeout=60)
        if re.search(rf'^UN\s+{IP}', out, re.M):
            rc2, out2 = nodetool('statusbinary', timeout=60)
            if out2.strip().startswith('running'):
                log(f'node up ({label}) after {time.time() - t0:.0f} s, pid {node_pid()}')
                return node_pid()
    raise RuntimeError('node did not come up')


def cqlsh(stmt, timeout=900, out=None):
    cmd = f'bin/cqlsh {IP} {NATIVE} --request-timeout=180 -e "{stmt}"'
    if out:
        cmd += f' > {out} 2>&1'
    return sh(cmd, timeout=timeout, check=False)


def ck(i):
    return f'{i:08d}'.ljust(1000, 'x')


def ingest():
    path = RUN + '/ingest.cql'
    kb = 'y' * 1000
    with open(path, 'w') as f:
        for b in range(0, N, 20):
            f.write('BEGIN UNLOGGED BATCH\n')
            for i in range(b, min(b + 20, N)):
                f.write(f'DELETE FROM ks.t WHERE pk = 0 AND ck = {i};\n')
            f.write('APPLY BATCH;\n')
        for b in range(0, NT2, 20):                                    # disjoint ranges: 2 markers each, 1000-char clusterings
            f.write('BEGIN UNLOGGED BATCH\n')
            for i in range(b, min(b + 20, NT2)):
                f.write(f"DELETE FROM ks.t2 WHERE pk = 0 AND ck > '{ck(2 * i)}' AND ck < '{ck(2 * i + 1)}';\n")
            f.write('APPLY BATCH;\n')
        for b in range(0, NLIVE, 20):
            f.write('BEGIN UNLOGGED BATCH\n')
            for i in range(b, min(b + 20, NLIVE)):
                f.write(f"INSERT INTO ks.live (pk, ck, v) VALUES (0, {i}, '{kb}');\n")
            f.write('APPLY BATCH;\n')
    log(f'ingest.cql: {os.path.getsize(path)} B')
    t0 = time.time()
    rc, out = sh(f'bin/cqlsh {IP} {NATIVE} --request-timeout=120 -f {path} > {LOGS}/ingest.out 2>&1', timeout=7200, check=False)
    errs = sum(1 for l in open(LOGS + '/ingest.out') if 'rror' in l)
    log(f'ingest rc={rc} in {time.time() - t0:.0f} s; errors in output: {errs}')
    if rc != 0 or errs:
        raise RuntimeError('ingest failed; see ingest.out')
    for t in ('t', 't2', 'live'):
        nodetool(f'flush ks {t}', timeout=600, check=True)


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


def classify(txt):
    if 'READ_TOO_MANY_TOMBSTONES' in txt or "'0x0001'" in txt:
        return 'FAIL_TOMBSTONE'
    if 'READ_SIZE' in txt:
        return 'FAIL_READSIZE'
    m = re.search(r'\((\d+) rows\)', txt)
    if 'ReadFailure' in txt or 'Error' in txt or 'Timeout' in txt:
        return 'FAIL_OTHER'
    return f'OK:{m.group(1)}' if m else 'UNKNOWN'


def storm(T, arm, table, nclients, dur, reps, pid):
    tag = f'T{T}-{arm}'
    sh(f'java -cp {RUN}/tools ThreadAlloc {JMX} > {LOGS}/alloc-idle0-{tag}.txt', check=False)
    sh(f'java -cp {RUN}/tools HeapPoll {JMX} 250 {IDLE_S * 4} > {LOGS}/heap-idle-{tag}.txt', timeout=IDLE_S + 60, check=False)
    sh(f'java -cp {RUN}/tools ThreadAlloc {JMX} > {LOGS}/alloc-before-{tag}.txt', check=False)
    jfr = f'{RUN}/jfr/{tag}.jfr'
    sh(f'jcmd {pid} JFR.start name=tfm settings=profile filename={jfr}', check=False)
    js = subprocess.Popen(f'exec java -cp {RUN}/tools HeapPoll {JMX} 250 0 > {LOGS}/heap-storm-{tag}.txt', shell=True, env=ENV)
    time.sleep(1.5)
    reads, lock = [], threading.Lock()
    t_start = now_ms()

    def worker(w):
        r = 0
        while True:
            if dur is not None and (time.time() * 1000 - t_start) >= dur * 1000 and r > 0:
                break
            if dur is None and r >= reps:
                break
            out = f'{RUN}/client/c_{tag}_{w}_{r}.out'
            pg = 'PAGING OFF; ' if table == 'live' else ''
            t0 = now_ms()
            subprocess.run(f'bin/cqlsh {IP} {NATIVE} --request-timeout=180 -e "CONSISTENCY ONE; {pg}SELECT * FROM ks.{table} WHERE pk=0;" 2>&1 | tail -c 3000 > {out}',
                           shell=True, cwd=C, env=ENV)
            t1 = now_ms()
            oc = classify(open(out, errors='replace').read())
            with lock:
                reads.append((T, arm, w, r, t0, t1, oc))
            os.remove(out)
            r += 1
    th = [threading.Thread(target=worker, args=(w,)) for w in range(nclients)]
    [t.start() for t in th]; [t.join() for t in th]
    t_end = now_ms()
    time.sleep(1)
    js.terminate(); js.wait()
    sh(f'jcmd {pid} JFR.stop name=tfm', check=False)
    sh(f'java -cp {RUN}/tools ThreadAlloc {JMX} > {LOGS}/alloc-after-{tag}.txt', check=False)
    with open(LOGS + '/reads.csv', 'a') as f:
        for x in sorted(reads, key=lambda x: x[4]):
            f.write(','.join(map(str, x)) + '\n')
    oc = {}
    for x in reads:
        oc[x[6]] = oc.get(x[6], 0) + 1
    log(f'storm {tag}: {t_end - t_start} ms, {len(reads)} reads, outcomes {oc}')
    sh(f'java -cp {RUN}/tools JfrBuf {jfr} > {LOGS}/jfr-{tag}.tsv', timeout=1800, check=False)
    return dict(tag=tag, T=T, arm=arm, table=table, nclients=nclients, start_ms=t_start, end_ms=t_end, outcomes=oc, nreads=len(reads))


def lifetime(T, label, extra=None, storms=()):
    make_conf(T, label, extra)
    off = syslog_size()
    pid = start_node(label)
    ph = dict(label=label, T=T, pid=pid, syslog_offset=off, storms=[], extra=extra or {})
    ph['T_read'] = sjk_get('org.apache.cassandra.db:type=StorageService', 'TombstoneFailureThreshold')
    log(f'T confirmed by sjk: {ph["T_read"]}')
    if str(ph['T_read']) != str(T):
        raise RuntimeError(f'T read back {ph["T_read"]} != {T}')
    bean = 'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name='
    if storms and storms[0][1] == 't':                      # first-trigger check: traced warm-up read must fail with the tombstone code
        cqlsh('CONSISTENCY ONE; TRACING ON; SELECT * FROM ks.t WHERE pk=0;', out=f'{LOGS}/warm-{label}.out')
        txt = open(f'{LOGS}/warm-{label}.out', errors='replace').read()
        ph['warm_outcome'] = classify(txt)
        ph['failures_after_warmup'] = sjk_get(bean + 'TombstoneFailures', 'Count')
        log(f'warm-up {label}: {ph["warm_outcome"]}, TombstoneFailures {ph["failures_after_warmup"]}')
        if ph['warm_outcome'] != 'FAIL_TOMBSTONE':
            raise RuntimeError('FIRST-TRIGGER CHECK FAILED: the warm-up read did not fail with READ_TOO_MANY_TOMBSTONES')
    for (arm, table, ncl, dur, reps) in storms:
        st = storm(T, arm, table, ncl, dur, reps, pid)
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
    sh(f'cp {RUN}/logs/gc-{label}.log* {LOGS}/ 2>/dev/null; true', check=False)
    PHASES.append(ph)
    json.dump(PHASES, open(LOGS + '/phases.json', 'w'), indent=1)


def main():
    if MODE == 'down':
        stop_node(); log('my daemons left: ' + str(my_daemons())); return
    log(f'cluster-run {RUNNAME}: RUN={RUN} N={N} NT2={NT2} NLIVE={NLIVE} TS={TS} VTS={VTS} C={CC} DUR={DUR} IDLE_S={IDLE_S} clone={C}')
    sh('git describe --tags; git rev-parse --short HEAD; java -version 2>&1 | head -1; uname -r; df -h /dev/shm', check=False)
    _, ss = sh('ss -ltn', check=False, quiet=True)
    busy = [p for p in ('7000', '9042', str(JMX)) if re.search(rf'(127\.0\.1\.1|127\.0\.0\.1):{p}\s', ss)]
    if busy or my_daemons():
        raise RuntimeError(f'ports busy {busy} or my daemons {my_daemons()}')
    sh(f'rm -rf {RUN} && mkdir -p {RUN}/data {RUN}/commitlog {RUN}/hints {RUN}/saved_caches {RUN}/cdc_raw {RUN}/logs {RUN}/jfr {RUN}/client {RUN}/tools {HOME}/s4-b10-tf-logs/dumps')
    sh(f'javac -d {RUN}/tools {H}/ThreadAlloc.java {H}/JfrBuf.java {H}/HeapPoll.java')
    open(LOGS + '/reads.csv', 'w').write('T,arm,worker,rep,start_ms,end_ms,outcome\n')
    make_conf(MAXT, 'setup')
    start_node('setup')
    cqlsh("CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1}; "
          "CREATE TABLE ks.t (pk int, ck int, v text, PRIMARY KEY (pk, ck)) WITH gc_grace_seconds = 864000; "
          "CREATE TABLE ks.t2 (pk int, ck text, v text, PRIMARY KEY (pk, ck)) WITH gc_grace_seconds = 864000; "
          "CREATE TABLE ks.live (pk int, ck int, v text, PRIMARY KEY (pk, ck)) WITH gc_grace_seconds = 864000;", out=f'{LOGS}/schema.out')
    ingest()
    cqlsh('CONSISTENCY ONE; TRACING ON; SELECT * FROM ks.t WHERE pk=0;', out=f'{LOGS}/check-trace.out')
    tr = re.findall(r'Read (\d+) live rows and (\d+) tombstone cells', open(f'{LOGS}/check-trace.out', errors='replace').read())
    log(f'first-trigger check (T=MAX): trace {tr}')
    if not tr or int(tr[-1][1]) != N:
        raise RuntimeError(f'FIRST-TRIGGER CHECK FAILED: ks.t pk 0 holds {tr}, expected {N} tombstones')
    cqlsh('CONSISTENCY ONE; TRACING ON; SELECT * FROM ks.t2 WHERE pk=0;', out=f'{LOGS}/check-trace-t2.out')
    tr2 = re.findall(r'Read (\d+) live rows and (\d+) tombstone cells', open(f'{LOGS}/check-trace-t2.out', errors='replace').read())
    log(f'ks.t2 check (T=MAX): trace {tr2}')
    sh(f'du -sb {RUN}/data', check=False)
    for t in ('t', 't2', 'live'):
        nodetool(f'tablestats ks.{t} >> {LOGS}/tablestats.txt', timeout=120)
    stop_node()
    sh(f'cp {RUN}/logs/gc-setup.log* {LOGS}/ 2>/dev/null; true', check=False)
    for T in TS:
        sts = [('main', 't', CC, DUR, None)]
        if T in VTS:
            sts.append(('variant', 't2', 1, None, 3))
        sts.append(('live', 'live', 1, None, 3))
        lifetime(T, f'T{T}', storms=sts)
    lifetime(100000, 'ctl-1MiB', extra={'read_thresholds_enabled': 'true', 'local_read_size_fail_threshold': '1MiB'},
             storms=[('live-1MiB', 'live', 1, None, 3)])
    log('all lifetimes done')


try:
    main()
except Exception as e:
    log(f'ABORT: {e!r}')
    raise
finally:
    if MODE == 'all':
        stop_node()
        log('my daemons left: ' + str(my_daemons()))
        open(LOGS + '/done', 'w').write(time.strftime('%F %T') + '\n')
