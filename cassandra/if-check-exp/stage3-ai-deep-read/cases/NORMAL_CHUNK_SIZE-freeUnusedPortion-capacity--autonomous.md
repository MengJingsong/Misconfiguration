# NORMAL_CHUNK_SIZE — verification solution  <!-- file: cases/NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/memory/BufferPool.java:1521` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.305, 2026-10-22 |
| Estimate | `negative`. The check at :1521 (`if (size == capacity) return;` in `Chunk.freeUnusedPortion`) compares a buffer's limit and capacity, each rounded up to the chunk's slot unit (derived from `NORMAL_CHUNK_SIZE`). It is a release-side guard that decides whether any whole slot can be given back. It never refuses or bounds an allocation, and it never changes how much direct memory the pool has reserved. |
| Ground | Both outcomes of the check leave `memoryAllocated` (the pool's reserved off-heap) untouched. The `return` branch frees nothing, and the other branch only flips bits in an already-allocated chunk (`BufferPool.java:1532-1541`). The guard exists for correctness: with `slotCount == 0`, the expression `0xffffffffffffffffL >>> (64 - 0)` equals `-1L` (Java masks shift distances to 6 bits), which would mark all 64 slots free. The memory cap of the pool is a different check, `memoryUsageThreshold` at `BufferPool.java:443` (`networking_cache_size` / `file_cache_size`). The slot unit sets only the granularity of internal slack (< 1 unit per buffer), not a ceiling on usage. |

## A. Constraint trace

**A1. The constraint.** At the target, the limit-side operand is `capacity`, which is `roundUp(buffer.capacity())` (`BufferPool.java:1520`). It is compared with `size = roundUp(buffer.limit())` (`:1519`). `Chunk.roundUp(v)` rounds to `unit()` (`:1483-1486`), `unit() = 1 << shift` (`:1348-1351`), and `shift = numberOfTrailingZeros(slab.capacity() / 64)` (`:1185`). The slab capacity is fixed at chunk creation:
- **Normal chunk:** `NORMAL_CHUNK_SIZE` = 128 KiB (`BufferPool.java:128`, `public static final int NORMAL_CHUNK_SIZE = 128 << 10;`), sliced from the macro chunk at `:474`/`:478`. The unit is 2048 B (= `NORMAL_ALLOCATION_UNIT`, `:129`).
- **Tiny chunk:** `TINY_CHUNK_SIZE = NORMAL_ALLOCATION_UNIT` = 2048 B (`:130`), taken from a normal chunk at `:796`. The unit is 32 B (= `TINY_ALLOCATION_UNIT`, `:131`).

So the constraint is the hard-coded **constant `NORMAL_CHUNK_SIZE`** (`BufferPool.java:128`). The tiny unit derives from it too. Unit: bytes. The default is the literal `128 << 10`. It cannot be set: no yaml key, no `-D` property, no JMX. Changing it needs a source change and a rebuild. `MACRO_CHUNK_SIZE = 64 * NORMAL_CHUNK_SIZE` = 8 MiB (`:385`). The javadoc there says "1 MiB", which is stale; the arithmetic gives 8 MiB.

**A2. What it caps.** Nominally, off-heap (direct) memory held by pooled buffers. The quantity at the check is the buffer's rounded capacity, i.e. the number of 2 KiB (or 32 B) slots the buffer holds, compared with the slots its live data (`limit`) needs. The check does not compare usage against any ceiling. It decides whether `capacity - size >= 1 unit`, i.e. whether there is anything to return.

**A3. Mechanism.**
1. Callers that over-allocate with `getAtLeast` and then trim are: `FrameEncoder.Payload.finish()` (`net/FrameEncoder.java:98-104`, used by internode `OutboundConnection` `:782/:810/:838` and by native-protocol v5 `transport/Flusher.java:204`), `FrameEncoderLZ4.encode` (`net/FrameEncoderLZ4.java:77,104`), `FrameDecoder.channelRead` (`net/FrameDecoder.java:272`), and `AsyncStreamingOutputPlus.writeToChannel` (`net/AsyncStreamingOutputPlus.java:140`). All of them use `BufferPools.forNetworking()`.
2. `BufferPool.putUnusedPortion` (`:249-258`). If the buffer is not exactly direct, nothing happens. If `limit == 0`, the whole buffer is `put`. Otherwise it calls `LocalPool.putUnusedPortion`.
3. `LocalPool.putUnusedPortion` (`:877-891`). If `chunk == null` (an unpooled overflow buffer), it only does `updateOverflowMemoryUsage(-(capacity - limit))` and returns, and **the buffer is not shrunk** (see the bypass below). Otherwise it calls `chunk.freeUnusedPortion(buffer)` and then `memoryInUse += newCapacity - originalCapacity`.
4. `Chunk.freeUnusedPortion` (`:1517-1543`):
   - `size == capacity` at **:1521** returns immediately. No slot is freed, and capacity and metrics are unchanged.
   - Otherwise it computes the slot `position` above `size` and `slotCount = (capacity - size) >> shift`, CAS-ORs those bits into `freeSlots` (`:1532-1541`), and sets the buffer capacity to `size` (`:1542`). The freed slots go back to the same chunk and can be reused by the owning `LocalPool`. `memoryAllocated` is never touched.
   - Why the guard is needed: with `slotCount == 0`, `0xffffffffffffffffL >>> 64` is `-1L` (JLS §15.19), so without the return every slot of the chunk would be OR-ed free. The `assert next == (cur ^ shiftedSlotBits)` at `:1538` would trip under `-ea`.
5. The real cap is `GlobalPool.allocateMoreChunks` (`:438-456`). If `memoryAllocated + MACRO_CHUNK_SIZE > memoryUsageThreshold`, it returns null, and `LocalPool.get` falls back to `allocate(size, OFF_HEAP)` (`:927-944`, `:224-230`), a plain `ByteBuffer.allocateDirect` counted as overflow. The threshold is `networking_cache_size` (`BufferPools.java:44-45`; default `min(128, maxHeap/16 MiB)` at `config/DatabaseDescriptor.java:573-574`) or `file_cache_size` (`BufferPools.java:38-39`).

Bypass and overshoot:
- Requests over `NORMAL_CHUNK_SIZE` are never pooled (`:940`, `:910`).
- **Accounting defect in the overflow branch:** `LocalPool.putUnusedPortion` subtracts `capacity - limit` from `overflowMemoryUsage` without shrinking or freeing anything (`:882-885`). The later `put` subtracts the full `capacity` (`:808-812`). Each trimmed overflow buffer therefore makes `OverflowSize` drift down by `capacity - limit`, and the metric can go negative.
- For a buffer from `get(size)` (not `getAtLeast`), `capacity` is not slot-aligned. The check then compares rounded values, but `memoryInUse` changes by raw capacity bytes (`:890`), not by freed slot bytes.

**A4. Other consumers.** Other users of direct memory: chunk-cache `BufferPool` (`file_cache_size`), Netty's own allocators, off-heap memtables, compression buffers, `FileUtils`/mmap users, and overflow `allocateDirect` from both pools. All direct `ByteBuffer`s, including the 8 MiB+4 KiB slabs (`allocateDirectAligned`, `BufferPool.java:1095-1101`), are bounded only by `-XX:MaxDirectMemorySize`.

**A5. Evidence beyond the source.**
- Existing test `test/unit/org/apache/cassandra/utils/memory/BufferPoolTest.java:1021-1050` (`testPuttingUnusedPortion`) exercises exactly this guard on tiny units: "the unused portion was too small to be returned, the buffer remains unchanged".
- `conf/cassandra.yaml:730-738` documents `networking_cache_size` as the cap for this pool.
- JLS §15.19 (shift distance masked with `0x3f` for `long`): https://docs.oracle.com/javase/specs/jls/se11/html/jls-15.html#jls-15.19
- `java.nio:type=BufferPool,name=direct` MXBean: https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html

## B. Verification solution

**B1. Claim under test.** The check at `BufferPool.java:1521`, whose operand `capacity` comes from `NORMAL_CHUNK_SIZE`, does not cap memory. Whatever its outcome, the networking pool's reserved off-heap (`memoryAllocated` = `Size − OverflowSize`) is unchanged by the call. The pool's ceiling is set only by `memoryUsageThreshold` (`networking_cache_size`), in whole 8 MiB macro chunks. The claim is refuted if any trim changes `memoryAllocated` or the process's direct memory, or if pooled bytes ever exceed `floor(threshold / 8 MiB) * 8 MiB`.

### B2. Unit tier

**B2a. Environment and build.** JDK 11.0.32.1, Ant 1.10.12, on local disk:
```
mkdir -p /tmp/s3bp && cd /tmp/s3bp
<repo>/cassandra/if-check-exp/stage4-runtime-verification/copy-source.sh cassandra
cd cassandra && ant jar        # also builds test deps on first testsome
```
Test source: `/tmp/s3bp/cassandra/test/unit/org/apache/cassandra/utils/memory/FreeUnusedPortionProbeTest.java`, in the same package so that it can reach the package-private `Chunk`, `Chunk.roundUp`, `Chunk.free`, and `Chunk.getParentChunk`. Use the default test JVM options from `build.xml` (`-ea` is on).

**B2b. Knobs.**
1. Slot unit: normal chunk (2048 B) vs tiny chunk (32 B), picked by request size (> 1024 B normal, ≤ 1024 B tiny, `BufferPool.java:906-918`). The constant itself cannot be changed without editing source, and these are the two units it yields.
2. Buffer `limit` relative to the rounded capacity: equal, one byte above a unit boundary, exactly on a boundary, and minimal.
3. For the positive control: `memoryUsageThreshold` = 8 MiB vs 16 MiB (constructor argument), and trim on vs off.

**B2c. Workload.** These are single-thread probe rows. Each row gets a buffer, sets the limit, calls `putUnusedPortion`, records the readings, then `put`s the buffer.

| Row | Get | cap before | limit | expected `size` / `capacity` at :1521 |
|---|---|---|---|---|
| N1 | `getAtLeast(8192)` | 8192 | 8192 | 8192 / 8192 (return) |
| N2 | `getAtLeast(8192)` | 8192 | 6145 | 8192 / 8192 (return) |
| N3 | `getAtLeast(8192)` | 8192 | 6144 | 6144 / 8192 (free 1 slot) |
| N4 | `getAtLeast(8192)` | 8192 | 1 | 2048 / 8192 (free 3 slots) |
| N5 | `get(5000)` | 5000 | 4097 | 6144 / 6144 (return) |
| N6 | `get(5000)` | 5000 | 4096 | 4096 / 6144 (free 1 slot) |
| T1 | `getAtLeast(100)` | 128 | 97 | 128 / 128 (return) |
| T2 | `getAtLeast(100)` | 128 | 96 | 96 / 128 (free 1 slot, 32 B) |
| O1 | `get(262144)` (overflow) | 262144 | 1024 | check not reached (`chunk == null`) |

Positive control, with the pool cap binding. A loop requests `getAtLeast(65536)` until `Chunk.getParentChunk(b) == null`, i.e. the first overflow.
- (a) No trim, threshold 8 MiB. Each buffer takes 32 slots of a 128 KiB chunk, so 2 per chunk × 64 chunks = **128** pooled buffers.
- (b) Trim to `limit = 2048` after each get. The guard is false (2048 ≠ 65536), so 31 slots are freed. 64 KiB runs must start at a 4-aligned index ≤ 32 (`:1428-1440`), so each chunk serves buffers at slots 0, 4, …, 32: 9 per chunk × 64 = **576**.
- (c) No trim, threshold 16 MiB: **256**.

**B2d. Observables and instruments.** Read in-process:
- Per row: `chunk.unit()`, `chunk.roundUp(limit)`, `chunk.roundUp(capBefore)`, the guard outcome, `b.capacity()` after, Δ`chunk.free()`, Δ`pool.usedSizeInBytes()`, Δ`pool.sizeInBytes()`, and Δ`pool.overflowMemoryInBytes()`.
- Positive control: pooled-buffer count before the first overflow, and `sizeInBytes() − overflowMemoryInBytes()` at that point.
- Print one CSV line per row to stdout. Ant writes it to `build/test/output/TEST-...FreeUnusedPortionProbeTest.xml`.
- Not observable here: real RSS. The unit tier reads only pool bookkeeping. Direct memory is observed in B3.

**B2e. Procedure.**
1. Write the test file:
```java
package org.apache.cassandra.utils.memory;

import java.nio.ByteBuffer;
import org.junit.After;
import org.junit.Test;
import org.apache.cassandra.io.compress.BufferType;
import static org.junit.Assert.*;

public class FreeUnusedPortionProbeTest
{
    BufferPool pool;
    @After public void tearDown() { if (pool != null) pool.unsafeReset(); }

    private void row(String id, int req, boolean atLeast, int limit)
    {
        ByteBuffer b = atLeast ? pool.getAtLeast(req, BufferType.OFF_HEAP) : pool.get(req, BufferType.OFF_HEAP);
        BufferPool.Chunk c = BufferPool.Chunk.getParentChunk(b);
        int capBefore = b.capacity();
        long used0 = pool.usedSizeInBytes(), size0 = pool.sizeInBytes(), ovf0 = pool.overflowMemoryInBytes();
        int free0 = c == null ? -1 : c.free();
        String op = c == null ? "unit=-,size=-,capacity=-,guard=-"
                  : "unit=" + c.unit() + ",size=" + c.roundUp(limit) + ",capacity=" + c.roundUp(capBefore)
                    + ",guard=" + (c.roundUp(limit) == c.roundUp(capBefore));
        b.limit(limit);
        pool.putUnusedPortion(b);
        System.out.println("ROW," + id + "," + op + ",capBefore=" + capBefore + ",capAfter=" + b.capacity()
            + ",dFree=" + (c == null ? 0 : c.free() - free0) + ",dUsed=" + (pool.usedSizeInBytes() - used0)
            + ",dSize=" + (pool.sizeInBytes() - size0) + ",dOverflow=" + (pool.overflowMemoryInBytes() - ovf0));
        long sizeBeforePut = pool.sizeInBytes();
        pool.put(b);
        System.out.println("PUT," + id + ",overflowAfterPut=" + pool.overflowMemoryInBytes() + ",sizeBeforePut=" + sizeBeforePut);
    }

    @Test public void probeRows()
    {
        pool = new BufferPool("probe", 8L << 20, false);
        row("N1", 8192, true, 8192); row("N2", 8192, true, 6145);
        row("N3", 8192, true, 6144); row("N4", 8192, true, 1);
        row("N5", 5000, false, 4097); row("N6", 5000, false, 4096);
        row("T1", 100, true, 97);    row("T2", 100, true, 96);
        row("O1", 262144, false, 1024);
        int zero = 0; assertEquals(-1L, 0xffffffffffffffffL >>> (64 - zero)); // why the guard exists
    }

    private int fill(long threshold, boolean trim)
    {
        pool = new BufferPool("ctl", threshold, false);
        int n = 0;
        while (true)
        {
            ByteBuffer b = pool.getAtLeast(65536, BufferType.OFF_HEAP);
            if (BufferPool.Chunk.getParentChunk(b) == null) { pool.put(b); break; }
            if (trim) { b.limit(2048); pool.putUnusedPortion(b); }
            n++;
        }
        long pooled = pool.sizeInBytes() - pool.overflowMemoryInBytes();
        System.out.println("CTL,threshold=" + threshold + ",trim=" + trim + ",buffers=" + n + ",pooledBytes=" + pooled);
        pool.unsafeReset(); pool = null;
        return n;
    }

    @Test public void positiveControl()
    {
        fill(8L << 20, false); fill(8L << 20, true); fill(16L << 20, false);
    }
}
```
> **Stage-4 runbook-defect fix D1 (2026-10-22, run 1 attempt 1).** As listed, `fill()` calls `pool.unsafeReset()` while every buffer it got is still held. With `-ea` on, the first `fill` then fails in `Chunk.recycleFully` ("Status of chunk … was not EVICTED", `BufferPool.java:1308`, reached from `LocalPool.unsafeRecycle`). The fix: `fill()` keeps the buffers it got in a list and `put`s them all back after printing its CTL line and before `unsafeReset()`. Nothing that is read changes, and B2f/B2g are unchanged. The unit tier restarted from its beginning, and attempt 1 is not counted.

2. `cd /tmp/s3bp/cassandra && ant testsome -Dtest.name=org.apache.cassandra.utils.memory.FreeUnusedPortionProbeTest`
3. `grep -E '^(ROW|PUT|CTL),' build/test/output/TEST-org.apache.cassandra.utils.memory.FreeUnusedPortionProbeTest.xml`

   > **Stage-4 runbook-defect fix D2 (2026-10-22, run 1 attempt 2).** On a passing run the XML holds no standard output, so the grep finds nothing. The lines are taken from the ant console output of step 2 instead, logged by the harness's `unit-run.sh` (`[junit-timeout] … ROW,…`). Attempt 2's test passed, but no line was extracted from the XML. The unit tier restarted from its beginning, and attempt 2 is not counted.
4. As a reference, also run the shipped `-Dtest.name=org.apache.cassandra.utils.memory.BufferPoolTest -Dtest.methods=testPuttingUnusedPortion`.

**B2f. Predictions.** For every ROW, `dSize = 0`, and `sizeBeforePut` stays at 8388608 (one macro chunk) after N1. Overflow row O1 is the only one that adds to `Size`, by +262144 at `get`.

| Row | guard | capAfter | dFree | dUsed | dOverflow |
|---|---|---|---|---|---|
| N1 | true | 8192 | 0 | 0 | 0 |
| N2 | true | 8192 | 0 | 0 | 0 |
| N3 | false | 6144 | +2048 | −2048 | 0 |
| N4 | false | 2048 | +6144 | −6144 | 0 |
| N5 | true | 5000 | 0 | 0 | 0 |
| N6 | false | 4096 | +2048 | −904 | 0 |
| T1 | true | 128 | 0 | 0 | 0 |
| T2 | false | 96 | +32 | −32 | 0 |
| O1 | n/a | 262144 (unchanged) | 0 | −261120 | −261120 |

After O1's put, `overflowAfterPut = −261120` (the accounting defect). The shift assertion passes (`-1L`).

CTL lines:
| threshold | trim | buffers | pooledBytes |
|---|---|---|---|
| 8 MiB | no | 128 | 8388608 |
| 8 MiB | yes | 576 | 8388608 |
| 16 MiB | no | 256 | 16777216 |

> **Stage-4 audit amendment U1 (2026-10-22), an error in the prediction found before any reading.** "For every ROW, `dSize = 0`" cannot hold for O1: its trim subtracts `capacity − limit` from `overflowMemoryUsage` (`BufferPool.java:883-885`), and `sizeInBytes()` includes that counter (`:274-277`). The prediction is therefore: **`dSize = 0` for the pooled rows N1–N6, T1–T2**; for **O1, `dSize = dOverflow = dUsed = −261120`** (bookkeeping only; nothing is freed). `sizeBeforePut` is 8388608 for N1–T2; for O1 the harness also prints `sizeAfterGet` = 8650752 (8 MiB + 262144), and `sizeBeforePut` = 8389632. B2g's second row ("any row with `dSize ≠ 0`") applies to N1–T2 only; O1 is read by the O1 rows added in U3.
>
> **Stage-4 audit amendment U2 (2026-10-22), the real resource.** B2d reads only pool bookkeeping. The harness copy of the test (`stage4-runtime-verification/harness/NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous/FreeUnusedPortionProbeTest.java`) also reads the JVM's direct memory (`BufferPoolMXBean` "direct", `MemoryUsed`, in the same JVM): every ROW line carries **`dDirect`**, the change across the `putUnusedPortion` call, and every CTL line carries **`directDelta`** (direct memory at the first overflow minus before the first `get`), `k = pooledBytes / 8 MiB`, and the page size. Predictions: **`dDirect = 0` for all nine rows**, O1 included (the overflow buffer is not shrunk, `capAfter = 262144`); **`directDelta = k × (8 MiB + pageSize)`**: with pageSize 4096, 8,392,704 for (a) and (b) and 16,785,408 for (c) (each macro chunk is `allocateDirect(8 MiB + pageSize)`, `BufferPool.java:1095-1101`).

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| All rows `dSize = 0`; guard true ⇒ dFree = 0; guard false ⇒ dFree = (capacity − size) | Claim confirmed: the check controls only slot release inside reserved memory. |
| Any row with `dSize ≠ 0`, or a guard-true row with dFree ≠ 0 | Claim refuted: the trim path changes reserved memory, or the guard does not behave as traced. |
| Trimming lets more buffers fit (576 vs 128), yet `pooledBytes` stays 8 MiB, and pooledBytes moves 8→16 MiB with threshold (positive control moves) | Claim confirmed: `memoryUsageThreshold`, not the check, sets the ceiling. |
| `pooledBytes` with trim > 8 MiB | Claim refuted: the trim path lets the pool exceed its cap. |
| `pooledBytes` does not move 8→16 MiB, or `buffers` never reaches overflow (loop never ends: the test times out) | Not confirmed: the positive control failed. Inspect `memoryUsageThreshold`. |
| Guard rows never produce `guard=false` (operand never reached the "free" side) | Not confirmed: the workload did not exercise both outcomes. |
| O1 `overflowAfterPut < 0` | Confirms the A3 accounting defect (a secondary finding, separate from the claim). |

> **Stage-4 audit amendment U3 (2026-10-22): rows made exact, missing outcomes added, and how the rows combine. Written before any reading.**
> - Row 1 reads "N1–N6, T1–T2 have `dSize = 0`" (U1); row 2 reads "any of N1–N6, T1–T2 with `dSize ≠ 0`, or a guard-true row with `dFree ≠ 0`".
> - Row 3 (positive control) is met when **`buffers(b) > buffers(a)`, `pooledBytes(a) = pooledBytes(b) = 8388608` and `pooledBytes(c) = 16777216`**. The exact counts 128 / 576 / 256 are B2f sub-predictions; a different count with these relations still meets the row and is recorded as a missed sub-prediction.
>
> | Added observation | Meaning |
> |---|---|
> | Any row with `abs(dDirect) ≥ 2048` (one normal slot), or `abs(directDelta(b) − directDelta(a)) ≥ 1 MiB` | **Claim refuted**: a trim changes the process's real direct memory. |
> | `directDelta` ≠ `k × (8 MiB + pageSize)` while (a) and (b) agree within 1 MiB | Another direct user in the test JVM, or a different slab size. Recorded; does not change the verdict. |
> | `buffers(b) ≤ buffers(a)` with `pooledBytes(a) = pooledBytes(b)` | Not confirmed: the free branch did not return reusable slots (mechanism not as traced in A3 step 4). |
> | O1 `overflowAfterPut = −261120`, `capAfter = 262144`, `dDirect = 0` | Confirms the A3 accounting defect exactly: `OverflowSize` drifts by `capacity − limit` per trimmed overflow buffer while nothing is freed (secondary). |
> | O1 `overflowAfterPut = 0` | The A3 accounting defect is not present (secondary finding refuted; the claim is unaffected). |
> | The shipped `testPuttingUnusedPortion` fails | Not confirmed: the independent reference for the tiny-unit guard failed. |
>
> **How the rows combine (unit tier).** A Refuted row that fires decides the tier (**Refuted**). Otherwise the tier is **Confirmed** when row 1 and row 3 hold, every `dDirect` is 0 within one slot, the shift assertion passes, and the shipped test passes. Otherwise it is **Not confirmed** with the row that fired. If the readings match no row at all, the tier is "Not confirmed (no matching row)". The O1 rows are a secondary finding and do not decide the tier.

**B2h. Controls.** N1/N2/N5/T1 vs N3/N4/N6/T2 cover both outcomes of the same check in both units, and only `limit` differs within a pair. Each row returns its buffer, so rows do not interact beyond one chunk in a single local pool. The shipped `testPuttingUnusedPortion` is an independent reference for the tiny-unit guard. The positive control uses the same pool class and the same request size, and changes only the threshold or trim, so a moving ceiling can be attributed to the threshold.

### B3. Cluster tier

**B3a. Environment and build.** One host with two nodes on loopback (127.0.0.1 seed, 127.0.0.2), built from the B2a clone (`ant jar`). Per node:
```
for i in 1 2; do
  mkdir -p /tmp/s3bp/n$i/{data,commitlog,hints,saved_caches,cdc,logs}
  cp -r /tmp/s3bp/cassandra/conf /tmp/s3bp/n$i/conf
  y=/tmp/s3bp/n$i/conf/cassandra.yaml
  sed -i -e "s/^listen_address:.*/listen_address: 127.0.0.$i/" \
         -e "s/^rpc_address:.*/rpc_address: 127.0.0.$i/" \
         -e "s/- seeds:.*/- seeds: \"127.0.0.1:7000\"/" \
         -e "s|^commitlog_directory:.*|commitlog_directory: /tmp/s3bp/n$i/commitlog|" \
         -e "s|^hints_directory:.*|hints_directory: /tmp/s3bp/n$i/hints|" \
         -e "s|^saved_caches_directory:.*|saved_caches_directory: /tmp/s3bp/n$i/saved_caches|" \
         -e "s|^cdc_raw_directory:.*|cdc_raw_directory: /tmp/s3bp/n$i/cdc|" $y
  # uncomment-or-add keys (add at end; later keys win only if not already present, so delete commented/active forms first)
  sed -i -e '/^# *data_file_directories:/,+1d' -e '/^data_file_directories:/,+1d' -e '/^# *networking_cache_size:/d' -e '/^networking_cache_size:/d' $y
  printf 'data_file_directories:\n    - /tmp/s3bp/n%s/data\nnetworking_cache_size: NCS\n' $i >> $y
  sed -i "s/^JMX_PORT=.*/JMX_PORT=\"7${i}99\"/" /tmp/s3bp/n$i/conf/cassandra-env.sh
done
```
(JMX ports: n1 = 7199, n2 = 7299.) `NCS` is replaced per knob value (B3b). The yaml leaves `internode_compression: dc`, so same-DC traffic uses `FrameEncoderCrc` (`Payload.finish` → `putUnusedPortion`). Start each node:
```
cd /tmp/s3bp/cassandra
CASSANDRA_CONF=/tmp/s3bp/n1/conf CASSANDRA_LOG_DIR=/tmp/s3bp/n1/logs MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M \
  JVM_EXTRA_OPTS="-XX:MaxDirectMemorySize=2g" bin/cassandra -p /tmp/s3bp/n1/pid
# wait for "Starting listening for CQL clients" in /tmp/s3bp/n1/logs/system.log, then the same with n2
```

**B3b. Knobs.** `networking_cache_size` on both nodes, at three values:
- `4MiB`: below one macro chunk, so `cur + 8 MiB > 4 MiB` holds from the start and nothing is ever pooled.
- `16MiB`: two macro chunks.
- `128MiB`: the default for a 4 GiB heap = `min(128, 4096/16=256)`.

Set it by replacing `NCS` with `sed -i "s/^networking_cache_size: .*/networking_cache_size: 16MiB/"`. A restart is required, because the value is read once into a static final (`BufferPools.java:44`). Confirm it in the log line `Global buffer pool limit is ... for networking` (`BufferPools.java:49-53`). `NORMAL_CHUNK_SIZE` itself is not settable, so the cluster tier tests it through its consequence: no trim outcome moves reserved memory past the threshold.

> **Stage-4 audit amendment K4 (2026-10-22): a fourth value, `8MiB`.** B3c doubts that 16 MiB is reached. If neither 16 MiB nor 128 MiB binds, the only binding value is 4 MiB, where no buffer is pooled and the check at :1521 is never reached. `8MiB` (= one macro chunk; `0 + 8 MiB > 8 MiB` is false, so exactly one slab can be made) adds a non-zero value where the cap binds as soon as the local pools need more than 64 normal chunks at once. The run order is 4MiB, 8MiB, 16MiB, 128MiB. Written before any reading.

**B3c. Workload.** RF = 2 and CL = ALL, so every write crosses 127.0.0.1↔127.0.0.2 as framed internode messages. Each `OutboundConnection` flush allocates `getAtLeast(min(pending, 64 KiB − header))` and trims with `finish()`. The workload uses native protocol v5, so CQL responses go through `Flusher` → `Payload.finish`.
```
tools/bin/cassandra-stress write n=3000000 cl=ALL -schema "replication(factor=2)" \
  -col size=FIXED(512) n=FIXED(5) -mode native cql3 protocolVersion=5 \
  -rate threads=256 -node 127.0.0.1,127.0.0.2 -log file=/tmp/s3bp/stress-write-NCS.log
tools/bin/cassandra-stress read n=1000000 cl=ALL -mode native cql3 protocolVersion=5 \
  -rate threads=256 -node 127.0.0.1,127.0.0.2 -log file=/tmp/s3bp/stress-read-NCS.log
```
Rough on-disk data per node is 3e6 × ~2.6 KiB ≈ 8 GiB uncompressed (less after compression), which fits within the ~50 GB of local disk. Run time is a few minutes per phase. Reachability of the cap: the default netty event-loop count on 40 cores is in the tens, and each `LocalPool` holds up to 3 chunks of 128 KiB. One macro chunk serves 64 such chunks, so 16 MiB is reachable. 128 MiB may not be reached, and that is allowed (see B3f).

> **Stage-4 audit amendment K3 (2026-10-22): workload volume.** The write phase is `n=1500000` and the read phase `n=1000000` (other options unchanged). Reason: the run host is shared, and the stage-4 budget is about 20 GB of local disk; 3e6 rows at RF = 2 on one host is about 2 × 8 GiB per run before commit logs. Whether the cap is reached depends on how many netty threads hold chunks at once (concurrency), not on the row count, so no prediction changes. Written before any reading.

**B3d. Observables and instruments.** Sample every 5 s on each node (port `P` = 7199 or 7299) into `/tmp/s3bp/nN-NCS.csv`:
```
for m in Size OverflowSize UsedSize Capacity; do
  bin/nodetool -p P sjk mx -b "org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=$m" -mg -f Value
done
bin/nodetool -p P sjk mx -b "java.nio:type=BufferPool,name=direct" -mg -f MemoryUsed
bin/nodetool -p P sjk mx -b "java.nio:type=BufferPool,name=direct" -mg -f Count
```
- Derived: `pooled = Size − OverflowSize` (= `memoryAllocated`, `BufferPool.java:274-277`).
- Also record `grep -c "Maximum memory usage reached" logs/system.log` and the RSS of the pid (`ps -o rss= -p $(cat pid)`).
- Not observable directly: the per-call guard outcome at :1521 (no metric or log), and what share of direct memory belongs to the networking pool versus other users. The unit tier covers the former. For the latter, `pooled` is the networking pool's exact share.

> **Stage-4 audit amendment K1 (2026-10-22): exact pooled bytes, the check's outcomes and the real cap's refusals on the node.** Written before any reading.
> - `pooled = Size − OverflowSize` comes from two gauge reads at two moments. Under load, `OverflowSize` changes between them, so the derived figure is neither exact nor always a multiple of 8 MiB. It could even exceed the cap for one sample and fire the Refuted row falsely. The exact figure comes from a Byteman observation script on each node (`stage4-runtime-verification/harness/NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous/ncs.btm`, `-javaagent:<byteman jar>=script:ncs.btm`, no listener; it changes no control flow). The script writes one `made n=<k>` line per macro chunk the networking pool creates, so **`P_exact = k × 8 MiB`** (macro chunks are never freed). The derived `pooled` is kept and read at the **idle tail** (the 60 s after load, from 15 s after the read phase ends), when no frame is in flight.
> - The script's counters, written on a `dump` line at every sampler pass: `refuse`, the real cap's disallow branch (`allocateMoreChunks` returned null, `:443`); `gtrue` and `gfalse`, how often `Chunk.freeUnusedPortion` was entered with `roundUp(limit) == roundUp(capacity)` (the :1521 return) or not (slots freed); `gtiny`, the share of those calls on tiny chunks; and `ovftrim`, the trims of unpooled overflow buffers (the `:885` call, the source of the `OverflowSize` drift). Every caller of `putUnusedPortion` uses the networking pool (`FrameEncoder.java:32`, `BufferPoolAllocator.java:40`, `AsyncStreamingOutputPlus.java:58`), so these counters need no pool filter.
> - The B3d attributes (networking `Capacity`, `Size`, `UsedSize`, `OverflowSize`, plus `Hits` and `Misses`, and java.nio direct `MemoryUsed` and `Count`) are read every 5 s over **one JMX connection per node** (harness `PoolSampler.java`), not with six `nodetool sjk` JVM starts per sample. RSS is read every 5 s with `ps -o rss=`.

**B3e. Procedure.** For each NCS in (4MiB, 16MiB, 128MiB):
1. Set NCS on both nodes (B3b), and wipe `/tmp/s3bp/n{1,2}/{data,commitlog,hints,saved_caches}/*`.
2. Start n1, wait for CQL; start n2, wait for CQL. Then run `bin/nodetool -p 7199 status`, which must show 2 UN.
3. Take the idle baseline: 6 samples (30 s).
4. Start the sampler loop in the background, and run the write phase and then the read phase.
5. Keep sampling for 60 s after the load ends. Then stop the sampler.
6. Run `bin/nodetool -p 7299 stopdaemon` and then `bin/nodetool -p 7199 stopdaemon`, and check that `pgrep -f CassandraDaemon` is empty.

**B3f. Predictions.** On both nodes, at every sample:

| NCS | `Capacity` | `pooled` | `OverflowSize` | log "Maximum memory usage reached" |
|---|---|---|---|---|
| 4MiB | 4194304 | 0 always | nonzero under load, and **drifts below 0** (trim of overflow buffers, A3) | ≥ 1 |
| 16MiB | 16777216 | ∈ {0, 8, 16} MiB, never > 16777216 | ≥ 0 until the cap is hit, then drifting as for 4MiB | ≥ 1 if pooled reaches 16 MiB |
| 128MiB | 134217728 | a multiple of 8388608, ≥ 8388608 once traffic starts, ≤ 134217728 | ~0 unless the cap is hit | 0 unless pooled = 128 MiB |

Other predictions:
- `pooled` never decreases during a run. Macro chunks are never freed (only `unsafeFree` in tests).
- `UsedSize ≤ Size` holds while overflow is 0.
- java.nio `MemoryUsed` minus the idle baseline is ≥ `pooled` (slabs are 8 MiB + 4 KiB each).
- The trim path running on every frame never makes `pooled` exceed the cap.
- Pooled memory is ordered pooled(4MiB) = 0 ≤ pooled(16MiB) ≤ pooled(128MiB). The memory follows `networking_cache_size`, not the trim check.

> **Stage-4 audit amendment K2a (2026-10-22): predictions for the K1 observables and the 8MiB value.** Written before any reading. `k` is the last `made n=` value on a node. `P_exact = k × 8 MiB`.
>
> | NCS | `k` per node | `refuse` | `gtrue` / `gfalse` | `ovftrim` |
> |---|---|---|---|---|
> | 4MiB | 0 | > 0 | 0 / 0 (no buffer is pooled, so :1521 is never reached) | > 0 |
> | 8MiB | 1 | > 0 expected (more than 64 chunks wanted at once) | > 0 / > 0 | > 0 if `refuse` > 0 |
> | 16MiB | 1 or 2 | > 0 if `k` = 2 and demand continues | > 0 / > 0 | > 0 if `refuse` > 0 |
> | 128MiB | ≤ 16, and ≥ `k`(16MiB) on the same node | 0 unless `k` = 16 | > 0 / > 0 | 0 unless `refuse` > 0 |
>
> - At the idle tail, the derived `pooled` equals `P_exact` within 64 KiB.
> - Order on each node: `P_exact`(4) ≤ (8) ≤ (16) ≤ (128).
> - `Capacity` equals NCS × 1 MiB.
> - The 4MiB row's `OverflowSize` "drifts below 0" is read on any sample of that run, as in B3g's last row.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| `pooled` ≤ cap at every NCS, a multiple of 8 MiB, and its ceiling moves with NCS (0 → ≤16 MiB → larger) | Claim confirmed: the cap is `networking_cache_size`, and the trim check (run on every frame) does not change reserved memory. This row is also the positive control: the same workload moves usage where a known cap binds. |
| `pooled` > `floor(NCS/8 MiB)·8 MiB` at any sample | Claim refuted: something, possibly the trim path, lets reserved memory exceed the cap. |
| `pooled` decreases during a run without restart | Claim refuted as traced: some path releases slabs. Re-check A3. |
| `pooled` is the same at 16MiB and 128MiB and below 16 MiB, and the 4MiB run also shows 0 | Not confirmed for the upper range (the workload never reached 16 MiB). The 4MiB row still shows the cap binding. Rerun with more `-rate threads` or a smaller NCS. |
| 4MiB run shows `pooled` > 0 | Positive control failed: the threshold is not applied as traced (`BufferPool.java:443`). |
| `OverflowSize` < 0 in the 4MiB run while java.nio `MemoryUsed` stays bounded | Confirms the A3 accounting defect. The metric under-reports real overflow, so `Size` is not a reliable usage figure when the pool is exhausted (a secondary finding). |

> **Stage-4 audit amendment K2b (2026-10-22): the rows made exact, missing outcomes added, and how the rows combine.** Written before any reading. Above, the row conditions overlapped. For example, pooled 0 / 16 / 16 MiB with the 16 MiB cap binding fitted neither row 1 ("0 → ≤16 MiB → larger") nor row 4 ("below 16 MiB"). With the K1 instruments and the K4 value, the rows read as follows. `cap(v) = floor(v / 8 MiB) × 8 MiB`, so 0 / 8 / 16 / 128 MiB. `P_exact` is from K1. Every condition applies to both nodes unless it says "on one node".
>
> | # | Observation | Meaning |
> |---|---|---|
> | 1 | `P_exact ≤ cap(v)` at every value; 4MiB has `k = 0` and `refuse > 0`; **in the 8MiB or the 16MiB run, on one node, `P_exact = cap(v)` and `refuse > 0`** (the cap reached in a run where the check runs); and `gfalse > 0` in every run with v ≥ 8MiB | **Claim confirmed** (replaces row 1). The ceiling is `networking_cache_size`, reached and holding while the :1521 check takes its slot-freeing branch. The 4MiB → 8/16MiB move is the positive control. |
> | 2 | `P_exact > cap(v)` on any node at any value, or the idle-tail derived `pooled` > `cap(v)` + 1 MiB | **Claim refuted** (replaces row 2). |
> | 3 | The idle-tail derived `pooled` ≤ `P_exact` − 8 MiB (a slab was released) | **Claim refuted as traced** (replaces row 3). Re-check A3. |
> | 4 | Rows 2, 3, 5 and 8 do not fire, but no 8MiB or 16MiB run has `refuse > 0` with `P_exact = cap(v)` | **Not confirmed**: the cap was never reached where the check runs (replaces row 4). |
> | 5 | 4MiB has `k > 0`, or `refuse = 0` | **Not confirmed: the positive control failed** (as row 5). |
> | 6 | `gfalse = 0` in every run with v ≥ 8MiB | **Not confirmed**: the slot-freeing branch of :1521 was not exercised on the node. |
> | 7 | `OverflowSize` never < 0 in the 4MiB run, on either node | The A3 drift is not shown on the node. A secondary finding; the claim is unaffected. The unit tier's O1 rows still decide the drift. |
> | 8 | `Capacity` ≠ NCS × 1 MiB, the ring is not 2 UN, or stress reports errors on more than 1 % of operations in a run | **Invalid run** for that value. |
>
> **How the rows combine (cluster tier).** Rows 2 and 3 are checked first; either one decides the tier (Refuted). Next comes row 8 (Invalid). Then rows 5, 4 and 6, in that order: the first that fires gives Not confirmed. Row 1 gives Confirmed only if none of these fired. Rows 7 and the last row above (the A3 drift) are secondary and do not decide the tier. If the readings match no row, the tier is "Not confirmed (no matching row)". Missed sub-predictions of B3f and K2a (exact `k`, the order, `OverflowSize ~0` at 128MiB, `MemoryUsed − baseline ≥ pooled`) are recorded and do not change the row.

**B3h. Controls.**
- An idle baseline is taken per run to separate other direct users (A4).
- Data dirs are wiped per run, and the same stress commands and seeds are used.
- The 4MiB run is the floor control: all frames go through the overflow branch, so pooled = 0 whatever the trim does.
- `Capacity` is read back over JMX to prove that the knob took effect.
- `-XX:MaxDirectMemorySize=2g` is held constant, so a JDK direct-memory limit cannot be what bounds `pooled`.
- Both nodes are sampled, because inbound (`FrameDecoder`) and outbound trims happen on different sides.

**B4. Risks and cleanup.**
- All files stay under `/tmp/s3bp` on local `/`. Expect about 3 GB for the clone and build, and up to ~10 GB per data run, wiped between runs. Check `df -h /` before each run, and abort below 15 GB free.
- Nothing is written to `/proj` (shared storage). The shared source clone is only read via `git clone`.
- After each run, `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` must both be empty. If not, `kill $(cat /tmp/s3bp/n*/pid)`, then `kill -9` after 30 s.
- Unit tier: ant forks a JVM per test, which exits by itself. Check that `pgrep -f junit` is empty.
- At the end, `rm -rf /tmp/s3bp`.
- Loopback 127.0.0.2 works by default on Linux. Ports 7000/9042 are reused per IP, and JMX uses 7199/7299. Check that no other process holds them (`ss -ltnp | grep -E ':(7000|9042|7199|7299)'`).

## C. Sources read

/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md
/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md
/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/README.md (§6.1 only)
src/java/org/apache/cassandra/utils/memory/BufferPool.java
src/java/org/apache/cassandra/utils/memory/BufferPools.java
src/java/org/apache/cassandra/net/FrameEncoder.java
src/java/org/apache/cassandra/net/FrameEncoderCrc.java
src/java/org/apache/cassandra/net/FrameEncoderLZ4.java
src/java/org/apache/cassandra/net/FrameDecoder.java
src/java/org/apache/cassandra/net/BufferPoolAllocator.java
src/java/org/apache/cassandra/net/AsyncStreamingOutputPlus.java
src/java/org/apache/cassandra/net/OutboundConnection.java (lines 760-840, 939-977)
src/java/org/apache/cassandra/net/OutboundConnections.java (line 69)
src/java/org/apache/cassandra/transport/Flusher.java
src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 573-574, 3796-3805)
src/java/org/apache/cassandra/config/Config.java (line 493-494)
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (line 388)
src/java/org/apache/cassandra/io/util/FileUtils.java (clean)
test/unit/org/apache/cassandra/utils/memory/BufferPoolTest.java
tools/stress/src/org/apache/cassandra/stress/settings/SettingsMode.java
conf/cassandra.yaml, conf/cassandra-env.sh, conf/jvm-server.options, bin/cassandra, build.xml
https://docs.oracle.com/javase/specs/jls/se11/html/jls-15.html#jls-15.19
https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html

