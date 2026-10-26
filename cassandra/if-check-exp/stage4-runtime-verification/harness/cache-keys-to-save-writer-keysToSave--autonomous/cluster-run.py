#!/usr/bin/env python3
"""Stage 4, cluster tier (B3) of cache-keys-to-save-writer-keysToSave--autonomous (case file as amended 2026-10-26).
usage: cluster-run.py main | ctl20 | yaml10k | down | clean
  main    fresh tmpfs dir; node with key_cache_size 200MiB, key_cache_save_period 1h, row/counter cache 0; autocompaction off; stress write n=2000000;
          nodetool flush; uniform read passes (n=500000 each) until the key cache holds >= 700000 entries (spec: >= 300000), max 5 passes;
          then K sweep 10000, 100000, 0, 2147483647 (default) set through JMX (CacheService MBean, attribute KeyCacheKeysToSave), each followed by the JMX
          operation saveCaches; per save: Saved KeyCache log line, KeyCache-g.db/.crc/.metadata sizes, Entries/Size gauges before and after,
          heap used (JMX, 100 ms) peak. Node stopped at the end; the data directory is kept for the next arms.
  ctl20   same data, key_cache_size 20MiB: node start, saved_caches wiped, read passes until entries stop growing (max 5), K sweep 10000, 0.
  yaml10k same data, key_cache_size 200MiB, yaml key_cache_keys_to_save: 10000 and key_cache_save_period: 60s: JMX read-back of KeyCacheKeysToSave
          (startup wiring), read passes to >= 700000 entries, wait for the periodic (startup-captured K) save, then a manual saveCaches.
  down    stop this harness's node (by PID).  clean  remove /dev/shm/s4-b7-ck.
Port slot 5: 127.0.5.1 storage 7000 / native 9042, JMX 7150. Output ~/s4-b7-ck-logs/<CK_RUN>/cluster/<arm>/ (summary.txt with EXPECTED lines, session.log,
results.json, system.log excerpt, heap-<K>.csv). Exit 1 on a failed set-up or first-trigger check; the node is stopped on any exit.
Environment: CK_MIN, CK_TARGET, CK_RUN (default run1), CASSANDRA_HOME (default ~/s4-b7-ck-n), CK_WRITE_N / CK_READ_N (shakedown overrides only)."""
import json, os, re, signal, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b7-ck-n')
HARNESS = os.path.dirname(os.path.abspath(__file__))
CK = '/dev/shm/s4-b7-ck'
RUN = os.environ.get('CK_RUN', 'run1')
ADDR = '127.0.5.1'
JMXPORT = 7150
WRITE_N = int(os.environ.get('CK_WRITE_N', '2000000'))
READ_N = int(os.environ.get('CK_READ_N', '500000'))
TARGET_ENTRIES = int(os.environ.get('CK_TARGET', '700000'))
MIN_ENTRIES = int(os.environ.get('CK_MIN', '300000'))
MAXK = 2147483647
CACHES = 'org.apache.cassandra.db:type=Caches'
MET = 'org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name='
args = sys.argv[1:]
if len(args) != 1 or args[0] not in ('main', 'ctl20', 'yaml10k', 'down', 'clean'):
    sys.exit(__doc__)
arm = args[0]
LOGS = f'{HOME}/s4-b7-ck-logs/{RUN}/cluster/{arm}'
os.makedirs(LOGS, exist_ok=True)
SESSION = open(LOGS + '/session.log', 'a')
SUMMARY = open(LOGS + '/summary.txt', 'a' if arm in ('down', 'clean') else 'w')
RES = {'arm': arm}


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=900, check=True, env=None, cwd=C, quiet=False):
    if not quiet:
        log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = r.stdout + r.stderr
    if not quiet:
        SESSION.write(out[-2500:] + '\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed ({r.returncode}): {cmd}\n{out[-1500:]}')
    return r.returncode, out


def pid_of():
    try:
        pid = int(open(CK + '/cassandra.pid').read().strip()); os.kill(pid, 0); return pid
    except (ValueError, OSError):
        return None


def stop_node():
    pid = pid_of()
    if pid is None:
        return
    sh(f'{C}/bin/nodetool -p {JMXPORT} drain', check=False, timeout=300, quiet=True)
    subprocess.run(['kill', str(pid)])
    for _ in range(120):
        if pid_of() is None:
            return
        time.sleep(1)
    log(f'node did not stop; kill -9 {pid}'); subprocess.run(['kill', '-9', str(pid)]); time.sleep(2)


