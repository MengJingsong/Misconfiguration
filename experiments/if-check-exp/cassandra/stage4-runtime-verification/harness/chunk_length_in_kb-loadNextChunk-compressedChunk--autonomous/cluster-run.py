#!/usr/bin/env python3
"""Cluster tier, one run (B3 as amended B3i).
Usage: cluster-run.py <label> <chunk_kb> <ratio:0|1.1> <mode:normal|entire|cap> <outdir> [rows=256] [rowbytes=1048576]
Needs: ~/s4-ci/node-tree (built, never used by ant), ~/s4-ci/harness (this folder). Two nodes on 127.0.12.1 (A) and 127.0.12.2 (B).
Everything is logged to <outdir>/session.log; nodes and sampler are stopped on any exit."""
import os, sys, time, subprocess, shutil, signal, json, yaml, glob, re, atexit

label, chunk_kb, ratio, mode, outdir = sys.argv[1:6]
rows = int(sys.argv[6]) if len(sys.argv) > 6 else 256
rowbytes = int(sys.argv[7]) if len(sys.argv) > 7 else 1 << 20
HOME = os.path.expanduser('~')
TREE = HOME + '/s4-ci/node-tree'
HARN = HOME + '/s4-ci/harness'
WORK = '/dev/shm/s4-ci/' + label
PORTS = dict(storage=7012, native=9112, jmxA=7212, jmxB=7213)
ADDR = dict(A='127.0.12.1', B='127.0.12.2')
os.makedirs(outdir, exist_ok=True)
LOG = open(outdir + '/session.log', 'a')
pids = {}
def log(*a):
    s = '[%s] %s' % (time.strftime('%FT%T', time.gmtime()) + '.%03dZ' % (int(time.time() * 1000) % 1000), ' '.join(str(x) for x in a))
    LOG.write(s + '\n'); LOG.flush(); print(s, flush=True)
