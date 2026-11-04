#!/usr/bin/env python3
"""One cluster-tier run of max_region_size-tryswapregion-minsize--autonomous (B3e as amended 2026-10-28).
usage: cluster-run.py <label> <alloc offheap_objects|heap_buffers> <offheap_space 512MiB|32MiB> <cleanup 0.99|none> <T tables|0> <blob 0|1>
One fresh node (JDK 11, G1, -Xms2G -Xmx2G -XX:+AlwaysPreTouch, Byteman region ledger), data on local disk. Output $OUT/<label>/:
cmdlog.txt, snaps.jsonl (base, end[, blob]), samples.csv (1 Hz sum of MemtableOffHeapSize over all tables), stdout.txt, system.log.
The node is stopped on any exit and the script prints the daemon count."""
import json, os, re, subprocess, sys, time, atexit
label, alloc, off, thr, T, blob = sys.argv[1:7]; T = int(T); blob = int(blob)
H = os.path.dirname(os.path.abspath(__file__)); HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-mrs'); N = HOME + '/stage4-tmp/mrs/node'
OUT = os.path.join(os.environ.get('OUT', HOME + '/stage4-logs/mrs/run1/cluster'), label); os.makedirs(OUT, exist_ok=True)
log = open(OUT + '/cmdlog.txt', 'a')
def say(*a):
    m = ' '.join(str(x) for x in a); print(m, flush=True); log.write(m + '\n'); log.flush()
def sh(cmd, **kw):
    say('$', cmd)
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=C, **kw)
    say(r.stdout.rstrip()[-1500:]); return r.stdout
def daemons():
    out = subprocess.run("ps -eo pid,comm,args | awk '$2==\"java\" && /CassandraDaemon/'", shell=True, capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if l.strip()]
sampler = None
def stop():
    if sampler:
        open(OUT + '/stop', 'w').close()
    if daemons():
        subprocess.run('bin/nodetool stopdaemon', shell=True, cwd=C, capture_output=True)
        for _ in range(40):
            if not daemons(): break
            time.sleep(2)
        for l in daemons(): os.kill(int(l.split()[0]), 9)
atexit.register(stop)
say('== %s alloc=%s offheap=%s cleanup=%s T=%d blob=%d start %d' % (label, alloc, off, thr, T, blob, time.time() * 1000))
assert not daemons(), 'daemon already running'
subprocess.run('rm -rf %s' % N, shell=True)
sh('%s/make-node.sh %s %s %s' % (H, alloc, off, thr), env=dict(os.environ, CASSANDRA_HOME=C, T=N))
byteman = C + '/build/lib/jars/byteman-4.0.20.jar'
extra = '-XX:+AlwaysPreTouch -javaagent:%s=script:%s/region.btm' % (byteman, H)
open(OUT + '/jvm-extra.txt', 'w').write(extra + '\n')
env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='512M', JVM_EXTRA_OPTS=extra)
# foreground (-f): the daemon mode closes System.out after start-up (CassandraDaemon.java:738), which would silence the Byteman ledger
nodeproc = subprocess.Popen('ulimit -n 100000; exec bin/cassandra -f -p %s/cassandra.pid > %s/stdout.txt 2>&1' % (N, N), shell=True, cwd=C, env=env, start_new_session=True)
up = False
for _ in range(120):
    r = subprocess.run('bin/nodetool statusbinary', shell=True, cwd=C, capture_output=True, text=True)
    if r.stdout.strip() == 'running': up = True; break
    if not daemons(): say('daemon died at start'); say(open(N + '/stdout.txt').read()[-2000:]); sys.exit(1)
    time.sleep(3)
