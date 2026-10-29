#!/usr/bin/env python3
"""Cluster tier (B3) of the two NAME_LENGTH cases; the same file serves both (--case ks | tbl), see the harness README.
usage on the run node:  cluster-run.py --case ks|tbl [--tag run1] [--n N] [--rows R] [--ctl-rows R] <arms|control|analyze|all>
Arms (B5 items 3-4): A1 B1 A2 B2 = short / long / short / long name length, fresh node each; control (B5 item 5): C64 then C256.
Everything is logged: <logdir>/cmd.log has each command and its output; each arm writes <label>.json; analyze writes summary.txt with
EXPECTED lines. Resumable: a label whose json exists is skipped. A node started here is stopped on any exit (finally) and checked."""
import argparse, glob, json, os, re, shutil, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/s4-b2/base')
HARNESS = os.path.dirname(os.path.abspath(__file__))
CASES = {
    'ks':  dict(stem='schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous', n=200, rows=10000, short=3, long=48, heap='2G',
                ctl_ks='kc3', reject=('try-ks', 49), reject_text='Keyspace name must not be more than 48 characters long', limit=48,
                budget=200 * 45 * 50),
    'tbl': dict(stem='table_name_length-validatetablename-name_length--autonomous', n=500, rows=1000, short=8, long=222, heap='1G',
                ctl_ks='kc', reject=('try-tbl', 223), reject_text='Table name must not be more than 222 characters long', limit=222,
                budget=500 * 214 * 20),
}
ap = argparse.ArgumentParser()
ap.add_argument('--case', required=True, choices=CASES)
ap.add_argument('--tag', default='run1')
ap.add_argument('--n', type=int)
ap.add_argument('--rows', type=int)
ap.add_argument('--ctl-rows', type=int, default=3000000)
ap.add_argument('--settle', type=int, default=60)
ap.add_argument('cmd', choices=['arms', 'control', 'analyze', 'all'])
A = ap.parse_args()
P = CASES[A.case]
N = A.n or P['n']
ROWS = A.rows or P['rows']
LOG = '%s/s4-b2/logs/%s/%s/cluster' % (HOME, P['stem'], A.tag)
RUN = '%s/s4-b2/run/%s' % (HOME, A.case)
os.makedirs(LOG, exist_ok=True)
CMDLOG = open(LOG + '/cmd.log', 'a')
JMXDIR = HOME + '/s4-b2/jmx'
PIDS = []


def say(s):
    line = '%s %s' % (time.strftime('%H:%M:%S'), s)
    print(line, flush=True)
    CMDLOG.write(line + '\n')
    CMDLOG.flush()


def sh(cmd, env=None, timeout=3600, check=False):
    say('$ ' + cmd)
    e = dict(os.environ)
    e['CASSANDRA_HOME'] = C
    if env:
        e.update(env)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=e, timeout=timeout, stdin=subprocess.DEVNULL)
    out = (r.stdout + r.stderr).strip()
    CMDLOG.write(out[-3000:] + '\n')
    CMDLOG.flush()
    if check and r.returncode:
        raise RuntimeError('failed: %s\n%s' % (cmd, out[-500:]))
    return r.returncode, r.stdout, r.stderr


def daemons():
    return subprocess.run("ps -eo pid,cmd | grep '[C]assandraDaemon'", shell=True, capture_output=True, text=True).stdout.strip()


def compile_jmx():
    if not os.path.exists(JMXDIR + '/Jmx.class'):
        os.makedirs(JMXDIR, exist_ok=True)
        sh('javac -d %s %s/Jmx.java' % (JMXDIR, HARNESS), check=True)


def start_node(label, extra):
    d = '%s/%s' % (RUN, label)
    shutil.rmtree(d, ignore_errors=True)
    sh('%s/make-node.sh %s %s' % (HARNESS, d, ' '.join(extra)), check=True)
    if daemons():
        raise RuntimeError('a CassandraDaemon is already running: ' + daemons())
    env = {'CASSANDRA_CONF': d + '/conf', 'CASSANDRA_LOG_DIR': d + '/logs', 'MAX_HEAP_SIZE': P['heap'] if 'ctl' not in label else P['heap']}
    sh('cd %s && bin/cassandra -p %s/pid > %s/stdout 2>&1' % (C, d, d), env=env, check=True)
    t0 = time.time()
    while time.time() - t0 < 240:
        time.sleep(4)
        if not os.path.exists(d + '/pid'):
            continue
        pid = int(open(d + '/pid').read())
        if not os.path.exists('/proc/%d' % pid):
            raise RuntimeError('daemon died during start; see %s/logs/system.log' % d)
        rc, out, _ = sh('%s/bin/nodetool statusbinary' % C)
        if out.strip() == 'running':
            PIDS.append(pid)
            say('node %s up, pid %d, %.0f s' % (label, pid, time.time() - t0))
            return d, pid
    raise RuntimeError('node did not start in 240 s')


