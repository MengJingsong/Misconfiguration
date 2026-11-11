#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of maximum_replication_factor-ReplicaList.add-newSize--autonomous (case file as amended 2026-10-26).
usage: cluster-run.py run|down        env: RL_RUN (default run1), RL_N (stress rows, default 1000000), CASSANDRA_HOME (default ~/s4-b7-rl-node)
One node lifetime on tmpfs (/dev/shm/s4-b7-rl), loopback 127.0.1.1 (storage 7000, native 9042), JMX 7110, MAX_HEAP_SIZE 1G, G1,
PasswordAuthenticator + CassandraAuthorizer (superusers and AllowAll clients skip guardrails: Guardrail.enabled(state)).
Steps: start; wait UN + binary + superuser; CREATE ROLE ord (LOGIN, CREATE on ALL KEYSPACES);
  P0  threshold 1/1 (JMX, read back): ord CREATE KEYSPACE RF 3 must be rejected (first-trigger check; if it is not, stop);
  then phases (threshold -1, 1, 3, -1, 1, 3): set + read back, histogram baseline, cassandra-stress write n=RL_N threads=32 into
  ks_rf1 (RF 1) sampled every 10 s with jcmd GC.class_histogram, a final sample; DDL controls as ord (RF 3 / RF 4 / RF 1) and as
  superuser (RF 3), expectations per threshold;
  then (threshold -1) the K=200 step: 100 RF-1 and 100 RF-3 keyspaces by the superuser, histogram before and after.
Output: ~/s4-b7-rl-logs/<RL_RUN>/cluster/ (summary.txt with EXPECTED lines, hist.csv, ddl.csv, stress-*.txt, session.log, node.out, system-log-excerpt.txt).
The node is stopped (by pid) on any exit. Exit 1: a set-up or first-trigger check failed."""
import atexit, csv, os, re, shutil, signal, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b7-rl-node')
H = os.path.dirname(os.path.abspath(__file__))
RUN = os.environ.get('RL_RUN', 'run1')
NROWS = int(os.environ.get('RL_N', 1000000))
SUPP = os.environ.get('RL_SUPP') == '1'   # supplement (not in run 1): stress into an RF-3 keyspace ks_rf3, thresholds -1 and 3 only, no K200 step
KS, FACTOR = ('ks_rf3', 3) if SUPP else ('ks_rf1', 1)
D = '/dev/shm/s4-b7-rl'
L = f'{HOME}/s4-b7-rl-logs/{RUN}/cluster'
ADDR, JMX, NATIVE = '127.0.1.1', 7110, 9042
PIDF = D + '/node.pid'
CLS = '[Lorg.apache.cassandra.locator.Replica;'
env0 = dict(os.environ)

def log(m):
    line = time.strftime('%FT%T') + ' ' + m
    print(line, flush=True)
    with open(L + '/session.log', 'a') as f: f.write(line + '\n')

def summ(m):
    print(m, flush=True)
    with open(L + '/summary.txt', 'a') as f: f.write(m + '\n')

def sh(cmd, timeout=120, env=None, cwd=None):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env or env0, cwd=cwd)
    return p.returncode, p.stdout + p.stderr

def node_pid():
    try: return int(open(PIDF).read().strip())
    except Exception: return None

def alive(pid):
    try:
        os.kill(pid, 0); return True
    except Exception: return False

def stop_node():
    pid = node_pid()
    if pid and alive(pid):
        log(f'stopping node pid {pid}')
        os.kill(pid, signal.SIGTERM)
        for _ in range(60):
            if not alive(pid): break
            time.sleep(1)
        if alive(pid): os.kill(pid, signal.SIGKILL)

def fail(msg):
    summ('FAIL: ' + msg); stop_node(); sys.exit(1)

def jmx(*a):
    rc, o = sh(f'java -cp {D}/jmx Jmx {JMX} ' + ' '.join(a), 60)
    return rc, o

def cql(user, pw, stmt, timeout=120):
    f = D + '/stmt.cql'
    open(f, 'w').write(stmt + '\n')
    rc, o = sh(f'cd {C} && bin/cqlsh {ADDR} {NATIVE} -u {user} -p {pw} -f {f}', timeout)
    return rc, o

def hist():
    pid = node_pid()
    rc, o = sh(f'jcmd {pid} GC.class_histogram', 120)
    rep = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+' + re.escape(CLS) + r'\s*$', o, re.M)
    tot = re.search(r'^Total\s+(\d+)\s+(\d+)', o, re.M)
    return (int(rep.group(1)), int(rep.group(2))) if rep else (0, 0), (int(tot.group(1)), int(tot.group(2))) if tot else (0, 0)

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('run', 'down'): sys.exit(__doc__)
    if sys.argv[1] == 'down':
        stop_node(); return
    shutil.rmtree(L, ignore_errors=True); os.makedirs(L)
    atexit.register(stop_node)
    # preconditions
    rc, o = sh(f"ss -ltn | grep -E '({ADDR}:(9042|7000)|:{JMX}\\b)' || true")
    if o.strip(): fail('port in use: ' + o)
    rc, o = sh("ps -eo pid,cmd | grep '[C]assandraDaemon' | grep -c s4-b7-rl-node || true")
    if o.strip() not in ('0', ''): fail('a node of this tree is running')
    ulim = sh('ulimit -n')[1].strip(); log('ulimit -n ' + ulim)
    shutil.rmtree(D, ignore_errors=True)
    for d in ('data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs', 'jmx', 'conf'): os.makedirs(f'{D}/{d}')
    # JMX helper
    shutil.copy(H + '/Jmx.java', D + '/jmx/Jmx.java')
    rc, o = sh(f'cd {D}/jmx && javac Jmx.java'); 
    if rc: fail('javac Jmx: ' + o)
    # conf
    shutil.rmtree(D + '/conf'); shutil.copytree(C + '/conf', D + '/conf')
    env_sh = open(D + '/conf/cassandra-env.sh').read()
    env_sh2 = env_sh.replace('JMX_PORT="7199"', f'JMX_PORT="{JMX}"')
    if env_sh2 == env_sh: fail('JMX_PORT line not found')
    open(D + '/conf/cassandra-env.sh', 'w').write(env_sh2)
    lines = f"""cluster_name: stage4-rl
