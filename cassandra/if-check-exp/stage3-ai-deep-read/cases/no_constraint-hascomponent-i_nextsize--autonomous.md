# no_constraint — ClusteringPrefix.Deserializer.hasComponent — verification solution  <!-- file: cases/no_constraint-hasComponent-i_nextSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | helper `org.apache.cassandra.db.ClusteringPrefix$Deserializer.hasComponent(int)`; its check [`ClusteringPrefix.java:653`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L653) (`if (i >= nextSize)`), loop at [`:656`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L656) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI (Agent SDK), 2026-10-27 |
| Estimate | `negative`: no constraint. The check is a bounds test on a component index against the clustering size, and a loop that deserializes components up to that index; it caps no memory or disk. |
| Ground | Bookkeeping / loop control. The memory allocated is governed elsewhere (`nextSize`, and the per-value read limit). |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands of the check at [`ClusteringPrefix.java:653`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L653):
- `i`: the parameter, a component index supplied by the caller `compareNextTo`, the loop variable `for (int i = 0; i < bound.size(); i++)` at `ClusteringPrefix.java:633`. It ranges over the bound's size.
- `nextSize` (field, declared `ClusteringPrefix.java:597`): set in `prepare()` at `:612` to `comparator.size()` for a row (the table's clustering column count) or `in.readUnsignedShort()` (bound size read from the sstable) otherwise.
- loop condition `deserializedSize <= i` (`:656`): `deserializedSize` is a field (`:599`) reset to 0 in `prepare()` (`:613`) and incremented in `deserializeOne()` (`:675`).
No yaml entry, JVM property or constant takes part.

**A2. What it caps.** Nothing. The check decides whether the in-progress clustering has a component at index `i`: false means the sstable-side clustering is shorter than the bound (the caller returns `nextKind.comparedToClustering`), true means deserialize components lazily up to `i`. The memory involved is `nextValues = new byte[nextSize][]` (`:620`, sized from `nextSize`, at most 65535 slots from the unsigned short or the clustering column count) plus the component bytes, which `deserializeOne()` reads with `readArray(in, DatabaseDescriptor.getMaxValueSize())` (`:677`). That value-size limit is a separate check inside `deserializeOne()`, not this helper, and the helper only prevents reading past `nextSize`. So the check bounds no held object.

**A3. Mechanism.** Enclosing method: `hasComponent(int)`, [`ClusteringPrefix.java:651-660`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L651-L660), private, single definition and no overloads.
- Outcome `i >= nextSize` ([`:653`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L653)): return false, nothing is read.
- Otherwise `while (deserializedSize <= i) deserializeOne();` (`:656-657`) reads components from the input until index `i` is available, then returns true. `deserializeOne()` (`:662-678`) itself returns false once `deserializedSize == nextSize`, so the loop terminates because `i < nextSize`.
- Call sites read: the only caller is `compareNextTo` at `ClusteringPrefix.java:636`. `compareNextTo` is called by `UnfilteredDeserializer.compareNextTo` (`UnfilteredDeserializer.java:115`) and from `AbstractSSTableIterator.java:495,530`, `big/SSTableIterator.java:170`, `big/SSTableReversedIterator.java:206,238`, `bti/SSTableReversedIterator.java:195,217` (seen by grep; these are slice-bound comparison loops).
- Bypass or overshoot: none relevant; the lazy deserialization only lowers allocation versus deserializing everything (see the comment at `:615-618`).

**A4. Other consumers.** n/a: no resource is capped here. The related memory (clustering values) is read by `deserializeOne` under `DatabaseDescriptor.getMaxValueSize()` and by `deserializeAll`/`skipNext`, none controlled by this check.

**A5. Evidence beyond the source.** Searched: callers of `hasComponent` (grep: only `:636`), `compareNextTo` callers (above), the class Javadoc at `:580-587` (describes lazy deserialization to do as little work as possible). No config key, doc, test or history item ties this check to a limit. `none` otherwise (the source copy has no git history).

## B. Verification solution

**B1. Claim under test.** The check `i >= nextSize` / loop in `hasComponent` does not cap memory or disk usage; it is index-bounds and loop control.

### Amendment 2026-10-29 (stage-4 audit, before the freeze): B2 and B3 filled in (they were `n/a: no constraint`)

Operand kind (none-type-design.md section 2): **1, a count of held data** (`nextSize`, the component count of the clustering prefix being read, against the index `i` of the probe bound). The filed text declared both tiers `n/a`; the audit finds a design that
answers the stage-4 question (does the check change what is allocated?) at the unit tier. Citations re-read in `cassandra/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java`. **Corrections** (feedback in section D; none changes the claim):
`nextSize` is set at **:617** (A1 says :612) and `deserializedSize` is reset at **:618** (A1 says :613), incremented at **:670** (A1 says :675); `nextValues = new byte[nextSize][]` is at **:626** (A2 says :620); the `compareNextTo` loop is at **:634** (A1 says :633); `readArray(in, DatabaseDescriptor.getMaxValueSize())` is at **:674**
(A2 and A3 say :677) and `deserializeOne` spans :662-676. Correct as filed: declaration of `nextSize` :597, `deserializedSize` :599, `prepare` from :610, check :653, loop :656-657, `hasComponent` :651-660 (private, the only caller :636), `UnfilteredDeserializer.java:115`,
`AbstractSSTableIterator.java:495,530`, `big/SSTableIterator.java:170`, `big/SSTableReversedIterator.java:206,238`, `bti/SSTableReversedIterator.java:195,217`. The claim in A2 that the check "bounds no held object" is kept; what is measured is whether the false return changes any allocation.

### B2. Unit tier (amended 2026-10-29)

**B2a. Environment and build.** JDK 11, Ant 1.10; a `copy-source.sh` copy built with `ant build-test`; one JUnit class `ClusteringHasComponentTest` (package `org.apache.cassandra.db`, harness `harness/no_constraint-hascomponent-i_nextsize--autonomous/`) compiled into the copy and run with the plain `java` launcher and `org.junit.runner.JUnitCore` (`-Xmx1g`, node module flags from `conf/jvm11-server.options`, `-javaagent:jamm`), Byteman only in the proof run.
**B2b. Knobs.** The pair (`nextSize`, S) where S is the size of the probe bound, so `i` runs over 0..S-1: S below, equal to and above `nextSize`. Component size 1,024 bytes (and 65,536 for the control). `DatabaseDescriptor.setMaxValueSize` (DatabaseDescriptor.java:1933) for the second control.
**B2c. Workload.** A `TableMetadata` with 16 `BytesType` clustering columns; `comparator = metadata.comparator`; `SerializationHeader.makeWithoutStats(metadata)`. For each point: a `ClusteringBound` (`INCL_START_BOUND`) of `nextSize` components, component j = 1,024 bytes all equal to (byte) j, serialized with `ClusteringBoundOrBoundary.serializer.serialize(...)` into a `DataOutputBuffer` (stream = kind byte, unsigned short size, header vint, values); a fresh `DataInputBuffer` and `new ClusteringPrefix.Deserializer(comparator, in, header)` per repeat; `prepare(0x02, 0)` (0x02 is `UnfilteredSerializer.IS_MARKER`, which is private; `UnfilteredSerializer.kind(0x02)` is asserted to be `RANGE_TOMBSTONE_MARKER` first) outside the window; then `compareNextTo(probe)` where `probe` is an `INCL_START_BOUND` of S components with the same bytes as the stored ones for j < `min(S, nextSize)` and component j = (byte) j beyond (so the comparison never returns early on a mismatch).
**B2d. Observables.** (1) `ThreadMXBean.getThreadAllocatedBytes` for the calling thread directly before and after `compareNextTo` with nothing else in the window (as `batch_size_fail_threshold-...--guided/Alloc.java`); 3 warm-up and 7 timed repeats per point, median, min, max. (2) `deserializedSize` after the call, read by reflection. (3) In a separate Byteman run: a counter for `hasComponent` returning false (`AT LINE 654`, tracing `$i` and `$0.nextSize`) and for `deserializeOne` entries. Instrument checks first: an 8 MiB `byte[]` reads 8 MiB to 8 MiB + 64 KiB; an empty window is the instrument baseline.
**B2e. Procedure.**
1. Instrument checks. 2. Noise block 1: (4,4), 7 repeats. 3. Sweep, in this order: (1,1), (2,1), (2,2), (2,4), (4,2), (4,4), (4,8), (8,8), (8,16), (16,16). 4. Noise block 2: (4,4), 7 repeats. 5. Control A: component size 65,536 at (4,4). 6. Control B: `setMaxValueSize(512)` at (4,4) with 1,024-byte components: the call must throw instead of allocating; restore the value afterwards. 7. The same sequence in a Byteman JVM for the branch counts.
**B2f. Predictions (frozen).** A 1,024-byte component is a `byte[1024]` = 1,040 bytes. The allocation inside the window is `min(S, nextSize)` components:
(1,1) 1,040; (2,1) 1,040; (2,2) 2,080; (2,4) 2,080; (4,2) 2,080; (4,4) 4,160; (4,8) 4,160; (8,8) 8,320; (8,16) 8,320; (16,16) 16,640 bytes; tolerance the larger of +-10 percent and +-256 bytes. `deserializedSize` after the call equals `min(S, nextSize)` exactly. The false return happens exactly once per call when S > `nextSize` and never when S <= `nextSize` (Byteman).
Branch-flip pairs with S on opposite sides of `nextSize` and the same predicted allocation, (2,2)|(2,4), (4,4)|(4,8), (8,8)|(8,16): the medians differ by at most max(2 x noise floor, 256 bytes). Noise floor: from the two (4,4) blocks, max(range within a block, |difference of the two block medians|); predicted below 256 bytes. Control A: 4 x 65,552 = 262,208 bytes +-10 percent, at least 50 times the 1,024-byte (4,4) reading. Control B: the call throws and the allocation is below 1,040 bytes plus the exception.
**B2g. Readings.**

| Observation | Meaning | Verdict | Effect |
|---|---|---|---|
| the allocations follow `min(S, nextSize)` x 1,040 within tolerance, every flip pair within max(2 x noise, 256 bytes), both branches observed, control A moved | allocation follows the stored data (the operand is the data itself); the false return changes nothing allocated | Confirmed | does not cap |
| a flip pair differs by more than max(2 x noise, 256 bytes) and the difference is explained by what the false return skips or adds | the check gates an allocation | Refuted | caps |
| the sweep is flat or does not follow the data, but control A moved | something other than `deserializeOne` allocates in the window | Not confirmed | undetermined |
| a flip-pair difference between the noise floor and twice the floor | not resolved | Not confirmed | undetermined |
| control A did not move, the false return was never observed for S > `nextSize`, or `deserializedSize` is not `min(S, nextSize)` | the experiment could not show an effect | Invalid / Not confirmed | undetermined |
| numeric predictions missed (for example a constant overhead) while the flip pairs and the data-following relation hold | arithmetic off | Confirmed, with the miss recorded | does not cap |

Note (none-type-design.md section 6): the operand is the data itself, so "allocation follows `nextSize`" is expected and is not a positive finding; the finding is the flip-pair comparison. Control B shows the real limit (`max_value_size`) acting on the same allocation.
**B2h. Controls.** Same bytes in stored and probe components; fresh Deserializer per repeat; `prepare` outside the window (it allocates `byte[nextSize][]`); no agent in the instrument run; control A with the same code and a larger component; control B with a real limit.

### B3. Cluster tier

`n/a: below heap noise.` One `compareNextTo` call allocates at most a few tens of KiB (16,640 bytes for the largest point) and the allocation is garbage immediately; a node-level reading has heap noise of about +-16 MiB with G1, three orders of magnitude larger. The unit tier decides.

**B3a-B3h.** n/a, see B3.

**B4. Risks and cleanup.** Unit tier only: the copy under `~/s4-none` on the run node and `~/stage4-logs/none/`; no daemon is started. Nothing is run under `/proj`.

## C. Sources read

- `src/java/org/apache/cassandra/db/ClusteringPrefix.java` (lines 585-720)
- grep results over `src/` for `hasComponent` and `compareNextTo`

## D. Stage-4 feedback

**2026-10-29, stage 4 (autonomous, unit tier only; results: [`results/no_constraint-hascomponent-i_nextsize--autonomous.md`](../../stage4-runtime-verification/results/no_constraint-hascomponent-i_nextsize--autonomous.md)).** Verdict: **Confirmed, does not cap**; outcome class **true negative** (estimate `negative`). Cluster tier `n/a: below heap noise`. B2/B3 were `n/a: no constraint` as filed and were filled in by the 2026-10-29 amendment (section B) before the freeze; the estimate is unchanged.
Readings: allocation around `compareNextTo` is `min(S, nextSize) x 1,040` bytes at all ten (nextSize, S) points (1,040 ... 16,640), identical on both sides of `i >= nextSize` (flip pairs (2,2)|(2,4), (4,4)|(4,8), (8,8)|(8,16): difference 0), noise floor 0, one false return per call exactly when S > nextSize (Byteman), 64 KiB components moved the allocation 63 x.
Feedback for stage 3 (none changes the claim):
1. Line citations off in A1-A3 (pinned source): `nextSize` is set at :617 (A1: :612), `deserializedSize` reset at :618 (:613) and incremented at :670 (:675), `nextValues = new byte[nextSize][]` at :626 (:620), the `compareNextTo` loop at :634 (:633), `readArray(in, DatabaseDescriptor.getMaxValueSize())` at :674 (:677; `deserializeOne` spans :662-676). Correct: :597, :599, :610, :636, :651-660, :653, :656-657 and the caller list.
2. The filed `n/a: no constraint` could have been run: a `Deserializer` is public, and a serialized bound plus a probe bound drive `prepare` and `compareNextTo` with no sstable (stream = kind byte, unsigned short size, header vint, values; `prepare(0x02, 0)` selects the marker branch because `UnfilteredSerializer.IS_MARKER` is private).
3. `DatabaseDescriptor.setMaxValueSize(int)` (DatabaseDescriptor.java:1933-1937) divides by 1 MiB, so any value below 1 MiB sets a limit of 0 (our control B ran with 0, not 512 bytes).
