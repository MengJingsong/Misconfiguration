#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of compression-metadata-writer-addOffset-maxCount--autonomous (case file as amended 2026-10-26).
usage: cluster-run.py <arm>     arms: M (main: load 4 compressed keyspaces + 1 uncompressed one, flush, compact, restart; Byteman trace)
                                      C48 / C96 (positive control: chunk cache on, file_cache_size 48 / 96 MiB, on M's data directory)
  One node lifetime per call (M has two: before and after the restart). Ports: JMX 7329, Byteman 9329, native 9351, storage 7029,
  loopback 127.0.29.1. Data and logs of the node on tmpfs: /dev/shm/s4-cm-data. Output: ~/s4-cm-logs/<CM_RUN>/<arm>/ (summary.txt
  with EXPECTED lines, session.log, samples). The node is stopped by pid on any exit.
"""
import glob, os, re, shlex, shutil, struct, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-cm')
D = '/dev/shm/s4-cm-data'
RUN = os.environ.get('CM_RUN', 'run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
ADDR, JMX, BTM_PORT, NATIVE, STORAGE = '127.0.29.1', 7329, 9329, 9351, 7029
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
JMXCP = HOME + '/s4-cm-jmx'
ROWS, UROWS = int(os.environ.get('CM_ROWS', 400000)), int(os.environ.get('CM_UROWS', 100000))
KS = [64, 16, 4, 1]
arm = sys.argv[1] if len(sys.argv) > 1 else ''
if arm not in ('M', 'C48', 'C96'):
    sys.exit(__doc__)
LOGS = f'{HOME}/s4-cm-logs/{RUN}/{arm}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a')
EXPECT = {'yes': 0, 'no': 0}


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=3000, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1200:]}')
    return r.returncode, out


def expect(desc, cond):
    EXPECT['yes' if cond else 'no'] += 1
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def pid():
    try:
        p = int(open(f'{D}/cassandra.pid').read().strip())
        cmd = open(f'/proc/{p}/cmdline').read().replace('\0', ' ')
        return p if 'CassandraDaemon' in cmd and D in cmd else None
    except (ValueError, OSError):
        return None


def stop_node():
    p = pid()
    if p is None:
        return
    sh(f'bin/nodetool -p {JMX} stopdaemon', check=False, timeout=180)
    for _ in range(120):
        if pid() is None:
            return
        time.sleep(1)
    log(f'node did not stop; kill -9 {p}')
    subprocess.run(['kill', '-9', str(p)])
    time.sleep(2)


def fail(msg):
    note('FAIL: ' + msg)
    stop_node()
    sys.exit(1)


def busy():
    out = sh('ss -ltn', check=False, quiet=True)[1]
    return [p for p in (f'127.0.0.1:{JMX}', f'*:{JMX}', f'127.0.0.1:{BTM_PORT}', f'{ADDR}:{NATIVE}', f'{ADDR}:{STORAGE}') if re.search(r'\s' + re.escape(p) + r'\s', out)]


def make_conf(cache_mib):
    N = D
    for sub in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
        os.makedirs(f'{N}/{sub}', exist_ok=True)
    shutil.rmtree(N + '/conf', ignore_errors=True)
    shutil.copytree(C + '/conf', N + '/conf')
    env = subprocess.run(['git', '-C', C, 'show', 'HEAD:conf/cassandra-env.sh'], capture_output=True, text=True, check=True).stdout
    env2 = env.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"')
    if env2 == env:
        fail('JMX_PORT line not replaced')
    open(N + '/conf/cassandra-env.sh', 'w').write(env2)
    jvm = subprocess.run(['git', '-C', C, 'show', 'HEAD:conf/jvm11-server.options'], capture_output=True, text=True, check=True).stdout
    open(N + '/conf/jvm11-server.options', 'w').write(jvm + '\n# stage4 cm (B3a)\n-Xms2G\n-Xmx2G\n')
    add = ['cluster_name: stage4-cm', 'num_tokens: 1', 'endpoint_snitch: SimpleSnitch', f'listen_address: {ADDR}', f'rpc_address: {ADDR}',
           f'storage_port: {STORAGE}', f'native_transport_port: {NATIVE}', 'seed_provider:',
           '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider', '    parameters:', f'      - seeds: "{ADDR}:{STORAGE}"',
           'data_file_directories:', f'    - {N}/data', f'commitlog_directory: {N}/commitlog', f'hints_directory: {N}/hints',
           f'saved_caches_directory: {N}/saved_caches', f'cdc_raw_directory: {N}/cdc_raw', 'auto_snapshot: false',
           'autocompaction_on_startup_enabled: false', 'native_transport_timeout: 60000ms', 'write_request_timeout: 30000ms']
    if cache_mib:
        add += ['file_cache_enabled: true', f'file_cache_size: {cache_mib}MiB']
    keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
    out, skip = [], False
    for l in subprocess.run(['git', '-C', C, 'show', 'HEAD:conf/cassandra.yaml'], capture_output=True, text=True, check=True).stdout.splitlines():
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
    open(N + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 cm lines ----\n' + '\n'.join(add) + '\n')
    note(f'yaml: file_cache_enabled={"true, file_cache_size " + str(cache_mib) + "MiB" if cache_mib else "default (false)"}, heap 2G, JMX {JMX}, native {NATIVE}, storage {STORAGE}, {ADDR}, data {N}')


def start_node(trace=None):
    left = busy()
    if left:
        fail('ports busy before start: %s' % left)
    extra = ''
    if trace:
        extra = (f'-javaagent:{BYTEMAN}=boot:{BYTEMAN},script:{HARNESS}/cm.btm,listener:true,port:{BTM_PORT} '
                 f'-Dorg.jboss.byteman.verbose=false -Dcm.trace={trace}')
    env = dict(os.environ, CASSANDRA_CONF=D + '/conf', CASSANDRA_LOG_DIR=D + '/logs', JVM_EXTRA_OPTS=extra)
    note('JVM_EXTRA_OPTS: ' + (extra or '(none)'))
    sh(f"bash -c 'ulimit -n 100000 && exec bin/cassandra -p {D}/cassandra.pid' > {D}/stdout.txt 2>&1", env=env)
    for _ in range(40):
        time.sleep(1)
        if pid() is not None:
            break
    else:
        fail('node did not start; see ' + D + '/stdout.txt')
    t0 = time.time()
    while time.time() - t0 < 300:
        if pid() is None:
            fail('node died during start')
        _, st = nt('status', check=False, quiet=True)
        _, sb = nt('statusbinary', check=False, quiet=True)
        if re.search(r'^UN\s+' + re.escape(ADDR), st, re.M) and re.search(r'^running\s*$', sb, re.M):
            log(f'UN and serving after {time.time() - t0:.0f} s')
            return
        time.sleep(3)
    fail('node not UN within the timeout')


def nt(*a, **k):
    return sh(f'bin/nodetool -p {JMX} ' + ' '.join(str(x) for x in a), **k)


def cql(text):
    open(LOGS + '/cql.tmp', 'w').write(text)
    sh(f'bin/cqlsh {ADDR} {NATIVE} -f {LOGS}/cql.tmp')


def stress(*a, label):
    out = LOGS + f'/stress-{label}.txt'
    rc, txt = sh(f'tools/bin/cassandra-stress ' + ' '.join(shlex.quote(x) for x in a) + f' -node {ADDR} -port native={NATIVE} jmx={JMX} -mode native cql3 > {out} 2>&1; tail -c 3000 {out}', check=False)
    full = open(out, errors='replace').read()
    errs = re.search(r'Total errors\s*:\s*(\d+)', full)
    expect(f'stress {label} finished with 0 errors', bool(errs) and errs.group(1) == '0')
    return full


def jget(bean, attr):
    rc, out = sh(f'java -cp {JMXCP} Jmx {JMX} get {bean} {attr}', check=False, quiet=True)
    for l in out.splitlines():
        p = l.split('|')
        if len(p) == 3:
            return p[2]
    return None


def metric(ks):
    v = jget(f'org.apache.cassandra.metrics:type=Table,keyspace={ks},scope=standard1,name=CompressionMetadataOffHeapMemoryUsed', 'Value')
    return int(v) if v is not None else None


def ci_files(ks):
    return sorted(glob.glob(f'{D}/data/{ks}/standard1-*/*-CompressionInfo.db'))


def ci_header(path):
    """CompressionMetadata.Writer.writeHeader layout (CompressionMetadata.java:375-395): UTF name, int n, n x (UTF k, UTF v), int chunkLength,
    int maxCompressedLength, long dataLength, int chunks, then chunks x long."""
    b = open(path, 'rb').read()
    o = 0
    (l,) = struct.unpack('>H', b[o:o + 2]); o += 2 + l
    (n,) = struct.unpack('>i', b[o:o + 4]); o += 4
    for _ in range(2 * n):
        (l,) = struct.unpack('>H', b[o:o + 2]); o += 2 + l
    chunk_len, max_comp, data_len, chunks = struct.unpack('>iiqi', b[o:o + 20]); o += 20
    return dict(chunk_len=chunk_len, data_len=data_len, chunks=chunks, size=len(b), body=len(b) - o)


def census(tag):
    """metric and header counts per keyspace; returns {ks: (metric, sum_chunks, nfiles)}"""
    res = {}
    for k in KS:
        ks = f'ks{k}'
        files = ci_files(ks)
        hs = [ci_header(f) for f in files]
        m = metric(ks)
        tot = sum(h['chunks'] for h in hs)
        for f, h in zip(files, hs):
            note(f'CI {tag} {ks} {os.path.basename(f)} chunkLen={h["chunk_len"]} dataLength={h["data_len"]} chunks={h["chunks"]} fileBytes={h["size"]} bodyBytes={h["body"]}')
            if h['body'] != 8 * h['chunks'] or h['chunk_len'] != k * 1024:
                expect(f'{tag} {ks} {os.path.basename(f)}: file body = 8 x chunks and chunk length = {k} KiB', False)
        note(f'METRIC {tag} {ks} CompressionMetadataOffHeapMemoryUsed={m} sstables={len(files)} sumHeaderChunks={tot} eight_x_chunks={8 * tot} dataLengthSum={sum(h["data_len"] for h in hs)}')
        res[ks] = (m, tot, len(files), sum(h['data_len'] for h in hs))
    mu = metric('ksu')
    note(f'METRIC {tag} ksu CompressionMetadataOffHeapMemoryUsed={mu}')
    res['ksu'] = (mu, 0, 0, 0)
    return res


def judge_census(tag, res, nominal=True):
    for k in KS:
        m, tot, nf, dl = res[f'ks{k}']
        expect(f'{tag} ks{k}: metric == 8 x sum of header chunk counts ({m} vs {8 * tot})', m == 8 * tot and tot > 0)
        expect(f'{tag} ks{k}: metric exceeds the 800-byte initial buffer by >= 100x ({m})', m is not None and m >= 80000)
        if nominal:
            nom = 8 * 2.02e9 / (k * 1024)
            expect(f'{tag} ks{k}: metric within +-15% of the nominal {nom:.0f} ({m})', m is not None and 0.85 * nom <= m <= 1.15 * nom)
    for a, b in ((64, 16), (16, 4), (4, 1)):
        r = res[f'ks{b}'][0] / res[f'ks{a}'][0]
        expect(f'{tag} metric(K={b})/metric(K={a}) in [3.4, 4.6] ({r:.3f})', 3.4 <= r <= 4.6)
    expect(f'{tag} uncompressed keyspace metric == 0 ({res["ksu"][0]})', res['ksu'][0] == 0)


def syslog_errors(off):
    n = 0
    p = D + '/logs/system.log'
    if os.path.exists(p):
        with open(p, errors='replace') as f:
            f.seek(off)
            for l in f:
                if l.startswith('ERROR'):
                    n += 1
                    note('SYSLOG ' + l.strip()[:300])
    return n


def logoff():
    p = D + '/logs/system.log'
    return os.path.getsize(p) if os.path.exists(p) else 0


def main_arm():
    shutil.rmtree(D, ignore_errors=True)
    os.makedirs(D)
    if not os.path.exists(JMXCP + '/Jmx.class'):
        os.makedirs(JMXCP, exist_ok=True)
        sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    trace = LOGS + '/cm.trace'
    if os.path.exists(trace):
        os.remove(trace)
    make_conf(0)
    start_node(trace)
    off = logoff()
    ddl = []
    for k in KS:
        ddl.append(f"CREATE KEYSPACE ks{k} WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}};")
        ddl.append(f"CREATE TABLE ks{k}.standard1 (key blob PRIMARY KEY, \"C0\" blob, \"C1\" blob, \"C2\" blob, \"C3\" blob, \"C4\" blob) "
                   f"WITH compression = {{'class': 'LZ4Compressor', 'chunk_length_in_kb': '{k}'}};")
    ddl.append("CREATE KEYSPACE ksu WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};")
    ddl.append('CREATE TABLE ksu.standard1 (key blob PRIMARY KEY, "C0" blob, "C1" blob, "C2" blob, "C3" blob, "C4" blob) '
               "WITH compression = {'enabled': 'false'};")
    cql('\n'.join(ddl) + '\n')
    for ks in [f'ks{k}' for k in KS] + ['ksu']:
        nt('disableautocompaction', ks, 'standard1')
    note(f'EPOCH_MS load-start {int(time.time() * 1000)}')
    for k in KS:
        stress('write', f'n={ROWS}', '-col', 'size=FIXED(1000)', '-rate', 'threads=16', '-schema', f'keyspace=ks{k}', label=f'write-ks{k}')
        nt('flush', f'ks{k}')
    stress('write', f'n={UROWS}', '-col', 'size=FIXED(1000)', '-rate', 'threads=16', '-schema', 'keyspace=ksu', label='write-ksu')
    nt('flush', 'ksu')
    time.sleep(3)
    note(f'EPOCH_MS load-end {int(time.time() * 1000)}')
    r1 = census('after-flush')
    judge_census('after-flush', r1)
    note(f'EPOCH_MS compact-start {int(time.time() * 1000)}')
    for k in KS:
        nt('compact', f'ks{k}', 'standard1', timeout=3000)
    nt('flush', 'ksu')
    note(f'EPOCH_MS compact-end {int(time.time() * 1000)}')
    r2 = census('after-compact')
    for k in KS:
        expect(f'after-compact ks{k}: one SSTable ({r2[f"ks{k}"][2]})', r2[f'ks{k}'][2] == 1)
    judge_census('after-compact', r2)
    for k in KS:   # compaction rewrites the same data
        expect(f'ks{k}: dataLength sum changed by compaction by < 0.5% ({r1[f"ks{k}"][3]} vs {r2[f"ks{k}"][3]})', abs(r1[f'ks{k}'][3] - r2[f'ks{k}'][3]) < 0.005 * r1[f'ks{k}'][3])
    stop_node()
    expect('node stopped for the restart', pid() is None)
    start_node(trace)
    r3 = census('after-restart')
    judge_census('after-restart', r3)
    for k in KS:
        expect(f'ks{k}: metric after restart == metric after compact ({r3[f"ks{k}"][0]} vs {r2[f"ks{k}"][0]})', r3[f'ks{k}'][0] == r2[f'ks{k}'][0])
    nerr = syslog_errors(off)
    expect(f'no ERROR line in system.log since the start of the run ({nerr})', nerr == 0)
    stop_node()
    expect('node stopped', pid() is None)
    trace_report(trace)


def trace_report(path):
    ev = {}
    prep = {}
    if os.path.exists(path):
        for l in open(path, errors='replace'):
            kv = dict(re.findall(r'(\w+)=(\S+)', l))
            if l.startswith('double '):
                ev.setdefault(kv['path'], []).append((int(kv['maxCountNow']), int(kv['count'])))
            elif l.startswith('prepare '):
                prep[kv['path']] = (int(kv['maxCount']), int(kv['count']))
    note(f'TRACE writers with a doubling: {len(ev)}; doubling lines: {sum(len(v) for v in ev.values())}; prepare lines: {len(prep)}')
    bad, maxcap = 0, 0
    for p, v in ev.items():
        prev = 100
        for (now, cnt) in v:
            if now != 2 * prev or cnt != prev:
                bad += 1
                note(f'TRACE odd {p}: now={now} count={cnt} expected now={2 * prev} count={prev}')
            prev = now
            maxcap = max(maxcap, now)
    expect(f'trace: every doubling is new = 2 x old and fires at count == old capacity ({bad} exceptions)', bad == 0 and len(ev) > 0)
    expect(f'trace: some writer reached a capacity above 100 x 2^14 ({maxcap})', maxcap > 100 * 2 ** 14)
    badp = [p for p, (mc, c) in prep.items() if not (c <= mc < max(2 * c, 101))]
    expect(f'trace: at prepare, count <= capacity and capacity < 2 x count (or the initial 100) for all {len(prep)} writers ({len(badp)} exceptions)', not badp and prep)
    note('TRACE max count at prepare: %d' % max((c for _, c in prep.values()), default=0))


def control_arm(mib):
    if not os.path.isdir(D + '/data/ks16'):
        fail('run arm M first (no data in ' + D + ')')
    if not os.path.exists(JMXCP + '/Jmx.class'):
        os.makedirs(JMXCP, exist_ok=True)
        sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    make_conf(mib)
    start_node(None)
    off = logoff()
    cap = (mib - 32) * 1024 * 1024
    capm = jget('org.apache.cassandra.metrics:type=Cache,scope=ChunkCache,name=Capacity', 'Value')
    note(f'CONTROL cache {mib} MiB: Capacity gauge = {capm}, expected (file_cache_size - 32 MiB) = {cap}')
    expect(f'control {mib}: ChunkCache Capacity == {cap}', capm is not None and int(capm) == cap)
    m0 = metric('ks16')
    stop = LOGS + '/stop'
    if os.path.exists(stop):
        os.remove(stop)
    jf = open(LOGS + '/samples.csv', 'w')
    poller = subprocess.Popen(['java', '-cp', JMXCP, 'Jmx', str(JMX), 'poll', '1000', '100000000', stop,
                               'org.apache.cassandra.metrics:type=Cache,scope=ChunkCache,name=Size', 'Value',
                               'org.apache.cassandra.metrics:type=Cache,scope=ChunkCache,name=Capacity', 'Value',
                               'org.apache.cassandra.metrics:type=Table,keyspace=ks16,scope=standard1,name=CompressionMetadataOffHeapMemoryUsed', 'Value'],
                              stdout=jf, stderr=subprocess.STDOUT)
    time.sleep(3)
    try:
        stress('read', f'n={UROWS}', '-col', 'size=FIXED(1000)', '-pop', f'dist=UNIFORM(1..{ROWS})', '-rate', 'threads=32', '-schema', 'keyspace=ks16', label=f'read-{mib}')
    finally:
        time.sleep(2)
        open(stop, 'w').close()
        try:
            poller.wait(timeout=30)
        except subprocess.TimeoutExpired:
            poller.kill()
        jf.close()
    rows = []
    for l in open(LOGS + '/samples.csv'):
        p = l.strip().split(',')
        if len(p) == 4 and p[0].isdigit():
            rows.append([int(p[0])] + [float(x) for x in p[1:]])
    mx = max((r[1] for r in rows), default=0)
    mxcap = max((r[2] for r in rows), default=0)
    note(f'CONTROL {mib}: samples={len(rows)} max ChunkCache Size={mx:.0f} max Capacity={mxcap:.0f} (cache cap {cap}); offsets metric ks16 before={m0}, samples min/max={min((r[3] for r in rows), default=0):.0f}/{max((r[3] for r in rows), default=0):.0f}')
    expect(f'control {mib}: Size never exceeds Capacity + one 16 KiB chunk ({mx:.0f} vs {cap})', mx <= cap + 16384)
    expect(f'control {mib}: Size reaches >= 90% of Capacity ({mx:.0f} vs {cap})', mx >= 0.9 * cap)
    expect(f'control {mib}: offsets metric constant during the read ({m0})', all(r[3] == m0 for r in rows))
    nerr = syslog_errors(off)
    expect(f'no ERROR line in system.log ({nerr})', nerr == 0)
    stop_node()
    expect('node stopped', pid() is None)


try:
    note(f'== arm {arm} start {time.strftime("%FT%TZ", time.gmtime())}')
    if arm == 'M':
        main_arm()
    else:
        control_arm(int(arm[1:]))
finally:
    stop_node()
    note(f'== arm {arm} end; EXPECTED yes={EXPECT["yes"]} no={EXPECT["no"]}')
