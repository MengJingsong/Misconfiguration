# maxHintsInProgress — verification solution  <!-- file: cases/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/service/StorageProxy.java:1592` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code autonomous agent (subagent), 2026-10-21 |
| Estimate | `negative`. The check at :1592-1593 can only throw if the per-destination hint counter is > 0. That counter comes from a bare Guava `CacheLoader` whose `load()` returns a **new** `AtomicInteger(0)` on every call (:203-209, :2768), so it always reads 0. The overload check therefore never fires, and in-flight hints (and the heap their queued mutations hold) are not capped by `maxHintsInProgress`. |
| Ground | Dead condition: `getHintsInProgressFor(dest).get() > 0` (:1593) is always `false`, because `hintsInProgress` is a `CacheLoader`, not a `LoadingCache`. Each `load()` builds a fresh zero counter, so the increments at :2826 and decrements at :2731 land on throw-away objects. The first operand (`totalHintsInProgress > maxHintsInProgress`) can be true, but the `&&` at :1593 short-circuits the whole condition to false. Usage (queued `HintRunnable`s on MutationStage, each holding a `Mutation`) grows without regard to the limit. |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `maxHintsInProgress` (JMX attribute `MaxHintsInProgress` on MBean `org.apache.cassandra.db:type=StorageProxy`).
- **Kind:** a runtime-queried, JMX-settable static field. It is not a yaml key.
- **First declared:** `src/java/org/apache/cassandra/service/StorageProxy.java:202`: `private static volatile int maxHintsInProgress = 128 * FBUtilities.getAvailableProcessors();`.
- **Unit:** a count of hint tasks (one per hint target), not bytes.
- **Default:** 128 × available processors. `FBUtilities.getAvailableProcessors()` (`src/java/org/apache/cassandra/utils/FBUtilities.java:150-156`) returns the `-Dcassandra.available_processors` value (`CassandraRelevantProperties.java:82`, read at `FBUtilities.java:135`, falling back to `DatabaseDescriptor.getAvailableProcessors()`) when it is > 0, and otherwise `Runtime.availableProcessors()`. On a 40-core host the default is 5120.
- **How to set it:**
  - At startup, only indirectly, through `-Dcassandra.available_processors=N`. This also resizes other pools, and the value is read once in the static initializer, so it needs a restart.
  - At runtime, through JMX `setMaxHintsInProgress(int)` (`StorageProxy.java:2748-2751`, `StorageProxyMBean.java:38`). This takes effect immediately, needs no restart and is not persisted.
  - There is no nodetool command for it; `NodeProbe.java:2200` only reads the `TotalHintsInProgress` metric.

**A2. What it caps.**
- **Intended resource:** heap. The comment at :1587 reads "avoid OOMing due to excess hints". Each in-flight hint is a `HintRunnable` queued on `Stage.MUTATION`, and it holds a reference to its `Mutation` until it runs (:2783-2820, :2827).
- **Quantity compared:** `StorageMetrics.totalHintsInProgress.getCount()` (Counter, `src/java/org/apache/cassandra/metrics/StorageMetrics.java:45`). It is compared with `> maxHintsInProgress`, and is AND-ed with `getHintsInProgressFor(destination.endpoint()).get() > 0 && shouldHint(destination)` (:1592-1593).

**A3. Mechanism.**
1. **Where the check is called.** Write coordinators call `checkHintOverload(destination)` for every contacted replica, before sending:
   - `sendToHintedReplicas` at `StorageProxy.java:1505`, in the loop over `plan.contacts()`;
   - `commitPaxos` (Paxos v1) at :796.
   - Paxos v2 (`service/paxos/PaxosCommit.java:231`) and `AbstractWriteResponseHandler.java:310` submit hints without calling the check.
2. **Accounting.** `submitHint(HintRunnable)` (:2822-2828) does three things:
   - `totalHintsInProgress.inc(targets.size())`;
   - `getHintsInProgressFor(target).incrementAndGet()` for each target;
   - submits the runnable to `Stage.MUTATION`.

   `HintRunnable.run()`'s `finally` block (:2727-2732) decrements the same two counters after `HintsService.write` (:2814). The remaining hint producers are:
   - timed-out local writes (fake hint, :2645-2654);
   - `submitHint(Mutation, Replica, handler)` (:2776);
   - the batchlog / CL=ANY paths at :988 and :1564.
