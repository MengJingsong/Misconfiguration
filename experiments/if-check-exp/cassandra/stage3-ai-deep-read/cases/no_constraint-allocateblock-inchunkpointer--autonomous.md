# InMemoryTrie.allocateBlock chunk-start check (no constraint) — verification solution  <!-- file: cases/no_constraint-allocateblock-inchunkpointer--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`InMemoryTrie.java:145`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L145) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI via Agent SDK, 2026-10-27 |
| Estimate | `negative`: the check only decides "is the allocation pointer at the first byte of a new buffer chunk", which is bookkeeping; the real size caps are other statements (line 148 hard 2GB limit; `reachedAllocatedSizeThreshold`, line 951). |
| Ground | The check bounds no quantity. It triggers allocation of the next doubling buffer; it never refuses, delays or limits anything. |

**Type:** non-config (none). Constant rule applied: the numeric literal `0` takes part in the comparison `inChunkPointer(v) == 0`. No yaml entry or JVM property takes part in this check (the JVM property `cassandra.memtable.row_overhead_size` only feeds `ALLOCATED_SIZE_THRESHOLD`, a different statement at line 63).

## A. Constraint trace

**A1. The constraint.** No constraint. Operands of the check at [`InMemoryTrie.java:145`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L145) (`inChunkPointer(v) == 0`):
- `v`: local copy of the field `allocatedPos`, declared at `InMemoryTrie.java:70` (`private int allocatedPos = 0;`), read at line 144. Origin: running byte offset of the next free 32-byte block (advanced by `BLOCK_SIZE` at line 158).
- `inChunkPointer(int pos)`: `InMemoryReadTrie.java:247-251`, which computes `pos + 256 - (256 << chunkIdx)` (`inChunkPointer(pos, chunkIndex, minChunkSize)` at `InMemoryReadTrie.java:236-239`; `getChunkIdx` at 231-234). Returns the offset of `pos` inside its buffer chunk.
- literal `0`: "offset zero", i.e. first byte of a chunk. Chunk i has size `BUF_START_SIZE << i` with `BUF_START_SIZE = 256` (`BUF_START_SHIFT = 8`, `InMemoryReadTrie.java:207-208`), so chunk starts are 0, 256, 768, 1792, ... (`256*(2^i - 1)`).
No unit, default or setting applies; the literal is not settable.

**A2. What it caps.** Nothing. It is the trigger for allocating the next buffer (an on-heap or off-heap `ByteBuffer` of `256 << leadBit` bytes, line 151). The object it relates to, the trie buffers, is memory-significant, but the check does not bound its size: both outcomes just decide whether a new chunk must be allocated before handing out the block. The size bound on those buffers is elsewhere: line 148 (`leadBit + BUF_START_SHIFT == 31` throws `SpaceExhaustedException`, the hard 2GB limit; arrays sized `31 - BUF_START_SHIFT` at line 90) and the soft threshold `ALLOCATED_SIZE_THRESHOLD` (lines 58-67, `MEMTABLE_OVERHEAD_SIZE` property `cassandra.memtable.row_overhead_size`, default `2048*10/11` MB, valid 1..2047), tested at line 953.

**A3. Mechanism.** Enclosing method: `allocateBlock()`, [`InMemoryTrie.java:140-160`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L140-L160). The if statement is [`InMemoryTrie.java:145`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L145).
- True (`allocatedPos` is at a chunk start): compute `leadBit` (147); if `leadBit + 8 == 31` throw `SpaceExhaustedException` (148-149, this is the real 2GB cap); else allocate `256 << leadBit` bytes and store in `buffers[leadBit]` (151-152). Then fall through to advance `allocatedPos` by 32 (158) and return `v`.
- False (mid-chunk): skip allocation; advance `allocatedPos` by 32 and return `v`, which lives in an already allocated chunk.
Because BLOCK_SIZE (32) divides every chunk size (assert at `InMemoryReadTrie.java:215`), a block never straddles chunks, so the pointer hits offset 0 exactly at each chunk start.
Callers of `allocateBlock()`: lines 433 (sparse node), 451 (chain/last-pointer), 476 (split node), 497 (prefix node), 964 (`advanceAllocatedPos`, test-only). Upstream, `TrieMemtable.put` (`TrieMemtable.java:192`) polls `reachedAllocatedSizeThreshold()` and requests a flush; `SpaceExhaustedException` is wrapped in `IllegalStateException` (`TrieMemtable.java:202-206`). Also used by `SegmentTrieBuffer.java:48` (SAI).
Bypass/overshoot: none for this check; the 2GB limit can only be passed if the sibling check at 148 were removed.

