# Harness — batch_size_warn_threshold-verifyBatchSize-size--autonomous

Instruments for the case's B2 (unit) and B3 (cluster) as amended A1–A8 (case file section D1, 2026-10-26; frozen
tables in results §1). Written 2026-10-26 after the audit and freeze, before run 1. Parts adapted from the closed
`batch_size_fail_threshold-verifyBatchSize-failThreshold--guided` harness (`Alloc.java`, `Jmx.java`, `client-logback.xml`
unchanged; `make-node-yaml.sh`, the Byteman rules and the runner adapted). Port slot 1: node on 127.0.1.1, JMX 7110, Byteman
agent 19110; native 9042 on 127.0.1.1 only. Working trees from `copy-source.sh`: `~/s4-b9-bs-u` (`ant build-test`, unit tier)
and `~/s4-b9-bs-n` (`ant jar`, node; never `ant` in a tree a node runs from).

| File | Tier | What it is | Checked how |
|---|---|---|---|
| `Alloc.java` | both | `stage4.Alloc`: bytes the calling thread allocated between `start(tag)` and `end(tag, extra)`; boot class path jar | known-answer: an 8 MiB `byte[]` reads 8,396,728 B (`STAGE4 check`) |
| `warn-size.btm` | both | Byteman, observation only: `dec`, `exe`, `bst` (allocation), `siz` (`verifyBatchSize` entry: mutations, `IMutation.dataSize`, warn and fail bytes), `rej` (it threw) | `TestScript` 10 rules type checked; `Submit -l` lists 10 at every node start; 10 s idle control with no trace line |
| `WarnBatches.java` | both | protocol-v4 `SimpleClient`, one batch in flight; LOGGED or UNLOGGED; `req` lines with outcome and the client warnings (`is of size N`). `--random true` (cluster) makes incompressible values; the unit run 1 used the zero-filled version (md5 `5c0fb0adb0ea`) | shakedown (not a reading) |
| `BatchWarnProbeTest.java` | unit | `CQLTester` in-process server (A1): 3 warm-up arms, then `w{1,5,1024,65536}-p{20,200}`, `sp-w1`, `fc`, `inv`, 20 batches each, a fresh table per arm | fails only on an instrument error; known-answer check |
| `unit-run.sh [run]` | unit | copies the test into `~/s4-b9-bs-u`, builds the helper jar, `TestScript`, `ant testsome` with the agent, `analyze.py unit` | `EXPECTED:` lines |
| `make-node-yaml.sh` | cluster | `~/s4-b9-bs-node/conf` from the tag's conf: slot-1 loopback, data under `/dev/shm/s4-b9-bs`, JMX port 7110, 64 MiB frame and message limits, 128 MiB in-flight limits, plus `key=value` arguments | yaml tail echoed into `summary.txt` |
| `Jmx.java` | cluster | JMX reader (`get`, `poll`) and `setint` (the warn threshold's live setter) | value read back after each set |
| `cluster-run.py [run]` | cluster | three node lifetimes (L1 warn 5 KiB then live 90000 KiB; L2 warn 90000 KiB; L3 fail 20 KiB control, then warn 200 KiB inversion), `-Xms2G -Xmx2G`, GC log, per-phase flush, data-directory bytes, write count; `analyze.py cluster` | each set-up check stops the run; node stopped on any exit |
| `analyze.py` | both | per-arm/phase table and `EXPECTED:` lines (V = validity, P = prediction, C = control, I = inversion arm) | — |

Run order (run 1, 2026-10-26, node `pc07`):

```bash
H=<repo>/cassandra/if-check-exp/stage4-runtime-verification/harness/batch_size_warn_threshold-verifyBatchSize-size--autonomous
ulimit -n 100000
bash $H/unit-run.sh run1                 # about 1 min; output ~/s4-b9-bs-logs/run1/unit/
python3 $H/cluster-run.py run1           # background job; output ~/s4-b9-bs-logs/run1/cluster/
```

Shakedowns (`shake`, 2 batches per unit arm and 10 per W1 phase) check the plumbing only; their readings are not used.
