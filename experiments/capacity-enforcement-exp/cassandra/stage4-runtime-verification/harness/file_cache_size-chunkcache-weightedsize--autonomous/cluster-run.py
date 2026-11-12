#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of file_cache_size-chunkcache-weightedsize--autonomous, as amended by AM3-AM6, AM8 (case file section D).
usage: cluster-run.py <run-name> [shakedown]      (a background job on the node; every exit stops the node it started)
Tree: /mydata/jingsong-cass-s4/o05/src (built). Node data/conf/logs: /mydata/jingsong-cass-s4/o05/node-<run-name>/.
Output: /mydata/jingsong-cass-s4/o05/logs/cluster-<run-name>/ (session.log, samples.jsonl, stress-*.log, nodetool-*.txt, system.log copy).
Ports: storage 7300, ssl 7301, JMX 7499, native 9342 (127.0.0.1). Heap 2G (G1), MaxDirectMemorySize 4G, NMT summary.
Steps (B3e): start node (cache disabled) -> stress write n=N_ROWS (LZ4, AM3) -> flush -> wait 0 pending compactions (AM4)
 -> for setting in [disabled, 64, 256, 512]: stop, set yaml, start, 60 s idle samples, 10 min read (32 threads) with samples
    every 30 s, 60 s post samples -> stop node; remove data dir (logs kept).
