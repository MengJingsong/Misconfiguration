# Harness — max_shard_split-getnumshards-count--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `41ebd4fa…`, see the results file
[§1](../../results/max_shard_split-getnumshards-count--autonomous.md)). Written 2026-10-28 on `pc39`; run copy `~/s4-ms`
(`copy-source.sh` of `cassandra/cassandra-5.0.9`, `ant build-test`; the probe test is copied into the copy's `test/unit/`, never into the repository).

| File | Tier | What it does |
|---|---|---|
| `ShardCapProbeTest.java` | unit (B2) | JUnit class in package `org.apache.cassandra.db.compaction.unified`. `sweep`: `Controller.fromOptions(null, options)` for growth {0, 0.333, 1} x target {1 MiB, 1 GiB} x base {1, 4, 2047, 2048, 4096} x 11 densities (each called twice), and the `min_sstable_size` control; `trackerHeap`: retained heap of 20,000 `ShardManagerNoDisks.BoundaryTracker`s at 4 / 1024 / 2^20 shards, 3 repetitions. `STAGE4 …` lines. |
| `unit-run.sh <copy> <out>` | unit | two `ant testsome` runs of the probe (`-Xmx1g -XX:+UseSerialGC`) and upstream `ControllerTest#testGetNumShards` as a known-answer check. |
| `KeyGen.java` | cluster | audit amendment 2026-10-28: keys whose Murmur3 token lies in a window of 2^-14 of the ring (dense arm) or random keys (control arm); needed because `ByteOrderedPartitioner` has no splitter. |
| `make-node.sh`, `workload.py` | cluster (B3a/B3c) | single node on 127.0.0.1 (num_tokens 1, `concurrent_compactors: 1`, `compaction_throughput: 0MiB/s`, `auto_snapshot: false`), local dirs; bundled python driver loading 4096 rows x 16 KiB per batch. |
| `cluster-run.py <label> [shakedown]` | cluster (B3e) | one node start, table `ks.t` under UCS: Config A dense/control, `ALTER` to Config B dense/control, then the `max_sstables_to_compact` 4 vs 32 control; 8 batches (64 MiB each) with a flush after each, `nodetool compact`, snapshots taken when no compaction is pending (post-GC heap, `Space used`, data files, `du`), `Shard count` DEBUG lines of `Controller` per phase, 5-s sampler (heap, RSS, table-dir bytes). |
| `chain.sh` | both | run 1: unit tier, then the cluster tier. |
| `selfcheck.py <run1 dir>` | both | independent re-parse of the raw run-1 files; copied to `results/<stem>/run1/` with its output. |
