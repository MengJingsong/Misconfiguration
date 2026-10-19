#!/usr/bin/env python3
"""Cluster tier, SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS (case 9b "Data", 9c
"load.py", amended 2026-10-15). Creates keyspace ks (SimpleStrategy RF 1) and the tables t and far (pk int PRIMARY KEY, i int,
val vector<float, 8>, compaction disabled, SAI on i and on val), then loads them: t with 200,000 rows flushed after every 50,000
(four SSTables), far with 50,000 rows by rank and one flush. Flushes with `bin/nodetool flush ks <table>`.
usage: load.py            prints one JSON line with the seeds, counts and timings"""
import json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mmkdata as d  # noqa: E402
from driver import session, CASS  # noqa: E402
from cassandra.concurrent import execute_concurrent_with_args  # noqa: E402

TDEF = ("(pk int PRIMARY KEY, i int, val vector<float, 8>) WITH compaction = "
        "{'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}")


def flush(table):
    subprocess.run([CASS + '/bin/nodetool', 'flush', 'ks', table], check=True, capture_output=True)


def main():
    c, s = session()
    out = {'protocol': c.protocol_version, 'seeds': {'t_vec': d.SEED_T_VEC, 't_order': d.SEED_T_ORDER, 'far_vec': d.SEED_FAR_VEC,
                                                     'far_order': d.SEED_FAR_ORDER, 'q': d.SEED_Q}}
    s.execute("CREATE KEYSPACE ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    for t in ('t', 'far'):
        s.execute(f'CREATE TABLE ks.{t} {TDEF}')
        s.execute(f"CREATE CUSTOM INDEX {t}_val ON ks.{t}(val) USING 'StorageAttachedIndex'")
        s.execute(f"CREATE CUSTOM INDEX {t}_i ON ks.{t}(i) USING 'StorageAttachedIndex'")
    time.sleep(5)
    for t, rows, every in (('t', d.t_rows(), 50000), ('far', d.far_rows(), d.N_FAR)):
        ins = s.prepare(f'INSERT INTO ks.{t} (pk, i, val) VALUES (?, ?, ?)')
        t0 = time.time()
        for k in range(0, len(rows), every):
            chunk = [(pk, pk, v) for pk, v in rows[k:k + every]]
            res = execute_concurrent_with_args(s, ins, chunk, concurrency=64, raise_on_first_error=True)
            if not all(ok for ok, _ in res):
                raise SystemExit(f'insert failed in {t}')
            flush(t)
        out[t] = {'rows': len(rows), 'flush_every': every, 'secs': round(time.time() - t0, 1)}
    q = d.query_vector()
    out['q'] = q
    out['count_t'] = s.execute('SELECT count(*) FROM ks.t').one()[0]
    out['count_far'] = s.execute('SELECT count(*) FROM ks.far').one()[0]
    c.shutdown()
    print('OK ' + json.dumps(out))


if __name__ == '__main__':
    main()
