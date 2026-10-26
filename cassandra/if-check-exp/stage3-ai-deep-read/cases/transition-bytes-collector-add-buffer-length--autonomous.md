# transition-bytes-collector — add — buffer-length — verification solution <!-- file: cases/transition-bytes-collector-add-buffer-length--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/io/tries/Walker.java:442` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (Claude Code, autonomous stage-3 agent), 2026-10-26 |
| Estimate | `negative`: line 442 is the capacity check of a scratch byte[] whose length is the depth of one trie walk; no configuration entry, property or limit governs it. |
| Ground | The buffer holds one trie path (one term/key) and is only reached from `getMinTerm`/`getMaxTerm` and from `ValueIterator` built with `collecting=true`. Neither is on a production path in 5.0.9 (only tests use them). Where a bound exists it is indirect and belongs to someone else: key/term size limits (SAI `sai_string_term_size_fail_threshold`, 8KiB) and the growth cap inside Lucene `ArrayUtil.grow`. The object is KB-scale and short-lived, so it is not memory- or disk-significant. |

## A. Constraint trace

**A1. The constraint.** The only "limit" at the target is the array capacity test `pos == bytes.length` (`Walker.java:442`), with initial capacity 32 (`Walker.java:437`). Growth is `ArrayUtil.grow(bytes, pos + 1)` (`Walker.java:444`), imported from `org.apache.lucene.util.ArrayUtil` (`Walker.java:32`). That is a library oversizing routine, not a Cassandra setting. Kind: constant / library behaviour. Unit: bytes. The initial 32 is a hard-coded literal. Not settable by yaml, `-D` or JMX; a change needs a source edit. There is no resource-capping constraint declared here. The nearest real limits on the path length are upstream: SAI term-size guardrails `sai_string_term_size_{warn,fail}_threshold` (1KiB/8KiB, `Config.java:941-942`, `sai_frozen_*` at 943-944, enforced via `StorageAttachedIndex.java:207-210`, 773-785, 825) and the 64KiB-class partition key limit. Those cap the input that becomes a trie path, not the collector.

**A2. What it caps.** Nothing. `pos` is compared with `bytes.length` only to decide whether to reallocate. The resource touched is heap (a transient byte[]), sized by the longest trie path walked, including the final copy in `toByteComparable` (`Walker.java:455-462`).

**A3. Mechanism.** `add(int b)` (`Walker.java:440`): if `pos == bytes.length` it grows the array (444), then stores `(byte) b` at `bytes[pos++]` (446). `pop()` (449-453) decrements `pos` (the `assert pos >= 0` is weak: it checks before decrementing). `toByteComparable()` returns null if `pos <= 0`, otherwise copies `pos` bytes (457-462). Callers:
- `Walker.getMaxTerm` (352-367) and `getMinTerm` (369-382): walk root to a leaf, adding one byte per level. The buffer length equals the path depth. No production caller found in `src/java` (grep); only `test/unit/.../TrieTermsDictionaryTest.java:140,144`.
- `ValueIterator` with `collecting=true` (`ValueIterator.java:74,107`): `collector.add` on descent (250), `collector.pop` on backtrack (226), read by `nextCollectedValue` (205-209). The BTI users (`PartitionIndex.IndexPosIterator`, `PartitionIndex.java:395-407`; `RowIndexReverseIterator`) use constructors that pass `collecting=false`. Only the test class `TrieTermsIterator` (`test/unit/.../trie/TrieTermsIterator.java`) uses `collecting=true`.
Overshoot / bypass: growth is geometric (Lucene oversize), so capacity can exceed the needed length by roughly 1/8 or more. Because the collector is bounded only by trie depth, nothing caps it other than the size of the stored keys.

**A4. Other consumers.** The trie file pages are served through the buffer cache / chunk cache (`file_cache_size`) and `Rebufferer` (`Walker.java` `source`, `bh`), the real memory/disk consumers of a walk. The trie files themselves are disk usage governed by data volume. The collector is negligible next to these.

**A5. Evidence beyond the source.** none (code search only, 5.0.9 tree; Lucene `ArrayUtil.grow` semantics taken from the Lucene javadoc, to be confirmed against the jar in `lib/`).

## B. Verification solution

