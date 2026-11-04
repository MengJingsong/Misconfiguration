#!/usr/bin/env python3
"""Cluster tier, one run (B3, amendments B5).
Usage: cluster-run.py <label> tree=<dir name under ~> mode=<CONTAINS|PREFIX|NONE> size=<chars> heap_mb=<memtable_heap_space MiB>
                      stop=<switches (0 = fixed rows)> rows=<row cap, or the fixed row count> inflight=<n> outdir=<dir> [expect_rejected=1]
One node on 127.0.31.1 (JMX 7331, native 9353, storage 7031; Byteman 9331 not used), heap 2 GiB, from ~/<tree> (never used by ant while the node runs).
Data under ~/s4-tm-data/<label>. Everything is logged to <outdir>/session.log; the node and the sampler are stopped on any exit."""
import os, sys, time, subprocess, shutil, signal, json, yaml, glob, re, atexit

label = sys.argv[1]
A = dict(a.split('=', 1) for a in sys.argv[2:])
tree, mode, size, heap_mb, stop, rows, inflight, outdir = A['tree'], A['mode'], int(A['size']), int(A['heap_mb']), int(A['stop']), int(A['rows']), int(A['inflight']), A['outdir']
HOME = os.path.expanduser('~')
TREE = HOME + '/' + tree
HARN = os.path.dirname(os.path.abspath(__file__))
WORK = HOME + '/s4-tm-data/' + label
JMX, NATIVE, STORAGE, ADDR = 7331, 9353, 7031, '127.0.31.1'
os.makedirs(outdir, exist_ok=True)
LOG = open(outdir + '/session.log', 'a')
pids = {}
def now_ms(): return int(time.time() * 1000)
def log(*a):
    s = '[%s] %s' % (time.strftime('%FT%T', time.gmtime()) + '.%03dZ' % (now_ms() % 1000), ' '.join(str(x) for x in a))
    LOG.write(s + '\n'); LOG.flush(); print(s, flush=True)
