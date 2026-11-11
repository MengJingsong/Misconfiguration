#!/usr/bin/env python3
"""Client for the cluster tier of unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous (B3c as amended).
usage: load.py probe|run <cassandra-tree> <address> [--threads 8 --batches 250 --keys 500]
  probe  one UNLOGGED batch of <keys> distinct keys into ks.probe (key range 0..keys-1); prints one JSON line
  run    <threads> threads x <batches> batches x <keys> inserts (value 200 B) into ks.t; keys thread*10^7 + batch*keys + i (all distinct);
         prints one JSON line: batches ok/failed, rows acked, batches with the 'Unlogged batch covering' client warning, first warning/error text, seconds.
Native protocol 4, the driver bundled with the tree (lib/cassandra-driver-internal-only-*.zip)."""
import glob, json, sys, threading, time
tree, addr = sys.argv[2], sys.argv[3]
sys.path.insert(0, glob.glob(tree + '/lib/cassandra-driver-internal-only-*.zip')[0] + '/cassandra-driver-3.29.0')
from cassandra.cluster import Cluster
from cassandra.query import BatchStatement, BatchType
mode = sys.argv[1]
opt = dict(zip(sys.argv[4::2], sys.argv[5::2]))
threads, batches, keys = int(opt.get('--threads', 8)), int(opt.get('--batches', 250)), int(opt.get('--keys', 500))
cl = Cluster([addr], protocol_version=4, executor_threads=threads)
s = cl.connect()
V = 'y' * 200
res = dict(ok=0, failed=0, rows=0, warned=0, first_warning='', first_error='')
lock = threading.Lock()


def send(ins, base):
    b = BatchStatement(batch_type=BatchType.UNLOGGED)
    for i in range(keys):
        b.add(ins, (base + i, V))
    f = s.execute_async(b, timeout=120)
    try:
        f.result()
    except Exception as e:
        with lock:
            res['failed'] += 1
            if not res['first_error']:
                res['first_error'] = str(e)[:300]
        return
    w = [x for x in (f.warnings or []) if x.startswith('Unlogged batch covering')]
    with lock:
        res['ok'] += 1
        res['rows'] += keys
        if w:
            res['warned'] += 1
            if not res['first_warning']:
                res['first_warning'] = w[0][:200]


t0 = time.time()
if mode == 'probe':
    send(s.prepare('INSERT INTO ks.probe (k, v) VALUES (?, ?)'), 0)
else:
    ins = s.prepare('INSERT INTO ks.t (k, v) VALUES (?, ?)')

    def worker(tid):
        for bi in range(batches):
            send(ins, tid * 10**7 + bi * keys)
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    [t.start() for t in ts]
    [t.join() for t in ts]
res['seconds'] = round(time.time() - t0, 1)
res['mode'] = mode
print(json.dumps(res))
cl.shutdown()