**B1. Claim under test.** The collector's memory (heap bytes of `bytes`) does not follow any configured limit: it tracks only the length of the longest path walked (about `ceil`-oversized path length, minimum 32 bytes), is independent of every yaml/`-D` knob, and is never exercised by a running node's read/write/compaction path in 5.0.9.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`stage4-runtime-verification/copy-source.sh <dir>`; never build in the shared tree), then `ant build-test`. Write the harness as a JUnit class in the copy, `test/unit/org/apache/cassandra/io/tries/CollectorGrowthTest.java` (package access to the protected `bytes`/`pos`), modelled on `AbstractTrieTestBase`/`TrieTermsDictionaryTest` for building a trie (`IncrementalDeepTrieWriterPageAware` with `TrieTermsDictionaryReader.trieSerializer` into an in-memory `DataOutputBuffer`, read through `ByteBufRebufferer` by a `TrieTermsDictionaryReader`). Run `ant testsome -Dtest.name=org.apache.cassandra.io.tries.CollectorGrowthTest` (the forked JVM has 1 GiB; its `-Xmx` cannot be lowered through Ant). The `-Xmx` variants of B2e step 4 run the same class in a plain `java -Xmx<n> org.junit.runner.JUnitCore` command, with the class path and JVM arguments the Ant run recorded.
> **[Amended 2026-10-26, audit R1, R2]** Replaced `rsync ~/cassandra-5.0.9` / `ant jar`, the `/tmp` files, `IncrementalTrieWriterPageAware` (recursive; a 65535-byte chain needs the deep writer) and the `-Xmx512m -XX:+UseSerialGC` line; reason: `ant testsome` forks a fixed 1 GiB JVM, the in-memory buffer avoids the disk, and the deep writer handles depth 65535.

**B2b. Knobs.** The trie path length L (key length in bytes) in {8, 32, 33, 1024, 8192, 65535}: 32/33 straddle the initial capacity (`Walker.java:437`), 8192 is the SAI fail threshold, 65535 the unsigned-short key bound. Set by constructing one key of length L. Second knob: SAI `sai_string_term_size_fail_threshold` (set via `DatabaseDescriptor`/`Config` in the harness) to show it does not change the collector for a given L.

**B2c. Workload.** Build a one-key trie of L bytes (a pure chain, depth about L, in ByteComparable form with the 0x40-style terminator). Call `getMaxTerm()` and `getMinTerm()` and, via the test-only `TrieTermsIterator`, iterate with `collecting=true`. Reaching "the limit" means `pos == 32` (L>=33) and repeated grows (L up to 65535). Arithmetic: for L=33 exactly one grow occurs; for L=65535 there are many (geometric growth with ratio about 1.125, see B2f).
> **[Amended 2026-10-26, audit R3]** The filed "about 20-30 reallocations" was wrong. Lucene 9.7.0 (`lib`/`build/lib/jars/lucene-core-9.7.0.jar`) `ArrayUtil.grow(byte[], n)` allocates `oversize(n,1)` = `n + max(3, n>>3)` rounded up to a multiple of 8. Calling it in a loop from 32 gives: L=33 -> capacity 40 (1 grow); L=65535 -> capacity 69,368 after 59 grows, the arrays allocated summing to 622,768 bytes including 16-byte headers. This was computed by running the library method alone (no trie, no Cassandra), not from any reading of the experiment.

**B2d. Observables and instruments.** (1) `bytes.length` and `pos` of the collector: for a standalone `TransitionBytesCollector` (fed L `add()` calls, the exact same code as `getMaxTerm`/`getMinTerm`) through a same-package subclass; for the `collecting=true` iterator (`TrieTermsIterator`) by `setAccessible` on `ValueIterator.collector` after the iterator is drained (`bytes` keeps its length after `pop`). The collector local to `getMaxTerm`/`getMinTerm` cannot be read; for those calls only (2) is available. (2) Allocated bytes per call via `com.sun.management.ThreadMXBean.getThreadAllocatedBytes` before/after, with a warm-up. (3) Length of the returned `ByteComparable` bytes. Cannot be observed directly: Lucene's internal oversizing formula (read from the jar's class, or measured as the capacity sequence).

**B2e. Procedure.**
1. Copy and build as in B2a.
2. For each L: build the one-key trie in memory, open the reader, warm up 1000 calls.
3. Record `getThreadAllocatedBytes` around 100 calls to `getMaxTerm()`; record collector capacity via a subclass copy that exposes the collector (or a standalone `TransitionBytesCollector` fed L `add()` calls, which is the exact same code).
4. Repeat with the guardrail threshold at 1KiB/8KiB/default and with `-Xmx` 256m/512m.
5. Run the positive control (B2h).
6. Delete the working tree.

