# Harness — internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous

Stage-4 harness for the autonomous case file (frozen sha256 `b6348477…`, see the results file
[§1](../../results/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md)). Written
2026-10-20/21 after the step-0 audit. Run on `pc13` (node3 of `jason92-320876`) from a copy in
`~/stage4-harness-run/rrc/` (compare `md5sum` with this folder first), against `~/cassandra-run1` (`cassandra-5.0.9`,
`b5f2a54`, built). Logs go to `~/stage4-logs/rrc/<run>/` on the node, outside the repo. Reuses the closed sibling
`internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided` (hold rule, trace, yaml maker,
sampler, `Jmx.java`) and the loopback recipe of `internode_max_message_size-inferMessageSize-size--autonomous`.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `ReleaseCapacityProbeTest.java` | unit (B2c–B2f) | Package `org.apache.cassandra.net`. A real `InboundMessageHandler` (package-private constructor, no-op consumer, `EmbeddedChannel`, decoder `null`) driven through `acquireCapacity`/`releaseCapacity`. Methods `script` (600, 600, 2000 then releases at Q 1024/4096 × R 2048/8192; the invariant `E = G = max(0, q − Q)` and `q − Q ≤ R` after every step; the exact (q, E) sequence at 1024/2048; Q 4096 borrows nothing), `boundary` (old = Q releases 0 while another handler holds 100 B; old = Q + 1, bytes 5 releases 1), `throttled` (+1 outer, +0 inner), `reactivation` (beyond B2f: a release at old ≤ Q wakes nobody, one at old > Q wakes the waiting handler), `concurrent` (1 acquirer + 4 releasers, 100,000 messages, 5 repetitions), `defaults` (4,194,304). `STAGE4 check … ok\|MISMATCH` lines. | shakedown 1: 108 checks, 0 mismatches |
| `ReleaseCapacityConfigTest.java` | unit (B2b) | Own JVM: `daemonInitialization(() -> config with 8MiB)`, the getter returns 8,388,608. | shakedown 1 |
| `unit-run.sh <run> [upstream\|harness\|mutant\|all]` | unit | Upstream `ResourceLimitsTest`; the two tests (copied in and removed after); the R1 mutants in a fresh clone `~/cassandra-rrc-mut` (removed at the end): M1 releases `bytes` instead of `excess`, M2 removes the guard — both must fail the test; M0 is the filed `>=` mutant, run only to record R1's audit finding (equivalent: expected to pass). | shakedown 1 (`harness`) |
| `receive-trace.btm` | cluster (B3d(1)) | Observation only: `acq` at the exit of `acquireCapacity(Limit, Limit, int)`; `rel` after the `getAndAdd` of `releaseCapacity` (`old` = the operand of `:464`); `relx` at the first `Limit.release(long)` of `releaseCapacity` (only reached when the guard is true; prints the local `excess`). | `TestScript` (no errors); `Submit -l` lists 4 rules in every lifetime |
| `hold-handler.btm` | cluster (B3a) | The sibling's hold: while the hold file exists, `MutationVerbHandler.doVerb` sleeps 200 ms at entry. | thread dump in every held lifetime (32 MutationStage workers asleep in `doVerb`) |
| `make-node-yaml.sh <A\|B> [k=v …]` | cluster (B3a/B3b) | A = 127.0.0.2 (JMX 7102, seed), B = 127.0.0.3 (JMX 7103); 1 token each, `SimpleSnitch`, `write_request_timeout` and `native_transport_timeout` 60 s, hints off, data on the tmpfs `/mnt/stage4-rrc`; A's raised send limits; B: `memtable_allocation_type: offheap_buffers`, NMT summary, then the label's keys. | yaml tail echoed into every summary |
| `big.yaml`, `small.yaml` | cluster (B3c, B3h(c)) | `cassandra-stress` user profiles: `ks.t (pk bigint, v blob)`, fixed 524,288 / 1,024 B values. | shakedowns |
| `client.py` | cluster | `schema` (NTS `datacenter1: 2`), `probe`. | shakedowns |
| `sample-vt.py` | cluster (B3d) | `system_views.internode_inbound` on B / `internode_outbound` on A every 0.5 s. | shakedowns |
| `Jmx.java` | cluster (B3d(1)) | The sibling's JMX client; `poll` fixed so a missing bean is one `ERR` field. | shakedown 2 |
| `cluster-run.py <label>\|analyze\|down` | cluster (B3e) | One lifetime of both nodes per label (see its docstring for the reading rules); `analyze` writes the cross-run B3f/B3g/B3h relations. Labels: `s1q64k`, `s1q4m-1..3`, `s1q32m` (set 1: reserves 16 MiB, max message 8 MiB), `s2q64k`, `s2q4m`, `s2q32m` (set 2: default reserves), `ctla-q64k`, `ctla-q32m` (B3h(a), no hold), `ctlb` (B3h(b), reserves 4 MiB, max message 2 MiB, Q 64 KiB), `ctlc` (B3h(c), 1 KiB writes). Q = 4 MiB is the default (no key). | shakedowns 1–3 |

Harness fixes from the shakedowns (all before run 1; none changes a B2f/B3f number): `Jmx.java poll` wrote two fields
for a missing bean; the thread dump came after the drain and matched a thread name 5.0 does not use (`SharedPool-Worker-N`);
the OOM count matched the `-XX:+HeapDumpOnOutOfMemoryError` flag; the histogram cadence (B3d's 30 s) gave at most one
sample inside a ~25 s stress, so samples start 2 s after the load reaches B and come every 10 s through the drain;
`Jmx` is recompiled every lifetime. Runbook defect 1 (results §3): R3's `write_request_timeout` alone leaves a 12 s
expiry, because the coordinator stamps the nearer of it and `native_transport_timeout`; both are 60 s now.

Run order (run 1):

```bash
H=~/stage4-harness-run/rrc
bash $H/unit-run.sh run1 all
for l in s1q64k s1q4m-1 s1q32m s1q4m-2 s2q64k s2q4m s2q32m s1q4m-3 ctla-q64k ctla-q32m ctlb ctlc; do
  RRC_RUN=run1 python3 $H/cluster-run.py $l; done          # one detached chain
RRC_RUN=run1 python3 $H/cluster-run.py analyze
```

Before a cluster run: `sudo mount -t tmpfs -o size=80g,mode=1777 tmpfs /mnt/stage4-rrc`; after: `sudo umount /mnt/stage4-rrc`.
