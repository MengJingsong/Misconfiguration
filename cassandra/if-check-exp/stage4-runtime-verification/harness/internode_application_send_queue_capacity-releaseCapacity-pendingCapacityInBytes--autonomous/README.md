# Harness — internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous

Stage-4 harness for the autonomous case file (audit-frozen sha256 `658ca786…`; after runbook defect 2's dated amendment
`b48dd16e…`; see the results file
[§1](../../results/internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.md)). Written
2026-10-21 after the step-0 audit. Run on `pc13` (node3 of `jason92-320876`) from a copy in `~/stage4-harness-run/sq2/` (md5 of
every file in `run1/harness-md5-*.txt`), against `~/cassandra-sq2` (`cassandra-5.0.9`, `b5f2a54`, `ant build-test`). Logs go to
`~/stage4-logs/sq2/<run>/` on the node, outside the repo. Reuses `Jmx.java`, `sample-vt.py` and the shape of `make-node-yaml.sh`
from the receive-side twin (`internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous`).

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `SendQueueCapacityProbeTest.java` | unit (B2) | Package `org.apache.cassandra.net`; copied into the clone by `unit-run.sh` and removed after. `u1Accounting`: U1 (`unsafeAcquireCapacity(1000)` to the first failure, then releases of 1000 with the invariant `endpoint == max(0, pending − C) == global` after every step) and U1-stress (16 threads × 200 cycles, barrier checks, amendment A1's band) at C = 64 KiB · 1 MiB · 4 MiB, R_e 256 KiB, R_g 1 MiB; the peer is a dead loopback port and no enqueue happens, so the link is never failing-to-connect. `u2HeapConnected`: the B2h M = 0 control and U2 at C = 8 · 32 · 128 MiB, R_e = R_g = 1 MiB, an in-process inbound socket; **delivery is blocked by parking the link's event-loop thread** (runbook defect 2). `u3FailingToConnect`: U3 at C = 8 · 32 MiB, a dead port, `connectionAttempts ≥ 2` first (A3). One `PROBE` line per reading and `STAGE4 check … ok\|MISMATCH` per assertion; with `-Dstage4.histo=<dir>` a class histogram of the test JVM at each U2 heap reading (diagnostic). | compile check; attempt 1 (results §3) |
| `unit-run.sh <run> [base\|probe\|mutants\|all]` | unit | `ConnectionTest#testAcquireReleaseOutbound,testInsufficientSpace` (B2e step 2); the probe three times (B2e steps 3–4); amendment A2's mutants in a throw-away clone `~/cassandra-sq2-mut`: M1 (`:452` releases `bytes`), M2 (`:449` guard → `if (true)`), each with `u1Accounting` only; the mutated class files are deleted before the build (runbook defect 1) and the bytecode of `releaseCapacity` is printed as proof. | attempt 1 found defect 1 |
| `make-node-yaml.sh <A\|B> [k=v …]` | cluster (B3a) | A = 127.0.0.1 (JMX 7199, seed), B = 127.0.0.2 (JMX 7299); B3a's lines for both (hints off, 60 s write timeout, phi 16, tcp_user_timeout 0, offheap_objects with 64/512 MiB) plus `native_transport_timeout: 60000ms` (A4); B `auto_bootstrap: false` (harness choice: empty ring); A gets the label's four knobs. Data under the tmpfs `~/stage4-sq2/nodes/<node>` (A9). | yaml diff kept per label |
| `Jmx.java` | cluster (B3d, A6) | `poll`: one JMX connection to A, every 1 s: `Connection,scope=127.0.0.2_7000` Small `PendingBytes`, `PendingTasks`, `DroppedBytes/TasksDueToOverload`, `DroppedTasksDueToTimeout`, `CompletedTasks`, Urgent/Large `PendingBytes`, Urgent/Large overload drops, heap used. | shakedown (beans resolve) |
| `sample-vt.py` | cluster (A6) | `system_views.internode_outbound` on A every 1 s (`pending_bytes`, `using_reserve_bytes`, `overload_count`, `expired_count`, …) with the in-tree Python driver. | shakedown |
| `cluster-run.py <run> <label>\|analyze\|down\|reanalyse <label>` | cluster (B3e) | One lifetime per label (wipe, both yamls, start A then B, pollers, `cassandra-stress` 90 s at 30,000/s = t0, histogram at t0 + 18 s, SIGSTOP B at t0 + 20 s, histogram + heap info at pause + 12 s, SIGCONT at pause + 30 s, 25 s drain, final vt read, logs copied, both nodes stopped with B SIGCONTed first, no daemon of this clone left). Labels `c4m c64m c256m` (reserves 1 MiB), `pos` (C 4 MiB, reserves 128 MiB), `neg` (C 64 MiB, B never stopped; its "plateau" histogram at t0 + 32 s), `shake` (shakedown). `analyze`: A7's noise N, ΔH, k. A daemon is matched by `java` + `CassandraDaemon` + cwd = the clone (or this run's conf path): its command line names the clone only as `bin/../`. | shakedown 1 (two harness fixes, below) |
| `run1-chain.sh` | cluster | the five labels in order, then `analyze`. | — |

Harness fixes before the cluster run (shakedown, not readings): the first daemon matcher looked for the clone path in the
command line and missed the running node (fixed as above; the orphaned node was stopped with `nodetool stopdaemon`); a
`None` format error in the analysis; the OOM count matched the `HeapDumpOnOutOfMemoryError` flag (now `java.lang.OutOfMemoryError`).

Run order (run 1):

```bash
H=~/stage4-harness-run/sq2
bash $H/unit-run.sh run1 all
sudo mount -t tmpfs -o size=40g,mode=1777 tmpfs ~/stage4-sq2/nodes
setsid nohup bash $H/run1-chain.sh > ~/stage4-logs/sq2/run1-chain.log 2>&1 < /dev/null &
python3 <results>/run1/selfcheck.py ~/stage4-logs/sq2/run1      # the self-check
sudo umount ~/stage4-sq2/nodes
```
