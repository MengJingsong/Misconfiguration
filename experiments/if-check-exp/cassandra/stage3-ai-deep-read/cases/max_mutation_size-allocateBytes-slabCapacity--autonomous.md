# max_mutation_size (hint slab size) — verification solution  <!-- file: cases/max_mutation_size-allocateBytes-slabCapacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/hints/HintsBuffer.java:190` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-sonnet-5-5, Claude Code (Agent SDK), 2026-10-19 |
| Estimate | `positive`, with a caveat: the slab is a fixed-size direct buffer allocated up front, so the line-190 check bounds how much hint data one slab holds. The real off-heap bound is slab size x `MAX_HINT_BUFFERS` (default 3), and slab size is derived from `max_mutation_size` with a 32 MiB floor. The line does not trigger or avoid any allocation. |

## A. Constraint trace

**A1. The constraint.** The check at line 190 compares against `slab.capacity()`. That capacity is not a setting of its own: it is the `bufferSize` argument passed to `ByteBuffer.allocateDirect(slabSize)` (`HintsBuffer.java:75-78`). It is computed once in `HintsService.<init>` as `Math.max(DatabaseDescriptor.getMaxMutationSize() * 2, MIN_BUFFER_SIZE)` (`hints/HintsService.java:110`), with `MIN_BUFFER_SIZE = 32 << 20` (`HintsService.java:79`).
- Kind: a derived constant. Inputs are the configuration entry `max_mutation_size` (`config/Config.java:406-407`) and the constant 32 MiB.
- Unit: bytes.
- Default: `max_mutation_size` is null in `Config` and defaults to `commitlog_segment_size / 2` (`DatabaseDescriptor.java:898-899`). `commitlog_segment_size` defaults to 32MiB (`Config.java:397`, `conf/cassandra.yaml:660`), so `max_mutation_size` is 16 MiB and the slab is `max(32 MiB, 32 MiB)` = 32 MiB.
- Setting it: yaml key `max_mutation_size` (a value above 16 MiB needs `commitlog_segment_size >= 2 x max_mutation_size`, else startup fails, `DatabaseDescriptor.java:900-901`). A restart is needed, because `HintsService.instance` is a static singleton built once. Values below 16 MiB change nothing, because of the 32 MiB floor.
- The number of slabs is a second constraint, the JVM property `cassandra.MAX_HINT_BUFFERS`, default 3 (`CassandraRelevantProperties.java:351`, read at `HintsBufferPool.java:41`). It is covered by a separate case (MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS).

**A2. What it caps.** Off-heap (direct) memory for hints that are queued in memory before they are flushed to hint files. The operand is `prev + totalSize`, the end offset of the requested allocation within the slab. It is compared against `slab.capacity()`, in bytes of one slab.

**A3. Mechanism.**
1. `HintsService.write` (`HintsService.java:161-169`) calls `HintsBufferPool.write` (`HintsBufferPool.java:60-67`), which calls `allocate(hintSize)` (line 69 onward).
2. `HintsBuffer.allocate(int)` (`HintsBuffer.java:148`) adds `ENTRY_OVERHEAD_SIZE = 12` (`HintsBuffer.java:58`). It rejects any single hint over `capacity/2` with `IllegalArgumentException` (lines 152-157). This is a hard cap on single-hint size, 16 MiB at the default.
3. `allocateBytes` (lines 183-197) does `position.getAndAdd(totalSize)`. If `prev < 0` the slab is already closed and the call returns -1 (line 187). **Line 190** checks `prev + totalSize > capacity`. If it is true, `position` is set to `Long.MIN_VALUE`, which closes the slab, and -1 is returned. Otherwise it returns the offset `prev`.
4. A -1 becomes a null `Allocation` (lines 171-180). In the pool (`HintsBufferPool.java:74-84`) the caller calls `switchCurrentBuffer(current)`. If it wins the switch, it calls `flushCallback.flush` (`HintsWriteExecutor.flushBuffer`), and then retries.
5. `switchCurrentBuffer` (`HintsBufferPool.java:99-124`) polls a recycled buffer. If none is free and `allocatedBuffers >= MAX_ALLOCATED_BUFFERS` it **blocks** on `reserveBuffers.take()`. Otherwise it allocates a new slab (`createBuffer`, lines 130-134).
6. `FlushBufferTask.run` (`HintsWriteExecutor.java:137-155`) writes the buffer to a hint file and then calls `recycle()` (`HintsBuffer.java:96-100`: `slab.clear()` plus a new `HintsBuffer` over the same slab). `offer` returns it to the reserve queue.
- Outcomes of the check: false means the hint is placed in the slab. True means the slab is closed, the hint goes to another slab, and writers may block when all slabs are in flight.
- Overshoot or bypass: `position` can exceed capacity by one failed `getAndAdd`, but nothing is written past capacity because the offset is not returned. The `position` long itself is not memory. Slab memory is fully allocated and zeroed at creation, so resident off-heap use is the slab size regardless of fill. The slab is never shrunk: `free()` (lines 102-105) is called only at `HintsBufferPool.close()` for the current buffer.
- Because `position.getAndAdd` is unconditional, the size is bounded but the counter is not clamped. This is irrelevant to memory.

