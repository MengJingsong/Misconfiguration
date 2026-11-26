# DROP_OVERSIZED_READ_REPAIR_MUTATIONS (`-Dcassandra.drop_oversized_readrepair_mutations`) — verification solution  <!-- file: cases/DROP_OVERSIZED_READ_REPAIR_MUTATIONS-createRepairMutation-SHOULD_DROP_OVERSIZED_READ_REPAIR_MUTATIONS--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the if statement on the entry's value, **linked**: [`BlockingReadRepairs.java:68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/repair/BlockingReadRepairs.java#L68) (`if (SHOULD_DROP_OVERSIZED_READ_REPAIR_MUTATIONS)`; closest place to a restriction, see "Config-first: places found") |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code (stage-3 autonomous subagent; CLI version not exposed to the agent), 2026-11-26 |
| Estimate | `negative`. The property only chooses what happens **after** a read-repair mutation has already been built and found larger than `max_mutation_size`: drop it quietly (true) or log a WARN and fail the read with `ReadTimeoutException` (false). The oversized mutation is discarded in both branches, so the entry decides no quantity of memory or disk. |
| Ground | The cap on the repair mutation's size is `max_mutation_size` (`Mutation.java:172`), a different entry, and it binds identically for both values of this property. The Mutation and its PartitionUpdate are allocated before the check (`BlockingReadRepairs.java:55`, `RowIteratorMergeListener.java:389`), so heap is spent either way; the stale replica receives no data for the oversized partition either way, so its disk is unchanged either way. The only side effects of the switch are a log level (WARN vs DEBUG, both in rolling logs capped by `conf/logback.xml`) and, with `true`, that smaller repairs to *other* replicas in the same partition are still sent, which is more disk written, not less. |

## Config-first: places found

Every place the value of `cassandra.drop_oversized_readrepair_mutations` flows to, in the pinned tree
(found by `grep -rn "DROP_OVERSIZED_READ_REPAIR_MUTATIONS\|drop_oversized_readrepair" src test`; only one reader exists):

