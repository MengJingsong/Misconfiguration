#!/usr/bin/env python3
"""Stage 4, cluster tier (B3, amended 2026-10-28) for the four SAI / SASI index-structure constant cases
(block_size-add-blockindex, block_size-writeposting-blocksize, block_packed_max_block_size-checkblocksize-blocksize, tokens_per_block-add-pos; all --autonomous).
The same file is in each case's harness folder; the case is taken from the folder name (or CASE=<key>).

usage: cluster-run.py seed <rows>        build the seed data directory for this case's table (stock build, rows loaded, one flushed/compacted sstable)
       cluster-run.py arm <label>        run one arm (build + seed + yaml extras), see ARMS
       cluster-run.py all                seeds (if missing), then every arm in order, then `analyze`
       cluster-run.py analyze            summary.txt with EXPECTED lines from the raw files of every finished arm
       cluster-run.py down               stop any node this script started

Layout on the measured node (all local disk): builds ~/s4-b34/<build> (base, v-*); seeds ~/s4-b34/seeds/<kind>-<rows>; per-case work ~/s4-b34/cl/<case>/;
logs ~/s4-b34/logs/<case>/cluster/<label>/. One node (127.0.0.1) at a time, started with `bin/cassandra -f` (Byteman ledger on stdout), stopped with
`nodetool stopdaemon` (kill -9 after 120 s). Every arm: restore the seed, start, CREATE INDEX (initial build), wait, measure, nodetool rebuild_index
(repeat), measure, verify queries, stop. Nothing is written outside ~ on local disk.
"""
import glob, json, os, random, re, shutil, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
HARNESS = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.basename(HARNESS)
KEY = os.environ.get('CASE') or {
    'block_size-add-blockindex--autonomous': 'blockindex',
    'block_size-writeposting-blocksize--autonomous': 'postings',
    'block_packed_max_block_size-checkblocksize-blocksize--autonomous': 'maxblock',
    'tokens_per_block-add-pos--autonomous': 'tpb'}[FOLDER]
W = HOME + '/s4-b34'
# the seed data directories carry their cluster name (system.local): one name per kind, shared by the cases (the first SAI case created the SAI seeds as 'stage4-blockindex')
CLUSTER_NAME = 'stage4-tpb' if KEY == 'tpb' else 'stage4-blockindex'
SEEDS = W + '/seeds'
CASEDIR = f'{W}/cl/{KEY}'
LOGROOT = f'{W}/logs/{KEY}/cluster'

# (label, build dir under ~/s4-b34, rows, extras)  extras: seg=<MiB> for sai_options.segment_write_buffer_size; opt=<MiB> for the SASI option
SAI_HEAP = {'blockindex': '4G', 'postings': '2G', 'maxblock': '4G'}
ARMS = {
    'blockindex': [('A-3M', 'base', 3000000, {}), ('B-num64', 'v-num64', 3000000, {}), ('C-num1m', 'v-num1m', 3000000, {}),
                   ('A-750k', 'base', 750000, {}), ('A2-3M', 'base', 3000000, {}), ('ctl-seg16', 'base', 3000000, {'seg': 16})],
    'postings': [('P128-3M', 'base', 3000000, {}), ('P32-3M', 'v-post32', 3000000, {}), ('P512-3M', 'v-post512', 3000000, {}),
                 ('P128-750k', 'base', 750000, {}), ('P128b-3M', 'base', 3000000, {}), ('ctl-seg16', 'base', 3000000, {'seg': 16})],
    'maxblock': [('S-750k', 'base', 750000, {}), ('S-1500k', 'base', 1500000, {}), ('S-3M', 'base', 3000000, {}),
                 ('M1m-3M', 'v-max1m', 3000000, {}), ('M8k-750k', 'v-max8k', 750000, {}), ('ctl-seg16', 'base', 3000000, {'seg': 16})],
    'tpb': [('S-1M', 'base', 1000000, {'opt': 1024}), ('S-500k', 'base', 500000, {'opt': 1024}), ('T124-1M', 'v-tpb124', 1000000, {'opt': 1024}),
            ('T124-500k', 'v-tpb124', 500000, {'opt': 1024}), ('ctl-opt16', 'base', 1000000, {'opt': 16})],
}[KEY]
if os.environ.get('SHAKE_ROWS'):   # instrument check only (disclosed in the results file), never a reading
    ARMS = ARMS + [('shake', os.environ.get('SHAKE_BUILD', 'base'), int(os.environ['SHAKE_ROWS']), {})]
