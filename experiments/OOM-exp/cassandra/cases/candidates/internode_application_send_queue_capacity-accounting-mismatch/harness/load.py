#!/usr/bin/env python3
"""B6 load generator: async prepared inserts to the measured coordinator only.

  load.py schema
  load.py run --kind map|blob --size N [--inflight 256] [--duration 120] [--rate 0] [--pk0 0]

kind=map : t_map(pk int PRIMARY KEY, m map<int,int>), N entries per insert (tiny cells)
kind=blob: t_blob(pk int PRIMARY KEY, b blob),        N bytes per insert (one cell)
Uses the Python driver bundled with cqlsh (lib/cassandra-driver-internal-only-*.zip).
"""
import argparse, glob, os, sys, threading, time

BUILD = "/mydata/b6/cassandra"
z = glob.glob(os.path.join(BUILD, "lib", "cassandra-driver-internal-only-*.zip"))[0]
ver = os.path.basename(z)[len("cassandra-driver-internal-only-"):-len(".zip")]
sys.path.insert(0, os.path.join(z, "cassandra-driver-" + ver))

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

HOST = "127.0.0.13"


def session():
    prof = ExecutionProfile(load_balancing_policy=WhiteListRoundRobinPolicy([HOST]),
                            consistency_level=ConsistencyLevel.ONE, request_timeout=120)
    c = Cluster([HOST], execution_profiles={EXEC_PROFILE_DEFAULT: prof}, protocol_version=5)
    return c, c.connect()


def schema():
    c, s = session()
    s.execute("CREATE KEYSPACE IF NOT EXISTS b6 WITH replication = "
              "{'class':'NetworkTopologyStrategy','v':1,'f':1}")
    s.execute("CREATE TABLE IF NOT EXISTS b6.t_map (pk int PRIMARY KEY, m map<int,int>)")
    s.execute("CREATE TABLE IF NOT EXISTS b6.t_blob (pk int PRIMARY KEY, b blob)")
    print("schema ok")
    c.shutdown()


def run(a):
    c, s = session()
    if a.kind == "map":
        ps = s.prepare("INSERT INTO b6.t_map (pk, m) VALUES (?, ?)")
        val = {i: i for i in range(a.size)}
    else:
        ps = s.prepare("INSERT INTO b6.t_blob (pk, b) VALUES (?, ?)")
        val = os.urandom(a.size)
    sem = threading.Semaphore(a.inflight)
    st = {"ok": 0, "err": 0, "sent": 0, "lasterr": ""}
    lock = threading.Lock()

    def done(_r):
        with lock:
            st["ok"] += 1
        sem.release()

    def fail(e):
        with lock:
            st["err"] += 1
            st["lasterr"] = type(e).__name__ + ": " + str(e)[:160]
        sem.release()

    t0 = time.time(); last = t0; pk = a.pk0
    while time.time() - t0 < a.duration:
        if a.rate > 0:
            due = t0 + (st["sent"] / a.rate)
            if due > time.time():
                time.sleep(min(0.01, due - time.time()))
                continue
        sem.acquire()
        f = s.execute_async(ps, (pk, val))
        f.add_callbacks(done, fail)
        pk += 1; st["sent"] += 1
        now = time.time()
        if now - last >= 5:
            last = now
            print(f"[{time.strftime('%H:%M:%S')}] t={now-t0:5.0f}s sent={st['sent']} ok={st['ok']} "
                  f"err={st['err']} {st['lasterr']}", flush=True)
    for _ in range(a.inflight):
        sem.acquire()
    print(f"FINAL sent={st['sent']} ok={st['ok']} err={st['err']} last_pk={pk} {st['lasterr']}", flush=True)
    c.shutdown()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["schema", "run"])
    p.add_argument("--kind", choices=["map", "blob"], default="map")
    p.add_argument("--size", type=int, default=1000)
    p.add_argument("--inflight", type=int, default=256)
    p.add_argument("--duration", type=float, default=120)
    p.add_argument("--rate", type=float, default=0)
    p.add_argument("--pk0", type=int, default=0)
    a = p.parse_args()
    schema() if a.cmd == "schema" else run(a)
