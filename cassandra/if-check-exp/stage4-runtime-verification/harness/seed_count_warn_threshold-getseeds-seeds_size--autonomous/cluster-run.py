#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of seed_count_warn_threshold-getseeds-seeds_size--autonomous.
usage: cluster-run.py run <U|P> <K> <T|default> <tag>      one node lifetime: fresh data, K seeds (127.0.0.1 + K-1 unrouted literals), threshold T
       cluster-run.py down
Arm U = ~/s4-base, arm P = ~/s4-seed-b (list truncated to the threshold). Node dir ~/s4-seed/node. Logs ~/stage4-logs/seed/cluster/<tag>/.
Readings after SETTLE s (default 150): WARN lines of this start, `nodetool getseeds` count, jmap -histo:live (total, InetAddressAndPort,
OutboundConnections), GC.heap_info. Exit 1 on a failed check; the node is stopped."""
import os, re, subprocess, sys, time

HOME = os.path.expanduser('~'); TREE = {'U': HOME + '/s4-base', 'P': HOME + '/s4-seed-b'}
N = HOME + '/s4-seed/node'; SETTLE = int(os.environ.get('SEED_SETTLE', 150))
cmd = sys.argv[1]; tag = sys.argv[5] if cmd == 'run' else 'down'
LOGS = HOME + '/stage4-logs/seed/cluster/' + tag; os.makedirs(LOGS, exist_ok=True)
SUMMARY = open(LOGS + '/summary.txt', 'a'); tree = TREE['U']


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush()


def sh(c, timeout=600, env=None, cwd=None):
    r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd or tree)
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def pid():
    try: return int(open(N + '/cassandra.pid').read().strip())
    except Exception: return None


def alive():
    p = pid(); return p is not None and os.path.exists(f'/proc/{p}')


def stop():
    if alive():
        sh('bin/nodetool stopdaemon', timeout=180)
        for _ in range(120):
            if not alive(): break
            time.sleep(1)
        if alive(): subprocess.run(['kill', '-9', str(pid())]); time.sleep(2)
    return sh("ps -eo cmd | grep '[C]assandraDaemon' || true")[1].strip()


def fail(m):
    note('FAIL: ' + m); stop(); sys.exit(1)


if cmd == 'down':
    note('down: ' + (stop() or 'no CassandraDaemon left')); sys.exit(0)
arm, K, T = sys.argv[2], int(sys.argv[3]), sys.argv[4]; tree = TREE[arm]
note(f'=== {tag}: arm {arm} ({tree}) K={K} T={T} settle={SETTLE}s')
if stop(): fail('a CassandraDaemon is already running')
sh(f'rm -rf {N}', cwd=HOME); os.makedirs(N)
for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'): os.makedirs(f'{N}/{d}')
sh(f'cp -r {tree}/conf {N}/conf && git -C {tree} show HEAD:conf/cassandra.yaml > {N}/conf/cassandra.yaml && git -C {tree} show HEAD:conf/cassandra-env.sh > {N}/conf/cassandra-env.sh', cwd=HOME)
seeds = ['127.0.0.1'] + ['10.%d.%d.%d' % (i // 62500, (i // 250) % 250, i % 250 + 1) for i in range(K - 1)]
y = open(N + '/conf/cassandra.yaml').read()
y2 = re.sub(r'(- seeds:\s*)"[^"]*"', lambda m: m.group(1) + '"' + ','.join(seeds) + '"', y, count=1)
if y2 == y: fail('seeds line not replaced')
y2 += f"\ndata_file_directories:\n    - {N}/data\ncommitlog_directory: {N}/commitlog\nhints_directory: {N}/hints\nsaved_caches_directory: {N}/saved_caches\ncdc_raw_directory: {N}/cdc_raw\n"
for k in ('data_file_directories', 'commitlog_directory', 'hints_directory', 'saved_caches_directory', 'cdc_raw_directory'):
    if len(re.findall('^%s:' % k, y2, re.M)) != 1: fail('yaml key ' + k)
open(N + '/conf/cassandra.yaml', 'w').write(y2)
note(f'yaml: {len(seeds)} seeds, first {seeds[:2]}, last {seeds[-1]}')
env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='1G')
env.pop('HEAP_NEWSIZE', None); env.pop('JVM_EXTRA_OPTS', None)
if T != 'default': env['JVM_EXTRA_OPTS'] = f'-Dcassandra.seed_count_warn_threshold={T}'
rc, o = sh(f'bin/cassandra -p {N}/cassandra.pid > {N}/stdout.txt 2>&1', env=env)
lp = N + '/logs/system.log'
for _ in range(300):
    time.sleep(2)
    if not alive(): fail('daemon died during start; see ' + N + '/stdout.txt')
    if os.path.exists(lp) and 'Starting listening for CQL clients' in open(lp, errors='replace').read(): break
else: fail('no CQL listener')
cl = open(f'/proc/{pid()}/cmdline').read().replace('\0', ' ')
m = re.search(r'-Dcassandra.seed_count_warn_threshold=(\S+)', cl)
note(f'READBACK jvm threshold property: {m.group(1) if m else "unset"}')
if (T == 'default') != (m is None) or (m and m.group(1) != T): fail('threshold read-back mismatch')
note(f'listener up; settling {SETTLE}s'); time.sleep(SETTLE)
syslog = open(lp, errors='replace').read()
warns = [l for l in syslog.splitlines() if 'Seed provider returned more than' in l]
note(f'WARN lines={len(warns)}'); [note('WARN-LINE ' + w[:200]) for w in warns[:2]]
rc, o = sh('bin/nodetool getseeds')
open(LOGS + '/getseeds.txt', 'w').write(o); ng = len(re.findall(r'^\d+\.\d+\.\d+\.\d+', o, re.M)); note('GETSEEDS count=%d' % ng)
p = pid(); sh(f'jmap -histo:live {p} > {LOGS}/histo.txt', timeout=300); sh(f'jcmd {p} GC.heap_info > {LOGS}/heapinfo.txt')
h = open(LOGS + '/histo.txt').read(); tot = re.search(r'^Total\s+(\d+)\s+(\d+)', h, re.M)
g = lambda c: (lambda mm: (int(mm.group(1)), int(mm.group(2))) if mm else (0, 0))(re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+' + re.escape(c) + r'\s*$', h, re.M))
ia, oc = g('org.apache.cassandra.locator.InetAddressAndPort'), g('org.apache.cassandra.net.OutboundConnections')
note(f'HISTO live_bytes={tot.group(2)} InetAddressAndPort={ia[0]} ({ia[1]} B) OutboundConnections={oc[0]} ({oc[1]} B)')
note('STOPPED: ' + (stop() or 'no CassandraDaemon left'))
