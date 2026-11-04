# Harness — batch_size_fail_threshold-verifyBatchSize-failThreshold--guided

Instruments for the case's §9 (stage 4), written 2026-10-20 after the design audit and the step-1 amendments R7 and R8
(frozen §9 hash `a7fa623e…`, results file §1). Run from a copy on the node, `~/stage4-harness-run/bsf/`; both run scripts
write the harness `md5sum` into their `summary.txt`.

| File | Tier | What it is | Checked how |
|---|---|---|---|
| `Alloc.java` | both | `stage4.Alloc`: the bytes the calling thread allocated between `start(tag)` and `end(tag, extra)` (`ThreadMXBean.getThreadAllocatedBytes`), one line per outermost pair; written to `-Dstage4.byteman.out`, flushed per line. Compiled into a jar on the boot class path (the node runs from the jar). | the unit test's known-answer check: an 8 MiB `byte[]` reads 8,396,728 bytes |
| `batch-alloc.btm` | both | Byteman, observation only: `dec` (event loop, `BatchMessage$1.decode`), `exe` (`BatchMessage.execute`), `bst` (`BatchStatement.execute`), `siz` (`verifyBatchSize` entry: mutations, `IMutation.dataSize`, the threshold), `rej` (`verifyBatchSize` throws). | `TestScript` (10 rules, no errors); `Submit -l` lists 10 rules at every node start |
| `SendBatches.java` | both | The client (package `org.apache.cassandra.transport`, on `SimpleClient`, protocol v5): one connection, one batch in flight; UNLOGGED batches of 64 prepared `INSERT INTO ks.t (pk, v)`, `v` a blob of size/64. After each response it joins the request's trace lines and prints one `req` line (format in the file's header). Replaces the `send_batches.py` named in 9c (R4: `SimpleClient`). | — |
| `BatchSizeAllocTest.java` | unit | `CQLTester` in-process server (R8): arms `ctl16k`, `t{50,500,5120}k-b{1,4,16}m`, `C-msg512k-b16m`, 20 batches each; thresholds and the message size set with `DatabaseDescriptor` setters. Fails only on an instrument or set-up error. | known-answer check of `Alloc` |
| `unit-run.sh [run]` | unit | Copies the test, `SendBatches` and `Alloc` into the clone's test tree, builds the boot jar, runs `TestScript`, the test with the agent, then `analyze.py`. Output `~/stage4-logs/bsf/<run>/unit/`. | — |
| `cluster-run.py [run]` | cluster | One node, `-Xms4G -Xmx4G`, two lifetimes: `main` (R1 yaml; idle control; `ctl16k`; thresholds set live over JMX and read back × 1, 4, 16 MiB) and `ctl` (`native_transport_max_message_size` 512 KiB; 16 MiB batches). Per arm: GC, 100 ms JMX poll of heap and the networking pool, GC and `GC.heap_info` after. Output `~/stage4-logs/bsf/<run>/cluster/` (`summary.txt`, `requests.txt`, `arms.csv`, `poll-*.csv`, `system-*.log`). | its own set-up checks stop the run on failure |
| `analyze.py <tier> <req file> <trace> [log]` | both | Per-arm table and `EXPECTED:` lines for validity (V1–V5), the prediction on the rejected pairs (P0–P2, R and F, for the primary `dec + exe` and the secondary `bst`) and the control (C1, C2). | — |
| `make-node-yaml.sh [key=value …]` | cluster | Builds `~/stage4-bsf/conf` from the tag's conf (loopback, data under `~/stage4-bsf/data`) plus the label's keys. Copied from the `native_transport_receive_queue_capacity` harness. | the yaml tail is echoed into `summary.txt` |
| `Jmx.java` | cluster | JMX reader (`get`, `query`, `poll`) plus `setint` (the threshold's live setter). From the `native_transport_receive_queue_capacity` harness. | the threshold is read back after each set |
| `client-logback.xml` | cluster | Client logging: warnings only. | — |

Run order (run 1, 2026-10-20, node `node0.jason92-320876`):

```bash
H=~/stage4-harness-run/bsf
$H/unit-run.sh run1
python3 $H/cluster-run.py run1        # background job; about 15 min
```

The diagnostic of 2026-10-20 (results file §4.2, part 2), which is not part of run 1, is the unit test with `-Dstage4.count=2` and
`-XX:StartFlightRecording=…,settings=profile` added to `test.jvm.args`, read with
`jfr print --events jdk.ObjectAllocationOutsideTLAB,jdk.ObjectAllocationSample --stack-depth 14`.