**A4. Other consumers.** The buffers allocated here count toward `sizeOnHeap()`/`sizeOffHeap()` (lines 969-981) used by memtable accounting; content arrays (`addContent`, 162-176) and referenced values are separate memory not governed by this check.

**A5. Evidence beyond the source.** Comment at line 142-143 and test `InMemoryTriePutTest.testOver1GSize` (`test/unit/org/apache/cassandra/db/tries/InMemoryTriePutTest.java:68`, `@Ignore`d, needs ~8G heap) exercise the allocation near the 2G limit; it targets the line-148 limit, not this check in isolation. Searched: callers of `allocateBlock`, `inChunkPointer`, property key usage (`MEMTABLE_TRIE_SIZE_LIMIT`, `cassandra.trie_size_limit_mb`, declared at `CassandraRelevantProperties.java:358`, has no consumer in `src`), tests; no git history available in the copy (not a repository). No documentation treats this check as a limit.

## B. Verification solution

**B1. Claim under test.** The check at `InMemoryTrie.java:145` does not cap memory or disk usage: it is a chunk-boundary test that triggers buffer allocation; total trie size is determined by the number of blocks written and bounded elsewhere (line 148, `ALLOCATED_SIZE_THRESHOLD`).

### B2. Unit tier

n/a: no constraint, the check has no limit value to push usage against. The evidence in A3 (both branches, chunk-start arithmetic from `InMemoryReadTrie.java:231-251`) answers the question. Optional sanity check an engineer may run from a scratch JVM against a build of the tag: call the package-private `advanceAllocatedPos(n)` (test-only, line 962) on a new `InMemoryTrie<String>(BufferType.ON_HEAP)` and observe via `sizeOnHeap()` that allocated bytes grow in 32-byte steps and that a new chunk (256, 512, 1024, ...) appears only at positions 0, 256, 768, 1792, ...; no knob changes any of this.

#### B2 amendment, 2026-10-29 (stage-4 audit; applies `none-type-design.md` §3-§4; changes no estimate; B2 as filed is `n/a` plus an optional sanity check, and is replaced by this design)