def stop_node(d, pid):
    if os.path.exists('/proc/%d' % pid):
        os.kill(pid, 15)
        for _ in range(60):
            if not os.path.exists('/proc/%d' % pid):
                break
            time.sleep(2)
        else:
            os.kill(pid, 9)
            time.sleep(3)
    say('node pid %d stopped; daemons left: [%s]' % (pid, daemons()))


def client(*args):
    rc, out, err = sh('python3 %s/client.py %s' % (HARNESS, ' '.join(str(a) for a in args)), timeout=7200)
    j = json.loads(out.strip().splitlines()[-1]) if out.strip() else {'ok': False, 'error': err[-300:]}
    if rc not in (0,) and not j.get('rejected'):
        say('CLIENT ERROR rc=%d %s' % (rc, err[-300:]))
    return j


def tree_bytes(path):
    t = 0
    for r, ds, fs in os.walk(path):
        for f in fs:
            try:
                t += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return t


def jmx_used():
    rc, out, _ = sh('java -cp %s Jmx 7199 get java.lang:type=Memory HeapMemoryUsage' % JMXDIR)
    m = re.search(r'\|(\d+)\s*$', out.strip().splitlines()[-1]) if out.strip() else None
    return int(m.group(1)) if m else None


def histo_total(pid, path):
    sh('jcmd %d GC.class_histogram > %s' % (pid, path))
    tot = None
    for l in open(path):
        m = re.match(r'^Total\s+(\d+)\s+(\d+)', l)
        if m:
            tot = int(m.group(2))
    return tot


def arm(label, L):
    if os.path.exists('%s/%s.json' % (LOG, label)):
        say('skip %s (done)' % label)
        return
    say('=== arm %s: name length %d, %d x %d rows ===' % (label, L, N, ROWS))
    d, pid = start_node(label, [])
    res = {'label': label, 'L': L, 'N': N, 'rows': ROWS, 'pid': pid, 't_start': time.time()}
    try:
        kind = A.case
        res['probe'] = client('probe')
        res['ddl'] = client('ddl', kind, L, N)
        k = 4                                    # four client processes in parallel, each every 4th target (one Python client does ~5000 rows/s)
        procs = [subprocess.Popen('python3 %s/client.py write %s %d %d %d 128 %d %d > %s/%s.arm-writer%d.out 2> %s/%s.arm-writer%d.err' % (HARNESS, kind, L, N, ROWS, i, k, LOG, label, i, LOG, label, i), shell=True) for i in range(k)]
        say('arm writers: %d processes' % k)
        for p_ in procs:
            p_.wait()
        ws = [json.loads(open('%s/%s.arm-writer%d.out' % (LOG, label, i)).read().strip().splitlines()[-1]) for i in range(k)]
        res['write'] = {'ok': all(w['ok'] for w in ws), 'succeeded': sum(w['succeeded'] for w in ws), 'failed': sum(w['failed'] for w in ws),
                        'rows_per_s': sum(w['rows_per_s'] for w in ws), 'writers': ws}
        sh('%s/bin/nodetool flush' % C, timeout=1800)
        t0 = time.time()
        while time.time() - t0 < 1200:
            rc, out, _ = sh('%s/bin/nodetool compactionstats' % C)
            if re.search(r'pending tasks\s*:?\s*0\b', out) and not re.search(r'^id\s', out, re.M):
                break
            time.sleep(10)
        say('settle %d s' % A.settle)
        time.sleep(A.settle)
        sh('jcmd %d GC.run' % pid)
        res['heap_used_after_gc'] = jmx_used()
        res['histo_total_bytes'] = histo_total(pid, '%s/%s.histo.txt' % (LOG, label))
        rc, out, _ = sh('%s/bin/nodetool info' % C)
        res['nodetool_info_heap'] = [l for l in out.splitlines() if 'Heap Memory' in l]
        res['rss_kb'] = int(re.search(r'VmRSS:\s+(\d+)', open('/proc/%d/status' % pid).read()).group(1))
        res['du_data'] = tree_bytes(d + '/data')
        res['du_commitlog'] = tree_bytes(d + '/commitlog')
        res['commitlog_files'] = len(os.listdir(d + '/commitlog'))
        names = []
        for ks in os.listdir(d + '/data'):
            names.append(ks)
            for t in os.listdir(os.path.join(d, 'data', ks)):
                names.append(t)
        res['longest_dir_name'] = max(len(x) for x in names)
        res['dir_count'] = len(names)
        res['data_ks_dirs'] = len(os.listdir(d + '/data'))
        if L == P['long']:
            kind_try, tl = P['reject']
            if kind_try == 'try-ks':
                res['reject'] = client('try-ks', 'k' * tl)
            else:
                res['reject'] = client('try-tbl', 'ks', 'a' * tl)
            res['reject_len'] = tl
        res['t_end'] = time.time()
        sh('grep -c "^ERROR" %s/logs/system.log' % d)
        res['log_errors'] = int(subprocess.run('grep -c "^ERROR" %s/logs/system.log' % d, shell=True, capture_output=True, text=True).stdout.strip() or 0)
        res['log_oom'] = int(subprocess.run('cat %s/logs/system.log %s/stdout | grep -c "java.lang.OutOfMemoryError"' % (d, d), shell=True, capture_output=True, text=True).stdout.strip() or 0)
    finally:
        stop_node(d, pid)
    json.dump(res, open('%s/%s.json' % (LOG, label), 'w'), indent=1)
    say('arm %s done: %s' % (label, {k: res[k] for k in ('heap_used_after_gc', 'histo_total_bytes', 'du_data', 'longest_dir_name')}))


