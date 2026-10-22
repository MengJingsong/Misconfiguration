#!/usr/bin/env python3
"""Stage 4, cluster tier (B3, with audit amendments R4-R8) of largestRatio-flushLargestMemtable-largestRatio--autonomous.
usage: cluster-run.py <run> <arm> [<arm> ...]       arms: L256-skew L256-even L1024-skew L1024-even never | down
  Lxxx-skew  : M-orig build (~/cassandra-lrt), memtable_heap_space xxx MiB, one stress process, n=4,000,000, 64 threads, ks1
  Lxxx-even  : the same, four stress processes together, n=1,000,000 and 16 threads each, ks1..ks4
  never      : M-never build (~/cassandra-lrt-mut, line 251 = Float.MAX_VALUE), L=256 MiB, W-skew with n=1,000,000 and
               -errors ignore, stress stopped 300 s after start (R7)
  down       : stop this harness's node and stress (java processes whose command line contains cassandra-lrt only)
One node, a fresh data directory and JVM per arm (B3e step 1), on 127.0.0.4 with JMX 7204 (environment deviation E1:
host shared with another stage-4 session). MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M (ignored under G1, as cassandra-env.sh
says). Every stress command has no-warmup and quoted -col options (R5); each keyspace is created first by a 100-row
stress write. Samplers: Jmx poll every 1 s (R6: AllMemtablesOnHeapDataSize, BlockedOnAllocation Count, heap used,
G1 Old Gen Usage.used and CollectionUsage.used). After stress: 30 s wait, tablestats, du, then the node is stopped.
Output: ~/stage4-logs/lrt/<run>/cluster/<arm>/ (session.log in the run dir, system.log/debug.log/gc.log, jmx.csv,
stress-*.out, tablestats.txt, du.txt, flushes.txt, arm.json). Analysis: cluster-analyze.py."""
import json, os, re, signal, subprocess, sys, time

HOME = os.path.expanduser('~')
HARNESS = os.path.dirname(os.path.abspath(__file__))
ORIG, MUT = HOME + '/cassandra-lrt', HOME + '/cassandra-lrt-mut'
ADDR, JMXP = '127.0.0.4', 7204
NODE = HOME + '/stage4-lrt/node'
JMXCP = HOME + '/stage4-lrt/jmx'
RUN = sys.argv[1] if len(sys.argv) > 1 else ''
ARMS = sys.argv[2:]
if not RUN or not ARMS:
    sys.exit(__doc__)
OUT = f'{HOME}/stage4-logs/lrt/{RUN}/cluster'
os.makedirs(OUT, exist_ok=True)
SESSION = open(OUT + '/session.log', 'a')
CHILDREN = []
MIN_FREE_GB = 25.0
SCALE = int(os.environ.get('LRT_SCALE', '1'))   # shakedown only: divides every timed n; run 1 uses 1


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, flush=True)
    SESSION.write(line + '\n'); SESSION.flush()


def sh(cmd, timeout=600, check=True, env=None, cwd=None, quiet=False):
    log('+ ' + cmd)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    except subprocess.TimeoutExpired:
        log(f'  TIMEOUT after {timeout} s')
        if check:
            raise RuntimeError('timeout: ' + cmd)
        return 124, ''
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'rc={r.returncode}: {cmd}\n{out[-1000:]}')
    return r.returncode, out


def my_java():
    """pid -> args of java processes whose command line contains 'cassandra-lrt' (never another session's)."""
    res = {}
    for p in os.listdir('/proc'):
        if not p.isdigit():
            continue
        try:
            a = open(f'/proc/{p}/cmdline', 'rb').read().split(b'\0')
        except OSError:
            continue
        if a and a[0].endswith(b'java') and b'cassandra-lrt' in b' '.join(a):
            res[int(p)] = b' '.join(a).decode(errors='replace')
    return res


def daemons():
    return [p for p, a in my_java().items() if 'CassandraDaemon' in a]


def free_gb():
    st = os.statvfs(HOME)
    return st.f_bavail * st.f_frsize / 1e9


def nodetool(c, args, timeout=120, quiet=True):
    return sh(f'{c}/bin/nodetool -h 127.0.0.1 -p {JMXP} {args}', timeout=timeout, check=False, quiet=quiet)


def stop_all(c=ORIG):
    for p in CHILDREN:
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
    for p in [p for p, a in my_java().items() if 'cassandra.stress' in a or 'Jmx' in a.split()]:
        os.kill(p, signal.SIGKILL)
    for p in daemons():
        log(f'SIGTERM node {p}')
        os.kill(p, signal.SIGTERM)
    for _ in range(60):
        if not daemons():
            break
        time.sleep(1)
    for p in daemons():
        log(f'node {p} alive after 60 s: SIGKILL')
        os.kill(p, signal.SIGKILL)
    time.sleep(2)
    left = my_java()
    log(f'java processes matching cassandra-lrt left: {len(left)} {list(left)}')
    return left


