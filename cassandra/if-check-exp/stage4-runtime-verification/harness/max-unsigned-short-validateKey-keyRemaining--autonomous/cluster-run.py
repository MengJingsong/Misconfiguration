#!/usr/bin/env python3
"""Stage 4, cluster tier (B3 + B3i) of max-unsigned-short-validateKey-keyRemaining--autonomous.
usage: cluster-run.py <run-name> [main|quick|mid]
  life 1 (memtable_heap_space 256 MiB, heap_buffers): boundary precheck (5 writes at K=65535 must succeed, 5 at K=65536 must fail; else stop), then arms
         k1000_n10k, k1000_n100k, k65535_n10k, k65535_n100k, k65536 (100 attempts);
  life 2 (restart, memtable_heap_space 128 MiB): arm p128_k65535_n100k.
  quick: precheck + k1000 (N=500) + k65536 (20 attempts) only; a shakedown, not a reading.
  Port slot 5: address 127.0.5.1, JMX 7150, Byteman agent 19150, native 9042 on that address. Node data on tmpfs /dev/shm/s4-b9-vk/node.
  A Byteman script traces Validation.validateKey (length >= 1000) and QueryProcessor.validateKey (length > 65535) entries to <node>/logs/vk-life<N>.trace.
Output: ~/s4-b9-vk-logs/<run>/cluster/ (summary.txt with EXPECTED lines, arms.jsonl, samples-<arm>.csv, session.log, system.log.life<N>, vk-life<N>.trace).
Exit 1 if a set-up or first-trigger check fails; the node is stopped on any exit."""
import glob, json, os, re, shutil, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b9-vk/c')
HARNESS = os.path.dirname(os.path.abspath(__file__))
W = '/dev/shm/s4-b9-vk/node'
ADDR, JMX, BM = '127.0.5.1', 7150, 19150
RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'main'
LOGS = f'{HOME}/s4-b9-vk-logs/{RUN}/cluster'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a')
ARMS = open(LOGS + '/arms.jsonl', 'a')
EXP = {'yes': 0, 'no': 0}
PID = [None]
MSG65536 = 'Key length of 65536 is longer than maximum of 65535'
MIB = 1 << 20
LIFE = [0]


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


