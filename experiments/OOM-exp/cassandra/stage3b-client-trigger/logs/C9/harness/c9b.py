#!/usr/bin/env python3
"""C9 stage 3-b confirm (pc99, 2026-11-23). Runs locally on pc99. Launcher, waits and teardown from the stage-2
harness (c9.py); this file adds: authentication on, roles and grants by the superuser, the attacker (role mallory,
CREATE ON ALL KEYSPACES only) building its own 2,000-sstable table through the table option
memtable_flush_period_in_ms (no JMX flush) and scanning it, a victim role with its own keyspace measuring
per-request success and latency, a restart after the endpoint and a repeat attack.
usage:
  c9b.py setup              copy harness to $B/h, compile C9Jmx
  c9b.py run <run-id>       one confirm run from an empty data directory
  c9b.py queue <run-id> ... sequential
Layout B=/mydata/s4/3b-C9: h/, inst/<run>/, runs/<run>/{scan1,scan2}/, dumps/ (scanned, then deleted)."""
import glob, os, re, shutil, signal, subprocess, sys, threading, time

B = '/mydata/s4/3b-C9'
CH = '/mydata/s4/cassandra-base'
H = os.path.dirname(os.path.abspath(__file__))   # /mydata/s4/3b-C9/h (R runs) or h2 (data arm)
ARM = os.environ.get('C9B_ARM', 'ddl')          # ddl: attacker = DDL role builds its own table; data: admin table, attacker SELECT only
NODE_CPUS, CLIENT_CPUS = '0-19', '20-31'
JPORT = 7199
NT = f'{CH}/bin/nodetool -h 127.0.0.1 -p {JPORT}'
HEAP, DIRECT = 4096, 2048          # B2, the verified test arm T2 (V7)
PERIOD_MS = int(os.environ.get('C9B_PERIOD', '200'))
C, D = 40, int(os.environ.get('C9B_D', '300'))   # T2: 40 scan workers, D <= 300 s (C9B_D only for the smoke test)
TARGET = int(os.environ.get('C9B_TARGET', '2000'))  # sstables (smoke test only: lower)
LOGF = None
PH = None


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, flush=True)
    if LOGF:
        LOGF.write(line + '\n'); LOGF.flush()


def phase(name):
    t = int(time.time() * 1000)
    PH.write(f'{name},{t}\n'); PH.flush()
    log(f'PHASE {name}')
    return t


def sh(cmd, timeout=600, check=False, quiet=False):
    if not quiet:
        log('+ ' + cmd)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or '') + (r.stderr or ''); rc = r.returncode
    except subprocess.TimeoutExpired:
        out = f'TIMEOUT after {timeout}s'; rc = -999
    if not quiet and LOGF:
        LOGF.write(out[-3000:] + f'\n  rc={rc}\n'); LOGF.flush()
    if check and rc != 0:
        raise RuntimeError(f'rc={rc}: {cmd}\n{out[-800:]}')
    return rc, out


def daemons():
    out = []
    for p in glob.glob('/proc/[0-9]*/cmdline'):
        try:
            c = open(p, 'rb').read().replace(b'\0', b' ').decode(errors='replace')
        except OSError:
            continue
        if 'CassandraDaemon' in c and c.split(' ')[0].endswith('java'):
            out.append((int(p.split('/')[2]), c))
    return out


def node_pid(inst):
    for p, c in daemons():
        if inst + '/' in c:
            return p
    return None


