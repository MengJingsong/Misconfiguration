#!/usr/bin/env python3
"""Stage 4, cluster tier (B3e as amended M5-M9) of commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous.
usage: cluster-run.py <outdir> [values...]      default values: 3 6 12 24 mmap6   (a background job; every exit stops the node)
One node on 127.0.0.1, storage 7400, ssl 7401, native 9442, JMX 7599; tree /mydata/jingsong-cass-s4/o44/src; data /mydata/jingsong-cass-s4/o44/node.
Per value: wipe node dirs, write conf, start (MAX_HEAP_SIZE=4G, MAX_DIRECT_MEMORY_SIZE=3G, NMT summary), wait UN + binary running,
sampler (Sampler.java, 2 s), 30 s idle, cassandra-stress (timeout 180 s), NMT + du every 30 s, stop (drain<=120 s, TERM 60 s, KILL)."""
import os, re, shutil, signal, subprocess, sys, time
H = os.path.dirname(os.path.abspath(__file__))
SRC = '/mydata/jingsong-cass-s4/o44/src'
NODE = '/mydata/jingsong-cass-s4/o44/node'
OUT = sys.argv[1]
VALUES = sys.argv[2:] or ['3', '6', '12', '24', 'mmap6']
JMX = 7599
os.makedirs(OUT, exist_ok=True)
SES = open(f'{OUT}/session.log', 'a')
def log(s):
    line = f'[{time.strftime("%FT%TZ", time.gmtime())} {int(time.time()*1000)}] {s}'
    print(line, flush=True); SES.write(line + '\n'); SES.flush()
