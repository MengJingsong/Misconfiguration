#!/usr/bin/env python3
"""Cluster-tier driver for diagnostic_event_memory_store_max_size-store-keyhead--autonomous (B3 + amendment 2026-10-27 C1-C8).
usage: cluster-run.py <arm> [run-name]
  arm  S-50 | S-200 | S-1000   small statements (~200 B), cumulative N, source copy with literal maxSize M (run2=50, run1=200, run3=1000)
       L-50 | L-200 | L-1000   256 KiB statements, cumulative N in 100,200,400,2000, fresh node
       OFF                     like L-200 but the persistence subscription is never made (one condition changed)
  S-200 also runs the second class (SchemaEvent, C5) and the client-side retainer control (C2d).
One node at a time, 127.0.0.1, JMX 7199 (local, no auth), storage under ~/stage4-diag/<run>/<arm>/ on local disk.
Every command and its output go to <logdir>/commands.log; readings to <logdir>/readings.jsonl; hist/heap raw files alongside."""
import glob, json, os, re, shutil, subprocess, sys, time

ARM = sys.argv[1]
RUN = sys.argv[2] if len(sys.argv) > 2 else 'run1'
HOME = os.path.expanduser('~')
HDIR = os.path.dirname(os.path.abspath(__file__))
M = int(ARM.split('-')[1]) if '-' in ARM else 200   # OFF and QOFF: default literal
SRC = {50: 'cassandra-run2', 200: 'cassandra-run1', 1000: 'cassandra-run3'}[M]
CASS = os.path.join(HOME, SRC)
ARMDIR = os.path.join(HOME, 'stage4-diag', RUN, ARM)           # node data: local disk
LOG = os.path.join(HOME, 'stage4-logs', 'diag', RUN, ARM)
QUERY = ARM.startswith('Q-') or ARM == 'QOFF'                    # supplementary S1: 256 KiB SELECT (comment padding), nothing is written to the memtable
LARGE = ARM.startswith('L-') or ARM in ('OFF', 'QOFF') or QUERY
S_BYTES = 256 * 1024
HEAP = '2G' if LARGE else '1G'                                  # amendment C8
CPS = [100, 200, 400, 2000] if LARGE else ([100, 200, 201, 1000, 20000] if M == 200 else [100, 200, 201, 1000, 3000])
AUDIT = 'org.apache.cassandra.audit.AuditEvent'
SCHEMA = 'org.apache.cassandra.schema.SchemaEvent'
GUAVA = glob.glob(os.path.join(CASS, 'lib', 'guava-*.jar'))[0]   # defect R-D2: SchemaEvent.toMap returns a Guava ImmutableSet; the JMX client needs Guava to unmarshal it
os.makedirs(LOG, exist_ok=True)
CMDLOG = open(os.path.join(LOG, 'commands.log'), 'a')
READ = open(os.path.join(LOG, 'readings.jsonl'), 'a')
PID = None


def log(s):
    line = time.strftime('%FT%T') + ' ' + s
    CMDLOG.write(line + '\n'); CMDLOG.flush(); print(line, flush=True)


def sh(cmd, env=None, timeout=900, check=True):
    log('$ ' + cmd)
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env, timeout=timeout)
    out = (p.stdout + p.stderr)
    CMDLOG.write(out[:4000] + ('...[truncated]\n' if len(out) > 4000 else '')); CMDLOG.flush()
    if check and p.returncode != 0:
        raise SystemExit('FAILED rc=%d: %s' % (p.returncode, cmd))
    return p.stdout


def jmx(*args):
    return sh('java -Xmx3g -cp %s:%s DiagJmx 7199 %s' % (HDIR + '/classes', GUAVA, ' '.join(args)))