def fail(msg):
    note('FAIL: ' + msg); json.dump(RES, open(LOGS + '/results.json', 'w'), indent=1)
    stop_node(); sys.exit(1)


CLS = HOME + '/s4-b7-ck-logs/jmxcls'


def jget(*pairs):
    _, out = sh(f'java -cp {CLS} Jmx {JMXPORT} get ' + ' '.join(f"'{b}' {a}" for b, a in pairs), check=False, quiet=True, timeout=120)
    d = {}
    for l in out.splitlines():
        p = l.rsplit('|', 2)
        if len(p) == 3: d[(p[0], p[1])] = p[2]
    return [d.get((b, a)) for b, a in pairs]


def gauges():
    e, s, c = jget((MET + 'Entries', 'Value'), (MET + 'Size', 'Value'), (MET + 'Capacity', 'Value'))
    return {'entries': int(e), 'size': int(s), 'capacity': int(c)}


def saved_files():
    d = CK + '/saved_caches'; r = {}
    for f in sorted(os.listdir(d)):
        if f.startswith('KeyCache'): r[f] = os.path.getsize(os.path.join(d, f))
    return r


def saved_lines():
    p = CK + '/logs/system.log'
    out = []
    if os.path.exists(p):
        for l in open(p, errors='replace'):
            m = re.search(r'Saved KeyCache \((\d+) items\) in (\d+) ms to (\S+) : (\d+) MB', l)
            if m: out.append({'n': int(m.group(1)), 'ms': int(m.group(2)), 'line': l.strip()[:300]})
    return out


def heap_sampler(path, stop):
    with open(path, 'w') as f:
        f.write('ms,heap_used\n')
        p = subprocess.Popen(f'java -cp {CLS} Jmx {JMXPORT} poll 100 100000 {stop} java.lang:type=Memory HeapMemoryUsage',
                             shell=True, stdout=f, stderr=subprocess.DEVNULL)
        p.wait()


def do_save(label, k, want_new_lines=1):
    """set K through JMX, read it back, save through JMX, wait for the log line; returns the reading dict."""
    r = {'label': label, 'K': k}
    if k is not None:
        _, o = sh(f"java -cp {CLS} Jmx {JMXPORT} set {CACHES} KeyCacheKeysToSave {k}", quiet=True)
        r['set_output'] = o.strip()
    r['K_readback'] = jget((CACHES, 'KeyCacheKeysToSave'))[0]
    r['before'] = gauges(); r['files_before'] = saved_files(); n0 = len(saved_lines())
    stop = f'{LOGS}/stop.heap'
    if os.path.exists(stop): os.remove(stop)
    hp = f'{LOGS}/heap-{label}.csv'
    th = threading.Thread(target=heap_sampler, args=(hp, stop), daemon=True); th.start(); time.sleep(1.5)
    t0 = time.time()
    sh(f"java -cp {CLS} Jmx {JMXPORT} invoke {CACHES} saveCaches", quiet=True, timeout=600)
    r['save_seconds'] = round(time.time() - t0, 2)
    for _ in range(60):
        ls = saved_lines()
        if len(ls) > n0: break
        time.sleep(0.5)
    time.sleep(1.5); open(stop, 'w').close(); th.join(timeout=10)
    ls = saved_lines()
    r['new_lines'] = ls[n0:]
    r['n_logged'] = ls[-1]['n'] if len(ls) > n0 else None
    r['files_after'] = saved_files(); r['after'] = gauges()
    peak = 0
    for l in open(hp).read().splitlines()[1:]:
        try: peak = max(peak, int(l.split(',')[1]))
        except (IndexError, ValueError): pass
    r['heap_peak_during_save'] = peak
    note(f"SAVE {label} K={k} readback={r['K_readback']} n_logged={r['n_logged']} data_file={r['files_after'].get('KeyCache-g.db')} entries {r['before']['entries']}->{r['after']['entries']} size {r['before']['size']}->{r['after']['size']} heap_peak={peak} save_s={r['save_seconds']}")
    RES.setdefault('saves', []).append(r)
    return r


