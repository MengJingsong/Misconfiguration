# maximum_replication_factor (nearest constraint) — ReplicaList.add growth — verification solution  <!-- file: cases/maximum_replication_factor-ReplicaList.add-newSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/locator/AbstractReplicaCollection.java:109` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (version not exposed to the agent), 2026-10-26 |
| Estimate | `negative`. Line 109 is the "array is full, grow it" test of an internal growable array. No memory or disk limit is declared for it. The only related limit, the `maximum_replication_factor` guardrail, bounds a count of at most RF replicas per collection, which is not a memory-significant object. |
| Ground | `ReplicaList` holds `Replica` references (a few per token or range, one per replica of that range). It is sized by RF or by the number of endpoints, and is short-lived. The line's own growth rule (3, 9, then doubling) has no ceiling and reads no config. The guardrail is off by default (`-1`), checked only at CREATE/ALTER KEYSPACE, and bounds RF, not bytes. Heap or disk use of the node does not follow it. |

## A. Constraint trace

**A1. The constraint.** The target line holds no constraint. The condition `size == contents.length` (`AbstractReplicaCollection.java:109`) is a capacity check, and the new capacity comes from hard-coded constants (`:112-114`: 3, 9, then `size * 2`). The nearest declared limit that bounds how large a `ReplicaList` can get is the guardrail `maximum_replication_factor`.
- Kind: configuration entry (guardrail), runtime-queried.
- First declared: `Config.java:931-932`, fields `maximum_replication_factor_warn_threshold` and `maximum_replication_factor_fail_threshold`, both `volatile int`, default `-1` (disabled). Guardrail object: `db/guardrails/Guardrails.java:482` (`MaxThreshold("maximum_replication_factor", ...)`). Validated at `config/GuardrailsOptions.java:89`.
- Unit: replicas (an integer count, not bytes). Default `-1` is a literal in `Config.java`, so it is not derived.
- Set via the yaml keys above, or at runtime via JMX or `nodetool` guardrail setters (the fields are `volatile` and have setters in `GuardrailsOptions`). No restart is needed for the guardrail. Capacity growth itself has no knob and is not settable.

**A2. What it caps.** The guardrail compares `rf.fullReplicas` of a keyspace being created or altered against the threshold (`SimpleStrategy.java:111-112`, `NetworkTopologyStrategy.java:352-353`). That is a replica count, not heap. Indirectly it limits the final `size` of the `ReplicaList` built per range or token, since builders are pre-sized from RF (`SimpleStrategy.java:71`, `new EndpointsForRange.Builder(replicaRange, rf.allReplicas)`). The array element is one reference (4 or 8 bytes), so a list at RF 3 to 10 is under 100 bytes.

**A3. Mechanism.**
1. `ReplicaList.add` (`:103`) throws `IllegalStateException` if `begin != 0`, so only an unsliced list can grow (`:106-107`).
2. If the array is full (`:109`): new size is 3 if `size < 3`, 9 if `size < 9`, otherwise `size * 2` (`:111-114`). Then `Arrays.copyOf` (`:115`).
3. The element is stored and `size` incremented (`:117`).
- When the limit is hit: there is no limit. Doubling never refuses. An `int` overflow in `size * 2` would only occur near 2^30 elements, which is not reachable via any replica count.
- Overshoot: when an exact capacity is given (`SimpleStrategy.java:71`) no growth happens. When no capacity is given (`NetworkTopologyStrategy.java:187`, `new EndpointsForRange.Builder(replicatedRange)`, capacity 0) the list grows 0 -> 3 -> 9 -> 18, which can overshoot the final size by up to 2x. This is a few bytes.
- Bypass: nothing consults the guardrail on this path. `maximum_replication_factor` is checked only when keyspace DDL is validated (see the `:111`/`:352` references above). Existing keyspaces and schema loaded from disk are not re-checked, and the default is disabled.

**A4. Other consumers.** The same heap is used by everything else (memtables, caches, `TokenMetadata`, and so on). `ReplicaList` instances are created per read/write/endpoint calculation (`ReplicaPlans.java:522,570,762`) and by `NetworkTopologyStrategy.calculateNaturalReplicas`; they are garbage soon after. Cached natural-endpoint sets are held per ring range, so the cumulative size is O(ranges x RF) references, governed by `num_tokens` and cluster size, not by any byte limit.

**A5. Evidence beyond the source.** None. The conclusion is from the source in the pinned tree only.

## B. Verification solution

