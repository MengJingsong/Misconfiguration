# initial-buffer-capacity-ensurecapacity-datalengthinbytes — verification solution  <!-- file: cases/initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/bytecomparable/ByteSourceInverse.java:424` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (Agent SDK), 2026-10-26 |
| Estimate | `negative`. Line 424 is the "buffer full" test of a private grow-by-doubling helper. It is not a configurable cap, and the byte[] it grows is a transient copy whose size is set by the input, which is bounded elsewhere. |
| Ground | The check is a growth trigger, not a limit: when it fires the buffer doubles and nothing is refused. The only constant involved, `INITIAL_BUFFER_CAPACITY = 32` (`ByteSourceInverse.java:34`), is a starting size. The only real ceiling is the implicit int overflow at 1<<30 bytes (comment `:425-428`), which is the JVM array limit, not a node resource cap. Bytes decoded here come from partition keys (limited to 65535 by `ClusteringPrefix.java:278-287` and `cql3/Validation.java:54`), SAI terms and other small fields, so the allocation is a short-lived heap object of at most about 2x the input. The doubling does not bound memory or disk. |

## A. Constraint trace

**A1. The constraint.** There is no named configuration entry. Three things are in play:
- `ensureCapacity(byte[] buf, int dataLengthInBytes)` (`ByteSourceInverse.java:422-432`). The tested condition `dataLengthInBytes == buf.length` (`:424`) means the buffer is full; it returns `Arrays.copyOf(buf, dataLengthInBytes * 2)` (`:429`), otherwise the same buffer (`:431`). Kind: hard-coded runtime growth rule.
- `INITIAL_BUFFER_CAPACITY = 32` (`:34`). Kind: constant, bytes. It is the default initial size used by `readBytes(ByteSource)` (`:400-403`). Callers can pass another size to `readBytes(ByteSource,int)` (`:366-386`): `IndexTermType.java:912` uses `DECIMAL_APPROXIMATION_BYTES = 24` (`IndexTermType.java:91`).
- The int overflow of `dataLengthInBytes * 2` at 1<<30 (`:425-428`), which is deliberately not guarded.
Nothing is settable by yaml, `-D` or JMX. Changing any of it needs a code change and a restart.

**A2. What it caps.** Nothing explicitly. The quantity compared is the number of bytes already read (`readBytes` local, `:373-377`) against the current heap array length. The resource touched is heap (a transient byte[]), and the line caps neither heap nor disk.

**A3. Mechanism.**
1. `readBytes` (`:366-386`) allocates `new byte[initialBufferCapacity]` and loops `byteSource.next()` until `END_OF_STREAM`.
2. For each byte it calls `ensureCapacity(buf, readBytes)` (`:377`), which at `:424` compares the count to the length. If equal, it allocates a new array of double size and the old one becomes garbage.
3. After the loop, if `readBytes != buf.length` it copies down to exact size (`:381-384`). So peak transient heap is old buffer + new buffer (about 3x the data size at the moment of the last doubling), then the exact-size result.
4. Outcomes: not full gives no action; full gives a doubling, never an error or rejection. At `dataLengthInBytes >= 1<<30` the multiplication overflows to a negative number and `Arrays.copyOf` throws `NegativeArraySizeException`. It is unreachable in practice because inputs are tiny (see A4). `copyBytes` (`:405-416`) is a separate fixed-buffer method and throws `ArrayIndexOutOfBoundsException` on overrun; it is not a cap either.
5. Callers: `getUnescapedBytes` (`:295-298`), `getString` (`:440-448`), `ByteOrderedPartitioner.java:236`, `OrderPreservingPartitioner.java:136`, `DecoratedKey.java:227,244`, `AbstractType.java:723`, `DynamicCompositeType.java:354-363`, `PrimaryKey.java:153`, `SegmentMetadata.java:168-169`, `IndexTermType.java:912`.
Bypass/overshoot: the buffer may overshoot the data by up to 2x (and the trailing copy is skipped only when the size matches exactly). That overshoot is capped by data size, not by any setting.

**A4. Other consumers.** The same heap is used by memtables, key/row/chunk caches, bloom filters and index summaries, compaction and the SAI segment builders. The decoded arrays are short-lived and negligible next to those. The effective bounds on input size are upstream: partition key and clustering size at most 65535 bytes (`ClusteringPrefix.java:278-287`), SAI term-size guardrails (`conf/cassandra.yaml:2246-2254`, `sai_string_term_size_fail_threshold` 8KiB default), `max_value_size` (`conf/cassandra.yaml:1864`).

