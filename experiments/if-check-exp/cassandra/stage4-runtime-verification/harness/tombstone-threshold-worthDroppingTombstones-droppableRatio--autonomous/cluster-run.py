#!/usr/bin/env python3
"""Stage 4, cluster tier, tombstone-threshold-worthDroppingTombstones-droppableRatio--autonomous (B3 as amended, 2026-10-26).
usage: cluster-run.py [run-name]        output: ~/s4-b10-td-logs/<run-name, default run1>/cluster/
One node on 127.0.3.1 (port slot 3: JMX 7130, native 9042), tree ~/s4-b10-td-n (ant jar), conf ~/s4-b10-td-node, data on tmpfs
/dev/shm/s4-b10-td, -Xms2G -Xmx2G. 14 tables (B3b). Load (load.py, TTL 120 s), flush, disableautocompaction; wait until last write
+ WAIT_EXTRA seconds (default 210 = 120 TTL + 60 histogram rounding + 10 gc_grace + 20); record du and sstablemetadata ratio; one
'enableautocompaction' on ks; observe OBS seconds (default 300) with du every 30 s; ratios again; 'nodetool compact ks pc'; du.
Environment overrides for plumbing shakedowns only: TD_ROWS (200000), TD_TTL (120), TD_WAIT (210), TD_OBS (300).
Every command is logged to session.log; EXPECTED lines go to summary.txt, then analyze-cluster.py. The node is stopped on any exit.
Exit 1: a set-up or instrument check failed."""
import csv, glob, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b10-td-n')
HARNESS = os.path.dirname(os.path.abspath(__file__))
TDN = HOME + '/s4-b10-td-node'
DD = '/dev/shm/s4-b10-td'
RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
D = f'{HOME}/s4-b10-td-logs/{RUN}/cluster'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
ADDR, JMX = '127.0.3.1', 7130
ROWS = int(os.environ.get('TD_ROWS', '200000'))
TTL = int(os.environ.get('TD_TTL', '120'))
WAIT = int(os.environ.get('TD_WAIT', '210'))
OBS = int(os.environ.get('TD_OBS', '300'))
DRV = HOME + '/s4-b10-td-drv/cassandra-driver-3.29.0'

# name -> (pct TTL'd, options)
def opts(x=None, interval='60', unchecked='true'):
    o = {'class': 'SizeTieredCompactionStrategy', 'tombstone_compaction_interval': interval, 'unchecked_tombstone_compaction': unchecked}
    if x is not None:
        o['tombstone_threshold'] = x
    return o
TABLES = {}
for tag, x in (('05', '0.05'), ('20', '0.2'), ('40', '0.4'), ('70', '0.7'), ('150', '1.5')):
    TABLES['a' + tag] = (50, opts(x))
    TABLES['b' + tag] = (15, opts(x))
TABLES['adef'] = (50, opts(None))
TABLES['gi'] = (50, opts('0.05', interval='86400'))
TABLES['go'] = (50, opts('0.05', unchecked='false'))
TABLES['pc'] = (50, opts('1.5'))
ORDER = list(TABLES)


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); SESSION.write(s + '\n'); SESSION.flush()


def sh(cmd, timeout=600, check=True, env=None, quiet=False):
    if not quiet:
        log('+ ' + cmd[:400])
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=C)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd[:200]}\n{out[-800:]}')
    return r.returncode, out


def java_daemons():
    r = subprocess.run(['ps', '-eo', 'pid,comm,args'], capture_output=True, text=True)
    out = []
    for l in r.stdout.splitlines()[1:]:
        p = l.split(None, 2)
        if len(p) == 3 and p[1] == 'java' and 'org.apache.cassandra.service.CassandraDaemon' in p[2]:
            out.append(p[0] + ' ' + p[2])
    return out


def pid_of():
    for l in java_daemons():
        if TDN in l:
            return int(l.split()[0])
    return None


