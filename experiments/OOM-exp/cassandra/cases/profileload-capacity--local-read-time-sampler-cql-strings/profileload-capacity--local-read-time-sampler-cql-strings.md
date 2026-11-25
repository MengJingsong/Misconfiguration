# B26 — profileload sampler capacity (`-s`): the LOCAL_READ_TIME sampler keeps up to 256 whole rendered CQL strings, counted, never sized (OC-590 + OC-587)  <!-- file: cassandra/cases/profileload-capacity--local-read-time-sampler-cql-strings/profileload-capacity--local-read-time-sampler-cql-strings.md -->

| Field | Value |
|---|---|
| Case ID | `B26` (B = bypass case; README "ID prefixes") |
| From | `OC-590` (primary, guided) + `OC-587` (autonomous, same holder) of the phase 1 OOM candidate list; owner-approved batch of 2026-11-24 |
| Phase-1 case file | [`profileload-capacity-beginsampling-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/profileload-capacity-beginsampling-capacity--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built copy `pc91:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 session, 2026-11-24 ≈ 05:30–05:54 America/New_York (frozen 05:54); nothing run (read-only checks of the five x86 nodes over ssh, JIRA read via REST) |
| Stage 2 (verify) | fresh OOM-agent sessions on `pc91`, 2026-11-24: attempt 1 ≈ 11:51–12:55 EST ran the lifetimes but ended before §3–§4; attempt 2 (this write-up, T0 15:01:46 EST) re-analysed the T dumps, fixed and reran the two all-tables arms, ran the CAL-4G/CAL-8G REPs, wrote §3–§4 |
| Verdict | **true positive** · `verified-OOM · deployment` |

## Summary

- **Conclusion:** **true positive** (`verified-OOM · deployment`), conditional on an operator running `nodetool
  profileload` (an admin diagnostic) while large clustering-`IN` reads arrive. With every constraint at its default
  (`profileload b26 t1`: `-s 256`, 10 s, all samplers), 2 GiB heap, S16 reads at c = 4: heap OOM **3/3** ≈ 7–9 s into
  sampling, the first `OutOfMemoryError` in the render (`ReadExecutionController.addSample` → `toCQLString`); each dump
  holds 108–110 rendered 16,008,07x-byte strings reachable only via `TableMetrics.topLocalReadQueryTime`'s queue
  (87.1–87.7 % of the dump). No session (M) 0/3; samples cut to 1,024 characters (I, same render work) 0/3; `-s 32`
  (D) 0/3. After a finished session the queue still holds 244 strings (3.906 GB released by the next session, exactly
  244 × 16,008,072 B). Upward search: OOM at **15,872 MiB** (2 tables) and **31,744 MiB** (cassandra-env's own heap for
  this node, 4 tables) in an all-tables 60 s session (451 / 915 strings, 97–99 % of the dump); a single-table 10 s
  session survives at 4 GiB (3/3) and 8 GiB (3/3) only because the window closes first, leaving 3.5 GiB (85 % of
  heap) / 5.4–6.0 GiB held until the next session.
- **Hypothesis (stage 1):** while an operator runs `nodetool profileload` with its shipped defaults (`-s 256`, `-k 10`,
  all samplers, 10 s), every local read renders its whole command to a CQL string (`command.toCQLString()`) and offers
  it to the per-table `LOCAL_READ_TIME` `MaxSampler`, which keeps the 256 slowest. The capacity counts strings, not
  bytes. A single-partition read with a clustering `IN` list of 2,000 × 4,000-byte blobs (an 8 MB request, inside the
  16 MiB native frame; the IN guardrail ships off) renders to a ≈ 16.0 MB string (hex, 2 characters per byte), which
  on G1 with the shipped 16 MiB regions is one humongous region per kept sample. 256 kept samples are 4 GiB per table,
  so a 2 GiB heap is predicted to run out after ≈ 80–110 kept samples (a few seconds of reads), while the same reads
  without sampling survive. The same holder at 2 regions per sample (≈ 30 MB strings) predicts OOM at 8 GiB on one
  table, and at the node's resolved heaps with 2–4 tables profiled at once.
- **Root cause (claimed, stage 1):** the sampler's only bound is a count (`maximumSize(max(1, capacity))`,
  `MaxSampler.java:45-47`); the item it keeps for `LOCAL_READ_TIME` is the full rendered command, whose size is bounded
  only by the request size (16 MiB) times the hex expansion (≈ 2×), and the queue also outlives the session
  (`finishSampling` takes only `count + 2` entries).

## 1. Candidate

**The rows** (`phase1-oom-candidates.md`, both set to `picked: B26 (2026-11-24)` by the coordinator):

