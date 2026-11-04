#!/usr/bin/env python3
"""Cluster tier (B3) of index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous, on pc12.

usage: ISC_RUN=run1 [ISC_N=4000000] [ISC_N2=1000000] [ISC_PHASES=all|short] python3 cluster-run.py
Writes ~/stage4-logs/isc/<ISC_RUN>/cluster/: session.log (every command and its output), rss-<life>.csv (RssAnon every 2 s, R4),
phases.json, system-<life>.log / isr-trace-<life>.log (each lifetime's slice), stress-*.out, summary.txt with EXPECTED lines.
Lifetimes (B3e + R3/R6/R7): L0 load (4096) | L1 4096 | L2 default | L3 400 | L4 100 | L5 0 | L6 0 + step 5 (max_index_interval=1)
| L7 step 6 (100, interval null, manual run, +ISC_N2 partitions). Node data under RUN=/tmp/isc-jason92 (local disk).
ISC_N != 4000000 is a shakedown (instrument check, not a reading). The node is stopped on every exit.
"""
import json, os, re, signal, socket, statistics, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-isc')
RUN = os.environ.get('ISC_DIR', '/tmp/isc-jason92')
RUNNAME = os.environ.get('ISC_RUN', 'run1')
N = int(os.environ.get('ISC_N', '4000000'))
N2 = int(os.environ.get('ISC_N2', '1000000'))
PHASES = os.environ.get('ISC_PHASES', 'all')
L = f'{HOME}/stage4-logs/isc/{RUNNAME}/cluster'
os.makedirs(L, exist_ok=True)
SESSION = open(f'{L}/session.log', 'a')
NT = [f'{C}/bin/nodetool', '-h', '127.0.0.1', '-p', '17199']
BEAN = 'org.apache.cassandra.db:type=IndexSummaries'
PH = {'N': N, 'N2': N2, 'lifetimes': {}}


def log(msg):
    line = f'{time.strftime("%Y-%m-%dT%H:%M:%S")} {int(time.time()*1000)} {msg}'
    print(line, flush=True); SESSION.write(line + '\n'); SESSION.flush()