def sh(cmd, timeout=600, env=None, check=False):
    log('+', cmd)
    r = subprocess.run(['bash', '-c', cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    if r.stdout.strip():
        LOG.write(r.stdout[-4000:] + '\n'); LOG.flush()
    if check and r.returncode:
        raise RuntimeError('command failed rc=%d: %s' % (r.returncode, cmd))
    return r
def alive(pid):
    try:
        return b'java' in open('/proc/%d/cmdline' % pid, 'rb').read() or True
    except Exception:
        return False
def stop_all():
    for name, p in list(pids.items()):
        try:
            os.kill(p, signal.SIGTERM)
        except Exception:
            pass
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

def mkconf(node):
    d = '%s/%s' % (WORK, node)
    for s in ['data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw', 'logs']:
        os.makedirs('%s/%s' % (d, s), exist_ok=True)
    conf = d + '/conf'
    shutil.copytree(TREE + '/conf', conf)
    y = yaml.safe_load(open(conf + '/cassandra.yaml'))
    tokA, tokB = ('-4611686018427387904', '4611686018427387904') if mode != 'entire' else ('-9223372036854775000', '9223372036854775000')
    y.update({'cluster_name': 's4ci', 'num_tokens': 1, 'initial_token': tokA if node == 'A' else tokB,
              'listen_address': ADDR[node], 'rpc_address': ADDR[node],
              'seed_provider': [{'class_name': 'org.apache.cassandra.locator.SimpleSeedProvider', 'parameters': [{'seeds': '%s:%d' % (ADDR['A'], PORTS['storage'])}]}],
              'storage_port': PORTS['storage'], 'native_transport_port': PORTS['native'],
              'data_file_directories': [d + '/data'], 'commitlog_directory': d + '/commitlog', 'hints_directory': d + '/hints',
              'saved_caches_directory': d + '/saved_caches', 'cdc_raw_directory': d + '/cdc_raw',
              'stream_entire_sstables': (mode == 'entire'), 'auto_bootstrap': (node == 'B')})
    yaml.safe_dump(y, open(conf + '/cassandra.yaml', 'w'), default_flow_style=False)
    env = open(conf + '/cassandra-env.sh').read()
    env = env.replace('JMX_PORT="7199"', 'JMX_PORT="%d"' % PORTS['jmx' + node])
    open(conf + '/cassandra-env.sh', 'w').write(env)
    return d, conf

def start(node):
    d, conf = mkconf(node)
    e = dict(os.environ)
    e.update(CASSANDRA_HOME=TREE, CASSANDRA_CONF=conf, CASSANDRA_LOG_DIR=d + '/logs', MAX_HEAP_SIZE='2G',
             JVM_EXTRA_OPTS='-Dcassandra.ring_delay_ms=5000 -Duser.timezone=UTC')
    if node == 'B' and mode == 'cap':
        e['MAX_DIRECT_MEMORY_SIZE'] = '100m'
    cmd = 'ulimit -n 100000; exec %s/bin/cassandra -f -p %s/pid' % (TREE, d)
    log('start', node, 'env MAX_DIRECT_MEMORY_SIZE=%s' % e.get('MAX_DIRECT_MEMORY_SIZE'), cmd)
    p = subprocess.Popen(['bash', '-c', cmd], env=e, stdout=open(d + '/stdout.log', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    pids[node] = p.pid
    return d, p

def nt(node, args, timeout=300):
    return sh('%s/bin/nodetool -h 127.0.0.1 -p %d %s' % (TREE, PORTS['jmx' + node], args), timeout=timeout)

def wait_binary(node, p, tmax=240):
    t0 = time.time()
    while time.time() - t0 < tmax:
        if p.poll() is not None:
            log('node', node, 'died during start rc', p.returncode); return False
        r = nt(node, 'statusbinary', 60)
        if 'running' in r.stdout and 'not running' not in r.stdout:
            return True
        time.sleep(3)
    return False

summary = dict(label=label, chunk_kb=chunk_kb, ratio=ratio, mode=mode, rows=rows, rowbytes=rowbytes)
try:
    log('run', label, 'chunk_kb', chunk_kb, 'ratio', ratio, 'mode', mode, 'host', os.uname().nodename)
    for port in PORTS.values():
        if sh('ss -ltn | grep -q ":%d "' % port).returncode == 0:
            raise RuntimeError('port %d busy' % port)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    sh('mkdir -p %s/sampler && javac -d %s/sampler %s/PoolSampler.java' % (WORK, WORK, HARN), check=True)
    dA, pA = start('A')
    if not wait_binary('A', pA):
        raise RuntimeError('A did not start')
    log('A up')
    r = sh('python3 %s/loader.py %s %s %d %s %s %d %d' % (HARN, TREE, ADDR['A'], PORTS['native'], chunk_kb, ratio, rows, rowbytes), timeout=900, check=True)
    nt('A', 'flush ks t'); nt('A', 'compact ks t', 900)
    ss = sorted(glob.glob(dA + '/data/ks/t-*/*-Data.db'))
    summary['A_sstables'] = [(os.path.basename(f), os.path.getsize(f)) for f in ss]
    log('A sstables', summary['A_sstables'])
    nt('A', 'tablestats ks.t | head -30')
    # sampler on B, then start B
    smp = subprocess.Popen(['java', '-cp', WORK + '/sampler', 'PoolSampler', str(PORTS['jmxB']), outdir + '/samples.csv', '20'],
                           stdout=open(outdir + '/sampler.out', 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    pids['sampler'] = smp.pid
    t_start_B = int(time.time() * 1000)
    dB, pB = start('B')
    summary['t_start_B_ms'] = t_start_B
    outcome = None
    t0 = time.time()
    tmax = 900 if mode != 'cap' else 300
    blog = dB + '/logs/system.log'
    while time.time() - t0 < tmax:
        if pB.poll() is not None:
            outcome = 'B_died_rc_%s' % pB.returncode; break
        txt = open(blog, errors='replace').read() if os.path.exists(blog) else ''
        if mode == 'cap' and re.search(r'java\.lang\.OutOfMemoryError|Direct buffer memory|Bootstrap failed|Stream failed|Error while waiting on bootstrap', txt):
            outcome = 'B_stream_failed'; time.sleep(10); break
        r = nt('B', 'statusbinary', 60)
        if 'running' in r.stdout and 'not running' not in r.stdout:
            outcome = 'B_UN_binary_running'; break
        time.sleep(3)
    if outcome is None:
        outcome = 'timeout'
    log('B outcome', outcome)
    summary['B_outcome'] = outcome
    time.sleep(6)
    nt('B', 'tablestats ks.t | head -30')
    sh('du -sb %s/data/ks 2>&1 | tail -1' % dB)
    summary['B_data_bytes'] = sum(os.path.getsize(f) for f in glob.glob(dB + '/data/ks/t-*/*-Data.db'))
    summary['B_cmdline'] = open('/proc/%d/cmdline' % pB.pid, 'rb').read().replace(b'\0', b' ').decode() if os.path.exists('/proc/%d' % pB.pid) else ''
    open(outdir + '/B-cmdline.txt', 'w').write(summary['B_cmdline'] + '\n')
    for f in ['system.log', 'debug.log']:
        shutil.copy(dB + '/logs/' + f, outdir + '/B-' + f) if os.path.exists(dB + '/logs/' + f) else None
    shutil.copy(dB + '/stdout.log', outdir + '/B-stdout.log')
    shutil.copy(dA + '/logs/system.log', outdir + '/A-system.log') if os.path.exists(dA + '/logs/system.log') else None
except Exception as ex:
    log('ERROR', repr(ex)); summary['error'] = repr(ex)
finally:
    json.dump(summary, open(outdir + '/summary.json', 'w'), indent=1)
    stop_all()
    pids.clear()
    shutil.rmtree(WORK, ignore_errors=True)
    log('done', json.dumps(summary))