3. **The broken counter.** `hintsInProgress` is declared as `CacheLoader<InetAddressAndPort, AtomicInteger>` (:203), and `load()` returns `new AtomicInteger(0)` (:205-208). `getHintsInProgressFor` calls `hintsInProgress.load(destination)` directly (:2768). Guava's `CacheLoader.load` is just the user-supplied computation and does no caching. Caching is done by a `LoadingCache` built with `CacheBuilder.build(loader)` ([Guava CacheLoader javadoc](https://guava.dev/releases/32.0.1-jre/api/docs/com/google/common/cache/CacheLoader.html); the Guava version is 32.0.1-jre per `.build/parent-pom-template.xml:307-309`). Every call therefore returns a distinct zero-valued object. The `incrementAndGet()` at :2826 and `decrementAndGet()` at :2731 change objects that are immediately discarded, and the `.get()` at :1593 and :1597 always reads 0.
4. **Outcome when the limit is reached.**
   - As intended: throw `OverloadedException("Too many in flight hints…")` (:1595). `mutate` counts it as a write Unavailable (:941-946), and the client receives an Overloaded error. In `syncWriteBatchedMutations` it becomes `handler.onFailure` (:1334-1336).
   - As coded: since clause 2 is always false, the throw is unreachable. The write proceeds, and if the replica is down a further `HintRunnable` is queued (:1563-1564).
5. **Overshoot even if the counter worked.** Check-then-increment is not atomic: the check at :1505 runs before the increment at :2824. Concurrent coordinators could therefore overshoot by up to the number of concurrent request threads. Hints for live-but-timed-out replicas (`AbstractWriteResponseHandler.java:310`) and Paxos v2 (`PaxosCommit.java:231`) bypass the check entirely.

**A4. Other consumers.** Outside this constraint's control:
- MutationStage itself, whose queue is unbounded (`Stage.java:46`, `multiThreadedLowSignalStage` at :229). It also holds local and remote mutations.
- `HintsBufferPool` off-heap buffers (32 MiB minimum, `HintsService.java:79`) and the hints write buffer (`HintsWriteExecutor.java:50`).
- Hint files on disk, governed by `max_hints_size_per_host` (`Config.java:448`, checked in `shouldHint` at `StorageProxy.java:2488-2497`), `max_hint_window` and `max_hints_file_size` (`conf/cassandra.yaml:80,106,111`).
- Messaging callbacks, memtables and the native-transport in-flight request bytes.

