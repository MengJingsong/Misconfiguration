# Harness: max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous

Written 2026-10-26 (step 1, set A batch 10, tag lz). Case: [`../../../stage3-ai-deep-read/cases/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous.md`](../../../stage3-ai-deep-read/cases/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous.md); results: [`../../results/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous.md`](../../results/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous.md).

| File | Tier | What it is |
|---|---|---|
| `frozen-B2f-B2g-B3f-B3g.txt` | both | the frozen prediction and conclusion tables (text of B2f+B2g and B3f+B3g after the audit amendments); its sha256 is in results section 1 |
| `LeveledManifestL0Test.java` | unit (B2) | JUnit class copied into `test/unit/org/apache/cassandra/db/compaction/` of a `copy-source.sh` tree. It only records readings (`R <section> <key> <value>` lines in `$L0_OUT`); it asserts no prediction. Tests: `routes` (R0 / R1 / R2 x tables `mt32`, `mt8` x N {31,32,33,64,200} x flag {false,true}, `L0_REPS` reps, default 3), `execute` (one STCS task on a fresh R1 arm, N 33 and 64), `positiveControl` (L1 at 3x target, flag true, execute L1->L2 candidates down to target) |
| `unit-run.sh <tree> <outdir> [compile-only]` | unit | copies the class in, runs `ant testsome` (timeout 2,400,000 ms), keeps `readings.txt`, `ant.log`, the JUnit XML |
| `unit-analyze.py <readings.txt>` | unit | judges B2f (PASS/FAIL per prediction group) |
| `cluster-run.py <label>` | cluster (B3) | one label per call (`A B C D`): `L0_TREE`, `L0_OUT` in the environment; mounts a 12 GiB tmpfs at `/mnt/s4lz`, starts one node on `127.0.4.1` (JMX 7140), creates `ks.standard1` (LCS 10 MiB, fanout 10), sets `LeveledManifest` to DEBUG, runs `cassandra-stress write n=1500000 throttle=5000/s` while `nodetool flush` loops, samples file bytes / fds / RssAnon (5 s) and `tablestats`/`compactionstats` (20 s), snapshots lag-end, drains (A, C, D), truncates, stops the node by PID. Stops at a failed first-trigger check; the node is stopped on any exit |
| `cluster-analyze.py <outdir>` | cluster | judges B3f from the snapshots and samples |
| `selfcheck.py <unit dir> <cluster dir>` | both | independent re-derivation from the raw files (console echo, XML, raw tablestats text, stress output, yaml, JVM args, debug.log) |

**Instrument checks (not readings):** the test class compiled against the tree (`ant build-test`); a 1-rep shakedown of the unit tier, looked at only for exceptions and setup keys (30 L1 sstables at 3.04x target, one held sstable, L0 sstables mutually overlapping) and discarded; a 100,000-row shakedown of label A, discarded, which found defect H1 (see below). Defects of the harness itself are listed in the results file section 3.
**Environment:** JDK 11, Ant 1.10, two trees from `copy-source.sh` on pc12 (`~/s4-b10-lz-unit` for the unit tier, `~/s4-b10-lz-node` for the node; never `ant` in the tree a node runs from). Run order: `unit-run.sh ~/s4-b10-lz-unit ~/s4-b10-lz-logs/unit1`, then `cluster-run.py` for A, B, C, D one after another.
**Cleanup:** the cluster runner stops its node; `sudo umount /mnt/s4lz` after the last label; delete the two trees and `~/s4-b10-lz-logs`.
