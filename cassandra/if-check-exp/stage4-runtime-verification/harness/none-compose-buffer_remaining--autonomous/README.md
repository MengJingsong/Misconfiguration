# Harness — none-compose-buffer_remaining--autonomous

Stage-4 harness for the autonomous case file, unit tier B2 as amended on 2026-10-29 (frozen sha256 in the results file
[§1](../../results/none-compose-buffer_remaining--autonomous.md)). Run on `pc41` against the copy `~/s4-none` (`copy-source.sh`, `ant build-test`). Logs: `~/stage4-logs/none/compose/<run>/` on the node
(outside the repo). Designed from `none-type-design.md` (operand sweep) and the drafts file; the instrument is the per-call
`ThreadMXBean.getThreadAllocatedBytes` window of `harness/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided/Alloc.java`.

| File | What it does |
|---|---|
| `ComposeProbe.java` | package `org.apache.cassandra.cql3.functions`; cells (type, L) for `BytesType`, `IntegerType`, `Int32Type`, a null buffer; window around one `UDFDataType.compose`; noise-floor repeats; C1; the positive control `BytesType.read` of a 2048 vint with max 1024. |
| `compose.btm` | Byteman rule `AT LINE 180` of `compose`, action `stage4.Count.hit()`. |
| `Count.java` | package `stage4`: a static counter the Byteman rule increments (no allocation). |
| `unit-run.sh [run] [shake]` | compiles the probe into `~/stage4-logs/none/compose/<run>/classes` (the tree is never touched), type-checks the rule with Byteman `TestScript`, runs one fresh JVM per value and pass (A: no agent; B: Byteman counter), `summary.txt`. |
| `analyze.py <run dir>` | prints the readings and one `EXPECTED:` line per frozen prediction. |
| `selfcheck.py <run dir>` | independent re-parse of the raw `test-A.out`/`test-B.out`; evaluates every frozen prediction again from the raw lines. |

Order: `./unit-run.sh run1 && python3 analyze.py ~/stage4-logs/none/compose/run1 && python3 selfcheck.py ~/stage4-logs/none/compose/run1`.
The single `shake` run of 2026-10-29 (one value, run name `shake`) was a pre-run shakedown of the probe, disclosed in the results file §3.
