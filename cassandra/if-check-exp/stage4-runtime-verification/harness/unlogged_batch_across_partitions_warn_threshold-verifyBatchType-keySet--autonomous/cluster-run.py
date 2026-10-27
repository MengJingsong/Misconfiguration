#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous (case file as amended 2026-10-26).
usage: cluster-run.py all | t1 | t10 | t100000 | t10r | ctl | down | clean
  Arms (one node lifetime each, data wiped, JDK 11 G1, -Xms2G -Xmx2G, native protocol 4 client):
    t1 / t10 / t100000   unlogged_batch_across_partitions_warn_threshold 1 / 10 / 100000; batch_size_warn = fail = 1000KiB
    t10r                 repeat of the middle setting (run-to-run noise)
    ctl                  threshold 10, batch_size_warn 10KiB, batch_size_fail 20KiB (positive control: the ~115 KB batches must be rejected)
  Per arm: start node, schema ks.t / ks.probe, first-trigger probe (one 500-key batch; abort if the warning or rejection is not seen),
  8 threads x 250 batches x 500 inserts (value 200 B) = 1,000,000 rows, jcmd GC.heap_info every ~1 s, directory-size sampler 1 s, tablestats every 15 s,
  then tablestats, flush, tablestats, count(*), du, WARN count in system.log; node stopped by PID. 'all' runs the five arms in this order:
  t1, t10, t100000, t10r, ctl, and ends with the cross-arm comparison (EXPECTED lines).
