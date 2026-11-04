#!/usr/bin/env python3
"""Stage 4, cluster tier B3 of segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous (amended 2026-10-27).
usage: cluster-run.py <label>     labels: invalid | seed | run-<MiB> (64, 256, 1024) | down
One node (127.0.0.1), clone CASSANDRA_HOME (default ~/cassandra-run1, unmodified), JMX 7199, MAX_HEAP_SIZE 4G, data and logs on local / under ~/s4b-sai.
seed: loads sai.t (pk bigint, v text of 400 random hex characters), SEED_ROWS rows, on a node with big memtable pools, flushes once, compacts to a
  single sstable, drains, stops, and copies the data directory to ~/s4b-sai/seed-data (no index yet).
run-<MiB>: restores the seed, starts the node with sai_options.segment_write_buffer_size = <MiB>MiB, samples the SAI gauges and heap every 500 ms
  (Sampler.java) and RSS every second, runs CREATE INDEX ... USING 'sai' (the initial build, SSTableIndexWriter path) and then
  `nodetool rebuild_index sai t v_idx` (a repeat of the same path), then stops the node.
invalid: starts a node with 32769MiB and expects it to refuse to start."""
import json, os, random, re, subprocess, sys, threading, time, shutil, glob

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get('SAI_BASE', HOME + '/s4b-sai')
LOGROOT = os.environ.get('SAI_LOGS', HOME + '/s4b-logs/sai/cluster')
SEED = BASE + '/seed-data'
SEED_ROWS = int(os.environ.get('SAI_ROWS', 3200000))
label = sys.argv[1] if len(sys.argv) > 1 else ''
D = f'{LOGROOT}/{label}'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'a')


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=1800, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-4000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1200:]}')
    return r.returncode, out


def daemons():
    _, o = sh("ps -eo comm,args | awk '$1==\"java\" && /CassandraDaemon/' || true", check=False, quiet=True)
    return o.strip()


def pid():
    try:
        p = int(open(BASE + '/cassandra.pid').read().strip())
        return p if 'CassandraDaemon' in open(f'/proc/{p}/cmdline').read() else None
    except (OSError, ValueError):
        return None


def stop_node():
    p = pid()
    if p is None:
        return
    sh('bin/nodetool stopdaemon', check=False, timeout=120)
    for _ in range(120):
        if pid() is None:
            return
        time.sleep(1)
    log(f'kill -9 {p}'); subprocess.run(['kill', '-9', str(p)]); time.sleep(2)


def fail(msg):
    note('FAIL: ' + msg)
    stop_node()
    sys.exit(1)