def start_node(yaml):
    if pid_of() is not None:
        fail('a node of this harness is already running')
    busy = sh('ss -ltn', quiet=True)[1]
    for w in (f'{ADDR}:7000', f'{ADDR}:9042', f'127.0.0.1:{JMXPORT}'):
        if re.search(r'\s' + re.escape(w) + r'\s', busy): fail(f'port {w} is busy')
    os.makedirs(CLS, exist_ok=True)
    sh(f'javac -d {CLS} {HARNESS}/Jmx.java', cwd=HOME)
    _, y = sh(f'bash {HARNESS}/make-node-yaml.sh ' + ' '.join(f"'{a}'" for a in yaml), env=dict(os.environ, CASSANDRA_HOME=C, CK=CK))
    note(y.strip().splitlines()[-1][:600])
    shutil_rm(CK + '/saved_caches'); os.makedirs(CK + '/saved_caches')
    shutil_rm(CK + '/logs'); os.makedirs(CK + '/logs')
    env = dict(os.environ, CASSANDRA_CONF=CK + '/conf', CASSANDRA_LOG_DIR=CK + '/logs', MAX_HEAP_SIZE='2G')
    env.pop('HEAP_NEWSIZE', None)
    t0 = time.time()
    sh(f"bash -c 'ulimit -n 100000 && exec bin/cassandra -p {CK}/cassandra.pid' > {CK}/stdout.txt 2>&1", env=env)
    while time.time() - t0 < 300:
        time.sleep(3)
        if pid_of() is None: fail('node died during start; see ' + CK + '/stdout.txt')
        rc, st = sh(f'bin/nodetool -p {JMXPORT} status', check=False, quiet=True, timeout=60)
        rc2, sb = sh(f'bin/nodetool -p {JMXPORT} statusbinary', check=False, quiet=True, timeout=60)
        if rc == 0 and re.search(r'^UN ', st, re.M) and sb.strip() == 'running': break
    else:
        fail('node not serving after 300 s')
    note(f'node up after {time.time()-t0:.0f} s, pid {pid_of()}')
    jvm = sh(f'tr "\\0" " " < /proc/{pid_of()}/cmdline', quiet=True, cwd=HOME)[1]
    RES['jvm_xmx'] = re.findall(r'-Xmx\S+', jvm)
    note('JVM heap flags: ' + ' '.join(RES['jvm_xmx']))


def shutil_rm(p):
    sh(f'rm -rf {p}', quiet=True, cwd=HOME)


def stress(cmd, label):
    t0 = time.time()
    rc, out = sh(f"bash -c 'ulimit -n 100000 && tools/bin/cassandra-stress {cmd} -node {ADDR}' > {LOGS}/stress-{label}.log 2>&1", check=False, timeout=7200)
    txt = open(f'{LOGS}/stress-{label}.log', errors='replace').read()
    m = re.search(r'Total errors\s*:\s*(\d+)', txt)
    return {'rc': rc, 'seconds': round(time.time() - t0, 1), 'errors': int(m.group(1)) if m else None,
            'partitions': (re.search(r'Total partitions\s*:\s*([\d,]+)', txt) or [None, None])[1]}


def populate(target, maxpass=5):
    hist = []
    for i in range(maxpass):
        before = gauges()['entries']
        s = stress(f'read n={READ_N} -pop dist=UNIFORM\\(1..{WRITE_N}\\) -rate threads=50', f'read{i+1}')
        g = gauges()
        hist.append({'pass': i + 1, 'entries_before': before, 'entries_after': g['entries'], 'size': g['size'], 'stress': s})
        note(f"read pass {i+1}: entries {before} -> {g['entries']} size {g['size']} capacity {g['capacity']} errors {s['errors']} {s['seconds']}s")
        if s['rc'] != 0 or s['errors'] != 0: fail('stress read pass failed')
        if g['entries'] >= target: break
        if g['entries'] <= before * 1.02 and i > 0: break
    RES['populate'] = hist
    return gauges()


