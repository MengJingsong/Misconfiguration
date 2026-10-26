#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of trie-pathreconstructor-keybytes-growth--autonomous (case-file sha256 in the results file section 1;
audit amendments R1-R9 = section B5 of the case file).
usage: cluster-run.py all | <lifetime label>... | down
Lifetimes (a fresh node and data directory each): H256, H1024, H64 (heap_buffers, memtable_heap_space 256/1024/64 MiB) and O256
(offheap_objects, heap 256 MiB, off-heap 256 MiB). Per lifetime: Byteman growth trace (trie-growth.btm) from node start; schema; t_small load
(1,000,000 x 16-byte keys); t_big load (5,000 x 60,000-byte keys); a 10 s warm-up scan; scan phase R=1 and R=32 on t_big (180 s each;
t_big flushed at 60 s and 120 s and 500 partitions rewritten after each flush and before the phase, so a memtable holds t_big data);
scan phase on t_small (R=1, 60 s). Alongside: JMX metric series every 2 s, class histogram every 15 s in scan phases and after each load.
Env: TP33_RUN (run1), TP33_SCALE (1; shakedown divisor), TP33_DIR (node data dir), CASSANDRA_HOME (tree)."""
import json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
H = os.path.dirname(os.path.abspath(__file__))
MODE = sys.argv[1] if len(sys.argv) > 1 else ''
if not MODE:
    sys.exit(__doc__)
RUNNAME = os.environ.get('TP33_RUN', 'run1')
SCALE = int(os.environ.get('TP33_SCALE', 1))
C = os.environ.get('CASSANDRA_HOME', f'{HOME}/s4-tp33')
RUN = os.environ.get('TP33_DIR', f'{HOME}/s4-tp33-run')
ADDR, STORAGE, SSL, NATIVE, JMX, BMPORT = '127.0.33.1', 7010, 7011, 9142, 7210, 9110
LOGS = f'{HOME}/s4-tp33-logs/{RUNNAME}/cluster'
BYTEMAN = f'{C}/build/lib/jars/byteman-4.0.20.jar'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
ENV = dict(os.environ, CASSANDRA_CONF=RUN + '/conf', CASSANDRA_LOG_DIR=RUN + '/logs', MAX_HEAP_SIZE='2G', CASSANDRA_HOME=C)
ENV.pop('HEAP_NEWSIZE', None)

N_SMALL = max(1000, 1_000_000 // SCALE)
N_BIG = max(100, 5000 // SCALE)
N_REWRITE = max(20, min(500, N_BIG // 5))
SCAN_S = 180 if SCALE == 1 else 30
FLUSH_AT = [60, 120] if SCALE == 1 else [10, 20]
SMALL_SCAN_S = 60 if SCALE == 1 else 10
LIVES = {  # label: (memtable_allocation_type, heap space, off-heap space)
    'H256': ('heap_buffers', '256MiB', '2048MiB'), 'H1024': ('heap_buffers', '1024MiB', '2048MiB'),
    'H64': ('heap_buffers', '64MiB', '2048MiB'), 'O256': ('offheap_objects', '256MiB', '256MiB')}
ORDER = ['H256', 'H1024', 'H64', 'O256']


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
    alloc, heap, off = LIVES[label]
    conf = RUN + '/conf'
    sh(f'rm -rf {conf} && cp -r {C}/conf {conf}')
    lines = {
        'cluster_name': "'tp33'",
        'data_file_directories': f'\n    - {RUN}/data',
        'commitlog_directory': f'{RUN}/commitlog', 'hints_directory': f'{RUN}/hints',
        'saved_caches_directory': f'{RUN}/saved_caches', 'cdc_raw_directory': f'{RUN}/cdc_raw',
        'listen_address': ADDR, 'rpc_address': ADDR,
        'seed_provider': f'\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: "{ADDR}:{STORAGE}"',
        'storage_port': str(STORAGE), 'ssl_storage_port': str(SSL), 'native_transport_port': str(NATIVE),
        'memtable_allocation_type': alloc, 'memtable_heap_space': heap, 'memtable_offheap_space': off,
        'concurrent_reads': '32', 'commitlog_total_space': '2GiB',
        'autocompaction_on_startup_enabled': 'false',
        'native_transport_timeout': '60s', 'read_request_timeout': '30s', 'range_request_timeout': '60s',
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
    out.append('# ---- stage4 tp33 (B3a) ----')
    out += [f'{k}: {v}' for k, v in lines.items()]
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n')
    env = open(conf + '/cassandra-env.sh').read()
    assert env.count('JMX_PORT="7199"') == 1
    open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"'))
    with open(conf + '/jvm11-server.options', 'a') as fo:
        fo.write(f'\n# stage4 tp33\n-XX:-HeapDumpOnOutOfMemoryError\n-Xlog:gc*:file={RUN}/logs/gc-{label}.log:time,uptime:filecount=10,filesize=100M\n')
        fo.write(f'-javaagent:{BYTEMAN}=script:{H}/trie-growth.btm,listener:true,port:{BMPORT},address:{ADDR}\n-Dstage4.trace={RUN}/logs/tp33-{label}.trace\n')
    log(f'conf {label}: ' + '; '.join(f'{k}={v.strip()}' for k, v in lines.items() if '\n' not in v))


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
                for _ in range(120):                      # statusbinary can say 'running' a few seconds before the port accepts
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


def rss_anon(pid):
    for l in open(f'/proc/{pid}/status'):
        if l.startswith('RssAnon'):
            return int(l.split()[1]) * 1024
    return None


def tb(table, name):
    return f'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope={table},name={name}'


def lifetime(label, wr):
    d = f'{LOGS}/{label}'
    os.makedirs(d, exist_ok=True)
    sh(f'rm -rf {RUN}/data {RUN}/commitlog {RUN}/hints {RUN}/saved_caches {RUN}/cdc_raw && mkdir -p {RUN}/data {RUN}/commitlog {RUN}/hints {RUN}/saved_caches {RUN}/cdc_raw')
    make_conf(label)
    off = os.path.getsize(RUN + '/logs/system.log') if os.path.exists(RUN + '/logs/system.log') else 0
    pid = start_node(label)
    wr(dict(kind='life', life=label, pid=pid, t_ms=now_ms(), cfg=LIVES[label], n_small=N_SMALL, n_big=N_BIG, scan_s=SCAN_S))
    log(f'schema: {client(f"schema {ADDR} {NATIVE}")}')
    nodetool('disableautocompaction ks')
    _, ss = sh('ss -ltn', check=False, quiet=True)
    wr(dict(kind='ports', byteman_listening=bool(re.search(rf'{re.escape(ADDR)}:{BMPORT}\s', ss)), t_ms=now_ms()))
    stop = f'{d}/stop'
    if os.path.exists(stop):
        os.remove(stop)
    series = open(f'{d}/series.csv', 'w')
    series.write('ms,big_on,big_off,big_switch,small_on,small_off,small_switch\n'); series.flush()
    pol = subprocess.Popen(f'exec java -cp {RUN}/tools Jmx {JMX} poll 2000 {stop} "{tb("t_big","MemtableOnHeapDataSize")}" Value '
                           f'"{tb("t_big","MemtableOffHeapDataSize")}" Value "{tb("t_big","MemtableSwitchCount")}" Count '
                           f'"{tb("t_small","MemtableOnHeapDataSize")}" Value "{tb("t_small","MemtableOffHeapDataSize")}" Value '
                           f'"{tb("t_small","MemtableSwitchCount")}" Count', shell=True, stdout=series, env=ENV)
    phases = open(f'{d}/phases.csv', 'w')
    phases.write('phase,start_ms,end_ms,detail\n')
    hn = [0]

    def snap(tag):
        hn[0] += 1
        h = histogram(pid, f'{d}/histo-{hn[0]:03d}-{tag}.txt')
        wr(dict(kind='histo', life=label, tag=tag, t_ms=now_ms(), histo=h, rss_anon=rss_anon(pid)))
        log(f'{label}: histo {tag} byte[] {h.get("byte[]")} total {h.get("total")}')

    def phase(name, fn):
        t0 = now_ms(); log(f'{label}: phase {name} start')
        detail = fn()
        t1 = now_ms()
        phases.write(f'{name},{t0},{t1},{json.dumps(detail).replace(",", ";")}\n'); phases.flush()
        wr(dict(kind='phase', life=label, phase=name, t_start_ms=t0, t_end_ms=t1, detail=detail))
        log(f'{label}: phase {name} end ({(t1 - t0) / 1000:.0f} s) {detail}')

    snap('base')
    phase('load_small', lambda: client(f'load {ADDR} {NATIVE} t_small 0 {N_SMALL} 128'))
    snap('after-load_small')
    phase('load_big', lambda: client(f'load {ADDR} {NATIVE} t_big 0 {N_BIG} 16'))
    snap('after-load_big')
    phase('warm', lambda: client(f'scan {ADDR} {NATIVE} t_big 1 10'))

    def scan_phase(table, R, secs, flushes):
        def run():
            det = {}
            if table == 't_big':
                det['rewrite0'] = client(f'load {ADDR} {NATIVE} t_big 0 {N_REWRITE} 16')
            sc = subprocess.Popen(f'exec python3 -I {H}/client.py scan {ADDR} {NATIVE} {table} {R} {secs}', shell=True, stdout=subprocess.PIPE, text=True, env=ENV)
            t0 = time.time(); nxt_h = 0; fl = list(flushes)
            while sc.poll() is None:
                el = time.time() - t0
                if el >= nxt_h:
                    snap(f'{table}-R{R}-t{int(el)}'); nxt_h += 15
                if fl and el >= fl[0]:
                    fl.pop(0)
                    nodetool(f'flush ks {table}')
                    det.setdefault('flushes_at', []).append(int(el))
                    det.setdefault('rewrites', []).append(client(f'load {ADDR} {NATIVE} t_big 0 {N_REWRITE} 16')['ok'])
                time.sleep(1)
            out = sc.stdout.read().strip().splitlines()
            det['scan'] = json.loads(out[-1]) if out else {'error': 'no output'}
            return det
        return run

    phase('scan_big_R1', scan_phase('t_big', 1, SCAN_S, FLUSH_AT))
    phase('scan_big_R32', scan_phase('t_big', 32, SCAN_S, FLUSH_AT))
    phase('scan_small_R1', scan_phase('t_small', 1, SMALL_SCAN_S, []))
    nodetool('flush ks')
    snap('end')
    open(stop, 'w').write('stop')
    time.sleep(3)
    pol.wait(timeout=60); series.close(); phases.close()
    _, du = sh(f'du -sb {RUN}/data', check=False, quiet=True)
    with open(RUN + '/logs/system.log', 'rb') as f:
        f.seek(off); seg = f.read()
    open(f'{d}/system.log', 'wb').write(seg)
    errs = [l for l in seg.decode(errors='replace').splitlines() if l.startswith('ERROR') or 'java.lang.OutOfMemoryError' in l]
    wr(dict(kind='end', life=label, error_lines=len(errs), first_errors=errs[:5], du_bytes=du.split()[0] if du else None, t_ms=now_ms()))
    log(f'{label}: system.log ERROR/OOM lines {len(errs)} {errs[:2]}; data {du.split()[0] if du else "?"} B')
    stop_node()
    sh(f'cp {RUN}/logs/tp33-{label}.trace {d}/growth-trace.txt 2>/dev/null; cp {RUN}/logs/gc-{label}.log {d}/ 2>/dev/null; cp {RUN}/conf/cassandra.yaml {d}/cassandra.yaml; true', check=False)


def main():
    if MODE == 'down':
        stop_node(); log('daemons left: ' + str(daemons())); return
    log(f'cluster-run {RUNNAME}: RUN={RUN} tree={C} scale={SCALE} n_small={N_SMALL} n_big={N_BIG} scan_s={SCAN_S}')
    sh('git describe --tags; git rev-parse --short HEAD; java -version 2>&1 | head -1; uname -r; df -h ' + HOME, check=False)
    _, ss = sh('ss -ltn', check=False, quiet=True)
    busy = [str(p) for p in (STORAGE, SSL, NATIVE, JMX, BMPORT) if re.search(rf':{p}\s', ss)]
    if busy or daemons():
        raise RuntimeError(f'ports busy {busy} or daemons {daemons()}')
    sh(f'mkdir -p {RUN}/logs {RUN}/tools && javac -d {RUN}/tools {H}/Jmx.java')
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
