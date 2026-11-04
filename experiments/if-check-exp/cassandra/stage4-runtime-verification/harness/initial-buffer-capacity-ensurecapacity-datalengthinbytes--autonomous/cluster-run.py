#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous (case file as amended 2026-10-26).
usage: cluster-run.py <arm> | down
  <arm>  one node lifetime: wipe the data directory (tmpfs), write the yaml (PasswordAuthenticator; guardrail thresholds in arm ctl), start one
         node with Byteman (ec.btm, boot-class-path helper Ec) and heap -Xmx<heap>, wait for UN + native port, wait for the superuser, create
         role/keyspace/table(/SAI index), start JFR, take the baseline (class-histogram total, heap, data bytes), then the workload as role `ordinary`:
           load half the rows, nodetool flush, load the other half, nodetool flush, nodetool compact, <Q> point queries,
           (arm ctl also: 4 KiB-v inserts, rejected by the 1 KiB fail threshold),
         then nodetool invalidatekeycache, the final class-histogram total, JFR dump, the trace summary, and stop the node.
         The first-trigger check: after the first flush of an indexed arm the trace must hold readBytes calls from SegmentMetadata.write;
         if not, the run stops (FAIL) and the node is stopped.
  Arms (K = partition key bytes; rows; heap; SAI index):
         k16 16/20000/1g/yes  k1k 1024/20000/1g/yes  k32k 32768/2000/1g/yes  k64k 65535/2000/1g/yes
         k16m 16/20000/512m/yes  k64km 65535/2000/512m/yes   k16n 16/20000/1g/no  k64kn 65535/2000/1g/no
         ctl 1024/2000/1g/yes with sai_string_term_size_warn/fail_threshold 512B/1KiB
         warm: a shakedown arm (k1k with 500 rows), never a reading.
  down   stop this harness's node (by pid file) and list leftovers.
Port slot 3: loopback 127.0.3.1, JMX 7130, Byteman agent 19130, native 9042 (on 127.0.3.1 only), storage 7000 (on 127.0.3.1 only).
Output: ~/s4-b7-ie-logs/<EC_RUN>/cluster/<arm>/ (summary.txt with EXPECTED lines, session.log, ec.trace, phases.json, samples.csv, histo-*.txt,
A-log-excerpt.txt, ec.jfr, jfr.json). Exit 1: a check failed; the node is then stopped. Environment: EC_RUN (default run1), CASSANDRA_HOME."""
import json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b7-ie')
HARNESS = os.path.dirname(os.path.abspath(__file__))
RUN = os.environ.get('EC_RUN', 'run1')
DATA = '/dev/shm/s4-b7-ie-data'          # tmpfs, never /proj
ADDR, JMXP, BMP, NATIVE = '127.0.3.1', 7130, 19130, 9042
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
Q = 1000
VLEN = 1000
ARMS = {  # K, rows, heap, index, extra yaml
    'k16': (16, 20000, '1G', True, []), 'k1k': (1024, 20000, '1G', True, []),
    'k32k': (32768, 2000, '1G', True, []), 'k64k': (65535, 2000, '1G', True, []),
    'k16m': (16, 20000, '512M', True, []), 'k64km': (65535, 2000, '512M', True, []),
    'k16n': (16, 20000, '1G', False, []), 'k64kn': (65535, 2000, '1G', False, []),
    'ctl': (1024, 2000, '1G', True, ['sai_string_term_size_warn_threshold=512B', 'sai_string_term_size_fail_threshold=1KiB']),
    'warm': (1024, 500, '1G', True, []),
}
args = sys.argv[1:]
if len(args) != 1 or (args[0] not in ARMS and args[0] != 'down'):
    sys.exit(__doc__)
arm = args[0]
ROOT = f'{HOME}/s4-b7-ie-logs/{RUN}/cluster'
LOGS = f'{ROOT}/{arm}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a' if arm == 'down' else 'w')
TRACE = LOGS + '/ec.trace'
EXPECT = {'yes': 0, 'no': 0}
PHASES = {}


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=900, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-4000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1200:]}')
    return r.returncode, out


def expect(desc, cond):
    EXPECT['yes' if cond else 'no'] += 1
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def pid_of():
    f = f'{DATA}/cassandra.pid'
    try:
        pid = int(open(f).read().strip())
        return pid if 'CassandraDaemon' in open(f'/proc/{pid}/cmdline').read() else None
    except (ValueError, OSError):
        return None


def mine():
    """java processes whose command line names this harness's data directory"""
    return sh(f"ps -eo pid,args | grep '[C]assandraDaemon' | grep -F '{DATA}' | cut -c1-120 || true", check=False, quiet=True)[1].strip()


