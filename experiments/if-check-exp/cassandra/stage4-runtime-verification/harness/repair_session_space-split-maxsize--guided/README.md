# Harness — repair_session_space-split-maxsize

Stage-4 harness for the case's §9 (frozen §9 hash `92f86a2d…`, see the results file
[§1](../../results/repair_session_space-split-maxsize--guided.md)). Written 2026-10-14 by the long-path AI session, after the
step-0 audit. Run from a copy on the node, `~/stage4-harness-run/rss/`, or from the repository on a node that mounts it;
the run scripts log the harness `md5sum`.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `RepairSessionSpaceTreeTest.java` | unit | Package `org.apache.cassandra.repair`; copy into `test/unit/org/apache/cassandra/repair/`. U1 the check alone (`RandomPartitioner`, *M* = 2, 1024, 16384: first `false` at `size == M`, 1,000 further refusals, allocation per call by `ThreadMXBean`); U2 `init()` (*M* = 2, 1024, 16384, 1000 → 512, leaves counted by walking the tree); U3 the depth table for both partitioners, the derivation through a real `ValidationManager.submitValidation` (init path at *s* = 1, 2, 4 on 2^14 keys; split path at *s* = 1, 2 on 2^16 keys, one row each; depth cap 10 at *s* = 64); U4 the overflow (*s* = 2047, 2048, 4096, 4097, 5120, init path). Prints `STAGE4 check <name> expected=… actual=… ok\|MISMATCH` and `STAGE4 value …`; fails at the end on any mismatch. | `unit-run.sh instrument` |
| `unit-run.sh [upstream\|harness\|instrument\|all]` | unit | Upstream `MerkleTreeTest`, `ValidatorTest`; the harness test; `instrument` runs `u3Derivation` with `split-trace.btm` attached. Output `~/stage4-logs/rss/unit[-instrument]/`. | — |
| `split-trace.btm` | both | Byteman, observation only: `split refused` at `MerkleTree.java:410`, `split toodeep` (false with `size < maxsize` at exit), `samples=<numKeys>` at `keys.clear()` in `Validator.prepare()`, and `split calls=<n>` per validation at `Validator.complete()` entry. | `TestScript`: no errors; the instrument run |
| `hold-trees.btm`, `Rss.java` | cluster | Byteman, N2 only: while `~/stage4-rss/N2/hold.flag` exists, `Validator.complete()` sleeps 20 s after writing `hold start`. `Rss.java` (compiled into a jar on the boot class path) holds the flag test and the sleep, because Byteman 4.0.20 cannot parse `new` in a condition. | `TestScript`: no errors; the shakedown |
| `Jmx.java` | cluster | JMX client on 127.0.0.1: `get`, and `setint` with read-back. | the shakedown |
| `make-node-yaml.sh <N1\|N2> <partitioner> <token> [k=v …]` | cluster | Builds `~/stage4-rss/<node>/conf` (loopback address, JMX port 7102/7103, token, partitioner, directories, `concurrent_merkle_tree_requests: 1`). | the yaml tail is echoed into the log |
| `cluster-run.py <label>` | cluster | Labels `m-setup`, `m-control`, `m-a`, `m-b`, `m-c`, `m-depth` (arm M), `o-scratch`, `o-setup`, `o-run` (arm O), `down`. Predictions from the unit tier's depth table; `EXPECTED:` lines in `~/stage4-logs/rss/<label>/summary.txt`, `readings.csv`, `session.log`. Stops on a failed set-up or instrument check (knob read-back, a missing log or trace line, a hold that never starts), stopping both nodes. | the shakedown (`RSS_ROWS=65536`, logs `~/stage4-logs/rss-shakedown/`) |

Run order (each label is its own background job; read `summary.txt`):

```bash
H=~/stage4-harness-run/rss
$H/unit-run.sh all
for l in m-setup m-control m-a m-b m-c m-depth down o-scratch o-setup o-run down; do $H/cluster-run.py $l || break; done
```