RULES = '''RULE vk validation entry
CLASS org.apache.cassandra.cql3.Validation
METHOD validateKey
AT ENTRY
IF $2 != null AND $2.remaining() >= 1000 AND (traceOpen("vk", "%(t)s") OR true)
DO traceln("vk", "V " + $2.remaining())
ENDRULE

RULE vk queryprocessor oversize
CLASS org.apache.cassandra.cql3.QueryProcessor
METHOD validateKey
AT ENTRY
IF $1 != null AND $1.remaining() > 65535 AND (traceOpen("vk", "%(t)s") OR true)
DO traceln("vk", "Q " + $1.remaining())
ENDRULE

RULE vk key length exception
CLASS org.apache.cassandra.exceptions.InvalidRequestException
METHOD <init>(java.lang.String)
AT ENTRY
IF $1 != null AND $1.startsWith("Key length of") AND (traceOpen("vk", "%(t)s") OR true)
DO traceln("vk", "X " + $1 + " :: " + formatStack(8).replace("\\n", " | "))
ENDRULE
'''


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
    LIFE[0] += 1
    open(W + '/vk.btm', 'w').write(RULES % {'t': f'{W}/logs/vk-life{LIFE[0]}.trace'})
    add = {'cluster_name': 'vk', 'num_tokens': '16', 'endpoint_snitch': 'SimpleSnitch', 'listen_address': ADDR, 'rpc_address': ADDR,
           'commitlog_directory': W + '/commitlog', 'hints_directory': W + '/hints', 'saved_caches_directory': W + '/saved_caches',
           'cdc_raw_directory': W + '/cdc_raw', 'memtable_heap_space': f'{pool_mib}MiB',
           'commitlog_total_space': '512MiB', 'memtable_allocation_type': 'heap_buffers', 'auto_snapshot': 'false',
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
    open(W + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 vk lines ----\n' + '\n'.join(tail) + '\n')
    note('yaml tail: ' + '; '.join(t for t in tail if not t.startswith(('  ', 'seed', 'data_file'))))


def start_node():
    if my_pid() is not None:
        fail('node already running')
    jar = glob.glob(C + '/build/lib/jars/byteman-4*.jar')
    jar = [j for j in jar if not any(x in j for x in ('submit', 'install', 'bmunit'))]
    if not jar:
        fail('no byteman jar')
    env = dict(os.environ, CASSANDRA_CONF=W + '/conf', CASSANDRA_LOG_DIR=W + '/logs', MAX_HEAP_SIZE='2G',
               JVM_EXTRA_OPTS=f'-javaagent:{jar[0]}=script:{W}/vk.btm,port:{BM},listener:true' + os.environ.get('VK_BM_EXTRA', ''))
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


def heap_used(pid):
    rc, out = sh(f'jcmd {pid} GC.heap_info', timeout=30, check=False, quiet=True)
    m = re.search(r'garbage-first heap\s+total (\d+)K, used (\d+)K', out)
    return int(m.group(2)) * 1024 if m else -1


class Sampler(threading.Thread):
    def __init__(self, arm, table):
        super().__init__(daemon=True); self.arm, self.table, self.stop = arm, table, threading.Event(); self.rows = []
    def run(self):
        f = open(f'{LOGS}/samples-{self.arm}.csv', 'w'); f.write('t,rss_anon,table_dir_bytes,commitlog_bytes,heap_used\n')
        t0 = time.time(); pid = my_pid(); n = 0
        while not self.stop.is_set():
            d = table_dir(self.table)
            hu = heap_used(pid) if n % 5 == 0 else ''
            row = (round(time.time() - t0, 1), rss_anon(pid), dir_bytes(d) if d else 0, dir_bytes(W + '/commitlog'), hu)
            self.rows.append(row); f.write(','.join(map(str, row)) + '\n'); f.flush(); n += 1
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


def run_arm(arm, K, N, seed, pool_mib):
    table = 't_' + arm
    note(f'--- arm {arm}: K={K} N={N} pool={pool_mib} MiB ---')
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
    mine = [x for x in fl if x[0].endswith(table) or table in x[0]]
    rss_peak = max([r[1] for r in smp.rows] + [rss_pre])
    ml = [x for x in mine if x[1] == 'MEMTABLE_LIMIT']
    usages = sorted((usage_mib(x[2])[0] or 0) for x in ml)
    reasons = {}
    for x in mine:
        reasons[x[1]] = reasons.get(x[1], 0) + 1
    rec = {'arm': arm, 'K': K, 'N': N, 'pool_mib': pool_mib, 'ok': w['ok'], 'errors': w['errors'], 'messages': w['messages'], 'write_seconds': round(wsec, 1),
           'rss_anon_before': rss0, 'rss_anon_peak': rss_peak, 'rss_anon_pre_flush': rss_pre, 'table_dir_before': d0, 'table_dir_pre_flush': d_pre,
           'commitlog_before': cl0, 'commitlog_max': max([r[3] for r in smp.rows] + [0]), 'pre_flush_tablestats': pre,
           'heap_used_max': max([r[4] for r in smp.rows if r[4] != ''] + [0]),
           'data_bytes': sb['data'], 'index_bytes': sb['index'], 'table_dir_after_flush': sb['all'],
           'flush_reasons': reasons, 'memtable_limit_flushes': len(ml), 'memtable_limit_usage_on_heap_mib': usages,
           'memtable_limit_median_on_heap_mib': usages[len(usages) // 2] if usages else None,
           'memtable_limit_max_on_heap_mib': usages[-1] if usages else None,
           'flush_lines': [{'table': a, 'reason': b, 'usage': c} for a, b, c in mine]}
    ARMS.write(json.dumps(rec) + '\n'); ARMS.flush()
    note(f'arm {arm}: ok={w["ok"]} errors={w["errors"]} msgs={dict(w["messages"])} write_s={wsec:.0f} data+index={sb["data"] + sb["index"]} '
         f'(N*K={N * K}) memtable_data(pre-flush)={pre["memtable_data"]} rss_anon peak={rss_peak} flushes={reasons} '
         f'MEMTABLE_LIMIT usage median={rec["memtable_limit_median_on_heap_mib"]} max={rec["memtable_limit_max_on_heap_mib"]}')
    writer('drop', table)
    return rec


def trace_counts(life):
    f = f'{W}/logs/vk-life{life}.trace'
    c = {'V_ge1000': {}, 'V_gt65535': 0, 'Q_gt65535': 0, 'X': 0, 'X_len65536': 0, 'X_stack_clusteringprefix': 0, 'X_stack_other_validators': 0}
    if not os.path.exists(f):
        return c
    for l in open(f):
        if l.startswith('X '):
            c['X'] += 1
            m = re.match(r'X Key length of (\d+) is longer than maximum of 65535 :: (.*)', l)
            if m:
                c['X_len65536'] += (m.group(1) == '65536')
                c['X_stack_clusteringprefix'] += ('ClusteringPrefix.validate' in m.group(2))
                c['X_stack_other_validators'] += ('QueryProcessor.validateKey' in m.group(2) or 'Validation.validateKey' in m.group(2))
            continue
        p = l.split()
        if len(p) != 2:
            continue
        n = int(p[1])
        if p[0] == 'V':
            c['V_ge1000'][n] = c['V_ge1000'].get(n, 0) + 1
            if n > 65535: c['V_gt65535'] += 1
        elif p[0] == 'Q':
            c['Q_gt65535'] += 1
    return c


def main():
    try:
        os.makedirs('/dev/shm/s4-b9-vk', exist_ok=True)
        recs = {}; tr = {}
        make_conf(256)
        start_node()
        note(f'life 1 started, pid {my_pid()}, memtable_heap_space 256 MiB')
        writer('schema', 't_pre')
        a = writer('write', 't_pre', 65535, 5, 1); b = writer('write', 't_pre', 65536, 5, 2)
        okb = expect('precheck: 5 writes at K=65535 succeed', a['ok'] == 5 and a['errors'] == 0, json.dumps(a['messages']))
        okc = expect('precheck: 5 writes at K=65536 fail with the exact message', b['errors'] == 5 and list(b['messages']) and all(MSG65536 in k for k in b['messages']), json.dumps(b['messages']))
        writer('drop', 't_pre')
        if not (okb and okc):
            fail('first-trigger check failed: the traced boundary is wrong (B3g row 3); stopping')
        if MODE == 'mid':
            arms = [('k65535_n10k', 65535, 10000, 13)]
        elif MODE == 'quick':
            arms = [('k1000_n10k', 1000, 500, 11), ('k65536', 65536, 20, 15)]
        else:
            arms = [('k1000_n10k', 1000, 10000, 11), ('k1000_n100k', 1000, 100000, 12), ('k65535_n10k', 65535, 10000, 13),
                    ('k65535_n100k', 65535, 100000, 14), ('k65536', 65536, 100, 15)]
        for arm, K, N, seed in arms:
            recs[arm] = run_arm(arm, K, N, seed, 256)
        tr[1] = trace_counts(1)
        shutil.copy(W + '/stdout.txt', LOGS + '/stdout.life1.txt')
        shutil.copy(W + '/logs/system.log', LOGS + '/system.log.life1')
        if os.path.exists(f'{W}/logs/vk-life1.trace'):
            shutil.copy(f'{W}/logs/vk-life1.trace', LOGS + '/vk-life1.trace')
        stop_node()
        if MODE == 'main':
            make_conf(128)
            start_node()
            note(f'life 2 started, pid {my_pid()}, memtable_heap_space 128 MiB')
            recs['p128_k65535_n100k'] = run_arm('p128_k65535_n100k', 65535, 100000, 14, 128)
            tr[2] = trace_counts(2)
            shutil.copy(W + '/stdout.txt', LOGS + '/stdout.life2.txt')
            shutil.copy(W + '/logs/system.log', LOGS + '/system.log.life2')
            if os.path.exists(f'{W}/logs/vk-life2.trace'):
                shutil.copy(f'{W}/logs/vk-life2.trace', LOGS + '/vk-life2.trace')
            stop_node()
        note('trace counts: ' + json.dumps(tr))
        evaluate(recs, tr)
    except SystemExit:
        raise
    except Exception as e:
        note(f'FAIL: exception {e!r}')
        stop_node()
        raise
    finally:
        stop_node()
        shutil.rmtree('/dev/shm/s4-b9-vk', ignore_errors=True)
        note(f'node pid left: {my_pid()}; /dev/shm/s4-b9-vk exists: {os.path.exists("/dev/shm/s4-b9-vk")}')


def evaluate(r, tr):
    if MODE != 'main':
        return
    NK = lambda a: r[a]['N'] * r[a]['K']
    tot = lambda a: r[a]['data_bytes'] + r[a]['index_bytes']
    for a in ('k1000_n10k', 'k1000_n100k', 'k65535_n10k', 'k65535_n100k', 'p128_k65535_n100k'):
        expect(f'{a}: no write rejected', r[a]['errors'] == 0, f"errors={r[a]['errors']}")
    k = r['k65536']
    expect('k65536: 100 of 100 writes rejected with the exact message', k['errors'] == 100 and list(k['messages']) and all(MSG65536 in m for m in k['messages']), json.dumps(k['messages']))
    expect('k65536: 0 B added to the table directory and memtable empty', k['table_dir_after_flush'] - k['table_dir_before'] == 0 and (k['pre_flush_tablestats']['memtable_data'] or 0) == 0,
           f"dir_after={k['table_dir_after_flush']} before={k['table_dir_before']} memtable={k['pre_flush_tablestats']}")
    for a in ('k65535_n10k', 'k65535_n100k', 'p128_k65535_n100k'):
        expect(f'{a}: Data+Index bytes between 1.0 and 3.0 x N*K', 1.0 * NK(a) <= tot(a) <= 3.0 * NK(a), f"ratio={tot(a) / NK(a):.2f}")
    for a in ('k1000_n10k', 'k1000_n100k'):
        expect(f'{a}: Data+Index bytes between 1.0 and 4.0 x N*K', 1.0 * NK(a) <= tot(a) <= 4.0 * NK(a), f"ratio={tot(a) / NK(a):.2f}")
    for lo, hi in (('k1000_n10k', 'k1000_n100k'), ('k65535_n10k', 'k65535_n100k')):
        expect(f'{hi} is 8 to 12 times {lo} in Data+Index bytes', 8 <= tot(hi) / tot(lo) <= 12, f"{tot(hi) / tot(lo):.2f}")
    m = r['k65535_n100k']
    expect('k65535 N=100k at 256 MiB: at least 10 MEMTABLE_LIMIT flushes, each logged on-heap usage <= 320 MiB', m['memtable_limit_flushes'] >= 10 and (m['memtable_limit_max_on_heap_mib'] or 1e9) <= 320, f"{m['memtable_limit_flushes']} flushes, max {m['memtable_limit_max_on_heap_mib']}")
    m1 = r['k65535_n10k']
    expect('k65535 N=10k at 256 MiB: 1 to 3 MEMTABLE_LIMIT flushes', 1 <= m1['memtable_limit_flushes'] <= 3, str(m1['memtable_limit_flushes']))
    expect('k1000 N=100k at 256 MiB: at most 1 MEMTABLE_LIMIT flush', r['k1000_n100k']['memtable_limit_flushes'] <= 1, str(r['k1000_n100k']['memtable_limit_flushes']))
    p = r['p128_k65535_n100k']
    expect('k65535 N=100k at 128 MiB: at least 20 MEMTABLE_LIMIT flushes, each logged on-heap usage <= 160 MiB', p['memtable_limit_flushes'] >= 20 and (p['memtable_limit_max_on_heap_mib'] or 1e9) <= 160, f"{p['memtable_limit_flushes']} flushes, max {p['memtable_limit_max_on_heap_mib']}")
    expect('flush-count ratio (128 MiB over 256 MiB, K=65535 N=100k) between 1.6 and 2.5', m['memtable_limit_flushes'] > 0 and 1.6 <= p['memtable_limit_flushes'] / m['memtable_limit_flushes'] <= 2.5, f"{p['memtable_limit_flushes']} / {m['memtable_limit_flushes']}")
    a, b = m['memtable_limit_median_on_heap_mib'], p['memtable_limit_median_on_heap_mib']
    expect('median logged on-heap usage ratio (256 MiB over 128 MiB) between 1.6 and 2.5', bool(a and b and 1.6 <= a / b <= 2.5), f"{a} / {b}")
    t1, t2 = tr[1], tr[2]
    expect('trace life 1: no Validation.validateKey entry above 65535', t1['V_gt65535'] == 0, str(t1['V_gt65535']))
    expect('trace life 1: 0 QueryProcessor.validateKey entries above 65535', t1['Q_gt65535'] == 0, str(t1['Q_gt65535']))
    expect('trace life 1: 105 "Key length of" exceptions, all for 65536, all with ClusteringPrefix.validate in the stack, none with QueryProcessor/Validation validateKey', t1['X'] == 105 and t1['X_len65536'] == 105 and t1['X_stack_clusteringprefix'] == 105 and t1['X_stack_other_validators'] == 0, json.dumps({k: v for k, v in t1.items() if k.startswith('X')}))
    expect('trace life 2: no "Key length of" exception', t2['X'] == 0, str(t2['X']))
    expect('trace life 1: Validation.validateKey entries of length 65535 = 110,005', t1['V_ge1000'].get(65535, 0) == 110005, str(t1['V_ge1000'].get(65535, 0)))
    expect('trace life 1: Validation.validateKey entries of length 1000 = 110,000', t1['V_ge1000'].get(1000, 0) == 110000, str(t1['V_ge1000'].get(1000, 0)))
    expect('trace life 2: no Validation entry above 65535 and no QueryProcessor entry above 65535', t2['V_gt65535'] == 0 and t2['Q_gt65535'] == 0, f"{t2['V_gt65535']} {t2['Q_gt65535']}")
    expect('trace life 2: Validation.validateKey entries of length 65535 = 100,000', t2['V_ge1000'].get(65535, 0) == 100000, str(t2['V_ge1000'].get(65535, 0)))
    note(f'summary: EXPECTED yes={EXP["yes"]} no={EXP["no"]}')


if __name__ == '__main__':
    main()
