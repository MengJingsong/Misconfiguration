#!/usr/bin/env python3
"""B3c (amended 2026-10-25) of max_value_size-applySimpleConfig-max_value_size--autonomous: one driver request per call.
usage: mvsclient.py <driver zip> <start label> <req file> <written.json> <mode> [args]
  modes: settings | schema | insert <k> <bytes> | read <k> | readall
  Bundled driver (loaded as bin/cqlsh.py loads it), protocol 5, DCAwareRoundRobinPolicy, token_metadata_enabled=False, CL ONE,
  request timeout 120 s, FallthroughRetryPolicy (the default policy turns a one-node error into NoHostAvailable).
  insert: os.urandom bytes; the sha256 and length are stored in <written.json> (k -> [len, sha256]).
  Appends one line to <req file>:
    REQ start=<label> op=<mode> k=<k|-> t0=<epoch ms> t1=<epoch ms> outcome=OK|ERR [len= sha= match=] [rows=k:len:match,...]
        [class=<exception class>] [msg=<message, newlines folded, <= 1500 chars>]
"""
import hashlib, json, os, sys, time
_zip = sys.argv[1]
_ver = os.path.splitext(os.path.basename(_zip))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(_zip, 'cassandra-driver-' + _ver))
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra.policies import DCAwareRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra.query import SimpleStatement  # noqa: E402

LABEL, REQ, WRITTEN, MODE = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
ARGS = sys.argv[6:]


def ms():
    return int(time.time() * 1000)


def load_written():
    try:
        return {int(k): v for k, v in json.load(open(WRITTEN)).items()}
    except FileNotFoundError:
        return {}


def main():
    prof = ExecutionProfile(load_balancing_policy=DCAwareRoundRobinPolicy(), request_timeout=120,
                            consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy())
    c = Cluster(['127.0.0.1'], protocol_version=5, token_metadata_enabled=False,
                execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = c.connect()
    written = load_written()
    k = ARGS[0] if ARGS else '-'
    parts = []
    t0 = ms()
    try:
        if MODE == 'settings':
            rows = list(s.execute("SELECT name, value FROM system_views.settings WHERE name = 'max_value_size'"))
            parts.append('value=' + ','.join(r.value for r in rows))
        elif MODE == 'schema':
            s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
            s.execute("CREATE TABLE IF NOT EXISTS ks.t (k int PRIMARY KEY, v blob)")
        elif MODE == 'insert':
            kk, n = int(ARGS[0]), int(ARGS[1])
            data = os.urandom(n)
            ps = s.prepare("INSERT INTO ks.t (k, v) VALUES (?, ?)")
            t0 = ms()
            s.execute(ps, (kk, data))
            written[kk] = [n, hashlib.sha256(data).hexdigest()]
            json.dump({str(a): b for a, b in written.items()}, open(WRITTEN, 'w'))
            parts.append('len=%d sha=%s' % (n, written[kk][1][:16]))
        elif MODE == 'read':
            kk = int(ARGS[0])
            ps = s.prepare("SELECT v FROM ks.t WHERE k = ?")
            t0 = ms()
            row = s.execute(ps, (kk,)).one()
            if row is None or row.v is None:
                parts.append('len=none')
            else:
                h = hashlib.sha256(row.v).hexdigest()
                exp = written.get(kk)
                parts.append('len=%d sha=%s match=%s' % (len(row.v), h[:16], 'yes' if exp and exp == [len(row.v), h] else 'no'))
        elif MODE == 'readall':
            t0 = ms()
            rows = list(s.execute(SimpleStatement("SELECT k, v FROM ks.t", fetch_size=5000)))
            out = []
            for r in sorted(rows, key=lambda r: r.k):
                h = hashlib.sha256(r.v).hexdigest() if r.v is not None else None
                exp = written.get(r.k)
                out.append('%d:%s:%s' % (r.k, len(r.v) if r.v is not None else 'none',
                                         'yes' if exp and h and exp == [len(r.v), h] else 'no'))
            parts.append('nrows=%d rows=%s' % (len(rows), ','.join(out)))
        else:
            raise SystemExit('unknown mode ' + MODE)
        t1 = ms()
        line = 'REQ start=%s op=%s k=%s t0=%d t1=%d outcome=OK %s' % (LABEL, MODE, k, t0, t1, ' '.join(parts))
        rc = 0
    except Exception as e:
        t1 = ms()
        msg = ' '.join(str(e).split())[:1500]
        line = 'REQ start=%s op=%s k=%s t0=%d t1=%d outcome=ERR class=%s msg=%s' % (LABEL, MODE, k, t0, t1, type(e).__name__, msg)
        rc = 1
    finally:
        c.shutdown()
    with open(REQ, 'a') as f:
        f.write(line.rstrip() + '\n')
    print(line, flush=True)
    return rc


if __name__ == '__main__':
    sys.exit(main())
