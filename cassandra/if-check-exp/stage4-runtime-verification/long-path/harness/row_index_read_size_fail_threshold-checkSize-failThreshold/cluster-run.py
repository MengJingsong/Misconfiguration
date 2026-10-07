#!/usr/bin/env python3
"""Stage 4, cluster tier, row_index_read_size_fail_threshold-checkSize-failThreshold (case 9b-9e).
usage: cluster-run.py <label>   label: 16m (first: calibration) | 16k | 64k | 256k | s64k | s16m | none
  16m/16k/64k/256k: column_index_cache_size 4 MiB (entries built on heap); s64k/s16m: the stock 2 KiB; none: both limits unset.
One node (~/cassandra-run1), restarted per value, RF 1. Logs every command to ~/stage4-logs/rirs/<label>/session.log, writes
summary.txt (EXPECTED lines) and readings.csv. Exit 1: an instrument/set-up check failed; the node is stopped on any exit.
The bypass arms C1, C2 and C3 run on the 64k start."""
import csv, json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
VALUES = {'16m': (16777216, False), '16k': (16384, False), '64k': (65536, False), '256k': (262144, False),
          's64k': (65536, True), 's16m': (16777216, True), 'none': (None, False)}
LADDER = [100, 141, 200, 283, 400, 566, 800, 1131, 1600, 2263, 3200]
PAYLOAD = 1200
KS1_ENTRIES = set(LADDER) | {10, 2263}
label = sys.argv[1]
F, STOCK = VALUES[label]
D = f'{HOME}/stage4-logs/rirs/{label}'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
RCSV = csv.writer(open(D + '/readings.csv', 'w'))
RCSV.writerow(['label', 'arm', 'pk', 'B', 'outcome', 'est', 'entries', 'bytes', 'command', 'cache_entries_before', 'cache_entries_after',
               'cache_size_before', 'cache_size_after', 'rowindexsize_count_delta', 'aborts_delta', 'codes'])
