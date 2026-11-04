# Harness — internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `d2bc53b0…`, see the results file
[§1](../../results/internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous.md)).
Written 2026-10-22 after the step-0 audit. Run on `pc06` (node2 of `jason92-320876`) from a copy in `~/stage4-harness-run/rsv/`
(compare `md5sum` with this folder first), against `~/cassandra-rsv` (`cassandra-5.0.9`, `b5f2a54`, built with `ant build-test`).
Logs go to `~/stage4-logs/rsv/<run>/` on the node, outside the repo. Reuses the closed sibling
`internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous` (hold rule, trace, yaml maker, samplers,
`Jmx.java`, the `Setup` of its unit test, the mutant runner), re-aimed at the reserve side of the check: the target node of the
case file is node A, the sender is node B (the sibling had them the other way round).

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `AcquireExcessProbeTest.java` | unit (B2c–B2f, R1–R2) | Package `org.apache.cassandra.net`. A real `InboundMessageHandler` on an `EmbeddedChannel` driven through `acquireCapacity(Limit, Limit, int)` / `releaseCapacity`. Methods: `sequential` (Q 1 KiB · 64 KiB × G 128 KiB · 512 KiB · 2 MiB, E 256 KiB, S 16 KiB: successes, refusal outcome, `E.using == G.using`, ≤ limits, `throttledCount` +1 for the outer form), `control` (Q ≥ offered: reserves untouched), `hook` (H1, H2, H1b: a `Limit` wrapper whose `tryAllocate` releases on the same handler, forcing the `:447` branch with known results; the endpoint-refusal rollback), `single` (100,000 single-thread steps, branch entries 0), `concurrent` (10^6 acquires, 4 releasing threads, a sampler thread; branch entries counted by an endpoint-limit wrapper), `defaults` (4 MiB / 128 MiB / 512 MiB). `STAGE4 check … ok\|MISMATCH` lines. | shakedown 1 (`shake1`): 149 checks, 0 mismatches |
| `AcquireExcessConfigTest.java` | unit (B2b) | Own JVM: reserves set to 32 MiB on the loaded `Config`, the getters (and the derived `internode_max_message_size`) return 33,554,432. | shakedown 1 |
| `unit-run.sh <run> [upstream\|harness\|mutant\|all]` | unit | Upstream `ResourceLimitsTest`; the two tests (copied in, removed after); the R2 mutants in a fresh clone `~/cassandra-rsv-mut` (removed at the end): M1 removes `globalReserve.release(excess)` in the `:447` branch, M2 sets `excess = allocatedExcess`; both must make the test fail. | shakedown 1 (`harness`) |
| `receive-trace.btm` | cluster (B3d, R7) | Observation only, on node A: `acq` at the exit of `acquireCapacity(Limit, Limit, int)` (outcome, `queueSize`, both limits' using/limit), `rel` at the exit of `releaseCapacity(int)` (the handler's own reserve fields). | `Submit -l` lists 3 rules in every lifetime |
| `hold-handler.btm` | cluster (B3b, R5) | While the hold file exists, `MutationVerbHandler.doVerb` sleeps 20 ms at entry on node A. | thread dump in every held lifetime (MutationStage workers asleep in `doVerb`) |
| `make-node-yaml.sh <A\|B> [k=v …]` | cluster (B3a/B3b) | A = 127.0.0.2 (JMX 7102, seed, target: `concurrent_writes: 2`, `memtable_allocation_type: offheap_buffers`, NMT summary, then the label's keys); B = 127.0.0.3 (JMX 7103, sender). Both: 60 s write and native-transport timeouts, hints off, `auto_snapshot` off, data on the tmpfs `/mnt/stage4-rsv`. | yaml tail echoed into every summary |
| `big.yaml`, `client.py`, `sample-vt.py`, `Jmx.java` | cluster | stress profile (`ks.t (pk bigint, v blob)`, fixed 262,144-byte values), schema/probe client, virtual-table sampler (`internode_inbound` on A / `internode_outbound` on B every 0.5 s), JMX poller. | shakedown 1 |
| `cluster-run.py <label>\|analyze\|down` | cluster (B3e) | One lifetime of both nodes per label (docstring: the reading rules fixed before run 1); `analyze` writes the cross-run B3f/B3h relations (R8). Labels: `g4`, `g32`, `g512` (E = G, Q 1 MiB), `ctlq16` (E = G = 4 MiB, Q 16 MiB), `base` (no stress). | shakedown 1 (`g4`, 40 s) |

Run order (run 1):

```bash
H=~/stage4-harness-run/rsv
bash $H/unit-run.sh run1 all
sudo mkdir -p /mnt/stage4-rsv && sudo mount -t tmpfs -o size=40g,mode=1777 tmpfs /mnt/stage4-rsv
for l in g4 g32 g512 ctlq16 base; do RSV_RUN=run1 python3 $H/cluster-run.py $l; done     # one detached chain
RSV_RUN=run1 python3 $H/cluster-run.py analyze
sudo umount /mnt/stage4-rsv
```
