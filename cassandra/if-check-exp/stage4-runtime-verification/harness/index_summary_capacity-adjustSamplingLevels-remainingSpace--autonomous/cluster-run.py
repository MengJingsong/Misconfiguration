#!/usr/bin/env python3
"""Cluster tier (B3) of index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous, on pc12 (loopback).

usage: IS2_RUN=run1 [IS2_BATCH=100000] [IS2_BATCHES=20] python3 cluster-run.py
Writes ~/stage4-logs/is2/<IS2_RUN>/cluster/: session.log (every command and its output), rss-<life>.csv (RssAnon every 2 s),
phases.json, system-<life>.log, isr-trace-<life>.log, r258-<life>.log, stress-*.out, summary.txt (cluster-analyze.py).
Lifetime L0 (yaml cap 64 MiB, interval null; R5): load 20 x 100,000 partitions with a flush after each batch (B3c), baseline
(step 4), then C = 4096, 1024, 512, 64, 8 over JMX with a restore (R7) after each, negative control (B3h, 300 s, no run), stop.
Lifetime L1 (yaml cap empty = auto): start, pool line, run, measure, stop. IS2_BATCH != 100000 is a shakedown (not a reading).
The node is stopped on every exit.
"""
import json, os, re, signal, socket, statistics, subprocess, threading, time

HOME = os.path.expanduser('~')
HARNESS = os.path.dirname(os.path.abspath(__file__))
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-is2')
RUN = os.environ.get('IS2_DIR', HOME + '/stage4-is2')
RUNNAME = os.environ.get('IS2_RUN', 'run1')
BATCH = int(os.environ.get('IS2_BATCH', '100000'))
BATCHES = int(os.environ.get('IS2_BATCHES', '20'))
CAPS = [int(x) for x in os.environ.get('IS2_CAPS', '4096,1024,512,64,8').split(',')]
NEG_S = int(os.environ.get('IS2_NEG_S', '300'))
L = f'{HOME}/stage4-logs/is2/{RUNNAME}/cluster'
os.makedirs(L, exist_ok=True)
SESSION = open(f'{L}/session.log', 'a')
NT = [f'{C}/bin/nodetool', '-h', '127.0.0.1', '-p', '17199']
BEAN = 'org.apache.cassandra.db:type=IndexSummaries'
BYTEMAN = f'{C}/build/lib/jars/byteman-4.0.20.jar'
PH = {'BATCH': BATCH, 'BATCHES': BATCHES, 'CAPS': CAPS, 'lifetimes': {}}


def log(msg):
    line = f'{time.strftime("%Y-%m-%dT%H:%M:%S")} {int(time.time()*1000)} {msg}'
    print(line, flush=True); SESSION.write(line + '\n'); SESSION.flush()


