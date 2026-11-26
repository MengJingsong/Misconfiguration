# ALLOW_UNLIMITED_CONCURRENT_VALIDATIONS (Repair-Task pool size derived from concurrent_validations) — verification solution  <!-- file: cases/ALLOW_UNLIMITED_CONCURRENT_VALIDATIONS-applyRepairCommandPoolSize-repair_command_pool_size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the default derivation `if (config.repair_command_pool_size < 1) config.repair_command_pool_size = config.concurrent_validations;`: [`DatabaseDescriptor.java:1087-1088`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1087-L1088) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-26 |
| Estimate | `negative`. The property only lets `concurrent_validations` (and therefore the default `repair_command_pool_size`) exceed `concurrent_compactors`; the resulting Repair-Task pool does not bound concurrent repair commands, because each pool task (`RepairCoordinator.run`) only starts an asynchronous future chain and returns, so the number of in-flight repairs and the coordinator memory they hold do not follow this pool size. |
| Ground | `RepairCoordinator.runMayThrow` (`RepairCoordinator.java:290-331`) calls `prepare(...).flatMap(repair(...)).addCallback(...)` and returns; the repair work runs on a per-command executor (`RepairCoordinator.java:466-480`) and message callbacks, not on the Repair-Task thread, so the pool slot (`ActiveRepairService.java:205`, `208-219`) is released right after setup. |

## A. Constraint trace

