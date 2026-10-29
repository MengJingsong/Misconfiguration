# Draft verification designs for `none`-type cases, kind 3 (buffer length / capacity)

Drafted 2026-10-28. **Documents only: nothing was run, built or committed, and no case file was edited.** Each section below is meant to be pasted
into B2 and B3 of its case file as a dated audit amendment, following [`none-type-design.md`](none-type-design.md) §3-§4. Source lines were
re-read in `cassandra/cassandra-5.0.9/`; a line marked "(case file)" was taken from the case file and not re-opened.
Wording for every design: *the operand is the buffer length itself, so "usage follows the operand" is expected and is not a finding (design §6);
the finding is the difference the branch causes at equal operand.*

## Summary

| Stem | Operand kind (confirmed?) | Runnable? | Instrument | Effort |
|---|---|---|---|---|
| `no_constraint-resizeto-newcapacity` | 3 yes (`newCapacity`, off-heap bytes) | unit; cluster n/a | Byteman on `Memory.java:65` (`MemoryUtil.allocate`) + `getThreadAllocatedBytes` | about 0.5 day |
| `no_constraint-capacity-newcapacity` | 3 yes (`newCapacity`, direct pool buffer) | unit; cluster n/a | `BufferPool.usedSizeInBytes()/overflowMemoryInBytes()` + `getThreadAllocatedBytes` | about 0.5 day |
| `no_constraint-allocateblock-inchunkpointer` | **1, not 3** (`allocatedPos`, size of held data; no caller sets it) | unit; cluster n/a | `getThreadAllocatedBytes` per `advanceAllocatedPos` call + `sizeOnHeap()` | about 0.5 day |
| `none-compose-buffer_remaining` | **2 (emptiness flag, `remaining()==0`), data size is a secondary kind 1** | unit only (tiny); cluster n/a | `getThreadAllocatedBytes` | about 2 hours (batch with kind 2) |
| `none-readfully-dest_length` | 3 yes (`dest.length`, caller's float count) | unit; cluster n/a | `getThreadAllocatedBytes` + Byteman counter at line 72 | about 1 day (shared with next) |
| `none-read-count` | 3 yes (`count`, caller's int count) | unit; cluster n/a | same harness as above (int twin) | included above |
| `none-allocateoversize-peer` | 3 for the allocation `size`, but the compared pair is `newOffset+size` vs `capacity` of a region sized exactly `size` | **no meaningful run for line 194**; recommend *Confirmed from source, not run* | (optional reach proof: Byteman counter) | 0 (or 2 hours for the optional proof) |
| `none-checklimit-length` | 3 yes (`length` = size of a pending read vs record remainder) | unit; cluster not worth it | `getThreadAllocatedBytes` around `Hint.readBufferIfLive` | about 0.5 day |

Cluster tier, all eight: only `none-checklimit-length` has a real production workload worth naming (hint replay); none is recommended, see each section.

---

## 1. `no_constraint-resizeto-newcapacity` (SafeMemoryWriter.java:52)

**Kind.** 3 confirmed. `newCapacity` is the byte size asked of an off-heap `SafeMemory` (`resizeTo`, SafeMemoryWriter.java:50-52). The true branch
(`!=`) copies into a new `SafeMemory` (SafeMemory.java:70-75, allocation at Memory.java:65) and frees the old one (SafeMemoryWriter.java:65).

**Caller and reach.** Grow: `expandToFit` -> `resizeTo(calculateNewSize(count))` (SafeMemoryWriter.java:45-47; DataOutputBuffer.java:158-172), always a different size
for `count > 0`. Equal size occurs only in `trim()` (69-72) on an exactly full writer. Production user: `IndexSummaryBuilder` (`trim()` at lines 250-251, case file).
Unit scaffolding exists: `test/unit/org/apache/cassandra/io/util/SafeMemoryWriterTest.java` (`testTrim`, line 56). A new test class in package
`org.apache.cassandra.io.util` is needed for the sweep. Prove execution: Byteman counter on `SafeMemory.copy` (SafeMemory.java:70) entry; equal arm must show 0 calls.

**Sweep (before the run).** Capacity C in {1 KiB, 64 KiB, 1 MiB, 64 MiB, 512 MiB} (five orders). For each C, a writer of capacity C filled to exactly C bytes:
arm E `trim()` (equal, check false), arm D fill C-1 bytes then `trim()` (differs by 1), arm H fill C/2 then `trim()`. Fresh JVM per C, 5 repetitions, median and range.

**Measure.** Off-heap bytes requested: Byteman rule at `Memory.java:65` recording `size` (this is the exact guarded allocation; `getThreadAllocatedBytes` cannot see Unsafe malloc,
so it is used only for the on-heap residue). Retained size: `writer.capacity()` after the call (SafeMemoryWriter.java:89-92).

**Branch flip (equal operand magnitude).** E vs D at the same C. Prediction: E requests 0 bytes and 0 `copy` calls; D requests C-1 bytes in one call, and peak
transient native memory is (C) + (C-1) until `oldBuffer.free()` (line 65). Retained capacity after the call: E = C, D = C-1, so the difference is at most 1 byte. H requests C/2.
On-heap residue per call: constant, independent of C (within 1 KiB).

**Positive control.** Growth knob `DOB_DOUBLING_THRESHOLD_MB` (DataOutputBuffer.java:48, read once at class load, so set the property in a fresh JVM): with C = 8 MiB and a
1-byte write, threshold 1 MiB gives newSize 1.5C = 12 MiB, the default threshold gives 2C = 16 MiB (arithmetic from lines 166-169). The same Byteman rule must move by 4 MiB
between the two JVMs. (Sibling control only; it acts in `calculateNewSize`, not at line 52.)

**Noise floor.** Run arm E twice on identical input and arm D twice; record the difference in the rule's byte total (expected 0 for native bytes) and in on-heap residue.

**Conclusions.**

| Reading | Verdict | Effect |
|---|---|---|
| E requests 0 bytes, D requests C-1 (transient), retained capacity differs by at most 1 byte, control moved by about 4 MiB, rule counted | Confirmed | `does not cap` (skips a redundant same-size copy only) |
| Retained capacity differs by more than 1 byte or E allocates | Refuted | `caps` / mechanism misread |
| Control did not move, or `copy` count is 0 in arm D | Not confirmed / Invalid | `undetermined` |
| Arm difference under the noise floor | Not confirmed | `undetermined` |

**Note for the audit.** The branch *does* gate an allocation (design §4 row 2), so the table's row 2 would read "caps" if applied mechanically. It gates a redundant allocation of
equal retained size; add the row "retained size equal on both branches, only the transient copy differs -> Confirmed, does not cap".

**Cluster tier.** `n/a: transient native copy of an index summary (key count x entry size, MiB scale), sweep does not reach the heap and the equal branch needs an exactly full writer.`

---

## 2. `no_constraint-capacity-newcapacity` (BufferPoolAllocator.java:121)

**Kind.** 3 confirmed. `newCapacity` is the requested capacity of a direct `Wrapped` ByteBuf (BufferPoolAllocator.java:119-124); the false branch calls `super.capacity`, which
re-allocates through `allocateDirect` -> `bufferPool.getAtLeast` (134-137) and returns the old buffer with `bufferPool.put(wrapped)` (128).

**Caller and reach.** Netty calls it from `ensureWritable`/`writeBytes` when a write needs more room (exercised today by `BufferPoolAllocatorTest.testBufferContentAfterResize`, line 126 onward).
Netty's own grow path only passes a larger size (inference from the Netty contract, not re-read in the jar), so the equal branch is reached by a direct call
`buf.capacity(buf.capacity())`. Scaffolding: `test/unit/org/apache/cassandra/net/BufferPoolAllocatorTest.java` (helper `allocateByteBuf(initial, max)` at line 198, `usedSizeInBytes()` assertions
at 58-62, `ensureThatAllMemoryIsReturnedBackToBufferPool` at 209-213); add a test method or a new class in package `org.apache.cassandra.net`.
Prove execution: Byteman counter at `BufferPoolAllocator.java:124` (`super.capacity`) for the false arm; the equal arm must show 0.

**Sweep.** Initial capacity C in {128 B, 4 KiB, 64 KiB, 1 MiB, 16 MiB}, max capacity 2C+64. Arms: E `capacity(C)`, G `capacity(C+1)` (grow by one), S `capacity(C/2)` (shrink). 5 reps each, fresh pool per rep.
Set `networking_cache_size` as in the existing test (128 MiB, test line 45).

**Measure.** `GlobalBufferPoolAllocator.instance.usedSizeInBytes()` (`BufferPool.java:282`, pooled + overflow) and `overflowMemoryInBytes()` (BufferPool.java:290), read before and after;
`getThreadAllocatedBytes` for the on-heap residue.

**Branch flip.** E vs G at the same C. Prediction: E leaves `usedSizeInBytes` unchanged (delta 0) and 0 `super.capacity` calls; G changes it to the new buffer's size (pool may hand out more than C+1:
read the value, do not assume it) and calls `super.capacity` once; for C >= 64 KiB (above any chunk) expect `overflowMemoryInBytes` to rise by about C. After G the old buffer is back in the pool, so
steady state is one buffer, not two (the existing test asserts used == capacity after resize, line 62).

**Positive control.** `networking_cache_size` (the test sets it, line 45; its comment at 43-44 says 0 or below a macro chunk means no pooling): allocate 16 buffers of 16 MiB with 128 MiB vs
with a value below one chunk and show `overflowMemoryInBytes` moves (audit must confirm the overflow semantics in `BufferPool.java` before freezing).

**Noise floor.** Repeat arm E and arm G twice with identical input; used-bytes difference expected 0, on-heap residue difference recorded.

**Conclusions.** As in section 1: E flat and G moves by the new-buffer size with steady-state usage equal to one buffer on both branches -> Confirmed `does not cap`; E allocates, or steady state keeps both
buffers -> Refuted; control flat or counter 0 -> Not confirmed/Invalid; under noise -> Not confirmed.

**Cluster tier.** `n/a: pool memory is bounded by networking_cache_size / overflow accounting elsewhere; a network workload only resizes upward and never exercises the equal branch.` Worth a note, not a run.

---

## 3. `no_constraint-allocateblock-inchunkpointer` (InMemoryTrie.java:145)

**Kind correction: 1, not 3.** The operand is `allocatedPos` (InMemoryTrie.java:70, read at 144): bytes already handed out, a running size of held data. No caller sets a requested length. The check is the
chunk-start test that decides whether a new buffer `256 << leadBit` bytes is allocated (151); it is the allocation trigger, so flipping it cannot be a "cap", only a bug (inference: `buffers[leadBit]` stays null).
The sibling limits are lines 148 and 953, other statements.

**Caller and reach.** Production: `allocateBlock` is called at 433, 451, 476, 497 (node creation during `put`). Test hook: `advanceAllocatedPos(int)` (961-966, package-private), so the class goes in
`org.apache.cassandra.db.tries` (existing neighbours: `InMemoryTriePutTest`, `InMemoryTrieApplyTest`); new test class needed. Constructor `new InMemoryTrie<>(BufferType.ON_HEAP)` (line 88).
Prove execution: the per-call allocation itself plus `sizeOnHeap()` (975-981).

**Sweep.** Chunk starts are 256*(2^i - 1): 0, 256, 768, 1792, ... (InMemoryReadTrie.java:231-251). For i in {0, 1, 3, 7, 11, 15, 19} take S_i. Call `advanceAllocatedPos(S_i)` (executes the block at S_i-32: mid-chunk, check false)
then `advanceAllocatedPos(S_i + 32)` (executes the block at S_i: chunk start, check true). Allocation at S_i is `256 << i` = 256 B, 512 B, 2 KiB, 32 KiB, 512 KiB, 8 MiB, 128 MiB (six orders). `-Xmx1g`, 5 fresh tries per i.

**Measure.** `getThreadAllocatedBytes` around each single call (exact instrument of `batch_size_fail_threshold-...--guided/Alloc.java`), and `sizeOnHeap()` before/after.

**Branch flip.** False call vs true call from the same state. Prediction: false call allocates 0 buffer bytes (constant residue under 1 KiB, same at every i); true call allocates `256 << i` plus the same residue;
`sizeOnHeap()` rises by `32` on the false call and by about `32 + REFERENCE_ARRAY_ON_HEAP_SIZE` on the true call, while `allocatedPos` advances by exactly 32 in both. Total retained after N blocks is `allocatedPos + const`, independent of the branch.

**Positive control.** Sibling cap at line 953: with `allocatedPos` at `ALLOCATED_SIZE_THRESHOLD - 32` vs the threshold, `reachedAllocatedSizeThreshold()` flips (a signal, not an allocation cap); the threshold property
(`cassandra.memtable.row_overhead_size`, case file) moves it. Honest limit: this shows the instrument can see a cap-like signal in the same sweep, not an allocation cap.

**Noise floor.** Two identical false calls and two identical true calls on fresh tries; residue difference recorded.

**Conclusions.** True-call allocation equals `256 << i` within the noise floor and is the only difference between branches -> Confirmed `does not cap` (trigger, not limit; usage follows blocks written). True call allocates
something other than `256 << i`, or false call allocates a buffer -> Refuted. Control not moved -> Not confirmed. This design is cheap; if it is not wanted, *Confirmed from source, not run* is also defensible because the arithmetic is closed-form.

**Cluster tier.** `n/a: the trie is a TrieMemtable detail; a cluster run restates memtable_size behaviour governed by other statements, and the sweep points are exact positions that only the test hook reaches.`

---

## 4. `none-compose-buffer_remaining` (UDFDataType.java:177)

**Kind correction: 2 (emptiness), with data size as kind 1.** The compared item is `buffer.remaining() == 0` combined with `isEmptyValueMeaningless()` (AbstractType.java:458, default false; `Int32Type.java:56` true).
The branch changes behaviour only at length 0; for L >= 1 both sides run line 180 (`typeCodec.deserialize`).

**Caller and reach.** `UDFDataType.wrap(type, false)` (line 120) then `compose(ProtocolVersion, ByteBuffer)` (175). No existing `UDFDataType` test (`test/unit/.../cql3/functions/` has none); new test class there.
Production caller via `getArgumentDeserializer` (case file, UDFDataType.java:292-298). No cluster or UDF enabling needed in the unit tier. Prove execution: return value null vs non-null, plus allocation delta.

**Sweep.** L in {0, 1, 1 KiB, 1 MiB, 16 MiB, 64 MiB} (kind-1 sweep, 7 orders), types `Int32Type` (empty meaningless) and `BytesType` (not). Branch-flip pair: L=0 with `Int32Type` (check true -> null) vs L=0 with `BytesType` (false -> deserialize).
`-Xmx512m`, 5 reps, warmup 20 calls.

**Measure.** `getThreadAllocatedBytes` per call; return class.

**Branch flip.** Prediction: L=0 `Int32Type`: result null, 0 bytes beyond harness residue. L=0 `BytesType`: non-null empty value, a small constant (tens of bytes; exact value unknown, driver codec). For L >= 1 allocation grows with L on both types
(at least L for the blob if the codec copies; unverified) and is identical with or without the check, so the check's whole effect is bounded by one empty object.

**Positive control.** The case file's control is `BytesType.read(in, 1024)` rejecting a 2048 vint length at AbstractType.java:594 (case file, not re-opened): a real size cap in the same harness; it must throw.

**Noise floor.** Two identical L=0 calls and two L=1 MiB calls; difference recorded.

**Conclusions.** Check-true arm allocates 0 and check-false arm allocates only a constant, data growth identical on both -> Confirmed `does not cap`. Any L >= 1 difference between types attributable to the check -> Refuted (not expected).
Control not throwing -> Not confirmed. Cluster tier: `n/a: the branch differs only at L=0, an object of tens of bytes, below heap noise (about 16 MiB)`; the filed B3 only restates that heap follows the argument data, which is "expected, not a positive finding" (design §6) and should be marked n/a.

---

## 5. `none-readfully-dest_length` (RandomAccessReaderAdapter.java:69) and 6. `none-read-count` (line 117)

One shared harness (float and int twins). **Kind.** 3 confirmed for the requested count (`dest.length` line 69, `count` line 117) compared with the elements left in the current mmap region.

**Caller and reach.** Constructor is package-private (line 40), so a new test class in `org.apache.cassandra.index.sai.disk.v1.vector` is needed (no existing test for the class). Build: `new FileHandle.Builder(file).mmapped(true).complete()` (as IndexDescriptor.java:274/296).
Region size comes from `MmappedRegions.MAX_SEGMENT_SIZE` (public, non-final, MmappedRegions.java:44; used at 186), default `Integer.MAX_VALUE`, i.e. one region for any test file. Prove execution: Byteman counter at line 72 / 120 (the allocation) per arm.

**Sweep.** N (floats or ints) in {128, 1536, 16384, 131072, 1048576} (512 B to 4 MiB, four orders). Arm F (check false): default segment size, 16 MiB file, start inside the region. Arm T (check true): `MAX_SEGMENT_SIZE = 65536` set before building the handle (restore after), start `4*N/2` bytes before a boundary
(for N >= 16384 every start straddles). Same file, same N, same start offset in both arms. 5 reps.

**Measure.** `getThreadAllocatedBytes` around one call; data compared to the file's contents.

**Branch flip.** Prediction: arm F allocates a constant c (view objects, expected under 1 KiB, independent of N); arm T allocates c + `4*N` (+16 header) within the noise floor; data identical. Retained heap: both arms garbage after the call (post-GC delta within noise), so no retained size or disk change.

**Positive control.** In the same harness, `ByteBuffer.allocate(4*N)` (or `new float[N]`) measured by the same instrument must read 4N+16, and `readFully` of the same bytes via plain `RandomAccessReader.readFully(byte[])` gives the file-read baseline (case file B2h). A retaining loop under `-Xmx512m` as filed shows post-GC heap rising; there is no
closed cap setting that binds this transient allocation, which is stated rather than invented.

**Noise floor.** Two identical arm-F runs and two identical arm-T runs; the T-F difference must exceed their spread by at least 10x for N >= 16384.

**Conclusions.** T-F = `4N` +- noise, retained heap flat -> Confirmed `does not cap` (path selection only). T-F not explained by `4N`, or retained growth -> Refuted. Straddle never taken (counter 0, T = F) or control off -> Not confirmed/Invalid.

**Cluster tier.** `n/a: default regions are about 2 GiB (MmappedRegions.java:44), so a node's graph file never straddles; the transient is 4 x dimension (up to tens of KiB per query), below heap noise; a patched-jar cluster adds no information.` Existing B3 should be marked n/a. Effort about 1 day for both, mostly mmap file setup and the jvector jar on the classpath.

---

## 7. `none-allocateoversize-peer` (NativeAllocator.java:194)

**Kind.** 3 for `size` (allocation length, `size > MAX_CLONED_SIZE` = 128 KiB, lines 47, 144), but the compared pair is `newOffset + size > capacity` (269-277) for a fresh `Region(peer, size)` (190), i.e. `0 + size > size`, always false.

**Why there is nothing to flip.** The check is an assertion: its true branch (`throw new AssertionError()`, line 195) cannot be reached (`-1` needs `newOffset + size > capacity` with `newOffset == 0` and `capacity == size`). A branch-flip comparison is impossible without editing the source, and
the allocation (190, `MemoryUtil.allocate(size)`) happens *before* the check, so no outcome of line 194 could change what is allocated. The pair "oversize size sweep vs `memtable_offheap_space`" in the filed B2/B3 measures the accounting at line 141, a different statement that belongs to its own case;
repeating it here would test the wrong `if`.

**Recommendation.** Close as **Confirmed from source, not run** with the reason above: the statement is unreachable-true and executes after the allocation it could guard. Index cell `n/a`, outcome-class column empty (design §6).

**Optional reach proof (about 2 hours, not required for the verdict).** New test in `org.apache.cassandra.utils.memory` next to `NativeAllocatorTest` (pool built at its line 55): allocate sizes 128 KiB (slab, `>` not `>=`), 128 KiB + 1, 1 MiB, 4 MiB, 64 MiB; Byteman counter at line 194 must equal the number of oversize calls
and no `AssertionError` is thrown; region capacity equals `size`. This shows reach and non-firing only; it does not change the verdict.

**Cluster tier.** `n/a.`

---

## 8. `none-checklimit-length` (ChecksummedDataInput.java:161)

**Kind.** 3 confirmed: `length` is the byte count of a pending read (`b.length` at 192, `len` at 199) compared with `limit` (record end, set by `limit(n)` at 130-134, reset to `Long.MAX_VALUE` at 153-157).

**Caller and reach.** Prod: `HintsReader` per record: `resetLimit` (211/317), `limit(size)` (234/340), then `Hint.readBufferIfLive` allocates `new byte[size]` (Hint.java:239) and reads with `in.readFully(bytes, header.length, size - header.length)` (241); `RebufferingInputStream.readFully(b,off,len)` (66-71) calls the overridden
`read(b,off,len)` (ChecksummedDataInput.java:196-201), so `checkLimit` runs. In a well-formed record the check never fires (`len` equals the rest of the record). Scaffolding: `test/unit/org/apache/cassandra/hints/ChecksummedDataInputTest.java` (uses `reader.limit(...)` at lines 93, 167, 223); new test class in package `org.apache.cassandra.hints`.
Prove execution: Byteman counter on `checkLimit` entry (line 159).

**Sweep.** Declared record size S in {1 KiB, 64 KiB, 1 MiB, 16 MiB, 64 MiB} (five orders; `-Xmx1g`). Arm F (check false throughout): file holds S real bytes after a valid header, `limit(S)`. Arm T (check true): same file, `limit(S - 1)` so the second read exceeds the limit. 5 reps, fresh JVM per S.

**Measure.** `getThreadAllocatedBytes` around `readBufferIfLive`; exception thrown or not; whether the result is retained.

**Branch flip.** The allocation `byte[S]` (Hint.java:239) precedes the throwing read, so both arms allocate at least S. Prediction: arm F delta = S + c; arm T delta = S + c', with `|c - c'|` under 4 KiB (exception and stack trace only); arm T throws `IOException("Digest mismatch exception")` (line 162), arm F returns a `ByteBuffer`. Retained after the call: F holds S, T holds 0.

**Positive control.** Write-side `max_hints_file_size` as filed (HintsWriteExecutor.java:243-248, case file, not re-opened): the same appended stream gives much smaller files at 1 MiB than at 128 MiB. Not the same instrument; a second control in the same instrument is `new byte[S]` read through `getThreadAllocatedBytes`, expected S + 16.

**Noise floor.** Two identical F and two identical T runs at S = 1 MiB; spread recorded.

**Conclusions.** Allocation independent of the branch beyond the exception residue, both arms >= S -> Confirmed `does not cap` (the check rejects the read, not the allocation). Arm T allocates materially less than S -> Refuted (it would mean the check precedes allocation; not expected). Control flat or counter 0 -> Not confirmed/Invalid; under noise -> Not confirmed.

**Cluster tier.** Not worth running: replay heap is a transient `byte[size]` per in-flight hint (at most the mutation size), reaching tens of MiB only with 16 MiB mutations; the filed two-node B3 (600 x 1 MiB hints) adds cost without a branch to flip, because the check does not fire on well-formed hints. If wanted, workload as filed: RF=2, stop node 2, write 1 MiB blobs, restart, sample `jstat -gc` on node 1.

---

## Shared harness ideas

- One `Alloc` helper copied from `harness/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided/Alloc.java` (`ThreadMXBean.getThreadAllocatedBytes`, 5 reps, median/range, `unit-run.sh` fresh JVM per value) used by sections 3, 4, 5/6, 8.
- A "branch-flip pair" runner: `(operand, armA, armB)` -> two medians, spread of each, and `|A-B|` against the noise floor, so the noise step (two identical runs) is built in rather than added per case. `analyze.py` from the same harness.
- A Byteman rule template "counter at entry/line" (pattern from any closed `autonomous` harness, e.g. `rules.btm`) for the reach proof, and a variant recording a method argument for the off-heap case (section 1; the instrument that sees Unsafe malloc).
- Sections 1 and 2 share the "capacity-equal vs differs" shape (call the resize with C, C+1, C/2) and could share the runner with different adapters; sections 5 and 6 are one class with a float and an int method.

## Cases to drop from kind 3

- `no_constraint-allocateblock-inchunkpointer`: kind 1 (running pointer), keep the design above but file it under kind 1.
- `none-compose-buffer_remaining`: kind 2 (emptiness flag); move to the unit-only kind-2 batch and mark its cluster tier n/a.
- `none-allocateoversize-peer`: no flippable branch; recommend *Confirmed from source, not run*.
