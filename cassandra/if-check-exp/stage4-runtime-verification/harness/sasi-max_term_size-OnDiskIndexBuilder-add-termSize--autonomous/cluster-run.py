#!/usr/bin/env python3
"""Cluster tier, one run (B3, amendments B5).
Usage: cluster-run.py <label> <size> <rows> <cap_mb|-> <outdir>
Needs ~/s4-od (built, never used by ant while the node runs), and this folder. One node on 127.0.26.1; JMX 7326, native 9348, storage 7026.
Data under ~/s4-od-data/<label>. Everything is logged to <outdir>/session.log; the node and the sampler are stopped on any exit."""
import os, sys, time, subprocess, shutil, signal, json, yaml, glob, re, atexit

label, size, rows, cap, outdir = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
HOME = os.path.expanduser('~')
TREE = HOME + '/s4-od'
HARN = os.path.dirname(os.path.abspath(__file__))
WORK = HOME + '/s4-od-data/' + label
JMX, NATIVE, STORAGE, ADDR = 7326, 9348, 7026, '127.0.26.1'
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
def stop_all():
    for name, p in list(pids.items()):
        try: os.kill(p, signal.SIGTERM)
        except Exception: pass
    t0 = time.time()
    while time.time() - t0 < 60 and any(os.path.exists('/proc/%d' % p) for p in pids.values()):
        time.sleep(1)
    for name, p in list(pids.items()):
        if os.path.exists('/proc/%d' % p):
            log('SIGKILL', name, p)
            try: os.kill(p, signal.SIGKILL)
            except Exception: pass
    log('stopped', pids)
atexit.register(stop_all)

def nt(args, timeout=900):
    return sh('%s/bin/nodetool -h 127.0.0.1 -p %d %s' % (TREE, JMX, args), timeout=timeout)