**A5. Evidence beyond the source.** The in-code comment at `ByteSourceInverse.java:425-428` and the method javadoc at `:354-365`. `conf/cassandra.yaml` lines cited above. No external links used.

## B. Verification solution

**B1. Claim under test.** The "buffer full" doubling at `ByteSourceInverse.java:424` does not cap memory or disk. The decode buffer is a transient copy that scales with the input length (peak about 2x to 3x input for the doubling path, 1x plus the 32-byte start for exact fits), independent of any configuration entry, and a node's heap and disk use is governed by other limits (key size, SAI term guardrails, memtable and cache settings). The decoding is never refused by this check.

### B2. Unit tier

**B2a. Environment and build.** Copy the tree to local disk (for example `rsync -a ~/cassandra-5.0.9/ /tmp/cass-ut/`; never build in the shared tree). JDK 11, Ant. `cd /tmp/cass-ut && ant jar` (or `ant build-test`). Put a throwaway JUnit test or `main` class in the copy at `test/unit/org/apache/cassandra/utils/bytecomparable/EnsureCapacityProbeTest.java` (copy only, not the original tree). Run with `ant testsome -Dtest.name=EnsureCapacityProbeTest` and `-Dtest.jvm.args="-Xmx512m -XX:+UseSerialGC"`. **[Amended 2026-10-26 (stage-4 audit, A1): `ant testsome` forks a 1 GiB JVM whose `maxmemory` overrides `-Xmx`, so the `-Xmx` knob (B2b 3) cannot be set that way. The probe is a plain `main` class (`EnsureCapacityProbe`) compiled against `build/classes/main` and `build/lib/jars/*` and run with `java -Xmx<m> -XX:+UseSerialGC`; the `testsome` form is dropped.]** The probe calls the public `ByteSourceInverse.readBytes(ByteSource,int)` and `getUnescapedBytes` (the helper is private; reflection `setAccessible` is acceptable only for a direct call to `ensureCapacity`).

**B2b. Knobs.** (1) Input length N in bytes: 0, 31, 32, 33, 64, 1000, 65535, 1<<20, 64<<20. 32 is the starting size, so 31/32/33 straddle the first doubling; 65535 is the key limit; 64 MiB shows linear growth. (2) `initialBufferCapacity` argument: 1, 32, 24, N, 2N. Set in the probe call. (3) Heap `-Xmx` 128m and 1g, to show the buffer does not depend on a heap limit.

**B2c. Workload.** A `ByteSource` that yields N bytes of nonzero data then `END_OF_STREAM`. For `getUnescapedBytes`, build the source with `ByteSource.of(byte[], version)` over random bytes including 0x00 so the escape path (`:295`, `unescape`) is exercised. Doublings expected for N, start 32: `ceil(log2(N/32))`, e.g. N=65535 gives 11 doublings, final capacity 65536, exact-size copy follows. **[Amended 2026-10-26: the 1<<30 overflow is run, not skipped. Two extra inputs N = 1<<30 and N = (1<<30)+1 from a counting `ByteSource` (no source array), at `-Xmx4g` (the node has 251 GiB); expected from the code at `:424-429`: N = 1<<30 returns a 1<<30 array (the buffer fills exactly, no further `ensureCapacity` call, no copy); N = (1<<30)+1 throws `NegativeArraySizeException` from `Arrays.copyOf(buf, 1<<31)`.]** Arithmetic for 1<<30: needs 1 GiB source and `-Xmx` over 3 GiB; do not run it, only call `ensureCapacity(new byte[1<<30], 1<<30)` with a stubbed array is impossible without allocating 1 GiB, so test the overflow with `-Xmx4g` only if local memory allows, expecting `NegativeArraySizeException` from `Arrays.copyOf(.., 1<<31)`.

**B2d. Observables and instruments.** (a) Number of distinct array lengths seen: wrap the source and count `next()` calls (does not count allocations); better, run with JFR (`-XX:+FlightRecorder` / `jcmd JFR.start`) and count `jdk.ObjectAllocationInNewTLAB` or `ObjectAllocationOutsideTLAB` events for `byte[]` from `ensureCapacity`. (b) Allocated bytes per call: `com.sun.management.ThreadMXBean#getThreadAllocatedBytes` before and after, on the calling thread. (c) Returned array length vs N. (d) Exceptions. Not directly observable: the unreachable 1<<30 path without a multi-GiB heap, and GC-collected garbage after return (use `System.gc()` and `Runtime.totalMemory()-freeMemory()` before/after to show nothing is retained).