def make_conf():
    shutil.rmtree(ARMDIR, ignore_errors=True)
    for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
        os.makedirs(os.path.join(ARMDIR, d))
    conf = os.path.join(ARMDIR, 'conf')
    shutil.copytree(os.path.join(CASS, 'conf'), conf)
    add = ['diagnostic_events_enabled: true',
           'audit_logging_options:', '  enabled: true', '  logger:', '    - class_name: DiagnosticEventAuditLogger',
           'data_file_directories:', '    - %s/data' % ARMDIR,
           'commitlog_directory: %s/commitlog' % ARMDIR, 'hints_directory: %s/hints' % ARMDIR,
           'saved_caches_directory: %s/saved_caches' % ARMDIR, 'cdc_raw_directory: %s/cdc_raw' % ARMDIR]
    keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
    out, skip = [], False
    for l in open(os.path.join(CASS, 'conf', 'cassandra.yaml')).read().splitlines():
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
    open(os.path.join(conf, 'cassandra.yaml'), 'w').write('\n'.join(out) + '\n# ---- stage4 diag lines ----\n' + '\n'.join(add) + '\n')
    log('yaml tail: ' + ' ; '.join(add))


def start():
    global PID
    sh('ss -ltn | grep -E ":(7000|7199|9042) " || true', check=False)
    make_conf()
    env = dict(os.environ, CASSANDRA_CONF=os.path.join(ARMDIR, 'conf'), CASSANDRA_LOG_DIR=os.path.join(ARMDIR, 'logs'),
               MAX_HEAP_SIZE=HEAP, HEAP_NEWSIZE='256M')
    pidf = os.path.join(ARMDIR, 'pid')
    sh('cd %s && bin/cassandra -p %s > %s/logs/stdout.log 2>&1' % (CASS, pidf, ARMDIR), env=env)
    t0 = time.time()
    while time.time() - t0 < 240:
        time.sleep(3)
        if not os.path.exists(pidf):
            continue
        PID = int(open(pidf).read().strip())
        if subprocess.run('kill -0 %d' % PID, shell=True).returncode != 0:
            raise SystemExit('daemon died during start')
        o = subprocess.run('cd %s && CASSANDRA_CONF=%s/conf bin/nodetool statusbinary' % (CASS, ARMDIR), shell=True, capture_output=True, text=True, env=env).stdout
        if o.strip() == 'running':
            break
    else:
        raise SystemExit('node did not come up')
    log('node up pid %d after %.0fs; heap %s; source %s' % (PID, time.time() - t0, HEAP, SRC))
    sh('ps -o pid,args -p %d | cut -c1-600' % PID)


def stop():
    if PID:
        sh('kill %d; for i in $(seq 1 60); do kill -0 %d 2>/dev/null || break; sleep 1; done; kill -9 %d 2>/dev/null; true' % (PID, PID, PID), check=False)


def hist(label):
    raw = sh('jcmd %d GC.class_histogram' % PID, timeout=300)
    open(os.path.join(LOG, 'hist-%s.txt' % label), 'w').write(raw)
    d = {}
    for l in raw.splitlines():
        p = l.split()
        if len(p) >= 4 and p[0].endswith(':'):
            d[p[3]] = (int(p[1]), int(p[2]))
    return d


def reading(label, n, extra=None, read_classes=(AUDIT,), do_read=True):
    h = hist(label)
    hi = sh('jcmd %d GC.heap_info' % PID)
    m = re.search(r'used (\d+)K', hi)
    r = {'arm': ARM, 'M': M, 'label': label, 'N': n, 't': int(time.time() * 1000), 'heap_used_after_gc': int(m.group(1)) * 1024 if m else None}
    for k, nm in (('AuditEvent', AUDIT), ('AuditLogEntry', 'org.apache.cassandra.audit.AuditLogEntry'), ('SchemaEvent', SCHEMA),
                  ('bytes[]', '[B'), ('String', 'java.lang.String')):
        r['hist_' + k] = h.get(nm)
    if do_read:
        for c in read_classes:
            o = jmx('read', c)
            mm = re.search(r'READ (\S+) count=(\d+) minKey=(-?\d+) maxKey=(-?\d+) opBytes=(\d+)', o)
            r['read_' + c.split('.')[-1]] = {'count': int(mm.group(2)), 'minKey': int(mm.group(3)), 'maxKey': int(mm.group(4)), 'opBytes': int(mm.group(5))}
    if extra:
        r.update(extra)
    READ.write(json.dumps(r) + '\n'); READ.flush()
    log('READING ' + json.dumps(r))
    return r