def stop_node():
    pid = pid_of()
    if pid is None:
        return
    try:
        sh(f'bin/nodetool -p {JMXP} stopdaemon', check=False, timeout=180)
    except subprocess.TimeoutExpired:
        log('stopdaemon timed out')
    for _ in range(120):
        if pid_of() is None:
            return
        time.sleep(1)
    pid = pid_of()
    if pid is not None:
        log(f'node did not stop; kill -9 {pid}')
        subprocess.run(['kill', '-9', str(pid)])
        time.sleep(2)


def fail(msg):
    note('FAIL: ' + msg)
    stop_node()
    left = mine()
    if left:
        note('WARNING: leftover: ' + left)
    sys.exit(1)


def client(*a, timeout=3600):
    rc, out = sh(f'python3 -I {HARNESS}/client.py ' + ' '.join(str(x) for x in a), timeout=timeout, check=False,
                 env=dict(os.environ, CASSANDRA_HOME=C, EC_VLEN=str(VLEN)))
    js = [l for l in out.splitlines() if l.startswith('{')]
    if rc != 0 or not js:
        return None
    return json.loads(js[-1])


def dir_bytes(d):
    t = 0
    for root, _, files in os.walk(d):
        for f in files:
            try:
                t += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return t


def write_conf(heap, extra):
    N = DATA
    sh(f'rm -rf {DATA}', check=False) if DATA.startswith('/dev/shm/s4-b7-ie-data') else None
    for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
        os.makedirs(f'{N}/{d}', exist_ok=True)
    sh(f'cp -r {C}/conf {N}/conf')
    sh(f'git -C {C} show HEAD:conf/cassandra-env.sh > {N}/conf/cassandra-env.sh')
    sh(f'sed -i \'s/^JMX_PORT="7199"/JMX_PORT="{JMXP}"/\' {N}/conf/cassandra-env.sh')
    if f'JMX_PORT="{JMXP}"' not in open(f'{N}/conf/cassandra-env.sh').read():
        fail('JMX_PORT line not replaced')
    sh(f'git -C {C} show HEAD:conf/jvm11-server.options > {N}/conf/jvm11-server.options')
    sh(f'git -C {C} show HEAD:conf/cassandra.yaml > {N}/shipped.yaml')
    add = ['cluster_name: stage4-ec', 'num_tokens: 4', 'endpoint_snitch: SimpleSnitch', f'listen_address: {ADDR}', f'rpc_address: {ADDR}',
           'storage_port: 7000', f'native_transport_port: {NATIVE}', 'seed_provider:', '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider',
           '    parameters:', f'      - seeds: "{ADDR}:7000"', 'data_file_directories:', f'    - {N}/data', f'commitlog_directory: {N}/commitlog',
           f'hints_directory: {N}/hints', f'saved_caches_directory: {N}/saved_caches', f'cdc_raw_directory: {N}/cdc_raw',
           'authenticator: PasswordAuthenticator', 'write_request_timeout: 30000ms', 'native_transport_timeout: 60000ms']
    for e in extra:
        k, v = e.split('=', 1)
        add.append(f'{k}: {v}')
    keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
    out, skip = [], False
    for l in open(f'{N}/shipped.yaml').read().splitlines():
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
    open(f'{N}/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 ec lines ----\n' + '\n'.join(add) + '\n')
    note('yaml tail: ' + ';'.join(l for l in add if not l.startswith(('  ', 'seed_provider', 'data_file'))))