def make_conf(c, L, d):
    conf = NODE + '/conf'
    sh(f'rm -rf {NODE} && mkdir -p {NODE}/data {NODE}/commitlog {NODE}/hints {NODE}/saved_caches {NODE}/cdc && cp -r {c}/conf {conf}')
    for f in ('cassandra.yaml', 'cassandra-env.sh', 'jvm-server.options', 'logback.xml'):
        sh(f'git -C {c} show HEAD:conf/{f} > {conf}/{f}')
    sh(f'sed -i \'s/^JMX_PORT="7199"/JMX_PORT="{JMXP}"/\' {conf}/cassandra-env.sh && grep -q \'^JMX_PORT="{JMXP}"\' {conf}/cassandra-env.sh')
    with open(conf + '/jvm-server.options', 'a') as f:
        f.write(f'\n# stage4 lrt (B3a)\n-XX:HeapDumpPath={d}\n-Xlog:gc*:file={d}/gc.log:time,uptime\n')
    lines = {
        'cluster_name': "'stage4-lrt'", 'listen_address': ADDR, 'rpc_address': ADDR,
        'data_file_directories': f'\n    - {NODE}/data', 'commitlog_directory': NODE + '/commitlog',
        'hints_directory': NODE + '/hints', 'saved_caches_directory': NODE + '/saved_caches', 'cdc_raw_directory': NODE + '/cdc',
        'memtable_allocation_type': 'heap_buffers', 'memtable_heap_space': f'{L}MiB', 'memtable_offheap_space': '64MiB',
        'commitlog_total_space': '16384MiB', 'auto_snapshot': 'false',
        'seed_provider': f'\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: "{ADDR}:7000"',
    }
    src = open(conf + '/cassandra.yaml').read().splitlines()
    out, skip = [], False
    for l in src:
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
    out.append('# ---- stage4 lrt lines (B3a) ----')
    out += [f'{k}: {v}' for k, v in lines.items()]
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n')
    sh(f'sed -n "/stage4 lrt lines/,\\$p" {conf}/cassandra.yaml > {d}/yaml-tail.txt; git -C {c} show HEAD:conf/cassandra.yaml > {d}/shipped.yaml; diff {d}/shipped.yaml {conf}/cassandra.yaml > {d}/yaml.diff; rm {d}/shipped.yaml; true',
       env=None)
    return conf