**A5. Evidence beyond the source.**
- [Guava `CacheLoader` API](https://guava.dev/releases/32.0.1-jre/api/docs/com/google/common/cache/CacheLoader.html): `load` computes a value. Caching is provided by `CacheBuilder.build(CacheLoader)`, which returns a `LoadingCache`.
- `doc/modules/cassandra/pages/managing/operating/metrics.adoc:759` documents `TotalHintsInProgress` ("Number of hints attemping to be sent currently").
- `test/unit/org/apache/cassandra/hints/HintTest.java:246,289` only asserts that the total is 0. No test in the tree exercises `checkHintOverload` or `MaxHintsInProgress`.
- The clone is shallow (single commit `b5f2a54`), so `git log -S` could not date when the `LoadingCache` became a bare `CacheLoader`. No issue-tracker reference is relied on.

## B. Verification solution

**B1. Claim under test.** In Cassandra 5.0.9, `checkHintOverload` never throws `OverloadedException`, whatever `MaxHintsInProgress` is set to (including 1, when `TotalHintsInProgress` is far above it). As a result, the number of queued hint tasks and the heap they retain do not follow `MaxHintsInProgress`. Refutation: an `OverloadedException` "Too many in flight hints", or queued-hint count or heap bounded near the limit, at any knob value in the unmodified build.

### B2. Unit tier

**B2a. Environment and build.**
1. Copy the tree to local disk, at `WORK=/local/s3work` or any local filesystem with at least 10 GB free (check with `df -h $WORK`):
   ```
   mkdir -p $WORK && git clone /users/jason92/cassandra-s3 $WORK/src && cd $WORK/src && git checkout cassandra-5.0.9
   ```
   Never build in `/users/jason92/cassandra-s3`.
2. Use JDK 11 (`export JAVA_HOME=<jdk11>`) and build with `ant jar build-test`.
3. Test source: `$WORK/src/test/unit/org/apache/cassandra/service/HintOverloadCheckTest.java` (below).
4. Test JVM: the standard `testsome` harness gives `-Xmx4G` (`build.xml:1245-1255`). Add nothing else.
5. **Positive-control build:** a second copy, `$WORK/src-fixed`, cloned the same way. In it, apply the patch below to `StorageProxy.java`, then run `ant jar build-test` there.
   - Replace :203-209 with:
     ```java
     private static final LoadingCache<InetAddressAndPort, AtomicInteger> hintsInProgress =
         CacheBuilder.newBuilder().concurrencyLevel(1).build(new CacheLoader<InetAddressAndPort, AtomicInteger>() {
             public AtomicInteger load(InetAddressAndPort a) { return new AtomicInteger(0); } });
     ```
   - At :2768, use `return hintsInProgress.get(destination);` (the existing `catch (Exception e)` covers `ExecutionException`).
   - Add the imports `com.google.common.cache.CacheBuilder` and `com.google.common.cache.LoadingCache`.

> **Amendment 2026-10-21 (stage-4 audit, R1; environment, not design).** The paths above do not exist on the run node
> (`pc07`). Original build: `~/cassandra-mhp` (a local clone at `cassandra-5.0.9`, `b5f2a54210`, built with `build-test`).
> Positive-control build: `~/cassandra-mhp-patched`, a `cp -a` of it with exactly the patch above (the diff is kept in the
> stage-4 harness folder as `hintsInProgress-LoadingCache.diff`), built with `ant jar build-test`. `$WORK` = `~/stage4-mhp`.
> The `testsome` test JVM gets `maxmemory="1024m"` (`build.xml:1153`), not `-Xmx4G` (`build.xml:1245-1255` is the
> `testlist` macro, which `testsome` does not use); B2c's 125 MiB still fits.

**B2b. Knobs.** `StorageProxy.instance.setMaxHintsInProgress(L)` for L ∈ {1, 128, 1000, Integer.MAX_VALUE}:
- 1 is the tightest limit;
- 128 is the default for one CPU;
- 1000 is half the workload;
- MAX_VALUE is effectively unlimited, as the baseline.

Each value is set in-process; no restart is needed.

**B2c. Workload.**
1. Block MutationStage so that hints stay "in progress": submit `DatabaseDescriptor.getConcurrentWriters()` tasks to `Stage.MUTATION`, each awaiting one `CountDownLatch`.
2. For i in 0..N-1 with N = 2000, mirroring `sendToHintedReplicas`:
   - call `checkHintOverload(replica)` by reflection;
   - if it does not throw, call `StorageProxy.submitHint(m_i, replica, null)`;
   - otherwise count a rejection.

   Each `m_i` is a distinct `Mutation` on `CREATE TABLE %s (k int PRIMARY KEY, v blob)` with a 64 KiB `v`, built with `PartitionUpdate.simpleBuilder(meta, i).row().add("v", ByteBuffer.allocate(65536)).buildAsMutation()`.
3. The target is `Replica.fullReplica(127.0.0.2, range)`, registered with `StorageService.instance.getTokenMetadata().updateHostId(UUID.randomUUID(), ep2)` so that `shouldHint` is true. Set `DatabaseDescriptor.getRawConfig().hint_window_persistent_enabled = false` so `shouldHint` does not depend on HintsService state.
4. Arithmetic: the total reaches 2000, which is greater than L for L ∈ {1, 128, 1000}, so clause 1 is true from the (L+1)-th submit onward. Retained payload is 2000 × 64 KiB ≈ 125 MiB if nothing is rejected, against a 4 GB heap.

**B2d. Observables and instruments.** Read once per L, after the loop and while the latch is still held:
- `queued` = `StorageMetrics.totalHintsInProgress.getCount()`;
- `rejected` = the number of `OverloadedException`s (the cause of an `InvocationTargetException`);
- `perDest` = `((AtomicInteger) getHintsInProgressFor(ep2)).get()`, read by reflection;
- `same` = `getHintsInProgressFor(ep2) == getHintsInProgressFor(ep2)`;
- `shouldHint` = `StorageProxy.shouldHint(replica)`;
- `heapDelta` = `MemoryMXBean.getHeapMemoryUsage().getUsed()` after `System.gc()` ×3, minus the same value before the loop.

The heap figure is approximate. The retained set of the `HintRunnable`s cannot be observed directly. Optionally, run `jcmd <testpid> GC.class_histogram | grep -E 'HeapByteBuffer|StorageProxy\$'` to count the anonymous `StorageProxy$N` runnables.

**B2e. Procedure.**
1. Create the test class in both copies:
   ```java
   package org.apache.cassandra.service;
   // imports: java.lang.management.*, java.lang.reflect.*, java.nio.ByteBuffer, java.util.*, java.util.concurrent.*,
   // java.util.concurrent.atomic.AtomicInteger, org.junit.*, org.apache.cassandra.cql3.CQLTester, org.apache.cassandra.concurrent.Stage,
   // org.apache.cassandra.config.DatabaseDescriptor, org.apache.cassandra.db.*, org.apache.cassandra.db.partitions.PartitionUpdate,
   // org.apache.cassandra.dht.*, org.apache.cassandra.locator.*, org.apache.cassandra.metrics.StorageMetrics, org.apache.cassandra.exceptions.OverloadedException
   public class HintOverloadCheckTest extends CQLTester {
     @Test public void sweep() throws Throwable {
       createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob)");
       DatabaseDescriptor.getRawConfig().hint_window_persistent_enabled = false;
       InetAddressAndPort ep2 = InetAddressAndPort.getByName("127.0.0.2");
       StorageService.instance.getTokenMetadata().updateHostId(UUID.randomUUID(), ep2);
       IPartitioner p = DatabaseDescriptor.getPartitioner();
       Replica r = Replica.fullReplica(ep2, new Range<>(p.getMinimumToken(), p.getMinimumToken()));
       Method chk = StorageProxy.class.getDeclaredMethod("checkHintOverload", Replica.class); chk.setAccessible(true);
       Method pd = StorageProxy.class.getDeclaredMethod("getHintsInProgressFor", InetAddressAndPort.class); pd.setAccessible(true);
       MemoryMXBean mem = ManagementFactory.getMemoryMXBean();
       for (int L : new int[]{1, 128, 1000, Integer.MAX_VALUE}) {
         StorageProxy.instance.setMaxHintsInProgress(L);
         CountDownLatch gate = new CountDownLatch(1);
         for (int t = 0; t < DatabaseDescriptor.getConcurrentWriters(); t++)
           Stage.MUTATION.execute(() -> { try { gate.await(); } catch (InterruptedException e) {} });
         Thread.sleep(500);
         System.gc(); System.gc(); System.gc(); long h0 = mem.getHeapMemoryUsage().getUsed();
         int rejected = 0; List<Mutation> keep = new ArrayList<>();
         for (int i = 0; i < 2000; i++) {
           Mutation m = PartitionUpdate.simpleBuilder(currentTableMetadata(), i).row().add("v", ByteBuffer.allocate(65536)).buildAsMutation();
           try { chk.invoke(null, r); StorageProxy.submitHint(m, r, null); }
           catch (InvocationTargetException e) { if (e.getCause() instanceof OverloadedException) rejected++; else throw e.getCause(); }
         }
         keep = null;
         System.gc(); System.gc(); System.gc(); long h1 = mem.getHeapMemoryUsage().getUsed();
         long queued = StorageMetrics.totalHintsInProgress.getCount();
         int perDest = ((AtomicInteger) pd.invoke(null, ep2)).get();
         boolean same = pd.invoke(null, ep2) == pd.invoke(null, ep2);
         System.out.printf("RESULT L=%d queued=%d rejected=%d perDest=%d same=%b shouldHint=%b heapDeltaMiB=%d%n",
                           L, queued, rejected, perDest, same, StorageProxy.shouldHint(r), (h1 - h0) >> 20);
         gate.countDown();
         long deadline = System.currentTimeMillis() + 120_000;
         while (StorageMetrics.totalHintsInProgress.getCount() > 0 && System.currentTimeMillis() < deadline) Thread.sleep(100);
         System.out.printf("DRAINED L=%d remaining=%d%n", L, StorageMetrics.totalHintsInProgress.getCount());
         HintsService.instance.deleteAllHints();
       }
     }
   }
   ```
   `HintsService` is `org.apache.cassandra.hints.HintsService`. If `deleteAllHints` is not public at the tag, delete `build/test/cassandra/hints/*` after the run instead.
   > **Amendment 2026-10-21 (stage-4 audit, R2; the code above does not compile).** `PartitionUpdate.simpleBuilder(...).row()`
   > returns a `Row.SimpleBuilder`, which has no `buildAsMutation()` (`PartitionUpdate.java:609,644`, `Row.java:596-630`). The
   > mutation is built as `PartitionUpdate.SimpleBuilder b = PartitionUpdate.simpleBuilder(currentTableMetadata(), i);
   > b.row().add("v", ByteBuffer.allocate(65536)); Mutation m = b.buildAsMutation();`, which is the same mutation. The import
   > `org.apache.cassandra.hints.HintsService` is added (`deleteAllHints()` is public, `HintsService.java:319`). The test also
   > prints, once, the JVM's max heap, `getConcurrentWriters()` and `totalHintsInProgress` before the first L (all reported, not
   > predicted). B2f and B2g are unchanged.