def make_yaml(extra):
    for d in ('conf', 'logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
        sh(f'mkdir -p {BASE}/{d}', quiet=True)
    sh(f'rm -rf {BASE}/conf && cp -r {C}/conf {BASE}/conf')
    y = open(f'{C}/conf/cassandra.yaml').read()
    add = ['cluster_name: stage4-sai', f'data_file_directories: [{BASE}/data]', f'commitlog_directory: {BASE}/commitlog',
           f'hints_directory: {BASE}/hints', f'saved_caches_directory: {BASE}/saved_caches', f'cdc_raw_directory: {BASE}/cdc_raw',
           'autocompaction_on_startup_enabled: false', 'native_transport_timeout: 120s', 'read_request_timeout: 120s', 'write_request_timeout: 60s'] + extra
    keys = {l.split(':')[0] for l in add if not l.startswith(' ')}
    out = [l for l in y.splitlines() if l.split(':')[0] not in keys or l.startswith((' ', '#', '-'))]
    open(f'{BASE}/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 sai lines ----\n' + '\n'.join(add) + '\n')
    return add


def start_node(extra, heap='4G'):
    add = make_yaml(extra)
    note('YAML tail: ' + ' ; '.join(add).replace('\n', ' '))
    env = dict(os.environ, CASSANDRA_CONF=BASE + '/conf', CASSANDRA_LOG_DIR=BASE + '/logs', MAX_HEAP_SIZE=heap)
    env.pop('HEAP_NEWSIZE', None)
    sh(f'rm -f {BASE}/cassandra.pid; bin/cassandra -p {BASE}/cassandra.pid > {BASE}/stdout.txt 2>&1', env=env)


def wait_up(timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pid() is None:
            fail('node died during start; ' + open(BASE + '/stdout.txt').read()[-600:])
        _, st = sh('bin/nodetool statusbinary', check=False, quiet=True)
        _, ns = sh('bin/nodetool status', check=False, quiet=True)
        if re.search(r'^running\s*$', st, re.M) and re.search(r'^UN\s', ns, re.M):
            note(f'node up after {time.time() - t0:.0f} s'); return
        time.sleep(3)
    fail('node not up')


def driver():
    import glob as g
    lib = os.path.join(C, 'lib')
    z = max(g.glob(os.path.join(lib, 'cassandra-driver-internal-only-*.zip')))
    ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
    sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
    for p in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
        zz = g.glob(os.path.join(lib, p + '*.zip'))
        if zz:
            sys.path.insert(0, max(zz))


def cql(stmt, timeout=1800):
    return sh(f"bin/cqlsh --request-timeout={timeout} -e \"{stmt}\"", timeout=timeout + 60, check=False)


def l_invalid():
    sh(f'rm -rf {BASE}/data/* {BASE}/commitlog/*', check=False)
    start_node(['sai_options:', '  segment_write_buffer_size: 32769MiB'])
    t0 = time.time()
    while pid() is not None and time.time() - t0 < 120:
        time.sleep(1)
    alive = pid() is not None
    out = open(BASE + '/stdout.txt').read()
    msg = 'Invalid value for segment_write_buffer_size'
    note(f'INVALID 32769MiB: alive after {time.time() - t0:.0f} s: {alive}; message in stdout: {msg in out}')
    note('INVALID stdout tail: ' + out[-600:].replace('\n', ' | '))
    if alive:
        stop_node()


def l_seed():
    sh(f'rm -rf {BASE}/data {BASE}/commitlog {SEED}', check=False)
    start_node(['memtable_heap_space: 6144MiB', 'memtable_offheap_space: 6144MiB', 'sai_options:', '  segment_write_buffer_size: 1024MiB'], heap='12G')
    wait_up()
    cql("CREATE KEYSPACE sai WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE sai.t (pk bigint PRIMARY KEY, v text) WITH compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'};")
    sh('bin/nodetool disableautocompaction sai t')
    driver()
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra.concurrent import execute_concurrent_with_args
    from cassandra import ConsistencyLevel
    prof = ExecutionProfile(consistency_level=ConsistencyLevel.ONE, request_timeout=120)
    cl = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = cl.connect()
    ps = s.prepare('INSERT INTO sai.t (pk, v) VALUES (?, ?)')
    rnd = random.Random(7)
    t0 = time.time(); done = 0; B = 20000
    while done < SEED_ROWS:
        rows = [(done + i, rnd.randbytes(200).hex()) for i in range(min(B, SEED_ROWS - done))]
        res = execute_concurrent_with_args(s, ps, rows, concurrency=128, raise_on_first_error=True)
        done += len(rows)
        if done % 400000 == 0:
            note(f'SEED rows {done} in {time.time() - t0:.0f} s')
    cl.shutdown()
    note(f'SEED loaded {done} rows in {time.time() - t0:.0f} s')
    sh('bin/nodetool flush sai t')
    sh('bin/nodetool compact sai t', check=False)
    sh('bin/nodetool drain', check=False)
    _, ls = sh(f'ls -l {BASE}/data/sai/t-*/*-Data.db', check=False)
    note('SEED sstables: ' + ls.strip().replace('\n', ' | '))
    n = len(glob.glob(f'{BASE}/data/sai/t-*/*-Data.db'))
    stop_node()
    _, du = sh(f'du -sb {BASE}/data | cut -f1')
    sh(f'cp -a {BASE}/data {SEED}')
    note(f'SEED copied to {SEED}; data du {du.strip()} B; Data.db count {n}')
    if n != 1:
        fail(f'expected one sstable, found {n}')


def l_run(mib):
    if not os.path.isdir(SEED):
        fail('no seed')
    if daemons():
        fail('a CassandraDaemon is running')
    sh(f'rm -rf {BASE}/data {BASE}/commitlog {BASE}/hints && cp -a {SEED} {BASE}/data')
    off_dbg = os.path.getsize(f'{BASE}/logs/debug.log') if os.path.exists(f'{BASE}/logs/debug.log') else 0
    off_sys = os.path.getsize(f'{BASE}/logs/system.log') if os.path.exists(f'{BASE}/logs/system.log') else 0
    start_node(['sai_options:', f'  segment_write_buffer_size: {mib}MiB']); wait_up()
    p = pid()
    sh('mkdir -p ' + BASE + '/samplercls && javac -d ' + BASE + '/samplercls ' + HARNESS + '/Sampler.java')
    csv = D + f'/gauges-{mib}.csv'
    open(csv, 'w').close()
    samp = subprocess.Popen(f'java -cp {BASE}/samplercls Sampler 7199 {csv} 500', shell=True, cwd=C, stdout=open(D + '/sampler.out', 'a'), stderr=subprocess.STDOUT)
    rss = open(D + f'/rss-{mib}.csv', 'w'); rss.write('ms,rss_kb\n')
    stop = threading.Event()

    def rss_loop():
        while not stop.is_set():
            try:
                m = re.search(r'VmRSS:\s+(\d+)', open(f'/proc/{p}/status').read())
                rss.write(f'{int(time.time() * 1000)},{m.group(1)}\n'); rss.flush()
            except OSError:
                pass
            stop.wait(1.0)
    th = threading.Thread(target=rss_loop, daemon=True); th.start()
    time.sleep(6)
    note(f'RUN {mib}MiB: node up, sampler started; sstables {sorted(os.path.getsize(f) for f in glob.glob(BASE + "/data/sai/t-*/*-Data.db"))}')
    t0 = time.time()
    rc, o = cql("CREATE INDEX v_idx ON sai.t (v) USING 'sai';", timeout=900)
    note(f'CREATE INDEX rc={rc} after {time.time() - t0:.0f} s: {o.strip()[-200:]!r}')
    built = False
    t1 = time.time()
    while time.time() - t1 < 1800:
        _, q = sh('bin/cqlsh -e "SELECT index_name FROM system.\\"IndexInfo\\";"', check=False, quiet=True)
        _, cs = sh('bin/nodetool compactionstats', check=False, quiet=True)
        if 'v_idx' in q and not re.search(r'Secondary index build|Index build|IndexBuild', cs, re.I):
            built = True; break
        time.sleep(3)
    note(f'INDEX build {"complete" if built else "NOT complete"} after {time.time() - t0:.0f} s (create + wait)')
    time.sleep(3)
    t2 = time.time()
    rc2, o2 = sh('bin/nodetool rebuild_index sai t v_idx', check=False, timeout=1800)
    note(f'REBUILD rc={rc2} in {time.time() - t2:.0f} s: {o2.strip()[-200:]!r}')
    time.sleep(5)
    _, cnt = cql("SELECT count(*) FROM sai.t WHERE v > 'ff';", timeout=300)
    note('QUERY sanity (count v > ff): ' + cnt.strip().replace('\n', ' | ')[-160:])
    stop.set(); th.join(3); samp.terminate(); rss.close()
    dl = open(f'{BASE}/logs/debug.log', errors='replace').read()[off_dbg:]
    sl = open(f'{BASE}/logs/system.log', errors='replace').read()[off_sys:]
    flushes = re.findall(r'Global limit of ([\d\.]+ ?\w+) and minimum flush size of ([\d\.]+ ?\w+) exceeded\. Current builder usage is ([\d\.]+ ?\w+) for (\d+) cells\. Global Usage is ([\d\.]+ ?\w+)', dl)
    open(D + f'/flush-lines-{mib}.txt', 'w').write('\n'.join(l for l in dl.splitlines() if 'Global limit of' in l or 'Memory limiter using' in l) + '\n')
    open(D + f'/sai-log-{mib}.txt', 'w').write('\n'.join(l for l in (sl + dl).splitlines() if 'Storage Attached' in l or 'segment' in l.lower() and 'index' in l.lower())[-60000:] + '\n')
    rows = [l.split(',') for l in open(csv).read().splitlines()[1:] if l.count(',') == 5]
    used = [int(r[1]) for r in rows]; lim = [int(r[2]) for r in rows]; heap = [int(r[4]) for r in rows]
    note(f'GAUGES {mib}MiB: samples {len(rows)}; limit gauge values {sorted(set(lim))}; peak used {max(used)} B = {max(used) / 1048576:.1f} MiB; peak heap {max(heap) / 1048576:.0f} MiB; '
         f'memory-limit flush DEBUG lines {len(flushes)}; ERROR lines {len(re.findall(r"^ERROR", sl, re.M))}')
    stop_node()
    note(f'STOPPED: daemons left: {daemons() or "none"}')


def main():
    note(f'LABEL {label} start {time.strftime("%F %T %Z")}; harness md5 ' + subprocess.run(f'cd {HARNESS} && md5sum cluster-run.py Sampler.java | cut -c1-12 | tr "\\n" " "', shell=True, capture_output=True, text=True).stdout.strip())
    if label == 'invalid': l_invalid()
    elif label == 'seed': l_seed()
    elif label.startswith('run-'): l_run(label[4:])
    elif label == 'down': stop_node(); note('down: daemons left: ' + (daemons() or 'none'))
    else: fail('unknown label')
    note(f'DONE {label}')


try:
    main()
except SystemExit:
    raise
except Exception as e:
    import traceback
    log(traceback.format_exc()); fail(f'{type(e).__name__}: {e}')
