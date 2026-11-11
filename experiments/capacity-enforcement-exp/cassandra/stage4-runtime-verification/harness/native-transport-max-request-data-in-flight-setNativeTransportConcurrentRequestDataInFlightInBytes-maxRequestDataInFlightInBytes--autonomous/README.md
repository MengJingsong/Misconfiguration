# Harness — native_transport_max_request_data_in_flight · setNativeTransportConcurrentRequestDataInFlightInBytes, autonomous

Written 2026-10-26 (set A batch 8, tag `cr`, node `pc12`, port slot 5) after the step-0 audit and the freeze. Case amendments (2026-10-26) are in the
case file next to B2/B3; results in `../../results/native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous.md`.

| File | Tier | Use |
|---|---|---|
| `GlobalInFlightLimitProbe.java` | unit | `main` class in package `org.apache.cassandra.transport` (Allocator is package-private); modes `sweep L`, `control L`, `default`, `v4`, `msg-default`, `msg-explicit`; `CHECK ... OK|MISMATCH` lines; `-Dprobe.mutant=1` makes the sweep expectation wrong on purpose (instrument check) |
| `unit-run.sh [instrument]` | unit | compiles the probe against the tree's `build/classes/main`, runs one fresh JVM per mode (`-Xmx512m`, jvm11 client options, own yaml), logs to `~/s4-b8-cr-logs/unit/`; `instrument` = mutant sweep must MISMATCH, v4 mode must see usage > L |
| `NativeFlood.java`, `flood-logback.xml` | cluster | the `SimpleClient` flood of the `native_transport_receive_queue_capacity` harness plus `--version 4\|5`; C connections x W in-flight `SELECT pk FROM ks.t WHERE pk = 0 AND v = ? ALLOW FILTERING` with a blob value |
| `hold-request.btm` | cluster | Byteman: at `Dispatcher.processRequest` entry, a request whose text starts `QUERY SELECT pk FROM ks.t ` sleeps 100 ms while `-Dstage4.hold.file` exists; one `hold` line each |
| `InflightProbe.java` | cluster | JMX sampler every 200 ms: `Client.RequestsSize`, `Client.PausedConnections`, `BufferPool direct` `MemoryUsed`/`Count`, heap used |
| `cluster-run.sh LABEL L ARM [live]` | cluster | one arm: conf, node start (heap 1 GiB, Netty on JDK direct buffers, NMT, Byteman 19150, JMX 7150, 127.0.5.1, data on /dev/shm), Byteman check, schema, warm-up, 30 s baseline, probe + NMT + histograms, flood, first-trigger check, stop node by PID, `reduce.py` |
| `reduce.py RUN_DIR L ARM LIVE` | cluster | readings and `EXPECTED:` lines per amended B3f (no verdict is chosen by the script) |
| `cluster-all.sh` | cluster | the 16 arms of run 1 in order |

Copy the folder to the node (`~/s4-b8-cr-harness`), tree `~/s4-b8-cr` made by `copy-source.sh` and `ant build-test` (never rebuilt afterwards).

`cluster-run.sh` after run 1: the optional `HIST_TOP=1` (diagnostic arms `x1-*`, top of the 60 s class histogram) was added; run 1 (arms `p1-*`, `p2-*`) used the earlier version (see results 1.2 for its sha256).
