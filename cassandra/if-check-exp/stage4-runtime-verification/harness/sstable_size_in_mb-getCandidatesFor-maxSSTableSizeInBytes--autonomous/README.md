# Harness: sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous

Written 2026-10-24 (step 1). Case: [`../../../stage3-ai-deep-read/cases/sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous.md`](../../../stage3-ai-deep-read/cases/sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous.md); results: [`../../results/sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous.md`](../../results/sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous.md).

| File | Tier | What it is |
|---|---|---|
| `LcsL0ThresholdProbeTest.java` | unit (B2) | JUnit class copied into `test/unit/org/apache/cassandra/db/compaction/` of a `copy-source.sh` tree. It only records readings (`R <section> <key> <value>` lines in `$LCS_OUT`); it asserts no prediction. Tests: `phase1CandidateSet` (N 1/5/160 × 3 reps: 6 overlapping L0 sstables + one L1, candidate set), `step4Outputs` (size-5 task, ≈ 12 MiB partition), `phase2L0Total` (200 flushes at size 1 and 160, truncate control) |
| `unit-run.sh <tree> <outdir> [compile-only]` | unit | copies the class in, runs `ant testsome`, keeps `readings.txt`, `ant.log`, the JUnit XML |
| `unit-analyze.py <readings.txt>` | unit | judges B2f/B2g (PASS/FAIL per prediction) |
| `cluster-run.py <label>` | cluster (B3) | one label per call (`N5 N160 N1024 S160`; S160 = N=160 with `setcompactionthroughput 1`): `LCS_TREE`, `LCS_OUT` in the environment; mounts a 24 GiB tmpfs at `/mnt/lcsrun`, starts one node, creates `ks.standard1`, runs `cassandra-stress`, samples file bytes (5 s) and `tablestats`/`compactionstats` (20 s), drains, truncates, stops the node. Stops at the first failed check; the node is stopped on any exit |
| `cluster-analyze.py <outdir>` | cluster | judges B3f/B3g from the snapshots and samples |
| `selfcheck.py <unit dir> <cluster dir>` | both | independent re-derivation from the raw files (console echo, raw tablestats text, stress output, yaml, node logs) |

**Instrument checks (not readings):** the test class compiled against the tree (`ant build-test`); the shared runner's 150,000- and 300,000-row shakedowns (label A of the sibling case), discarded, found defects D1 (stop condition) and D2 (unquoted `-col`) of the results file §3.
**Environment:** JDK 11, Ant 1.10, a tree from `copy-source.sh`. Run order used: `unit-run.sh ~/cassandra-lcsC ~/stage4-logs/lcs/C-unit`, then `~/stage4-logs/lcs/chain.sh` (labels one after another).
**Cleanup:** the cluster runner stops its node; `sudo umount /mnt/lcsrun` after the last label; delete the tree and `~/stage4-logs/lcs`.