**A4. Other consumers.** Other direct and heap memory outside this control: chunk cache, `BufferPool` (`file_cache_size`), netty direct buffers, memtables (heap/off-heap), compression buffers, the commitlog. Hints on disk are bounded by a different control, `max_hints_size_per_host` (`DatabaseDescriptor.java:3601-3603`). Hint file size is `max_hints_file_size` (`Config.java:447`). `-XX:MaxDirectMemorySize` bounds `allocateDirect` globally; if unset it defaults to the max heap, and exceeding it raises `OutOfMemoryError` in `HintsBuffer.create`.

**A5. Evidence beyond the source.** none. (Existing tests such as `HintsBufferTest` and `HintsBufferPoolTest` under `test/unit/org/apache/cassandra/hints/` were not opened in this pass.)

## B. Verification solution

**B1. Claim under test.** (1) A `HintsBuffer` never accepts allocations whose cumulative size exceeds its slab capacity, and the slab capacity equals `max(2 x max_mutation_size, 32 MiB)`. (2) On a real node, direct-memory use for hints equals (slabs allocated, at most `MAX_HINT_BUFFERS`) x that slab size, and does not grow with the volume of hints queued, which stays flat once the slabs exist. It moves with `max_mutation_size` only above the 16 MiB point, and with `MAX_HINT_BUFFERS`. The claim is wrong if hint-attributable direct memory exceeds `slabs x capacity`, or if it changes when `max_mutation_size` is lowered below 16 MiB.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Clone the tag to local disk (for example `git clone --branch cassandra-5.0.9 --depth 1 <local clone> /local/c509`; never build in the shared tree). Put a new test class in the clone's `test/unit/org/apache/cassandra/hints/` (the same package gives access to the package-private `HintsBuffer.create/allocate`). Build with `ant build-test`. Run with `ant testsome -Dtest.name=org.apache.cassandra.hints.SlabCapacityProbeTest`. JVM options come from the default test JVM args, plus `-XX:NativeMemoryTracking=summary` if wanted.

**B2b. Knobs.** The slab size passed to `HintsBuffer.create(int)`: 1 MiB, 4 MiB and 32 MiB (the default). Use small sizes to keep the run fast; the logic is size-independent. Hint payload sizes: 100 B, 1 KiB, and `capacity/2 - 12` (the largest legal hint). Also `HintsService`-level values for 32 MiB vs 64 MiB, derived by computing `Math.max(mms*2, 32<<20)` for `max_mutation_size` of 4 MiB, 16 MiB and 32 MiB (this part is a pure arithmetic assertion, since the singleton cannot be re-created).

**B2c. Workload.** For each capacity C, loop `buffer.allocate(h)` for payload size h until the first null. Accepted bytes are `n x (h+12)`, with n = floor(C/(h+12)). The null must appear at n+1. Then call `allocate` several more times and confirm all return null (slab closed). Then `recycle()` and confirm allocation works again. Finally try `allocate(C/2)` which must throw (total = C/2+12 > C/2), and `allocate(C/2 - 12)` which must succeed on an empty slab.

**B2d. Observables and instruments.** Return value of `allocate` (null or not), `remaining()`, `isClosed()`, `capacity()`, the sum of accepted `totalSize`, and `ManagementFactory` `BufferPoolMXBean` named "direct" (`getMemoryUsed`, `getCount`) before and after `create`. Not observable: `position` directly (private); use `remaining()`/`isClosed()`.

