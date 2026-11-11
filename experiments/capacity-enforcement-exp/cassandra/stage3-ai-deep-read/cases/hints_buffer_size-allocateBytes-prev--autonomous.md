# hints buffer slab size (`max(2 × max_mutation_size, 32 MiB)`) — verification solution  <!-- file: cases/hints_buffer_size-allocateBytes-prev--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`HintsBuffer.java:187`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBuffer.java#L187) (also covers `HintsBuffer.java:174#1`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code at Meta (`claude --version` prints no version number), 2026-10-26 |
| Estimate | `positive` — every hints buffer is one direct `ByteBuffer` of exactly B = max(2 × `max_mutation_size`, 32 MiB) bytes, and `allocateBytes` refuses any allocation that would run past B (capacity test `HintsBuffer.java:190`, which closes the slab; the target :187 then refuses every later allocation on the closed slab, and :174 turns either refusal into a buffer switch), so the hint bytes held in one buffer, and the off-heap memory of one buffer, are both capped at B. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** The capacity B of a hints buffer slab. It is a derived, runtime-queried value, not a yaml key of its own:
- [`HintsService.java:79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L79) `MIN_BUFFER_SIZE = 32 << 20` (constant, 32 MiB);
- [`HintsService.java:110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L110) `bufferSize = Math.max(DatabaseDescriptor.getMaxMutationSize() * 2, MIN_BUFFER_SIZE)`;
- `max_mutation_size` is the yaml key `max_mutation_size` ([`Config.java:406-407`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L406-L407), KiB-bound data-storage spec, old name `max_mutation_size_in_kb`). Default: `commitlog_segment_size / 2` ([`DatabaseDescriptor.java:898-899`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L898-L899)), so with the default `commitlog_segment_size: 32MiB` M = 16 MiB and B = max(32, 32) = 32 MiB. If set explicitly, `commitlog_segment_size` must be ≥ 2 × M ([`DatabaseDescriptor.java:900-901`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L900-L901)) and < 2048 MiB (`:894-896`).
- B is passed to `HintsBufferPool` ([`HintsService.java:111`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L111)) and to `HintsBuffer.create(slabSize)` → `ByteBuffer.allocateDirect(slabSize)` ([`HintsBuffer.java:75-78`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBuffer.java#L75-L78), `HintsBufferPool.java:142-146`).
- Unit: bytes. Setting it needs a restart (read once in the `HintsService` constructor). B cannot go below 32 MiB through configuration.


**Limit type (2026-10-29).** non-config: runtime-queried. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Off-heap (direct) memory: the bytes of serialized hints held in one buffer before they are flushed to hints files. The operand of the target :187 is `prev`, the slab's allocation position before this hint, which is negative once the slab has been closed; the capacity test at :190 compares `prev + totalSize` (where `totalSize = hintSize + 12`, `HintsBuffer.java:150`) with `slab.capacity()` = B and closes the slab by setting `position = Long.MIN_VALUE` (:192). :174 tests the resulting `offset < 0`.

**A3. Mechanism.**
1. A write that must be hinted reaches `HintsService.write` → `HintsBufferPool.write` ([`HintsService.java:169`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L169), [`HintsBufferPool.java:59-66`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L59-L66)), which computes `hintSize` and calls `allocate`.
2. `HintsBuffer.allocate(int)` rejects a single hint with `totalSize > B/2` with `IllegalArgumentException` ([`HintsBuffer.java:150-157`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBuffer.java#L150-L157)). Through the client path this is unreachable because a mutation larger than M is refused before it is hinted and B/2 ≥ M.
3. `allocateBytes` ([`HintsBuffer.java:183-196`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBuffer.java#L183-L196)) does `position.getAndAdd(totalSize)`; if the slab is already closed (`prev < 0`, **target :187**) it returns −1 (:188); if `prev + totalSize > B` (:190) it sets `position = Long.MIN_VALUE` (:192, closes the slab, so every later caller hits :187) and returns −1 (:193). Without :187, a later caller on a closed slab would get a negative `prev` that passes :190 and return a negative offset.
4. `allocate(int, OpOrder.Group)` (**:174**) sees `offset < 0`, closes the op group and returns `null` ([`HintsBuffer.java:171-180`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBuffer.java#L171-L180)).
5. `HintsBufferPool.allocate` loops: on `null` it calls `switchCurrentBuffer` and, if it won the switch, `flushCallback.flush(current, this)` ([`HintsBufferPool.java:68-82`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L68-L82)). The switch takes a reserve buffer, or creates a new B-sized buffer while `allocatedBuffers < MAX_ALLOCATED_BUFFERS` (default 3, `cassandra.MAX_HINT_BUFFERS`, [`CassandraRelevantProperties.java:351`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L351), `HintsBufferPool.java:41,108-128`), else blocks on `reserveBuffers.take()`.
6. The flush task writes the slab to the per-host hints files, then `recycle()`s the same slab (`slab.clear()`, new `HintsBuffer` over it) and offers it back to the pool ([`HintsWriteExecutor.java:141-154`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java#L141-L154), [`HintsBuffer.java:98-102`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBuffer.java#L98-L102)). Slabs are never freed while the service runs; only `close()` frees the current one (`HintsBufferPool.java:148-151`).
7. Periodic flush every `hints_flush_period` (10 s, [`Config.java:445`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L445), [`HintsService.java:116-121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L116-L121)) drains the current buffer's offset queues to disk but does not reset its position ([`HintsWriteExecutor.java:157-180`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java#L157-L180)), so the slab still fills up and switches.

Overshoot/bypass: the atomic `position` may pass B in the counter (`getAndAdd`), but no byte is written past B — the losing allocation gets −1. The memory of a slab is fully committed at `allocateDirect`, independent of how full it is. Total hints-buffer memory is (allocated buffers) × B ≤ 3 × B; that count is a separate constraint (`MAX_HINT_BUFFERS`), not this one.

**A4. Other consumers.** Other direct memory: the networking and chunk-cache `BufferPool` (`file_cache_size`), memtable off-heap allocators, compression buffers, the hints writer's own buffer (`HintsWriter` session buffer, heap), and the dispatch side (`HintsReader` reads into heap `byte[]`, `Hint.java:239`). Disk used by hints files is governed by `max_hints_size_per_host` / `max_hint_window`, not by B.

**A5. Evidence beyond the source.** `test/unit/org/apache/cassandra/hints/HintsBufferTest.java:69-92` (oversize allocation, B/2 rule) and `:94-132` (a slab sized for exactly N hints accepts N and then `allocate(1)` returns `null`); `HintsBufferPoolTest.java` (Byteman on `reserveBuffers.take()`). JDK `java.lang.management.BufferPoolMXBean` (`java.nio:type=BufferPool,name=direct`) for direct memory: https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html

## B. Verification solution

**B1. Claim under test.** (1) Each hints buffer allocates exactly B = max(2 × `max_mutation_size`, 32 MiB) bytes of direct memory, and (2) the serialized hint bytes accepted into one buffer never exceed B: once the next hint would pass B, the buffer is closed and later hints go to another buffer. The claim is wrong if a slab of another size is allocated, if accepted bytes exceed B, or if direct memory per buffer does not scale with B.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Clone to local disk: `git clone --branch cassandra-5.0.9 --depth 1 <origin or /Users/.../cassandra-src> ~/hb-run && cd ~/hb-run && ant jar build-test`. Test source: `~/hb-run/test/unit/org/apache/cassandra/hints/HintsBufferCapTest.java` (same package, because `HintsBuffer` and `HintsBufferPool` are package-private). Run: `ant testsome -Dtest.name=org.apache.cassandra.hints.HintsBufferCapTest`. JVM options: the default test JVM options from `build.xml`, plus `-XX:MaxDirectMemorySize=1g` (pass via `-Dtest.jvm.args` or edit `build.xml` locally in the clone).

> **Amendment B2a (2026-10-26, stage-4 audit, before any run-1 reading).** On the advisor's machine (macOS 27, arm64; `environment-advisor.md`): the clone is
> `$W/cassandra-run36` (`W=~/Library/Caches/stage4`), a fresh full clone of `~/cassandra-src` at `cassandra-5.0.9` (`b5f2a54210`), built with
> `ant -Dlocal.repository=$W/m2 build-test` (it also builds the jar). The test source is `cassandra/stage4-runtime-verification/harness/hints_buffer_size-allocateBytes-prev--autonomous/HintsBufferCapTest.java`; `unit-run.sh` (B2e) copies it
> into `test/unit/org/apache/cassandra/hints/` for the run and removes it afterwards, so the clone's `git status` stays clean. The JVM option is passed as
> `-Dtest.jvm.args="-XX:MaxDirectMemorySize=1g"` (`build.xml:94`, `:1192`); `build.xml` is not edited.

**B2b. Knobs.** The slab size passed to `HintsBuffer.create(B)`: B ∈ {1 MiB, 32 MiB, 64 MiB}. 32 MiB is the default node value; 64 MiB is the value for `max_mutation_size: 32MiB`; 1 MiB shows the check works independent of the floor. Also one case through `HintsService`'s formula: compute `Math.max(M * 2, 32 << 20)` for M ∈ {8, 16, 32} MiB → 32, 32, 64 MiB.

**B2c. Workload.** In `@BeforeClass`: `SchemaLoader.prepareServer(); SchemaLoader.createKeyspace("hbcap", KeyspaceParams.simple(1), SchemaLoader.standardCFMD("hbcap", "t"))`. Build hints as in `HintsBufferTest.createHint`: one row per mutation with a value of 4,096 random bytes; `hintSize = (int) Hint.serializer.serializedSize(hint, MessagingService.current_version)`, entry e = hintSize + 12 (≈ 4.2 KiB). Case 1 (single buffer): for each B, `HintsBuffer buf = HintsBuffer.create(B)`; loop `try (Allocation a = buf.allocate(hintSize)) { if (a == null) break; a.write(List.of(hostId), hint); n++; }`. B/e ≈ 7,900 at 32 MiB, so the limit is reached and passed. Case 2 (oversize): `buf.allocate(B/2 - 12 + 1)` must throw `IllegalArgumentException`. Case 3 (pool): `new HintsBufferPool(B=32 MiB, (b, p) -> held.add(b))` (a flush callback that never recycles); a writer thread writes hints until 2.5 × B bytes have been offered, a second check thread reads `allocatedBuffers` by reflection after 5 s; the writer is interrupted at the end (it blocks in `take()` once 3 buffers are allocated).

> **Amendment B2c (2026-10-26, stage-4 audit, before any run-1 reading).**
> 1. **Case 3 offers 3.5 × B, not 2.5 × B.** From source, the pool creates a buffer only when the current one is refused and fewer than
>    `MAX_ALLOCATED_BUFFERS` (3) exist (`HintsBufferPool.java:107-134`), so three buffers hold up to 3 × B before a writer reaches `take()` (`:118`).
>    At 2.5 × B the writer finishes inside the third buffer and is never blocked, so B2f's "the writer is blocked" could not hold. At 3.5 × B
>    (⌈3.5 × B / e⌉ hints) it must wait for a fourth buffer.
> 2. **Hints of one fixed size.** The key is the 4-byte `bytes(idx)` (as in `HintsBufferTest.createMutation`), the clustering an 8-character string, the
>    value 4,096 random bytes drawn from `a`–`z` with a fixed seed (the table's `val` is an ascii column; nothing on this path validates it), and every
>    hint has the same timestamp and creation time. `HintsBufferTest.createHint` varies the timestamp with the index, which can change the vint
>    lengths; B2f's "e constant" needs a fixed size. The test records the smallest and largest e it saw.
> 3. **Warm-up before each baseline.** The first `Mutation.serializedSize()` on a thread takes a per-thread direct scratch buffer
>    (`DataOutputBuffer.scratchBuffer`, `Mutation.java:453`). The test thread computes one hint size in `@BeforeClass`, and the case-3 writer thread
>    computes one before the case-3 baseline, so that buffer is not inside any dmem delta.
> 4. **The slab's contents are counted.** After the fill loop the test walks the slab with `consumingHintsIterator(hostId)` and records how many entries
>    it holds and their total bytes (claim 2 of B1: the bytes accepted into the buffer).

**B2d. Observables and instruments.** n (accepted hints per buffer) and Σ = n × e (sum of `totalSize`); `buf.remaining()` after the loop (0, because the slab is closed); `BufferPoolMXBean` named `direct` (`ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)`): `getMemoryUsed()` and `getCount()` read before `create`, after `create`, and after the fill loop; `allocatedBuffers` (reflection) in case 3. Each value printed with `System.out.printf("HBCAP B=%d n=%d sum=%d dmem0=%d dmem1=%d dmem2=%d%n", ...)`. Not observable directly: the native allocation behind `allocateDirect` (only the JDK's accounting).

> **Amendment B2d (2026-10-26, stage-4 audit, before any run-1 reading).** One line per reading, to stdout (it lands in
> `build/test/logs/**/TEST-org.apache.cassandra.hints.HintsBufferCapTest.log`; the run script copies it to `unit/TEST.log`):
> - `HBCAP setup maxDirectMemorySize=<value> directBean=true valueBytes=4096 entryOverhead=12`
> - `HBCAP case=1 B= e= emin= emax= n= sum= remaining= nextNull= alloc1Null= leftover= found= foundBytes= dmem0= dmem1= dmem2= dmem3= cnt0= cnt1= cnt2= cnt3=`,
>   where `dmem0/cnt0` are read after a GC before `create`, `dmem1/cnt1` after `create`, `dmem2/cnt2` after the loop and the `allocate(1)`, and
>   `dmem3/cnt3` after `buf.free()`; `nextNull` is the refusal that ended the loop, `alloc1Null` the following 13-byte request, `leftover` = B − sum.
> - `HBCAP case=2 B= request= threw=<exception class or none> msg=`
> - `HBCAP case=3 B= max= e= offeredTarget= hintsToWrite= hintsWritten= allocatedBuffers= held= writerState= inTake= inSwitch= dmem0= dmem1= cnt0= cnt1=`
>   (read 5 s after the writer starts; `held` = buffers handed to the flush callback; `inTake`/`inSwitch` from the writer's stack), then
>   `HBCAP case=3 end writerAlive= dmemAfterFree= cntAfterFree=`
> - `HBCAP formula M= B=` for M ∈ {8, 16, 32} MiB.
> The test asserts nothing about the case, so every reading reaches the log.

**B2e. Procedure.**
1. Clone and build (B2a). 2. Add `HintsBufferCapTest.java` with cases 1–3 (B2c), one `@Test` per B. 3. Run `ant testsome -Dtest.name=org.apache.cassandra.hints.HintsBufferCapTest 2>&1 | tee ~/hb-unit.log`. 4. `grep HBCAP ~/hb-unit.log`. 5. Free each buffer with `buf.free()` at the end of each test and check `dmem` returns to `dmem0` (± 0).

> **Amendment B2e (2026-10-26, stage-4 audit, before any run-1 reading).** Run `cassandra/stage4-runtime-verification/harness/hints_buffer_size-allocateBytes-prev--autonomous/unit-run.sh` with no argument (one `ant testsome` JVM; one `@Test`
> runs cases 1 and 2 for each B in turn, a second runs case 3 and the formula lines). It logs each command, copies the test log, the XML report and
> the `HBCAP` lines to `$W/logs/hints_buffer_size-allocateBytes-prev--autonomous/unit/`, and removes the test from the clone. Step 5 is done inside
> the test (`dmem3`, and `dmemAfterFree` for case 3).

**B2f. Predictions.** For each B: n = ⌊B / e⌋ exactly (e constant), Σ ≤ B and Σ > B − e; the next allocation returns `null` and `remaining()` = 0; a following `buf.allocate(1)` (13 bytes) also returns `null` whenever B − Σ ≥ 13 (the closed-slab test :187 refuses it although it would fit; with e ≈ 4.2 KiB the leftover is ≥ 13 bytes unless B is an exact multiple of e); `dmem1 − dmem0` = B exactly and `count` +1; `dmem2 = dmem1` (filling does not grow memory). Across B: n(64 MiB) = 2 × n(32 MiB) ± 1, n(1 MiB) = ⌊2^20 / e⌋. Case 2 throws. Case 3: `allocatedBuffers` = 3, never more, direct delta = 3 × B; the writer is blocked.

> **Amendment B2f (2026-10-26, stage-4 audit, before any run-1 reading).** Exact form, derived from `HintsBuffer.java:148-197` and the JDK's accounting
> of `allocateDirect` (one buffer of exactly the requested capacity). For each B ∈ {1,048,576; 33,554,432; 67,108,864}:
> - `emin` = `emax` (= e); n = ⌊B / e⌋; sum = n × e, so B − e < sum ≤ B; `nextNull=true`; `remaining=0`;
> - `alloc1Null=true` when `leftover` ≥ 13 (if `leftover` < 13 the 13-byte request would not fit anyway, and the reading is reported, not used for :187);
> - `found` = n and `foundBytes` = sum;
> - dmem1 − dmem0 = B and cnt1 − cnt0 = 1; dmem2 = dmem1 and cnt2 = cnt1; dmem3 = dmem0 and cnt3 = cnt0;
> - case 2: `threw=java.lang.IllegalArgumentException`.
> Across B: n(64 MiB) ∈ {2 × n(32 MiB), 2 × n(32 MiB) + 1}. Case 3 (B = 32 MiB): `allocatedBuffers` = 3 = `max`, `held` = 2 (the third buffer is
> handed over only after the wait, `HintsBufferPool.java:79-80`), `writerState=WAITING`, `inTake=true`, `hintsWritten` < `hintsToWrite`,
> dmem1 − dmem0 = 3 × B and cnt1 − cnt0 = 3. Formula lines: B = 33,554,432; 33,554,432; 67,108,864.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Σ ≤ B < Σ + e and dmem delta = B for each B, n doubles with B | claim confirmed: per-buffer usage follows B |
| Σ > B for any B | claim wrong: the check does not cap the slab |
| `allocate(1)` after the first `null` succeeds | claim wrong for :187: the closed slab is reopened |
| dmem delta ≠ B (e.g. grows with writes, or larger than B) | claim wrong for the real resource: slab memory is not B |
| n flat across B | claim wrong (the knob does not govern the operand) |
| case 3 `allocatedBuffers` > 3 | not this claim; the `MAX_HINT_BUFFERS` bound fails |
| no `null` within the loop | not confirmed: the limit was never reached (workload too small) |

> **Amendment B2g (2026-10-26, stage-4 audit, before any run-1 reading).** Verdict words and added rows.
> - Row 1 (all of amended B2f's case-1 and case-2 predictions hold for every B) → **Confirmed**. Effect: **caps**.
> - Rows "Σ > B", "`allocate(1)` … succeeds" (with `leftover` ≥ 13), "n flat across B", or `found`/`foundBytes` above n/sum → **Refuted**. Effect:
>   **does not cap**.
> - Row "dmem delta ≠ B" (dmem1 − dmem0 ≠ B with cnt1 − cnt0 = 1, or dmem2 > dmem1) → **Refuted** for the real resource. Effect: **undetermined**.
> - Case 2 does not throw → a failed prediction outside B1's two parts; recorded, and the verdict is at most **Not confirmed**.
> - `emin` ≠ `emax`, or a dmem/cnt delta that also moved `cnt` by more than the slab (another allocator in the window), or dmem3 ≠ dmem0 →
>   **Not confirmed** (the exact-size checks cannot be made). Effect: **undetermined**.
> - No `HBCAP` lines, the test did not run, or `maxDirectMemorySize` ≠ `1g` → **Invalid**.
> - Case 3: `allocatedBuffers` > 3 is "not this claim" (as filed). A case-3 reading off its prediction otherwise (fewer buffers, writer not waiting,
>   direct delta ≠ 3 × B) is recorded and does not change the row, since B1 is about one buffer.

**B2h. Controls.** The dmem readings before/after `create` with no writes (positive control: the instrument moves by B when a slab exists); free at the end restores dmem0 (no leak from other code); case 1 is single-threaded so no other allocator runs between readings; e is fixed so ⌊B/e⌋ is exact.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, two nodes on 127.0.0.1 and 127.0.0.2, each from its own copy of the built clone (`cp -r ~/hb-run ~/hb-n1 ~/hb-n2`), data, commit log and hints under `~/hb-nX/data` on local disk with ≥ 10 GiB free. JVM: `-Xms2g -Xmx2g -XX:MaxDirectMemorySize=2g` (in `conf/jvm-server.options` / `cassandra-env.sh`), JMX on 7199 / 7299. Byteman agent on node 1: `JVM_EXTRA_OPTS="-javaagent:$HOME/hb-n1/build/lib/jars/byteman-4.0.20.jar=script:$HOME/hb.btm,boot:$HOME/hb-n1/build/lib/jars/byteman-4.0.20.jar"` (use the byteman jar version present in `build/lib/jars`). `hb.btm`:
```
RULE slab create
CLASS org.apache.cassandra.hints.HintsBuffer
METHOD create
AT ENTRY
IF true
DO traceln("HBCAP create slabSize=" + $1)
ENDRULE

RULE slab full
CLASS org.apache.cassandra.hints.HintsBuffer
METHOD allocateBytes
AT EXIT
IF $! < 0
DO traceln("HBCAP full totalSize=" + $1 + " cap=" + $0.capacity())
ENDRULE

RULE pool count
CLASS org.apache.cassandra.hints.HintsBufferPool
METHOD createBuffer
AT EXIT
IF true
DO traceln("HBCAP allocatedBuffers=" + $0.allocatedBuffers)
ENDRULE
```
yaml on both: `cluster_name: hbcap`, `seed_provider` with `seeds: "127.0.0.1"`, `listen_address`/`rpc_address` per node, `num_tokens: 16`, `hinted_handoff_enabled: true`, `max_hint_window: 3h`, `hints_directory: <local>`, `file_cache_size: 32MiB`.

> **Amendment B3a (2026-10-26, stage-4 audit, before any run-1 reading).** On the advisor's machine (macOS, arm64; no `setsid`; loopback aliases
> 127.0.0.1–.3 present): both nodes run from the one built clone `$W/cassandra-run36` (never built while a node runs), each with its own
> `CASSANDRA_CONF` and directories (`$W/node-hb1`, `$W/node-hb2`, amendment B4) instead of two copies of the clone. Node 2's `cassandra-env.sh` has
> `JMX_PORT="7299"`. The heap is `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (→ `-Xms2G -Xmx2G`); `-XX:MaxDirectMemorySize=2g` and, on node 1, the agent
> `-javaagent:$BMJAR=script:cassandra/stage4-runtime-verification/harness/hints_buffer_size-allocateBytes-prev--autonomous/hb.btm,boot:$BMJAR` (`BMJAR=$W/cassandra-run36/build/lib/jars/byteman-4.0.20.jar`) are passed in
> `JVM_EXTRA_OPTS`, scoped to `bin/cassandra` only. Each node is a tracked background `bin/cassandra -f` (stdout to `node1.out` / `node2.out`, where
> `traceln` writes). Both yamls get the filed keys plus their own directories, `listen_address`/`rpc_address`, and an explicit
> `commitlog_segment_size` (32MiB on node 2 and in arm (i)), and `auto_bootstrap: false`; `seeds` stays the default `"127.0.0.1:7000"`. `hb.btm` adds two
> rules (amendment B3d). *`auto_bootstrap: false` was added after the cluster shakedown (20,000 writes, arm (i), before the freeze): node 2's
> bootstrap streams `system_auth` by zero-copy `FileChannel.transferTo`, which fails on this host with `java.io.IOException: Operation not permitted`,
> so node 2 never left `UJ`. The ring is empty when node 2 joins, so there is nothing to stream; the change does not touch the hint path.*

**B3b. Knobs.** On node 1 (the hint writer), per run: (i) default — `commitlog_segment_size: 32MiB`, no `max_mutation_size` → B = 32 MiB; (ii) `commitlog_segment_size: 64MiB`, `max_mutation_size: 32MiB` → B = 64 MiB; (iii) `commitlog_segment_size: 128MiB`, `max_mutation_size: 64MiB` → B = 128 MiB. Each needs a full restart (wipe data between runs). Node 2 keeps defaults.

**B3c. Workload.** `CREATE KEYSPACE hb WITH replication = {'class':'SimpleStrategy','replication_factor':2}` via the stress `-schema` option. Phase U (control, node 2 up): `tools/bin/cassandra-stress write n=200000 cl=ONE -col size=FIXED(1024) n=FIXED(1) -schema "replication(factor=2)" keyspace=hb -rate threads=50 -node 127.0.0.1`. Phase D (node 2 stopped by `kill <pid>` after `nodetool -p 7299 drain`): the same command with keyspace `hb` reused (`-schema` unchanged), so every write to a node-2 replica is hinted on node 1. Hint bytes: 200,000 × ~1.1 KiB ≈ 220 MiB ≈ 7 × B at 32 MiB, 1.7 × B at 128 MiB, so every arm fills at least one slab. Duration ≈ 2–5 min per phase.

**B3d. Observables and instruments.** (1) Byteman lines in node 1's `logs/system.log`/stdout (`grep HBCAP`): `slabSize`, `allocatedBuffers`, `full ... cap`. (2) Direct memory on node 1: `nodetool -p 7199 sjk mx -mg -b "java.nio:type=BufferPool,name=direct" -f MemoryUsed` and `-f Count`, every 5 s into a CSV during each phase. (3) `du -sb <hints_directory>` every 5 s (to show hints go to disk and are not bounded by B). Not observable directly: which direct buffers belong to the hints pool other than via the Byteman counters.

> **Amendment B3d (2026-10-26, stage-4 audit, before any run-1 reading).**
> 1. **JMX sampler instead of `sjk` and `du -sb`.** `nodetool sjk mx` starts a JVM per call and exits 0 even on failure; `du -sb` is GNU-only. The sampler
>    `cassandra/stage4-runtime-verification/harness/hints_buffer_size-allocateBytes-prev--autonomous/HbJmx.java` keeps one JMX connection to node 1 (port 7199) and writes one line every **1 s**: epoch ms, the direct pool's `MemoryUsed`
>    and `Count`, the mapped pool's `MemoryUsed` (commit-log segments; reported only), `org.apache.cassandra.metrics:type=Storage,name=TotalHints`
>    `Count` (`HintsService.java:171`), and the exact byte sum and number of `*.hints` files in node 1's hints directory.
> 2. **Two more observation-only Byteman rules,** `slab dmem before` (entry of `HintsBuffer.create`) and `slab dmem after` (its exit), print the direct
>    pool's `MemoryUsed` and `Count` (`jdk.internal.misc.SharedSecrets.getJavaNioAccess().getDirectBufferPool()`, the counters behind the JMX bean)
>    around each slab allocation: `HBCAP dmem before slabSize=<B> used=<bytes> count=<n>` and `HBCAP dmem after cap=<B> used=<bytes> count=<n>`.
>    The per-slab step is used(after) − used(before). Reason (group A, "real resource"): the filed ΔD − ΔU cannot isolate slab memory (amendment B3f).
>    `hb.btm` = the three filed rules unchanged + these two.
> 3. **Phase boundaries** are written to `summary.txt` as epoch ms and as byte offsets of node 1's stdout (`node1.out`, where the `HBCAP` lines go), so
>    each line is placed in a phase by its offset.
> 4. **Definitions.** S0 = median direct `MemoryUsed` over the samples in the 15 s quiet window before phase D starts (node 2 DN, no load; amendment B3e).
>    S1 = median over the samples in the last 15 s of the 30 s tail after phase D. k0 = the largest `allocatedBuffers` printed before phase D starts
>    (0 if none); k1 = the largest printed by the end of the tail. ΔU and ΔD are as filed (peak − last sample before the phase; ΔD's window includes
>    the tail) and are reported only. TotalHints Δ(D) = its value at the tail's end − its value at phase D's start.

**B3e. Procedure.** Per knob value: 1. wipe data, set yaml, start node 1 then node 2, wait for `nodetool status` UN/UN. 2. Start the 5 s sampler. 3. Phase U; record direct-memory trace. 4. Wait 60 s, drain and kill node 2; wait until `nodetool status` on node 1 shows DN. 5. Phase D; keep sampling 30 s after it ends. 6. `grep HBCAP` node 1's log. 7. Stop sampler; `nodetool drain` + kill node 1; start nothing else. Repeat for (ii), (iii).

> **Amendment B3e (2026-10-26, stage-4 audit, before any run-1 reading).** One script, `cassandra/stage4-runtime-verification/harness/hints_buffer_size-allocateBytes-prev--autonomous/cluster-run.sh`, runs the three arms in order
> (i), (ii), (iii). Per arm it does steps 1–7 as filed, with these specifics: the sampler (amendment B3d) starts 5 s before phase U and stops at the
> end of the tail; after node 2 shows DN on node 1, a **15 s quiet window** (S0) precedes phase D; after phase D, a **30 s tail** (S1 = its last
> 15 s). Node 2 is stopped by `nodetool -p 7299 drain` and `kill`; node 1 by `nodetool -p 7199 drain` and `kill`. The script stops at the first
> failed step (a node not UN/running within 360 s, node 2 not DN within 60 s, a daemon left after an arm) and always stops every node it started.
> Both node directories are wiped between arms. Logs per arm: `$W/logs/hints_buffer_size-allocateBytes-prev--autonomous/cluster/arm-<a>/`.

**B3f. Predictions.** For each arm with B_arm: every `HBCAP create slabSize` = B_arm (33,554,432 / 67,108,864 / 134,217,728); `allocatedBuffers` ≤ 3 and ≥ 2 in phase D (≥ 220 MiB of hints passes one slab); each `full` line has `cap` = B_arm. Direct memory: let ΔU = peak − start in phase U, ΔD = peak − start in phase D; ΔD − ΔU = k × B_arm ± 8 MiB where k is the last `allocatedBuffers` printed. The ratio of ΔD − ΔU between arms (ii)/(i) ≈ 2 and (iii)/(i) ≈ 4 when k is equal. Hints directory grows to ≈ 220 MiB in every arm (not bounded by B).

> **Amendment B3f (2026-10-26, stage-4 audit, before any run-1 reading).** The filed direct-memory relation "ΔD − ΔU = k × B_arm ± 8 MiB, k = the last
> `allocatedBuffers` printed" is wrong from source, independent of any reading:
> (a) the first slab exists before phase U — the periodic flush runs every `hints_flush_period` (10 s, `HintsService.java:116-121`) and calls
> `bufferPool.currentBuffer()` (`HintsWriteExecutor.java:166-168`), which creates the first buffer on an idle node (`HintsBufferPool.java:93-105`) —
> so k counts a slab that phase D does not add;
> (b) ΔU includes internode buffers taken from the networking `BufferPool`, whose chunks stay allocated after phase U (`BufferPool.java:74, 128, 385`)
> and which phase D, with node 2 down, does not need again; subtracting ΔU removes memory phase D never re-allocates.
> Replacement, for each arm with B_arm ∈ {33,554,432; 67,108,864; 134,217,728}:
> - **P1** every `HBCAP create slabSize` = B_arm and every `HBCAP dmem after cap` = B_arm;
> - **P2** every `HBCAP full … cap` = B_arm, and at least one `full` line lies after phase D's start offset;
> - **P3** k1 ≤ 3 and k1 ≥ 2 (k0 is expected to be 1, the periodic flush's slab; P5 uses the observed k0);
> - **P4** for every slab creation, used(after) − used(before) = B_arm and count(after) − count(before) = 1 (a pair whose count step is not 1 included
>   another buffer; it is reported and not used);
> - **P5** S1 − S0 = (k1 − k0) × B_arm ± 8 MiB (8 MiB = one macro chunk of the networking `BufferPool`, 64 × 128 KiB, `BufferPool.java:128, 385`,
>   the granularity of the other direct allocator that can still grow in phase D);
> - **P6** across arms, the per-slab step of (ii) and (iii) is 2 × and 4 × that of (i) (follows from P4);
> - **P7** TotalHints Δ(D) ≥ 0.95 × 200,000 (with RF 2 on two nodes every phase-D write has node 2 as a replica); the hints directory at the tail's
>   end holds ≥ B_arm bytes in every arm, and the three arms' values are within ±10 % of their mean (hints on disk are not bounded by B);
> - **P8** both stress phases report 200,000 partitions and 0 errors.
> ΔU, ΔD (and their difference) are reported only.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| slabSize = B_arm, ΔD − ΔU = k·B_arm, scaling 1:2:4 | claim confirmed on the node |
| slabSize ≠ B_arm (e.g. always 32 MiB) | claim wrong: B is not derived from `max_mutation_size` as traced |
| ΔD − ΔU not a multiple of B_arm, or larger than 3 × B_arm | claim wrong for the real resource: hints memory not governed by B |
| no `full` line in phase D | not confirmed: the slab was never filled (workload too small) |
| ΔU and ΔD equal (no hints buffer at all) | not confirmed: hints were not written (check node 2 really DN) |

> **Amendment B3g (2026-10-26, stage-4 audit, before any run-1 reading).** The rows above are replaced by these, read against amended B3f:
> 1. P1–P5, P7 and P8 hold in all three arms → **Confirmed** (claim confirmed on the node). Effect: **caps**.
> 2. Any `create slabSize` ≠ B_arm (e.g. always 32 MiB) → **Refuted**: B is not derived from `max_mutation_size` as traced. Effect: **does not cap**.
> 3. Any `full … cap` ≠ B_arm, or a P4 step ≠ B_arm with a count step of 1, or `dmem after cap` ≠ B_arm → **Refuted** (the check or the slab memory
>    is not B). Effect: **does not cap**.
> 4. P1–P4 hold but P5 fails (another direct consumer moved in phase D, which the settled measure cannot separate) → **Not confirmed**. Effect:
>    **undetermined**.
> 5. No `full` line after phase D's start in some arm → **Not confirmed**: the slab was never filled (workload too small). Effect: **undetermined**.
> 6. TotalHints Δ(D) < 0.95 × 200,000, or the hints directory does not grow → **Not confirmed**: hints were not written (check node 2 DN). Effect:
>    **undetermined**.
> 7. k1 > 3 → not this claim; the `MAX_HINT_BUFFERS` bound fails (recorded; the row is decided by the others). k1 < 2 with a `full` line present →
>    **Not confirmed**.
> 8. A node did not start, the agent did not load (no `HBCAP create` line before phase U) or logged a rule error, node 1 died, stress reported errors,
>    or S0 or S1 has fewer than 10 samples → **Invalid**.
> The arm-level rows combine as: the tier is Confirmed only if every arm is; any Refuted arm makes the tier Refuted; otherwise the weakest row holds.

**B3h. Controls.** Phase U on the same node and workload separates direct memory used by networking and memtables from the hints slabs; the Byteman count k ties the direct-memory step to buffer creations; the hints directory trace shows hints were produced; 1:2:4 scaling across arms rules out a constant unrelated allocation. Phase U is also the positive control for the instrument: it shows the sampler sees direct-memory changes from other allocators.

> **Amendment B3h (2026-10-26, stage-4 audit, before any run-1 reading).** The per-slab `dmem` lines tie each direct-memory step to one creation; S0 and S1 are
> taken with no load (quiet window, tail), so transient buffers of the stress load and of flushes are not in them. Phase U stays the instrument's
> positive control (the sampler moves with other allocators) and reports ΔU.

**B4. Risks and cleanup.** Hints ≤ ~250 MiB per arm and data ≤ 1 GiB per node, all under `~/hb-n*` on local disk; never in the shared clone. After each arm: `nodetool drain` and kill both nodes, `pgrep -f CassandraDaemon` must print nothing, `pgrep -f cassandra-stress` nothing; `rm -rf ~/hb-n*/data` between arms and `rm -rf ~/hb-run ~/hb-n1 ~/hb-n2` at the end. The unit test JVM exits with the Ant run.

> **Amendment B4 (2026-10-26, stage-4 audit, before any run-1 reading).** On this host the nodes are `$W/node-hb1` and `$W/node-hb2` (each with its own
> `conf/`, `data/`, `commitlog/`, `hints/`, `saved_caches/`, `cdc_raw/`, `logs/`), wiped between arms and at the end. The process check uses a pattern
> built so the checking command never matches itself. The run clone `$W/cassandra-run36` is kept (as for every case on this host) with a clean
> `git status`.

## C. Sources read

- `src/java/org/apache/cassandra/hints/HintsBuffer.java`
- `src/java/org/apache/cassandra/hints/HintsBufferPool.java`
- `src/java/org/apache/cassandra/hints/HintsService.java`
- `src/java/org/apache/cassandra/hints/HintsWriteExecutor.java`
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (lines 885-915, 2827-2830)
- `src/java/org/apache/cassandra/config/Config.java` (lines 406-407, 444-445)
- `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java` (line 351)
- `conf/cassandra.yaml`
- `test/unit/org/apache/cassandra/hints/HintsBufferTest.java`
- https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1** (advisor's machine; [results](../../stage4-runtime-verification/results/hints_buffer_size-allocateBytes-prev--autonomous.md);
frozen at sha256 `198eb1ce…13a2` after thirteen audit amendments; uncommitted).
- **Unit: Confirmed — caps** (B2g row 1).
  - At B = 1, 32 and 64 MiB a slab took exactly ⌊B/e⌋ entries of 4,173 B (251, 8,040, 16,081), at most B bytes.
  - After its first refusal it refused a 13-byte request too (`:187`).
  - Its direct memory was exactly B (Count +1), it did not grow while filling, and it was back to baseline after `free()`.
  - A hint over B/2 threw. The pool held 3 × B with the writer waiting in `take()`.
- **Cluster: Confirmed — caps** (B3g row 1). Two nodes; node 1 has `max_mutation_size` unset, 32MiB and 64MiB.
  - Every slab and every refusal (66 / 45 / 37 `full` lines) was at B = 32 / 64 / 128 MiB.
  - Per-slab direct steps were exactly B (1 : 2 : 4). The settled step over phase D was B + 0.14 / 0.29 / 0.14 MB.
  - 250,000 hints (274 MB on disk) were written in every arm; on-disk hints are not bounded by B.
- **Audit findings for stage 3:**
  - The filed cluster relation ΔD − ΔU = k × B is wrong from source. The first slab is created before any hint by the 10 s periodic flush
    (`HintsWriteExecutor.java:166-168` → `HintsBufferPool.currentBuffer()`), and ΔU contains networking-pool chunks that stay allocated. It was
    replaced by per-slab direct steps and a settled step.
  - Case 3 at 2.5 × B could never block the writer (three buffers hold 3 × B).
  - cassandra-stress adds a warm-up (n/4, at most 50,000 writes), so phase D wrote 250,000 hints, not 200,000.
- **Host finding:** zero-copy bootstrap streaming fails on this Mac (`transferTo`: Operation not permitted), so node 2 needs `auto_bootstrap: false`.
