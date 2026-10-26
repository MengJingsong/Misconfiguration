#!/usr/bin/env python3
"""Cluster tier load (B3c). Creates ks (RF 1), ks.t (pk int PK, grp int, v vector<float,16>; compaction off; SAI on v and on grp) and
ks.mt (same shape, 5,000 rows, never flushed: the memtable control B3h). Loads ks.t with 80,500 rows, flushes. usage: load.py  -> prints "OK {json}"."""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import srdata as d  # noqa: E402
from driver import session, CASS  # noqa: E402
from cassandra.concurrent import execute_concurrent_with_args  # noqa: E402
TDEF = ("(pk int PRIMARY KEY, grp int, v vector<float, 16>) WITH compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}")
def main():
    c, s = session()
    out = {}
    s.execute("CREATE KEYSPACE ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    for t in ('t', 'mt'):
        s.execute(f'CREATE TABLE ks.{t} {TDEF}')
        s.execute(f"CREATE CUSTOM INDEX {t}_v ON ks.{t}(v) USING 'StorageAttachedIndex'")
        s.execute(f"CREATE CUSTOM INDEX {t}_grp ON ks.{t}(grp) USING 'StorageAttachedIndex'")
    time.sleep(5)
    rows = d.rows()
    for t, rs in (('t', rows), ('mt', rows[:5000])):
        ins = s.prepare(f'INSERT INTO ks.{t} (pk, grp, v) VALUES (?, ?, ?)')
        t0 = time.time()
        res = execute_concurrent_with_args(s, ins, rs, concurrency=64, raise_on_first_error=True)
        assert all(ok for ok, _ in res), 'insert failed'
        out[t] = {'rows': len(rs), 'secs': round(time.time() - t0, 1)}
    subprocess.run([CASS + '/bin/nodetool', '-h', '127.0.0.1', '-p', '7328', 'flush', 'ks', 't'], check=True, capture_output=True,
                   env=dict(os.environ, CASSANDRA_CONF=os.environ['CASSANDRA_CONF']))
    out['count_t'] = s.execute('SELECT count(*) FROM ks.t').one()[0]
    out['count_by_grp'] = {g: s.execute(f'SELECT count(*) FROM ks.t WHERE grp = {g}').one()[0] for g in d.N_BY_GRP}
    c.shutdown()
    print('OK ' + json.dumps(out))
if __name__ == '__main__':
    main()
