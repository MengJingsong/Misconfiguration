# streaming_state_size — verification solution  <!-- file: cases/streaming_state_size-streammanager-states--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`StreamManager.java:268`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamManager.java#L268) (not an if statement: the construction of the Guava `states` cache that receives the capacity; the enforcement is Guava's weight-based eviction, see A3) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code autonomous subagent, 2026-11-11 |
| Estimate | `positive` — the `states` cache is built with `maximumWeight(streaming_state_size)` and a weigher that charges each `StreamingState` its estimated heap size, so Guava evicts tracking entries once the summed weight passes the limit; the bound is approximate, because each entry's weight is frozen at insert time (before peers are added), so real retained heap can exceed the limit by a bounded per-entry factor. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `streaming_state_size`, a configuration entry (yaml), declared at
[`Config.java:949`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L949)
as `DataStorageSpec.LongBytesBound streaming_state_size = new DataStorageSpec.LongBytesBound("40MiB")`.
Unit: bytes (any data-storage unit accepted in yaml, e.g. `16KiB`, `4MiB`). Default `40MiB`, a literal
(not derived from heap size). Documented, commented out, at `conf/cassandra.yaml:1430-1432`
("How much memory may be used for tracking before evicting session from tracking"). Read via
`DatabaseDescriptor.getStreamingStateSize()` (`DatabaseDescriptor.java:5003-5006`). There is a setter
`DatabaseDescriptor.setStreamingStateSize` (`DatabaseDescriptor.java:5008-5015`) but no caller in `src/`,
no JMX attribute (`StreamManagerMBean.java` exposes only stats-enabled and slow-events timeout) and the
`system_views.settings` table is read-only. The value is read once, in the `StreamManager` constructor
(`StreamManager.java:266`), which runs when `StreamManager.instance` is initialised (`StreamManager.java:59`),
so a change **needs a restart**. Companion knobs: `streaming_state_expires` (default `3d`, `Config.java:948`),
`streaming_stats_enabled` (default `true`, `Config.java:951`).

**A2. What it caps.** Heap: the on-heap tracking records (`StreamingState`) of current and historic stream
plans, kept in the Guava cache `StreamManager.states` (`StreamManager.java:228`) and served by the virtual
table `system_views.streaming` (`StreamingVirtualTable.java:33-75`). The quantity compared against the limit
is the cache's total weight, the sum over entries of
`val.unsharedHeapSize() + TimeUUID.TIMEUUID_SIZE` (`StreamManager.java:278-282`), where
`unsharedHeapSize() = peers().size() * (IPV6_SOCKET_ADDRESS_SIZE + 48) + sizeOf(completeMessage) + EMPTY`
(`StreamingState.java:75-80`) and `EMPTY` is a jamm `measureDeep` of a fresh state (`StreamingState.java:51`).