**A1. The constraint.** `ALLOW_UNLIMITED_CONCURRENT_VALIDATIONS`, JVM system property
`-Dcassandra.allow_unlimited_concurrent_validations`, declared at
[`CassandraRelevantProperties.java:47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L47).
Boolean, default `false`, read into `DatabaseDescriptor.allowUnlimitedConcurrentValidations` (`DatabaseDescriptor.java:229`);
set by `-D` (restart). At startup it decides whether `concurrent_validations > concurrent_compactors` is admitted
(`DatabaseDescriptor.java:1077`, place 1). The admitted `concurrent_validations` then becomes the default of
`repair_command_pool_size` (`Config.java:673`, initial 0; `DatabaseDescriptor.java:784`, `1085-1089`), which is the size of
the coordinator's `Repair-Task` executor (`ActiveRepairService.java:205`, `208-219`; read once at class init of the holder,
so restart needed). `repair_command_pool_size` has no entry in `conf/cassandra.yaml` (only the Config field) and an explicit
yaml value overrides the derivation. Strategy `repair_command_pool_full_strategy` (`Config.java:672`, default `queue`): queue
limit `Integer.MAX_VALUE`, or 0 for `reject` (`ActiveRepairService.java:215`).

**A2. What it caps.** Nominally the number of repair commands a coordinator runs at once (each command holds sessions,
jobs and received Merkle trees, RF trees per job, off-heap by default, `Config.java:212`, `Validator.java:295-300`). The
quantity is the Repair-Task pool size (threads) against the number of submitted repair commands
(`StorageService.java:4802`). The estimate is that this bounds only the synchronous setup of each command, not memory.

**A3. Mechanism.**
1. `applyConcurrentValidations` admits/derives `concurrent_validations` (`DatabaseDescriptor.java:1071-1082`); with the
   property `true`, any value is kept.
2. **The derivation** [`DatabaseDescriptor.java:1087-1088`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1087-L1088):
   `if (config.repair_command_pool_size < 1) config.repair_command_pool_size = config.concurrent_validations;` (called at
   `DatabaseDescriptor.java:784`, after `:783`).
3. `ActiveRepairService.RepairCommandExecutorHandle.repairCommandExecutor = initializeExecutor(getRepairCommandPoolSize(), …)`
   (`ActiveRepairService.java:205`) → pooled executor "Repair-Task", core = max = size, keep-alive 1 h, queue unbounded
   (or 0 with `reject`, then `AbortPolicy`) (`ActiveRepairService.java:208-219`).
4. `StorageService.repair` submits `createRepairTask(...)` (a `FutureTask` around a `RepairCoordinator`,
   `StorageService.java:4802`, `4848-4863`) to that executor.
5. `RepairCoordinator.run` → `runMayThrow` (`RepairCoordinator.java:273-331`): synchronous part = column families,
   trace state, neighbours/ranges, `maybeStoreParentRepairStart`; then `prepare(...)` returns a `Future`
   (`RepairCoordinator.java:445-455`), chained with `flatMap(repair(...))` and `addCallback`; `repair(...)` creates a
   per-command executor and calls `task.perform(executor, validationScheduler)` (`RepairCoordinator.java:458-480`). The
   method returns while the repair is still running → the Repair-Task thread is free again.
Outcome when the pool is "full": with `queue`, later commands wait only for earlier commands' setup; with `reject`, a
command submitted while all threads are in setup is rejected. Neither bounds commands in flight.

**A4. Other consumers.** Validation-side trees on replicas (bounded by `concurrent_validations`, places 1–2);
`concurrent_merkle_tree_requests` (per command, `RepairCoordinator.java:127`); per-command job executor (`-j`);
streaming; ANTI_ENTROPY stage.

**A5. Evidence beyond the source.** `test/unit/org/apache/cassandra/config/DatabaseDescriptorTest.java:539-552`
(`testRepairCommandPoolSize`: default derives from `concurrent_validations`); `conf/cassandra.yaml:842-861`
(`concurrent_merkle_tree_requests`, CASSANDRA-19336, says repair commands can OOM across tables/vnodes); CHANGES.txt:1974
(CASSANDRA-13521). No document states that the Repair-Task pool bounds in-flight repairs.

## B. Verification solution

**B1. Claim under test (negative).** Raising or lowering the coordinator's Repair-Task pool through
`concurrent_validations` (admitted by `-Dcassandra.allow_unlimited_concurrent_validations=true`) does not change how many
repair commands are in flight at once, nor the repair memory they generate: with 8 concurrent single-table repairs,
in-flight commands and replica-side validation requests reach 8 whether the derived pool size is 1 or 8.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant:
```
RUN=/mydata/s4-aucv; mkdir -p $RUN && rsync -a /users/jason92/cassandra-5.0.9/ $RUN/src/
cd $RUN/src && ant jar build-test
```
Test `$RUN/src/test/unit/org/apache/cassandra/service/AucvRepairPoolProbeTest.java` (package `org.apache.cassandra.service`
to reach the package-private `ActiveRepairService.initializeExecutor`; `DatabaseDescriptor.applyConcurrentValidations` /
`applyRepairCommandPoolSize` are reached through a tiny helper class in `org.apache.cassandra.config`, below). Run with
`-Dtest.jvm.args="-Dcassandra.allow_unlimited_concurrent_validations=true"` so V = 8 > compactors = 2 is admitted.

**B2b. Knobs.** `concurrent_compactors = 2`; `concurrent_validations V ∈ {1, 8}` → derived `repair_command_pool_size`;
task shape: `async` (models `RepairCoordinator.run`: start work that completes later, return) vs `blocking` (positive
control: the task holds its thread until the work is done).

**B2c. Workload.** 8 tasks submitted to `initializeExecutor(poolSize, queue)`. Each task allocates an 8 MiB `byte[]`
"repair state" and either (async) hands it to a separate `ScheduledExecutorService` that releases it after 5 s and
returns at once, or (blocking) sleeps 5 s holding it. Live states are counted with an AtomicInteger high-water mark.

**B2d. Observables and instruments.** `AUCVR` lines: derived pool size, executor core size, high-water of live
states, heap delta after GC at t = 2 s. Limitation: this models the async shape of `RepairCoordinator.runMayThrow`; the
real class is exercised only in the cluster tier.

**B2e. Procedure.**
1. Helper `$RUN/src/test/unit/org/apache/cassandra/config/AucvCfg.java`:
```java
package org.apache.cassandra.config;
public class AucvCfg
{
    public static int derivedPool(int compactors, int validations)
    {
        Config c = new Config();
        c.concurrent_compactors = compactors;
        c.concurrent_validations = validations;
        DatabaseDescriptor.applyConcurrentValidations(c);
        DatabaseDescriptor.applyRepairCommandPoolSize(c);
        return c.repair_command_pool_size;
    }
}
```
2. Test:
```java
package org.apache.cassandra.service;

import java.lang.management.ManagementFactory;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.Test;
import org.apache.cassandra.concurrent.ExecutorPlus;
import org.apache.cassandra.config.AucvCfg;
import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DatabaseDescriptor;

public class AucvRepairPoolProbeTest
{
    static long usedAfterGc() { for (int i = 0; i < 3; i++) System.gc(); return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed(); }

    @Test
    public void probe() throws Exception
    {
        DatabaseDescriptor.clientInitialization();
        System.out.printf("AUCVR flag=%s%n", DatabaseDescriptor.allowUnlimitedConcurrentValidations);
        ScheduledExecutorService later = Executors.newScheduledThreadPool(16);
        for (int v : new int[]{ 1, 8 })
            for (boolean async : new boolean[]{ true, false })
            {
                int pool = AucvCfg.derivedPool(2, v);
                ExecutorPlus ex = ActiveRepairService.initializeExecutor(pool, Config.RepairCommandPoolFullStrategy.queue);
                AtomicInteger live = new AtomicInteger(), hw = new AtomicInteger();
                CountDownLatch done = new CountDownLatch(8);
                long base = usedAfterGc();
                for (int i = 0; i < 8; i++)
                    ex.execute(() -> {
                        byte[] state = new byte[8 << 20];
                        hw.accumulateAndGet(live.incrementAndGet(), Math::max);
                        Runnable finish = () -> { live.decrementAndGet(); state[0] = 1; done.countDown(); };
                        if (async) later.schedule(finish, 5, TimeUnit.SECONDS);
                        else { try { Thread.sleep(5000); } catch (InterruptedException e) {} finish.run(); }
                    });
                Thread.sleep(2000);
                long held = usedAfterGc() - base;
                System.out.printf("AUCVR v=%d pool=%d core=%d async=%s hwAt2s=%d heapDelta=%d%n",
                                  v, pool, ex.getCorePoolSize(), async, hw.get(), held);
                done.await(120, TimeUnit.SECONDS);
                ex.shutdown();
            }
        later.shutdown();
    }
}
```
3. Run:
```
cd $RUN/src && ant testsome -Dtest.name=org.apache.cassandra.service.AucvRepairPoolProbeTest \
     -Dtest.jvm.args="-Dcassandra.allow_unlimited_concurrent_validations=true"
grep -h AUCVR $(find build/test/output -name '*AucvRepairPoolProbe*') > $RUN/unit-rcp.txt
```
Optional second run without `-Dtest.jvm.args`: V = 8 then throws `ConfigurationException` from
`DatabaseDescriptor.java:1079` (the place-1 gate), confirming the derivation only sees V > compactors when the property is set.

**B2f. Predictions.**

| V | derived pool | async: hw at 2 s / heapDelta | blocking (control): hw at 2 s / heapDelta |
|---|---|---|---|
| 1 | 1 | 8 / ≈ 64 MiB | 1 / ≈ 8 MiB |
| 8 | 8 | 8 / ≈ 64 MiB | 8 / ≈ 64 MiB |

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| async hw = 8 for both pool sizes, blocking hw = pool | claim (negative) supported at model level: a pool of async-returning tasks does not bound in-flight state; the pool does bind when tasks hold the thread (control moved) |
| async hw = pool size (1 for V=1) | the executor bounds even async tasks → claim refuted (model) |
| blocking hw = 8 for pool 1 | control did not move: executor not built with the derived size → probe error, not confirmed |
| derived pool ≠ V | derivation differs from A3 step 2 → amend A3 |

**B2h. Controls.** Blocking variant (positive control: same workload, a cap known to bind); same 8 MiB state per task;
same pool construction call as production (`ActiveRepairService.initializeExecutor`).

### B3. Cluster tier

**B3a. Environment and build.** Two nodes on loopback (n1 = 127.0.0.1 coordinator, JMX 7199, token
`-9223372036854775808`; n2 = 127.0.0.2, JMX 7299, token `0`), RF 2, heap 2 GiB, as in the place-1 case B3a:
```
for n in n1 n2; do rsync -a --exclude test $RUN/src/ $RUN/$n/; mkdir -p $RUN/$n/{data,commitlog,hints,saved_caches,cdc,logs}; done
BM=$(find $RUN/src/build -name 'byteman-4.0.20.jar' | head -1)
sed -i 's/^JMX_PORT="7199"/JMX_PORT="7299"/' $RUN/n2/conf/cassandra-env.sh
```
Appended yaml per node (last key wins): `cluster_name: aucv`, `num_tokens: 1`, `initial_token`, `listen_address` /
`rpc_address`, `seed_provider` seeds `"127.0.0.1:7000"`, data / commitlog / hints / saved_caches / cdc directories under
`$RUN/nX`, `concurrent_compactors: 2`, `concurrent_merkle_tree_requests: 0`, `repair_session_space: 128MiB`, plus
`concurrent_validations` (B3b). **Do not set `repair_command_pool_size` on n1** except in run P3-c.
n2: `concurrent_validations: 8`, property `-Dcassandra.allow_unlimited_concurrent_validations=true`, Byteman hold rule
`$RUN/hold.btm` (Validator.complete AT ENTRY `Thread.sleep(30000)`, text in the place-1 case) via
`JVM_EXTRA_OPTS="-Dcassandra.allow_unlimited_concurrent_validations=true -javaagent:$BM=script:$RUN/hold.btm"`.
n1: `JVM_EXTRA_OPTS="-Dcassandra.allow_unlimited_concurrent_validations=true"` in all runs.
Start: `(cd $RUN/nX && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_LOG_DIR=$RUN/nX/logs JVM_EXTRA_OPTS="..." bin/cassandra -p $RUN/nX/pid)`.

**B3b. Knobs.** n1 only, restart n1 between runs (the Repair-Task executor is built once, `ActiveRepairService.java:205`).

| Run | n1 `concurrent_validations` | n1 `repair_command_pool_size` | Derived Repair-Task size | Why |
|---|---|---|---|---|
| P3-a | 8 (admitted by the property) | unset | 8 | property-enabled large pool |
| P3-b | 1 | unset | 1 | small pool via the same derivation |
| P3-c | 8 | 1 (explicit) | 1 | small pool without shrinking n1's own ValidationExecutor (isolates the pool from n1's validations) |

Check the pool size after start: `java $RUN/tools/JmxOp.java 127.0.0.1 7199 "org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=Repair-Task,name=MaxPoolSize" get Value`
(`JmxOp.java` text in the place-2 case B3a; the gauge exists only after the first repair creates the executor, so read it
after the run if it is missing before).

**B3c. Workload.** Keyspace `ks` RF 2, tables `t1..t8 (k int PRIMARY KEY, v text)`, 300,000 partitions each, loaded once
with `cqlsh COPY` and flushed on both nodes (place-1 case B3c, ≈ 350 MB per node). Per run, 8 concurrent single-table
full repairs from n1:
```
for i in $(seq 1 8); do $RUN/n1/bin/nodetool -h 127.0.0.1 -p 7199 repair -full ks t$i > $RUN/rep-$RID-t$i.log 2>&1 & done; wait
```
n2 holds every validation 30 s and can run 8 at once, so the number of validation requests n2 sees concurrently equals
the number of repair commands n1 has in flight (one table per command). Duration ≈ 40 s per run if commands overlap;
≈ 8 × 35 s ≈ 5 min if the pool serialises them.

**B3d. Observables and instruments.**
- n2: `nodetool -h 127.0.0.1 -p 7299 tpstats | grep ValidationExecutor` every 1 s → max(Active + Pending) = concurrent
  validation requests = in-flight commands.
- n1: `cqlsh 127.0.0.1 -e "SELECT command_id, status, completed FROM system_views.repairs"` every 2 s
  (`LocalRepairTables.java:75-95`, `422-434`) → max number of rows with `completed = False`.
- n1: `nodetool -h 127.0.0.1 -p 7199 tpstats | grep Repair-Task` every 1 s → Active, Pending, Completed.
- Memory proxy on n2: `jcmd <n2 pid> GC.class_histogram | grep -E 'MerkleTree\$OnHeap(Leaf|Inner)'` every 10 s → live
  leaves (≈ in-flight commands × N, N ≈ 2^18 from `grep "Created .* merkle trees" $RUN/n2/logs/debug.log`).
- Wall time of the 8 repairs (`date +%s` before/after `wait`).
Not observed directly: coordinator off-heap tree bytes per command (short-lived after the burst); in-flight count is the
operand that drives them.

**B3e. Procedure.**
1. Build, configure, start n1 (run P3-a config) and n2; `nodetool status` both UN; load data.
2. For RID in P3-a, P3-b, P3-c: (re)start n1 with that config (stop per B4, wait for UN); start the three samplers
   in the background writing `$RUN/$RID-n2tp.txt`, `$RUN/$RID-n1vt.txt`, `$RUN/$RID-n1tp.txt` and the histogram loop
   `$RUN/$RID-histo.txt`; record start time; run the 8 repairs; `wait`; record end time; stop the samplers; read
   Repair-Task MaxPoolSize; check all repair logs report success.
3. Tabulate per run: derived pool size, max n2 Active+Pending, max n2 Active, max n1 in-flight repairs (vtable), max n1
   Repair-Task Active / Pending, max n2 live leaves, wall time.

**B3f. Predictions.**

| Run | Repair-Task size | max in-flight repairs (n1 vtable) | max n2 Active+Pending | max n2 live OnHeapLeaf | wall time |
|---|---|---|---|---|---|
| P3-a | 8 | 8 | 8 | ≈ 8N | ≈ 30–60 s |
| P3-b | 1 | 8 | 8 | ≈ 8N | ≈ 30–60 s |
| P3-c | 1 | 8 | 8 | ≈ 8N | ≈ 30–60 s |

n1 Repair-Task Active ≤ pool size and Pending back to 0 within a few seconds of submission in every run. Tolerance:
in-flight counts exact (8); leaves ±15 %.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| in-flight 8 and n2 ≈ 8N in P3-b/P3-c as in P3-a, while the control (B3h) moves | claim (negative) confirmed: usage does not follow the pool size derived via the property |
| P3-b/P3-c in-flight ≤ 1 (≈ 1N), wall time ≈ 5 min | the pool serialises commands → claim refuted: usage follows the derived pool size (estimate wrong) |
| P3-b differs from P3-c | n1's own ValidationExecutor size, not the pool, is acting → attribute to place 1, not this place |
| P3-a in-flight < 8 | workload did not overlap (repairs launched too slowly, or n2 Active capped) → not confirmed |
| control run also stays at 8 | control did not move → not confirmed |

**B3h. Controls.** Positive control (a cap known to bind, same workload): run P3-ctl = P3-a but with n2
`concurrent_validations: 2` (property on, restart n2) → n2 max Active 2, live leaves ≈ 2N, while in-flight repairs on n1
still 8 (Pending carries the rest). This shows the instruments see a binding cap. P3-c vs P3-b separates the pool from
n1's own validation executor. n2 config unchanged across P3-a/b/c; same data and N.

**B4. Risks and cleanup.** ≈ 350 MB per node under `$RUN` on local disk (`df -h` first); nothing on shared storage;
shared tree only read. Two 2 GiB heaps. After the tiers:
```
for n in n1 n2; do [ -f $RUN/$n/pid ] && kill $(cat $RUN/$n/pid); done; sleep 20
pkill -f "$RUN/n[12]"; pkill -f "while sleep"
pgrep -af "CassandraDaemon|nodetool|cqlsh|JmxOp" | grep "$RUN" || echo clean
```
Unit tier: one forked JVM; check `pgrep -af AucvRepairPoolProbe` is empty. `rm -rf $RUN` when stage 4 is done.

## C. Sources read

src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/service/ActiveRepairService.java
src/java/org/apache/cassandra/service/StorageService.java
src/java/org/apache/cassandra/repair/RepairCoordinator.java
src/java/org/apache/cassandra/repair/ValidationManager.java
src/java/org/apache/cassandra/repair/Validator.java
src/java/org/apache/cassandra/db/compaction/CompactionManager.java
src/java/org/apache/cassandra/db/virtual/LocalRepairTables.java
src/java/org/apache/cassandra/metrics/ThreadPoolMetrics.java
src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java
src/java/org/apache/cassandra/concurrent/ExecutorFactory.java
src/java/org/apache/cassandra/utils/MerkleTree.java
test/unit/org/apache/cassandra/config/DatabaseDescriptorTest.java
conf/cassandra.yaml
build.xml
CHANGES.txt

## D. Stage-4 feedback

none yet