def sh(cmd, timeout=600, check=False, quiet=False):
    log('+', cmd)
    r = subprocess.run(['bash', '-c', cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if r.stdout.strip() and not quiet:
        LOG.write(r.stdout[-4000:] + '\n'); LOG.flush()
    if check and r.returncode:
        raise RuntimeError('command failed rc=%d: %s' % (r.returncode, cmd))
    return r
def alive(pid):
    try:
        return open('/proc/%d/stat' % pid).read().rsplit(')', 1)[1].split()[0] != 'Z'
    except Exception:
        return False
def stop_all():
    for name, p in list(pids.items()):
        try: os.kill(p, signal.SIGTERM)
        except Exception: pass
    t0 = time.time()
    while time.time() - t0 < 90 and any(alive(p) for p in pids.values()):
        time.sleep(1)
    for name, p in list(pids.items()):
        if alive(p):
            log('SIGKILL', name, p)
            try: os.kill(p, signal.SIGKILL)
            except Exception: pass
    log('stopped', pids)
atexit.register(stop_all)

def nt(args, timeout=900):
    return sh('%s/bin/nodetool -h 127.0.0.1 -p %d %s' % (TREE, JMX, args), timeout=timeout)

def mkconf():
    d = WORK
    for s_ in ['data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs']:
        os.makedirs('%s/%s' % (d, s_), exist_ok=True)
    conf = d + '/conf'
    shutil.copytree(TREE + '/conf', conf)
    y = yaml.safe_load(open(conf + '/cassandra.yaml'))
    y.update({'cluster_name': 's4tm', 'num_tokens': 1, 'listen_address': ADDR, 'rpc_address': ADDR,
              'seed_provider': [{'class_name': 'org.apache.cassandra.locator.SimpleSeedProvider', 'parameters': [{'seeds': '%s:%d' % (ADDR, STORAGE)}]}],
              'storage_port': STORAGE, 'native_transport_port': NATIVE, 'sasi_indexes_enabled': True, 'auto_snapshot': False,
              'memtable_heap_space': '%dMiB' % heap_mb, 'memtable_allocation_type': 'heap_buffers', 'commitlog_total_space': '1024MiB', 'concurrent_writes': 8,
              'data_file_directories': [d + '/data'], 'commitlog_directory': d + '/commitlog', 'hints_directory': d + '/hints',
              'saved_caches_directory': d + '/saved_caches', 'cdc_raw_directory': d + '/cdc_raw'})
    yaml.safe_dump(y, open(conf + '/cassandra.yaml', 'w'), default_flow_style=False)
    env = open(conf + '/cassandra-env.sh').read().replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % JMX)
    open(conf + '/cassandra-env.sh', 'w').write(env)
    lb = open(conf + '/logback.xml').read().replace('<maxFileSize>50MB</maxFileSize>', '<maxFileSize>4GB</maxFileSize>').replace('<totalSizeCap>5GB</totalSizeCap>', '<totalSizeCap>20GB</totalSizeCap>')
    open(conf + '/logback.xml', 'w').write(lb)   # no rolling inside a run: log counts are read from one file
    return d, conf

def start():
    d, conf = mkconf()
    e = dict(os.environ)
    e.update(CASSANDRA_HOME=TREE, CASSANDRA_CONF=conf, CASSANDRA_LOG_DIR=d + '/logs', MAX_HEAP_SIZE='2G', JVM_EXTRA_OPTS='-Dcassandra.ring_delay_ms=5000 -Duser.timezone=UTC')
    cmd = 'ulimit -n 100000; exec %s/bin/cassandra -f -p %s/pid' % (TREE, d)
    log('start node', cmd)
    p = subprocess.Popen(['bash', '-c', cmd], env=e, stdout=open(d + '/stdout.log', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    pids['node'] = p.pid
    return d, p

def wait_binary(p, tmax=300):
    t0 = time.time()
    while time.time() - t0 < tmax:
        if p.poll() is not None:
            log('node died during start rc', p.returncode); return False
        r = nt('statusbinary', 60)
        if 'running' in r.stdout and 'not running' not in r.stdout:
            return True
        time.sleep(3)
    return False

def histo(pid, tag):
    r = sh('jcmd %d GC.class_histogram' % pid, timeout=300, quiet=True)
    open('%s/histogram-%s.txt' % (outdir, tag), 'w').write(r.stdout)
    tot = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith('Total')]
    keep = [l.strip() for l in r.stdout.splitlines() if re.search(r'CharArrayNode|ConcurrentSkipListMap\$Node |ConcurrentSkipListMap\$Index|\[C$|\[C |SizeEstimating', l)][:14]
    log('histogram', tag, tot, keep)
    m = re.search(r'Total\s+(\d+)\s+(\d+)', r.stdout)
    return dict(total_bytes=int(m.group(2)) if m else None, total_instances=int(m.group(1)) if m else None, top=keep)

def last_sample(path):
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2); sz = f.tell(); f.seek(max(0, sz - 400))
            ls = f.read().decode().strip().split('\n')
        parts = ls[-1].split(',')
        if len(parts) == 4 and parts[0].isdigit():
            return [int(x) for x in parts]
    except Exception:
        pass
    return None

STRINGS = ["Can't add term", "Enqueuing flush of ks.t, Reason: MEMTABLE_LIMIT", "Enqueuing flush of ks.t", "Flushed index segment", "Rejecting value", "java.lang.OutOfMemoryError", "Flushing largest"]
def count_log(path):
    txt = open(path, 'rb').read().decode('utf8', 'replace')
    return {k: txt.count(k) for k in STRINGS}
def si_files(d):
    return sorted((os.path.basename(f), os.path.getsize(f)) for f in glob.glob(d + '/data/ks/t-*/*SI_*.db'))
def data_files(d):
    return sorted((os.path.basename(f), os.path.getsize(f)) for f in glob.glob(d + '/data/ks/t-*/*-Data.db'))

summary = dict(label=label, args=A, host=os.uname().nodename)
try:
    log('run', label, A, 'host', os.uname().nodename)
    for port in (JMX, NATIVE, STORAGE):
        if sh('ss -ltn | grep -q ":%d "' % port).returncode == 0:
            raise RuntimeError('port %d busy' % port)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    sh('mkdir -p %s/sampler && javac -d %s/sampler %s/Sampler.java' % (WORK, WORK, HARN), check=True)
    d, p = start()
    if not wait_binary(p):
        log('first start failed; retrying once after 20 s')
        shutil.copy(d + '/stdout.log', outdir + '/node-stdout-failed-start.log')
        pids.clear(); time.sleep(20)
        shutil.rmtree(WORK, ignore_errors=True); os.makedirs(WORK)
        sh('mkdir -p %s/sampler && javac -d %s/sampler %s/Sampler.java' % (WORK, WORK, HARN), check=True)
        d, p = start()
        if not wait_binary(p):
            raise RuntimeError('node did not start')
    log('node up'); time.sleep(5)
    slog = d + '/logs/system.log'
    cmdline = open('/proc/%d/cmdline' % p.pid, 'rb').read().replace(b'\0', b' ').decode()
    open(outdir + '/node-cmdline.txt', 'w').write(cmdline + '\n')
    summary['xmx'] = re.findall(r'-Xmx\S+', cmdline); summary['xms'] = re.findall(r'-Xms\S+', cmdline)
    summary['maxterm_jar'] = os.path.basename(glob.glob(TREE + '/build/apache-cassandra-*.jar')[0])
    jar = glob.glob(TREE + '/build/apache-cassandra-*.jar')[0]
    cc = sh("javap -constants -cp %s org.apache.cassandra.index.sasi.disk.OnDiskIndexBuilder | grep MAX_TERM_SIZE; javap -c -cp %s org.apache.cassandra.index.sasi.memory.TrieMemIndex | grep -m1 -B1 'if_icmplt'" % (jar, jar), quiet=True)
    c = [x.strip() for x in cc.stdout.strip().splitlines()]
    summary['constant_check'] = c
    log('constant check', c)
    y = yaml.safe_load(open(d + '/conf/cassandra.yaml'))
    summary['yaml'] = {k: y.get(k) for k in ('memtable_heap_space', 'memtable_cleanup_threshold', 'memtable_flush_writers', 'memtable_allocation_type', 'commitlog_total_space', 'concurrent_writes', 'sasi_indexes_enabled')}
    summary['histo_base'] = histo(p.pid, 'base')
    r = sh('python3 %s/loader.py schema %s %s %d %s' % (HARN, TREE, ADDR, NATIVE, mode), timeout=300, check=True)
    summary['schema_out'] = r.stdout.strip().splitlines()[-1:]
    samp = outdir + '/samples.csv'
    smp = subprocess.Popen(['java', '-cp', WORK + '/sampler', 'Sampler', str(JMX), samp, '100'],
                           stdout=open(outdir + '/sampler.out', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    pids['sampler'] = smp.pid
    time.sleep(6)
    stopfile = WORK + '/stop'; rowslog = outdir + '/rows.csv'
    open(rowslog, 'w').close()
    off0 = os.path.getsize(slog)
    sm0 = last_sample(samp)
    base_switch = sm0[3] if sm0 else 0   # the CREATE INDEX already switched the memtable once
    summary['base_switch'] = base_switch; summary['sample_before_load'] = sm0
    summary['t_load_start'] = now_ms()
    ld = subprocess.Popen(['python3', HARN + '/loader.py', 'load', TREE, ADDR, str(NATIVE), str(size), str(rows), str(inflight), stopfile, rowslog, WORK + '/pause'],
                          stdout=open(outdir + '/loader.out', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    pids['loader'] = ld.pid
    trigger = heap_mb * 1048576 / 3.0
    mid_done = False; t_deadline = time.time() + 3600
    while ld.poll() is None and time.time() < t_deadline:
        sm = last_sample(samp)
        if sm:
            if stop and sm[3] - base_switch >= stop and not os.path.exists(stopfile):
                open(stopfile, 'w').close(); log('stop file written at switch_count', sm[3])
            if (not mid_done) and sm[2] >= 0.4 * trigger and mode != 'NONE':
                mid_done = True
                open(WORK + '/pause', 'w').close()   # the loader waits while this file exists, so the histogram sees the full index memtable
                time.sleep(0.5)
                summary['mid_sample'] = last_sample(samp)
                summary['mid_fraction_of_trigger'] = round(summary['mid_sample'][2] / trigger, 3)
                summary['histo_mid'] = histo(p.pid, 'mid')
                os.remove(WORK + '/pause')
        if p.poll() is not None:
            raise RuntimeError('node died during load')
        time.sleep(0.1)
    if ld.poll() is None:
        ld.kill(); raise RuntimeError('loader timeout')
    summary['loader_rc'] = ld.returncode
    summary['t_load_end'] = now_ms()
    summary['loader_out'] = open(outdir + '/loader.out').read().strip().splitlines()[-3:]
    time.sleep(25)   # let the last flush and its index segments finish
    summary['t_settled'] = now_ms()
    v = sh('python3 %s/loader.py verify %s %s %d %d %s' % (HARN, TREE, ADDR, NATIVE, size, mode), timeout=600)
    summary['verify_out'] = v.stdout.strip().splitlines()[-3:]
    summary['log_counts'] = count_log(slog)
    summary['si_files'] = si_files(d); summary['data_files'] = data_files(d)
    summary['histo_post'] = histo(p.pid, 'post')
    nt('tablestats ks.t')
    open(outdir + '/tablestats.txt', 'w').write(nt('tablestats ks.t').stdout)
    summary['t_end'] = now_ms()
    # keep the flush lines and errors, drop the per-row rejection lines
    sh("grep -e 'Enqueuing flush of ks.t' -e 'Flushing largest' -e 'Completed flushing' -e 'Flushed index segment' -e 'OutOfMemory' -e '^ERROR' -e '^WARN' %s | grep -v \"Can't add term\" > %s/flush-lines.txt" % (slog, outdir), quiet=True)
    sh("grep -c \"Can't add term\" %s > %s/cantadd-count.txt" % (slog, outdir), quiet=True)
    sh("grep -m3 \"Can't add term\" %s > %s/cantadd-sample.txt" % (slog, outdir), quiet=True)
    sh('df -h %s | tail -1' % WORK)
except Exception as ex:
    log('ERROR', repr(ex)); summary['error'] = repr(ex)
finally:
    json.dump(summary, open(outdir + '/summary.json', 'w'), indent=1)
    stop_all()
    for f in ('stdout.log',):
        if os.path.exists(WORK + '/' + f): shutil.copy(WORK + '/' + f, outdir + '/node-' + f)
    pids.clear()
    time.sleep(1)
    shutil.rmtree(WORK, ignore_errors=True)
    log('done', json.dumps({k: v for k, v in summary.items() if not k.startswith('histo')}))
