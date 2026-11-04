#!/usr/bin/env python3
"""Stage 4, cluster tier, local_read_size_fail_threshold-addSize-failBytes (case 9b-9e).
usage: cluster-run.py <label>        label: 16m (first: calibration) | 256k | 1m | 4m | none
One node (~/cassandra-run1), restarted per value, RF 1. Logs every command to ~/stage4-logs/lrs/<label>/session.log, writes
summary.txt (EXPECTED lines) and readings.csv. Exit 1: an instrument/set-up check failed; the node is stopped on any exit."""
import csv, glob, json, math, os, re, subprocess, sys, time, shutil

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
VALUES = {'16m': 16777216, '256k': 262144, '1m': 1048576, '4m': 4194304, 'none': None}
N, PAYLOAD, M_NAMES = 8000, 1000, 2000
label = sys.argv[1]
F = VALUES[label]
D = f'{HOME}/stage4-logs/lrs/{label}'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
RCSV = csv.writer(open(D + '/readings.csv', 'w'))
RCSV.writerow(['label', 'arm', 'cql', 'outcome', 'rows', 'X', 'aborts_before', 'aborts_after', 'alloc_bytes', 'codes'])
CALIB = f'{HOME}/stage4-logs/lrs/calibration.json'
ALLOC = D + '/alloc.trace'
SYSLOG = C + '/logs/system.log'
METER = 'org.apache.cassandra.metrics:type=Table,keyspace=ks1,scope=t,name=LocalReadSizeAborts'


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=300, check=True, env=None, cwd=C):
    log('+ ' + (cmd if isinstance(cmd, str) else ' '.join(cmd)))
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    SESSION.write(out[-4000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-800:]}')
    return r.returncode, out


def daemon_up():
    return subprocess.run("pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon'", shell=True, capture_output=True).returncode == 0


def stop_node():
    if daemon_up():
        sh('bin/nodetool stopdaemon', check=False)
        for _ in range(90):
            if not daemon_up():
                break
            time.sleep(1)
        if daemon_up():
            subprocess.run("pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon'", shell=True)
            time.sleep(2)
    if daemon_up():
        log('WARNING: a CassandraDaemon is still running')
    sh('git checkout -q conf/cassandra.yaml', check=False)