def start(inst, unit, rundir):
    for d in ('logs', 'dumps', 'hints', 'saved_caches', 'cdc_raw', 'data', 'commitlog'):
        os.makedirs(f'{inst}/{d}', exist_ok=True)
    shutil.rmtree(inst + '/conf', ignore_errors=True)
    shutil.copytree(CH + '/conf', inst + '/conf')
    y = open(CH + '/conf/cassandra.yaml').read()
    # security settings (not capacity constraints): password authentication and CassandraAuthorizer
    y, n1 = re.subn(r'^authenticator: AllowAllAuthenticator$', 'authenticator: PasswordAuthenticator', y, flags=re.M)
    y, n2 = re.subn(r'^authorizer: AllowAllAuthorizer$', 'authorizer: CassandraAuthorizer', y, flags=re.M)
    assert n1 == 1 and n2 == 1 and re.search(r'^role_manager: CassandraRoleManager$', y, re.M)
    add = [f'data_file_directories: [{inst}/data]', f'commitlog_directory: {inst}/commitlog', f'hints_directory: {inst}/hints',
           f'saved_caches_directory: {inst}/saved_caches', f'cdc_raw_directory: {inst}/cdc_raw']
    open(inst + '/conf/cassandra.yaml', 'w').write(y + '\n# ---- C9 3-b confirm lines (environment) ----\n' + '\n'.join(add) + '\n')
    sh(f'diff {CH}/conf/cassandra.yaml {inst}/conf/cassandra.yaml > {rundir}/yaml.diff', quiet=True)
    env = (f'CASSANDRA_CONF={inst}/conf CASSANDRA_LOG_DIR={inst}/logs CASSANDRA_HEAPDUMP_DIR={inst}/dumps '
           f'MAX_HEAP_SIZE={HEAP}M MAX_DIRECT_MEMORY_SIZE={DIRECT}M JVM_EXTRA_OPTS=-Dcassandra.printHeapHistogramOnOutOfMemoryError=true')
    inner = (f'cd {inst}; ulimit -n 100000; exec systemd-run --user --scope -p MemorySwapMax=0 --unit {unit} '
             f'taskset -c {NODE_CPUS} {CH}/bin/cassandra -f')
    cmd = f"( setsid nohup env -u HEAP_NEWSIZE {env} bash -c '{inner}' < /dev/null >> {inst}/logs/launch.log 2>&1 & )"
    sh(cmd, timeout=30)
    log(f'start: heap {HEAP} MiB, direct {DIRECT} MiB, auth on, yaml add: {add}')


def wait_up(inst, timeout=240):
    t0 = time.time(); seen = False
    while time.time() - t0 < timeout:
        p = node_pid(inst)
        if p is None and seen:
            return None
        if p is not None:
            seen = True
            rc, st = sh(f'{NT} statusbinary', timeout=30, quiet=True)
            if re.search(r'^running\s*$', st, re.M):
                log(f'node up (pid {p}) after {time.time() - t0:.0f} s')
                return p
        time.sleep(2)
    return None


def stop_node(inst, unit, graceful=True):
    p = node_pid(inst)
    if p is not None:
        if graceful:
            sh(f'{NT} stopdaemon', timeout=70)
            for _ in range(40):
                if node_pid(inst) is None:
                    break
                time.sleep(1)
        p = node_pid(inst)
        if p is not None:
            log(f'kill -9 {p}'); os.kill(p, signal.SIGKILL); time.sleep(2)
    sh(f'systemctl --user stop {unit}.scope', timeout=30, quiet=True)
    return node_pid(inst) is None


class Rss(threading.Thread):
    def __init__(self, pid, path):
        super().__init__(daemon=True); self.pid = pid; self.f = open(path, 'a'); self.f.write('ms,rss_anon_kb,vmrss_kb\n'); self.ev = threading.Event()

    def run(self):
        while not self.ev.is_set():
            try:
                st = open(f'/proc/{self.pid}/status').read()
                a = re.search(r'RssAnon:\s+(\d+)', st).group(1); r = re.search(r'VmRSS:\s+(\d+)', st).group(1)
                self.f.write(f'{int(time.time() * 1000)},{a},{r}\n'); self.f.flush()
            except (OSError, AttributeError):
                pass
            self.ev.wait(1.0)


def jcount():
    rc, o = sh(f'java -Xmx64m -cp {H} C9Jmx count {JPORT}', timeout=60, quiet=True)
    m = re.search(r'live (-?\d+) pending_compactions (-?\d+) table_pending (-?\d+)', o)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (None, None, None)


def sampler(csv):
    return subprocess.Popen(['taskset', '-c', CLIENT_CPUS, 'java', '-Xmx64m', '-cp', H, 'C9Jmx', 'poll', str(JPORT), csv, '200'],
                            stdout=open(csv + '.out', 'w'), stderr=subprocess.STDOUT, start_new_session=True)


