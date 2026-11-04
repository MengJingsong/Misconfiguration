# items_per_collection (guardrail) — verification solution  <!-- file: cases/items_per_collection-doAdd-elements_size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`Sets.java:393`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Sets.java#L393) (`elements.size() == 0`, the early return in `Sets.Adder.doAdd` just before `Guardrails.itemsPerCollection.guard(elements.size(), ...)` at `:399`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code at Meta (version string not available), 2026-10-26; stage-3 autonomous, Band D triage |
| Estimate | `undetermined`. The target check itself only skips empty additions; it adds no cells and so needs no cap. The constraint it gates, `items_per_collection_fail_threshold`, rejects a single ordinary-user write that adds more than T items to a set. That bounds the per-write cell count, but in items, not bytes. It counts only the written fragment, so repeated `s = s + {...}` appends grow the stored collection without bound. The sstable-write check only logs. Superusers and the default `AllowAllAuthenticator` are exempt. Whether it "caps memory or disk" depends on which quantity is meant: per write yes, per stored collection no |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** The `items_per_collection` guardrail. Its threshold pair is configuration entries:
- `items_per_collection_warn_threshold` and `items_per_collection_fail_threshold` are declared at [`Config.java:919-920`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L919-L920) (`volatile int`, default `-1`, which means disabled).
- Unit: item count, meaning elements and cells.
- Validated by `validateMaxIntThreshold` (`src/java/org/apache/cassandra/config/GuardrailsOptions.java:83, 669`).
- Set by the yaml keys (`conf/cassandra.yaml:2161-2169`, commented out by default), or at runtime through JMX `org.apache.cassandra.db:type=Guardrails` `setItemsPerCollectionThreshold(warn, fail)` ([`GuardrailsMBean.java:571-582`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/GuardrailsMBean.java#L571-L582); [`Guardrails.java:1000`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrails.java#L1000)). A runtime change needs no restart.
- The guardrail object is `Guardrails.itemsPerCollection` ([`Guardrails.java:380-387`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrails.java#L380-L387)), a `MaxThreshold`.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** The quantity compared is `elements.size()`, the number of
elements in the set literal or bound value *being written* (`Sets.java:389, 399`).
Each element becomes one cell added to the mutation and then to the memtable
(`Sets.java:401-409`), and later becomes part of an sstable on disk. Resource: the
heap of the mutation and memtable, and the disk used by the collection, bounded
only in item count per write. Bytes are a separate guardrail, `collection_size`
(`Sets.java:410`).

**A3. Mechanism.**
1. Entry points. `Sets.Setter.execute` ([`Sets.java:347-360`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Sets.java#L347-L360); handles `INSERT` or `SET s = {...}`) and `Sets.Adder.execute` (`:370-376`; handles `SET s = s + {...}`) both call `Adder.doAdd` (`:378`).
2. In `doAdd`, for a multi-cell (non-frozen) set:
   - The target `:393` returns at once if the added set is empty. No guard runs and no cell is added.
   - Otherwise `itemsPerCollection.guard(elements.size(), column, false, params.clientState)` runs at `:399`, before any cell is created at `:407`.
   - For a frozen set, the same guard runs at `:414` on the whole value.
3. `Threshold.guard` ([`Threshold.java:128-141`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Threshold.java#L128-L141)):
   - It returns without checking unless `enabled(state)` holds ([`Threshold.java:80-85`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Threshold.java#L80-L85)). `enabled` requires the daemon to be initialized and `state == null || state.isOrdinaryUser()` ([`Guardrail.java:93-96`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrail.java#L93-L96)), plus some threshold above 0.
   - `MaxThreshold.compare` is `value > threshold` ([`MaxThreshold.java:50-53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/MaxThreshold.java#L50-L53)). A fail value of 0 or less becomes `Long.MAX_VALUE` (`:56-60`).
   - When the fail threshold is exceeded, `Guardrail.fail` ([`Guardrail.java:124-141`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrail.java#L124-L141)) logs an error and throws `GuardrailViolatedException` because `state != null`, so the whole statement is rejected before any cell is applied. When only the warn threshold is exceeded, a client warning is sent and the write proceeds.
4. Bypasses and overshoot:
   - (a) `ClientState.isSuper()` is true whenever the authenticator does not require authentication ([`ClientState.java:602-605`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ClientState.java#L602-L605)). With the default `authenticator: AllowAllAuthenticator` (`conf/cassandra.yaml:198`), the guardrail never applies to client writes. It also never applies to superusers or internal writes.
   - (b) Only the fragment being written is counted (the comment at [`Sets.java:396-398`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Sets.java#L396-L398); `conf/cassandra.yaml:2163-2166`), so N appends of T items each produce a stored set of N·T items.
   - (c) At sstable write time, `SortedTableWriter.guardCollectionSize` ([`SortedTableWriter.java:393-428`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java#L393-L428), called at `:191, :210`) checks the live cell count, but with `state = null`, so `fail` only logs and does not throw ([`Guardrail.java:140-141`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrail.java#L140-L141)).

**A4. Other consumers.**
- The same guardrail at the list and map sites (`Lists.java:531,544`; `Maps.java:480,492`).
- `collection_size` (bytes).
- Element values are bounded by `max_value_size` and by the native-transport frame and message limits.
- Memtable heap is bounded overall by `memtable_heap_space`, which triggers flushes.
- None of these bound the total stored items of one non-frozen collection.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/db/guardrails/GuardrailItemsPerCollectionTest.java:64-113`. In particular, `testSetSizeWithUpdates` shows that appends are checked per fragment.
- The yaml comment at `conf/cassandra.yaml:2161-2169`.
- CASSANDRA-17153, which introduced the collection guardrails: https://issues.apache.org/jira/browse/CASSANDRA-17153.

## B. Verification solution

**B1. Claim under test.** For an ordinary (non-super) authenticated user with
`items_per_collection_fail_threshold = T`:
- (i) a single write adding more than T items to a set is rejected and adds no cells, memtable or disk usage, while a write of at most T items is accepted;
- (ii) repeated appends of at most T items each grow the stored set, its memtable heap and its sstable disk usage well past T items, and are never rejected;
- (iii) an empty addition (`:393`) adds nothing.

So the constraint caps per-write usage but not the stored collection.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Clone the tag to local disk:
`git clone --branch cassandra-5.0.9 --depth 1 <shared clone> /local/$USER/c509-ipc && cd /local/$USER/c509-ipc && ant build-test`.

> **Amendment B2a (2026-10-26, stage-4 audit, before any reading).** `/local` does not exist on the advisor's machine
> (`environment-advisor.md`). Use `source ~/Library/Caches/stage4/env.sh; git clone --branch cassandra-5.0.9 ~/cassandra-src
> $W/cassandra-run31 && cd $W/cassandra-run31 && ant -Dlocal.repository=$W/m2 build-test` (macOS, JDK 11, Ant 1.10.18).

**B2b. Knobs.** T, the fail threshold, set at runtime through
`Guardrails.instance.setItemsPerCollectionThreshold(warn, fail)`. Use `T = 100` (warn
50) and `T = 1000` (warn 500). Use `-1/-1` (disabled) as a reference.

> **Amendment B2b (2026-10-26, stage-4 audit, before any reading).** The `-1/-1` reference is the default
> (`Config.java:919-920`) and is the third knob value group A needs, but the probe as filed never runs it. The amended probe
> (B2c) runs it: after the two T passes, a fresh table, thresholds `-1/-1`, and the ordinary user's single write of 1001 items.

**B2c. Workload.** Create the file `test/unit/org/apache/cassandra/db/guardrails/ItemsPerCollectionProbeTest.java` in the local clone. It extends the tree's `GuardrailTester`, which logs in an ordinary user over the native protocol (`GuardrailTester.java:112-150`):

```java
package org.apache.cassandra.db.guardrails;

import java.util.*;
import org.junit.Test;

public class ItemsPerCollectionProbeTest extends GuardrailTester
{
    private static Set<Integer> range(int from, int to) { Set<Integer> s = new HashSet<>(); for (int i = from; i < to; i++) s.add(i); return s; }
    private long mem() { return getCurrentColumnFamilyStore().metric.memtableLiveDataSize.getValue(); }
    private int card(int k) throws Throwable { return executeNet("SELECT v FROM %s WHERE k = " + k).one().getSet("v", Integer.class).size(); }

    @Test
    public void probe() throws Throwable
    {
        for (int t : new int[]{ 100, 1000 })
        {
            createTable("CREATE TABLE %s (k int PRIMARY KEY, v set<int>)");
            Guardrails.instance.setItemsPerCollectionThreshold(t / 2, t);
            // (i) single write at T and T+1
            executeNet("INSERT INTO %s (k, v) VALUES (1, ?)", range(0, t));
            long m0 = mem(); String r;
            try { executeNet("INSERT INTO %s (k, v) VALUES (2, ?)", range(0, t + 1)); r = "accepted"; }
            catch (Exception e) { r = "rejected:" + e.getMessage(); }
            System.out.printf("PROBE t=%d single(T+1)=%s memDelta=%d%n", t, r, mem() - m0);
            // (iii) empty add
            m0 = mem(); executeNet("UPDATE %s SET v = v + {} WHERE k = 1");
            System.out.printf("PROBE t=%d emptyAdd memDelta=%d card=%d%n", t, mem() - m0, card(1));
            // (ii) 50 appends of T items each
            executeNet("INSERT INTO %s (k, v) VALUES (3, {})");
            for (int j = 0; j < 50; j++)
            {
                executeNet("UPDATE %s SET v = v + ? WHERE k = 3", range(j * t, (j + 1) * t));
                if (j % 10 == 9) System.out.printf("PROBE t=%d appends=%d card=%d mem=%d%n", t, j + 1, card(3), mem());
            }
            // superuser control: same over-threshold single write
            useSuperUser();
            executeNet("INSERT INTO %s (k, v) VALUES (4, ?)", range(0, t + 1));
            System.out.printf("PROBE t=%d superuser(T+1) card=%d%n", t, card(4));
            useUser(USERNAME, PASSWORD);
        }
        Guardrails.instance.setItemsPerCollectionThreshold(-1, -1);
    }
}
```

Arithmetic: with T = 100, the single write of 101 items is 1 past T. The 50 appends
reach 5,000 items, which is 50·T. With T = 1000, the appends reach 50,000 items. Each int
cell is about tens of bytes in the memtable, so the 50,000-item set adds on the order
of a megabyte of memtable data, which `memtableLiveDataSize` can see.

> **Amendment B2c (2026-10-26, stage-4 audit, before any reading).** The probe as filed does not compile and logs badly; the
> run uses `stage4-runtime-verification/harness/items_per_collection-doAdd-elements_size--autonomous/ItemsPerCollectionProbeTest.java`,
> which is the text above with these changes only:
> 1. `useUser(USERNAME, PASSWORD)` → `useUser("guardrail_user", "guardrail_password")`: both constants are `private` in
>    `GuardrailTester` (`GuardrailTester.java:89-90`), so the subclass cannot see them.
> 2. Each `System.out.printf` → one `System.out.println(String.format(...))`: the unit test JVM's log writes one line per
>    `System.out` write, and `printf` splits a reading over several lines.
> 3. The T values and the append count are read from `-Dprobe.t` (default `100,1000`) and `-Dprobe.appends` (default 50);
>    run 1 uses the defaults, which are the filed values. Only the harness shakedown sets them.
> 4. After setting the thresholds, a line `PROBE t=<T> readback warn=<w> fail=<f>` from `Guardrails.instance` getters
>    (`Guardrails.java:988-996`).
> 5. The superuser line also prints `memDelta` of the superuser write: `PROBE t=<T> superuser(T+1) card=<n> memDelta=<d>`.
> 6. The disabled reference of amendment B2b: `PROBE t=-1 readback ...` and `PROBE t=-1 single(1001)=<outcome> memDelta=<d> card=<n>`.
>
> **Amendment B2c-2 (2026-10-26, stage-4 run 1, runbook defect U1; claim, predictions and conclusions unchanged).** The first
> unit attempt stopped at the 50th-append read-back at T = 1000: `card(3)` failed with `ReadFailureException` because the unit
> yaml enables read thresholds (`test/conf/cassandra.yaml:63-67`, `local_read_size_fail_threshold: 8192KiB`) and the
> read of the stored set loaded 8,846,516 bytes. The read-back is an instrument, not the traced write path, so:
> 7. The probe first calls `DatabaseDescriptor.setReadThresholdsEnabled(false)` (`DatabaseDescriptor.java:4857`) and prints
>    `PROBE readThresholdsEnabled=false`. The node's default is already `false` (`Config.java:526`), so the cluster tier is unchanged.
> The unit tier restarts from its beginning.

**B2d. Observables and instruments.** The `PROBE` lines report:
- the accept or reject outcome (with the guardrail message),
- `memtableLiveDataSize` deltas (`TableMetrics.java:91, 502`),
- the stored set cardinality, read back through `SELECT`.

The check's operand, `elements.size()`, equals the bound set's size by construction.

> **Amendment B2d (2026-10-26, stage-4 audit, before any reading).** The `PROBE` lines are written by the forked test JVM to
> `build/test/logs/**/TEST-org.apache.cassandra.db.guardrails.ItemsPerCollectionProbeTest.log`, not to Ant's console, so they
> are read from that file. `memtableLiveDataSize` is the memtable's own data-size accounting, not a live-heap reading (gap named;
> the cluster tier reads disk bytes).

**B2e. Procedure.** `ant testsome -Dtest.name=org.apache.cassandra.db.guardrails.ItemsPerCollectionProbeTest 2>&1 | tee /local/$USER/ipc-probe.log; grep PROBE /local/$USER/ipc-probe.log`.

> **Amendment B2e (2026-10-26, stage-4 audit, before any reading).** Run `harness/.../unit-run.sh` with no argument: it copies
> the probe into `$W/cassandra-run31/test/unit/org/apache/cassandra/db/guardrails/`, runs
> `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.db.guardrails.ItemsPerCollectionProbeTest`, copies the
> test log (B2d) and greps `PROBE t=` from it, then removes the probe so the clone's git status is clean. Logs under
> `$W/logs/items_per_collection-doAdd-elements_size--autonomous/unit/`.

**B2f. Predictions.**
- For each T: `single(T+1)=rejected:...Guardrail items_per_collection violated...` with `memDelta = 0`.
- `emptyAdd memDelta = 0`, `card = T`.
- The append lines show `card = 10T, 20T, ..., 50T`, with no exception, and `mem` increases monotonically, roughly linearly in card.
- `superuser(T+1) card = T+1`.

> **Amendment B2f (2026-10-26, stage-4 audit, before any reading).** Exact forms, and predictions for the added lines:
> - `readback warn=T/2 fail=T` for each T; `readback warn=-1 fail=-1` for the reference.
> - "rejected" means the outcome string starts `rejected:` and contains `Guardrail items_per_collection violated` and
>   `with T+1 items` (`Guardrails.java:380-387`, `Guardrail.java:147`). `memDelta = 0` exactly.
> - "mem increases monotonically" means the five append samples' `mem` are strictly increasing. "Roughly linearly" is
>   recorded, not a condition: each of the four successive increments lies within [0.5, 1.5] × their mean.
> - `superuser(T+1) memDelta > 0`.
> - Reference: `single(1001)=accepted`, `memDelta > 0`, `card = 1001`.
> - The test passes (`Tests run: 1, Failures: 0, Errors: 0`): any rejected append throws out of the loop and fails it.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Single T+1 rejected with memDelta 0; appends reach 50T and mem grows; superuser accepted | Claim confirmed: the cap is per write only (positive per write, negative per stored collection) |
| An append is rejected once card exceeds T | Claim (ii) wrong: something counts existing items. Usage of the stored collection *does* follow T |
| Single T+1 accepted for the ordinary user | Claim (i) wrong: the guardrail is not enforced on this path (check that the user is not super) |
| memDelta > 0 on rejection | Partial application before the guard. This would contradict A3 step 2 |
| Appends do not grow mem (flat) while card grows | The instrument failed (e.g. a flush happened). Re-run with `disableAutoCompaction`/`flush` checks; not confirmed |

> **Amendment B2g (2026-10-26, stage-4 audit, before any reading).** Rows added so every plausible outcome has one:
>
> | Observation | Meaning |
> |---|---|
> | The superuser write is rejected, or its `card ≠ T+1`, or its `memDelta = 0` | Positive control failed: **Invalid** for that T |
> | The disabled reference (`-1/-1`) rejects the 1001-item write, or its `memDelta = 0` | The rejection does not come from the knob, or the instrument is blind: **Invalid** |
> | A threshold read-back differs from what was set | **Invalid** |
> | `emptyAdd memDelta ≠ 0` or `card ≠ T` | Claim (iii) wrong; recorded as **Not confirmed** for (iii); the other rows are read on their own |
> | Row 1 holds for one T and not the other | The tier is **Not confirmed**; each T is reported |
> | No row fits | No row fits: feedback to stage 3 |
>
> Row 1 needs, for **both** T: the rejection as in B2f, `memDelta = 0`, append `card = 10T … 50T` with `mem` strictly
> increasing, the superuser control as in B2f, plus the reference as in B2f. **Effect for row 1: caps only on some paths
> (bypass)** — the knob caps the items (and so the memtable usage) a single ordinary-user write adds, but not the stored
> collection, and not superuser writes. Row 2 → Effect `caps`.

**B2h. Controls.** The superuser write is the positive control: the same over-threshold
write is accepted when the guard is bypassed, which shows that the rejection comes from the
guard. The append series is the usage-moving control: it shows that the workload moves
memtable usage. The disabled reference (`-1/-1`) accepts everything.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node from the local clone, built with `ant jar`.
`W=/local/$USER/ipc` on local disk with at least 10 GB free. In `conf/cassandra.yaml` set:
- the data, commitlog, hints, saved_caches and cdc dirs under `$W`
- `authenticator: PasswordAuthenticator`
- `authorizer: CassandraAuthorizer`
- `items_per_collection_warn_threshold: 500`
- `items_per_collection_fail_threshold: 1000`

Set the heap with `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`, and `CASSANDRA_LOG_DIR=$W/logs`.

> **Amendment B3a (2026-10-26, stage-4 audit, before any reading).** On the advisor's machine:
> - Node from `$W/cassandra-run31` (its `build-test` already built the jar; no `ant` runs there while the node is up), node
>   files under `$W/node-ipc/{data,commitlog,hints,saved_caches,cdc_raw,logs}` (local SSD), its own `CASSANDRA_CONF=$W/node-ipc/conf`
>   (a copy of the clone's `conf/` with the yaml overrides) so the clone stays clean; `listen_address`/`rpc_address: 127.0.0.1`.
> - The yaml settings above are kept (PasswordAuthenticator and CassandraAuthorizer are what make `app` an ordinary user:
>   under AllowAllAuthenticator every client is a superuser, `ClientState.java:602-605`, and `Guardrail.enabled` skips
>   superusers, `Guardrail.java:93-96`). Also `read_request_timeout: 60000ms`: arm B reads back a 2,000,000-element row.
> - **Heap 4G** (`MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`) instead of 2G: at T = 10000 phase (ii) holds 2,000,000 cells in one
>   memtable partition; at 2G the memtable pool is 512 MiB (`DatabaseDescriptor.java:586-587`) and flushes start at
>   1/(1+2) of it (`conf/cassandra.yaml:811`, two flush writers, `DatabaseDescriptor.java:753-755`), about 170 MiB, which
>   the partition could reach, splitting phase (ii) across sstables. At 4G the trigger is about 341 MiB. Automatic flushes are
>   still logged and counted (B3d).
> - No `setsid` here: the node runs as a tracked background `bin/cassandra -f`; it is ready when `nodetool status` shows
>   `UN`, `nodetool statusbinary` prints `running`, and `cassandra/cassandra` can log in (the default superuser is created
>   `cassandra.superuser_setup_delay_ms` = 10 s after start, `CassandraRelevantProperties.java:538`).

**Amendment 2026-10-28 (after run 1, authorised by the user) — B3a, a fresh clone for the cluster re-run.** This amendment follows run 1's readings (see the B3f amendment of 2026-10-28). The re-run uses a fresh clone, `$W/cassandra-run73` (`git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run73`, then `ant -Dlocal.repository=$W/m2 build-test`), and the node directory `$W/node-ipc73` (same layout and yaml overrides as above). Heap, authenticator, authorizer, thresholds and readiness checks are unchanged. Reason: a separate clone per run (`HANDOFF-ADVISOR.md` §7.1).

**B3b. Knobs.** `items_per_collection_fail_threshold` = 1000 (yaml). As a second point,
use 10000, set at runtime with JMX `org.apache.cassandra.db:type=Guardrails`
`setItemsPerCollectionThreshold(5000,10000)` (warn, fail) through `jmxterm`. An alternative is
`bin/nodetool setguardrailsconfig items_per_collection_threshold 10000 5000`, where the failure
value comes first (`GuardrailsConfigCommand.java:172-182`). Confirm the change with
`bin/nodetool getguardrailsconfig | grep items_per_collection`. Use `-1`
(disabled) as the reference.

> **Amendment B3b (2026-10-26, stage-4 audit, before any reading).** `jmxterm` is not installed; the runtime values are set
> with `nodetool setguardrailsconfig items_per_collection_threshold <fail> <warn>` and read back with
> `nodetool getguardrailsconfig items_per_collection_threshold` (prints `[fail, warn]`) before each arm. The `-1` reference is not in B3e as filed; it is run as arm R (B3e amendment): thresholds `-1 -1` at
> runtime, workload W = 1000, table `probe.sref`. So three values: 1000 (yaml), 10000 (runtime), -1 (default, runtime).

**B3c. Workload.** Use `ipc.py`, run with the bundled driver:
`PYTHONPATH=/local/$USER/c509-ipc/lib/cassandra-driver-internal-only-3.29.0.zip python3 ipc.py <T>`.
- As superuser `cassandra/cassandra`, it creates keyspace `probe` (RF 1), the table `probe.s (k int PRIMARY KEY, v set<int>)`, the role `app WITH PASSWORD='app' AND LOGIN=true` (not superuser), and `GRANT ALL ON KEYSPACE probe TO app`.
- As `app`, it runs:
  - (i) 200 single `INSERT ... VALUES (k, ?)` with T+1 items each, on keys 1000-1199, and records the failures;
  - (ii) on key 1, 200 appends `UPDATE probe.s SET v = v + ? WHERE k = 1`, each with T new distinct ints (200·T items total: 200,000 at T=1000);
  - (iii) 200 empty appends `v = v + {}` on key 2.
- As `cassandra`, it runs (iv) the same 200 single T+1 inserts on keys 2000-2199. This is the positive control showing the workload moves usage when nothing binds.

After each phase, it runs `nodetool flush probe s` and samples. Total duration: a few minutes.

> **Amendment B3c (2026-10-26, stage-4 audit, before any reading).**
> - `PYTHONPATH=<driver zip>` cannot import `cassandra`: the package sits under `cassandra-driver-3.29.0/` inside the zip. The
>   client, `harness/.../ipc.py`, imports from that subfolder, connects with `PlainTextAuthProvider`, protocol 5,
>   `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, `idle_heartbeat_interval=0`, and retries a connection error
>   (not a server rejection) up to 5 times on a new session (a set append is idempotent).
> - `ipc.py` runs one phase per call (`setup <table>`, `phase <i|ii|iii|iv> <W> <table>`, `card`, `keys`, `bytes`) so that
>   `cluster-run.sh` samples and flushes between phases; W is the workload size (phases (i) and (iv) write W+1 items).
> - Each arm has its own table: `probe.s1000`, `probe.s10000`, `probe.sref` (B3e says "a fresh table name" without one).
> - The table is created `WITH compression = {'enabled': false}`: B3f's disk lower bound counts about 4 B per item plus cell
>   overhead, which holds for uncompressed cells only; the default is LZ4 (`CompressionParams.java:61`).
> - After `setup`, `nodetool disableautocompaction probe <table>`, so a compaction cannot change a phase's disk delta.
> - After `GRANT`, the client waits 3 s (> `roles_validity`/`permissions_validity` 2000 ms, `conf/cassandra.yaml:300, 327`)
>   and checks that `app` can log in and select and is not a superuser (`system_auth.roles`).

**Amendment 2026-10-28 (after run 1, authorised by the user) — B3c, phase (iii-b) added.** This amendment follows run 1's readings (see the B3f amendment of 2026-10-28). Phase (iii) is unchanged (200 empty appends on key 2, a key not written before). A new phase **(iii-b)** runs after (iii)'s samples and before (iv), in every arm, as `app`: one append `UPDATE probe.<table> SET v = v + {0} WHERE k = 3` (the seed: 1 item, at most T in every arm, so it is accepted; `ipc.py phase iiibseed`), then 200 empty appends `v = v + {}` on key 3 (`ipc.py phase iiib`). Why: the B3f amendment of 2026-10-28 shows that phase (iii) cannot test the strict reading of claim (iii), because its key is new to the memtable; (iii-b)'s key is in the current memtable when the empty appends arrive. Phases (i), (ii), (iv), the tables, users and sizes are unchanged.

**B3d. Observables and instruments.**
- Memtable data size before each flush: `bin/nodetool tablestats probe.s`, field "Memtable data size".
- Disk: `du -sb $W/data/probe/s-*` after each flush, and "Space used (live)" from tablestats.
- Stored cardinality: `SELECT v FROM probe.s WHERE k=1` (count in the script).
- Rejections: the driver exceptions, and `grep "items_per_collection" $W/logs/system.log`. The flush-time error has the form "Detected collection v in row ... with N items, this exceeds the failure threshold" (from `SortedTableWriter.java:427`).

> **Amendment B3d (2026-10-26, stage-4 audit, before any reading).** BSD `du` has no `-b`: disk bytes are the sum of file
> sizes under the table directory, skipping `snapshots/` and `backups/` (`ipc.py bytes`). Per phase the run records, in this
> order: the client's accepted/rejected counts and first message; tablestats "Memtable data size", "SSTable count" and "Space
> used (live)" before the flush; `nodetool flush probe <table>` and its exit code; the same tablestats after it; the directory
> bytes; the `system.log` lines containing `items_per_collection` written since the phase started (read from the file's byte
> offset), split into write-time failures (`violated: Detected collection v with`), write-time warnings, and flush-time lines
> (` in row `) — the guardrail logs through a `NoSpamLogger` (`Guardrail.java:47`), so identical write-time messages are folded
> and their count is recorded, not compared with the number of rejections; then after (i) how many of keys 1000-1199 exist, after (ii) the cardinality of key 1, after (iii) of key 2,
> after (iv) how many of keys 2000-2199 exist and the cardinality of key 2000. A phase's disk delta is its directory bytes
> minus the previous sample's. Automatic flushes are counted from `system.log` ("Flushing largest").

**Amendment 2026-10-28 (after run 1, authorised by the user) — B3d, samples of phase (iii-b).** This amendment follows run 1's readings (see the B3f amendment of 2026-10-28). Phase (iii-b) records: the seed's accepted/rejected counts; tablestats "Memtable data size" right after the seed (M_seed) and again after the 200 empty appends, before the flush (M_empty); then the phase samples of the amended B3d above (flush, tablestats, directory bytes, `items_per_collection` lines of the window); then the cardinality of key 3. (iii-b)'s disk delta is its directory bytes minus (iii)'s; (iv)'s delta is now its bytes minus (iii-b)'s. Automatic flushes of a probe table are listed with their times, so one inside (iii) or (iii-b) can be seen.

**B3e. Procedure.**
1. Start the node with `bin/cassandra -p $W/pid` and wait for `UN`.
2. Run `ipc.py 1000`, recording tablestats and du after each phase's flush.
3. Change the threshold to 10000 at runtime and run `ipc.py 10000` on a fresh table name.
4. Run `bin/nodetool stopdaemon`, then `pgrep -f CassandraDaemon || echo gone`.

> **Amendment B3e (2026-10-26, stage-4 audit, before any reading).** One script, `harness/.../cluster-run.sh` (no arguments in
> run 1), one node lifetime: start and wait as in amendment B3a; arm A (yaml 500/1000, table `probe.s1000`, W = 1000);
> `setguardrailsconfig items_per_collection_threshold 10000 5000`; arm B (`probe.s10000`, W = 10000); `setguardrailsconfig
> items_per_collection_threshold -1 -1`; arm R (`probe.sref`, W = 1000). Each arm: read back the thresholds, `setup`,
> `disableautocompaction`, base sample, phases (i)-(iv) with the B3d samples. Then `nodetool stopdaemon` (kill after 60 s),
> check that no daemon is left (`ps`/`pgrep` with a pattern the script's own command line does not match), copy
> `system.log`, wipe `$W/node-ipc`. Logs under `$W/logs/items_per_collection-doAdd-elements_size--autonomous/cluster/`.

**Amendment 2026-10-28 (after run 1, authorised by the user) — B3e, order and paths of the cluster re-run.** This amendment follows run 1's readings (see the B3f amendment of 2026-10-28). Each arm runs phases (i), (ii), (iii), (iii-b), (iv) in this order; everything else in the amended B3e is unchanged (one node lifetime, arms A, B, R, read-backs, `setup`, `disableautocompaction`, base sample). Command: `C=$W/cassandra-run73 IPC_NODE=$W/node-ipc73 IPC_PLAN=run2 OUT=<log dir> cluster-run.sh [T1 T2 REPS]`, first as a shakedown (`50 500 20`, log dir `$W/logs/items_per_collection-doAdd-elements_size--autonomous/cluster-shake2/`), then with no size arguments (1000 10000 200, as filed) into `$W/logs/items_per_collection-doAdd-elements_size--autonomous/cluster-run2/`. `IPC_PLAN=run1` (the default) reproduces run 1's phases.

**B3f. Predictions.**
- **(i)** All 200 inserts are rejected. The memtable size and disk delta for phase (i) are about 0 (only the 0-byte flush; no new sstable for probe.s).
- **(ii)** All 200 appends are accepted. The stored cardinality is 200·T. The disk delta is at least 200·T × (about 4 B value plus cell overhead): more than 1 MB at T = 1000, and more than 10 MB at T = 10000. The flush logs one ERROR line naming 200·T items, and the flush is not interrupted.
- **(iii)** Zero delta.
- **(iv)** The superuser control is accepted. Its disk delta is about 200·(T+1) items' worth, which is the same order as (ii), and it is far above the ~0 of (i).

> **Amendment B3f (2026-10-26, stage-4 audit, before any reading).** Exact forms (W = the arm's workload size; MB = 10^6 B):
> - Read-backs (`nodetool getguardrailsconfig items_per_collection_threshold` prints `[fail, warn]`): arm A `[1000, 500]`,
>   arm B `[10000, 5000]`, arm R `[-1, -1]`. `setup` reports `app_is_superuser=False`.
> - **(i)** (arms A, B) `rejected=200`, `accepted=0`, `conn_errors=0`, the first message contains `Guardrail items_per_collection
>   violated` and `with W+1 items`; keys 1000-1199 present: 0; "Memtable data size" before the flush 0; SSTable count
>   unchanged; "about 0" disk delta means at most 1 % of the same arm's phase (iv) delta.
> - **(ii)** `accepted=200`, `rejected=0`; cardinality of key 1 = 200·W exactly; disk delta > 1 MB (arm A) and > 10 MB
>   (arm B); "one ERROR line" means exactly one flush-time line (` in row `) in the phase-(ii) window, naming `with 200·W items`;
>   "not interrupted" means `nodetool flush` exits 0 and the SSTable count rises by one.
> - **(iii)** `accepted=200`; "Memtable data size" before the flush 0; disk delta at most 1 % of the arm's (iv) delta;
>   cardinality of key 2 = 0.
> - **(iv)** `accepted=200`; keys 2000-2199 present: 200; cardinality of key 2000 = W+1; "same order as (ii)" means the
>   disk delta lies within [0.1, 10] × the arm's (ii) delta. Its flush also logs flush-time lines for its rows (W+1 > T):
>   recorded, not a condition.
> - **Arm R** (thresholds -1/-1, W = 1000): (i) `accepted=200`, keys 1000-1199 present: 200, disk delta within [0.1, 10] × arm
>   R's (iv) delta; (ii) cardinality 200,000; no flush-time `items_per_collection` line in any arm-R phase.

**Amendment 2026-10-28 (after run 1, authorised by the user) — B3f (iii), the bound restated from the source, and (iii-b).** This amendment follows run 1's readings. In run 1, phase (iii) left "Memtable data size" 8 B in every arm (no items, disk delta 0) against the frozen bound 0, and claim (iii) was Not confirmed in the cluster tier through that alone (results §4.2). The user (Yang, the advisor) authorised on 2026-10-28 that the bound be restated from the source and the cluster tier re-run from its beginning. B1, claims (i)–(ii) and their predictions, rows and controls, the unit tier, and the disk and cardinality parts of (iii) are unchanged.
- **What the memtable accounting charges for an empty update** (from the source):
  1. The statement reaches the target and adds no cell. The driver serialises an empty set as a non-null value of 0 elements (`cassandra/cqltypes.py` `serialize_safe`, `len(items)`, in the bundled driver), so `Sets.Marker.bind` gives a `Value` with no elements (`Sets.java:240-250, 332-339`) and `Sets.Adder.doAdd` returns at `:393`. `UpdateStatement.addUpdateForKey` builds the row with no primary-key liveness (only INSERT sets it, `UpdateStatement.java:70-73`), so the row is empty, and `PartitionUpdate.Builder.add` drops an empty row (`PartitionUpdate.java:913-916`).
  2. The empty update is still applied. `SingleTableUpdatesCollector.toMutations` wraps every builder in a `Mutation` with no emptiness filter (`SingleTableUpdatesCollector.java:97-117`); `ModificationStatement` sends it (`ModificationStatement.java:520-529`); the replica applies each partition update (`Keyspace.java:627-653` → `CassandraTableWriteHandler.java:38` → `ColumnFamilyStore.java:1475-1477` → `Memtable.put`).
  3. The memtable is `SkipListMemtable` (`conf/cassandra.yaml:783-790`, `default` inherits `skiplist`; the harness's yaml does not change it). `SkipListMemtable.put` (`SkipListMemtable.java:107-138`): if the key is not in the current memtable (`:110`, `:113`), it inserts an empty partition and sets `initialSize = 8` (`:112-128`, the assignment at `:126`); then `liveDataSize += initialSize + updater.dataSize` (`:133`). The row overhead (token heap size + `ROW_OVERHEAD_HEAP_SIZE`, `:72-80, :124-125`) goes to the allocator's on-heap count, **not** to `liveDataSize`, so the per-JVM estimate of the row overhead does not enter this quantity.
  4. For an empty update, `updater.dataSize = 0`. `makeMergedPartition` (`BTreePartitionUpdater.java:80-94`) keeps the existing deletion info for a live one (`:108-109`), keeps the static row for an empty one (`:98-99`), and `BTree.update` returns the current tree for an empty insert tree (`BTree.java:347-348`) without calling `insert`/`merge`/`delete`, the only places `dataSize` changes (`BTreePartitionUpdater.java:131, 154, 163, 171`).
  5. tablestats "Memtable data size" is `MemtableLiveDataSize` (`TableStatsHolder.java:337`), the current memtable's `getLiveDataSize()` (`TableMetrics.java:502-503`, `SkipListMemtable.java:363-366`). Phase (ii)'s `nodetool flush` replaces the memtable by a new one (`ColumnFamilyStore.java:1211-1212`) whose `liveDataSize` starts at 0 (`SkipListMemtable.java:87`).
  6. Disk: a flush skips empty partitions (`Flushing.java:167`) and aborts a writer that wrote no bytes (`ColumnFamilyStore.java:1332-1339`), so a memtable holding only empty partitions writes no sstable.
- **Consequences.** The charge depends on whether the key is in the **current memtable**, not on whether it exists in the table: after a flush every key is new to the memtable (step 5), so an empty append on a key that exists on disk (key 1, for instance) is also charged 8 B. "Use a key that already exists" therefore removes the charge only if the key was written since the last flush. Hence the two choices test two readings of claim (iii):
  - **Reading (iii-a)**, tested by phase (iii) with the term included: an empty addition adds no item, cell, data byte or disk byte of its own; the only charge is the memtable's fixed 8 B entry for a partition new to the memtable, which `SkipListMemtable.put` makes for any update to such a key, before and independently of its content.
  - **Reading (iii-s), strict**, tested by phase (iii-b): an empty addition to a partition already in the memtable leaves the memtable's data-size accounting unchanged.
- **New relations** (arms A and B; W = the arm's workload size):
  - **(iii)** `accepted=200`; "Memtable data size" before the flush **= 8 B exactly** (the first of the 200 empty appends creates key 2's partition and adds 8 + 0; the other 199 find it, `:110`, `:113`, and add 0 + 0); disk delta at most 1 % of the arm's (iv) delta (unchanged); cardinality of key 2 = 0 (unchanged). Derived expectation, reported and not a condition: disk delta 0 and SSTable count unchanged (step 6).
  - **(iii-b)** seed `accepted=1`; `accepted=200`, `rejected=0`, `conn_errors=0` for the empty appends; **M_empty − M_seed = 0 exactly** (key 3 is in the current memtable, so `initialSize = 0`, step 3, and `updater.dataSize = 0`, step 4); cardinality of key 3 = 1. Recorded, not conditions: M_seed (> 0), (iii-b)'s disk delta, its SSTable count.
  - **Arm R:** (iii) and (iii-b) are recorded against the same expectations, not conditions (as for (iii) in the amended B3f above).
- **What was known of run 1 when this was written:** all of run 1's §4–§5 and section D, including the 8 B in phase (iii) of every arm, disk delta 0, card(2) = 0, and section D's pointer to `SkipListMemtable.java:112-133`. The 8 B is the literal `initialSize = 8` (`SkipListMemtable.java:126`), and "exactly one new partition" follows from steps 1–5; neither was chosen from the reading. **Run 1's readings would pass the amended (iii) relation** (8 B in arms A and B), so (iii-b), which run 1 did not run, is the part of claim (iii) that this re-run can newly fail; under the amended relations run 1 has no (iii-b) reading, so claim (iii) would not be evaluable from run 1's files.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| (i) ~0 delta and all rejected; (ii) grows to 200·T and is accepted; (iv) grows | Claim confirmed: per-write cap holds; stored collection unbounded by T |
| (ii) rejections once the stored count exceeds T | Claim wrong: stored usage does follow T |
| (i) accepted for `app` | Guard not enforced. Check the authenticator and that `app` is not super; not confirmed |
| (iv) delta ~0 | The positive control failed (e.g. the workload never reached disk). Not confirmed |
| Flush fails or aborts on the large set | The sstable-time check binds, which contradicts A3 step 4(c) |

> **Amendment B3g (2026-10-26, stage-4 audit, before any reading).** Rows added so every plausible outcome has one:
>
> | Observation | Meaning |
> |---|---|
> | A read-back differs from what was set, `app` is a superuser, or a phase ends with `conn_errors > 0` | **Invalid** |
> | Arm R rejects (i), or its (i) disk delta is outside [0.1, 10] × its (iv) | The rejection does not come from the knob, or the workload cannot show usage: **Invalid** |
> | (iii) leaves a memtable or disk delta above the B3f bound, or key 2 has items | Claim (iii) wrong; recorded as **Not confirmed** for (iii); the other rows are read on their own |
> | (i) rejected but its disk delta is above the B3f bound | Partial application before the guard (contradicts A3 step 2): **Not confirmed** |
> | Row 1 holds for one of arms A and B only | The tier is **Not confirmed**; each arm is reported |
> | An automatic flush ("Flushing largest") of the probe table during a phase | Recorded. If it splits phase (ii), the one-line condition reads "every flush-time line of phase (ii) names fewer than 200·W items, none aborts a flush, and the phase's sstables sum to the (ii) delta" |
> | No row fits | No row fits: feedback to stage 3 |
>
> Row 1 needs arms A and B as in B3f and arm R as in B3f. **Effect for row 1: caps only on some paths (bypass)** — the knob
> caps what one ordinary-user write adds, not the stored collection and not superuser writes. Row 2 → Effect `caps`.

**Amendment 2026-10-28 (after run 1, authorised by the user) — B3g, row 3 read with the amended (iii) and (iii-b).** This amendment follows run 1's readings (see the B3f amendment of 2026-10-28). The 2026-10-26 row "(iii) leaves a memtable or disk delta above the B3f bound, or key 2 has items" is read with the B3f amendment of 2026-10-28, and rows are added for (iii-b):

| Observation | Meaning |
|---|---|
| (iii) "Memtable data size" before the flush ≠ 8 B, or its disk delta above 1 % of (iv), or key 2 has items (arm A or B) | Reading (iii-a) wrong: claim (iii) **Not confirmed**; the other rows are read on their own |
| (iii) holds, but (iii-b) M_empty − M_seed ≠ 0, or card(3) ≠ 1, or a (iii-b) operation rejected (arm A or B) | The strict reading (iii-s) wrong: claim (iii) **Not confirmed** (reading (iii-a) holds); reported |
| An automatic flush ("Flushing largest") of the probe table inside (iii) or (iii-b), or a (iii)/(iii-b) phase with `conn_errors > 0` | That phase's memtable reading is **Invalid**; claim (iii) **Not confirmed** |
| (iii) and (iii-b) hold in arms A and B, and row 1 holds | The tier is **Confirmed** for claims (i)–(iii) |

Row 1 and its Effect (**caps only on some paths (bypass)**), and every other 2026-10-26 row, are unchanged.

**B3h. Controls.**
- The superuser phase (iv) shows the identical workload consumes disk when the guard is bypassed.
- The empty-add phase isolates the `:393` branch.
- Flushing after every phase attributes the disk use to that phase.
- Using two T values gives a dose check of the per-write rejection boundary.

**Amendment 2026-10-28 (after run 1, authorised by the user) — B3h, the empty-add controls.** This amendment follows run 1's readings (see the B3f amendment of 2026-10-28). The empty-add phase (iii) isolates the `:393` branch on a key new to the memtable, where the only expected charge is the fixed 8 B partition entry (B3f amendment of 2026-10-28, steps 3–5); phase (iii-b) isolates it on a partition already in the memtable, where the expected charge is 0, so the two together separate the branch from the memtable's per-partition charge. The other controls are unchanged.

**B4. Risks and cleanup.**
- Use only local clones. Never add the probe test to the shared clone.
- Node data lives under `$W`, which needs under 1 GB.
- After the runs: `bin/nodetool stopdaemon`, `pgrep -f CassandraDaemon` and `pgrep -f junit` (kill any leftover), then `rm -rf $W`.
- Reset the guardrail to `-1/-1` in the test (as the code above does).

> **Amendment B4 (2026-10-26, stage-4 audit, before any reading).** On the advisor's machine: the clone is
> `$W/cassandra-run31`; node data `$W/node-ipc` (wiped by `cluster-run.sh` before and after); the probe is removed from the
> clone after the unit run and the clone's `git status` must be clean; no Cassandra or JUnit process may be left
> (`ps -eo command | grep '[C]assandraDaemon'`).

**Amendment 2026-10-28 (after run 1, authorised by the user) — B4, paths of the cluster re-run.** This amendment follows run 1's readings (see the B3f amendment of 2026-10-28). The re-run uses the clone `$W/cassandra-run73` and the node directory `$W/node-ipc73`, which `cluster-run.sh` wipes before and after; the clone's `git status` must be clean afterwards; no Cassandra process may be left. Logs: `$W/logs/items_per_collection-doAdd-elements_size--autonomous/cluster-run2/` (shakedown `cluster-shake2/`). Everything else in B4 is unchanged.

## C. Sources read

- src/java/org/apache/cassandra/cql3/Sets.java (253-420)
- src/java/org/apache/cassandra/db/guardrails/Guardrails.java (370-395, 988-1000)
- src/java/org/apache/cassandra/db/guardrails/Threshold.java (75-141)
- src/java/org/apache/cassandra/db/guardrails/MaxThreshold.java (45-60)
- src/java/org/apache/cassandra/db/guardrails/Guardrail.java (80-145)
- src/java/org/apache/cassandra/db/guardrails/GuardrailsMBean.java (571-582)
- src/java/org/apache/cassandra/config/Config.java (919-920); GuardrailsOptions.java (83, 658-677)
- src/java/org/apache/cassandra/service/ClientState.java (594-605)
- src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java (185-215, 385-430)
- src/java/org/apache/cassandra/metrics/TableMetrics.java (91, 502)
- conf/cassandra.yaml (198, 217, 232, 2155-2170)
- test/unit/org/apache/cassandra/db/guardrails/GuardrailTester.java (95-150); GuardrailItemsPerCollectionTest.java (41-115)
- https://issues.apache.org/jira/browse/CASSANDRA-17153

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1 on the advisor's machine** — results:
[`../../stage4-runtime-verification/results/items_per_collection-doAdd-elements_size--autonomous.md`](../../stage4-runtime-verification/results/items_per_collection-doAdd-elements_size--autonomous.md)
(uncommitted). Frozen at sha256 `268a63b5…60be7` after sixteen audit amendments and one run-1 fix (B2c-2, runbook defect U1).

- **Unit: Confirmed — caps only on some paths (bypass)** (B2g row 1). At T = 100 and 1000 the T+1 write is rejected with
  memDelta 0; 50 appends grow the set to 50·T items (+24 B of memtable data per item); the superuser write and the −1/−1
  reference are accepted.
- **Cluster: Confirmed for claims (i)–(ii) — caps only on some paths (bypass)** (B3g row 1). At T = 1000 and 10000 all 200
  over-threshold writes by `app` are rejected with zero memtable and disk usage; 200 appends grow one set to 200·T items
  (1.80 MB and 18.6 MB on disk), never rejected; the flush-time check logs one ERROR line and does not interrupt the flush;
  superuser and reference writes of the same size add about 1.2 MB / 12.0 MB. **Claim (iii) Not confirmed** (amended B3g
  row 3): 200 empty appends on a key not yet written leave 8 B of memtable data size (no items, no disk bytes). Source: the
  skiplist memtable charges 8 B for each new partition (`SkipListMemtable.java:112-133`); the `:393` branch added nothing.
- For stage 3: (1) the B2c probe did not compile (`GuardrailTester` constants are private) and its 50,000-item read-back
  trips the unit yaml's read thresholds (`test/conf/cassandra.yaml:63-67`); (2) phase (iii) should target an existing partition
  (as the unit tier does) or allow the per-partition charge; (3) A1's yaml lines are 2166-2169.

**2026-10-28, stage 4 cluster re-run ("run 1b", authorised by the user)** — same results file, §7 (uncommitted). Re-frozen at
sha256 `8b256e69…5840` after eight amendments `Amendment 2026-10-28 (after run 1, authorised by the user)` (B3a, B3c, B3d, B3e,
B3f (iii), B3g, B3h, B4), written knowing run 1's readings (run 1 would pass the restated (iii) relation; it has no (iii-b)).

- **Cluster: Confirmed for claims (i)–(iii) — caps only on some paths (bypass)** (B3g row 1 and the 2026-10-28 row). Claims
  (i)–(ii) repeat run 1 (all over-threshold `app` writes rejected with zero usage at T = 1000 and 10000; 200 appends to 200·T
  items, 1.80 MB / 18.6 MB on disk, never rejected; superuser bypass; the flush-time check only logs). (iii): empty appends on a
  key new to the memtable leave exactly the 8 B `SkipListMemtable.put` charges for a new partition (`SkipListMemtable.java:126`),
  no items, disk 0; (iii-b): 200 empty appends to a partition already in the memtable change its data size by 0 (65 → 65 B).
- For stage 3: a "zero memtable delta" prediction for a no-op write must say whether the key is already in the current memtable;
  after every flush all keys are new to it, so "a key that exists" is not enough.
