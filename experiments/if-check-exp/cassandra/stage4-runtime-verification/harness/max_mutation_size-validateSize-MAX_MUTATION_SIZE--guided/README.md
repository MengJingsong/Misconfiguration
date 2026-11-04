# Harness — max_mutation_size-validateSize-MAX_MUTATION_SIZE

Stage-4 harness for the case's §9 (frozen §9 hash `16618c14…`, see the results file §1). Written 2026-10-11 by the long-path AI session.
Run from a copy on the node, `~/stage4-harness-run/mms/`; compare `md5sum` with this folder before run 1.

| File | Tier | What it does |
|---|---|---|
| `MaxMutationSizeGuardTest.java` | unit | 9e unit steps 2.1–2.6 in one JVM: read-back, calibration of *p\** (largest payload with *T* ≤ *M*), the check's boundary, `CommitLog.add()` position / segment count / content size / meter around an accepted and a refused add, the counter site, idle. Prints `STAGE4 check <name> <expected> <actual> ok\|MISMATCH`, fails at the end on any mismatch. Package `org.apache.cassandra.db.commitlog`. |
| `make-unit-yaml.sh` | unit | `build/test/mms-<label>.yaml` = the unit yaml + `max_mutation_size: <value>`. |
| `unit-run.sh [upstream\|harness\|all]` | unit | Upstream `GroupCommitLogTest`, then the harness test at 256 KiB, 1 MiB, 2 MiB, unset (2,621,440 B) and the 3 MiB range control. Output `~/stage4-logs/mms/unit/`. |
| `make-node-yaml.sh <label> <value\|none> [default-transport]` | cluster | Rebuilds `conf/cassandra.yaml` from the tag with the 9b hold-fixed settings (batch sync, 10 s write timeout, 64 MiB batch fail threshold, 64 MiB v4 frame and v5 message caps) and the knob. |
| `send-mutation.py` | cluster | Bundled driver, protocol 4: `probe`, `settings`, `insert`, `batch logged\|unlogged`, `readback`. One `OK`/`ERR` line. |
| `jmx.sh` | cluster | `nodetool sjk mx`, one attribute per call (copied from `local_read_size_fail_threshold`). |
| `cluster-run.py` | cluster | Modes `instrument`, `value <1m\|4m\|default>` (Phase 1), `batch <label>` (Phase 2), `derived`, `replay`, `down`. `EXPECTED:` lines in `summary.txt`, `readings.csv`, `session.log` under `~/stage4-logs/mms/<run>/`; stops at a failed instrument or set-up check; node stopped on any exit. |
