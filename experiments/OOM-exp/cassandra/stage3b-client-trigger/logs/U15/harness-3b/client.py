#!/usr/bin/env python3
"""U15 stage-2 client, 3-b confirm version (adds login credentials from CQL_USER/CQL_PASS and the modes setup, probe, victim).
U15 stage-2 client (from R22's client.py; design §2.5). Bundled Python driver, protocol 4, whitelist 127.0.0.1,
FallthroughRetryPolicy (no retries), CL ONE, client request timeout 60 s, token metadata off, prepared statements.
Optional source address (E5): the driver's socket is bound to <src> before connect.
  schema   <port>
  settings <port>                                     resolved settings from system_views.settings (JSON)
  clients  <port>                                     system_views.clients address counts (JSON)
  data     <port> <src> <idx> <rate/s> <max_out> <maxsec> <stopfile> <csv> <resp>
           open loop: slot k at t0 + k/rate; a slot that finds <max_out> outstanding is skipped ('capped').
           INSERT INTO u15.t (pk, ck, v) VALUES (idx*1e9 + seq, 0x01 || seq as 8 bytes, <1,048,576 random bytes, once>).
  poison   <port> <src> <mode delete|cas|once> <bound_bytes> <rate/s> <max_out> <maxsec> <stopfile> <csv> <resp>
           delete: DELETE FROM u15.t WHERE pk = 0 AND ck > <bound_bytes x 0x00>, open loop at <rate>, <= max_out outstanding;
           once:   the same DELETE once at t0, then idle until maxsec/stopfile;
           cas:    INSERT INTO u15.t (pk, ck, v) VALUES (0, <bound_bytes x 0x00>, 0x00) IF NOT EXISTS at <rate>.
  Stream modes stop at <maxsec> or when <stopfile> exists; then drain up to 35 s. Timeouts/errors counted, never retried.
  <csv>: one cumulative row per second: epoch_s,issued,capped,ok,timeouts,errors,outstanding
  <resp>: one row per response: issue_epoch,latency_s,outcome(o=ok,t=timeout,e=error)"""
import glob, json, os, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', '/mydata/s4/u15/cassandra')
LIB = os.path.join(CASS, 'lib')


def find_zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None


cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
    z = find_zip(lib)
    if z:
        sys.path.insert(0, z)

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.auth import PlainTextAuthProvider  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra.query import BatchStatement, BatchType  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402
import cassandra.connection as cconn  # noqa: E402

VAL = 1048576
SRC = None
_orig_init = cconn.Connection._initiate_connection


def _bound_init(self, sockaddr):
    if SRC:
        self._socket.bind((SRC, 0))
    return _orig_init(self, sockaddr)


cconn.Connection._initiate_connection = _bound_init


def connect(port, timeout=60, user=None, pw=None):
    # 3-b confirm: login role from CQL_USER / CQL_PASS (PasswordAuthenticator on); no credentials if unset
    user = user if user is not None else os.environ.get('CQL_USER')
    pw = pw if pw is not None else os.environ.get('CQL_PASS')
    auth = PlainTextAuthProvider(username=user, password=pw) if user else None
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy(['127.0.0.1']))
    c = Cluster(['127.0.0.1'], port=port, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                connect_timeout=30, token_metadata_enabled=False, auth_provider=auth)
    return c, c.connect()


def poll_last(path):
    try:
        with open(path, 'rb') as f:
            hdr = f.readline().decode().split()
            f.seek(0, 2)
            sz = f.tell()
            f.seek(max(0, sz - 8192))
            lines = f.read().decode(errors='replace').splitlines()
        for l in reversed(lines):
            p = l.split()
            if len(p) == len(hdr) and p[0].isdigit():
                return dict(zip(hdr, map(int, p)))
    except Exception:
        pass
    return None


def is_timeout(e):
    return 'imeout' in type(e).__name__ or 'imeout' in str(e)[:100]