**B2e. Procedure.**
1. Clone and build as in B2a.
2. Write the probe test with the loops from B2c.
3. Record direct pool `memoryUsed` before and after `HintsBuffer.create(C)` for each C.
4. Run the test and save stdout.
5. Delete the clone's build output when done.

**B2f. Predictions (before any run).**
- Direct pool grows by exactly C per `create(C)` (plus a count increase of 1).
- Accepted allocations: n = floor(C/(h+12)); the (n+1)th returns null; `sum(accepted totalSize) <= C` always; `remaining() == C - sum` before the null, then 0 after closing.
- After close, every `allocate` returns null with no growth in direct memory.
- Maximum legal hint is `C/2 - 12` (accepted); `C/2 - 11` throws `IllegalArgumentException`.
- After `recycle()`, the same n is accepted again and direct memory does not grow (the slab is reused).
- Derived slab: 4 MiB -> 32 MiB, 16 MiB -> 32 MiB, 32 MiB -> 64 MiB.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Accepted sum <= C, null at n+1, matches formula | Check works as traced |
| Accepted sum > C, or null appears early or late | Claim wrong (off-by-one or accounting error) |
| Direct pool grows by more than C per create | Overhead outside the cap (note, not a refutation of the slab bound) |
| Direct pool grows on `allocate` or `recycle` | Claim wrong: growth beyond the slab |
| Over-large single hint accepted | Single-hint guard not as traced |

**B2h. Controls.** Run the same loop with C unchanged but different h to show n scales with h and the sum stays <= C. Run with a fresh JVM per C, or compare direct memory deltas, so other direct allocations in the test JVM do not mix in (take deltas, with a GC call before sampling).

### B3. Cluster tier

**B3a. Environment and build.** Two nodes (A under test, B as the dead replica), JDK 11, built from the local clone (`ant jar`). Both on local disk with a known size (for example 20 GB). Config on A: `hinted_handoff_enabled: true`, `max_hints_size_per_host: 0` or a large value, `hints_flush_period: 3600000ms`-style long value (1h) so flushes only happen when a slab fills, `hints_directory`, `data_file_directories` and `commitlog_directory` on local disk, `commitlog_segment_size: 32MiB` for the first runs. Heap 2 GiB, and `-XX:MaxDirectMemorySize=2g` so direct memory is bounded and explicit. Enable JMX.

**B3b. Knobs.**
- (a) `max_mutation_size` (yaml): not set (16 MiB, slab 32 MiB), then `4096KiB` (slab still 32 MiB, shows the floor), then `32768KiB` with `commitlog_segment_size: 64MiB` (slab 64 MiB).
- (b) `-Dcassandra.MAX_HINT_BUFFERS`: 3 (default) and 1.
Each is a restart of node A.

**B3c. Workload.** Create a keyspace with RF=2, then stop node B. Write through A using `cassandra-stress` or a CQL loop at CL=ONE: 2 KiB values, enough that hints queued total much more than the slab: with a 32 MiB slab, 200,000 mutations x about 2.1 KiB = about 420 MB, that is about 13 slabs worth, so the slab fills and recycles several times. Also a phase with a few 8 MiB values (below `capacity/2` = 16 MiB) and one at slightly over 16 MiB with the default setting, which must be rejected. Duration: a few minutes per configuration. Disk for hints: roughly 0.5 GB per run (check free space first).

**B3d. Observables and instruments.** JMX `java.nio:type=BufferPool,name=direct` (`MemoryUsed`, `Count`) on A sampled every 5 s; baseline taken before any hint is written, then deltas. Process RSS (`ps -o rss`) every 5 s. `nodetool` `tpstats` and `gcinfo`. Hint-file sizes in the hints directory (`du`). `org.apache.cassandra.metrics:type=Hints*` for hints written. Not observable: `allocatedBuffers` and slab fill (private); infer from the direct-pool count delta. Other direct allocations (chunk cache, BufferPool) add noise, so use deltas against the pre-write baseline and compare across configurations.

**B3e. Procedure.**
1. Clone the tag to local disk, `ant jar`, create the two node directories.
2. Start A and B, create the keyspace, take the baseline direct-memory reading with no hints yet.
3. Stop B (`nodetool drain` then kill, or just kill).
4. Run the workload through A and sample B3d every 5 s.
5. Record the direct delta once hints exceed 1.5 slabs worth, and again at the end of the run.
6. Restart A with the next knob setting (B3b) and repeat from step 2.
7. Stop everything and check with `ps` that no Cassandra or stress process remains; delete node directories.

