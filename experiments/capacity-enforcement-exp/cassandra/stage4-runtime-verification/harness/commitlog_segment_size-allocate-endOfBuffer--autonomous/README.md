# Harness — commitlog_segment_size-allocate-endOfBuffer--autonomous

Code for the case file's B2 (unit) and B3 (cluster), as amended 2026-10-23 (B2i). Results:
[`../../results/commitlog_segment_size-allocate-endOfBuffer--autonomous.md`](../../results/commitlog_segment_size-allocate-endOfBuffer--autonomous.md). Node copies: `pc12:~/stage4-seg/harnessA/` (md5s in `../../results/commitlog_segment_size-allocate-endOfBuffer--autonomous/run1/harness.md5`). Not committed (the human closes the commit).

| File | What it is |
|---|---|
| `SegmentSizeCapTest.java` | B2's test, copied into `<tree>/test/unit/org/apache/cassandra/db/commitlog/`. One writer thread calls `CommitLog.instance.add`; after every add it records each segment's capacity (first sight), the returned end offset (`buffer.limit()`, the `next` of `:246`) and, by reflection, `endOfBuffer` / `allocatePosition`. Main workload (`adds` x entry total `E`), max-accepted and oversize probes, the two exact-edge probes (B2i.4), then a per-segment census (`seg.csv`) and `PROBE`/`SUMMARY` lines (`seg.summary`). The LZ4 census walks the sync-marker chain to count blocks. |
| `unit-run.sh` | `bash unit-run.sh <tree> <outdir> [label:S:mode:E:fill ...]`. One `ant testsome` JVM per arm with its own yaml (B2i.1): segment size, `commitlog_sync_period: 1h`, memtable limit 600 MiB x 0.95 (so no flush recycles a segment), LZ4 for the `lz4` arms. Default: S in {1, 2, 8, 32} x {mmap, lz4}, plus E = 16 KiB, a zero-fill LZ4 arm and a repeat. |
| `analyze_unit.py` | Readings and the `EXPECTED:` checks per arm (B2f / B2g / B2i). |
| `cluster-run.sh` | `bash cluster-run.sh <outroot> <label> <S> <mmap\|lz4> <total_MiB> <n> <stress\|loader\|none>`. One node from `~/stage4-seg/treeA` under `~/stage4-seg/nodeA`, yaml keys replaced or appended and each checked to occur once; 4 GiB heap, `memtable_heap_space: 2048MiB` and `memtable_cleanup_threshold: 0.9` (environment deviation, see results §2), NMT on. `sampler.py` (0.25 s: file sizes by stat, `/proc/<pid>/maps`), a 1 s `TotalCommitLogSize` JMX loop, stress `write n` 1,000-byte values x 32 threads. Stops the node on any exit. |
| `sampler.py`, `loader.py` | The directory/maps sampler; the compressible-value loader on the bundled driver (B2i.5). |
| `cluster-chain.sh` | B3e's arms in order: S = 8, 32, 128; control (S = 8, total 64); LZ4 (S = 32); compressible (S = 32, loader); idle. |
| `analyze_cluster.py` | Readings and `EXPECTED:` lines per B3f / B3g / B2i.5. |

**Instrument checks (not readings):** `ant build-test` compiled the test (11 s); a 2-arm unit shakedown (S = 1, mmap and lz4) exercised the probes and found two analyzer parse bugs (`oversizedMutations+1` has no `=`; Java prints `true`), fixed before run 1; a 30,000-row cluster shakedown (S = 8) checked the yaml assertions, the sampler, maps and JMX. Shakedown outputs are in `pc12:~/stage4-seg/{shakeA,}` and are not run 1.
