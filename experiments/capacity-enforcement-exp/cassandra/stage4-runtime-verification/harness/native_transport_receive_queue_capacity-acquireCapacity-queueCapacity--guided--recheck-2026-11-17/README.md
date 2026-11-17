# Harness — native_transport_receive_queue_capacity, recheck claim (2026-11-17)

Stage-4 harness for the case file's section "Stage-4 design for the recheck claim (2026-11-17)" (frozen; hash in the
results file `../../results/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided--recheck-2026-11-17.md` §1).
Written 2026-11-17 after the freeze. Run on `pc72` from a copy, `/mydata/s4/ntq-recheck/harness/` (`md5sum` compared
with this folder; the run script prints every file's `md5sum` into `summary.txt`).

| File | Origin | What it does |
|---|---|---|
| `ntq-trace.btm` | copied unchanged from `../native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided/` | Byteman, observation only: `new`, `acq` (outcome, `queueSize` after, per-IP and global reserve use/limit), `rel`, `dec` (bytes, backpressure), `rls`, `disc`, `ldisc`, `wake` lines of the server's `CQLMessageHandler`s |
| `hold-request.btm` | copied unchanged | the trigger: each `QUERY SELECT pk FROM ks.t` request sleeps `-Dstage4.hold.ms` (here 250; 50 in the shakedowns `shake1`/`shake2`) on the request executor while the hold file exists |
| `NativeFlood.java` | copied unchanged | the client: *N* protocol-v5 `SimpleClient` connections of one mode, *W* requests in flight each, retry after an overload (`--retry-ms`), per-second and total counts, drain before close |
| `Jmx.java` | copied unchanged | JMX reader (`get`, `poll`) |
| `make-node-yaml.sh` | copied unchanged; run with `CASSANDRA_HOME=/mydata/s4/ntq-recheck/cassandra NTQ=/mydata/s4/ntq-recheck/node` and **no** extra keys | the node's `conf/`: loopback, directories, `native_transport_timeout: 60s`, `read_request_timeout: 60000ms`, `throw_on_overload: false`, rate limiting off (both defaults); the capacity, the reserves, the max message size are **not** set (defaults) |
| `recheck-run.py` | new | one node lifetime: the node in `systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0` (`bin/cassandra -f`, `MAX_HEAP_SIZE=2G`, `MAX_DIRECT_MEMORY_SIZE=2G`, Byteman agent), read-backs (yaml has none of the knobs, scope limits, `Submit -l` 9 rules), schema, the arms `idle`, `U10`, `D20`, `D30`, `D40`, `T40`, `L20`; per arm Client meters before/after, `Jmx poll` every 2 s (heap, direct `MemoryUsed`, networking pool, global reserve in use, paused), the scope's `memory.current` every 2 s, class histograms at 1/3 and 2/3, the drain check; then stops the node, checks no `CassandraDaemon` is left, parses the whole trace and writes `EXPECTED:` lines per prediction 1–10 of the design |

```bash
# on pc72
cd /mydata/s4/ntq-recheck && RECHECK_RUN=run1 python3 harness/recheck-run.py     # keep the ssh session open
```

`RECHECK_SCALE` (multiplies durations and windows) is for shakedowns only, never for a reading.
Checks before run 1: Byteman `TestScript` type-checks all 9 rules of the two `.btm` files; `javac` of both Java files
(done by the script); shakedowns at `RECHECK_SCALE=0.2` (`shake1`, `shake2`, hold 50 ms; `shake3`, hold 250 ms) exercised every step; their numbers are not readings.