**B2f. Predictions.** (1) Capacity is 32 for L<=32; for L>=33 it is L <= capacity <= L + L/8 + 10 (Lucene 9.7.0 `oversize`: first grow 33 -> 40; L=65535 -> 69,368). The capacity is the same for the same L under every guardrail value and every `-Xmx` (relation: capacity independent of knobs, monotone in L). (2) Auxiliary, for `getMaxTerm()`/`getMinTerm()` (thread-allocated bytes after warm-up): at least S(L) + L, where S(L) is the summed size (+16 B header) of the arrays the collector allocates, computed by feeding L `add()` calls to a standalone collector (S = 104 for L=33; 622,768 for L=65535), and at most S(L) + L + 65,536. (3) The `collecting=true` iterator and the standalone collector give the same capacity as (1) for the same L. Wrong if capacity depends on any configuration value, if it stays at 32 for L>32 (no growth), or if (1) is violated.
> **[Amended 2026-10-26, audit R3]** Replaced the filed text, which said capacity "between L and about 1.2L+" and "for L=65535 below roughly 300KB, for L=8 about 100-200 bytes". The 300 KB bound contradicts Lucene's growth (the arrays alone sum to 622,768 B); (1) states the exact band; (2) states the allocation as an auxiliary lower/upper bound with the slack stated.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| capacity depends only on L; same under all guardrail/-Xmx values | claim confirmed |
| capacity or allocation changes when a config knob changes | claim refuted: a configured limit does bind |
| capacity grows without bound for L past 65535 with no exception | no cap exists at the collector (consistent with claim) |
| capacity independent of every knob but outside the band L..L+L/8+10 at some L, or allocation outside (2) | claim confirmed on knob-independence; the numeric band is mis-specified (auxiliary sub-claim) and the results file says so; not a refutation |
> **[Amended 2026-10-26, audit R3]** The row above was added.
| allocation flat in L while the control moves | not expected; would indicate measurement is wrong |
| the control (B2h) does not move | not confirmed, instrument invalid |

**B2h. Controls.** Positive control: a cap known to bind on the same bytes: `Guardrails.saiStringTermSize.failsOn(size, null)` (the check `StorageAttachedIndex.validateTermSize` applies, `StorageAttachedIndex.java:807-830`) with the fail threshold set through `DatabaseDescriptor.getGuardrailsConfig().setSaiStringTermSizeThreshold(...)` to 1KiB, 8KiB and 64KiB: it must fail exactly the sizes above the threshold (e.g. 8193 B fails at 8KiB, passes at 64KiB) while the collector accepts the same L with the same capacity. Also a `new byte[L]` baseline to show the allocation measurement counts a known array (tolerance 64 B).

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, a local copy built by `copy-source.sh` + `ant build-test`, `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` on local disk (budget 5 GB). `-Xmx1g`, G1, `-XX:-HeapDumpOnOutOfMemoryError`. Config: `sstable: selected_format: bti` so the trie code under test is the one in use (`big` for the control lifetime); SAI needs no switch in 5.0.9. `storage_compatibility_mode: NONE` in all four lifetimes (the node refuses `bti` under the default `CASSANDRA_4`: "Selected sstable format 'bti' is not available when in storage compatibility mode 'CASSANDRA_4'", found by the shakedown on 2026-10-26; the same mode in the `big` lifetime keeps the lifetimes comparable).
> **[Amended 2026-10-26, runbook defect D2, found by the shakedown: with the default `AllowAllAuthenticator` every client is a superuser and `Guardrail.enabled(state)` (`Guardrail.java:93-96`, `ClientState.java:602-605`) skips the SAI term-size guardrail, so the 8191-byte and 40960-byte values were accepted under a 1KiB threshold; B3f (c) and B3h could not hold]** The nodes run `authenticator: PasswordAuthenticator` and `authorizer: CassandraAuthorizer`; a superuser creates the schema and an ordinary role `tcw` (LOGIN, ALL on keyspace `ks`), and every load and read uses `tcw`. B3f/B3g are unchanged.
> **[Amended 2026-10-26, runbook defect D1, found by the harness shakedown before run 1; does not touch B2f/B2g/B3f/B3g]**

**B3b. Knobs.** (i) `sai_string_term_size_fail_threshold` in {1KiB, 8KiB (default), 64KiB}; (ii) partition key length in {100 B, 8 KiB, 60 KiB}; (iii) `sstable.selected_format` bti vs big (control). Set via yaml, one node lifetime per row: T1k, T8k (default), T64k with bti and BIG (8KiB, big format).

