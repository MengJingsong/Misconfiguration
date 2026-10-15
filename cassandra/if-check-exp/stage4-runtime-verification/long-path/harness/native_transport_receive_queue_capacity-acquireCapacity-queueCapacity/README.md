# Harness — native_transport_receive_queue_capacity-acquireCapacity-queueCapacity

Stage-4 harness for the case's §9 (frozen §9a `892454c7…`, see the results file
[§1](../../results/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md)). Written 2026-10-15 by
the long-path AI session, after the step-0 audit and the freeze. Run from a copy on the node, `~/stage4-harness-run/ntq/`
(compare `md5sum` with the repo first); the run script writes the harness `md5sum` into every `summary.txt`.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `NativeQueueModesTest.java` | unit | Package `org.apache.cassandra.transport`; copy into `test/unit/org/apache/cassandra/transport/`. Extends `NativeProtocolLimitsTestBase` (in-process server, protocol v5). One `@Test` running steps u0–u6 of the amended 9e in order: *M*; throwing small (refusal = `OverloadedException` + `RequestDiscarded` + 1, not decoded, the `≤` boundary at 3*M*); default small (decoded while `queueSize` stays at *C*, the connection paused, the warning, `queueSize` −*M* after the releases, the paused request served when the reserve frees); the drift's effect (*C* + *M* admitted with no refusal); default large (refused and not decoded, waits for the reserve even with `queueSize` 0, `queueSize` 0 at the end); throwing large; wiring (capacity per new connection, the mode per connection). Reads the server's own handler by reflection on its event loop; requests wait at a gate (`awaitGate()`). `STAGE4 check …` lines; fails at the end on any mismatch. | `javac`; `unit-run.sh instrument` |
| `unit-hold.btm` | unit | The unit trigger: at the entry of the static `Dispatcher.processRequest(Channel, Request, Overload, RequestTime)`, a request of `ntq_unit` calls `NativeQueueModesTest.awaitGate()`. | `TestScript` |
| `ntq-trace.btm` | both | Byteman, observation only, server `CQLMessageHandler`s only: `new`, `acq`, `rel`, `dec`, `rls`, `disc`, `ldisc`, `wake` lines (format in the file's header). | `TestScript`; `unit-run.sh instrument` (every kind appears); `Submit -l` at every node start |
| `hold-request.btm` | cluster | The trigger: at the same `Dispatcher.processRequest` entry, a `QUERY SELECT pk FROM ks.t` request sleeps 500 ms while the hold file exists; one `hold` line each. | `TestScript`; the shakedowns |
| `NativeFlood.java` | cluster | The client (package `org.apache.cassandra.transport`, on `SimpleClient`, protocol v5): *N* connections of one mode, *W* requests in flight each, a 100 ms retry after an `OverloadedException`, per-second and total counts (ok, warned, overload by text, other errors), drains before closing. Compiled by `cluster-run.py` into `~/stage4-harness-run/ntq/classes`; logging from `flood-logback.xml`. | the shakedowns |
| `Jmx.java` | cluster | JMX reader (`get`, `query`, `poll`), copied unchanged from the `internode_application_receive_queue_capacity` harness. | — |
| `make-node-yaml.sh [key=value …]` | cluster | Builds `~/stage4-ntq/conf` (127.0.0.1, directories under `~/stage4-ntq/data`, the 9b hold-fixed keys) plus the label's keys. | the yaml tail is echoed into `summary.txt` |
| `cluster-run.py <label>\|down` | cluster | One node lifetime per label (`c128k`, `c512k`, `c1m`, `c4m`, `nsweep`, `defres`): start with the agent, check `Submit -l` (9 rules), schema, then the label's arms; per arm the client, meters, `Jmx` poll, class histograms (B arms), trace analysis and `EXPECTED:` lines per §9a prediction; `summary.txt`, `arms.csv`, one folder per arm with `handlers.csv` and `series.csv`. `NTQ_RUN` names the run folder; `NTQ_ARMS`, `NTQ_SCALE` only for shakedowns. | the shakedowns |
| `unit-run.sh [upstream\|harness\|instrument\|all]` | unit | Upstream `ClientResourceLimitsTest`; the harness test with `unit-hold.btm`; `instrument` adds `ntq-trace.btm` and counts every line kind. Output `~/stage4-logs/ntq/<run>/unit[-instrument]/`. | — |

Run order:

```bash
H=~/stage4-harness-run/ntq
NTQ_RUN=run1 $H/unit-run.sh all
for l in c128k c512k c1m c4m nsweep defres; do NTQ_RUN=run1 $H/cluster-run.py $l; done   # one background job each
```
