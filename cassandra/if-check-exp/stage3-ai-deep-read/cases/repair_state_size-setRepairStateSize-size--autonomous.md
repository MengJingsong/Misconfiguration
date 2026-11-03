# repair_state_size (setter change-detection in setRepairStateSize) — verification solution  <!-- file: cases/repair_state_size-setRepairStateSize-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:5070`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L5070) (`5070#1`, `conf.repair_state_size != size`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code at Meta (version string not available in the sandbox), 2026-10-25, band D triage |
| Estimate | `positive`, with three limits on scope: it caps the number of entries, it applies only at startup, and bytes per entry are not bounded. `repair_state_size` is the Guava `maximumSize` of the two heap caches of repair coordinator and participant states (`ActiveRepairService.java:250-260`), so the number of retained `CoordinatorState`/`ParticipateState` objects is ≤ the value. The value is read only once, when `ActiveRepairService` is constructed. The setter that holds the target check (`DatabaseDescriptor.java:5068-5075`) has no caller in `src/java`, and the check is only change detection for a log line, so a runtime change would have no effect on the live caches. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Declaration and default.** `repair_state_size` is a configuration entry ([`Config.java:958`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L958), `volatile int`, default 100 000). Its companion is `repair_state_expires` (default 3d, [`Config.java:957`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L957)). Neither appears in `conf/cassandra.yaml`, but both can be set there by key. The unit is a number of entries per cache.
- **Getter.** [`DatabaseDescriptor.java:5063-5066`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L5063-L5066).
- **Setter.** `:5068-5075`. If the value differs (line 5070), it logs and assigns; it does no validation.
- **Callers.** A search of `src/java` finds no caller of `setRepairStateSize` and no JMX or nodetool exposure. The only reader is `ActiveRepairService.<init>` ([`ActiveRepairService.java:251`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L251)).
- **Restart.** A change requires a restart.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** It caps heap: the entry count of the `repairs` cache (`Cache<TimeUUID, CoordinatorState>`, `ActiveRepairService.java:191,253-256`) and of the `participates` cache (`Cache<TimeUUID, ParticipateState>`, `:193,257-260`). Each entry holds the following:
- **`CoordinatorState`:** repair options, a map of `SessionState`s (each with a map of `JobState`s), the column-family list, and neighbours and ranges (`CoordinatorState.java:47-54`; `SessionState.java:41-47`; `JobState.java:39-42`).
- **`ParticipateState`:** table ids, ranges, and a map of jobs with validation and sync states (`ParticipateState.java:42-60,66+`).

The quantity Guava compares internally is the per-segment entry count against `maximumSize`.

