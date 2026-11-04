#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of range_tombstone_list_growth_factor-<A|G|N> autonomous cases (case-file sha256 in the results
file §1; audit amendments R1-R7 = section B5 of the case file).
usage: cluster-run.py <A|G|N> all | down | <lifetime-label>...
  A = addInternal-capacity (tree ~/cassandra-rtl-a), G = growToFree-newLength (~/cassandra-rtl-g), N = grow-newLength (~/cassandra-rtl-n)
  all    every lifetime of that case in order (a background job); down: stop this harness's node.
Per lifetime (a fresh data directory): conf (R4/R5), start with the Byteman growth trace, schema, autocompaction off (R7); per cell:
set/confirm the factor, baseline histogram, load with checkpoints, per checkpoint: JMX metrics + class histogram + RssAnon, the 2-s
counter series and the 250-ms heap poll alongside. Each checkpoint appends one JSON line to cells.jsonl. The analysis is cluster-analyze.py.
Env: RTL_RUN (run1), RTL_SCALE (1; divides every per-partition count, a shakedown knob), RTL_ONLY (comma list of lifetime labels)."""
import json, os, re, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
H = os.path.dirname(os.path.abspath(__file__))
CASE = sys.argv[1] if len(sys.argv) > 1 else ''
MODE = sys.argv[2] if len(sys.argv) > 2 else ''
if CASE not in ('A', 'G', 'N') or not MODE:
    sys.exit(__doc__)
T = {'A': 'a', 'G': 'g', 'N': 'n'}[CASE]
RUNNAME = os.environ.get('RTL_RUN', 'run1')
SCALE = int(os.environ.get('RTL_SCALE', 1))
C = os.environ.get('CASSANDRA_HOME', f'{HOME}/cassandra-rtl-{T}')
RUN = os.environ.get('RTL_DIR', f'{HOME}/stage4-rtl-{T}')
PORTS = {'A': (7210, 7211, 9242, 7399), 'G': (7220, 7221, 9252, 7499), 'N': (7230, 7231, 9262, 7599)}[CASE]
STORAGE, SSL, NATIVE, JMX = PORTS
LOGS = f'{HOME}/stage4-logs/rtl/{T}/{RUNNAME}/cluster'
BYTEMAN = f'{C}/build/lib/jars/byteman-4.0.20.jar'
SVC = 'org.apache.cassandra.db:type=StorageService'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
ENV = dict(os.environ, CASSANDRA_CONF=RUN + '/conf', CASSANDRA_LOG_DIR=RUN + '/logs', MAX_HEAP_SIZE='8G', CASSANDRA_HOME=C)
ENV.pop('HEAP_NEWSIZE', None)


def S(n):                              # per-partition counts, scaled down only by the shakedown knob
    return max(1, n // SCALE)


# ---- the design (case-file B3, as amended: R4, R5) ------------------------------------------------------------------
# a cell: label, factor, via ('yaml' | 'jmx'), table, kind, partitions P, checkpoints (per-partition counts), sink (None | 'jmx-after')
def cell(label, f, via, table, kind, P, cps, **kw):
    d = dict(label=label, f=f, via=via, table=table, kind=kind, P=P, cps=[S(c) for c in cps]); d.update(kw); return d


if CASE == 'A':
    MAIN = '2048MiB'
    CP50 = [5000, 10000, 20000, 50000]
    def A(label, f, shape, **kw):
        P, cps = {'M': (10, CP50), 'S1': (1, CP50), 'S100': (100, [500, 1000, 2000, 5000])}[shape]
        return dict(label=label, space=kw.pop('space', MAIN), cells=[cell(label, f, kw.pop('via', 'yaml'), 't', 'del1', P, cps, **kw)])
    LIFETIMES = [A('M-1.2-r1', 1.2, 'M'), A('M-5.0-r1', 5.0, 'M'), A('M-1.5-r1', 1.5, 'M'),
                 A('S1-1.2', 1.2, 'S1'), A('S1-5.0', 5.0, 'S1'), A('S100-1.2', 1.2, 'S100'), A('S100-5.0', 5.0, 'S100'),
                 A('J-1.2to5.0', 1.2, 'M', jmx_to=5.0),
                 A('C-1.5-128MiB', 1.5, 'M', space='128MiB', control=True),
                 A('M-1.5-r2', 1.5, 'M'), A('M-5.0-r2', 5.0, 'M'), A('M-1.2-r2', 1.2, 'M')]
elif CASE == 'G':
    MAIN = '3072MiB'
    CPG = [10000, 25000, 50000]
    def G(label, f, **kw):
        return dict(label=label, space=kw.pop('space', MAIN), cells=[cell(label, f, 'jmx', kw.pop('table', 't'), kw.pop('kind', 'del4'), 20, CPG, **kw)])
    LIFETIMES = [G('F-1.2', 1.2), G('F-1.5', 1.5), G('F-5.0', 5.0),
                 G('C-ins-64MiB', 1.5, space='64MiB', table='t2', kind='ins', control=True)]
else:
    MAIN = '3072MiB'
    CPN = [5000, 10000, 20000]
    order = [1.2, 5.0, 1.5, 2.0, 2.0, 1.5, 5.0, 1.2]
    cells = [cell(f'F-{f}-{i + 1}', f, 'jmx', 't', 'del4', 50, CPN) for i, f in enumerate(order)]
    cells.append(cell('INS-1.5', 1.5, 'jmx', 't2', 'ins', 50, CPN, control_table=True))
    LIFETIMES = [dict(label='L1', space=MAIN, cells=cells),
                 dict(label='C-1.5-256MiB', space='256MiB', cells=[cell('C-1.5-256MiB', 1.5, 'yaml', 't', 'del4', 50, CPN, control=True)])]

MODE_LABELS = None if MODE in ('all', 'down') else sys.argv[2:]
ONLY = os.environ.get('RTL_ONLY')


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, flush=True)
    SESSION.write(line + '\n'); SESSION.flush()


def now_ms():
    return int(time.time() * 1000)


def sh(cmd, timeout=900, check=True, quiet=False, cwd=None):
    log('+ ' + cmd[:300])
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=ENV, cwd=cwd or C)
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


def daemons():
    # this harness's daemons only (the same host may run another case's node): match this run directory in the arguments
    _, out = sh("ps -eo pid,args | grep -E '^ *[0-9]+ [^ ]*java .*CassandraDaemon' || true", check=False, quiet=True)
    return [l for l in out.splitlines() if l.strip() and RUN + '/' in l]


def node_pid():
    try:
        pid = int(open(RUN + '/cassandra.pid').read().strip())
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except (OSError, ValueError):
        return None


def nodetool(args, timeout=300, check=False):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} {args}', timeout=timeout, check=check, quiet=True)


def jmx_get(*pairs):
    rc, out = sh(f'java -cp {RUN}/tools Jmx {JMX} get ' + ' '.join(f'"{p}"' for p in pairs), check=False, quiet=True, timeout=120)
    vals = {}
    for l in out.splitlines():
        if l.count('|') >= 2:
            b, a, v = l.split('|', 2)
            vals[(b, a)] = v.strip()
    return vals


def tbl(table, name):
    return f'org.apache.cassandra.metrics:type=Table,keyspace=ks,scope={table},name={name}'


def get_factor():
    return jmx_get(SVC, 'RangeTombstoneResizeListGrowthFactor').get((SVC, 'RangeTombstoneResizeListGrowthFactor'))


def set_factor(f):
    rc, out = sh(f'java -cp {RUN}/tools Jmx {JMX} setdouble "{SVC}" setRangeTombstoneListResizeGrowthFactor {f}', check=False, quiet=True)
    return out.strip()


def stop_node():
    pid = node_pid()
    if pid is None:
        return
    log(f'stopping node pid {pid}')
    sh(f'kill {pid}', check=False)
    for _ in range(180):
        if not os.path.exists(f'/proc/{pid}'):
            log('node stopped'); return
        time.sleep(1)
    sh(f'kill -9 {pid}', check=False); time.sleep(2)


def make_conf(label, f, space):
    conf = RUN + '/conf'
    sh(f'rm -rf {conf} && cp -r {C}/conf {conf}')
    lines = {
        'cluster_name': f"'rtl-{T}'",
        'data_file_directories': f'\n    - {RUN}/data',
        'commitlog_directory': f'{RUN}/commitlog', 'hints_directory': f'{RUN}/hints',
        'saved_caches_directory': f'{RUN}/saved_caches', 'cdc_raw_directory': f'{RUN}/cdc_raw',
        'listen_address': '127.0.0.1', 'rpc_address': '127.0.0.1',
        'seed_provider': f'\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: "127.0.0.1:{STORAGE}"',
        'storage_port': str(STORAGE), 'ssl_storage_port': str(SSL), 'native_transport_port': str(NATIVE),
        'memtable_allocation_type': 'heap_buffers', 'memtable_heap_space': space,
        'autocompaction_on_startup_enabled': 'false',                       # R7
        'range_tombstone_list_growth_factor': str(f),                       # the knob, from the yaml (a jmx cell then changes it)
        'native_transport_timeout': '60s',
    }
    if CASE in ('A', 'G'):
        lines['tombstone_failure_threshold'] = '1000000' if CASE == 'G' else '100000'
    out, skip = [], False
    for l in open(C + '/conf/cassandra.yaml').read().splitlines():
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
    out.append(f'# ---- stage4 rtl-{T} (B3a, R4, R5, R7) ----')
    out += [f'{k}: {v}' for k, v in lines.items()]
    open(conf + '/cassandra.yaml', 'w').write('\n'.join(out) + '\n')
    env = open(conf + '/cassandra-env.sh').read()
    assert env.count('JMX_PORT="7199"') == 1
    open(conf + '/cassandra-env.sh', 'w').write(env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"'))
    with open(conf + '/jvm11-server.options', 'a') as fo:
        fo.write(f'\n# stage4 rtl-{T}\n-XX:-HeapDumpOnOutOfMemoryError\n-Xlog:gc*:file={RUN}/logs/gc-{label}.log:time,uptime:filecount=10,filesize=100M\n')
        fo.write(f'-javaagent:{BYTEMAN}=script:{H}/growth.btm\n-Dstage4.trace={RUN}/logs/rtl-{label}.trace\n')
    log(f'conf {label}: ' + '; '.join(f'{k}={v.strip()}' for k, v in lines.items() if '\n' not in v))


def start_node(label):
    if node_pid() is not None or daemons():
        raise RuntimeError('a CassandraDaemon is already running: ' + str(daemons()))
    sh(f'bash -c "ulimit -n 100000; bin/cassandra -p {RUN}/cassandra.pid > {RUN}/logs/start-{label}.out 2>&1"')
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(3)
        if node_pid() is None and time.time() - t0 > 15:
            raise RuntimeError('daemon died during start: ' + open(f'{RUN}/logs/start-{label}.out', errors='replace').read()[-800:])
        rc, out = nodetool('status', timeout=60)
        if re.search(r'^UN\s+127\.0\.0\.1', out, re.M):
            rc2, out2 = nodetool('statusbinary', timeout=60)
            if 'running' in out2:
                log(f'node up ({label}) after {time.time() - t0:.0f} s, pid {node_pid()}')
                return node_pid()
    raise RuntimeError('node did not come up')


def client(args, timeout=7200):
    rc, out = sh(f'python3 -I {H}/client.py {args}', timeout=timeout, check=False, quiet=True)
    last = [l for l in out.splitlines() if l.startswith('{')]
    return json.loads(last[-1]) if last else {'error': out[-500:]}


HISTO_ROWS = {'ClusteringBound[]': '[Lorg.apache.cassandra.db.ClusteringBound;', 'BufferClusteringBound': 'org.apache.cassandra.db.BufferClusteringBound',
              'long[]': '[J', 'int[]': '[I', 'byte[]': '[B', 'RangeTombstoneList': 'org.apache.cassandra.db.RangeTombstoneList'}


def histogram(pid, dest):
    sh(f'jcmd {pid} GC.class_histogram > {dest}', timeout=600, check=False, quiet=True)
    res = {}
    for l in open(dest, errors='replace'):
        p = l.split()
        if len(p) >= 4 and p[0].endswith(':'):          # array rows carry a trailing '(java.base@11...)' module column
            for k, name in HISTO_ROWS.items():
                if p[3] == name:
                    res[k] = (int(p[1]), int(p[2]))
        elif p and p[0] == 'Total':
            res['total'] = (int(p[1]), int(p[2]))
    return res


def rss_anon(pid):
    for l in open(f'/proc/{pid}/status'):
        if l.startswith('RssAnon'):
            return int(l.split()[1]) * 1024
    return None


def syslog_size():
    try:
        return os.path.getsize(RUN + '/logs/system.log')
    except OSError:
        return 0


def run_cell(life, c, pid, writer):
    label, table = c['label'], c['table']
    d = f'{LOGS}/{label}'; os.makedirs(d, exist_ok=True)
    if c['via'] == 'jmx':
        r = set_factor(c['f']); log(f'{label}: set f={c["f"]} over JMX: {r}')
    got = get_factor(); log(f'{label}: factor read back over JMX: {got}')
    if c.get('jmx_to'):
        r = set_factor(c['jmx_to']); got2 = get_factor(); log(f'{label}: runtime change to {c["jmx_to"]}: {r}; read back {got2}')
        got = got2
    nodetool('flush ks', timeout=600)
    time.sleep(2)
    m = tbl(table, 'MemtableOnHeapDataSize'), tbl(table, 'MemtableColumnsCount'), tbl(table, 'MemtableSwitchCount')
    def metrics():
        v = jmx_get(m[0], 'Value', m[1], 'Value', m[2], 'Count')
        return dict(counter=v.get((m[0], 'Value')), columns=v.get((m[1], 'Value')), switch=v.get((m[2], 'Count')))
    trace_off = os.path.getsize(f'{RUN}/logs/rtl-{life["label"]}.trace') if os.path.exists(f'{RUN}/logs/rtl-{life["label"]}.trace') else 0
    base = metrics(); hb = histogram(pid, f'{d}/histo-base.txt')
    rec = dict(kind='base', case=CASE, life=life['label'], cell=label, factor_set=c['f'], factor_read=got, via=c['via'], space=life['space'], table=table,
               load=c['kind'], P=c['P'], t_ms=now_ms(), metrics=base, histo=hb, rss_anon=rss_anon(pid), control=bool(c.get('control')))
    writer(rec)
    log(f'{label}: base {base} histo ClusteringBound[] {hb.get("ClusteringBound[]")} total {hb.get("total")}')
    stop = f'{d}/stop'
    if os.path.exists(stop): os.remove(stop)
    series = open(f'{d}/series.csv', 'w')
    pol = subprocess.Popen(f'exec java -cp {RUN}/tools Jmx {JMX} poll 2000 {stop} "{m[0]}" Value "{m[2]}" Count', shell=True, stdout=series, env=ENV)
    heap = open(f'{d}/heap.txt', 'w')
    hp = subprocess.Popen(f'exec java -cp {RUN}/tools HeapPoll {JMX} 250 0', shell=True, stdout=heap, env=ENV)
    prev, total_ok, total_err = 0, 0, 0
    for k, cp in enumerate(c['cps']):
        t0 = now_ms()
        r = client(f'load 127.0.0.1 {NATIVE} {c["kind"]} {table} 0 {c["P"]} {prev} {cp} {c["P"]}')
        t1 = now_ms()
        total_ok += r.get('ok', 0); total_err += r.get('errors', 0) + (1 if 'error' in r else 0)
        log(f'{label}: checkpoint {k + 1}: per-partition {prev}->{cp}: {r}')
        time.sleep(1)
        mt = metrics(); h = histogram(pid, f'{d}/histo-cp{k + 1}.txt')
        rec = dict(kind='cp', case=CASE, life=life['label'], cell=label, k=k + 1, per_partition=cp, tombstones=cp * c['P'], writes_ok_total=total_ok,
                   write_errors_total=total_err, load=r, t_start_ms=t0, t_end_ms=t1, t_ms=now_ms(), metrics=mt, histo=h, rss_anon=rss_anon(pid), factor_read=get_factor())
        writer(rec)
        log(f'{label}: cp{k + 1} counter {mt["counter"]} columns {mt["columns"]} switch {mt["switch"]}; ClusteringBound[] {h.get("ClusteringBound[]")} BufferClusteringBound {h.get("BufferClusteringBound")} total {h.get("total")}')
        prev = cp
    open(stop, 'w').write('stop')
    time.sleep(3)
    hp.terminate(); hp.wait(); pol.wait(timeout=30); series.close(); heap.close()
    selc = client(f'select 127.0.0.1 {NATIVE} {table} 0')
    nodetool('flush ks', timeout=600)
    _, du = sh(f'du -sb {RUN}/data', check=False, quiet=True)
    tr = RUN + f'/logs/rtl-{life["label"]}.trace'
    seg = ''
    if os.path.exists(tr):
        with open(tr, errors='replace') as f:
            f.seek(trace_off); seg = f.read()
    open(f'{d}/growth-trace.txt', 'w').write(seg)
    writer(dict(kind='end', case=CASE, life=life['label'], cell=label, select=selc, du_bytes=du.split()[0] if du else None, trace_lines=len(seg.splitlines()), t_ms=now_ms(), metrics=metrics()))
    log(f'{label}: done; select {selc}; trace lines {len(seg.splitlines())}; data {du.split()[0] if du else "?"} B')


def lifetime(life):
    label = life['label']
    f0 = life['cells'][0]['f']
    sh(f'rm -rf {RUN}/data {RUN}/commitlog {RUN}/hints {RUN}/saved_caches {RUN}/cdc_raw && mkdir -p {RUN}/data {RUN}/commitlog {RUN}/hints {RUN}/saved_caches {RUN}/cdc_raw')
    make_conf(label, f0, life['space'])
    off = syslog_size()
    pid = start_node(label)
    r = client(f'schema 127.0.0.1 {NATIVE}'); log(f'schema: {r}')
    nodetool('disableautocompaction ks', timeout=120)
    ms = jmx_get('org.apache.cassandra.db:type=CompactionManager', 'CompletedTasks')
    jf = open(LOGS + '/cells.jsonl', 'a')
    def writer(rec):
        jf.write(json.dumps(rec) + '\n'); jf.flush()
    writer(dict(kind='life', case=CASE, life=label, pid=pid, space=life['space'], heap='8G', syslog_offset=off, t_ms=now_ms(),
                factor_read=get_factor(), cells=[c['label'] for c in life['cells']]))
    for c in life['cells']:
        run_cell(life, c, pid, writer)
    with open(RUN + '/logs/system.log', 'rb') as f:
        f.seek(off); seg = f.read()
    open(f'{LOGS}/system-{label}.log', 'wb').write(seg)
    txt = seg.decode(errors='replace')
    errs = [l for l in txt.splitlines() if l.startswith('ERROR') or 'java.lang.OutOfMemoryError' in l]
    writer(dict(kind='syslog', case=CASE, life=label, error_lines=len(errs), first_errors=errs[:5], oom=any('OutOfMemoryError' in l for l in errs), t_ms=now_ms()))
    log(f'{label}: system.log ERROR/OOM lines: {len(errs)} {errs[:2]}')
    stop_node()
    sh(f'cp {RUN}/logs/gc-{label}.log {LOGS}/ 2>/dev/null; cp {RUN}/logs/rtl-{label}.trace {LOGS}/ 2>/dev/null; cp {RUN}/conf/cassandra.yaml {LOGS}/cassandra-{label}.yaml; true', check=False)
    jf.close()


def main():
    if MODE == 'down':
        stop_node(); log('daemons left: ' + str(daemons())); return
    log(f'cluster-run {CASE} {RUNNAME}: RUN={RUN} tree={C} scale={SCALE} lifetimes={[l["label"] for l in LIFETIMES]}')
    sh('git describe --tags; git rev-parse --short HEAD; java -version 2>&1 | head -1; uname -r; df -h ' + HOME, check=False)
    _, ss = sh('ss -ltn', check=False, quiet=True)
    busy = [str(p) for p in PORTS if re.search(rf':{p}\s', ss)]
    if busy or daemons():
        raise RuntimeError(f'ports busy {busy} or daemons {daemons()}')
    sh(f'mkdir -p {RUN}/logs {RUN}/tools && javac -d {RUN}/tools {H}/Jmx.java {H}/HeapPoll.java')
    wanted = MODE_LABELS or ([x for x in ONLY.split(',')] if ONLY else None)
    for life in LIFETIMES:
        if wanted and life['label'] not in wanted:
            continue
        lifetime(life)
    log('all lifetimes done')


try:
    main()
except Exception as e:
    log(f'ABORT: {e!r}')
    raise
finally:
    if MODE != 'down':
        stop_node()
        log('daemons left: ' + str(daemons()))
        open(LOGS + '/done', 'w').write(time.strftime('%F %T') + '\n')