def sh(cmd, timeout=None, env=None, out=None):
    log('+ ' + cmd)
    try:
        r = subprocess.run(cmd, shell=True, cwd=SRC, env=env, timeout=timeout, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        o = r.stdout
        rc = r.returncode
    except subprocess.TimeoutExpired as e:
        o = (e.stdout or b'').decode() if isinstance(e.stdout, bytes) else (e.stdout or ''); rc = 'timeout'
    if out:
        open(out, 'a').write(o)
    else:
        SES.write(o[-4000:]); SES.flush()
    log(f'rc={rc}')
    return rc, o

def yaml_for(n, compress):
    base = open(f'{SRC}/conf/cassandra.yaml').read().split('\n')
    keys = ['cluster_name', 'data_file_directories', 'commitlog_directory', 'saved_caches_directory', 'hints_directory', 'cdc_raw_directory',
            'listen_address', 'rpc_address', 'seed_provider', 'storage_port', 'ssl_storage_port', 'native_transport_port', 'commitlog_segment_size',
            'commitlog_compression', 'commitlog_sync', 'commitlog_sync_period', 'periodic_commitlog_sync_lag_block', 'commitlog_total_space',
            'write_request_timeout', 'native_transport_timeout', 'commitlog_max_compression_buffers_in_pool']
    out, skip = [], False
    for l in base:
        m = re.match(r'^([a-z_]+):', l)
        if m:
            skip = m.group(1) in keys
        elif skip and l and not (l.startswith(' ') or l.startswith('-') or l.startswith('#')):
            skip = False
        if not skip:
            out.append(l)
    add = f"""
# ---- stage-4 o44 overrides (case B3a as amended M5) ----
cluster_name: o44
data_file_directories: [{NODE}/data]
commitlog_directory: {NODE}/commitlog
saved_caches_directory: {NODE}/saved_caches
hints_directory: {NODE}/hints
cdc_raw_directory: {NODE}/cdc_raw
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
seed_provider: [{{class_name: org.apache.cassandra.locator.SimpleSeedProvider, parameters: [{{seeds: "127.0.0.1:7400"}}]}}]
storage_port: 7400
ssl_storage_port: 7401
native_transport_port: 9442
commitlog_segment_size: 64MiB
commitlog_sync: periodic
commitlog_sync_period: 10000ms
periodic_commitlog_sync_lag_block: 600000ms
commitlog_total_space: 8192MiB
write_request_timeout: 60000ms
native_transport_timeout: 60000ms
commitlog_max_compression_buffers_in_pool: {n}
"""
    if compress:
        add += """commitlog_compression:
  - class_name: ZstdCompressor
    parameters:
      - compression_level: "19"
"""
    return '\n'.join(out) + add

CUR = {'pid': None}   # fix D3 (2026-11-11): Cassandra deletes its pid file when shutdown starts, so track the PID read at start
def alive(p):
    try:
        os.kill(p, 0)
    except Exception:
        return False
    try:
        return 'CassandraDaemon' in open(f'/proc/{p}/cmdline').read().replace('\0', ' ')
    except Exception:
        return False
def node_pid():
    p = CUR['pid']
    if p is None:
        try:
            p = int(open(f'{NODE}/pid').read().strip()); CUR['pid'] = p
        except Exception:
            return None
    return p if alive(p) else None

def stop_node():
    p = node_pid()
    if not p:
        log('stop: no live node pid'); return
    sh(f'bin/nodetool -p {JMX} drain', timeout=120)
    for sig, wait in ((signal.SIGTERM, 60), (signal.SIGKILL, 30)):
        if not node_pid(): break
        log(f'kill {sig.name} {p}')
        try: os.kill(p, sig)
        except ProcessLookupError: break
        t0 = time.time()
        while time.time() - t0 < wait and node_pid(): time.sleep(1)
    log(f'node stopped: {node_pid() is None}')
    CUR['pid'] = None

def run_value(v):
    compress = not v.startswith('mmap')
    n = int(v.replace('mmap', ''))
    tag = v
    st = os.statvfs('/mydata'); free = st.f_bavail * st.f_frsize / 2**30
    log(f'=== value {tag}: N={n} compression={"Zstd19" if compress else "none (mmap)"}; /mydata free {free:.1f} GiB')
    if free < 30: log('STOP: < 30 GiB free'); return False
    left = subprocess.run('ps -C java -o pid,args | grep "[C]assandraDaemon" | grep -c "jingsong-cass-s4/o44"', shell=True, stdout=subprocess.PIPE, text=True).stdout.strip()
    if left != '0':
        log(f'STOP: an o44 node is still running ({left})'); return False
    CUR['pid'] = None
    for d in ('data', 'commitlog', 'saved_caches', 'hints', 'cdc_raw', 'logs', 'conf'):
        shutil.rmtree(f'{NODE}/{d}', ignore_errors=True)
    shutil.copytree(f'{SRC}/conf', f'{NODE}/conf')
    open(f'{NODE}/conf/cassandra.yaml', 'w').write(yaml_for(n, compress))
    envsh = open(f'{NODE}/conf/cassandra-env.sh').read()
    envsh = envsh.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"')
    open(f'{NODE}/conf/cassandra-env.sh', 'w').write(envsh)
    env = dict(os.environ, CASSANDRA_CONF=f'{NODE}/conf', CASSANDRA_LOG_DIR=f'{NODE}/logs', MAX_HEAP_SIZE='4G', MAX_DIRECT_MEMORY_SIZE='3G')
    env.pop('HEAP_NEWSIZE', None)
    senv = dict(env, JVM_EXTRA_OPTS='-XX:NativeMemoryTracking=summary')
    sh(f'bin/cassandra -p {NODE}/pid > {OUT}/start-{tag}.out 2>&1', env=senv, timeout=60)
    t0 = time.time(); up = False
    while time.time() - t0 < 240:
        time.sleep(3)
        if not node_pid():
            log('STOP: node died during start'); return False
        r1 = subprocess.run(f'bin/nodetool -p {JMX} status 2>/dev/null | grep -q "^UN" && bin/nodetool -p {JMX} statusbinary 2>/dev/null', shell=True, cwd=SRC, env=env, stdout=subprocess.PIPE, text=True)
        if 'running' in r1.stdout:
            up = True; break
    if not up:
        log('STOP: node not up in 240 s'); stop_node(); return False
    pid = node_pid(); log(f'node up pid={pid}')
    sh(f'ps -o pid,args -p {pid} | tr " " "\\n" | grep -E "Xmx|Xms|MaxDirectMemorySize|NativeMemoryTracking"', env=env)
    sh(f'grep -E "commitlog_max_compression_buffers_in_pool=|commitlog_compression=|commitlog_segment_size=|commitlog_disk_access_mode=|native_transport_port=|storage_port=" -o {NODE}/logs/system.log | sort -u; grep -oE "commitlog_max_compression_buffers_in_pool=[0-9]+|commitlog_compression=[^;]*;" {NODE}/logs/system.log | head -3', env=env)
    sh(f'grep -i "Zstd\\|commit log disk access mode\\|DiskAccessMode" {NODE}/logs/system.log | head -5', env=env)
    stopf = f'{OUT}/sampler-{tag}.stop'
    if os.path.exists(stopf): os.remove(stopf)
    csv = f'{OUT}/samples-{tag}.csv'
    sampler = subprocess.Popen(['java', f'{H}/Sampler.java', str(JMX), f'{NODE}/commitlog', csv, stopf], stdout=open(f'{OUT}/sampler-{tag}.err', 'w'), stderr=subprocess.STDOUT)
    log(f'sampler pid={sampler.pid}')
    def periodic(phase, secs):
        end = time.time() + secs
        while time.time() < end:
            sh(f'jcmd {pid} VM.native_memory summary | grep -E "^-  *(Other|Internal)|Total:" ; echo epoch_ms=$(date +%s%3N)', out=f'{OUT}/nmt-{tag}.txt')
            sh(f'echo {phase} $(date +%s%3N) $(du -sb {NODE} | cut -f1)', out=f'{OUT}/du-{tag}.txt')
            time.sleep(max(0, min(30, end - time.time())))
    log(f'PHASE idle_start {int(time.time()*1000)}')
    periodic('idle', 30)
    log(f'PHASE stress_start {int(time.time()*1000)}')
    stress_cmd = ('timeout 180 tools/bin/cassandra-stress write n=2000000 cl=ONE -rate threads=64 -col "n=FIXED(1)" "size=FIXED(4096)" '
                  '-port native=9442 jmx=7599 -node 127.0.0.1 -errors ignore -schema "replication(factor=1)"')
    log('+ ' + stress_cmd)
    sp = subprocess.Popen(stress_cmd, shell=True, cwd=SRC, env=env, stdout=open(f'{OUT}/stress-{tag}.log', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
    while sp.poll() is None:
        sh(f'jcmd {pid} VM.native_memory summary | grep -E "^-  *(Other|Internal)|Total:" ; echo epoch_ms=$(date +%s%3N)', out=f'{OUT}/nmt-{tag}.txt')
        sh(f'echo stress $(date +%s%3N) $(du -sb {NODE} | cut -f1)', out=f'{OUT}/du-{tag}.txt')
        for _ in range(30):
            if sp.poll() is not None: break
            time.sleep(1)
    log(f'PHASE stress_end {int(time.time()*1000)} rc={sp.returncode}')
    try: os.killpg(sp.pid, signal.SIGKILL)
    except Exception: pass
    time.sleep(3)
    open(stopf, 'w').close(); sampler.wait(timeout=30)
    sh(f'grep -E "^ERROR" {NODE}/logs/system.log | sort | uniq -c | sort -rn | head -5; grep -c "^WARN" {NODE}/logs/system.log', env=env)
    sh(f'bin/nodetool -p {JMX} tpstats | head -30', env=env)
    stop_node()
    for f in ('system.log', 'debug.log'):
        if os.path.exists(f'{NODE}/logs/{f}'): shutil.copy(f'{NODE}/logs/{f}', f'{OUT}/{f.split(".")[0]}-{tag}.log')
    shutil.copy(f'{NODE}/conf/cassandra.yaml', f'{OUT}/cassandra-{tag}.yaml')
    sh(f'ps -eo pid,args | grep "[j]ava" | grep -E "o44" || echo "no o44 java left"')
    return True

log(f'start cluster run values={VALUES}')
try:
    for v in VALUES:
        if not run_value(v):
            log(f'value {v} failed; stopping run'); break
finally:
    stop_node()
    sh('ps -eo pid,args | grep "[C]assandraDaemon" | grep -c "o44" || true')
    log('end cluster run')