2. Run it in each copy and keep the output:
   ```
   cd $WORK/src && ant testsome -Dtest.name=org.apache.cassandra.service.HintOverloadCheckTest -Dno-build-test=false 2>&1 | tee $WORK/unit-orig.log
   cd $WORK/src-fixed && ant testsome -Dtest.name=org.apache.cassandra.service.HintOverloadCheckTest 2>&1 | tee $WORK/unit-fixed.log
   ```
3. Extract the results with `grep -h RESULT $WORK/unit-*.log`. Read the stdout for each copy from `build/test/output/TEST-org.apache.cassandra.service.HintOverloadCheckTest.xml` if ant does not echo it.

**B2f. Predictions** (stated before any run).

| Build | L | queued | rejected | perDest | same | heapDeltaMiB |
|---|---|---|---|---|---|---|
| orig | 1, 128, 1000, MAX | 2000 | 0 | 0 | false | ≈125 (±30), independent of L |
| fixed | 1 | 2 | 1998 | 2 | true | ≈0 (< 10) |
| fixed | 128 | 129 | 1871 | 129 | true | ≈8 |
| fixed | 1000 | 1001 | 999 | 1001 | true | ≈63 |
| fixed | MAX | 2000 | 0 | 2000 | true | ≈125 |

In both builds, `shouldHint` is true and `DRAINED remaining=0`. For the fixed build the relation is queued = min(L+1, 2000), and heap ∝ queued.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| orig: rejected = 0 and queued = 2000 for all L, perDest = 0, same = false; fixed: queued = min(L+1, 2000) | Claim confirmed: usage is flat while the positive control moves with the knob. |
| orig: rejected > 0 or queued ≈ L+1 for some L < 2000 | Claim refuted: the cap binds. |
| orig: perDest > 0 or same = true | The trace (A3.3) is wrong. Claim refuted at the mechanism level. |
| queued < 2000 with rejected = 0 (stage not blocked, hints drained early), or shouldHint = false | The limit was never reached, or clause 3 masked the result. Not confirmed; fix the setup. |
| fixed: rejected = 0 at L = 1 | The positive control did not move. Not confirmed; check the patch or shouldHint. |
| heapDelta does not differ between fixed L = 1 and MAX | The heap instrument is too coarse. Rely on queued and the histogram counts. |

