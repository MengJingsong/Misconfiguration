# Harness — flushLowWaterMark-doRun-flushLowWaterMark--autonomous

Stage-4 harness for the autonomous case file. It was written 2026-10-22 after the step-0 audit. Case-file sha256 values:
- as filed: `16b0da55…`
- audit-frozen: `f754e36f…`
- after runbook defects 1–2: `b797d658…`

See the results file
[§1](../../results/flushLowWaterMark-doRun-flushLowWaterMark--autonomous.md). The run was on `pc13` (node3 of `jason92-320876`),
from a copy in `~/stage4-harness-run/flw/`; the md5 of every file is in `run1/unit/harness-md5.txt` and
`run1/cluster/harness-md5-cluster.txt`. The trees:
- `~/cassandra-flw`: `cassandra-5.0.9`, `b5f2a54`, `ant build-test`; this is V0.
- `~/cassandra-flw-p1..p4`: V1–V4, the patched copies. They were removed after the run.

Logs are in `~/stage4-logs/flw/` on the node, outside the repo. `Jmx.java` and `sample-vt.py` are reused from the closed
`internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous` harness.
`make-node-yaml.sh` follows the shape of that harness's version.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `FlushWaterMarkProbeTest.java` | unit (B2) | Package `org.apache.cassandra.net`; `unit-run.sh` copies it into the clone and removes it after. **`handshake`** is the step-1 check: one message through the in-test TCP proxy, with the template and established settings read back. **`sweep`** runs B2b–B2e: S0, the L-set (H 1 MiB, L 1024 · 32768 · 524288 · 1040384) and the P-set (H 64 KiB · 1 MiB · 8 MiB, L = H/2), three repetitions each. Each run writes one CSV row: S, N, U, P, R statistics, resume-send levels, the counts of flips, guard misses and inference errors (amendment A2), read-back, and handled vs. enqueued. The H/L fields are set by reflection on the settings object before the connection is built. | compile; `handshake` passed (proxy in path, (H, L) read back) |
| `unit-run.sh <label> handshake\|sweep` | unit | `ant testsome … -Dtest.methods=<m> -Dtest.timeout=1800000 -Dtest.jvm.args=-Dstage4.csv=…` (A1); keeps the ant log, JUnit XML and CSV; removes the test file and its class files; checks that no test JVM is left and nothing listens on 7012. | — |
| `build-variants.sh` | cluster (B3a, A5) | Runs `ant jar` on V0. For V1–V4: `cp -a`, the line-104 `sed`, delete `OutboundConnectionSettings*.class` (Ant's 1 s timestamps), `ant jar`. Prints line 104 and `javap -c` of the two-argument constructor read from the jar that `bin/cassandra` loads (B3h). | `run1/step1/build-variants.log`: the ldc/sipush constants of all five jars are as intended |
| `make-node-yaml.sh <A\|B>` | cluster (B3a, A5) | A = 127.0.0.1 (JMX 7199, seed), B = 127.0.0.2 (JMX 7299, `auto_bootstrap: false`). B3a's lines, **without the two 4 KiB socket-buffer lines** (runbook defect 1). Data goes on the tmpfs `~/stage4-flw/nodes/<node>`. | shakedowns |
| `flw.btm.in` | cluster (A8) | Byteman observation rules on node A, with output to a file through `traceOpen`. **STALL** fires `AFTER INVOKE promiseToExecuteLater` in `doRun`: flushingBytes plus the running connection's H and L. **RESUME** fires at the first `doRun` entry after a stall that finds `isWritable` true again. The first version used `AT LINE 857`, which Byteman injected at the inlined `finally` (line 902, offset 104): runbook defect 2. | `TestScript` type check; shakedown `diag3` |
| `Jmx.java` | cluster (A7) | A persistent JMX poller at 500 ms: networking `UsedSize`, direct `MemoryUsed`, Small/Urgent `PendingBytes` and Small overload drops to 127.0.0.2, heap. | shakedown |
| `sample-vt.py` | cluster (A7, A10) | `system_views.internode_outbound` every 2 s, plus `active_connections` and the connection-attempt columns. | shakedown |
| `cluster-run.py <run> <V> <rep>\|analyze\|reanalyse\|down\|shake` | cluster (B3e) | One lifetime: wipe; both yamls; start A (Byteman), then B; samplers; stress `duration=60s fixed=20000/s` (A6) at t0; SIGSTOP B at t0 + 15 s; SIGCONT at t0 + 40 s; 10 s drain; stop the samplers; copy logs; stop both nodes (B SIGCONTed first, on any exit); check for leftovers. Daemons are matched by `java` + `CassandraDaemon` + cwd. D uses the pre window [pause − 11, pause − 1] s and the plateau window [pause + 10, pause + 22] s (A7). `analyze` prints the A9 relations. | `shakedown1` (found defects 1 and 2), `diag1`–`diag3` |
| `run1-chain.sh <run>` | cluster | V0..V4 for rep 1, then rep 2, then `analyze`. | — |

Run order (run 1), from `pc07`:

```bash
H=~/stage4-harness-run/flw
bash $H/unit-run.sh step1-handshake handshake     # step 1
bash $H/unit-run.sh run1-unit sweep               # unit tier, run 1
bash $H/build-variants.sh
sudo mount -t tmpfs -o size=40g,mode=1777 tmpfs ~/stage4-flw/nodes
setsid nohup bash $H/run1-chain.sh run1 > ~/stage4-logs/flw/run1/run1-chain.log 2>&1 < /dev/null &
python3 <results>/run1/selfcheck.py unit|cluster …   # the self-check
sudo umount ~/stage4-flw/nodes; rm -rf ~/cassandra-flw-p{1,2,3,4}
```