**B3c. Workload.** `cqlsh`/`cassandra-stress`: table `t(pk blob, ck int, v text, PRIMARY KEY(pk, ck))` with SAI index on `v`. One table per row of the workload (each `t(pk blob, ck int, v text, PRIMARY KEY(pk, ck))` with SAI on `v`): W1 20,000 partitions, pk 100 B, v 900 B; W2 5,000 partitions, pk 8 KiB, v 8,191 B; W3 2,000 partitions, pk 60,000 B, v 900 B; W4 2,000 partitions, pk 100 B, v 40,960 B. Per node lifetime: load W1-W4, `nodetool flush`, `nodetool compact`, then 3 minutes of mixed reads (point reads by key and `WHERE v = <stored value>` SAI queries on every table). Volume about 0.3 GB. A write the guardrail rejects is a reading (counted), not an error: W2 fails under T1k, W4 under T1k and T8k.
> **[Amended 2026-10-26, audit R6]** Filed text had 20,000 partitions at every pk length (1.2 GB for 60 KiB keys) and a 10-minute read phase for each knob combination; replaced by the table above (time and disk arithmetic in the results file section 1).

**B3d. Observables and instruments.** (a) A Byteman trace (observation only) of every construction of `Walker$TransitionBytesCollector` and every call of its `add`; (b) liveness counters in the same trace, sampled every 1000th call: constructions of `Walker` (any subclass, e.g. the BTI partition-index reader) and of `TrieTermsDictionaryReader` (SAI on-disk term lookups) and of `ValueIterator`; (c) `jcmd <pid> GC.class_histogram` `byte[]` total after each phase; (d) per-table write outcome counts (accepted, rejected with the guardrail message) from the client; (e) `du` of the data directory. Cannot be observed directly: the collector's `byte[]` among all `byte[]` (so the histogram is context only); the trace is exact for constructions and `add` calls, which makes sampling unnecessary.
> **[Amended 2026-10-26, audit R5]** The filed JFR sampling (`jdk.ObjectAllocationSample`, filtered by frame) is replaced by the exact Byteman trace: JFR samples may miss a short-lived 32-byte array, so zero samples would not show zero calls; `VM.native_memory` is dropped (the collector is a heap array).

**B3e. Procedure.**
1. Copy tree, build, create dirs, start the node with the Byteman agent and `trace` rules (`collector.btm`) loaded.
2. For each lifetime (T1k, T8k, T64k, BIG): create the schemas, load W1-W4, flush, compact, run the reads and SAI queries.
3. After each phase `jcmd GC.class_histogram`; at the end count `collector` lines and the last sampled counter of each liveness rule in the trace.
4. The control (B3h) is the same load in the other lifetimes.
5. Stop the node by PID, copy the logs out, delete the data, confirm no `CassandraDaemon` of this harness is left (`ps`, by working directory).

**B3f. Predictions.** (a) Zero constructions of `Walker$TransitionBytesCollector` and zero `add` calls in the trace in all four lifetimes, because no production path calls `getMinTerm`/`getMaxTerm` or builds a collecting `ValueIterator`. (b) The liveness counters are nonzero in every lifetime (`Walker` constructions and `TrieTermsDictionaryReader` constructions; in the bti lifetimes also the partition-index reader), so the instrument was watching live trie readers. (c) Accepted writes follow the threshold exactly: W1 accepted in all four lifetimes; W2 rejected in T1k and accepted in T8k, T64k, BIG; W4 rejected in T1k, T8k, BIG and accepted in T64k; W3 accepted in all (rows rejected by the guardrail never reach a trie). (d) `du` of the data directory follows the accepted volume. Wrong if any collector line appears in a normal run, or if the accepted counts do not follow the thresholds.
> **[Amended 2026-10-26, audit R5, R7]** Filed (a) was zero JFR samples; (b) and (c) are new (the control moved to the guardrail, see B3h) and the filed claim "heap follows `file_cache_size`" is dropped.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| no collector lines in any lifetime, liveness counters nonzero, accepted counts follow the thresholds (B3f) | claim confirmed |
| collector lines appear, with lengths scaling with the key length | a runtime path uses the collector (claim refuted for "never exercised"); then check whether the size follows a limit |
| collector lines appear and their lengths follow the SAI threshold | refutes: a configured limit does bind |
| no collector lines but a liveness counter is zero in a lifetime, or accepted counts do not follow the thresholds, or a load did not complete | not confirmed (instrument or load inadequate) |
> **[Amended 2026-10-26, audit R5]** Rows rewritten for the Byteman trace (the filed rows named JFR samples).