**B2e. Procedure.**
1. Build as in B2a.
2. For each N and initial capacity: warm up with 5 calls, then `long a0 = tmx.getThreadAllocatedBytes(tid)`; call `readBytes`; `a1`. Record `a1 - a0`, result length, exception.
3. Repeat with `-Xmx128m` and `-Xmx1g`.
4. Call `System.gc()` three times and record retained heap to show the result is the only survivor.
5. Positive control (below) in the same JVM.
6. Delete `/tmp/cass-ut` when done.

**B2f. Predictions.** Result length equals N exactly for every N. Allocation per call: N <= 32 with initial 32: about 32 + 16 header, plus a second exact-size copy only if N != 32 (for N=0 a copy of length 0). For N > 32: sum of doublings, about 2 x roundup_pow2(N) + exact-size copy of N, and linear in N. **[Amended 2026-10-26 (audit, B1: the stated 2x to 4x band is wrong for N just above a power of two; it is arithmetic, not a reading): exact expectation, bytes allocated per call = sum over every array created of (16 + length), i.e. the initial array, each doubling, and the final exact copy when N differs from the final capacity; the ratio to N is 2.0 when N is a power of two (1<<20, 64<<20), about 3.0 for N = 1000 and 65535, and up to about 5 for N just above a power of two (N = 33, 65). A reading is judged against the exact sum (tolerance 1 percent or 256 B), and against 'linear in N, slope between 2 and 5, constant across heap sizes'.]** Initial capacity N gives about N (no doubling, no copy); initial capacity 1 gives the most garbage but the same retained result. Allocation is the same at `-Xmx128m` and `-Xmx1g`. No exception for any N <= 64 MiB. Peak transient heap is below 4N + small.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Allocation per call linear in N (the exact sum above, slope 2 to 5), result length N, no exception, same under both `-Xmx` | Claim confirmed: the line is a growth rule, the buffer scales with input and no setting caps it. |
| Allocation per call flat or capped as N grows (for example never above some fixed size) and the result is truncated or refused | Claim refuted: something caps decode size. |
| Allocation depends on `-Xmx` | Claim refuted: a heap-derived limit is involved. |
| Exception for some N well below 1<<30 | Hidden limit; claim refuted for that range. |
| **[Added 2026-10-26, audit B3]** `NegativeArraySizeException` only at N = (1<<30)+1, and N = 1<<30 returns N bytes | Claim confirmed for that range: the only bound is the JVM array limit through the int overflow at `:429`, not a configured cap. |
| Initial capacity N removes doubling garbage but result identical | Initial capacity only changes transient garbage, supports "starting size, not a limit". |
| Positive control does not move (see B2h) | Not confirmed; harness suspect. |
| Largest N not reached (OOM from the test heap) | Not confirmed for that N; lower N or raise `-Xmx`. |

