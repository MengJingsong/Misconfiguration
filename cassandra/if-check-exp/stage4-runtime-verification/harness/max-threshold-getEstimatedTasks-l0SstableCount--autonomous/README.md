# Harness: max-threshold-getEstimatedTasks-l0SstableCount--autonomous

Written 2026-10-26 (step 1). Case: `../../../stage3-ai-deep-read/cases/max-threshold-getEstimatedTasks-l0SstableCount--autonomous.md`; results: `../../results/max-threshold-getEstimatedTasks-l0SstableCount--autonomous.md`. Node: pc07, port slot 6 (127.0.6.1, JMX 7160).

| File | Tier | What it is |
|---|---|---|
| `MaxThresholdEstimateProbeTest.java` | unit (B2) | JUnit class copied into `test/unit/org/apache/cassandra/db/compaction/` of a `copy-source.sh` tree. Records readings (`R <section> <key> <value>` in `$MT_OUT`), asserts nothing. Tests: `estimateVsMaxThreshold` (200 one-row L0 sstables; `max_threshold` 4,32,128,32,4,128,32; STCS-in-L0 on then off), `controlByteTerm` (U4a), `controlOutputFileSize` (U4b) |
| `unit-run.sh <tree> <outdir> [compile-only]` | unit | copies the class in, runs `ant testsome`, keeps `readings.txt`, `ant.log`, the JUnit XML |
| `unit-analyze.py <readings.txt>` | unit | PASS/FAIL per B2f prediction and per control (U3, U4) |
| `cluster-run.py <arm>` | cluster (B3) | `MT_TREE` (tree built with `ant jar`), `MT_OUT`; arms `mt4 mt32 mt128 mt32b c64 d32`; tmpfs `/mnt/s4b10lm`; `EXPECTED:` lines are checks, a failed one stops the arm; the node is stopped on any exit |
| `chain.sh <tree> <outdir>` | cluster | the six arms one after another |
| `cluster-analyze.py <outdir>` | cluster | judges B3f/B3g (C5-C7) from `phase-A.json`, `phase-B.json` |
| `selfcheck.py <unit dir> <cluster dir>` | both | independent re-derivation from the raw files (junit xml, raw tablestats/compactionstats text, stress tail, samples, node logs) |

**Instrument checks (not readings):** probe class compiled against the tree; one discarded unit run (all analyzer checks passed); `unit-analyze.py` fed a perturbed copy of those readings flags the three perturbations; `cluster-analyze.py` fed six copies of one shakedown arm flags the pending-tasks and control checks; two discarded cluster shakedowns of arm mt4 (330k rows, then 200k rows) found D1 (the executor's completed-task counter also counts empty background submissions, so "no compaction ran" now uses `compactionhistory` and sstable count == L0) and D2 (`statusautocompaction` prints `not running` for a disabled table, not `false`).
**Cleanup:** the runner stops its node; `sudo umount /mnt/s4b10lm` after the last arm; delete `~/s4-b10-lm`, `~/s4-b10-lm2`, `~/s4-b10-lm-logs`.