def control(label, space):
    if os.path.exists('%s/%s.json' % (LOG, label)):
        say('skip %s (done)' % label)
        return
    say('=== control %s: memtable_heap_space %s, %d rows ===' % (label, space, A.ctl_rows))
    d, pid = start_node(label, ['memtable_heap_space=' + space])
    stop = d + '/stop-sampler'
    res = {'label': label, 'memtable_heap_space': space, 'rows': A.ctl_rows, 'pid': pid}
    smp = None
    try:
        sh('grep -c "Enqueuing flush of" %s/logs/system.log || true' % d)
        smp = subprocess.Popen('java -cp %s Jmx 7199 poll 1000 100000 %s "org.apache.cassandra.metrics:type=Table,name=AllMemtablesHeapSize" Value '
                               'java.lang:type=Memory HeapMemoryUsage > %s/%s.samples.csv 2>> %s/%s.samples.err' % (JMXDIR, stop, LOG, label, LOG, label),
                               shell=True)
        time.sleep(3)
        client('one', P['ctl_ks'], 1, 1)          # creates the keyspace and table once
        k = 3                                    # three client processes in parallel (one Python client does ~5000 rows/s), disjoint id ranges
        per = A.ctl_rows // k
        procs = [subprocess.Popen('python3 %s/client.py one %s %d 128 %d > %s/%s.writer%d.json 2> %s/%s.writer%d.err' % (HARNESS, P['ctl_ks'], per, i * per, LOG, label, i, LOG, label, i), shell=True) for i in range(k)]
        say('control writers: %d processes x %d rows' % (k, per))
        for p_ in procs:
            p_.wait()
        ws = [json.loads(open('%s/%s.writer%d.json' % (LOG, label, i)).read().strip().splitlines()[-1]) for i in range(k)]
        res['write'] = {'ok': all(w['ok'] for w in ws), 'succeeded': sum(w['succeeded'] for w in ws), 'failed': sum(w['failed'] for w in ws), 'writers': ws}
        time.sleep(5)
        open(stop, 'w').close()
        smp.wait(timeout=60)
        peak, peakheap, n = 0, 0, 0
        for l in open('%s/%s.samples.csv' % (LOG, label)):
            f = l.strip().split(',')
            if len(f) == 3 and f[1].isdigit():
                n += 1
                peak = max(peak, int(f[1]))
                peakheap = max(peakheap, int(f[2])) if f[2].isdigit() else peakheap
        res.update(samples=n, peak_all_memtables_heap=peak, peak_heap_used=peakheap)
        res['flushes_enqueued'] = int(subprocess.run('grep -c "Enqueuing flush of" %s/logs/system.log' % d, shell=True, capture_output=True, text=True).stdout.strip() or 0)
        res['log_errors'] = int(subprocess.run('grep -c "^ERROR" %s/logs/system.log' % d, shell=True, capture_output=True, text=True).stdout.strip() or 0)
    finally:
        open(stop, 'w').close()
        if smp and smp.poll() is None:
            smp.kill()
        stop_node(d, pid)
    json.dump(res, open('%s/%s.json' % (LOG, label), 'w'), indent=1)
    say('control %s done: peak_all_memtables_heap=%s flushes=%s' % (label, res['peak_all_memtables_heap'], res['flushes_enqueued']))