**B2h. Controls.** Positive control: the same loop through `ByteSourceInverse.copyBytes(source, new byte[M])` (`:405-416`) with M < N, which does enforce a hard cap via `ArrayIndexOutOfBoundsException` at `:413`. It must throw when N > M and succeed when N <= M, showing the harness can detect a binding bound. **[Amended 2026-10-26 (audit, C3): the vague 'ByteBufferUtil direct copy' baseline is defined as `Arrays.copyOf(src, N)` of an N-byte array, which allocates exactly 16 + N bytes; it shows the instrument's zero-doubling reading.]** Check the JIT is warm and use identical N order between runs.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy (`rsync -a ~/cassandra-5.0.9/ /tmp/cass-node/ && cd /tmp/cass-node && ant jar`). `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` all under `/tmp/cass-node-data` on local disk of known free size (at least 5 GiB, check `df`). `-Xms1g -Xmx1g`. Enable the code path: SAI is enabled by default in 5.0; `ByteOrderedPartitioner` (`partitioner: org.apache.cassandra.dht.ByteOrderedPartitioner` in a fresh data dir) exercises `ByteOrderedPartitioner.java:236`. Default Murmur3 still exercises `DecoratedKey.java:227` and `SegmentMetadata.java:168-169` during SAI segment writes. No change to the 32-byte constant (needs a rebuild; do it only as an optional variant, see B3b).

**B3b. Knobs.** (1) Partition key size K: 16 B, 1 KiB, 32 KiB, 65535 B (the key limit, the largest input to the decoder). (2) `sai_string_term_size_fail_threshold` (default 8KiB): 1KiB and 8KiB, to show a real cap that binds on a related size. **[Amended 2026-10-26 (audit, A4/D3): guardrails are skipped for a superuser and when the authenticator is `AllowAllAuthenticator` (`ClientState.isSuper()` is true when `requireAuthentication()` is false, `Guardrail.java:95` needs `isOrdinaryUser()`), so with the default yaml this control cannot fire. The control runs with `authenticator: PasswordAuthenticator`, a superuser (`cassandra`) creating the table and an ordinary LOGIN role `ordinary` with MODIFY/SELECT that does the inserts; the K-sweep runs use the same authenticator so the workload is identical.]** (3) Optional rebuilt variant with `INITIAL_BUFFER_CAPACITY` set to 1 and to 65536 in the copy only. (4) `-Xmx`: 512m and 1g.

**B3c. Workload.** Table `ks.t (k blob PRIMARY KEY, v text)` with SAI index on `v`; insert 20000 rows per K (K=65535 gives about 1.3 GB of key data, so use 2000 rows for the two largest K, about 130 MB), 1 KiB `v`. **[Amended 2026-10-26 (audit, D2): run matrix, one node lifetime each, fresh data directory on tmpfs: K = 16 B and 1 KiB with 20000 rows; K = 32 KiB and 65535 B with 2000 rows; each at `-Xmx1g`; K = 16 B and 65535 B again at `-Xmx512m`; K = 16 B and 65535 B again with no SAI index (B3h); one control lifetime for the 1KiB threshold. Each key row is repeated once only if the first two readings disagree. 'Each K twice' of B3h is dropped for cost; the repeat of 16 B and 65535 B at two heap sizes plays that role.]** Flush (`nodetool flush`) so SAI segment metadata is written (calls `readBytes` on min/max key per segment, `SegmentMetadata.java:168-169`), then run compaction (`nodetool compact`) and `SELECT ... WHERE v = ...` queries. Duration about 10 minutes per K. Reachability: each decode handles one key (at most 65535 B), so the heap effect per call is below 256 KiB, far under the heap.

**B3d. Observables and instruments.** Heap: `jcmd <pid> GC.heap_info` and `jstat -gcutil <pid> 1000`; allocation by site: JFR (`jcmd <pid> JFR.start settings=profile`, then `jfr print --events jdk.ObjectAllocationSample`) filtered on the stack frame `ByteSourceInverse.ensureCapacity`. **[Amended 2026-10-26 (audit, C3/D1): JFR samples are statistical and a per-call size cannot be read from them, so an exact instrument is added: a Byteman observation rule on `ByteSourceInverse.readBytes(ByteSource,int)` (entry and exit) that logs, per call, the calling thread's allocated bytes delta (`com.sun.management.ThreadMXBean`), the result length and the immediate caller; rules on Cassandra classes need no `boot:`. The retained heap is read as the `GC.class_histogram` total (full GC) before the load and after the last query, after `nodetool invalidatekeycache` so the key cache does not mix in; JFR stays as the case writes it.]** Disk: `du -sb /tmp/cass-node-data`. JMX `java.lang:type=Memory` for sampling. Not observable directly: per-call transient size (use the unit tier), because the arrays die in the young generation.

**B3e. Procedure.**
1. Build, set the directories, start the node (`bin/cassandra -f` in the background, record the pid).
2. Create schema; start `jcmd JFR.start`.
3. For each K insert, flush, compact, run 1000 indexed queries; sample `jstat`/`GC.heap_info` every second and `du` before/after.
4. Dump JFR; extract allocation weight attributed to `ensureCapacity`.
5. Repeat with `-Xmx512m`, and with the SAI term threshold at 1KiB (inserting 4 KiB `v` should fail with the guardrail, as the positive control).
6. `nodetool drain`, stop the node (`kill <pid>`), `rm -rf /tmp/cass-node-data`, `pgrep -f CassandraDaemon` must be empty.

**B3f. Predictions.** The `ensureCapacity` share of allocation samples is small (below about 1 percent of total allocation) and its per-call size scales with K, at most about 4x65535 B = 256 KiB. Old-generation occupancy, `du` of data dir and steady-state heap after GC do not change with K attributable to the decode buffer (disk grows with K because the keys are stored, so compare per-byte disk against data, not against the buffer). With `-Xmx512m` the same behaviour and no failures. Rebuilt variant with initial capacity 1 changes only allocation rate, not retained heap or disk. The SAI 1KiB threshold rejects 4 KiB `v` writes (control).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `ensureCapacity` allocation proportional to K, tiny share of allocation, retained heap and disk unchanged by it | Claim confirmed: usage does not follow the doubling check. |
| Retained heap or old-gen growth tracks K beyond the data size, traced to buffers from this method | Claim refuted: these buffers are retained. |
| A write with a legal key size fails at the decode with an exception from `ensureCapacity` | Claim refuted; the check acts as a limit. |
| SAI 1KiB threshold rejects 4 KiB values while decode volume is unaffected | Positive control works: a real cap binds and is visible; supports the negative claim. |
| Positive control does not reject, or `ensureCapacity` never appears in JFR (path not reached) | Not confirmed; check the index was built and the flush wrote segments. |
| Rebuilt variant changes disk or retained heap | Claim refuted. |

**B3h. Controls.** Baseline run with K=16 B. Same run with SAI index absent (shows which allocations disappear, isolating `SegmentMetadata` calls). Repeat each K twice; same data directory wiped between runs. Keep other consumers constant (memtable and caches at defaults, no repair or streaming). Compare disk growth to raw input bytes to separate the stored data from the decode copy.

**B4. Risks and cleanup.** Unit tier: only `/tmp/cass-ut` and JVM heap; avoid the 1<<30 case unless 4 GiB is free; delete the copy and kill the JVM. Cluster tier: all data on local `/tmp/cass-node-data` (at least 5 GiB free, check `df -h /tmp` first); never point directories at shared storage or the shared source tree; stop with `nodetool drain` then `kill`, confirm `pgrep -f CassandraDaemon` and `jcmd -l` are empty, remove `/tmp/cass-node*`. No change outside the nodes.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/utils/bytecomparable/ByteSourceInverse.java (lines 28-36, 150-175, 285-330, 340-470)
- grep results over src/java (callers, `MAX_UNSIGNED_SHORT`, `longer than maximum of`, SAI term thresholds, `DECIMAL_APPROXIMATION_BYTES`), with excerpts of `index/sai/disk/v1/segment/SegmentMetadata.java:160-172`
- conf/cassandra.yaml (grep hits only: `max_value_size`, `sai_*_term_size_*`, `commitlog_segment_size`)

## D. Stage-4 feedback

**Stage-4 result (2026-10-26, run 1 + self-check; [results](../../stage4-runtime-verification/results/initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous.md)): unit Confirmed — does not cap; cluster Confirmed — does not cap; outcome class true negative.** Unit: allocation per call equals the exact doubling sum (2.00 x N at powers of two, 3.00 x N at 65535, up to 5.6 x N at N = 33 and 65 where headers dominate), result length N at every N to 64 MiB, identical at `-Xmx128m` and `-Xmx1g`; `NegativeArraySizeException` only at N = (1<<30)+1 (N = 1<<30 returns). Cluster (nine lifetimes, K = 16 B to 65535 B): decode length follows K (K + 3 to 275), `ensureCapacity` allocation per decode 0 / 2 KB / 66 KB / 131 KB (up to 262 KB for the 65810-byte SAI min/max key), nothing refused, retained heap does not rise with K (+7 to +29 MB without trend), the same at `-Xmx512m`. Deviations (prediction text left as filed): B3f's JFR share "below about 1 percent" is exceeded at K >= 32 KiB (1.8, 3.5, 4.7 percent of the JVM's allocation weight); B2f's peak transient heap was not measured; the optional rebuilt variant was not run. Stage-3 notes for the next case of this kind: JFR on JDK 11 has no `jdk.ObjectAllocationSample`; a Byteman rule on a per-byte method (`ensureCapacity`) perturbs the allocation it measures; the SAI guardrail control needs an authenticated non-superuser role.

*(Superseded text:)* `none yet`.

**Amendments by the stage-4 audit, 2026-10-26** (all independent of any reading; each is also marked inline): (1) B2a: the probe is a `main` class run with `java -Xmx`, because `ant testsome` overrides `-Xmx`; (2) B2c: the 1<<30 overflow is run (N = 1<<30 and (1<<30)+1 at `-Xmx4g`), with a matching B2g row; (3) B2f: the allocation slope band 2x to 4x corrected to the exact sum (2 to about 5), arithmetic of `:424-431`; (4) B2h: the baseline is `Arrays.copyOf`; (5) B3b: the SAI guardrail control needs `PasswordAuthenticator` and an ordinary role, since guardrails do not apply to a superuser or without authentication; (6) B3c: the run matrix is fixed; (7) B3d: an exact Byteman per-call instrument is added beside JFR. The B3 optional rebuilt variant (B3b 3) is not run; the unit tier's `initialBufferCapacity` knob answers the same question. Prediction and conclusions rows are otherwise unchanged.
