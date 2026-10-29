#!/usr/bin/env python3
"""Stage 4, cluster tier (B3 + B3i) of max_unsigned_short-validateindexedvalue-value_remaining--autonomous.
usage: cluster-run.py <run-name> [main|quick]
  life 1 (memtable_offheap_space 512 MiB): boundary precheck (5 inserts at S=65534 accepted, 5 at S=65535 rejected; else stop), then arms
         n1000, n4000, n16000 (S=65534), s65535 (N=200, all rejected), noidx4000 (no index, N=4000), s100 (S=100, N=655,340);
  life 2 (256 MiB): arm p256_n16000 (S=65534, N=16000).
  quick: precheck + n1000 (N=300) + s65535 (N=50) only; a shakedown, not a reading.
  Address 127.0.2.1, JMX 7270, native 9042. Node data on tmpfs /dev/shm/s4-b2/node.
Output: ~/s4-b2-logs/<run>/cluster/ (summary.txt with EXPECTED lines, arms.jsonl, samples-<arm>.csv, session.log, system.log per life).
Exit 1 if a set-up or first-trigger check fails; the node is stopped on any exit."""
import glob, json, os, re, shutil, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b2/c')
HARNESS = os.path.dirname(os.path.abspath(__file__))
W = '/dev/shm/s4-b2/node'
ADDR, JMX = '127.0.2.1', 7270
RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'main'
LOGS = f'{HOME}/s4-b2-logs/{RUN}/cluster'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a')
ARMS = open(LOGS + '/arms.jsonl', 'a')
EXP = {'yes': 0, 'no': 0}
PID = [None]
MSG = 'Cannot index value of size 65535 for index'
MIB = 1 << 20


def log(s):
    SESSION.write(f'[{time.strftime("%F %T")}] {s}\n'); SESSION.flush()


def note(s):
    print(s, flush=True); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=900, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    try:
        r = subprocess.run(['bash', '-c', 'ulimit -n 100000; ' + cmd], capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        log('  TIMEOUT')
        if check:
            raise RuntimeError('timeout: ' + cmd)
        return 124, ''
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'rc={r.returncode}: {cmd}\n{out[-800:]}')
    return r.returncode, out


def expect(desc, cond, detail=''):
    EXP['yes' if cond else 'no'] += 1
    note(f'EXPECTED: {desc} - {"yes" if cond else "NO (recorded; judged in the results file)"}' + (f' [{detail}]' if detail else ''))
    return cond


def my_pid():
    try:
        p = int(open(W + '/cassandra.pid').read().strip())
        return p if 'CassandraDaemon' in open(f'/proc/{p}/cmdline').read() else None
    except (OSError, ValueError):
        return PID[0] if PID[0] and os.path.exists(f'/proc/{PID[0]}') else None


def nodetool(cmd, timeout=180):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} {cmd}', timeout=timeout, check=False, quiet=True)[1]


def stop_node():
    p = my_pid()
    if p is None:
        return
    PID[0] = p
    nodetool('stopdaemon')
    for _ in range(90):
        if not os.path.exists(f'/proc/{p}'):
            return
        time.sleep(1)
    note(f'kill -9 {p}')
    subprocess.run(['kill', '-9', str(p)]); time.sleep(3)


def fail(msg):
    note('FAIL: ' + msg)
    stop_node()
    sys.exit(1)