**B1. Claim under test.** The `ReplicaList` growth at line 109 is not capped by any memory or disk limit, and heap occupied by `ReplicaList` arrays follows the number of replicas added (and so RF), not the `maximum_replication_factor_*` thresholds. Setting the guardrail only rejects DDL; it changes no byte-level usage for keyspaces that pass the check, and its effect on total node memory is negligible (well under 1 MB at any realistic RF).

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk, outside the shared source: `rsync -a /users/jason92/cassandra-5.0.9/ /tmp/$USER/c509/` then `cd /tmp/$USER/c509 && ant jar`. Put a small JUnit test in the copy at `test/unit/org/apache/cassandra/locator/ReplicaListGrowthTest.java` (package `org.apache.cassandra.locator`, since `ReplicaList` is `protected final` and its fields are package-private). Run with `ant testsome -Dtest.name=org.apache.cassandra.locator.ReplicaListGrowthTest`. (**Amended 2026-10-26: the copy is made with `copy-source.sh` into the agent's own work dir on local disk, not `/tmp/$USER` or `rsync` from the home clone; the test must call `DatabaseDescriptor.daemonInitialization()` first, because `Guardrail.enabled()` is false until `isDaemonInitialized()` (`Guardrail.java:95`), which would make the positive control pass vacuously (the guardrail is also disabled while both thresholds are -1, `Threshold.java:80-86`). `ant testsome` forks its own 1 GiB JVM; the options of B2a other than `-Dstage4.out` are not applied.**) JVM option for test: `-Xmx512m -XX:+UseSerialGC` so the heap is quiet. Do not run on the cluster.

**B2b. Knobs.** (1) N = number of replicas added to one list: 1, 2, 3, 4, 9, 10, 100, 10_000, 1_000_000. (2) Initial capacity: 0 (as `NetworkTopologyStrategy.java:187`) vs exact N (as `SimpleStrategy.java:71`). (3) Guardrail threshold value: unset (`-1`), `1` and `3` (**amended 2026-10-26: `1` added so the knob has three values; `1` is allowed because `default_keyspace_rf` is 1**), set through `DatabaseDescriptor.getGuardrailsConfig().setMaximumReplicationFactorThreshold(warn, fail)` with warn = fail (**amended 2026-10-26: the setter takes both values; there is no single fail setter**), to show it has no effect on `ReplicaList.add`.

**B2c. Workload.** Create N `Replica` objects (`Replica.fullReplica(InetAddressAndPort.getByName("127.0.0.1"), range)` with a single shared `Range<Token>` and one shared endpoint object, so only list overhead is measured, not Replica objects). Call `new EndpointsForRange.Builder(range, cap)`, `builder.add(replica, Conflict.NONE)` N times is not applicable to duplicates, so instead use distinct ports `InetAddressAndPort.getByAddressOverrideDefaults(addr, port)` for N distinct endpoints, or, to test the list only, add the same `Replica` to a bare `ReplicaList` via a test in the same package: `ReplicaList l = new ReplicaList(cap); for i<N: l.add(r)`. Arithmetic: capacity after N adds with cap 0 follows 3, 9, 18, 36, ..., so for N=10 capacity is 18, for N=100 it is 144 (9*2^4), for N=10_000 it is 9*2^10 = 9216 -> 9216 < 10_000 so 18432. (**Amended 2026-10-26: capacity after N adds from 0 is 3 for N<=3, 9 for N<=9, else 9*2^k with k the smallest integer for which 9*2^k >= N; N=1_000_000 gives 9*2^17 = 1,179,648.**)

**B2d. Observables and instruments.** (a) `l.contents.length` and `l.size` read directly (same package). (b) Array shallow size via `org.github.jamm.MemoryMeter` (`measure()`, already a Cassandra dependency) on `l.contents`, as a cross-check of 16 + 4/8 x length. (c) Count of growth events: wrap by checking `contents` identity change after each add. Not observable directly: the GC-level lifetime of the lists.

**B2e. Procedure.**
1. Build the copy (B2a). Add the test file.
2. For each N and each initial capacity, run the add loop, record `size`, `contents.length`, number of reallocations, MemoryMeter bytes of `contents`.
3. Set the guardrail fail threshold to 3 (via the config setter, no node), repeat for N=10 and N=1000. Confirm `add` still succeeds.
4. Positive control: in the same test, call `Guardrails.maximumReplicationFactor.guard(10, "ks", false, null)` with threshold 3 (and 1) and confirm it fires, read as `failsOn(10, null)` being true (**amended 2026-10-26, from source: with a null `ClientState` `Guardrail.fail` logs the violation and returns without throwing (`Guardrail.java:139-140`, `if (state != null) throw`), and `Threshold.enabled()` is false while both thresholds are not above 0 (`Threshold.java:80-86`); so "throws `InvalidRequestException`" cannot be seen in the unit tier. The real throw is seen in the cluster tier (B3e step 3) with an ordinary role**) (a cap that does bind, on a count); with `-1` it must not throw; `guard(3, ...)` at threshold 3 must not throw (the comparison is strictly greater). (**Amended 2026-10-26: the control binds a replica count, not bytes. The test also reads `new EndpointsForRange.Builder(range, rf)` for rf 1, 3, 10 to show the only route from the knob to array bytes (builder capacity = RF), and the heap of 10 retained lists of 1,000,000 against the instrument bytes, as the real-resource check.**)
5. Remove the temp tree: `rm -rf /tmp/$USER/c509`.

**B2f. Predictions (before any run).**
- Capacity sequence with initial 0: 0 -> 3 (N=1..3), 9 (N=4..9), 18 (N=10..18), then doubling; reallocations for N=10_000: 13 (3, 9, 18, 36, 72, 144, 288, 576, 1152, 2304, 4608, 9216, 18432). (**Amended 2026-10-26: the filed text said 12, "1+1+10"; the listed sequence has 13 members (3, 9, then 9*2^1 to 9*2^11). Arithmetic only.**)
- With initial capacity N: zero reallocations, `contents.length == N`.
- Final capacity / N is between 1 and 2 for N >= 9 with initial 0.
- Array bytes ~ 16 + 4 x capacity (compressed oops) or 16 + 8 x capacity; for N=10: under 100 bytes; for N=1_000_000: about 4-8 MB (2^20 x 9/... capacity 1,179,648 x 4 = about 4.7 MB).
- Guardrail threshold 1 or 3 changes nothing on the list: same `contents.length` and same bytes as with `-1`.
- Claim wrong if: `add` refuses or truncates at the guardrail value, or capacity depends on the threshold.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Bytes track capacity = 3/9/18/doubling and are independent of the threshold | Claim confirmed: no cap on this growth; usage follows N |
| `add` throws or capacity differs when threshold is 3 | Claim refuted: the guardrail does govern the list |
| Guardrail `guard(10, ...)` fires at threshold 3 (`failsOn(10, null)` true; amended 2026-10-26, see B2e step 4) (positive control) while the list still grows to 1,000,000 | Confirmed: the cap binds on RF count at DDL only, not on the array |
| Positive control `guard` does not fire (`failsOn` false) | Control did not work; not confirmed |
| N never reaches beyond 18 (loop too small) | Limit never reached; not confirmed |
| Bytes flat across N | Measurement wrong (check MemoryMeter target) |

**B2h. Controls.** (Amended 2026-10-26: the instrument's sensitivity is shown by the bytes moving with N and with the exact initial capacity; this is the "workload can move usage" half of the positive control, the guard throw is the "knob is applied" half. Neither moves bytes by the knob, which is the claim.) Same N with exact initial capacity (no growth) isolates the growth cost. Shared `Replica` object isolates array bytes from Replica bytes. Run each N three times with `System.gc()` before measuring (MemoryMeter is deterministic, GC only matters for the optional `Runtime` heap cross-check).

### B3. Cluster tier

**B3a. Environment and build.** One node (second optional) on local disk with known free space (>= 5 GB), JDK 11. Copy and build as in B2a: `cd /tmp/$USER/c509 && ant jar`. Use `bin/cassandra -f` from that copy with data, commitlog, hints, saved_caches and logs under `/tmp/$USER/node1/...` (`-Dcassandra.storagedir=/tmp/$USER/node1`). JVM: `-Xms1g -Xmx1g -XX:+UseG1GC`, `-Dcassandra.jmx.local.port=7199`. Config: `num_tokens: 16`, `partitioner: Murmur3Partitioner`, `endpoint_snitch: GossipingPropertyFileSnitch`. Do not touch any shared node. **Amended 2026-10-26 (all pre-reading): (a) the node uses `authenticator: PasswordAuthenticator` (and `CassandraRoleManager`, default `authorizer: CassandraAuthorizer`) because `Guardrail.enabled(state)` is false for a superuser and, with `AllowAllAuthenticator`, every client is a superuser (`ClientState.isSuper()` returns true when the authenticator does not require authentication, `ClientState.java:604`); the DDL positive control (B3e step 3) is run by an ordinary role `ord` (LOGIN, with CREATE on ALL KEYSPACES), and a CREATE KEYSPACE by the superuser `cassandra` at the same threshold is a second control (expected to succeed); stress and keyspace set-up use `cassandra`. (b) Local node, not `/tmp`: loopback 127.0.1.1 (storage 7000, native 9042), JMX 7110, data on tmpfs `/dev/shm/s4-b7-rl`, `MAX_HEAP_SIZE=1G` (G1). (c) The 3-node optional ring is `n/a`: one node; the RF-3 keyspace is built with capacity 3 by `SimpleStrategy.java:71` whatever the endpoint count, so the per-array size shows RF without a ring. (d) The threshold is changed at runtime through `GuardrailsMBean.setMaximumReplicationFactorThreshold(warn, fail)` (JMX), with warn = fail, and read back.** (Constraint from the task: no processes on the cluster were run while writing this; the stage-4 runner executes this.)

**B3b. Knobs.** `maximum_replication_factor_fail_threshold`: `-1` (default), `1`, `3`; set in `cassandra.yaml` or at runtime via JMX `GuardrailsMBean`. RF of test keyspaces: 1, 3. Number of keyspaces K: 1 and 200 (each with a different `replication_factor` but same table count 0, to isolate replica-calculation overhead). Cluster size: 1 node (so the lists are RF-capped by the 1 endpoint) and optionally 3 nodes with 3 x 256 tokens to widen the ring.

**B3c. Workload.** `cassandra-stress write n=1000000 -rate threads=32` against the created keyspace (RF 1 on one node), then repeat with RF 3 on a 3-node cluster. Each write calls `calculateNaturalReplicas`/`ReplicaPlans`, creating short-lived `ReplicaList` arrays (each at most RF+1 elements). Arithmetic: 1M writes x about 56-byte array = about 56 MB total allocation over the run, but all garbage; live retained is far lower. Duration: about 5 min per run.

**B3d. Observables and instruments.** (1) Live heap of `ReplicaList` / `Replica[]`: `jcmd <pid> GC.class_histogram` before and after, filtered for `[Lorg.apache.cassandra.locator.Replica;`, sampled every 10 s (**amended 2026-10-26: a stress run of 1M writes lasts about a minute, so 30 s would give two samples; the heap dump is dropped, the histogram is the instrument**). (2) Total heap after GC: `jstat -gc <pid> 5000` (OU, EU columns). (3) Disk: `du -sk /tmp/$USER/node1`. (4) `nodetool getguardrailsconfig` (or JMX read) to confirm the threshold. Not observable directly: the allocation rate of the arrays (inferred from `jstat` YGC counts, not per class).

**B3e. Procedure.**
1. Copy and build, create dirs on local disk, start node 1 with the threshold at `-1`.
2. Record baseline class histogram and `jstat`. Create keyspace `ks_rf1` (RF 1). Run stress (B3c). Record histogram every 10 s during and after, then force `jcmd GC.run` and record again.
3. Set threshold to 1 through JMX (`nodetool setguardrails...` or JMX bean). Re-run stress against `ks_rf1`. Try `CREATE KEYSPACE ks_rf3 WITH replication = {'class':'SimpleStrategy','replication_factor':3}`; expect an `InvalidRequestException` (positive control: the cap binds for DDL).
4. Set threshold back to `-1`, create 200 keyspaces with RF 1 and RF 3 variants, record the `Replica[]` histogram line (instances and bytes).
5. Stop the node: `kill <pid>` then `pgrep -f CassandraDaemon` must print nothing. `rm -rf /tmp/$USER/node1 /tmp/$USER/c509`.

**B3f. Predictions.**
- Retained bytes of `Replica[]` after forced GC are under 1 MB in every configuration (live `ReplicaList`s are held only by cached endpoint sets and in-flight requests).
- Threshold `-1`, `1`, or `3` produce the same retained `Replica[]` bytes (within +/- 10 percent noise) for the same keyspaces and workload; heap used (jstat OU) differs by less than the noise of normal operation.
- Raising RF from 1 to 3 raises per-array size from about 24 to about 32 bytes (3 -> capacity 3 or 4), so total retained scales with RF x ring ranges, not with the threshold.
- Threshold 1 makes `CREATE KEYSPACE` with RF 3 fail and does not change heap for writes to the existing RF 1 keyspace.
- Claim wrong if retained `Replica[]` bytes change when only the threshold changes, or reach tens of MB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `Replica[]` retained < 1 MB, identical across threshold values | Confirmed: no byte-level cap; usage independent of the knob |
| `Replica[]` retained changes with threshold alone | Refuted: the threshold governs the arrays |
| RF 3 DDL rejected at threshold 1 (positive control), writes to RF 1 keyspace unchanged | Confirmed: the cap binds only on RF count at DDL, not on memory |
| RF 3 DDL accepted at threshold 1 | Control failed (setting not applied); not confirmed |
| Stress writes did not reach 1M, or histogram never shows `Replica[]` | Limit/workload not reached; not confirmed |
| Retained `Replica[]` tens of MB | Prediction wrong; investigate retention (e.g. endpoint cache), claim of negligible memory refuted |

**B3h. Controls.** Same workload with threshold unset is the baseline. Identical seed and row count across runs. Heap size fixed at 1 GB and GC type fixed. Run each configuration twice to estimate noise before comparing.

**B4. Risks and cleanup.** Disk: all node data under `/tmp/$USER/node1` (local, 1M small rows is under 1 GB); check `df -h /tmp` first and abort if free space is under 5 GB. No shared storage written and no file added to the shared source tree. Processes: node JVM, `cassandra-stress`, `jcmd`; stop with `kill` and verify with `pgrep -fl 'CassandraDaemon|stress'` printing nothing. Remove `/tmp/$USER/c509` and `/tmp/$USER/node1`.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/locator/AbstractReplicaCollection.java (lines 1-200 and grep of the rest)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/locator/SimpleStrategy.java (excerpts, grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/locator/NetworkTopologyStrategy.java (excerpts, grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/locator/ReplicaPlans.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/locator/EndpointsForRange.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrails.java (lines 478-492)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (lines 925-933)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/GuardrailsOptions.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java (grep)

## D. Stage-4 feedback

**Stage-4 audit amendments, 2026-10-26** (all made before any reading; the results file is `stage4-runtime-verification/results/maximum_replication_factor-ReplicaList.add-newSize--autonomous.md`):
1. B2b: threshold values -1, 1, 3 (was -1 and 3); setter is `setMaximumReplicationFactorThreshold(warn, fail)`.
2. B2c/B2f: reallocation count for N=10_000 is 13, not 12 (arithmetic); general capacity rule stated.
3. B2a/B2e/B2g: `DatabaseDescriptor.daemonInitialization()` needed, else the guardrail control is vacuous; copy by `copy-source.sh`; extra reads (builder capacity = RF, heap of retained lists).
4. B3a/B3e: `PasswordAuthenticator` and an ordinary role for the DDL control, because superusers (and every client under `AllowAllAuthenticator`) skip guardrails; local tmpfs, ports of the agent's slot, 1 GiB heap, no ring, runtime threshold change by JMX, histogram every 10 s.
B2e step 4 and two rows of B2g were reworded (item 5); no row of B3g was changed and no prediction was changed except the arithmetic in item 2.
5. B2e step 4, B2g rows 2-3: the unit control reads `failsOn(10, null)` instead of "throws `InvalidRequestException`" (a null `ClientState` never throws, `Guardrail.java:139-140`; the guardrail is disabled at -1, `Threshold.java:80-86`). Found by the first test run (a shakedown whose readings are not used; it showed `guard` returning without a throw); the cause is established from the source lines cited, and run 1 starts from scratch with the corrected text.

**Stage-4 result, 2026-10-26 (`stage4-runtime-verification/results/maximum_replication_factor-ReplicaList.add-newSize--autonomous.md`):** unit tier **Confirmed**, does not cap; cluster tier **Confirmed**, does not cap. Outcome class: true negative. Unit: capacity 3/9/18/doubling exactly as predicted (N=10_000: 18432 after 13 reallocations; N=1_000_000: 1,179,648, 4.7 MB), one identical reading per N for thresholds -1, 1 and 3, guardrail fires at 3 and 1 (positive control, by `failsOn`). Cluster: live `Replica[]` is 35 arrays, 832 B in all six stress phases (thresholds -1, 1, 3, twice) and after 200 extra keyspaces; an ordinary role is refused RF 3 at threshold 1 and RF 4 at threshold 3, the superuser never. The prediction needed no change except the reallocation count (amendment 2). Two source facts found for future cases: `Threshold.enabled()` is false while both thresholds are at or below 0, and `Guardrail.fail()` does not throw for a null `ClientState`; guardrails are skipped for superusers and, under `AllowAllAuthenticator`, for every client.