# ---------------- client (bundled Python driver, protocol 4, one thread, simple statements) ----------------
def driver():
    import glob as g
    z = max(g.glob(os.path.join(CASS, 'lib', 'cassandra-driver-internal-only-*.zip')))
    ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
    sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
    for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
        zz = g.glob(os.path.join(CASS, 'lib', lib + '*.zip'))
        if zz:
            sys.path.insert(0, max(zz))
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra.policies import WhiteListRoundRobinPolicy
    from cassandra import ConsistencyLevel
    prof = ExecutionProfile(request_timeout=60, consistency_level=ConsistencyLevel.ONE, load_balancing_policy=WhiteListRoundRobinPolicy(['127.0.0.1']))
    c = Cluster(['127.0.0.1'], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, token_metadata_enabled=False)
    return c, c.connect()


SESSION = None
NEXT_ID = 0


def run_statements(count, size=None):
    """INSERT INTO ks.t (id, v) VALUES (<i>, '<size bytes>') x count, one at a time."""
    global NEXT_ID
    pad = 'x' * (S_BYTES if LARGE else 200)
    t0 = time.time()
    for _ in range(count):
        if QUERY:
            SESSION.execute("SELECT id FROM ks.t WHERE id = %d /* %s */" % (NEXT_ID, pad))
        else:
            SESSION.execute("INSERT INTO ks.t (id, v) VALUES (%d, '%s')" % (NEXT_ID, pad))
        NEXT_ID += 1
    log('client: %d statements of %d value bytes in %.1fs (ids up to %d)' % (count, len(pad), time.time() - t0, NEXT_ID - 1))


def main():
    global SESSION
    sh('mkdir -p %s/classes && javac -d %s/classes %s/DiagJmx.java' % (HDIR, HDIR, HDIR))
    start()
    try:
        reading('00-baseline-pre', 0, do_read=False)
        jmx('enabled')
        if ARM not in ('OFF', 'QOFF'):
            jmx('enable', AUDIT)
        c, SESSION = driver()
        SESSION.execute("CREATE KEYSPACE ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        SESSION.execute("CREATE TABLE ks.t (id int PRIMARY KEY, v text)")
        time.sleep(2)
        reading('01-baseline-after-schema', 0)
        done = 0
        for cp in CPS:
            run_statements(cp - done)
            done = cp
            time.sleep(2)
            reading('N%05d' % cp, cp)
        if ARM == 'S-200':
            # 30 s after the last statement: plateau
            time.sleep(30)
            reading('N20000-plus30s', done)
            # C5: second class
            jmx('enable', SCHEMA)
            reading('c5-baseline', done, read_classes=(AUDIT, SCHEMA))
            SESSION.execute("USE ks")
            for i in range(250):
                SESSION.execute("ALTER TABLE ks.t WITH comment = 'c%d'" % i)
            time.sleep(2)
            reading('c5-after250alter', done, read_classes=(AUDIT, SCHEMA))
            # C2d: client-side unbounded retainer vs the store
            stopf = os.path.join(LOG, 'drain.stop')
            if os.path.exists(stopf):
                os.remove(stopf)
            dr = subprocess.Popen('java -Xmx3g -cp %s/classes:%s DiagJmx 7199 drain %s 50 %s > %s/drain.out 2>&1' % (HDIR, GUAVA, AUDIT, stopf, LOG), shell=True)
            time.sleep(3)
            run_statements(3000)
            time.sleep(3)
            open(stopf, 'w').write('stop')
            dr.wait(timeout=60)
            log('drain control: ' + open(os.path.join(LOG, 'drain.out')).read().strip().splitlines()[-1])
            reading('drain-after3000', done + 3000)
        c.shutdown()
        log('ARM DONE ' + ARM)
    finally:
        stop()


main()