def fail(msg):
    note('FAIL: ' + msg)
    stop_node()
    sys.exit(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def jmx(bean, attr):
    _, out = sh(f'{HARNESS}/jmx.sh {bean} {attr}', check=False)
    m = re.findall(r'-?\d+', out.strip().splitlines()[-1] if out.strip() else '')
    return int(m[-1]) if m else None


def client(*args):
    r = subprocess.run([sys.executable, f'{HARNESS}/send-read.py', *args], capture_output=True, text=True, timeout=300)
    log('+ send-read.py ' + ' '.join(args)[:200]); SESSION.write(r.stderr[-600:] + '\n'); SESSION.flush()
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {'ok': False, 'error': 'ClientFailure', 'message': (r.stdout + r.stderr)[-400:]}


alloc_seen = 0
def new_alloc():
    global alloc_seen
    time.sleep(0.6)
    if not os.path.exists(ALLOC):
        return []
    lines = open(ALLOC).read().splitlines()
    new = lines[alloc_seen:]
    alloc_seen = len(lines)
    return [int(re.search(r'bytes=(-?\d+)', l).group(1)) for l in new if 'read-alloc' in l]


def abort_lines():
    try:
        return [l for l in open(SYSLOG, errors='replace') if 'aborted the query' in l and 'local_read_size_fail_threshold' in l]
    except FileNotFoundError:
        return []


def read(arm, cql, fetch=None, trace=False):
    before = jmx(METER, 'Count'); logs_before = len(abort_lines())
    args = ['read'] + (['--fetch-size', str(fetch)] if fetch else []) + (['--trace'] if trace else []) + [cql]
    r = client(*args)
    time.sleep(0.4)
    after = jmx(METER, 'Count'); al = abort_lines()
    X = None
    if r.get('ok'):
        for w in r.get('warnings', []):
            m = re.search(r'loaded over (\d+) bytes', w)
            if m:
                X = int(m.group(1))
    elif len(al) > logs_before:
        m = re.search(r'loaded over (\d+) bytes', al[-1]); X = int(m.group(1)) if m else None
    a = new_alloc()
    res = dict(arm=arm, ok=bool(r.get('ok')), rows=r.get('rows'), X=X, before=before, after=after, alloc=a, codes=r.get('codes'), raw=r)
    RCSV.writerow([label, arm, cql[:120], 'OK' if res['ok'] else 'ERR:' + str(r.get('error')), res['rows'], X, before, after, a, r.get('codes')])
    note(f'READ {arm}: {"OK" if res["ok"] else "ERR " + str(r.get("error"))} rows={res["rows"]} X={X} meter {before}->{after} alloc={a} codes={r.get("codes")}')
    return res


def main():
    # ---- config, reset, start
    if daemon_up():
        fail('a CassandraDaemon is already running')
    sh('git checkout -q conf/cassandra.yaml', check=False)
    note(sh(f'{HARNESS}/make-node-yaml.sh {label} {F if F else "none"}')[1].strip())
    sh('rm -rf data logs saved_caches')
    # the node runs from build/apache-cassandra-*.jar, so the helper goes on the boot class path as a small jar
    sh(f'rm -rf {D}/alloc-classes && mkdir -p {D}/alloc-classes && javac -d {D}/alloc-classes {HARNESS}/Alloc.java && jar cf {D}/stage4-alloc.jar -C {D}/alloc-classes .')
    env = dict(os.environ, MAX_HEAP_SIZE='4G',
               JVM_EXTRA_OPTS=f'-javaagent:{C}/build/lib/jars/byteman-4.0.20.jar=script:{HARNESS}/read-alloc.btm,listener:true -Xbootclasspath/a:{D}/stage4-alloc.jar -Dstage4.byteman.out={ALLOC}')
    if os.path.exists(ALLOC):
        os.remove(ALLOC)
    sh(f'bin/cassandra -p {D}/cassandra.pid > {D}/startup.log 2>&1', env=env)
    for _ in range(120):
        _, st = sh('bin/nodetool statusbinary', check=False)
        _, ns = sh('bin/nodetool status', check=False)
        if 'running' in st and re.search(r'^UN', ns, re.M):
            break
        time.sleep(2)
    else:
        fail('node did not come up')
    note('node up')
    sh('bin/cqlsh -e "CREATE KEYSPACE ks1 WITH replication = {\'class\': \'SimpleStrategy\', \'replication_factor\': 1}; '
       'CREATE TABLE ks1.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {\'enabled\': false} AND '
       'compaction = {\'class\': \'SizeTieredCompactionStrategy\', \'enabled\': \'false\'};"')

    # ---- instrument check
    p = client('probe')
    if not p.get('ok') or p.get('protocol') != 5:
        fail(f'probe failed or protocol is not 5: {p}')
    note(f'INSTRUMENT probe: release {p["release_version"]} protocol {p["protocol"]}')
    if jmx(METER, 'Count') is None:
        fail('cannot read the LocalReadSizeAborts meter over JMX')
    note('INSTRUMENT jmx: meter readable')
    if new_alloc():
        fail('a read-alloc line was written before any ks1 read (the probe read system.local)')
    note('INSTRUMENT alloc: the probe (a system read) wrote no read-alloc line')

    # ---- load, flush
    ld = client('load', str(N), str(PAYLOAD))
    if not ld.get('ok'):
        fail(f'load failed: {ld}')
    sh('bin/nodetool flush ks1 t')
    _, ls = sh('ls data/data/ks1/t-*/*-Data.db')
    nfiles = len(ls.split())
    note(f'DATASET rows loaded {ld["loaded"]}, Data.db files {nfiles}')
    if nfiles != 1:
        fail('expected one Data.db file')
    if os.path.exists(ALLOC) and open(ALLOC).read().strip():
        note('note: alloc lines exist before the first read (schema or load reads)')
    new_alloc()
    time.sleep(10)
    if new_alloc():
        fail('idle control: a read-alloc line appeared with no reads')
    note('INSTRUMENT idle control: no read-alloc line in 10 s')

    # ---- calibration
    sel = 'SELECT * FROM ks1.t WHERE pk = 1'
    if label == 'none':
        cal = json.load(open(CALIB))
    else:
        r100 = read('calib c100', sel + ' AND ck < 100'); r200 = read('calib c200', sel + ' AND ck < 200')
        if not (r100['ok'] and r200['ok'] and r100['X'] and r200['X']):
            fail('calibration reads did not complete with a warn total')
        h = (r200['X'] - r100['X']) / 100
        b0 = r100['X'] - 100 * h
        cal = dict(b0=b0, h=h, T100=r100['X'], T200=r200['X'])
        if label == '16m':
            rf = read('calib full', sel)
            if not (rf['ok'] and rf['rows'] == N and rf['X']):
                fail('calibration full read did not return all rows with a total')
            cal['TN'] = rf['X']
            expect('T(N) = b0 + N*h', abs(cal['TN'] - (b0 + N * h)) < 1)
            expect('T(N) below 16 MiB (the run is invalid otherwise)', cal['TN'] < 16777216)
            json.dump(cal, open(CALIB, 'w'))
        else:
            ref = json.load(open(CALIB))
            expect('calibration equals the 16m run (b0, h)', abs(ref['b0'] - b0) < 1 and abs(ref['h'] - h) < 1e-9)
    b0, h = cal['b0'], cal['h']
    T = lambda i: int(round(b0 + i * h))
    note(f'CALIBRATION b0={b0} h={h} T(N)={T(N)}')

    if F is not None and F <= T(N) and label != '16m':
        istar = math.ceil((F - b0) / h); pstar = istar - 1
        note(f'PREDICTION F={F}: i*={istar} p*={pstar} X_abort={T(istar)} X_A={T(pstar)}')
        A = read('A ck<p*', sel + f' AND ck < {pstar}')
        expect('A completes with X = T(p*) < F', A['ok'] and A['X'] == T(pstar) and T(pstar) < F)
        B1 = read('B1 ck<p*+1', sel + f' AND ck < {istar}')
        expect('B1 aborts with X = T(i*) >= F, code 4, meter +1', (not B1['ok']) and B1['X'] == T(istar) and T(istar) >= F and B1['after'] == B1['before'] + 1 and list((B1['codes'] or {}).values()) == [4])
        B2 = read('B2 whole partition', sel)
        expect('B2 aborts with the same X as B1', (not B2['ok']) and B2['X'] == T(istar))
        if B1['alloc'] and B2['alloc']:
            expect('alloc(B2) within 10% of alloc(B1)', abs(B2['alloc'][0] - B1['alloc'][0]) / B1['alloc'][0] < 0.10)
    else:
        B2 = read('B2 whole partition', sel)
        expect('whole partition completes with all rows', B2['ok'] and B2['rows'] == N)

    # ---- scenario C
    names = ','.join(str(i) for i in range(M_NAMES))
    c1n = read('C1 names IN', sel + f' AND ck IN ({names})')
    c1s = read('C1 slice ck<2000', sel + f' AND ck < {M_NAMES}')
    c2a = read('C2 fetch 100', sel, fetch=100)
    c2b = read('C2 fetch 1000', sel, fetch=1000)
    c3 = read('C3 filter', sel + ' AND v = 0xdeadbeefdeadbeef ALLOW FILTERING')
    if F is None or F > T(N):
        ok_all = all(x['ok'] for x in (c1n, c1s, c2a, c2b, c3))
        expect('every arm completes when the limit is above the data or unset', ok_all)
        expect('fetch 100 delivers all rows', c2a['rows'] == N); expect('filter returns 0 rows', c3['rows'] == 0)
    else:
        expect('C1 names aborts iff T(M) >= F', (not c1n['ok']) == (T(M_NAMES) >= F))
        expect('C1 slice aborts iff T(M) >= F', (not c1s['ok']) == (T(M_NAMES) >= F))
        expect('C2 fetch 100 completes iff T(100) < F and delivers all rows', c2a['ok'] == (T(100) < F) and (not c2a['ok'] or c2a['rows'] == N))
        expect('C2 fetch 1000 aborts iff T(1000) >= F', (not c2b['ok']) == (T(1000) >= F))
        expect('C3 filter aborts iff T(N) >= F', (not c3['ok']) == (T(N) >= F))
        if c1n['alloc'] and c1s['alloc'] and (not c1n['ok']):
            note(f'INFO C1 names alloc {c1n["alloc"][0]} slice alloc {c1s["alloc"][0]}')

    note('DONE')
    stop_node()
    sh(f'cp {SYSLOG} {D}/system.log', check=False)


try:
    main()
except SystemExit:
    raise
except Exception as e:
    note(f'FAIL (exception): {e!r}')
    stop_node()
    sys.exit(1)