KIND = 'sasi' if KEY == 'tpb' else 'sai'
HEAP = '1G' if KEY == 'tpb' else SAI_HEAP[KEY]
BYTEMAN = W + '/base/build/lib/jars/byteman-4.0.20.jar'

cmd = sys.argv[1] if len(sys.argv) > 1 else ''
arg = sys.argv[2] if len(sys.argv) > 2 else ''
os.makedirs(LOGROOT, exist_ok=True)
SUMMARY = open(f'{LOGROOT}/summary.txt', 'a')
SESSION = open(f'{LOGROOT}/session.log', 'a')


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(c, timeout=1800, check=True, env=None, cwd=None, quiet=False):
    log('+ ' + c)
    r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {c}\n{out[-1200:]}')
    return r.returncode, out


def daemons():
    _, o = sh("ps -eo comm,args | awk '$1==\"java\" && /CassandraDaemon/' || true", check=False, quiet=True)
    return o.strip()


PIDFILE = CASEDIR + '/cassandra.pid'


def pid():
    try:
        p = int(open(PIDFILE).read().strip())
        return p if 'CassandraDaemon' in open(f'/proc/{p}/cmdline').read() else None
    except (OSError, ValueError):
        return None


class Fail(Exception):
    pass


def stop_node(cl):
    p = pid()
    if p is None:
        return
    sh(f'{cl}/bin/nodetool stopdaemon', check=False, timeout=120)
    for _ in range(120):
        if pid() is None:
            return
        time.sleep(1)
    log(f'kill -9 {p}'); subprocess.run(['kill', '-9', str(p)]); time.sleep(2)


def make_yaml(extra):
    nd = CASEDIR + '/node'
    for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
        os.makedirs(f'{nd}/{d}', exist_ok=True)
    return nd, extra


