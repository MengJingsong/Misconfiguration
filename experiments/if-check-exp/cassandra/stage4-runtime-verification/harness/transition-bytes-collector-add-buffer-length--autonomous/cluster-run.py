#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of transition-bytes-collector-add-buffer-length--autonomous (case-file sha256 in the results file section 1;
audit amendments R1-R8 = section D of the case file).
usage: cluster-run.py all | <lifetime label>... | down
Lifetimes (a fresh node and data directory each): T1k, T8k, T64k (sstable format bti; sai_string_term_size_fail_threshold 1KiB, 8KiB, 64KiB)
and BIG (format big, 8KiB). Per lifetime: Byteman trace (collector.btm) from node start; schema (w1..w4, SAI on v); loads W1-W4 (B3c);
flush; compact; 3 minutes of mixed point reads and SAI queries; class histogram after each phase; du; system.log segment; node stopped by PID.
Env: TC_RUN (run1), TC_SCALE (1; shakedown divisor), TC_DIR (node data dir), TC_READ_S (180), CASSANDRA_HOME (tree), TC_COMPAT (storage_compatibility_mode, default as in the yaml)."""
import json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
H = os.path.dirname(os.path.abspath(__file__))
MODE = sys.argv[1] if len(sys.argv) > 1 else ''
if not MODE:
    sys.exit(__doc__)
RUNNAME = os.environ.get('TC_RUN', 'run1')
SCALE = int(os.environ.get('TC_SCALE', 1))
READ_S = int(os.environ.get('TC_READ_S', 180 if SCALE == 1 else 20))
COMPAT = os.environ.get('TC_COMPAT', 'NONE')
C = os.environ.get('CASSANDRA_HOME', f'{HOME}/s4-b7-tc')
RUN = os.environ.get('TC_DIR', f'{HOME}/s4-b7-tc-run')
ADDR, STORAGE, SSL, NATIVE, JMX, BMPORT = '127.0.1.1', 7000, 7001, 9042, 7110, 19110
LOGS = f'{HOME}/s4-b7-tc-logs/{RUNNAME}/cluster'
BYTEMAN = f'{C}/build/lib/jars/byteman-4.0.20.jar'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
ENV = dict(os.environ, CASSANDRA_CONF=RUN + '/conf', CASSANDRA_LOG_DIR=RUN + '/logs', MAX_HEAP_SIZE='1G', CASSANDRA_HOME=C)
ENV.pop('HEAP_NEWSIZE', None)

# workload: table, partitions, pk bytes, v chars
W = [('w1', 20000, 100, 900), ('w2', 5000, 8192, 8191), ('w3', 2000, 60000, 900), ('w4', 2000, 100, 40960)]
W = [(t, max(50, n // SCALE), a, b) for t, n, a, b in W]
LIVES = {'T1k': ('bti', '1KiB'), 'T8k': ('bti', '8KiB'), 'T64k': ('bti', '64KiB'), 'BIG': ('big', '8KiB')}
ORDER = ['T1k', 'T8k', 'T64k', 'BIG']


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, flush=True)
    SESSION.write(line + '\n'); SESSION.flush()


def now_ms():
    return int(time.time() * 1000)


def sh(cmd, timeout=900, check=True, quiet=False, cwd=None):
    log('+ ' + cmd[:300])
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=ENV, cwd=cwd or C)
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
    return [l for l in out.splitlines() if l.strip() and RUN + '/' in l]


def node_pid():
    try:
        pid = int(open(RUN + '/cassandra.pid').read().strip())
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except (OSError, ValueError):
        return None


def nodetool(args, timeout=600):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} {args}', timeout=timeout, check=False, quiet=True)


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


def make_conf(label):
    fmt, thr = LIVES[label]
    conf = RUN + '/conf'
    sh(f'rm -rf {conf} && cp -r {C}/conf {conf}')
    lines = {
        'cluster_name': "'tc'",
        'data_file_directories': f'\n    - {RUN}/data',
        'commitlog_directory': f'{RUN}/commitlog', 'hints_directory': f'{RUN}/hints',
        'saved_caches_directory': f'{RUN}/saved_caches', 'cdc_raw_directory': f'{RUN}/cdc_raw',
        'listen_address': ADDR, 'rpc_address': ADDR,
        'seed_provider': f'\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: "{ADDR}:{STORAGE}"',
        'storage_port': str(STORAGE), 'ssl_storage_port': str(SSL), 'native_transport_port': str(NATIVE),
        'autocompaction_on_startup_enabled': 'false',
        'authenticator': 'PasswordAuthenticator', 'authorizer': 'CassandraAuthorizer',
        'native_transport_timeout': '60s', 'write_request_timeout': '30s', 'read_request_timeout': '30s',
    }
    if COMPAT:
        lines['storage_compatibility_mode'] = COMPAT
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
    out.append('# ---- stage4 tc (B3a) ----')
    out += [f'{k}: {v}' for k, v in lines.items()]
    out.append(f'sstable:\n  selected_format: {fmt}')
    out.append(f'sai_string_term_size_warn_threshold: 1KiB\nsai_string_term_size_fail_threshold: {thr}')
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n')
    env = open(conf + '/cassandra-env.sh').read()
    assert env.count('JMX_PORT="7199"') == 1
    open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"'))
    with open(conf + '/jvm11-server.options', 'a') as fo:
        fo.write(f'\n# stage4 tc\n-XX:-HeapDumpOnOutOfMemoryError\n-Xlog:gc*:file={RUN}/logs/gc-{label}.log:time,uptime:filecount=10,filesize=100M\n')
        fo.write(f'-javaagent:{BYTEMAN}=script:{H}/collector.btm,listener:true,port:{BMPORT},address:{ADDR}\n-Dstage4.trace={RUN}/logs/tc-{label}.trace\n')
    log(f'conf {label}: format={fmt} sai_string_term_size_fail_threshold={thr} compat={COMPAT or "(yaml)"}')


def start_node(label):
    if node_pid() is not None or daemons():
        raise RuntimeError('a CassandraDaemon of this harness is already running: ' + str(daemons()))
    sh(f'bash -c "ulimit -n 100000; bin/cassandra -p {RUN}/cassandra.pid > {RUN}/logs/start-{label}.out 2>&1"')
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(3)
        if node_pid() is None and time.time() - t0 > 15:
            raise RuntimeError('daemon died during start: ' + open(f'{RUN}/logs/start-{label}.out', errors='replace').read()[-800:])
        rc, out = nodetool('status', timeout=60)
        if re.search(rf'^UN\s+{re.escape(ADDR)}', out, re.M):
            rc2, out2 = nodetool('statusbinary', timeout=60)
            if 'running' in out2:
                import socket
                for _ in range(120):
                    try:
                        socket.create_connection((ADDR, NATIVE), timeout=2).close(); break
                    except OSError:
                        time.sleep(1)
                else:
                    raise RuntimeError('native port never accepted a connection')
                log(f'node up ({label}) after {time.time() - t0:.0f} s, pid {node_pid()}')
                return node_pid()
    raise RuntimeError('node did not come up')


def client(args, timeout=7200):
    rc, out = sh(f'python3 -I {H}/client.py {args}', timeout=timeout, check=False, quiet=True)
    last = [l for l in out.splitlines() if l.startswith('{')]
    return json.loads(last[-1]) if last else {'error': out[-500:]}


def histogram(pid, dest):
    sh(f'jcmd {pid} GC.class_histogram > {dest}', timeout=600, check=False, quiet=True)
    res = {}
    for l in open(dest, errors='replace'):
        p = l.split()
        if len(p) >= 4 and p[0].endswith(':') and p[3] == '[B':
            res['byte[]'] = (int(p[1]), int(p[2]))
        elif p and p[0] == 'Total':
            res['total'] = (int(p[1]), int(p[2]))
    return res


def du(path):
    _, o = sh(f'du -sb {path}', check=False, quiet=True)
    try:
        return int(o.split()[0])
    except (IndexError, ValueError):
        return None


def lifetime(label, wr):
    d = f'{LOGS}/{label}'
    os.makedirs(d, exist_ok=True)
    sh(f'rm -rf {RUN}/data {RUN}/commitlog {RUN}/hints {RUN}/saved_caches {RUN}/cdc_raw && mkdir -p {RUN}/data {RUN}/commitlog {RUN}/hints {RUN}/saved_caches {RUN}/cdc_raw')
    sh(f'rm -f {RUN}/logs/tc-{label}.trace')      # Byteman appends to an existing trace file
    make_conf(label)
    off = os.path.getsize(RUN + '/logs/system.log') if os.path.exists(RUN + '/logs/system.log') else 0
    pid = start_node(label)
    wr(dict(kind='life', life=label, pid=pid, t_ms=now_ms(), cfg=LIVES[label], workload=W, read_s=READ_S))
    log(f'schema: {client(f"schema {ADDR} {NATIVE}")}')
    _, ss = sh('ss -ltn', check=False, quiet=True)
    wr(dict(kind='ports', byteman_listening=bool(re.search(rf'{re.escape(ADDR)}:{BMPORT}\s', ss)), t_ms=now_ms()))
    phases = open(f'{d}/phases.csv', 'w')
    phases.write('phase,start_ms,end_ms,detail\n')
    hn = [0]

    def snap(tag):
        hn[0] += 1
        h = histogram(pid, f'{d}/histo-{hn[0]:03d}-{tag}.txt')
        wr(dict(kind='histo', life=label, tag=tag, t_ms=now_ms(), histo=h, du_data=du(RUN + '/data')))
        log(f'{label}: histo {tag} byte[] {h.get("byte[]")} total {h.get("total")}')

    def phase(name, fn):
        t0 = now_ms(); log(f'{label}: phase {name} start')
        detail = fn()
        t1 = now_ms()
        phases.write(f'{name},{t0},{t1},{json.dumps(detail).replace(",", ";")}\n'); phases.flush()
        wr(dict(kind='phase', life=label, phase=name, t_start_ms=t0, t_end_ms=t1, detail=detail))
        log(f'{label}: phase {name} end ({(t1 - t0) / 1000:.0f} s) {detail}')
        return detail

    snap('base')
    loads = {}
    for t, n, pklen, vlen in W:
        loads[t] = phase(f'load_{t}', lambda t=t, n=n, pklen=pklen, vlen=vlen: client(f'load {ADDR} {NATIVE} {t} {n} {pklen} {vlen} 16'))
        snap(f'after-load_{t}')
    phase('flush', lambda: dict(zip(('rc', 'out'), nodetool('flush ks', timeout=1800))))
    snap('after-flush')
    phase('compact', lambda: dict(zip(('rc', 'out'), nodetool('compact ks', timeout=3600))))
    snap('after-compact')
    specs = ' '.join(f'{t}:{loads[t].get("ok", 0)}:{pklen}:{vlen}' for t, n, pklen, vlen in W)
    phase('reads', lambda: client(f'read {ADDR} {NATIVE} {READ_S} 8 {specs}', timeout=READ_S + 600))
    snap('after-reads')
    phases.close()
    wr(dict(kind='du', life=label, data_bytes=du(RUN + '/data'), t_ms=now_ms()))
    with open(RUN + '/logs/system.log', 'rb') as f:
        f.seek(off); seg = f.read()
    open(f'{d}/system.log', 'wb').write(seg)
    GR = 'Guardrail sai_string_term_size violated'      # the rejected writes' own (rate-limited) ERROR line: expected, counted apart
    allerr = [l for l in seg.decode(errors='replace').splitlines() if l.startswith('ERROR') or 'java.lang.OutOfMemoryError' in l]
    errs = [l for l in allerr if GR not in l]
    wr(dict(kind='end', life=label, error_lines=len(errs), guardrail_error_lines=len(allerr) - len(errs), first_errors=errs[:5], t_ms=now_ms()))
    log(f'{label}: system.log ERROR/OOM lines {len(errs)} {errs[:2]}')
    stop_node()
    sh(f'cp {RUN}/logs/tc-{label}.trace {d}/trace.txt 2>/dev/null; cp {RUN}/logs/gc-{label}.log {d}/ 2>/dev/null; cp {RUN}/conf/cassandra.yaml {d}/cassandra.yaml; true', check=False)


def main():
    if MODE == 'down':
        stop_node(); log('daemons left: ' + str(daemons())); return
    log(f'cluster-run {RUNNAME}: RUN={RUN} tree={C} scale={SCALE} workload={W} read_s={READ_S}')
    sh('git describe --tags; git rev-parse --short HEAD; java -version 2>&1 | head -1; uname -r; df -h ' + HOME, check=False)
    _, ss = sh('ss -ltn', check=False, quiet=True)
    busy = [str(p) for p in (STORAGE, SSL, NATIVE, JMX, BMPORT) if re.search(rf'(127\.0\.1\.1|127\.0\.0\.1|\*|0\.0\.0\.0):{p}\s', ss)]
    if busy or daemons():
        raise RuntimeError(f'ports busy {busy} or daemons {daemons()}')
    sh(f'mkdir -p {RUN}/logs')
    wanted = ORDER if MODE == 'all' else sys.argv[1:]
    jf = open(LOGS + '/cells.jsonl', 'a')

    def wr(rec):
        jf.write(json.dumps(rec) + '\n'); jf.flush()
    for label in wanted:
        lifetime(label, wr)
    log('all lifetimes done')


try:
    main()
except Exception as e:
    log(f'ABORT: {e!r}')
    raise
finally:
    if MODE != 'down':
        stop_node()
        log('daemons left: ' + str(daemons()))
        open(LOGS + '/done', 'w').write(time.strftime('%F %T') + '\n')
