#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of cache_keys_to_save-saveCache-keysEstimate--autonomous (audit amendments C1-C4, 2026-10-26).
usage: cluster-run.py <run-name> [all|y100|y10000|nosave|main]
  main (default): one chain of lifetimes on ONE data directory (/dev/shm/s4-b8-kt/node), each a start/stop of the node:
    L1  yaml keys_to_save unset (all): stress write 200000 (key, row cache via reader.py) + counter_write 200000; phase "all";
        then at runtime nodetool setcachekeystosave 10000x3, 100x3, 0x3 (a phase each); a capacity control
        (setcachecapacity 8 100 50 with keys_to_save 0: Entries fall, saved items follow Entries); setcachekeystosave 100x3.
    L2  restart with yaml keys_to_save 100x3, capacity 200/100/50: entries after warm load; repopulate; phase "yaml100".
    L3  restart with yaml keys_to_save 10000x3: repopulate; phase "yaml10000".
    L4  restart with saved_caches emptied and all three save periods 0: repopulate; no file expected (control).
  Port slot 1: address 127.0.1.1, JMX 7110, native 9042 on 127.0.1.1. Node data under /dev/shm/s4-b8-kt/node.
Output: ~/s4-b8-kt-logs/<run>/cluster/ (summary.txt with EXPECTED lines, phases.jsonl, session.log, system.log copies, stress outputs).
Exit 1 if a set-up check fails; the node is stopped on any exit. A reading that misses a prediction is recorded as
EXPECTED ... NO and the run goes on."""
import json, os, re, shutil, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b8-kt/c')
HARNESS = os.path.dirname(os.path.abspath(__file__))
W = '/dev/shm/s4-b8-kt/node'
ADDR, JMX = '127.0.1.1', 7110
RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
MODE = sys.argv[2] if len(sys.argv) > 2 else 'main'
N_ROWS = int(os.environ.get('KT_ROWS', 200000))
PERIOD = 10
LOGS = f'{HOME}/s4-b8-kt-logs/{RUN}/cluster'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a')
PHASES = open(LOGS + '/phases.jsonl', 'a')
EXP = {'yes': 0, 'no': 0}
PID = [None]


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


def expect(desc, cond):
    EXP['yes' if cond else 'no'] += 1
    note(f'EXPECTED: {desc} - {"yes" if cond else "NO (recorded; judged in the results file)"}')
    return cond


def daemons():
    # only THIS harness's node (its directory is in the command line): other sessions run nodes on the same host
    return sh("ps -eo pid,cmd | grep -E 'java .*org\\.apache\\.cassandra\\.service\\.CassandraDaemon' | grep -F 's4-b8-kt/node' | grep -v grep | cut -c1-60 || true", check=False, quiet=True)[1].strip()


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


def make_conf(extra):
    """conf copy whose cassandra.yaml = the tag's file without the keys set here, plus these lines (B3a + C1)"""
    shutil.rmtree(W + '/conf', ignore_errors=True)
    for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
        os.makedirs(f'{W}/{d}', exist_ok=True)
    shutil.copytree(C + '/conf', W + '/conf')
    env = open(W + '/conf/cassandra-env.sh').read()
    env2 = env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"')
    assert env2 != env
    open(W + '/conf/cassandra-env.sh', 'w').write(env2)
    add = {'cluster_name': 'kt', 'num_tokens': '16', 'endpoint_snitch': 'SimpleSnitch', 'listen_address': ADDR, 'rpc_address': ADDR,
           'commitlog_directory': W + '/commitlog', 'hints_directory': W + '/hints', 'saved_caches_directory': W + '/saved_caches',
           'cdc_raw_directory': W + '/cdc_raw', 'key_cache_size': '200MiB', 'row_cache_size': '100MiB', 'counter_cache_size': '50MiB',
           'key_cache_save_period': f'{PERIOD}s', 'row_cache_save_period': f'{PERIOD}s', 'counter_cache_save_period': f'{PERIOD}s',
           'native_transport_timeout': '30s'}
    add.update(extra)
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
    open(W + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 kt lines ----\n' + '\n'.join(tail) + '\n')
    note('yaml tail: ' + '; '.join(t for t in tail if not t.startswith(('  ', 'seed', 'data_file'))))


def start_node():
    if my_pid() is not None or daemons():
        fail('a CassandraDaemon is already running: ' + daemons()[:200])
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


def syslog_size():
    try:
        return os.path.getsize(W + '/logs/system.log')
    except OSError:
        return 0


SAVED = re.compile(r'Saved (\w+) \((\d+) items\) in (\d+) ms to (\S+) : (\d+) MB')


def saved_since(off):
    with open(W + '/logs/system.log', 'rb') as f:
        f.seek(off); txt = f.read().decode('utf8', 'replace')
    res = {}
    for m in SAVED.finditer(txt):
        res.setdefault(m.group(1), []).append(int(m.group(2)))
    return res


def info():
    t = nodetool('info')
    d = {}
    for name, key in (('Key Cache', 'key'), ('Row Cache', 'row'), ('Counter Cache', 'counter')):
        m = re.search(name + r'\s*:\s*entries (\d+), size ([\d.]+) (\w+), capacity ([\d.]+) (\w+)', t)
        if m:
            unit = {'bytes': 1, 'KiB': 1024, 'MiB': 1 << 20, 'GiB': 1 << 30}
            d[key] = {'entries': int(m.group(1)), 'size': float(m.group(2)) * unit.get(m.group(3), 1),
                      'cap': float(m.group(4)) * unit.get(m.group(5), 1)}
    m = re.search(r'Heap Memory \(MB\)\s*:\s*([\d.]+) / ([\d.]+)', t)
    if m: d['heap_mb'] = float(m.group(1))
    m = re.search(r'Off Heap Memory \(MB\)\s*:\s*([\d.]+)', t)
    if m: d['offheap_mb'] = float(m.group(1))
    return d


def heap_after_gc():
    p = my_pid()
    sh(f'jcmd {p} GC.run', check=False, quiet=True)
    out = sh(f'jcmd {p} GC.heap_info', check=False, quiet=True)[1]
    m = re.search(r'garbage-first heap\s+total (\d+)K, used (\d+)K', out)
    rss = 0
    try:
        for l in open(f'/proc/{p}/status'):
            if l.startswith('RssAnon'):
                rss = int(l.split()[1]) // 1024
    except OSError:
        pass
    return {'heap_used_mb': round(int(m.group(2)) / 1024, 1) if m else None, 'rss_anon_mb': rss}


def files():
    d = {}
    for e in os.scandir(W + '/saved_caches'):
        if e.name.endswith('.db'):
            d[e.name.split('-')[0]] = e.stat().st_size
    return d


CTYPES = {'key': 'KeyCache', 'row': 'RowCache', 'counter': 'CounterCache'}


def phase(label, n, expect_limit=True, wait_s=75):
    """wait until every cache has a Saved line newer than now, then read files, entries, heap (B3d/B3e step 3)."""
    off = syslog_size()
    t0 = time.time()
    got = {}
    while time.time() - t0 < wait_s:
        got = saved_since(off)
        if all(c in got for c in CTYPES.values()):
            break
        time.sleep(2)
    time.sleep(1)
    got = saved_since(off)
    fs = files()
    inf = info()
    hp = heap_after_gc()
    rec = {'label': label, 'N': n, 'saved_items': {k: (got.get(v) or [None])[-1] for k, v in CTYPES.items()},
           'saves_seen': {k: len(got.get(v) or []) for k, v in CTYPES.items()},
           'file_bytes': {k: fs.get(v) for k, v in CTYPES.items()}, 'entries': {k: inf.get(k, {}).get('entries') for k in CTYPES},
           'size': {k: inf.get(k, {}).get('size') for k in CTYPES}, 'cap': {k: inf.get(k, {}).get('cap') for k in CTYPES},
           'info_heap_mb': inf.get('heap_mb'), 'info_offheap_mb': inf.get('offheap_mb'), **hp}
    PHASES.write(json.dumps(rec) + '\n'); PHASES.flush()
    note(f'PHASE {label} N={n}: saved={rec["saved_items"]} file_bytes={rec["file_bytes"]} entries={rec["entries"]} heap_used_mb={hp["heap_used_mb"]} rss_anon_mb={hp["rss_anon_mb"]}')
    for k in CTYPES:
        e, it = rec['entries'][k], rec['saved_items'][k]
        if e is None or it is None:
            expect(f'{label}: {k} cache saved and has entries (entries={e}, saved={it})', False)
            continue
        want = e if (n == 0 or n >= e) else n
        expect(f'{label}: {k} saved items == min(N,live) = {want} (saved {it}, live {e})', it == want)
    return rec


def stress(args, tag):
    rc, out = sh(f'tools/bin/cassandra-stress {args} -node {ADDR} -rate threads=50 -log file={LOGS}/stress-{tag}.log', timeout=1800, check=False, quiet=True)
    open(f'{LOGS}/stress-{tag}.out', 'w').write(out)
    keep = [l for l in out.splitlines() if re.search(r'Op rate|Total errors|Partition rate|Total partitions|Running time', l)]
    note(f'stress {tag} rc={rc}: ' + ' | '.join(l.strip() for l in keep[:5]))
    return rc


def cql(stmt):
    return sh(f'bin/cqlsh {ADDR} 9042 -e "{stmt}"', timeout=120, check=False, quiet=True)


def populate(first):
    if first:
        rc = stress(f'write n={N_ROWS} -pop seq=1..{N_ROWS}', 'write')
        cql("ALTER TABLE keyspace1.standard1 WITH caching = {'keys':'ALL','rows_per_partition':'ALL'}")
        nodetool('flush')
        stress('counter_write n=1 -pop seq=1..1', 'counter-create')
    rc, out = sh(f'python3 {HARNESS}/reader.py {ADDR}', timeout=1800, check=False, env=dict(os.environ, CASSANDRA_HOME=C))
    note('reader: ' + out.strip().splitlines()[-1][:200] if out.strip() else 'reader: no output')
    stress(f'counter_write n={N_ROWS} -pop seq=1..{N_ROWS}', 'counter' + ('1' if first else 'x'))


def set_keys(a, b, c):
    nodetool(f'setcachekeystosave {a} {b} {c}')
    note(f'nodetool setcachekeystosave {a} {b} {c}')


def run_main():
    shutil.rmtree('/dev/shm/s4-b8-kt', ignore_errors=True)
    os.makedirs(W, exist_ok=True)
    phases = {}
    # ---- L1
    note('=== L1: yaml keys_to_save unset')
    make_conf({})
    start_node()
    populate(True)
    inf = info()
    note(f'populated: entries {[(k, inf.get(k, {}).get("entries")) for k in CTYPES]}')
    expect('key cache populated (entries >= 100000)', (inf.get('key', {}).get('entries') or 0) >= 100000)
    expect('row cache populated (entries >= 100000)', (inf.get('row', {}).get('entries') or 0) >= 100000)
    expect('counter cache populated (entries >= 100000)', (inf.get('counter', {}).get('entries') or 0) >= 100000)
    phases['all'] = phase('all(yaml unset)', 0)
    for n in (10000, 100, 0):
        set_keys(n, n, n)
        phases[f'rt{n}'] = phase(f'runtime {n}', n)
    # capacity control (C3): keys_to_save 0, key cache capacity 8 MiB
    nodetool('setcachecapacity 8 100 50'); note('nodetool setcachecapacity 8 100 50')
    phases['cap8'] = phase('capacity 8 MiB, N=0', 0)
    nodetool('setcachecapacity 200 100 50')
    set_keys(100, 100, 100)
    phases['rt100b'] = phase('runtime 100 (before restart)', 100)
    stop_node()
    # ---- L2
    for label, n, extra in (('yaml100', 100, 3), ('yaml10000', 10000, 3)):
        note(f'=== {label}: restart with yaml keys_to_save {n}')
        make_conf({'key_cache_keys_to_save': n, 'row_cache_keys_to_save': n, 'counter_cache_keys_to_save': n})
        start_node()
        time.sleep(40)  # warm load of the saved files (cache_load_timeout 30s)
        inf = info()
        note(f'{label}: entries after warm load: ' + str({k: inf.get(k, {}).get('entries') for k in CTYPES}))
        phases[label + '_warm'] = {k: inf.get(k, {}).get('entries') for k in CTYPES}
        populate(False)
        phases[label] = phase(label, n)
        stop_node()
    # ---- L4 no-save control
    note('=== L4: save periods 0, saved_caches emptied')
    shutil.rmtree(W + '/saved_caches', ignore_errors=True)
    make_conf({'key_cache_save_period': '0s', 'row_cache_save_period': '0s', 'counter_cache_save_period': '0s'})
    start_node()
    time.sleep(40)
    inf0 = info()
    note('nosave baseline: entries after start with no saved files (the node\'s own system-keyspace reads), before the workload: ' + str({k: inf0.get(k, {}).get('entries') for k in CTYPES}))
    populate(False)
    off = syslog_size()
    time.sleep(2 * PERIOD + 5)
    fs = files()
    inf = info()
    note(f'nosave: files={fs} saved lines={saved_since(off)} entries={[(k, inf.get(k, {}).get("entries")) for k in CTYPES]}')
    expect('nosave control: caches populated but no saved file is created', not fs and (inf.get('key', {}).get('entries') or 0) > 1000)
    stop_node()
    cross(phases)


def cross(ph):
    """cross-phase relations of B3f"""
    allp = ph.get('all')
    if not allp:
        return
    for k in CTYPES:
        base = allp['file_bytes'][k]
        live = allp['entries'][k]
        for lab in ('rt10000', 'rt100', 'rt0', 'yaml100', 'yaml10000'):
            p = ph.get(lab)
            if not p or not base or not p['file_bytes'].get(k) or not live:
                continue
            n = p['N']; want = (live if n == 0 or n >= live else n) / live
            ratio = p['file_bytes'][k] / base
            expect(f'cross {k} {lab}: file/file(all) = {ratio:.4f} within 20% of items/live = {want:.4f} (+0.002 abs for tiny)', abs(ratio - want) <= 0.2 * want + 0.002)
    for k in CTYPES:
        es = [ph[l]['entries'][k] for l in ('all', 'rt10000', 'rt100', 'rt0', 'rt100b') if l in ph and ph[l]['entries'].get(k) is not None]
        if es:
            expect(f'cross {k}: live entries unchanged by N across runtime phases (min {min(es)}, max {max(es)})', max(es) - min(es) <= 0.01 * max(es))
    hs = [ph[l]['heap_used_mb'] for l in ('all', 'rt10000', 'rt100', 'rt0') if l in ph and ph[l].get('heap_used_mb')]
    if hs:
        expect(f'cross: steady heap (after GC) differs < 5% between runtime phases (min {min(hs)}, max {max(hs)} MB)', (max(hs) - min(hs)) <= 0.05 * max(hs))
    rs = [ph[l]['rss_anon_mb'] for l in ('all', 'rt10000', 'rt100', 'rt0') if l in ph and ph[l].get('rss_anon_mb')]
    if rs:
        expect(f'cross: RssAnon differs < 5% between runtime phases (min {min(rs)}, max {max(rs)} MB)', (max(rs) - min(rs)) <= 0.05 * max(rs))
    c = ph.get('cap8')
    if c and c['entries'].get('key') is not None:
        expect(f'capacity control: key cache entries fall with key_cache_size (8 MiB): {c["entries"]["key"]} < {allp["entries"]["key"]}', c['entries']['key'] < allp['entries']['key'])


def main():
    note(f'cluster-run {RUN} {MODE} start {time.strftime("%FT%T%z")} host {os.uname().nodename}')
    left = daemons()
    note('daemons before: ' + (left or 'none (own start not yet)'))
    try:
        if MODE == 'main':
            run_main()
        else:
            sys.exit('mode ' + MODE)
    except SystemExit:
        raise
    except Exception as e:
        note('EXCEPTION: ' + repr(e)[:600])
        stop_node(); raise
    finally:
        stop_node()
        note('daemons after: ' + (daemons() or 'none'))
        for f in ('system.log', 'stdout.txt'):
            try: shutil.copy(f'{W}/logs/{f}' if f == 'system.log' else f'{W}/{f}', f'{LOGS}/{f}')
            except OSError: pass
        note(f'EXPECTED totals: yes={EXP["yes"]} no={EXP["no"]}')


main()