def sh(cmd, check=False, timeout=900, quiet=False, env=None):
    log(f'$ {cmd}')
    p = subprocess.run(['bash', '-c', cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, env=env)
    out = p.stdout
    if not quiet:
        for l in out.rstrip().splitlines()[-60:]:
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
    sh(f'stat -f -c %T {RUN}; df -h {RUN}')
    sh(f'rm -rf {RUN}/conf && cp -r {C}/conf {RUN}/conf', check=True)
    Y = f'{RUN}/conf/cassandra.yaml'
    sh(f'''sed -i -e "s/^cluster_name:.*/cluster_name: 'isc-probe'/" \
       -e 's/^storage_port:.*/storage_port: 17000/' -e 's/^ssl_storage_port:.*/ssl_storage_port: 17001/' \
       -e 's/^native_transport_port:.*/native_transport_port: 19042/' \
       -e 's/^listen_address:.*/listen_address: 127.0.0.1/' -e 's/^rpc_address:.*/rpc_address: 127.0.0.1/' \
       -e 's/"127.0.0.1:7000"/"127.0.0.1:17000"/' \
       -e 's/^index_summary_capacity:.*/index_summary_capacity: 4096MiB/' \
       -e 's/^index_summary_resize_interval:.*/index_summary_resize_interval: 1m/' \
       -e 's/^key_cache_size:.*/key_cache_size: 0MiB/' {Y}''', check=True)
    with open(Y, 'a') as f:
        f.write(f'''data_file_directories:
    - {RUN}/data
commitlog_directory: {RUN}/commitlog
hints_directory: {RUN}/hints
saved_caches_directory: {RUN}/saved_caches
cdc_raw_directory: {RUN}/cdc_raw
memtable_heap_space: 256MiB
''')
    sh(f"sed -i 's/^JMX_PORT=\"7199\"/JMX_PORT=\"17199\"/' {RUN}/conf/cassandra-env.sh", check=True)
    # R4 item 6: TRACE appender for IndexSummaryRedistribution (additivity on)
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
    sh(f"grep -nE '^(cluster_name|storage_port|ssl_storage_port|native_transport_port|listen_address|rpc_address|index_summary_capacity|index_summary_resize_interval|key_cache_size|memtable_heap_space|commitlog_directory)|seeds:' {Y}; tail -8 {Y}; grep -n ISRTRACE -A1 {lb}; grep -n '^JMX_PORT' {RUN}/conf/cassandra-env.sh")
    for name in ('isc.yaml',):   # runbook fix D1 (2026-10-21): no `population:` on k; isc2 = the same profile with -pop seq=N+1..N+N2
        open(f'{RUN}/{name}', 'w').write(f'''keyspace: isc
keyspace_definition: |
  CREATE KEYSPACE isc WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}};
table: t
table_definition: |
  CREATE TABLE t (k blob PRIMARY KEY, v blob)
    WITH min_index_interval = 1 AND max_index_interval = 128
    AND bloom_filter_fp_chance = 1.0
    AND caching = {{'keys': 'NONE', 'rows_per_partition': 'NONE'}}
    AND compression = {{'enabled': 'false'}}
    AND compaction = {{'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}};
columnspec:
  - name: k
    size: fixed(200)
  - name: v
    size: fixed(16)
insert:
  partitions: fixed(1)
  batchtype: UNLOGGED
queries:
  read1:
    cql: SELECT v FROM t WHERE k = ?
    fields: samerow
''')
    sh(f'cat {RUN}/isc.yaml')


def set_yaml(cap, interval='1m'):
    Y = f'{RUN}/conf/cassandra.yaml'
    capv = '' if cap is None else f' {cap}MiB'
    sh(f"sed -i -e 's/^index_summary_capacity:.*/index_summary_capacity:{capv}/' "
       f"-e 's/^index_summary_resize_interval:.*/index_summary_resize_interval: {interval}/' {Y}; "
       f"grep -nE '^index_summary_(capacity|resize_interval)' {Y}", check=True)


def syslog_size():
    p = f'{RUN}/logs/system.log'
    return os.path.getsize(p) if os.path.exists(p) else 0


def trace_size():
    p = f'{RUN}/logs/isr-trace.log'
    return os.path.getsize(p) if os.path.exists(p) else 0


def read_from(path, off):
    if not os.path.exists(path):
        return ''
    with open(path, errors='replace') as f:
        f.seek(off); return f.read()


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


class Life:
    def __init__(self, name, cap, interval='1m'):
        self.name, self.cap, self.interval = name, cap, interval
        self.rec = {'cap': cap, 'interval': interval}
        PH['lifetimes'][name] = self.rec

    def start(self):
        if daemon_pids():
            raise RuntimeError(f'a node is already running: {daemon_pids()}')
        set_yaml(self.cap, self.interval)
        self.off = syslog_size(); self.toff = trace_size()
        self.rec['syslog_offset'] = self.off; self.rec['trace_offset'] = self.toff
        env = dict(os.environ, CASSANDRA_CONF=f'{RUN}/conf', CASSANDRA_LOG_DIR=f'{RUN}/logs', MAX_HEAP_SIZE='8G',
                   HEAP_NEWSIZE='2G', MALLOC_MMAP_THRESHOLD_='131072')
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
            txt = read_from(f'{RUN}/logs/system.log', self.off)
            try:
                socket.create_connection(('127.0.0.1', 19042), 1).close(); up = True
            except OSError:
                up = False
            if pid and up and 'Initializing index summary manager' in txt:
                break
        else:
            raise RuntimeError('node did not come up in 300 s')
        self.pid = pid; self.rec['pid'] = pid; self.rec['up_ms'] = int(time.time()*1000)
        m = re.search(r'Initializing index summary manager with a memory pool size of (\d+) MB and a resize interval of (-?\d+) minutes', txt)
        self.rec['pool_MB'] = int(m[1]); self.rec['interval_min'] = int(m[2])
        log(f'{self.name}: up pid={pid} in {time.time()-t0:.0f} s; {m[0]}')
        sh(f'{NT[0]} {" ".join(NT[1:])} statusbinary; ' + f"grep -E '^(VmRSS|RssAnon|RssFile)' /proc/{pid}/status")

    def wait_completed(self, after_off=None, timeout=240):
        off = self.off if after_off is None else after_off
        t0 = time.time(); self.redist_seen_ms = None
        while time.time() - t0 < timeout:
            txt = read_from(f'{RUN}/logs/system.log', off)
            i = txt.find('Redistributing index summaries')
            if i >= 0:
                if self.redist_seen_ms is None:
                    self.redist_seen_ms = int(time.time()*1000)   # R4 item 5: the pre-resize window ends here (2-s poll)
                if 'Completed resizing of index summaries' in txt[i:]:
                    return txt[i:]   # a run that both began and completed after the offset
            if not daemon_pids():
                raise RuntimeError('daemon died')
            time.sleep(2)
        raise RuntimeError('no Completed resizing line')

    def resize_lines(self, txt):
        b = re.search(r'Beginning redistribution of index summaries for (\d+) sstables with memory pool size (\d+) MiB; current spaced used is ([\d.E-]+) MiB', txt)
        d = re.search(r'index summaries: downsample: (\d+), force resample: (\d+), upsample: (\d+), force upsample: (\d+)', txt)
        c = re.search(r'Completed resizing of index summaries; current approximate memory used: ([\d.E-]+) MiB, time spent: (\d+)ms', txt)
        return b, d, c

    def measure(self, tag, after_off=None, tr_off=None):
        """B3e step 3d/3e: wait for the first Completed line after the offset, 30 s, then T, 5 RssAnon samples, tablestats, Summary.db."""
        txt = self.wait_completed(after_off)
        b, d, c = self.resize_lines(txt)
        r = {'T_MiB': float(c[1]), 'resize_ms': int(c[2]),
             'begin_sstables': int(b[1]), 'begin_pool_MiB': int(b[2]), 'T_before_MiB': float(b[3]),
             'downsample': int(d[1]), 'force_resample': int(d[2]), 'upsample': int(d[3]), 'force_upsample': int(d[4]),
             'completed_ms': int(time.time()*1000)}
        log(f'{self.name}/{tag}: {b[0]} | {d[0]} | {c[0]}')
        # the Beginning-line time in epoch ms from the rss sampler's perspective: use wall time of detection minus nothing;
        # the 20-s pre-resize window is taken from the rss csv by the analysis, using the log timestamps
        m2 = re.search(r'(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+)[^\n]*Completed resizing', txt)
        r['completed_logtime'] = m2[1] if m2 else None
        r['redist_seen_ms'] = self.redist_seen_ms
        time.sleep(30)
        samples = []
        for i in range(5):
            dd = rss_status(self.pid); samples.append([int(time.time()*1000), dd.get('RssAnon'), dd.get('RssFile')])
            if i < 4:
                time.sleep(10)
        r['rss_samples'] = samples
        r['R_MiB'] = statistics.median(s[1] for s in samples) / 1024.0
        ts = sh(f'{" ".join(NT)} tablestats isc.t | grep -E "SSTable count|Index summary off heap|Bloom filter off heap|Compression metadata off heap|Off heap memory used"')
        m = re.search(r'Index summary off heap memory used: (\d+)', ts)
        r['tablestats_isc_bytes'] = int(m[1]) if m else None
        m = re.search(r'SSTable count: (\d+)', ts); r['sstables'] = int(m[1]) if m else None
        files = sh(f'ls -l {RUN}/data/isc/t-*/*-Summary.db', quiet=True)
        sizes = [int(l.split()[4]) for l in files.splitlines() if l.endswith('Summary.db')]
        r['summary_db_sizes'] = sizes; r['summary_db_total'] = sum(sizes)
        sh(f'du -cb {RUN}/data/isc/t-*/*-Summary.db | tail -1')
        tr = read_from(f'{RUN}/logs/isr-trace.log', self.toff if tr_off is None else tr_off)
        segs = tr.split('Redistributing index summaries')
        tr = segs[1] if len(segs) > 1 else ''   # the first run after the offset only
        r['trace_keep_isc'] = len(re.findall(r'Using leftover space to keep \S*isc/t-', tr))
        r['trace_resample_isc'] = len(re.findall(r'Re-sampling index summary for \S*isc/t-', tr))
        r['trace_keep_all'] = tr.count('Using leftover space to keep')
        r['trace_resample_all'] = tr.count('Re-sampling index summary for')
        self.rec[tag] = r
        log(f'{self.name}/{tag}: T={r["T_MiB"]:.4f} MiB, before {r["T_before_MiB"]:.4f}, R={r["R_MiB"]:.1f} MiB, tablestats isc {r["tablestats_isc_bytes"]} B, '
            f'Summary.db total {r["summary_db_total"]} B over {len(sizes)} files, trace keep/resample isc {r["trace_keep_isc"]}/{r["trace_resample_isc"]}')
        dump()
        return r

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
        with open(f'{L}/system-{self.name}.log', 'w') as f:
            f.write(read_from(f'{RUN}/logs/system.log', self.off))
        with open(f'{L}/isr-trace-{self.name}.log', 'w') as f:
            f.write(read_from(f'{RUN}/logs/isr-trace.log', self.toff))
        self.rec['stop_ms'] = int(time.time()*1000)
        log(f'{self.name}: stopped; daemons left {daemon_pids()}')
        dump()


def dump():
    json.dump(PH, open(f'{L}/phases.json', 'w'), indent=1)


def stress(profile, n, tag, pop=''):
    out = sh(f'{C}/tools/bin/cassandra-stress user profile={RUN}/{profile} "ops(insert=1)" n={n} no-warmup cl=ONE {pop} '
             f'-rate threads=64 -node 127.0.0.1 -port native=19042 jmx=17199 -mode native cql3 > {L}/stress-{tag}.out 2>&1; '
             f'echo exit $?; grep -E "^(Op rate|Partition rate|Total partitions|Total errors|Total operation time)" {L}/stress-{tag}.out; tail -3 {L}/stress-{tag}.out', timeout=3600)
    PH.setdefault('stress', {})[tag] = out.strip().splitlines()


def jmx_get(attr):
    out = sh(f'{" ".join(NT)} sjk mx -b {BEAN} -mg -f {attr}')
    m = re.findall(r'^\s*([\d.E-]+)\s*$', out, re.M)
    return float(m[-1]) if m else None


def main():
    ab = None
    try:
        log(f'cluster-run start: N={N} N2={N2} PHASES={PHASES} host {socket.gethostname()} clone {C}')
        sh(f'cd {C} && git describe --tags && git rev-parse HEAD; java -version 2>&1 | head -1; uname -r; ss -ltn | grep -E ":(17000|17001|19042|17199) " || echo ports-free')
        sh(f'md5sum {os.path.dirname(os.path.abspath(__file__))}/*')
        if daemon_pids():
            raise RuntimeError('node already running')
        sh(f'rm -rf {RUN}', check=True)
        setup()
        # L0: load (B3e steps 1-2)
        ab = Life('L0-load', 4096); ab.start()
        stress('isc.yaml', N, 'load')
        sh(f'{" ".join(NT)} flush isc t; ls {RUN}/data/isc/t-*/*-Data.db | wc -l; du -sb {RUN}/data/isc {RUN}/commitlog; df -h {RUN}')
        PH['load_sstables'] = int(sh(f'ls {RUN}/data/isc/t-*/*-Data.db | wc -l').split()[0])
        ab.stop(); ab = None
        seq = [('L1-4096', 4096), ('L2-default', None), ('L3-400', 400), ('L4-100', 100), ('L5-0a', 0), ('L6-0b', 0)]
        if PHASES == 'short':
            seq = [('L1-4096', 4096), ('L3-400', 400), ('L5-0a', 0)]
        if PHASES == 'quick':   # shakedown of steps 5-6 only
            seq = [('L5-0a', 0), ('L6-0b', 0)]
        for name, cap in seq:
            ab = Life(name, cap); ab.start(); ab.measure('first')
            if name == 'L6-0b':
                # B3e step 5: floor/override control on the running node
                sh(f'{C}/bin/cqlsh 127.0.0.1 19042 -e "ALTER TABLE isc.t WITH min_index_interval = 1 AND max_index_interval = 1"', timeout=120)
                PH['lifetimes'][name]['alter_ms'] = int(time.time()*1000)
                off = syslog_size(); toff = trace_size()   # a run that began before the ALTER is not counted
                ab.measure('after_alter_max1', after_off=off, tr_off=toff)
            ab.stop(); ab = None
        if PHASES == 'short':
            return
        # L7: step 6 (R6)
        ab = Life('L7-step6', 100, interval='null'); ab.start()
        sh(f'{C}/bin/cqlsh 127.0.0.1 19042 -e "ALTER TABLE isc.t WITH min_index_interval = 1 AND max_index_interval = 128; DESCRIBE TABLE isc.t" | grep -E "index_interval"', timeout=120)
        off = syslog_size(); toff = trace_size()
        sh(f'{" ".join(NT)} sjk mx -b {BEAN} -mc -op redistributeSummaries', timeout=600)
        r = ab.measure('manual_run', after_off=off, tr_off=toff)
        PH['lifetimes']['L7-step6']['T_trig_jmx_MiB'] = jmx_get('MemoryPoolSizeInMB')
        off2 = syslog_size()
        stress('isc.yaml', N2, 'extra', pop=f'-pop seq={N+1}..{N+N2}')
        sh(f'{" ".join(NT)} flush isc t')
        log('waiting 120 s with no resize run (interval null)')
        time.sleep(120)
        rec = PH['lifetimes']['L7-step6']
        rec['T_after_jmx_MiB'] = jmx_get('MemoryPoolSizeInMB')
        ts = sh(f'{" ".join(NT)} tablestats isc.t | grep -E "SSTable count|Index summary off heap"')
        m = re.search(r'Index summary off heap memory used: (\d+)', ts); rec['T_after_tablestats_isc_bytes'] = int(m[1]) if m else None
        rec['completed_lines_after_manual'] = read_from(f'{RUN}/logs/system.log', off2).count('Completed resizing of index summaries')
        dd = rss_status(ab.pid); rec['rss_after_extra_kB'] = dd.get('RssAnon')
        log(f'step6: T_trig={r["T_MiB"]:.3f} MiB (jmx {rec["T_trig_jmx_MiB"]}), T_after jmx={rec["T_after_jmx_MiB"]} MiB, '
            f'tablestats {rec["T_after_tablestats_isc_bytes"]} B, Completed lines after manual run: {rec["completed_lines_after_manual"]}')
        dump()
        ab.stop(); ab = None
    except Exception as e:
        log(f'ERROR {type(e).__name__}: {e}')
        PH['error'] = str(e)
    finally:
        if ab is not None or daemon_pids():
            try:
                sh(f'{" ".join(NT)} drain', timeout=120)
            except Exception:
                pass
            for p in daemon_pids():
                os.kill(p, signal.SIGKILL)
        dump()
        log(f'daemons left: {daemon_pids()}; stress left: ' + subprocess.run(['bash', '-c', "ps -eo pid,args | grep '[S]tress' | wc -l"], stdout=subprocess.PIPE, text=True).stdout.strip())
        sh(f'python3 {os.path.dirname(os.path.abspath(__file__))}/cluster-analyze.py {L} > {L}/summary.txt 2>&1; cat {L}/summary.txt')
        open(f'{L}/done', 'w').write('done\n')


if __name__ == '__main__':
    main()
