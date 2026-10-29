#!/usr/bin/env python3
"""One cluster-tier run of logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous (B3e, 2026-10-28).
usage: cluster-run.py <label> <build A|B> <appender on|off> <max_rows> <phase full|startup>
Copy ~/s4-lv (build A, constant 50_000) or ~/s4-lvB (build B, constant 1_000); node data copied from the seeded schema ~/stage4-tmp/lv/seed;
-Xms1g -Xmx1g, SerialGC; Byteman observation (lv.btm); sampler (jcmd class histogram of the two classes, GC.heap_info, /proc status) every 5 s for 150 s, then every 30 s.
Output $OUT/<label>/ : cmdlog.txt samples.csv stdout.txt system.log readings.txt. The node is stopped on any exit; the daemon count is printed."""
import json, os, re, subprocess, sys, time, atexit, threading
label, build, app, maxrows, phase = sys.argv[1:6]
H = os.path.dirname(os.path.abspath(__file__)); HOME = os.path.expanduser('~')
C = HOME + ('/s4-lv' if build == 'A' else '/s4-lvB'); N = HOME + '/stage4-tmp/lv/node'; SEED = HOME + '/stage4-tmp/lv/seed'
OUT = os.path.join(os.environ.get('OUT', HOME + '/stage4-logs/lv/run1'), label); os.makedirs(OUT, exist_ok=True)
log = open(OUT + '/cmdlog.txt', 'a'); rd = open(OUT + '/readings.txt', 'a')
def say(*a):
    m = ' '.join(str(x) for x in a); print(m, flush=True); log.write(m + '\n'); log.flush()
def reading(m):
    say(m); rd.write(m + '\n'); rd.flush()
def sh(cmd, tmo=1800, **kw):
    say('$', cmd)
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=C, timeout=tmo, **kw)
    say(r.stdout.rstrip()[-1200:]); return r.stdout
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
say('== %s build=%s appender=%s max_rows=%s phase=%s start %d' % (label, build, app, maxrows, phase, time.time() * 1000))
assert not daemons(), 'daemon already running'
subprocess.run('rm -rf %s' % N, shell=True)
sh('T=%s %s/make-node.sh %s %s' % (N, H, app, C))
for d in ('data', 'commitlog', 'saved_caches', 'hints'):
    sh('cp -a %s/%s/. %s/%s/' % (SEED, d, N, d))
sh('javap -constants -p -cp %s/build/classes/main org.apache.cassandra.db.virtual.LogMessagesTable | grep DEFAULT_ROWS; javap -p -c -cp %s/build/classes/main org.apache.cassandra.utils.logging.VirtualTableAppender | grep -E "sipush|ldc.*50000"' % (C, C))
byteman = C + '/build/lib/jars/byteman-4.0.20.jar'
extra = '-javaagent:%s=script:%s/lv.btm -Dcassandra.virtual.logs.max.rows=%s' % (byteman, H, maxrows)
open(OUT + '/jvm-extra.txt', 'w').write(extra + '\n')
env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='1G', HEAP_NEWSIZE='256M', JVM_EXTRA_OPTS=extra)
t_launch = int(time.time() * 1000)
nodeproc = subprocess.Popen('ulimit -n 100000; exec bin/cassandra -f > %s/stdout.txt 2>&1' % N, shell=True, cwd=C, env=env, start_new_session=True)
pidbox = {}
def sampler():
    t0 = time.time(); f = open(OUT + '/samples.csv', 'w'); f.write('epoch_ms,LoggingEvent,LoggingEventBytes,LogMessage,heap_used_kB,RssAnon_kB,VmRSS_kB\n')
    while not stopflag.is_set():
        ds = daemons()
        if ds:
            pid = ds[0].split()[0]; pidbox['pid'] = int(pid)
            h = subprocess.run('jcmd %s GC.class_histogram 2>/dev/null' % pid, shell=True, capture_output=True, text=True).stdout
            def g(c):
                for l in h.splitlines():
                    p = l.split()
                    if len(p) >= 4 and p[3] == c: return int(p[1]), int(p[2])
                return 0, 0
            le = g('ch.qos.logback.classic.spi.LoggingEvent'); lm = g('org.apache.cassandra.db.virtual.LogMessagesTable$LogMessage')
            hi = subprocess.run('jcmd %s GC.heap_info 2>/dev/null' % pid, shell=True, capture_output=True, text=True).stdout
            m = re.search(r'used (\d+)K', hi)
            try:
                st = dict(l.split(':', 1) for l in open('/proc/%s/status' % pid).read().splitlines() if ':' in l)
                kb = lambda k: int(st[k].split()[0])
                f.write('%d,%d,%d,%d,%s,%d,%d\n' % (time.time() * 1000, le[0], le[1], lm[0], m.group(1) if m else -1, kb('RssAnon'), kb('VmRSS'))); f.flush()
            except Exception: pass
        time.sleep(5 if time.time() - t0 < 150 else 30)