## D. Stage-4 feedback

**2026-10-22, run 1 (both tiers), on `pc07`. Results file: `stage4-runtime-verification/results/NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous.md`.**

The design audit came out "Ready after amendments": U1–U3 and K1–K4, each dated next to the text it changes. The frozen sha256 is `b4a452ceeeaecb18b5b0091612d59443e48b728c364ec8c20ee2d604c5bdd94e`. Two runbook-defect fixes to B2e followed during the unit tier, D1 and D2, neither touching a prediction or a row. Not committed.

**Unit tier: Confirmed — does not cap.**
- Every B2f value held exactly, as did those of U1 and U2.
- Both outcomes of :1521 occurred in both units (2048 B and 32 B). On both, `dSize = 0` and the JVM's direct `MemoryUsed` did not move (`dDirect = 0`).
- The free branch let one 8 MiB reservation serve 576 instead of 128 buffers of 64 KiB, while `pooledBytes` and `directDelta` (8,392,704) stayed equal.
- The threshold alone moved the reservation, from 8 to 16 MiB.

**Cluster tier: Not confirmed (K2b row 4), Effect undetermined.**
- Two nodes ran at `networking_cache_size` 4 / 8 / 16 / 128 MiB, with 1.5 M writes and 1 M reads at CL=ALL over v5.
- At 8, 16 and 128 MiB the pool made exactly one slab, at start-up, and never refused a chunk (`refuse = 0`).
- Meanwhile :1521 ran about 2.9 M times per node per run, about a third of them on the slot-freeing branch.
- The cap therefore never bound in a run where the check runs. Row 4 was frozen for exactly this case, and the tier cannot confirm.
- At 4 MiB the pool made no slab and refused about 3 M chunk requests per node, but there the check is never reached.
- The first V128 attempt was invalid (row 8: a 13.5 s commit-log sync stall, then `WriteTimeoutException` at CL=ALL). It was repeated, and the repeat was valid.