def analyze():
    J = {}
    for f in glob.glob(LOG + '/*.json'):
        if '.' not in os.path.basename(f)[:-5]:          # skip <label>.writerN.json
            J[os.path.basename(f)[:-5]] = json.load(open(f))
    out = []
    w = out.append
    w('summary %s %s case %s: N=%d rows=%d short L=%d long L=%d heap %s' % (time.strftime('%F %T'), A.tag, A.case, N, ROWS, P['short'], P['long'], P['heap']))
    for k in sorted(J):
        r = J[k]
        if 'histo_total_bytes' in r:
            w('arm %s L=%d heap_used_after_gc=%s histo_total=%s du_data=%s du_commitlog=%s commitlog_files=%s longest_dir_name=%s dirs=%s rss_kb=%s write_rows_per_s=%s failed=%s ddl_s=%s errors_in_log=%s oom=%s'
              % (k, r['L'], r['heap_used_after_gc'], r['histo_total_bytes'], r['du_data'], r['du_commitlog'], r['commitlog_files'], r['longest_dir_name'],
                 r['dir_count'], r['rss_kb'], r['write'].get('rows_per_s'), r['write'].get('failed'), r['ddl'].get('elapsed_s'), r['log_errors'], r['log_oom']))
            if 'reject' in r:
                w('reject %s len=%d rejected=%s class=%s message=%s' % (k, r['reject_len'], r['reject']['rejected'], r['reject'].get('error_class'), (r['reject'].get('message') or '')[:200]))
        else:
            w('control %s memtable_heap_space=%s rows=%d samples=%s peak_all_memtables_heap=%s peak_heap_used=%s flushes=%s errors_in_log=%s'
              % (k, r['memtable_heap_space'], r['rows'], r['samples'], r['peak_all_memtables_heap'], r['peak_heap_used'], r['flushes_enqueued'], r['log_errors']))
    def mean(lbls, key):
        v = [J[l][key] for l in lbls if l in J and J[l].get(key) is not None]
        return sum(v) / len(v) if v else None
    S, Lg = ['A1', 'A2'], ['B1', 'B2']
    if all(l in J for l in S + Lg):
        for key in ('histo_total_bytes', 'heap_used_after_gc'):
            d = mean(Lg, key) - mean(S, key)
            spread = max(abs(J['A1'][key] - J['A2'][key]), abs(J['B1'][key] - J['B2'][key]))
            w('EXPECTED %s: long-arm mean minus short-arm mean = %+.0f B (name-byte budget %d B, rep spread %d B): %s' % (
                key, d, P['budget'], spread, 'within noise/budget' if abs(d) <= max(P['budget'], spread) else 'EXCEEDS both'))
        dd = mean(Lg, 'du_data') - mean(S, 'du_data')
        w('EXPECTED du_data: long minus short = %+.0f B = %.3f %% of data size: %s' % (dd, 100 * dd / mean(S, 'du_data'), 'within 1 %' if abs(dd) <= 0.01 * mean(S, 'du_data') else 'DIFFERS by more than 1 %'))
    for l in Lg:
        if l in J and 'reject' in J[l]:
            r = J[l]['reject']
            w('EXPECTED %s %d-character name rejected with "%s": %s' % (l, J[l]['reject_len'], P['reject_text'], 'OK' if r['rejected'] and P['reject_text'] in (r.get('message') or '') else 'MISMATCH'))
    if 'C64' in J and 'C256' in J:
        a, b = J['C64'], J['C256']
        w('EXPECTED control B: peak AllMemtablesHeapSize 64MiB=%d 256MiB=%d (ratio %.2f, need <= 0.5); flushes 64MiB=%d 256MiB=%d (need 64 > 256): %s' % (
            a['peak_all_memtables_heap'], b['peak_all_memtables_heap'], a['peak_all_memtables_heap'] / max(1, b['peak_all_memtables_heap']), a['flushes_enqueued'], b['flushes_enqueued'],
            'moves clearly' if a['peak_all_memtables_heap'] <= 0.5 * b['peak_all_memtables_heap'] and a['flushes_enqueued'] > b['flushes_enqueued'] else 'DOES NOT move clearly'))
    out.append('daemons left: [%s]' % daemons())
    open(LOG + '/summary.txt', 'w').write('\n'.join(out) + '\n')
    print('\n'.join(out))


compile_jmx()
try:
    if A.cmd in ('arms', 'all'):
        for lbl, L in (('A1', P['short']), ('B1', P['long']), ('A2', P['short']), ('B2', P['long'])):
            arm(lbl, L)
    if A.cmd in ('control', 'all'):
        control('C64', '64MiB')
        control('C256', '256MiB')
    if A.cmd in ('analyze', 'all'):
        analyze()
finally:
    for pid in PIDS:
        if os.path.exists('/proc/%d' % pid):
            os.kill(pid, 9)
    say('exit; daemons left: [%s]' % daemons())
