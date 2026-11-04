# Harness — commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous

Code for the case file's B2 (unit) and B3 (cluster), as amended 2026-10-23 (B2i). Results:
[`../../results/commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous.md`](../../results/commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous.md). Node copies: `pc12:~/stage4-seg/harnessB/` (md5s in `../../results/commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous/run1/harness.md5`). Not committed (the human closes the commit).
It shares its scaffolding with the sibling case `commitlog_segment_size-allocate-endOfBuffer--autonomous` (copied, then adapted); the two files are run and judged independently, each in its own working tree (`treeA`, `treeB`).

| File | What it is |
|---|---|
| `SegmentCapProbeTest.java` | B2's test, copied into `<treeB>/test/unit/org/apache/cassandra/db/commitlog/`. One writer thread adds 64 random-payload mutations of `n/16` bytes (B2i.5); after every add it records each segment's capacity (first sight), the returned end offset and, by reflection, `endOfBuffer` / `allocatePosition`; then the max-accepted (`max_mutation_size`) and oversize (`+1`) mutations, a final `sync(true)`, and a per-segment census (`seg.csv`: capacity, `endOfBuffer`, `allocatePosition`, `isStillAllocating()`, file length, `onDiskSize()`, blocks). |
| `unit-run.sh` | `bash unit-run.sh <tree> <outdir> [label:n:mode ...]`. One `ant testsome` JVM per arm with its own yaml (B2i.1; direct arms set `commitlog_disk_access_mode: direct`, LZ4 arms `commitlog_compression`). Default: n in {1, 4, 32} x {mmap, lz4, direct} plus a repeat. |
| `analyze_unit.py` | Readings and `EXPECTED:` checks per arm (B2f / B2g / B2i): capacity, offsets, retired and active states, file lengths per mode, probes, the `(n+1)` control assertion. |
| `cluster-run.sh`, `sampler.py` | One node from `~/stage4-seg/treeB` under `~/stage4-seg/nodeB`: 2 GiB heap, `memtable_heap_space` and `memtable_offheap_space` 1024 MiB, sync period 10 s, `commitlog_total_space` per arm; stress `write n=2000000`, 1,024-byte values, 64 threads (B3c); sampler of file sizes and `/proc/<pid>/maps` every 0.25 s, a 1 s `TotalCommitLogSize` loop, `jcmd VM.native_memory summary` after the load (NMT on). `loader.py` is unused in this case. |
| `cluster-chain.sh` | n = 8, 32, 64; LZ4 at 32; control (32 MiB, total 256). |
| `analyze_cluster.py` | Readings and `EXPECTED:` lines per B3f / B3g. |
