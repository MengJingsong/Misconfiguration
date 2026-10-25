# Harness: sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous

Written 2026-10-24 (step 1). Case: [`../../../stage3-ai-deep-read/cases/sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous.md`](../../../stage3-ai-deep-read/cases/sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous.md); results: [`../../results/sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous.md`](../../results/sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous.md).

| File | Tier | What it is |
|---|---|---|
| `LcsNextLevelProbeTest.java` | unit (B2) | JUnit class copied into `test/unit/org/apache/cassandra/db/compaction/` of a `copy-source.sh` tree. It only records readings (`R <section> <key> <value>` lines in `$LCS_OUT`). Tests: `boundary` (MockSchema sstables with exact sizes: N MiB − 1, N MiB, N MiB + 1; mixed-level; all-L1), `sets` (Sets A and B as real flushes; Set B compacted once), `bigPartition` (≈ 15 MiB partition at N=5), `sameInputControl` (the same ≈ 30 MiB input compacted at N = 1/5/20/160: the file-count positive control of B2h) |
| `unit-run.sh <tree> <outdir> [compile-only]` | unit | copies the class in, runs `ant testsome`, keeps `readings.txt`, `ant.log`, the JUnit XML |
| `unit-analyze.py <readings.txt>` | unit | judges B2f/B2g |
| `cluster-run.py <label>` | cluster (B3) | one label per call (`N5 N20 N160 T20 STCS`): `LCS_TREE`, `LCS_OUT` in the environment; mounts a 24 GiB tmpfs at `/mnt/lcsrun`, starts one node, creates `ks.standard1` in the stress layout, runs `cassandra-stress` (write, then the overwrite phase), then the large-partition table `ks.big` through `big-writer.py`, samples file bytes (5 s) and `tablestats`/`compactionstats` (20 s), drains, truncates, stops the node |
| `big-writer.py` | cluster | 3 partitions × 10,000 rows × 4 KiB into `ks.big` with the bundled Python driver (protocol 4, UNLOGGED batches of 10 rows) |
| `cluster-analyze.py <outdir>` | cluster | judges B3f/B3g |
| `selfcheck.py <unit dir> <cluster dir>` | both | independent re-derivation from the raw files |

**Instrument checks (not readings):** the test class compiled against the tree; the shared runner's discarded shakedowns (150,000 and 300,000 rows, label A of the sibling case) found defects D1 and D2 of the results file §3; `big-writer.py` first ran against the real node in the N5 run (an earlier draft used batches of 20 rows = 80 KiB, over `batch_size_fail_threshold`, and was corrected to 10 rows before any run).
**Unit tier history:** the first N unit run (`~/stage4-logs/lcs/N-unit-attempt1/`) lacked the same-input positive control B2h names (the sets scale with N); `sameInputControl` was added and the unit tier re-run from the start (results file §3, D5).
**Run order used:** `unit-run.sh ~/cassandra-lcsN ~/stage4-logs/lcs/N-unit`, then `~/stage4-logs/lcs/chain.sh`.
**Cleanup:** the runner stops its node; `sudo umount /mnt/lcsrun` after the last label; delete the tree and `~/stage4-logs/lcs`.
