# Harness: lcs-maxBytesForLevel-fanoutXsstableSize--autonomous

Written 2026-10-24 (step 1). Case: [`../../../stage3-ai-deep-read/cases/lcs-maxBytesForLevel-fanoutXsstableSize--autonomous.md`](../../../stage3-ai-deep-read/cases/lcs-maxBytesForLevel-fanoutXsstableSize--autonomous.md); results: [`../../results/lcs-maxBytesForLevel-fanoutXsstableSize--autonomous.md`](../../results/lcs-maxBytesForLevel-fanoutXsstableSize--autonomous.md).

| File | Tier | What it is |
|---|---|---|
| `LeveledManifestCapTest.java` | unit (B2) | JUnit class copied into `test/unit/org/apache/cassandra/db/compaction/` of a `copy-source.sh` tree. It only records readings (`R <section> <key> <value>` lines in `$LCS_OUT`); it asserts no prediction. Tests: `arithmetic`, `ladder` (6 knob pairs × 3 reps: 40 flushes, drain, truncate control), `level8` (F1), `bigPartition`, `maxThresholdControl` (F3) |
| `unit-run.sh <tree> <outdir> [compile-only]` | unit | copies the class in, runs `ant testsome`, keeps `readings.txt`, `ant.log`, the JUnit XML |
| `unit-analyze.py <readings.txt>` | unit | judges B2f/B2g (PASS/FAIL per prediction) |
| `cluster-run.py <label>` | cluster (B3) | one label per call (`A B C D Aprime`): `LCS_TREE`, `LCS_OUT` in the environment; mounts a 24 GiB tmpfs at `/mnt/lcsrun`, starts one node, creates `ks.standard1`, runs `cassandra-stress`, samples file bytes (5 s) and `tablestats`/`compactionstats` (20 s), drains, truncates, stops the node. Stops at the first failed check; the node is stopped on any exit |
| `cluster-analyze.py <outdir>` | cluster | judges B3f/B3g from the snapshots and samples |
| `selfcheck.py <unit dir> <cluster dir>` | both | independent re-derivation from the raw files (console echo, raw tablestats text, stress output, yaml, node logs) |

**Instrument checks (not readings):** the test class compiled against the tree (`ant build-test`); a 150,000- and a 300,000-row shakedown of label A, discarded, found defects D1 (stop condition) and D2 (unquoted `-col`) of the results file §3.
**Environment:** JDK 11, Ant 1.10, a tree from `copy-source.sh`. Run order used: `unit-run.sh ~/cassandra-lcsF ~/stage4-logs/lcs/F-unit`, then `~/stage4-logs/lcs/chain.sh` (labels one after another).
**Cleanup:** the cluster runner stops its node; `sudo umount /mnt/lcsrun` after the last label; delete the tree and `~/stage4-logs/lcs`.
