# paxos_repair_parallelism — verification solution  <!-- file: cases/paxos_repair_parallelism-scheduleKeyRepairsOrFinish-inflight--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the if statement in `PaxosCleanupLocalCoordinator.scheduleKeyRepairsOrFinish`, **linked**: [`PaxosCleanupLocalCoordinator.java:128`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/paxos/cleanup/PaxosCleanupLocalCoordinator.java#L128) (with its fill loop at [`:138`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/paxos/cleanup/PaxosCleanupLocalCoordinator.java#L138)) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code (CLI version not visible to the agent), 2026-11-26 |
| Estimate | `positive`, with a scope caveat. The entry caps how many per-key Paxos repairs one local cleanup coordinator keeps in flight (`inflight.size() < parallelism`). Each in-flight repair holds the key's latest committed (and any accepted) `PartitionUpdate` received from the replicas, so the heap held by paxos cleanup scales with `min(parallelism, uncommitted keys) × update size`. The cap is per coordinator (per table and range session), not per node. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `paxos_repair_parallelism`, a cassandra.yaml configuration entry (`Config` field), declared at
[`Config.java:1144`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1144)
as `public volatile int paxos_repair_parallelism = -1;`. Javadoc at `Config.java:1140-1142`: "The number of keys we may
simultaneously attempt to finish incomplete paxos operations for."
- Unit: a count of partition keys (concurrent per-key Paxos repairs).
- Default: `-1` in `Config`, so a value `<= 0` is replaced at startup by `Math.max(1, concurrent_writes / 8)`
  (`DatabaseDescriptor.java:1007-1008`). With the shipped `concurrent_writes: 32` (`conf/cassandra.yaml:723`,
  `Config.java:180`) the effective default is **4**.
- How to set it: the yaml key `paxos_repair_parallelism: <int>` (not present in the shipped `conf/cassandra.yaml`, but
  accepted: `test/data/config/version=5.0-alpha1.yml:62`), which needs a restart; or live over JMX, MBean
  `org.apache.cassandra.db:type=RepairService` (`ActiveRepairServiceMBean.java:27`), attribute `PaxosRepairParallelism`
  (`ActiveRepairServiceMBean.java:75-76`, `ActiveRepairService.java:1177-1185`), which calls
  `DatabaseDescriptor.setPaxosRepairParallelism` (`DatabaseDescriptor.java:4118-4122`, rejects `v <= 0`). No nodetool
  command sets it. The field is `volatile` and read on every scheduling pass (`PaxosCleanupLocalCoordinator.java:126`),
  so a JMX change applies to running coordinators at their next pass.

