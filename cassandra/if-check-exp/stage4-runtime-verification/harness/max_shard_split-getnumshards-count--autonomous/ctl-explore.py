#!/usr/bin/env python3
"""EXPLORATORY copy (after run 1) of the control only; see the results file, section 3 defect 2. Cluster tier of max_shard_split-getnumshards-count--autonomous (B3e as amended 2026-10-28). One node start, all phases, one table ks.t.
usage: cluster-run.py <label> [shakedown]      (shakedown: 2 batches instead of 8, Config A only)
Phases (B3e 4-7): for Config A (target 1MiB, growth 0, base 1, min 0MiB) then Config B (ALTER: target 1GiB, growth 0.333): dense arm, then control arm
(truncate between): 8 batches of 4096 rows x 16 KiB (64 MiB), flush after each; snapshot; `nodetool compact ks t`; snapshot; shard-count log lines.
Then the positive control (B3h): Config A + max_sstables_to_compact 4, then 32, on dense data: inputs per compaction task and peak table-directory bytes.
Output $OUT/<label>/ : cmdlog.txt readings.txt snaps.jsonl samples.csv shardlines-*.txt compacting-*.txt system.log debug-excerpt.txt"""
import json, os, re, subprocess, sys, time, atexit, threading
label = sys.argv[1]; shake = len(sys.argv) > 2
BATCHES = 2 if shake else 8
H = os.path.dirname(os.path.abspath(__file__)); HOME = os.path.expanduser('~')
C = HOME + '/s4-ms'; N = HOME + '/stage4-tmp/ms/node'
OUT = os.path.join(os.environ.get('OUT', HOME + '/stage4-logs/ms/run1'), label); os.makedirs(OUT, exist_ok=True)
log = open(OUT + '/cmdlog.txt', 'a'); rd = open(OUT + '/readings.txt', 'a')
def say(*a):
    m = ' '.join(str(x) for x in a); print(m, flush=True); log.write(m + '\n'); log.flush()
def reading(m):
    say(m); rd.write(m + '\n'); rd.flush()
def sh(cmd, tmo=3600, quiet=False):
    if not quiet: say('$', cmd)
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=C, timeout=tmo)
    if not quiet: say(r.stdout.rstrip()[-1200:])
    return r.stdout
def daemons():
    out = subprocess.run("ps -eo pid,comm,args | awk '$2==\"java\" && /CassandraDaemon/'", shell=True, capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if l.strip()]
stopflag = threading.Event()
def stop():
    stopflag.set()
    if daemons():
        subprocess.run('bin/nodetool stopdaemon', shell=True, cwd=C, capture_output=True)
        for _ in range(40):
            if not daemons(): break
            time.sleep(2)
        for l in daemons(): os.kill(int(l.split()[0]), 9)
atexit.register(stop)
assert not daemons(), 'daemon already running'
say('== %s start %d shakedown=%s' % (label, time.time() * 1000, shake))
# keys
sh('mkdir -p %s/cls && javac -cp "%s/build/classes/main:%s/build/lib/jars/*:%s/lib/*" -d %s/cls %s/KeyGen.java' % (OUT, C, C, C, OUT, H))
KCP = '%s/cls:%s/build/classes/main:%s/build/classes/thrift:%s/build/lib/jars/*:%s/lib/*' % (OUT, C, C, C, C)
rows = BATCHES * 4096
reading(sh('java -cp "%s" KeyGen window %d 14 %s/keys-dense.txt | tail -n 1' % (KCP, rows, OUT)).strip())
reading(sh('java -cp "%s" KeyGen any %d 0 %s/keys-control.txt | tail -n 1' % (KCP, rows, OUT)).strip())
subprocess.run('rm -rf %s' % N, shell=True)
sh('T=%s %s/make-node.sh %s' % (N, H, C))
extra = '-Dunified_compaction.base_shard_count=1 -Dunified_compaction.sstable_growth=0 -Dunified_compaction.min_sstable_size=0MiB'
open(OUT + '/jvm-extra.txt', 'w').write(extra + '\n')
env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G', HEAP_NEWSIZE='512M', JVM_EXTRA_OPTS=extra)
nodeproc = subprocess.Popen('ulimit -n 100000; exec bin/cassandra -f > %s/stdout.txt 2>&1' % N, shell=True, cwd=C, env=env, start_new_session=True)
up = False
for _ in range(120):
    if subprocess.run('bin/nodetool statusbinary', shell=True, cwd=C, capture_output=True, text=True).stdout.strip() == 'running': up = True; break
    if nodeproc.poll() is not None: say('daemon died'); say(open(N + '/stdout.txt').read()[-2000:]); sys.exit(1)
    time.sleep(3)