**B2h. Controls.**
- The same harness, workload and JVM run against two builds that differ only in the counter container, which isolates the `CacheLoader` defect.
- L = MAX_VALUE is the uncapped baseline.
- `shouldHint` is printed to rule out clause 3.
- `queued` is printed to show clause 1 was satisfied.
- The drain check rules out leaking counters between iterations.

### B3. Cluster tier

**B3a. Environment and build.**
1. Two nodes on one Linux host (127.0.0.1 = n1, the coordinator; 127.0.0.2 = n2, the replica that will be down), with JDK 11.
2. Build the original copy with `cd $WORK/src && ant jar`, and the fixed copy the same way in `$WORK/src-fixed` (the patch from B2a).
3. Per run, create the nodes with `cp -a $WORK/src $WORK/n1` and `cp -a $WORK/src $WORK/n2` (use `src-fixed` for control runs). Data, commit log and hints default to `$CASSANDRA_HOME/data/*`, which is on local disk.
4. Edit `n1/conf/cassandra.yaml`:
   - `listen_address: 127.0.0.1`, `rpc_address: 127.0.0.1`, `seeds: "127.0.0.1:7000"`;
   - `concurrent_writes: 2` (the minimum allowed, `DatabaseDescriptor.java:565`), so hint tasks queue;
   - leave `max_hints_size_per_host` at 0 and `hinted_handoff_enabled: true`.
5. Edit `n2/conf/cassandra.yaml` the same way with `listen_address/rpc_address: 127.0.0.2`, and set `JMX_PORT="7299"` in `n2/conf/cassandra-env.sh` (line 235).
6. Heap: `export MAX_HEAP_SIZE=2G` (G1, so leave `HEAP_NEWSIZE` unset, per `cassandra-env.sh:112-113`).

> **Amendment 2026-10-21 (stage-4 audit, R3; environment, not design).** The node host runs a second stage-4 session, so
> this run uses n1 = `127.0.0.21` (JMX 7221, the seed) and n2 = `127.0.0.22` (JMX 7222) in place of 127.0.0.1 / 127.0.0.2 and
> 7199 / 7299, and `$WORK` = `~/stage4-mhp`. Every 127.0.0.1 / 7199 below reads as n1's address / 7221 (nodetool and
> the JMX script connect to `127.0.0.1:<JMX port>`, where a local-JMX node listens). The node copies are made from the
> two builds of B2a (R1).

**B3b. Knobs.** n1's `MaxHintsInProgress` = L ∈ {1, 128, 2147483647}, set over JMX after start: 1 is the tightest, 128 is the 1-CPU default, and 2147483647 is the baseline. Runs:
- O-1, O-128, O-MAX on the original build;
- F-1 and F-MAX on the fixed build (positive control).

**B3c. Workload.** cassandra-stress from n1's tree:
```
tools/bin/cassandra-stress write n=1000000 cl=ONE -schema "replication(factor=2)" \
  -col "size=FIXED(1024)" "n=FIXED(1)" -rate threads=400 -errors ignore -node 127.0.0.1 -log file=$WORK/stress-<run>.log
```
- Every write is coordinated by n1. Its replicas are n1 (local) and n2 (down), so every write queues one `HintRunnable` on n1's two-thread MutationStage, alongside the local apply.
- With 400 client threads, more than 1 (and very likely more than 128) hint tasks are in flight at once.
- Volume: about 1 M × ~1.1 KB ≈ 1.1 GB of hints plus 1.1 GB of data on n1, so each run needs about 3 GB. Wipe between runs.
- Duration is a few minutes per run.

> **Amendment 2026-10-21 (stage-4 audit, R4).** Add `retries=0` to `-errors ignore` in every stress command of this tier
> (`-errors ignore retries=0`). cassandra-stress retries a failed operation 9 times by default (`SettingsErrors.java:41,49`),
> so a write refused by the check in F-1 would be re-sent and could still produce its hint, which would blur the F-1
> prediction "hints on disk well below O-1". With `retries=0` each write is attempted once in every run. B3f and B3g are
> unchanged by this.