> | OC-587 | 2026-11-24 | `profileload-capacity-beginsampling-capacity--autonomous` | autonomous | LOCAL_READ_TIME entries are full CQL strings from command.toCQLString(). They include the hex-rendered partition key (up to 64 KiB key, ~128 KiB of chars) and every clustering value of the filter (IN lists). The capacity limits only the number of strings, not their size, and the sampler keeps the slowest reads, which tend to be the largest queries. Example: a 500-value IN of 200-byte blob clusterings is ~200 KB per string, so ~50 MB per table at -s 256 and ~200 MB at -s 1024; profiling all tables multiplies that. [details](runs/p1-cassandra-2026-11-24.md#oc-587) | — | picked: B26 (2026-11-24) |

> | OC-590 | 2026-11-24 | `profileload-capacity-beginsampling-capacity--autonomous` | guided | LOCAL_READ_TIME MaxSampler keeps the full CQL string of each of the slowest reads (capacity counts queries, not bytes) and the string is rendered on the request thread for every read while sampling is on; a read with a large clustering IN list (the IN guardrail ships off) renders to MBs, and slow reads tend to be the large ones; e.g. a 10,000-value IN list of 100-byte blobs is ~2 MB per string, ~512 MB per table at the default -s 256 (kept after finishSampling), with up to 1000 queued tasks holding more [details](runs/p1-cassandra-2026-11-24.md#oc-590) | CP-2, CP-12, CP-14, CP-5 | picked: B26 (2026-11-24) |

**Full text, OC-590** (`runs/p1-cassandra-2026-11-24.md#oc-590`), quoted in part: "Holder: the String values of the
LOCAL_READ_TIME MaxSampler queue, and the strings captured by the pending samplerExecutor tasks. … while
topLocalReadQueryTime is enabled, ReadExecutionController records createdAtNanos for every local read and, on close,
calls command.toCQLString() and addSample(cql, timeMicros). The string is the whole WHERE clause: the partition key
rendered as a CQL literal … and every clustering of a names filter (ClusteringIndexNamesFilter.toCQLString appends each
clustering of the IN list) … Nothing bounds the string size: in_select_cartesian_product_warn/fail_threshold ship as -1,
so only the native frame (16 MiB) limits the request. … MaxSampler.finishSampling leaves capacity - count - 2 strings in
the queue until the next session on that table (CP-14)."

**Full text, OC-587** (`#oc-587`), quoted in part: "When LOCAL_READ_TIME is enabled, every local read builds String cql =
command.toCQLString() … The bound is maximumSize(max(1, capacity)) entries … with no byte limit. … Retention continues
after finishSampling … Up to 1000 pending insert tasks in samplerExecutor can each hold one such string, outside the
cap. … nodetool profileload with no table samples all tables with all samplers by default … which multiplies this per
table."

**What this design covers.** The holder both rows name (the `LOCAL_READ_TIME` queue of rendered strings) through the
clustering-IN form (OC-590's shape, OC-587's second example), sized to the native request limit; the per-table multiplier
of an all-tables session (both rows) in the upward budget search; the post-session retention (OC-590, CP-14) in one
calibration lifetime. **Not covered:** OC-587's large-partition-key form (≤ 64 KiB key → ≈ 128 KiB string, far smaller
than the IN form) and the `samplerExecutor` backlog (measured, not driven: the single sampler thread is not slowed
on purpose). OC-588 (read samplers pinning memtable slab regions) is a different holder and is kept out of this design
(no writes during the measured lifetimes, so no memtable keys are sampled; §2 workload).

**Phase-1 case and its stage-4 result.** Constraint: the sampler capacity, nodetool `profileload`/`toppartitions`
option `-s` (default 256, `tools/nodetool/ProfileLoad.java:52-53`; client-side maximum 1024, `:79`); server side it
goes to `MaxSampler.beginSampling` → `MinMaxPriorityQueue.maximumSize(Math.max(1, capacity))` (`metrics/MaxSampler.java:40-49`).
Unit: number of samples, not bytes. Stage 4 run 1 (2026-11-24, `ms0604`, aarch64): **Confirmed — caps** in both tiers:
the queue held exactly `min(max(1, C), N)` entries at every capacity; on a node, 1,000,000 writes kept exactly 256 /
1024 / 100,000 `Sampler$Sample` objects at C = 256 / 1024 / 100,000, ≈ 116 B per entry on the **write** path
(`WRITE_SIZE`, 10-byte keys). It never measured a `LOCAL_READ_TIME` entry, i.e. the bytes per counted item when the
item is a rendered query; that is this case's dial.

**JIRA prior art** (read only; REST `issues.apache.org/jira/rest/api/2/search`, `project = CASSANDRA`, 2026-11-24 ≈ 05:55
EST, requests ≥ 2.5 s apart; nothing posted):

| JQL (`project = CASSANDRA AND …`) | Hits | On point |
|---|---|---|
| `text ~ "profileload"` | 9 | CASSANDRA-14436 (adds the query-time sampler and `profileload`, fixed 4.0), 18022 (more profileload samplers, 5.0), 17821 (recurring profileload, 5.0); the rest unrelated (8612, 15589, 14916, 21732, 20159, 17445) |
| `text ~ "profileload" AND (text ~ "memory" OR text ~ "heap" OR text ~ "OOM")` | 1 | 14436 only (its javadoc: "Number of sample items to keep in memory … understand the memory trade offs"); its 24 comments discuss no string size |
| `text ~ "topLocalReadQueryTime"` | 3 | 14436, 20383 (bulk transfer), 15909 (metric names): none about memory |
| `text ~ "MaxSampler"` | 3 | 14436, 17821, 7926 (stress tool sample merging): none |
| `text ~ "beginLocalSampling"` | 5 | 16083, 17798 (flaky test), 14436, 18125, 16082: none |
| `text ~ "sampler" AND (text ~ "OutOfMemory" OR text ~ "OOM")` | 6 | 10449, 13213, 17178, 14239, 14096, 17992: none about the samplers |
| `text ~ "toppartitions" AND (text ~ "OutOfMemory" OR text ~ "heap")` | 0 | — |
| `text ~ "toCQLString" AND (text ~ "memory" OR text ~ "heap" OR text ~ "large")` | 26 | none about the sampler (read-size thresholds 16896/16850, RFP 15907, slow-query and timeout paths 7392) |
| `text ~ "LOCAL_READ_TIME"` | 474 | the phrase search matched consistency-level text; first 30 read by title, only 14436 on point |

Shipped docs (`NEWS.txt`, `conf/`, `doc/`): `NEWS.txt:214` describes the recurring `profileload` flag; no warning about
sampler memory; the nodetool help calls `profileload` "Low footprint profiling of activity for a period of time"
(`ProfileLoad.java:46`). **Verdict: `new`** (no issue reports or bounds the size of sampled query strings; not a
known-fixed bug, so not a positive control).

## 2. Design solution (stage 1; frozen)

**Direction and technique note.** **Bypass — accounting mismatch** of a count cap: the control counts kept samples
(K ≤ C = 256) and the bytes per sample are not counted or bounded, so U grows with the rendered size of each query
(U > what the count contract implies for its ≈ 116 B/entry write-path items). Multiplicity dials: kept samples per table
(≤ 256) and tables profiled at once (an all-tables session). Technique: [`bypass-playbook.md`](../../../bypass-playbook.md)
(compare the same workload with and without the suspect path; intervention bounds the retained item). Interpretation:
intentional count cap (documented as "items", with a memory-trade-off javadoc) plus a suspected implementation defect:
a diagnostic sampler retains whole rendered queries with no size bound, after the session too.

**Mechanism** (every line checked in `systems/cassandra/source`, 5.0.9).
1. **Session.** `nodetool profileload <ks> <table>` with defaults: capacity 256, top-K 10, all samplers, duration
   10,000 ms (`ProfileLoad.java:49-60, 82`). `NodeProbe.getPartitionSample` (`tools/NodeProbe.java:572-586`) calls
   `beginLocalSampling(sampler, 256, 10000)` for each sampler, sleeps the duration, then `finishLocalSampling(sampler, 10)`.
   With `<ks> '*'` or no keyspace, `StorageService.samplePartitions` (`service/StorageService.java:6533-6542`) does the
   same for every table. `MaxSampler.beginSampling` builds a new `MinMaxPriorityQueue` with
   `maximumSize(Math.max(1, capacity))` (`metrics/MaxSampler.java:40-49`), replacing (and freeing) any old queue.
2. **Render on every local read.** `ReadExecutionController.forCommand` records `createdAtNanos` only while
   `topLocalReadQueryTime.isEnabled()` (`db/ReadExecutionController.java:134`); `close()` then calls `addSample()`
   (`:210-211`), which renders `String cql = command.toCQLString()` and calls `addSample(cql, timeMicros)` (`:236-243`).
   `isEnabled()` stays true from `beginSampling` until `finishSampling` (`metrics/Sampler.java:121-124`), so rendering
   continues even after the duration has passed until nodetool finishes.
3. **Size of the string.** `AbstractReadQuery.toCQLString` (`db/AbstractReadQuery.java:101-118`): `SELECT <cols> FROM
   ks.t` + `appendCQLWhereClause` + limits + `ALLOW FILTERING`. For a single-partition read
   (`db/SinglePartitionReadCommand.java:1226-1236`): the partition key literal plus
   `ClusteringIndexNamesFilter.toCQLString` (`db/filter/ClusteringIndexNamesFilter.java:166-197`), which appends
   **every** clustering of the IN list (`ck IN (v1, v2, …)`). A blob renders as `"0x" + hex`
   (`serializers/BytesSerializer.java:65-67`; `utils/Hex.java:76-87`), 2 characters per byte, all ASCII, so JDK 11
   compact strings store it as a Latin-1 `byte[]` of ≈ 2 bytes per value byte. Two `StringBuilder`s grow by doubling
   (filter string, then the whole query) and each `toString()` copies, so the transient per render is ≈ 3–4 × the
   final string.
4. **Keep.** `Sampler.addSample` submits `insert(item, value)` to the single-thread `samplerExecutor` (queue limit
   1000 tasks, drop beyond, `Sampler.java:100-113`); `MaxSampler.insert` adds a new `Sample(item, value, 0)` when
   `value > 0` and (queue not full, or slower than the fastest kept) and Guava evicts the fastest once full
   (`MaxSampler.java:66-75`). The `TableMetrics` sampler stores the `String` as is (`metrics/TableMetrics.java:447-453`).
5. **After the session.** `finishSampling(10)` disables the sampler and polls while `result.size() <= count`: 12 polls
   (11 returned, 1 dropped), so **244 of 256 strings stay referenced** by the sampler until the next
   `beginSampling` on that table (`MaxSampler.java:52-63`). `finishLocalSampling` returns the 11 strings through JMX
   (`db/ColumnFamilyStore.java:2063-2079`).
6. **Where the read runs.** Single node, RF 1, CL ONE: the coordinator reads locally through
   `Stage.READ.maybeExecuteImmediately(new LocalReadRunnable(…))` (`service/reads/AbstractReadExecutor.java:165`), usually
   inline on the Native-Transport-Requests thread; the controller is closed (render included) before
   `command.complete()` (`service/StorageProxy.java:2208-2230`), so the render counts toward the slow-query time.
7. **Request size.** Prepared `SELECT v FROM b26.tN WHERE pk = ? AND ck IN ?` binding a `list<blob>`. Protocol v4 frame
   limit `native_transport_max_frame_size` 16 MiB (`config/Config.java:285`, `transport/Envelope.java:197`); v5 message
   limit min(`max_mutation_size` 16 MiB, in-flight heap/10, per-IP heap/40) (`config/DatabaseDescriptor.java:3237-3245`).
   The IN guardrail `in_select_cartesian_product_fail_threshold` ships `-1` (`conf/cassandra.yaml:2104-2105`).

**Claim.** With sampling on at its defaults, U (live heap held as kept `LOCAL_READ_TIME` strings) grows by ≈ one
rendered query (≈ 16.0 MB; one 16 MiB G1 humongous region) per kept sample, while K (kept samples) stays ≤ 256, until a
heap OOM at 2 GiB after ≈ 80–110 kept samples; the identical read load without sampling survives, and the same load on a
build that keeps only the first 1,024 characters of each sample survives.

**Protection map** (fixed before any run; s = rendered length of one sampled read).

| Domain | Holder (allocation → release) | Counter K | Limit at default | At the limit |
|---|---|---|---|---|
| Sampler capacity (`-s`) | `MinMaxPriorityQueue<Sample<String>>` of `topLocalReadQueryTime`, per table (`MaxSampler.java:45-47`) → freed when the next `beginSampling` replaces it | kept samples | **256** (nodetool default; ≤ 1024 client-side) | evict the fastest / refuse a faster one; **no byte bound**, item size unbounded |
| Post-session retention | the same queue after `finishSampling(10)` | — | none (244 kept until the next session on that table) | — |
| Sampler task queue | `samplerExecutor` tasks capturing `cql` (`Sampler.java:100-113`) → freed when run or dropped | tasks | 1000 tasks (hard-coded), shared by all samplers | drop (`_SAMPLE` dropped counter) |
| Render transient | the two `StringBuilder`s and copies on the request thread (`AbstractReadQuery.java:101-118`, `ClusteringIndexNamesFilter.java:166-197`) → garbage after `addSample` | — | none | — |
| Request size | the request body and the bound IN values / `ReadCommand` clusterings | bytes | 16 MiB frame / message (`Config.java:285`, `DatabaseDescriptor.java:3237-3245`) | request refused |
| Native in-flight bytes | request bodies in flight | bytes | heap/10, per IP heap/40 (2 GiB heap: 204.8 / 51.2 MiB) | backpressure; counts requests, not samples |
| IN size guardrail | — | IN product | `in_select_cartesian_product_*_threshold: -1` (off) | nothing (unprotected configuration, left off) |
| Slow-query monitor (confounder) | `MonitoringTask` keeps finished slow reads and renders their names (`db/monitoring/MonitorableImpl.java:114-115`; R12's holder) | operations | `slow_query_log_timeout` 500 ms, `monitoring_max_operations` 50 | keeps ≤ 50 per queue; **must stay idle** in this design (reads ≪ 500 ms; checked) |
| Other samplers in an all-sampler session | `READS`/`WRITES`/`CAS_CONTENTIONS` (`StreamSummary`), `READ_ROW_COUNT`/`READ_TOMBSTONE_COUNT`/`READ_SSTABLE_COUNT`/`WRITE_SIZE` (`MaxSampler<ByteBuffer>`) | entries | 256 each | `int` keys from sstables (no writes, empty memtables) → < 1 MiB in total |
| Baseline | node with ≤ 4 tiny tables, key cache min(5 % heap, 100 MiB), chunk cache (direct), networking pool 128 MiB direct | own | defaults | evict |

**Configuration and budget audit.**
- **Node: `pc91`** (UMass, x86_64, 32 cores, 125 GiB RAM; read-only check 2026-11-24 05:47 EST: `/mydata` 706 GiB
  free, load 0.00, **no java process**, `/mydata/s4` holds `3b-C10`, `3b-S2`, `cassandra-base` and a `NODE-LOCK/owner`
  file "phase1-hadoop o9 Mon Nov 23 11:12:13 PM MST 2026" (no matching process at the check); JDK 11.0.33; the node's
  clock is MST, log in EST). **Fallback node:** `pc72` (same class, same state at the check). Not `pc82` (Hadoop
  NameNode/DataNode running at the check). Stage 2 first re-checks: no `CassandraDaemon`/`java` of another case on the
  node and no lock newer than this design; otherwise use the fallback (record).
- Build: `/mydata/s4/cassandra-base` (5.0.9 SNAPSHOT jar) copied to `$ROOT/tree`, `ROOT=/mydata/s4/b26`; the intervention
  build is a second copy `$ROOT/tree-iv` with the one-line patch below. G1 with the shipped `jvm11-server.options`
  (`-XX:G1HeapRegionSize=16m`, `MaxGCPauseMillis=300`, `IHOP 70`), `HeapDumpOnOutOfMemoryError` and
  `OnOutOfMemoryError="kill -9 %p"` from `jvm-server.options`; compact strings on (JDK default; none of the shipped
  options disables them). Record `uname -r`, `java -version`, jar sha256s, the resolved `-Xmx` and
  `-XX:MaxDirectMemorySize` from `ps` in every `run.meta`.
- **Every capacity constraint at its shipped default (V6)** in T and M arms: sampler capacity **256**, top-K 10, all
  samplers, duration 10,000 ms (the `nodetool profileload <ks> <table>` defaults; the upward-search arms with several
  tables give the duration 60,000 ms explicitly, see below); `samplerExecutor` 1000 tasks (hard-coded);
  `in_select_cartesian_product_*` −1; `native_transport_max_frame_size` 16 MiB; `native_transport_max_message_size`
  derived; in-flight limits heap/10 and heap/40; `slow_query_log_timeout` 500 ms; `monitoring_max_operations` 50;
  `read_request_timeout` 5,000 ms; caches, memtables, `concurrent_reads` 32, `native_transport_max_threads` 128 at
  defaults; `AllowAllAuthenticator`. Only arms I (a code patch) and D (`-s 32`) differ.
- **Not constraints (documented operator/deployment choices, labelled):** running `nodetool profileload` at all (an
  operator diagnostic, off until run; the condition of the result), its duration argument (a time window, not a
  memory bound: 256 samples fill in seconds here), the schema (blob clustering column) and the client's IN list size.
- `cassandra.yaml` diff (environment only): the five directories under `$ROOT/node/`; addresses stay `localhost`. Save
  `yaml.diff` per lifetime.
- **Budgets (V7; standing rule ≥ 512 MiB, 2 GiB ideal, search upward):**
  - **Primary: heap 2,048 MiB** (`MAX_HEAP_SIZE=2G`). Direct left to `cassandra-env.sh` (on this node with G1:
    `heap_limit` 31,744, ½ RAM > it → `MaxDirectMemorySize` 15,872 MiB; record from `ps`). Heap regions: 128 × 16 MiB.
  - **Upward search:** 4,096 MiB, 8,192 MiB, 15,872 MiB, and optionally **31,744 MiB** = what `cassandra-env.sh`
    resolves for this node by itself (`MAX_HEAP_SIZE` unset; G1 branch `heap_limit` 31,744 since ½ RAM ≈ 64,000 MiB
    exceeds it; record from `ps`).
  - **No container budget.** Victim in `systemd-run --user --scope -p MemorySwapMax=0` for isolation only (swap off;
    B17's `victim-ctl.sh` pattern). A scope `oom_kill` makes the lifetime invalid; record `memory.events`.
- **RAM:** ≤ 31,744 heap + direct use (small) + client JVM 8 GiB + nodetool 128 MiB — fits 125 GiB.
- **Disk:** data ≈ 10 MiB; hprofs 2 GiB each at 2 GiB heap (keep the three T dumps until §3 is written); for heaps
  ≥ 8 GiB write the dump (disk is ample) but delete it after `bigarrays.py`/`retainers.py` have run, keeping their
  output.

**Ceiling arithmetic.** Two request shapes, both inside the 16 MiB request limit:

| Shape | IN values n × bytes b | Request body | Rendered string s | G1 regions per kept sample |
|---|---|---|---|---|
| **S16** | 2,000 × 4,000 B | ≈ 8.01 MB | 2,000 × 8,002 + 3,998 + ≈ 70 ≈ **16,008,100 B** (15.27 MiB) | **1** (< 16 MiB, humongous) |
| **S30** | 3,750 × 4,000 B | ≈ 15.02 MB (< 16,777,216) | 3,750 × 8,002 + 7,498 + ≈ 70 ≈ **30,015,100 B** (28.6 MiB) | **2** (32 MiB) |

Retained per table at the default capacity: S16 256 × 16 MiB = **4,096 MiB**; S30 256 × 32 MiB = **8,192 MiB** (in
regions; byte[] bytes 3,908 / 7,328 MiB). After the session (244 kept): 3,904 / 7,808 MiB. Baseline (idle node, tiny
tables): 150–350 MiB (≈ 10–22 regions). Transient per in-flight sampled read (S16): request 8 MB + clusterings 8 MB +
render chain ≈ 48–64 MB (filter string, outer builder up to 2×, final copy) ≈ 64–80 MB, at c = 4 ≈ 256–320 MB
(≈ 16–20 regions); without sampling ≈ 16 MB per read.
- **2,048 MiB (128 regions), S16, 1 table:** OOM when kept samples ≈ 128 − 20 (baseline) − 20 (transient) ≈ **80–110**
  (band 70–120); 256 can never fit. M (no sampling): ≤ 22 + 4–8 regions → survives. I (1,024-char samples): retained
  ≤ 256 × ≈ 1 KiB, transient as T → survives. D (`-s 32`): 32 regions retained + transient → ≤ 75 of 128 → survives.
- **4,096 MiB (256 regions), S16, 1 table:** 256 kept need 256 regions = the whole heap → **OOM** at ≈ 210–240 kept.
- **8,192 MiB (512 regions), S30, 1 table:** 256 × 2 = 512 regions = the whole heap → **OOM** at ≈ 220–245 kept.
  (S16 at 8 GiB: 4 GiB retained → survives; that is the CAL-RET lifetime.)
- **15,872 MiB (992 regions), S30, 2 tables (`profileload b26 '*' 60000`):** 512 × 2 = 1,024 regions > 992 → **OOM**
  at ≈ 450–490 kept in total. One table only → 512 regions → survives (boundary).
- **31,744 MiB (1,984 regions), S30, 4 tables:** 1,024 × 2 = 2,048 regions > 1,984 → **OOM** at ≈ 950–1,000 kept.
Σ contract capacities: the only bound is 256 items × (≤ 16 MiB request × ≈ 2) per sampler-table ≈ 8 GiB per table
(regions), × tables profiled; no byte budget exists. Direct memory: ≤ c × 15 MB of request frames + chunk cache
≤ 512 MiB + networking 128 MiB ≪ 15,872 MiB.

**Workload and environment.**
- Node `pc91` only: victim = one Cassandra node (coordinator = replica); client = one Java-driver JVM (`-Xmx8g`) on the
  same node (loopback); `bin/nodetool` from the victim tree (shipped 128 MiB client heap). Before every lifetime refuse
  to start if a `CassandraDaemon` runs.
- Schema: `CREATE KEYSPACE b26 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`; four tables
  `b26.t1` … `b26.t4`, each `(pk int, ck blob, v int, PRIMARY KEY (pk, ck))`, default options.
- Values: for partition p ∈ 0..63 a list L_p of 3,750 distinct 4,000-byte blobs from `Random(1_000 + p)` (S16 uses the
  first 2,000, S30 all 3,750). Data: in every table, each partition p holds 10 rows with `ck` = the first 10 values of
  L_p and `v` = 0..9 (64 × 10 rows × ≈ 4 KB ≈ 2.6 MB per table). Load once, `nodetool flush b26`, then the template
  (below). **No writes during measured lifetimes**, so memtables stay empty (keeps OC-588's slab holder out).
- Query (prepared, protocol v4, CL ONE, fetch size default 5,000): `SELECT v FROM b26.tN WHERE pk = ? AND ck IN ?`
  binding p and L_p's prefix (2,000 or 3,750 values). Each read returns 10 rows. Thread k reads pk = (k + 4·i) mod 64,
  table tN = round-robin over the lifetime's table set.
- Client `B26Load.java` (adapted from B17's `B17Load.java`; Java driver 3.12.1 from `$ROOT/tree/build/lib/jars`,
  4 connections, `readTimeoutMillis` 60,000, `FallthroughRetryPolicy`): `schema`, `load`, `one <S16|S30> <table>`,
  `run <S16|S30> <tables> <c> <secs>` (closed loop: each thread sends its next read when the last returns). Output: per
  second a CSV (`t, c, ok, err_by_class, reads_s, p50ms, p99ms, maxms, lastErr`), a `SUMMARY` line at the end.
- **Template.** Lifetime `LOAD` (heap 8G, not a reading): schema, data, flush, `SELECT count(*)` per table = 640,
  `nodetool drain`, SIGTERM; `cp -a $ROOT/node $ROOT/template`; `rm -rf $ROOT/template/saved_caches/*`. **Every
  measured lifetime starts from a fresh `cp -a` of the template.**
- **Lifetime procedure (all measured arms).** Start the victim; wait for `UN` and the native port; start the sampler
  (below); **warm-up**: client `run <shape> <tables> <c> 20` without sampling, then 10 s idle; **main**: start the
  client `run <shape> <tables> <c> 120` and, at client second 10, the arm's nodetool command (T, D, CAL, I) or
  `nodetool tpstats` (M) in the background, output to `$RUN/nodetool.out`; end at the first OOM (process gone) or at
  client second 120; then `nodetool tpstats` (dropped `_SAMPLE`), `nodetool drain`, SIGTERM by PID, collect.

| Label | Build | Heap | Shape | Tables | c | Session command (at client second 10) | Reps |
|---|---|---|---|---|---|---|---|
| `LOAD` (not a reading) | A | 8G | — | t1–t4 | 4 | — | 1 |
| `VERIFY+PROBE` (not a reading) | A | 8G | S16, S30 | t1 | 1, 4 | see below | 1 |
| `CAL-RET-8G` | A | 8G | S16 | t1 | 4 | `nodetool profileload b26 t1`; then retention measurement (below) | 1 |
| `T-2G-1..3` | A | **2G** | S16 | t1 | 4 | `nodetool profileload b26 t1` (all defaults) | 3 (+2 if 2/3) |
| `M-2G-1..3` | A | 2G | S16 | t1 | 4 | none (`nodetool tpstats`) | 3 |
| `I-2G-1..3` | **IV** | 2G | S16 | t1 | 4 | `nodetool profileload b26 t1` | 3 |
| `D-2G-1..3` optional | A | 2G | S16 | t1 | 4 | `nodetool profileload b26 t1 -s 32` (dose: capacity changed, control arm) | ≤ 3 |
| `CAL-4G` | A | 4G | S16 | t1 | 4 | `nodetool profileload b26 t1` | 1 (+2 REP if time) |
| `CAL-8G` | A | 8G | S30 | t1 | 4 | `nodetool profileload b26 t1` | 1 (+2 REP if time) |
| `CAL-15872M` | A | 15,872M | S30 | t1, t2 | 8 | `nodetool profileload b26 '*' 60000` | 1 |
| `BND-15872M-1T` optional | A | 15,872M | S30 | t1 | 8 | `nodetool profileload b26 t1 60000` (predicted survive: boundary) | 1 |
| `CAL-AUTO` optional | A | unset (→ 31,744M) | S30 | t1–t4 | 8 | `nodetool profileload b26 '*' 60000` | 1 |

  **Duration rule (pre-registered).** T, M, I, D, CAL-4G, CAL-8G keep the default 10 s window. If PROBE shows fewer
  than 25 S16 reads/s at c = 4 (fewer than ≈ 110 kept in 10 s), or fewer than 30 S30 reads/s, those arms use
  `… t1 60000` instead (same in T, I and D; recorded, not an amendment). The multi-table arms use 60,000 ms because
  512–1,024 S30 reads are needed in one window.

- **VERIFY+PROBE** (heap 8G, from the template): (a) `one S16 t1` returns 10 rows; `one S30 t1` returns 10 rows;
  (b) `nodetool profileload b26 t1 5000 -s 2000` is refused ("Capacity (-s) cannot exceed 1024."); (c) render size:
  `nodetool profileload b26 t1 5000 -a LOCAL_READ_TIME -k 1` while `one S16 t1` runs once → `wc -c nodetool.out` ≈ 16.0 MB
  and the line starts `SELECT v FROM b26.t1 WHERE pk = … AND ck IN (0x…` (keep the first 300 bytes in `logs/`); same
  with S30 ≈ 30.0 MB; (d) PROBE: S16 c = 1 ×5, then c = 4 for 30 s, then S30 c = 4 and c = 8 for 30 s each, without
  sampling, then S16 c = 4 for 30 s **with** `nodetool profileload b26 t1 20000 -a LOCAL_READ_TIME` → reads/s, p50/p99
  with and without sampling; `debug.log` lines matching `operations were slower than` (expected 0) and `Query cancelled`
  (expected 0). **Gate:** if p99 with sampling ≥ 400 ms at c = 4, rerun with c = 2 and use the c that keeps p99
  < 400 ms in every 2 GiB arm (recorded; the slow-query monitor must stay idle).
- **Retention measurement (`CAL-RET-8G`).** After nodetool returns (session finished, 10 s), wait 5 s, then M1:
  `jmap -histo:live $PID` (save; `Total` line) and `jcmd $PID GC.heap_info` (G1 used, humongous count from the GC log);
  then `nodetool profileload b26 t1 1000 -a LOCAL_READ_TIME` with the client stopped (the new `beginSampling`
  replaces and frees the queue), wait 5 s, M2 likewise. Release delta M1 − M2 = bytes the finished session still held.

**Intervention build (arm I, separate tree, diff saved as `harness/iv.patch`).**
```diff
--- a/src/java/org/apache/cassandra/db/ReadExecutionController.java
+++ b/src/java/org/apache/cassandra/db/ReadExecutionController.java
@@ private void addSample()
     {
         String cql = command.toCQLString();
+        if (cql.length() > 1024)
+            cql = cql.substring(0, 1024); // B26 intervention: bound the kept sample; the render itself is unchanged
         int timeMicros = (int) Math.min(TimeUnit.NANOSECONDS.toMicros(clock.now() - createdAtNanos), Integer.MAX_VALUE);
```
Build: `cp -a /mydata/s4/cassandra-base $ROOT/tree-iv`, `patch -p1`, `ant jar` (offline; the node built this tree
before). If `ant jar` cannot run offline, compile the one class with `javac -cp 'build/classes/main:lib/*:build/lib/jars/*'`
into `build/classes/main` and rebuild the jar with `jar uf` (record which). The patch keeps the render (same transient,
same request-thread work) and removes only the retention, so it isolates the claimed holder.

**Harness** (under `harness/` in this folder; adapted from B17's
[`../cql-row-limit--in-order-by-limit-after-materialization/harness/`](../cql-row-limit--in-order-by-limit-after-materialization/harness/)
and R12's hprof tools [`../monitoring_max_operations+traced-render--slow-query-monitor-stacked/harness/`](../monitoring_max_operations+traced-render--slow-query-monitor-stacked/harness/)):
`setup.sh` (tree copies, `conf-pristine`, compile `B26Load.java`, `C2Sampler.java`, build `tree-iv`), `victim-ctl.sh`
(`ROOT=/mydata/s4/b26`; builds `A`/`IV`; `MAX_HEAP_SIZE` explicit except `CAL-AUTO`; `MAX_DIRECT_MEMORY_SIZE` unset;
scope `b26-<label>-<epoch>`, `MemorySwapMax=0`; GC log `-Xlog:gc*,gc+heap=info,safepoint:file=<run>/gc.log:time,uptime`
(G1 logs humongous region counts); NMT summary; `CASSANDRA_HEAPDUMP_DIR=<run>`), `run-arm.sh`/`batch.sh` (one lifetime per
call, `setsid nohup`, bounded polls), `bigarrays.py` and `retainers.py` from R12 adapted to B26's buckets, `gcwin.py`.

**Instruments (U independent of K).**
- **K:** kept samples: ≤ 256 by construction; observed as the number of `byte[]` of the rendered length (S16:
  16,008,0xx B; S30: 30,015,0xx B) reachable from the `topLocalReadQueryTime` queue in the dump, and as the 11 strings
  nodetool returns in surviving arms; `_SAMPLE` dropped count (`nodetool tpstats`, before/after).
- **U:** (a) JMX sampler `C2Sampler` every 1 s: heap used, G1 old gen used after each GC, NTR/ReadStage active and
  pending, direct `MemoryUsed`; (b) GC log: humongous regions before/after each GC (the per-sample unit here), pause
  share per 60 s (`gcwin.py`); (c) at an OOM: the hprof → `bigarrays.py` (every `byte[]` ≥ 8 MiB by length) and
  `retainers.py` (owner path of each: `TableMetrics$N.queue` → `MinMaxPriorityQueue` → `Sampler$Sample.value`; a
  `samplerExecutor` task lambda; a request thread's `StringBuilder`/locals; `MonitoringTask`; other), plus the first
  `OutOfMemoryError` with thread and stack from `stdout.log`/`system.log`; (d) CAL-RET: `jmap -histo:live` `Total`
  and G1 used at M1 and M2.
- **Completed work:** reads/s and errors per second (client CSV); T and M must deliver comparable reads/s before T's
  OOM (recorded), and I must keep ≥ 80 % of M's reads/s.
- **Validity per lifetime:** `-Xmx`, `MaxDirectMemorySize`, G1 region size 16 MiB (from `gc.log` header); no `-D` or
  yaml change beyond the directories (and the I build's jar sha); `memory.events` `oom_kill` 0; sampler gap ≤ 3 s;
  `debug.log` slow-operation lines = 0 (a lifetime with slow-operation lines is still kept but flagged, and its dump
  must show the monitor's share).

**Predicted response** (before readings).
- VERIFY: as listed; rendered lengths 16.0 / 30.0 MB (± 0.1 %); S16 read p50 20–80 ms, S30 40–150 ms on this x86
  node; ≥ 40 S16 reads/s at c = 4; no slow-operation lines.
- **CAL-RET-8G:** survives; at M1 the queue holds **244** S16 strings: release delta ≈ 3.73 GiB of `byte[]`
  (`jmap` `Total` delta 3.7–3.95 GB; G1 used delta ≈ 3.8–3.9 GiB = 244 humongous regions), ≈ 0 after M2.
- **T-2G ×3:** heap **OOM 3/3** within the 10 s session (≈ 2–4 s after nodetool starts), at ≈ 80–110 kept samples;
  first `OutOfMemoryError` on a request thread (Native-Transport-Requests or ReadStage) inside the render
  (`Hex.bytesToHex` / `AbstractStringBuilder` growth / `String` copy, ≈ 80 %) or on the request decode (≈ 20 %); dump:
  `byte[]` of the rendered length held by the sampler queue ≥ 60 % of the live heap (target 70–85 %), plus ≤ c render
  transients on request threads; `samplerExecutor` tasks ≤ a few.
- **M-2G ×3:** survive 3/3, old gen after GC ≤ 400 MiB, same reads/s as T before its session.
- **I-2G ×3:** survive 3/3, same render work (reads/s within 20 % of T's pre-OOM rate), old gen ≤ 600 MiB; nodetool
  returns 11 strings of 1,024 characters.
- **D-2G (optional):** survive; ≈ 32 regions (≈ 500 MiB) held, released at the next session.
- **CAL-4G:** OOM (≈ 210–240 kept). **CAL-8G (S30):** OOM (≈ 220–245 kept). **CAL-15872M (2 tables):** OOM (≈ 450–490
  kept in total). **BND-15872M-1T:** survives with ≈ 7.6–7.8 GiB held after the session. **CAL-AUTO (4 tables):** OOM.
- A **direct OOM**, a scope kill, or GC service loss (≥ 90 % pause share over 60 s) without a heap OOM is recorded as
  such and does not count toward the heap claim.

**Stopping budget.** T0 = stage-2 start. Per lifetime ≤ 8 min including start (≤ 12 min for ≥ 15,872 MiB heaps,
including the dump); a sweep stops at its first OOM; no escalation beyond the listed rows. **No lifetime starts after
T0 + 3 h 30 min; every process stopped and §3–§4 written by T0 + 4 h 15 min.** Plan: setup + IV build + LOAD 40 min;
VERIFY+PROBE 15 min; CAL-RET 8 min; T/M/I ×3 = 9 × 6 min; CAL-4G, CAL-8G 15 min; CAL-15872M 12 min; optional rows
in the drop order's reverse while time remains; analysis and write-up 45 min.

**Drop order** (first dropped first): `CAL-AUTO` → `BND-15872M-1T` → `D-2G` → REP of CAL-4G/CAL-8G → `CAL-15872M` →
`CAL-8G`. Never dropped: `VERIFY+PROBE`, `CAL-RET-8G`, `T-2G` ×3, `M-2G` ×3, `I-2G` ×3, `CAL-4G`.

**Controls and intervention** (V2, V4). Matched control **M**: the same build, data, read shape, concurrency, warm-up,
budget and timing, with no sampling session (≥ 3 runs). Intervention **I**: a separate build whose only change keeps the
first 1,024 characters of each `LOCAL_READ_TIME` sample (render unchanged), same session command (≥ 3 runs; reads/s
recorded so that an intervention that stopped work is not taken for protection). Optional dose control **D**: capacity
32 on the shipped build (the count dial).

**Verdict rules (pre-registered).**
- **True positive:** T-2G heap OOM ≥ 3/3 (from clean starts), M-2G 0/3, I-2G 0/3, the T dumps show the kept
  `LOCAL_READ_TIME` strings as the largest holder (≥ 50 % of the live heap) and the slow-query monitor idle or < 10 % of
  the dump; CAL-RET's release delta within 25 % of 244 × 16.0 MB. Report the largest failing heap from the upward search.
- **Retry:** T OOMs but the dumps are led by another holder (e.g. `MonitoringTask`, request decode), or M/I also
  OOM; or T survives at 2 GiB while CAL-RET shows the footprint (state what was held and why it did not fill).
- **False positive:** a valid T run reaches ≥ 256 kept S16 samples per table (or its window) at 2 GiB and 4 GiB without
  OOM and CAL-RET shows < 1 GiB held (the strings are not retained as the source reading claims).
- **Blocked:** VERIFY (c) shows a rendered length far from the prediction (e.g. truncated) → stop, record, amend the
  mechanism before readings.

**Cleanup.** Stop every process started (by PID): no `CassandraDaemon`, no `B26Load` or `nodetool` JVM; keep
`/mydata/s4/b26/{template,runs}` (logs; hprofs only as listed) and report the size; never touch
`/mydata/s4/cassandra-base`, other cases' folders or `NODE-LOCK`.

`sha256 of §1–§2 at freeze: a2135596f1dd86a58dc44e5f06ce522ac894e1aeaece70c77abd43f6d253ce26` (computed as `awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-24, America/New_York) · amendments after the freeze: none

## 3. Runs (stage 2)

Freeze hash re-checked at the start of attempt 2 (2026-11-24 15:01 EST): `a2135596…ce26`, matches; no amendment to
§1–§2.

### 3.1 Environment

- **Node `pc91`** (the design's node; no node deviation): x86_64, 32 cores, 125 GiB, kernel `5.15.0-203-generic`, OpenJDK
  `11.0.33`. Attempt 2 acquired `/mydata/s4/NODE-LOCK` at 15:01:46 EST (no lock held, no `java` running) and released it
  at the end. Victim and client on the node (loopback); scope `systemd-run --user --scope -p MemorySwapMax=0`,
  `memory.events` `oom_kill 0` in every lifetime.
- Builds: A `tree/build/apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `570b5249…0176e`; IV (`harness/iv.patch`)
  `tree-iv/…jar` sha256 `3981aecc…9c91`. From `ps`/`gc.log` per lifetime: `-Xmx` as the arm's heap (2G / 4G / 8G /
  15872M; CAL-AUTO unset → **31744M**), `-XX:MaxDirectMemorySize=15872M` (cassandra-env.sh), G1, region 16 MiB,
  `MaxGCPauseMillis=300`, `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError=kill -9`. `yaml.diff`: the five directories
  only (12 diff lines) in every lifetime.
- Harness: [`harness/`](harness/) (`setup.sh`, `victim-ctl.sh`, `run-arm.sh`, `batch.sh` (attempt 1), `batch2.sh`
  (attempt 2), `B26Load.java`, `C2Sampler.java`, `iv.patch`, `bigarrays.py`, `retainers.py`, `hprof_oome_thread.py`,
  `gcwin.py`). Raw data `pc91:/mydata/s4/b26/runs/<label>/`; excerpts [`logs/<label>/`](logs/) (`run-arm.out`,
  `readings.csv`, `samples.csv`, `client.out`, `nodetool.out.head`, `gcwin.txt`, dump summaries); batch outcomes
  `logs/batch1.outcomes.txt`, `logs/batch2.outcomes.txt`.

### 3.2 Deviations (dated)

1. **Two stage-2 sessions (2026-11-24).** Attempt 1 (≈ 11:51–12:55 EST) ran VERIFY+PROBE, CAL-RET, T/M/I ×3, CAL-4G,
   CAL-8G, BND, D ×3 and two all-tables arms with the frozen procedure, then ended before writing §3–§4. Attempt 2 (T0
   15:01:46 EST, a fresh session that did not write the design) audited those lifetimes and kept the valid ones
   (same harness, build, template and procedure), and ran what was missing (items 3–5).
2. **nodetool client heap (attempt 1).** The shipped 128 MiB nodetool heap cannot deserialize the returned top-10
   when each sample is 16–30 MB: nodetool fails with an OOM **in its own JVM** after the server has finished the
   session (`nodetool.err` of CAL-4G, CAL-8G, D, BND). This is client-side only. VERIFY (c) S30 and CAL-RET ran nodetool
   with `MAX_HEAP_SIZE=1g` (the tool's heap, not a server constraint); every other arm used the shipped nodetool.
3. **Dump bucket length (attempt 1 → 2).** `batch.sh` searched the T dumps for 16,008,088-byte arrays (the nodetool
   line width). The real string lengths are **16,008,071 / 16,008,072 B** (pk with 1 or 2 digits) and 30,015,071 /
   30,015,072 B, so attempt 1's `retainers.txt` found 0 targets. Attempt 2 reran `retainers.py` and
   `hprof_oome_thread.py` on the kept T dumps with the real lengths (`logs/T-2G-*/retainers.txt`, `oome-thread.txt`).
4. **All-tables arms invalid in attempt 1, rerun in attempt 2.** `bin/nodetool` expands its arguments unquoted
   (`[ ! $1 ]`, `$ARGS`), so `profileload b26 * 60000` was globbed against the files of the run folder and refused
   ("Invalid arguments"): no session ran (`logs/CAL-15872M-try1-invalid`, `logs/CAL-AUTO-try1-invalid`). Fixed in
   `run-arm.sh` (nodetool runs from an empty directory, 15:20 EST), and both arms were rerun (`batch2.sh`).
5. **REPs (attempt 2).** CAL-4G and CAL-8G each survived once, so they were repeated ×2 as the frozen "+2 REP if time"
   allows.
6. **CAL-RET-8G-try1 invalid (attempt 1).** A harness bug (`nt` called through `timeout`) skipped the second session,
   so M2 = M1. It was rerun as CAL-RET-8G (valid); try1's M1 is kept as a second retention reading.
7. **Duration rule and gate (pre-registered, not amendments).** PROBE: 35–45 sampled S16 reads/s ≥ 25 and 69.9
   unsampled S30 reads/s ≥ 30, so the default 10 s window was kept. p99 with sampling was 164 ms < 400 ms, so c = 4.
8. Dumps of the ≥ 8 GiB lifetimes were deleted after `bigarrays.py` / `retainers.py` / `hprof_oome_thread.py` had run,
   as designed. The three T dumps were deleted after this section was written.

Validity over all valid lifetimes: `debug.log` slow-operation lines **0** and `Query cancelled` **0** (the slow-query
monitor stayed idle); `_SAMPLE` dropped **0** (`tpstats`); sampler gaps ≤ 1 s except the last rows of OOM lifetimes
(the heap-dump pause: 3.1–3.6 s at 2 GiB, 22 s / 80 s at 15,872 / 31,744 MiB).

### 3.3 VERIFY+PROBE (heap 8G; `logs/VERIFY+PROBE/`)

- (a) `one S16 t1`: 10 rows, 200 ms; `one S30 t1`: 10 rows, 232 ms (request ≈ 8.01 / 15.02 MB).
- (b) `-s 2000`: "Capacity (-s) cannot exceed 1024." ✓.
- (c) Render: S16 sample line `SELECT v FROM b26.t1 WHERE pk = 0 AND ck IN (0x00135bf9…` (`render-S16-default.head`).
  The string is 16,008,071 B (pk 0; dumps show 16,008,071 / 16,008,072 B), against the predicted 16,008,100 (−0.0002 %).
  S30: 30,015,071 B, predicted 30,015,100. Not truncated, so the "Blocked" rule does not apply.
- (d) PROBE without sampling: S16 c = 1 30.6 reads/s (p50 31 ms); c = 4 136.9/s (p50 28, p99 49); S30 c = 4 69.9/s
  (p50 55, p99 91); c = 8 108.9/s. S16 c = 4 **with** `-a LOCAL_READ_TIME` for 20 s: 35–45 reads/s, p50 84–109 ms,
  p99 110–310 ms (the render on the request thread), back to ≈ 150/s when sampling ends. Slow-operation lines 0.

### 3.4 Retention after the session (CAL-RET-8G; `logs/CAL-RET-8G/`)

S16, c = 4, `profileload b26 t1` (nodetool 1g). The client was stopped when nodetool returned; after 5 s, M1; then
`profileload b26 t1 1000 -a LOCAL_READ_TIME` (which replaces the queue); after 5 s, M2.

| Reading | `jmap -histo:live` `byte[]` | G1 used (`GC.heap_info`) |
|---|---|---|
| M1 (session finished) | 206,074 arrays, **3,937,747,352 B** | 4,087,102 KiB |
| M2 (after the next session on t1) | 205,831 arrays, **31,773,904 B** | 89,392 KiB |
| **Release delta** | **3,905,973,448 B = 244.0 × 16,008,072 B** (243 arrays fewer) | 3,997,710 KiB (3.81 GiB) |

Predicted 244 strings, ≈ 3.73 GiB of `byte[]` (3.7–3.95 GB) and a G1 delta of 3.8–3.9 GiB: **met** (byte delta within
0.0001 % of 244 × 16,008,072 B). try1's M1 (a second lifetime) also read 3,935,043,176 B of live `byte[]` 6 s after the
session. `int[]` fell by 188 MB between M1 and M2 as well (not attributed; within the 25 % tolerance either way).

### 3.5 Test, control, intervention and dose at 2 GiB (S16, t1, c = 4, session at client second 10)

| Lifetime | Session | Outcome | Reads/s: before / first 4 s of session | Live after full GCs during the session | Dump / end state |
|---|---|---|---|---|---|
| T-2G-1 | `profileload b26 t1` | **heap OOM** at session + 10.1 s (dump start; ≈ 8.5 s after sampling began) | 133 / 71 | 646 → 1,030 → … → 1,931 MiB (49 full GCs, climbing) | 110 rendered strings (90 × 16,008,072 + 20 × 16,008,071 B) = 1,679.3 MiB = **87.7 %** of 1,914.1 MiB |
| T-2G-2 | same | **heap OOM** at session + 9.9 s | 145 / 72 | 666 → … → 1,926 MiB (45, climbing) | 109 strings = 1,664.1 MiB = **87.1 %** of 1,911.2 MiB |
| T-2G-3 | same | **heap OOM** at session + 8.8 s | 150 / 68 | 618 → … → 1,902 MiB (38, climbing) | 108 strings = 1,648.8 MiB = **87.4 %** of 1,887.3 MiB |
| M-2G-1..3 | none (`tpstats`) | survived 3/3 | 142–154 / 118–145 | no full GC besides the diagnostic ones; 86–87 MiB at the end | — |
| I-2G-1..3 (IV) | `profileload b26 t1` | survived 3/3 | 143–154 / 72–76 | **102–198 MiB** (8–9 full GCs each) | 87 MiB at the end; nodetool returned 11 samples of **1,024** characters |
| D-2G-1..3 | `profileload b26 t1 -s 32` | survived 3/3 | 134–154 / 72–76 | 422–726 MiB (12–13 full GCs; render churn plus the 32-sample queue) | 407 MiB at the end = 87 + 20 × 16 MiB (32 − 12 kept after `finishSampling`) |

- **First error (V5)**, the same in all three T dumps (`logs/T-2G-*/oome-thread.txt`): `OutOfMemoryError` ←
  `Arrays.copyOf` ← `AbstractStringBuilder.append` ← `AbstractReadQuery.toCQLString:112` ← `ReadCommand.toCQLString:91`
  ← `ReadExecutionController.addSample:238` ← `close:211` ← `StorageProxy$LocalReadRunnable.runMayThrow:2212` ←
  `SEPWorker.run`. `system.log` shows `java.lang.OutOfMemoryError: Java heap space`, the dump, and `kill -9`.
- **Holder (V3, V5):** `retainers.py` on every rendered-length array in all three T dumps (108–110 per dump): `String.value`
  ← `Sampler$Sample.value` ← `Object[]` ← `MinMaxPriorityQueue.queue` ← `TableMetrics$6.queue` ←
  `TableMetrics.topLocalReadQueryTime` (100 %; no `samplerExecutor` task, request thread or `MonitoringTask` among
  them). The only other arrays ≥ 8 MiB are 1–2 in-flight render `StringBuilder`s (16,406,526 / 16,008,045 B) on a thread
  stack (`ROOT_JAVA_FRAME`) and one 8 MiB `int[]`. K (kept samples) 108–110 ≤ 256; U = 1.65–1.68 GiB, against the
  ≈ 116 B/entry that the count contract implies for write-path items (stage-4 phase-1 reading).
- **Completed work:** before its OOM, T served the same reads/s as I in the session's first 4 s (67.5–72 vs 72–75.5;
  the render, unchanged in I, is what slows both). Over the whole lifetime, I served 11,986–12,932 reads against M's
  11,879–17,512 (≈ 86 % of M's mean). The intervention did not stop work.
- Reads in T's sampling window before the OOM: ≈ 280–320. Nothing was dropped (`_SAMPLE` 0), so K at the OOM was
  set by the heap, not by the cap.

### 3.6 Upward search

| Lifetime | Heap | Shape · tables · c | Session | Outcome | Holder / what stayed held |
|---|---|---|---|---|---|
| CAL-4G, REP1, REP2 | 4,096 MiB | S16 · t1 · 4 | `profileload b26 t1` (default 10 s) | **survived 3/3** (predicted OOM) | live after full GC peaked at **3,758–3,767 MiB (92 %)**, and 390–520 full GCs throttled reads to 2–6/s until the 10 s window closed; **3,479–3,503 MiB (85 % of the heap, ≈ 213 strings) stayed held after the session**; reads afterwards 72–95/s vs 130–142 before; GC pause share ≤ 29 % per 60 s (no service loss) |
| CAL-8G, REP1, REP2 | 8,192 MiB | S30 · t1 · 4 | `profileload b26 t1` (default 10 s) | **survived 3/3** (predicted OOM) | sampled S30 rate 25–28 reads/s, so the window closed first; **5,431–6,039 MiB held after the session** (≈ 167–186 strings × 2 regions) |
| BND-15872M-1T | 15,872 MiB | S30 · t1 · 8 | `profileload b26 t1 60000` | survived (predicted: boundary) | **7,895 MiB held after the session = 87 + 244 × 32 MiB** (predicted 7.6–7.8 GiB) |
| **CAL-15872M** (attempt 2) | 15,872 MiB | S30 · t1, t2 · 8 | `profileload b26 * 60000` | **heap OOM** at session + 20.4 s (dump start) | 451 rendered strings (373 × 30,015,072 + 78 × 30,015,071 B) = 12,909.7 MiB = **97.0 %** of 13,308.8 MiB, under two `topLocalReadQueryTime` queues (t1, t2); first error in the same render frames (`logs/CAL-15872M/oome-thread.txt`). Predicted ≈ 450–490 kept |
| **CAL-AUTO** (attempt 2) | **31,744 MiB** (MAX_HEAP_SIZE unset; cassandra-env.sh) | S30 · t1–t4 · 8 | `profileload b26 * 60000` | **heap OOM** at session + 37.7 s (dump start) | 915 strings (775 + 140) = 26,191.5 MiB = **98.6 %** of 26,557.0 MiB, under four `topLocalReadQueryTime` queues; same render frames. Predicted ≈ 950–1,000 kept |

The ≥ 8 GiB dumps were deleted after analysis (`logs/<label>/bigarrays.txt`, `retainers.txt`, `oome-thread.txt`,
`hprof.ls`).

### 3.7 Predictions against readings

Met: VERIFY render lengths; CAL-RET (244 strings, 3.906 GB); T OOM 3/3 within the 10 s session at 108–110 kept (band
80–110, upper edge); first error in the render (predicted ≈ 80 %, seen 3/3); holder 87 % of the dump (target 70–85 %,
slightly above); M 0/3; I 0/3 with 11 × 1,024-character samples; D 0/3 with ≈ 20 strings held after the session;
BND survives with 244 × 32 MiB held; CAL-15872M OOM; CAL-AUTO OOM. **Not met:** CAL-4G and CAL-8G, predicted to OOM,
survived 3/3 each. The design assumed the window always fills the queue. In fact the default 10 s window closes first:
at 4 GiB the GC thrash near the limit cut reads to a few per second, and at 8 GiB S30 sampled reads run at 25–28/s,
so about 167–225 strings are kept rather than 256. I peaked at 1.6–1.9 GiB occupancy before GC, with live data
≤ 198 MiB after full GCs: render garbage, not retention.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status **`verified-OOM · deployment`** (bypass, accounting mismatch of a count cap).
The condition is that an operator runs `nodetool profileload` (shipped defaults) while large clustering-`IN` reads
arrive.

**Reason.** At every capacity constraint's default (sampler capacity 256, top-K 10, all samplers, 10 s; IN guardrail
off; 16 MiB frame; `samplerExecutor` 1000; slow-query monitor 500 ms / 50), a 2 GiB node OOMed 3/3 about 7–9 s into a
single-table `profileload`. Each S16 read (an 8 MB request) is rendered to a 16,008,07x-byte CQL string, and the
`LOCAL_READ_TIME` `MaxSampler` keeps it as one counted item. The dumps show 108–110 such strings, all reachable only
through `TableMetrics.topLocalReadQueryTime`'s `MinMaxPriorityQueue` (87 % of the heap), with K well under the 256 cap.
The first error was thrown while rendering the next one. The same reads without a session (M), and the same session
on a build that keeps only the first 1,024 characters of each sample while rendering the full string (I), survived
3/3 each with matched work, which isolates the retained strings from the render cost. A 32-sample session (D) also
survived 3/3. The queue outlives the session: 244 strings (3,905,973,448 B, exactly 244 × 16,008,072) stayed live until
the next session on the table replaced them.

The upward search reached OOM at **15,872 MiB** (two tables) and at **31,744 MiB**, the heap cassandra-env.sh picks
for this 125 GiB node, in an all-tables session (`profileload <ks> * 60000`, the documented all-tables form; the
duration is a time window, not a memory bound), with 451 and 915 kept strings at 97–99 % of the dump. A single-table
default 10 s session did not OOM at 4 GiB or 8 GiB (3/3 each): the window closed before the queue filled. It still
left **85 % of a 4 GiB heap** (3.5 GiB) and 5.4–6.0 GiB of 8 GiB held until the next session, with reads 30–50 %
slower afterwards. So the largest failing heap is 2 GiB for the strict-default single-table command and 31,744 MiB
(the node's resolved default heap) for the all-tables command.

**V1–V7.**

| | Evidence |
|---|---|
| V1 Repetition | T-2G 3/3 heap OOM from clean template clones (§3.5) |
| V2 Matched control | M-2G 0/3, same build, data, shape, c, warm-up and budget, no session (§3.5) |
| V3 Measurement | U from dumps (bytes of each kept string, by length and owner path) and from CAL-RET's live-`byte[]` delta; K ≤ 256 by construction, counted as kept strings (108–110; 244 after the session) |
| V4 Intervention | I-2G 0/3 (kept sample cut to 1,024 chars, render unchanged, same session; T-equal reads/s during sampling); D-2G 0/3 as dose |
| V5 Initiating failure | first `OutOfMemoryError` in `ReadExecutionController.addSample` → `toCQLString` on a SEP worker in all three T dumps; holder path as above |
| V6 Default constraints | every capacity constraint at its default in T (the `profileload` defaults, yaml unchanged except directories); only I (patch) and D (`-s 32`) differ |
| V7 Acceptable budget | 2 GiB (standing-rule ideal); OOM also at 15,872 MiB and at the node's own cassandra-env heap of 31,744 MiB (all-tables session) |

**Limits of attribution.** (1) The workload needs a client sending single-partition reads with large clustering-`IN`
lists of large blobs (≈ 8–15 MB requests, inside the 16 MiB frame), and an operator session running at the same time.
`profileload` is an operator diagnostic, and the condition of the result. (2) For the single-table default command,
the endpoint at heaps ≥ 4 GiB depends on the read rate in the 10 s window, which these shapes did not reach. The
retained footprint (≤ 256 × the request size × ≈ 2) is what scales. (3) The `samplerExecutor` backlog (≤ 1000 tasks)
and OC-587's large-partition-key form were not driven (`_SAMPLE` drops 0). (4) The shipped 128 MiB nodetool client
itself fails with an OOM while deserializing the returned samples (client-side, after the server finished). An operator
sees an error, but the server keeps the queue.

**New holders:** none beyond the design (the in-flight render `StringBuilder`s are the transient named in the protection
map). **Not a retry:** nothing named in the design is left untried that the verdict depends on.