**Operand kind: 1, not 3** (the stage-4 draft's correction, confirmed): `v` is `allocatedPos` (InMemoryTrie.java:70, read at 144), bytes already handed out, a running size of held data. No caller sets a requested length. The check at 145 is the allocation trigger: it decides whether `bufferType.allocate(256 << leadBit)` runs (151). It can only be a trigger, not a limit; "usage follows the operand" is expected and is not a finding. The finding is the allocation the true branch makes, against the false branch at the neighbouring block. All citations in A1-A3 hold (`InMemoryTrie.java:70, 140-160, 145, 148, 151, 158, 953, 961-966, 975-981`; `InMemoryReadTrie.java:127, 207-208, 215, 231-251`; callers at 433, 451, 476, 497, 964). Audit corrections: (1) `sizeOnHeap()` (InMemoryTrie.java:975-981) counts `allocatedPos` (bytes handed out), not the buffers' capacities: the chunk `256 << i` is allocated when only 32 bytes of it are used, and the term `REFERENCE_ARRAY_ON_HEAP_SIZE * getChunkIdx(allocatedPos, ...)` steps when `allocatedPos` **reaches** a chunk start, i.e. on the preceding (false) block, not on the allocating (true) block; the draft's prediction put the step on the wrong call. (2) Setting up by `advanceAllocatedPos(S_i)` from a fresh trie would put every earlier chunk inside the measured window; the setup is done outside the window (item a). (3) The draft's sweep point `i = 0` has no preceding mid-chunk block; the sweep starts at `i = 1`. (4) The draft's control (the soft threshold, line 953) is a signal, not an allocation; the control below uses the hard limit at line 148 instead, in the same instrument.

**a. Trigger.** New JUnit class `InMemoryTrieAllocBlockTest` in package `org.apache.cassandra.db.tries` (needed: `advanceAllocatedPos`, `allocatedPos`, `buffers` and `ALLOCATED_SIZE_THRESHOLD` are package-private or private), run with `java` + JUnitCore, **no Byteman** (the allocation itself is the proof the branch ran; `allocatedPos` and `buffers[i]` are read by reflection). Chunk starts are `S_i = 256 * (2^i - 1)` (0, 256, 768, 1792, ...), the buffer allocated there is `N_i = 256 << i` bytes. For each `i`: a fresh `new InMemoryTrie<String>(BufferType.ON_HEAP)`; setup `advanceAllocatedPos(S_i - 32)` outside any window (allocatedPos = S_i - 32); measured call **A** = `advanceAllocatedPos(S_i)` (exactly one block, at `S_i - 32`, mid-chunk, check false); measured call **B** = `advanceAllocatedPos(S_i + 32)` (exactly one block, at `S_i`, a chunk start, check true).

**b. Sweep (stated before the run).** i in {1, 3, 7, 11, 15, 19}: N_i = 512 B, 2 KiB, 32 KiB, 512 KiB, 8 MiB, 128 MiB (six octaves of the guarded buffer; `-Xmx1g`). One discarded warm-up cycle, then 5 repetitions per i on fresh tries. An empty window (two `getThreadAllocatedBytes` reads with nothing between) is read 5 times per i as the instrument floor. Off-heap arm: `BufferType.OFF_HEAP` at i = 11 and 15 (the same A and B). Control JVM (item f): `-Xmx6g`, ON_HEAP.

**c. Measure.** `ThreadMXBean.getThreadAllocatedBytes` around each single call (the instrument of `harness/batch_size_fail_threshold-...--guided/Alloc.java`, called directly); `allocatedPos` and `buffers[j]` (null or capacity) by reflection before and after; `sizeOnHeap()` before and after; the sum of retained buffer capacities; for the off-heap arm the JDK `BufferPoolMXBean` "direct" `getMemoryUsed()` before and after (direct allocation is invisible to the thread counter).

**d. Branch flip.** A against B on the same trie: the two calls differ in the check and in nothing else (both advance `allocatedPos` by 32).

**e. Prediction (frozen with this amendment).** For every i and repetition, with R = `REFERENCE_ARRAY_ON_HEAP_SIZE` (InMemoryTrie.java:78) read by reflection:
- Instrument floor (empty window) at most 1 KiB.
- **A:** allocated bytes at most 1 KiB (expected 0); `allocatedPos` S_i - 32 -> S_i; `buffers[i]` still null; `sizeOnHeap()` delta = 32 + R (the chunk-index step occurs on this call); retained buffer total = S_i.
- **B:** allocated bytes between N_i + 16 and N_i + 512; `allocatedPos` S_i -> S_i + 32; `buffers[i]` non-null with capacity N_i; `sizeOnHeap()` delta = 32; retained buffer total = S_i + N_i = S_{i+1}.
- Therefore B - A is between N_i and N_i + 512 at every i, and the residue (B - N_i) differs between any two values of i by at most 256 B.
- Off-heap arm (i = 11, 15): B raises the JDK direct gauge by exactly N_i, A by 0; thread-allocated bytes of B at most 1 KiB (the instrument does not see the buffer).
- Retained-to-used ratio after B (retained buffer total / `allocatedPos`) is reported; it lies between 1 and 2 by construction (doubling chunks).
- **Control (item f), same instrument:** `i = 22` (N_22 = 2^30 B): B between 2^30 + 16 and 2^30 + 512 B; then `advanceAllocatedPos(S_23)` with `S_23 = 2147483392`: at most 1 KiB (false blocks only); then `advanceAllocatedPos(S_23 + 32)`: throws `SpaceExhaustedException` with at most 4 KiB allocated (against the 2^31 B the unbounded pattern would allocate, 256 << 23), and `allocatedPos` stays 2147483392.
- Noise: the five repetitions of one call at one i differ by at most 256 B.

**f. Positive control (B2h).** The hard limit at line 148 (`leadBit + BUF_START_SHIFT == 31`, i.e. the chunk after `S_23`) is a statement that does stop this allocation: in the control JVM the same instrument that reads N_i at every chunk start reads at most 4 KiB and an exception at `S_23`. It binds on the same resource (the trie's buffer bytes), at a different statement (see the closed case `trie_2gb_hard_limit-allocateblock-leadbit`), and it shows that "flat" is distinguishable from "the instrument cannot see a cap".

**g. Conclusions table (B2g).**

| Reading | Verdict | Effect on the constraint |
|---|---|---|
| A allocates nothing, B allocates N_i (within the stated bounds) at every i, positions and `sizeOnHeap()` steps as predicted, retained buffers = S_i + N_i, control stopped by line 148 | **Confirmed** | `does not cap`. The check is the allocation trigger; usage follows the blocks written (`allocatedPos`) with at most 2x slack from doubling chunks; no limit at line 145. |
| B allocates less than N_i, or nothing, at a chunk start with i < 22, or an exception or refusal is raised at line 145 for i < 22, or A allocates a buffer | **Refuted** | `caps` (the check limits what is held) |
| The control did not throw or still allocated, or the floor is above 1 KiB, or a position does not match | **Not confirmed** / **Invalid** | `undetermined` |
| The `sizeOnHeap()` step lands on the other call than predicted, but the allocation figures hold | **Confirmed** with the miss recorded | `does not cap` (the accounting figure is secondary) |

**h. Hold fixed.** JDK 11, `-Xmx1g` (control `-Xmx6g`), one thread, no yaml (the trie needs no `DatabaseDescriptor` beyond `CassandraRelevantProperties`), `cassandra.memtable.row_overhead_size` unset (its default threshold, ALLOCATED_SIZE_THRESHOLD, is not reached by the sweep).

### B3. Cluster tier

**B3 amendment, 2026-10-29:** stays `n/a`; reason as filed, plus: the trie is a TrieMemtable detail, the sweep points are exact positions that only the test hook (`advanceAllocatedPos`) reaches, and 512 B to 128 MiB of buffers is below or at heap noise (about 16 MiB with G1) for all but the top points. As filed: n/a: no constraint, there is no setting that moves this check, and a cluster run can only restate the memtable-size behaviour governed by `cassandra.memtable.row_overhead_size` / the flush threshold (other statements). Evidence in A2/A3 answers the question instead.

**B4. Risks and cleanup.** None for the design above; if the optional unit sanity check is run, build in a private copy of the tree, not the shared source, and stop the JVM.

## C. Sources read

- `src/java/org/apache/cassandra/db/tries/InMemoryTrie.java` (lines 41-200, 430-500, 940-1030)
- `src/java/org/apache/cassandra/db/tries/InMemoryReadTrie.java` (127-260)
- `src/java/org/apache/cassandra/db/memtable/TrieMemtable.java` (175-215)
- `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java` (350-358, 881-888)
- `test/unit/org/apache/cassandra/db/tries/InMemoryTriePutTest.java` (60-110)

## D. Stage-4 feedback

**2026-10-29 — unit tier run and self-checked; B3 `n/a`.** Results: [`results/no_constraint-allocateblock-inchunkpointer--autonomous.md`](../../stage4-runtime-verification/results/no_constraint-allocateblock-inchunkpointer--autonomous.md). Verdict **Confirmed — does not cap** (outcome class: true negative). The frozen text is everything above this section (B2 amendment of 2026-10-29); the estimate is unchanged.

- Readings (i = 1, 3, 7, 11, 15, 19, N_i = 512 B to 128 MiB, 5 repetitions, exact): the mid-chunk block A allocated 0 bytes; the chunk-start block B allocated N_i + 96 bytes (608, 2144, 32864, 524384, 8388704, 134217824), the residue 96 bytes at every i; empty-window floor 0. Positions, `buffers[i]` null then N_i, retained buffers = S_i then S_i + N_i, all as predicted. Control (i = 22): B allocated 1,073,741,920 B; advancing to S_23 = 2,147,483,392 allocated 0 B; the next block threw `SpaceExhaustedException` after 1,584 B (against 2^31 B), `allocatedPos` stayed 2,147,483,392. Off-heap arm: the JDK direct gauge moved by exactly N_i (524,288 and 8,388,608) while the thread-allocated reading was 168 B, i.e. the instrument is blind to the buffer there.
- Kind 1 (the draft's correction) confirmed. Audit corrections: `sizeOnHeap()` counts `allocatedPos`, not buffer capacities, and its chunk-index term steps on the block that **reaches** a chunk start (call A: +32 + R, R = 32), not on the allocating block (call B: +32); the draft had the step on B. All citations in A1-A3 held.
- Observation outside the claim: right after the allocating block, the retained buffers are 2.0x to 2.7x `allocatedPos` (2.667 at i = 1, 2.000 at i >= 11), while `sizeOnHeap()` reports `allocatedPos` plus constants: the live trie's buffer capacity can be up to about twice what `sizeOnHeap()` accounts at that moment. Not tested against TrieMemtable's own accounting.
- Weaker than it looks: the check cannot be flipped without editing the source, so "flip" is the neighbouring-block pair; the control is a different statement (line 148) in the same instrument. Unit tier only (B3 `n/a`).