def killpg(p):
    if p is None:
        return
    try:
        os.killpg(p.pid, signal.SIGTERM); time.sleep(1); os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def admin(rundir):
    """Superuser (default cassandra/cassandra, created by CassandraRoleManager after startup): roles, grants, victim schema."""
    sys.path.insert(0, H)
    from c9b_drv import connect
    f = open(rundir + '/admin.log', 'w', buffering=1)
    cl = s = None
    t0 = time.time()
    while time.time() - t0 < 120:
        try:
            cl, s = connect('cassandra', 'cassandra', timeout=60)
            break
        except Exception as e:
            err = f'{type(e).__name__}: {str(e)[:150]}'
            time.sleep(2)
    if s is None:
        raise SystemExit('superuser login failed: ' + err)
    f.write(f'superuser login after {time.time() - t0:.0f} s\n')
    stmts = ["CREATE ROLE mallory WITH LOGIN = true AND PASSWORD = 'mallory-pw'",
             'GRANT CREATE ON ALL KEYSPACES TO mallory',
             "CREATE ROLE victim WITH LOGIN = true AND PASSWORD = 'victim-pw'",
             "CREATE KEYSPACE vks WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
             'CREATE TABLE vks.kv (k int PRIMARY KEY, v text)',
             'GRANT SELECT ON KEYSPACE vks TO victim',
             'GRANT MODIFY ON KEYSPACE vks TO victim']
    if ARM == 'data':
        # the admin's table holding an sstable backlog (compaction paused as stand-in for a backlog); attacker gets SELECT on it only
        stmts = [x for x in stmts if 'GRANT CREATE ON ALL KEYSPACES' not in x]
        stmts += ["CREATE KEYSPACE c9 WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
                  "CREATE TABLE c9.t (pk bigint PRIMARY KEY, v blob) WITH compaction = "
                  "{'class':'SizeTieredCompactionStrategy','enabled':'false'} AND memtable_flush_period_in_ms = " + str(PERIOD_MS),
                  'GRANT SELECT ON TABLE c9.t TO mallory']
    for q in stmts:
        s.execute(q); f.write(f'OK {q}\n')
    for who in ('mallory', 'victim'):
        for r in s.execute(f'LIST ALL PERMISSIONS OF {who}'):
            f.write(f'  {who}: {r.role} {r.resource} {r.permission}\n')
    for r in s.execute('LIST ROLES'):
        f.write(f'  role: {r.role} super={r.super} login={r.login}\n')
    cl.shutdown()
    f.close()


