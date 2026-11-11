# Harness — native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided

Instruments for the case's §9 (stage 4), written 2026-10-20 after the step-0 audit (frozen §9 hash `dcad2ce8…`, results
file §1; amendments R1–R4 in the case's 9f). Run from a copy on the node, `~/stage4-harness-run/nqa/` (compare `md5sum`
with the repo first); both run scripts write the harness `md5sum` into their `summary.txt`.

| File | Tier | What it is | Checked how |
|---|---|---|---|
| `nqa.btm` | both | Byteman. `nqa hold` (R2, the stall): at `Dispatcher$RequestProcessor.run` entry an `EXECUTE` waits while the release file (`-Dstage4.release.file`) is absent; `hold in` / `hold out` lines. `nqa chk` (observation): at `Dispatcher.hasQueueCapacity` exit, the head's age, threshold, timeout and verdict (`chk` lines). One trace file, `-Dstage4.trace`. | `TestScript` (2 rules, no errors); `Submit -l` lists 2 rules at every node start |
| `NqaHold.java` | both | `stage4.NqaHold.await(file)`: the rule's helper, polls the file every 10 ms. Boot class path on the node (jar built by `cluster-run.py`); `test/unit/stage4/` in the unit tier. | the unit tier's u0 (4 held, `ActiveTasks` 4) |
| `QueueAgeWriter.java` | both | The fixed-rate writer (replaces 9c's `fixed_rate_writer.py`, R5): one protocol-v5 `SimpleClient` connection with no `THROW_ON_OVERLOAD` startup option (the yaml decides, R3); `EXECUTE` of a prepared `INSERT INTO ks.t (pk, v)` with a 64 KiB blob, request *k* due at *k*/rate, stream id *k*+1, never retried; outcome classes `ok`, `warned`, `ovl_queue`, `ovl_late`, `ovl_bytes`, `ovl_other`, `err`; `r` lines per request, `sec` lines, `TOTAL`. | the unit tier |
| `NqaQueueAgeTest.java` | unit | `CQLTester` in-process server, request pool resized to 4, in-flight limits 1 GiB. u0 (running tasks are not the operand), u1 (`hasQueueCapacity()` at off / above / at / below the head's age; queued bytes unchanged), u2 (throwing refusal), u3 (default mode queues and pauses), u4 (50 req/s × 4 s at threshold off, 0.2, 0.05, 0.01), u5 (global limit 2 MiB control). `STAGE4 check` lines. | `unit-run.sh` (shakedown) |
| `unit-run.sh [run]` | unit | Copies the test, `QueueAgeWriter` and `NqaHold` into the clone's test tree, `TestScript`, the test with the agent. Output `~/stage4-logs/nqa/<run>/unit/`. | — |
| `cluster-run.py <run> <label>…` | cluster | One node lifetime per label (`off1 off2 off3 t0.5 t0.1 t0.02 d0.1 ctl`): yaml (9b hold-fixed + the label's threshold, mode and in-flight limit), JMX read-back of each, `Submit -l`, schema, 10 s idle control, the arm (stall on, 2 s JMX poll, 100 req/s × 60 s, final sample and class histogram at `sendend` + 2 s, release, every response awaited), node stopped. `EXPECTED:` lines per arm, then `JUDGE` lines with R4's edges over `arms.csv`. Output `~/stage4-logs/nqa/<run>/cluster/`. | its own set-up checks stop the run on failure |
| `make-node-yaml.sh [key=value …]` | cluster | `~/stage4-nqa/conf` from the tag's conf (loopback, data under `~/stage4-nqa/data`) plus the label's keys. From the `batch_size_fail_threshold` harness. | the yaml tail is echoed into `summary.txt` |
| `Jmx.java` | cluster | JMX reader (`get`, `query`, `poll`), unchanged from the `native_transport_receive_queue_capacity` harness. | — |
| `client-logback.xml` | cluster | Client logging: warnings only. | — |

Run order (run 1, 2026-10-20, node `pc13` = `node3.jason92-320876`):

```bash
H=~/stage4-harness-run/nqa
$H/unit-run.sh run1
python3 $H/cluster-run.py run1 off1 t0.5 t0.1 t0.02 off2 d0.1 ctl off3     # one background job, about 20 min
```
