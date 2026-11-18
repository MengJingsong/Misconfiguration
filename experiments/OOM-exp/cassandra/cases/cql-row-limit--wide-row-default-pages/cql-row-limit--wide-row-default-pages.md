# U4 — CQL row limit (page size in rows): default 5,000-row pages of wide rows held twice on heap, read thresholds off  <!-- file: cassandra/cases/cql-row-limit--wide-row-default-pages/cql-row-limit--wide-row-default-pages.md -->

| Field | Value |
|---|---|
| Case ID | `U4` (U = unprotected-accumulation case; README "ID prefixes"); campaign row U4 / P2 |
| From | `OC-27` of the phase 1 OOM candidate list (read-limit cluster; related rows OC-37, OC-39, OC-40, OC-44, OC-48, not tested here) |
| Phase-1 case file | [`cql-row-limit-incrementRowCount-rowsCounted--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/cql-row-limit-incrementRowCount-rowsCounted--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built copy `pc75:/mydata/s4/cassandra-base` |
| Stage 1 (design) | phase-2 OOM agent, stage 1 session (Claude Opus 5.5), 2026-11-17 22:40–23:30 EST; nothing run |
| Stage 2 (verify) | pending (a fresh session) |
| Verdict | `pending` |

## Summary

- **Conclusion:** pending (stage 2).
- **Hypothesis (stage 1):** at shipped defaults a page is bounded in rows only (the driver's default 5,000), the
  read-size thresholds that would bound its bytes are off, and each in-flight page is held twice on the heap
  (replica serialized buffer + coordinator `ResultSet`, ≈ 2.4 × page bytes). With 48 KiB rows a default page is
  234 MiB of payload and ≈ 0.55 GiB held, so about three concurrent paged reads exhaust a 2 GiB heap; nothing sums
  concurrent reads.

## 1. Candidate

**Candidate row (quoted from `phase1-oom-candidates.md`, OC-27):**

> | OC-27 | 2026-11-16 | `cql-row-limit-incrementRowCount-rowsCounted--autonomous` | legacy | [lead list ×4 (blind, E1/E4): budget ledger heap (`read_thresholds_enabled: false`), `default_page_size-cqlgroupbylimits_onclose-rowlimit`, `group-by-row-limit-incrementRowCount-rowsCounted`, `cql-row-limit-incrementRowCount-rowsCounted`; N17; queued as U4] Page sizes, LIMIT and GROUP BY sub-pages count rows, not bytes, and the read-size thresholds are off by default, so a page is held whole as the replica's buffer (`ReadResponse.java:197-201`) and the coordinator's `ResultSet` (`SelectStatement.java:1004`): ≈ 2–2.4 × rows × row size per read (stage 4: 512 × 1 MiB rows → 1,241 MiB), a 5,000-row page of 64 KiB rows ≈ 0.7 GiB, × concurrent reads. | CP-2, CP-12 | picked: U4 |

Related rows of the read-limit cluster (OC-37 range sub-requests, OC-39 replica-filtering protection, OC-40 SAI
top-K, OC-44 unpaged branch, OC-48 tombstone threshold) are **not** arms of this design; they stay separate
candidates.

**Phase-1 constraint and check.** `CQLLimits.rowLimit` (`DataLimits.java:349`), checked by
`if (++rowsCounted >= rowLimit) stop();` (`DataLimits.java:509-510`). Paging replaces `rowLimit` with the client's
page size, also in rows (`DataLimits.java:392-395`). Unit: CQL rows; row width is not bounded by the check.
The case's estimate is `negative` (the count does not cap bytes); its recheck (E1–E4) flags an OOM lead: a whole
page is materialized twice on heap with no byte guard at defaults.

**Phase-1 stage 4 (recheck, pc75, 2026-11-17;
[results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/cql-row-limit-incrementRowCount-rowsCounted--autonomous--recheck-2026-11-17.md)):**
one node, 8 GiB heap, shipped guardrails. One `LIMIT N` read or one N-row first page holds **2.0–2.4 × N × W** of
live heap at the coordinator's end of the read: the replica's serialized `DataOutputBuffer` (1.0–1.4 × N × W; its
capacity grows by doubling to 64 MiB, then by half) and the coordinator's `ResultSet` (1.0 × N × W, fresh copies)
live together (512 × 1 MiB → H_C 1,241 MiB; 51 × from 16 KiB to 1 MiB rows at N = 512; page = LIMIT within 0.1 %).
Positive control: `local_read_size_fail_threshold: 40MiB` turned every larger read into a READ_SIZE failure with
64–65 MiB held. No OOM was tested (single reads inside an 8 GiB heap); concurrency was never applied.

**Contract and default (checked against the pinned source, 2026-11-17).**
- `read_thresholds_enabled = false` (`Config.java:526`); `coordinator_read_size_*`, `local_read_size_*`,
  `row_index_read_size_*` = null (`Config.java:527-532`). The yaml says
  `# read_thresholds_enabled: false # scheduled to be set true in 4.2` (`cassandra.yaml:2015`) and documents the local
  threshold as tracking "the size of the local read (as defined by heap size)" (`:2023-2024`). It was never turned
  on (5.0.9 ships it off). **This is the documented contract this case tests: a heap-size read bound announced as
  becoming default and left off, so at defaults no byte bound applies to a read.**
- `page_size_warn/fail_threshold: -1` (off; `cassandra.yaml:2089-2090`), and it counts rows anyway
  (`SelectStatement.java:517`).
- Drivers page at 5,000 rows by default (Java driver 3.12.1 `QueryOptions.DEFAULT_FETCH_SIZE = 5000`, checked in
  the shaded jar on pc75; Java driver 4.x `basic.request.page-size = 5000`; Python driver `default_fetch_size = 5000`).
- Multiplicity: `native_transport_max_threads: 128` (`Config.java:283`) and `concurrent_reads: 32`
  (`Config.java:179`; a local read runs inline on the request thread when a READ permit is free,
  `AbstractReadExecutor.java:165` → `SEPExecutor.java:218-230`). Nothing sums the bytes of concurrent reads.

**JIRA prior art (read only; nothing posted).** Survey
[`jira-oom-survey.csv`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv):
4304 (*Add bytes-limit clause to queries*, Later), 4743 (*Range slice query causes OOM*, Not A Problem),
5336 (wide-table OOM, Not A Problem: page), 6052 (unpaged huge LIMIT, Duplicate), 4098/16 (old wide-row OOMs,
Fixed), 6492 (*Have server pick query page size by default*, excluded in the survey). JIRA REST checked
2026-11-17 22:50 EST: **CASSANDRA-11745** *Add bytes limit to queries and paging* — Resolved/Fixed in 6.0,
6.0-alpha3, 7.0 (not in 5.0.x; opt-in byte paging); its comment of 2025-10-28 (Nadav Har'El) describes this case:
"page_size=5000 (this is the default in the Python driver), but each row size is pretty big - 100 KB … a single page
of size 500 MB … can cause Cassandra, the client, or both, [to] run out of memory", asking for a hard-coded page cutoff
(not adopted). 6492 still Open. Search `project = CASSANDRA AND (text ~ "fetch size" OR text ~ "page size" OR text ~
"paging") AND (text ~ OOM OR text ~ OutOfMemoryError) AND created >= 2023-01-01`: 10 hits, none on this
shape (18424 tombstone paging, 20052 v5 message size, others unrelated). Campaign plan queries of 2026-11-17 (U4
row) found 16850/16896 (read thresholds, Fixed 4.1, off by default) and no issue on the default being off.
**Verdict: `by design`** for the client-chosen row limit in 5.0.x (4304, 4743, 5336); byte paging exists only in
6.0-alpha3 (11745); **`documented`** for the read thresholds announced as default-on and still off. The case is
therefore an **unprotected configuration** at defaults (the byte control exists and is off), not a bypass and not
a known-fixed bug (GROUP BY sub-pages, fixed by 11745 in 6.0, are not tested here).

**Overlap with verified C2** ([case](../convergence/coordinator_read_size_fail_threshold-concurrent-reads/coordinator_read_size_fail_threshold--concurrent-reads.md)).
C2 S-A (`verified-OOM · deployment`, unprotected configuration) rests on the same switch (read thresholds off) and
the same missing aggregate over concurrent reads, but its holder is **Netty direct memory** (encoded v4 responses of
3.5 MiB pages waiting for **slow readers**, 1,024 outstanding). C2's fast-client arm at defaults (F-A: 3.5 MiB
pages, 256 in flight, 128 processed) was **negative** at a 512 MiB heap (80–83 % STW). U4 differs in the holder and
the dial: **heap** (replica buffer + `ResultSet`), **fast clients**, **few** concurrent reads (≈ 3 at 2 GiB), and
page bytes ≈ 67 × C2's because the page is the driver's default **row** count over wide rows. The shared root cause
(no byte bound across reads at defaults) is stated in both; a U4 result is the heap-side counterpart, reachable with
few clients and no slow reader. A direct-memory OOM in `Message.encode` here would be C2's domain and does not verify
this design (see §2 verdict rules).

## 2. Design solution (stage 1; frozen)

**Mechanism.** Direction: **unprotected configuration** (protocol "Unprotected results"), multiplicity of
concurrent reads; technique note [`default-convergence-playbook.md`](../../../default-convergence-playbook.md) for
the multiplicity sweep at default capacities. A paged `SELECT * FROM t WHERE pk = ?` at the driver's default page of
5,000 rows stops on `rowsCounted` (`DataLimits.java:509-510`), never on bytes. On a single node (coordinator =
replica) the request thread runs the local read inline (`AbstractReadExecutor.java:165`) and serializes the whole
page into one heap `DataOutputBuffer` (`ReadResponse.java:199-201`; growth ×2 up to 64 MiB, then ×1.5,
`DataOutputBuffer.java:158-171`), then builds the full `ResultSetBuilder`/`ResultSet` with fresh value copies
while that buffer's iterator is still open (`SelectStatement.java:427`, `:1004`, `:1014`; paged path `:542`).
`read_thresholds_enabled: false` (`Config.java:526`) means `query.trackWarnings()` (`SelectStatement.java:335`) is
never called, so no local or coordinator byte limit applies. With c concurrent paged reads, held heap ≈ c × 2.4 × page
bytes + baseline, bounded only by 128 request threads.

**Protection map** (fixed before any run).

| Domain | Holder (allocation → release) | Counter K | Limit at default | At the limit |
|---|---|---|---|---|
| Row limit / page size | replica `DataOutputBuffer` (`ReadResponse.java:199`) → released after the coordinator iterates the response; coordinator `ResultSet` (`SelectStatement.java:1004-1014`) → released after `Message.encode` | `rowsCounted` (rows) | 5,000 rows (driver default page); `NO_LIMIT` server side | stops the page at 5,000 rows; no byte bound (by design) |
| Read-size thresholds | same holders (local: `ReadCommand` size tracking of `row.unsharedHeapSize()`; coordinator: `ResultSetBuilder` value bytes) | bytes | **off** (`read_thresholds_enabled: false`, thresholds null) | nothing → **unprotected configuration** |
| Page-size guardrail | — | rows | −1 (off) | nothing |
| Concurrency | per request: one page per in-flight read | request threads; READ permits | 128 NTR threads; 32 READ permits (inline local read) | queues; no byte sum across reads |
| Native in-flight request bytes | request body (small SELECT) | request bytes | heap/10, per IP heap/40 | does not cover response memory |
| Encoded response (ledgered, not claimed) | Netty direct buffer from `Message.encode` (`Message.java:367`/`:392`, `CBUtil.allocator`) until flushed | — | `MaxDirectMemorySize` | direct OOM (C2's domain) |
| Baseline | memtable heap pool (H/4, empty: read-only workload), key cache (min(5 % H, 100 MiB)), chunk cache (direct, min(512 MiB, H/4)) | own counters | defaults | evict / flush |

**Configuration and budget audit.**
- Source/build: `pc75:/mydata/s4/cassandra-base` (cassandra-5.0.9, `build/apache-cassandra-5.0.9-SNAPSHOT.jar`,
  built 2026-11-17 for the stage-4 recheck), copied to `/mydata/u4/tree`. JDK 11.0.33 (G1, shipped
  `jvm11-server.options`: `G1HeapRegionSize=16m`, `MaxGCPauseMillis=300`; `HeapDumpOnOutOfMemoryError` from
  `jvm-server.options:120`). Ubuntu 22.04, kernel 5.15.0-203, cgroup v2 (user delegation: memory, pids).
- **Every capacity constraint at its shipped default** (V6): read thresholds off, page-size guardrail off, row limit
  = driver default page 5,000, `native_transport_max_threads` 128, `concurrent_reads` 32, memtable/caches default,
  `num_tokens: 16`, `read_request_timeout` 5 s, `native_transport_timeout` 12 s (not raised). The only constraint
  changed is in the intervention arm I (below).
- `cassandra.yaml` diff from the shipped file (environment only): `data_file_directories`, `commitlog_directory`,
  `hints_directory`, `saved_caches_directory`, `cdc_raw_directory` under `/mydata/u4/node/`. Addresses stay at the
  shipped `localhost` (client on the same node).
- **Budgets** (V7; standing rule: heap and direct ≥ 512 MiB meet V7, 2 GiB ideal; record resolved values):
  - **Primary: heap 2 GiB** (`MAX_HEAP_SIZE=2G`), direct **resolved by `cassandra-env.sh`** with the hand-set heap:
    on pc75 (125 GiB RAM) ½ RAM > 15,872 MiB, so `MaxDirectMemorySize = 7936M` (`cassandra-env.sh:59-64`, `MAX_DIRECT_MEMORY_SIZE`
    left unset). 2 GiB is what `cassandra-env.sh` resolves for a 4 GiB-RAM node and the ideal budget; a hand-set
    2 GiB heap on a large node is common practice (C2 used the same pair). Record `-Xmx`/`-XX:MaxDirectMemorySize`
    from the process command line.
  - **Upward search** (same node, node classes `cassandra-env.sh` resolves): heap 4 GiB / direct 2048 MiB (8 GiB
    node), 8 GiB / 4096 MiB (16 GiB node), 15,872 MiB / 7,936 MiB (pc75's own resolution, the largest default heap).
  - **Optional E2:** heap 2 GiB / direct 1024 MiB (the full resolution of a 4 GiB node), to see which domain fails first.
  - **No container budget.** Each process runs in `systemd-run --user --scope -p MemoryMax=<heap + direct + 8G>
    -p MemorySwapMax=0` for isolation only (swap off). The scope is never the budget: a scope `oom_kill` makes the run
    **invalid**; record `memory.events` at the end of every lifetime.

**Ceiling arithmetic.** Workload: W = 49,152 B (48 KiB) per value, N = 5,000 rows per page → payload
N × W = 245,760,000 B = **234.4 MiB** per page. Held per in-flight page (stage-4 model, 2.0–2.4 ×): replica buffer
≈ 325 MiB (growth from ≈ 48 MiB by doubling to ≈ 96 MiB, then ×1.5: 144 → 217 → 325 MiB; estimate) + `ResultSet`
234 MiB ≈ **0.55 GiB**, plus a transient ≈ 0.53 GiB (old + new buffer) during the last growth. No contract capacity
bounds this: Σ contract capacities is unbounded; the implicit ceiling is 128 threads × 0.55 GiB ≈ 70 GiB. Baseline at
2 GiB (read-only, memtables empty): ≈ 0.15–0.3 GiB. Predicted smallest failing concurrency
c_fail ≈ ⌈(H − 0.3 GiB − 0.2 GiB transient) / 0.55 GiB⌉: **2 GiB → 3 (band 2–4)**; 4 GiB → 7 (6–8);
8 GiB → 14 (13–16); 15,872 MiB → 28 (26–32). Humongous objects (≥ 8 MiB at 16 MiB regions) need contiguous
regions, which can lower c_fail. Direct per in-flight encoded page ≈ 234 MiB (drained fast by a local client):
at 7,936 MiB direct it would take ≈ 30 encoded pages at once, so the heap is predicted to fail first.
*Client frame limit:* the Java driver 3.12.1 rejects response frames > 256 MiB
(`Frame$Decoder$DecoderForStreamIdSize.MAX_FRAME_LENGTH` = 256 × 1024 × 1024, system property
`com.datastax.driver.NATIVE_TRANSPORT_MAX_FRAME_SIZE_IN_MB`, checked with `javap` on the jar); a frame here is
5,000 × (8 + 8 + 4 + 49,152) B + metadata ≈ 234.5 MiB, below it. This is why W is 48 KiB, not 64 KiB.

**Workload and environment.**
- Node `pc75` only (x86_64, Xeon E5-2660 v2, 40 cores, 125 GiB RAM, 8 GiB swap excluded per scope, `/mydata`
  713 GiB free; checked 2026-11-17 22:42 EST read-only: no java process, load 0.00; `/mydata/s4/rowlim-rc/` is the
  stage-4 run's evidence — **do not touch it**). Victim = one Cassandra node; client = one Java-driver JVM on the
  same node (loopback; fast client).
- Schema: `CREATE KEYSPACE u4 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
  `CREATE TABLE u4.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))` with **default table options** (LZ4,
  STCS, `caching` keys ALL).
- Data: **16 partitions (pk 0–15) × 5,000 rows (ck 0–4999) × 49,152 random bytes** (Java `Random(pk0).nextBytes`),
  ≈ 3.75 GiB; one 5,000-row page = one whole partition (one page per read, as in C2Load).
  Each write is 48 KiB (far below `max_mutation_size` 16 MiB and `max_value_size` 256 MiB).
- Load once (lifetime `LOAD`, heap 8G, not a reading): schema, load at 32 concurrent async inserts (CL ONE),
  `nodetool flush u4`, `nodetool compact u4` (wait), `nodetool drain`, SIGTERM; then
  `cp -a /mydata/u4/node /mydata/u4/template` and `rm -rf /mydata/u4/template/saved_caches/*`. **Every measured
  lifetime starts from a fresh `cp -a` of the template** (no hard links: sstable component files can be rewritten
  in place) so data state is identical.
- Read client: closed loop, c reads in flight over 16 connections, protocol **v4**, CL ONE, prepared
  `SELECT * FROM u4.t WHERE pk = ?` with random pk in [0,16) (seed 42), **fetch size 5,000** (driver default;
  set explicitly), first page only, values counted and dropped. Steps are `c:secs` lists (C2Load format).
- **Arms and conditions** (labels; `steps` as `c:secs`):

| Label | Arm | Heap / direct | Fetch | Steps | Reps |
|---|---|---|---|---|---|
| `IC` instrument check (not a reading) | A | 2G / auto | 5000 | `1:30` | 1 |
| `CAL-2G` calibration sweep | A | 2G / auto (7936M) | 5000 | `1:60,2:60,3:60,4:60,6:60,8:60` | 1 |
| `T-2G-1..3` test | A | 2G / auto | 5000 | `1:20,<c_T>:160` | 3 |
| `M-2G-1..3` matched control | A | 2G / auto | **500** | `1:20,<c_T>:160` | 3 |
| `I-2G-1..3` intervention | **I** | 2G / auto | 5000 | `1:20,<c_T>:160` | 3 |
| `CAL-4G` budget search | A | 4G / 2048M | 5000 | `4:60,6:60,7:60,8:60,10:60,12:60,16:60` | 1 |
| `CAL-8G` | A | 8G / 4096M | 5000 | `10:60,12:60,14:60,16:60,20:60,24:60` | 1 |
| `CAL-auto` | A | 15872M / 7936M | 5000 | `20:60,24:60,28:60,32:60,40:60,48:60` | 1 |
| `REP-<H>-1..2` repeats at the largest failing heap | A | that heap | 5000 | warm-up, then its failing c for 160 s | 2 (if time) |
| `E2-2G1G-1..3` optional | A | 2G / 1024M | 5000 | `1:20,<c_T>:160` | ≤ 3 (if time) |

  Arm **A** = shipped defaults. Arm **I** = A plus `read_thresholds_enabled: true` and
  `local_read_size_fail_threshold: 64MiB` (no other threshold; 64 MiB ≈ 1.6 × the stage-4 control value, ≈ 1,300 rows
  of 48 KiB). **c_T** = the smallest c at which `CAL-2G` reached an OOM. If `CAL-2G` survives up to c = 8, run one
  extra sweep `CAL-2G-x` with `12:60,16:60,24:60,32:60` before deciding (verdict rules). Each sweep stops at the
  first OOM. The budget-search sweeps start at their predicted band and are extended by one step if no OOM.

**Harness** (build under `harness/` in this folder; adapt the verified C2 harness,
[`../convergence/coordinator_read_size_fail_threshold-concurrent-reads/harness/`](../convergence/coordinator_read_size_fail_threshold-concurrent-reads/harness/),
which ran the same driver and samplers):
1. `setup.sh`: `mkdir -p /mydata/u4`; `cp -a /mydata/s4/cassandra-base /mydata/u4/tree`; `cp -a /mydata/u4/tree/conf
   /mydata/u4/conf-pristine`; compile the client and sampler into `/mydata/u4/cls`.
2. `victim-ctl.sh` (from C2's): `ROOT=/mydata/u4`, `BUILD=/mydata/u4/tree`, pristine conf
   `/mydata/u4/conf-pristine`; no address edits; per lifetime `rm -rf $ROOT/node && cp -a $ROOT/template $ROOT/node`
   (`LOAD` creates an empty node dir instead); arms `A` / `I`; launch `bin/cassandra -f` under
   `systemd-run --user --scope --unit=u4-<label> -p MemoryMax=<heap+direct+8G> -p MemorySwapMax=0` with
   `setsid nohup … < /dev/null`, `MAX_HEAP_SIZE`, `MAX_DIRECT_MEMORY_SIZE` (unset for "auto"),
   `CASSANDRA_HEAPDUMP_DIR=<run dir>`, `JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -Xlog:gc=info,safepoint=info:file=<run>/gc.log:time,uptime,level,tags"`;
   save `yaml.diff`, `run.meta` (label, arm, heap, direct, jar sha256, resolved `-Xmx`/`MaxDirectMemorySize` from `ps`).
3. `U4Load.java` (from `C2Load.java`): keyspace/table above; `load <host> <parts> <rows> <bytes> <pk0>`;
   `one <host> <pk> <fetch>` prints rows and value bytes; `run <host> <conns> <steps> <parts> <fetch>` (fetch size an
   argument; `SELECT *`); per-second CSV as C2Load plus `rowsLastRead`. `load.sh`: classpath
   `/mydata/u4/tree/build/lib/jars/{cassandra-driver-core-3.12.1-shaded,guava-32.0.1-jre,metrics-core-4.2.28}.jar`
   plus `/mydata/u4/tree/lib/*`; client JVM `-Xmx16g -XX:MaxDirectMemorySize=16g` in its own scope
   `u4-client-<label>` (`MemoryMax=40G`, `MemorySwapMax=0`); default frame limit left as is.
4. `C2Sampler.java` (copied unchanged): JMX 1 s — heap used, G1 old-gen post-GC usage, NTR and ReadStage
   active/pending, `java.nio` direct.
5. `run-arm.sh <label> <A|I> <heap|auto> <direct|auto> <fetch> <steps>`: refuse if a `CassandraDaemon` runs; clone;
   start; wait ready (`Starting listening for CQL clients`); sampler; every 10 s `jcmd <pid> VM.native_memory summary`
   and `RssAnon`; run the client; on client exit or JVM death record outcome (`OutOfMemoryError` lines from
   `stdout.log`/`system.log`, hprof present, scope `memory.events`); stop a surviving node with `nodetool drain` and
   SIGTERM by PID; copy small files to `logs/<label>/` (client CSV, samples, `gcwin.py` output, `hprofhist`/`hprofstacks`
   summaries, `run.meta`, `yaml.diff`, `memory.events`, first OOM lines); full logs and hprofs stay in
   `pc75:/mydata/u4/runs/<label>/`. Launch each lifetime as a background job and poll with bounded waits.
6. `gcwin.py`, `hprofhist.py`, `hprofstacks.py`, `summarize.py` from C2; `hprofhist.py` adds two buckets:
   `byte[]` ≥ 128 MiB (replica buffers) and `byte[]` of 49,152 ± 64 B (`ResultSet` value copies; count ÷ 5,000 =
   coordinator pages held).

**Instruments (U independent of K).** K = rows per page (client `rowsLastRead` = 5,000; arm I: READ_SIZE failures
and the bytes in the error message). U = (a) G1 old-gen post-GC usage and heap used (1 s JMX); (b) at an OOM, the
hprof written by `HeapDumpOnOutOfMemoryError`: count and bytes of `byte[]` ≥ 128 MiB and of 48 KiB `byte[]`, and
thread stacks inside `LocalDataResponse.build`, `DataOutputBuffer.expandToFit`, `ResultSetBuilder`; (c) in surviving
T/M/I lifetimes one `jcmd <pid> GC.class_histogram` at load second 150 (same buckets; intrusive, so only once and
only in surviving arms); (d) GC log → STW fraction per 60 s window (`gcwin.py`); (e) NTR/ReadStage active (the
load actually reached c), client in-flight, reads/s, MB/s, errors; (f) NMT and `RssAnon` every 10 s; JVM direct
(`java.nio`) for the ledger.

**Predicted response.**
- `IC`: 5,000 rows per read, 245,760,000 value bytes per read; samples and GC log present.
- `CAL-2G`: survives c = 1 and 2 (c = 2 with heavy GC); **Java heap OOM at c = 3** (band 2–4) within its 60 s step;
  NTR active ≈ c before death; old post-GC rises by ≈ 0.5–0.6 GiB per step of c.
- `T-2G`: Java heap OOM 3/3 within 160 s at c_T. First error `java.lang.OutOfMemoryError: Java heap space` on a
  request thread in `DataOutputBuffer.expandToFit` (replica serialization) or in the `ResultSet` value copy; hprof
  with ≥ c_T − 1 page-sized `byte[]` (≥ 128 MiB) and/or ≥ (c_T − 1) × 5,000 48 KiB `byte[]`; then Cassandra's heap
  dump and kill.
- `M-2G` (fetch 500, payload 23.4 MiB per page, held ≈ 56 MiB): survives 0/3 OOM; old post-GC < 1 GiB; STW < 50 %.
- `I-2G`: survives 0/3 OOM; nearly every read fails with READ_SIZE (`ReadFailureException`, "loaded over … bytes")
  after ≈ 64 MiB counted; held per aborted read ≈ 100 MiB; useful work ≈ 0 reads/s (recorded: the bound protects by
  rejecting; the client-side remedy is M's smaller page).
- Budget search: OOM at each heap near its predicted c band; largest failing heap predicted **15,872 MiB at c ≈ 28**.
- Direct (`java.nio`/NMT Other) stays far below 7,936 MiB; no scope `oom_kill`.

**Stopping budget and time plan** (deadline: everything stopped and §3–§4 written by **02:30 EST, 2026-11-18**;
pc75's clock is MST = EST − 2 h). Planned durations from the stage-2 start S (expected ≈ 23:30 EST):
setup + harness S → S+30 min; `LOAD` + template + `IC` → S+50; `CAL-2G` (≤ 8 min) → S+60; `T-2G` ×3 (≈ 5 min each) →
S+75; `M-2G` ×3 → S+90; `I-2G` ×3 → S+105; budget search `CAL-4G`, `CAL-8G`, `CAL-auto` (≈ 9 min each, in that
order) → S+135; `REP-*` and `E2` only if time remains. **Hard limits:** no new lifetime starts after 01:55 EST unless
it ends by 02:10; all processes stopped by 02:15 EST; if S is later than 00:15 EST, skip `CAL-8G`, `REP-*` and `E2`.
Per lifetime: load ≤ 180 s (`T`/`M`/`I`), ≤ 7 × 60 s (sweeps); client read timeout 120 s; a node not ready in
120 s is an invalid lifetime (retry once). No escalation after an OOM beyond the planned list.

**Controls and intervention.**
- **Matched control `M-2G` ×3:** same build, budget, data, connections, c_T and client; only the client page size
  is lowered to 500 rows (10 × fewer bytes per page). Shows the holder is page bytes, not the request count.
  The `CAL-2G` step below c_T is reported as the multiplicity boundary (one run).
- **Intervention `I-2G` ×3:** the T workload with the byte control that is off by default switched on
  (`read_thresholds_enabled: true`, `local_read_size_fail_threshold: 64MiB`). Removing the OOM attributes it to the
  missing byte bound. Record throughput and rejection rate (an intervention that stops useful work is reported as such).

**Verdict rules (stated before readings).**
- **true positive:** `T-2G` heap OOM in ≥ 3 runs (n/N stated; if 2/3, add up to 2 more repetitions), `M-2G` 0/3,
  `I-2G` 0/3, dumps show the claimed holders (replica buffers and/or `ResultSet` copies of ≈ c_T pages) →
  `verified-OOM · deployment`, **unprotected configuration**, largest failing budget from the search.
- **retry:** OOM only with E2's 1 GiB direct or only in `Message.encode`/Netty (C2's domain); service loss (≥ 90 % STW
  over ≥ 60 s) without OOM (`verified-gap`); OOM < 3 runs after 5 repetitions; time ran out before V1/V2/V4.
- **false positive:** `CAL-2G` and `CAL-2G-x` reach c = 32 with NTR active ≥ c (load reached) and old post-GC stays
  below 90 % of the heap with no OOM, and the measured held set per in-flight page shows why (e.g. pages do not
  overlap), with no named factor left untried.
- **invalid lifetime:** client JVM OOM or frame-size error, scope `oom_kill`, workload not started, rows per read
  ≠ 5,000 (≠ 500 in M); fix and rerun, recorded as a deviation.
- Cleanup: stop every process started; keep `/mydata/u4/runs/` (raw logs, hprofs) and the template; report what is
  left. Delete nothing in `/mydata/s4/`.

`sha256 of §1–§2 at freeze: 3d17b678d577ae6c2f1fe169095f42063239cdc9b853677bc7d1443a97ec527c` · computed over the lines from `## 1. Candidate` through the line before this one (`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum`) · amendments after the freeze: dated, with reason, below this line.

## 3. Runs (stage 2)

pending

## 4. Conclusion (stage 2)

pending