**B3f. Predictions (before any run).**
- Default setting (slab 32 MiB, 3 buffers): the direct delta after first hint is about 32 MiB, and it stays between 32 and 96 MiB (1 to 3 slabs) however many hints are queued. Total hints written are far over 96 MiB, yet the delta does not exceed 96 MiB (plus noise).
- `max_mutation_size: 4096KiB`: same as default (slab remains 32 MiB, within noise).
- `max_mutation_size: 32768KiB`: slab 64 MiB, so delta 64 to 192 MiB; the one-slab step doubles relative to default.
- `MAX_HINT_BUFFERS=1`: delta stays at one slab (32 MiB), and writers briefly block while the flush completes (hint write latency rises).
- RSS rises by about the same amount as the direct delta (the slab is zeroed on allocation).
- Hint of 17 MiB with the default setting is refused (the mutation fails earlier at `max_mutation_size` validation, or at the 16 MiB guard in `HintsBuffer.allocate`); no memory change.
- The claim is wrong if the delta keeps growing with hints written, exceeds `MAX_HINT_BUFFERS x slab` by more than noise, or moves when `max_mutation_size` is lowered below 16 MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Delta plateaus at k x slab, k <= MAX_HINT_BUFFERS, and the plateau scales with slab size | Claim confirmed |
| Delta grows with hints written past k x slab | Claim refuted: usage not bounded by slab capacity |
| Delta differs between default and `max_mutation_size: 4096KiB` | Floor reading wrong (re-check the derivation at `HintsService.java:110`) |
| Delta stays at 32 MiB with `max_mutation_size: 32768KiB` | Slab size not following the knob; check that the setting took effect |
| Hints written never exceed 1 slab | Limit not reached; not confirmed. Increase the workload or lower `hints_flush_period` effects |
| No hints written (B really up) | Workload invalid, rerun |

**B3h. Controls.** (1) Same workload with `hinted_handoff_enabled: false`: direct delta should be about 0 for hints, which shows the delta is from hints. (2) Same build and machine for all runs, so JVM overhead is the same. (3) Repeat the default run twice to measure noise of the direct-pool baseline. (4) Check B was down for the full run so no hint dispatch drains buffers.

**B4. Risks and cleanup.** Disk: hints, data and commitlog total under 3 GB per run on a local disk of known size; never use shared storage. Memory: with `-XX:MaxDirectMemorySize=2g` the worst case is bounded. Processes: kill nodes A and B and the stress client, verify with `ps -u $USER | grep -i -E 'cassandra|stress'`; remove the node directories and the clone's build output.

**Audit amendments (stage 4 step 0, 2026-10-20).** Made before any run or reading; each leaves B1, the predictions and the readings tables as filed, except where it says it adds a row or corrects a number (results file §1.1 gives the reason for each). Where an amendment corrects text above, the amendment governs.

- **R1 (B3g: added rows).** Add before any reading:

  | Observation | Meaning |
  |---|---|
  | `MAX_HINT_BUFFERS=1` delta stays at one slab plus noise, and hint write latency rises | The slab count governs the plateau (prediction holds) |
  | `MAX_HINT_BUFFERS=1` delta equals the default run's | The count does not bind; claim (2) partly wrong |
  | The 17 MiB write is accepted at the default setting | The coordinator's `max_mutation_size` guard is not as traced; stop and re-trace |

- **R2 (B3f: the 17 MiB bullet).** At the default `max_mutation_size` (16 MiB) the coordinator refuses a 17 MiB write with a mutation-too-large error before any hint exists, so the cluster tier exercises that guard, not the slab's `capacity/2` guard; the slab guard is tested only in the unit tier (B2c). Read the bullet as: the write fails at the coordinator, no hint is written, no direct-memory change.
- **R3 (B3a: exact value).** `hints_flush_period: 3600000ms` (a duration in milliseconds; default 10 s).

## C. Sources read