**A3. Mechanism.**
1. At startup `StreamManager()` reads duration and size (`StreamManager.java:265-267`) and builds the cache at
   [`StreamManager.java:268-272`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamManager.java#L268-L272):
   `expireAfterWrite(3d)`, **[`.maximumWeight(sizeBytes)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamManager.java#L270)**,
   `.weigher(new StreamingStateWeigher())` ([`StreamManager.java:278-282`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamManager.java#L278-L282)).
2. `CassandraDaemon.java:374` calls `StreamManager.instance.start()`, which registers the listener
   (`StreamManager.java:285-288`). Every stream plan registered as initiator (`registerInitiator`,
   `StreamManager.java:359-367`) or follower (`registerFollower`, `StreamManager.java:369-382`) calls
   `onRegister`; if [`streaming_stats_enabled` is false](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamManager.java#L234)
   nothing is stored, otherwise a new `StreamingState` is
   [`states.put(...)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamManager.java#L244)
   (`StreamManager.java:238-251`).
3. The check itself is inside Guava `LocalCache` (32.0.1-jre): on each write the weigher is evaluated and the
   segment evicts least-recently-used entries while its total weight exceeds its share of `maximumWeight`
   (the cache is split into up to 4 segments, each capped at about `maximumWeight/4`; Guava docs: the cache
   "may evict an entry before this limit is exceeded"). Outcome at the limit: the oldest tracking entries
   (completed or running) silently disappear from `states` and from `system_views.streaming`; streaming
   itself is not throttled or failed.
4. On failure the state's `completeMessage` becomes the full stack trace and the entry is re-put to be
   re-weighed ([`StreamingState.java:296-302`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamingState.java#L296-L302),
   `StreamManager.java:256-261`).

Overshoot / bypass paths:
- **Weight frozen at insert.** Guava weighs an entry only at `put`. Peers are added later in
  `streamPrepared` (`StreamingState.java:258`), so a successful entry is charged `EMPTY + TIMEUUID_SIZE`
  while it really also holds a non-empty `ConcurrentHashMap` table plus one `InetSocketAddress` per peer.
  Real retained heap per entry is therefore larger than its weight (estimated factor 1.2–1.6 for one peer).
- **Running plans.** While a plan runs its `StreamResultFuture` holds the state as an event listener
  (`StreamManager.java:246`); eviction from `states` does not free it until the plan completes. Bounded by the
  number of concurrent plans, not by this knob.
- `streaming_stats_enabled: false` (or JMX `setStreamingStatsEnabled(false)`) stops tracking entirely.
- Tiny caps: an entry heavier than a segment's share is evicted at once (nothing retained).

**A4. Other consumers.** Everything else streaming keeps on heap is outside this knob: the live
`StreamResultFuture`/`StreamCoordinator`/`StreamSession` objects in `initiatorStreams`/`followerStreams`
(`StreamManager.java:225-226`), streaming buffers (`streaming_*` network settings), stream rate limiters
(`StreamManager.java:97-215`, bandwidth not memory), and `system.available_ranges`/`streaming` system-table
writes (disk, via `StreamStateStore`).

**A5. Evidence beyond the source.**
- CASSANDRA-17390 "Expose streaming as a vtable" (`CHANGES.txt:952`), https://issues.apache.org/jira/browse/CASSANDRA-17390 — introduced the cache and these knobs.
- `conf/cassandra.yaml:1426-1434` comments.
- `test/unit/org/apache/cassandra/db/virtual/StreamingVirtualTableTest.java` (shows how to create and register states without a cluster; does not test the weight cap).
- Guava `CacheBuilder.maximumWeight` javadoc, https://guava.dev/releases/32.0.1-jre/api/docs/com/google/common/cache/CacheBuilder.html#maximumWeight(long) — weight computed at creation/replace time and static thereafter; eviction may happen before the limit.

## B. Verification solution

**B1. Claim under test.** With `streaming_state_size = S`, the number of `StreamingState` objects retained
after many completed stream plans stops growing once their summed weight reaches S (summed weight ≤ S), while
with a large S all of them are retained; the real heap they retain is bounded by S times a constant
(1 < factor ≤ 2) that comes from the insert-time weight underestimate. The claim is wrong if retained count
or summed weight keeps growing with the workload past S, or if real retained bytes exceed 2·S.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk:
`rsync -a ~/cassandra-5.0.9/ /mydata/s4/o53/src/` (never build in the shared tree). Build once:
`cd /mydata/s4/o53/src && ant jar build-test`. New test file
`/mydata/s4/o53/src/test/unit/org/apache/cassandra/streaming/StreamingStateCapTest.java` (below). The `testsome`
target supplies the jamm javaagent (`build.xml:1159`) and the default test heap; no other JVM options.

```java
package org.apache.cassandra.streaming;

import java.util.*;
import org.junit.*;
import org.apache.cassandra.config.*;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.utils.*;
import static org.apache.cassandra.utils.TimeUUID.Generator.nextTimeUUID;

public class StreamingStateCapTest
{
    static final int N = 2000;
    static final String[] SIZES = { "16KiB", "256KiB", "1MiB", "40MiB" };

    @BeforeClass public static void init() { DatabaseDescriptor.daemonInitialization(); }

    static StreamingState newState(StreamManager m, boolean addPeer) throws Exception
    {
        StreamResultFuture f = new StreamResultFuture(nextTimeUUID(), StreamOperation.REBUILD, null, null); // follower: not completed in ctor
        StreamingState s = new StreamingState(f);
        m.putStreamingState(s);                       // weighed here, peers empty
        s.phase.start();
        if (addPeer)                                  // what a real plan does after registration
            s.handleStreamEvent(new StreamEvent.SessionPreparedEvent(s.id(),
                new SessionInfo(InetAddressAndPort.getByName("127.0.0.2:7000"), 0, InetAddressAndPort.getByName("127.0.0.1:7000"),
                                Collections.emptyList(), Collections.emptyList(), StreamSession.State.PREPARING, null),
                StreamSession.PrepareDirection.ACK));
        s.onSuccess(null);
        return s;
    }

    @Test public void cap() throws Exception
    {
        System.out.println("O53 EMPTY=" + StreamingState.EMPTY + " TIMEUUID_SIZE=" + TimeUUID.TIMEUUID_SIZE);
        for (boolean peer : new boolean[]{ false, true })
            for (String size : SIZES)
            {
                DatabaseDescriptor.setStreamingStateSize(new DataStorageSpec.LongBytesBound(size));
                StreamManager m = new StreamManager();          // reads the knob in its constructor
                long cap = DatabaseDescriptor.getStreamingStateSize().toBytes();
                for (int i = 1; i <= N; i++)
                {
                    newState(m, peer);
                    if (i % 250 == 0)
                    {
                        Collection<StreamingState> live = new ArrayList<>(m.getStreamingStates());
                        long weight = 0;
                        for (StreamingState s : live) weight += s.unsharedHeapSize() + TimeUUID.TIMEUUID_SIZE; // weight as of now
                        long deep = ObjectSizes.measureDeep(live) - ObjectSizes.measureDeep(new ArrayList<>(live.size()));
                        System.out.printf("O53 peer=%s size=%s cap=%d inserted=%d retained=%d weightNow=%d deep=%d%n",
                                          peer, size, cap, i, live.size(), weight, deep);
                    }
                }
            }
    }
}
```
(If `daemonInitialization()` alone is not enough to construct `StreamResultFuture`, make the class extend
`org.apache.cassandra.cql3.CQLTester` and call `CQLTester.setUpClass()` in `init()`, as
`StreamingVirtualTableTest` does.)

> **Amendment S4-A1 (2026-11-11, stage-4 audit; runbook only, no prediction changed).** Paths and build on the
> stage-4 node: the tree is made with `cassandra/stage4-runtime-verification/copy-source.sh /mydata/jingsong-cass-s4/o53/src`
> (from the repository's `systems/cassandra/source/`, `cassandra-5.0.9`), not `rsync` from `~/cassandra-5.0.9`, and built
> with `ant build-test`; every `/mydata/s4/o53/` in B2 and B3 reads `/mydata/jingsong-cass-s4/o53/`. The test is kept in the
> stage-4 harness folder (`harness/streaming_state_size-streammanager-states--autonomous/StreamingStateCapTest.java`) and copied
> into the tree. On this build the test's standard output lands in `build/test/logs/_jdk11/TEST-org.apache.cassandra.streaming.StreamingStateCapTest.log`
> (B2e step 4 greps that file, not the XML). The test also prints the insert-time weight `w = EMPTY + TIMEUUID_SIZE` on its first line.
>
> **Amendment S4-A2 (2026-11-11, stage-4 audit; workload arithmetic).** `N = 5000`, not 2000 (B2c, B2e, B2f). From the source,
> `EMPTY` is the jamm size of a fresh `StreamingState` (object, `TimeUUID`, empty `ConcurrentHashMap` set, `Sessions`, `long[4]`,
> `Phase`), roughly 300–500 B, so w ≈ 330–550 B; at N = 2000 the 1MiB cap binds only for w > 525 B (B2c says so), so the 1MiB
> prediction could fail for a reason that is not the claim. 5000 · 330 B ≈ 1.6 MB > 1 MiB; 5000 · 800 B = 4 MB ≪ 40 MiB, so
> 40MiB stays the uncapped reference. Samples stay every 250 inserts (20 per configuration).

**B2b. Knobs.** `streaming_state_size` ∈ {16KiB, 256KiB, 1MiB, 40MiB}, set with
`DatabaseDescriptor.setStreamingStateSize` before each `new StreamManager()` (the public constructor reads it,
`StreamManager.java:266`). 16KiB/256KiB/1MiB are reached by N=2000 entries; 40MiB (default) is not, and serves
as the uncapped reference. Second factor: `addPeer` false/true, to expose the frozen-weight underestimate.

**B2c. Workload.** N = 2000 completed states per configuration. With per-entry weight
w = EMPTY + TIMEUUID_SIZE (printed; expected a few hundred bytes, say 300–800 B): 2000·w ≈ 0.6–1.6 MB, which
exceeds 16KiB (≈20–55 entries), 256KiB (≈330–870 entries) and, for w > 525 B, 1MiB; it stays far below 40MiB.

**B2d. Observables and instruments.** Printed `O53` lines every 250 inserts: `retained` (cache size),
`weightNow` (weigher formula re-evaluated now, i.e. after peers were added), `deep` (jamm `measureDeep` of the
retained states, the real heap they hold; shared enum constants are counted once and are negligible). The
insert-time weight per entry equals `EMPTY + TIMEUUID_SIZE` (peers empty at `put`). Not observable directly:
Guava's internal per-segment totals.

**B2e. Procedure.**
1. `echo "start $(date -u +%FT%TZ)"`; `cd /mydata/s4/o53/src`.
2. Write the test file above.
3. `ant testsome -Dtest.name=org.apache.cassandra.streaming.StreamingStateCapTest 2>&1 | tee /mydata/s4/o53/unit.log`
4. `grep O53 build/test/output/TEST-org.apache.cassandra.streaming.StreamingStateCapTest.xml /mydata/s4/o53/unit.log`.
5. Tabulate retained/weight/deep vs inserted per size and peer setting.

**B2f. Predictions.** Let w = EMPTY + TIMEUUID_SIZE (insert-time weight).
- 40MiB: `retained` = inserted at every sample (2000 at the end).
- 16KiB, 256KiB, 1MiB: `retained` grows to a plateau and stays there; plateau·w ≤ cap and plateau·w ≥ 0.7·cap
  (segment imbalance); i.e. plateau ≈ floor(cap/w) within −30%/0.
- `addPeer=false`: `weightNow` ≤ cap and `deep` within ±20% of `weightNow` (weigher ≈ jamm).
- `addPeer=true`: same `retained` plateau as `addPeer=false` (weight frozen at insert), but `weightNow` and
  `deep` exceed cap, by a factor between 1.1 and 2.0.

> **Amendment S4-A3 (2026-11-11, stage-4 audit, before any reading; reading rules fixed in writing).** N = 5000 (S4-A2), so
> "2000 at the end" reads "5000 at the end". w is the printed `EMPTY + TIMEUUID_SIZE`; P(cap) = floor(cap / w). All quantities
> are taken from the `O53` lines of the test log. For each configuration:
> - **uncapped** (40MiB): `retained` = `inserted` exactly at every sample.
> - **plateau** (16KiB, 256KiB, 1MiB): the plateau is `retained` at the final sample (inserted = 5000); it is **flat** if
>   max − min of `retained` over the last three samples (inserted = 4500, 4750, 5000) is ≤ 4; it is **in band** if
>   0.7 · P(cap) ≤ plateau ≤ P(cap) (equivalently 0.7 · cap ≤ plateau · w ≤ cap).
> - **summed weight** in B1 is the insert-time weight, plateau · w (the weight Guava compares; it is frozen at insert).
> - **weigher ≈ jamm** (addPeer=false): |deep / weightNow − 1| ≤ 0.20 at the final sample.
> - **same plateau** (addPeer true vs false, same cap): plateaus differ by ≤ 4.
> - **overshoot factor** (addPeer=true): weightNow / cap and deep / cap at the final sample; predicted in [1.1, 2.0].
> - **real bytes bound** (B1): deep ≤ 2 · cap at the final sample of every capped configuration, both addPeer settings.
> The secondary bands (in band, weigher ≈ jamm, same plateau, overshoot factor in [1.1, 2.0]) are predictions whose miss is
> recorded as a deviation; per B1 ("The claim is wrong if retained count or summed weight keeps growing with the workload past
> S, or if real retained bytes exceed 2·S") they do not by themselves change the verdict (B2g rows as amended by S4-A4).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| retained plateaus at ≈cap/w for the three small caps; 2000 at 40MiB | claim confirmed: the knob caps the tracking set |
| retained keeps rising with inserts at 16KiB/256KiB | claim wrong: knob not enforced |
| `deep` > 2·cap with addPeer=true | cap is nominal only; overshoot larger than claimed (claim wrong in its bound) |
| retained = 0 at small cap | entries heavier than a segment share; choose larger cap; not a refutation |
| retained at 40MiB < 2000 | something other than weight evicts (expiry / bug); invalidates the run |

> **Amendment S4-A4 (2026-11-11, stage-4 audit, before any reading; verdict labels and missing rows).** Each row above is
> given a verdict and an effect, with the thresholds of S4-A3 (N = 5000), and rows are added for outcomes the table missed.
> Rows are checked in this order; the first that matches is the verdict.
>
> | Observation (S4-A3 terms) | Verdict — effect |
> |---|---|
> | V1. 40MiB `retained` < `inserted` at any sample (either addPeer) | **Invalid run** — something other than weight evicts |
> | V2. plateau = 0 at a cap | that cap is **invalid** (entry heavier than a segment share), not a refutation; the verdict is taken from the other caps if at least two remain |
> | V3. at 16KiB or 256KiB (either addPeer) `retained` is not flat and plateau · w > cap (keeps growing past S) | **Refuted — does not cap** |
> | V4. every capped configuration flat with plateau · w ≤ cap, but deep > 2 · cap in at least one (addPeer=true expected) | **Refuted (bound) — caps (soft)**: the count is capped, real bytes exceed the claimed 2·S |
> | V5. 40MiB `retained` = `inserted` at every sample; every capped configuration flat with plateau · w ≤ cap; deep ≤ 2 · cap everywhere | **Confirmed — caps** (row 1 of the table above); each secondary band of S4-A3 is reported as met or missed |
> | V6. anything else (e.g. flat but plateau · w > cap, or not flat at 1MiB only) | **Not confirmed (no matching row)** |

**B2h. Controls.** 40MiB run is the positive control (same workload, cap never binds, count follows
workload). `addPeer` false vs true separates the enforcement mechanism from the weight-estimate accuracy.
Fresh `StreamManager` per configuration avoids carry-over; `expireAfterWrite` is 3d so expiry cannot evict
during the run.

### B3. Cluster tier

**B3a. Environment and build.** One machine, two nodes on 127.0.0.1 and 127.0.0.2 (Linux routes all of
127/8 to `lo`), JDK 11. Build the copied tree once (`ant jar` in `/mydata/s4/o53/src`), then
`cp -a /mydata/s4/o53/src /mydata/s4/o53/n1` and `... /n2`. In each `nK/conf/cassandra.yaml`:
`cluster_name: 'o53'`, `num_tokens: 16`, `listen_address`/`rpc_address: 127.0.0.K`,
`seeds: "127.0.0.1:7000"`, `endpoint_snitch: SimpleSnitch`,
`data_file_directories: [/mydata/s4/o53/nK/data]`, `commitlog_directory`, `hints_directory`,
`saved_caches_directory`, `cdc_raw_directory` under `/mydata/s4/o53/nK/`,
`skip_paxos_repair_on_topology_change: true`, and the knob `streaming_state_size: <S>`.
In `n2/conf/cassandra-env.sh` set `JMX_PORT="7299"`. Heap per node: `export MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M`
(2 nodes ≈ 2.5 GiB of the 14 GiB). JVM option on both: `JVM_EXTRA_OPTS="-Dcassandra.consistent.rangemovement=false"`
so `rebuild` may use any replica.

> **Amendment S4-A5 (2026-11-11, stage-4 audit; shared-node addresses and ports, no prediction changed).** The stage-4 node is
> shared, so the pair 127.0.0.1 / 127.0.0.2 is replaced by **127.0.0.21 (node 1, seed) and 127.0.0.22 (node 2)** (loopback,
> no alias or firewall change needed), and both nodes use `storage_port: 7300`, `ssl_storage_port: 7301`,
> `native_transport_port: 9342` (each bound to its own address), `seeds: "127.0.0.21:7300"`; JMX `JMX_PORT=7499` (node 1) and
> `7498` (node 2), local JMX on 127.0.0.1 (`nodetool -h 127.0.0.1 -p 7499|7498`); `cqlsh 127.0.0.2K 9342`. Node directories
> `/mydata/jingsong-cass-s4/o53/n1` and `/n2`, made with `cp -a` of the built `src` tree (B3a), never built in again.
> `cluster_name: 'o53'`. Heap as filed (1G / 256M per node); `cassandra-env.sh` sets its own `-XX:MaxDirectMemorySize`.
>
> **Amendment S4-A6 (2026-11-11, stage-4 audit; the workload as filed would create one plan only).** On node 2 add
> `-Dcassandra.reset_bootstrap_progress=true` to `JVM_EXTRA_OPTS`, and set `auto_bootstrap: false` in node 2's yaml.
> Reason (source): `RangeStreamer.fetchAsync` (`RangeStreamer.java:716-749`) filters out ranges already recorded as available
> by an earlier stream (`StreamStateStore` records them on completion) and, when it finds some and the property is not set,
> throws `IllegalStateException` ("Discovered existing bootstrap data …") **before** `streamPlan.execute()`; so rebuilds 2–150 of
> `o53` would fail without registering a plan, and no `StreamingState` would be created. With the property true it resets the
> keyspace's available ranges and streams all of them again (`RangeStreamer.java:707-712`), one plan per rebuild. `auto_bootstrap:
> false` keeps node 2's join from adding a BOOTSTRAP plan on each node, so the count is exactly the number of rebuilds.
>
> **Amendment S4-A7 (2026-11-11, stage-4 audit; third binding value, samples).** Knob values are **16KiB, 32KiB and 4MiB**
> (B3b listed two; the audit requires three; 32KiB is a second binding value, so the plateau can be seen to follow S). The
> default 40MiB is not run separately: for 150 plans of a few hundred bytes it does not bind, exactly as 4MiB does not. The
> stats-disabled run (B3b, B3e.7) is part of run 1, at S = 4MiB. Samples on both nodes at i = 25, 50, 75, 100, 125, 150 (B3d
> listed 25/50/100/150): `SELECT count(*) FROM system_views.streaming` with cqlsh, and the `org.apache.cassandra.streaming.StreamingState`
> line of `jcmd <pid> GC.class_histogram` (the same full-GC live histogram as `jmap -histo:live`). After i = 150 also the
> vtable's rows grouped by `operation` and `status`. Every rebuild's exit status is logged; a failed rebuild is counted and
> reported. Before the loop of each value, the log line `Storing streaming state for 3d or for size <bytes>` is checked on both
> nodes; the run stops if it shows another size.

**B3b. Knobs.** `streaming_state_size` ∈ {16KiB, 4MiB}, identical on both nodes, restart per value (read once
at startup). 16KiB binds after a few dozen plans; 4MiB does not bind for the workload (positive control). Optional
third run: `streaming_stats_enabled: false` (expect 0 entries).

**B3c. Workload.** Create `CREATE KEYSPACE o53 WITH replication = {'class':'SimpleStrategy','replication_factor':2};`
`CREATE TABLE o53.t (k int PRIMARY KEY, v text);` insert 100 rows. Then on node 2, 150 sequential rebuilds:
`for i in $(seq 150); do n2/bin/nodetool -p 7299 rebuild -ks o53 -- datacenter1; done`. Each rebuild is one
stream plan: an initiator `StreamingState` on node 2 and a follower one on node 1. 150 plans × w (≈300–800 B)
≈ 45–120 KB ≫ 16KiB and ≪ 4MiB. Duration ≈ 150 × (nodetool JVM start + rebuild) ≈ 5–10 min.

**B3d. Observables and instruments.** Per node, after the loop and at i = 25, 50, 100, 150:
- `bin/cqlsh 127.0.0.K -e "SELECT count(*) FROM system_views.streaming;"` (the cache's contents).
- `jmap -histo:live <pid> | grep -E 'streaming\.StreamingState(\$Sessions)? '` — live instance count and shallow
  bytes; real retained ≈ count × deep size per entry from B2 (`deep/retained`, addPeer=true).
- Whole-heap use (`nodetool info` heap) cannot resolve a 16KiB–120KB difference; it is recorded only as a check
  that nothing else grew.

**B3e. Procedure.**
1. Write the yaml/env changes with S=16KiB. Start: `cd /mydata/s4/o53/n1 && bin/cassandra -p n1.pid`; wait for
   `nodetool status` UN; then node 2 likewise (`-p n2.pid`); both UN in `n1/bin/nodetool status`.
2. Check the log line `Storing streaming state for 3d or for size 16384` (`StreamManager.java:267`) on both nodes.
3. Schema + data (B3c) with `n1/bin/cqlsh 127.0.0.1`.
4. Rebuild loop with samples at 25/50/100/150 (B3d).
5. Stop: `kill $(cat n2/n2.pid) $(cat n1/n1.pid)`; wait; `pgrep -f o53` must be empty.
6. Remove `nK/data nK/commitlog nK/hints nK/saved_caches`; set S=4MiB; repeat 1–5.
7. Optional: S=4MiB with `streaming_stats_enabled: false`; repeat 1–5.

**B3f. Predictions.** With w measured in B2:
- S=16KiB: row count and live `StreamingState` count on each node rise to ≈floor(16384/w) (within −30%) by i≈50
  and stay flat to i=150 (e.g. w=500 B → ≤32). Retained real bytes ≤ 2 × 16KiB.
- S=4MiB: count = i at every sample (150 at the end) on each node.
- stats disabled: 0 rows, 0 live instances.

> **Amendment S4-A8 (2026-11-11, stage-4 audit, before any reading; thresholds fixed in writing).** w is the unit tier's
> printed `EMPTY + TIMEUUID_SIZE`; P(S) = floor(S / w); "count" is the vtable count on a node; "live" is that node's
> histogram instance count of `StreamingState`; deep-per-entry d = deep / retained at the final sample of the unit tier's
> 16KiB, addPeer=true configuration. For each node separately:
> - **S = 16KiB and S = 32KiB:** if P(S) < 150, the value binds: count at i = 125 and i = 150 differ by ≤ 4 (**flat**), and
>   count at i = 150 ≤ P(S) (summed insert-time weight ≤ S) and ≥ 0.7 · P(S) (**in band**). If P(S) ≥ 150 the value does not bind
>   and the prediction is that of 4MiB.
> - **S = 4MiB:** count = i at every sample.
> - **stats disabled:** count = 0 and live = 0 at every sample.
> - **live vs count:** live − count ≤ 2 at every sample (sampled after the rebuild returned, so no plan is running).
> - **real bytes bound:** live · d ≤ 2 · S at i = 150 for the binding values.
> As in the unit tier (S4-A3), "in band" is a secondary prediction; its miss is recorded as a deviation and does not by
> itself change the verdict (B3g as amended by S4-A9).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| 16KiB plateau ≈ 16384/w on both nodes, 4MiB reaches 150 | claim confirmed |
| 16KiB count reaches 150 (or grows linearly) | claim wrong: cap not enforced in a real node |
| 4MiB count < 150 | workload did not create one plan per rebuild, or rebuild failed; check logs, not a result |
| histogram count ≫ vtable count after completion | states retained elsewhere (running futures); overshoot path, investigate |
| count × deep-per-entry > 2·S | overshoot beyond claimed bound |

> **Amendment S4-A9 (2026-11-11, stage-4 audit, before any reading; verdict labels).** With the thresholds of S4-A8, checked
> in this order on both nodes (a row holds only if it holds on both, except V1–V3 which hold if they hold on either):
>
> | Observation (S4-A8 terms) | Verdict — effect |
> |---|---|
> | C1. 4MiB count < i at some sample, or a rebuild failed, or the size log line is wrong | **Invalid run** (workload or setup), not a result |
> | C2. stats disabled: count or live > 0 | **Invalid instrument** (the counted objects come from elsewhere) |
> | C3. a binding value (16KiB or 32KiB) is not flat and count at i = 150 > P(S) (keeps growing past S), or count at i = 150 ≥ 135 | **Refuted — does not cap** |
> | C4. live − count > 5 at i = 150 for a binding value and live at i = 150 > P(S) + 5 | **Refuted (real resource) — does not cap** the retained objects, only the tracking set |
> | C5. binding values flat with count ≤ P(S), but live · d > 2 · S | **Refuted (bound) — caps (soft)** |
> | C6. 4MiB count = i at every sample; both binding values flat with count ≤ P(S); live − count ≤ 5; live · d ≤ 2 · S | **Confirmed — caps**; the in-band check and live − count ≤ 2 are reported as met or missed |
> | C7. anything else | **Not confirmed (no matching row)** |

**B3h. Controls.** The 4MiB run on the same workload is the positive control (usage moves with the workload when
the cap does not bind). The stats-disabled run shows the counted objects come only from this tracking path.
`jmap -histo:live` forces a full GC so unreachable evicted states are not counted. Both nodes are measured, giving
initiator- and follower-side states.

**B4. Risks and cleanup.** All files under `/mydata/s4/o53/` on local disk (≈ build 1 GB + 2 node copies; data
negligible). Never write into `~/cassandra-5.0.9`. Stop both Cassandra JVMs via their pid files and check
`pgrep -f /mydata/s4/o53` is empty; `nodetool` and `ant` JVMs exit on their own. Clean with
`rm -rf /mydata/s4/o53` after copying `unit.log` and the readings.

## C. Sources read

- /users/jason92/writeup-ext/playbook-autonomous.md
- /users/jason92/writeup-ext/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/streaming/StreamManager.java
- src/java/org/apache/cassandra/streaming/StreamingState.java
- src/java/org/apache/cassandra/streaming/StreamManagerMBean.java
- src/java/org/apache/cassandra/streaming/StreamResultFuture.java (lines 60-135)
- src/java/org/apache/cassandra/streaming/StreamCoordinator.java (constructor)
- src/java/org/apache/cassandra/streaming/SessionInfo.java (constructor)
- src/java/org/apache/cassandra/streaming/StreamOperation.java
- src/java/org/apache/cassandra/config/Config.java (lines 940-955, 1015-1060)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 4989-5030)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (CONSISTENT_RANGE_MOVEMENT)
- src/java/org/apache/cassandra/db/virtual/StreamingVirtualTable.java
- src/java/org/apache/cassandra/db/virtual/SettingsTable.java (grep)
- src/java/org/apache/cassandra/service/CassandraDaemon.java (line 374)
- src/java/org/apache/cassandra/service/StorageService.java (rebuild, lines 1505-1590)
- src/java/org/apache/cassandra/utils/ObjectSizes.java (grep), src/java/org/apache/cassandra/utils/TimeUUID.java (grep)
- test/unit/org/apache/cassandra/db/virtual/StreamingVirtualTableTest.java
- conf/cassandra.yaml, conf/cassandra-env.sh (grep), build.xml (grep), .build/parent-pom-template.xml (grep), CHANGES.txt (grep)
- https://issues.apache.org/jira/browse/CASSANDRA-17390 (cited, not fetched)
- https://guava.dev/releases/32.0.1-jre/api/docs/com/google/common/cache/CacheBuilder.html (cited from knowledge of the Guava API, not fetched)

## D. Stage-4 feedback

**2026-11-11 — stage 4, run 1 (unit and cluster tiers): Confirmed — caps; outcome class true positive.** Results:
[`../../stage4-runtime-verification/results/streaming_state_size-streammanager-states--autonomous.md`](../../stage4-runtime-verification/results/streaming_state_size-streammanager-states--autonomous.md)
(case file and results untracked at repository HEAD `f74aade6`; the coordinator commits them).
- Audit amendments S4-A1 to S4-A9 (in B2 and B3 above, dated 2026-11-11, all made before any reading): stage-4 paths and
  test-log location; N = 5000 (2000 does not reach 1MiB for w < 525 B); reading rules and verdict labels for B2g and B3g;
  shared-node addresses 127.0.0.21/.22 and ports; `-Dcassandra.reset_bootstrap_progress=true` and `auto_bootstrap: false` on
  node 2 (as filed, `RangeStreamer.java:716-749` throws before `streamPlan.execute()` on rebuilds 2–150, so only one plan
  would have been tracked); a third cluster value 32KiB and samples every 25.
- Unit (B2g row 1): w = EMPTY 352 + TIMEUUID_SIZE 32 = 384 B; plateaus 40 / 680 / 2728 entries at 16KiB / 256KiB / 1MiB
  (exactly 4 · floor(cap/4/w): Guava splits `maximumWeight` over 4 segments), 5000 of 5000 at 40MiB; with one peer added after
  the insert an entry holds 592 B, so real bytes reach 1.54 · S (inside the claimed 2 · S). Without peers the weigher
  over-charges slightly (the `TimeUUID` is counted in `EMPTY` and again as `TIMEUUID_SIZE`; jamm/weight 0.917).
- Cluster (B3g row 1): after 150 rebuilds, 40 / 84 / 150 tracked entries at 16KiB / 32KiB / 4MiB on both the initiator
  (node 2) and the follower (node 1); live `StreamingState` objects equal the tracked entries; 0 with
  `streaming_stats_enabled: false`.
- No section of the trace (A1–A5) is refuted.
