# ALLOW_UNLIMITED_CONCURRENT_VALIDATIONS (runtime JMX gate on setConcurrentValidators) — verification solution  <!-- file: cases/ALLOW_UNLIMITED_CONCURRENT_VALIDATIONS-setConcurrentValidators-value--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the runtime check `value > concurrentCompactors && !DatabaseDescriptor.allowUnlimitedConcurrentValidations`: [`StorageService.java:2012`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L2012) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-26 |
| Estimate | `positive`. While the switch is off (property unset and no JMX bypass), `setConcurrentValidators(value)` with `value > concurrent_compactors` is refused and the ValidationExecutor keeps its size, so concurrent on-heap Merkle-tree builds stay at ≤ `concurrent_compactors`; with the switch on, the resize goes through and tree heap follows `value`. Caveats to be measured: the switch is flipped by a JMX op, re-enforcing it does not shrink an already grown pool, and the CompactionManager MBean resizes the same pool without any check. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `ALLOW_UNLIMITED_CONCURRENT_VALIDATIONS`, JVM system property
`-Dcassandra.allow_unlimited_concurrent_validations`, declared at
[`CassandraRelevantProperties.java:47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L47).
Boolean switch, default `false` (no default string). Copied at class load into the mutable static
`DatabaseDescriptor.allowUnlimitedConcurrentValidations` (`DatabaseDescriptor.java:229`). Settable by `-D` at startup
(restart needed) and, without restart, over JMX on `org.apache.cassandra.db:type=StorageService`:
`bypassConcurrentValidatorsLimit()` sets it `true`, `enforceConcurrentValidatorsLimit()` sets it `false`
(`StorageService.java:1972-1982`, `StorageServiceMBean.java:823-825`). The getter `isConcurrentValidatorsLimitEnforced()`
returns the field itself (`StorageService.java:1984-1987`), i.e. `true` means the limit is *not* enforced (inverted name).
The limit it switches: `concurrent_validations ≤ concurrent_compactors` (threads). Documented in `conf/cassandra.yaml:1232-1239`.

**A2. What it caps.** Heap held by concurrently running repair validations on a replica. The quantity compared is the
requested new ValidationExecutor size `value` against `DatabaseDescriptor.getConcurrentCompactors()`. The pool size is
the number of validations that run at once; each holds Merkle trees of up to `repair_session_space / RF` bytes on heap
(`ValidationManager.java:54-88`, `127`) until `Validator.complete()` (`Validator.java:222-237`).

**A3. Mechanism.**
1. JMX `StorageService.setConcurrentValidators(int value)` (`StorageService.java:2009-2029`, `StorageServiceMBean.java:831`;
   no nodetool command exists for it).
2. **The check** [`StorageService.java:2012`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L2012):
   `if (value > concurrentCompactors && !DatabaseDescriptor.allowUnlimitedConcurrentValidations)` → throws
   `IllegalArgumentException("Cannot set concurrent_validations greater than concurrent_compactors (<n>)")`
   (`:2013-2015`); nothing is changed. Otherwise `value ≤ 0` is replaced by `concurrent_compactors` (`:2017-2021`),
   `DatabaseDescriptor.setConcurrentValidations(value)` stores it (`:2027`, `DatabaseDescriptor.java:2528-2532`) and
   `CompactionManager.instance.setConcurrentValidations()` → `ValidationExecutor.adjustPoolSize()` sets maximum then core
   pool size to the new value (`:2028`, `CompactionManager.java:2243-2246`, `2116-2120`).
3. Running validations = core pool size (unbounded queue, `CompactionManager.java:2109-2114`,
   `ThreadPoolExecutorBuilder.java:34-39`); queued requests hold no trees (trees are built when the task runs,
   `ValidationManager.java:127`).

Bypasses / overshoots: (a) `bypassConcurrentValidatorsLimit` turns the check off at runtime (`StorageService.java:1972-1976`);
(b) `enforceConcurrentValidatorsLimit` only flips the flag — it does not shrink a pool that was already grown
(`StorageService.java:1978-1982`); (c) `CompactionManagerMBean.setCoreValidationThreads` / `setMaximumValidatorThreads`
(`CompactionManager.java:2304-2320`, `CompactionManagerMBean.java:101-118`) and the executor's own JMX bean
(`withJmxInternal`, `CompactionManager.java:2035`; `ThreadPoolExecutorJMXAdapter.java:195-210`) resize the same pool with no
check; (d) raising `concurrent_compactors` at runtime (`StorageService.java:1964-1970`) raises the ceiling;
(e) shrinking: `adjustPoolSize` calls `setMaximumPoolSize(new)` before `setCorePoolSize(new)`
(`CompactionManager.java:2118-2119`); JDK 11 `ThreadPoolExecutor.setMaximumPoolSize` throws `IllegalArgumentException`
when the new maximum is below the current core size (JDK 11 API docs), so a shrink through this path is expected to fail
after `DatabaseDescriptor` was already updated — the reported value and the real pool would then disagree;
(f) completed trees handed to ANTI_ENTROPY / network (`Validator.java:236`, `281-300`) are outside the thread bound.

**A4. Other consumers.** Coordinator-side received trees (off-heap by default, `Config.java:212`; per-command limit
`concurrent_merkle_tree_requests`, `RepairCoordinator.java:127`); compaction executor; streaming; memtables, caches.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:1232-1239` (documents "first call the bypassConcurrentValidatorsLimit method on the
  org.apache.cassandra.db:type=StorageService mbean").
- `CHANGES.txt:1974` (CASSANDRA-13521, https://issues.apache.org/jira/browse/CASSANDRA-13521).
- `test/unit/org/apache/cassandra/db/compaction/ValidationExecutorTest.java` (`testAdjustPoolSize` covers growth only).
- JDK 11 `java.util.concurrent.ThreadPoolExecutor#setMaximumPoolSize` / `#setCorePoolSize` API documentation
  (https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html), for (e).

## B. Verification solution

**B1. Claim under test.** On a running node with the switch off, `setConcurrentValidators(V)` with
`V > concurrent_compactors` is refused and concurrent validations (and their on-heap trees) stay at
`concurrent_compactors × T`; after `bypassConcurrentValidatorsLimit` the same call takes effect and tree heap rises to
`V × T` under the same repair workload.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant; local copy and build:
```
RUN=/mydata/s4-aucv; mkdir -p $RUN && rsync -a /users/jason92/cassandra-5.0.9/ $RUN/src/
cd $RUN/src && ant jar build-test
```
Test: `$RUN/src/test/unit/org/apache/cassandra/service/AucvJmxGateProbeTest.java`, run with `ant testsome` (jamm agent
and test yaml `test/conf/cassandra.yaml` supplied by the build). Property unset (default) — the switch is driven by
the JMX methods called directly on `StorageService.instance`.

**B2b. Knobs.** `concurrent_compactors = 2` (`StorageService.instance.setConcurrentCompactors(2)`); requested V ∈ {8}
with the switch off, then on; shrink to 1; then the unchecked CompactionManager path to 16.

**B2c. Workload.** 16 tasks via `CompactionManager.instance.submitValidation(Callable)` (the production entry,
`CompactionManager.java:1295-1298`), each building one full-ring `MerkleTrees` of 2^16 leaves and blocking on a latch;
16 ≥ every pool size used, so live trees = running tasks.

**B2d. Observables and instruments.** Lines prefixed `AUCVJ`: exception class/message of each JMX call;
`getConcurrentValidators()`; `CompactionManager.instance.getCoreValidationThreads()` / `getMaximumValidatorThreads()`;
`isConcurrentValidatorsLimitEnforced()`; high-water mark of live trees; heap delta after GC (MemoryMXBean).

**B2e. Procedure.**
1. Write the test:
```java
package org.apache.cassandra.service;

import java.lang.management.ManagementFactory;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import com.google.common.util.concurrent.Uninterruptibles;
import org.junit.BeforeClass;
import org.junit.Test;
import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.db.compaction.CompactionManager;
import org.apache.cassandra.dht.IPartitioner;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.dht.Range;
import org.apache.cassandra.utils.MerkleTrees;

public class AucvJmxGateProbeTest
{
    static final StorageService SS = StorageService.instance;
    static final CompactionManager CM = CompactionManager.instance;

    @BeforeClass public static void setup() { SchemaLoader.prepareServer(); SS.setConcurrentCompactors(2); }

    static MerkleTrees buildTree()
    {
        IPartitioner p = Murmur3Partitioner.instance;
        MerkleTrees t = new MerkleTrees(p);
        t.addMerkleTree(1 << 16, new Range<>(p.getMinimumToken(), p.getMinimumToken()));
        t.init();
        return t;
    }

    static long usedAfterGc() { for (int i = 0; i < 3; i++) System.gc(); return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed(); }

    static void state(String step)
    {
        System.out.printf("AUCVJ %s flagField=%s isEnforced()=%s reported=%d core=%d max=%d%n", step,
                          org.apache.cassandra.config.DatabaseDescriptor.allowUnlimitedConcurrentValidations,
                          SS.isConcurrentValidatorsLimitEnforced(), SS.getConcurrentValidators(),
                          CM.getCoreValidationThreads(), CM.getMaximumValidatorThreads());
    }

    static void call(String step, Runnable r)
    {
        try { r.run(); System.out.printf("AUCVJ %s OK%n", step); }
        catch (Throwable t) { System.out.printf("AUCVJ %s THREW %s: %s%n", step, t.getClass().getName(), t.getMessage()); }
        state(step);
    }

    static void load(String step) throws Exception
    {
        AtomicInteger live = new AtomicInteger(), hw = new AtomicInteger();
        CountDownLatch release = new CountDownLatch(1), done = new CountDownLatch(16);
        long base = usedAfterGc();
        for (int i = 0; i < 16; i++)
            CM.submitValidation(() -> {
                MerkleTrees t = buildTree();
                hw.accumulateAndGet(live.incrementAndGet(), Math::max);
                Uninterruptibles.awaitUninterruptibly(release);
                live.decrementAndGet(); t.release(); done.countDown();
                return null;
            });
        Thread.sleep(5000);
        System.out.printf("AUCVJ %s load hw=%d heapDelta=%d%n", step, hw.get(), usedAfterGc() - base);
        release.countDown();
        done.await(120, TimeUnit.SECONDS);
    }

    @Test
    public void probe() throws Exception
    {
        call("S0 enforce", SS::enforceConcurrentValidatorsLimit);
        call("S0 set2", () -> SS.setConcurrentValidators(2));
        load("S0");
        call("S1 set8-enforced", () -> SS.setConcurrentValidators(8));
        load("S1");
        call("S2 bypass", SS::bypassConcurrentValidatorsLimit);
        call("S2 set8-bypassed", () -> SS.setConcurrentValidators(8));
        load("S2");
        call("S3 enforce-again", SS::enforceConcurrentValidatorsLimit);
        load("S3");
        call("S4 shrink-to-1", () -> SS.setConcurrentValidators(1));
        load("S4");
        call("S5 cm-max16", () -> CM.setMaximumValidatorThreads(16));
        call("S5 cm-core16", () -> CM.setCoreValidationThreads(16));
        load("S5");
    }
}
```
2. Run and extract:
```
cd $RUN/src && ant testsome -Dtest.name=org.apache.cassandra.service.AucvJmxGateProbeTest
grep -h AUCVJ $(find build/test/output -name '*AucvJmxGateProbe*') > $RUN/unit-jmx.txt
```
Record T_unit once with the B2 probe of the place-1 case, or add `ObjectSizes.measureDeep(buildTree())` to `setup()`.

**B2f. Predictions.**

| Step | JMX outcome | reported / core | load hw | heapDelta |
|---|---|---|---|---|
| S0 (enforced, set 2) | OK; `isEnforced()=false` (inverted) | 2 / 2 | 2 | ≈ 2×T_unit |
| S1 set 8, enforced | `IllegalArgumentException: Cannot set concurrent_validations greater than concurrent_compactors (2)` | 2 / 2 | 2 | ≈ 2×T_unit |
| S2 bypass + set 8 | OK; `isEnforced()=true` | 8 / 8 | 8 | ≈ 8×T_unit |
| S3 enforce again | OK; flag false | 8 / 8 (not shrunk) | 8 | ≈ 8×T_unit |
| S4 shrink to 1 (1 ≤ 2 passes the check) | expected `IllegalArgumentException` from `ThreadPoolExecutor.setMaximumPoolSize` | reported 1, core 8 (mismatch) | 8 | ≈ 8×T_unit |
| S5 CompactionManager MBean 16 | OK, no check | reported 1, core 16 | 16 | ≈ 16×T_unit |

S4 is the least certain row; if the shrink succeeds instead (core 1, hw 1), record it — it does not affect the B1 claim.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| S1 throws and hw stays 2; S2 hw 8 | claim supported: the switch decides whether the runtime resize happens, and the resize sets live tree count/heap |
| S1 succeeds (core 8) while flag false | runtime gate not effective → claim wrong |
| S2 core 8 but hw 2 | pool size does not govern concurrency → cap is elsewhere, claim wrong in its mechanism |
| S3 hw back to 2 | enforcing again shrinks the pool (contradicts A3 (b)) → amend A3, claim still holds |
| S5 hw 16 with flag false | confirms the unchecked bypass (A3 (c)); expected, not a refutation of B1 |

**B2h. Controls.** S0 (baseline at the ceiling) vs S2 (same workload, only the switch changed); S5 shows the pool,
not the switch, is what bounds usage (positive control: a known binding cap — pool size — moves usage); identical
task allocation in every step; `load` waits for all 16 tasks to finish before the next step.

### B3. Cluster tier

**B3a. Environment and build.** Same two-node loopback cluster as the place-1 case (n1 = 127.0.0.1, JMX 7199, token
`-9223372036854775808`; n2 = 127.0.0.2, JMX 7299, token `0`; RF 2; heap 2 GiB; Byteman hold rule on n2). Build and
node trees:
```
for n in n1 n2; do rsync -a --exclude test $RUN/src/ $RUN/$n/; mkdir -p $RUN/$n/{data,commitlog,hints,saved_caches,cdc,logs}; done
BM=$(find $RUN/src/build -name 'byteman-4.0.20.jar' | head -1)
sed -i 's/^JMX_PORT="7199"/JMX_PORT="7299"/' $RUN/n2/conf/cassandra-env.sh
```
Append to each node's `conf/cassandra.yaml` (last key wins, `CassandraRelevantProperties.java:44`):
`cluster_name: aucv`, `num_tokens: 1`, `initial_token: <TOKEN>`, `listen_address: <IP>`, `rpc_address: <IP>`,
`seed_provider` with seeds `"127.0.0.1:7000"`, `data_file_directories: [$RUN/nX/data]`, `commitlog_directory`,
`hints_directory`, `saved_caches_directory`, `cdc_raw_directory` under `$RUN/nX`, `concurrent_compactors: 2`,
`concurrent_validations: 2`, `repair_command_pool_size: 16`, `concurrent_merkle_tree_requests: 0`,
`repair_session_space: 128MiB` (the exact block is in the place-1 case, B3a). Property unset on both nodes.
`$RUN/hold.btm`:
```
RULE aucv hold validation trees
CLASS org.apache.cassandra.repair.Validator
METHOD complete
AT ENTRY
IF TRUE
DO Thread.sleep(30000)
ENDRULE
```
Start: `(cd $RUN/nX && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_LOG_DIR=$RUN/nX/logs JVM_EXTRA_OPTS="<OPTS>" bin/cassandra -p $RUN/nX/pid)`,
`<OPTS>` empty for n1 and `-javaagent:$BM=script:$RUN/hold.btm` for n2.
JMX client (`$RUN/tools/JmxOp.java`, run with the JDK 11 source launcher):
```java
import javax.management.*;
import javax.management.remote.*;
public class JmxOp {
  // JmxOp host port bean get Attr | set Attr N | call op [N]
  public static void main(String[] a) throws Exception {
    JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + ":" + a[1] + "/jmxrmi"));
    MBeanServerConnection m = c.getMBeanServerConnection(); ObjectName o = new ObjectName(a[2]);
    try {
      if (a[3].equals("get")) System.out.println(m.getAttribute(o, a[4]));
      else if (a[3].equals("set")) { m.setAttribute(o, new Attribute(a[4], Integer.parseInt(a[5]))); System.out.println("ok"); }
      else { boolean arg = a.length > 5;
             System.out.println(m.invoke(o, a[4], arg ? new Object[]{ Integer.parseInt(a[5]) } : new Object[0],
                                         arg ? new String[]{ "int" } : new String[0])); }
    } catch (Exception e) { Throwable t = e; while (t.getCause() != null) t = t.getCause(); System.out.println("THREW " + t); }
    c.close();
  }
}
```
Shorthands: `SS="org.apache.cassandra.db:type=StorageService"`, `CMB="org.apache.cassandra.db:type=CompactionManager"`,
`J2="java $RUN/tools/JmxOp.java 127.0.0.1 7299"`.

**B3b. Knobs.** All on n2 at runtime over JMX, no restart between C0–C3; restart before C4.

| Phase | JMX actions on n2 | Why |
|---|---|---|
| C0 | none (V = 2 from yaml) | baseline at the ceiling |
| C1 | `$J2 $SS call setConcurrentValidators 8` (switch off) | gate must refuse |
| C2 | `$J2 $SS call bypassConcurrentValidatorsLimit`; `$J2 $SS call setConcurrentValidators 8` | switch on → resize |
| C3 | `$J2 $SS call enforceConcurrentValidatorsLimit`; then `$J2 $SS call setConcurrentValidators 2` | re-enforce and shrink (A3 (b), (e)) |
| C4 | restart n2; `$J2 $CMB set MaximumValidatorThreads 8`; `$J2 $CMB set CoreValidationThreads 8` (switch off) | unchecked bypass (A3 (c)) |

After each action read `$J2 $SS get ConcurrentValidators`, `$J2 $SS get ConcurrentValidatorsLimitEnforced`,
`$J2 $CMB get CoreValidationThreads`, `$J2 $CMB get MaximumValidatorThreads`.

**B3c. Workload.** As in the place-1 case: keyspace `ks` RF 2, 8 tables `t1..t8 (k int PRIMARY KEY, v text)` with
300,000 partitions each (v = 100 chars), loaded once with `cqlsh COPY` from
`seq 0 299999 | awk '{printf "%d,%0100d\n",$1,$1}'` and flushed on both nodes (≈ 350 MB per node). Per phase:
8 concurrent full repairs from n1, one table each:
```
for i in $(seq 1 8); do $RUN/n1/bin/nodetool -h 127.0.0.1 -p 7199 repair -full ks t$i > $RUN/rep-$PH-t$i.log 2>&1 & done; wait
```
Each validation on n2 builds 2 trees (2 ranges) of depth ≈ 17 (budget 128 MiB / 2 / 2 per range, ≈ 150k partitions
per range), N ≈ 2^18 leaves, T ≲ 64 MiB; the 30 s hold keeps them alive while the thread is busy.

**B3d. Observables and instruments.** On n2 during each phase's repairs: `nodetool -h 127.0.0.1 -p 7299 tpstats |
grep ValidationExecutor` every 1 s (max Active, Pending); `jcmd <n2 pid> GC.class_histogram | grep -E
'MerkleTree\$OnHeap(Leaf|Inner)'` and `jcmd <n2 pid> GC.heap_info` every 10 s (max live leaves / bytes, used heap after
GC); the JMX reads of B3b; `grep "Created .* merkle trees" $RUN/n2/logs/debug.log` for N; `grep -E "concurrent
validations|concurrent_validations" $RUN/n2/logs/system.log` for the INFO lines of `StorageService.java:1974`, `1980`, `2024`.

**B3e. Procedure.**
1. Start n1, then n2 (B3a); `nodetool status` shows both UN; load data (B3c).
2. For PH in C0 C1 C2 C3: apply the phase's JMX actions and reads (B3b); start the two samplers
   (`tpstats` 1 s loop and histogram 10 s loop, writing `$RUN/$PH-tp.txt`, `$RUN/$PH-histo.txt`, as in the place-1 case
   B3e step 2); run the 8 repairs; `wait`; stop the samplers; check repair logs for success.
3. Stop n2 (B4), start it again with the same config (switch off, V = 2), run C4 the same way.
4. Tabulate per phase: JMX outcome, reported V, core, max Active, max Pending, max live OnHeapLeaf.

**B3f. Predictions.** N from debug.log (≈ 262,144).

| Phase | JMX outcome | reported / core | max Active | max live OnHeapLeaf |
|---|---|---|---|---|
| C0 | — | 2 / 2 | 2 | ≈ 2N |
| C1 | `THREW java.lang.IllegalArgumentException: Cannot set concurrent_validations greater than concurrent_compactors (2)` | 2 / 2 | 2 | ≈ 2N |
| C2 | ok, ok | 8 / 8 | 8 | ≈ 8N (≈ 4× C0) |
| C3 | enforce ok; shrink expected `THREW IllegalArgumentException` (JDK) | 2 / 8 | 8 | ≈ 8N |
| C4 | ok, ok (no check) | 2 / 8 | 8 | ≈ 8N |

Tolerance ±15 % on leaf counts; leaves never exceed max Active × N × 1.05.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| C1 refused and stays at 2N; C2 reaches ≈ 8N | claim confirmed: the runtime gate, while the switch is off, keeps concurrent tree memory at compactors × T |
| C1 accepted (core 8) or C1 leaves ≈ 8N | runtime gate not effective → claim wrong |
| C2 accepted but Active stays 2 | resizing does not change concurrency, or the workload did not deliver 8 concurrent requests (check n1 repair logs and n1 `tpstats` Repair-Task) → not confirmed |
| C3 core back to 2 and leaves ≈ 2N | shrink works and enforcing is effective after the fact → amend A3 (b)/(e); B1 unaffected |
| C4 Active 8 with switch off | unchecked bypass confirmed (expected; limits the strength of the cap, not B1) |

**B3h. Controls.** C0 vs C1 (refused call changes nothing); C2 (positive control: same workload moves usage when the pool
is allowed to grow); C4 (pool size, not the switch, is what bounds usage); n1 unchanged across phases; repair_command_pool_size
16 and concurrent_merkle_tree_requests 0 remove coordinator throttles; n2 is validator only, so its heap excludes coordinator trees.

**B4. Risks and cleanup.** Data ≈ 350 MB per node under `$RUN` (local disk; `df -h` first); nothing on shared storage;
the shared tree is only read. Heap 2 GiB × 2. After the tiers:
```
for n in n1 n2; do [ -f $RUN/$n/pid ] && kill $(cat $RUN/$n/pid); done; sleep 20
pkill -f "$RUN/n[12]"; pkill -f "while sleep 1; do date" ; pkill -f "while sleep 10; do date"
pgrep -af "CassandraDaemon|nodetool|cqlsh|JmxOp" | grep "$RUN" || echo clean
```
Unit tier: one forked JVM from `ant testsome`; check `pgrep -af AucvJmxGateProbe` is empty. `rm -rf $RUN` when stage 4 is done.

## C. Sources read

src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/service/StorageService.java
src/java/org/apache/cassandra/service/StorageServiceMBean.java
src/java/org/apache/cassandra/db/compaction/CompactionManager.java
src/java/org/apache/cassandra/db/compaction/CompactionManagerMBean.java
src/java/org/apache/cassandra/repair/ValidationManager.java
src/java/org/apache/cassandra/repair/Validator.java
src/java/org/apache/cassandra/repair/RepairCoordinator.java
src/java/org/apache/cassandra/utils/MerkleTree.java
src/java/org/apache/cassandra/utils/MerkleTrees.java
src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java
src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBase.java
src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorJMXAdapter.java
src/java/org/apache/cassandra/concurrent/WrappedExecutorPlus.java
src/java/org/apache/cassandra/tools/nodetool/ (directory listing: no set/getconcurrentvalidators command)
test/unit/org/apache/cassandra/db/compaction/ValidationExecutorTest.java
test/unit/org/apache/cassandra/config/DatabaseDescriptorTest.java
conf/cassandra.yaml
conf/cassandra-env.sh
build.xml
CHANGES.txt
https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html (cited from knowledge of the JDK API, not fetched)
https://issues.apache.org/jira/browse/CASSANDRA-13521 (cited from CHANGES.txt, not fetched)

## D. Stage-4 feedback

none yet