def scan(rundir, sub, inst):
    """One attack: C scan workers as mallory; returns seconds to node death or None."""
    d = f'{rundir}/{sub}'
    os.makedirs(d, exist_ok=True)
    t_load = time.time()
    open(d + '/t_load.txt', 'w').write(f'{int(t_load * 1000)}\n')
    phase(sub + '_start')
    cargs = f'--streams {C} --fetch 1000 --duration {D} --out {d}/client'
    cl = subprocess.Popen(f'exec taskset -c {CLIENT_CPUS} python3 {H}/c9b_scan.py {cargs}', shell=True,
                          stdout=open(d + '/client.out', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
    died = None
    while cl.poll() is None:
        if node_pid(inst) is None:
            died = time.time(); break
        if time.time() - t_load > D + 150:
            break
        time.sleep(0.5)
    notes = [f'arm=3b-T2 budget=B2 heap={HEAP} direct={DIRECT} C={C} D={D} attacker=mallory']
    if died:
        phase(sub + '_node_gone')
        notes.append(f'NODE GONE at load+{died - t_load:.1f}s')
        time.sleep(3)
    killpg(cl)
    notes.append(f'load_end at load+{time.time() - t_load:.1f}s; node_alive={node_pid(inst) is not None}')
    open(d + '/notes.txt', 'w').write('\n'.join(notes) + '\n')
    log(' | '.join(notes))
    return (died - t_load) if died else None


def collect(inst, d, rundir, tag):
    os.makedirs(d, exist_ok=True)
    for f in glob.glob(inst + '/logs/*'):
        if os.path.isfile(f):
            shutil.copy(f, d)
    for f in glob.glob(inst + '/hs_err*'):
        shutil.move(f, d)
    for f in glob.glob(inst + '/dumps/*.hprof') + glob.glob(inst + '/*.hprof'):
        os.makedirs(B + '/dumps', exist_ok=True)
        dst = f'{B}/dumps/{os.path.basename(rundir)}-{tag}.hprof'
        shutil.move(f, dst)          # scanned at the end of the run (scan_dumps), then deleted
        log(f'heap dump moved to {dst} ({os.path.getsize(dst) / 2**30:.2f} GiB)')
    # fresh logs for the next phase
    for f in glob.glob(inst + '/logs/*'):
        if os.path.isfile(f) and not f.endswith('launch.log'):
            os.remove(f)


def l_setup():
    os.makedirs(H, exist_ok=True); os.makedirs(B + '/runs', exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    for f in glob.glob(here + '/*'):
        if os.path.isfile(f) and os.path.abspath(f) != os.path.abspath(H + '/' + os.path.basename(f)):
            shutil.copy(f, H)
    sh(f'javac -d {H} {H}/C9Jmx.java', check=True)
    sh(f'sha256sum {CH}/build/apache-cassandra-5.0.9-SNAPSHOT.jar')


def l_run(name, seed):
    global LOGF, PH
    if daemons():
        raise SystemExit('CassandraDaemon running: ' + str([p for p, _ in daemons()]))
    rundir = f'{B}/runs/{name}'
    if os.path.exists(rundir):
        raise SystemExit('run dir exists: ' + rundir)
    os.makedirs(rundir)
    LOGF = open(rundir + '/session.log', 'a')
    PH = open(rundir + '/phases.csv', 'a')
    inst = f'{B}/inst/{name}'
    unit = f'c9b-{name}'
    shutil.rmtree(inst, ignore_errors=True)
    os.makedirs(inst)
    log(f'RUN {name}: arm {ARM}, target {TARGET}, empty data dir, B2 {HEAP}/{DIRECT}, period {PERIOD_MS} ms, load={open("/proc/loadavg").read().split()[:3]}')
    stopfile = rundir + '/victim.stop'
    vic = samp = samp2 = rss = None
    try:
        phase('start_cmd')
        start(inst, unit, rundir)
        p = wait_up(inst)
        if p is None:
            raise SystemExit('node not up')
        phase('node_up')
        sh(f'ps -o args= -p {p} | tr " " "\\n" | grep -E "^-Xm[sx]|MaxDirectMemorySize|^-Xlog|HeapDump|OutOfMemory|printHeap" > {rundir}/jvmargs.txt', quiet=True)
        admin(rundir)
        phase('roles_done')
        samp = sampler(rundir + '/samples.csv')
        rss = Rss(p, rundir + '/rss.csv'); rss.start()
        vic = subprocess.Popen(f'exec taskset -c {CLIENT_CPUS} python3 {H}/c9b_victim.py --out {rundir}/victim --stopfile {stopfile}',
                               shell=True, stdout=open(rundir + '/victim.out', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
        phase('victim_start')
        time.sleep(60)
        if ARM == 'data':
            phase('attack_prep')     # admin load first (the backlog), then the attacker's checks
            sh(f'C9B_USER=cassandra C9B_PW=cassandra taskset -c {CLIENT_CPUS} python3 {H}/c9b_attack.py build --out {rundir} --period {PERIOD_MS} '
               f'--target {TARGET} --every 10 --seed {seed}', timeout=1800, check=True)
            sh(f'taskset -c {CLIENT_CPUS} python3 {H}/c9b_attack.py dataprep --out {rundir}', timeout=300, check=True)
            phase('build_start'); phase('build_end')
        else:
            phase('attack_prep')
            sh(f'taskset -c {CLIENT_CPUS} python3 {H}/c9b_attack.py prep --out {rundir} --period {PERIOD_MS}', timeout=300, check=True)
            phase('build_start')
            sh(f'taskset -c {CLIENT_CPUS} python3 {H}/c9b_attack.py build --out {rundir} --period {PERIOD_MS} --target {TARGET} --seed {seed}', timeout=1800, check=True)
            phase('build_end')
        # observer (admin-side measurement only, not part of the attack)
        live, pend, tpend = jcount()
        rc, cs = sh(f'{NT} compactionstats', timeout=60, quiet=True)
        data = sorted(glob.glob(f'{inst}/data/c9/t-*/*-Data.db'), key=lambda x: int(os.path.basename(x).split('-')[1]))
        sizes = sorted(os.path.getsize(x) for x in data)
        md = ''
        for f in (data[0], data[len(data) // 2], data[-1]) if data else ():
            rc, o = sh(f'{CH}/tools/bin/sstablemetadata {f} 2>&1 | grep -iE "First token|Last token|SSTable:|Partitions|Estimated droppable" | head -8', timeout=120, quiet=True)
            md += f'== {f}\n{o}\n'
        rc, desc = sh(f"{CH}/bin/cqlsh 127.0.0.1 -u mallory -p mallory-pw -e 'DESCRIBE TABLE c9.t' 2>&1", timeout=120, quiet=True)
        rc, fl = sh(f'grep -c "MEMTABLE_PERIOD_EXPIRED" {inst}/logs/debug.log', timeout=30, quiet=True)
        with open(rundir + '/observer.txt', 'w') as f:
            f.write(f'LiveSSTableCount (JMX) {live}; pending compactions {pend}; c9.t pending {tpend}\n')
            f.write(f'Data.db files {len(data)}; size bytes min {sizes[0] if sizes else -1} median {sizes[len(sizes) // 2] if sizes else -1} '
                    f'max {sizes[-1] if sizes else -1}; below 256 KiB: {sum(1 for x in sizes if x < 262144)}\n')
            f.write(f'debug.log lines with MEMTABLE_PERIOD_EXPIRED: {fl.strip()}\n')
            f.write('compactionstats:\n' + cs + '\n' + md + '\nDESCRIBE TABLE c9.t (as mallory):\n' + desc + '\n')
        log(f'observer: live {live}, Data.db {len(data)}, pending {pend}')
        time.sleep(20)  # idle B0
        g1 = scan(rundir, 'scan1', inst)
        if g1 is None:
            time.sleep(30)
            phase('after')
        else:
            time.sleep(60)                         # victim's view with the node down
            killpg(samp); samp = None; rss.ev.set()
            sh(f'systemctl --user stop {unit}.scope', timeout=30, quiet=True)
            collect(inst, rundir + '/scan1', rundir, 'scan1')
            sh(f'cp {rundir}/samples.csv {rundir}/scan1/samples.csv', quiet=True)
            phase('restart_cmd')
            start(inst, unit, rundir)
            p = wait_up(inst)
            if p is None:
                raise SystemExit('node not up after restart')
            phase('restart_up')
            live2, _, _ = jcount()
            with open(rundir + '/observer.txt', 'a') as f:
                f.write(f'after restart: LiveSSTableCount {live2}\n')
            samp2 = sampler(rundir + '/samples2.csv')
            rss = Rss(p, rundir + '/rss2.csv'); rss.start()
            time.sleep(40)
            g2 = scan(rundir, 'scan2', inst)    # repeat attack: same table, no new setup
            time.sleep(30)
            phase('after')
    finally:
        try:
            open(stopfile, 'w').write('stop\n')
        except OSError:
            pass
        time.sleep(4)
        killpg(vic); killpg(samp); killpg(samp2)
        if rss:
            rss.ev.set()
        stopped = stop_node(inst, unit)
        log(f'stopped_clean={stopped}')
        last = rundir + ('/scan2' if os.path.isdir(rundir + '/scan2') else '/scan1')
        collect(inst, last, rundir, os.path.basename(last))
        if os.path.exists(rundir + '/samples2.csv'):
            sh(f'cp {rundir}/samples2.csv {rundir}/scan2/samples.csv', quiet=True)
        elif os.path.isdir(rundir + '/scan1') and not os.path.exists(rundir + '/scan1/samples.csv'):
            sh(f'cp {rundir}/samples.csv {rundir}/scan1/samples.csv', quiet=True)
        sh(f'du -sh {inst} > {rundir}/inst-du.txt 2>&1', quiet=True)
        shutil.rmtree(inst, ignore_errors=True)
        for sub in ('scan1', 'scan2'):
            if os.path.isdir(f'{rundir}/{sub}'):
                rc, o = sh(f'python3 {H}/c9_sum.py {rundir}/{sub}', timeout=300, quiet=True)
                open(f'{rundir}/{sub}/summary.txt', 'w').write(o)
                rc, o = sh(f'python3 {H}/c9_d1.py {rundir}/{sub}', timeout=300, quiet=True)
                open(f'{rundir}/{sub}/d1.txt', 'w').write(o)
                log('OUTCOME ' + sub + ' ' + (o.strip().splitlines()[0] if o.strip() else ''))
        for f in sorted(glob.glob(f'{B}/dumps/{name}-*.hprof')):
            tag = f.rsplit('-', 1)[1][:-6]
            sub = f'{rundir}/{tag}' if os.path.isdir(f'{rundir}/{tag}') else rundir
            sz = os.path.getsize(f)
            sh(f'python3 {H}/hprofhist.py {f} 40 > {sub}/hprof-hist.txt 2>&1', timeout=1800)
            os.remove(f)
            with open(sub + '/notes.txt', 'a') as nf:
                nf.write(f'heap dump {os.path.basename(f)} {sz / 2**30:.2f} GiB scanned (hprof-hist.txt) and deleted\n')
        rc, o = sh(f'python3 {H}/c9b_vsum.py {rundir}', timeout=300, quiet=True)
        open(rundir + '/victim-summary.txt', 'w').write(o)
        left = [p for p, c in daemons() if B in c]
        log(f'left: daemons {left}')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'setup':
        l_setup()
    elif a[0] == 'run':
        l_run(a[1], int(a[2]) if len(a) > 2 else 9)
    elif a[0] == 'queue':
        for i, n in enumerate(a[1:]):
            r = subprocess.run([sys.executable, os.path.abspath(__file__), 'run', n, str(9 + i)])
            with open(B + '/runs/queue.log', 'a') as f:
                f.write(f'end {n} rc={r.returncode} at {time.strftime("%T")}\n')