def start_node(heap):
    if pid_of() is not None:
        fail('a node of this harness is already running')
    env = dict(os.environ, CASSANDRA_CONF=DATA + '/conf', CASSANDRA_LOG_DIR=DATA + '/logs', MAX_HEAP_SIZE=heap)
    env.pop('HEAP_NEWSIZE', None); env.pop('JVM_EXTRA_OPTS', None)
    extra = (f'-javaagent:{BYTEMAN}=script:{HARNESS}/ec.btm,listener:true,port:{BMP},address:127.0.0.1 -Xbootclasspath/a:{LOGS}/stage4-ec.jar '
             f'-Dorg.jboss.byteman.verbose=false -Dstage4.byteman.out={TRACE}')
    env['JVM_EXTRA_OPTS'] = extra
    note(f'JVM_EXTRA_OPTS: {extra}; MAX_HEAP_SIZE={heap}')
    sh(f"bash -c 'ulimit -n 100000 && exec bin/cassandra -p {DATA}/cassandra.pid' > {DATA}/stdout.txt 2>&1", env=env)
    for _ in range(30):
        time.sleep(1)
        if pid_of() is not None:
            return
    fail(f'node did not start; see {DATA}/stdout.txt')


def wait_up(timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pid_of() is None:
            fail('node died during start')
        _, st = sh(f'bin/nodetool -p {JMXP} status', check=False, quiet=True)
        _, sb = sh(f'bin/nodetool -p {JMXP} statusbinary', check=False, quiet=True)
        if re.search(rf'^UN\s+{re.escape(ADDR)}\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
            log(f'UN and serving after {time.time() - t0:.0f} s')
            return
        time.sleep(3)
    fail('node not UN within the timeout')


def histo(tag):
    """full-GC class histogram total (bytes) and the [B row"""
    pid = pid_of()
    rc, out = sh(f'jcmd {pid} GC.class_histogram', check=False, timeout=300, quiet=True)
    open(f'{LOGS}/histo-{tag}.txt', 'w').write(out)
    tot = re.search(r'^Total\s+(\d+)\s+(\d+)', out, re.M)
    b = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+\[B\b', out, re.M)
    return {'total_bytes': int(tot.group(2)) if tot else None, 'byte_arrays_bytes': int(b.group(2)) if b else None, 'byte_arrays_n': int(b.group(1)) if b else None}


def heap_used():
    _, out = sh(f'java -cp {LOGS}/cls Jmx {JMXP} get java.lang:type=Memory HeapMemoryUsage', check=False, quiet=True)
    m = re.search(r'\|(\d+)\s*$', out.strip().splitlines()[-1]) if out.strip() else None
    return int(m.group(1)) if m else None


def trace_lines():
    if not os.path.exists(TRACE):
        return []
    return [l.split() for l in open(TRACE) if l.startswith('rb')]


def summarize_trace(since_ms=0):
    """per (kind, caller method) over the readBytes calls at or after since_ms; the caller's line number is dropped"""
    by = {}
    for p in trace_lines():
        kv = dict(x.split('=', 1) for x in p[1:] if '=' in x)
        if int(kv.get('ms', 0)) < since_ms:
            continue
        key = (p[0], re.sub(r':\d+$', '', kv['caller']))
        d = by.setdefault(key, {'n': 0, 'bytes': 0, 'max_bytes': 0, 'mirror_grow': 0, 'mirror_total': 0, 'len_sum': 0, 'max_len': 0, 'below_mirror': 0})
        d['n'] += 1
        b = int(kv['bytes'])
        d['bytes'] += b
        d['max_bytes'] = max(d['max_bytes'], b)
        ln = int(kv.get('len', 0))
        d['len_sum'] += ln
        d['max_len'] = max(d['max_len'], ln)
        if p[0] == 'rb':
            g = expected_grow(ln, 32)
            tot = expected_total(ln, 32)
            d['mirror_grow'] += g       # inferred: the doubling code applied to the observed result length
            d['mirror_total'] += tot
            if b < tot:
                d['below_mirror'] += 1
    return {f'{k[0]}|{k[1]}': v for k, v in by.items()}


def expected_total(n, init):
    """sum of align8(16 + length) over every array readBytes(src of n bytes, init) creates: the initial one, the doublings, the final copy"""
    ln = init
    tot = (16 + ln + 7) & ~7
    while n > ln:
        ln *= 2
        tot += (16 + ln + 7) & ~7
    if n != ln:
        tot += (16 + n + 7) & ~7
    return tot


def expected_grow(n, init):
    """sum of align8(16 + length) over the arrays ensureCapacity creates while readBytes reads n bytes from an init-sized buffer"""
    ln, tot = init, 0
    while n > ln:
        ln *= 2
        tot += (16 + ln + 7) & ~7
    return tot


def main():
    if arm == 'down':
        stop_node()
        left = mine()
        note('down: leftovers: ' + (left or 'none'))
        return
    K, rows, heap, idx, extra = ARMS[arm]
    note(f'cluster-run {arm} {time.strftime("%FT%T")} host {os.uname().nodename} K={K} rows={rows} heap={heap} index={idx} Q={Q} vlen={VLEN}')
    note(f'tree {C} {sh(f"git -C {C} describe --tags", check=False)[1].strip()}; harness md5 ' + sh(f'cd {HARNESS} && md5sum ec.btm Ec.java client.py cluster-run.py JfrSum.java', check=False)[1].replace('\n', ' | '))
    # instruments: helper jar, Jmx, JfrSum
    os.makedirs(LOGS + '/cls', exist_ok=True)
    os.makedirs(LOGS + '/ecclasses', exist_ok=True)
    sh(f'javac -d {LOGS}/ecclasses {HARNESS}/Ec.java && jar cf {LOGS}/stage4-ec.jar -C {LOGS}/ecclasses .')
    sh(f'javac -d {LOGS}/cls {HARNESS}/Jmx.java {HARNESS}/JfrSum.java')
    if pid_of() is not None or mine():
        fail('a node of this harness is running')
    if os.path.exists(TRACE):
        os.remove(TRACE)
    ss = sh('ss -ltn', check=False, quiet=True)[1]
    busy = [p for p in (f'{ADDR}:7000', f'{ADDR}:{NATIVE}', f'127.0.0.1:{JMXP}', f'127.0.0.1:{BMP}', f'*:{JMXP}', f'*:{BMP}') if re.search(r'\s' + re.escape(p) + r'\s', ss)]
    if busy:
        fail(f'ports busy: {busy}')
    sh(f'df -h /dev/shm | tail -1; ulimit -n', check=False)
    write_conf(heap, extra)
    start_node(heap)
    wait_up()
    pid = pid_of()
    note(f'node pid {pid}; JVM args: ' + ' '.join(t for t in open(f"/proc/{pid}/cmdline").read().split('\0') if t.startswith(('-Xm', '-javaagent', '-Dstage4', '-Xbootclasspath', '-XX:+UseG1')))[:600])
    r = client('ready')
    if not r or not r.get('ready'):
        fail(f'superuser login never worked: {r}')
    r = client('setup', 1 if idx else 0)
    note('setup: ' + json.dumps(r))
    if not r or r.get('ordinary_is_superuser') is not False:
        fail('role ordinary is missing or a superuser (guardrails would not apply)')
    # instrument check: the trace file is written by the helper (first readBytes call). A read of the system keyspace may already call it.
    sh(f'jcmd {pid} JFR.start name=ec settings=profile filename={LOGS}/ec.jfr', check=False)
    base = {'histo': histo('base'), 'heap_used': heap_used(), 'data_bytes': dir_bytes(DATA + '/data'), 'ms': int(time.time() * 1000)}
    PHASES['base'] = base
    note(f'baseline: {json.dumps(base)}')
    half = rows // 2
    errs = 0
    t_load0 = int(time.time() * 1000)
    r1 = client('load', K, 0, half, VLEN)
    note('load1: ' + json.dumps(r1))
    errs += (r1 or {}).get('err', 999999)
    sh(f'bin/nodetool -p {JMXP} flush ks t', timeout=900)
    PHASES['flush1'] = {'ms': int(time.time() * 1000), 'data_bytes': dir_bytes(DATA + '/data')}
    s1 = summarize_trace(t_load0)
    note('trace after flush 1: ' + json.dumps(s1))
    if idx:
        sm = [v for k, v in s1.items() if k.startswith('rb|SegmentMetadata.write')]
        if not expect('first trigger: at least two readBytes calls from SegmentMetadata.write (the min and the max key) are in the trace after the first flush of an indexed arm (path reached)', bool(sm) and sm[0]['n'] >= 2):
            fail('the path was not reached (no readBytes call from SegmentMetadata.write after the flush)')
    r2 = client('load', K, half, rows - half, VLEN)
    note('load2: ' + json.dumps(r2))
    errs += (r2 or {}).get('err', 999999)
    sh(f'bin/nodetool -p {JMXP} flush ks t', timeout=900)
    PHASES['flush2'] = {'ms': int(time.time() * 1000), 'data_bytes': dir_bytes(DATA + '/data')}
    tc = int(time.time() * 1000)
    sh(f'bin/nodetool -p {JMXP} compact ks t', timeout=1800)
    PHASES['compact'] = {'ms': int(time.time() * 1000), 'data_bytes': dir_bytes(DATA + '/data'), 'trace': summarize_trace(tc)}
    note('trace during compaction: ' + json.dumps(PHASES['compact']['trace']))
    tq = int(time.time() * 1000)
    rq = client('query', 1 if idx else 0, K, 0, rows, Q)
    note('queries: ' + json.dumps(rq))
    PHASES['queries'] = {'ms': int(time.time() * 1000), 'trace': summarize_trace(tq), 'client': rq}
    note('trace during queries: ' + json.dumps(PHASES['queries']['trace']))
    if arm == 'ctl':
        rb = client('big', 20, 4096)
        note('big (4 KiB v) inserts: ' + json.dumps(rb))
        PHASES['big'] = rb
    sh(f'bin/nodetool -p {JMXP} invalidatekeycache', check=False)
    time.sleep(5)
    fin = {'histo': histo('final'), 'heap_used': heap_used(), 'data_bytes': dir_bytes(DATA + '/data'), 'ms': int(time.time() * 1000)}
    PHASES['final'] = fin
    note(f'final: {json.dumps(fin)}')
    sh(f'jcmd {pid} JFR.dump name=ec filename={LOGS}/ec.jfr', check=False)
    jf = sh(f'java -cp {LOGS}/cls JfrSum {LOGS}/ec.jfr', check=False)[1].strip().splitlines()
    jf = [l for l in jf if l.startswith('{')]
    open(LOGS + '/jfr.json', 'w').write((jf[-1] if jf else '{}') + '\n')
    PHASES['jfr'] = json.loads(jf[-1]) if jf else None
    note('jfr: ' + (jf[-1] if jf else 'none'))
    allsum = summarize_trace(0)
    PHASES['trace_all'] = allsum
    note('trace, all: ' + json.dumps(allsum))
    # logs
    nerr = nwarn = 0
    exc = []
    for l in open(f'{DATA}/logs/system.log', errors='replace'):
        if l.startswith('ERROR'):
            nerr += 1
            exc.append(l.rstrip()[:300])
        if l.startswith('WARN'):
            nwarn += 1
    open(LOGS + '/A-log-excerpt.txt', 'w').write('\n'.join(exc[:50]) + f'\nERROR lines: {nerr} WARN lines: {nwarn}\n')
    PHASES['log'] = {'errors': nerr, 'warns': nwarn}
    json.dump(PHASES, open(LOGS + '/phases.json', 'w'), indent=1)
    # EXPECTED lines (B3f, read from the case's prediction; numbers fixed before run 1)
    expect(f'no write failed for the legal key size K={K} (client errors across both load phases = 0)', errs == 0)
    expect('no ERROR line in system.log', nerr == 0)
    sm = [v for k, v in allsum.items() if k.startswith('rb|SegmentMetadata.write')]
    if idx:
        d = sm[0] if sm else None
        expect(f'readBytes calls from SegmentMetadata.write decode keys of about K bytes: max_len in [K, 1.02K+64] (K={K})',
               d is not None and K <= d['max_len'] <= 1.02 * K + 64)
    rbk = {k: v for k, v in allsum.items() if k.startswith('rb|')}
    expect('every readBytes call allocated at least what the doubling code allocates for its result length (below_mirror = 0 for every caller; the surplus is the byte source, which is not this code)',
           all(v['below_mirror'] == 0 for v in rbk.values()))
    big = [v for v in rbk.values() if v['max_len'] >= 1000]
    worst = max((v['mirror_grow'] / v['len_sum'] for v in big if v['len_sum']), default=0)
    expect(f'inferred (mirror of the doubling code on the observed lengths): ensureCapacity allocation per call is at most 4.1 x the decoded length on average for every caller that decodes 1000 B or more (arithmetic: sum of doublings to the next power of two is about 2 x capacity < 4 x length, plus 16-byte headers; worst {worst:.2f})', worst <= 4.1)
    mxg = max((v['mirror_grow'] / v['n'] for v in rbk.values()), default=0)
    expect(f'inferred: mean ensureCapacity allocation per call is at most 4 x 65535 B = 262140 B (largest caller mean {mxg:.0f})', mxg <= 4 * 65535)
    expect('no readBytes call threw (no rbexc line)', not any(k.startswith('rbexc|') for k in allsum))
    if PHASES['jfr']:
        expect(f'JFR: allocation weight under ensureCapacity is below 1 percent of all allocation weight (share {PHASES["jfr"]["share_ensureCapacity"]:.5f})',
               PHASES['jfr']['share_ensureCapacity'] < 0.01)
    dh = fin['histo']['total_bytes'] - base['histo']['total_bytes'] if fin['histo']['total_bytes'] and base['histo']['total_bytes'] else None
    note(f'retained live heap (class-histogram total) final - baseline = {dh}; data dir bytes final = {fin["data_bytes"]}; raw input bytes = {rows * (K + VLEN)}')
    if arm == 'ctl':
        rb = PHASES.get('big') or {}
        expect('guardrail control: the 4 KiB-v inserts are all rejected at fail threshold 1 KiB (err = n = 20)', rb.get('err') == 20 and rb.get('ok') == 0)
    note(f'EXPECTED totals: yes={EXPECT["yes"]} no={EXPECT["no"]}')
    stop_node()
    left = mine()
    note('node stopped; leftovers: ' + (left or 'none'))
    sh(f'cp {DATA}/logs/system.log {LOGS}/system.log', check=False)
    sh(f'rm -rf {DATA}/data {DATA}/commitlog {DATA}/hints {DATA}/saved_caches {DATA}/cdc_raw', check=False)


try:
    main()
except SystemExit:
    raise
except BaseException as e:
    note(f'EXCEPTION: {type(e).__name__}: {e}')
    stop_node()
    sys.exit(1)
