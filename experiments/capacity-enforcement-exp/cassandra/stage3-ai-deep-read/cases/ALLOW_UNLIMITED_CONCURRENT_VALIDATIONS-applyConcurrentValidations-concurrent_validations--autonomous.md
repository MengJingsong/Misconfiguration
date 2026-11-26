# ALLOW_UNLIMITED_CONCURRENT_VALIDATIONS (startup gate on concurrent_validations) — verification solution  <!-- file: cases/ALLOW_UNLIMITED_CONCURRENT_VALIDATIONS-applyConcurrentValidations-concurrent_validations--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the startup check `concurrent_validations > concurrent_compactors && !allowUnlimitedConcurrentValidations`: [`DatabaseDescriptor.java:1077`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1077) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-26 |
| Estimate | `positive`. With the property unset (default `false`) the node refuses to start when `concurrent_validations > concurrent_compactors`, so the ValidationExecutor has at most `concurrent_compactors` threads, and each running validation holds one set of Merkle trees of up to `repair_session_space / RF` bytes on heap; setting the property to `true` removes that ceiling and the heap held by concurrent validations grows with `concurrent_validations`. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `ALLOW_UNLIMITED_CONCURRENT_VALIDATIONS`, a JVM system property
`-Dcassandra.allow_unlimited_concurrent_validations`, declared at
[`CassandraRelevantProperties.java:47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L47).
Kind: boolean switch (it is not itself a size; it turns the limit `concurrent_validations ≤ concurrent_compactors` on or off).
No default string is given, so `getBoolean()` yields `false` when unset. It is read once into
`public static volatile boolean DatabaseDescriptor.allowUnlimitedConcurrentValidations` at class initialisation
(`src/java/org/apache/cassandra/config/DatabaseDescriptor.java:229`). Set by `-D` on the JVM command line
(e.g. `JVM_EXTRA_OPTS`, `conf/jvm-server.options`); for the startup check it needs a restart. The same static
field can also be flipped at runtime over JMX (`StorageService.bypassConcurrentValidatorsLimit` /
`enforceConcurrentValidatorsLimit`, `StorageService.java:1972-1982`), but that only matters for the runtime path
(separate case `…-setConcurrentValidators-value`), because the startup check has run by then.
The limit it switches compares two yaml entries: `concurrent_validations` (`Config.java:671`, default 0 → "use
`concurrent_compactors`") and `concurrent_compactors` (`Config.java:335`, default
`min(8, max(2, min(cores, #data dirs)))`, `DatabaseDescriptor.java:777-781`). Unit of both: threads.
Documented in `conf/cassandra.yaml:1232-1239`.

**A2. What it caps.** Indirectly, heap used by repair validation compactions on a replica. The quantity compared is
`config.concurrent_validations` (requested validation threads) against `config.concurrent_compactors`.
`concurrent_validations` becomes the core and maximum size of the `ValidationExecutor`
(`CompactionManager.java:2109-2120`), i.e. the number of validations that run at the same time. Each running
validation allocates a `MerkleTrees` object sized from `repair_session_space / RF` (`ValidationManager.java:54-88`,
created at `ValidationManager.java:127`) plus sstable scanners, and holds them until `Validator.complete()` hands
them to the ANTI_ENTROPY stage (`Validator.java:222-237`, `253-268`). So the resource is heap (on-heap
`MerkleTree$OnHeapLeaf/OnHeapInner` nodes and their 32-byte hash arrays); with the switch off, the validation-side
tree heap is bounded by about `concurrent_compactors × repair_session_space / RF`.

**A3. Mechanism.**
1. `DatabaseDescriptor.applySimpleConfig` derives `concurrent_compactors` (`DatabaseDescriptor.java:777-781`), then
   calls `applyConcurrentValidations(conf)` and `applyRepairCommandPoolSize(conf)` (`DatabaseDescriptor.java:783-784`).
2. `applyConcurrentValidations` (`DatabaseDescriptor.java:1071-1082`): if `concurrent_validations < 1` it is set to
   `concurrent_compactors` (`:1073-1076`); **the check**
   [`DatabaseDescriptor.java:1077`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1077):
   `else if (config.concurrent_validations > config.concurrent_compactors && !allowUnlimitedConcurrentValidations)`
   throws `ConfigurationException("To set concurrent_validations > concurrent_compactors, set the system property
   -Dcassandra.allow_unlimited_concurrent_validations=true")` (`:1079-1080`). Outcome when the limit is exceeded and the
   switch is off: the node does not start. With the switch on: the value is kept as is (no upper bound at all).
3. `CompactionManager` builds `ValidationExecutor` with `DatabaseDescriptor.getConcurrentValidations()` threads and an
   unbounded queue (`CompactionManager.java:160`, `2109-2114`; queue limit `Integer.MAX_VALUE`). Builder semantics: core
   = max = threads, unbounded queue, core threads may time out (`ThreadPoolExecutorBuilder.java:34-39`). So at most
   `concurrent_validations` validations run; the rest wait in the queue.
4. Validation requests arrive through `ValidationManager.submitValidation` → `cfs.getRepairManager().submitValidation`
   → `CompactionManager.submitValidation` → `validationExecutor.submitIfRunning` (`ValidationManager.java:186-212`,
   `CompactionManager.java:1295-1298`). A queued request holds only the `Callable` and `Validator`; trees are created
   inside `doValidation` when the task runs (`ValidationManager.java:127`).
5. Tree size per validation: budget `repair_session_space MiB × 1 MiB / RF` (`ValidationManager.java:62-63`), split by
   each range's share of partitions; depth = `min(ceil(log2(partitions in range)), estimatedMaxDepthForBytes(...),
   repair_session_max_tree_depth=20)` (`ValidationManager.java:65-80`, `MerkleTree.java:1520-1541`,
   `DatabaseDescriptor.java:595-606`). `repair_session_space` defaults to heap/16 (`DatabaseDescriptor.java:609-614`).
   Trees are built on heap (`MerkleTree.java:139-162`); `use_offheap_merkle_trees` only affects trees moved after
   completion/deserialisation (`Validator.java:295-300`, `MerkleTree.java:769-772`).

Bypasses and overshoots: (a) the ceiling is `concurrent_compactors`, itself a free yaml value (no upper bound once set
explicitly, `DatabaseDescriptor.java:777-781`), so the "cap" is relative; (b) after startup the pool can be grown over
JMX without this check: `CompactionManagerMBean.setCoreValidationThreads/setMaximumValidatorThreads`
(`CompactionManager.java:2304-2320`), and `StorageService.setConcurrentValidators` after
`bypassConcurrentValidatorsLimit` (`StorageService.java:1972-2029`); (c) `StorageService.setConcurrentCompactors` at
runtime (`StorageService.java:1964-1970`) does not re-check validations; (d) completed trees are passed to the
ANTI_ENTROPY stage and network send/retry (`Validator.java:236`, `281-300`) after the executor thread is freed, so trees
waiting to be sent are outside the thread-count bound.

**A4. Other consumers.** Repair coordinator memory for received trees (bounded per command by
`concurrent_merkle_tree_requests`, `RepairCoordinator.java:127`; off-heap by default, `Config.java:212`); normal
compactions on `CompactionExecutor` (`concurrent_compactors`); streaming; memtables, caches; the Repair-Task pool whose
default size is derived from `concurrent_validations` (`DatabaseDescriptor.java:1085-1089`, separate case
`…-applyRepairCommandPoolSize-repair_command_pool_size`).

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:1232-1239` (documents the property and the JMX bypass); `conf/cassandra.yaml:827-861`
  (`repair_session_space`, `concurrent_merkle_tree_requests`).
- `CHANGES.txt:1974`: "Add configurable upper bound for validation executor threads (CASSANDRA-13521)",
  https://issues.apache.org/jira/browse/CASSANDRA-13521.
- `test/unit/org/apache/cassandra/config/DatabaseDescriptorTest.java:509-536` (testConcurrentValidations: the exception
  text and the bypass); `test/unit/org/apache/cassandra/db/compaction/ValidationExecutorTest.java` (queueing beyond
  core size, `adjustPoolSize`).
- CASSANDRA-14096 (repair_session_space), linked from `conf/cassandra.yaml:837`.

## Config-first: places found

Flow: `CassandraRelevantProperties.java:47` → `DatabaseDescriptor.allowUnlimitedConcurrentValidations`
(`DatabaseDescriptor.java:229`; written at runtime by `StorageService.java:1975`, `1981`; read back, with inverted
naming, by `StorageService.isConcurrentValidatorsLimitEnforced`, `StorageService.java:1984-1987`, which returns `true`
when the limit is *not* enforced).

| # | Place | What it restricts | Case file |
|---|---|---|---|
| 1 | `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:1077` | startup: refuses `concurrent_validations > concurrent_compactors` unless the property is true → ValidationExecutor thread count → concurrent on-heap Merkle-tree builds | this file |
| 2 | `src/java/org/apache/cassandra/service/StorageService.java:2012` | runtime JMX `setConcurrentValidators`: same ceiling for resizing the ValidationExecutor | `ALLOW_UNLIMITED_CONCURRENT_VALIDATIONS-setConcurrentValidators-value--autonomous.md` |
| 3 | `src/java/org/apache/cassandra/service/StorageService.java:1972-1982` | JMX switch `bypassConcurrentValidatorsLimit` / `enforceConcurrentValidatorsLimit` that turns place 2 off/on at runtime | covered in the place-2 file |
| 4 | `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:1087-1088` | `repair_command_pool_size` defaults to `concurrent_validations` (so a value admitted by place 1 also sizes the Repair-Task pool, `ActiveRepairService.java:205`, `208-219`) | `ALLOW_UNLIMITED_CONCURRENT_VALIDATIONS-applyRepairCommandPoolSize-repair_command_pool_size--autonomous.md` |

Not restricted by the property (checked): `CompactionManagerMBean` resize ops (`CompactionManager.java:2304-2320`),
`StorageService.setConcurrentCompactors` (`StorageService.java:1964-1970`), `DatabaseDescriptor.setConcurrentValidations`
(`DatabaseDescriptor.java:2528-2532`, maps ≤ 0 to `Integer.MAX_VALUE`).

## B. Verification solution

**B1. Claim under test.** With `-Dcassandra.allow_unlimited_concurrent_validations` unset, a node cannot run more than
`concurrent_compactors` validations at once (a config asking for more is refused at startup), so the on-heap Merkle-tree
memory of concurrent validations stays at about `concurrent_compactors × T` (T = trees of one validation,
`T ≤ repair_session_space / RF`); with the property `true` and `concurrent_validations = V > concurrent_compactors`,
it rises to about `V × T` under the same repair workload.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tree to local disk and build there (never in the shared tree):
```
RUN=/mydata/s4-aucv            # local disk; check: df -h /mydata  (need ≥ 10 GiB free)
mkdir -p $RUN && rsync -a /users/jason92/cassandra-5.0.9/ $RUN/src/
cd $RUN/src && ant jar build-test
```
Test source: `$RUN/src/test/unit/org/apache/cassandra/config/AucvGateProbeTest.java` (package `org.apache.cassandra.config`
so it can call the package-private `applyConcurrentValidations`). JVM options come from `ant testsome` (jamm agent
included, `build.xml:1159`); the property is passed through `-Dtest.jvm.args` (`build.xml:94`, `1192`).

**B2b. Knobs.** `concurrent_compactors = 2` fixed; `concurrent_validations V ∈ {1, 2, 4, 8}` (two at/below the ceiling,
two above it); property unset vs `-Dcassandra.allow_unlimited_concurrent_validations=true` (two JVM runs, because the
static field is read at class load, `DatabaseDescriptor.java:229`).

**B2c. Workload.** 16 tasks submitted to a fresh `CompactionManager.ValidationExecutor`; each task builds one
`MerkleTrees` with one full-ring Murmur3 tree of `2^16` leaves (`MerkleTree.init`, `MerkleTree.java:139-147`) — the
same object a validation holds — then blocks on a latch. 16 > 8 ≥ V, so the executor is saturated in every case and
the number of live trees equals the number of running tasks.

**B2d. Observables and instruments.** Printed lines prefixed `AUCV`: gate outcome (accepted value or exception text);
executor `getCorePoolSize()`, `getActiveTaskCount()`, `getPendingTaskCount()`; high-water mark of live trees
(AtomicInteger); heap delta = `MemoryMXBean` heap used after 3× `System.gc()` with tasks blocked minus the same before
submission; `T_unit = ObjectSizes.measureDeep(one tree)`. Not observable here: real validation trees (data-dependent
depth), network sends.

**B2e. Procedure.**
1. Write the test:
```java
package org.apache.cassandra.config;

import java.lang.management.ManagementFactory;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import com.google.common.util.concurrent.Uninterruptibles;
import org.junit.Test;
import org.apache.cassandra.db.compaction.CompactionManager;
import org.apache.cassandra.dht.IPartitioner;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.dht.Range;
import org.apache.cassandra.exceptions.ConfigurationException;
import org.apache.cassandra.utils.MerkleTrees;
import org.apache.cassandra.utils.ObjectSizes;

public class AucvGateProbeTest
{
    static final int TASKS = 16, DEPTH = 16, COMPACTORS = 2;

    static MerkleTrees buildTree()
    {
        IPartitioner p = Murmur3Partitioner.instance;
        MerkleTrees t = new MerkleTrees(p);
        t.addMerkleTree(1 << DEPTH, new Range<>(p.getMinimumToken(), p.getMinimumToken()));
        t.init();
        return t;
    }

    static long usedAfterGc()
    {
        for (int i = 0; i < 3; i++) System.gc();
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    @Test
    public void probe() throws Exception
    {
        DatabaseDescriptor.clientInitialization();
        DatabaseDescriptor.setConcurrentCompactors(COMPACTORS);
        DatabaseDescriptor.setConcurrentValidations(COMPACTORS);
        CompactionManager.instance.forceShutdown();   // as ValidationExecutorTest does
        System.out.printf("AUCV prop=%s flag=%s%n",
                          System.getProperty("cassandra.allow_unlimited_concurrent_validations"),
                          DatabaseDescriptor.allowUnlimitedConcurrentValidations);
        System.out.printf("AUCV T_unit=%d%n", ObjectSizes.measureDeep(buildTree()));
        for (int v : new int[]{ 1, 2, 4, 8 })
        {
            Config c = new Config();
            c.concurrent_compactors = COMPACTORS;
            c.concurrent_validations = v;
            try { DatabaseDescriptor.applyConcurrentValidations(c); }
            catch (ConfigurationException e) { System.out.printf("AUCV v=%d REJECTED %s%n", v, e.getMessage()); continue; }
            DatabaseDescriptor.setConcurrentValidations(c.concurrent_validations);
            CompactionManager.ValidationExecutor ex = new CompactionManager.ValidationExecutor();
            AtomicInteger live = new AtomicInteger(), hw = new AtomicInteger();
            CountDownLatch release = new CountDownLatch(1);
            long base = usedAfterGc();
            for (int i = 0; i < TASKS; i++)
                ex.submit(() -> {
                    MerkleTrees t = buildTree();
                    hw.accumulateAndGet(live.incrementAndGet(), Math::max);
                    Uninterruptibles.awaitUninterruptibly(release);
                    live.decrementAndGet();
                    t.release();
                });
            Thread.sleep(5000);
            long held = usedAfterGc() - base;
            System.out.printf("AUCV v=%d accepted=%d core=%d active=%d pending=%d hw=%d heapDelta=%d%n",
                              v, c.concurrent_validations, ex.getCorePoolSize(), ex.getActiveTaskCount(),
                              ex.getPendingTaskCount(), hw.get(), held);
            release.countDown();
            ex.shutdown();
            ex.awaitTermination(60, TimeUnit.SECONDS);
        }
    }
}
```
2. Run without the property, then with it:
```
cd $RUN/src
ant testsome -Dtest.name=org.apache.cassandra.config.AucvGateProbeTest
cp build/test/output/TEST-org.apache.cassandra.config.AucvGateProbeTest.xml $RUN/unit-off.xml
ant testsome -Dtest.name=org.apache.cassandra.config.AucvGateProbeTest \
     -Dtest.jvm.args="-Dcassandra.allow_unlimited_concurrent_validations=true"
cp build/test/output/TEST-org.apache.cassandra.config.AucvGateProbeTest.xml $RUN/unit-on.xml
grep -h AUCV $RUN/unit-off.xml $RUN/unit-on.xml
```
(If the output file name differs, `find build/test/output -name '*AucvGateProbe*'`.)

**B2f. Predictions.**

| Run | V=1 | V=2 | V=4 | V=8 |
|---|---|---|---|---|
| property unset (`flag=false`) | accepted, core 1, hw 1, pending 15, heapDelta ≈ 1×T_unit | accepted, core 2, hw 2, pending 14, ≈ 2×T_unit | REJECTED with the exact message of `DatabaseDescriptor.java:1079-1080` | REJECTED |
| property `true` (`flag=true`) | hw 1, ≈ 1×T_unit | hw 2, ≈ 2×T_unit | accepted, core 4, hw 4, ≈ 4×T_unit | accepted, core 8, hw 8, pending 8, ≈ 8×T_unit |

"≈" means within ±30 % (GC noise; T_unit is a few MiB for 2^16 leaves). hw never exceeds core.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Table above reproduced | claim supported at unit level: the switch decides whether V above compactors is admitted, and admitted V sets live trees and heap |
| `flag=false` and V=4/8 accepted | gate not effective → claim wrong |
| `prop=true` printed but `flag=false` | property not reaching the field (run setup error), not a verdict |
| hw > core for any V | the executor does not bound concurrency → claim wrong (cap is not thread count) |
| hw = core but heapDelta flat across V | per-task allocation not retained (probe error) — fix probe, not confirmed |

**B2h. Controls.** V=1 vs V=2 (both admitted with the switch off) shows heap moves with V independent of the switch;
the `flag=true` row with V=1/2 shows the switch alone does not change usage (it only admits larger V); 16 tasks
guarantee saturation; same tree size for all tasks.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, two Cassandra nodes on loopback addresses (n1 = 127.0.0.1, n2 =
127.0.0.2), RF = 2, JDK 11. After the B2a build:
```
for n in n1 n2; do rsync -a --exclude test $RUN/src/ $RUN/$n/; mkdir -p $RUN/$n/{data,commitlog,hints,saved_caches,cdc,logs}; done
ls $RUN/n1/build/apache-cassandra-*.jar $RUN/n1/lib/jamm-*.jar     # both must exist
BM=$(find $RUN/src/build -name 'byteman-4.0.20.jar' | head -1); echo $BM   # test dependency, fetched by build-test
sed -i 's/^JMX_PORT="7199"/JMX_PORT="7299"/' $RUN/n2/conf/cassandra-env.sh
```
Append to each `conf/cassandra.yaml` (duplicate keys are allowed and the last wins, `CassandraRelevantProperties.java:44`);
for nX with IP and token (n1: 127.0.0.1, `-9223372036854775808`; n2: 127.0.0.2, `0`):
```
cat >> $RUN/nX/conf/cassandra.yaml <<EOF
cluster_name: aucv
num_tokens: 1
initial_token: <TOKEN>
listen_address: <IP>
rpc_address: <IP>
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "127.0.0.1:7000"
data_file_directories: [$RUN/nX/data]
commitlog_directory: $RUN/nX/commitlog
hints_directory: $RUN/nX/hints
saved_caches_directory: $RUN/nX/saved_caches
cdc_raw_directory: $RUN/nX/cdc
concurrent_compactors: 2
concurrent_validations: <V>
repair_command_pool_size: 16
concurrent_merkle_tree_requests: 0
repair_session_space: 128MiB
EOF
```
Start (heap 2 GiB, G1 from `conf/jvm11-server.options:63`):
```
start() { # $1=node  $2=extra JVM opts
  (cd $RUN/$1 && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_LOG_DIR=$RUN/$1/logs JVM_EXTRA_OPTS="$2" \
     bin/cassandra -p $RUN/$1/pid > $RUN/$1/logs/stdout 2>&1); }
start n1 ""; sleep 40; start n2 "<OPTS>"; sleep 60
$RUN/n1/bin/nodetool -h 127.0.0.1 -p 7199 status      # both UN
```
Hold rule for n2 (`$RUN/hold.btm`) — keeps each finished validation's trees alive on its executor thread for 30 s so
concurrency is observable (Validator.complete runs on the executor thread, `ValidationManager.java:141`):
```
RULE aucv hold validation trees
CLASS org.apache.cassandra.repair.Validator
METHOD complete
AT ENTRY
IF TRUE
DO Thread.sleep(30000)
ENDRULE
```
n2 `<OPTS>` per run (B3b) always includes `-javaagent:$BM=script:$RUN/hold.btm`.

**B3b. Knobs.** On n2 only (n1 keeps `concurrent_validations: 2`, property unset); `concurrent_compactors: 2` on both.

| Run | n2 `concurrent_validations` | n2 property | Why |
|---|---|---|---|
| R0 | 8 | unset | gate must refuse startup |
| R1 | 2 | unset | at the ceiling, switch off |
| R2 | 8 | `-Dcassandra.allow_unlimited_concurrent_validations=true` | above the ceiling, switch on |
| R3 | 2 | `=true` | switch on, V unchanged (switch alone does nothing) |
| R4 | 0 (default) | unset | default path → V = compactors = 2 |

Change n2's appended `concurrent_validations:` line and restart n2 between runs (stop per B4). Confirm the property:
`jcmd $(cat $RUN/n2/pid) VM.system_properties | grep allow_unlimited`.

**B3c. Workload.** Keyspace `ks` RF 2; K = 8 tables `t1..t8 (k int PRIMARY KEY, v text)`, each with P = 300,000
partitions (v = 100 chars), loaded once and flushed on both nodes:
```
CQ=$RUN/n1/bin/cqlsh
$CQ 127.0.0.1 -e "CREATE KEYSPACE ks WITH replication={'class':'NetworkTopologyStrategy','datacenter1':2}"
for i in $(seq 1 8); do $CQ 127.0.0.1 -e "CREATE TABLE ks.t$i (k int PRIMARY KEY, v text)"; done
seq 0 299999 | awk '{printf "%d,%0100d\n",$1,$1}' > $RUN/rows.csv          # ~32 MB
for i in $(seq 1 8); do $CQ 127.0.0.1 -e "COPY ks.t$i (k,v) FROM '$RUN/rows.csv' WITH CHUNKSIZE=5000"; done
$RUN/n1/bin/nodetool -h 127.0.0.1 -p 7199 flush ks; $RUN/n1/bin/nodetool -h 127.0.0.1 -p 7299 flush ks
```
Disk ≈ 8 × 300k × ~140 B ≈ 350 MB per node. Arithmetic: 2 ranges per validation (num_tokens 1, 2 nodes, both ranges
replicated on {n1,n2} → one session, one validation per table per node); ~150k partitions per range →
`ceil(log2 150000) = 18`; budget per range = 0.5 × 128 MiB / 2 = 32 MiB → `estimatedMaxDepthForBytes` gives
d = floor(log2(32 MiB / (leaf+inner))) = 17 for leaf+inner between 128 and 256 B (so depth is set by the budget,
d ≈ 17, capped by 20). Per validation N = 2 × 2^d leaves ≈ 262,144, T ≲ 64 MiB (`repair_session_space/RF`).
Repair: 8 concurrent full repairs, one table each, coordinated by n1 (repair_command_pool_size 16 so the coordinator
does not serialise them):
```
for i in $(seq 1 8); do $RUN/n1/bin/nodetool -h 127.0.0.1 -p 7199 repair -full ks t$i > $RUN/rep-$RUN_ID-t$i.log 2>&1 & done; wait
```
n2 receives 8 validation requests at once; with the 30 s hold, runtime ≈ ceil(8/V) × 30 s + scan time (R1: ~2 min, R2: ~40 s).

**B3d. Observables and instruments.** On n2 (pure validator; n1 is the coordinator and its received trees are off-heap,
so they are not in n2's heap), from just before the repairs until they finish:
- `nodetool -h 127.0.0.1 -p 7299 tpstats | grep ValidationExecutor` every 1 s → Active, Pending (max of each).
- `jcmd $(cat $RUN/n2/pid) GC.class_histogram | grep -E 'MerkleTree\$OnHeap(Leaf|Inner)'` every 10 s (forces a full GC,
  so it counts live objects) → max instance counts and bytes of `OnHeapLeaf` and `OnHeapInner`.
- `jcmd $(cat $RUN/n2/pid) GC.heap_info` right after each histogram → used heap after GC.
- `grep "Created .* merkle trees" $RUN/n2/logs/debug.log` → N (tree size per validation) and its byte count
  (`ValidationManager.java:82-86`; debug.log is on by default, `conf/logback.xml:48-66`).
- R0: `grep -A2 "allow_unlimited_concurrent_validations" $RUN/n2/logs/system.log` and whether the pid survives.
Not directly observable: per-object attribution of byte[] hash arrays to trees (use counts of nodes instead).

**B3e. Procedure.**
1. B3a build/config, start n1 (V=2, unset), start n2 for R1, load data (B3c) once.
2. For each run R1, R2, R3, R4 (R0 separately): (re)start n2 with that run's config; set `RUN_ID`; start the samplers
   in the background writing to `$RUN/$RUN_ID-tp.txt` and `$RUN/$RUN_ID-histo.txt`:
   ```
   P2=$(cat $RUN/n2/pid)
   ( while sleep 1; do date +%s; $RUN/n1/bin/nodetool -h 127.0.0.1 -p 7299 tpstats | grep ValidationExecutor; done ) > $RUN/$RUN_ID-tp.txt & S1=$!
   ( while sleep 10; do date +%s; jcmd $P2 GC.class_histogram | grep -E 'MerkleTree\$OnHeap(Leaf|Inner)'; jcmd $P2 GC.heap_info | head -3; done ) > $RUN/$RUN_ID-histo.txt & S2=$!
   ```
   run the 8 repairs (B3c), `wait` for them, then `kill $S1 $S2`. Check every `rep-*.log` ends with success.
3. R0: set n2 `concurrent_validations: 8`, no property; start n2; after 60 s check `system.log` for the exception and
   `kill -0 $(cat $RUN/n2/pid)` (expected: process gone).
4. Tabulate per run: max Active, max Pending, max OnHeapLeaf count, max OnHeapLeaf+OnHeapInner bytes, N from debug.log.

**B3f. Predictions.** Let N = tree size from debug.log (expected ≈ 2^18 = 262,144 leaves per validation).

| Run | Startup | max Active | max Pending | max live OnHeapLeaf on n2 | tree heap |
|---|---|---|---|---|---|
| R0 | fails: `ConfigurationException` "To set concurrent_validations > concurrent_compactors, set the system property -Dcassandra.allow_unlimited_concurrent_validations=true" | — | — | — | — |
| R1 | ok | 2 | ≈ 6 | ≈ 2N (±15 %) | ≈ 2T |
| R2 | ok | 8 | 0–1 | ≈ 8N | ≈ 8T, i.e. ≈ 4× R1 |
| R3 | ok | 2 | ≈ 6 | ≈ 2N | = R1 |
| R4 | ok | 2 | ≈ 6 | ≈ 2N | = R1 |

Leaf count never exceeds max Active × N (+5 % slack).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| R0 refused, R1/R3/R4 at 2N, R2 at ≈ 8N | claim confirmed: switch off caps concurrent tree memory at compactors × T; switch on lets V raise it |
| R0 starts with V=8 and the property unset | gate not effective → claim wrong |
| R1 leaves > 2N × 1.15 or Active > 2 | something other than the executor size lets validations run → claim wrong for the cap |
| R2 leaves ≈ R1 leaves although Active reached 8 | trees not retained per validation (hold rule not applied?) → not confirmed; check `grep -i byteman $RUN/n2/logs/stdout` |
| R2 Active never > 2 | workload did not deliver > 2 concurrent requests (coordinator serialising) → not confirmed; check n1 `tpstats` Repair-Task and repair logs |
| R3 differs from R1 | the switch has an effect beyond admitting V → investigate, claim incomplete |

**B3h. Controls.** R3 (switch on, same V) and R4 (default V) isolate the switch from V; n1 config fixed in all runs;
`repair_command_pool_size 16` and `concurrent_merkle_tree_requests 0` remove coordinator-side throttles; the hold rule is
identical in all runs, so only the number of concurrently held trees changes; measuring n2 (validator only) excludes
coordinator tree memory; same data and N each run (compare N in debug.log across runs).

**B4. Risks and cleanup.** Disk: ≈ 350 MB per node plus commit log under `$RUN` on local disk (check `df -h` before);
nothing on shared storage; the shared tree `/users/jason92/cassandra-5.0.9` is only read by rsync. Heap 2 GiB per node
(≥ 8 GiB RAM host). Stop everything after each tier:
```
for n in n1 n2; do [ -f $RUN/$n/pid ] && kill $(cat $RUN/$n/pid); done; sleep 20
pkill -f "$RUN/n[12]" ; kill $S1 $S2 2>/dev/null
pgrep -af "CassandraDaemon|nodetool|cqlsh" | grep "$RUN" || echo clean
```
Unit tier: `ant testsome` forks one JVM that exits; check `pgrep -af AucvGateProbe` is empty. Remove `$RUN` when stage 4
is done (`rm -rf $RUN`).

## C. Sources read

src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/service/StorageService.java
src/java/org/apache/cassandra/service/StorageServiceMBean.java
src/java/org/apache/cassandra/service/ActiveRepairService.java
src/java/org/apache/cassandra/db/compaction/CompactionManager.java
src/java/org/apache/cassandra/db/compaction/CompactionManagerMBean.java
src/java/org/apache/cassandra/db/compaction/AbstractCompactionStrategy.java
src/java/org/apache/cassandra/db/repair/CassandraValidationIterator.java
src/java/org/apache/cassandra/repair/ValidationManager.java
src/java/org/apache/cassandra/repair/Validator.java
src/java/org/apache/cassandra/repair/RepairCoordinator.java
src/java/org/apache/cassandra/utils/MerkleTree.java
src/java/org/apache/cassandra/utils/MerkleTrees.java
src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java
src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBase.java
src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorJMXAdapter.java
src/java/org/apache/cassandra/concurrent/WrappedExecutorPlus.java
test/unit/org/apache/cassandra/config/DatabaseDescriptorTest.java
test/unit/org/apache/cassandra/db/compaction/ValidationExecutorTest.java
conf/cassandra.yaml
conf/cassandra-env.sh
conf/logback.xml
conf/jvm11-server.options
bin/cassandra.in.sh
build.xml
.build/parent-pom-template.xml
CHANGES.txt
https://issues.apache.org/jira/browse/CASSANDRA-13521 (cited from CHANGES.txt, not fetched)
https://issues.apache.org/jira/browse/CASSANDRA-14096 (cited from conf/cassandra.yaml, not fetched)

## D. Stage-4 feedback

none yet
