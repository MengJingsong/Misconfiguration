# Harness — internode_max_message_size-inferMessageSize-size--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `46d2788e…`, see the results file
[§1](../../results/internode_max_message_size-inferMessageSize-size--autonomous.md)). Written 2026-10-20 after the step-0
audit and the freeze. Run on `pc57` from this folder against a fresh clone `~/cassandra-run5` (`cassandra-5.0.9`,
`b5f2a54210`, `ant build-test`). Logs go to `~/stage4-logs/imm/<run>/` on the node, outside the repo.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `InferMessageSizeLimitTest.java` | unit (B2) | Package `org.apache.cassandra.net`; copied into the clone's `test/unit/org/apache/cassandra/net/` by `unit-run.sh` and removed after. A `Verb._TEST_2` message with a raw *P*-byte payload, serialized at the current version, fed to `Message.serializer.inferMessageSize`. For *L* = 64 KiB, 1 MiB, 16 MiB: *P* = *L* − 1 KiB, size exactly *L* and *L* + 1, *P* = 2*L* and 8*L*; the limit at size and size − 1 on the same bytes; the header and length vint only (payload absent), and one byte less. Controls: the 8 × 16 MiB message at `Integer.MAX_VALUE − 1` (the largest value `DataStorageSpec.IntBytesBound` accepts), a 4 MiB message at 16 MiB and 1 MiB. One `STAGE4 case` and one `STAGE4 check … ok\|MISMATCH` line per step. | the upstream `MessageTest` (9/9) beside it; the shakedown (36 checks, 0 mismatches at both heaps) |
| `unit-run.sh <run>` | unit | Upstream `MessageTest`; the harness test at the default test heap (1 GiB) and again at 2 GiB; the case lines of the two heaps compared. The 2 GiB run uses `build-stage4.xml`, a temporary copy of `build.xml` with `maxmemory="2048m"`, because `build.xml`'s `maxmemory="1024m"` is placed after `test.jvm.args` and overrides an `-Xmx` there; the test prints `maxMemory` to show the heap took effect. | the shakedown (`maxMemory` 1,056,309,248 and 2,130,051,072) |
| `make-node-yaml.sh <A\|B> [key=value …]` | cluster (B3a) | `~/stage4-imm/<node>/conf`: the tag's yaml plus A = 127.0.0.1 (JMX 7199, the seed) or B = 127.0.0.2 (JMX 7299), `num_tokens: 4`, `SimpleSnitch`, `commitlog_segment_size: 32MiB`, `hinted_handoff_enabled: false` (amendment R3), all directories under `~/stage4-imm/<node>/` on local disk, and the run's `internode_max_message_size`; `-XX:MaxDirectMemorySize=1G` in `jvm11-server.options`. `native_transport_max_message_size` not set (amendment R4). | the yaml tail echoed into the summary; the read-back |
| `client.py` | cluster (B3c) | Bundled Python driver, protocol 5, whitelist one host, no driver retries: `schema` (ks RF 2, `ks.t (k int PRIMARY KEY, v blob)`), `setting` (a `system_views.settings` row), `write` (*n* INSERTs of *S* random bytes at CL ALL, one after another, each logged with its outcome), `count` (CL ONE). | the shakedown |
| `Jmx.java` | cluster (B3d) | JMX client copied from the `internode_application_receive_queue_capacity` harness: `get`, `query`, `poll`. | the shakedown |
| `cluster-run.py <label> <rep> \| analyze \| down` | cluster (B3e) | One lifetime of both nodes per call: wipe, yaml, start A then B, UN, schema, the limit's read-back from `system_views.settings` on both nodes, `jcmd GC.run` on B and the baseline, a 10 s control, then 20 writes at each of 512 KiB, 4 MiB, 12 MiB (5 s settle each). B sampled every 200 ms (direct pool `MemoryUsed`/`Count`, heap, networking pool `Size`/`UsedSize`/`OverflowSize` — amendment R2 —, inbound counters from A, VmRSS); the 1 s readings of B3d are the first sample of each second, and both are reported. Then per-size counter deltas (B's and A's local writes to `ks.t`, B's inbound bytes and errors, dropped MUTATION), `tpstats`, flush, `tablestats`, `count(*)` at ONE through each node, the "exceeds allowed maximum" and "terminating connection" lines of both logs. `summary.txt` with `EXPECTED:` lines, `phases.json`, `samples.csv`, `keys.csv`. Labels: `R0` default/default (amendment R1), `R1` 16/16 MiB, `R2` 16/1 MiB, `R3` 1/1 MiB; `<rep>` 1 or 2 (B3h). `analyze` writes the cross-run B3f relation (R2's 12 MiB peak against R1's). | the shakedown (`IMM_RUN=shakedown IMM_N=3`) |

Run order (run 1):

```bash
H=<this folder>
CASSANDRA_HOME=~/cassandra-run5 $H/unit-run.sh run1
for rep in 1 2; do for l in R0 R1 R2 R3; do IMM_RUN=run1 $H/cluster-run.py $l $rep; done; done   # one background job
IMM_RUN=run1 $H/cluster-run.py analyze
```