def start_node(c, conf, d):
    if daemons():
        raise RuntimeError('a cassandra-lrt node is already running')
    env = dict(os.environ, CASSANDRA_CONF=conf, CASSANDRA_LOG_DIR=d, MAX_HEAP_SIZE='4G', HEAP_NEWSIZE='800M')
    env.pop('JVM_EXTRA_OPTS', None)
    sh(f'ulimit -n 100000; {c}/bin/cassandra -p {NODE}/pid > {d}/stdout.txt 2>&1', env=env, cwd=c)
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(3)
        if time.time() - t0 > 20 and not daemons():
            raise RuntimeError('node died during start; see stdout.txt')
        _, st = nodetool(c, 'status')
        _, sb = nodetool(c, 'statusbinary')
        if re.search(r'^UN\s+' + re.escape(ADDR) + r'\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
            pid = daemons()[0]
            a = my_java()[pid]
            log(f'UN and serving after {time.time() - t0:.0f} s, pid {pid}; jvm: ' +
                ' '.join(sorted(set(x for x in a.split() if x.startswith(('-Xmx', '-Xms', '-XX:+UseG1GC', '-Dcassandra.jmx.local.port', '-Xlog'))))))
            return pid
    raise RuntimeError('node not UN within 300 s')


def stress_cmd(c, ks, n, threads, extra=''):
    return (f'{c}/tools/bin/cassandra-stress write n={n} no-warmup cl=ONE -col \'n=FIXED(1)\' \'size=FIXED(1024)\' '
            f'-rate threads={threads} -schema keyspace={ks} \'replication(strategy=SimpleStrategy,factor=1)\' '
            f'-node {ADDR} -mode native cql3 {extra}').strip()


def run_arm(arm):
    never = arm == 'never'
    c = MUT if never else ORIG
    L = 256 if never else int(re.match(r'L(\d+)-', arm).group(1))
    even = arm.endswith('-even')
    d = f'{OUT}/{arm}'
    sh(f'rm -rf {d} && mkdir -p {d}')
    info = {'arm': arm, 'clone': c, 'L_MiB': L, 'workload': 'even' if even else 'skew', 'build': 'M-never' if never else 'M-orig'}
    _, diff = sh(f'git -C {c} diff -- src', quiet=True)
    open(d + '/src.diff', 'w').write(diff)
    if never != ('float largestRatio = Float.MAX_VALUE;' in diff) or (not never and diff.strip()):
        raise RuntimeError('build does not match the arm: ' + diff[:300])
    if free_gb() < MIN_FREE_GB + 10:
        raise RuntimeError(f'free space {free_gb():.1f} GB too low to start')
    log(f'=== arm {arm}: clone {c} L={L}MiB {info["workload"]} build {info["build"]}; free {free_gb():.1f} GB')
    conf = make_conf(c, L, d)
    info['pid'] = start_node(c, conf, d)
    kss = ['ks1', 'ks2', 'ks3', 'ks4'] if even else ['ks1']
    for ks in kss:   # R5: create each keyspace with a 100-row write before the timed run
        sh(stress_cmd(c, ks, 100, 4) + f' > {d}/stress-create-{ks}.out 2>&1', timeout=300, check=True)
    jmx = subprocess.Popen(
        ['java', '-cp', JMXCP, 'Jmx', str(JMXP), 'poll', '1000', '100000', d + '/jmx.stop',
         'org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize', 'Value',
         'org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation', 'Count',
         'java.lang:type=Memory', 'HeapMemoryUsage',
         'java.lang:type=MemoryPool,name=G1 Old Gen', 'Usage',
         'java.lang:type=MemoryPool,name=G1 Old Gen', 'CollectionUsage'],
        stdout=open(d + '/jmx.csv', 'w'), stderr=open(d + '/jmx.err', 'w'), start_new_session=True)
    CHILDREN.append(jmx)
    time.sleep(5)
    info['syslog_offset'] = os.path.getsize(d + '/system.log')
    procs = []
    info['stress_start_ms'] = int(time.time() * 1000)
    if never:
        specs = [('ks1', 1000000 // SCALE, 64, '-errors ignore')]
    elif even:
        specs = [(ks, 1000000 // SCALE, 16, '') for ks in kss]
    else:
        specs = [('ks1', 4000000 // SCALE, 64, '')]
    info['scale'] = SCALE
    for ks, n, t, extra in specs:
        cmd = stress_cmd(c, ks, n, t, extra)
        log('+ ' + cmd)
        p = subprocess.Popen(cmd + f' > {d}/stress-{ks}.out 2>&1', shell=True, start_new_session=True)
        procs.append(p); CHILDREN.append(p)
    limit = (300 // SCALE if SCALE > 1 else 300) if never else 1800
    stopped_by_limit = False
    while any(p.poll() is None for p in procs):
        time.sleep(2)
        el = time.time() - info['stress_start_ms'] / 1000
        if free_gb() < MIN_FREE_GB:
            log(f'DISK GUARD: free {free_gb():.1f} GB < {MIN_FREE_GB}; stopping stress')
            info['disk_guard'] = True
            break
        if el > limit:
            stopped_by_limit = True
            break
        if not daemons():
            log('node died during stress')
            info['node_died'] = True
            break
    for p in procs:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGKILL)
    info['stress_end_ms'] = int(time.time() * 1000)
    info['stress_stopped_by_limit'] = stopped_by_limit
    info['stress_rc'] = [p.wait() for p in procs]
    log(f'stress ended after {(info["stress_end_ms"] - info["stress_start_ms"]) / 1000:.0f} s rc={info["stress_rc"]} limit={stopped_by_limit}')
    if not never and daemons():
        time.sleep(30)
    sh(f'{c}/bin/nodetool -h 127.0.0.1 -p {JMXP} tablestats {" ".join(kss)} > {d}/tablestats.txt 2>&1; true', timeout=180, check=False)
    sh(f'{c}/bin/nodetool -h 127.0.0.1 -p {JMXP} tpstats > {d}/tpstats.txt 2>&1; true', timeout=120, check=False)
    sh(f'du -sb {NODE}/data {NODE}/commitlog > {d}/du.txt; true', check=False)
    info['syslog_end_offset'] = os.path.getsize(d + '/system.log')   # flushes after this (DRAIN at stop) are not readings
    open(d + '/jmx.stop', 'w').close()
    time.sleep(2)
    left = stop_all(c)
    info['left_after_stop'] = len(left)
    _, fl = sh(f'tail -c +{info["syslog_offset"] + 1} {d}/system.log | head -c {info["syslog_end_offset"] - info["syslog_offset"]} | grep -E "Flushing largest|Enqueuing flush" > {d}/flushes.txt; wc -l < {d}/flushes.txt', check=False)
    sh(f'grep -c "^ERROR" {d}/system.log; grep -m5 -E "^ERROR|java.lang.OutOfMemoryError" {d}/system.log; true', check=False)
    json.dump(info, open(d + '/arm.json', 'w'), indent=1)
    sh(f'rm -rf {NODE}/data {NODE}/commitlog {NODE}/hints', check=False)
    log(f'=== arm {arm} done; free {free_gb():.1f} GB')


def main():
    if ARMS == ['down']:
        stop_all()
        return
    os.makedirs(JMXCP, exist_ok=True)
    if not os.path.exists(JMXCP + '/Jmx.class'):
        sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    if daemons():
        sys.exit('a cassandra-lrt node is already running')
    for arm in ARMS:
        try:
            run_arm(arm)
        except Exception as e:
            log(f'ARM {arm} FAILED: {e}')
            stop_all()
            sys.exit(1)
    log('all arms done')


if __name__ == '__main__':
    try:
        main()
    finally:
        if my_java():
            stop_all()