**A2. What it caps.** Heap. The quantity compared against the limit is `inflight.size()`, the number of entries in the
coordinator's `ConcurrentHashMap<DecoratedKey, AbstractPaxosRepair> inflight` (`PaxosCleanupLocalCoordinator.java:70`),
i.e. the number of per-key Paxos repairs this coordinator has started and not yet seen finish. Each entry is a
`PaxosRepair` (`PaxosRepair.java:120`) whose `Querying` state (`PaxosRepair.java:163-288`) sends `PAXOS2_REPAIR_REQ` to
every replica (`:283-288`) and keeps, from the responses, `latestAccepted` (an `Accepted` with its full `PartitionUpdate`)
and `latestCommitted` (a `Committed` with its full `PartitionUpdate`) (`:170-173`, `:197-198`). Each replica's
`Response` carries both (`PaxosRepair.java:481-491`, built from the replica's `PaxosState` snapshot at `:557-583`; the
snapshot's `Committed`/`Accepted` include the stored update, `PaxosRows.java:92-124`). So the memory held per in-flight
key is about one to RF copies of the key's last committed/accepted update, plus message and state-machine overhead; the
cap bounds the number of such keys held at once by one coordinator.

**A3. Mechanism.**
1. A local cleanup coordinator is created per (table, ranges) either for a repair session — `PaxosCleanupRequest`
   verb handler, `PaxosCleanupRequest.java:85` (sent by `PaxosCleanupSession.startCleanup`, one endpoint at a time,
   `PaxosCleanupSession.java:~105-130`; started from `RepairJob.java:128-132` for `nodetool repair --paxos-only` or v2
   repairs, and from `ActiveRepairService.java:1169` for topology changes) — or for auto repair,
   `StorageService.autoRepairPaxos`, `StorageService.java:4951-4960`, scheduled per table by
   `PaxosUncommittedTracker.schedulePaxosAutoRepairs`, `PaxosUncommittedTracker.java:276-306` (every
   `cassandra.auto_repair_frequency_seconds`, default 300 s, `CassandraRelevantProperties.java:64`; at most one auto
   repair per table at a time, `:295`).
2. Its input is a streaming iterator over the uncommitted keys of the table and ranges
   (`PaxosUncommittedTracker.uncommittedKeyIterator`, `PaxosUncommittedTracker.java:192-215`), not a materialised list.
3. `start()` (`:86-106`) calls `scheduleKeyRepairsOrFinish()` (`:124-145`): it reads the entry (`:126`), and
   **the check** [`if (inflight.size() < parallelism)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/paxos/cleanup/PaxosCleanupLocalCoordinator.java#L128)
   gates a fill loop `while (inflight.size() < parallelism && uncommittedIter.hasNext()) repairKey(...)` (`:138-139`).
   `repairKey` (`:147-168`) puts the key into `inflight` with the repair obtained from
   `PaxosTableRepairs.startOrGetOrQueue` (`PaxosTableRepairs.java:151-155`, `:89-107`), which creates and starts a
   `PaxosRepair` (`:207-210`) or attaches to one already queued for the key.
4. Below the limit: more keys are pulled from the iterator and started. At the limit: nothing new is started; the
   coordinator returns and waits. Each finished key calls `onKeyFinish` (`:188-197`), which removes the key from
   `inflight` and re-runs the check, so the map refills one-for-one. A failed key cancels all in-flight repairs and
   fails the session (`:205-216`). When `inflight` is empty and the iterator is exhausted, the coordinator finishes
   (`:143-144`, `:218-229`).
5. Bypasses and overshoot:
   - **Per coordinator, not per node.** Every coordinator has its own `inflight` map. Concurrent coordinators on one
     node (auto repair for several tables, several repair sessions/ranges in one `nodetool repair`, topology-change
     repair) each get `parallelism`. Node-wide in-flight ≤ S × parallelism, S = concurrent coordinators.
   - `PaxosTableRepairs` is shared per table across coordinators on the node and can queue more than one repair per key
     (`PaxosTableRepairs.java:55`, `:93-106`); a coordinator's in-flight count counts keys, not queued repairs.
   - A repair whose quorum is reached keeps its callback registered until the remaining replica replies or the request
     times out, so a finished `PaxosRepair` can stay reachable briefly after leaving `inflight`.
   - `repairKey` returns without inserting when the key's consistency is unknown (`:155-156`), which only lowers usage.
   - `maybeWaitForOriginalCoordinator` (`:174-186`) can sleep inside the fill loop when `paxos_repair_race_wait` is
     true (default, `Config.java:1402`) and a ballot is recent; that delays scheduling, it does not exceed the cap.

**A4. Other consumers.** Heap used by paxos outside this cap: normal LWT/SERIAL client operations (bounded by client
concurrency and native transport limits); the `PaxosRepair` objects started by the replica side of other coordinators
(`PaxosRepair.RequestHandler`, `PaxosRepair.java:557-583`, which builds a response holding the update); paxos messages
queued in internode messaging; the `system.paxos` memtable, which stores every LWT update a second time
(`SystemKeyspace.java:229-236`) and so also uses memtable heap/off-heap and disk; the uncommitted-key index files
(`PaxosUncommittedTracker`, `UncommittedDataFile`) on disk. None of these is bounded by `paxos_repair_parallelism`.

**A5. Evidence beyond the source.** The Paxos v2 / paxos repair design (CEP-14, CASSANDRA-17164) introduced the entry;
`CHANGES.txt:308` (CASSANDRA-19668, repairIterator under OpOrder) and `:310` (CASSANDRA-19445, auto paxos repair
logging) touch the same path. The existing unit test `test/unit/org/apache/cassandra/service/paxos/cleanup/PaxosTableRepairsTest.java`
shows the mock-repair pattern reused in B2. No issue or doc found that measures memory against this entry.

## B. Verification solution

**B1. Claim under test.** On one node, the number of per-key Paxos repairs a single paxos cleanup coordinator holds at
once never exceeds `paxos_repair_parallelism`; and the extra heap held during a paxos cleanup grows with
`min(paxos_repair_parallelism, uncommitted keys) × (size of the keys' committed update)`, so lowering the entry lowers
the peak heap held by paxos cleanup and raising it raises it. The claim is wrong if the in-flight count exceeds the
entry for one coordinator, or if the peak extra heap does not change with the entry when the update size is large.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tag to local disk and build there, never in the shared
tree:
```
export S4=/mydata/<you>-s4/paxos_repair_parallelism     # local disk, >= 10 GiB free
mkdir -p $S4 && rsync -a <local copy of cassandra-5.0.9>/ $S4/src/
cd $S4/src && ant clean jar build-test
```
Test source location: `$S4/src/test/unit/org/apache/cassandra/service/paxos/cleanup/ParallelismCapProbeTest.java`
(same package as the coordinator, so package-private `PaxosTableRepairs.createRepair` and `PaxosRepairState.getForTable`
can be overridden). Run with heap fixed: `-Dtest.jvm.args="-Xms2g -Xmx2g -XX:+UseG1GC"` (`build.xml:94`, `:1192`).

**B2b. Knobs.** `p = paxos_repair_parallelism`, set in-process with `DatabaseDescriptor.setPaxosRepairParallelism(p)`
(the same setter JMX uses). Values: `1`, `4` (the derived default), `64`, `256`, and `1024` (> N, to show the iterator,
not the entry, then bounds it). Also one run with p changed from 4 to 64 mid-run (the volatile read at `:126`).
Fixed: N = 512 uncommitted keys, U = 1 MiB payload held per repair (stands in for the committed update a real
`PaxosRepair` holds).

**B2c. Workload.** A synthetic iterator of N = 512 `PaxosKeyState(tableId, key_i, ballot_i, false)` with
`ballot_i = BallotGenerator.Global.atUnixMicros(1_000_000L + i, Ballot.Flag.GLOBAL)` (old ballots, so
`maybeWaitForOriginalCoordinator` never sleeps; GLOBAL flag so `getConsistencyLevel()` is `SERIAL`,
`PaxosKeyState.java:62-70`). A `HoldingRepair extends AbstractPaxosRepair` allocates `new byte[U]` when created,
never completes on its own (`restart` returns a fresh `State`), and is completed by the driver with `set(DONE)`.
Arithmetic: with no cap, all 512 repairs would be live, 512 MiB; with cap p, live ≤ p × 1 MiB (4 MiB at p=4,
256 MiB at p=256). 512 MiB fits in a 2 GiB heap, so an uncapped mechanism is observable without OOM.

**B2d. Observables and instruments.**
- `inflight.size()` read by reflection after every driver step (the check's operand). Record its maximum.
- `live` = repairs created by `createRepair` minus those completed (AtomicInteger), maximum recorded.
- `created` total = N (every key repaired once).
- Heap: `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed()` after `System.gc()` twice, at the plateau
  (after the first scheduling pass, before completing any repair), minus the same value before the coordinator starts.
- Not observable here: real `PaxosRepair` message traffic and real update sizes (covered by B3).

**B2e. Procedure.**
1. Write the test (sketch; fields and classes as in the tree):
```java
package org.apache.cassandra.service.paxos.cleanup;
// imports: DatabaseDescriptor, DecoratedKey, Murmur3Partitioner, ByteBufferUtil, TableId, Ballot, BallotGenerator,
// AbstractPaxosRepair, PaxosRepair, ConsistencyLevel, TableMetadata, SharedContext, PaxosKeyState,
// UncommittedPaxosKey, CloseableIterator, java.lang.reflect.*, java.util.*, java.util.concurrent.*
public class ParallelismCapProbeTest {
  static final int N = 512, U = 1 << 20;
  static final AtomicInteger live = new AtomicInteger(), maxLive = new AtomicInteger();
  static final ConcurrentLinkedDeque<HoldingRepair> started = new ConcurrentLinkedDeque<>();

  static class HoldingRepair extends AbstractPaxosRepair {
    final byte[] payload = new byte[U];
    HoldingRepair(DecoratedKey k, Ballot b) { super(k, b); }
    public State restart(State s, long w) { started.add(this); return new State(); }
    void finish() { live.decrementAndGet(); set(DONE); }
  }
  static class Tables extends PaxosTableRepairs {
    @Override AbstractPaxosRepair createRepair(DecoratedKey k, Ballot b, ConsistencyLevel c, TableMetadata t) {
      maxLive.accumulateAndGet(live.incrementAndGet(), Math::max); return new HoldingRepair(k, b); }
  }
  static class State2 extends PaxosRepairState {
    final Tables t = new Tables(); State2(SharedContext c) { super(c); }
    @Override PaxosTableRepairs getForTable(TableId id) { return t; }
  }

  @BeforeClass public static void init() { DatabaseDescriptor.daemonInitialization(); }

  long run(int p, Integer switchTo) throws Exception {
    DatabaseDescriptor.setPaxosRepairParallelism(p);
    live.set(0); maxLive.set(0); started.clear();
    SharedContext ctx = new SharedContext.ForwardingSharedContext(SharedContext.Global.instance) {
      final State2 s = new State2(this);
      @Override public PaxosRepairState paxosRepairState() { return s; } };
    List<UncommittedPaxosKey> keys = new ArrayList<>();
    for (int i = 0; i < N; i++)
      keys.add(new PaxosKeyState(TableId.generate(), Murmur3Partitioner.instance.decorateKey(ByteBufferUtil.bytes(i)),
               BallotGenerator.Global.atUnixMicros(1_000_000L + i, Ballot.Flag.GLOBAL), false));
    Constructor<PaxosCleanupLocalCoordinator> k = PaxosCleanupLocalCoordinator.class.getDeclaredConstructor(
        SharedContext.class, UUID.class, TableId.class, Collection.class, CloseableIterator.class, boolean.class);
    k.setAccessible(true);
    PaxosCleanupLocalCoordinator c = k.newInstance(ctx, UUID.randomUUID(), TableId.generate(),
        Collections.emptyList(), CloseableIterator.wrap(keys.iterator()), true);
    Field f = PaxosCleanupLocalCoordinator.class.getDeclaredField("inflight"); f.setAccessible(true);
    Map<?,?> inflight = (Map<?,?>) f.get(c);
    Method m = PaxosCleanupLocalCoordinator.class.getDeclaredMethod("scheduleKeyRepairsOrFinish"); m.setAccessible(true);
    long h0 = heapAfterGc();
    synchronized (c) { m.invoke(c); }            // bypasses start(): no schema/peer check needed
    long plateau = heapAfterGc() - h0;
    int maxInflight = inflight.size(), done = 0;
    while (!c.isDone()) {
      if (switchTo != null && done == N / 4) DatabaseDescriptor.setPaxosRepairParallelism(switchTo);
      HoldingRepair r = started.poll(); if (r == null) break;
      r.finish(); done++;                         // triggers onKeyFinish -> refill
      maxInflight = Math.max(maxInflight, inflight.size());
    }
    System.out.printf("p=%d switch=%s maxInflight=%d maxLive=%d done=%d plateauMiB=%.1f isDone=%s%n",
        p, switchTo, maxInflight, maxLive.get(), done, plateau / 1048576.0, c.isDone());
    return plateau;
  }
  static long heapAfterGc() { System.gc(); System.gc();
    return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed(); }

  @Test public void sweep() throws Exception {
    for (int p : new int[]{1, 4, 64, 256, 1024}) run(p, null);
    run(4, 64);
    // control C2 (instrument check): hold K=256 payloads directly, no coordinator
    long h0 = heapAfterGc(); byte[][] hold = new byte[256][]; for (int i = 0; i < 256; i++) hold[i] = new byte[U];
    System.out.printf("control K=256 heldMiB=%.1f%n", (heapAfterGc() - h0) / 1048576.0); hold[0][0] = 1;
  }
}
```
   If `TableId.generate()` for the coordinator's table leaves `table == null`, that is fine: `start()` is bypassed and
   `table` only flows into `createRepair`, which ignores it.
2. `cd $S4/src && ant testsome -Dtest.name=org.apache.cassandra.service.paxos.cleanup.ParallelismCapProbeTest -Dtest.jvm.args="-Xms2g -Xmx2g -XX:+UseG1GC"`
3. Read the printed lines from `build/test/output/TEST-org.apache.cassandra.service.paxos.cleanup.ParallelismCapProbeTest.xml`
   (or stdout). Repeat step 2 three times.

**B2f. Predictions.**

| p | maxInflight | maxLive | done | plateau heap |
|---|---|---|---|---|
| 1 | 1 | 1 | 512 | ≈ 1 MiB (±16 MiB GC noise) |
| 4 | 4 | 4 | 512 | ≈ 4 MiB |
| 64 | 64 | 64 | 512 | ≈ 64 MiB |
| 256 | 256 | 256 | 512 | ≈ 256 MiB |
| 1024 | 512 (= N) | 512 | 512 | ≈ 512 MiB |
| 4 → 64 at 128 done | 64 after the switch (4 before) | 64 | 512 | ≈ 4 MiB (taken before the switch) |
| control K=256 | — | — | — | ≈ 256 MiB |

In all runs `isDone=true`, and plateau ≈ min(p, N) × 1 MiB.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| maxInflight = min(p, N) for every p, plateau ≈ min(p, N) MiB, control ≈ 256 MiB | Claim supported: the check caps the per-coordinator in-flight count and the held memory follows the entry |
| maxInflight > p for any p < N | Claim wrong: the check does not cap the operand |
| maxInflight = min(p, N) but plateau flat while the control reads ≈ 256 MiB | The count is capped but held memory does not follow it (in-flight objects do not hold the payload); claim about memory wrong |
| Control reads ≈ 0 or plateau noise > 32 MiB | Instrument not valid; increase U to 4 MiB and N to 256, rerun |
| The switch run never exceeds 4 | The entry is not re-read live; the JMX path would not take effect until restart |
| `done < N` or `isDone=false` | Driver or harness error, not a reading on the claim |

**B2h. Controls.** C1: p ≥ N run (1024) shows the iterator, not the entry, bounds usage there, so the lower runs are
attributable to the entry. C2: direct allocation of 256 × 1 MiB shows the heap instrument sees held payloads. C3: three
repetitions for GC noise. C4: `setPaxosRepairParallelism(0)` must throw `IllegalArgumentException`
(`DatabaseDescriptor.java:4120`) — confirms values ≤ 0 cannot be set live.

### B3. Cluster tier

**B3a. Environment and build.** One Linux machine with ≥ 16 GiB RAM and ≥ 30 GiB free local disk; three Cassandra
nodes on 127.0.0.1-3 via ccm, from the B2a build (`ant jar` in `$S4/src`). Python 3 with `pip install --user ccm cassandra-driver`.
```
export CCM_CONFIG_DIR=$S4/ccm                     # all node data, commit logs, logs on local disk
ccm create pr --install-dir=$S4/src -n 3 --config-dir=$CCM_CONFIG_DIR
ccm updateconf --config-dir=$CCM_CONFIG_DIR 'paxos_variant: v2' 'paxos_repair_race_wait: false' \
     'num_tokens: 1' 'commitlog_total_space: 2048MiB' 'concurrent_writes: 32'
for n in 1 2 3; do
  d=$CCM_CONFIG_DIR/pr/node$n/conf
  printf -- '-Xms3G\n-Xmx3G\n-Xmn600M\n-Dcassandra.disable_paxos_auto_repairs=true\n-Dcassandra.auto_repair_frequency_seconds=20\n-Xlog:gc*:file=%s/gc.log:time,uptime\n' \
     "$CCM_CONFIG_DIR/pr/node$n/logs" >> $d/jvm11-server.options
done
ccm start --config-dir=$CCM_CONFIG_DIR --wait-for-binary-proto
```
(If `jvm11-server.options` already sets `-Xms/-Xmx` via `cassandra-env.sh`, set `MAX_HEAP_SIZE=3G HEAP_NEWSIZE=600M` in
each node's `conf/cassandra-env.sh` instead.)

**B3b. Knobs.** `paxos_repair_parallelism` p ∈ {1, 4 (default), 64, 512}, set live on all three nodes:
`ccm node$n nodetool sjk mx -b org.apache.cassandra.db:type=RepairService -ms -f PaxosRepairParallelism -v <p>`
and read back with `-mg -f PaxosRepairParallelism`. (Fallback: `paxos_repair_parallelism: <p>` via `ccm updateconf`
and a restart.) Fixed: U = 256 KiB update per key, N = 4096 keys, RF = 3. Why: p=512 makes min(p,N)×U = 128 MiB
(×RF up to 384 MiB) of held updates, far above GC noise; p=4 makes ≤ 3 MiB.

**B3c. Workload.** Script `$S4/pr.py` (kept outside the source tree):
```python
import os, sys, uuid
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import WhiteListRoundRobinPolicy
from cassandra.concurrent import execute_concurrent_with_args
from cassandra import ConsistencyLevel as CL
mode, N, U = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
host = sys.argv[4] if len(sys.argv) > 4 else '127.0.0.1'
prof = ExecutionProfile(load_balancing_policy=WhiteListRoundRobinPolicy([host]), request_timeout=60)
s = Cluster([host], execution_profiles={EXEC_PROFILE_DEFAULT: prof}).connect()
if mode == 'write':
    s.execute("CREATE KEYSPACE IF NOT EXISTS pr WITH replication={'class':'SimpleStrategy','replication_factor':3}")
    s.execute("CREATE TABLE IF NOT EXISTS pr.t (k int PRIMARY KEY, v blob)")
    q = s.prepare("INSERT INTO pr.t (k, v) VALUES (?, ?) IF NOT EXISTS"); q.consistency_level = CL.QUORUM; q.serial_consistency_level = CL.SERIAL
    for k in range(N): s.execute(q, (k, os.urandom(U)))
elif mode == 'promise':          # SERIAL read leaves a read promise newer than the commit -> key is "uncommitted"
    q = s.prepare("SELECT k FROM pr.t WHERE k = ?"); q.consistency_level = CL.SERIAL
    execute_concurrent_with_args(s, q, [(k,) for k in range(N)], concurrency=16)
elif mode == 'check':            # count keys whose latest promise is newer than the latest commit (on `host`)
    n = 0
    for r in s.execute("SELECT in_progress_read_ballot, in_progress_ballot, most_recent_commit_at FROM system.paxos"):
        pr = max([b.time for b in (r.in_progress_read_ballot, r.in_progress_ballot) if b] or [0])
        if pr > (r.most_recent_commit_at.time if r.most_recent_commit_at else 0): n += 1
    print('uncommitted', n)
elif mode == 'readload':         # positive control: SERIAL reads of the full row at client concurrency U
    q = s.prepare("SELECT v FROM pr.t WHERE k = ?"); q.consistency_level = CL.QUORUM
    for _ in range(5): execute_concurrent_with_args(s, q, [(k,) for k in range(N)], concurrency=U)
```
Data: `python3 $S4/pr.py write 4096 262144` once (1 GiB table + ≈ 1 GiB in `system.paxos` per node; with commit log
≤ 2 GiB, ≈ 4-5 GiB per node, ≈ 15 GiB total). Per measured run: `python3 $S4/pr.py promise 4096 0`, wait 10 s, then
flush `system.paxos` on each node (`ccm node$n nodetool flush system paxos`) so the tracker has files
(`PaxosUncommittedTracker.java:283`), then check `python3 $S4/pr.py check 0 0 127.0.0.$n` = 4096 on each node.
Duration: at p=4 a run is ≈ 1024 rounds of a few ms to tens of ms (≈ 5-30 s); at p=512 a few seconds.

**B3d. Observables and instruments.**
- Live in-flight repairs (cluster-level operand): `jcmd <pid> GC.class_histogram | grep -E ' org.apache.cassandra.service.paxos.PaxosRepair$'`
  instance count, sampled every 1 s on each node during the run (forces a full GC; that is accepted, it gives the live set).
- Live heap: total bytes line of the same histogram, and `jstat -gc <pid> 250` (OU, EU) for context.
- Peak live heap after GC: from `logs/gc.log`, the post-GC heap figure (`->NNNM(3072M)`) of every pause between the
  "paxos auto repairs enabled via jmx" log line and the "Completed N uncommitted paxos instances for pr.t" INFO line
  (`PaxosCleanupLocalCoordinator.java:223`) in each node's `system.log`. Baseline = the same figure over the 60 s before.
- Concurrent coordinators S on a node: count `Completing uncommitted paxos instances` (debug.log for auto repair,
  `:101`) that overlap in time; with auto repair S = 1 per table per node (`PaxosUncommittedTracker.java:295`).
- Not observable directly: which bytes on the heap belong to which repair; the per-key update copies inside
  in-flight messages.

**B3e. Procedure.**
1. B3a, then load data (B3c). Record `ccm status`, `du -sh $CCM_CONFIG_DIR`.
2. For each p in 1, 4, 64, 512 (in this order), and each repeat r in 1..2:
   a. Set p on all nodes (B3b); read it back.
   b. Create uncommitted keys: `promise`, wait 10 s, flush `system.paxos` on all nodes, `check` = 4096 on each node.
   c. Start samplers on each node: `while :; do date +%s.%N; jcmd $PID GC.class_histogram | grep -E 'paxos.PaxosRepair$|^Total'; sleep 1; done > $S4/hist-p$p-r$r-node$n.txt &`
      (`PID=$(cat $CCM_CONFIG_DIR/pr/node$n/cassandra.pid)`).
   d. Enable auto repair on all nodes: `ccm node$n nodetool sjk mx -b org.apache.cassandra.db:type=StorageService -ms -f PaxosAutoRepairsEnabled -v true`.
      It fires within 20 s (`-Dcassandra.auto_repair_frequency_seconds=20`).
   e. Wait for `Completed .* uncommitted paxos instances for pr.t` in each node's `system.log`/`debug.log`, then
      `check` = 0 on each node, then disable auto repair (`-v false`) and stop the samplers (`kill %1`).
   f. Copy `gc.log` lines for the window.
3. Control runs (B3h): p = 512 with U = 1 KiB data in a second table/keyspace; positive control `readload` with client
   concurrency 4 and 512 at p = 4, no paxos repair running.
4. Teardown (B4).

**B3f. Predictions.** Per node that does the work (the first to repair a key commits it on all replicas, so the others
mostly find nothing; the predictions are for the maximum over the three nodes):

| p | max live `PaxosRepair` (histogram) | peak post-GC heap above baseline during repair |
|---|---|---|
| 1 | ≤ 1-3 | ≤ 1 MiB + noise (noise ≲ 30 MiB) |
| 4 | ≤ 4 (+ a few with late callbacks) | ≤ 3 MiB + noise |
| 64 | ≤ 64 (+ few) | ≈ 16-48 MiB |
| 512 | ≤ 512 (+ few) | ≈ 128-384 MiB |

Relation: max live repairs ≤ S × p (+ a small number awaiting a third reply), and peak extra heap rises monotonically
with p, approximately ∝ min(p, uncommitted keys) × 256 KiB × (1..3). The p=512 peak must exceed the p=4 peak by at
least 100 MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Max live `PaxosRepair` ≤ S×p (+few) and peak extra heap grows with p (p=512 ≥ p=4 + 100 MiB) | Claim supported at cluster level |
| Max live `PaxosRepair` well above S×p for some p | Cap bypassed (another path creates repairs, or S underestimated: recheck debug.log for overlapping coordinators) |
| Live count follows p but peak heap is flat across p while the `readload` control moves heap with concurrency | Claim wrong for memory: in-flight repairs do not hold the update long enough to matter |
| Peak heap flat and `readload` control also flat | Not confirmed: instrument does not resolve the effect (raise U to 1 MiB, N to 1024) |
| `check` ≠ 4096 before a run | Workload did not create uncommitted keys (SERIAL read did not leave a promise); rerun `promise`; if still 0, see B4 alternative generator note |
| Repair never completes / `check` never reaches 0 | Not a reading on the claim; inspect logs (paxos v2 not active, auto repair still disabled) |

**B3h. Controls.**
- Null control: p = 512 with U = 1 KiB rows: live count still ≤ 512, but peak extra heap ≤ a few MiB — shows the
  heap effect is the held update, not object overhead.
- Positive control (known binding cap): `readload` at client concurrency 4 vs 512 reading the 256 KiB rows with no
  paxos repair running; peak post-GC heap should rise by roughly 512 × 256 KiB ≈ 128 MiB or more at 512 — the same
  instruments resolve a concurrency-bounded heap effect of this size.
- Baseline: 60 s idle before each run; auto repair disabled except during the run window, so no unplanned coordinators.
- Order and repeat: p ascending and each run twice; compare repeats to separate GC noise.

**B4. Risks and cleanup.**
- Disk: ≈ 15 GiB under `$CCM_CONFIG_DIR` on local disk; check `df -h $S4` ≥ 30 GiB free first. Nothing in shared
  storage; the source copy and build are under `$S4/src`.
- Memory: 3 × 3 GiB heap plus off-heap; run on a machine with ≥ 16 GiB RAM and no other heavy jobs.
- Leftover processes: kill sampler loops; `ccm stop --config-dir=$CCM_CONFIG_DIR`; `ccm remove pr --config-dir=$CCM_CONFIG_DIR`;
  then `pgrep -f CassandraDaemon -u $USER` and `pgrep -f "ant|junit" -u $USER` must print nothing from this run.
- Remove `$S4/ccm` and, when stage 4 is done, `$S4/src`.
- Unit tier: the test JVM ends with Ant; verify with `pgrep -f ParallelismCapProbeTest`.
- If SERIAL reads do not leave uncommitted keys (B3g row), an alternative generator is to issue LWT `UPDATE ... IF`
  statements while stopping one replica (`ccm node3 stop`) mid-run so some proposals are accepted but not committed;
  restart node3 before the run. This makes `check` counts less exact; record them.

## Config-first: places found

1. `src/java/org/apache/cassandra/config/Config.java:1144` — declaration, default -1. (Not a restricting place.)
2. `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:1007-1008` — startup derivation: `<= 0` → `max(1, concurrent_writes/8)` (default 4). Sets the cap's default; restricts nothing itself.
3. `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:4113-4122` — getter; setter rejects `v <= 0`. Plumbing.
4. `src/java/org/apache/cassandra/service/ActiveRepairService.java:1177-1185` (`ActiveRepairServiceMBean.java:75-76`) — JMX get/set on `org.apache.cassandra.db:type=RepairService`. Plumbing.
5. **`src/java/org/apache/cassandra/service/paxos/cleanup/PaxosCleanupLocalCoordinator.java:126-139`** — the only
   restricting place: `inflight.size() < parallelism` (`:128`) and the fill loop (`:138`) cap the number of concurrent
   per-key Paxos repairs per local cleanup coordinator, each holding the key's committed/accepted `PartitionUpdate`(s)
   on heap. This case file.

No other reader of the entry exists in `src/`, `tools/` or `test/` (grep for `paxos_repair_parallelism` and
`PaxosRepairParallelism`). One case file is written.

## C. Sources read

- src/java/org/apache/cassandra/config/Config.java (lines 180, 1100, 1135-1150, 1402)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 895-1010, 3337-3344, 4108-4122, 5324-5330)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (lines 64, 194, 395, 402)
- src/java/org/apache/cassandra/service/ActiveRepairService.java (lines 1160-1185)
- src/java/org/apache/cassandra/service/ActiveRepairServiceMBean.java (lines 27, 75-76)
- src/java/org/apache/cassandra/service/StorageService.java (lines 4930-4960, 7402-7411)
- src/java/org/apache/cassandra/service/StorageServiceMBean.java (lines 1241-1242)
- src/java/org/apache/cassandra/service/paxos/cleanup/PaxosCleanupLocalCoordinator.java (whole file)
- src/java/org/apache/cassandra/service/paxos/cleanup/PaxosTableRepairs.java (lines 40-211)
- src/java/org/apache/cassandra/service/paxos/cleanup/PaxosRepairState.java (lines 53-83)
- src/java/org/apache/cassandra/service/paxos/cleanup/PaxosCleanupRequest.java (lines 60-110)
- src/java/org/apache/cassandra/service/paxos/cleanup/PaxosCleanupSession.java (lines 28-140)
- src/java/org/apache/cassandra/service/paxos/cleanup/PaxosCleanup.java (lines 60-155)
- src/java/org/apache/cassandra/service/paxos/PaxosRepair.java (lines 80-340, 481-497, 557-684)
- src/java/org/apache/cassandra/service/paxos/AbstractPaxosRepair.java (lines 39-100, 130-245)
- src/java/org/apache/cassandra/service/paxos/PaxosState.java (lines 570-620)
- src/java/org/apache/cassandra/service/paxos/uncommitted/PaxosUncommittedTracker.java (lines 52-81, 192-217, 270-350)
- src/java/org/apache/cassandra/service/paxos/uncommitted/PaxosRows.java (lines 92-129, 200-240)
- src/java/org/apache/cassandra/service/paxos/uncommitted/PaxosKeyState.java
- src/java/org/apache/cassandra/service/paxos/uncommitted/UncommittedPaxosKey.java
- src/java/org/apache/cassandra/service/paxos/BallotGenerator.java (lines 28-40)
- src/java/org/apache/cassandra/db/SystemKeyspace.java (lines 225-240, 1330-1410)
- src/java/org/apache/cassandra/repair/SharedContext.java (lines 54-100, 200-240)
- src/java/org/apache/cassandra/repair/RepairJob.java (lines 120-140)
- src/java/org/apache/cassandra/net/Verb.java (lines 197, 201)
- src/java/org/apache/cassandra/concurrent/Stage.java (line 57)
- src/java/org/apache/cassandra/utils/CloseableIterator.java
- src/java/org/apache/cassandra/tools/nodetool/Repair.java (lines 105-106, 178, 188); tools/nodetool/Sjk.java (existence)
- test/unit/org/apache/cassandra/service/paxos/cleanup/PaxosTableRepairsTest.java
- test/data/config/version=5.0-alpha1.yml (line 62)
- conf/cassandra.yaml (lines 42, 652-660, 723, 883, 1597-1602)
- build.xml (lines 94, 1192, 1240-1260, 1382-1390)
- CHANGES.txt (lines 13, 308, 310)

## D. Stage-4 feedback

none yet
