# Harness — last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `c9adb80e…`). Written 2026-10-28 on `pc32`. Run copy `~/s4-b34`; small-constant variant `~/s4-b34-vS` (`make-variant.sh`).

| File | Tier | What it does |
|---|---|---|
| `SegmentRowCapProbe.java` | unit (B2) | package `…v1`, set-up copied from `SegmentFlushTest` (`SAITester.createMockIndex`, `IndexDescriptor.create`); `grid cap limitMiB N S`: N sorted keys, row ids 0..N-1, S-byte distinct UTF8 terms, own `NamedMemoryLimiter`; `pair cap id1 id2`: two rows. Reads segments and per-segment rows from the written META. |
| `unit-run.sh <copy> <out> [grid\|check]` | unit | caps -1/1000/100 x limits 1/64/1024 MiB x 3 repetitions (27 JVMs), boundary pairs and the gap test. |
| `make-variant.sh <copy>` | cluster | `cp -a` copy with `SegmentBuilder.java:46` = `10_000L`, recompiled into the copy and its jar (the node runs from the jar). |
| `cluster-run.py seed <slot>` / `<label> <std\|small> <MiB> <slot>` | cluster | seed: `cassandra-stress user` (`profile-seed.yaml`: `ks.t3 (id bigint, c0 text)`, 1000-character values; n = 5,000,000 gives 3,931,031 distinct rows), flush, compact to one sstable, copied to `~/stage4-tmp/b34/c3/seed` (the first version used native-mode stress, whose columns are blobs, which SAI rejects); run: restore seed, node (4 GiB G1), `CREATE CUSTOM INDEX` on `c0`, wait for `is_queryable`, record segments, heap, `SegmentBufferSpaceUsedBytes`, debug-log lines. |
| `chain.sh <slot>` | cluster | S1024, S256a, S16, V1024 (small constant), S256b. |
| `profile-seed.yaml`, `analyze_cluster.py`, `selfcheck.py`, `Jmx.java`, `nodelib.py` | both | as in the sibling harnesses. |