shakedown: N_ROWS=200000, read 60 s, idle/post 30 s, settings [disabled, 40] (checks the instruments; 40 MiB is not a frozen value, so no reading of the case)."""
import json, os, re, shutil, signal, subprocess, sys, time

B = '/mydata/jingsong-cass-s4/o05'
C = B + '/src'
H = os.path.dirname(os.path.abspath(__file__))
RUNNAME = sys.argv[1] if len(sys.argv) > 1 else sys.exit(__doc__)
SHAKE = len(sys.argv) > 2 and sys.argv[2] == 'shakedown'
N_ROWS = 200000 if SHAKE else 4000000
READ_S = 60 if SHAKE else 600
IDLE_S = 30 if SHAKE else 60
SAMPLE_S = 30
SETTINGS = ['disabled', 40] if SHAKE else ['disabled', 64, 256, 512]
NODE = f'{B}/node-{RUNNAME}'
LOGS = f'{B}/logs/cluster-{RUNNAME}'
JMX, NATIVE, STORAGE, SSL = 7499, 9342, 7300, 7301
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SAMPLES = open(LOGS + '/samples.jsonl', 'a')
ENV = dict(os.environ, CASSANDRA_CONF=NODE + '/conf', CASSANDRA_LOG_DIR=NODE + '/logs', MAX_HEAP_SIZE='2G',
           MAX_DIRECT_MEMORY_SIZE='4G', CASSANDRA_HOME=C)
for k in ('HEAP_NEWSIZE', 'JVM_EXTRA_OPTS', 'JVM_OPTS'):
    ENV.pop(k, None)
NODE_ENV = dict(ENV, JVM_EXTRA_OPTS='-XX:NativeMemoryTracking=summary')   # scoped to bin/cassandra only (environment.md section 6)
NT = f'{C}/bin/nodetool -h 127.0.0.1 -p {JMX}'


def log(s):
    line = f'[{time.strftime("%FT%TZ", time.gmtime())} {int(time.time()*1000)}] {s}'
    print(line, flush=True)
    SESSION.write(line + '\n'); SESSION.flush()


def sh(cmd, timeout=900, check=True, quiet=False, env=None):
    log('+ ' + cmd[:400])
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env or ENV, cwd=C)
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
        pid = int(open(NODE + '/pid').read().strip())
    except Exception:
        return None
    try:
        cmd = open(f'/proc/{pid}/cmdline').read()
    except Exception:
        return None
    return pid if ('CassandraDaemon' in cmd and NODE in cmd) else None


def write_conf(setting):
    conf = NODE + '/conf'
    if not os.path.isdir(conf):
        shutil.copytree(C + '/conf', conf)
        env = open(conf + '/cassandra-env.sh').read()
        env, n = re.subn(r'^JMX_PORT="7199"$', f'JMX_PORT="{JMX}"', env, flags=re.M)
        assert n == 1, 'JMX_PORT line not found'
        open(conf + '/cassandra-env.sh', 'w').write(env)
    y = open(C + '/conf/cassandra.yaml').read()
    sets = {
        'cluster_name': "'o05'", 'storage_port': STORAGE, 'ssl_storage_port': SSL, 'native_transport_port': NATIVE,
        'listen_address': '127.0.0.1', 'rpc_address': '127.0.0.1',
        'commitlog_directory': NODE + '/commitlog', 'hints_directory': NODE + '/hints',
        'saved_caches_directory': NODE + '/saved_caches', 'cdc_raw_directory': NODE + '/cdc_raw',
        'disk_access_mode': 'mmap_index_only', 'key_cache_size': '0MiB', 'row_cache_size': '0MiB',
        'file_cache_enabled': 'false' if setting == 'disabled' else 'true',
    }
    if setting != 'disabled':
        sets['file_cache_size'] = f'{setting}MiB'
    lines = []
    for ln in y.split('\n'):
        m = re.match(r'^([a-z_]+):', ln)          # drop only uncommented top-level lines of the keys we set
        if m and m.group(1) in sets:
            continue
        lines.append(ln)
    y = '\n'.join(lines)
    y = re.sub(r'- seeds: "127\.0\.0\.1:7000"', f'- seeds: "127.0.0.1:{STORAGE}"', y)
    assert f'127.0.0.1:{STORAGE}' in y, 'seeds line not found'
    y = re.sub(r'^data_file_directories:.*$', '', y, flags=re.M)
    y += '\n# --- o05 stage-4 settings ---\n' + ''.join(f'{k}: {v}\n' for k, v in sets.items())
    y += f'data_file_directories:\n    - {NODE}/data\n'
    open(conf + '/cassandra.yaml', 'w').write(y)
    tail = y[y.index('# --- o05'):]
    log('yaml settings:\n' + tail)


def start_node():
    assert node_pid() is None
    for p in (JMX, NATIVE, STORAGE, SSL):      # a stopped JVM can hold its sockets for some seconds after /proc shows it gone
        for _ in range(90):
            rc, out = sh(f"ss -ltn '( sport = :{p} )' | tail -n +2", check=False, quiet=True)
            if not out.strip():
                break
            time.sleep(1)
        else:
            raise RuntimeError(f'port {p} busy: {out}')
    sh(f'( setsid nohup {C}/bin/cassandra -p {NODE}/pid < /dev/null > {NODE}/logs/stdout.log 2>&1 & )', env=NODE_ENV)
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(3)
        if time.time() - t0 > 15 and node_pid() is None:
            raise RuntimeError('daemon died during start')
        rc, out = sh(f'{NT} status 2>/dev/null | grep "^UN"; {NT} statusbinary 2>/dev/null', check=False, quiet=True)
        if out.startswith('UN') and 'running' in out:
            LAST_PID[0] = node_pid()
            log(f'node up (pid {node_pid()}) after {time.time()-t0:.0f} s')
            rc, cmd = sh(f'tr "\\0" " " < /proc/{node_pid()}/cmdline', quiet=True)
            log('cmdline flags: ' + ' '.join(x for x in cmd.split() if x.startswith('-X')))
            return
    raise RuntimeError('node did not come up')


LAST_PID = [None]


def alive(pid):
    try:
        return 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read()
    except Exception:
        return False


def stop_node():
    pid = node_pid() or LAST_PID[0]
    if pid is None or not alive(pid):
        return
    log(f'stopping node pid {pid}')
    os.kill(pid, signal.SIGTERM)
    for _ in range(180):          # wait for the process itself, not the pid file (removed early at shutdown)
        time.sleep(1)
        if not alive(pid):
            log('node stopped'); return
    os.kill(pid, signal.SIGKILL); time.sleep(3)
    log('node killed (SIGKILL)')


def sample(setting, stage):
    pid = node_pid()
    rec = {'setting': setting, 'stage': stage, 't_ms': int(time.time() * 1000)}
    rc, out = sh(f'java -cp {B}/harness-classes O05Jmx {JMX}', check=False, quiet=True, timeout=60)
    m = re.search(r'O05JMX (.*)', out)
    if m:
        for kv in m.group(1).split():
            k, v = kv.split('=', 1)
            rec[k] = None if v == 'NA' else (int(v) if re.fullmatch(r'-?\d+', v) else v)
    else:
        rec['jmx_error'] = out[-300:]
    if pid:
        rc, out = sh(f'jcmd {pid} VM.native_memory summary', check=False, quiet=True, timeout=60)
        m = re.search(r'-\s+Other \(reserved=(\d+)KB, committed=(\d+)KB\)', out)
        rec['nmt_other_committed_kb'] = int(m.group(2)) if m else None
        try:
            st = open(f'/proc/{pid}/status').read()
            rec['rss_anon_kb'] = int(re.search(r'RssAnon:\s+(\d+)', st).group(1))
            rec['vm_rss_kb'] = int(re.search(r'VmRSS:\s+(\d+)', st).group(1))
        except Exception as e:
            rec['proc_error'] = str(e)
    SAMPLES.write(json.dumps(rec) + '\n'); SAMPLES.flush()
    return rec


def sample_for(setting, stage, seconds):
    end = time.time() + seconds
    while time.time() < end:
        t = time.time()
        r = sample(setting, stage)
        log(f'sample {setting} {stage}: cc_size={r.get("cc_size")} entries={r.get("cc_entries")} pool={r.get("pool_size")} '
            f'ovf={r.get("pool_overflow")} direct={r.get("direct_used")} req={r.get("cc_requests")} miss={r.get("cc_misses")}')
        time.sleep(max(0, SAMPLE_S - (time.time() - t)))


STRESS = f'{C}/tools/bin/cassandra-stress'
COMMON = f"-col 'n=FIXED(5)' 'size=FIXED(200)' -node 127.0.0.1 -port native={NATIVE} jmx={JMX}"


def main():
    log(f'=== cluster run {RUNNAME} shakedown={SHAKE} N_ROWS={N_ROWS} READ_S={READ_S} settings={SETTINGS}')
    os.makedirs(NODE + '/logs', exist_ok=True)
    sh(f'javac -d {B}/harness-classes {H}/O05Jmx.java')
    write_conf('disabled')
    start_node()
    sh(f'{STRESS} write n={N_ROWS} {COMMON} -rate threads=32 -schema "replication(factor=1)" compression=LZ4Compressor '
       f'> {LOGS}/stress-write.log 2>&1', timeout=3600)
    sh(f'grep -A30 "^Results:" {LOGS}/stress-write.log | head -30; grep -i "error" {LOGS}/stress-write.log | head -5', check=False)
    sh(f'{NT} flush keyspace1')
    for i in range(240):
        rc, out = sh(f'{NT} compactionstats', check=False, quiet=True)
        m = re.search(r'pending tasks:?\s+(\d+)', out)
        if m and m.group(1) == '0' and not re.search(r'^\s*\S+\s+Compaction\s', out, re.M):   # no task in progress either
            log('compactions settled: ' + m.group(0))
            break
        time.sleep(5)
    sh(f'{NT} compactionstats > {LOGS}/nodetool-compactionstats.txt 2>&1', check=False)
    sh(f'{NT} tablestats keyspace1.standard1 > {LOGS}/nodetool-tablestats.txt 2>&1')
    sh(f'cat {LOGS}/nodetool-tablestats.txt | grep -E "SSTable count|Space used \\(live\\)|Compression|Number of partitions"', check=False)
    sh(f'du -sb {NODE}/data', check=False)
    sh(f'cqlsh_out=$({C}/bin/cqlsh 127.0.0.1 {NATIVE} -e "DESCRIBE TABLE keyspace1.standard1" 2>&1); echo "$cqlsh_out" | grep -i compression', check=False)
    for s in SETTINGS:
        log(f'=== setting {s}')
        stop_node()
        write_conf(s)
        start_node()
        sh(f'{NT} info > {LOGS}/nodetool-info-{s}-start.txt 2>&1', check=False)
        sample_for(s, 'idle', IDLE_S)
        log(f'read start {s}')
        p = subprocess.Popen(f'{STRESS} read duration={READ_S}s -pop dist=UNIFORM\\(1..{N_ROWS}\\) {COMMON} -rate threads=32 '
                             f'> {LOGS}/stress-read-{s}.log 2>&1', shell=True, env=ENV, cwd=C, preexec_fn=os.setsid)
        t0 = time.time()
        while p.poll() is None:
            t = time.time()
            r = sample(s, 'read')
            log(f'sample {s} read +{t-t0:.0f}s: cc_size={r.get("cc_size")} entries={r.get("cc_entries")} pool={r.get("pool_size")} '
                f'ovf={r.get("pool_overflow")} direct={r.get("direct_used")} req={r.get("cc_requests")} miss={r.get("cc_misses")}')
            if time.time() - t0 > READ_S + 300:
                log('stress read overran; killing it'); os.killpg(p.pid, signal.SIGTERM); break
            while p.poll() is None and time.time() - t < SAMPLE_S:
                time.sleep(1)
        log(f'read end {s} rc={p.returncode}')
        sh(f'grep -A30 "^Results:" {LOGS}/stress-read-{s}.log | head -30', check=False)
        sh(f'{NT} info > {LOGS}/nodetool-info-{s}-end.txt 2>&1', check=False)
        sample_for(s, 'post', IDLE_S)
        sh(f'cp {NODE}/logs/system.log {LOGS}/system-{s}.log', check=False)
    stop_node()


if __name__ == '__main__':
    try:
        main()
        log('CLUSTER RUN DONE')
    except Exception as e:
        log(f'CLUSTER RUN FAILED: {e!r}')
    finally:
        stop_node()
        if True:
            for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
                shutil.rmtree(f'{NODE}/{d}', ignore_errors=True)
        time.sleep(3)
        left = []
        for d in os.listdir('/proc'):
            if d.isdigit():
                try:
                    cl = open(f'/proc/{d}/cmdline').read()
                except Exception:
                    continue
                if 'CassandraDaemon' in cl and NODE in cl:
                    left.append(d)
        n = len(left)
        log(f'leftover CassandraDaemon processes from this run: {n}')