- `src/java/org/apache/cassandra/hints/HintsBuffer.java` (lines 60-258)
- `src/java/org/apache/cassandra/hints/HintsBufferPool.java` (lines 40-150)
- `src/java/org/apache/cassandra/hints/HintsService.java` (lines 60-125)
- `src/java/org/apache/cassandra/hints/HintsWriteExecutor.java` (lines 83-165)
- `src/java/org/apache/cassandra/config/Config.java` (lines 396-397, 406-407, 444-448)
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (lines 898-901, 2827-2830, 3239, 3592-3603, 3720)
- `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java` (line 351)
- `conf/cassandra.yaml` (lines 68, 93-125, 660)
- Existing case `cases/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided.md` (first 40 lines, for format and the related constraint)
- `_TEMPLATE-autonomous.md`, `playbook-autonomous.md`

## D. Stage-4 feedback

**2026-10-20, run 1 (`pc06`; nodes A and B on loopback on one host, an environment deviation from the audit's `pc57` + `pc50`). Unit Confirmed (B2g row 1); cluster Confirmed (B3g row 1, R1 row 1) — caps; no run 2.** Results: [`stage4-runtime-verification/results/max_mutation_size-allocateBytes-slabCapacity--autonomous.md`](../../stage4-runtime-verification/results/max_mutation_size-allocateBytes-slabCapacity--autonomous.md). B1, B2f and B3f stand. The sections above are not amended; these notes are for a later reader.

- **Readings.**
  - Unit: n = ⌊C/(h+12)⌋ exactly at C = 1, 4 and 32 MiB; direct +C and `Count` +1 per `create`; no growth on fill or `recycle`; `C/2 − 12` is the largest legal hint (115/115 checks).
  - Cluster: hint-pool direct memory 64.2 MiB (2 × 32 MiB) at the default, 64.2 MiB at `max_mutation_size` 4096KiB (the floor), 128.2 MiB (2 × 64 MiB, a per-slab step of 1.996×) at 32768KiB, and 31.9 MiB (one slab) at `MAX_HINT_BUFFERS=1`. Each was flat across 200,000 hints and 0.4 GB of hint files.
- **The first slab exists before any hint (A3, B3e step 2).** An idle node creates it about RING_DELAY after start, through `BatchlogManager` → `HintsService.flushAndFsyncBlockingly` → `HintsWriteExecutor$PartiallyFlushBufferPoolTask` → `HintsBufferPool.currentBuffer()`. A baseline "with no hints yet" therefore already contains one slab. This happens even with `hinted_handoff_enabled: false`. The literal delta after the first hint (32.2 MiB) is the second slab.
- **Only 2 of the 3 default slabs were ever needed.** The flush kept up and recycled 12–13 slabs per lifetime, so B3f's 96 MiB bound is an upper bound that was not reached.
- **`MAX_HINT_BUFFERS=1` deadlocks the hint path for good** (B3f bullet 4 said "writers briefly block while the flush completes"; refuted in that part).
  - The single slab filled after 15,849 hints. The switching writer then parked in `reserveBuffers.take()` (`HintsBufferPool.java:118`) while holding the pool monitor, and the full slab is flushed only after `switchCurrentBuffer()` returns (`:79-80`). Nothing ever offered a slab back.
  - Consequences: 31 more `MutationStage` threads blocked on the monitor; MutationStage showed 32 active and 41,483 pending; local writes stopped; `nodetool stopdaemon` hung.
  - The guided `MAX_HINT_BUFFERS` case used n ≥ 2 throughout, which is why it never saw this. Worth a JIRA check as an upstream issue candidate (a property value of 1 makes a node stop writing).
- **The 17 MiB write (B3f bullet 6, R2) never reaches `max_mutation_size`.** The CQL transport refuses it first.
  - Under protocol 4: `native_transport_max_frame_size` (16 MiB, `Envelope.java:429`, "Request is too big").
  - Under v5: `native_transport_max_message_size`, which defaults to min(`max_mutation_size`, heap/10, heap/40).
  - R2's observable claims held (the write fails, no hint is written, no direct change); its naming of the guard did not. A test of that guard through CQL needs a value between `max_mutation_size` and the transport limit. The M4 arm had one by accident: its 8 MiB writes were refused by `Mutation.validateSize` ("Rejected an oversized mutation (8388664/4194304)"), and v4 frames are not checked against the 4 MiB `native_transport_max_message_size`.
- **RSS "rises by about the same amount" (B3f bullet 5)** held within 25 % at the end of the 2 KiB phase in all four lifetimes. After the 8 MiB phase it missed in D-1 (96.6 vs 64.2 MiB) and M32 (199 vs 128 MiB); the cause was not traced.