**A3. Mechanism.**
1. At startup, `ActiveRepairService()` reads `getRepairStateExpires()` and `getRepairStateSize()` and builds both caches with `expireAfterWrite(expires)` and `maximumSize(size)` ([`ActiveRepairService.java:250-260`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L250-L260)). It also logs "Storing repair state for {} or for {} elements" (`:252`).
2. **Coordinator entries.** Every repair command that gets past the RF/ranges check ([`StorageService.java:4797-4802`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L4797-L4802)) creates a `RepairCoordinator` in `createRepairTask` (`:4862`). The constructor builds a `CoordinatorState` and registers it with `repairs.put` ([`RepairCoordinator.java:128-132`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L128-L132), [`ActiveRepairService.java:1202-1205`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L1202-L1205)).
3. **Participant entries.** Every prepare message received registers a `ParticipateState` ([`RepairMessageVerbHandler.java:111-112`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairMessageVerbHandler.java#L111-L112), `ActiveRepairService.java:684,1207-1217`).
4. **Eviction.** When a put pushes a segment over its share of `maximumSize`, Guava evicts entries close to least-recently-used. Entries also expire 3 days after write. Eviction is silent; nothing is rejected.

**Bypasses.**
- `RepairCoordinator` objects queued in `repairCommandExecutor` keep their state reachable until they run, whatever the cache does ([`StorageService.java:4802`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L4802)).
- `repairStatusByCmd` is a separate cache sized by the system property `cassandra.parent_repair_status_cache_size` (default 100 000, [`CassandraRelevantProperties.java:392`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L392); [`ActiveRepairService.java:241-247`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L241-L247)).
- The setter at 5070 cannot resize the existing caches.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — A3, derived from the source and the pinned Guava.** (i) **Cache type and eviction.** Both caches are Guava `com.google.common.cache.Cache` ([`ActiveRepairService.java:37-38`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L37-L38)), Guava **32.0.1-jre** (`.build/parent-pom-template.xml:307-309`; the jar in the run clone's `build/lib/jars/`), built with `expireAfterWrite(repair_state_expires)` (3d, [`Config.java:957`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L957)) and `maximumSize(repair_state_size)`, default concurrency level 4, no weigher, so the bound is an **entry count**, not bytes. Guava splits `maximumSize` over its segments: the number of segments is the largest power of two ≤ 4 with segments × 20 ≤ S, and each segment's cap is S / segments with the remainder spread so that the caps sum to S exactly; a put evicts within its segment while the segment's count exceeds its cap. Read from the jar at the audit by `$W/audit-run27/GuavaLayout.java` (it builds the cache with the same builder calls and reads Guava's own fields): S = 10 → 1 segment [10]; 50 → 4 [13 13 12 12]; 100 → 4 × 25; 500 → 4 × 125; 1000 → 4 × 250; 100000 → 4 × 25000; every sum = S. So once every segment has received at least its cap, the cache holds **exactly S** entries, not "≥ 0.75 × S"; it never holds more than S. Expiry (3 days) cannot act in a test of minutes. Eviction is silent (no removal listener, no metric); the evidence that it fired is registered − retained. (ii) **What an entry holds and its heap.** Per coordinator entry: the `CoordinatorState` (≈ 88 B shallow: the `AbstractCompletable`/`AbstractState` fields plus `cmd`, `keyspace`, `options`, `sessions`, `columnFamilies`, `neighborsAndRanges`, `phase`), its `long[6]` state times, an empty `ConcurrentHashMap` of sessions, a `Phase`, a `TimeUUID` (also the key), an `AtomicReference` for the result, and a `RepairOption` with four `HashSet`s ([`RepairOption.java:278-295`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/messages/RepairOption.java#L278-L295)); plus Guava's `LocalCache$StrongWriteEntry` and value reference. A bare state as in B2c (empty option) is about 0.6 KB. A state of B3's single-node repair also holds the failure `Result` with its message and a ranges set with one node per local range (16 with the shipped `num_tokens: 16`; the `Range` objects themselves come from the replica map and are shared), about 1.5 KB. A state of a real repair adds one `SessionState` per common range and one `JobState` per table ([`CoordinatorState.java:51`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/state/CoordinatorState.java#L51), [`SessionState.java:41-47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/state/SessionState.java#L41-L47)) and, after `phase.start`, references to the `ColumnFamilyStore` list and `NeighborsAndRanges`; **no knob bounds the bytes of one entry**, so `repair_state_size` caps bytes only as S × (that workload's entry size). (iii) **How the setter can be reached.** `setRepairStateSize` has no caller in `src/java` (search at the audit: only its definition, [`DatabaseDescriptor.java:5068`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L5068)); there is no MBean attribute or operation for it and no `nodetool` command; `system_views.settings` is read-only in 5.0.9 ([`SettingsTable.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/virtual/SettingsTable.java#L46), no update path). The yaml value is written into `Config.repair_state_size` by the YAML loader, not through the setter. So on a node line 5070 is never executed; B2 reaches it by a direct call, and B3 tests the constraint through startup (yaml). (iv) The value is read once per `ActiveRepairService` construction ([`ActiveRepairService.java:250-260`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L250-L260)); a node constructs it once (`ActiveRepairService.instance()`, started at [`CassandraDaemon.java:373`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/CassandraDaemon.java#L373)). Reason: the group A/B audit asks for the cache type, eviction arithmetic, entry cost and setter reachability to be derived from the source.

**A4. Other consumers.**
- `parentRepairSessions` and `sessions` maps (`ActiveRepairService.java:468,843`).
- Merkle trees, governed by `repair_session_space`.
- Consistent-repair `LocalSessions`.
- `repairStatusByCmd`.

**A5. Evidence beyond the source.** The virtual tables `system_views.repairs` and `system_views.repair_participates` list exactly the cache contents (`LocalRepairTables.java:80,119,276,295`; registered at `SystemViewsKeyspace.java:55`). Guava's `CacheBuilder.maximumSize` documentation says eviction may occur before the limit is exceeded and that the limit applies per segment: https://guava.dev/releases/32.0.0-jre/api/docs/com/google/common/cache/CacheBuilder.html#maximumSize(long). I found no Jira ticket in the tree for the setter.

## B. Verification solution

**B1. Claim under test.** With `repair_state_size: S` at startup, after N > S repair commands the coordinator cache holds at most S `CoordinatorState` objects, and their retained heap is bounded by S × the per-entry size. For N ≤ S, all N are retained. Calling `DatabaseDescriptor.setRepairStateSize(S')` after construction does not change how many entries are retained.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant.
- Clone with `git clone --depth 1 --branch cassandra-5.0.9 <shared-clone-path> /local/c509`. Never build in the shared clone.
- Test file: `/local/c509/test/unit/org/apache/cassandra/service/RepairStateSizeTest.java`.
- Run with `ant testsome -Dtest.name=org.apache.cassandra.service.RepairStateSizeTest -Dtest.jvm.args="-Dorg.apache.cassandra.disable_mbean_registration=true"`. The property lets more than one `ActiveRepairService` be constructed in one JVM (`MBeanWrapper.java:61-65`, `CassandraRelevantProperties.java:383`; `test.jvm.args` is passed at `build.xml:94,1192`). The heap is 1024 MiB.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2a, this host.** Run clone `$W/cassandra-run27` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run27`, full clone at `b5f2a54210`, `ant -Dlocal.repository=$W/m2 build-test`), macOS arm64, JDK 11.0.32.1, Ant 1.10.18. The test class is kept under `stage4-runtime-verification/harness/<stem>/RepairStateSizeTest.java` and copied into the clone's `test/unit/org/apache/cassandra/service/` by `unit-run.sh`, which runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.service.RepairStateSizeTest -Dtest.jvm.args=-Dorg.apache.cassandra.disable_mbean_registration=true` three times (r1, r2, r3). Instrument check (audit): the class compiles in the run clone (`ant build-test`, `BUILD SUCCESSFUL`, `$W/logs/repair_state_size-setRepairStateSize/audit-compile.log`). Reason: B2a named a CloudLab path.

**B2b. Knobs.**
- S is set with `DatabaseDescriptor.setRepairStateSize(S)`, which exercises the target line, **before** constructing a new `ActiveRepairService`. Values: S ∈ {10, 100, 1000, 100000}, spanning four orders of magnitude, with 100000 as the default.
- Post-construction control: build with S = 100, then call `setRepairStateSize(100000)` and register again.

**B2c. Workload.** Register N = 5000 `CoordinatorState`s, each `new CoordinatorState(Clock.Global.clock(), i, "ks", RepairOption.parse(new HashMap<>(), Murmur3Partitioner.instance))`, through `service.register(state)` (`ActiveRepairService.java:1202-1205`). N > S for S ≤ 1000, so the limit is crossed. N < S for 100000, which is the not-binding control.

**B2d. Observables and instruments.**
- `service.coordinators().size()` after `cleanUp`. Reach the cache through reflection (field `repairs`) and call `cleanUp()`.
- `ObjectSizes.measureDeep(new ArrayList<>(service.coordinators()))` for the retained bytes.
- The log line at `:252` for the size that was read.

Real states hold more fields, such as sessions and ranges, than these bare ones, so the byte figures are a lower bound per entry.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2d, where each reading is read.** The unit JVM routes `System.out` to the logger (`test/conf/logback-test.xml`; seen in the closed `repair_session_max_tree_depth` setter case), so every reading is read from the test log `build/test/logs/**/TEST-org.apache.cassandra.service.RepairStateSizeTest.log`, not the XML: the test's own lines (prefix `RSS `), the startup line `Storing repair state for … or for <S> elements` (`ActiveRepairService.java:252`, one per construction) and the setter's line `Setting repair_state_size to <S>` (`DatabaseDescriptor.java:5072`, one per call whose value differs). Added observable: `registered` (the number of `register` calls per arm), so that evicted = registered − retained is read, not assumed. Reason: the output location in B2e is wrong for this build, and eviction is silent (A3 amendment).

**B2e. Procedure.**
```java
package org.apache.cassandra.service;
public class RepairStateSizeTest {
  @BeforeClass public static void init() { org.apache.cassandra.ServerTestUtils.daemonInitialization(); }
  static long retained(ActiveRepairService s) throws Exception {
    java.lang.reflect.Field f = ActiveRepairService.class.getDeclaredField("repairs"); f.setAccessible(true);
    ((com.google.common.cache.Cache<?, ?>) f.get(s)).cleanUp(); return s.coordinators().size();
  }
  @Test public void size() throws Exception {
    for (int S : new int[]{10, 100, 1000, 100000}) {
      DatabaseDescriptor.setRepairStateSize(S);
      ActiveRepairService svc = new ActiveRepairService();
      for (int i = 0; i < 5000; i++)
        svc.register(new CoordinatorState(Clock.Global.clock(), i, "ks", RepairOption.parse(new HashMap<>(), Murmur3Partitioner.instance)));
      System.out.printf("S=%d retained=%d bytes=%d%n", S, retained(svc), ObjectSizes.measureDeep(new ArrayList<>(svc.coordinators())));
    }
    DatabaseDescriptor.setRepairStateSize(100);
    ActiveRepairService svc = new ActiveRepairService();
    DatabaseDescriptor.setRepairStateSize(100000);
    for (int i = 0; i < 5000; i++)
      svc.register(new CoordinatorState(Clock.Global.clock(), i, "ks", RepairOption.parse(new HashMap<>(), Murmur3Partitioner.instance)));
    System.out.printf("postConstructionSet retained=%d%n", retained(svc));
  }
}
```
Imports: `java.util.*`, `org.junit.*`, `org.apache.cassandra.config.DatabaseDescriptor`, `org.apache.cassandra.repair.state.CoordinatorState`, `org.apache.cassandra.repair.messages.RepairOption`, `org.apache.cassandra.dht.Murmur3Partitioner`, `org.apache.cassandra.utils.Clock`, `org.apache.cassandra.utils.ObjectSizes`. Run three times. The output is in `build/test/output/TEST-org.apache.cassandra.service.RepairStateSizeTest.xml`.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2e, the procedure as run.** The filed skeleton is kept, with three changes that do not touch what is measured: (i) each `printf` becomes one `System.out.println(String.format(…))` with the prefix `RSS ` (B2d amendment); (ii) a line `RSS start getter=<v>` before the loop, the `registered` count in each arm's line, and the getter in the post-construction line; (iii) after the post-construction control, `setRepairStateSize(100000)` is called once more with the value it already has (the false branch of line 5070) and `RSS sameValueSet getter=<v>` is printed. Readings are in the test log (B2d amendment), not `build/test/output/TEST-….xml`. Run three times (r1–r3) by `unit-run.sh`. Reason: the output location, and an exercise of both branches of the target line.

**B2f. Predictions.**
- **Retained count.** `retained` ≤ S for S = 10, 100 and 1000, and ≥ 0.75 × S. Guava's per-segment limits with the default concurrency level of 4 can evict slightly early. For S = 100000, `retained` = 5000.
- **Bytes.** `bytes` scales with `retained`: bytes(1000)/bytes(100) ≈ 10 ± 2.
- **Post-construction control.** `postConstructionSet retained` ≤ 100. The setter does not resize the live cache.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2f, exact values derived at the audit.** (i) **Retained count:** exactly **10, 100, 1000** for S = 10, 100, 1000 (Guava caps sum to S, A3 amendment; with 5,000 keys each segment receives far more than its cap), and **5000** for S = 100000; `registered` = 5000 in every arm. The filed band (≤ S and ≥ 0.75 × S) stays the condition for the cap; "exactly S" is the derived expectation, with its own row in B2g. (ii) **Post-construction control:** `postConstructionSet retained` = **100** exactly, with `getter` = 100000 (the setter changed the field but not the live cache). (iii) **Bytes:** bytes(1000)/bytes(100) in [8, 12] (the filed 10 ± 2); added: bytes(100000-arm, 5000 entries)/bytes(1000) in [4, 6], and bytes/retained in [300, 1500] B for S ≥ 100 (bare entry ≈ 0.6 KB, A3 amendment); the S = 10 arm's bytes are recorded only (the shared objects of `measureDeep` are not negligible against 10 entries). (iv) **Log lines:** `start getter` = 100000 (the test yaml does not set the entry; default `Config.java:958`); `Storing repair state` lines with the values **10, 100, 1000, 100000, 100** in that order (one per construction; a further line could only come from another construction and is reported); `Setting repair_state_size` lines with the values **10, 100, 1000, 100000, 100, 100000** — exactly 6, none for the same-value call; `sameValueSet getter` = 100000. (v) Every prediction holds in each of the three runs. Reason: the filed band was looser than the Guava arithmetic; the log counts and the bytes bands were not stated. No filed value is widened.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| retained ≤ S for all S < N, = N otherwise, bytes ∝ retained | Claim confirmed |
| retained = 5000 for S = 10 | Size not applied (claim wrong) |
| postConstructionSet retained > 100 | Setter does affect live cache (A3 wrong) |
| retained ≪ 0.75 × S | Guava evicts far earlier than the configured size; cap holds but is looser than stated (report) |

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2g, the rows the audit adds.** Row 1 ("claim confirmed") requires all of: retained ≤ S for S = 10, 100, 1000 and = 5000 for S = 100000; registered = 5000; post-construction retained ≤ 100 with getter 100000; bytes(1000)/bytes(100) in [8, 12]; the `Storing` values 10, 100, 1000, 100000, 100; in all three runs. It is reported as two findings, kept apart: **entry count capped** (the retained counts) and **bytes of the cached entries follow the count** (the bytes ratios). Added rows:

| Observation | Meaning |
|---|---|
| retained < S for some S < N (but ≥ 0.75 × S), all else as row 1 | Cap holds; the audit's "exactly S" (Guava layout) is wrong — Confirmed, reported |
| counts as row 1 but bytes(1000)/bytes(100) outside [8, 12] or bytes(5000)/bytes(1000) outside [4, 6] | Entry count capped; bytes of the retained entries not shown to follow it — Not confirmed for bytes |
| bytes/retained outside [300, 1500] B with the ratios in band | Confirmed; the audit's entry-size estimate is wrong (reported) |
| a `Storing` value ≠ the S set before that construction | The constructor did not read the set value — Refuted (A3 wrong) |
| `Setting` lines ≠ the 6 values, or a line for the same-value call | Target line's change detection not as traced (reported; does not change the cache result) |
| registered ≠ 5000 in an arm | Invalid run |
| the three runs disagree on a count | Not confirmed (report) |
| compile or run failure | Runbook defect (stop) |

**B2h. Controls.**
- A fresh service for each S.
- The same N and the same state shape.
- S = 100000 as the not-binding control.
- The post-construction setter control.
- Three repetitions.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node built from `/local/c509` with `ant jar`. Copy the config to `/local/rs/conf`.
- In the yaml, add `repair_state_size: <S>`, and point data, commitlog, hints, saved_caches and cdc under `/local/rs/`.
- JVM options: `-Xms1G -Xmx1G`.
- Start: `CASSANDRA_CONF=/local/rs/conf CASSANDRA_LOG_DIR=/local/rs/logs bin/cassandra -p /local/rs/pid`.
- At least 3 GB free on `/local`.
- Schema: `CREATE KEYSPACE rs WITH replication = {'class':'SimpleStrategy','replication_factor':2}; CREATE TABLE rs.t (k int PRIMARY KEY, v int);`. RF 2 is required so that `allReplicas >= 2`; otherwise no coordinator is created (`StorageService.java:4797-4798`). On one node the repair then has no neighbours and finishes or fails quickly, but the state is registered in the constructor first.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3a, this host.** One node on `127.0.0.1` from the run clone `$W/cassandra-run27` (its `build-test` includes the jar), conf rebuilt for each value by `harness/<stem>/make-node-conf.sh <S>` under `$W/node-rss/n1/` (the tag's `cassandra.yaml` plus `cluster_name: rss`, data, commitlog, hints, saved_caches and cdc directories under `$W/node-rss/n1/`, and `repair_state_size: <S>`; the shipped `num_tokens: 16` is kept), JMX on 7199 (the tag's `cassandra-env.sh`, local, no auth), `MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M`, started with `nohup bin/cassandra -f` and stopped with `nodetool drain` then `kill` (macOS has no `setsid`); about 136 GiB free on the SSD. The schema is created once and the data directory kept between values (B3e); `$W/node-rss` is wiped at the start and the end. Reason: B3a named CloudLab paths.

**B3b. Knobs.** `repair_state_size` in the yaml, with a restart for each value: S ∈ {50, 500, 100000}. There is no runtime path.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3b, no runtime path.** Confirmed at the audit (A3 amendment (iii)): the setter holding line 5070 cannot be reached on a node (no caller, no JMX, no nodetool, read-only settings table), and the yaml value bypasses it. This tier therefore tests the constraint through startup only and never executes line 5070; the post-construction behaviour of the setter is tested only by B2. Reason: stated so the cluster verdict is not read as a test of the setter.

**B3c. Workload.** N = 2000 repair commands through JMX `StorageServiceMBean.repairAsync("rs", {})` (`StorageServiceMBean.java:476`), issued from this client saved as `/local/tools/Rep.java`:
```java
import javax.management.*; import javax.management.remote.*; import java.util.*;
public class Rep { public static void main(String[] a) throws Exception {
  MBeanServerConnection m = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + "/jmxrmi")).getMBeanServerConnection();
  ObjectName ss = new ObjectName("org.apache.cassandra.db:type=StorageService"); int n = Integer.parseInt(a[1]);
  for (int i = 0; i < n; i++) { m.invoke(ss, "repairAsync", new Object[]{"rs", new HashMap<String, String>()}, new String[]{"java.lang.String", "java.util.Map"}); if (i % 50 == 49) Thread.sleep(1000); }
  System.out.println("issued " + n); } }
```
Throttling to 50 per second keeps the executor queue short. The run takes about 40 s.

**B3d. Observables and instruments.**
- `bin/cqlsh -e "SELECT count(*) FROM system_views.repairs"`. This counts the entries in the `repairs` cache.
- `jmap -histo:live $(cat /local/rs/pid) | grep -E 'repair.state.(CoordinatorState|SessionState|JobState)$'` for instance counts and shallow bytes.
- `jcmd <pid> GC.run` followed by `GC.heap_info` for used heap.
- The startup log line "Storing repair state for … or for S elements".

Deep bytes per entry are not directly visible. Estimate them as the Δ used-heap divided by retained entries.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3d, instruments on this host.** `jmap -histo:live` and `GC.run` + `GC.heap_info` are replaced by `jcmd <pid> GC.class_histogram` (it forces a full GC; its `Total` bytes is the live-heap reading — `GC.heap_info`'s used counts young regions, closed cases on this machine). Read from each histogram: `Total`, and instances/bytes of `org.apache.cassandra.repair.state.CoordinatorState`, `CoordinatorState$Phase`, `org.apache.cassandra.repair.messages.RepairOption`, `org.apache.cassandra.repair.RepairCoordinator` (queued or running commands), `org.apache.cassandra.repair.state.ParticipateState`, `com.google.common.cache.LocalCache$StrongWriteEntry`. Added: `SELECT count(*) FROM system_views.repair_participates` (the participant cache, `LocalRepairTables.java:295`); from the part of `system.log` written after the baselines (by byte offset): the number of `Starting repair command #` lines, of `Nothing to repair for` and of `WARN … Repair … aborted` lines, and of `^ERROR` lines; `Rep.java`'s `issued N`. Rep.java runs in source mode from `$W/tools-rss/Rep.java` with its working directory in `$W`. On one node every repair fails in `getNeighborsAndRanges` with "Nothing to repair … aborting" (`RepairCoordinator.java:373-396`) after the constructor has registered its state (`RepairCoordinator.java:128-132`) and before any prepare, so the participant cache stays empty (`ActiveRepairService.java:684` is not reached). Reason: the jmap/heap_info pair is not the live heap on this JDK, and the count of commands that reached the coordinator was not observed.

**Amendment 2026-10-28 (after run 1, authorised by the user; Claude Opus 5.5, claude-opus-5-5) — B3d, instrument (6): the retained heap of the `repairs` cache, read from one heap dump.** This amendment follows run 1's readings (results file §4–§5: the cluster tier was Not confirmed only because the bytes relation "Δ difference = Δcount × e" needs the common part of the live-heap total to cancel between node starts, and it did not: Δ(500) came out 1.2 MB below Δ(50)). The user (Yang, the advisor) authorised an amendment and a re-run of the whole cluster tier on 2026-10-28. (i) **What is measured.** After each value's workload (and, as a null control, before it, in the same node start) the node's live heap is dumped with `jcmd <pid> GC.heap_dump <file>` (live objects only, after a full GC), and `harness/<stem>/HprofRetained.java` (observe-only; it reads the dump and the class histogram taken just before it) computes three reachability sets from the GC roots (every root record of the dump and every class): **A** all; **B** with the one reference held in `ActiveRepairService.repairs` (`ActiveRepairService.java:191`) removed; **C** with no `org.apache.cassandra.repair.state.CoordinatorState` entered. **R_cache = bytes(A) − bytes(B)** is the heap that only the coordinator cache keeps alive; **R_values = bytes(A) − bytes(C)** is the heap that only the cached states keep alive (the states and everything only they reach). Also read: the number of `CoordinatorState` objects in the dump, reachable in A, and reachable in B (states held outside the cache), and whether the cut field's referent is still reachable in B. Shallow sizes are the JVM's own: instances from the histogram row of their class (bytes / instances), arrays 16 B + length × element size rounded up to 8 (compressed oops and class pointers, 1 GiB heap); `java.lang.Class` objects are roots in all three sets and cancel. (ii) **Why this instrument, from the source.** B1's bytes half is about the states' *retained* heap; R_values is that quantity by definition, and it is an absolute reading inside one node start, so nothing has to cancel between starts. The alternatives named in the authorisation do not work here: S cannot be varied in one JVM, because `maximumSize` is fixed when `ActiveRepairService` is constructed (`ActiveRepairService.java:250-256`) and the setter has no runtime path (A3 amendment (iii), B3b amendment); there is no weigher (the cache counts entries, A3 amendment (i)), so there is no byte figure inside the cache for a probe to observe; and class-histogram instance counts × size cannot attribute most of an entry, because the classes of its bytes (`HashMap$Node`, `HashMap`, `HashSet`, `String`, `byte[]`, `long[]`, `Range`, `ConcurrentHashMap`, `AtomicReference`) are shared with every other consumer — only `CoordinatorState`, `$Phase`, `RepairOption` and `Completable$Result` (192 of the 1,680 B derived in B3f (iv′)) are exclusive. A dump attributes every object. (iii) **Instrument checks (made before the re-freeze, 2026-10-28, not readings of this case):** a known answer outside Cassandra (`harness/<stem>/KnownAnswer.java`: a holder field → a box → 100 items, one of them also held by a static; the program dumps itself) — `HprofRetained` returned R_cache = 7,568 B and R_values = 7,200 B, the hand-computed values, and 1 item reachable after the cut; `harness/<stem>/EntryLayoutProbe.java` read the JVM's shallow sizes of every class on the per-entry list of B3f (iv′) on the run clone's classpath (`$W/logs/repair_state_size-setRepairStateSize/instrument-run2/`). Limits: the dump has no root record for the string table or for the instance fields of class mirrors (reflection data), so objects reachable only from those are "unreached" (≈ 6 % of the known-answer JVM's small heap; recorded per dump); an object held both by such a root and by the cache would be counted as retained — no repair-state object is held by either in the source read.

**B3e. Procedure.** For each S, in the order 50, 500, 100000:
1. Set the yaml value and start the node. Check the startup log line.
2. Create the schema if it is missing.
3. Take baselines: count₀ and used₀ (after GC ×2).
4. Run `java /local/tools/Rep.java 127.0.0.1:7199 2000`, then wait 60 s.
5. Record count₁, the histogram, and used₁ (after GC ×2).
6. Stop the node with `kill $(cat /local/rs/pid)`, wait for it to exit, and check `pgrep -f CassandraDaemon`.

The data directory can be kept between values, because the cache is in memory only.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3e, the procedure as run** (`harness/<stem>/cluster-run.sh run1 2000 50 500 100000`). Pre-checks: no `CassandraDaemon`, ports 7000, 7199, 9042 free. For each S in the order 50, 500, 100000: (1) rebuild the conf with S, start, wait for `UN` and `statusbinary` `running` (≤ 360 s), record the startup line; (2) create the schema on the first start only (`IF NOT EXISTS`); (3) count₀ and participates₀, then histogram A, 60 s, histogram B: used₀ = B's Total, drift₀ = B − A; (4) note the `system.log` offset, run `Rep.java 127.0.0.1:7199 2000` (exit code and `issued` line recorded); (5) wait 60 s, count₁ and participates₁, histogram after-A (used₁ = its Total, Δ = used₁ − used₀), 30 s, histogram after-B (drift₁ = after-B − after-A) and a second count; the log segment; (6) `nodetool drain`, `kill`, wait for exit, check no `CassandraDaemon`. After the last value: wipe `$W/node-rss`, check no `CassandraDaemon` and no `Rep.java`. A shakedown of the same script with N = 200 and S = 50 runs before run 1 (not judged) to check every step and that each frozen bound is measured by an instrument that sees it. Reason: B3e's baselines had no drift control and the order of reads was open.

**Amendment 2026-10-26 (after the cluster harness shakedown, before cluster run 1; Claude Opus 5.5, claude-opus-5-5) — B3e, settle before the baselines.** The shakedown (`cluster-run.sh shake 200 50`, not judged) ran every step, and its histograms showed the live heap still rising by about 0.9 MB in the 60 s baseline window that starts right after the node reports `UN`/`running` (drift₀), against about 1 KB over 30 s once the node had been up for some minutes (drift₁). The frozen resolvability rule (a Δ difference must exceed 3 × the largest drift) would then be set by start-up activity, not by the instrument's noise, and the smallest predicted difference (≈ 0.77 MB at the band's low end) could not be seen. Step (3) therefore starts with a **180 s settle** after the node is up and before histogram A; nothing else changes (no prediction, band or row of B3f/B3g). The Guava entry class of a size-bounded cache is `LocalCache$StrongAccessWriteEntry` (the shakedown read 0 for `$StrongWriteEntry`); the harness records both; neither is used by any prediction. Reason: an instrument check of the shakedown, made before any reading of cluster run 1.

**Amendment 2026-10-28 (after run 1, authorised by the user; Claude Opus 5.5, claude-opus-5-5) — B3e, the procedure as re-run.** This amendment follows run 1's readings (results file §4–§5: the cluster tier was Not confirmed only because the bytes relation "Δ difference = Δcount × e" needs the common part of the live-heap total to cancel between node starts, and it did not: Δ(500) came out 1.2 MB below Δ(50)). The user (Yang, the advisor) authorised an amendment and a re-run of the whole cluster tier on 2026-10-28. A **fresh clone** `$W/cassandra-run71` (`git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run71`, `ant -Dlocal.repository=$W/m2 build-test`) and node directory `$W/node-rss71`; command `RSS_C=$W/cassandra-run71 RSS_NODE=$W/node-rss71 RSS_DUMP=1 cluster-run.sh run2 2000 50 500 100000`, after a shakedown with the same settings (`shake2 200 50`, not judged). Every step of the 2026-10-26 procedure (pre-checks, conf, start, startup line, schema, 180 s settle, count₀, histograms base-a/base-b 60 s apart, Rep 2000, 60 s, count₁, histograms after-a/after-b 30 s apart, second count, log segment, stop) is kept in its order, with two added readings: (3′) right after histogram base-b, `jcmd <pid> GC.heap_dump S<v>/dump-base.hprof` (empty cache: the null control of B3h); (5′) right after the second count, `jcmd <pid> GC.heap_dump S<v>/dump-after.hprof`. After the node is stopped, `HprofRetained` analyses each dump with the histogram taken just before it (base-b, after-b), cut class `org.apache.cassandra.service.ActiveRepairService`, field `repairs`, value class `org.apache.cassandra.repair.state.CoordinatorState`. Raw logs to `$W/logs/repair_state_size-setRepairStateSize/cluster-run2/` (the dumps stay there, outside the repo; about 0.1 GB each). Excerpts to `results/<stem>/run1b-cluster/`.

**B3f. Predictions.**
- **Entry count.** count₁ ≤ 50, ≤ 500 and = 2000 (± failed submissions) for S = 50, 500 and 100000. The count is also ≥ 0.75 × S for S ≤ 500.
- **Heap instances.** The CoordinatorState instance count in the histogram is ≤ count₁ + (queued, not yet run), and should equal count₁ after the 60 s wait.
- **Heap bytes.** (used₁ − used₀) is greater at 100000 than at 500, by about (2000 − 500) × the per-entry size. A per-entry size of a few KB is expected, so a few MB in total. That is small, and it is reported as such.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3f, exact values derived at the audit.** (i) **Entry count:** count₁ = exactly **50, 500, 2000** for S = 50, 500, 100000 (Guava caps 13+13+12+12 and 4 × 125 sum to S; each segment receives ≈ 500 of the 2,000 keys; A3 amendment), the same in the second count 30 s later; count₀ = 0 (fresh start). The filed "≤ S and ≥ 0.75 × S" stays the condition for the cap. (ii) **Commands:** `issued 2000`, Rep exit 0, and 2,000 `Starting repair command #` lines and 2,000 `Repair … aborted: Nothing to repair` WARN lines in each value's log segment. (iii) **Heap instances:** after the 60 s wait, `CoordinatorState` and `CoordinatorState$Phase` instances = count₁ exactly at every S (nothing else holds a state once its task has run, A3), `RepairCoordinator` instances = 0 (none queued), `ParticipateState` = 0 and participates₁ = 0 (one node, no prepare). (iv) **Heap bytes:** the bytes of the `CoordinatorState` row = count₁ × its shallow size (constant across S). The live-heap Δ = used₁ − used₀ contains the same N-dependent other consumers at every S (2,000 `parent_repair_history` updates with their stack traces in the `system_distributed` memtable, `SystemDistributedKeyspace.java:265-275`; 2,000 `repairStatusByCmd` entries; logging), which cancel in a difference between values; so Δ(100000) − Δ(500) ≈ 1,500 × e and Δ(100000) − Δ(50) ≈ 1,950 × e, with e (one failed-repair entry, A3 amendment (ii)) in **[0.5, 5] KB**: [768,000, 7,680,000] B and [998,400, 9,984,000] B. A difference counts as resolved only if it exceeds 3 × the largest |drift₀| or |drift₁| of the two values compared. The filed "a few MB" is this band. (v) **Startup line:** `Storing repair state for 3d or for <S> elements` once per start, with the yaml's S. Reason: the filed band was looser than the Guava arithmetic; the bytes prediction had no band and no drift control; the command and instance counts were open. No filed value is widened.

**Amendment 2026-10-28 (after run 1, authorised by the user; Claude Opus 5.5, claude-opus-5-5) — B3f (iv′), the bytes relations.** This amendment follows run 1's readings (results file §4–§5: the cluster tier was Not confirmed only because the bytes relation "Δ difference = Δcount × e" needs the common part of the live-heap total to cancel between node starts, and it did not: Δ(500) came out 1.2 MB below Δ(50)). The user (Yang, the advisor) authorised an amendment and a re-run of the whole cluster tier on 2026-10-28. The 2026-10-26 relations Δ(100000) − Δ(500) ≈ 1,500 × e, Δ(100000) − Δ(50) ≈ 1,950 × e and their resolvability rule are **kept as records, not conditions** (the live-heap Totals and drifts are still read). They are replaced, as conditions, by (iv′-1)–(iv′-4) on instrument (6) of B3d, each read in one node start; count, command, instance and startup predictions (i)–(iii), (v) are unchanged. **Derivation of one entry, from the source.** Each `repairAsync` builds `RepairOption.parse(spec)` with an empty spec (`StorageService.java:4771-4773`; `RepairOption.java:209`: four empty `HashSet`s, `:292-295`), adds the node's 16 local full ranges (`StorageService.java:4795`; one node, `num_tokens: 16`, so every token's range is local), each a **new** `Range` made by `SimpleStrategy.calculateNaturalReplicas` (`SimpleStrategy.java:68`, called per token by `AbstractReplicationStrategy.getAddressReplicas`, `:239-255`) over tokens that stay in the token metadata (shared); builds a `RepairCoordinator` whose constructor makes the `CoordinatorState` with a new `TimeUUID` and registers it under that id (`RepairCoordinator.java:128-132`, `ActiveRepairService.java:1202-1205`); the keyspace string is the one the JMX call deserialised (one per call). The run sets SETUP (`RepairCoordinator.java:292`, no allocation), fails in `getNeighborsAndRanges` (`:396`), and `fail(e.getMessage())` (`:283-287`) stores `Result.fail(reason)` (`:220`; `AbstractCompletable.java:97-104,139-142`; `Completable.java:68-80`) and puts **the same `reason` string** into `repairStatusByCmd` (`:236-237`, `ActiveRepairService.java:525-528`; that cache keeps 100,000 entries for 1 day, `CassandraRelevantProperties.java:392-393`), so the message is not retained by the state. `columnFamilies` and `neighborsAndRanges` stay null (`CoordinatorState.java:53-54`, set only at `:153-157`, not reached); `sessions` is an empty `ConcurrentHashMap` (`:51`). So one entry's state retains exactly: `CoordinatorState` 88 B, `long[6]` (`AbstractState.java:58`, six `State` constants, `CoordinatorState.java:41-46`) 64 B, `$Phase` 24 B, `AtomicReference` 16 B, `Completable$Result` 24 B, `ConcurrentHashMap` 64 B, the keyspace `String` 24 B + `byte[2]` 24 B, `RepairOption` 56 B, 4 `HashSet` 64 B and 4 `HashMap` 192 B, one `HashMap$Node[32]` 144 B (16 adds: the table grows from 16 to 32 at the 13th), 16 `HashMap$Node` 512 B and 16 `Range` 384 B (`AbstractBounds.java:48-49`): **E_src = 1,680 B**. The cache's own structure per entry is the Guava `LocalCache$StrongAccessWriteEntry` 64 B, its `StrongValueReference` 16 B and the key `TimeUUID` (`TimeUUID.java:88`) 32 B: **112 B**. Shallow sizes from `EntryLayoutProbe` (B3d (iii)); arrays by the rule in B3d (i). Segment tables (Guava 32.0.1, `javap` of the pinned jar: initial capacity min(16, S) over 4 segments → table length 4; `Segment.put` expands when count + 1 > threshold; `expand` doubles with threshold = 3/4 × length; a put reaches cap + 1 before it evicts): length 32 for the caps 13/13/12/12 (S = 50), 256 for 4 × 125 (S = 500), 1024 for ≈ 500 entries per segment (S = 100000; 512 for a segment that never exceeds 384), each table an `AtomicReferenceArray` 16 B + `Object[L]` 16 + 4L B: **T = 640, 4,224 and 16,512 B**, and 192 B in an empty cache. **Conditions:** (iv′-1) in each after-dump, `CoordinatorState` objects = count₁, all reachable, **none reachable with the cut** (no state is held outside the cache), and the `repairs` referent unreachable with the cut. (iv′-2) **e_v = R_values / count₁ in [512, 5120] B at every S** (the frozen e band, unchanged) and **max e_v / min e_v ≤ 1.01 over the three values** (R_values ∝ count₁: the per-entry graph above is the same for every command of this workload and no object is held only by several entries; 1 % allows for one stray object at S = 50). (iv′-3) **null control**: in each base dump (empty cache), R_values = 0 and `CoordinatorState` objects = 0. (iv′-4) **R_cache ≤ count₁ × (e_v + 112) + T + 4,096 B** at every S (4,096 B for the cache's fixed objects: `LocalManualCache`, `LocalCache`, the segment array and per segment the `Segment`, its lock, recency, write and access queues with their heads, about 1.2 KB derived from the same jar), and R_cache(50) < R_cache(500) < R_cache(100000). **Derived expectations (reported if missed; not conditions):** e_v = E_src = 1,680 B exactly at every S; structure(after) − structure(base) = 112 × count₁ + T − 192 B exactly, where structure = R_cache − R_values. **What I knew of run 1 when writing this:** all of results §4.1–§5 of run 1 — the counts, the live-heap Totals and drifts, the Δ differences (2,739,488 and 1,539,920 B, e = 1,826 and 790 B), Δ(500) − Δ(50) = −1,199,568 B, and the histogram rows of run 1 for `CoordinatorState` (88 B), `$Phase` (24 B), `RepairOption` (56 B), `Completable$Result` (24 B), `LocalCache$StrongAccessWriteEntry` (64 B) and `$StrongValueReference` (16 B) per instance. The sizes used above were read again from the fresh probe (they agree); E_src, 112 B, T and every band come from the source and the jar, not from run 1. **Would run 1 pass?** It cannot be evaluated: run 1 took no heap dump, so under the amended B3g its bytes half falls in the Invalid row (instrument (6) missing); its count half would hold as before.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| count₁ tracks min(S, N) and instance counts agree | Claim confirmed on a node |
| count₁ = 2000 for S = 50 | Size not applied (claim wrong) |
| count₁ ≤ S but CoordinatorState instances ≫ S after wait | Objects retained elsewhere (executor queue, listeners): the cap governs the cache, not the heap (claim partially wrong) |
| count₁ = 0 for all S | Repairs not reaching the coordinator (RF/keyspace setup wrong): not confirmed |

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3g, the rows the audit adds.** Row 1 ("claim confirmed on a node") requires: count₁ ≤ S for S = 50, 500 and = 2000 for 100000 (with `issued 2000` and 2,000 `Starting` lines per value); `CoordinatorState` instances = count₁ at each S; `RepairCoordinator` = 0; the startup line shows the yaml's S. Its two findings are reported apart: **entry count capped** (count₁ and the instance counts) and **bytes capped** (the `CoordinatorState` row's bytes ∝ count₁, and Δ(100000) − Δ(500) and Δ(100000) − Δ(50) resolved and positive). Added rows:

| Observation | Meaning |
|---|---|
| count₁ < S for S = 50 or 500 (but ≥ 0.75 × S), all else as row 1 | Cap holds; the audit's "exactly S" is wrong — Confirmed, reported |
| count part of row 1 holds, but a Δ difference is not resolved (≤ 3 × drift) or not positive | Entry count capped; heap bytes not shown to follow it — Not confirmed for bytes |
| count part holds and both Δ differences resolved and positive, but e outside [0.5, 5] KB | Confirmed; the audit's entry-size estimate is wrong (reported) |
| `RepairCoordinator` instances > 0 after the wait | Commands still queued or running hold states outside the cache (A3 bypass seen) — report; Not confirmed if instances of `CoordinatorState` exceed count₁ because of it |
| startup line ≠ yaml S | Invalid run (value not applied) |
| issued < 2000, or `Starting` lines ≠ issued | Invalid for that value (workload did not reach the coordinator as designed) |
| participates₁ > 0 | Unexpected on one node (report); does not change the coordinator result |
| the 30 s second count ≠ count₁ | Report (expiry or late commands); Not confirmed if it exceeds S |

**Amendment 2026-10-28 (after run 1, authorised by the user; Claude Opus 5.5, claude-opus-5-5) — B3g, rows read with B3f (iv′).** This amendment follows run 1's readings (results file §4–§5: the cluster tier was Not confirmed only because the bytes relation "Δ difference = Δcount × e" needs the common part of the live-heap total to cancel between node starts, and it did not: Δ(500) came out 1.2 MB below Δ(50)). The user (Yang, the advisor) authorised an amendment and a re-run of the whole cluster tier on 2026-10-28. Row 1's bytes half ("bytes capped") now requires B3f (iv′-1)–(iv′-4) instead of "Δ(100000) − Δ(500) and Δ(100000) − Δ(50) resolved and positive"; its count half is unchanged. The 2026-10-26 added row "count part holds, but a Δ difference is not resolved (≤ 3 × drift) or not positive" and the e-band row on the Δ estimate are **superseded for this tier** (their quantities are recorded). Added rows:

| Observation | Meaning |
|---|---|
| count part of row 1 holds, (iv′-1) fails: a `CoordinatorState` reachable outside the cache (or instances ≠ count₁) | The cap governs the cache, not all state objects (A3 bypass) — Not confirmed for bytes (report the holder) |
| count part holds, (iv′-2) or (iv′-4) fails | Entry count capped; the cache's retained heap not shown to follow it — Not confirmed for bytes |
| (iv′-3) fails, a dump or its analysis is missing, the `repairs` referent is still reachable with the cut, or the analyser's known answer fails | Instrument (6) does not isolate the cache — Invalid for bytes; the tier is then Not confirmed — caps (entry count) |
| count part and (iv′-1)–(iv′-4) hold, but e_v ≠ 1,680 B or structure(after) − structure(base) ≠ 112 × count₁ + T − 192 | Confirmed; the derived entry or structure size is wrong (reported with the per-class breakdown) |

**B3h. Controls.**
- The same N and the same keyspace for every S.
- A restart for each S, with the value confirmed in the startup log.
- S = 100000 as the not-binding control.
- A 60 s settle period before reading, so that queued tasks drain.

**Amendment 2026-10-28 (after run 1, authorised by the user; Claude Opus 5.5, claude-opus-5-5) — B3h, null control for instrument (6).** This amendment follows run 1's readings (results file §4–§5: the cluster tier was Not confirmed only because the bytes relation "Δ difference = Δcount × e" needs the common part of the live-heap total to cancel between node starts, and it did not: Δ(500) came out 1.2 MB below Δ(50)). The user (Yang, the advisor) authorised an amendment and a re-run of the whole cluster tier on 2026-10-28. Each value's base dump, taken in the same node start after the settle and before the workload (count₀ = 0), is the null control of B3f (iv′-3): with an empty cache the analysis must find R_values = 0 and no `CoordinatorState`. The known answer outside Cassandra (B3d (iii)) is the instrument's positive control. The other controls are unchanged.

**B4. Risks and cleanup.**
- **Unit tier:** no data. Afterwards, `rm -rf /local/c509/build/test/cassandra`.
- **Cluster tier:**
  1. Stop the node with `kill $(cat /local/rs/pid)`.
  2. Check that `pgrep -f CassandraDaemon` and `pgrep -f Rep.java` are both empty.
  3. `rm -rf /local/rs`.
- Never write in the shared clone.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B4, this host.** Unit: after the three runs, remove `test/unit/org/apache/cassandra/service/RepairStateSizeTest.java` and `build/test/cassandra` from the run clone and check `git -C $W/cassandra-run27 status` shows no change to `test/conf/`. Cluster: `cluster-run.sh` stops the node (`nodetool drain`, `kill`, wait), checks `ps -eo command | grep '[C]assandraDaemon'` and `pgrep -f Rep.java` are empty, and removes `$W/node-rss`; full logs stay under `$W/logs/repair_state_size-setRepairStateSize/`. Reason: B4 named CloudLab paths.

**Amendment 2026-10-28 (after run 1, authorised by the user; Claude Opus 5.5, claude-opus-5-5) — B4, re-run paths.** This amendment follows run 1's readings (results file §4–§5: the cluster tier was Not confirmed only because the bytes relation "Δ difference = Δcount × e" needs the common part of the live-heap total to cancel between node starts, and it did not: Δ(500) came out 1.2 MB below Δ(50)). The user (Yang, the advisor) authorised an amendment and a re-run of the whole cluster tier on 2026-10-28. The re-run uses `$W/cassandra-run71` and `$W/node-rss71` (wiped before and after); the heap dumps stay under `$W/logs/repair_state_size-setRepairStateSize/cluster-run2/` and `cluster-shake2/`; the clone's `git status` must be clean at the end, and no `CassandraDaemon`, `Rep.java` or analyser process may be left.

## C. Sources read

- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
- src/java/org/apache/cassandra/service/ActiveRepairService.java
- src/java/org/apache/cassandra/service/StorageService.java
- src/java/org/apache/cassandra/service/StorageServiceMBean.java
- src/java/org/apache/cassandra/repair/RepairCoordinator.java
- src/java/org/apache/cassandra/repair/RepairMessageVerbHandler.java
- src/java/org/apache/cassandra/repair/state/{CoordinatorState,ParticipateState,SessionState,JobState,AbstractState,AbstractCompletable,ValidationState}.java
- src/java/org/apache/cassandra/db/virtual/LocalRepairTables.java
- src/java/org/apache/cassandra/db/virtual/SystemViewsKeyspace.java
- src/java/org/apache/cassandra/utils/MBeanWrapper.java
- build.xml
- https://guava.dev/releases/32.0.0-jre/api/docs/com/google/common/cache/CacheBuilder.html#maximumSize(long)

## D. Stage-4 feedback

**2026-10-26 — stage 4 run 1** (Claude Opus 5.5, claude-opus-5-5, on the advisor's machine; results: [`../../stage4-runtime-verification/results/repair_state_size-setRepairStateSize-size--autonomous.md`](../../stage4-runtime-verification/results/repair_state_size-setRepairStateSize-size--autonomous.md); uncommitted).

- **Unit: Confirmed — caps** (B2g row 1). Three identical runs: of 5,000 registered bare states the cache kept exactly 10, 100, 1000, and 5,000 at the default; deep bytes 604 B per entry (ratios 9.985 and 4.999); built at 100 and then set to 100000, the live cache kept 100; the setter logged `Setting repair_state_size` only when the value changed (6 lines, none for the repeated value), and each construction logged the value set before it.
- **Cluster: Not confirmed — caps (entry count)** (B3g added row "count part holds, Δ difference not resolved", reached through the self-check). One node, yaml S = 50, 500, 100000, 2,000 `repairAsync` commands each, all reaching the coordinator: `system_views.repairs` held exactly 50, 500, 2000; `CoordinatorState` instances on the live heap equalled those counts, none queued (`RepairCoordinator` 0); participant cache 0 (one node never prepares). The live-heap differences passed the frozen numbers (2.74 MB and 1.54 MB, e = 1,826 and 790 B), but Δ(500) came out 1.2 MB below Δ(50): the start-to-start variation of the other consumers (plausibly memtable slab regions of 1 MiB) is as large as the effect, so the bytes half of B1 is not shown on a node.
- Audit findings for stage 3: (i) Guava's `maximumSize` here is exact, not "≥ 0.75 × S": the segment caps sum to S (read from guava-32.0.1 at the audit: 50 → 13 + 13 + 12 + 12, 500 → 4 × 125, 10 → one segment), so a full cache holds exactly S, as both tiers showed; (ii) the setter holding line 5070 has no runtime path (no caller, no MBean, no nodetool, read-only `system_views.settings`) and the yaml bypasses it, so the line runs only when called directly, and it is dead code on a node; (iii) the bound is an entry count; one entry's bytes grow with sessions and jobs and no knob bounds them; (iv) the filed B2e output location (the XML) is wrong for this build: the unit JVM writes stdout to the test log; (v) the participant cache was not exercised (needs a ring of at least two nodes).
- No runbook defect. A post-shakedown amendment (B3e: 180 s settle before the baselines) was made before cluster run 1; no prediction changed.

**2026-10-28 — stage 4 cluster re-run ("run 1b")** (Claude Opus 5.5, claude-opus-5-5, on the advisor's machine; authorised by the user (Yang, the advisor) on 2026-10-28; results: §7 of [`../../stage4-runtime-verification/results/repair_state_size-setRepairStateSize-size--autonomous.md`](../../stage4-runtime-verification/results/repair_state_size-setRepairStateSize-size--autonomous.md); uncommitted).

- **Cluster: Confirmed — caps** (B3g row 1 with the amended B3f (iv′), through the added row "derived entry size wrong (reported)"), at the re-frozen version sha256 `92f32f87…ef3b` (six amendments `Amendment 2026-10-28 (after run 1, authorised by the user)`: B3d, B3e, B3f (iv′), B3g, B3h, B4). Fresh clone `$W/cassandra-run71`, shakedown first. Count half as in run 1: exactly 50 · 500 · 2000 states of 2,000 commands, instances = count, nothing queued, startup line = S. Bytes half, read inside each node start from a heap dump cut at `ActiveRepairService.repairs`: the cached states retain exactly **1,768 B each** at all three values (88,400 / 884,000 / 3,536,000 B), no state is reachable outside the cache, an empty-cache dump in the same start retains 0 B, and the cache as a whole retains 95,856 / 945,440 / 3,777,728 B (112 B of Guava entry, value reference and key per entry, the segment tables and 1,216 B of fixed objects, equal to the derivation to the byte). The live-heap Δ relations are now records; Δ(500) − Δ(50) = −1.2 MB recurred.
- Finding for stage 3: the source-derived entry size (1,680 B) missed 88 B of lazily cached collection views — `HashMap.keySet()` views cached when `RepairOption.toString()` (the "Starting repair command" log line) and `getNeighborsAndRanges` iterate the four sets, and the `ConcurrentHashMap.keySet()` view cached when the virtual table builds a row. The run-1 cluster verdict (Not confirmed — caps (entry count)) stays on record; the unit tier (Confirmed) was not re-run.