Port slot 4: 127.0.4.1 storage 7000 / native 9042, JMX 7140. Output ~/s4-b9-bu-logs/<BU_RUN, default run1>/cluster/<arm>/ (summary.txt with EXPECTED lines).
Exit 1 on a failed set-up or first-trigger check; the node is stopped on any exit.
Environment: BU_RUN, CASSANDRA_HOME (default ~/s4-b9-bu-node), BU_BATCHES (shakedown override, default 250)."""
import glob, json, os, re, resource, signal, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b9-bu-node')
HARNESS = os.path.dirname(os.path.abspath(__file__))
BU = '/dev/shm/s4-b9-bu'
RUN = os.environ.get('BU_RUN', 'run1')
ADDR, JMXPORT = '127.0.4.1', 7140
BATCHES = int(os.environ.get('BU_BATCHES', '250'))
THREADS, KEYS = 8, 500
ROWS = THREADS * BATCHES * KEYS
ARMS = {  # name: (threshold, warn, fail)
    't1': (1, '1000KiB', '1000KiB'), 't10': (10, '1000KiB', '1000KiB'), 't100000': (100000, '1000KiB', '1000KiB'),
    't10r': (10, '1000KiB', '1000KiB'), 'ctl': (10, '10KiB', '20KiB')}
args = sys.argv[1:]
if len(args) != 1 or args[0] not in list(ARMS) + ['all', 'down', 'clean']:
    sys.exit(__doc__)
BASE = f'{HOME}/s4-b9-bu-logs/{RUN}/cluster'
os.makedirs(BASE, exist_ok=True)
SUMMARY = open(BASE + '/summary.txt', 'a')
SESSION = open(BASE + '/session.log', 'a')
resource.setrlimit(resource.RLIMIT_NOFILE, (100000, 100000))


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=900, check=True, env=None, cwd=C, quiet=False):
    if not quiet:
        log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = r.stdout + r.stderr
    if not quiet:
        SESSION.write(out[-2500:] + '\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed ({r.returncode}): {cmd}\n{out[-1500:]}')
    return r.returncode, out


def pid_of():
    try:
        pid = int(open(BU + '/cassandra.pid').read().strip()); os.kill(pid, 0); return pid
    except (ValueError, OSError):
        return None


def stop_node():
    pid = pid_of()
    if pid is None:
        return
    sh(f'{C}/bin/nodetool -p {JMXPORT} stopdaemon', check=False, timeout=120, quiet=True)
    for _ in range(90):
        if pid_of() is None:
            return
        time.sleep(1)
    log(f'node did not stop; kill -9 {pid}'); subprocess.run(['kill', '-9', str(pid)]); time.sleep(2)


def fail(msg):
    note('FAIL: ' + msg)
    stop_node(); sys.exit(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} - {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def dirsize(*paths):
    t = 0
    for p in paths:
        for root, _, files in os.walk(p):
            for f in files:
                try:
                    t += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    return t


def nt(cmd, **kw):
    return sh(f'{C}/bin/nodetool -p {JMXPORT} {cmd}', quiet=True, check=False, **kw)[1]


def tablestats(table='ks.t'):
    o = nt(f'tablestats {table}')
    g = lambda pat: (lambda m: int(float(m.group(1))) if m else None)(re.search(pat, o))
    return {'memtable_data_size': g(r'Memtable data size: (\d+)'), 'space_live': g(r'Space used \(live\): (\d+)'),
            'partitions_est': g(r'Number of partitions \(estimate\): (\d+)'), 'memtable_cells': g(r'Memtable cell count: (\d+)')}


def run_arm(name):
    thr, warn, failt = ARMS[name]
    D = f'{BASE}/{name}'
    os.makedirs(D, exist_ok=True)
    out = open(D + '/summary.txt', 'w')
    res = {'arm': name, 'threshold': thr, 'warn': warn, 'fail': failt}

    def anote(s):
        out.write(s + '\n'); out.flush(); note(f'[{name}] {s}')

    def aexpect(desc, cond):
        out.write(f'EXPECTED: {desc} - {"yes" if cond else "NO"}\n'); out.flush()
        return expect(f'[{name}] {desc}', cond)

    stop_node()
    if pid_of():
        fail('node still running')
    sh(f'rm -rf {BU}/data {BU}/commitlog {BU}/hints {BU}/logs {BU}/saved_caches {BU}/cdc_raw', check=False)
    _, y = sh(f'CASSANDRA_HOME={C} BU={BU} bash {HARNESS}/make-node-yaml.sh unlogged_batch_across_partitions_warn_threshold={thr} '
              f'batch_size_warn_threshold={warn} batch_size_fail_threshold={failt} range_request_timeout=600s read_request_timeout=600s native_transport_timeout=600s')
    anote('yaml: ' + y.strip().splitlines()[-1][:600])
    env = dict(os.environ, CASSANDRA_CONF=BU + '/conf', CASSANDRA_LOG_DIR=BU + '/logs', MAX_HEAP_SIZE='2G')
    env.pop('HEAP_NEWSIZE', None); env.pop('JVM_EXTRA_OPTS', None)
    sh(f'bin/cassandra -p {BU}/cassandra.pid > {D}/stdout.txt 2>&1', env=env)
    time.sleep(5)
    pid = pid_of()
    if pid is None:
        fail(f'node did not start; see {D}/stdout.txt')
    t0 = time.time()
    while time.time() - t0 < 300:
        if pid_of() is None:
            fail('node died during start-up')
        st, sb = nt('status'), nt('statusbinary')
        if re.search(r'^UN\s+127\.0\.4\.1\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
            break
        time.sleep(2)
    else:
        fail('node not UN / native transport not running in 300 s')
    anote(f'node up after {time.time() - t0:.0f} s, pid {pid}')
    jvm = open(f'/proc/{pid}/cmdline').read().replace('\0', ' ').split()
    aexpect('heap -Xms2G -Xmx2G (B3a)', '-Xms2G' in jvm and '-Xmx2G' in jvm)
    aexpect('G1 collector (B3a)', '-XX:+UseG1GC' in jvm)
    rc, o = sh(f'bin/cqlsh {ADDR} 9042 -e "CREATE KEYSPACE ks WITH replication = {{\'class\':\'SimpleStrategy\',\'replication_factor\':1}}; '
               f'CREATE TABLE ks.t (k int PRIMARY KEY, v text); CREATE TABLE ks.probe (k int PRIMARY KEY, v text);"', check=False, timeout=120)
    if rc != 0:
        fail('schema: ' + o[-400:])
    # the knob as the node sees it: the yaml line is the only source (no JMX attribute); check it in the node's own log of the config
    _, cfg = sh(f'grep -h "unlogged_batch_across_partitions_warn_threshold" {BU}/logs/system.log {BU}/logs/debug.log | head -2', check=False, quiet=True)
    mm = re.search(r'unlogged_batch_across_partitions_warn_threshold=(\d+)', cfg)
    aexpect(f'node reads the knob from the yaml: Config echo unlogged_batch_across_partitions_warn_threshold={thr}', bool(mm) and int(mm.group(1)) == thr)
    mm = re.search(r'batch_size_warn_threshold=([^;]+);', cfg); anote('Config echo batch_size_warn_threshold=' + (mm.group(1) if mm else '?'))
    mm = re.search(r'batch_size_fail_threshold=([^;]+);', cfg); anote('Config echo batch_size_fail_threshold=' + (mm.group(1) if mm else '?'))
    log0 = len(open(BU + '/logs/system.log', errors='replace').read().splitlines())
    gc0 = len(open(BU + '/logs/gc.log', errors='replace').read().splitlines())
    tprobe = time.time()
    # first-trigger probe (its WARN counts: NoSpamLogger allows one line per minute, so the probe's line suppresses the workload's for 60 s)
    rc, o = sh(f'python3 {HARNESS}/load.py probe {C} {ADDR}', check=False, timeout=180)
    try:
        pr = json.loads(o.strip().splitlines()[-1])
    except Exception:
        fail('probe output: ' + o[-400:])
    res['probe'] = pr
    anote('probe ' + json.dumps(pr))
    if name == 'ctl':
        ok = aexpect('first trigger: 500-key probe batch rejected "Batch too large" (positive control reaches the size branch)',
                     pr['failed'] == 1 and 'Batch too large' in pr['first_error'])
    elif thr < KEYS:
        ok = aexpect(f'first trigger: 500-key probe batch accepted with the unlogged-batch client warning (500 > {thr})', pr['ok'] == 1 and pr['warned'] == 1)
    else:
        ok = aexpect(f'first trigger: 500-key probe batch accepted without the warning (500 <= {thr})', pr['ok'] == 1 and pr['warned'] == 0)
    if not ok:
        fail('first-trigger check failed (the instrument cannot see the branch the arm depends on)')
    # samplers
    stop = threading.Event()

    def dsamp():
        with open(D + '/dirsize.csv', 'w') as f:
            f.write('epoch,data,commitlog\n')
            while not stop.is_set():
                f.write(f'{int(time.time())},{dirsize(BU + "/data")},{dirsize(BU + "/commitlog")}\n'); f.flush(); stop.wait(1)

    def tsamp():
        with open(D + '/tablestats.csv', 'w') as f:
            f.write('epoch,memtable_data_size,memtable_cells,space_live\n')
            while not stop.is_set():
                t = tablestats(); f.write(f"{int(time.time())},{t['memtable_data_size']},{t['memtable_cells']},{t['space_live']}\n"); f.flush(); stop.wait(15)
    def hsamp():
        # heap used from jcmd GC.heap_info (jstat cannot attach: the node runs with -XX:+PerfDisableSharedMem)
        with open(D + '/heap.csv', 'w') as f:
            f.write('epoch,heap_used_bytes\n')
            while not stop.is_set():
                o = sh(f'jcmd {pid} GC.heap_info', quiet=True, check=False, timeout=30)[1]
                m = re.search(r'garbage-first heap\s+total (\d+)K, used (\d+)K', o)
                if m:
                    f.write(f'{int(time.time())},{int(m.group(2)) * 1024}\n'); f.flush()
                stop.wait(0.5)
    th = [threading.Thread(target=dsamp), threading.Thread(target=tsamp), threading.Thread(target=hsamp)]
    [t.start() for t in th]
    tstart = time.time()
    rc, o = sh(f'python3 {HARNESS}/load.py run {C} {ADDR} --threads {THREADS} --batches {BATCHES} --keys {KEYS}', check=False, timeout=3600)
    tend = time.time()
    try:
        lr = json.loads(o.strip().splitlines()[-1])
    except Exception:
        stop.set(); jp.terminate(); fail('load output: ' + o[-500:])
    res['load'] = lr
    anote('load ' + json.dumps(lr))
    pre = tablestats()
    sh(f'jcmd {pid} GC.run', quiet=True, check=False, timeout=120); time.sleep(1)
    mh = re.search(r'garbage-first heap\s+total (\d+)K, used (\d+)K', sh(f'jcmd {pid} GC.heap_info', quiet=True, check=False, timeout=60)[1])
    heap_after_gc = int(mh.group(2)) * 1024 if mh else None
    stop.set(); [t.join() for t in th]
    nt('flush ks t')
    post = tablestats()
    rc, cnt = sh(f'bin/cqlsh {ADDR} 9042 --request-timeout=900 -e "SELECT count(*) FROM ks.t;"', check=False, timeout=1000)
    open(D + '/count.txt', 'w').write(cnt)
    m = re.search(r'^\s*(\d+)\s*$', cnt, re.M)
    count = int(m.group(1)) if m else None
    disk = {'data': dirsize(BU + '/data'), 'commitlog': dirsize(BU + '/commitlog')}
    # heap used: jcmd samples (heap.csv); GC pause time: sum of 'Pause ... N.NNNms' in gc.log lines written since the probe
    used = [int(l.split(',')[1]) for l in list(open(D + '/heap.csv'))[1:] if l.strip()]
    gl = open(BU + '/logs/gc.log', errors='replace').read().splitlines()[gc0:]
    pauses = [float(m.group(1)) for l in gl for m in [re.search(r'Pause .* (\d+\.\d+)ms$', l)] if m]
    gct = sum(pauses) / 1000
    res.update(count=count, pre_flush=pre, post_flush=post, disk=disk, heap_peak=max(used) if used else None,
               heap_mean=round(sum(used) / len(used)) if used else None, heap_samples=len(used), heap_after_gc=heap_after_gc, gc_seconds=round(gct, 3), gc_pauses=len(pauses),
               load_seconds=tend - tstart)
    lines = open(BU + '/logs/system.log', errors='replace').read().splitlines()[log0:]
    wl = [l for l in lines if re.search(r'^WARN .*Unlogged batch covering', l)]
    el = [l for l in lines if l.startswith('ERROR')]
    res['warn_log_lines'] = len(wl); res['error_log_lines'] = len(el)
    open(D + '/warn-lines.txt', 'w').write('\n'.join(l[:300] for l in wl[:20]) + '\n')
    open(D + '/error-lines.txt', 'w').write('\n'.join(l[:300] for l in el[:20]) + '\n')
    anote(f'count(*) {count}; pre-flush {pre}; post-flush {post}; disk {disk}; heap after load+GC.run {heap_after_gc}; heap peak {res["heap_peak"]} mean {res["heap_mean"]}; '
          f'{len(used)} heap samples; gc pause {gct:.3f} s in {len(pauses)} pauses; load {tend - tstart:.0f} s; WARN log lines {len(wl)}; ERROR lines {len(el)}')
    nwarn_max = int((tend - tprobe) // 60) + 2
    if name == 'ctl':
        aexpect('control: every batch rejected, rows acked 0, count(*) 0', lr['ok'] == 0 and lr['failed'] == THREADS * BATCHES and count == 0)
        aexpect('control: error text "Batch too large"', 'Batch too large' in lr['first_error'])
    else:
        aexpect(f'all {ROWS} rows acked and count(*) = {ROWS}', lr['rows'] == ROWS and lr['failed'] == 0 and count == ROWS)
        if thr < KEYS:
            aexpect(f'client warning on every batch ({THREADS * BATCHES})', lr['warned'] == THREADS * BATCHES)
            aexpect(f'1 to {nwarn_max} WARN log lines (NoSpamLogger, at most one per minute)', 1 <= len(wl) <= nwarn_max)
        else:
            aexpect('no client warning, no WARN log line', lr['warned'] == 0 and len(wl) == 0)
    json.dump(res, open(D + '/results.json', 'w'), indent=1)
    sh(f'cp {BU}/logs/system.log {D}/system.log', check=False)
    stop_node()
    aexpect('node stopped', pid_of() is None)
    return res


def compare(rs):
    r = {x['arm']: x for x in rs}
    if not all(a in r for a in ('t1', 't10', 't100000')):
        return
    note('--- cross-arm comparison (B3f: peak heap, GC time and disk agree within about 10% across the thresholds)')
    for key, get in (('heap_peak', lambda x: x['heap_peak']), ('gc_seconds', lambda x: x['gc_seconds']),
                     ('post_flush space_live', lambda x: x['post_flush']['space_live']), ('data dir bytes', lambda x: x['disk']['data']),
                     ('commitlog dir bytes', lambda x: x['disk']['commitlog']), ('load seconds', lambda x: x['load_seconds'])):
        vals = {a: get(r[a]) for a in ('t1', 't10', 't100000', 't10r') if a in r}
        lo, hi = min(vals.values()), max(vals.values())
        note(f'{key}: {vals}; max/min {hi / lo:.3f}' if lo else f'{key}: {vals}')
        if key in ('heap_peak', 'post_flush space_live', 'data dir bytes'):
            expect(f'{key} within 10% across thresholds (max/min <= 1.10)', lo and hi / lo <= 1.10)
    if 'ctl' in r and 't10' in r:
        note(f"heap after load + GC.run: { {a: r[a]['heap_after_gc'] for a in r} }")
        expect('control moved usage: control data dir bytes far below t10 (< 10%; the commit log directory holds pre-allocated segments and is not a usage reading)', r['ctl']['disk']['data'] < 0.1 * r['t10']['disk']['data'])


def main():
    if args[0] == 'down':
        stop_node(); return
    if args[0] == 'clean':
        stop_node(); sh(f'rm -rf {BU}', check=False); return
    sh(f'git describe --tags', quiet=True)
    note(f'cluster-run {RUN} {time.strftime("%F %T %Z")} host {os.uname().nodename} tree {C} batches/thread {BATCHES} rows/arm {ROWS}')
    _, md5 = sh(f'cd {HARNESS} && md5sum cluster-run.py load.py make-node-yaml.sh', quiet=True)
    note('harness md5 ' + ' '.join(f'{p[1]}={p[0][:12]}' for p in (l.split() for l in md5.splitlines()) if len(p) == 2))
    note('jvm: ' + sh('java -version 2>&1 | head -1', quiet=True)[1].strip())
    names = ['t1', 't10', 't100000', 't10r', 'ctl'] if args[0] == 'all' else [args[0]]
    rs = [run_arm(n) for n in names]
    if args[0] == 'all':
        compare(rs)
    left = sh("ps -eo pid,comm,args | awk '$2==\"java\" && /CassandraDaemon/ && /s4-b9-bu/'", quiet=True, check=False)[1].strip()
    note('leftover CassandraDaemon of this harness: ' + (left or 'none'))


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        fail(f'{type(e).__name__}: {e}')