assert up
pid = int(daemons()[0].split()[0]);   # foreground mode writes no pid file say('node up, pid', pid)
args = open('/proc/%d/cmdline' % pid).read().split('\0')
open(OUT + '/proc-args.txt', 'w').write('\n'.join(a for a in args if re.search(r'Xm[sx]|AlwaysPreTouch|byteman|G1|CMS', a)) + '\n')
say(open(OUT + '/proc-args.txt').read())
JAVA = 'java -cp %s/cls Jmx 7199 ' % H
os.makedirs(H + '/cls', exist_ok=True); sh('javac -d %s/cls %s/Jmx.java' % (H, H))
PAT = 'org.apache.cassandra.metrics:type=Table,keyspace=*,scope=*,name=MemtableOffHeapSize'
if os.path.exists(OUT + '/stop'): os.remove(OUT + '/stop')
sampler = subprocess.Popen(JAVA + "sumpoll 1000 100000 %s/stop '%s' Value > %s/samples.csv 2>%s/sampler.err" % (OUT, PAT, OUT, OUT), shell=True, cwd=C)
def jsum(pattern, attr):
    out = subprocess.run(JAVA + "query '%s' %s" % (pattern, attr), shell=True, capture_output=True, text=True).stdout
    tot = 0
    for l in out.splitlines():
        p = l.split('|')
        if len(p) == 3 and re.fullmatch(r'-?\d+', p[2]): tot += int(p[2])
    return tot
def snap(name):
    st = dict(l.split(':', 1) for l in open('/proc/%d/status' % pid).read().splitlines() if ':' in l)
    kb = lambda k: int(st[k].split()[0])
    led = [int(x.split()[1]) for x in open(N + '/stdout.txt', errors='replace').read().splitlines() if x.startswith('REGION ')]
    d = dict(snap=name, t=int(time.time() * 1000), RssAnon_kB=kb('RssAnon'), VmData_kB=kb('VmData'), VmRSS_kB=kb('VmRSS'),
             charged_all=jsum(PAT, 'Value'),
             charged_ks=jsum(PAT.replace('keyspace=*', 'keyspace=ks'), 'Value'),
             switch_ks=jsum('org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=*,name=MemtableSwitchCount', 'Value'),
             switch_all=jsum('org.apache.cassandra.metrics:type=Table,keyspace=*,scope=*,name=MemtableSwitchCount', 'Value'),
             ledger_regions=len(led), ledger_bytes=sum(led), ledger_max=max(led) if led else 0)
    say('SNAP', json.dumps(d)); open(OUT + '/snaps.jsonl', 'a').write(json.dumps(d) + '\n'); return d
def workload(*a):
    env = dict(os.environ)
    return sh('python3 %s/workload.py %s/lib %s' % (H, C, ' '.join(a)))
try:
    sl = open(N + '/logs/system.log').read()
    say('EXPECTED yaml: ', [l for l in sl.splitlines() if 'memtable off-heap threshold' in l or 'memtable on-heap' in l][:2])
    time.sleep(20); b = snap('base')
    if T:
        workload('tables', str(T)); time.sleep(30); e = snap('end')
    else:
        time.sleep(30); e = snap('end')
    if blob:
        workload('blob'); time.sleep(10); snap('blob')
    for _ in range(1): pass
    say('DELTA end-base: RssAnon_kB=%d VmData_kB=%d charged_all=%d ledger_bytes=%d switch_ks=%d' % (
        e['RssAnon_kB'] - b['RssAnon_kB'], e['VmData_kB'] - b['VmData_kB'], e['charged_all'] - b['charged_all'], e['ledger_bytes'] - b['ledger_bytes'], e['switch_ks'] - b['switch_ks']))
finally:
    open(OUT + '/stop', 'w').close(); time.sleep(2)
    sh('bin/nodetool tablestats ks 2>&1 | grep -E "^Keyspace|Table:|Memtable|Off heap" | head -20 > %s/tablestats-head.txt; tail -3 %s/tablestats-head.txt' % (OUT, OUT))
    subprocess.run('cp %s/logs/system.log %s/system.log; cp %s/stdout.txt %s/stdout.txt' % (N, OUT, N, OUT), shell=True)
    stop(); say('daemons left:', len(daemons()))
    subprocess.run('grep -c "^REGION" %s/stdout.txt > %s/ledger-lines.txt; rm -rf %s' % (OUT, OUT, N), shell=True)