assert up
pid = int(daemons()[0].split()[0])
open(OUT + '/proc-args.txt', 'w').write('\n'.join(a for a in open('/proc/%d/cmdline' % pid).read().split('\0') if re.search(r'Xm[sx]|G1|unified|Serial', a)) + '\n')
say(open(OUT + '/proc-args.txt').read())
phase = ['startup']
def sampler():
    f = open(OUT + '/samples.csv', 'w'); f.write('epoch_ms,phase,heap_used_kB,RssAnon_kB,VmRSS_kB,table_dir_bytes\n')
    while not stopflag.is_set():
        try:
            hi = subprocess.run('jcmd %d GC.heap_info 2>/dev/null' % pid, shell=True, capture_output=True, text=True).stdout
            used = sum(int(x) for x in re.findall(r'used (\d+)K', hi)[:1])
            st = dict(l.split(':', 1) for l in open('/proc/%d/status' % pid).read().splitlines() if ':' in l)
            kb = lambda k: int(st[k].split()[0])
            du = subprocess.run("du -sb %s/data/ks 2>/dev/null | cut -f1" % N, shell=True, capture_output=True, text=True).stdout.strip() or '0'
            f.write('%d,%s,%d,%d,%d,%s\n' % (time.time() * 1000, phase[0], used, kb('RssAnon'), kb('VmRSS'), du)); f.flush()
        except Exception: pass
        time.sleep(5)
threading.Thread(target=sampler, daemon=True).start()
sh('bin/nodetool setlogginglevel org.apache.cassandra.db.compaction.unified.Controller DEBUG')
DEBUG = N + '/logs/debug.log'
def ddl(q): sh("python3 %s/workload.py %s/lib ddl \"%s\"" % (H, C, q))
def comp(target, growth, extra_opt=''):
    return ("{'class':'UnifiedCompactionStrategy','scaling_parameters':'T2','base_shard_count':'1','target_sstable_size':'%s','sstable_growth':'%s','min_sstable_size':'0MiB'%s}" % (target, growth, extra_opt))
