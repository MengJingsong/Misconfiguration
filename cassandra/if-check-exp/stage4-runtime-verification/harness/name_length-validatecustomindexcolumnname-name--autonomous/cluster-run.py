#!/usr/bin/env python3
"""Stage 4, cluster tier (B3 + B3i) of name_length-validatecustomindexcolumnname-name--autonomous.
usage: cluster-run.py <run-name> [main|quick]
  life A (memtable_heap_space 256 MiB): arms custom40, custom48, custom49 (DDL rejected), custom100 (DDL rejected), plain40, plain48, plain100, none40;
        each accepted arm loads N rows of a 100-char hex value, then nodetool flush and compact;
  life B (128 MiB) and life C (512 MiB): arm plain48 only (the pool control).
  quick: custom40 (N=20000), custom49 only; a shakedown, not a reading.
  Address 127.0.2.1, JMX 7270, native 9042. Node data on tmpfs /dev/shm/s4-b2/node.
Output: ~/s4-b2-logs/<run>/cluster/ (summary.txt with EXPECTED lines, arms.jsonl, samples-<arm>.csv, session.log, system.log per life).
Exit 1 if a set-up check fails; the node is stopped on any exit."""
import glob, json, os, re, shutil, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b2/c')
HARNESS = os.path.dirname(os.path.abspath(__file__))
W = '/dev/shm/s4-b2/node'
ADDR, JMX = '127.0.2.1', 7270
RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'main'
N_ROWS = int(os.environ.get('NL_ROWS', '500000'))
LOGS = f'{HOME}/s4-b2-logs/{RUN}/cluster'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a')
ARMS = open(LOGS + '/arms.jsonl', 'a')
EXP = {'yes': 0, 'no': 0}
PID = [None]
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
    add = {'cluster_name': 'nl', 'num_tokens': '16', 'endpoint_snitch': 'SimpleSnitch', 'listen_address': ADDR, 'rpc_address': ADDR,
           'commitlog_directory': W + '/commitlog', 'hints_directory': W + '/hints', 'saved_caches_directory': W + '/saved_caches',
           'cdc_raw_directory': W + '/cdc_raw', 'memtable_heap_space': f'{pool_mib}MiB', 'memtable_allocation_type': 'heap_buffers',
           'sasi_indexes_enabled': 'true', 'auto_snapshot': 'false', 'native_transport_timeout': '30s', 'write_request_timeout': '20000ms'}
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
    open(W + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 nl lines ----\n' + '\n'.join(tail) + '\n')
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


def usage_heap_mib(s):
    u = {'B': 1 / MIB, 'KiB': 1 / 1024, 'MiB': 1, 'GiB': 1024}
    m = re.search(r'([\d.]+)\s*(B|KiB|MiB|GiB)\s*\(\d+%\)\s*on-heap', s)
    return float(m.group(1)) * u[m.group(2)] if m else None


def heap_info(pid):
    """used heap in bytes after jcmd GC.run, from jcmd GC.heap_info (information)"""
    sh(f'jcmd {pid} GC.run', check=False, quiet=True, timeout=120)
    t = sh(f'jcmd {pid} GC.heap_info', check=False, quiet=True, timeout=120)[1]
    m = re.search(r'garbage-first heap\s+total (\d+)K, used (\d+)K', t)
    return int(m.group(2)) * 1024 if m else None


def spec(arm):
    kind, L = re.match(r'(custom|plain|none)(\d+)', arm).groups()
    return kind, int(L)


def run_arm(arm, seed=21):
    kind, L = spec(arm)
    table = 't_' + arm
    N = 50 if MODE == 'quick' and kind == 'custom' and L == 49 else (20000 if MODE == 'quick' else N_ROWS)
    note(f'--- arm {arm}: kind={kind} L={L} N={N} ---')
    off = syslog_size(); pid = my_pid()
    sc = writer('schema', table, L, kind)
    rec = {'arm': arm, 'kind': kind, 'L': L, 'N': N, 'schema': sc}
    if sc.get('create_index') == 'rejected':
        rec.update({'ok': 0, 'errors': 0, 'index_in_schema': writer('indexcount', table)['count']})
        ARMS.write(json.dumps(rec) + '\n'); ARMS.flush()
        note(f'arm {arm}: CREATE INDEX rejected: {sc.get("message")}; indexes in system_schema: {rec["index_in_schema"]}')
        writer('drop', table)
        return rec
    rss0 = rss_anon(pid)
    smp = Sampler(arm, table); smp.start()
    t0 = time.time()
    w = writer('write', table, L, N, seed, timeout=5400)
    wsec = time.time() - t0
    heap_load = heap_info(pid)
    rss_pre = rss_anon(pid)
    smp.stop.set(); smp.join()
    nodetool(f'flush ks {table}', timeout=1800)
    time.sleep(2)
    d_flush = dir_bytes(table_dir(table) or '/nonexistent')
    nodetool(f'compact ks {table}', timeout=3600)
    time.sleep(2)
    d_comp = dir_bytes(table_dir(table) or '/nonexistent')
    heap_after = heap_info(pid)
    fl = flush_lines_since(off)
    mine = [x for x in fl if table in x[0]]
    ml = [x for x in mine if x[1] == 'MEMTABLE_LIMIT']
    rec.update({'ok': w['ok'], 'errors': w['errors'], 'messages': w['messages'], 'write_seconds': round(wsec, 1), 'heap_used_after_load_gc': heap_load,
                'heap_used_after_compact_gc': heap_after, 'rss_anon_before': rss0, 'rss_anon_pre_flush': rss_pre,
                'rss_anon_peak': max([r[1] for r in smp.rows] + [rss_pre]), 'dir_after_flush': d_flush, 'dir_after_compact': d_comp,
                'flush_lines': [{'table': a, 'reason': b, 'usage': c} for a, b, c in mine], 'memtable_limit_flushes': len(ml),
                'memtable_limit_first_heap_mib': usage_heap_mib(ml[0][2]) if ml else None,
                'memtable_limit_max_heap_mib': max([usage_heap_mib(x[2]) or 0 for x in ml], default=None)})
    ARMS.write(json.dumps(rec) + '\n'); ARMS.flush()
    note(f'arm {arm}: ok={w["ok"]} errors={w["errors"]} msgs={dict(w["messages"])} write_s={wsec:.0f} dir after flush={d_flush} after compact={d_comp} '
         f'MEMTABLE_LIMIT flushes={len(ml)} first heap usage MiB={rec["memtable_limit_first_heap_mib"]} heap_used_gc={heap_load} rss_peak={rec["rss_anon_peak"]}')
    writer('drop', table)
    return rec


LIFE_A = ['custom40', 'custom48', 'custom49', 'custom100', 'plain40', 'plain48', 'plain100', 'none40']


def main():
    try:
        os.makedirs('/dev/shm/s4-b2', exist_ok=True)
        recs = {}
        arms_a = ['custom40', 'custom49'] if MODE == 'quick' else LIFE_A
        make_conf(256)
        start_node()
        note(f'life A started, pid {my_pid()}, memtable_heap_space 256 MiB')
        for arm in arms_a:
            recs[arm] = run_arm(arm)
        shutil.copy(W + '/logs/system.log', LOGS + '/system.log.lifeA')
        stop_node()
        if MODE != 'quick':
            for pool, tag in ((128, 'B'), (512, 'C')):
                make_conf(pool)
                start_node()
                note(f'life {tag} started, pid {my_pid()}, memtable_heap_space {pool} MiB')
                recs[f'plain48@{pool}'] = run_arm('plain48')
                shutil.copy(W + '/logs/system.log', LOGS + f'/system.log.life{tag}')
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
    for L in (49, 100):
        a = r[f'custom{L}']; name = 'c' + 'x' * (L - 1)
        want = f"Column '{name}' is longer than the permissible name length of 48 characters"
        expect(f'custom{L}: CREATE INDEX rejected with the exact text, no index in system_schema', a['schema'].get('create_index') == 'rejected' and want in a['schema'].get('message', '') and a['index_in_schema'] == 0,
               (a['schema'].get('message') or '')[:160])
    for a in ('custom40', 'custom48', 'plain40', 'plain48', 'plain100', 'none40', 'plain48@128', 'plain48@512'):
        expect(f'{a}: DDL accepted and no row insert failed', r[a]['schema'].get('create_index') in ('none', 'ok') and r[a]['errors'] == 0 and r[a]['ok'] == r[a]['N'], f"ok={r[a]['ok']} errors={r[a]['errors']}")
    spread = lambda v: (max(v) - min(v)) / (sum(v) / len(v))
    pl = [r[f'plain{L}']['dir_after_compact'] for L in (40, 48, 100)]
    expect('plain L=40,48,100: directory bytes after compaction (max-min)/mean <= 2%', spread(pl) <= 0.02, f'{spread(pl) * 100:.3f}% {pl}')
    cu = [r['custom40']['dir_after_compact'], r['custom48']['dir_after_compact']]
    expect('custom L=40 vs 48: directory bytes after compaction (max-min)/mean <= 2%', spread(cu) <= 0.02, f'{spread(cu) * 100:.3f}% {cu}')
    fu = [r[f'plain{L}']['memtable_limit_first_heap_mib'] for L in (40, 48, 100)]
    expect('plain L=40,48,100: first MEMTABLE_LIMIT logged on-heap usage (max-min)/mean <= 15%', all(fu) and spread(fu) <= 0.15, f'{fu}')
    a, b, c = r['plain48@128'], r['plain48'], r['plain48@512']
    ra, rc_ = a['memtable_limit_first_heap_mib'], c['memtable_limit_first_heap_mib']
    expect('control: first MEMTABLE_LIMIT on-heap usage ratio (512 MiB over 128 MiB) in [2.5, 6]', bool(ra and rc_ and 2.5 <= rc_ / ra <= 6), f'{rc_} / {ra}')
    expect('control: MEMTABLE_LIMIT flush count at 128 MiB > at 512 MiB >= 1', a['memtable_limit_flushes'] > c['memtable_limit_flushes'] >= 1, f"{a['memtable_limit_flushes']} / {b['memtable_limit_flushes']} / {c['memtable_limit_flushes']} (128/256/512)")
    ds = [a['dir_after_compact'], b['dir_after_compact'], c['dir_after_compact']]
    expect('control: directory bytes after compaction at 128 / 256 / 512 MiB (max-min)/mean <= 2%', spread(ds) <= 0.02, f'{spread(ds) * 100:.3f}% {ds}')
    expect('no-index L=40 directory bytes < plain L=40', r['none40']['dir_after_compact'] < r['plain40']['dir_after_compact'], f"{r['none40']['dir_after_compact']} vs {r['plain40']['dir_after_compact']}")
    note(f'summary: EXPECTED yes={EXP["yes"]} no={EXP["no"]}')


if __name__ == '__main__':
    main()