num_tokens: 16
partitioner: org.apache.cassandra.dht.Murmur3Partitioner
endpoint_snitch: GossipingPropertyFileSnitch
listen_address: {ADDR}
rpc_address: {ADDR}
storage_port: 7000
native_transport_port: {NATIVE}
authenticator: PasswordAuthenticator
authorizer: CassandraAuthorizer
role_manager: CassandraRoleManager
commitlog_total_space: 1024MiB
data_file_directories:
    - {D}/data
commitlog_directory: {D}/commitlog
hints_directory: {D}/hints
saved_caches_directory: {D}/saved_caches
cdc_raw_directory: {D}/cdc_raw
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "{ADDR}:7000"
"""
    keys = set(re.findall(r'^([a-z_]+):', lines, re.M))
    out, skip = [], False
    for l in open(C + '/conf/cassandra.yaml').read().splitlines():
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in keys
            if skip: continue
        elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')): continue
        else: skip = False
        out.append(l)
    open(D + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 rl lines ----\n' + lines)
    # start
    e = dict(env0, CASSANDRA_CONF=D + '/conf', CASSANDRA_LOG_DIR=D + '/logs', MAX_HEAP_SIZE='1G')
    e.pop('HEAP_NEWSIZE', None)
    proc = subprocess.Popen(f'ulimit -n 100000; cd {C} && exec bin/cassandra -f -p {PIDF} > {L}/node.out 2>&1 < /dev/null', shell=True, env=e,
                            start_new_session=True)
    open(PIDF, 'w').write(str(proc.pid))  # -f does not write the pid file; the shell execs, so this is the java pid (checked below)
    log('node starting')
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(3)
        pid = node_pid()
        if pid and not alive(pid): fail('node died during start')
        if not pid: continue
        rc, o = sh(f'cd {C} && bin/nodetool -h 127.0.0.1 -p {JMX} status', 60)
        rc2, o2 = sh(f'cd {C} && bin/nodetool -h 127.0.0.1 -p {JMX} statusbinary', 60)
        if re.search(r'^UN', o, re.M) and o2.strip() == 'running': break
    else: fail('node not UN/running within 300 s')
    pid = node_pid(); log(f'node up, pid {pid} after {time.time()-t0:.0f} s')
    rc, o = sh(f'cat /proc/{pid}/cmdline | tr "\\0" " " | grep -c CassandraDaemon')
    if o.strip() != '1': fail('pid ' + str(pid) + ' is not the CassandraDaemon JVM')
    # settings echo
    rc, o = sh(f"grep -E '^(authenticator|authorizer|num_tokens|listen_address|native_transport_port|storage_port)' {D}/conf/cassandra.yaml")
    summ('settings: ' + o.replace('\n', '; '))
    rc, o = sh(f'cat /proc/{pid}/cmdline | tr "\\0" " " | grep -o -E "\\-Xm[sx][0-9A-Za-z]+|UseG1GC|jmx.local.port=[0-9]+"')
    summ('jvm: ' + o.replace('\n', ' '))
    # superuser ready (cassandra/cassandra is created ~10 s after start)
    for _ in range(40):
        rc, o = cql('cassandra', 'cassandra', 'SELECT release_version FROM system.local;')
        if rc == 0: break
        time.sleep(3)
    else: fail('superuser login failed: ' + o)
    rc, o = cql('cassandra', 'cassandra', "CREATE ROLE IF NOT EXISTS ord WITH PASSWORD = 'ord' AND LOGIN = true;\nGRANT CREATE ON ALL KEYSPACES TO ord;")
    if rc: fail('create role: ' + o)
    time.sleep(5)  # permissions cache
    # instrument check: histogram line present and parses
    r0, t0_ = hist()
    summ(f'EXPECTED: histogram parses (Total > 10 MB). baseline Replica[] instances,bytes={r0} total={t0_}')
    if t0_[1] < 10_000_000: fail('histogram total not parsed')
    # ddl helper
    ddlcsv = csv.writer(open(L + '/ddl.csv', 'w')); ddlcsv.writerow(['phase', 'thr', 'role', 'rf', 'ks', 'accepted', 'detail'])
    def ddl(phase, thr, role, rf):
        ks = f'ks_{phase}_{role}_rf{rf}'
        u, p = ('ord', 'ord') if role == 'ord' else ('cassandra', 'cassandra')
        rc, o = cql(u, p, f"CREATE KEYSPACE {ks} WITH replication = {{'class':'SimpleStrategy','replication_factor':{rf}}};")
        acc = rc == 0 and 'above the' not in o
        m = re.search(r'above the \w+ threshold of \d+', o)
        ddlcsv.writerow([phase, thr, role, rf, ks, acc, m.group(0) if m else o.strip().replace('\n', ' ')[:120]]); 
        log(f'ddl {phase} thr={thr} {role} rf={rf} accepted={acc} {m.group(0) if m else ""}')
        return acc, o
    def setthr(t):
        rc, o = jmx('setrf', str(t), str(t))
        if rc or f'fail|{t}' not in o or f'warn|{t}' not in o: fail(f'setrf {t}: {o}')
        log(f'threshold {t} applied, read back {o.split()}')
    # P0 first trigger
    summ('EXPECTED: P0 thr=1: ord CREATE KEYSPACE RF 3 rejected (message "above the failure threshold of 1")')
    setthr(1)
    acc, o = ddl('P0', 1, 'ord', 3)
    if acc: fail('first-trigger check: RF 3 DDL by an ordinary role was ACCEPTED at threshold 1 (control did not bind)')
    if 'above the failure threshold of 1' not in o: fail('rejection message differs: ' + o[:300])
    summ('P0 ok: rejected with "above the failure threshold of 1"')
    # phases
    hc = csv.writer(open(L + '/hist.csv', 'w')); hc.writerow(['phase', 'thr', 'label', 'epoch_ms', 'rep_instances', 'rep_bytes', 'total_instances', 'total_bytes'])
    def sample(phase, thr, label):
        (ri, rb), (ti, tb) = hist()
        hc.writerow([phase, thr, label, int(time.time() * 1000), ri, rb, ti, tb]); 
        log(f'hist {phase} thr={thr} {label} Replica[] inst={ri} bytes={rb} total={tb}')
        return rb, tb
    thrs = [-1, 3] if SUPP else [-1, 1, 3, -1, 1, 3]
    exp_ddl = {-1: {3: True, 4: True}, 1: {3: False, 4: False}, 3: {3: True, 4: False}}
    summ('EXPECTED: per phase thr t: ord RF3 accepted iff t in (-1,3); ord RF4 accepted iff t == -1; ord RF1 accepted always; superuser RF3 accepted always; '
         f'stress write n={NROWS} into ks_rf1 with 0 errors; Replica[] bytes after stress < 1 MB and equal across thresholds within 10 percent')
    for i, t in enumerate(thrs):
        ph = f'p{i+1}'
        setthr(t)
        sample(ph, t, 'baseline')
        stop = threading.Event()
        def sampler():
            n = 0
            while not stop.wait(10):
                n += 1; sample(ph, t, f'during{n}')
        th = threading.Thread(target=sampler); th.start()
        sf = f'{L}/stress-{ph}.txt'
        t1 = time.time()
        rc, o = sh(f'cd {C} && tools/bin/cassandra-stress write n={NROWS} no-warmup cl=ONE -pop seq=1..{NROWS} -rate threads=32 '
                   f'-schema "replication(strategy=SimpleStrategy,factor={FACTOR})" keyspace={KS} -node {ADDR} -port native={NATIVE} '
                   f'-mode native cql3 user=cassandra password=cassandra', 1500)
        stop.set(); th.join()
        # keep header and results block only
        keep = [l for l in o.splitlines() if re.match(r'^(Total|Op rate|Partition rate|Row rate|Latency mean|Latency 99th|Total errors|Total partitions|Total operation time|Results:|END|Failed|java.|Exception)', l.strip()) or 'rror' in l][:40]
        open(sf, 'w').write(f'rc={rc} seconds={time.time()-t1:.0f}\n' + '\n'.join(keep) + '\n')
        log(f'stress {ph} rc={rc} {time.time()-t1:.0f}s')
        if rc != 0 and i == 0: fail('stress failed in the first phase: ' + o[-500:])
        sample(ph, t, 'after-stress')
        for role, rf in (('ord', 3), ('ord', 4), ('ord', 1), ('su', 3)):
            if t == 1 and False: pass
            ddl(ph, t, role, rf)
        sample(ph, t, 'end')
    if SUPP:
        sh(f"grep -E '^(ERROR|WARN)' {D}/logs/system.log | cut -c1-240 | head -60 > {L}/system-log-excerpt.txt")
        summ('cluster run complete ' + time.strftime('%FT%T')); return
    # K = 200 step
    setthr(-1)
    sample('K200', -1, 'before')
    stm = ''.join(f"CREATE KEYSPACE IF NOT EXISTS ksk{i}_rf{rf} WITH replication = {{'class':'SimpleStrategy','replication_factor':{rf}}};\n"
                  for i in range(100) for rf in (1, 3))
    rc, o = cql('cassandra', 'cassandra', stm, 900)
    log(f'200 keyspaces rc={rc} {o[-200:] if rc else ""}')
    time.sleep(10)
    sample('K200', -1, 'after')
    rc, o = cql('cassandra', 'cassandra', "SELECT count(*) FROM system_schema.keyspaces;")
    summ('keyspaces after K200 step: ' + ' '.join(o.split()))
    sh(f"cp {D}/logs/system.log {L}/system.log.full; grep -E '^(ERROR|WARN)' {D}/logs/system.log | cut -c1-240 | head -60 > {L}/system-log-excerpt.txt")
    summ('cluster run complete ' + time.strftime('%FT%T'))

main()
