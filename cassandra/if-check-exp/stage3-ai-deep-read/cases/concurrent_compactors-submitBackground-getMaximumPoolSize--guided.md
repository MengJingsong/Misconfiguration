# concurrent_compactors — compaction task

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Estimate: negative** (Rule 2, recorded in `predicted-negative.md`, batch "the capacity-word pass"). This file writes the negative estimate up with a test of the opposite claim: that `concurrent_compactors` does **not** bound the memory or disk a node uses for compaction.

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | CONCURRENT_COMPACTORS-SUBMITBACKGROUND-GETMAXIMUMPOOLSIZE |
| **Constraint** | `concurrent_compactors` — configuration entry (`cassandra.yaml`), live-settable (`nodetool setconcurrentcompactors`) |
| **Enforcement pattern** | n/a — rejected at Rule 2. Had it counted, pattern (a): the comparison is the decision to skip scheduling. |
| **Capacity check** | [`CompactionManager.submitBackground():245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L245) — `executor.getActiveTaskCount() >= executor.getMaximumPoolSize()` |
| **Decision point** | the same line: `Collections.emptyList()` (skip) vs. `executor.submitIfRunning(new BackgroundCompactionCandidate(cfs), …)` at [`CompactionManager.java:258`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L258) |
| **Allocation site** | n/a for the check. What a running task allocates: the output writer, [`CompactionTask.runMayThrow():213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L213) |
| **Related cases** | [`max_space_usable_for_compactions_in_percentage…`](max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--guided.md) (the byte budget that caps the same compaction output; used here as the positive control) |

```java
int count = compactingCF.count(cfs);
if (count > 0 && executor.getActiveTaskCount() >= executor.getMaximumPoolSize())
{
    logger.trace("Background compaction is still running for {}.{} ({} remaining). Skipping", ...);
    return Collections.emptyList();
}
...
Future<?> fut = executor.submitIfRunning(new BackgroundCompactionCandidate(cfs), "background task");
```

## 2. Context

Compactions merge SSTables in the background. Cassandra runs them on a fixed-size thread pool, and `concurrent_compactors` sets that pool's size. The check above only avoids piling more background tasks on a table that already has one running when every thread is busy; it is a scheduling guard, not a byte comparison. Without a bound on the pool, a node with many tables could start a compaction for each at once.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | storage engine — compaction scheduling (`db/compaction`) |
| **One-line role** | Chooses SSTables to merge and runs the merges on a bounded executor. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | partial — it compares a running-task count to a pool size, so the operands are counts, not bytes. |
| **Usage-side operand** | `executor.getActiveTaskCount()` — threads currently running a compaction task |
| **Limit-side operand** | `executor.getMaximumPoolSize()` — the pool size, set from `concurrent_compactors` |
| **Limit type** | Configuration entry, with a derived default |

**Limit initialization path:**

1. [`Config.concurrent_compactors:335`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L335) — declared (`Integer`, null by default)
2. [`DatabaseDescriptor.applySimpleConfig():777-778`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L777-L778) — when unset, `min(8, max(2, min(cores, data_file_directories.length)))`; [`DatabaseDescriptor.java:780-781`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L780-L781) rejects values ≤ 0
3. [`CompactionExecutor():2024`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L2024) — the pool is built with `getConcurrentCompactors()` threads and an unbounded queue (`Integer.MAX_VALUE`)
4. [`CompactionManager.submitBackground():245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L245) — read at the comparison; live changes go through [`StorageService.setConcurrentCompactors():1964`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L1964) → [`CompactionManager.setConcurrentCompactors():2238`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L2238), which resizes the pool

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`CompactionManager.submitBackground():245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L245) |
| **Verdict** | n/a — the check is the decision |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | the table has no running compaction, or a thread is idle | submits a `BackgroundCompactionCandidate` to the pool |
| **Disallow** | the table already has a compaction and every thread is busy | returns an empty list; the table is rescheduled when a task ends ([`BackgroundCompactionCandidate.run():383`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L383)) |

## 6. Code path

### 6a. Allow path → object creation

