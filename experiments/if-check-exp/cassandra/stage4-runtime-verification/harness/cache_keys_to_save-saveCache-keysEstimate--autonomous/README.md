# Harness — cache_keys_to_save-saveCache-keysEstimate--autonomous

Stage-4 harness for the autonomous case file (frozen text in `frozen-prediction.txt`, sha256 `c88c1547...`; amendments B5 of 2026-10-26).
Written on pc07 (node0), work trees `~/s4-b8-kt/u` (unit, `ant build-test`) and `~/s4-b8-kt/c` (node, `ant jar` + `ant stress-build`), both from
`copy-source.sh`. Logs on the node: `~/s4-b8-kt-logs/<run>/`. Port slot 1: 127.0.1.1, JMX 7110, native 9042.

| File | Tier | What it does |
|---|---|---|
| `KeysToSaveTest.java` | unit (B2) | package `org.apache.cassandra.cache`; key cache P=10000 (flushed SSTable + `getPosition`), row cache P=2000 (OHC, unit yaml), counter cache P=2000 (`CounterMutation`); per N and rep (2, shuffled): `submitWrite(N)` file length, direct `Writer.saveCache()` completed count and thread-allocated bytes, reload count; no-save control; hot-key check; private-cache race test with a blocking stub serializer. `STAGE4 save/check/race/hot/alloc` lines. |
| `unit-run.sh [run]` | unit | copies the test into the unit tree, `ant testsome`, then upstream `AutoSavingCacheTest`; `summary.txt`. |
| `reader.py` | cluster | scans `keyspace1.standard1` keys, `SELECT *` each (protocol 4) to fill key and row caches. |
| `cluster-run.py <run> main` | cluster (B3) | L1 yaml unset + runtime 10000/100/0 + capacity control; L2/L3 restarts with yaml 100 / 10000; L4 save periods 0 control. `EXPECTED:` lines, `phases.jsonl`. Node data on tmpfs `/dev/shm/s4-b8-kt/node`. Node stopped on any exit. |