def write_conf(cl, extra):
    nd = CASEDIR + '/node'
    for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
        os.makedirs(f'{nd}/{d}', exist_ok=True)
    shutil.rmtree(nd + '/conf', ignore_errors=True)
    shutil.copytree(cl + '/conf', nd + '/conf')
    y = open(f'{cl}/conf/cassandra.yaml').read()
    add = [f'cluster_name: {CLUSTER_NAME}', f'data_file_directories: [{nd}/data]', f'commitlog_directory: {nd}/commitlog',
           f'hints_directory: {nd}/hints', f'saved_caches_directory: {nd}/saved_caches', f'cdc_raw_directory: {nd}/cdc_raw',
           'autocompaction_on_startup_enabled: false', 'native_transport_timeout: 300s', 'read_request_timeout: 300s', 'range_request_timeout: 300s',
           'write_request_timeout: 60s'] + extra
    keys = {l.split(':')[0] for l in add if not l.startswith(' ')}
    out, skip = [], False
    for l in y.splitlines():
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in keys
            if skip:
                continue
        elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
            continue
        else:
            skip = False
        out.append(l)
    open(nd + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 lines ----\n' + '\n'.join(add) + '\n')
    return nd, add


LEDGER = {
    'blockindex': 'ledger-bitpack.btm', 'maxblock': 'ledger-bitpack.btm', 'postings': 'ledger-postings.btm', 'tpb': None}


def start_node(cl, extra, heap, ledger=True):
    nd, add = write_conf(cl, extra)
    note('YAML tail: ' + ' ; '.join(add).replace('\n', ' '))
    env = dict(os.environ, CASSANDRA_CONF=nd + '/conf', CASSANDRA_LOG_DIR=nd + '/logs', MAX_HEAP_SIZE=heap)
    env.pop('HEAP_NEWSIZE', None); env.pop('JVM_EXTRA_OPTS', None)
    btm = LEDGER.get(KEY)
    if ledger and btm:
        env['JVM_EXTRA_OPTS'] = f'-javaagent:{BYTEMAN}=script:{HARNESS}/{btm}'
    if os.path.exists(PIDFILE):
        os.remove(PIDFILE)
    out = open(nd + '/stdout.txt', 'w')
    pr = subprocess.Popen([cl + '/bin/cassandra', '-f'], stdout=out, stderr=subprocess.STDOUT, env=env, cwd=cl, start_new_session=True)
    open(PIDFILE, 'w').write(str(pr.pid))   # `-f` execs the JVM, so the child pid is the JVM pid (checked by pid(): the cmdline must name CassandraDaemon)
    return nd


def wait_up(cl, nd, timeout=300):
    t0 = time.time()
    time.sleep(5)
    while time.time() - t0 < timeout:
        if pid() is None and time.time() - t0 > 15:
            raise Fail('node died during start; ' + open(nd + '/stdout.txt').read()[-600:])
        _, st = sh(f'{cl}/bin/nodetool statusbinary', check=False, quiet=True)
        _, ns = sh(f'{cl}/bin/nodetool status', check=False, quiet=True)
        if re.search(r'^running\s*$', st, re.M) and re.search(r'^UN\s', ns, re.M):
            note(f'node up after {time.time() - t0:.0f} s'); return
        time.sleep(3)
    raise Fail('node not up')


def driver(cl):
    lib = os.path.join(cl, 'lib')
    z = max(glob.glob(os.path.join(lib, 'cassandra-driver-internal-only-*.zip')))
    ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
    sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
    for p in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
        zz = glob.glob(os.path.join(lib, p + '*.zip'))
        if zz:
            sys.path.insert(0, max(zz))


def cql(cl, stmt, timeout=1800):
    return sh(f"{cl}/bin/cqlsh --request-timeout={timeout} -e \"{stmt}\"", timeout=timeout + 60, check=False)


def session(cl):
    driver(cl)
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra import ConsistencyLevel
    prof = ExecutionProfile(consistency_level=ConsistencyLevel.ONE, request_timeout=600)
    c = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    return c, c.connect()


# ---------------------------------------------------------------- seed

_W = {}


def _winit(cl, ins, kind):
  try:
    _winit2(cl, ins, kind)
  except BaseException:
    import traceback
    open(CASEDIR + '/worker-error.txt', 'a').write(traceback.format_exc())
    raise


def _winit2(cl, ins, kind):
    driver(cl)
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra import ConsistencyLevel
    prof = ExecutionProfile(consistency_level=ConsistencyLevel.ONE, request_timeout=600)
    c = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    _W['s'] = c.connect(); _W['ps'] = _W['s'].prepare(ins); _W['kind'] = kind


def _wload(a):
    from cassandra.concurrent import execute_concurrent_with_args
    st, n = a
    rnd = random.Random(20261028 + st)
    if _W['kind'] == 'sai':
        batch = [((st + i) // 100, (st + i) % 100, rnd.randrange(1000000), 'w%d' % ((st + i) % 100)) for i in range(n)]
    else:
        batch = [(st + i, 'q', rnd.randbytes(8).hex()) for i in range(n)]
    execute_concurrent_with_args(_W['s'], _W['ps'], batch, concurrency=64, raise_on_first_error=True)
    return n

def seed(rows):
    cl = W + '/base'
    sd = f'{SEEDS}/{KIND}-{rows}'
    if os.path.isdir(sd):
        note(f'SEED {sd} exists'); return
    if daemons():
        raise Fail('a CassandraDaemon is running')
    os.makedirs(SEEDS, exist_ok=True)
    shutil.rmtree(CASEDIR + '/node', ignore_errors=True)
    nd = start_node(cl, ['memtable_heap_space: 2048MiB', 'memtable_offheap_space: 2048MiB'], '8G', ledger=False)
    try:
        wait_up(cl, nd)
        if KIND == 'sai':
            cql(cl, "CREATE KEYSPACE sai WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE sai.t (pk int, ck int, v int, txt text, PRIMARY KEY (pk, ck)) WITH compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'};")
            ins, tbl = 'INSERT INTO sai.t (pk, ck, v, txt) VALUES (?, ?, ?, ?)', 'sai t'
        else:
            cql(cl, "CREATE KEYSPACE sasi WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE sasi.t (pk bigint PRIMARY KEY, c text, u text) WITH compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'};")
            ins, tbl = 'INSERT INTO sasi.t (pk, c, u) VALUES (?, ?, ?)', 'sasi t'
        sh(f'{cl}/bin/nodetool disableautocompaction {tbl}')
        # 8 worker processes, each with its own driver session (one Python process loads only about 4k rows/s); chunk i is rows [i*B, (i+1)*B) with its own rng
        import concurrent.futures as cf
        t0 = time.time(); B = 20000
        starts = list(range(0, rows, B))
        done = 0
        with cf.ProcessPoolExecutor(max_workers=8, initializer=_winit, initargs=(cl, ins, KIND)) as ex:
            for k, n in enumerate(ex.map(_wload, [(st, min(B, rows - st)) for st in starts])):
                done += n
                if (k + 1) % 25 == 0:
                    note(f'SEED rows {done} in {time.time() - t0:.0f} s')
        note(f'SEED loaded {done} rows in {time.time() - t0:.0f} s')
        sh(f'{cl}/bin/nodetool flush {tbl}')
        sh(f'{cl}/bin/nodetool compact {tbl}', check=False)
        sh(f'{cl}/bin/nodetool drain', check=False)
        _, ls = sh(f'ls -l {CASEDIR}/node/data/{tbl.split()[0]}/t-*/*-Data.db', check=False)
        n = len(glob.glob(f'{CASEDIR}/node/data/{tbl.split()[0]}/t-*/*-Data.db'))
        note('SEED sstables: ' + ls.strip().replace('\n', ' | '))
        if n != 1:
            raise Fail(f'expected one sstable, found {n}')
    finally:
        stop_node(cl)
    time.sleep(2)
    _, du = sh(f'du -sb {CASEDIR}/node/data | cut -f1')
    sh(f'cp -a {CASEDIR}/node/data {sd}')
    note(f'SEED copied to {sd}; du {du.strip()} B; daemons left: {daemons() or "none"}')


# ---------------------------------------------------------------- samplers
def start_sampler(cl, D, tag):
    sh(f'mkdir -p {W}/samplercls && javac -d {W}/samplercls {HARNESS}/Sampler.java', quiet=True)
    csv = f'{D}/gauges-{tag}.csv'
    open(csv, 'w').close()
    samp = subprocess.Popen(f'java -cp {W}/samplercls Sampler 7199 {csv} 500', shell=True, cwd=cl, stdout=open(D + '/sampler.out', 'a'), stderr=subprocess.STDOUT)
    rss = open(f'{D}/rss-{tag}.csv', 'w'); rss.write('ms,rss_kb\n')
    stop = threading.Event()
    p = pid()

    def loop():
        while not stop.is_set():
            try:
                m = re.search(r'VmRSS:\s+(\d+)', open(f'/proc/{p}/status').read())
                rss.write(f'{int(time.time() * 1000)},{m.group(1)}\n'); rss.flush()
            except OSError:
                pass
            stop.wait(1.0)
    th = threading.Thread(target=loop, daemon=True); th.start()
    return csv, samp, stop, th, rss


def stop_sampler(s):
    csv, samp, stop, th, rss = s
    stop.set(); th.join(3); samp.terminate(); rss.close()


def peaks(csv):
    rows = [l.split(',') for l in open(csv).read().splitlines()[1:] if l.count(',') == 5]
    if not rows:
        return dict(samples=0)
    used = [int(r[1]) for r in rows]; lim = [int(r[2]) for r in rows]; heap = [int(r[4]) for r in rows]
    return dict(samples=len(rows), seg_used_peak=max(used), seg_limits=sorted(set(lim)), heap_used_peak=max(heap))


def listing(table_dir, D, tag):
    out = []
    for f in sorted(glob.glob(table_dir + '/*')):
        if os.path.isfile(f) and ('SAI' in f or 'SI_' in f):
            out.append((os.path.basename(f), os.path.getsize(f)))
    open(f'{D}/files-{tag}.txt', 'w').write('\n'.join(f'{n}\t{s}' for n, s in out) + '\n')
    return out


# ---------------------------------------------------------------- arm
def sai_arm(label, build, rows, ex):
    cl = f'{W}/{build}'
    D = f'{LOGROOT}/{label}'
    shutil.rmtree(D, ignore_errors=True); os.makedirs(D)
    sd = f'{SEEDS}/sai-{rows}'
    if not os.path.isdir(sd):
        raise Fail(f'no seed {sd}')
    if daemons():
        raise Fail('a CassandraDaemon is running')
    shutil.rmtree(CASEDIR + '/node', ignore_errors=True)
    os.makedirs(CASEDIR + '/node', exist_ok=True)
    sh(f'cp -a {sd} {CASEDIR}/node/data')
    extra = []
    if 'seg' in ex:
        extra = ['sai_options:', f'  segment_write_buffer_size: {ex["seg"]}MiB']
    note(f'ARM {label} start {time.strftime("%F %T %Z")}: build {build} ({cl}), rows {rows}, extras {ex}, heap {HEAP}')
    _, jc = sh(f'ls -l {cl}/build/apache-cassandra*.jar; md5sum {cl}/build/apache-cassandra*.jar', check=False)
    open(D + '/jar.txt', 'w').write(jc)
    nd = start_node(cl, extra, HEAP)
    try:
        wait_up(cl, nd)
        s = start_sampler(cl, D, label)
        time.sleep(6)
        tdir = glob.glob(f'{nd}/data/sai/t-*')[0]
        note(f'ARM {label}: node up, sampler started; before index: {len(listing(tdir, D, label + "-before"))} SAI files')
        off_dbg = os.path.getsize(f'{nd}/logs/debug.log') if os.path.exists(f'{nd}/logs/debug.log') else 0
        t0 = time.time()
        ok = True
        for stmt in ("CREATE INDEX v_idx ON sai.t (v) USING 'sai';", "CREATE INDEX txt_idx ON sai.t (txt) USING 'sai';"):
            rc, o = cql(cl, stmt, timeout=900)
            note(f'CREATE INDEX rc={rc} after {time.time() - t0:.0f} s: {stmt[13:30]} {o.strip()[-160:]!r}')
        built = False
        t1 = time.time()
        while time.time() - t1 < 1500:
            _, q = sh(f'{cl}/bin/cqlsh -e "SELECT index_name FROM system.\\"IndexInfo\\";"', check=False, quiet=True)
            _, cs = sh(f'{cl}/bin/nodetool compactionstats', check=False, quiet=True)
            if 'v_idx' in q and 'txt_idx' in q and not re.search(r'Secondary index build|Index build|IndexBuild', cs, re.I):
                built = True; break
            time.sleep(3)
        note(f'INDEX build {"complete" if built else "NOT complete"} after {time.time() - t0:.0f} s (create + wait)')
        time.sleep(3)
        fl1 = listing(tdir, D, label + '-after-build')
        note(f'FILES after build: {len(fl1)} SAI files, {sum(x[1] for x in fl1)} bytes')
        t2 = time.time()
        for ix in ('v_idx', 'txt_idx'):
            rc2, o2 = sh(f'{cl}/bin/nodetool rebuild_index sai t {ix}', check=False, timeout=1800)
            note(f'REBUILD {ix} rc={rc2} in {time.time() - t2:.0f} s: {o2.strip()[-120:]!r}')
        time.sleep(5)
        fl2 = listing(tdir, D, label + '-after-rebuild')
        note(f'FILES after rebuild: {len(fl2)} SAI files, {sum(x[1] for x in fl2)} bytes')
        # verify queries through the driver
        vres = 'not run'
        try:
            c, sess = session(cl)
            n_v = sess.execute('SELECT count(*) FROM sai.t WHERE v >= 0').one()[0]
            n_t = [sess.execute("SELECT count(*) FROM sai.t WHERE txt = %s", ('w%d' % k,)).one()[0] for k in (0, 7, 99)]
            c.shutdown()
            vres = f'count(v>=0)={n_v} expected {rows}; count(txt=w0,w7,w99)={n_t} expected {rows // 100} each'
            note('VERIFY ' + vres + (' OK' if n_v == rows and n_t == [rows // 100] * 3 else ' MISMATCH'))
        except Exception as e:
            note(f'VERIFY failed: {type(e).__name__}: {str(e)[:200]}')
        stop_sampler(s)
        pk = peaks(s[0])
        note(f'GAUGES {label}: ' + json.dumps(pk))
        dl = open(f'{nd}/logs/debug.log', errors='replace').read()[off_dbg:]
        open(D + '/flush-lines.txt', 'w').write('\n'.join(l for l in dl.splitlines() if 'Global limit of' in l or 'Memory limiter using' in l) + '\n')   # analysis counts only the 'Global limit' lines
        sl = open(f'{nd}/logs/system.log', errors='replace').read()
        open(D + '/errors.txt', 'w').write('\n'.join(l for l in sl.splitlines() if l.startswith(('ERROR', 'WARN')))[-20000:] + '\n')
        shutil.copy(nd + '/stdout.txt', D + '/stdout-trace.txt')
        led = [l for l in open(D + '/stdout-trace.txt', errors='replace') if l.startswith(('BPW ', 'PW ', 'CHK '))]
        open(D + '/ledger.txt', 'w').write(''.join(led))
        note(f'LEDGER {label}: {len(led)} lines; lengths ' + json.dumps(sorted({l.split()[1] for l in led if l.startswith(("BPW", "PW"))}, key=int)) if led else f'LEDGER {label}: 0 lines')
        note(f'ERROR lines in system.log: {len(re.findall(r"^ERROR", sl, re.M))}; memory-limit flush DEBUG lines in this arm: {len(re.findall("Global limit of", dl))}')
    finally:
        stop_node(cl)
        time.sleep(2)
    note(f'ARM {label} STOPPED: daemons left: {daemons() or "none"}')


def sasi_arm(label, build, rows, ex):
    cl = f'{W}/{build}'
    D = f'{LOGROOT}/{label}'
    shutil.rmtree(D, ignore_errors=True); os.makedirs(D)
    sd = f'{SEEDS}/sasi-{rows}'
    if not os.path.isdir(sd):
        raise Fail(f'no seed {sd}')
    if daemons():
        raise Fail('a CassandraDaemon is running')
    shutil.rmtree(CASEDIR + '/node', ignore_errors=True)
    os.makedirs(CASEDIR + '/node', exist_ok=True)
    sh(f'cp -a {sd} {CASEDIR}/node/data')
    note(f'ARM {label} start {time.strftime("%F %T %Z")}: build {build} ({cl}), rows {rows}, extras {ex}, heap {HEAP}')
    _, jc = sh(f'md5sum {cl}/build/apache-cassandra*.jar', check=False)
    open(D + '/jar.txt', 'w').write(jc)
    nd = start_node(cl, ['sasi_indexes_enabled: true'], HEAP, ledger=False)
    opt = ex.get('opt', 1024)
    try:
        wait_up(cl, nd)
        tdir = glob.glob(f'{nd}/data/sasi/t-*')[0]
        off_dbg = os.path.getsize(f'{nd}/logs/debug.log') if os.path.exists(f'{nd}/logs/debug.log') else 0
        for col, mode in (('c', 'CONTAINS'), ('u', 'PREFIX')):
            ix = col + '_idx'
            s = start_sampler(cl, D, f'{label}-{col}')
            seen = set(); mx = [0]; stop = threading.Event()

            def watch():
                while not stop.is_set():
                    for f in os.listdir(tdir):
                        if 'SI_' in f:
                            seen.add(f)
                    stop.wait(0.05)
            th = threading.Thread(target=watch, daemon=True); th.start()
            t0 = time.time()
            stmt = (f"CREATE CUSTOM INDEX {ix} ON sasi.t ({col}) USING 'org.apache.cassandra.index.sasi.SASIIndex' "
                    f"WITH OPTIONS = {{'mode': '{mode}', 'max_compaction_flush_memory_in_mb': '{opt}'}};")
            rc, o = cql(cl, stmt, timeout=900)
            note(f'CREATE {ix} ({mode}, option {opt}) rc={rc} after {time.time() - t0:.0f} s: {o.strip()[-160:]!r}')
            built = False
            t1 = time.time()
            while time.time() - t1 < 1500:
                _, q = sh(f'{cl}/bin/cqlsh -e "SELECT index_name FROM system.\\"IndexInfo\\";"', check=False, quiet=True)
                _, cs = sh(f'{cl}/bin/nodetool compactionstats', check=False, quiet=True)
                if ix in q and not re.search(r'Secondary index build|Index build|IndexBuild', cs, re.I):
                    built = True; break
                time.sleep(3)
            time.sleep(3)
            stop.set(); th.join(2)
            stop_sampler(s)
            fl = listing(tdir, D, f'{label}-{col}')
            segs = sorted(x for x in seen)
            note(f'INDEX {ix} build {"complete" if built else "NOT complete"} after {time.time() - t0:.0f} s; files {[(n, sz) for n, sz in fl if ix in n or "SI_" in n]}; temp-segment files seen {len(segs)}: {segs[:12]}')
            note(f'GAUGES {label} {col}: ' + json.dumps(peaks(s[0])))
            # verify
            try:
                c, sess = session(cl)
                if col == 'c':
                    n = sess.execute("SELECT count(*) FROM sasi.t WHERE c LIKE '%q%'").one()[0]
                else:
                    first = sess.execute('SELECT u FROM sasi.t LIMIT 1').one()[0]
                    n = sess.execute("SELECT count(*) FROM sasi.t WHERE u = %s", (first,)).one()[0]
                c.shutdown()
                exp = rows if col == 'c' else 1
                note(f'VERIFY {ix}: count={n} expected {exp}' + (' OK' if n == exp else ' MISMATCH'))
            except Exception as e:
                note(f'VERIFY {ix} failed: {type(e).__name__}: {str(e)[:200]}')
            open(f'{D}/segments-{col}.txt', 'w').write('\n'.join(segs) + '\n')
            if col == 'c':
                cql(cl, 'DROP INDEX sasi.c_idx;', timeout=300)
                time.sleep(3)
        dl = open(f'{nd}/logs/debug.log', errors='replace').read()[off_dbg:]
        sl = open(f'{nd}/logs/system.log', errors='replace').read()
        open(D + '/errors.txt', 'w').write('\n'.join(l for l in sl.splitlines() if l.startswith(('ERROR', 'WARN')))[-20000:] + '\n')
        open(D + '/sasi-debug.txt', 'w').write('\n'.join(l for l in dl.splitlines() if 'SASI' in l or 'sasi' in l)[-30000:] + '\n')
        note(f'ERROR lines in system.log: {len(re.findall(r"^ERROR", sl, re.M))}')
    finally:
        stop_node(cl)
        time.sleep(2)
    note(f'ARM {label} STOPPED: daemons left: {daemons() or "none"}')


def run_arm(label):
    for a in ARMS:
        if a[0] == label:
            (sasi_arm if KIND == 'sasi' else sai_arm)(*a)
            return
    raise Fail('unknown arm ' + label)


def main():
    note(f'CMD {" ".join(sys.argv[1:])} case {KEY} start {time.strftime("%F %T %Z")}; harness md5 ' +
         subprocess.run(f'cd {HARNESS} && md5sum cluster-run.py Sampler.java | cut -c1-12 | tr "\\n" " "', shell=True, capture_output=True, text=True).stdout.strip())
    if cmd == 'seed':
        seed(int(arg))
    elif cmd == 'arm':
        run_arm(arg)
    elif cmd == 'all':
        for rows in sorted({a[2] for a in ARMS}):
            seed(rows)
        for a in ARMS:
            run_arm(a[0])
    elif cmd == 'down':
        stop_node(W + '/base'); note('down: daemons left: ' + (daemons() or 'none'))
    else:
        raise Fail('usage: seed <rows> | arm <label> | all | down')
    note(f'DONE {cmd} {arg}')


try:
    main()
except SystemExit:
    raise
except Exception as e:
    import traceback
    log(traceback.format_exc())
    note(f'FAIL: {type(e).__name__}: {e}')
    try:
        stop_node(W + '/base')
    except Exception:
        pass
    sys.exit(1)
