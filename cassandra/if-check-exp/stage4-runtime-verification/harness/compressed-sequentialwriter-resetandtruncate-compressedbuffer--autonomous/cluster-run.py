#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of compressed-sequentialwriter-resetandtruncate-compressedbuffer--autonomous (case file as amended 2026-10-26).
usage: cluster-run.py <arm>          arms: C4 C16 C256 C1024 (chunk sweep, 1 table, concurrent_compactors 1) · W4 (4 tables, chunk 1024,
                                     concurrent_compactors 4, compacted together) · U (uncompressed table) · S1 [frac] (corrupted SSTable scrub, observer rules)
                                     · S2 [frac] (the same with Byteman forcing the grow at line 247)
  One node lifetime per call (one fresh data dir): yaml + jvm options, start with Byteman cs.btm, wait for UN and the client port,
  create the table(s) and ALTER compression (B3b), load 4 x 50,000 rows of 1,024 random bytes per table with a flush after each,
  GC, baseline, then `nodetool compact ks <t>` (all tables at once in W4) sampled every 1 s (direct pool via JMX; NMT every 2 s),
  read the Byteman trace, write summary.txt with EXPECTED lines, stop the node by pid file.
Ports: JMX 7327, Byteman 9327, native 9349, storage 7027, loopback 127.0.27.1. Output: ~/s4-cs-logs/<CS_RUN>/<arm>/ (default run1).
"""
import json, os, re, shutil, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-cs')
D = HOME + '/s4-cs-data'
RUN = os.environ.get('CS_RUN', 'run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
ADDR, JMX, BTM_PORT, NATIVE, STORAGE = '127.0.27.1', 7327, 9327, 9349, 7027
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
JMXCP = D + '-jmx'
NROWS, NROUNDS, ROWBYTES = int(os.environ.get('CS_N', 50000)), 4, 1024
arm = sys.argv[1] if len(sys.argv) > 1 else ''
frac = float(sys.argv[2]) if len(sys.argv) > 2 else 0.55
if arm not in ('C4', 'C16', 'C256', 'C1024', 'W4', 'U', 'S1', 'S2'):
    sys.exit(__doc__)
tag = arm if not arm.startswith('S') else '%s-%02d' % (arm, int(frac * 100))
LOGS = f'{HOME}/s4-cs-logs/{RUN}/{tag}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'w')
EXPECT = {'yes': 0, 'no': 0}
CHILDREN = []


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
    for _ in range(90):
        if pid() is None:
            return
        time.sleep(1)
    log(f'node did not stop; kill -9 {p}')
    subprocess.run(['kill', '-9', str(p)])
    time.sleep(2)


def fail(msg):
    note('FAIL: ' + msg)
    for ch in CHILDREN:
        if ch.poll() is None:
            ch.kill()
    stop_node()
    sys.exit(1)


def busy():
    out = sh('ss -ltn', check=False, quiet=True)[1]
    return [p for p in (f'127.0.0.1:{JMX}', f'*:{JMX}', f'127.0.0.1:{BTM_PORT}', f'{ADDR}:{NATIVE}', f'{ADDR}:{STORAGE}') if re.search(r'\s' + re.escape(p) + r'\s', out)]


def make_conf(compactors):
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
    open(N + '/conf/jvm11-server.options', 'w').write(jvm + '\n# stage4 cs (B3a)\n-XX:MaxDirectMemorySize=1g\n-XX:NativeMemoryTracking=summary\n')
    add = ['cluster_name: stage4-cs', 'num_tokens: 1', 'endpoint_snitch: SimpleSnitch', f'listen_address: {ADDR}', f'rpc_address: {ADDR}',
           f'storage_port: {STORAGE}', f'native_transport_port: {NATIVE}', 'seed_provider:',
           '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider', '    parameters:', f'      - seeds: "{ADDR}:{STORAGE}"',
           'data_file_directories:', f'    - {N}/data', f'commitlog_directory: {N}/commitlog', f'hints_directory: {N}/hints',
           f'saved_caches_directory: {N}/saved_caches', f'cdc_raw_directory: {N}/cdc_raw', f'concurrent_compactors: {compactors}',
           'compaction_throughput: 0MiB/s', 'flush_compression: table', 'auto_snapshot: false']
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
    open(N + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 cs lines ----\n' + '\n'.join(add) + '\n')
    note(f'yaml: concurrent_compactors={compactors}, flush_compression=table, compaction_throughput=0MiB/s, JMX {JMX}, native {NATIVE}, storage {STORAGE}, {ADDR}')


def start_node(trace, force=False):
    left = busy()
    if left:
        fail('ports busy before start: %s' % left)
    extra = (f'-javaagent:{BYTEMAN}=boot:{BYTEMAN},script:{HARNESS}/cs.btm,listener:true,port:{BTM_PORT} '
             f'-Dorg.jboss.byteman.verbose=false -Dcs.trace={trace} -Dcs.force={1 if force else 0}')
    env = dict(os.environ, CASSANDRA_CONF=D + '/conf', CASSANDRA_LOG_DIR=D + '/logs', MAX_HEAP_SIZE='2G', JVM_EXTRA_OPTS=extra)
    env.pop('HEAP_NEWSIZE', None)
    note('JVM_EXTRA_OPTS: ' + extra)
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
        _, st = sh(f'bin/nodetool -p {JMX} status', check=False, quiet=True)
        _, sb = sh(f'bin/nodetool -p {JMX} statusbinary', check=False, quiet=True)
        if re.search(r'^UN\s+' + re.escape(ADDR), st, re.M) and re.search(r'^running\s*$', sb, re.M):
            log(f'UN and serving after {time.time() - t0:.0f} s')
            return
        time.sleep(3)
    fail('node not UN within the timeout')


def client(*a, timeout=3600):
    rc, out = sh(f'python3 -I {HARNESS}/client.py ' + ' '.join(str(x) for x in a), timeout=timeout, check=False, env=dict(os.environ, CASSANDRA_HOME=C, CS_NATIVE_PORT=str(NATIVE)))
    js = [l for l in out.splitlines() if l.startswith('{')]
    if rc != 0 or not js:
        fail('client failed: ' + out[-500:])
    return json.loads(js[-1])


def nt(*a, **k):
    return sh(f'bin/nodetool -p {JMX} ' + ' '.join(str(x) for x in a), **k)


def datafiles(table=None):
    res = []
    for root, _, files in os.walk(D + '/data/ks'):
        if table is None or os.path.basename(root).startswith(table + '-'):
            res += [os.path.join(root, f) for f in files if f.endswith('-Data.db')]
    return sorted(res)


def sample_loop(stopfile, outdir):
    """direct pool + heap via one Jmx poll JVM; NMT every 2 s"""
    jf = open(outdir + '/samples-jmx.csv', 'w')
    cmd = ['java', '-cp', JMXCP, 'Jmx', str(JMX), 'poll', '1000', '100000000', stopfile,
           'java.nio:type=BufferPool,name=direct', 'MemoryUsed', 'java.nio:type=BufferPool,name=direct', 'Count',
           'java.lang:type=Memory', 'HeapMemoryUsage']
    p = subprocess.Popen(cmd, stdout=jf, stderr=subprocess.STDOUT)
    CHILDREN.append(p)
    nm = open(outdir + '/nmt.txt', 'w')
    alive = {'v': True}
    jp = pid()

    def nmt():
        while alive['v']:
            r = subprocess.run(['jcmd', str(jp), 'VM.native_memory', 'summary'], capture_output=True, text=True)
            ms = int(time.time() * 1000)
            for l in r.stdout.splitlines():
                m = re.match(r'^-\s+(Other|Internal|Total|Java Heap)\s+\(reserved=(\d+)KB, committed=(\d+)KB', l.strip()) or re.match(r'^(Total): reserved=(\d+)KB, committed=(\d+)KB', l.strip())
                if m:
                    nm.write(f'{ms},{m.group(1)},{m.group(3)}\n')
            nm.flush()
            time.sleep(2)
    th = threading.Thread(target=nmt, daemon=True)
    th.start()

    def close():
        open(stopfile, 'w').close()
        alive['v'] = False
        th.join()
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
        jf.close(); nm.close()
    return close


def read_trace(path):
    ev = []
    if os.path.exists(path):
        for l in open(path, errors='replace'):
            l = l.strip()
            kind = l.split(' ', 1)[0]
            if kind in ('init', 'reset', 'r2', 'r2f', 'r3', 'closed'):
                kv = dict(re.findall(r'(\w+)=(\S+)', l))
                kv['kind'] = kind
                ev.append(kv)
    return ev


def lz4_bound(n):
    return 4 + n + n // 255 + 16


def csv_rows(path):
    rows = []
    for l in open(path):
        p = l.strip().split(',')
        if len(p) >= 4 and p[0].isdigit():
            try:
                rows.append([int(p[0])] + [float(x) for x in p[1:4]])
            except ValueError:
                pass
    return rows


def standard():
    chunk_kb = {'C4': 4, 'C16': 16, 'C256': 256, 'C1024': 1024, 'W4': 1024, 'U': 'none'}[arm]
    tables = ['t1', 't2', 't3', 't4'] if arm == 'W4' else ['t']
    compactors = 4 if arm == 'W4' else 1
    trace = LOGS + '/cs.trace'
    if os.path.exists(trace):
        os.remove(trace)
    if not os.path.isdir(JMXCP) or not os.path.exists(JMXCP + '/Jmx.class'):
        os.makedirs(JMXCP, exist_ok=True)
        sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    shutil.rmtree(D, ignore_errors=True)
    make_conf(compactors)
    start_node(trace)
    cr = client('create', ADDR, chunk_kb, *tables)
    note('schema read-back: ' + json.dumps(cr))
    for t in tables:
        for r in range(NROUNDS):
            client('load', ADDR, t, r * NROWS, NROWS, ROWBYTES, 64)
            nt('flush', 'ks', t)
    n_ss = {t: len(datafiles(t)) for t in tables}
    note('sstables before compaction: ' + json.dumps(n_ss))
    expect('every table has 4 SSTables before compaction', all(v == 4 for v in n_ss.values()))
    sh(f'jcmd {pid()} GC.run', check=False); sh(f'jcmd {pid()} GC.run', check=False)
    time.sleep(5)
    stopfile = LOGS + '/sampler.stop'
    if os.path.exists(stopfile):
        os.remove(stopfile)
    close = sample_loop(stopfile, LOGS)
    time.sleep(6)
    t_start = int(time.time() * 1000)
    procs = [subprocess.Popen(f'bin/nodetool -p {JMX} compact ks {t}', shell=True, cwd=C, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) for t in tables]
    CHILDREN.extend(procs)
    for p in procs:
        p.wait(timeout=1800)
    t_end = int(time.time() * 1000)
    note(f'compaction window: {t_start}..{t_end} ms ({(t_end - t_start) / 1000:.1f} s), nodetool rc: {[p.returncode for p in procs]}')
    time.sleep(6)
    close()
    n_after = {t: len(datafiles(t)) for t in tables}
    note('sstables after compaction: ' + json.dumps(n_after))
    ev = read_trace(trace)
    ks = [e for e in ev if e['kind'] == 'init' and '/ks/' in e.get('path', '')]
    note(f'trace: {len(ev)} events; ks writers constructed: {len(ks)}')
    comp = [e for e in ks if int(e['ms']) >= t_start]
    flush = [e for e in ks if int(e['ms']) < t_start]
    note(f'  flush-time ks writers: {len(flush)}; compaction-window ks writers: {len(comp)}')
    for e in ks:
        log('  init ' + json.dumps({k: e[k] for k in ('path', 'buffer', 'compressed', 'direct', 'thread', 'ms')}))
    if arm == 'U':
        expect('uncompressed table: no CompressedSequentialWriter constructed for ks (R1 silent for ks)', len(ks) == 0)
    else:
        kb = chunk_kb * 1024
        expect(f'every ks writer has buffer={kb} (chunk) and compressed={lz4_bound(kb)} (LZ4 bound + 4), both direct',
               len(ks) > 0 and all(int(e['buffer']) == kb and int(e['compressed']) == lz4_bound(kb) and e['direct'] == 'true' for e in ks))
        expect(f'flush writers: {len(tables) * NROUNDS} constructed (one per flush)', len(flush) == len(tables) * NROUNDS)
        expect(f'compaction writers: {len(tables)} constructed in the compaction window', len(comp) == len(tables))
        # concurrency: intervals [init, closed]
        closed = {e['w']: int(e['ms']) for e in ev if e['kind'] == 'closed'}
        iv = [(int(e['ms']), closed.get(e['w'], t_end)) for e in comp]
        best = max((sum(1 for a, b in iv if a <= x <= b) for x, _ in iv), default=0)
        note(f'  max compaction writers alive at once (init..cleanup, {sum(1 for e in comp if e["w"] in closed)} of {len(comp)} cleanup events seen): {best}')
        expect(f'{len(tables)} compaction writer(s) alive at once', best == len(tables))
    expect('R2 never printed in this arm (line 247 never evaluated in flush/compaction)', not any(e['kind'] == 'r2' for e in ev))
    dj = csv_rows(LOGS + '/samples-jmx.csv')
    base = [r for r in dj if r[0] <= t_start][-1:] or dj[:1]
    during = [r for r in dj if t_start <= r[0] <= t_end + 3000]
    if base and during:
        pk = max(during, key=lambda r: r[1])
        note(f'direct pool (secondary reading, includes reader buffers): baseline used={base[0][1]:.0f} count={base[0][2]:.0f}; peak during compaction used={pk[1]:.0f} count={max(r[2] for r in during):.0f}; peak-baseline={pk[1] - base[0][1]:.0f}; heap used baseline={base[0][3]:.0f} max={max(r[3] for r in during):.0f}')
    nm = {}
    for l in open(LOGS + '/nmt.txt'):
        p = l.strip().split(',')
        if len(p) == 3:
            nm.setdefault(p[1], []).append((int(p[0]), int(p[2])))
    for cat, v in nm.items():
        b = [x for x in v if x[0] <= t_start][-1:]
        d = [x for x in v if t_start <= x[0] <= t_end + 3000]
        if b and d:
            note(f'NMT {cat} committed KB: baseline={b[0][1]} peak={max(x[1] for x in d)}')
    json.dump({'arm': arm, 'chunk_kb': chunk_kb, 't_start': t_start, 't_end': t_end, 'writers': [{k: e[k] for k in ('path', 'buffer', 'compressed', 'direct', 'ms')} for e in ks]}, open(LOGS + '/phases.json', 'w'))


def scrub_arm():
    force = arm == 'S2'
    trace1, trace2 = LOGS + '/cs-load.trace', LOGS + '/cs-scrub.trace'
    for t in (trace1, trace2):
        if os.path.exists(t):
            os.remove(t)
    if not os.path.isdir(JMXCP) or not os.path.exists(JMXCP + '/Jmx.class'):
        os.makedirs(JMXCP, exist_ok=True)
        sh(f'javac -d {JMXCP} {HARNESS}/Jmx.java')
    shutil.rmtree(D, ignore_errors=True)
    make_conf(1)
    start_node(trace1, force=False)
    note('load: ' + json.dumps(client('scrubtable', ADDR, 16, 6, 40, 4096)))
    nt('flush', 'ks', 'scr')
    files = datafiles('scr')
    expect('one SSTable Data.db after flush', len(files) == 1)
    stop_node()
    f = files[0]
    size = os.path.getsize(f)
    off = int(size * frac)
    with open(f, 'r+b') as fh:
        fh.seek(off); b = fh.read(1); fh.seek(off); fh.write(bytes([b[0] ^ 0xFF]))
    note(f'corrupted {f}: size {size}, flipped byte at offset {off} (frac {frac}); chunk about {off // (16384 + 8)} of about {size // (16384 + 8)}')
    start_node(trace2, force=force)
    rc, out = nt('scrub', 'ks', 'scr', check=False, timeout=900)
    note(f'nodetool scrub rc={rc}: ' + out.strip().replace('\n', ' | ')[:400])
    time.sleep(3)
    syslog = open(D + '/logs/system.log', errors='replace').read()
    errs = len(re.findall(r'Error reading partition', syslog))
    note(f'system.log: "Error reading partition" x {errs}; "Retrying from partition index" x {len(re.findall("Retrying from partition index", syslog))}; ' +
         'CorruptBlockException/CorruptSSTable lines x %d' % len(re.findall(r'CorruptBlockException|CorruptSSTableException', syslog)))
    for l in re.findall(r'.*Scrub of .*|.*Scrubbed.*|.*partitions.*scrub.*', syslog)[:5]:
        note('  log: ' + l[:300])
    ev = read_trace(trace2)
    sw = {e['w'] for e in ev if e['kind'] == 'init' and '/ks/scr' in e.get('path', '')}
    resets = [e for e in ev if e['kind'] == 'reset' and e['w'] in sw]
    r2 = [e for e in ev if e['kind'] == 'r2']
    r3 = [e for e in ev if e['kind'] == 'r3']
    r2f = [e for e in ev if e['kind'] == 'r2f']
    note(f'trace (scrub lifetime): scrub-output writers {len(sw)}; resetAndTruncate calls on them {len(resets)}; r2 events {len(r2)}; r3 {len(r3)}; r2f {len(r2f)}')
    for e in ev:
        if e['kind'] in ('init', 'reset', 'r2', 'r2f', 'r3') and (e['kind'] != 'init' or '/ks/scr' in e.get('path', '')):
            log('  ' + e['kind'] + ' ' + json.dumps({k: v for k, v in e.items() if k not in ('kind', 'path')}))
    expect('resetAndTruncate was called by the scrub (scrubber failure path reached)', len(resets) >= 1)
    expect('line 247 evaluated (R2 printed) in the scrub: the real failure path reached the branch', len(r2) >= 1)
    if not force:
        expect('S1: R2 capacity >= chunkSize and R3 shows the same object identity (no grow)', len(r2) >= 1 and len(r2) == len(r3) and all(int(a['compressedCap']) >= int(a['chunkSize']) and a['id'] == b['id'] for a, b in zip(r2, r3)))
        expect('S1: R2 capacity equals the LZ4 bound %d for chunk 16 KiB' % lz4_bound(16384), len(r2) >= 1 and all(int(a['compressedCap']) == lz4_bound(16384) for a in r2))
    else:
        expect('S2: R2f forced capacity 64 on every R2', len(r2f) == len(r2) >= 1 and all(int(e['forcedCap']) == 64 for e in r2f))
        expect('S2: R3 capacity == chunkSize exactly and a new identity', len(r3) == len(r2) >= 1 and all(int(b['compressedCap']) == int(a['chunkSize']) and a['id'] != b['id'] for a, b in zip(r2, r3)))
        expect('S2: grown capacity is below the LZ4 bound (no ceiling and no floor: it is the stored chunk size)', len(r3) >= 1 and all(int(b['compressedCap']) < lz4_bound(16384) for b in r3))
    rc2, o2 = client_count()
    note('rows readable after scrub: ' + o2)
    stop_node()


def client_count():
    try:
        r = client('count', ADDR, 'scr')
        return 0, json.dumps(r)
    except SystemExit:
        return 1, 'count failed'


try:
    note(f'arm {arm} start {time.strftime("%FT%TZ", time.gmtime())}')
    if arm.startswith('S'):
        scrub_arm()
    else:
        standard()
        stop_node()
finally:
    stop_node()
    left = subprocess.run("ps -eo pid,cmd | grep '[s]4-cs-data' | cut -c1-120", shell=True, capture_output=True, text=True).stdout.strip()
    note('processes naming s4-cs-data left: ' + (left or 'none'))
    note(f'EXPECTED totals: yes={EXPECT["yes"]} no={EXPECT["no"]}')