ddl("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
ddl("CREATE TABLE IF NOT EXISTS ks.t (k blob PRIMARY KEY, v blob) WITH compaction = %s" % comp('1MiB', '0'))
def tablestats():
    out = sh('bin/nodetool tablestats ks.t', quiet=True)
    d = {}
    for l in out.splitlines():
        m = re.match(r'\s+(SSTable count|Space used \(live\)|Space used \(total\)|Memtable off heap memory used|Bloom filter off heap memory used|Compression metadata off heap memory used|Index summary off heap memory used|Memtable data size): (\S+)', l)
        if m: d[m.group(1)] = m.group(2)
    return d
def heapnow():
    sh('jcmd %d GC.run' % pid, quiet=True); time.sleep(2)
    hi = sh('jcmd %d GC.heap_info' % pid, quiet=True)
    return int(re.findall(r'used (\d+)K', hi)[0])
def ssdata():
    return int(sh("ls %s/data/ks/t-*/*-Data.db 2>/dev/null | wc -l" % N, quiet=True).strip() or 0)
def snap(tag):
    st = dict(l.split(':', 1) for l in open('/proc/%d/status' % pid).read().splitlines() if ':' in l)
    d = dict(snap=tag, t=int(time.time() * 1000), heap_post_gc_kB=heapnow(), RssAnon_kB=int(st['RssAnon'].split()[0]), data_files=ssdata(),
             du_bytes=int(sh("du -sb %s/data/ks | cut -f1" % N, quiet=True).strip() or 0), **tablestats())
    say('SNAP', json.dumps(d)); open(OUT + '/snaps.jsonl', 'a').write(json.dumps(d) + '\n'); return d
def wait_idle(tag, tmo=900):
    # snapshots are taken only when no compaction is pending or running (a background UCS compaction would otherwise be caught half done)
    t0 = time.time(); n = 0
    while time.time() - t0 < tmo:
        out = sh('bin/nodetool compactionstats', quiet=True)
        if re.search(r'pending tasks\s+0\b', out) and not re.search(r'\bks\s', out):
            n += 1
            if n >= 2: break
        else: n = 0
        time.sleep(3)
    reading('IDLE %s after %.0f s' % (tag, time.time() - t0))
def logsize(): return os.path.getsize(DEBUG)
def excerpt(tag, off):
    seg = subprocess.run("tail -c +%d %s" % (off + 1, DEBUG), shell=True, capture_output=True, text=True, errors='replace').stdout
    shard = [l for l in seg.splitlines() if 'Shard count' in l and 'Controller' in l]
    comp_ = [l for l in seg.splitlines() if re.search(r'Compacting \(', l)]
    open(OUT + '/shardlines-%s.txt' % tag, 'w').write('\n'.join(shard) + '\n'); open(OUT + '/compacting-%s.txt' % tag, 'w').write('\n'.join(comp_) + '\n')
    nums = [int(m.group(1)) for l in shard for m in [re.search(r'Shard count (-?\d+) for density', l)] if m]
    return shard, comp_, nums
def arm(tag, keyfile):
    phase[0] = tag; off = logsize(); t0 = time.time()
    for b in range(BATCHES):
        sh('python3 %s/workload.py %s/lib load %s %d 4096 16384' % (H, C, keyfile, b * 4096)); sh('bin/nodetool flush ks t', quiet=True)
    wait_idle(tag + '-postflush')
    s1 = snap(tag + '-postflush')
    flush_shards = excerpt(tag + '-flushphase', off)
    off2 = logsize(); tc = time.time()
    sh('bin/nodetool compact ks t'); reading('COMPACT %s seconds=%.0f' % (tag, time.time() - tc))
    time.sleep(5); wait_idle(tag + '-postcompact')
    s2 = snap(tag + '-postcompact')
    shard, comp_, nums = excerpt(tag + '-compact', off2)
    reading('ARM %s: flush-phase shard lines=%d values=%s | compact-phase shard lines=%d values=%s | sstables postflush=%s postcompact=%s (data files %d -> %d) | space live %s -> %s | heap post-GC kB %d -> %d | du bytes %d -> %d | seconds=%.0f' % (
        tag, len(flush_shards[0]), sorted(set(flush_shards[2])), len(shard), sorted(set(nums)), s1.get('SSTable count'), s2.get('SSTable count'),
        s1['data_files'], s2['data_files'], s1.get('Space used (live)'), s2.get('Space used (live)'), s1['heap_post_gc_kB'], s2['heap_post_gc_kB'], s1['du_bytes'], s2['du_bytes'], time.time() - t0))
    return nums
def truncate(): sh("bin/nodetool disableautocompaction ks t >/dev/null 2>&1; true", quiet=True); ddl("TRUNCATE ks.t"); sh("bin/nodetool enableautocompaction ks t", quiet=True)
reading('EXPLORATORY (not run 1): max_sstables_to_compact 4 vs 32 through BACKGROUND compaction (autocompaction on, no nodetool compact) on the dense data, config A')
snap('base')
for mx in (4, 32):
    truncate()
    ddl("ALTER TABLE ks.t WITH compaction = %s" % comp('1MiB', '0', ",'max_sstables_to_compact':'%d'" % mx))
    phase[0] = 'ctl-max%d' % mx; off = logsize(); t0 = time.time()
    for b in range(BATCHES):
        sh('python3 %s/workload.py %s/lib load %s %d 4096 16384' % (H, C, OUT + '/keys-dense.txt', b * 4096)); sh('bin/nodetool flush ks t', quiet=True)
    wait_idle('ctl-max%d' % mx)
    shard, comp_, nums = excerpt('ctl-max%d' % mx, off)
    ins = [l.count('nb-') for l in comp_]
    reading('CTLBG max_sstables_to_compact=%d: compaction tasks logged=%d, max inputs per task=%d, inputs per task (first 30)=%s, sstables now=%d, seconds=%.0f' % (mx, len(comp_), max(ins or [0]), ins[:30], ssdata(), time.time() - t0))
phase[0] = 'end'
stopflag.set(); time.sleep(6)
sh('cp %s/logs/system.log %s/system.log; ls -l %s/logs > %s/loglist.txt; df -h / | tail -n 1 >> %s/loglist.txt' % (N, OUT, N, OUT, OUT))
sh("grep -E 'ERROR|OutOfMemory|Exception' %s/logs/system.log | head -n 20 > %s/errors.txt; wc -l %s/errors.txt" % (N, OUT, OUT))
stop(); say('daemons left:', len(daemons()))
subprocess.run('rm -rf %s' % N, shell=True)