class Stream:
    """shared bookkeeping of a stream process"""

    def __init__(self, csvp, respp):
        self.lock = threading.Lock()
        self.st = {'issued': 0, 'capped': 0, 'burst': 0, 'ok': 0, 'timeout': 0, 'err': 0, 'inv': 0, 'outstanding': 0, 'first_err': []}
        self.lat = {'o': [], 't': [], 'e': []}
        self.fcsv = open(csvp, 'w')
        self.fcsv.write('epoch_s,issued,capped_or_burst,ok,timeouts,errors,outstanding\n')
        self.fcsv.flush()
        self.fresp = open(respp, 'w')
        self.fresp.write('issue_epoch,latency_s,outcome\n')
        self.capcol = 'capped'

    def on_ok(self, _, ts):
        now = time.time()
        with self.lock:
            self.st['ok'] += 1
            self.st['outstanding'] -= 1
            self.lat['o'].append(now - ts)
            self.fresp.write('%.3f,%.3f,o\n' % (ts, now - ts))

    def on_err(self, e, ts):
        now = time.time()
        with self.lock:
            self.st['outstanding'] -= 1
            o = 't' if is_timeout(e) else 'e'
            self.st['timeout' if o == 't' else 'err'] += 1
            if o == 'e' and 'Invalid' in type(e).__name__:
                self.st['inv'] += 1
            self.lat[o].append(now - ts)
            self.fresp.write('%.3f,%.3f,%s\n' % (ts, now - ts, o))
            if len(self.st['first_err']) < 3:
                self.st['first_err'].append('%s: %s' % (type(e).__name__, str(e)[:200]))

    def row(self):
        with self.lock:
            s = self.st
            self.fcsv.write('%d,%d,%d,%d,%d,%d,%d\n' % (int(time.time()), s['issued'], s[self.capcol], s['ok'], s['timeout'], s['err'], s['outstanding']))
        self.fcsv.flush()
        self.fresp.flush()

    def send(self, s, ps, a):
        ts = time.time()
        try:
            f = s.execute_async(ps, a)
            f.add_callbacks(callback=self.on_ok, errback=self.on_err, callback_args=(ts,), errback_args=(ts,))
        except Exception as e:
            self.on_err(e, ts)

    def drain(self, last_row):
        t_stop = time.time()
        while time.time() - t_stop < 35:
            with self.lock:
                if self.st['outstanding'] == 0:
                    break
            if int(time.time()) > last_row:
                last_row = int(time.time())
                self.row()
            time.sleep(0.2)
        self.row()
        self.fcsv.close()
        with self.lock:
            self.fresp.close()

    def summary(self, extra, el):
        def q(ls, f):
            return round(ls[min(len(ls) - 1, int(f * len(ls)))] * 1000, 1) if ls else None
        out = dict(extra)
        s = self.st
        out.update({'issued': s['issued'], 'capped': s['capped'], 'burst': s['burst'], 'ok': s['ok'], 'timeouts': s['timeout'],
                    'errors': s['err'], 'invalid_request': s['inv'], 'outstanding_after_drain': s['outstanding'], 'seconds': round(el, 1),
                    'ok_per_s': round(s['ok'] / el, 2) if el else None, 'first_errors': s['first_err']})
        for o, name in (('o', 'ok'), ('t', 'timeout'), ('e', 'error')):
            ls = sorted(self.lat[o])
            out['lat_%s_ms' % name] = {'p50': q(ls, 0.5), 'p99': q(ls, 0.99), 'max': q(ls, 1.0)}
        return out