**Secondary finding (A3), confirmed at both tiers:**
- Unit: O1 left `OverflowSize = −261120` exactly.
- Cluster at 4 MiB: about 2.9 M overflow trims per node drove `OverflowSize`, and with it `Size`, to −14.7 / −14.5 GB in about 2 minutes of load, while direct memory rose by 1.4 MiB. The two pool metrics are meaningless as usage figures once the pool is exhausted.

**Overlap.** The cluster tier's dose-response on `networking_cache_size` repeats the closed guided case `networking_cache_size-allocateMoreChunks-memoryUsageThreshold`. That case's U4 had already recorded the same drift on its CRC path, at −6 B per frame; here the average per trim is about 5 kB.

**For stage 3:**
- (1) A cluster arm that makes the local pools want more than 64 normal chunks at once is needed before this tier can confirm. Two ways: many more concurrent connections or event loops, or a client that holds frames, as the guided case's stall client did.
- (2) Line citations off by a few lines, none load-bearing:
  - `unit()` is `:1364-1367`;
  - `roundUp(int)` is `:1481-1484`;
  - the overflow branch of `LocalPool.put` is `:813-817`;
  - the double-free assert is at `:1539`.
- (3) A1/B1 could say that `NORMAL_CHUNK_SIZE` does shape usage through other paths. It sets the cap's granularity (`MACRO_CHUNK_SIZE = 64 ×` it) and the pooled/unpooled split (requests over 128 KiB are never pooled); only the :1521 path leaves usage alone.