def mkconf():
    d = WORK
    for s in ['data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs']:
        os.makedirs('%s/%s' % (d, s), exist_ok=True)
    conf = d + '/conf'
    shutil.copytree(TREE + '/conf', conf)
    y = yaml.safe_load(open(conf + '/cassandra.yaml'))
    y.update({'cluster_name': 's4od', 'num_tokens': 1, 'listen_address': ADDR, 'rpc_address': ADDR,
              'seed_provider': [{'class_name': 'org.apache.cassandra.locator.SimpleSeedProvider', 'parameters': [{'seeds': '%s:%d' % (ADDR, STORAGE)}]}],
              'storage_port': STORAGE, 'native_transport_port': NATIVE, 'sasi_indexes_enabled': True, 'auto_snapshot': False,
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

def java_pid(p):
    # the node is started through bash exec: p.pid is the java pid
    return p.pid

STRINGS = ["Rejecting value (size", "Can't add term", "Flushed index segment", "Rejecting value (value size", "OutOfMemoryError"]
def count_since(path, off):
    with open(path, 'rb') as f:
        f.seek(off); txt = f.read().decode('utf8', 'replace')
    return {k: txt.count(k) for k in STRINGS}
def si_files(d):
    out = []
    for f in glob.glob(d + '/data/ks/t-*/*SI_*.db'):
        out.append((os.path.basename(f), os.path.getsize(f)))
    return sorted(out)
def data_files(d):
    return sorted((os.path.basename(f), os.path.getsize(f)) for f in glob.glob(d + '/data/ks/t-*/*-Data.db'))
def histo(pid, tag):
    r = sh('jcmd %d GC.class_histogram' % pid, timeout=300, quiet=True)
    open('%s/histogram-%s.txt' % (outdir, tag), 'w').write(r.stdout)
    keep = [l.strip() for l in r.stdout.splitlines() if re.search(r'OnDiskIndexBuilder|DynamicTokenTreeBuilder|Total', l)]
    log('histogram', tag, keep)
    return keep

summary = dict(label=label, size=size, rows=rows, cap=cap, host=os.uname().nodename)
try:
    log('run', label, 'size', size, 'rows', rows, 'cap', cap, 'host', os.uname().nodename)
    for port in (JMX, NATIVE, STORAGE):
        if sh('ss -ltn | grep -q ":%d "' % port).returncode == 0:
            raise RuntimeError('port %d busy' % port)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    sh('mkdir -p %s/sampler && javac -d %s/sampler %s/HeapSampler.java' % (WORK, WORK, HARN), check=True)
    d, p = start()
    if not wait_binary(p):
        raise RuntimeError('node did not start')
    log('node up'); time.sleep(5)
    slog = d + '/logs/system.log'
    cmdline = open('/proc/%d/cmdline' % p.pid, 'rb').read().replace(b'\0', b' ').decode()
    open(outdir + '/node-cmdline.txt', 'w').write(cmdline + '\n')
    summary['xmx'] = re.findall(r'-Xmx\S+', cmdline); summary['xms'] = re.findall(r'-Xms\S+', cmdline)
    smp = subprocess.Popen(['java', '-cp', WORK + '/sampler', 'HeapSampler', str(JMX), outdir + '/heap.csv', '500'],
                           stdout=open(outdir + '/sampler.out', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    pids['sampler'] = smp.pid
    time.sleep(5)
    # phase 0: load
    off0 = os.path.getsize(slog)
    summary['t_load_start'] = now_ms()
    r = sh('python3 %s/loader.py %s %s %d %d %d %s' % (HARN, TREE, ADDR, NATIVE, size, rows, cap), timeout=3600, check=True)
    summary['t_load_end'] = now_ms()
    summary['load_out'] = [l for l in r.stdout.splitlines() if l.startswith('loaded') or l.startswith('index')]
    summary['log_load'] = count_since(slog, off0)
    summary['si_after_load'] = si_files(d); summary['data_after_load'] = data_files(d)
    summary['histo_pre_flush'] = histo(p.pid, 'pre-flush')
    # phase 1: flush
    off1 = os.path.getsize(slog)
    summary['t_flush_start'] = now_ms()
    nt('flush ks t')
    time.sleep(10)   # async index flush tasks log after the nodetool call returns
    summary['t_flush_end'] = now_ms()
    summary['log_flush'] = count_since(slog, off1)
    summary['si_after_flush'] = si_files(d); summary['data_after_flush'] = data_files(d)
    summary['log_load_plus_flush'] = count_since(slog, off0)
    summary['histo_post_flush'] = histo(p.pid, 'post-flush')
    nt('tablestats ks.t | head -40')
    # phase 2: compaction (MAJOR_COMPACTION is not FLUSH, so PerSSTableIndexWriter.maxMemorySize uses the index option)
    off2 = os.path.getsize(slog)
    summary['t_compact_start'] = now_ms()
    nt('compact ks t', 1800)
    time.sleep(10)
    summary['t_compact_end'] = now_ms()
    summary['log_compact'] = count_since(slog, off2)
    summary['si_after_compact'] = si_files(d); summary['data_after_compact'] = data_files(d)
    summary['histo_post_compact'] = histo(p.pid, 'post-compact')
    for f in ['system.log', 'debug.log']:
        if os.path.exists(d + '/logs/' + f):
            # keep only the SASI lines and errors, not 400k rejection lines
            sh("grep -v -e \"Rejecting value (size\" -e \"Can't add term\" %s/logs/%s > %s/%s.filtered" % (d, f, outdir, f), quiet=True)
    sh('df -h %s | tail -1' % WORK)
except Exception as ex:
    log('ERROR', repr(ex)); summary['error'] = repr(ex)
finally:
    json.dump(summary, open(outdir + '/summary.json', 'w'), indent=1)
    stop_all()
    pids.clear()
    time.sleep(1)
    shutil.rmtree(WORK, ignore_errors=True)
    log('done', json.dumps({k: v for k, v in summary.items() if not k.startswith('histo')}))