def main():
    global SRC
    mode, port = sys.argv[1], int(sys.argv[2])
    if mode in ('data', 'poison'):
        SRC = sys.argv[3]
    c, s = connect(port)
    if mode == 'schema':
        s.execute("CREATE KEYSPACE IF NOT EXISTS u15 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        s.execute('CREATE TABLE IF NOT EXISTS u15.t (pk bigint, ck blob, v blob, PRIMARY KEY (pk, ck))')
        print(json.dumps({'schema': 'ok'}))
    elif mode == 'settings':
        names = ['memtable_heap_space', 'memtable_offheap_space', 'memtable_cleanup_threshold', 'memtable_flush_writers',
                 'memtable_allocation_type', 'memtable', 'concurrent_writes', 'max_mutation_size', 'max_value_size',
                 'native_transport_max_request_data_in_flight', 'native_transport_max_request_data_in_flight_per_ip',
                 'write_request_timeout', 'native_transport_timeout', 'native_transport_max_threads',
                 'native_transport_max_frame_size', 'commitlog_segment_size', 'commitlog_total_space',
                 'native_transport_rate_limiting_enabled', 'storage_compatibility_mode', 'disk_failure_policy',
                 'commit_failure_policy', 'column_value_size_warn_threshold', 'column_value_size_fail_threshold',
                 'native_transport_max_concurrent_requests_in_bytes', 'native_transport_max_concurrent_requests_in_bytes_per_ip',
                 'cql_start_time', 'key_cache_size', 'row_cache_size', 'counter_cache_size', 'compaction_throughput',
                 'hinted_handoff_enabled', 'authenticator', 'authorizer', 'role_manager', 'network_authorizer',
                 'roles_validity', 'permissions_validity', 'credentials_validity', 'native_transport_max_requests_per_second',
                 'native_transport_max_concurrent_connections', 'native_transport_max_concurrent_connections_per_ip']
        out = {}
        for r in s.execute('SELECT name, value FROM system_views.settings'):
            if r.name in names:
                out[r.name] = r.value
        r = s.execute("SELECT memtable_flush_period_in_ms, memtable, compaction FROM system_schema.tables WHERE keyspace_name='u15' AND table_name='t'").one()
        out['table_memtable_flush_period_in_ms'] = r.memtable_flush_period_in_ms
        out['table_memtable'] = r.memtable
        out['table_compaction'] = dict(r.compaction)
        print(json.dumps(out, sort_keys=True))
    elif mode == 'clients':
        out = {}
        for r in s.execute('SELECT address, port, username FROM system_views.clients'):
            k = '%s/%s' % (r.address, r.username)
            out[k] = out.get(k, 0) + 1
        print(json.dumps({'clients_by_address': out}, sort_keys=True))
    elif mode == 'setup':
        # 3-b confirm, run as the superuser: admin-made schema, the two login roles and their grants
        apw, vpw = os.environ['ATT_PASS'], os.environ['VIC_PASS']
        stm = ["CREATE KEYSPACE IF NOT EXISTS u15 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}",
               'CREATE TABLE IF NOT EXISTS u15.t (pk bigint, ck blob, v blob, PRIMARY KEY (pk, ck))',
               "CREATE KEYSPACE IF NOT EXISTS vks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}",
               'CREATE TABLE IF NOT EXISTS vks.kv (k int PRIMARY KEY, v blob)',
               "CREATE ROLE attacker WITH PASSWORD = '%s' AND LOGIN = true AND SUPERUSER = false" % apw,
               'GRANT MODIFY ON TABLE u15.t TO attacker',
               "CREATE ROLE victim WITH PASSWORD = '%s' AND LOGIN = true AND SUPERUSER = false" % vpw,
               'GRANT SELECT ON KEYSPACE vks TO victim',
               'GRANT MODIFY ON KEYSPACE vks TO victim']
        for q in stm:
            s.execute(q)
            print(q.replace(apw, '<pw>').replace(vpw, '<pw>'))
        for who in ('attacker', 'victim'):
            print('-- LIST ALL PERMISSIONS OF %s' % who)
            for r in s.execute('LIST ALL PERMISSIONS OF %s' % who):
                print('   role=%s resource=%s permission=%s' % (r.role, r.resource, r.permission))
        print('-- LIST ROLES')
        for r in s.execute('LIST ROLES'):
            print('   %s super=%s login=%s' % (r.role, r.super, r.login))
    elif mode == 'probe':
        # 3-b confirm: what the attacker role can and cannot do (run as attacker; also an unauthenticated connect)
        c.shutdown()
        try:
            c2, s2 = connect(port, user='', pw='')
            print('no-credentials connect: ACCEPTED (unexpected)')
            c2.shutdown()
        except Exception as e:
            print('no-credentials connect: %s: %s' % (type(e).__name__, str(e)[:160]))
        c, s = connect(port)
        tests = [('SELECT u15.t', 'SELECT * FROM u15.t LIMIT 1'),
                 ('SELECT vks.kv', 'SELECT * FROM vks.kv LIMIT 1'),
                 ('INSERT vks.kv', "INSERT INTO vks.kv (k, v) VALUES (-1, 0x00)"),
                 ('CREATE KEYSPACE', "CREATE KEYSPACE ax WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}"),
                 ('CREATE TABLE in u15', 'CREATE TABLE u15.x (k int PRIMARY KEY)'),
                 ('ALTER TABLE u15.t', 'ALTER TABLE u15.t WITH comment = \'x\''),
                 ('INSERT u15.t small row (MODIFY)', "INSERT INTO u15.t (pk, ck, v) VALUES (-1, 0x01, 0x00)"),
                 ('DELETE u15.t small row (MODIFY)', "DELETE FROM u15.t WHERE pk = -1 AND ck = 0x01"),
                 ('SELECT system_views.settings', 'SELECT name FROM system_views.settings LIMIT 1')]
        for name, q in tests:
            try:
                s.execute(q)
                print('%-34s ALLOWED' % name)
            except Exception as e:
                print('%-34s %s: %s' % (name, type(e).__name__, str(e)[:140]))
    elif mode == 'victim':
        # 3-b confirm victim: own role/keyspace; open loop <rate>/s alternating a 1 KiB INSERT and a SELECT by key (CL ONE),
        # <= max_out outstanding, client request timeout <tmo> s; per-second CSV (ops issued in that second, by outcome, ok latency)
        # and a per-response file. Runs until <stopfile> exists or <maxsec>. Session errors (node gone) are counted as errors.
        rate, maxout, tmo, maxsec, stopf, csvp, respp = (float(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6]),
                                                         sys.argv[7], sys.argv[8], sys.argv[9])
        c.shutdown()
        SRC = os.environ.get('SRC_ADDR') or None   # victim's own source address (another application server)
        c, s = connect(port, timeout=tmo)
        pw = s.prepare('INSERT INTO vks.kv (k, v) VALUES (?, ?)')
        pr = s.prepare('SELECT v FROM vks.kv WHERE k = ?')
        val = os.urandom(1024)
        lock = threading.Lock()
        per = {}
        tot = {'issued': 0, 'capped': 0}
        out = [0]
        fr = open(respp, 'w')
        fr.write('issue_epoch,op,latency_s,outcome,err\n')

        def rec(sec, op, oc, lat, err):
            with lock:
                d = per.setdefault(sec, {'w_ok': 0, 'w_to': 0, 'w_err': 0, 'r_ok': 0, 'r_to': 0, 'r_err': 0, 'lat': []})
                d['%s_%s' % (op, oc)] += 1
                if oc == 'ok':
                    d['lat'].append(lat)
                out[0] -= 1
                fr.write('%.3f,%s,%.4f,%s,%s\n' % (sec + 0.0, op, lat, oc, err))

        def done(_, ts, op):
            rec(int(ts), op, 'ok', time.time() - ts, '')

        def fail(e, ts, op):
            rec(int(ts), op, 'to' if is_timeout(e) else 'err', time.time() - ts, type(e).__name__)

        t0 = time.time()
        slot = 0
        nw = 0
        while time.time() - t0 < maxsec and not os.path.exists(stopf):
            now = time.time()
            while slot <= (now - t0) * rate:
                op = 'w' if slot % 2 == 0 else 'r'
                slot += 1
                with lock:
                    if out[0] >= maxout:
                        tot['capped'] += 1
                        continue
                    out[0] += 1
                    tot['issued'] += 1
                ts = time.time()
                try:
                    if op == 'w':
                        f = s.execute_async(pw, (nw, val))
                        nw += 1
                    else:
                        f = s.execute_async(pr, (max(0, nw - 1),))
                    f.add_callbacks(callback=done, errback=fail, callback_args=(ts, op), errback_args=(ts, op))
                except Exception as e:
                    fail(e, ts, op)
            time.sleep(0.005)
        t_end = time.time()
        while time.time() - t_end < tmo + 2 and out[0] > 0:
            time.sleep(0.2)
        with lock:
            fr.close()
            with open(csvp, 'w') as fc:
                fc.write('epoch_s,w_ok,w_to,w_err,r_ok,r_to,r_err,ok_p50_ms,ok_p99_ms,ok_max_ms\n')
                for sec in sorted(per):
                    d = per[sec]
                    ls = sorted(d['lat'])
                    q = (lambda f: round(ls[min(len(ls) - 1, int(f * len(ls)))] * 1000, 1) if ls else '')
                    fc.write('%d,%d,%d,%d,%d,%d,%d,%s,%s,%s\n' % (sec, d['w_ok'], d['w_to'], d['w_err'], d['r_ok'], d['r_to'], d['r_err'],
                                                                  q(0.5), q(0.99), q(1.0)))
            print(json.dumps({'kind': 'victim', 'issued': tot['issued'], 'capped': tot['capped'], 'outstanding_after': out[0],
                              'seconds': round(t_end - t0, 1)}))
    elif mode == 'data':
        idx, rate, maxout, maxsec, stopf, csvp, respp = (int(sys.argv[4]), float(sys.argv[5]), int(sys.argv[6]), float(sys.argv[7]),
                                                         sys.argv[8], sys.argv[9], sys.argv[10])
        ps = s.prepare('INSERT INTO u15.t (pk, ck, v) VALUES (?, ?, ?)')
        val = os.urandom(VAL)
        S = Stream(csvp, respp)
        t0 = time.time()
        slot = 0
        last_row = int(t0)
        why = 'maxsec'
        while True:
            now = time.time()
            if now - t0 > maxsec:
                break
            if os.path.exists(stopf):
                why = 'stopfile'
                break
            while slot <= (now - t0) * rate:
                with S.lock:
                    full = S.st['outstanding'] >= maxout
                    if full:
                        S.st['capped'] += 1
                    else:
                        kk = S.st['issued']
                        S.st['issued'] += 1
                        S.st['outstanding'] += 1
                slot += 1
                if not full:
                    S.send(s, ps, (idx * 1000000000 + kk, b'\x01' + kk.to_bytes(8, 'big'), val))
            if int(now) > last_row:
                last_row = int(now)
                S.row()
            time.sleep(0.005)
        el = time.time() - t0
        S.drain(last_row)
        print(json.dumps(S.summary({'kind': 'data', 'src': SRC, 'idx': idx, 'stop': why, 'rate': rate, 'max_out': maxout}, el)))
    elif mode == 'poison':
        pmode, size, rate, maxout, maxsec, stopf, csvp, respp = (sys.argv[4], int(sys.argv[5]), float(sys.argv[6]), int(sys.argv[7]),
                                                                 float(sys.argv[8]), sys.argv[9], sys.argv[10], sys.argv[11])
        bound = bytes(size)
        if pmode == 'cas':
            ps = s.prepare('INSERT INTO u15.t (pk, ck, v) VALUES (0, ?, 0x00) IF NOT EXISTS')
        else:
            ps = s.prepare('DELETE FROM u15.t WHERE pk = 0 AND ck > ?')
        S = Stream(csvp, respp)
        t0 = time.time()
        slot = 0
        last_row = int(t0)
        why = 'maxsec'
        while True:
            now = time.time()
            if now - t0 > maxsec:
                break
            if os.path.exists(stopf):
                why = 'stopfile'
                break
            while slot <= (now - t0) * rate and not (pmode == 'once' and slot >= 1):
                with S.lock:
                    full = S.st['outstanding'] >= maxout
                    if full:
                        S.st['capped'] += 1
                    else:
                        S.st['issued'] += 1
                        S.st['outstanding'] += 1
                slot += 1
                if not full:
                    S.send(s, ps, (bound,))
            if int(now) > last_row:
                last_row = int(now)
                S.row()
            time.sleep(0.01)
        el = time.time() - t0
        S.drain(last_row)
        print(json.dumps(S.summary({'kind': 'poison', 'mode': pmode, 'bound_bytes': size, 'src': SRC, 'stop': why, 'rate': rate,
                                    'max_out': maxout}, el)))
    c.shutdown()


main()
