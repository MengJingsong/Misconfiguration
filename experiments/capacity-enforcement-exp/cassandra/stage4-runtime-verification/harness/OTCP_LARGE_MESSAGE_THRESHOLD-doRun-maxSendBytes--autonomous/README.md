# Harness — OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous

**What this is.** The stage-4 harness for the autonomous case file, written 2026-10-22 after the step-0 audit.

**Case-file version.** The audit-frozen sha256 is `6b3a899e…`; see the results file
[§1](../../results/OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous.md).

**Where it ran.**
- **Node:** `pc06` (node2 of `jason92-320876`).
- **Harness copy:** `~/stage4-harness-run/otc/`. The md5 of every file is in `run1/harness-md5-*.txt`.
- **Clone:** `~/cassandra-otc` (`cassandra-5.0.9`, `b5f2a54`, `ant build-test`).
- **Logs:** `~/stage4-logs/otc/<run>/`.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `LargeMessageThresholdFrameTest.java` | unit (B2) | In package `org.apache.cassandra.net`. Three methods (`fillAndDrain_C4M`, `_C1M`, `_C4M_repeat`). Each one: (1) fills a `SMALL_MESSAGES` link to C with 1000-byte `_TEST_1` messages while the inbound socket is closed; (2) opens the socket; (3) drains, recording per-frame payload (`onSendSmallFrame`), the networking pool's `usedSizeInBytes` peak minus the pre-drain baseline (1 ms poller plus one sample per frame callback, S4-A2), pendingPeak, sent, errors. It asserts `LARGE_MESSAGE_THRESHOLD = property − 21`. Output is one `RESULT` line per method, also appended to `-Dstage4.out` | compile check; `lmt` assertion in every run |
| `unit-run.sh <run> [V…]` | unit | For V = 16384 · 65536 · 131072 and three repetitions, runs `ant testsome … -Dtest.jvm.args="-Dcassandra.otcp_large_message_threshold=V -Dstage4.out=…"`. It keeps the XML and ant logs and stops at the first failure or property mismatch. It removes the test file at the end | run 1 |
| `make-node-yaml.sh <n1\|n2> [k=v…]` | cluster (B3a/B3b) | Builds the per-node `CASSANDRA_CONF` with B3a's lines and the label's knobs, including S4-A6's receive endpoint key. JMX ports are 7199 / 7299 | yaml diff kept per lifetime |
| `Jmx.java` | cluster (S4-A8) | One JMX connection, 1 s polling. Copied unchanged from `internode_application_send_queue_capacity-releaseCapacity-…--autonomous` | shakedown |
| `cluster-run.py <run> <label>\|analyze\|down` | cluster (B3e) | Runs one lifetime per label (`v16k-r`, `v64k-r`, `v128k-r`, `ctl-r`): start both nodes with the property and NMT, poller, stress (S4-A7), SIGSTOP n2 at t0 + 30 s, histogram at +12 s, NMT at +15 s, SIGCONT at t0 + 50 s, drain and stop, logs copied, data removed. `analyze` applies C1–C7 in S4-A9's order. Daemons are matched by `java` + `CassandraDaemon` + the cwd or conf path | shakedown `shake` (found defect 1: only DOWN lines inside the stall count) |
| `run1-chain.sh <run>` | cluster | Runs the eight lifetimes in interleaved order, then `analyze` | run 1 |

**Run order (run 1).**

```bash
H=~/stage4-harness-run/otc
bash $H/unit-run.sh run1
python3 $H/cluster-run.py shake shake          # instrument check, not counted
setsid nohup bash $H/run1-chain.sh run1 > ~/stage4-logs/otc/run1-chain.log 2>&1 < /dev/null &
python3 -I <results>/run1/selfcheck.py unit ~/stage4-logs/otc/run1/unit/all-results.txt
python3 -I <results>/run1/selfcheck.py cluster ~/stage4-logs/otc/run1/cluster
```