1. [`CassandraRelevantProperties.java:209`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L209) — declaration, key `cassandra.drop_oversized_readrepair_mutations`, one-argument constructor so the default is `null` (`CassandraRelevantProperties.java:651-655`); `getBoolean()` parses `null` with `Boolean::parseBoolean` → `false` (`:751-756`, `:971`). Restricts nothing.
2. `BlockingReadRepairs.java:43` — read once into `private static final boolean SHOULD_DROP_OVERSIZED_READ_REPAIR_MUTATIONS` at class initialisation (so changing it needs a JVM restart). Restricts nothing.
3. [`BlockingReadRepairs.java:68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/repair/BlockingReadRepairs.java#L68) — inside the `catch (MutationExceededMaxSizeException)` of `createRepairMutation`: `true` → DEBUG log, `return null`; `false` → WARN log, then throw `ReadTimeoutException` unless `suppressException`, else `return null` (`:77-93`). In every branch the oversized mutation is not returned. Restricts no memory or disk; **chosen as Entry pointer** (closest place).
4. `RowIteratorMergeListener.java:391` (caller, `suppressException=false`, the normal blocking read-repair path) — `true`: the oversized replica is skipped (`:392-393`) and the loop continues, so repairs for other replicas of the same partition are still sent via `readRepair.repairPartition` (`:397`); `false`: the exception escapes `close()` before `:397`, so **no** repair of that partition reaches any replica and the client read fails. Restricts no memory or disk; with `true` more repair data can be written to other replicas.
5. `BlockingPartitionRepair.java:225` (caller, `suppressException=true`, speculative additional writes in `maybeSendAdditionalWrites`) — the flag only selects DEBUG vs WARN for the log line; the method treats `null` the same way (`:228-233`). Restricts nothing.

The size limit actually enforced on this path is `max_mutation_size` (`Mutation.java:169-177`, `IMutation.java:31`, `DatabaseDescriptor.java:898-901`, `:2827-2830`), a separate yaml entry, not this property.

Places that restrict memory or disk: **none**. One case file is written (addendum rule 3).

## A. Constraint trace

**A1. The constraint.** `DROP_OVERSIZED_READ_REPAIR_MUTATIONS`, a JVM system property, key
`cassandra.drop_oversized_readrepair_mutations`, declared at
[`CassandraRelevantProperties.java:209`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L209).
Unit: boolean. Default: no default string (`CassandraRelevantProperties.java:651-655`), so `getBoolean()` returns
`Boolean.parseBoolean(null)` = `false` (`:751-756`, `:971`). Set only by `-Dcassandra.drop_oversized_readrepair_mutations=true`
on the JVM command line (e.g. via `JVM_EXTRA_OPTS`, appended at `conf/cassandra-env.sh:307`, or a line in `conf/jvm-server.options`).
No yaml key, no JMX, no nodetool. It is copied into a `static final` field at class load (`BlockingReadRepairs.java:43`), so a
change needs a restart. It matters on the **coordinator** of a read (where `createRepairMutation` runs).

**A2. What it caps.** Nothing. It is a policy switch for an oversized read-repair mutation, not a limit. The quantity
compared against a limit on this path is the mutation's serialized size, `Mutation.serializedSize(version)` (`Mutation.java:171`),
against `MAX_MUTATION_SIZE` = `max_mutation_size` in bytes (`IMutation.java:31`, `DatabaseDescriptor.java:2827-2830`; default
`commitlog_segment_size / 2` = 16 MiB with the shipped 32 MiB segment, `DatabaseDescriptor.java:898-899`, `conf/cassandra.yaml:660`).
The resources one might expect it to touch: coordinator heap (the repair mutation) and the stale replica's disk
(memtable → commit log → SSTables when the repair is applied). The property bounds neither.

**A3. Mechanism.**
1. A read at CL > ONE finds a digest mismatch; `AbstractReadRepair.startRepair` marks `ReadRepair.RepairedBlocking`
   (`AbstractReadRepair.java:126-128`) and re-reads full data; the merged result goes through `RowIteratorMergeListener`.
2. `RowIteratorMergeListener.close()` builds a `PartitionUpdate` per stale replica (`RowIteratorMergeListener.java:383-389`)
   and calls `BlockingReadRepairs.createRepairMutation(update, CL, endpoint, false)` (`:391`).
3. `createRepairMutation` allocates `new Mutation(update)` (`BlockingReadRepairs.java:55`) and calls
   `mutation.validateSize(messagingVersion, 0)` (`:60`). `validateSize` compares `serializedSize(version)` with
   `MAX_MUTATION_SIZE`; on excess it marks the `CommitLog.OverSizedMutations` meter and throws
   `MutationExceededMaxSizeException` (`Mutation.java:169-177`). Under the limit, the mutation is returned (`:61`),
   collected (`RowIteratorMergeListener.java:395`) and sent (`BlockingReadRepair.java:112-117`,
   `BlockingPartitionRepair.java:145-162`) — this is where the stale replica's disk grows.
4. Over the limit, the if statement
   [`BlockingReadRepairs.java:68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/repair/BlockingReadRepairs.java#L68)
   runs:
   - **true**: DEBUG log (`:70-75`), `return null` (`:93`). The caller skips this replica (`RowIteratorMergeListener.java:392-393`),
     sends the remaining (under-limit) repairs, and the client read succeeds with the merged data. The stale replica stays stale.
   - **false (default)**: WARN log (`:79-84`); with `suppressException=false` throws `ReadTimeoutException`
     (`:86-91`), which leaves `close()` before `repairPartition` (`RowIteratorMergeListener.java:397`): no repair for this
     partition is sent to any replica and the client read fails. With `suppressException=true` (speculative path,
     `BlockingPartitionRepair.java:225`) it returns `null` (`:93`).
5. Outcome at the limit, both values: the oversized mutation is never sent; its heap was already allocated in steps 2-3 and becomes
   garbage after the call. **No path bypasses or overshoots the size check because of this property**; the property only changes
   what is reported and whether sibling repairs go out.

**A4. Other consumers.** Coordinator heap for the read (the merged partition, per-replica `PartitionUpdate`s built at
`RowIteratorMergeListener.java:389`) is bounded by paging and read thresholds, not by this property. The stale replica's disk is
also filled by hinted handoff (`hinted_handoff_enabled`), `nodetool repair` and normal writes. The log lines go to
`system.log`/`debug.log`, rolled at 50 MB and capped at 5 GB total each (`conf/logback.xml:39-41`, `:56-58`). The size cap itself
(`max_mutation_size`) also guards normal writes, batches and hints.

**A5. Evidence beyond the source.** `CHANGES.txt:2258` (3.11.2 section): "Add flag to allow dropping oversized read repair
mutations (CASSANDRA-13975)", https://issues.apache.org/jira/browse/CASSANDRA-13975 (cited by key, not fetched).
`doc/modules/cassandra/pages/architecture/storage-engine.adoc:37-41` (default and constraint of `max_mutation_size`).
`test/distributed/org/apache/cassandra/distributed/test/OversizedMutationTest.java` (shows `max_mutation_size` can be set to
48 KiB in a test and rejects larger writes; there is no test of this property in the tree).

## B. Verification solution

**B1. Claim under test.** Usage does **not** follow `cassandra.drop_oversized_readrepair_mutations`: with the same
stale-replica workload, the stale replica's on-disk live size after read repair, and the bytes the coordinator retains for
oversized repair mutations, are the same (within the stated tolerances) for property unset, `false` and `true`; only the client
outcome (ReadTimeout vs success) and the log level change. The positive control — raising `max_mutation_size` above the
partition size — moves the same readings by the size of the oversized data, showing the workload can move usage where a cap binds.

### B2. Unit tier

Drive `BlockingReadRepairs.createRepairMutation` directly in a CQLTester JVM, one JVM per property value (the field is
`static final`), and measure per call: outcome, bytes retained (serialized size of a returned Mutation) and bytes allocated by the
calling thread.

**B2a. Environment and build.** Linux, JDK 11 (`java -version` 11.x), Apache Ant ≥ 1.10, network to Maven Central for the first
build (or a pre-filled `~/.m2`). Work on local disk only:
```
export WORK=/mydata/rrflag          # any local disk with >= 5 GiB free; check: df -h "$WORK"
mkdir -p "$WORK" && export SRC=$WORK/src
rsync -a <pinned cassandra-5.0.9 source copy>/ "$SRC"/      # never build in the shared tree
cd "$SRC" && ant jar
```
Test source location: `$SRC/test/unit/org/apache/cassandra/service/reads/repair/` (four files below). The ant `testsome`
target forks one JVM per class with `-ea`, the jamm agent and 1024 MB heap (`build.xml:1153`, `:1382-1391`); test config is
`$SRC/test/conf/cassandra.yaml` (`commitlog_segment_size: 5MiB`, no `max_mutation_size` → limit 2,621,440 B).

File `AbstractOversizedReadRepairFlagTest.java`:
```java
package org.apache.cassandra.service.reads.repair;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;

import org.junit.Test;

import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.db.IMutation;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.commitlog.CommitLog;
import org.apache.cassandra.db.partitions.PartitionUpdate;
import org.apache.cassandra.exceptions.ReadTimeoutException;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.schema.TableMetadata;

public abstract class AbstractOversizedReadRepairFlagTest extends CQLTester
{
    static final int[] SIZES = { 64 << 10, 1 << 20, 2 << 20, 3 << 20, 6 << 20 };
    abstract String label();

    @Test
    public void probe() throws Throwable
    {
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob) WITH compression = {'enabled': false}");
        TableMetadata md = currentTableMetadata();
        Field f = BlockingReadRepairs.class.getDeclaredField("SHOULD_DROP_OVERSIZED_READ_REPAIR_MUTATIONS");
        f.setAccessible(true);
        boolean flag = f.getBoolean(null);
        System.out.println("RRPROBE-HDR label=" + label() + " flag=" + flag + " max=" + IMutation.MAX_MUTATION_SIZE
                           + " sysprop=" + System.getProperty("cassandra.drop_oversized_readrepair_mutations"));
        InetAddressAndPort dest = InetAddressAndPort.getByName("127.0.0.2");
        com.sun.management.ThreadMXBean tmx = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        long tid = Thread.currentThread().getId();
        long meter0 = CommitLog.instance.metrics.oversizedMutations.getCount();
        System.out.println("RRPROBE,label,flag,size,suppress,rep,updSer,outcome,retained,allocated");
        for (int size : SIZES)
            for (boolean suppress : new boolean[]{ false, true })
                for (int rep = 0; rep < 5; rep++)
                {
                    PartitionUpdate upd = new RowUpdateBuilder(md, 1L, rep).add("v", ByteBuffer.wrap(new byte[size])).buildUpdate();
                    long updSer = PartitionUpdate.serializer.serializedSize(upd, MessagingService.current_version);
                    String outcome; long retained = 0;
                    long a0 = tmx.getThreadAllocatedBytes(tid);
                    try
                    {
                        Mutation m = BlockingReadRepairs.createRepairMutation(upd, ConsistencyLevel.ONE, dest, suppress);
                        outcome = m == null ? "null" : "mutation";
                        if (m != null) retained = m.serializedSize(MessagingService.current_version);
                    }
                    catch (ReadTimeoutException e) { outcome = "ReadTimeoutException"; }
                    long a1 = tmx.getThreadAllocatedBytes(tid);
                    System.out.printf("RRPROBE,%s,%b,%d,%b,%d,%d,%s,%d,%d%n", label(), flag, size, suppress, rep, updSer, outcome, retained, a1 - a0);
                }
        System.out.println("RRPROBE-METER label=" + label() + " oversizedDelta=" + (CommitLog.instance.metrics.oversizedMutations.getCount() - meter0));
    }
}
```
Three concrete classes, each setting the property in its own static initialiser (runs before `BlockingReadRepairs` is loaded;
the reflective read of the field in `RRPROBE-HDR` confirms it):
```java
// OversizedReadRepairFlagUnsetTest.java
package org.apache.cassandra.service.reads.repair;
public class OversizedReadRepairFlagUnsetTest extends AbstractOversizedReadRepairFlagTest
{ static { System.clearProperty("cassandra.drop_oversized_readrepair_mutations"); } String label() { return "unset"; } }

// OversizedReadRepairFlagFalseTest.java
package org.apache.cassandra.service.reads.repair;
public class OversizedReadRepairFlagFalseTest extends AbstractOversizedReadRepairFlagTest
{ static { System.setProperty("cassandra.drop_oversized_readrepair_mutations", "false"); } String label() { return "false"; } }

// OversizedReadRepairFlagTrueTest.java
package org.apache.cassandra.service.reads.repair;
public class OversizedReadRepairFlagTrueTest extends AbstractOversizedReadRepairFlagTest
{ static { System.setProperty("cassandra.drop_oversized_readrepair_mutations", "true"); } String label() { return "true"; } }
```

**B2b. Knobs.**
- The property: unset, `false`, `true` (all three values the code can see; unset and `false` must behave the same).
- Positive-control knob: `max_mutation_size` in `$SRC/test/conf/cassandra.yaml`: default (2,621,440 B) for the main runs; `8MiB`
  (with `commitlog_segment_size: 16MiB`, required ≥ 2× by `DatabaseDescriptor.java:900-901`) for control run U-C, so that the
  3 MiB and 6 MiB updates are no longer oversized.

**B2c. Workload.** One single-row PartitionUpdate per call with a blob of 64 KiB, 1 MiB, 2 MiB (all under 2,621,440 B, overhead
is tens of bytes) and 3 MiB, 6 MiB (1.2× and 2.4× the limit); each with `suppressException` false and true; 5 repetitions
(rep 0 is warm-up: class loading of the exception path is charged to it). 50 calls per JVM.

**B2d. Observables and instruments.** Per call (CSV lines `RRPROBE,` in the JUnit XML system-out):
`outcome` (mutation / null / ReadTimeoutException), `retained` (serialized bytes of the returned Mutation, 0 if none — what the
caller would keep and send), `allocated` (bytes allocated by the calling thread during the call,
`com.sun.management.ThreadMXBean.getThreadAllocatedBytes`; the update's own buffer is allocated before `a0` and excluded).
Per JVM: the field value and `MAX_MUTATION_SIZE` (`RRPROBE-HDR`), the `OverSizedMutations` meter delta (`RRPROBE-METER`).
Not observable: retained heap of objects other than the return value (the call has no other output; the Mutation built at
`BlockingReadRepairs.java:55` becomes unreachable when `null` is returned or the exception is thrown).

**B2e. Procedure.**
```
cd "$SRC"
# put the four .java files in test/unit/org/apache/cassandra/service/reads/repair/
for c in Unset False True; do
  ant testsome -Dtest.name=org.apache.cassandra.service.reads.repair.OversizedReadRepairFlag${c}Test
done
grep -h 'RRPROBE' build/test/output/TEST-org.apache.cassandra.service.reads.repair.OversizedReadRepairFlag*Test.xml > "$WORK/unit-main.csv"
# positive control U-C: raise the cap, rerun the default-value class only
cp test/conf/cassandra.yaml "$WORK/test-cassandra.yaml.orig"
sed -i 's/^commitlog_segment_size: 5MiB/commitlog_segment_size: 16MiB/' test/conf/cassandra.yaml
echo 'max_mutation_size: 8MiB' >> test/conf/cassandra.yaml
grep -nE '^(commitlog_segment_size|max_mutation_size)' test/conf/cassandra.yaml
ant testsome -Dno-build-test=true -Dtest.name=org.apache.cassandra.service.reads.repair.OversizedReadRepairFlagUnsetTest
grep -h 'RRPROBE' build/test/output/TEST-org.apache.cassandra.service.reads.repair.OversizedReadRepairFlagUnsetTest.xml > "$WORK/unit-control.csv"
cp "$WORK/test-cassandra.yaml.orig" test/conf/cassandra.yaml
```
Summarise: for each (label, size, suppress), the outcome of reps 1-4 (must agree), median `retained`, median `allocated`.

**B2f. Predictions** (main runs: `max` = 2,621,440 in every `RRPROBE-HDR`; `flag` = false, false, true for unset/false/true).

| size | suppress | unset / false: outcome, retained | true: outcome, retained |
|---|---|---|---|
| 64 KiB, 1 MiB, 2 MiB | false, true | `mutation`, retained = updSer ≈ size + < 100 B | `mutation`, same retained |
| 3 MiB, 6 MiB | false | `ReadTimeoutException`, 0 | `null`, 0 |
| 3 MiB, 6 MiB | true | `null`, 0 | `null`, 0 |

- `allocated` (median of reps 1-4) for the same (size, suppress): |true − unset| < 64 KiB, and it does not grow with size:
  allocated(6 MiB) − allocated(3 MiB) < 64 KiB in every JVM (i.e. < 2% of the 3 MiB size step).
- `oversizedDelta` = 20 (2 sizes × 2 suppress × 5 reps) in all three JVMs.
- Control U-C (`max` = 8,388,608): all 50 calls `mutation`, retained ≈ size for every size including 3 MiB and 6 MiB; `oversizedDelta` = 0.
- The claim is wrong if, for oversized updates, `true` returns a non-null Mutation or `retained` > 0, or if `allocated` differs
  between values by an amount that scales with size (≥ 1% of size), or if unset and `false` differ.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Oversized: retained 0 for all values; allocated within 64 KiB across values and flat in size; under-limit retained ≈ size; U-C retained ≈ size at 3/6 MiB | Claim confirmed: the cap that decides retained bytes is `max_mutation_size`; the property moves no bytes |
| `true` returns a Mutation (retained > 0) for an oversized update, or retained/allocated differ across values by ≥ 1% of size | Claim refuted: usage follows the property |
| Only the outcome column differs (exception vs null) | Expected: behaviour switch, not a usage cap |
| Usage flat across property values, but U-C also shows 0 retained at 3/6 MiB | Not confirmed: the control did not move, the workload cannot show usage moving; check that the edited yaml was loaded (`max` in `RRPROBE-HDR`) |
| `oversizedDelta` = 0 or `max` ≠ 2,621,440 in a main run | Not confirmed: the limit was never reached; fix the config and rerun |
| `flag` in `RRPROBE-HDR` does not match the label | Invalid run (class loaded before the property was set); rerun |

**B2h. Controls.** Reflective read of the static field (proves the JVM saw the intended value). Unset and `false` as two
independent JVMs (must match). Under-limit sizes in the same JVM (show retained follows size when no cap binds). U-C (raises the
binding cap; same code, same sizes). Rep 0 discarded (class-loading noise). The update buffer is allocated outside the measured
window.

### B3. Cluster tier

Two Cassandra instances on one Linux host (127.0.0.1 and 127.0.0.2; two hosts work the same with their own IPs), RF=2,
hinted handoff off. Make node 2 miss data, then read at CL=ALL through node 1 so node 1 coordinates read repair toward node 2.
Measure node 2's on-disk live size gained from read repair.

**B3a. Environment and build.** As B2a (`$SRC` built with `ant jar`), plus Python 3.8–3.11 (the bundled driver
`lib/cassandra-driver-internal-only-3.29.0.zip` uses asyncore; on 3.12+ use a venv with `pip install cassandra-driver==3.29.0 pyasyncore`
and drop the zip path in the script). Make each node a copy of the built tree (data, commit log and hints then default to
`$WORK/nX/data/...` via `cassandra_storagedir`, `bin/cassandra.in.sh:48`):
```
mknode() { n=$1; ip=$2; jmx=$3; mm=$4
  rm -rf "$WORK/$n"; rsync -a --exclude build/test "$SRC"/ "$WORK/$n"/
  y=$WORK/$n/conf/cassandra.yaml
  sed -i -e "s/^listen_address: localhost/listen_address: $ip/" \
         -e "s/^rpc_address: localhost/rpc_address: $ip/" \
         -e "s/^hinted_handoff_enabled: true/hinted_handoff_enabled: false/" \
         -e "s/^auto_snapshot: true/auto_snapshot: false/" "$y"
  echo "max_mutation_size: $mm" >> "$y"            # not set elsewhere in the shipped yaml
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jmx\"/" "$WORK/$n/conf/cassandra-env.sh"
  grep -nE '^(listen_address|rpc_address|hinted_handoff_enabled|auto_snapshot|max_mutation_size|commitlog_segment_size)|seeds:' "$y"
  grep -n '^JMX_PORT=' "$WORK/$n/conf/cassandra-env.sh"; }
start() { n=$1; ( export MAX_HEAP_SIZE=1G JVM_EXTRA_OPTS="$2"; "$WORK/$n/bin/cassandra" -p "$WORK/$n.pid" > "$WORK/$n.out" 2>&1 ); }
nt1() { "$WORK/n1/bin/nodetool" -p 7199 "$@"; }
nt2() { "$WORK/n1/bin/nodetool" -p 7299 "$@"; }
waitun() { until nt1 status 2>/dev/null | grep -q "^UN  $1 "; do sleep 5; done; }
meters() { for b in 'type=CommitLog,name=OverSizedMutations' 'type=ReadRepair,name=RepairedBlocking' \
                   'type=Table,keyspace=rr,scope=t,name=ReadRepairRequests'; do
             echo "$b $(nt1 sjk mx -mg -b "org.apache.cassandra.metrics:$b" -f Count | tail -1)"; done; }
stopnode() { kill "$(cat "$WORK/$1.pid")"; while kill -0 "$(cat "$WORK/$1.pid")" 2>/dev/null; do sleep 2; done; }
```
Seeds stay `"127.0.0.1:7000"` (shipped). Heap 1 GiB per node, G1 (shipped `jvm11-server.options`).

Workload script `$WORK/workload.py` (outside the node trees):
```python
#!/usr/bin/env python3
import sys, os, glob, csv
home = os.environ['CASS_HOME']
z = glob.glob(os.path.join(home, 'lib', 'cassandra-driver-internal-only-*.zip'))[0]
sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + os.path.basename(z)[len('cassandra-driver-internal-only-'):-4]))
from cassandra import ConsistencyLevel, ReadTimeout
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import WhiteListRoundRobinPolicy
BIG, BIG_ROWS = range(1, 201), 25          # 200 partitions x 25 rows x 16 KiB = 400 KiB each
SMALL, SMALL_ROWS = range(1001, 1201), 4   # 200 partitions x  4 rows x 16 KiB =  64 KiB each
ROW = 16384
prof = ExecutionProfile(load_balancing_policy=WhiteListRoundRobinPolicy(['127.0.0.1']), request_timeout=60)
c = Cluster(['127.0.0.1'], execution_profiles={EXEC_PROFILE_DEFAULT: prof}, protocol_version=5)
s = c.connect(); s.default_fetch_size = 1000   # whole partition in one page
mode = sys.argv[1]
if mode == 'schema':
    s.execute("CREATE KEYSPACE rr WITH replication = {'class':'SimpleStrategy','replication_factor':2}")
    s.execute("CREATE TABLE rr.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {'enabled': false} "
              "AND read_repair = 'BLOCKING' AND speculative_retry = 'NONE'")
elif mode == 'load':
    ins = s.prepare("INSERT INTO rr.t (pk, ck, v) VALUES (?, ?, ?)"); ins.consistency_level = ConsistencyLevel.ONE
    for pks, rows in ((BIG, BIG_ROWS), (SMALL, SMALL_ROWS)):
        for pk in pks:
            for ck in range(rows):
                s.execute(ins, (pk, ck, os.urandom(ROW)))
elif mode == 'read':
    sel = s.prepare("SELECT pk, ck, v FROM rr.t WHERE pk = ?"); sel.consistency_level = ConsistencyLevel.ALL
    with open(sys.argv[2], 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['pk', 'kind', 'outcome', 'rows', 'bytes'])
        for kind, pks in (('big', BIG), ('small', SMALL)):
            for pk in pks:
                try:
                    rs = list(s.execute(sel, (pk,)))
                    w.writerow([pk, kind, 'ok', len(rs), sum(len(r.v) for r in rs)])
                except ReadTimeout:
                    w.writerow([pk, kind, 'ReadTimeout', 0, 0])
                except Exception as e:
                    w.writerow([pk, kind, type(e).__name__, 0, 0])
c.shutdown()
```

**B3b. Knobs.** Four runs, each from fresh node copies:

| Run | `-Dcassandra.drop_oversized_readrepair_mutations` (both nodes) | `max_mutation_size` (both nodes) | Role |
|---|---|---|---|
| A | unset (default false) | 128KiB | property at default, cap binds for big partitions |
| B | `=true` | 128KiB | property flipped, cap binds |
| C | unset | 1MiB | **positive control**: cap lifted above the 400 KiB partition |
| D | `=true` | 1MiB | property flipped where the cap does not bind (optional, should equal C) |

128 KiB is 3.1× below a big partition's repair mutation (≥ 409,600 B of values) and 2× above a small one (65,536 B + < 1 KiB);
1 MiB is 2.5× above a big one. `commitlog_segment_size` stays 32MiB (≥ 2 × 1 MiB, `DatabaseDescriptor.java:900-901`).
The property is set with `JVM_EXTRA_OPTS` and checked in the `JVM Arguments:` line of `system.log` (`CassandraDaemon.java:619`).

**B3c. Workload.** Node 2 is stopped while node 1 takes 200 big partitions (81,920,000 B of values, 78.1 MiB) and 200 small
partitions (13,107,200 B, 12.5 MiB) at CL=ONE, uncompressed random bytes, no hints. Node 2 is restarted, then every partition is
read once at CL=ALL through node 1 (pass 1), and again (pass 2). Every read mismatches on pass 1 (node 2 has nothing), so node 1
builds one repair mutation per partition for node 2: 200 of ~400 KiB (oversized in A/B) and 200 of ~64 KiB (never oversized).
Pass 2 shows whether anything was repaired. Duration: load ~2-5 min, each read pass ~1-2 min.

**B3d. Observables and instruments.**
- Primary: node 2 table live size, `nt2 tablestats rr.t | grep 'Space used (live)'` (bytes) after `nt2 flush rr t`; cross-check
  `du -sb $WORK/n2/data/data/rr`. Readings: S2_0 (before pass 1), S2_1 (after pass 1), S2_2 (after pass 2). ΔS2 = S2_1 − S2_0.
- Same for node 1 (S1, should not change).
- Client outcome per read: `read1.csv`, `read2.csv` (counts of ok / ReadTimeout per kind; returned bytes per ok read).
- Coordinator meters on node 1, before/after each pass:
  `nt1 sjk mx -mg -b 'org.apache.cassandra.metrics:type=CommitLog,name=OverSizedMutations' -f Count`,
  `nt1 sjk mx -mg -b 'org.apache.cassandra.metrics:type=ReadRepair,name=RepairedBlocking' -f Count`,
  `nt1 sjk mx -mg -b 'org.apache.cassandra.metrics:type=Table,keyspace=rr,scope=t,name=ReadRepairRequests' -f Count`.
- Log lines on node 1: `grep -c 'Encountered an oversized' $WORK/n1/logs/system.log` (WARN only) and `.../debug.log` (WARN + DEBUG).
- Not observable directly: coordinator heap per repair mutation (short-lived garbage; covered by the unit tier's `allocated`).

**B3e. Procedure** (one run; set `FLAG` to `""` or `"-Dcassandra.drop_oversized_readrepair_mutations=true"` and `MM` to `128KiB`/`1MiB`):
```
export CASS_HOME=$WORK/n1; R=A; FLAG=""; MM=128KiB          # B: FLAG="-D...=true"; C: MM=1MiB; D: both
mknode n1 127.0.0.1 7199 $MM; mknode n2 127.0.0.2 7299 $MM
start n1 "$FLAG"; waitun 127.0.0.1; start n2 "$FLAG"; waitun 127.0.0.2
grep 'JVM Arguments' $WORK/n1/logs/system.log | grep -o 'drop_oversized[^,]*'   # must show =true for B/D, nothing for A/C
python3 $WORK/workload.py schema
nt2 drain; stopnode n2; until nt1 status | grep -q '^DN  127.0.0.2 '; do sleep 5; done
python3 $WORK/workload.py load
nt1 flush rr t; nt1 tablestats rr.t | grep 'Space used (live)'          # S1 ~ 94-96 MB
ls $WORK/n1/data/hints | wc -l                                          # must be 0 (hints off)
start n2 "$FLAG"; waitun 127.0.0.2
nt2 flush rr t; nt2 tablestats rr.t | grep 'Space used (live)'          # S2_0
meters > $WORK/$R-meters0.txt                                          # three coordinator meters on n1 (B3d)
python3 $WORK/workload.py read $WORK/$R-read1.csv
nt2 flush rr t; nt2 tablestats rr.t | grep 'Space used (live)'; du -sb $WORK/n2/data/data/rr   # S2_1
meters > $WORK/$R-meters1.txt
python3 $WORK/workload.py read $WORK/$R-read2.csv
nt2 flush rr t; nt2 tablestats rr.t | grep 'Space used (live)'          # S2_2
meters > $WORK/$R-meters2.txt
grep -c 'Encountered an oversized' $WORK/n1/logs/system.log $WORK/n1/logs/debug.log
awk -F, 'NR>1{c[$2","$3]++} END{for(k in c) print k, c[k]}' $WORK/$R-read1.csv $WORK/$R-read2.csv
nt2 stopdaemon || stopnode n2; nt1 stopdaemon || stopnode n1
pgrep -u "$USER" -f 'org.apache.cassandra.service.CassandraDaemon' && echo LEFTOVER   # must print nothing
mkdir -p $WORK/results/$R && cp $WORK/$R-read*.csv $WORK/$R-meters*.txt $WORK/n1/logs/system.log $WORK/results/$R/
```
Repeat for B, C, D. Between runs `mknode` wipes the node copies.

**B3f. Predictions.** Let SMALL = 13.1 MB of values, BIG = 81.9 MB of values; SSTable overhead for 16 KiB cells is a few %.

| Run | ΔS2 after pass 1 | S2_2 − S2_1 | pass 1 big reads | pass 1 small reads | OverSizedMutations Δ (pass 1) | ReadRepairRequests Δ (pass 1) | WARN lines |
|---|---|---|---|---|---|---|---|
| A | 13.1–14.5 MB (small only) | < 1 MB | 200 ReadTimeout | 200 ok | 200 | 200 | 200 |
| B | same as A, \|ΔS2_B − ΔS2_A\| < 1 MB | < 1 MB | 200 ok, 409,600 B each | 200 ok | 200 | 200 | 0 (200 DEBUG in debug.log) |
| C (control) | 95.0–100 MB (small + big) | < 1 MB | 200 ok | 200 ok | 0 | 400 | 0 |
| D | same as C, \|ΔS2_D − ΔS2_C\| < 1 MB | < 1 MB | 200 ok | 200 ok | 0 | 400 | 0 |

Pass 2 in A repeats 200 ReadTimeout and in B 200 more oversized drops (node 2 still stale); in C/D pass 2 has no mismatches
(RepairedBlocking Δ ≈ 0). S1 is unchanged by reads in all runs. The claim is wrong if ΔS2_B − ΔS2_A ≥ 10 MB (i.e. node 2 gains a
noticeable part of BIG when the property is `true`), or if ΔS2 differs between A and B by more than the 1 MB tolerance in either
direction in a way that repeats across a rerun.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| ΔS2_A ≈ ΔS2_B ≈ SMALL, ΔS2_C ≈ ΔS2_D ≈ SMALL + BIG | **Claim confirmed**: usage flat across the property while the positive control (cap lifted) moves it by BIG; `max_mutation_size` is the binding cap |
| ΔS2_B ≥ SMALL + 10 MB (node 2 gains big-partition data with `true`) | Claim refuted: usage follows the property |
| ΔS2_B < ΔS2_A by ≥ 1 MB, repeatable | Claim refuted in the opposite direction (property changes disk); inspect which repairs were not sent |
| A and B flat, but ΔS2_C ≈ SMALL too | Not confirmed: the control did not move (repair path not exercised, e.g. hints or a prior repair made node 2 consistent, or `max_mutation_size` not loaded); check S2_0 ≈ 0 and the yaml |
| OverSizedMutations Δ = 0 in A/B | Not confirmed: the limit was never reached (check `max_mutation_size` and that node 1 coordinated) |
| ΔS2 ≈ 0 in all runs including small | Invalid: read repair did not run (check CL=ALL, `read_repair='BLOCKING'`, node 2 UN) |
| A shows ok big reads / B shows ReadTimeout | Property not applied as intended (check `JVM Arguments` line); rerun |

**B3h. Controls.** Small partitions in every run (an under-limit repair that must land identically in all runs: proves the
repair path works and gives the per-run scale). Run C/D (same workload, cap lifted: proves the workload moves disk where the cap
binds). Pass 2 (proves nothing was repaired late, e.g. by hints). Hints off and `ls hints` = 0, S2_0 ≈ 0 (node 2 really stale).
Coordinator pinned to node 1 by `WhiteListRoundRobinPolicy`. Uncompressed random payload (sizes are not shrunk by compression).
`JVM Arguments` log line (property really set). Unset and D vs C (property irrelevant when not oversized).

**B4. Risks and cleanup.** Disk: per run node 1 ≈ 96 MB data + ≤ 4 × 32 MiB commit log, node 2 ≤ 100 MB + commit log; node copies
≈ 2 × the built tree size; total < 3 GiB on `$WORK` (local disk; check `df -h $WORK` ≥ 5 GiB before starting). Nothing is
written to shared storage or the shared source tree (build and tests run in `$SRC` copy; the unit-tier yaml edit is restored
from `$WORK/test-cassandra.yaml.orig`). Processes: after each run `pgrep -u "$USER" -f CassandraDaemon` must be empty; kill
any leftover by its pid file (`kill $(cat $WORK/nX.pid)`); `ant testsome` JVMs exit by themselves (check
`pgrep -u "$USER" -f junit` empty). Ports 7000, 7199, 7299, 9042 on 127.0.0.1/127.0.0.2 must be free before starting
(`ss -ltnp`). Final cleanup: `rm -rf $WORK/n1 $WORK/n2` (keep `$WORK/results`, `unit-*.csv`).

## C. Sources read

- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (lines 200-215, 645-659, 751-780, 971)
- src/java/org/apache/cassandra/service/reads/repair/BlockingReadRepairs.java
- src/java/org/apache/cassandra/service/reads/repair/RowIteratorMergeListener.java (lines 360-400)
- src/java/org/apache/cassandra/service/reads/repair/BlockingPartitionRepair.java (lines 145-235)
- src/java/org/apache/cassandra/service/reads/repair/BlockingReadRepair.java (lines 60-118)
- src/java/org/apache/cassandra/service/reads/repair/AbstractReadRepair.java (lines 115-135)
- src/java/org/apache/cassandra/service/reads/repair/PartitionIteratorMergeListener.java (lines 45-100)
- src/java/org/apache/cassandra/service/reads/repair/ReadRepairStrategy.java
- src/java/org/apache/cassandra/db/Mutation.java (lines 160-185, 326)
- src/java/org/apache/cassandra/db/IMutation.java (lines 31, 49-56)
- src/java/org/apache/cassandra/db/MutationExceededMaxSizeException.java
- src/java/org/apache/cassandra/db/partitions/PartitionUpdate.java (line 770)
- src/java/org/apache/cassandra/db/commitlog/CommitLog.java (line 86)
- src/java/org/apache/cassandra/metrics/CommitLogMetrics.java (lines 48, 55)
- src/java/org/apache/cassandra/metrics/ReadRepairMetrics.java
- src/java/org/apache/cassandra/metrics/TableMetrics.java (lines 345, 834)
- src/java/org/apache/cassandra/net/EndpointMessagingVersions.java (lines 66-77)
- src/java/org/apache/cassandra/net/MessagingService.java (line 257)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 500, 898-901, 1470, 2827-2830)
- src/java/org/apache/cassandra/config/Config.java (lines 81-423, selected fields)
- src/java/org/apache/cassandra/service/CassandraDaemon.java (line 619)
- src/java/org/apache/cassandra/tools/nodetool/Sjk.java (existence)
- test/unit/org/apache/cassandra/db/RowUpdateBuilder.java
- test/unit/org/apache/cassandra/cql3/CQLTester.java (selected signatures)
- test/unit/org/apache/cassandra/service/reads/repair/ (listing)
- test/distributed/org/apache/cassandra/distributed/test/OversizedMutationTest.java
- test/anttasks/org/apache/cassandra/anttasks/TestNameCheckTask.java (naming rule)
- test/conf/cassandra.yaml, test/conf/logback-test.xml
- conf/cassandra.yaml, conf/cassandra-env.sh, conf/logback.xml
- bin/cassandra, bin/cassandra.in.sh, bin/cqlsh.py (driver path), pylib/cqlshlib/cqlshmain.py (default page size)
- lib/cassandra-driver-internal-only-3.29.0.zip (listing)
- build.xml (test targets, output dir)
- CHANGES.txt (line 2258), doc/modules/cassandra/pages/architecture/storage-engine.adoc (lines 37-41), doc/modules/cassandra/pages/managing/configuration/configuration.adoc (line 111)
- https://issues.apache.org/jira/browse/CASSANDRA-13975 (cited from CHANGES.txt, not fetched)

## D. Stage-4 feedback

none yet