threading.Thread(target=sampler, daemon=True).start()
up = False
for _ in range(200):
    r = subprocess.run('bin/nodetool statusbinary', shell=True, cwd=C, capture_output=True, text=True)
    if r.stdout.strip() == 'running': up = True; break
    if nodeproc.poll() is not None: say('daemon died at start'); say(open(N + '/stdout.txt').read()[-2000:]); sys.exit(1)
    time.sleep(3)
assert up
t_up = int(time.time() * 1000)
reading('LAUNCH_MS %d UP_MS %d startup_s %.1f' % (t_launch, t_up, (t_up - t_launch) / 1000))
def so(): return open(N + '/stdout.txt', errors='replace').read()
def flushinfo():
    e = re.search(r'LVFLUSH_ENTRY ms=(\d+) attempts=(\d+) buffered=(\d+)', so()); x = re.search(r'LVFLUSH_EXIT ms=(\d+) buffered=(\d+)', so())
    return e, x
def readlogs(tag, split):
    out = sh('python3 %s/readlogs.py %s/lib %d' % (H, C, split), tmo=900)
    m = re.search(r'LOGROWS .*', out); reading('%s %s' % (tag, m.group(0) if m else 'LOGROWS FAILED'))
try:
    time.sleep(15)
    e, x = flushinfo()
    if app == 'on':
        assert e, 'no LVFLUSH_ENTRY in stdout: appender not active or flush not reached'
        fl = int(e.group(1))
        reading('FLUSH_ENTRY ms=%s attempts=%s buffered=%s' % (e.group(1), e.group(2), e.group(3)))
        reading('FLUSH_EXIT ms=%s buffered=%s' % (x.group(1), x.group(2)) if x else 'FLUSH_EXIT missing')
        readlogs('TABLE_AFTER_STARTUP', fl)
    else:
        reading('FLUSH_ENTRY %s' % ('present' if e else 'absent'))
        fl = t_up
    if phase == 'full':
        t0 = int(time.time() * 1000)
        stress = subprocess.Popen('tools/bin/cassandra-stress write n=1500000 -rate threads=32 -node 127.0.0.1 > %s/stress.out 2>&1' % OUT, shell=True, cwd=C)
        k = 0
        while stress.poll() is None:
            time.sleep(20); k += 1
            if k % 3 == 0: subprocess.run('bin/nodetool flush', shell=True, cwd=C, capture_output=True)
            if time.time() * 1000 - t0 > 900000: say('stress over 15 min: killing'); stress.kill(); break
        reading('STRESS seconds=%.0f rc=%s' % ((time.time() * 1000 - t0) / 1000, stress.returncode))
        subprocess.run('grep -E "Total errors|Total partitions|Op rate" %s/stress.out | tail -n 4 > %s/stress-summary.txt; cat %s/stress-summary.txt' % (OUT, OUT, OUT), shell=True)
        time.sleep(30)
        if app == 'on': readlogs('TABLE_AFTER_STRESS', fl)
    time.sleep(35)  # one more sample
finally:
    stopflag.set(); time.sleep(1)
    dl = N + '/logs/debug.log'
    subprocess.run('cp %s/logs/system.log %s/system.log; cp %s/stdout.txt %s/stdout.txt; ls -l %s/logs > %s/loglist.txt; df -h / | tail -n 1 >> %s/loglist.txt' % (N, OUT, N, OUT, N, OUT, OUT), shell=True)
    e2, _ = flushinfo()
    if os.path.exists(dl) and e2:
        # debug.log lines (any level it holds) timestamped before the flush entry: ground truth of events logged before the flush
        import datetime
        ft = datetime.datetime.utcfromtimestamp(int(e2.group(1)) / 1000).strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]
        n = tot = 0
        with open(dl, errors='replace') as f:
            for l in f:
                tot += 1
                m = re.search(r'(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d:\d\d,\d{3})', l)
                if m and (m.group(1) + ' ' + m.group(2)) < ft: n += 1
        reading('DEBUGLOG lines_total=%d lines_before_flush=%d flush_utc=%s' % (tot, n, ft))
    subprocess.run('grep -c . %s/logs/debug.log > %s/debuglog-lines.txt' % (N, OUT), shell=True)
    stop(); say('daemons left:', len(daemons()))
    subprocess.run('rm -rf %s' % N, shell=True)
