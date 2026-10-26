# Harness - max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous

Written 2026-10-26 by the stage-4 agent (tag `mh`, node pc12) after the step-0 audit and the freeze (results file section 1).
Run from `~/s4-mh-harness/` on the node (rsync of this folder), tree `~/s4-mh` (copy-source.sh, `ant build-test`).

| File | Tier | What it does |
|---|---|---|
| `HintsFileSizeLimitTest.java` | unit | Package `org.apache.cassandra.hints`; copy to `test/unit/org/apache/cassandra/hints/`. Real `HintsService.instance.write()` + `flushAndFsyncBlockingly()`; one warm-up run (excluded), then L = 1, 4, 16, 128 MiB x 3 reps (4096 hints of 16 KiB), a 65,536 x 1 KiB run at L = 1, and the control: real `StorageProxy.shouldHint` with `max_hints_size_per_host` 16 MiB. Prints `STAGE4 predict/run/control/check` lines. |
| `mh.btm` | both | Byteman, observation only: `roll` (HintsWriteExecutor.java:248, `return false`), `sessclose`, `decide`. |
| `unit-run.sh <tree> <logdir> [plain\|instrument]` | unit | `ant testsome` of the test, with `mh.btm` attached for `instrument` (the run of record). |
| `make-node-yaml.sh <A\|B> [k=v ...]` | cluster | Builds `~/s4-mh-run/<node>/conf` (loopback 127.0.23.1/2, storage 7023/7024, JMX 7323/7324, native 9345/9346, directories, hold-fixed settings). |
| `write-load.py` | cluster | Writer: bundled driver, protocol 5, node A only, CL ONE, 2,048-byte blobs, 1,000 rows/s, `MH_ROWS` rows (400,000); `schema` (RF 2). |
| `Jmx.java` | cluster | JMX client (`get`, `setint`, `query`) on 127.0.0.1. |
| `cluster-run.py arm <label> <L_MiB> [cap_MiB]` | cluster | One fresh ring per arm; samplers; final readings; stops every node. |
| `selfcheck.py` | both | Independent re-parse of the raw logs (written for the self-check). |

Run order: `bash unit-run.sh ~/s4-mh ~/s4-mh-logs/run1/unit instrument`, then
`MH_LOGS=~/s4-mh-logs/run1 python3 cluster-run.py arm L16 16` (L1 = 1, L128 = 128, `CTRL 128 100`), one after another (ulimit -n raised).
