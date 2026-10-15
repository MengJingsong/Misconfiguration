# Harness — internode_application_receive_queue_capacity-acquireCapacity-queueCapacity

Stage-4 harness for the case's §9 (frozen §9a `5ef01c26…`, see the results file
[§1](../../results/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md)). Written 2026-10-14 by
the long-path AI session, after the step-0 audit and the freeze. Run from a copy on the node, `~/stage4-harness-run/rqc/`
(compare `md5sum` with the repo first); the run script writes the harness `md5sum` into every `summary.txt`.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `AcquireCapacityTest.java` | unit | Package `org.apache.cassandra.net`; copy into `test/unit/org/apache/cassandra/net/`. A minimal `AbstractMessageHandler` on a Netty `EmbeddedChannel` with `ResourceLimits.Concurrent` reserves and real wait queues; `processUpToOneMessage` is overridden to retry the waiting request through the three-argument `acquireCapacity`. Steps u1 (the `≤` boundary, one byte over borrows one byte), u2 (allow, borrow only the excess), u3 (`INSUFFICIENT_GLOBAL`: nothing taken, `throttledCount` 1, a ticket, no reactivation yet), u4 (`INSUFFICIENT_ENDPOINT`, the global borrow rolled back), u5 (a release lets the wait queue lease the whole 700 B and reactivate the handler on its event loop: retry `SUCCESS`, `q` 1300, reserves 300 / 300, the lease's 400 returned, `throttledNanos > 0`). `STAGE4 check …` lines. | `javac`; `unit-run.sh instrument` (11 `acq`, 3 `rel` lines, `cap=1000`, the lease line `gl=300/700`) |
| `ReceiveQueueWiringTest.java` | unit | Step u6, its own JVM: raw config 123,456 / 654,321 / 777,777 B before `MessagingService` exists; `getInbound()` and a handler from `createHandler()` (urgent, small, large) carry them; a second peer gets its own endpoint reserve and the same global one. | the shakedown unit run |
| `unit-run.sh [upstream\|harness\|instrument\|all]` | unit | Upstream `ResourceLimitsTest`; the two harness tests, one `ant testsome` each; `instrument` runs `AcquireCapacityTest` with `receive-trace.btm`. Output `~/stage4-logs/rqc/unit[-instrument]/`. | — |
| `receive-trace.btm` | both | Byteman, observation only: `acq id= b= out= q= cap= ep=<using>/<limit> gl=<using>/<limit> ms=` at the exit of `acquireCapacity(Limit, Limit, int)`, `rel id= b= q= ms=` at the exit of `releaseCapacity(int)`. The handler id carries the peer and the connection type. | `TestScript`; the instrument run; `Submit -l` on R |
| `hold-handler.btm` | cluster | The trigger, R only: at `MutationVerbHandler.doVerb`'s entry, while `-Dstage4.hold.file` exists, sleep `-Dstage4.hold.ms` (200) and write a `hold thread= ms=` line. (The `new` expression must be parenthesized for Byteman's parser.) | `TestScript`; the thread dump in every held arm |
| `write-load.py` | cluster | The writer: bundled driver, protocol 5, pinned to one sender, CL `ALL`, `INSERT INTO ks.t (pk, v)`, exactly *W* writes in flight for a time or a row count, every `pk` logged with its outcome. Also `probe`, `schema <rf>`, `truncate`. | the shakedown |
| `sample-inbound.py` | cluster | `system_views.internode_inbound` on R (one row per peer: `using_bytes`, `using_reserve_bytes`, `scheduled_bytes`, `throttled_count`, `throttled_nanos`, `expired_count`, …) every 0.5 s until a stop file, or `once`. | the shakedown |
| `Jmx.java` | cluster | JMX client: `get`, `query`, and `poll <ms> <n> <stopfile> <bean> <attr> …` (one JVM; a `CompositeData` prints its `used`). | the shakedown |
| `make-node-yaml.sh <R\|S1..S4> [key=value …]` | cluster | Builds `~/stage4-rqc/<node>/conf` (loopback address 127.0.0.2–.6, JMX 7102–7106, one evenly spaced Murmur3 token, directories, `write_request_timeout: 10000ms`, `auto_snapshot: false`, `native_transport_max_threads: 512` on the senders) plus the extra keys. | the yaml tail is echoed into the log |
| `cluster-run.py ring\|<label>\|down` | cluster | `ring`: wipe, five nodes up, `ks` RF 5. A label is one R lifetime (R restarted with the label's yaml and the agent; read-back from the first `acq` line; `Submit -l` must list 3 rules), then its arms: control, A, B (hold file, *P* writers, class histograms and thread dumps at 1/3 and 2/3 of B, samplers), drain, counters, `TRUNCATE`. `summary.txt` with `EXPECTED:` lines, `arms.csv`, the trace `rqc.trace`, one folder per arm. Labels: `c512k` (B), `c1m` (B, `nohold`), `c4m` (B, `p2`, `p4`, `small`), `c16m` (B), `defres` (B). `RQC_RUN` names the run folder (`run1`); `RQC_B`, `RQC_CTRL`, `RQC_ARMS` override for a shakedown. | the shakedown (`~/stage4-logs/rqc/shakedown*`) |

Run order:

```bash
H=~/stage4-harness-run/rqc
$H/unit-run.sh all
RQC_RUN=run1 $H/cluster-run.py ring
for l in c512k c1m c4m c16m defres; do RQC_RUN=run1 $H/cluster-run.py $l; done   # one background job each
RQC_RUN=run1 $H/cluster-run.py down
```