**B3d. Observables and instruments.** Sample n1 every 200 ms with the jshell JMX script below, writing CSV:
- `TotalHintsInProgress`: `org.apache.cassandra.metrics:type=Storage,name=TotalHintsInProgress`, attribute `Count`;
- MutationStage pending: `org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks`, attribute `Value`;
- write Unavailables, which include `OverloadedException` (`StorageProxy.java:941-946`): `org.apache.cassandra.metrics:type=ClientRequest,scope=Write,name=Unavailables`, attribute `Count`;
- heap used: `java.lang:type=Memory`, attribute `HeapMemoryUsage.used`.

After each run, also collect:
- `grep -c "Too many in flight hints" $WORK/n1/logs/system.log $WORK/n1/logs/debug.log`;
- stress's error count from its log;
- `du -sb $WORK/n1/data/hints`;
- `jstat -gcutil <n1pid> 1000` during the run, for old-gen occupancy after GCs.

Heap held specifically by queued hints cannot be isolated. `TotalHintsInProgress` and the pending count are its proxies, and heap after GC is the actual resource.

`$WORK/jmx.jsh`, run as `PORT=7199 MODE=set L=<L> jshell $WORK/jmx.jsh` or `PORT=7199 MODE=sample OUT=<csv> jshell $WORK/jmx.jsh`:
```java
import javax.management.*; import javax.management.remote.*; import javax.management.openmbean.*;
var env = System.getenv();
var c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + env.get("PORT") + "/jmxrmi"));
var m = c.getMBeanServerConnection();
var sp = new ObjectName("org.apache.cassandra.db:type=StorageProxy");
if (env.get("MODE").equals("set")) { m.setAttribute(sp, new Attribute("MaxHintsInProgress", Integer.parseInt(env.get("L")))); System.out.println("MaxHintsInProgress=" + m.getAttribute(sp, "MaxHintsInProgress")); }
else {
  var thp = new ObjectName("org.apache.cassandra.metrics:type=Storage,name=TotalHintsInProgress");
  var pend = new ObjectName("org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks");
  var una = new ObjectName("org.apache.cassandra.metrics:type=ClientRequest,scope=Write,name=Unavailables");
  var mem = new ObjectName("java.lang:type=Memory");
  var w = new java.io.PrintWriter(new java.io.FileWriter(env.get("OUT")), true);
  w.println("ms,limit,hintsInProgress,mutationPending,unavailables,heapUsed");
  while (!new java.io.File(env.get("OUT") + ".stop").exists()) {
    w.println(System.currentTimeMillis() + "," + m.getAttribute(sp, "MaxHintsInProgress") + "," + m.getAttribute(thp, "Count") + "," + m.getAttribute(pend, "Value") + "," + m.getAttribute(una, "Count") + "," + ((CompositeData) m.getAttribute(mem, "HeapMemoryUsage")).get("used"));
    Thread.sleep(200);
  }
  w.close();
}
c.close();
/exit
```

**B3e. Procedure.** Repeat for each run R ∈ {O-1, O-128, O-MAX, F-1, F-MAX}:
1. Create the node copies and apply the edits from B3a (use `src-fixed` for F-*).
2. Start n1 (the seed) first, then n2:
   ```
   cd $WORK/n1 && bin/cassandra -p $WORK/n1.pid
   ```
   Wait for "Starting listening for CQL clients" in `n1/logs/system.log`, then:
   ```
   cd $WORK/n2 && bin/cassandra -p $WORK/n2.pid
   ```
   Wait until `$WORK/n1/bin/nodetool status` shows two `UN` nodes.
3. Create the schema while both nodes are up: run the stress command with `n=1000` and the same `-schema`.
4. Stop n2 with `kill $(cat $WORK/n2.pid)`, and wait until `nodetool -p 7199 status` on n1 shows 127.0.0.2 as `DN`.
5. Set the limit and start sampling:
   ```
   PORT=7199 MODE=set L=<L> jshell $WORK/jmx.jsh
   PORT=7199 MODE=sample OUT=$WORK/R.csv jshell $WORK/jmx.jsh &
   jstat -gcutil $(cat $WORK/n1.pid) 1000 > $WORK/R.jstat &
   ```
6. Run the B3c stress command with `n=1000000`.
7. Wait 30 s, then stop the samplers with `touch $WORK/R.csv.stop` and `kill %2`. Collect:
   - `grep -c "Too many in flight hints" $WORK/n1/logs/*.log`;
   - `du -sb $WORK/n1/data/hints`;
   - stress's final "Total errors" line.
8. Shut down: `kill $(cat $WORK/n1.pid)`, wait for exit, `pgrep -f CassandraDaemon` must be empty, then `rm -rf $WORK/n1 $WORK/n2`.

**B3f. Predictions** (stated before any run).

