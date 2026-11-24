#!/usr/bin/env python3
"""3-b confirm B20 attacker client, adapted from the case's writer.py. Role 'attacker' (LOGIN; only grant: CREATE ON
KEYSPACE atk), bundled Python driver, native protocol 4, CL ONE. No nodetool, no admin step.
  attacker.py schema                    CREATE TABLE atk.t (pk bigint, ck int, v blob, PRIMARY KEY (pk, ck))
  attacker.py negative                  privilege checks that must fail (other tenant's table, new keyspace)
  attacker.py wide <a> <b>              rows ck in [a, b) of pk = 0, v = 1,048,576 seeded random bytes, <= 16 in flight;
                                        failed writes retried (up to 5 passes), as any client would
  attacker.py small <a> <b> <inflight>  partitions pk in [a, b), one row ck = pk mod 4000, v = 64 random bytes; retries
  attacker.py cql "<statement>" [timeout]
Prints one JSON line per command.
"""
import collections, json, random, sys, time, drv
from cassandra.concurrent import execute_concurrent_with_args
mode = sys.argv[1]
tmo = float(sys.argv[3]) if mode == 'cql' and len(sys.argv) > 3 else 120
cl, s = drv.session('attacker', timeout=tmo)
t0 = time.time()

def run_retry(st, keys, mk, conc, passes=5):
    todo = list(keys); msgs = collections.Counter(); tried = 0
    for p in range(passes):
        if not todo: break
        res = execute_concurrent_with_args(s, st, (mk(k) for k in todo), concurrency=conc, raise_on_first_error=False)
        failed = []
        for k, (good, r) in zip(todo, res):
            tried += 1
            if not good:
                failed.append(k); msgs[f'pass{p} ' + type(r).__name__ + ': ' + str(r)[:160]] += 1
        todo = failed
    return len(keys), len(keys) - len(todo), tried, msgs

if mode == 'schema':
    s.execute("CREATE TABLE atk.t (pk bigint, ck int, v blob, PRIMARY KEY (pk, ck))")
    print(json.dumps({'created': 'atk.t'}))
elif mode == 'negative':
    out = {}
    for name, q in [('select_other_tenant', 'SELECT * FROM vks.kv LIMIT 1'),
                    ('create_keyspace', "CREATE KEYSPACE atk2 WITH replication = {'class':'SimpleStrategy','replication_factor':1}"),
                    ('create_table_other_ks', 'CREATE TABLE vks.x (a int PRIMARY KEY)')]:
        try:
            s.execute(q); out[name] = 'ALLOWED'
        except Exception as e:
            out[name] = type(e).__name__ + ': ' + str(e)[:200]
    print(json.dumps(out))
elif mode == 'wide':
    a, b = int(sys.argv[2]), int(sys.argv[3])
    st = s.prepare('INSERT INTO atk.t (pk, ck, v) VALUES (0, ?, ?)')
    n, ok, tried, msgs = run_retry(st, range(a, b), lambda i: (i, random.Random(1_000_003 * 7 + i).randbytes(1048576)), 16)
    print(json.dumps({'kind': 'wide', 'rows': [a, b], 'ok': ok, 'missing': n - ok, 'writes_sent': tried,
                      'messages': msgs, 'seconds': round(time.time() - t0, 1)}))
elif mode == 'small':
    a, b, conc = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    st = s.prepare('INSERT INTO atk.t (pk, ck, v) VALUES (?, ?, ?)')
    n, ok, tried, msgs = run_retry(st, range(a, b), lambda pk: (pk, pk % 4000, random.Random(2_000_003 + pk).randbytes(64)), conc)
    print(json.dumps({'kind': 'small', 'rows': [a, b], 'ok': ok, 'missing': n - ok, 'writes_sent': tried,
                      'messages': msgs, 'seconds': round(time.time() - t0, 1)}))
elif mode == 'cql':
    rows = list(s.execute(sys.argv[2]))
    print(json.dumps({'cql': sys.argv[2], 'rows': [list(map(str, r)) for r in rows][:20],
                      'seconds': round(time.time() - t0, 1)}))
cl.shutdown()
