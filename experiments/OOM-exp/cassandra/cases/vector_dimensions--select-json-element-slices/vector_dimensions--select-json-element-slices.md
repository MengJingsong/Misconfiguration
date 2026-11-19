# U8 — vector_dimensions (off): SELECT JSON splits a whole vector cell into one ByteBuffer slice per element  <!-- file: cassandra/cases/vector_dimensions--select-json-element-slices/vector_dimensions--select-json-element-slices.md -->

| Field | Value |
|---|---|
| Case ID | `U8` (U = unprotected accumulation; README "ID prefixes") |
| From | `OC-407` of the phase 1 OOM candidate list (cluster of one row: OC-407, primary OC-407) |
| Phase-1 case file | [`no_constraint-isallzero-vectorelement--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/no_constraint-isallzero-vectorelement--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built copy `ms0640:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 session, wave 4, 2026-11-18 13:40–14:20 EST; nothing run (node checked read-only) |
| Stage 2 (verify) | phase-2 OOM agent, stage 2, fresh session, wave 4: runs 2026-11-18 13:54–15:39 EST on `ms0640` (aarch64), §3–§4 written 15:42 EST |
| Verdict | **true positive** — `verified-OOM · deployment` (unprotected), Java heap OOM at heap 2 GiB, N = 2, 3/3 |

## Summary

- **Conclusion:** **true positive.** At shipped defaults, two concurrent `SELECT JSON` reads of one
  `vector<boolean, 16000000>` cell (16 MB serialized) killed a 2 GiB-heap Cassandra 5.0.9 node with
  `java.lang.OutOfMemoryError: Java heap space` in **3/3** runs, within 12 s, thrown in `VectorType.toJSONString`.
  The same reads without JSON (0/3), one JSON read at a time (0/3) and a one-method fix that does not build the
  per-element list (0/3, all 112 MB responses served) did not OOM. The holder also killed 4 GiB (N = 6, 3/3) and
  16 GiB (N = 21, 3/3, after minutes of GC thrash) heaps. `verified-OOM · deployment`, unprotected.
- **Root cause:** `VectorType.toJSONString` `split()`s the whole cell into an `ArrayList` of one 48-byte
  `HeapByteBuffer` per element (measured: 16,000,007 extra buffers + a 64 MB array = **832 MB per request** for a
  16 MB cell, 52×) and keeps it while it builds a 112 MB JSON string. Nothing counts these bytes: the only checks
  see 16 MB serialized (mutation and frame size), the dimension guardrail ships off (−1), read-size thresholds are
  off, and only the 128 native-transport threads bound how many renders run at once.
- **Hypothesis (stage 1, kept):** a vector cell is bounded only in serialized bytes; `SELECT JSON` expands it ≈ 52×
  on the heap per request, so two concurrent reads of one row should exhaust a 2 GiB heap.

## 1. Candidate

**Row of the phase 1 OOM candidate list** (`phase1-oom-candidates.md:416`), the only row of the cluster:

> | OC-407 | 2026-11-18 | `no_constraint-isallzero-vectorelement--autonomous` | guided | Holder: the per-element List that VectorType builds when it splits or deserializes a vector cell. [details](runs/wave2.md#oc-407) | CP-1, CP-12, CP-8 | picked: U8 |

**Full text** (`runs/wave2.md`, `## OC-407`):

> Holder: the per-element List that VectorType builds when it splits or deserializes a vector cell. split()/deserialize() pre-size `new ArrayList<>(dimension)` and, for variable-length element types, create one ByteBuffer slice (about 48 B) plus a reference per element. An element can be as small as 1 serialized byte (a vint length of 0), so a split holds about 50x the cell's serialized bytes. split() is called for the whole cell in toJSONString (line 282) and asComparableBytes (line 210). Why nothing stops it: the dimension is any positive int (VectorType.java:89), and the vector_dimensions guardrail ships off (vector_dimensions_warn/fail_threshold = -1). The write-side size limits count serialized bytes only. Size: a vector<text, ~16M> cell at the default 16 MiB max mutation size splits to about 16M slices, about 0.8-0.9 GB per materialization, times concurrent reads (32). The similarity-function path itself (composeAsFloat) checks the length before allocating and holds only 4 x dimension bytes per argument. Confidence: plausible; the reachable callers that split a whole stored cell were not traced end to end.
>
> **Where:** src/java/org/apache/cassandra/db/marshal/VectorType.java:89, 210, 282, 587-599, 633-648; src/java/org/apache/cassandra/config/Config.java:924-925

**Triage** (`runs/triage-2026-11-18.md`, rank 13 of the top 20): "yes | single ARM node | VectorType.split builds
one roughly 48 B ByteBuffer slice per element, and the dimension is uncapped (the vector_dimensions guardrail is -1).
A vector<text, ~16M> cell inside the 16 MiB mutation limit expands to about 0.8-0.9 GB per materialization (for
example SELECT JSON or asComparableBytes), so 2-3 concurrent reads pass a 2 GiB heap. Confidence is only plausible:
that a whole stored cell is split on a reachable read path still has to be confirmed first. | No existing case."
No other row is grouped with it (triage notes §1–§4 do not list OC-407).

**Stage 1 trace (the triage's open question).** A whole stored cell *is* split on a default read path:
`SELECT JSON` → `Selection` JSON row builder (`cql3/selection/Selection.java:476-479`) → `rowToJson`
(`Selection.java:305-345`, `:339` `spec.type.toJSONString(buffer, protocolVersion)`) → `VectorType.toJSONString`
(`VectorType.java:272-275` → `:278-291`, `:282` `List<V> split = split(value, accessor)`) → for a fixed-length
element type `FixedLengthSerializer.split` (`VectorType.java:445-460`: `new ArrayList<>(dimension)`, one
`accessor.slice` = `ByteBuffer.duplicate()` per element, `ByteBufferAccessor.java:106-112`). The function
`toJson(v)` reaches the same method (`cql3/functions/ToJsonFct.java:66`). It runs on the Native-Transport-Requests
thread of the coordinator, after the read returned, while building the result (`ResultSetBuilder.java:173-175`).

**What this design covers and does not cover (the cluster has one row).**

| Part of OC-407 | Covered? |
|---|---|
| Holder = the per-element `List` built by `split()` of a whole stored cell; unbounded dimension; guardrail `vector_dimensions` off | **yes** |
| Reachable caller `toJSONString` (line 282) via `SELECT JSON` (and `toJson()`, same method) | **yes** (`SELECT JSON` is the test path) |
| `FixedLengthSerializer.split` (`:445-460`) with 1-byte `boolean` elements (1 serialized byte per element, the same ≈ 50× ratio) | **yes**: the element type used |
| `VariableLengthSerializer.split` (`:587-601`) with `vector<text, ~16M>` and empty text elements | **no**: an empty `text` element is a null element (`TypeSerializer.isNull` = empty, `TypeSerializer.java:71-74`), which the literal path rejects (`Vectors.java:218`); using it would rest on input the system documents as invalid. Same holder code shape, so the result transfers in kind, not tested |
| `asComparableBytes` (`:210`) | **no**: reached only by byte-comparable consumers (trie memtable, BTI format, SAI), none of which is on the default `SkipListMemtable` + `big` path for a regular column; SAI vector indexes accept only `float` vectors |
| `deserialize()` (`:633-648`) and `CQL3Type.Vector.toCQLLiteral` (`CQL3Type.java:551-555`, also splits) | **no**: callers are UDFs (off by default) and tool/debug paths |
| "times concurrent reads (32)" | **reframed**: JSON rendering runs on the request thread after the read, so the multiplicity bound is `native_transport_max_threads` (128), not `concurrent_reads` (32) |

**Phase-1 case.** [`no_constraint-isallzero-vectorelement--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/no_constraint-isallzero-vectorelement--autonomous.md):
estimate `negative`, no constraint (`isAllZero`, `VectorFcts.java:96-103`, is an argument check of
`similarity_cosine`). The OOM clue is not about that check; it came from reading the vector code around it. Stage 4:
none for this case file.

**JIRA prior art** (read only; nothing posted). Local survey `jira-oom-survey.csv` (604 issues): no vector issue;
nearest is CASSANDRA-12769 (ListSerializer pre-sizes an `ArrayList` from a bogus element count; malformed input,
fixed), a different holder. JIRA REST search, 2026-11-18 (`issues.apache.org/jira/rest/api/2/search`):
`text~"VectorType" AND text~"memory"` (3: CASSANDRA-18715, 18504, 18166, feature work);
`text~"vector" AND text~"toJSONString"` (1: CASSANDRA-18504, the type itself);
`summary~"vector" AND (OOM|OutOfMemory|heap)` (3: SAI recall/sharding, unrelated);
`text~"vector_dimensions"` (15; CASSANDRA-18730 "Add guardrail for vector dimensions", fixed 5.0-alpha1:
"analogous to the current guardrails limiting the number of items per collection", shipped at −1);
`text~"SELECT JSON"`/`toJson` with OOM (2, unrelated); `vector … split … ByteBuffer` (14, none about memory).
Trunk `VectorType.toJSONString` (GitHub `apache/cassandra` trunk, read 2026-11-18) still materializes the list
(`unpack(value, accessor)`, line 301). **Verdict: `new`** (the guardrail exists but ships off; no report of the
per-element slice amplification). Related filed case: U3 (`items_per_collection--whole-collection-read-materialization`,
true positive) materializes whole collections on read; U8 is a different holder (one 16 MB cell, no collection).

## 2. Design solution (stage 1; frozen)

**Mechanism.** Direction: **unprotected** (protocol "Unprotected results"): unprotected configuration (the
`vector_dimensions` guardrail ships at −1, `Config.java:924-925`, and with the default `AllowAllAuthenticator`
every client is a superuser that guardrails skip) plus unprotected accumulation (nothing bounds the bytes a read
materializes from one cell). Technique note: [`default-convergence-playbook.md`](../../../default-convergence-playbook.md)
for the multiplicity sweep at default capacities. A vector's dimension is any positive int (`VectorType.java:89`).
The write path checks only serialized bytes: the frame (`native_transport_max_frame_size` 16 MiB,
`Config.java:285`, `Envelope.java:197`) and the mutation (`max_mutation_size` = ½ `commitlog_segment_size` =
16 MiB, `DatabaseDescriptor.java:898-899`); a bound value is validated element by element without retaining
anything (`Constants.java:441-460`, `VectorType.java:514-533`). On `SELECT JSON` the coordinator's request thread
calls `VectorType.toJSONString` (`:278-291`), which builds `split` (`:282`; `FixedLengthSerializer.split`,
`:445-460`) = `ArrayList(dimension)` + one `HeapByteBuffer` duplicate per element (48 B shallow on JDK 11 with
compressed oops, + 4 B reference), keeps it live through the whole append loop (`:283-288`), and appends each
element's JSON (`"false"`, `BooleanType.java:109-112`, a constant: no per-element string kept) to one
`StringBuilder`. For `vector<boolean, D>` the cell is D bytes and the held list is ≈ 52·D bytes; the JSON text is
7·D − 1 bytes (Latin-1), copied again by `sb.toString()`, `rowToJson`'s builder and its `toString()`, and the UTF-8
`byte[]` (`Selection.java:339-343`). With N concurrent `SELECT JSON` of the same row the held heap is
≈ N × (52·D + JSON buffers) + baseline, bounded only by 128 request threads.

**Protection map** (fixed before any run).

| Domain | Holder (allocation → release) | Counter K | Limit at default | At the limit |
|---|---|---|---|---|
| Vector dimension | the column type; sets the element count of every split | dimension (count) | `vector_dimensions_fail_threshold: -1` (off); superusers exempt anyway | nothing → **unprotected configuration** |
| Cell bytes (write) | the stored cell, 1 B per `boolean` element | serialized bytes | `max_mutation_size` 16 MiB; frame 16 MiB; `column_value_size` guardrail null (`Config.java:915-916`) | write rejected above 16 MiB (D = 16,000,000 is under it) |
| **Split list (claimed holder)** | `ArrayList` `Object[D]` + D `HeapByteBuffer` slices, `VectorType.java:445-460`, created at `:282` → unreachable when `toJSONString` returns | none | none | nothing → **unprotected accumulation** |
| JSON text (ledgered, same request) | `StringBuilder` in `toJSONString` (`:280`), its `toString()`, `rowToJson` builder + `toString()` + UTF-8 `byte[]` (`Selection.java:310-343`) → released after the `ResultSet` is encoded | none | none | nothing |
| Read-size thresholds | coordinator result size (`ResultSetBuilder.addSize`, `:176`) | bytes | **off** (`read_thresholds_enabled: false`, `coordinator_read_size_*` null, `Config.java:526-528`) | nothing |
| Concurrency | one split + JSON render per in-flight request | NTR threads | `native_transport_max_threads` 128 (`Config.java:283`) | queue; no byte sum |
| Native in-flight request bytes | the request body (a ≈ 60 B `SELECT`) | request bytes | heap/10, per IP heap/40 | does not cover response-side memory |
| Encoded response (ledgered, not claimed) | Netty direct buffer from `Message.encode` (`CBUtil.allocator`), ≈ 112 MB per response | — | `MaxDirectMemorySize` | direct OOM (not expected: ≤ 2.4 GB at N = 21 vs 15,872 MiB) |
| Baseline | memtable heap pool (H/4; empty after flush), key cache, chunk cache (direct) | own counters | defaults | evict / flush |

**Configuration and budget audit.**
- **Node:** `ms0640` (node1.jason92-326377, Utah m400), **aarch64**, 8 cores, 62 GiB (`MemTotal` 65,791,808 kB),
  `/mydata` 39 G with **18 G free** (checked read-only 2026-11-18 13:43 EST; `/mydata/s2r2` 19 G and
  `/mydata/u1r2` 482 M belong to other cases: do not touch), 8 GiB swap (kept off for the victim), cgroup v2
  (`memory` delegated), Ubuntu 22.04, OpenJDK 11.0.33, `jcmd`, `python3`. No Java process was running.
- **Build:** `/mydata/s4/cassandra-base` (469 M; cassandra-5.0.9, `build/apache-cassandra-5.0.9-SNAPSHOT.jar`;
  `build/lib/jars/cassandra-driver-core-3.12.1-shaded.jar`, `guava-32.0.1-jre.jar`, `metrics-core-4.2.28.jar`),
  copied read-only to `/mydata/s4/u8/tree`. Record the jar's sha256.
- **JVM** (shipped options): G1 (`jvm11-server.options:63-84`: `G1HeapRegionSize=16m`, `G1NewSizePercent=50`,
  `MaxGCPauseMillis=300`, `InitiatingHeapOccupancyPercent=70`), `HeapDumpOnOutOfMemoryError`, `AlwaysPreTouch`
  (`jvm-server.options:120,128`), `-XX:OnOutOfMemoryError="kill -9 %p"` (`cassandra-env.sh:209`).
- **Every capacity constraint at its shipped default (V6):** `vector_type_enabled: true`,
  `vector_dimensions_warn/fail_threshold: -1`, `commitlog_segment_size: 32MiB` → `max_mutation_size` 16 MiB,
  `native_transport_max_frame_size` 16 MiB, `native_transport_max_message_size` derived (16 MiB at ≥ 640 MiB heap),
  `native_transport_max_threads` 128, in-flight limits heap/10 and heap/40, read thresholds off,
  `column_value_size` guardrail null, `memtable_allocation_type: heap_buffers`, `authenticator: AllowAllAuthenticator`,
  timeouts (`read_request_timeout` 5 s, `native_transport_timeout` 12 s) not raised. Only arm I changes anything
  (five patched class files; below).
- **`cassandra.yaml` diff** from the shipped file (environment only): `data_file_directories`, `commitlog_directory`,
  `hints_directory`, `saved_caches_directory`, `cdc_raw_directory` under `/mydata/s4/u8/node/`. Single node,
  `localhost`, client on the same node. Save the diff per run (`yaml.diff`).
- **Budgets (V7;** standing rule: heap/direct ≥ 512 MiB meets V7, 2 GiB ideal, search upward**):**
  - What the node would resolve by itself: `cassandra-env.sh:51-68` with G1 → heap_limit 31,744 MiB;
    ½ RAM = 32,124 MiB > limit → heap **31,744 MiB**, `MaxDirectMemorySize` **15,872 MiB**.
  - **Primary: heap 2 GiB** (`MAX_HEAP_SIZE=2G`), direct **auto** (`MAX_DIRECT_MEMORY_SIZE` unset → 15,872 MiB, as
    U4 recorded with a hand-set heap; read the resolved `-XX:MaxDirectMemorySize` from `ps` and record it).
    Claimed node class: any ≥ 4 GiB node running a 2 GiB heap (≥ 512 MiB rule; no per-case review needed).
  - **Upward search:** heap 4 GiB, 8 GiB, 16 GiB (all below the resolved 31,744 MiB), direct auto.
  - **Container:** a `systemd-run --user --scope` with `MemoryMax = heap + 15,872 MiB + 8 GiB` and
    `MemorySwapMax=0` isolates the victim only; it is **not** a budget and must never fire (`memory.events`
    `oom_kill` 0 in every run; a cgroup kill makes that run invalid, not a result).

**Ceiling arithmetic.** D = 16,000,000 (`vector<boolean, 16000000>`; cell 16,000,000 B, mutation ≈ D + 100 B
< 16,777,216; EXECUTE frame ≈ D + 40 B < 16 MiB). Per `SELECT JSON` request, heap:
split list = 16 B + 4·D (`Object[]`, 64.0 MB) + 48·D (slices, 768.0 MB) = **832 MB** (793 MiB; 0.79–0.87 GB
allowing for layout); JSON `StringBuilder` 112 MB final length, capacity 112–224 MB, transiently up to ≈ 336 MB
while growing; read path (response `DataOutputBuffer`, cell copies) ≤ 50 MB. Peak per request while the list is live
≈ **0.95–1.2 GB**; after `toJSONString` returns, ≤ 4 × 112 MB of JSON copies, not all at once. Baseline at a 2 GiB heap
(idle node, flushed memtable) ≈ 0.15–0.3 GB. Contract capacities: no contract covers the list (K = 0 bytes counted;
the only byte checks see 16 MB per cell, ≈ 52× below U). Reachable sums at 2 GiB: N = 1 → 1.1–1.5 GB (fits,
25–45 % margin); N = 2 → 2.05–2.7 GB > 2.0 GiB (OOM). Needed N at heap H ≈ ceil(1.25·H/GiB) + 1 (6 at 4 GiB, 11 at
8 GiB, 21 at 16 GiB), all ≤ 128 threads.

**Workload and environment.**
- Single node on `ms0640`, client on the same node (8 cores shared). Fresh node dir per run (no cloning), then:
  `CREATE KEYSPACE u8 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
  `CREATE TABLE u8.t (pk int PRIMARY KEY, v vector<boolean, 16000000>)`; one prepared
  `INSERT INTO u8.t (pk, v) VALUES (0, ?)` with a 16,000,000-byte zero `ByteBuffer` (all `false`), CL ONE;
  `nodetool flush u8`; verify `SELECT v … WHERE pk = 0` returns exactly 16,000,000 bytes. Then idle 30 s
  (or `nodetool` GC-free settle) and start the arm's load. If `vector<boolean, …>` is refused, fall back (recorded as
  an amendment before readings) to `vector<float, 4000000>` (fixed 4 B; list ≈ 208 MB per request) and scale N ×4.
- **Client `U8Client.java`** (Java driver 3.12.1 shaded from `tree/build/lib/jars`, compiled like U4's `setup.sh`):
  protocol V4; `QueryOptions.setMetadataEnabled(false)` (driver 3 cannot parse `vector<…>` schema strings; the
  prepared metadata carries the type as CUSTOM and `setBytesUnsafe` binds the raw bytes); client read timeout
  120 s (client side only). Modes: `load D`, and `run <json|plain> N R`: N separate `Cluster` objects (one
  connection each), a `CyclicBarrier(N)` per round, R rounds; `json` = `SELECT JSON v FROM u8.t WHERE pk = 0`,
  `plain` = `SELECT v FROM u8.t WHERE pk = 0`. Per request write a CSV line: UTC ms start/end, thread, round,
  response length (`row.getBytesUnsafe(0).remaining()`; expected 112,000,007 for JSON = `{"v": ` + 7·D − 1 + `}`,
  16,000,000 for plain), error class. Do not decode the JSON to a `String`. Exit when R rounds finish or the node
  is unreachable. Client JVM `-Xmx8g -XX:MaxDirectMemorySize=8g`.
- **Harness:** under this folder's `harness/`, adapted from U4's
  (`../cql-row-limit--wide-row-default-pages/harness/`: `victim-ctl.sh` start/ready/stop/oom pattern with per-run
  `CASSANDRA_CONF`, `systemd-run` scope, `C2Sampler.java`, `gcwin.py`, `hprofhist.py`, `hprofstacks.py`).
  Node root `/mydata/s4/u8/` (`tree/`, `conf-pristine/`, `node/` wiped per run, `runs/<label>/`, `cls/`, `patch/`).
  Launch with `( setsid nohup … < /dev/null > … 2>&1 & )`; poll in bounded background loops; kill by PID.
- **Arms.** All at D = 16,000,000, fresh node per run, R = 5 rounds unless stated.

| Arm | Heap | Load | Runs | Purpose |
|---|---|---|---|---|
| **D1** diagnostic | 8 GiB | `json`, N = 1, R = 3 (one at a time) | 1 lifetime | reachability + **U** of the list, independent of K (histograms below) |
| **T** test | 2 GiB | `json`, N = 2 | 3 | V1: OOM endpoint |
| **C1** matched-path control | 2 GiB | `plain`, N = 2 (same row, same concurrency, no split) | 3 | V2 |
| **I** intervention | 2 GiB | `json`, N = 2, **patched `VectorType`** | 3 | V4 |
| **C2** multiplicity control | 2 GiB | `json`, N = 1 | 3 | V2 (low multiplicity alone) |
| **B** budget search | 4 / 8 / 16 GiB | `json`, N = 6 / 11 / 21, R = 3 | 1 each, then 2 more at the largest failing heap | V7: largest failing budget, n/3 |

  Pre-declared dial rules: if T run 1 survives at N = 2, raise N to 3, then 4 (2 GiB); the first N with an OOM is
  N\*, run T ×3 at N\*, and C1 and I at the same N\*. If C2 (N = 1) OOMs in ≥ 1 of 3, the claimed condition becomes
  N = 1 at 2 GiB (a single request): then run C1 and I at N = 1 as well and report T as the N = 2 arm. If a B step
  survives, run one step between it and the last failing heap (e.g. 12 GiB with N = 16) if time allows.
- **Intervention (arm I).** A diagnostic build of one class, the unmodified build otherwise: copy
  `systems/cassandra/source/src/java/org/apache/cassandra/db/marshal/VectorType.java` to
  `harness/VectorType.java`, replace the body of `toJSONString(V value, ValueAccessor<V> accessor, ProtocolVersion)`
  (`:278-291`) with:

  ```java
          StringBuilder sb = new StringBuilder();
          sb.append('[');
          if (elementType.isValueLengthFixed())
          {
              // U8 intervention: walk the elements one at a time instead of materializing split()
              int length = elementType.valueLengthIfFixed();
              int offset = 0;
              for (int i = 0; i < dimension; i++)
              {
                  if (i > 0)
                      sb.append(", ");
                  V element = accessor.slice(value, offset, length);
                  offset += length;
                  sb.append(elementType.toJSONString(element, accessor, protocolVersion));
              }
          }
          else
          {
              List<V> split = split(value, accessor);
              for (int i = 0; i < dimension; i++)
              {
                  if (i > 0)
                      sb.append(", ");
                  sb.append(elementType.toJSONString(split.get(i), accessor, protocolVersion));
              }
          }
          sb.append(']');
          return sb.toString();
  ```

  save `diff -u` as `harness/vectortype-intervention.diff`, compile with
  `javac --release 11 -cp "tree/build/apache-cassandra-5.0.9-SNAPSHOT.jar:tree/lib/*" -d patch harness/VectorType.java`,
  and for arm I copy `patch/org/apache/cassandra/db/marshal/VectorType*.class` (5 files) into the run's
  `conf/org/apache/cassandra/db/marshal/`: `CASSANDRA_CONF` is the first classpath entry (`bin/cassandra.in.sh:27`),
  so the patched class shadows the jar's. Every arm runs with `-Xlog:class+load=info:file=<run>/classload.log`;
  check the `VectorType` line's `source:` (the run's `conf/` in I, the jar elsewhere). The patch removes only the
  list; the JSON `StringBuilder` and its copies stay. Also compare I's response lengths with D1's (both 112,000,007)
  and record I's completed requests per round, so a "survival" that stops useful work is not mistaken for a fix.
- **Realistic fault:** none needed.

**Instruments** (U independent of K; K = the only byte counts that exist: 16,000,000 B cell / ≈ 60 B request).
- **D1 (U of the list):** before the first request one `jcmd <pid> GC.class_histogram` (baseline); then, for each
  of the 3 sequential requests, `jcmd GC.class_histogram` every 2 s while it is in flight. Per sample record
  `java.nio.HeapByteBuffer` instances and bytes and `[Ljava.lang.Object;` bytes (and the largest `Object[]` /
  `[B` sizes if `-all` is unavailable, from a final histogram). U_list = max over samples of (instances − baseline)
  × 48 B + the `Object[D]`. The forced GCs slow the request, which is acceptable in a diagnostic arm. Also
  per-request latency (used to judge overlap) and response length.
- **All arms:** GC log `-Xlog:gc*=info:file=<run>/gc.log:time,uptime,level,tags:filecount=5,filesize=20m`
  (heap before/after every pause → live-heap peaks; `gcwin.py` for the service-loss criterion); JMX sampler
  (`C2Sampler`, 1 s: heap used, GC counts) as in U4; `RssAnon`, cgroup `memory.current` and `memory.events` at
  start/end and on death; client CSV (requests started/completed, latency, errors); `stdout.log` for
  `java.lang.OutOfMemoryError` and the `OnOutOfMemoryError` lines.
- **At OOM (2 GiB only):** the default heap dump into the run dir (≤ 2 GiB). For **T run 1** run
  `hprofhist.py` (class histogram: expect `HeapByteBuffer` ≈ k·D with k = splits in progress, `Object[]` of
  64,000,016 B × k) and `hprofstacks.py <hprof> VectorType` (the request thread's frames:
  `VectorType$FixedLengthSerializer.split` / `VectorType.toJSONString` / `Selection.rowToJson` or the
  `StringBuilder` growth inside `toJSONString`); keep the text outputs in `logs/`, delete the hprof. T runs 2–3:
  record the dump size and delete it unparsed unless time allows. Arms above 2 GiB (D1, B):
  `-XX:-HeapDumpOnOutOfMemoryError` appended in `JVM_EXTRA_OPTS` (disk: 18 G free). Parse a dump on the node's
  one spare core while a light arm (C1) runs, and note it in §3.

**Predicted response** (stated before readings).
- D1: response 112,000,007 B per request; peak ΔHeapByteBuffer ≥ 0.9·D (≥ 14.4M) in at least one sample per
  request during the append loop; U_list ≈ 0.79–0.87 GB per request against K = 16 MB (≈ 52×). Latency per
  request a few seconds on the m400 (estimate 3–15 s).
- T (2 GiB, N = 2): Java heap OOM (`java.lang.OutOfMemoryError: Java heap space`, process killed by
  `OnOutOfMemoryError`) in **3/3**, in round 1, in a Native-Transport-Requests thread inside `toJSONString`
  (split or `StringBuilder` growth); the dump shows ≈ 2·D `HeapByteBuffer`. Live heap after the last full GCs
  > 1.9 GiB. cgroup `oom_kill` 0.
- C1 (plain, N = 2): **0/3** OOM; all 10 requests per run return 16,000,000 B; live heap < 0.5 GiB.
- I (patched, N = 2): **0/3** OOM; all requests return 112,000,007 B; live heap peaks ≈ 0.9–1.3 GiB.
- C2 (N = 1): **0/3** OOM (peak 1.1–1.5 GB live; long G1 pauses possible; the margin is the weakest prediction).
- B: OOM at 4 GiB (N = 6) and 8 GiB (N = 11); at 16 GiB (N = 21) OOM or GC service loss (21 concurrent renders on
  8 cores). The largest failing heap is reported with its n/3.
- **False-positive conditions:** D1 shows ΔHeapByteBuffer < 0.5·D in every in-loop sample (the list is not what is
  held), or T survives at N = 4 with the list measured at the predicted size (then the arithmetic is wrong).

**Stopping budget.** Per run: 10 min wall from the first request, or node death, whichever first; a run that
completes R rounds with the node alive and no OOM line is a survival (record GC service loss with `gcwin.py`
separately). No escalation after an OOM beyond the pre-declared dials. Stage-2 wall time must end before
**18:07 America/New_York, 2026-11-18**.

**Time plan** (stage 2 start T0, expected ≈ 14:30 EST; each lifetime ≈ 1.5 min start incl. pre-touch + 1 min
load/flush + run + stop):

| Step | Budget | Cumulative (T0 = 14:30) |
|---|---|---|
| Setup: copy tree, conf, compile client and patched class, check the node | 15 min | 14:45 |
| D1 (1 lifetime, 3 requests with histograms) | 15 min | 15:00 |
| T × 3 (+ T1 dump parse started in background) | 25 min | 15:25 |
| C1 × 3 (dump parse finishes) | 20 min | 15:45 |
| I × 3 | 20 min | 16:05 |
| C2 × 3 (≤ 10 min each) | 30 min | 16:35 |
| B: 4 / 8 / 16 GiB, then 2 repeats at the largest failing heap | 55 min | 17:30 |
| Cleanup, §3, §4, write-backs | 30 min | 18:00 |

Hard rules: no new run starts after **17:35 EST**; every process started by stage 2 is stopped by **17:50 EST**. If
T0 is later, drop from the bottom: B repeats, then the 16 GiB step, then 8 GiB, then C2 to 1 run. The minimum
valid set (V1–V5) is D1, T × 3, C1 × 3, I × 3 (≈ 1 h 50 min including setup).

**Node fit.** RAM: at most a 16 GiB heap (pre-touched) + ≤ 2.4 GB direct in use + client ≤ 16 GiB → < 40 GiB of
62 GiB. Cores: 8 shared by node and client (recorded). Disk: tree 0.47 G + per-run node dir < 0.2 G (wiped) + logs
(GC ≤ 100 M per run) + at most one 2 GiB hprof at a time → peak < 3.5 G of 18 G free. ARM only: never mix with x86
runs; record `aarch64`.

**Controls and intervention (summary).** V2: C1 (matched data, concurrency and budget, no split) ×3 and C2 (low
multiplicity alone) ×3. V4: I (list removed by a one-method diagnostic build, same load) ×3; reproduce the original
failure on the unmodified build (T). V3: D1 histograms plus the T1 dump histogram. V5: T1 dump stack and histogram,
`stdout.log` OOM lines, GC log. V6: defaults as audited. V7: 2 GiB primary, upward search.

**Cleanup.** Stop every Cassandra, client and sampler process started by stage 2; delete `/mydata/s4/u8/node` and
every hprof; leave `/mydata/s4/u8/runs/` (logs only) and `/mydata/s4/u8/tree` and say so in §3. Do not touch
`/mydata/s4/cassandra-base`, `/mydata/s2r2`, `/mydata/u1r2`.

`sha256 of §1–§2 at freeze: 952aa7d56d84b789e116c7f71fb5c4e8ed2c3a0fbe636128c3a3c47c0654ad7e` · computed over the lines from `## 1. Candidate` through the line before this one (`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum`) · amendments after the freeze: dated, with reason, below this line.

**Stage-2 amendments (dated, with reasons; §1–§2 above unchanged, freeze hash re-checked and matching at stage-2 start,
2026-11-18 13:51 EST).**

- **A1 (13:52 EST, path).** Node root is `/mydata/s4/u8-w4/` instead of `/mydata/s4/u8/` (the stage-2 instruction asked
  for a fresh directory). Layout otherwise as designed (`tree/`, `conf-pristine/`, `node/`, `runs/<label>/`, `cls/`,
  `patch/`, plus `out/<label>/` for the small files copied into `logs/`). `/proj` is not mounted on `ms0640`; small
  files were copied back with `rsync`.
- **A2 (13:58 EST, D1 instrument).** The first D1 lifetime (`D1-8G-attempt0`) ran with a histogram summarizer that did
  not match `jcmd`'s `(java.base@11.0.33)` module suffix, so its per-sample class counts were lost (the files were
  deleted after summarizing). Its 3 responses (112,000,007 B each) and total-live readings are kept in
  `logs/D1-8G-attempt0/`; D1 was re-run from a clean start as `D1-8G` with the parser fixed and the loop sleep cut to
  0.5 s (one histogram takes ≈ 1.5 s itself, so samples are ≈ 1.7–3.4 s apart instead of 2 s).
- **A3 (14:05 EST, parse timing).** The T1 dump was parsed at nice 19 during T2–T3 instead of during C1 (one core of
  8; T runs OOM within 12 s of load). Time allowed, so the T2 and T3 dumps were also parsed (histogram + stacks)
  before deletion.
- **A4 (14:50 and 15:10 EST, B stopping rule; harness defects, not design changes).** The frozen stopping budget is
  "10 min wall from the first request, or node death"; the client exits "when R rounds finish or the node is
  unreachable". (a) The first client also treated its own 120 s read timeout as "unreachable", so `B-8G-N11-1` and
  `B-16G-N21-1` stopped the client after round 0 and the harness then stopped the live victim at +126/128 s.
  Fixed at 14:50 (`U8Client.java`: only `NoHostAvailableException` / `TransportException` end the run).
  (b) In `B-16G-N21-2` and `B-8G-N11-2` the driver itself closed connections to the GC-stalled node
  (`TransportException: Connection has been closed`), the client gave up, and the harness again stopped the live
  victim (+128/157 s). Fixed at 15:10 (`run-arm.sh` watch rule: if the client gives up with `down=true` while the
  victim is alive, keep watching the victim to 600 s from the first request or its death). These four early-stopped
  lifetimes are recorded below but count neither as survivals nor as failures. The B search was then re-run from the
  largest step (`batch-b3.sh`: 16 GiB first; 8 GiB only if 16 GiB survived; 6 GiB, N = 9, only if 8 GiB survived),
  which is the design's "largest failing budget" rule; 16 GiB failed 3/3, so 8 GiB was not re-run under the watch rule.
- **A5 (recorded, not a change).** With R = 3 and the 120 s client timeout (both frozen), a client that is still
  connected after round 0 times out sends round 1. In `B-16G-N21-w1`, `-w3` and `B-8G-N11-2` the 21 (11) round-1
  requests were sent at +120 s and failed with `TransportException` 26–78 s later; whether the node accepted them was
  not measured (the JMX sampler stops answering during the full-GC stall, so `ntr_active` is stale). Server-side
  multiplicity in w1/w3 is therefore between 21 and 42. In `B-16G-N21-w2` connections closed before round 1, so only
  the 21 round-0 requests were ever sent, and it also ended in OOM.
- No other deviation. `vector<boolean, 16000000>` was accepted (no fallback); every arm used the unmodified jar
  except I (class-load log: `VectorType` from the run's `conf/` in I, from the jar in every other run).

## 3. Runs (stage 2)

**Environment.** `ms0640` (node1.jason92-326377, Utah m400), **aarch64**, 8 cores, 62 GiB, swap 8 GiB (victim scope
`MemorySwapMax=0`), cgroup v2, Ubuntu 22.04, OpenJDK 11.0.33; no other Java process before or during stage 2
(`pgrep -af CassandraDaemon` empty at 13:51 EST). Build: `/mydata/s4/cassandra-base` copied to
`/mydata/s4/u8-w4/tree`, jar sha256 `2a9cbd5c…2c26712`. Arm-I classes (`harness/vectortype-intervention.diff`, one
method): `VectorType.class` sha256 `46f14457…3d7567` (+ 4 nested classes, hashes in `logs/I-2G-N2-*/run.meta`).
Resolved limits from `ps` (every run): `-Xms=-Xmx` = the arm's heap, `-XX:MaxDirectMemorySize=15872M` (auto: heap set
by hand, `MAX_DIRECT_MEMORY_SIZE` unset, `cassandra-env.sh` → heap_limit 31,744 / 2), G1 with the shipped options,
`AlwaysPreTouch`, `OnOutOfMemoryError=kill -9 %p`; heap dump on OOM at 2 GiB only. `yaml.diff` (every run) = the five
directories only. Victim scope `MemoryMax` = heap + 15,872 + 8,192 MiB; `memory.events` `oom_kill 0` in every run.
Single node, client on the same node (loopback), protocol V4, CL ONE. Data per lifetime: empty node dir → schema → one
prepared `INSERT` of a 16,000,000-byte zero vector (458 ms in D1) → `nodetool flush u8` → `SELECT v` returned
exactly 16,000,000 B in every lifetime → idle 30 s → load.

**Harness** (`harness/`): `setup.sh`, `victim-ctl.sh`, `run-arm.sh`, `batch.sh` (frozen arm list), `batch-b2.sh` /
`batch-b3.sh` (B re-runs, A4), `U8Client.java`, `C2Sampler.java` (JMX, 1 s), `gcwin.py`, `hprofhist.py`,
`hprofstacks.py` (from U4), `VectorType.java` + `vectortype-intervention.diff`. **Full logs on the node:**
`ms0640:/mydata/s4/u8-w4/runs/<label>/` (system/stdout logs, `gc.log*`, `classload.log`, client CSV, samples,
histograms). **Excerpts:** `logs/<label>/` (outcome, run.meta, yaml.diff, readings, samples, client.csv, gcwin, GC
pause tail, max post-GC heap, OOM excerpt, class-load lines, memory.events, run-arm.out) and `logs/batch*.log`,
`logs/batch.outcomes`.

**Runs.** D = 16,000,000; "live" = heap after a Full GC from the GC log unless stated; K = the only byte counts that
exist on this path: 16,000,000 B for the cell (write-side `max_mutation_size` / frame) and ≈ 60 B per `SELECT`
request (in-flight limit). Times are from the first request of the run.

| Run | Arm | Budget (heap / direct) | Load reached | Endpoint | Key reading (U vs K) |
|---|---|---|---|---|---|
| `D1-8G` | D1 diagnostic | 8 GiB / 15,872M | `json` N = 1, 3/3 requests, each 112,000,007 B, 5.45–6.79 s (with forced histograms) | none (diagnostic) | baseline `HeapByteBuffer` 647; in-loop samples s3 and s6: **16,000,654** (Δ = 16,000,007 = **1.0000·D**, 768,031,392 B = 48.0 B each), `Object[]` 67.4 MB (Δ 64.1 MB = one `Object[16,000,000]`); total live 951–1,008 MB vs 51.2 MB baseline. **U_list = 832 MB per request vs K = 16 MB (52×).** After the list dies (s9): `HeapByteBuffer` back to 648, `byte[]` 401 MB (the JSON copies) |
| `T-2G-N2-1` | T test | 2 GiB / 15,872M | `json` N = 2, round 1; 0/2 completed | **Java heap OOM** at ≈ +11.8 s | live 1,755 → 1,894 MB over 6 Full GCs (last 1,894 of 2,048 MB); dump 2.64 GB: `HeapByteBuffer` **32,000,660 = 2·D + 660** (1,678.5 MiB in the parser's 55 B/object estimate), `Object[]` 125.0 MiB (2 × 64 MB), `byte[]` ≥ 8 MiB: 6 arrays 235.6 MiB; OOM thread: `Arrays.copyOf` ← `AbstractStringBuilder.ensureCapacityInternal` ← `StringBuilder.append` ← **`VectorType.toJSONString:286`** ← `:274` ← `Selection.rowToJson:339` ← `ResultSetBuilder.getOutputRow:175` ← `SelectStatement.process:1014`; other request thread in `toJSONString:283` (loop) |
| `T-2G-N2-2` | T test | 2 GiB / 15,872M | same; 0/2 completed | **Java heap OOM** at ≈ +11.6 s | last live 1,862 MB; dump 2.60 GB: `HeapByteBuffer` 32,000,660, `Object[]` 125.0 MiB; OOM thread in `toJSONString:286` (StringBuilder growth), other in `:283` |
| `T-2G-N2-3` | T test | 2 GiB / 15,872M | same; 0/2 completed | **Java heap OOM** at ≈ +10.6 s | last live 1,862 MB; dump 2.59 GB: `HeapByteBuffer` 32,000,660, `Object[]` 125.1 MiB; OOM thread in `toJSONString:286`, other in `:283` |
| `C1-2G-N2-1..3` | C1 matched path (`SELECT v`) | 2 GiB / 15,872M | N = 2, 5 rounds, **10/10** per run, 16,000,000 B each, mean 186–189 ms (max 334 ms) | none, 0/3 | 0 Full GCs; max heap after any GC 32 MB; GC STW 0 % of any 60 s |
| `I-2G-N2-1..3` | I intervention (list removed) | 2 GiB / 15,872M | N = 2, 5 rounds, **10/10** per run, **112,000,007 B** each (same as D1), mean 3.18–3.28 s (max 3.83 s), ≈ 20 s per run | none, 0/3 | live after Full GC 305 / 385 MB (runs 1–2; run 3 had no Full GC); heap after young GC ≤ 1,601 MB (unreclaimed humongous JSON buffers); `VectorType` loaded from the run's `conf/` |
| `C2-2G-N1-1..3` | C2 low multiplicity | 2 GiB / 15,872M | N = 1, 5 rounds, **5/5** per run, 112,000,007 B, mean 5.44–5.55 s (max 6.70 s) | none, 0/3 | live after Full GC peaks **969–973 MB** (one list + JSON); 4–6 Full GCs; STW ≤ 12 % of any 60 s |
| `B-4G-N6-1..3` | B budget search | 4 GiB / 15,872M | N = 6, round 1; 0/6 completed | **Java heap OOM** 3/3 at +66 / +79 / +74 s | live 4,080–4,083 of 4,096 MB; GC service loss before the OOM (≥ 90 % STW over 71 / 86 / 80 s); no dump (disabled > 2 GiB) |
| `B-8G-N11-1` | B (early-stopped, A4a) | 8 GiB / 15,872M | N = 11, round 0 timed out at +120 s | not concluded: service loss (≥ 90 % STW over 277 s incl. stop), stopped at +126 s | live 8,141–8,144 of 8,192 MB |
| `B-8G-N11-2` | B (early-stopped, A4b) | 8 GiB / 15,872M | N = 11 round 0 timed out, round 1 sent at +120 s, connections closed +148–150 s | not concluded: service loss (166 s window), stopped at +157 s | live 8,172 of 8,192 MB |
| `B-16G-N21-1` | B (early-stopped, A4a) | 16 GiB / 15,872M | N = 21, round 0 timed out at +120 s | not concluded: service loss (277 s window), stopped at +128 s | live 16,329–16,330 of 16,384 MB, Full GC ≈ 9.9 s each |
| `B-16G-N21-2` | B (early-stopped, A4b) | 16 GiB / 15,872M | N = 21 round 0 (2 connections closed at +90 s) | not concluded: service loss (129 s window), stopped at +128 s | live 16,342 of 16,384 MB |
| `B-16G-N21-w1` | B (watch rule) | 16 GiB / 15,872M | N = 21 round 0 (timeouts +120 s) + round 1 sent (failed +184 s), A5 | **Java heap OOM** at +266 s | live 16,371 of 16,384 MB; service loss over 289 s (260 s paused, 23 Full GCs) |
| `B-16G-N21-w2` | B (watch rule) | 16 GiB / 15,872M | N = 21 round 0 only (connections closed +49 / +92 s; 15 timeouts +120 s) | **Java heap OOM** at +367 s | live 16,368 of 16,384 MB; service loss over 400 s (360 s paused, 33 Full GCs) |
| `B-16G-N21-w3` | B (watch rule) | 16 GiB / 15,872M | N = 21 round 0 (timeouts +120 s) + round 1 sent (failed +146–198 s), A5 | **Java heap OOM** at +332 s | live 16,371 of 16,384 MB; service loss over 362 s (326 s paused, 30 Full GCs) |
| `D1-8G-attempt0` | (discarded, A2) | 8 GiB / 15,872M | N = 1, 3/3, 112,000,007 B | none | total live 1,007.5 MB in one in-loop sample (consistent with D1) |

Every OOM line is `java.lang.OutOfMemoryError: Java heap space` in `stdout.log` followed by
`-XX:OnOutOfMemoryError="kill -9 %p"`; `scopeOomKill` 0 and cgroup `oom_kill 0` in every run (the isolation scope never
fired). GC service-loss criterion (protocol default) **not** met in T (≤ 16 % STW in any 60 s; the OOM comes within
12 s), met before every B OOM and in every early-stopped B run.

**Predictions vs readings.** D1: met (ΔHeapByteBuffer = 1.0000·D, U_list 832 MB, latency 5.5–6.8 s). T: OOM 3/3 in
round 1 in `toJSONString` with ≈ 2·D `HeapByteBuffer` in the dump, as predicted; the last live heap was 1,862–1,894 MB
(1.82–1.85 GiB), a little below the predicted "> 1.9 GiB" (G1 fails a humongous allocation of the growing JSON
buffer before the old generation is full). C1: met (0/3, 10/10 at 16,000,000 B, live < 0.5 GiB). I: 0/3 with all
112,000,007 B responses, as predicted; live after Full GC 0.3–0.4 GB, below the predicted 0.9–1.3 GiB peak (the list
is the larger part). C2: 0/3, live peak 0.97 GB, below the predicted 1.1–1.5 GB. B: 4 GiB OOM as predicted; 8 GiB
predicted OOM, observed service loss only, not concluded (A4); 16 GiB predicted "OOM or service loss", observed
service loss then OOM 3/3. Neither false-positive condition occurred.

**Cleanup.** Every Cassandra, client and sampler process started by stage 2 was stopped (by PID; OOM-killed victims
by `OnOutOfMemoryError`); no `u8-` scope left; checked 15:41 EST. All three hprofs (2.59–2.64 GB) were parsed and
deleted; `/mydata/s4/u8-w4/node` deleted. Left on `ms0640`: `/mydata/s4/u8-w4/` (722 MB: `tree/` 469 MB, `runs/`
logs, `out/`, `cls/`, `patch/`, `harness/`). `/mydata/s4/cassandra-base`, `/mydata/s2r2`, `/mydata/u1r2` untouched.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`**, direction **unprotected** (unprotected
accumulation: no control applies to the per-element split list or the JSON buffers; unprotected configuration: the
`vector_dimensions` guardrail ships at −1), endpoint **Java heap OOM**, n/N **3/3** at heap 2 GiB / direct 15,872M
(resolved), every capacity constraint at its shipped default. Largest failing heap budget tested: **16 GiB, 3/3**
(after GC service loss); 4 GiB 3/3; 8 GiB not concluded (service loss, early-stopped; A4).

**Reason.** One `vector<boolean, 16000000>` cell (16,000,000 B, accepted at defaults because only serialized bytes
are checked: `max_mutation_size` 16 MiB, frame 16 MiB, dimension guardrail −1) is rendered by `SELECT JSON` through
`VectorType.toJSONString`, which first `split()`s it into an `ArrayList` of 16,000,000 `HeapByteBuffer` slices and
keeps it for the whole append loop. D1 measured that list independently of any counter: ΔHeapByteBuffer = 16,000,007
(1.0000·D) plus a 64 MB `Object[]`, **U = 832 MB per request against K = 16 MB (52×)**, ≈ 0.95 GB live per request
with the JSON buffer. Two concurrent `SELECT JSON` reads of that one row killed a 2 GiB-heap Cassandra 5.0.9 node with
`OutOfMemoryError: Java heap space` in **3/3** runs within 12 s; each dump held 32,000,660 `HeapByteBuffer` (two
whole lists) and the failing request thread was growing the JSON `StringBuilder` inside `toJSONString:286` while the
other was still in the loop. The matched-path control (`SELECT v`, same row, same N = 2, 2 GiB) served 10/10 reads
per run with ≤ 32 MB live after GC (0/3), one JSON read at a time (N = 1) served 5/5 per run with a 0.97 GB live
peak (0/3), and the one-method intervention that walks the elements without materializing the list served 10/10
identical 112,000,007-byte JSON responses per run at N = 2 (0/3, live ≤ 0.39 GB after Full GC, 3.2 s per request vs
5.5 s at N = 1 unpatched), so the list is the cause and the fix keeps the useful work. The same holder scales with
concurrency up the budget range: 6 reads at 4 GiB (3/3) and 21 reads at 16 GiB (3/3, after 4–6 min of ≥ 90 % GC
time) ended in heap OOM; native-transport threads (128) are the only bound.

**V1–V7.**

| | Evidence |
|---|---|
| V1 Repetition | `T-2G-N2-1..3`: Java heap OOM 3/3 at N = 2 (+ `B-4G-N6-1..3` 3/3, `B-16G-N21-w1..w3` 3/3) |
| V2 Matched control | `C1-2G-N2-1..3` (`SELECT v`, same row/N/budget/build): 0/3; `C2-2G-N1-1..3` (N = 1): 0/3 |
| V3 Measurement | U from `jcmd GC.class_histogram` in flight (D1: ΔHeapByteBuffer 1.0000·D, Δ`Object[]` 64 MB) and from the three T dumps (32,000,660 `HeapByteBuffer`, 2 × 64 MB `Object[]`); GC-log live heap; K = 16 MB cell / ≈ 60 B request (no counter on the holder) |
| V4 Intervention | `I-2G-N2-1..3` (diagnostic class, diff saved; unmodified-build failure reproduced in T): 0/3 OOM, 10/10 correct responses per run (throughput kept) |
| V5 Initiating failure | OOM thread stack from each dump: `StringBuilder.append` growth in `VectorType.toJSONString:286` ← `Selection.rowToJson:339` ← `SelectStatement.process`; dump histogram shows two whole split lists; `stdout.log` OOM lines; GC logs |
| V6 Default constraints | `vector_dimensions_*` −1, `commitlog_segment_size` 32 MiB (`max_mutation_size` 16 MiB), frame 16 MiB, NTR 128, in-flight limits heap/10, heap/40, read thresholds off, `column_value_size` null, `AllowAllAuthenticator`; `yaml.diff` = directories only |
| V7 Acceptable budget | heap 2 GiB (ideal; ≥ 512 MiB standing rule), direct 15,872M as resolved by the shipped `cassandra-env.sh` with a hand-set heap; also 4 GiB and 16 GiB (≤ the node's own 31,744 MiB); scope limit isolation only, never reached |

| Condition | Status |
|---|---|
| 2 GiB heap, N = 2 | `verified-OOM · deployment` (unprotected), 3/3 |
| 4 GiB heap, N = 6 | heap OOM 3/3 (after service loss) |
| 8 GiB heap, N = 11 | GC service loss in 2 early-stopped runs (no status); OOM not tested to the 600 s budget |
| 16 GiB heap, N = 21 | heap OOM 3/3 (after 4–6 min service loss; w1/w3 had up to 42 requests sent, w2 exactly 21) |

**Limits of attribution.** (1) The cell is a 16-million-dimension vector of booleans: accepted at defaults (no
guardrail, no size check beyond 16 MiB serialized), but unusual for vector search; the same split shape exists for
`float` (4 B per element → 13× instead of 52×) and for variable-length elements (not tested, §1). (2) Single node,
coordinator = replica, one local client, protocol V4; the holder is on the coordinator after the read, so replication
does not change it. (3) At 16 GiB the OOM came only after minutes of GC thrash, and in two of three runs the frozen
client re-sent a round after its 120 s timeout (A5), so the 16 GiB multiplicity is 21–42; w2 (exactly 21) also
failed. (4) 8 GiB was not taken to the 600 s budget. (5) `toJson(v)` and `asComparableBytes` were not tested.

**Shape for phase 1.** Covered by CP-12 (one item materialized whole: "a string rendering of a value") together
with CP-1 (the only byte checks count 16 MB serialized against 832 MB held); no new clue pattern needed.