def stop_node():
    p = pid_of()
    if p:
        sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} stopdaemon', check=False, timeout=120)
        for _ in range(60):
            if pid_of() is None:
                break
            time.sleep(1)
        if pid_of():
            sh(f'kill -9 {pid_of()}', check=False)
            time.sleep(2)
    if pid_of():
        log('WARNING: my CassandraDaemon is still running')


def fail(msg):
    note('FAIL: ' + msg)
    stop_node()
    sys.exit(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def nt(args, **kw):
    return sh(f'bin/nodetool -h 127.0.0.1 -p {JMX} {args}', **kw)


def du(name):
    d = glob.glob(f'{DD}/data/data/ks/{name}-*')
    if not d:
        return -1
    _, o = sh(f'du -sb {d[0]}', check=False, quiet=True)
    return int(o.split()[0]) if o.strip() else -1


def ratios(tag):
    res = {}
    for name in ORDER:
        d = glob.glob(f'{DD}/data/data/ks/{name}-*')
        fs = sorted(glob.glob(d[0] + '/*-Data.db')) if d else []
        vals = []
        for f in fs:
            env = dict(os.environ, CASSANDRA_CONF=TDN + '/conf')
            _, o = sh(f'tools/bin/sstablemetadata --gc_grace_seconds 10 {f}', check=False, env=env, quiet=True)
            m = re.search(r'Estimated droppable tombstones:\s*([0-9.eE+-]+)', o)
            vals.append(float(m.group(1)) if m else float('nan'))
        res[name] = vals
        SESSION.write(f'ratio[{tag}] {name} {vals}\n')
    SESSION.flush()
    return res


def start_node():
    stop_node()
    if pid_of():
        fail('my CassandraDaemon is still running')
    sh(f'rm -rf {DD} {TDN}/logs', check=False)
    _, y = sh(f'{HARNESS}/make-node-yaml.sh concurrent_compactors=2 compaction_throughput=0MiB/s')
    note('yaml: ' + y.strip().splitlines()[-1][:1500])
    env = dict(os.environ, CASSANDRA_CONF=TDN + '/conf', CASSANDRA_LOG_DIR=TDN + '/logs', MAX_HEAP_SIZE='2G')
    env.pop('HEAP_NEWSIZE', None)
    env['JVM_EXTRA_OPTS'] = f'-Xlog:gc:file={D}/gc.log:utc'
    sh(f'ulimit -n 100000 && bin/cassandra -p {TDN}/cassandra.pid > {D}/stdout.txt 2>&1', env=env)
    time.sleep(5)
    if pid_of() is None:
        fail(f'node did not start; see {D}/stdout.txt')
    t0 = time.time()
    while time.time() - t0 < 300:
        if pid_of() is None:
            fail('node died during start-up')
        _, st = nt('status', check=False, quiet=True)
        _, sb = nt('statusbinary', check=False, quiet=True)
        if re.search(rf'^UN\s+{re.escape(ADDR)}\s', st, re.M) and re.search(r'^running\s*$', sb, re.M):
            log(f'node UN and native transport running after {time.time() - t0:.0f} s')
            break
        time.sleep(2)
    else:
        fail('node not UN / native transport not running in 300 s')
    jvm = open(f'/proc/{pid_of()}/cmdline').read().replace('\0', ' ')
    flags = [t for t in jvm.split() if t.startswith(('-Xm', '-XX:+Use', '-Xlog'))]
    note('jvm: ' + ' '.join(flags))
    expect('heap -Xms2G -Xmx2G (B3a)', '-Xms2G' in jvm.split() and '-Xmx2G' in jvm.split())
    if '-Xms2G' not in jvm.split():
        fail('heap is not 2G')


def cql(stmt, timeout=120):
    return sh(f'bin/cqlsh {ADDR} 9042 -e "{stmt}"', check=False, timeout=timeout)


def load(groups):
    env = dict(os.environ, TD_DRIVER=DRV)
    procs = []
    for i, g in enumerate(groups):
        log(f'loader {i}: {g}')
        procs.append(subprocess.Popen(['python3', '-I', f'{HARNESS}/load.py', ADDR, str(ROWS), str(TTL)] + g, env=env,
                                      stdout=open(f'{D}/load-{i}.out', 'w'), stderr=subprocess.STDOUT))
    return procs


def main():
    sh(f'test -d {DRV} || (mkdir -p {HOME}/s4-b10-td-drv && cd {HOME}/s4-b10-td-drv && unzip -qo {C}/lib/cassandra-driver-internal-only-3.29.0.zip "cassandra-driver-3.29.0/*")')
    start_node()
    rc, out = cql("CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1};")
    if rc != 0:
        fail('keyspace: ' + out[-300:])
    for name in ORDER:
        o = TABLES[name][1]
        copt = '{' + ', '.join(f"'{k}':'{v}'" for k, v in o.items()) + '}'
        rc, out = cql(f"CREATE TABLE ks.{name} (k int PRIMARY KEY, v blob) WITH gc_grace_seconds = 10 AND compaction = {copt};")
        if rc != 0:
            fail(f'create {name}: ' + out[-300:])
    nt('disableautocompaction ks')
    # instrument: options read back
    rc, out = cql("SELECT table_name, compaction, gc_grace_seconds FROM system_schema.tables WHERE keyspace_name='ks';")
    open(D + '/schema-readback.txt', 'w').write(out)
    okopt = True
    for name in ORDER:
        o = TABLES[name][1]
        m = re.search(rf'^\s*{name}\s*\|(.*)$', out, re.M)
        line = m.group(1) if m else ''
        for k, v in o.items():
            vv = 'org.apache.cassandra.db.compaction.' + v if k == 'class' else v
            if f"'{k}': '{vv}'" not in line:
                okopt = False
        if o.get('tombstone_threshold') is None and 'tombstone_threshold' in line:
            okopt = False
        if '10' not in line.split('|')[-1]:
            okopt = False
    if not expect('14 tables exist with the B3b compaction options and gc_grace_seconds 10 (system_schema.tables)', okopt):
        fail('schema read-back differs; see schema-readback.txt')
    # load in 3 parallel loaders, flush each table after its loader finishes it (one process per group, tables in sequence)
    groups = [[f'{n}:{TABLES[n][0]}' for n in ORDER[i::3]] for i in range(3)]
    procs = load(groups)
    t_load0 = time.time()
    done = set()
    while len(done) < 14:
        for i in range(3):
            for l in open(f'{D}/load-{i}.out').read().splitlines():
                m = re.match(r'loaded (\w+) rows=(\d+) ttl_rows=(\d+) t_last_write=(\d+)', l)
                if m and m.group(1) not in done:
                    done.add(m.group(1))
                    nt(f'flush ks {m.group(1)}', timeout=300)
        if any(p.poll() not in (None, 0) for p in procs):
            fail('a loader exited with an error; see load-*.out')
        if time.time() - t_load0 > 1800:
            fail('loading did not finish in 30 min')
        time.sleep(2)
    last = 0
    for i in range(3):
        for l in open(f'{D}/load-{i}.out').read().splitlines():
            m = re.match(r'loaded (\w+) rows=(\d+) ttl_rows=(\d+) t_last_write=(\d+)', l)
            if m:
                last = max(last, int(m.group(4)))
                if m.group(1) in ('a05', 'b05'):
                    note(f'load check {m.group(1)}: rows={m.group(2)} ttl_rows={m.group(3)}')
    # overlap sstable for go
    rc, out = sh(f'TD_DRIVER={DRV} python3 -I {HARNESS}/load.py {ADDR} extra go 2000', check=False, timeout=300)
    if rc != 0:
        fail('extra load for go: ' + out[-300:])
    last = max(last, int(time.time()))
    nt('flush ks go', timeout=300)
    _, nb = nt('tablestats ks.go', check=False, quiet=True)
    m = re.search(r'SSTable count:\s*(\d+)', nb)
    expect(f'go has 2 sstables (first load + overlap sstable): {m.group(1) if m else "?"}', bool(m) and m.group(1) == '2')
    sc = {}
    for name in ORDER:
        sc[name] = len(glob.glob(glob.glob(f'{DD}/data/data/ks/{name}-*')[0] + '/*-Data.db'))
    expect('every table except go has exactly 1 sstable after the flush: ' + str(sc), all(v == 1 for k, v in sc.items() if k != 'go') and sc['go'] == 2)
    peak = {n: du(n) for n in ORDER}
    note('peak du (bytes): ' + ' '.join(f'{n}={v}' for n, v in peak.items()))
    expect('peak du of every table between 30 and 90 MB', all(30e6 < v < 90e6 for v in peak.values()) or ROWS != 200000)
    wait_until = last + WAIT
    log(f'waiting until {wait_until} (last write {last} + {WAIT} s)')
    while time.time() < wait_until:
        if pid_of() is None:
            fail('node died during the wait')
        time.sleep(5)
    r0 = ratios('before-enable')
    du0 = {n: du(n) for n in ORDER}
    open(D + '/ratios.csv', 'w').write('when,table,ratios,du\n' + ''.join(f'before-enable,{n},{" ".join(map(str, r0[n]))},{du0[n]}\n' for n in ORDER))
    note('ratio before enable: ' + ' '.join(f'{n}={"/".join(f"{x:.3f}" for x in r0[n])}' for n in ORDER))
    note('du before enable: ' + ' '.join(f'{n}={v}' for n, v in du0.items()))
    expect('no compaction ran before the enable (du unchanged from the peak, every table)', all(du0[n] == peak[n] for n in ORDER))
    # enable all at once
    t_en = int(time.time())
    nt('enableautocompaction ks')
    note(f'enableautocompaction ks at epoch {t_en}')
    f = open(D + '/du.csv', 'w'); w = csv.writer(f); w.writerow(['t_rel'] + ORDER)
    t0 = time.time()
    while time.time() - t0 < OBS:
        if pid_of() is None:
            fail('node died during the observation window')
        w.writerow([int(time.time() - t0)] + [du(n) for n in ORDER]); f.flush()
        time.sleep(max(0, 30 - ((time.time() - t0) % 30)))
    w.writerow([int(time.time() - t0)] + [du(n) for n in ORDER]); f.flush()
    r1 = ratios('after-window')
    du1 = {n: du(n) for n in ORDER}
    open(D + '/ratios.csv', 'a').write(''.join(f'after-window,{n},{" ".join(map(str, r1[n]))},{du1[n]}\n' for n in ORDER))
    note('ratio after window: ' + ' '.join(f'{n}={"/".join(f"{x:.3f}" for x in r1[n])}' for n in ORDER))
    _, cs = nt('compactionstats', check=False)
    open(D + '/compactionstats-end.txt', 'w').write(cs)
    # positive control
    rc, out = nt('compact ks pc', check=False, timeout=900)
    duc = du('pc')
    note(f'pc: du before nodetool compact {du1["pc"]}, after {duc}')
    open(D + '/ratios.csv', 'a').write(f'after-compact,pc,,{duc}\n')
    shutil_log()
    stop_node()
    expect('no CassandraDaemon of this run left', pid_of() is None)
    out = subprocess.run(['python3', f'{HARNESS}/analyze-cluster.py', D, str(ROWS)], capture_output=True, text=True).stdout
    open(D + '/analysis.txt', 'w').write(out)
    note(out)


def shutil_log():
    for src, dst in ((TDN + '/logs/system.log', D + '/system.log'), (TDN + '/logs/debug.log', D + '/debug.log')):
        if os.path.exists(src):
            subprocess.run(['cp', src, dst])


if __name__ == '__main__':
    try:
        note(f'cluster-run {time.strftime("%F %T")} host {os.uname().nodename} rows {ROWS} ttl {TTL} wait {WAIT} obs {OBS}')
        note('harness md5 ' + subprocess.run(f'cd {HARNESS} && md5sum cluster-run.py load.py analyze-cluster.py make-node-yaml.sh', shell=True, capture_output=True, text=True).stdout.replace(chr(10), ' '))
        main()
    except SystemExit:
        raise
    except Exception as e:
        note(f'FAIL: exception {e!r}')
        stop_node()
        sys.exit(1)
    finally:
        stop_node()