**B3h. Controls.** Positive control: the SAI term-size guardrail changes between lifetimes (T1k, T8k, T64k) and the accepted and rejected write counts must move with it exactly as B3f (c) says (a cap that binds on the same bytes that become trie paths), and the liveness counters show the trace sees live trie readers. A lifetime with format `big` shows the same workload without the BTI partition index. The filed control `file_cache_size` is dropped: `file_cache_enabled` defaults to false (`conf/cassandra.yaml:742`), so the setting would not change a quantity the workload reads.
> **[Amended 2026-10-26, audit R7]** See B3f.

**B4. Risks and cleanup.** Disk: everything under `/tmp/c509-*` on local disk; keep <=5 GB; never use the shared source tree or shared storage. Processes: the node and `jcmd`/JFR; kill and verify with `pgrep`. Delete the copies and JFR files. Unit tier writes only small tries in `/tmp`.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/io/tries/Walker.java (lines 335-470)
- src/java/org/apache/cassandra/io/tries/ValueIterator.java (30-300)
- src/java/org/apache/cassandra/io/sstable/format/bti/PartitionIndex.java (385-440)
- src/java/org/apache/cassandra/index/sai/disk/v1/segment/LiteralIndexSegmentTermsReader.java (145-170)
- src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java (205-220)
- src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java (grep)
- src/java/org/apache/cassandra/db/guardrails/Guardrails.java (520-552)
- src/java/org/apache/cassandra/config/Config.java (941-944); conf/cassandra.yaml (2246-2251)
- test/unit/org/apache/cassandra/index/sai/disk/v1/trie/TrieTermsIterator.java (30-60)
- grep results across src/java and test/unit for the callers named above

## D. Stage-4 feedback

Stage 4 ran 2026-10-26 (results: `stage4-runtime-verification/results/transition-bytes-collector-add-buffer-length--autonomous.md`). Unit: **Confirmed — does not cap** (B2g row 1): the collector's capacity is 32 up to 32 bytes and then follows Lucene 9.7.0 `ArrayUtil.grow` (L=33 -> 40, 1024 -> 1088, 8192 -> 8296, 65535 -> 69,368; 131072 -> 140,656; 1,048,576 -> 1,172,112), one value per L under every guardrail value (1KiB/8KiB/64KiB) and JVM size (260/519/1056 MB). Cluster: **Confirmed — does not cap** (B3g row 1): in four node lifetimes (bti with the SAI term-size threshold at 1KiB, 8KiB, 64KiB; big at 8KiB) the Byteman trace shows zero constructions and zero `add` calls of the collector, while 71,000 to 222,000 trie-reader constructions were counted and the guardrail rejected exactly the writes above its threshold. Outcome class: true negative. Corrections to the filed text, made as dated amendments before run 1 (listed below): the allocation and reallocation arithmetic (59 grows for 65535, arrays summing to 622,768 B, not "20-30" and "below 300 KB"), JFR sampling replaced by an exact trace, `file_cache_size` dropped as a control (`file_cache_enabled` is false by default), `storage_compatibility_mode: NONE` (bti is refused under `CASSANDRA_4`) and an ordinary role under `PasswordAuthenticator` (superusers skip guardrails; with `AllowAllAuthenticator` the term-size guardrail never fired). Not established: that no repair, streaming or index-summary path builds the collector (static grep says none does; the trace covers write, flush, compaction, point read, SAI query and the BTI partition index).

### Stage-4 amendments (audit, 2026-10-26, before run 1)

R1 cites checked against the pinned source (`Walker.java:437-462`, `ValueIterator.java:74,107,226,250`, `PartitionIndex.java:395-407`, `Config.java:941-944`, `StorageAttachedIndex.java:147,207-210,773-830`): correct; the only change is `validateTermSize` at 807-830. R2 build and harness mechanics (B2a). R3 Lucene growth arithmetic (B2c, B2f, B2g). R4 unit-tier control uses the guardrail object (B2h). R5 JFR replaced by an exact Byteman trace (B3d-B3g). R6 cluster workload sized to the time and disk available (B3c). R7 `file_cache_size` control dropped (B3h). R8 none of these depend on any reading of the experiment. D1 (shakedown, same day): `storage_compatibility_mode: NONE` for the cluster tier (B3a). D2 (shakedown): ordinary role under PasswordAuthenticator for the cluster tier, otherwise the guardrail is skipped (B3a).
