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

### B3. Cluster tier

n/a: no constraint, there is no setting that moves this check, and a cluster run can only restate the memtable-size behaviour governed by `cassandra.memtable.row_overhead_size` / the flush threshold (other statements). Evidence in A2/A3 answers the question instead.

**B4. Risks and cleanup.** None for the design above; if the optional unit sanity check is run, build in a private copy of the tree, not the shared source, and stop the JVM.

## C. Sources read

- `src/java/org/apache/cassandra/db/tries/InMemoryTrie.java` (lines 41-200, 430-500, 940-1030)
- `src/java/org/apache/cassandra/db/tries/InMemoryReadTrie.java` (127-260)
- `src/java/org/apache/cassandra/db/memtable/TrieMemtable.java` (175-215)
- `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java` (350-358, 881-888)
- `test/unit/org/apache/cassandra/db/tries/InMemoryTriePutTest.java` (60-110)

## D. Stage-4 feedback

`none yet`
