#!/usr/bin/env python3
"""Stage 4, cluster tier (B3 + B3i) of max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous.
usage: cluster-run.py <run-name> [main|quick]
  life 1 (pools 256 MiB): precheck (single-ck and two-ck boundary, must match exactly or the run stops), arms
         k100_r1e5, k1000_r1e5, k1000_r1e6, k65535_r1e4, k65536_r1e4;
  life 2 (restart, memtable_heap_space = memtable_offheap_space = 64 MiB): arm p64_k65535_r1e4 (the control), then the probe (B3i.8).
  quick: precheck + k1000 (R=500) + k65536 (R=200) + probe only; a shakedown, not a reading.
  Port slot 6: address 127.0.6.1, JMX 7160, native 9042 on that address. Node data on tmpfs /dev/shm/s4-b9-cp/node.
Output: ~/s4-b9-cp-logs/<run>/cluster/ (summary.txt with EXPECTED lines, arms.jsonl, samples-<arm>.csv, session.log, system.log per life).
Exit 1 if a set-up or first-trigger check fails; the node is stopped on any exit."""
import glob, json, os, re, shutil, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b9-cp')
HARNESS = os.path.dirname(os.path.abspath(__file__))
W = '/dev/shm/s4-b9-cp/node'
ADDR, JMX = '127.0.6.1', 7160
RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'main'
LOGS = f'{HOME}/s4-b9-cp-logs/{RUN}/cluster'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a')
ARMS = open(LOGS + '/arms.jsonl', 'a')
EXP = {'yes': 0, 'no': 0}
PID = [None]
MSG65536 = 'Key length of 65536 is longer than maximum of 65535'
MSG70010 = 'Key length of 70010 is longer than maximum of 65535'
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
    add = {'cluster_name': 'cp', 'num_tokens': '16', 'endpoint_snitch': 'SimpleSnitch', 'listen_address': ADDR, 'rpc_address': ADDR,
           'commitlog_directory': W + '/commitlog', 'hints_directory': W + '/hints', 'saved_caches_directory': W + '/saved_caches',
           'cdc_raw_directory': W + '/cdc_raw', 'memtable_heap_space': f'{pool_mib}MiB', 'memtable_offheap_space': f'{pool_mib}MiB',
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
    open(W + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 cp lines ----\n' + '\n'.join(tail) + '\n')
    note('yaml tail: ' + '; '.join(t for t in tail if not t.startswith(('  ', 'seed', 'data_file'))))


def start_node():
    if my_pid() is not None:
        fail('node already running')
    env = dict(os.environ, CASSANDRA_CONF=W + '/conf', CASSANDRA_LOG_DIR=W + '/logs', MAX_HEAP_SIZE='1G')
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
    d = table_dir(table); r = {'data': 0, 'index': 0, 'all': 0}
    if d:
        for f in glob.glob(d + '/*-Data.db'): r['data'] += os.path.getsize(f)
        for f in glob.glob(d + '/*-Index.db'): r['index'] += os.path.getsize(f)
        r['all'] = dir_bytes(d)
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


def tablestats(table):
    t = nodetool(f'tablestats ks.{table}')
    d = {}
    for key, name in (('memtable_data', r'Memtable data size'), ('memtable_off_heap', r'Memtable off heap memory used'), ('memtable_cells', r'Memtable cell count')):
        m = re.search(name + r':\s*(\d+)', t)
        d[key] = int(m.group(1)) if m else None
    return d


def run_arm(arm, K, N, seed):
    table = 't_' + arm
    note(f'--- arm {arm}: K={K} N={N} ---')
    writer('schema', table)
    time.sleep(1)
    off = syslog_size(); pid = my_pid()
    rss0 = rss_anon(pid); d0 = sstable_bytes(table)['all']; cl0 = dir_bytes(W + '/commitlog')
    smp = Sampler(arm, table); smp.start()
    t0 = time.time()
    w = writer('write', table, K, N, seed)
    wsec = time.time() - t0
    pre = tablestats(table)
    rss_pre = rss_anon(pid)
    smp.stop.set(); smp.join()
    d_pre = sstable_bytes(table)['all']
    nodetool(f'flush ks {table}', timeout=600)
    time.sleep(2)
    sb = sstable_bytes(table)
    fl = flush_lines_since(off)
    mine = [x for x in fl if table in x[0]]
    rss_peak = max([r[1] for r in smp.rows] + [rss_pre])
    rec = {'arm': arm, 'K': K, 'N': N, 'ok': w['ok'], 'errors': w['errors'], 'messages': w['messages'], 'write_seconds': round(wsec, 1),
           'rss_anon_before': rss0, 'rss_anon_peak': rss_peak, 'rss_anon_pre_flush': rss_pre, 'table_dir_before': d0, 'table_dir_pre_flush': d_pre,
           'commitlog_before': cl0, 'commitlog_max': max([r[3] for r in smp.rows] + [0]), 'pre_flush_tablestats': pre,
           'data_bytes': sb['data'], 'index_bytes': sb['index'], 'table_dir_after_flush': sb['all'],
           'flush_lines': [{'table': a, 'reason': b, 'usage': c} for a, b, c in mine]}
    ml = [x for x in mine if x[1] == 'MEMTABLE_LIMIT']
    rec['memtable_limit_flushes'] = len(ml)
    rec['memtable_limit_first_usage_mib'] = usage_mib(ml[0][2]) if ml else None
    rec['memtable_limit_max_off_heap_mib'] = max([usage_mib(x[2])[1] or 0 for x in ml], default=None)
    ARMS.write(json.dumps(rec) + '\n'); ARMS.flush()
    note(f'arm {arm}: ok={w["ok"]} errors={w["errors"]} msgs={dict(w["messages"])} write_s={wsec:.0f} data+index={sb["data"] + sb["index"]} '
         f'(N*K={N * K}) memtable_data(pre-flush)={pre["memtable_data"]} off_heap={pre["memtable_off_heap"]} rss_anon peak={rss_peak} '
         f'MEMTABLE_LIMIT flushes={len(ml)} first usage={rec["memtable_limit_first_usage_mib"]}')
    writer('drop', table)
    return rec


def precheck():
    writer('schema', 't_pre'); writer('schema2', 't_pre2')
    a = writer('write', 't_pre', 65535, 5, 1); b = writer('write', 't_pre', 65536, 5, 2)
    c = writer('write2', 't_pre2', 32768, 32767, 3, 3); d = writer('write2', 't_pre2', 32768, 32768, 3, 4); e = writer('write2', 't_pre2', 70000, 10, 3, 5)
    ok = [expect('precheck: 5 inserts at K=65535 succeed', a['ok'] == 5 and a['errors'] == 0, json.dumps(a['messages'])),
          expect('precheck: 5 inserts at K=65536 fail with the exact message', b['errors'] == 5 and bool(b['messages']) and all(MSG65536 in k for k in b['messages']), json.dumps(b['messages'])),
          expect('precheck: 3 inserts (32768, 32767) succeed (sum 65535)', c['ok'] == 3 and c['errors'] == 0, json.dumps(c['messages'])),
          expect('precheck: 3 inserts (32768, 32768) fail with the exact message (sum branch)', d['errors'] == 3 and bool(d['messages']) and all(MSG65536 in k for k in d['messages']), json.dumps(d['messages'])),
          expect('precheck: 3 inserts (70000, 10) fail with the sum in the message (first branch)', e['errors'] == 3 and bool(e['messages']) and all(MSG70010 in k for k in e['messages']), json.dumps(e['messages']))]
    writer('drop', 't_pre'); writer('drop', 't_pre2')
    if not all(ok):
        fail('first-trigger check failed: the traced boundary is wrong (B3g row 3); stopping')


def probe(recs):
    note('--- probe (B3i.8, informational, outside B3g) ---')
    writer('schema', 't_probe')
    off = syslog_size()
    w = writer('probe', 't_probe', timeout=300)
    time.sleep(3)
    nodetool('flush ks t_probe', timeout=120)
    with open(W + '/logs/system.log', 'rb') as f:
        f.seek(off); txt = f.read().decode('utf8', 'replace')
    errs = [l[:300] for l in txt.splitlines() if l.startswith(('ERROR', 'WARN')) or 'AssertionError' in l]
    rec = {'arm': 'probe', 'outcomes': w, 'log_error_or_warn_lines': errs[:20], 'n_log_error_or_warn_lines': len(errs), 'node_alive_after': my_pid() is not None}
    ARMS.write(json.dumps(rec) + '\n'); ARMS.flush()
    note('probe outcomes: ' + json.dumps(w))
    note(f'probe log lines (ERROR/WARN/AssertionError): {len(errs)}; node alive: {my_pid() is not None}')
    recs['probe'] = rec


def main():
    try:
        os.makedirs('/dev/shm/s4-b9-cp', exist_ok=True)
        recs = {}
        make_conf(256)
        start_node()
        note(f'life 1 started, pid {my_pid()}, pools 256 MiB')
        precheck()
        if MODE == 'quick':
            arms = [('k1000_r500', 1000, 500, 11), ('k65536_r200', 65536, 200, 15)]
        else:
            arms = [('k100_r1e5', 100, 100000, 11), ('k1000_r1e5', 1000, 100000, 12), ('k1000_r1e6', 1000, 1000000, 13),
                    ('k65535_r1e4', 65535, 10000, 14), ('k65536_r1e4', 65536, 10000, 15)]
        for arm, K, N, seed in arms:
            recs[arm] = run_arm(arm, K, N, seed)
        shutil.copy(W + '/logs/system.log', LOGS + '/system.log.life1')
        stop_node()
        make_conf(64 if MODE != 'quick' else 256)
        start_node()
        note(f'life 2 started, pid {my_pid()}, pools {64 if MODE != "quick" else 256} MiB')
        if MODE != 'quick':
            recs['p64_k65535_r1e4'] = run_arm('p64_k65535_r1e4', 65535, 10000, 14)
        probe(recs)
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
        shutil.rmtree('/dev/shm/s4-b9-cp', ignore_errors=True)
        note(f'node pid left: {my_pid()}; /dev/shm/s4-b9-cp exists: {os.path.exists("/dev/shm/s4-b9-cp")}')


def evaluate(r):
    p = r['probe']['outcomes']
    # probe predictions (B3i.8): (a) rejected with the text; (b), (c) not rejected with the text
    expect('probe (a) plain insert with a 65536-byte ck is rejected with the exact message', MSG65536 in p['a_plain_insert_65536']['outcome'], p['a_plain_insert_65536']['outcome'][:160])
    expect('probe (b) IF NOT EXISTS insert with a 65536-byte ck is not rejected with the message', 'Key length' not in p['b_cas_insert_65536']['outcome'], p['b_cas_insert_65536']['outcome'][:160])
    expect('probe (c) slice delete with a 70000-byte bound is not rejected with the message', 'Key length' not in p['c_slice_delete_70000']['outcome'], p['c_slice_delete_70000']['outcome'][:160])
    if MODE == 'quick':
        return
    NK = lambda a: r[a]['N'] * r[a]['K']
    tot = lambda a: r[a]['data_bytes'] + r[a]['index_bytes']
    for a in ('k100_r1e5', 'k1000_r1e5', 'k1000_r1e6', 'k65535_r1e4', 'p64_k65535_r1e4'):
        expect(f'{a}: no insert rejected', r[a]['errors'] == 0, f"errors={r[a]['errors']}")
    k = r['k65536_r1e4']
    expect('k65536: all 10,000 inserts rejected with the exact message', k['errors'] == 10000 and bool(k['messages']) and all(MSG65536 in m for m in k['messages']), json.dumps(k['messages']))
    expect('k65536: 0 B added to the table directory and memtable empty', k['table_dir_after_flush'] - k['table_dir_before'] == 0 and (k['pre_flush_tablestats']['memtable_data'] or 0) == 0,
           f"dir_after={k['table_dir_after_flush']} before={k['table_dir_before']} memtable={k['pre_flush_tablestats']}")
    for a in ('k1000_r1e6', 'k65535_r1e4'):
        expect(f'{a}: Data+Index bytes between 1.0 and 3.0 x R*K', 1.0 * NK(a) <= tot(a) <= 3.0 * NK(a), f"ratio={tot(a) / NK(a):.2f}")
    expect('Data+Index order (K=100,R=1e5) < (K=1000,R=1e5) < (K=1000,R=1e6) and K=65535 > (K=1000,R=1e5)',
           tot('k100_r1e5') < tot('k1000_r1e5') < tot('k1000_r1e6') and tot('k65535_r1e4') > tot('k1000_r1e5'),
           ' '.join(f"{a}={tot(a)}" for a in ('k100_r1e5', 'k1000_r1e5', 'k1000_r1e6', 'k65535_r1e4')))
    for a in ('k1000_r1e6', 'k65535_r1e4'):
        m = r[a]
        expect(f'{a} at 256 MiB: at least one MEMTABLE_LIMIT flush, logged off-heap usage <= 320 MiB', m['memtable_limit_flushes'] >= 1 and (m['memtable_limit_max_off_heap_mib'] or 1e9) <= 320, f"{m['memtable_limit_flushes']} flushes, max off-heap {m['memtable_limit_max_off_heap_mib']}")
    for a in ('k100_r1e5', 'k1000_r1e5'):
        expect(f'{a} at 256 MiB: no MEMTABLE_LIMIT flush', r[a]['memtable_limit_flushes'] == 0, str(r[a]['memtable_limit_flushes']))
    q = r['p64_k65535_r1e4']
    expect('k65535 at 64 MiB: at least one MEMTABLE_LIMIT flush, logged off-heap usage <= 80 MiB', q['memtable_limit_flushes'] >= 1 and (q['memtable_limit_max_off_heap_mib'] or 1e9) <= 80, f"{q['memtable_limit_flushes']} flushes, max off-heap {q['memtable_limit_max_off_heap_mib']}")
    a, b = (r['k65535_r1e4']['memtable_limit_first_usage_mib'] or (None, None))[1], (q['memtable_limit_first_usage_mib'] or (None, None))[1]
    expect('plateau ratio (first MEMTABLE_LIMIT off-heap usage, k65535 at 256 MiB over k65535 at 64 MiB) between 2.5 and 6', bool(a and b and 2.5 <= a / b <= 6), f"{a} / {b}")
    note(f'summary: EXPECTED yes={EXP["yes"]} no={EXP["no"]}')


if __name__ == '__main__':
    main()