| Run | Overloaded log lines | Write Unavailables delta | max hintsInProgress | Hints on disk | Peak heap |
|---|---|---|---|---|---|
| O-1, O-128, O-MAX | 0 | 0 | ≥ 2 in all; > 128 expected in at least O-MAX | ≈ 1 M hints (~1.0-1.3 GB) | Peak hintsInProgress, peak MutationStage pending and peak post-GC heap (jstat O%) within ±25 % of each other |
| F-1 (positive control) | > 0 | > 0, a substantial share of the 1 M writes | Bounded at about 1 + native request threads (≤ ~130 with default `native_transport_max_threads: 128`) | Well below O-1 | Lower peak pending than O-1 |
| F-MAX | 0 | 0 | — | — | Matches O-MAX |

O-1 vs O-MAX: hint bytes equal within ±5 %, with stress errors ≈ 0.

> **Amendment 2026-10-21 (stage-4 audit, R5; from the source, before any reading).** The node writes no log line for this
> `OverloadedException`. It is a `RequestExecutionException`; `ExecuteMessage.execute` (`ExecuteMessage.java:205-210`, the
> path of stress's prepared writes) returns it to the client without logging, and `QueryMessage` logs only exceptions that are
> neither validation nor execution exceptions (`QueryMessage.java:125-131`). So the column "Overloaded log lines" is **0 in
> every run, F-1 included**, and it is reported but not used as evidence. The evidence that the disallow branch fired is the
> **write Unavailables delta** (marked for `OverloadedException` at `StorageProxy.java:941-946`) together with **stress's error
> count** and the message text stress prints, where it prints one. Read "Overloaded errors" in B3g as "Unavailables delta > 0
> and stress errors > 0", and "0 overloaded lines" as "Unavailables delta = 0 and stress errors = 0".

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| O-*: 0 overloaded lines, 0 Unavailables, max hintsInProgress > L (for L = 1, 128), hints bytes and heap peaks the same across L; F-1 shows Overloaded errors and lower hint volume and pending | Claim confirmed: usage does not follow the knob, while the positive control moves. |
| O-1 or O-128 shows "Too many in flight hints" or Unavailables > 0, or hintsInProgress is capped near L | Claim refuted: the cap binds. |
| O-1 hint volume or heap clearly below O-MAX (more than 25 %) with no Overloaded errors | Unexpected. Investigate other throttling (timeouts); does not confirm. |
| max hintsInProgress ≤ L throughout O-1 (never above 1) | The limit was never reached. Not confirmed; raise stress threads or lower `concurrent_writes`. |
| F-1 shows no Overloaded errors | The positive control did not move. Not confirmed; check the patch, n2 `DN`, and that `shouldHint` holds (hint window, `max_hints_size_per_host`). |

**B3h. Controls.**
- The same host, workload and config are used across runs. The only variables are L and the one-container patch.
- O-MAX and F-MAX are uncapped baselines and should match each other.
- n2 must be `DN` so that every write is hinted. Check `nodetool status`, and check that `TotalHints` grows (attribute `TotalHints` on the StorageProxy MBean).
- The fresh data directories per run rule out hint replay or a carry-over hint window.
- Unavailables come only from this path while n2 is down at CL=ONE with n1 up: a plain unavailable cannot occur, because n1 alone satisfies CL=ONE.

> **Amendment 2026-10-21 (stage-4 audit, R6; shared host).** Step 8's `pgrep -f CassandraDaemon` and B4's `pgrep -fa`
> check cannot be empty on a host another session uses. The check is that none of **this run's** PIDs (n1, n2, the samplers,
> jstat, stress) is alive, and that no `java` process whose command line names `CassandraDaemon` has a `-Dcassandra.config`
> or working directory under `~/stage4-mhp`. Nothing else is killed.

**B4. Risks and cleanup.**
- **Disk:** about 3 GB per cluster run plus about 0.3 GB for unit runs, all under `$WORK` on local disk. Never use `/proj` or other shared storage, and never touch `/users/jason92/cassandra-s3`. Check `df -h $WORK` before each run.
- **Processes:**
  - Cluster tier: two Cassandra JVMs, the jshell samplers, jstat and stress.
  - Unit tier: the ant JUnit JVM.
  - After each tier, `pgrep -fa 'CassandraDaemon|jshell|jstat|cassandra-stress|junit'` must show nothing from this run; kill anything that remains.
- **Ports:** 7000, 9042 and 7199/7299 on 127.0.0.1/127.0.0.2 only.
- **Cleanup:** `rm -rf $WORK` at the end. No change outside the nodes.

## C. Sources read

- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/service/StorageProxy.java (195-215, 770-830, 930-950, 980-998, 1325-1340, 1470-1640, 2420-2500, 2640-2660, 2690-2840)
- src/java/org/apache/cassandra/service/StorageProxyMBean.java (grep)
- src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java (grep :310)
- src/java/org/apache/cassandra/service/paxos/PaxosCommit.java (grep :231)
- src/java/org/apache/cassandra/metrics/StorageMetrics.java (grep :45)
- src/java/org/apache/cassandra/utils/FBUtilities.java (130-160)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (grep :82)
- src/java/org/apache/cassandra/config/Config.java (grep)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (grep)
- src/java/org/apache/cassandra/concurrent/Stage.java (40-60, 229-235)
- src/java/org/apache/cassandra/hints/HintsService.java (75-80, 160-200)
- src/java/org/apache/cassandra/hints/HintsWriteExecutor.java (grep)
- src/java/org/apache/cassandra/gms/Gossiper.java (541-548)
- src/java/org/apache/cassandra/locator/Replica.java, TokenMetadata.java (grep)
- src/java/org/apache/cassandra/db/partitions/PartitionUpdate.java (grep)
- src/java/org/apache/cassandra/tools/NodeProbe.java (grep)
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsErrors.java (grep)
- test/unit/org/apache/cassandra/hints/HintTest.java (240-300), test/unit/org/apache/cassandra/ServerTestUtils.java, test/unit/org/apache/cassandra/cql3/CQLTester.java (grep), test/conf/cassandra.yaml (grep)
- conf/cassandra.yaml, conf/cassandra-env.sh (108-135, 228-245), conf/jvm11-server.options (grep)
- build.xml (1245-1260, 1379-1401), .build/parent-pom-template.xml (grep guava), .build/cassandra-deps-template.xml (grep)
- doc/modules/cassandra/pages/managing/operating/metrics.adoc (:759)
- https://guava.dev/releases/32.0.1-jre/api/docs/com/google/common/cache/CacheLoader.html (cited from knowledge of the Guava API; not fetched in this session)

## D. Stage-4 feedback

**2026-10-21 — run 1, both tiers: Confirmed — does not cap** (estimate negative, matched). Results:
[`../../stage4-runtime-verification/results/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.md`](../../stage4-runtime-verification/results/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.md);
harness `../../stage4-runtime-verification/harness/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous/`.
Frozen version: sha256 `af8d24c24d212b7c05896cec190eeeaa3eb6205ad75a378c0f69f80999dc3312` (after the audit amendments R1–R6
above, dated 2026-10-21; only this section changed after the freeze). Not committed.

- **Unit (B2g row 1).** Original build: queued = 2000, rejected = 0, perDest = 0, same = false at L = 1 · 128 · 1000 · MAX,
  heap +124…127 MiB at every L. Patched build (`LoadingCache`): queued = 2 · 129 · 1001 · 2000 = min(L+1, 2000), rejected =
  2000 − queued, perDest = queued, same = true, heap −6 · 8 · 63 · 126 MiB. Exactly B2f, twice (a repeat agreed).
- **Cluster (B3g row 1).** Original build, L = 1 · 128 · MAX: 0 write Unavailables, 0 stress errors, peak `TotalHintsInProgress`
  129 in all three (above L = 1 and L = 128 in 89 and 22 of the 200 ms samples), 1,150,800,378 B of hints in all three
  (1,050,000 hints incl. stress's 50,000 warm-up writes). Positive control F-1 (patched, L = 1): 833,479 Unavailables of
  1,050,000 writes, 804,749 stress errors with "Too many in flight hints", 237,307,100 B of hints (0.206 × O-1), peak
  MutationStage pending 4 vs 255. F-MAX matched O-MAX in hints, pending and in-flight count.
- **Sub-prediction missed (cluster):** B3f's "F-MAX peak heap matches O-MAX" fails on the old-gen reading (1,882 vs 857 MiB);
  a Full GC after the stress window took F-MAX's heap from 1,993 to 80 MiB, so it is GC timing, not retention. Peak heap used
  (1,978 vs 2,002 MiB) matches.
- **Runbook defects found (fixed in the harness, B2f–B3g unchanged):** D1, `jstat` cannot attach to a node started with
  `-XX:+PerfDisableSharedMem` (`conf/jvm-server.options:137`), so B3d's old-gen reading was taken over JMX (G1 Old Gen
  `Usage`/`CollectionUsage`, 1 s). H1, the unit test JVM routes `System.out` through a logger that splits each `printf` into
  pieces (the runner re-joins them). H2, `jmx.jsh`'s `else {` on its own line is a separate snippet in jshell: both modes still
  did their job (set and read back L; 200 ms samples) and printed parse errors.
- **Findings beyond the claim.** (1) In this workload in-flight hints stop at 129 whatever L is, very likely because the 128
  native request threads each wait for their own local write and so leave at most one hint each in the queue (inferred; not
  tested). So the default limit (128 × cores, 5,120 on the host) could not be reached by client writes alone at default
  `native_transport_max_threads`. (2) With the counter fixed, the check still overshoots: the refusal messages re-read the
  total as 0–35 at L = 1 (check-then-increment, A3.5).