def make_conf(pool_mib):
    """conf copy: the tag's cassandra.yaml without the keys set here, plus the B3a/B3i.1 lines"""
    shutil.rmtree(W, ignore_errors=True)
    for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
        os.makedirs(f'{W}/{d}', exist_ok=True)
    shutil.copytree(C + '/conf', W + '/conf')
    env = open(W + '/conf/cassandra-env.sh').read()
    env2 = env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"')
    assert env2 != env
    open(W + '/conf/cassandra-env.sh', 'w').write(env2)
    add = {'cluster_name': 'ivl', 'num_tokens': '16', 'endpoint_snitch': 'SimpleSnitch', 'listen_address': ADDR, 'rpc_address': ADDR,
           'commitlog_directory': W + '/commitlog', 'hints_directory': W + '/hints', 'saved_caches_directory': W + '/saved_caches',
           'cdc_raw_directory': W + '/cdc_raw', 'memtable_offheap_space': f'{pool_mib}MiB',
           'commitlog_total_space': '1GiB', 'memtable_allocation_type': 'offheap_objects', 'auto_snapshot': 'false',
           'memtable_cleanup_threshold': '0.99', 'native_transport_timeout': '30s', 'write_request_timeout': '20000ms'}
    lines = open(C + '/conf/cassandra.yaml').read().splitlines()
    keys = set(add) | {'seed_provider', 'data_file_directories'}
    out, skip = [], False
    for l in lines:
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in keys
            if skip:
                continue
        elif skip and (l.startswith((' ', '\t', '-')) or not l.strip() or l.lstrip().startswith('#')):
            continue
        else:
            skip = False
        out.append(l)
    tail = [f'{k}: {v}' for k, v in add.items()]
    tail += ['seed_provider:', '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider', '    parameters:',
             f'      - seeds: "{ADDR}:7000"', 'data_file_directories:', f'    - {W}/data']
    open(W + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 ivl lines ----\n' + '\n'.join(tail) + '\n')
    note('yaml tail: ' + '; '.join(t for t in tail if not t.startswith(('  ', 'seed', 'data_file'))))


def start_node():
    if my_pid() is not None:
        fail('node already running')
    env = dict(os.environ, CASSANDRA_CONF=W + '/conf', CASSANDRA_LOG_DIR=W + '/logs', MAX_HEAP_SIZE='2G')
    env.pop('JVM_EXTRA_OPTS', None)
    sh(f'bin/cassandra -p {W}/cassandra.pid > {W}/stdout.txt 2>&1', env=env)
    for _ in range(30):
        time.sleep(1)
        if my_pid() is not None:
            break
    else:
        fail('node did not start; see ' + W + '/stdout.txt')
    t0 = time.time()
    while time.time() - t0 < 300:
        if my_pid() is None:
            fail('node died during start')
        st = nodetool('status')
        sb = nodetool('statusbinary')
        if re.search(r'^UN\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
            log(f'UN and serving after {time.time() - t0:.0f} s')
            return
        time.sleep(3)
    fail('not UN within 300 s')


def rss_anon(pid):
    try:
        for l in open(f'/proc/{pid}/status'):
            if l.startswith('RssAnon:'):
                return int(l.split()[1]) * 1024
    except OSError:
        pass
    return -1


def dir_bytes(path):
    t = 0
    for root, _, files in os.walk(path):
        for f in files:
            try: t += os.path.getsize(os.path.join(root, f))
            except OSError: pass
    return t


def table_dir(table):
    g = glob.glob(f'{W}/data/ks/{table}-*')
    return g[0] if g else None


def sstable_bytes(table):
    """Data.db + Index.db bytes of the base table and of its index backing table (hidden directory .idx_<table>)"""
    d = table_dir(table); r = {'data': 0, 'index': 0, 'all': 0, 'idx_data': 0, 'idx_index': 0, 'idx_all': 0}
    if d:
        for f in glob.glob(d + '/*-Data.db'): r['data'] += os.path.getsize(f)
        for f in glob.glob(d + '/*-Index.db'): r['index'] += os.path.getsize(f)
        r['all'] = dir_bytes(d)
        for f in glob.glob(d + '/.idx_*/*-Data.db'): r['idx_data'] += os.path.getsize(f)
        for f in glob.glob(d + '/.idx_*/*-Index.db'): r['idx_index'] += os.path.getsize(f)
        r['idx_all'] = sum(dir_bytes(x) for x in glob.glob(d + '/.idx_*'))
    return r


class Sampler(threading.Thread):
    def __init__(self, arm, table):
        super().__init__(daemon=True); self.arm, self.table, self.stop = arm, table, threading.Event(); self.rows = []
    def run(self):
        f = open(f'{LOGS}/samples-{self.arm}.csv', 'w'); f.write('t,rss_anon,table_dir_bytes,commitlog_bytes\n')
        t0 = time.time(); pid = my_pid()
        while not self.stop.is_set():
            d = table_dir(self.table)
            row = (round(time.time() - t0, 1), rss_anon(pid), dir_bytes(d) if d else 0, dir_bytes(W + '/commitlog'))
            self.rows.append(row); f.write(','.join(map(str, row)) + '\n'); f.flush()
            self.stop.wait(2)
        f.close()


def writer(*args, timeout=3600):
    rc, out = sh(f'python3 {HARNESS}/writer.py {ADDR} ' + ' '.join(map(str, args)), timeout=timeout, check=False, quiet=True,
                 env=dict(os.environ, CASSANDRA_HOME=C))
    SESSION.write(out[-1500:] + '\n'); SESSION.flush()
    try:
        return json.loads(out.strip().splitlines()[-1])
    except Exception:
        fail(f'writer failed (rc={rc}): {out[-400:]}')


def syslog_size():
    return os.path.getsize(W + '/logs/system.log')


FLUSH = re.compile(r'Enqueuing flush of (\S+), Reason: (\w+), Usage: ([^\n]*)')


def flush_lines_since(off):
    with open(W + '/logs/system.log', 'rb') as f:
        f.seek(off); txt = f.read().decode('utf8', 'replace')
    return [(m.group(1), m.group(2), m.group(3).strip()) for m in FLUSH.finditer(txt)]


def usage_mib(s):
    """parse 'X MiB (n%) on-heap, Y MiB (m%) off-heap' -> (on, off) in MiB; units B/KiB/MiB/GiB"""
    u = {'B': 1 / MIB, 'KiB': 1 / 1024, 'MiB': 1, 'GiB': 1024}
    res = {}
    for val, unit, kind in re.findall(r'([\d.]+)\s*(B|KiB|MiB|GiB)\s*\(\d+%\)\s*(on-heap|off-heap)', s):
        res[kind] = float(val) * u[unit]
    return res.get('on-heap'), res.get('off-heap')


def tablestats(name):
    t = nodetool(f'tablestats ks.{name}')
    d = {}
    for key, pat in (('memtable_data', r'Memtable data size'), ('memtable_off_heap', r'Memtable off heap memory used'), ('memtable_cells', r'Memtable cell count'), ('space_live', r'Space used \(live\)')):
        m = re.search(pat + r':\s*(\d+)', t)
        d[key] = int(m.group(1)) if m else None
    return d


def run_arm(arm, S, N, seed, index=True):
    table = 't_' + arm
    note(f'--- arm {arm}: S={S} N={N} index={index} ---')
    writer('schema', table, 'index' if index else 'noindex')
    time.sleep(1)
    off = syslog_size(); pid = my_pid()
    rss0 = rss_anon(pid); d0 = sstable_bytes(table); cl0 = dir_bytes(W + '/commitlog')
    smp = Sampler(arm, table); smp.start()
    t0 = time.time()
    w = writer('write', table, S, N, seed)
    wsec = time.time() - t0
    pre = tablestats(table)
    pre_idx = tablestats(table + '.idx_' + table) if index else None
    rss_pre = rss_anon(pid)
    smp.stop.set(); smp.join()
    nodetool(f'flush ks {table}', timeout=900)
    time.sleep(2)
    sb = sstable_bytes(table)
    post_idx = tablestats(table + '.idx_' + table) if index else None
    fl = flush_lines_since(off)
    mine = [x for x in fl if table in x[0]]
    rss_peak = max([r[1] for r in smp.rows] + [rss_pre])
    rec = {'arm': arm, 'S': S, 'N': N, 'index': index, 'ok': w['ok'], 'errors': w['errors'], 'messages': w['messages'], 'write_seconds': round(wsec, 1),
           'rss_anon_before': rss0, 'rss_anon_peak': rss_peak, 'rss_anon_pre_flush': rss_pre, 'table_dir_before': d0['all'], 'idx_dir_before': d0['idx_all'],
           'commitlog_before': cl0, 'commitlog_max': max([r[3] for r in smp.rows] + [0]), 'pre_flush_tablestats': pre, 'pre_flush_idx_tablestats': pre_idx,
           'post_flush_idx_tablestats': post_idx,
           'data_bytes': sb['data'], 'index_bytes': sb['index'], 'table_dir_after_flush': sb['all'],
           'idx_data_bytes': sb['idx_data'], 'idx_index_bytes': sb['idx_index'], 'idx_dir_after_flush': sb['idx_all'],
           'flush_lines': [{'table': a, 'reason': b, 'usage': c} for a, b, c in mine]}
    ml = [x for x in mine if x[1] == 'MEMTABLE_LIMIT']
    rec['memtable_limit_flushes'] = len(ml)
    rec['memtable_limit_first_usage_mib'] = usage_mib(ml[0][2]) if ml else None
    rec['memtable_limit_max_off_heap_mib'] = max([usage_mib(x[2])[1] or 0 for x in ml], default=None)
    ARMS.write(json.dumps(rec) + '\n'); ARMS.flush()
    note(f'arm {arm}: ok={w["ok"]} errors={w["errors"]} msgs={dict(w["messages"])} write_s={wsec:.0f} base data+index={sb["data"] + sb["index"]} '
         f'idx data+index={sb["idx_data"] + sb["idx_index"]} (N*S={N * S}) memtable_data(pre-flush)={pre["memtable_data"]} off_heap={pre["memtable_off_heap"]} '
         f'idx space_live={post_idx["space_live"] if post_idx else None} rss_anon peak={rss_peak} MEMTABLE_LIMIT flushes={len(ml)} first usage={rec["memtable_limit_first_usage_mib"]}')
    writer('drop', table)
    return rec


def main():
    try:
        os.makedirs('/dev/shm/s4-b2', exist_ok=True)
        recs = {}
        make_conf(512)
        start_node()
        note(f'life 1 started, pid {my_pid()}, memtable_offheap_space 512 MiB')
        writer('schema', 't_pre', 'index')
        a = writer('write', 't_pre', 65534, 5, 1); b = writer('write', 't_pre', 65535, 5, 2)
        okb = expect('precheck: 5 inserts at S=65534 succeed', a['ok'] == 5 and a['errors'] == 0, json.dumps(a['messages']))
        okc = expect('precheck: 5 inserts at S=65535 fail with the index message', b['errors'] == 5 and list(b['messages']) and all(MSG in k for k in b['messages']), json.dumps(b['messages']))
        writer('drop', 't_pre')
        if not (okb and okc):
            fail('first-trigger check failed: the traced boundary is wrong (B3g row 2); stopping')
        if MODE == 'quick':
            arms = [('n1000', 65534, 300, 12, True), ('s65535', 65535, 50, 15, True)]
        else:
            arms = [('n1000', 65534, 1000, 11, True), ('n4000', 65534, 4000, 12, True), ('n16000', 65534, 16000, 13, True), ('s65535', 65535, 200, 15, True),
                    ('noidx4000', 65534, 4000, 12, False), ('s100', 100, 655340, 16, True)]
        for arm, S, N, seed, ix in arms:
            recs[arm] = run_arm(arm, S, N, seed, ix)
        shutil.copy(W + '/logs/system.log', LOGS + '/system.log.life1')
        stop_node()
        if MODE != 'quick':
            make_conf(256)
            start_node()
            note(f'life 2 started, pid {my_pid()}, memtable_offheap_space 256 MiB')
            recs['p256_n16000'] = run_arm('p256_n16000', 65534, 16000, 13, True)
            shutil.copy(W + '/logs/system.log', LOGS + '/system.log.life2')
            stop_node()
        evaluate(recs)
    except SystemExit:
        raise
    except Exception as e:
        note(f'FAIL: exception {e!r}')
        stop_node()
        raise
    finally:
        stop_node()
        shutil.rmtree('/dev/shm/s4-b2', ignore_errors=True)
        note(f'node pid left: {my_pid()}; /dev/shm/s4-b2 exists: {os.path.exists("/dev/shm/s4-b2")}')


def evaluate(r):
    if MODE == 'quick':
        return
    NS = lambda a: r[a]['N'] * r[a]['S']
    idxb = lambda a: r[a]['idx_data_bytes'] + r[a]['idx_index_bytes']
    for a in ('n1000', 'n4000', 'n16000', 'noidx4000', 's100', 'p256_n16000'):
        expect(f'{a}: no insert rejected', r[a]['errors'] == 0, f"errors={r[a]['errors']}")
    k = r['s65535']
    expect('s65535: all 200 inserts rejected with the index message', k['errors'] == 200 and list(k['messages']) and all(MSG in m for m in k['messages']), json.dumps(k['messages'])[:300])
    expect('s65535: 0 B added to the base and index directories and memtable empty', k['table_dir_after_flush'] - k['table_dir_before'] == 0 and k['idx_dir_after_flush'] - k['idx_dir_before'] == 0 and (k['pre_flush_tablestats']['memtable_data'] or 0) == 0,
           f"base_dir={k['table_dir_after_flush']} idx_dir={k['idx_dir_after_flush']} memtable={k['pre_flush_tablestats']}")
    for a in ('n1000', 'n4000', 'n16000'):
        expect(f'{a}: index Data+Index bytes in [0.9, 2.2] x N*S', 0.9 * NS(a) <= idxb(a) <= 2.2 * NS(a), f"ratio={idxb(a) / NS(a):.2f}")
    expect('index bytes ratio n16000/n4000 in [3.5, 4.5]', 3.5 <= idxb('n16000') / idxb('n4000') <= 4.5, f"{idxb('n16000') / idxb('n4000'):.2f}")
    expect('index bytes ratio n4000/n1000 in [3.5, 4.5]', 3.5 <= idxb('n4000') / idxb('n1000') <= 4.5, f"{idxb('n4000') / idxb('n1000'):.2f}")
    m, p = r['n16000'], r['p256_n16000']
    expect('n16000 at 512 MiB: at least one MEMTABLE_LIMIT flush, logged off-heap usage <= 640 MiB', m['memtable_limit_flushes'] >= 1 and (m['memtable_limit_max_off_heap_mib'] or 1e9) <= 640, f"{m['memtable_limit_flushes']} flushes, max off-heap {m['memtable_limit_max_off_heap_mib']}")
    expect('n16000 at 256 MiB: at least one MEMTABLE_LIMIT flush, logged off-heap usage <= 320 MiB', p['memtable_limit_flushes'] >= 1 and (p['memtable_limit_max_off_heap_mib'] or 1e9) <= 320, f"{p['memtable_limit_flushes']} flushes, max off-heap {p['memtable_limit_max_off_heap_mib']}")
    a, b = (m['memtable_limit_first_usage_mib'] or (None, None))[1], (p['memtable_limit_first_usage_mib'] or (None, None))[1]
    expect('first MEMTABLE_LIMIT off-heap usage ratio (512 MiB over 256 MiB) in [1.4, 3.0]', bool(a and b and 1.4 <= a / b <= 3.0), f"{a} / {b}")
    n = r['noidx4000']
    expect('noidx4000: base Data+Index bytes in [0.9, 1.3] x N*S', 0.9 * NS('noidx4000') <= n['data_bytes'] + n['index_bytes'] <= 1.3 * NS('noidx4000'), f"{n['data_bytes'] + n['index_bytes']} vs N*S {NS('noidx4000')}")
    expect('index of n4000 adds at least 0.9 x N*S on top of the no-index base', idxb('n4000') >= 0.9 * NS('n4000'), f"idx={idxb('n4000')}")
    c1, c2 = idxb('s100') / NS('s100'), idxb('n1000') / NS('n1000')
    expect('small-value control: (index bytes / key bytes) within [0.5, 2.0] x that of n1000', 0.5 <= c1 / c2 <= 2.0, f"s100={c1:.2f} n1000={c2:.2f}")
    note(f'summary: EXPECTED yes={EXP["yes"]} no={EXP["no"]}')


if __name__ == '__main__':
    main()