1. [`submitBackground():258`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L258) — the candidate is submitted
2. [`BackgroundCompactionCandidate.run():366`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L366) — asks the strategy for the next task
3. [`BackgroundCompactionCandidate.run():374`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L374) — `task.execute(active)`
4. [`CompactionTask.runMayThrow():213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L213) — the output writer is created; the task then writes its output SSTables

### 6b. Disallow path effect

The caller gets an empty future list and nothing is queued for that table now. The pool has no cap on queued tasks, so the guard limits how many *tables* stack up, not how many threads run. The thread bound itself comes from the pool size: at most `concurrent_compactors` tasks execute at once, whichever way they were submitted (manual `nodetool compact` goes through the same executor).

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | per running task: an output `SSTableWriter` set and its read buffers |
| **Resource consumed** | on-disk bytes (in-progress output SSTables, up to roughly the size of the inputs until the task commits); heap and off-heap for buffers and index summaries |
| **Rough sizing** | output ≈ the size of the merged inputs, per task |
| **Lifetime / release** | the task's transaction commits (inputs deleted) or aborts (outputs deleted) |

## 8. Maximum memory/disk bound

By the rejection's reading, the pool size bounds threads, not bytes: each task's footprint depends on the SSTables it merges, whatever `concurrent_compactors` is. Against that, node-wide compaction usage is the **sum over running tasks**, so a node can hold up to `concurrent_compactors × (largest task's footprint)`. Whether this sum actually follows the knob, or whether other limits keep it flat, is what §9 tests. Source reading predicts the sum does follow the knob, which would make the rejection too narrow (see §10 Notes).

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** It carries no measured numbers and no verdict. The test varies `concurrent_compactors` against a fixed backlog of equal compactions and reads the peak extra disk the node holds for in-flight compaction output, at both the check's own operand and the real resource.

### 9a. Procedure and conclusions

**Testability:** config, live-settable (`nodetool setconcurrentcompactors <n>`). A fresh node per value is cleaner but not required.

**Claim under test (the rejection):** `concurrent_compactors` does not bound compaction's disk or memory usage; the peak extra disk held for in-flight compaction output is the same at every value of the knob.

**How this verifies the hypothesis:**

- **Hypothesis:** the knob bounds threads only, so peak in-flight output bytes do not change with it.
- **Test:** vary `concurrent_compactors` over 1, 2 (the default on a one-directory node), 4 and 8 against 8 tables that each hold 4 equal SSTables of 256 MiB (output ≈ 1 GiB per compaction), compaction throughput capped so each compaction lasts minutes. Read peak extra disk and the number of tasks running.
- **Logic:** (1) the running-task count peaks at `min(n, 8)`, else the run is invalid; (2) peak extra disk is read at each value; (3) a positive control lowers a known byte cap on the same workload and the instrument must show the peak drop; (4) the claim is confirmed only if peak extra disk stays flat while the control moves.
- **Refuted if:** peak extra disk rises with the knob (the hypothesis predicts it does not).

**Procedure:**

1. **Unit tier** — hold *k* compaction tasks open in a test node and read the executor's running-task count and the summed input sizes of the held tasks at each pool size (9c).
2. **Cluster tier** — one node; load the 8 tables, then enable compaction for all at once and sample, once per value (9e).
3. **Positive control** — rerun the largest pool size with `max_space_usable_for_compactions_in_percentage` lowered so the byte budget fits only about two compactions.
4. **Compare** with the prediction and read the table.

**Prediction (what the rejection claims):** peak extra disk is the same at every value of the knob (within the noise band measured in the control run), while the running-task count still equals `min(n, 8)`; the positive control moves peak extra disk down.

**Conclusions:**

| Result | Conclusion |
|---|---|
| Peak extra disk is flat across the four values, the task count follows the knob, and the positive control lowers the peak | **Confirmed** — the knob does not cap compaction bytes; the rejection holds. |
| Peak extra disk rises with the knob (about `min(n, 8)` × one compaction's output) | **Refuted** — usage follows the constraint, indirectly through the number of tasks. The rejection is too narrow; record the slope. |
| Peak extra disk is flat but the positive control does not move it | **Not confirmed** — the instrument cannot see a cap; fix the sampler and rerun. |
| The task count never reaches the pool size (fewer than `n` compactions run) | **Invalid run** — the backlog is too small; raise the table count or SSTable size. |
| Peak extra disk rises but less than proportionally, flattening at some value | **Refuted** — usage follows the knob up to a second limit; name the limit from the control and the disk-space budget. |

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `concurrent_compactors` — `nodetool setconcurrentcompactors <n>` (live) or the yaml key (restart). |
| **Confirm it took effect** | `nodetool getconcurrentcompactors`, and the pool's max size in `nodetool tpstats` (`CompactionExecutor`). |
| **Capacity values** | 1, 2 (default on a one-directory node), 4, 8 (threads). |
| **Scope** | Node-wide; one pool shared by all tables. The multiplier is the number of tables with eligible compactions (8). |
| **Level** | Unit and cluster. |

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `compaction_throughput` | `nodetool setcompactionthroughput 16` (MiB/s) | keeps compactions alive long enough to sample (**amended 2026-10-20, R1:** the limiter is shared by all running compactions, so the 8 GiB of output takes about 8.5 min at every *n*; only at *n* = 1 does one compaction last about a minute) |
| `data_file_directories` | one local directory on a 40 GiB filesystem | a known disk size, not `/proj` |
| compaction strategy | `SizeTieredCompactionStrategy`, `min_threshold=4`, `max_threshold=4` | one compaction per table, equal sizes |
| `max_space_usable_for_compactions_in_percentage` | 0.95 (default) except in the control | otherwise the byte budget would bind |
| heap | `-Xms8G -Xmx8G` | removes heap sizing as a variable |

**Controls:** an idle node (baseline disk and heap), the default knob, and the positive control above.

**Reset between runs:** stop the node, delete the data and commit-log directories, start, recreate the schema.

### 9c. Workload

Unit tier: in a `CQLTester`-based test, create 8 tables with 4 small SSTables each, and use a Byteman rule to hold every `CompactionTask.runMayThrow()` at entry until released. For each pool size, call `setConcurrentCompactors(n)`, trigger `submitBackground` on all tables, and read the running-task count and the summed on-disk size of the held tasks' input SSTables.

Cluster tier:

```bash
# load: 8 tables x 4 SSTables x 256 MiB, compaction disabled during the load
python3 harness/load_tables.py --tables 8 --sstables 4 --sstable-mib 256 --disable-compaction
nodetool setcompactionthroughput 16
nodetool setconcurrentcompactors <n>
nodetool enableautocompaction ks          # releases all 8 compactions at once
```

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Running tasks** — the check's operand | `nodetool compactionstats` (active count); `nodetool tpstats` `CompactionExecutor` active | every 2 s | Validation and index builds use other pools; read only `CompactionExecutor`. |
| **Extra disk held** — the real resource | `du -sb <data dir>` minus the baseline taken before enabling compaction | every 2 s until all compactions end | Inputs are deleted at commit, so the peak is mid-run, not at the end. |
| **Heap/off-heap** | `jcmd <pid> GC.heap_info` and `nodetool info` off-heap | every 10 s | GC timing blurs small differences; use it as a secondary reading. |
| **Cap evidence for the control** | the "insufficient disk" / reduced-scope compaction lines in `system.log` | continuous | Produced only by the byte budget. |

### 9e. Running the scenarios

1. **Control run** — idle node; record baseline disk and heap.
2. **Scenario A — default knob (2)** — load, enable compaction, sample until no compaction is active; record peak extra disk and peak running tasks.
3. **Scenario B — vary the knob** — repeat from a clean node for 1, 4 and 8.
4. **Scenario C — positive control** — at 8, set `max_space_usable_for_compactions_in_percentage` to a value whose budget fits about two 1 GiB compactions (budget ≈ `(40 GiB - baseline) × p`; choose `p` accordingly) and repeat; the peak must drop toward two compactions' output.

### 9f. Stage-4 audit amendments (2026-10-20)

Made at the step-0 audit, before any run or reading; each is a dated change that leaves the claim, the prediction and the conclusions table as filed (results file §1.1 gives the reason for each). Where one corrects a number or a procedure above, this block governs.

- **R1 (9b, 9d: duration and stop).** `compaction_throughput` is one limiter for all running compactions, so total time is about 8.5 min (8 GiB at 16 MiB/s) at every value, and at *n* = 8 all eight compactions advance together and finish near the end. Sampling runs until no compaction is active, at most 20 min; the peak is the maximum over the whole run.
- **R2 (9c: input size).** "256 MiB" means on-disk bytes of each input SSTable. Create the tables with `compression = {'enabled': 'false'}` and random (incompressible) blob values, take `du -sb` of each table's data directory after the load, and compute the expected ceiling as `min(n, 8)` × (the measured input bytes of one table), not a nominal 1 GiB.
- **R3 (9e step 4: control budget).** Choose `p` in a step-1 dry run so the budget fits two but not three compactions, on a fixed-size local loopback filesystem (as for `DataDirectory_getAvailableSpace`; `~/stage4-dds.img` is one) so that `available` is known. The chosen `p`, the filesystem size and the baseline go into results §2.
- **R4 (9a: "within the noise band").** The noise band is the range of peak extra disk over three repeats of the default value (*n* = 2). "Flat" means the peaks at 1, 2, 4 and 8 differ by no more than that band; "rises with the knob" means the peak at 8 exceeds the peak at 1 by more than twice the band.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Estimate** | `negative` |
| **Ground** | Rule 2: the limit-side operand is a thread-pool size (`predicted-negative.md`, batch "the capacity-word pass") |
| **Autonomous reference** | none |
| **Stage-3 feed** | 3b (found by reading the source; recorded in `predicted-negative.md`) |
| **Filed by / Date** | guided agent session, 2026-10-19 |
| **Line numbers checked** | 2026-10-19 against `cassandra-5.0.9` |
| **Escape hatch / Target-3 note** | `nodetool setconcurrentcompactors` raises the pool live; the queue is unbounded (`Integer.MAX_VALUE`, [`CompactionManager.java:2024`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L2024)) |
| **Stage-4 feedback** | none yet |
| **Notes** | Written as the pilot of the rejected-entry write-up. The source reading in §8 predicts the claim will be **refuted**: usage of in-flight compactions is a sum over running tasks, so the pool size bounds it indirectly. If stage 4 confirms that, the Rule 2 ground "thread-pool size is not a byte limit" is too strong for pools whose tasks each hold bytes, and other thread-pool rejections (`SEPExecutor`, `concurrent_reads`) should be re-examined for the same effect. |

---

## 11. Notes

- Related thread-pool rejections written up with this file are not yet in `cases/`: `SEPExecutor.java` permit accounting, `concurrent_validations`.