def sh(cmd, check=False, timeout=900, quiet=False, env=None):
    log(f'$ {cmd}')
    p = subprocess.run(['bash', '-c', cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, env=env)
    out = p.stdout
    if not quiet:
        for l in out.rstrip().splitlines()[-80:]:
            SESSION.write('  | ' + l + '\n')
    SESSION.write(f'  | exit {p.returncode}\n'); SESSION.flush()
    if check and p.returncode != 0:
        raise RuntimeError(f'command failed ({p.returncode}): {cmd}')
    return out


def daemon_pids():
    out = subprocess.run(['ps', '-eo', 'pid,args'], stdout=subprocess.PIPE, text=True).stdout
    pids = []
    for l in out.splitlines():
        f = l.split(None, 1)
        if len(f) == 2 and os.path.basename(f[1].split()[0]) == 'java' and 'CassandraDaemon' in f[1] and RUN + '/conf' in f[1]:
            pids.append(int(f[0]))
    return pids


def setup():
    sh(f'mkdir -p {RUN}/data {RUN}/commitlog {RUN}/hints {RUN}/saved_caches {RUN}/cdc_raw {RUN}/logs', check=True)
    sh(f'df -h {RUN}; ls /usr/lib/x86_64-linux-gnu | grep -c jemalloc || true')
    sh(f'rm -rf {RUN}/conf && cp -r {C}/conf {RUN}/conf', check=True)
    Y = f'{RUN}/conf/cassandra.yaml'
    sh(f'''sed -i -e "s/^cluster_name:.*/cluster_name: 'is2-probe'/" \
       -e 's/^storage_port:.*/storage_port: 17000/' -e 's/^ssl_storage_port:.*/ssl_storage_port: 17001/' \
       -e 's/^native_transport_port:.*/native_transport_port: 19042/' \
       -e 's/^listen_address:.*/listen_address: 127.0.0.1/' -e 's/^rpc_address:.*/rpc_address: 127.0.0.1/' \
       -e 's/"127.0.0.1:7000"/"127.0.0.1:17000"/' \
       -e 's/^index_summary_capacity:.*/index_summary_capacity: 64MiB/' \
       -e 's/^index_summary_resize_interval:.*/index_summary_resize_interval: null/' \
       -e 's/^commitlog_total_space:.*/commitlog_total_space: 4096MiB/' \
       -e 's/^#* *commitlog_total_space:.*/commitlog_total_space: 4096MiB/' \
       -e 's/^concurrent_compactors:.*/concurrent_compactors: 2/' -e 's/^#* *concurrent_compactors:.*/concurrent_compactors: 2/' {Y}''', check=True)
    with open(Y, 'a') as f:
        f.write(f'''data_file_directories:
    - {RUN}/data
commitlog_directory: {RUN}/commitlog
hints_directory: {RUN}/hints
saved_caches_directory: {RUN}/saved_caches
cdc_raw_directory: {RUN}/cdc_raw
''')
    sh(f"sed -i 's/^JMX_PORT=\"7199\"/JMX_PORT=\"17199\"/' {RUN}/conf/cassandra-env.sh", check=True)
    lb = f'{RUN}/conf/logback.xml'
    s = open(lb).read()
    add = '''  <appender name="ISRTRACE" class="ch.qos.logback.core.FileAppender">
    <file>${cassandra.logdir}/isr-trace.log</file>
    <encoder><pattern>%-5level [%thread] %date{ISO8601} %F:%L - %msg%n</pattern></encoder>
  </appender>
  <logger name="org.apache.cassandra.io.sstable.indexsummary.IndexSummaryRedistribution" level="TRACE">
    <appender-ref ref="ISRTRACE"/>
  </logger>
</configuration>'''
    assert s.count('</configuration>') == 1
    open(lb, 'w').write(s.replace('</configuration>', add))
    open(f'{RUN}/r258.btm', 'w').write(open(f'{HARNESS}/r258.btm.in').read().replace('@OUT@', f'{RUN}/logs/r258.log'))
    sh(f"grep -nE '^(cluster_name|storage_port|ssl_storage_port|native_transport_port|listen_address|rpc_address|index_summary_capacity|index_summary_resize_interval|commitlog_total_space|concurrent_compactors|disk_access_mode)|seeds:' {Y}; tail -6 {Y}; grep -n ISRTRACE -A1 {lb}; grep -n '^JMX_PORT' {RUN}/conf/cassandra-env.sh; cat {RUN}/r258.btm")
    # B3c profile with amendment R5 (no population: on pk)
    open(f'{RUN}/isr.yaml', 'w').write('''keyspace: isr
keyspace_definition: CREATE KEYSPACE isr WITH replication = {'class':'SimpleStrategy','replication_factor':1};
table: t
table_definition: |
  CREATE TABLE t (pk text PRIMARY KEY, v int)
  WITH min_index_interval = 1 AND max_index_interval = 2048
  AND compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'};
columnspec:
  - name: pk
    size: fixed(1000)
  - name: v
    size: fixed(4)
insert:
  partitions: fixed(1)
  batchtype: UNLOGGED
queries:
  read:
    cql: SELECT * FROM t WHERE pk = ?
    fields: samerow
''')
    sh(f'cat {RUN}/isr.yaml')


def set_yaml_cap(cap):
    Y = f'{RUN}/conf/cassandra.yaml'
    capv = '' if cap is None else f' {cap}MiB'
    sh(f"sed -i -e 's/^index_summary_capacity:.*/index_summary_capacity:{capv}/' {Y}; grep -nE '^index_summary_(capacity|resize_interval)' {Y}", check=True)


def fsize(name):
    p = f'{RUN}/logs/{name}'
    return os.path.getsize(p) if os.path.exists(p) else 0


def read_from(name, off):
    p = f'{RUN}/logs/{name}'
    if not os.path.exists(p):
        return ''
    with open(p, errors='replace') as f:
        f.seek(off); return f.read()


def offsets():
    return {n: fsize(n) for n in ('system.log', 'isr-trace.log', 'r258.log')}


def rss_status(pid):
    d = {}
    try:
        for l in open(f'/proc/{pid}/status'):
            k, _, v = l.partition(':')
            if k in ('RssAnon', 'RssFile', 'RssShmem', 'VmRSS'):
                d[k] = int(v.split()[0])
    except Exception:
        pass
    return d


class Sampler(threading.Thread):
    def __init__(self, pid, path):
        super().__init__(daemon=True); self.pid = pid; self.f = open(path, 'w'); self.stop_ = False
        self.f.write('epoch_ms,RssAnon_kB,RssFile_kB,VmRSS_kB\n')

    def run(self):
        while not self.stop_:
            d = rss_status(self.pid)
            if not d:
                break
            self.f.write(f"{int(time.time()*1000)},{d.get('RssAnon')},{d.get('RssFile')},{d.get('VmRSS')}\n"); self.f.flush()
            time.sleep(2)


def jmx_get(attr, quiet=False):
    return sh(f'{" ".join(NT)} sjk mx -b {BEAN} -mg -f {attr}', quiet=quiet)


def jmx_num(attr):
    out = jmx_get(attr)
    m = re.findall(r'^\s*(-?[\d.]+(?:E-?\d+)?)\s*$', out, re.M)
    return float(m[-1]) if m else None


def jmx_set_cap(c):
    sh(f'{" ".join(NT)} sjk mx -b {BEAN} -ms -f MemoryPoolCapacityInMB -v {c}', check=True)
    v = jmx_num('MemoryPoolCapacityInMB')
    if v is None or int(v) != c:
        raise RuntimeError(f'capacity readback {v} != {c}')
    return v


def intervals():
    out = jmx_get('IndexIntervals', quiet=True)
    open(f'{L}/intervals-last.txt', 'w').write(out)
    iv = re.findall(r'(\S*isr/t-\S*?)\S*\s+(\d+)\s*$', out, re.M)
    if not iv:   # fall back to "name=value" maps
        iv = re.findall(r'(\S*isr/t-[^=\s]*)=(\d+)', out)
    return [int(x[1]) for x in iv], out


def rss_window(pid, seconds, step):
    samples = []
    n = int(seconds // step)
    for i in range(n):
        d = rss_status(pid); samples.append([int(time.time()*1000), d.get('RssAnon'), d.get('RssFile'), d.get('VmRSS')])
        if i < n - 1:
            time.sleep(step)
    return samples


def stress(tag, a, b):
    out = sh(f'{C}/tools/bin/cassandra-stress user profile={RUN}/isr.yaml "ops(insert=1)" n={b - a + 1} no-warmup cl=ONE '
             f'-pop seq={a}..{b} -rate threads=64 -node 127.0.0.1 -port native=19042 jmx=17199 -mode native cql3 '
             f'> {L}/stress-{tag}.out 2>&1; echo exit $?; grep -E "^(Op rate|Partition rate|Total partitions|Total errors|Total operation time)" {L}/stress-{tag}.out',
             timeout=3600)
    PH.setdefault('stress', {})[tag] = out.strip().splitlines()


class Node:
    def __init__(self, name, cap):
        self.name, self.cap = name, cap
        self.rec = {'yaml_cap': cap, 'runs': {}}
        PH['lifetimes'][name] = self.rec

    def start(self):
        if daemon_pids():
            raise RuntimeError(f'a node is already running: {daemon_pids()}')
        set_yaml_cap(self.cap)
        self.off = offsets(); self.rec['offsets'] = self.off
        env = dict(os.environ, CASSANDRA_CONF=f'{RUN}/conf', CASSANDRA_LOG_DIR=f'{RUN}/logs', MAX_HEAP_SIZE='8G',
                   HEAP_NEWSIZE='2G', MALLOC_MMAP_THRESHOLD_='131072', CASSANDRA_LIBJEMALLOC='-',
                   JVM_EXTRA_OPTS=f'-javaagent:{BYTEMAN}=script:{RUN}/r258.btm')
        t0 = time.time(); self.rec['start_ms'] = int(t0*1000)
        sh(f'ulimit -n 100000; ulimit -n; {C}/bin/cassandra -p {RUN}/cassandra.pid > {RUN}/logs/stdout-{self.name}.txt 2>&1', env=env)
        pid = None
        while time.time() - t0 < 300:
            time.sleep(2)
            ps = daemon_pids()
            if ps:
                pid = ps[0]
                if not hasattr(self, 'sampler'):
                    self.sampler = Sampler(pid, f'{L}/rss-{self.name}.csv'); self.sampler.start()
            elif time.time() - t0 > 20:
                raise RuntimeError('daemon not running (died during start?)')
            txt = read_from('system.log', self.off['system.log'])
            try:
                socket.create_connection(('127.0.0.1', 19042), 1).close(); up = True
            except OSError:
                up = False
            if pid and up and 'Initializing index summary manager' in txt:
                break
        else:
            raise RuntimeError('node did not come up in 300 s')
        self.pid = pid; self.rec['pid'] = pid
        m = re.search(r'Initializing index summary manager with a memory pool size of (\d+) MB and a resize interval of (-?\d+) minutes', txt)
        self.rec['pool_line'] = m[0]; self.rec['pool_MB'] = int(m[1]); self.rec['interval_min'] = int(m[2])
        log(f'{self.name}: up pid={pid} in {time.time()-t0:.0f} s; {m[0]}')
        sh(f'{" ".join(NT)} statusbinary; grep -E "^(VmRSS|RssAnon|RssFile)" /proc/{pid}/status; '
           f'grep -c jemalloc /proc/{pid}/maps; tr "\\0" " " < /proc/{pid}/cmdline | grep -o "javaagent[^ ]*"; '
           f'tr "\\0" "\\n" < /proc/{pid}/environ | grep -E "MALLOC_MMAP|LD_PRELOAD" || true')

    def state(self, tag):
        """T (JMX), tablestats isr, intervals, Summary.db bytes, compactionstats."""
        r = {'ms': int(time.time()*1000)}
        r['T_jmx_MiB'] = jmx_num('MemoryPoolSizeInMB')
        ts = sh(f'{" ".join(NT)} tablestats isr.t | grep -E "SSTable count|Index summary off heap|Bloom filter off heap|Compression metadata off heap|Off heap memory used"')
        m = re.search(r'Index summary off heap memory used: (\d+)', ts); r['isr_bytes'] = int(m[1]) if m else None
        m = re.search(r'SSTable count: (\d+)', ts); r['sstables'] = int(m[1]) if m else None
        iv, _ = intervals(); r['isr_intervals'] = iv
        files = sh(f'ls -l {RUN}/data/isr/t-*/*-Summary.db', quiet=True)
        sizes = [int(l.split()[4]) for l in files.splitlines() if l.endswith('Summary.db')]
        r['summary_db_n'] = len(sizes); r['summary_db_total'] = sum(sizes)
        r['big_summary_files'] = sum(1 for l in files.splitlines() if '-big-Summary.db' in l)
        cs = sh(f'{" ".join(NT)} compactionstats')
        r['compactionstats_pending'] = (re.search(r'pending tasks: (\d+)', cs) or [None, None])[1]
        r['compactionstats_lines'] = [l for l in cs.splitlines() if l.strip() and 'pending' not in l]
        log(f'{self.name}/{tag}: T_jmx={r["T_jmx_MiB"]} MiB isr={r["isr_bytes"]} B sstables={r["sstables"]} '
            f'intervals={sorted(set(iv))} Summary.db {r["summary_db_n"]} files {r["summary_db_total"]} B')
        return r

    def run_once(self, tag, cap):
        """Set cap over JMX, R_before (30 s), trigger, Completed line, 30 s, R_after (5 x 10 s), state, trace, R258."""
        rec = {'cap': cap}
        jmx_set_cap(cap)
        rec['before'] = self.state(f'{tag}/before')
        rec['rss_before'] = rss_window(self.pid, 30, 5)
        rec['R_before_MiB'] = statistics.median(s[1] for s in rec['rss_before']) / 1024.0
        off = offsets(); rec['offsets'] = off
        t0 = time.time()
        sh(f'{" ".join(NT)} sjk mx -b {BEAN} -mc -op redistributeSummaries', timeout=1800)
        rec['invoke_s'] = round(time.time() - t0, 1)
        txt = ''
        for _ in range(300):
            txt = read_from('system.log', off['system.log'])
            if 'Completed resizing of index summaries' in txt:
                break
            time.sleep(2)
        b = re.search(r'Beginning redistribution of index summaries for (\d+) sstables with memory pool size (\d+) MiB; current spaced used is ([\d.E-]+) MiB', txt)
        d = re.search(r'index summaries: downsample: (\d+), force resample: (\d+), upsample: (\d+), force upsample: (\d+)', txt)
        c = re.search(r'Completed resizing of index summaries; current approximate memory used: ([\d.E-]+) MiB, time spent: (\d+)ms', txt)
        if not c:
            raise RuntimeError(f'{tag}: no Completed resizing line')
        rec.update({'begin_sstables': int(b[1]), 'begin_pool_MiB': int(b[2]), 'T_before_MiB': float(b[3]),
                    'downsample': int(d[1]), 'force_resample': int(d[2]), 'upsample': int(d[3]), 'force_upsample': int(d[4]),
                    'T_MiB': float(c[1]), 'resize_ms': int(c[2]), 'completed_count': txt.count('Completed resizing of index summaries')})
        log(f'{self.name}/{tag}: {b[0]} | {d[0]} | {c[0]}')
        tr = read_from('isr-trace.log', off['isr-trace.log'])
        rec['keep_isr'] = len(re.findall(r'Using leftover space to keep \S*isr/t-', tr))
        rec['resample_isr'] = len(re.findall(r'Re-sampling index summary for \S*isr/t-', tr))
        rec['keep_all'] = tr.count('Using leftover space to keep')
        rec['resample_all'] = tr.count('Re-sampling index summary for')
        rr = re.findall(r'R258 epoch_ms=(\d+) remainingSpace=(-?\d+) memoryPoolCapacity=(-?\d+) branch=(\w+)', read_from('r258.log', off['r258.log']))
        rec['r258'] = [[int(x[0]), int(x[1]), int(x[2]), x[3]] for x in rr]
        time.sleep(30)
        rec['rss_after'] = rss_window(self.pid, 50, 10)
        rec['R_after_MiB'] = statistics.median(s[1] for s in rec['rss_after']) / 1024.0
        rec['after'] = self.state(f'{tag}/after')
        log(f'{self.name}/{tag}: cap={cap} T={rec["T_MiB"]:.3f} (before {rec["T_before_MiB"]:.3f}) R258={rec["r258"]} '
            f'keep/resample isr {rec["keep_isr"]}/{rec["resample_isr"]} R_before={rec["R_before_MiB"]:.1f} R_after={rec["R_after_MiB"]:.1f} MiB')
        self.rec['runs'][tag] = rec
        dump()
        return rec

    def restore(self, tag):
        """R7: ALTER min=max=1, cap 8192, run (force upsample), ALTER back to 1/2048."""
        sh(f'{C}/bin/cqlsh 127.0.0.1 19042 -e "ALTER TABLE isr.t WITH min_index_interval = 1 AND max_index_interval = 1"', timeout=120, check=True)
        rec = self.run_once(tag, 8192)
        sh(f'{C}/bin/cqlsh 127.0.0.1 19042 -e "ALTER TABLE isr.t WITH min_index_interval = 1 AND max_index_interval = 2048; DESCRIBE TABLE isr.t" | grep -E "index_interval"', timeout=120, check=True)
        rec['restored_ok'] = rec['T_MiB'] >= 1900 * (BATCH * BATCHES) / 2_000_000 and all(x == 1 for x in rec['after']['isr_intervals']) and len(rec['after']['isr_intervals']) == BATCHES
        log(f'{self.name}/{tag}: restore ok={rec["restored_ok"]}')
        dump()

    def stop(self):
        sh(f'{" ".join(NT)} drain', timeout=300)
        for p in daemon_pids():
            os.kill(p, signal.SIGTERM)
        t0 = time.time()
        while daemon_pids() and time.time() - t0 < 120:
            time.sleep(2)
        for p in daemon_pids():
            os.kill(p, signal.SIGKILL)
        if hasattr(self, 'sampler'):
            self.sampler.stop_ = True
        time.sleep(3)
        for n, pre in (('system.log', 'system'), ('isr-trace.log', 'isr-trace'), ('r258.log', 'r258')):
            with open(f'{L}/{pre}-{self.name}.log', 'w') as f:
                f.write(read_from(n, self.off[n]))
        self.rec['stop_ms'] = int(time.time()*1000)
        log(f'{self.name}: stopped; daemons left {daemon_pids()}')
        dump()


def dump():
    json.dump(PH, open(f'{L}/phases.json', 'w'), indent=1)


def main():
    nd = None
    try:
        log(f'cluster-run start: BATCH={BATCH} BATCHES={BATCHES} CAPS={CAPS} host {socket.gethostname()} clone {C}')
        sh(f'cd {C} && git describe --tags && git rev-parse HEAD; java -version 2>&1 | head -1; uname -r; ss -ltn | grep -E ":(17000|17001|19042|17199|9091) " || echo ports-free')
        sh(f'md5sum {HARNESS}/*')
        if daemon_pids():
            raise RuntimeError('node already running')
        sh(f'rm -rf {RUN}', check=True)
        setup()
        nd = Node('L0-main', 64); nd.start()
        # B3e step 3: load with a flush after each batch
        for i in range(BATCHES):
            stress(f'load{i:02d}', i * BATCH + 1, (i + 1) * BATCH)
            sh(f'{" ".join(NT)} flush isr t', check=True)
        sh(f'ls {RUN}/data/isr/t-*/ | head -12; du -sb {RUN}/data/isr {RUN}/commitlog; df -h {RUN}')
        # step 4: baseline (bypass a at cap 64, no run)
        time.sleep(60)
        rec = nd.rec
        rec['baseline'] = nd.state('baseline')
        rec['baseline']['cap_jmx'] = jmx_num('MemoryPoolCapacityInMB')
        rec['baseline']['rss'] = rss_window(nd.pid, 30, 5)
        rec['baseline']['completed_lines'] = read_from('system.log', nd.off['system.log']).count('Completed resizing')
        dump()
        for cap in CAPS:
            nd.run_once(f'C{cap}', cap)
            nd.restore(f'restore-after-C{cap}')
        # B3h negative control: cap 64, no trigger, NEG_S s
        jmx_set_cap(64)
        off = offsets()
        neg = {'before': nd.state('neg/before'), 'start_ms': int(time.time()*1000)}
        neg['rss'] = rss_window(nd.pid, NEG_S, 10)
        neg['after'] = nd.state('neg/after')
        neg['completed_lines'] = read_from('system.log', off['system.log']).count('Completed resizing')
        neg['resize_interval_jmx'] = jmx_num('ResizeIntervalInMinutes')
        rec['negative_control'] = neg
        dump()
        nd.stop(); nd = None
        # step 6: auto default (state is full after the last restore)
        nd = Node('L1-auto', None); nd.start()
        nd.rec['baseline'] = nd.state('auto/baseline')
        nd.run_once('Cauto', nd.rec['pool_MB'])
        nd.stop(); nd = None
    except Exception as e:
        log(f'ERROR {type(e).__name__}: {e}')
        PH['error'] = str(e)
    finally:
        if nd is not None or daemon_pids():
            try:
                sh(f'{" ".join(NT)} drain', timeout=120)
            except Exception:
                pass
            for p in daemon_pids():
                os.kill(p, signal.SIGKILL)
        dump()
        log(f'daemons left: {daemon_pids()}; stress left: ' + subprocess.run(['bash', '-c', "ps -eo pid,args | awk '$2 ~ /java$/ && /Stress/' | wc -l"], stdout=subprocess.PIPE, text=True).stdout.strip())
        sh(f'python3 {HARNESS}/cluster-analyze.py {L} > {L}/summary.txt 2>&1; cat {L}/summary.txt')
        open(f'{L}/done', 'w').write('done\n')


if __name__ == '__main__':
    main()