def main_arm():
    sh(f'rm -rf {CK}', quiet=True, cwd=HOME)
    start_node(['key_cache_size=200MiB', 'key_cache_save_period=1h'])
    g = gauges(); note(f'gauges at start: {g}')
    if g['capacity'] != 200 * 1024 * 1024: fail('key cache capacity is not 200 MiB: ' + str(g))
    note('K at start (JMX KeyCacheKeysToSave): ' + str(jget((CACHES, 'KeyCacheKeysToSave'))))
    sh(f'bin/nodetool -p {JMXPORT} disableautocompaction')
    s = stress(f'write n={WRITE_N} -rate threads=50', 'write')
    RES['write'] = s; note(f'write: {s}')
    if s['rc'] != 0 or s['errors'] != 0: fail('stress write failed')
    sh(f'bin/nodetool -p {JMXPORT} flush', timeout=900)
    sh(f'bin/nodetool -p {JMXPORT} info | grep -i "key cache"', check=False)
    g = populate(TARGET_ENTRIES)
    # first-trigger check: the cache must hold more entries than the largest K tested
    if g['entries'] < MIN_ENTRIES: fail(f"limit not reached: entries {g['entries']} < {MIN_ENTRIES}")
    note(f"limit reached: entries {g['entries']} >= {MIN_ENTRIES}")
    RES['info_after_populate'] = sh(f'bin/nodetool -p {JMXPORT} info | grep -i "key cache"', check=False)[1].strip()
    for k in (10000, 100000, 0, MAXK):
        do_save(f'K{k}', k)
    stop_node(); fin()


def ctl_arm():
    start_node(['key_cache_size=20MiB', 'key_cache_save_period=1h'])
    g = gauges(); note(f'gauges at start: {g}')
    if g['capacity'] != 20 * 1024 * 1024: fail('key cache capacity is not 20 MiB: ' + str(g))
    sh(f'bin/nodetool -p {JMXPORT} disableautocompaction')
    g = populate(10 ** 9, maxpass=4)
    if g['entries'] < 20000: fail('control arm: entries below 20000 (limit not reached)')
    for k in (10000, 0):
        do_save(f'K{k}', k)
    stop_node(); fin()


def yaml_arm():
    start_node(['key_cache_size=200MiB', 'key_cache_keys_to_save=10000', 'key_cache_save_period=60s'])
    rb = jget((CACHES, 'KeyCacheKeysToSave'))[0]
    RES['yaml_readback'] = rb; note(f'EXPECTED yaml key_cache_keys_to_save: 10000 read back through JMX at startup: {rb}')
    if rb != '10000': fail('yaml value not read back')
    sh(f'bin/nodetool -p {JMXPORT} disableautocompaction')
    g = populate(TARGET_ENTRIES)
    # periodic save (period 60 s, K captured at startup): wait for a Saved line after the last read pass
    n0 = len(saved_lines()); t0 = time.time()
    while time.time() - t0 < 150 and len(saved_lines()) <= n0: time.sleep(2)
    ls = saved_lines()
    RES['periodic'] = {'lines_total': len(ls), 'new': ls[n0:], 'files': saved_files(), 'gauges': gauges()}
    note(f"periodic save after populate: {ls[n0:] if len(ls) > n0 else 'NONE seen in 150 s'}; files {saved_files()}")
    do_save('manual', None)
    stop_node(); fin()


def fin():
    # keep a small excerpt of the node's log for the repo
    sh(f"grep -E 'Saved KeyCache|Initializing key cache|ERROR|WARN' {CK}/logs/system.log | head -60 > {LOGS}/system.log.excerpt", check=False, quiet=True)
    sh(f"cp {CK}/logs/system.log {LOGS}/system.log.full", check=False, quiet=True)
    RES['leftover'] = sh("ps -eo pid,args | awk '$2 ~ /java$/ && /s4-b7-ck/' | cut -c1-120", check=False, quiet=True)[1].strip()
    json.dump(RES, open(LOGS + '/results.json', 'w'), indent=1)
    note(f"{arm} finished; leftover java processes of this harness: [{RES['leftover']}]")


if arm == 'down':
    stop_node(); print('node pid alive:', pid_of()); sys.exit(0)
if arm == 'clean':
    stop_node(); sh(f'rm -rf {CK}', cwd=HOME); sys.exit(0)
note(f'cluster-run {arm} {time.strftime("%F %T %Z")} host {os.uname().nodename.split(".")[0]} tree {C} {sh("git describe --tags", quiet=True)[1].strip()} write_n={WRITE_N} read_n={READ_N}')
try:
    {'main': main_arm, 'ctl20': ctl_arm, 'yaml10k': yaml_arm}[arm]()
except SystemExit:
    raise
except Exception as e:
    note(f'EXCEPTION {e!r}'); fail('unexpected exception')