CALIB = f'{HOME}/stage4-logs/rirs/calibration.json'
TRACE = D + '/checksize.trace'
SYSLOG = C + '/logs/system.log'
KC = 'org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name='
TM = 'org.apache.cassandra.metrics:type=Table,keyspace=ks1,scope=%s,name=%s'
SS = 'org.apache.cassandra.db:type=StorageService'


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=300, check=True, env=None, cwd=C):
    log('+ ' + (cmd if isinstance(cmd, str) else ' '.join(cmd)))
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
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
    note('FAIL: ' + msg); stop_node(); sys.exit(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def jmx_get(*pairs):
    args = [x for p in pairs for x in p]
    _, out = sh(['java', '-cp', D + '/jmx-classes', 'Jmx', 'get', *args], check=False)
    vals = {}
    for l in out.splitlines():
        parts = l.split('|')
        if len(parts) == 3:
            vals[(parts[0], parts[1])] = parts[2]
    return vals


def jmx_set(bean, attr, value):
    rc, out = sh(['java', '-cp', D + '/jmx-classes', 'Jmx', 'set', bean, attr, value], check=False)
    return rc == 0


def snap(table='t'):
    v = jmx_get((KC + 'Entries', 'Value'), (KC + 'Size', 'Value'), (TM % (table, 'RowIndexSize'), 'Count'), (TM % (table, 'RowIndexSizeAborts'), 'Count'))
    g = lambda k: int(float(v.get(k, 'nan'))) if v.get(k) not in (None, 'NaN') else None
    return dict(entries=g((KC + 'Entries', 'Value')), size=g((KC + 'Size', 'Value')), count=g((TM % (table, 'RowIndexSize'), 'Count')),
                aborts=g((TM % (table, 'RowIndexSizeAborts'), 'Count')))


def client(*args):
    r = subprocess.run([sys.executable, f'{HARNESS}/send-read.py', *args], capture_output=True, text=True, timeout=900)
    log('+ send-read.py ' + ' '.join(args)[:200]); SESSION.write(r.stderr[-500:] + '\n'); SESSION.flush()
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {'ok': False, 'error': 'ClientFailure', 'message': (r.stdout + r.stderr)[-400:]}


trace_seen = 0
def new_trace():
    global trace_seen
    time.sleep(0.5)
    if not os.path.exists(TRACE):
        return []
    lines = open(TRACE).read().splitlines()
    new = lines[trace_seen:]; trace_seen = len(lines)
    out = []
    for l in new:
        m = re.search(r'entries=(\d+) bytes=(\d+) command=(\S+)', l)
        if m:
            out.append((int(m.group(1)), int(m.group(2)), m.group(3)))
    return out


def abort_lines():
    try:
        return [l for l in open(SYSLOG, errors='replace') if 'in RowIndexEntry and aborted the query' in l]
    except FileNotFoundError:
        return []


def invalidate():
    sh('bin/nodetool invalidatekeycache')


def read(arm, cql, pk=None, B=None, table='t', fresh=True):
    if fresh:
        invalidate()
        client('probe')   # the client's connection reads system tables and caches their entries; do it before the snapshot
    new_trace()           # discard lines written so far (system-table reads of earlier connections)
    before = snap(table); lb = len(abort_lines())
    r = client('read', cql)
    time.sleep(0.4)
    after = snap(table); al = abort_lines()
    est = None
    if r.get('ok'):
        for w in r.get('warnings', []):
            m = re.search(r'loaded over (\d+) bytes in RowIndexEntry', w)
            if m: est = int(m.group(1))
    elif len(al) > lb:
        m = re.search(r'loaded over (\d+) bytes', al[-1]); est = int(m.group(1)) if m else None
    tr = new_trace()
    res = dict(arm=arm, ok=bool(r.get('ok')), rows=r.get('rows'), est=est, trace=tr, before=before, after=after, codes=r.get('codes'), raw=r)
    cmdline = tr[-1] if tr else (None, None, None)
    RCSV.writerow([label, arm, pk, B, 'OK' if res['ok'] else 'ERR:' + str(r.get('error')), est, cmdline[0], cmdline[1], [t[2] for t in tr],
                   before['entries'], after['entries'], before['size'], after['size'],
                   (after['count'] or 0) - (before['count'] or 0), (after['aborts'] or 0) - (before['aborts'] or 0), r.get('codes')])
    note(f'READ {arm}: {"OK" if res["ok"] else "ERR " + str(r.get("error"))} rows={res["rows"]} est={est} checksize={tr} '
         f'cache entries {before["entries"]}->{after["entries"]} size {before["size"]}->{after["size"]} '
         f'RowIndexSize count {before["count"]}->{after["count"]} aborts {before["aborts"]}->{after["aborts"]} codes={r.get("codes")}')
    return res


def main():
    if daemon_up():
        fail('a CassandraDaemon is already running')
    sh('git checkout -q conf/cassandra.yaml', check=False)
    note(sh(f'{HARNESS}/make-node-yaml.sh {label} {F if F else "none"} {"stock-cache" if STOCK else ""}')[1].strip())
    sh('rm -rf data logs saved_caches')
    sh(f'rm -rf {D}/jmx-classes && mkdir -p {D}/jmx-classes && javac -d {D}/jmx-classes {HARNESS}/Jmx.java')
    if os.path.exists(TRACE):
        os.remove(TRACE)
    env = dict(os.environ, MAX_HEAP_SIZE='4G',
               JVM_EXTRA_OPTS=f'-javaagent:{C}/build/lib/jars/byteman-4.0.20.jar=script:{HARNESS}/checksize.btm,listener:true -Dstage4.byteman.out={TRACE}')
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
       'compaction = {\'class\': \'SizeTieredCompactionStrategy\', \'enabled\': \'false\'}; '
       'CREATE TABLE ks1.t2 (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {\'enabled\': false} AND '
       'compaction = {\'class\': \'SizeTieredCompactionStrategy\', \'enabled\': \'false\'} AND caching = {\'keys\': \'NONE\'};"')

    # ---- instrument check
    p = client('probe')
    if not p.get('ok') or p.get('protocol') != 5:
        fail(f'probe failed or protocol is not 5: {p}')
    note(f'INSTRUMENT probe: release {p["release_version"]} protocol {p["protocol"]}')
    s0 = snap()
    if None in s0.values():
        fail(f'a JMX reading is missing: {s0}')
    note(f'INSTRUMENT jmx: key cache entries {s0["entries"]} size {s0["size"]}, RowIndexSize count {s0["count"]}, aborts {s0["aborts"]}')
    cur = jmx_get((SS, 'RowIndexReadSizeAbortThreshold')).get((SS, 'RowIndexReadSizeAbortThreshold'))
    setter_ok = False
    if cur is not None:
        setter_ok = jmx_set(SS, 'RowIndexReadSizeAbortThreshold', cur if cur not in ('null', 'None') else '') if cur not in ('null', 'None') else False
    note(f'INSTRUMENT jmx setter: current RowIndexReadSizeAbortThreshold={cur!r}; set-to-same ok={setter_ok} (needed for arm C1 only)')
    sysl = new_trace()
    if [t for t in sysl if t[2].startswith('ks1.')]:
        fail('a checksize line with a ks1 command was written before any read of a ks1 table')
    note(f'INSTRUMENT byteman: {len(sysl)} checksize line(s) from system tables so far, none with a ks1 command (the rule fires for every deserialization)')

    # ---- load, flush
    ld = client('load-ladder', 'ks1.t', ','.join(map(str, LADDER)), str(PAYLOAD))
    if not ld.get('ok'):
        fail(f'load failed: {ld}')
    sh('bin/nodetool flush ks1 t')
    _, ls = sh('ls data/data/ks1/t-*/*-Data.db')
    nfiles = len(ls.split())
    note(f'DATASET rows loaded {ld["loaded"]} (expected {sum(LADDER)}), Data.db files {nfiles}')
    if nfiles != 1 or ld['loaded'] != sum(LADDER):
        fail('dataset check failed')
    invalidate(); new_trace()
    time.sleep(10)
    idle = [t for t in new_trace() if t[2].startswith('ks1.') or t[0] in KS1_ENTRIES]
    if idle:
        fail(f'idle control: a ks1 checksize line appeared with no reads: {idle}')
    note('INSTRUMENT idle control: no ks1 checksize line in 10 s (lines from system tables are ignored)')

    # ---- ladder
    o = json.load(open(CALIB))['o'] if (label != '16m' and os.path.exists(CALIB)) else None
    results = []
    for k, B in enumerate(LADDER, start=1):
        r = read(f'ladder pk{k}', f'SELECT ck FROM ks1.t WHERE pk = {k} LIMIT 1', pk=k, B=B)
        results.append(r)
    ests = {}
    if label == '16m':
        os_ = []
        for r, B in zip(results, LADDER):
            tr = [t for t in r['trace'] if t[2] == 'ks1.t']
            if not (tr and r['est']):
                fail(f'calibration: no checksize line with a command, or no estimate, for B={B}')
            entries, nbytes, _ = tr[-1]
            os_.append((r['est'] - nbytes) / entries)
            ests[B] = r['est']
        expect('o = (estimate - bytes)/entries is the same for every partition', len(set(os_)) == 1)
        expect('all 11 partitions accepted at 16 MiB', all(r['ok'] for r in results))
        o = os_[0]
        json.dump({'o': o, 'est': {str(B): ests[B] for B in LADDER}}, open(CALIB, 'w'))
        note(f'CALIBRATION o={o} est={ests}')
    else:
        for r, B in zip(results, LADDER):
            tr = [t for t in r['trace'] if t[2] == 'ks1.t']
            if tr:
                ests[B] = int(o * tr[-1][0] + tr[-1][1])
        expect('checksize lines present for every read', len(ests) == len(LADDER))
        if F is None:
            expect('default (limits unset): every read accepted, RowIndexSize count unchanged, no checksize line with a command',
                   all(r['ok'] for r in results) and all(r['after']['count'] == r['before']['count'] for r in results) and
                   all(not [t for t in r['trace'] if t[2] == 'ks1.t'] for r in results))
        else:
            for r, B in zip(results, LADDER):
                expect(f'B={B}: accepted iff est({ests.get(B)}) <= F({F})', r['ok'] == (ests.get(B, 10**12) <= F))
            for r, B in zip(results, LADDER):
                if not r['ok']:
                    expect(f'B={B}: refusal evidence (code 4, aborts +1, no cache entry added)',
                           list((r['codes'] or {}).values()) == [4] and r['after']['aborts'] == r['before']['aborts'] + 1 and r['after']['entries'] == r['before']['entries'])
            acc = [(ests[B], r) for r, B in zip(results, LADDER) if r['ok']]
            if acc:
                big = max(acc, key=lambda x: x[0])
                note(f'LARGEST ACCEPTED est={big[0]} (F={F}; ladder step 1.41: expect F/1.42 < est <= F: {F / 1.42 < big[0] <= F})')
            if label in ('s64k', 's16m'):
                ws = [r['after']['size'] - r['before']['size'] for r, B in zip(results, LADDER) if r['ok'] and (o and 0 < 1)]
                note(f'SHALLOW weights added by accepted partitions: {ws}')

    # ---- bypass arms on the 64k start
    if label == '64k':
        acceptable = [(ests[B], k + 1, B) for k, B in enumerate(LADDER) if results[k]['ok']]
        e_big, pk_big, B_big = max(acceptable)
        note(f'C1 partition: pk{pk_big} B={B_big} est={e_big}')
        r1 = read('C1 first (cache cold)', f'SELECT ck FROM ks1.t WHERE pk = {pk_big} LIMIT 1', pk=pk_big, B=B_big)
        if setter_ok:
            jmx_set(SS, 'RowIndexReadSizeAbortThreshold', f'{e_big - 1}B')
            note('C1 limit lowered to est-1 over JMX: ' + str(jmx_get((SS, 'RowIndexReadSizeAbortThreshold'))))
            r2 = read('C1 second (cache hit, limit below est)', f'SELECT ck FROM ks1.t WHERE pk = {pk_big} LIMIT 1', pk=pk_big, B=B_big, fresh=False)
            expect('C1: the cached read completes, adds no cache entry, writes no checksize line, RowIndexSize count unchanged',
                   r2['ok'] and r2['after']['entries'] == r2['before']['entries'] and r2['after']['count'] == r2['before']['count']
                   and not [t for t in r2['trace'] if t[2] == 'ks1.t' or t[0] == B_big])   # system-table lines (a client connection scans them) are ignored
            r3 = read('C1 third (cache invalidated, limit below est)', f'SELECT ck FROM ks1.t WHERE pk = {pk_big} LIMIT 1', pk=pk_big, B=B_big)
            expect('C1: after invalidation the same read is refused', (not r3['ok']) and list((r3['codes'] or {}).values()) == [4])
            jmx_set(SS, 'RowIndexReadSizeAbortThreshold', f'{F}B')
        else:
            note('C1 not run: the JMX setter did not work')
        # C2: SSTable opened late
        client('load-rows', 'ks1.t2', '1', '0', '10', str(PAYLOAD)); sh('bin/nodetool flush ks1 t2')
        client('load-rows', 'ks1.t2', '1', '1000', '3263', str(PAYLOAD)); sh('bin/nodetool flush ks1 t2')
        _, ls2 = sh('ls data/data/ks1/t2-*/*-Data.db')
        note(f'C2 Data.db files {len(ls2.split())}')
        up = read('C2 ck>=1000', 'SELECT ck FROM ks1.t2 WHERE pk = 1 AND ck >= 1000 LIMIT 1', table='t2', fresh=False)
        asc = read('C2 full ascending', 'SELECT ck FROM ks1.t2 WHERE pk = 1', table='t2', fresh=False)
        desc = read('C2 full descending', 'SELECT ck FROM ks1.t2 WHERE pk = 1 ORDER BY ck DESC', table='t2', fresh=False)
        expect('C2: ck>=1000 refused', not up['ok'])
        expect('C2: full ascending completes with 2273 rows', asc['ok'] and asc['rows'] == 2273)
        late = [t for t in asc['trace'] if t[0] == 2263]
        expect('C2: the 2263-block entry was seen with command=null and the 10-block entry with command=ks1.t2',
               bool(late) and late[0][2] == 'null' and any(t[0] == 10 and t[2] == 'ks1.t2' for t in asc['trace']))
        expect('C2: full descending refused', not desc['ok'])
        # C3: scan
        if setter_ok:
            jmx_set(SS, 'RowIndexReadSizeAbortThreshold', '16384B')
        sc = read('C3 scan', 'SELECT ck FROM ks1.t', fresh=False)
        expect('C3: the scan completes', sc['ok'])
        expect('C3: every checksize line of the scan has command=null', bool(sc['trace']) and all(t[2] == 'null' for t in sc['trace']))
        if setter_ok:
            jmx_set(SS, 'RowIndexReadSizeAbortThreshold', f'{F}B')

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
