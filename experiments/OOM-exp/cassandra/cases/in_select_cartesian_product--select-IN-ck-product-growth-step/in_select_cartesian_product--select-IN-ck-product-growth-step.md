# R14 (retry of U5) — in_select_cartesian_product: one SELECT with c1 IN × c2 IN fails the product list's growth step on an 8 GiB heap  <!-- file: cassandra/cases/in_select_cartesian_product--select-IN-ck-product-growth-step/in_select_cartesian_product--select-IN-ck-product-growth-step.md -->

| Field | Value |
|---|---|
| Case ID | `R14` (R = a new attempt at an earlier case; README "ID prefixes"). Direction of the design: unprotected configuration / unprotected accumulation, as U5 |
| From | retry of `U5` (row U5 of [`phase2-retry-list.md`](../../phase2-retry-list.md)); U5's cluster `OC-412` (primary), `OC-351`, `OC-352`, `OC-365`, `OC-276` |
| Phase-1 case file | [`no_constraint-handleinfilter-restriction_position--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/no_constraint-handleinfilter-restriction_position--autonomous.md) (OC-412); for the others see U5 §1 |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9). Node build `pc91:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`, x86_64 build; shipped `conf/cassandra.yaml` md5 `714ee9bf58b3bc1710377ac16bcbba03`); `MultiCBuilder.java`, `ClusteringColumnRestrictions.java`, `BTree.java`, `SelectStatement.java` in that tree are byte-identical (md5) to the pinned source |
| Stage 1 (design) | phase-2 OOM agent, stage-1 session, 2026-11-20 10:30–11:50 America/New_York; nothing run (pc91 checked read-only) |
| Stage 2 (verify) | fresh phase-2 OOM-agent session on `pc91`, 2026-11-20 10:42–12:30 EST (lifetimes 10:45–11:47; parsers to 12:22); freeze hash matched; no amendment |
| Verdict | **true positive** — `verified-OOM · deployment` (unprotected configuration); CK at 8192M: OOM 3/3 counted, **strict request-thread 3/3**; control 0/3; intervention 3/3; largest failing heap tested 28672M (3/3) |

## Summary

- **Conclusion:** **true positive** (`verified-OOM · deployment`, unprotected configuration). On x86 (`pc91`), one prepared
  `SELECT … WHERE pk = 0 AND c1 IN ? AND c2 IN ?` with 160 × 1,600,000 bound values (12.8 MB request) ran an 8 GiB
  Cassandra 5.0.9 node at shipped defaults out of heap **3/3** (`Java heap space` at +37–47 s, then heap dump and
  `kill -9`); in all three the **request (NTR) thread itself threw** (strict count 3/3) in `ArrayList.grow` ←
  `MultiCBuilder.addEachElementToAll:359`, and the dump shows the product (157.7M `ArrayList` + 157.7M `Object[2]` + the
  602 MiB backing array) as ≈ 97 % of the heap. The matched control (same bytes, 1 × 1,600,159) returned its row 3/3; a
  pre-allocation count check rejected the request 3/3 and stopped the OOM. The same request shape also threw on the
  request thread at 12, 18 and 28 GiB (28672M: 3/3), each at the growth step the step-window model predicted.
- **Root cause (confirmed by stage 2; the stage-1 text follows):** `c1 IN ? AND c2 IN ?` on two clustering columns is
  expanded by `MultiCBuilder` into the full cartesian product on the request thread (one `ArrayList` + `Object[2]` per
  combination, in one `ArrayList` `elementsList`), before any limit runs. The only control on that count,
  `in_select_cartesian_product`, ships disabled (−1) and is skipped for every client under the shipped
  `AllowAllAuthenticator`. U5 showed the mechanism but its deciding CK form mostly ended in a G1 full-GC spiral at 2 GiB
  instead of a request-thread OOM. This design explains why (the "step window" arithmetic in §2: a clean OOM comes
  only when the heap ceiling falls between the live size at an `elementsList` growth step and that size plus the new
  backing array; 2 GiB lies between two windows, 8 GiB inside one) and re-runs CK where the OOM is predicted to be the
  request thread's own failed humongous allocation: 8 GiB heap, `c1 IN (160) × c2 IN (1,600,000)`, with matched
  control and intervention ×3 there. Stage 2 confirmed the model on x86 at four budgets (b = 211–226 MiB).

## 1. Candidate

**The retry row (quoted from [`phase2-retry-list.md`](../../phase2-retry-list.md), Status as it stands at stage 1).**

> | [U5](cases/in_select_cartesian_product--select-IN-product-key-build/in_select_cartesian_product--select-IN-product-key-build.md) (from OC-412 cluster) | 2026-11-18 | The IN × IN product is uncounted at defaults (controls ≤ 313 MiB, pre-allocation check 6/6). PK form `verified-OOM` 3/3 at 2 GiB, but the deciding CK condition (64M combinations, 2 GiB) mostly ended in a G1 spiral: OOM on the request thread 2/5 against the frozen ≥ 3 (`verified-gap · service-loss`); 8 GiB gave OOM 3/3 without control or intervention | Pre-register CK at 8 GiB, c1 IN (160) × c2 IN (1,600,000) (OOM 3/3 here), with matched control and intervention ×3 there and the OOM thread kept attributable; or 2 GiB at 32M combinations; state in the rule whether an OOM on another thread counts when the dump shows the holder; keep PK | picked again: R14 (2026-11-20) |

**The earlier case and its verdict.** [U5 — `in_select_cartesian_product--select-IN-product-key-build`](../in_select_cartesian_product--select-IN-product-key-build/in_select_cartesian_product--select-IN-product-key-build.md)
(stage 2 on `ms0617`, **aarch64**, 2026-11-18): **`retry`**, confirmed by the owner the same day ("U5 stays `retry` under
the frozen 'OOM on the request thread' rule"; root `HANDOFF.md`, wave 4). What it showed (its §3–§4):

| Condition (U5) | Result |
|---|---|
| CK, 2 GiB, `pk = 0 AND c1 IN (64) AND c2 IN (1,000,000)` (64M) | heap full 5/5; `Java heap space` thrown inside 240 s in 4/5, on the request (NTR) thread in the build frames in **2/5** (`T-CK-2G-3` +22 s at the `elementsList` 31.15M → 46.7M growth; `T-CK-2G-4` ≈ +103 s); a table-metrics task threw in `T-CK-2G-5` (dump: the product ≈ 94 % of the heap); thread unknown in `T-CK-2G-1` (dump never ran); nothing thrown in `T-CK-2G-2`. JVM exit in the window 1/5; service loss (≥ 90 % STW ≥ 60 s) 4/5 → `verified-gap · service-loss · deployment` |
| CK matched control (1 × 1,000,063, same bytes) | 1 row 3/3, old gen ≤ 313 MiB |
| CK intervention (pre-allocation check, `-Du5.max_in_product=1100000`) | rejected 3/3 in 0.4 s; `IM` 1 row |
| CK budget search | **8192M, 160 × 1,600,000 (256M): heap OOM 3/3** at +158–160 s (`CAL-CK-8G`, `REP-8192M-1,2`), each after `Pause Full (G1 Humongous Allocation) 8016M->8014M`, `8014M->8014M(8192M)` with `Humongous regions: 39->39`, then `ReportJavaOutOfMemory`, JVM exit; no dump (disabled > 4096M by design), no control or intervention at 8 GiB. 4096M (128M), 15872M (320M), 31744M auto (640M): spiral, no OOM in 420–900 s |
| CK boundary at 2 GiB | 4M, 8M answer (read timeout); 16M builds, then OOM in the request-exception **logger** (ledgered other holder); 24M spiral; 32M OOM +36 s at the `BTree.Builder` array doubling in `build()` (1/1) |
| PK, 2 GiB, `a IN (16) AND b IN (500,000)` (8M keys) | **`verified-OOM · deployment`**: OOM 3/3 (+1/1 CAL) in `SinglePartitionReadCommand.create` ← `SelectStatement.getSliceCommands`; control 0/3; intervention rejected 3/3 |
| Arm G (guardrail on, ordinary user; diagnostic) | late enforcement: 16M rejected only after its product was built (1.27 GiB); 64M OOM 2/2 before the check |

**Phase-1 case files and stage 4** (from U5 §1, unchanged). OC-412: `ClusteringColumnRestrictions.handleInFilter`
(`:226-229`), estimate `negative` (planning metadata, caps nothing), no stage 4. OC-351 / OC-365:
`QueryProcessor.java:251` (`validateKey`), `negative`, no stage 4. OC-352: `Validation.java:47`, `negative`, no stage 4.
OC-276: `BatchStatement.java:340` (`batch_size_warn_threshold`), `negative`; stage 4 (2026-10-26) unit Refuted / cluster
Not confirmed (the warn threshold does not cap; no IN product measured). None names the cartesian product as the
constraint; the control actually involved is the guardrail pair `in_select_cartesian_product_*` /
`partition_keys_in_select_*` (both −1). The five cluster rows of `phase1-oom-candidates.md` now read `retry (U5)`.

**What R14 decides.** OC-412 (CK form, primary): yes, by the CK condition below. OC-351 and the product form of OC-365:
already `verified-OOM · deployment` by U5's PK condition (aarch64); R14 keeps that result and only replicates PK on x86
if time remains (P3, not deciding). OC-352 / OC-276 (write-side holders): not tested (U7 and a batch case), as in U5.

**JIRA prior art (read only; nothing posted).**
- Survey [`jira-oom-survey.csv`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv),
  re-read 2026-11-20: CASSANDRA-15250 *Large cartesian produces in IN queries cause the server to run out of memory*
  (kept, Unresolved, `unprotected:accumulation`, "5.0.9 guardrail in_select_cartesian_product … off"); CASSANDRA-9454
  *Log WARN on Multi Partition IN clause Queries* (Duplicate; guardrail off by default); CASSANDRA-12420 (excluded:
  duplicate IN keys loop, client-side).
- JIRA REST, 2026-11-20 10:35 EST: **CASSANDRA-15250 Open**, no resolution, no fix version, last updated 2019-07-27;
  CASSANDRA-17187 *Guardrail for SELECT IN terms and their cartesian product* Resolved / Fixed 4.1-alpha1, 4.1 (the
  shipped-off guardrail). U5's search `project = CASSANDRA AND (text ~ "cartesian" OR summary ~ "IN clause" OR summary ~
  "IN query" OR summary ~ "IN restrictions") AND (text ~ "memory" OR text ~ "OOM" OR text ~ "OutOfMemoryError" OR text ~
  "guardrail")`: still 79 hits, 0 updated since 2026-11-18. New search `project = CASSANDRA AND (text ~ "MultiCBuilder" OR
  text ~ "elementsList" OR text ~ "in_select_cartesian_product")`: 29 hits; the memory-related ones are allocation trims
  (CASSANDRA-20129 *Restore optimization in MultiCBuilder around building one clustering*, fix 6.0; CASSANDRA-21351
  *Reduce memory allocations in SelectStatement.getQuery*, 6.0-alpha2/7.0; CASSANDRA-19679, 6.0) and the CASSANDRA-19341
  refactor; none bounds the product or moves the guard before the allocation.
- **Verdict: `known-open`** (15250, the same shape on a partition key) with the mitigating guardrail **`documented`** as
  opt-in and off by default. Not known-fixed, so R14 is not a positive control.

## 2. Design solution (stage 1; frozen)

**Mechanism.** Direction: **unprotected configuration** (the control exists and ships disabled, and is skipped for
non-ordinary users) with an **unprotected accumulation** shape (one request's own expansion). Technique notes:
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md) for the boundary and budget search at default
capacities. A prepared `SELECT * FROM u5.ck WHERE pk = ? AND c1 IN ? AND c2 IN ?` with bound int lists of k1 and k2
values reaches `SelectStatement.getSliceCommands:725` → `makeClusteringIndexFilter:835` → `getRequestedRows:977` →
`StatementRestrictions.getClusteringColumns:942` → `ClusteringColumnRestrictions.valuesAsClustering:105-119` →
`SingleColumnRestriction$INRestriction.appendTo:241` → `MultiCBuilder$MultiClusteringBuilder.addEachElementToAll:339-372`
on the `Native-Transport-Requests` (NTR) thread. For c2, for each of the k1 old composites it does
`elementsList.remove(0)` (`:354`, O(n) shift) and k2 times `new ArrayList<>(oldComposite)` + `elementsList.add` (`:358-359`)
+ `newComposite.add(value)` (`:368`), so `elementsList` grows to N = k1 × k2 entries; `build()` (`:419-437`) then copies
them into a `BTreeSet<Clustering>` (`BTree$Builder.add:1537-1539`, array doubling from 16). The guard
(`ClusteringColumnRestrictions.java:112-113`) is off at defaults and, when on, runs after each column's product exists.
Nothing between the request bytes (≤ 16 MiB) and the N per-combination objects is counted.

**Why U5's CK form spiralled at 2 GiB and why 8 GiB throws (the step window; derived for this design from U5's logs).**
Live bytes per composite during the c2 loop: `ArrayList` 24 B + `Object[2]` 24 B = **48 B** (compressed oops,
compressed class pointers; the `Object[1]` made by the copy constructor is garbage at once), plus 4 B per slot of
`elementsList`'s backing `Object[]`. That array grows ×1.5 (JDK 11 `ArrayList.grow`: `old + (old >> 1)`) from the
default 10, so its capacities are fixed whatever k1 is: …, 31,151,587, 46,727,380, 70,091,070, 105,136,605,
**157,704,907**, **236,557,360**, **354,836,040**, **532,254,060**, 798,381,090. At a growth step from capacity s the
heap holds L(s) = 48·s + 4·s + b (b = everything else live: baseline, the 1.6M deserialized bound values, young
leftovers) and must find a new **humongous, contiguous** array of 6·s bytes. So, for heap H:
- **throw at the step** (the NTR thread's own allocation fails in `ArrayList.grow` ← `elementsList.add`,
  `addEachElementToAll:359`) when L(s) < H < L(s) + 6·s;
- **spiral** when H lies between L(s) + 6·s and the next L(1.5·s): the heap fills with 48-byte composites between steps,
  each full GC frees only the per-composite `Object[1]` crumbs, and G1 (JDK 11, no GC-overhead limit) keeps going; an
  `OutOfMemoryError` then comes late and from whichever thread allocates (U5 T-1, T-2, T-5).

Fitted on U5's two dumps/GC logs: at 8 GiB the failing full GC left `8014M` with 39 humongous regions (the 602 MiB array
of capacity 157,704,907) → b ≈ 193 MiB; at 2 GiB `T-CK-2G-3` left `1687M` at the 31.15M step → b ≈ 142 MiB. With
b = 100–250 MiB the windows are (MiB of heap):

| Step s (capacity) | L(s) = 52·s + b | L(s) + 6·s (new array) | U5 budgets that fell here (observed) |
|---|---|---|---|
| 31,151,587 | 1,645–1,795 | 1,823–1,973 (+178) | — (2048M is above: spiral 4/5; T-3's throw here was a fragmentation failure of the 178 MiB array) |
| 46,727,380 | 2,417–2,567 | 2,685–2,835 (+267) | — |
| 70,091,070 | 3,576–3,726 | 3,977–4,127 (+401) | 4096M at the upper edge (spiral 1/1) |
| 157,704,907 | 7,921–8,071 | 8,823–8,973 (+902) | **8192M inside: OOM 3/3** |
| 236,557,360 | 11,831–11,981 | 13,185–13,335 (+1,354) | — (15872M above: spiral) |
| 354,836,040 | 17,697–17,847 | 19,727–19,877 (+2,030) | — |
| 532,254,060 | 26,495–26,645 | 29,541–29,691 (+3,046) | — (31744M above: spiral) |
| 798,381,090 | 39,693–39,843 | — | — |

This is a post-hoc fit (b is taken from the same logs), but it matches all five U5 budgets (2048M, 4096M, 8192M, 15872M,
31744M) and it makes testable predictions on a new architecture and new budgets (below). It answers the retry row's
option choice: **2 GiB is between two windows** for any request (the elementsList capacities do not depend on k1), and
the 2 GiB × 32M alternative (U5 `CAL-CK-2G-32M`) throws only if the 32 MiB `BTree.Builder` array finds no contiguous
regions, a fragmentation outcome that is not predictable. So R14 pre-registers **the 8 GiB condition** (row option 1),
with a declared x86 calibration and a 12 GiB fallback that lies in the next window; it does not run 2 GiB CK.
The request must also pass the step: N > s (256M > 157.7M at 8 GiB; 256M > 236.6M at 12 GiB).

**Protection map** (fixed before any run; as U5, re-checked against the pinned source).

| Domain | Holder (allocation → release) | Counter K | Limit at default | At the limit |
|---|---|---|---|---|
| IN cartesian product (CK) — **claimed** | `MultiCBuilder.elementsList` (`ArrayList` + `Object[2]` per composite, `MultiCBuilder.java:358,368`; backing `Object[]` grown ×1.5 at `:359`) → `BTreeSet<Clustering>` (`ByteBuffer[2]` + `BufferClustering` per composite, `:435`); released when the request ends | `builder.buildSize()` = composites | `in_select_cartesian_product_warn/fail_threshold: -1` (`Config.java:877-878`), off (`Threshold.java:80-86`); skipped for non-ordinary users (`Guardrail.java:93-96`; shipped `AllowAllAuthenticator`, `cassandra.yaml:198`) | nothing at defaults → **unprotected configuration**; when enabled, rejects only after each column's product exists (U5 arm G) |
| Partition keys in SELECT | not reached in CK (one key `pk = 0`) | `keys.size()` | `partition_keys_in_select_*: -1` | — |
| Native request size | request frame (≈ 8 B per bound int) | message bytes | `native_transport_max_message_size` 16 MiB (derived), `native_transport_max_frame_size` 16 MiB | rejects the frame; charges ≤ 14.4 MB here |
| Native in-flight bytes | request bytes while processed | in-flight bytes | heap/10 global, heap/40 per IP (204.8 MiB per IP at 8 GiB) | back-pressure on socket reads; K ≪ C |
| Concurrency | one request per NTR thread | NTR threads | `native_transport_max_threads` 128 | not used: **one** request per lifetime |
| Read after the build | names-filter read of one 1-row partition | rows | page 5,000; `read_request_timeout` 5 s | irrelevant to the holder (the T request never finishes its build) |
| Slow/failed-query rendering (**ledgered, not claimed**) | `MonitoringTask` / `StorageProxy.logRequestException` render `toCQLString` with every requested clustering (U5 `CAL-CK-2G-16M` OOMed there) | none | none | only a request whose build completes reaches it (M: 1.6M clusterings ≈ 20 MB string, harmless at ≥ 8 GiB). An OOM there is **not** this endpoint |
| Baseline | memtable heap pool, key cache min(5 % H, 100 MiB), schema, system keyspaces | own counters | defaults | evict / flush |

**Configuration and budget audit.**
- Node **`pc91`** (`node0.jason92-326665`, UMass, **x86_64**, Intel Xeon E5-2667 v2 @ 3.30 GHz, 32 cores, MemTotal
  131,943,328 kB (`free -m` total 128,850), 8 GiB swap on `/dev/sda99` (excluded: `MemorySwapMax=0`), `/mydata`
  753 G LVM on a rotational `PERC H710P` volume, **714 GiB free**; Ubuntu 22.04, cgroup v2 with user delegation
  `memory pids`, passwordless sudo; OpenJDK 11.0.33+9 (x86_64), Ant, `jcmd`, Python 3.10.12). Checked read-only
  2026-11-20 10:31 EST: no java process, load 0.00, `/mydata/s4/` holds only `cassandra-base` (419 MB); the node clock
  is MST = EST − 2 h. **Not the U5 node and not the U5 architecture** (U5: ms0617, aarch64); U5's numbers are used only
  as predictions, never as controls for R14.
- Build: a copy of `pc91:/mydata/s4/cassandra-base` (jar sha256 `570b5249…0176e`, above). GC: G1 with the shipped
  `jvm11-server.options` (`G1HeapRegionSize=16m` `:66`, `MaxGCPauseMillis=300` `:79`, `G1NewSizePercent=50`,
  `AlwaysPreTouch`), `jvm-server.options:120` `-XX:+HeapDumpOnOutOfMemoryError` (**kept on at every heap**, unlike U5),
  `:137` `-XX:+PerfDisableSharedMem` (so no `jstat`; U5 A2), `cassandra-env.sh` `-XX:OnOutOfMemoryError="kill -9 %p"`.
  Region size 16 MiB at every heap here (explicit), so humongous threshold 8 MiB and per-object sizes are the same at
  every budget (compressed oops stay on: all heaps ≤ 28 GiB).
- **Every capacity constraint at its shipped default (V6)** in arms A and in the budget search:
  `in_select_cartesian_product_*` −1, `partition_keys_in_select_*` −1, `AllowAllAuthenticator`,
  `native_transport_max_message_size` (derived 16 MiB), `native_transport_max_frame_size` 16 MiB, in-flight limits
  derived from the heap, `native_transport_max_threads` 128, `read_request_timeout` 5 s, `native_transport_timeout` 12 s,
  `slow_query_log_timeout` 500 ms. The only constraint deviation is the intervention build (arm I).
- `cassandra.yaml` diff from the shipped file (**environment only**, every arm): `data_file_directories`,
  `commitlog_directory`, `hints_directory`, `saved_caches_directory`, `cdc_raw_directory` under the lifetime's node
  directory. Addresses stay `localhost`; the client runs on the same node.
- **Budgets (V7).** Standing rule: a heap or direct budget ≥ 512 MiB meets V7 without per-case review; 2 GiB is ideal; search
  for the largest failing budget. Resolved values on pc91 (`cassandra-env.sh`: ½ RAM = 64,425 MB > G1 `heap_limit`
  31,744): automatic heap **31744M**, `MaxDirectMemorySize` **15872M** (= heap_limit / 2, computed from RAM, so it is
  15872M also with a hand-set heap; record it from the process command line).
  - **Primary heap H_T = 8192M** (`MAX_HEAP_SIZE=8192M`, `HEAP_NEWSIZE` unset, `MAX_DIRECT_MEMORY_SIZE` unset → 15872M):
    what `cassandra-env.sh` resolves on a 16 GiB-RAM node, below this node's own 31744M; meets the standing rule.
    Fallback H_T = 12288M (resolved on a 24 GiB node) only by the calibration rule below.
  - **Upward search:** 12288M, 18432M, 28672M (each is what `cassandra-env.sh` resolves on a 24 / 36 / 56 GiB node; all
    below the node's automatic 31744M and under 32 GiB, so compressed oops stay on). 31744M (auto) is **not** run: no
    `elementsList` step window contains it (between 29.7 and 39.7 GiB), so the model predicts a spiral, as U5 saw on
    aarch64 (not reached in 900 s); U5's reading stands as the boundary evidence.
  - **No container budget.** Every Cassandra JVM runs in `systemd-run --user --scope -p MemoryMax=<heap + 6G>
    -p MemorySwapMax=0` (isolation and swap off only). A scope `oom_kill` makes the lifetime **invalid**.
  - No budget below 2 GiB and no tightened budget is used anywhere (U5's PK replication in P3 uses 2 GiB).

**Ceiling arithmetic.** No contract capacity bounds the product: N = k1 × k2, and the only bound on the lists is the
16 MiB request (≈ 2.09M int values in total). Requests used:

| Request | k1 × k2 = N | EXECUTE body K (≈) | `elementsList` alone at N | Step reached first | Predicted at H |
|---|---|---|---|---|---|
| T (8 GiB, 12 GiB) | 160 × 1,600,000 = 256,000,000 | 12.80 MB | 256M × 48 B + 1.42 GB array ≈ 12.9 GB | 157.7M (8 GiB), 236.6M (12 GiB) | throw at the step |
| T18 (18 GiB) | 240 × 1,800,000 = 432,000,000 | 14.40 MB | ≈ 21.8 GB | 354.8M | throw at the step |
| T28 (28 GiB) | 300 × 1,800,000 = 540,000,000 | 14.40 MB | ≈ 27.3 GB + array | 532.3M | throw at the step |
| M (8 GiB, matched) | 1 × 1,600,159 = 1,600,159 | 12.80 MB (same 1,600,160 values) | 1.6M × 52 B ≈ 80 MiB (+ ≈ 70 MiB `BTreeSet`) | none (< 2.37M) | 1 row |
| PK (P3, 2 GiB) | 16 × 500,000 = 8,000,000 keys | 4.00 MB | as U5 (≈ 370 B per key) | — | OOM in `getSliceCommands` (U5 3/3) |

All bodies are below 16,777,216 B (the client refuses larger frames before sending). Request bytes K ≈ 12.8 MB against
the 16 MiB message limit and 204.8 MiB per-IP in-flight limit (K ≪ C), while U (live product) reaches ≈ 7.8 GiB at the
8 GiB step: amplification ≈ 650× per request byte. CPU: `remove(0)` shifts ≈ Σ_i i·k2 references; to the 157.7M step that
is ≈ 99²/2 × 1.6M × 4 B ≈ 31 GB of memmove (U5 aarch64: +158 s to the throw); ≈ 70 GB to the 236.6M step, ≈ 140 GB to
354.8M (k1 = 240), ≈ 315 GB to 532.3M (k1 = 300).

**Workload and environment.**
- **Node `pc91` only**, one measured experiment at a time. Victim = one Cassandra node; client = one stdlib-only
  Python 3.10 process on the same node (loopback). Before every lifetime: no other `CassandraDaemon` (`ps -eo cmd |
  grep '[C]assandraDaemon'`), free disk on `/mydata` ≥ heap + 20 GiB.
- **Work directory `pc91:/mydata/s4/r14/`** (local disk, fresh, named for the run; do not touch
  `/mydata/s4/cassandra-base` beyond copying it): `tree/` (copy of `cassandra-base`), `tree-I/` (intervention copy),
  `conf-pristine/`, `template-A/`, `node/` (per lifetime), `runs/<label>/`, `h/` (harness), `cls/` (sampler).
- **Harness** under `harness/` in this case folder, adapted from U5's
  [`harness/`](../in_select_cartesian_product--select-IN-product-key-build/harness/) (copy, then change only what is
  listed): `setup.sh` (ROOT `/mydata/s4/r14`; tree copy, `conf-pristine`, `tree-I` built by compiling only the patched
  `MultiCBuilder.java` against the stock jar with `javac` and `jar uf` into a copy of the tree, never `ant`; C2Sampler
  compiled to `cls/`; both jar sha256s to `jars.sha256`), `run-arm.sh`, `u5client.py` (unchanged: keyspace `u5`,
  protocol v4, one connection, PREPARE + one EXECUTE, consistency ONE, page size 5,000, bound lists `0..k1−1`,
  `0..k2−1`, never IN literals), `C2Sampler.java`, `gcwin.py`, `hs_full.py`, `hprofstacks.py`, `hprofhist.py`,
  `summarize.py` (unchanged), and new sequencers `seq-p1.sh`, `seq-p2.sh`, `p3.sh`. **Changes to `run-arm.sh`** (each is
  a fix of a U5 limitation, not a change of the mechanism):
  1. ROOT `/mydata/s4/r14`; arm I passes `-Du5.max_in_product=2000000`; the line that turned
     `HeapDumpOnOutOfMemoryError` off above 4096M is **removed** (dump on at every heap, as shipped);
     `CASSANDRA_HEAPDUMP_DIR=$R`.
  2. **OOM detection independent of JVM death:** a watcher prefixes each new `stdout.log` line with the wall clock
     (`stdout.ts`), so the times of `java.lang.OutOfMemoryError: Java heap space`, `Dumping heap to …`,
     `Heap dump file created […]` and `Executing /bin/sh -c "kill -9 …"` are recorded; `outcome` reports
     `thrown_at`, `dump_done_at`, `jvm_exit_at` separately (U5's harness looked only at JVM death).
  3. **Lifetime end:** (a) no throw: client exit + 15 s, or the throw window W after `t_send`; (b) after a throw: wait for
     JVM exit up to the grace G after the throw (lets the dump finish and `OnOutOfMemoryError` run), then SIGTERM, 30 s,
     SIGKILL. W / G: 8192M and 12288M 600 s / 600 s; 18432M 1,200 s / 900 s; 28672M 1,500 s / 900 s; PK 2G 300 s / 300 s.
  4. **Humongous trigger:** a watcher on `gc.log` runs **one** `timeout 120 jcmd <pid> Thread.print > threads-hum.txt` at
     the first `Pause Full (G1 Humongous Allocation)` line (a second attribution of the NTR frames, if the dump fails).
  5. Excerpts: `ntr-t2.txt`, `ntr-t6.txt`, `ntr-hum.txt` (NTR thread with `MultiCBuilder|ClusteringColumnRestrictions|
     SelectStatement|BTree|CBuilder` frames), `gc-tail.txt`, `gcwin.txt`, `oom-excerpt.txt`, `stdout.ts` excerpt,
     `hprof.ls`, `memory.events`, `parent.memory.events.*`, `run.meta`, `yaml.diff`, `client.jsonl`, `samples.csv`,
     `rss.txt` into `runs/<label>/small/`; pulled to `logs/<label>/` in this folder.
- **Schema** (lifetime `LOAD`, heap 2G, not a reading; as U5): `CREATE KEYSPACE u5 WITH replication =
  {'class':'SimpleStrategy','replication_factor':1}`; `CREATE TABLE u5.ck (pk int, c1 int, c2 int, v int, PRIMARY KEY
  (pk, c1, c2))`; `CREATE TABLE u5.pk (a int, b int, v int, PRIMARY KEY ((a, b)))`; rows `(0,0,0,1)` and `(0,0,1)`, so a
  completed request returns exactly **1 row**. `nodetool flush u5`, `nodetool drain`, SIGTERM → `template-A` (empty
  `saved_caches`). Every measured lifetime starts from a fresh `cp -a` of `template-A`.
- **Intervention build (arm I; diagnostic patch, separate tree).** U5's
  [`u5-pre-allocation-check.patch`](../in_select_cartesian_product--select-IN-product-key-build/harness/u5-pre-allocation-check.patch)
  unchanged: in `MultiClusteringBuilder.addEachElementToAll` and `addAllElementsToAll`, right after
  `checkUpdateable()`, throw `InvalidRequestException("u5: IN cartesian product <a> x <b> exceeds <limit>")` when
  `max(1, elementsList.size()) × values.size() > Long.getLong("u5.max_in_product", -1)` — the count checked **before**
  the product is allocated (the order the shipped guardrail does not use). Property **2,000,000** in arm I: M
  (1 × 1,600,159) passes, T (160 × 1,600,000) is rejected at the c2 column, PK T (16 × 500,000) is rejected. Save the diff
  and both jar sha256s.

**Labels and order** (P1 > P2 > P3; one lifetime per row; reps from clean starts).

| Pri | Label | Arm | Heap | Request | Reps | Counted? |
|---|---|---|---|---|---|---|
| P1 | `LOAD`, `IC` (IC: CK 4×4, 1×1,000, 160×1,000, PK 4×4, 1×1,000, one request each, + `GC.class_histogram` baseline; also the client's body-size check for T, T18, T28, M) | A | 2G | small | 1 | no (setup, instrument check) |
| P1 | `CAL-X-8G` x86 calibration | A | 8192M | T | 1 | **no** |
| P1 | `CAL-X-12G` (only if `CAL-X-8G` did not throw, rule below) | A | 12288M | T | 1 | no |
| P1 | `T-CK-<H_T>-1..3` test (+ `-4`, `-5` only if exactly 2 of the first 3 count) | A | H_T | T | 3 (≤ 5) | yes (V1) |
| P1 | `M-CK-<H_T>-1..3` matched control | A | H_T | M | 3 | yes (V2) |
| P1 | `I-CK-<H_T>-1..3` intervention | I | H_T | T | 3 | yes (V4) |
| P1 | `IM-CK-<H_T>` useful work under I | I | H_T | M | 1 | supporting |
| P2 | `CAL-CK-12G` (skipped if 12288M is H_T or already run as `CAL-X-12G`), `CAL-CK-18G`, `CAL-CK-28G` budget search, ascending, all run (no stop at the first survivor: the windows are not monotonic) | A | 12288M, 18432M, 28672M | T, T18, T28 | 1 each | budget search |
| P2 | `REP-<Hmax>-1..2` at the largest heap whose point threw and counted (8192M excluded: its n/N is the T arm) | A | Hmax | its request | 2 | budget n/N |
| P3 | `T-PK-2G-1..3`, `M-PK-2G-1..3` (1 × 500,015), `I-PK-2G-1..3` — x86 replication of U5's PK condition | A / I | 2G | PK | 3 each | not deciding (reported) |

**Calibration rule (declared before any reading; not counted).** `CAL-X-8G` runs the T request at 8192M with all
instruments. If `Java heap space` is thrown within W **and** the hprof (or `threads-hum.txt` if the dump did not finish)
shows the NTR thread in the CK build frames, then **H_T = 8192M**. Otherwise (no throw in W: spiral at the heap ceiling
before the 157.7M step, i.e. x86's b exceeds ≈ 370 MiB; or a throw not attributable) run `CAL-X-12G` at 12288M with the
same request; if it meets the same test, **H_T = 12288M**; if neither does, H_T = 8192M (the retry row's pre-registered
condition) and the counted arms run there anyway; the verdict rules decide. Record IC's baseline (`GC.class_histogram`
total) and the calibration lifetime's last full-GC "after" value and humongous region count as b_x86.

**Instruments (U independent of K).** K = EXECUTE body bytes (client) against the request-byte controls; arm I's
rejection message carries the pre-allocation count. U = (a) the GC log `-Xlog:gc*,safepoint:file=$R/gc.log:time,uptime,
level,tags:filecount=10,filesize=50m`: heap before/after each GC, `Pause Full (… Humongous Allocation)`, `Humongous
regions: a->b` (the size of the `elementsList` array in 16 MiB regions, plus one other humongous object that U5 also
had (U5 8 GiB: 39 = 38 for the 602 MiB array + 1): 39 = capacity 157,704,907; 58 = 236,557,360; 86 = 354,836,040;
128 = 532,254,060), pause times — **the primary U source** (the JMX sampler stalls in full GCs, U5 A2);
(b) `C2Sampler` over JMX every 1 s (heap used, G1 Old Gen used, old post-GC, NTR active/pending, GC times); (c)
`RssAnon` and scope `memory.events` every 5 s; (d) `jcmd <pid> Thread.print` at `t_send` + 2 s, + 6 s, and once at the
first humongous-allocation full GC; (e) at an OOM: the `stdout.ts` lines, the hprof: `hs_full.py <hprof> OutOfMemoryError`
(the thread holding the error, all frames) and `hs_full.py <hprof> MultiCBuilder` (the NTR thread) right after every
lifetime with a dump (record-only parse, seconds), and `hprofhist.py` (instances and shallow bytes of `ArrayList`,
`Object[2]`, the largest `Object[]`, `ByteBuffer[2]`, `BufferClustering`, top 15) for **every counted T dump and
`CAL-X-*`**, and for the P2 dumps if time allows; (f) baseline `GC.class_histogram` in IC; (g) `system.log` / `debug.log`
lines from `MonitoringTask`, `StorageProxy`, guardrails, `InvalidRequest`; (h) `gcwin.py` (STW share per 60 s window).
Parsers run under `nice -n 19 taskset -c 28-31`, never during a `CAL-X` or `T-CK` lifetime (they may run during M, I,
P2, P3 lifetimes and between lifetimes; record when). hprofs are kept on the node (expected ≈ 8.5 GB per 8 GiB dump,
≈ 190 GB worst case in total against 714 GiB free); delete only if free space would drop below 100 GiB, oldest P2 dump
first, after its stacks are saved (log it).

**Predicted response** (numbers before any reading).
- `IC`: every small request returns 1 row; EXECUTE bodies as computed; baseline live heap 50–200 MiB (U5 aarch64:
  56.7 MiB). Body-size check: T 12,80x,xxx B, T18/T28 14,40x,xxx B, M 12,80x,xxx B, all < 16,777,216.
- `CAL-X-8G` and `T-CK-8192M-1..3`: `Thread.print` at +2/+6 s shows the NTR thread in `addEachElementToAll` (`:354`
  shift or `:358` copy). The old gen climbs to ≈ 7.8–7.9 GiB; then `Pause Young (… G1 Humongous Allocation)` and two
  `Pause Full (G1 Humongous Allocation) X->X(8192M)` with **X = 7,920–8,070 MiB** and **`Humongous regions: 39->39`**;
  then `java.lang.OutOfMemoryError: Java heap space` at **t_send + 40–170 s** (U5 aarch64 +158 s; x86 expected faster),
  thrown on the **NTR thread** in `Arrays.copyOf` ← `ArrayList.grow` ← `ArrayList.add` ←
  `MultiCBuilder$MultiClusteringBuilder.addEachElementToAll:359` (the 157,704,907 → 236,557,360 growth, a 902 MiB
  array) ← `INRestriction.appendTo:241` ← `ClusteringColumnRestrictions.valuesAsClustering:110` ← … ←
  `SelectStatement.getSliceCommands:725` ← `ExecuteMessage.execute` ← `Dispatcher.processRequest`; heap dump ≈ 8.3–8.6 GB
  written in 30–150 s, then `kill -9`: **JVM exit 3/3 within G**. Histogram: `ArrayList` and `Object[2]` ≈ 157.7M each
  (± 1M), one `Object[157,704,907]`; together ≥ 85 % of the shallow total. Client: `conn_closed`. Service loss
  (≥ 90 % STW ≥ 60 s) possible only in the last ≈ 60 s before the throw (U5: 60–61 s at 91–92 %), recorded, not the endpoint.
  **Strict count (NTR thread is the thrower): 3/3 predicted.**
- `M-CK-8192M`: **1 row 3/3** in ≤ 10 s; old gen post-GC ≤ 1 GiB, no full GC, no OOM. A slow-query line rendering 1.6M
  clusterings is possible (harmless).
- `I-CK-8192M`: `InvalidRequest` (0x2200) "u5: IN cartesian product 160 x 1600000 exceeds 2000000" **3/3** within 2 s
  of `t_send`; heap ≤ baseline + 1 GiB (young only), no full GC, no OOM. `IM-CK-8192M`: 1 row.
- If H_T = 12288M (fallback): the same, with `Humongous regions: 58->58` (902 MiB array), X = 11,830–11,980 MiB, failing
  allocation 1,354 MiB at `addEachElementToAll:359`, throw at t_send + 80–400 s, dump ≈ 12.5–13 GB.
- P2 (budget search; each predicted to **throw on the NTR thread at the step**): `CAL-CK-12G` as just above;
  `CAL-CK-18G` (T18): `Humongous regions: 86->86`, X = 17,700–17,850 MiB, failing 2,030 MiB, throw at + 150–800 s;
  `CAL-CK-28G` (T28): `Humongous regions: 128->128`, X = 26,500–26,650 MiB, failing 3,046 MiB, throw at + 250–1,200 s.
  **Largest failing heap predicted: 28672M**; with `REP-28672M-1..2`: 3/3 there. 31744M (auto, not run): spiral (U5).
  A P2 point that instead spirals without a throw in W is the model's failure for that window and is reported as such
  (`not reached (time)`), not as a negative.
- P3 (if run): as U5 PK: OOM 3/3 at + 60–140 s in `SinglePartitionReadCommand.create` ← `getSliceCommands:737`; M-PK
  read timeout or 1 row with old gen < 0.6 GiB, 0/3 OOM; I-PK rejected 3/3.
- No scope `oom_kill` anywhere (scope limit heap + 6 GiB; the JVM's RSS ≈ heap + ≤ 1 GiB).

**Stopping budget and time plan** (stage 2 starts ≈ 12:00 EST 2026-11-20; everything stopped and §3–§4 and the
write-backs done by **17:30 EST**; pc91's clock is MST = EST − 2 h). Lifetime estimates on pc91: 8 GiB T ≈ 4–7 min
(start ≈ 30 s with `AlwaysPreTouch`; throw ≤ 170 s; dump ≤ 150 s), M / I ≈ 1.5–2 min, 12 GiB ≤ 20 min, 18 GiB ≤ 30 min,
28 GiB ≤ 40 min worst case (W + G), PK 2G ≈ 3–5 min.
- 12:00 → 12:30: setup (copy tree, `tree-I`, harness, sampler), `LOAD`, `IC`.
- 12:30 → 12:45: `CAL-X-8G` (+ `CAL-X-12G` if needed, to ≈ 13:05).
- 12:45 → 13:50: `T-CK-<H_T>-1..3`, then `M` ×3, `I` ×3, `IM`; stacks after each T; histograms of the T dumps during the
  M/I lifetimes; `T-4`, `T-5` only if exactly 2 of 3 counted. **P1 complete by ≈ 14:00** (later by ≤ 20 min if H_T = 12288M).
- 14:00 → 15:30: P2 points ascending (12288M, 18432M, 28672M).
- 15:30 → 16:45: `REP-<Hmax>-1..2`, each only if it can end by 16:50 (a 28 GiB REP needs ≤ 40 min).
- Then P3, only if at least 45 min remain before 16:50 (all nine lifetimes, or none).
- **Hard limits:** no lifetime starts unless its W + G ends by **16:55**; all processes stopped by **17:00**; §3–§4
  and write-backs by 17:30. If P1 is not complete by 15:00, skip P2's REP and P3. No escalation after an OOM beyond this
  plan; no heap, request or arm outside the table.

**Controls and intervention.**
- **Matched control `M-CK-<H_T>` ×3 (V2):** same build, budget, template, statement, connection and request bytes
  (the same 1,600,160 int values, ≈ 12.8 MB) with 1 value in c1 and 1,600,159 in c2, so the product is additive
  (1.6M composites instead of 256M). It isolates the multiplication, not the request size or value count.
- **Intervention `I-CK-<H_T>` ×3 (V4):** the T request against the pre-allocation check (separate build `tree-I`,
  saved diff); removing the OOM attributes it to the unchecked expansion. `IM-CK-<H_T>` shows useful work continues.
- The shipped guardrail (arm G) is not re-run: U5 showed it enforces late (diagnostic); it is not the intervention.

**Verdict rules (stated before readings; this answers the retry row's "state in the rule whether an OOM on another
thread counts").**
- **A counted OOM (V1 unit)** in a `T-CK` lifetime needs all of: (1) `java.lang.OutOfMemoryError: Java heap space` in
  `stdout.log` within W after `t_send`; (2) the claimed holder at the failure: the hprof written at that OOM shows
  `ArrayList` + `Object[2]` + the largest `Object[]` (+ `BufferClustering` + `ByteBuffer[2]`) ≥ 50 % of the shallow
  total; (3) the request was still building: the NTR thread's stack in the hprof (or, only if the dump did not complete
  within G, in `threads-hum.txt` taken at the first humongous full GC, together with a GC log showing old gen ≥ 95 % of
  the heap after the last full GC) is inside `MultiCBuilder$MultiClusteringBuilder.addEachElementToAll` or `.build`
  under `ClusteringColumnRestrictions.valuesAsClustering`. **An OOM thrown on another thread counts** when (2) and (3)
  hold: in a heap-exhaustion OOM the thrower is whichever thread allocates next, and the protocol's V5 asks for the
  first error with its thread plus a dump showing the claimed holder, not that the holder's thread throws. The thread
  holding the error is reported for every run, and the **strict count** (thrower = the NTR thread in those frames) is
  reported beside the counted one in the Result phrase. A throw with neither a complete dump nor `threads-hum.txt` is
  **not counted** (unattributed). **JVM exit** (`kill -9` by `OnOutOfMemoryError`) and **service loss** are scored
  separately and are not required.
- **true positive:** counted OOM in ≥ 3 `T-CK-<H_T>` runs (3/3, or 3 of 5 after the two extra runs allowed when exactly 2
  of 3 count), at least one with a complete dump and histogram (V3/V5); `M-CK-<H_T>` 0/3 OOM and 1 row each;
  `I-CK-<H_T>` 0/3 OOM with the u5 rejection each; constraints at defaults (V6) and H_T ≥ 512 MiB (V7) →
  **`verified-OOM · deployment`**, unprotected configuration, with the largest failing heap from P2 and its n/N.
  The strict n/N is stated; a counted 3/3 with strict < 3 is still true positive under this rule.
- **retry:** fewer than 3 counted OOMs in ≤ 5 runs; an M or I run OOMs or M does not return its row (after the invalid
  rule); time ran out before V1, V2 or V4; the claimed holder < 50 % of a dump; the only OOMs are in another holder
  (e.g. the `toCQLString` / logger rendering path).
- **false positive:** a `T-CK-<H_T>` request completes its build and returns (1 row, or a timeout after the build with
  `Thread.print` past `makeClusteringIndexFilter`) with old gen post-GC < 90 % (not possible by the arithmetic: 256M
  composites need ≥ 11.4 GiB for `ArrayList` + `Object[2]` alone), or a shipped default control rejects it (named).
- **PK** (P3) gets its own status line; it does not change the case verdict (U5's PK `verified-OOM · deployment`
  on aarch64 stands either way).
- **Invalid lifetime:** scope `oom_kill`; client error before `t_send`; frame refused for size; node not ready in 180 s;
  wrong row count in IC or M. Fix, rerun once, record as a deviation.
- **Cleanup:** stop every process started (Cassandra by PID, samplers, watchers, client, parsers); keep
  `/mydata/s4/r14/` (runs, hprofs, trees, template); touch nothing else on pc91; report what is left and its size.

`sha256 of §1–§2 at freeze: ad3c3660b7df2306bfdb9830fed49ee72b9b91f1f31bb064bf69b3a5ed2264b8` · computed over the lines from `## 1. Candidate` through the line before this one (`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum`) · amendments after the freeze: dated, with reason, below this line.

## 3. Runs (stage 2)

**Owner ruling (2026-11-20, Jingsong, relayed by the coordinator at ≈ 10:55 EST, before any reading was taken
into account).** The verdict is decided by the pre-registered rule frozen in §2: an OOM thrown on another thread counts
when the heap dump shows the key product ≥ 50 % of the heap and the request thread still in the CK build frames. The
strict request-thread count is reported beside it. No other change.

**Stage 2:** fresh phase-2 OOM-agent session, 2026-11-20 10:42–12:30 EST. Freeze hash checked first:
`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum` =
`ad3c3660b7df2306bfdb9830fed49ee72b9b91f1f31bb064bf69b3a5ed2264b8`, **matches**. No amendment to §2 was needed.
Started ≈ 75 min earlier than the time plan's 12:00 (the plan's hard limits were kept).

### 3.1 Environment

- Node `pc91` (`node0.jason92-326665`), x86_64, 32 cores, 125 GiB, kernel 5.15.0-203-generic, Ubuntu 22.04,
  cgroup v2, swap 8 GiB present and unused (`MemorySwapMax=0` in every scope), OpenJDK 11.0.33+9. Checked before the
  first lifetime: no `CassandraDaemon` and no other java process, load 0.00, `/mydata` 714 GiB free.
- Work directory `pc91:/mydata/s4/r14/` (`tree/` copy of `cassandra-base`, `tree-I/`, `conf-pristine/`,
  `template-A/`, `runs/<label>/`, `h/`, `cls/`, `patchwork/`). Stock jar sha256 `570b5249…0176e` (as §2);
  intervention jar `04668d2e…c76c47f` ([`logs/jars.sha256`](logs/jars.sha256)). The generated intervention diff is
  identical (every `+`/`-` line) to U5's [`u5-pre-allocation-check.patch`](harness/u5-pre-allocation-check.patch).
- Resolved JVM settings from the process command line (every arm): `-XX:+UseG1GC -XX:G1HeapRegionSize=16m
  -XX:MaxGCPauseMillis=300 -XX:+AlwaysPreTouch -XX:+HeapDumpOnOutOfMemoryError -XX:OnOutOfMemoryError="kill -9 %p"`,
  `-Xms = -Xmx` = the heap of the row, **`-XX:MaxDirectMemorySize=15872M`** in every lifetime (cassandra-env.sh's
  RAM-derived value, as predicted). Scope `MemoryMax` = heap + 6 GiB, `MemorySwapMax=0`.
- `cassandra.yaml` diff (every lifetime, [`logs/CAL-X-8G/yaml.diff`](logs/CAL-X-8G/yaml.diff)): the five directories
  only. Every capacity constraint at its shipped default (V6) in arm A; arm I differs only by the patched jar and
  `-Du5.max_in_product=2000000`.
- Harness: [`harness/`](harness/) (`setup.sh`, `run-arm.sh`, `ts.py`, `seq.sh`, `seq-rep-p3.sh`, `pull-logs.sh`;
  `u5client.py`, `C2Sampler.java`, `gcwin.py`, `hs_full.py`, `hprofstacks.py`, `hprofhist.py`, `summarize.py` copied
  unchanged from U5). The design's `seq-p1.sh` / `seq-p2.sh` / `p3.sh` are one generic `seq.sh` called with the §2
  label table (P1 as `P1a` = LOAD, IC, CAL-X-8G and `P1b` = T, M, I, IM; P2; then `seq-rep-p3.sh` = REP and P3);
  `seq.sh` refuses any lifetime whose start + 300 s + W + G would end after 16:55 EST.
- Full run data on the node: `pc91:/mydata/s4/r14/runs/<label>/` (`stdout.log`, `stdout.ts`, `gc.log*`,
  `logs/system.log`, `debug.log`, `samples.csv`, `threads-*.txt`, `stack-oom.txt`, `hist.txt`, hprof where kept);
  small excerpts in [`logs/<label>/`](logs/).

**Harness deviations (recorded; none changes the mechanism, the arms or a reading).**
1. *Throw detector, CAL-X-8G only.* The watcher's pattern `java.lang.OutOfMemoryError` was a regex and matched a
   startup line of `stdout.log` (`CompileCommand: exclude …forceHeapSpaceOomMaybe(Ljava/lang/OutOfMemoryError;)V`),
   so CAL-X-8G's driver entered its "after a throw" branch at +2 s (lifetime end = JVM exit or +602 s instead of
   W = 600 s or throw + G; JVM exit came at +123 s, so the lifetime ended the same way). The outcome's time parser
   matched literally and was unaffected (`thrown_at=+35.9s` is the real throw). Fixed (`grep -F
   'java.lang.OutOfMemoryError: '`) at 10:48 EST, after CAL-X-8G and before any counted lifetime; CAL-X-8G's
   `kill9_at=-9.7s` is the same parser matching the JVM command line, also fixed (`Executing /bin/sh -c "kill -9`).
2. *Scope `memory.events` `max`.* Every lifetime that wrote a heap dump shows `max` events (8 GiB: 40,835–57,526;
   12 GiB 73,622; 18 GiB 207,425; 28 GiB 250,567–327,667) and **`oom 0`, `oom_kill 0`** everywhere. The hprof (14.5–48 GB) is
   written from inside the scope, so its page cache meets `MemoryMax` and is reclaimed; anonymous memory stayed far
   below the limit (`RssAnon` peak 9,108 MiB at 8 GiB against 14,336 MiB). Not a scope OOM, so no lifetime is invalid;
   the dumps took 84–364 s.
3. *hprof retention.* §2 kept every hprof unless free space fell below 100 GiB; the session's node instruction was
   to delete surplus dumps after reading them. Deleted after their stacks (and, for 8 GiB, histograms) were saved:
   CAL-X-8G, T-CK-8192M-2, T-CK-8192M-3, REP-28672M-1, REP-28672M-2 (list and times in
   `pc91:/mydata/s4/r14/runs/hprof-deleted.log`); see §3.6 for what is left. No reading was taken from a deleted
   dump after its deletion.
4. The `+2 s` / `+6 s` stacks show the NTR thread at `MultiCBuilder.java:356` (the c2 loop's `remove(0)` /
   copy) or `:359` (`ArrayList.grow`), where §2 named `:354`/`:358`; same loop, line numbering only.
5. Parsers (`hs_full.py`, `hprofhist.py`) ran under `nice -n 19 taskset -c 28-31`: CAL-X-8G's stack between
   CAL-X-8G and T-CK-8192M-1 (no lifetime running); T stacks and the four 8 GiB histograms during M/I/IM and P2
   lifetimes; P2/REP stacks and histograms during P2, REP and P3 lifetimes. None ran during a CAL-X or T-CK lifetime.

### 3.2 LOAD and IC (2G; not readings)

- `LOAD` 10:46 EST: schema and the two rows, flush, drain, `template-A` 1.2 MB.
- `IC` ([`logs/IC/`](logs/IC/)): CK 4×4, 1×1,000, 160×1,000 and PK 4×4, 1×1,000 each returned **1 row** (0.007–0.30 s).
  Baseline `GC.class_histogram` total **77,110,136 B (73.5 MiB)**, 715,796 objects (predicted 50–200 MiB).
  Body-size check ([`bodysize.txt`](logs/IC/bodysize.txt)): T 12,801,331 B; T18 14,401,971 B; T28 14,402,451 B;
  M 12,801,331 B; PK 4,000,171 B; M-PK 4,000,171 B, all < 16,777,216.

### 3.3 P1 at H_T = 8192M (calibration, T, M, I, IM)

**Calibration (`CAL-X-8G`, not counted).** Threw `Java heap space` at **+35.9 s**; the hprof (14,488,324,868 B,
written in 83.7 s) shows the thread holding the error is `Native-Transport-Requests-1` in `Arrays.copyOf` ←
`ArrayList.grow` ← `ArrayList.add` ← `MultiCBuilder$MultiClusteringBuilder.addEachElementToAll:359` ←
`INRestriction.appendTo:241` ← `ClusteringColumnRestrictions.valuesAsClustering:110` ← … ←
`SelectStatement.getSliceCommands:725` ← `ExecuteMessage.execute` ← `Dispatcher.processRequest`
([`hprof-stack-oom.txt`](logs/CAL-X-8G/hprof-stack-oom.txt)). Rule met → **H_T = 8192M**; `CAL-X-12G` not run.
b_x86 = last full GC "after" 8,032 MiB − 52 B × 157,704,907 = **211 MiB** (`Humongous regions: 39->39`).

**Counted lifetimes** (`summarize.py`; heap / direct = `-Xmx` / resolved `MaxDirectMemorySize`; JMX columns stall
during full GCs, the GC log is the primary U source):

| Label | Arm | Heap / direct | Request (N) | K body B | Client | Latency s | JMX heap / old / old post-GC max MiB | Full GCs, max STW in 60 s, ≥ 90 % window | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| `T-CK-8192M-1` | A | 8192M / 15872M | 160 × 1,600,000 (256M) | 12,801,331 | conn_closed | 135.6 | 7,975 / 7,954 / 7,954 | 19, 48 %, 0 s | **OOM** thrown +46.8 s, dump done +131.6 s, `kill -9` +134.6 s, JVM exit ≤ +136 s |
| `T-CK-8192M-2` | A | 8192M / 15872M | 256M | 12,801,331 | conn_closed | 132.8 | 8,113 / 7,972 / 7,972 | 15, 44 %, 0 s | **OOM** thrown +44.5 s, dump +130.2 s, `kill -9` +131.7 s, exit ≤ +133 s |
| `T-CK-8192M-3` | A | 8192M / 15872M | 256M | 12,801,331 | conn_closed | 126.3 | 7,982 / 7,966 / 7,966 | 10, 32 %, 0 s | **OOM** thrown +37.1 s, dump +123.8 s, `kill -9` +125.3 s, exit ≤ +127 s |
| `M-CK-8192M-1` | A | 8192M / 15872M | 1 × 1,600,159 | 12,801,331 | **1 row** | 1.29 | 2,780 / 636 / 0 | 0, 0 %, 0 s | survived |
| `M-CK-8192M-2` | A | 8192M / 15872M | 1 × 1,600,159 | 12,801,331 | **1 row** | 1.23 | 2,780 / 636 / 0 | 0, 0 %, 0 s | survived |
| `M-CK-8192M-3` | A | 8192M / 15872M | 1 × 1,600,159 | 12,801,331 | **1 row** | 1.23 | 2,764 / 636 / 0 | 0, 0 %, 0 s | survived |
| `I-CK-8192M-1` | I | 8192M / 15872M | 256M | 12,801,331 | `0x2200 u5: IN cartesian product 160 x 1600000 exceeds 2000000` | 0.18 | 1,244 / 12 / 0 | 0, 0 %, 0 s | survived |
| `I-CK-8192M-2` | I | 8192M / 15872M | 256M | 12,801,331 | same rejection | 0.17 | 1,232 / 0 / 0 | 0, 0 %, 0 s | survived |
| `I-CK-8192M-3` | I | 8192M / 15872M | 256M | 12,801,331 | same rejection | 0.15 | 1,258 / 10 / 0 | 0, 0 %, 0 s | survived |
| `IM-CK-8192M` | I | 8192M / 15872M | 1 × 1,600,159 | 12,801,331 | **1 row** | 1.19 | 2,748 / 636 / 0 | 0, 0 %, 0 s | survived |

**Attribution of the three T OOMs** ([`logs/T-CK-8192M-*/`](logs/)):
- **GC log:** in each, the failing sequence is `Pause Young (Normal) (G1 Humongous Allocation)` then `Pause Full (G1
  Humongous Allocation) 8033M->8032M(8192M)` (≈ 1.5 s) with **`Humongous regions: 39->39`** (the 602 MiB backing array
  of capacity 157,704,907 + one other), as predicted (X = 7,920–8,070). An earlier `Pause Full (G1 Humongous
  Allocation)` at +13.6–14.6 s (the 31.15M → 46.7M or 46.7M → 70.1M step, recovered to ≈ 5.4 GiB) is where
  `threads-hum.txt` was taken: NTR at `addEachElementToAll:359` (`ArrayList.grow`) in all three.
- **Thrower (hprof `hs_full.py … OutOfMemoryError`):** in all three dumps exactly one stored trace holds the
  error, and it is the NTR thread: `OutOfMemoryError.<init>` ← `Arrays.copyOf` ← `ArrayList.grow` ← `ArrayList.add` ←
  `addEachElementToAll:359` ← `INRestriction.appendTo:241` ← `valuesAsClustering:110` ← `getClusteringColumns:942` ←
  `getRequestedRows:977` ← `makeClusteringIndexFilter:835` ← `getSliceCommands:725` ← … ← `Dispatcher.processRequest`;
  the `MultiCBuilder` search returns the same single trace. **Strict count (thrower = NTR thread in the build frames):
  3/3.**
- **Holder (hprof `hprofhist.py`, [`hist.txt`](logs/T-CK-8192M-1/hist.txt), identical within ± 3 objects across
  CAL-X-8G and T-1..3):** `java.util.ArrayList` **157,707,500** instances; `Object[]` of length 2
  **157,706,383**; one `Object[157,704,907]` (601.6 MiB; the `elementsList` backing array at the failing growth step);
  `HeapByteBuffer` 1,608,673 (the deserialized bound values, 84 MiB); `BufferClustering` 1,342 (the `BTreeSet` was never
  reached). Share of the parser's shallow total (9,253 MiB; it sizes an `ArrayList` at 32 B): `ArrayList` 4,812.9 +
  `Object[2]` 3,609.6 + big array 601.6 = **97.5 %**; at real sizes (24 B + 24 B per composite + the 602 MiB array) the
  holder is **7,821 MiB of the 8,032 MiB live** after the last full GC (97.4 %). Predicted ≈ 157.7M ± 1M each,
  ≥ 85 % — met.
- **`Thread.print` at +2 / +6 s:** NTR in `addEachElementToAll` (`:356` or `:359`) in all three
  ([`ntr-t2.txt`](logs/T-CK-8192M-1/ntr-t2.txt), `ntr-t6.txt`).
- **Service loss:** not met in any (max STW share in 60 s 32–48 %; the throw comes ≈ 35–47 s after send, before a
  60 s spiral can form). Not the endpoint (scored separately, as §2).
- **Client:** `conn_closed` (connection reset at `kill -9`) in all three; **JVM exit 3/3** within G.
- **Scope:** `oom_kill 0` everywhere (deviation 2).

**Matched control and intervention.** M returned its 1 row 3/3 in 1.2–1.3 s with old gen ≤ 636 MiB (JMX), 0 full GCs;
I rejected the T request 3/3 in 0.15–0.18 s with the pre-allocation message (old gen ≤ 12 MiB, 0 full GCs); IM (the M
request on the intervention build) returned its row: the check stops the multiplication, not useful work.

### 3.4 P2 budget search (one lifetime each; all ascending, all run) and REP

| Label | Heap / direct | Request (N) | K body B | Throw (s after send) | Last full GC before the throw | Humongous regions | b_x86 MiB | Thrower (hprof) | Dump B, written in | Outcome |
|---|---|---|---|---|---|---|---|---|---|---|
| `CAL-CK-12G` | 12288M / 15872M | 160 × 1,600,000 (256M) | 12,801,331 | **+59.0** | `11946M->11946M(12288M)` 2.4 s | **58->58** | 215 | NTR, `addEachElementToAll:359` (`ArrayList.grow`) | 21,579,019,862, 176 s | OOM, `kill -9`, exit +237 s |
| `CAL-CK-18G` | 18432M / 15872M | 240 × 1,800,000 (432M) | 14,401,971 | **+93.5** | `17826M->17823M(18432M)` 3.7 s | **86->86** | 226 | NTR, same frames | 32,241,282,151, 279 s | OOM, `kill -9`, exit +376 s |
| `CAL-CK-28G` | 28672M / 15872M | 300 × 1,800,000 (540M) | 14,402,451 | **+173.9** | `26616M->26616M(28672M)` 7.5 s | **128->128** | 221 | NTR, same frames | 48,208,977,617, 304 s | OOM, `kill -9`, exit +482 s |
| `REP-28672M-1` | 28672M / 15872M | 540M | 14,402,451 | **+180.4** | `26617M->26616M(28672M)` 4.8 s | **128->128** | 221 | NTR, same frames | 48,214,429,332, 363 s (deleted after the stack) | OOM, `kill -9`, exit +546 s |
| `REP-28672M-2` | 28672M / 15872M | 540M | 14,402,451 | **+168.3** | `26616M->26616M(28672M)` 5.0 s | **128->128** | 221 | NTR, same frames | 48,208,630,986, 321 s (deleted after the stack) | OOM, `kill -9`, exit +492 s |

Every P2 point fell where the step-window model put it: the failing full GC's "after" value lies in the predicted
L(s) range at every heap (12 GiB 11,830–11,980 → 11,946; 18 GiB 17,700–17,850 → 17,823; 28 GiB 26,500–26,650 →
26,616), the humongous count is the predicted array (58 / 86 / 128), and b_x86 = 211–226 MiB at all four budgets.
Throw times: predicted 80–400 s / 150–800 s / 250–1,200 s, observed 59 / 94 / 174–180 s (x86 faster than the
aarch64-based estimate). Service loss: not met (max STW share in 60 s 42 % / 44 % / 39 %). **Largest failing heap
tested: 28672M, OOM 3/3** (CAL-CK-28G + REP-1, REP-2). Histograms of the three CAL-CK dumps (run during the REP and P3 lifetimes and after them;
[`logs/CAL-CK-*/hist.txt`](logs/CAL-CK-28G/hist.txt)): 12 GiB 236,559,951 `ArrayList` + 236,558,886 `Object[2]` + one
`Object[236,557,360]` (902 MiB) = **98.3 %** of the shallow total; 18 GiB 354,838,633 + 354,837,535 + `Object[354,836,040]`
(1,354 MiB) = **98.8 %**; 28 GiB 532,256,651 + 532,255,593 + `Object[532,254,060]` (2,030 MiB) = **99.2 %**. The two REP
dumps were read for the thrower only (no histogram planned) and then deleted.

### 3.5 P3 — x86 replication of U5's PK condition (2G; not deciding)

Run 11:40–11:47 EST (≥ 45 min were left, so all nine lifetimes ran). `SELECT * FROM u5.pk WHERE a IN ? AND b IN ?`,
heap 2G, direct 15872M, W / G 300 / 300 s.

| Label | Arm | Request | K body B | Client | Latency s | JMX heap / old / old post-GC max MiB | Full GCs, max STW 60 s | Outcome | Thrower (hprof) |
|---|---|---|---|---|---|---|---|---|---|
| `T-PK-2G-1` | A | 16 × 500,000 (8M keys) | 4,000,171 | conn_closed | 50.5 | 1,949 / 1,949 / 1,949 | 47, 43 % | **OOM** +9.8 s, dump +35.1 s, `kill -9` +50.1 s | NTR: `SinglePartitionReadCommand.create:149` ← … ← `SinglePartitionReadQuery.createGroup:56` ← `SelectStatement.getSliceCommands` |
| `T-PK-2G-2` | A | 8M keys | 4,000,171 | conn_closed | 44.9 | 1,993 / 1,993 / 1,993 | 40, 0 % | **OOM** +10.5 s, dump +44.4 s, `kill -9` +44.5 s | **RMI TCP connection thread** (`TCPTransport.handleMessages:568`; the harness's JMX sampler connection); NTR thread in `Dispatcher.processRequest` at its `catch (Throwable)` block (the request had already failed) |
| `T-PK-2G-3` | A | 8M keys | 4,000,171 | conn_closed | 50.1 | 1,936 / 1,936 / 1,936 | 46, 43 % | **OOM** +9.1 s, dump +36.4 s, `kill -9` +49.7 s | NTR: same frames as T-1 |
| `M-PK-2G-1..3` | A | 1 × 500,015 | 4,000,171 | `0x1200` read timeout (0 responses) 3/3 | 5.02–5.03 | 704 / 87–94 / 0 | 0, 0 % | survived 3/3 | — |
| `I-PK-2G-1..3` | I | 8M keys | 4,000,171 | `0x2200 u5: IN cartesian product 16 x 500000 exceeds 2000000` 3/3 | 0.09–0.10 | 768–784 / 0 / 0 | 0, 0 % | survived 3/3 | — |

Holder in all three T-PK dumps ([`hist.txt`](logs/T-PK-2G-1/hist.txt)): 8,000,045 `PreHashedDecoratedKey`, 8,000,150
`LongToken`, 8,003,709 `HeapByteBuffer`, 8,000,980 `byte[14]`, two `Object[8,000,000]`, and 5,689,234–5,723,874
`SinglePartitionReadCommand` (+ as many `DataRange` / `Bounds`): ≈ 2,318 of 2,427–2,433 MiB shallow (≈ 95 %), the same
in T-PK-2G-2. **PK on x86: OOM 3/3 with the holder ≥ 50 % in every dump (counted under the §2 rule), strict
(thrower = NTR) 2/3; control 0/3 (read timeout, as U5's M-PK); intervention rejected 3/3.** As predicted (U5: OOM
3/3 in `SinglePartitionReadCommand.create`); this does not change the case verdict.

### 3.6 Cleanup and what is left

- Every process this session started on `pc91` is stopped (Cassandra JVMs ended by `OnOutOfMemoryError` / SIGTERM by
  the harness; samplers, watchers, clients, sequencers and parsers ended); checked 12:22 EST: no java, no harness
  python, no `seq.sh`.
- Left on `pc91`: **`/mydata/s4/r14/` 18 GB** — `runs/` 17 GB (full logs of every lifetime, two hprofs kept:
  `T-CK-8192M-1/cassandra-1795189825-pid158948.hprof` 14.5 GB and `T-PK-2G-1/cassandra-1795192787-pid179583.hprof`
  3.0 GB), `tree/` and `tree-I/` 419 MB each, `template-A/`, `node/` (last lifetime's data, 1.7 MB), `h/`, `cls/`,
  `patchwork/`. Ten hprofs (≈ 248 GB) were deleted after reading
  ([`logs/hprof-deleted.log`](logs/hprof-deleted.log)). `/mydata/s4/cassandra-base` untouched.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status (detail): **`verified-OOM · deployment`**, direction **unprotected
configuration** (the only control on the product, `in_select_cartesian_product_*`, ships at −1 and is skipped for every
client under the shipped `AllowAllAuthenticator`; when enabled it checks only after each column's product exists, U5
arm G), shape unprotected accumulation (one request's own expansion). Interpretation: configuration gap (an opt-in
guardrail, documented, off by default) plus a late-check implementation order; JIRA CASSANDRA-15250 (same shape on a
partition key) is still Open.

**Reason.** The pre-registered CK condition (8192M heap, shipped defaults, `pk = 0 AND c1 IN (160 values) AND c2 IN
(1,600,000 values)`, a 12,801,331-byte request against the 16 MiB message limit) reached `java.lang.OutOfMemoryError:
Java heap space` in **3/3** `T-CK-8192M` lifetimes at +37.1 / +44.5 / +46.8 s, each right after `Pause Full (G1
Humongous Allocation) 8033M->8032M(8192M)` with `Humongous regions: 39->39` (the `elementsList` array of capacity
157,704,907 could not grow to 236,557,360, a 902 MiB humongous array), followed by a complete heap dump and JVM exit by
`OnOutOfMemoryError` 3/3. **All three are counted** under the frozen rule (and the owner's ruling of 2026-11-20): the
dump shows the claimed holder at 97.5 % of the shallow total (157,707,500 `ArrayList` + 157,706,383 `Object[2]` + one
`Object[157,704,907]`; 7,821 of 8,032 MiB live at real object sizes) and the request thread in the build frames. **Strict
request-thread count: 3/3** — in every dump the only stored trace holding the error is `Native-Transport-Requests` in
`Arrays.copyOf` ← `ArrayList.grow` ← `MultiCBuilder$MultiClusteringBuilder.addEachElementToAll:359` ←
`INRestriction.appendTo:241` ← `ClusteringColumnRestrictions.valuesAsClustering:110` ← `SelectStatement.getSliceCommands:725`,
so the result meets the pre-registered rule and the stricter "OOM on the request thread" reading that kept U5 at
retry. The matched control (the same 1,600,160 values as 1 × 1,600,159, same bytes) returned 1 row **3/3** in 1.2–1.3 s
with old gen ≤ 636 MiB and no full GC; the pre-allocation intervention rejected the T request **3/3** in ≤ 0.18 s
(`u5: IN cartesian product 160 x 1600000 exceeds 2000000`, no full GC) and still served the M request (IM, 1 row). U
(GC log, hprof histogram) is measured independently of K (request bytes ≈ 12.8 MB, far below the 16 MiB message and
204.8 MiB per-IP in-flight limits): ≈ 7.8 GiB of live product per 12.8 MB request, ≈ 610×. The budget search showed the
same request-thread OOM at **12288M** (+59.0 s, 58 regions), **18432M** (+93.5 s, 86 regions) and **28672M** (+173.9 /
+180.4 / +168.3 s, 128 regions; **3/3**, the largest heap tested), each at the growth step the step-window model
predicted, with b_x86 = 211–226 MiB. Service loss (≥ 90 % STW over 60 s) was not met in any lifetime: on x86 the throw
comes before a spiral forms. P3 replicated U5's PK condition on x86 at 2 GiB (OOM 3/3, holder ≥ 50 % in each dump, strict
2/3 — one throw landed on the JMX sampler's RMI thread; control 0/3; intervention 3/3), not deciding.

**V1–V7 (condition CK, 8192M, arm A unless stated).**

| | Requirement | Evidence | Met |
|---|---|---|---|
| V1 Repetition | ≥ 3 runs reach the endpoint from clean starts | `T-CK-8192M-1..3`: counted OOM 3/3 (strict 3/3); also CAL-X-8G (not counted) | yes |
| V2 Matched control | nearest surviving control ≥ 3 runs, no endpoint | `M-CK-8192M-1..3`: 1 row 3/3, no full GC, no OOM | yes |
| V3 Measurement | U independent of K | GC log (old gen, humongous regions), hprof histograms of CAL-X-8G and T-1..3 (157.7M composites, 97 %), `Thread.print` at +2/+6 s and at the first humongous full GC; K = request bytes | yes |
| V4 Intervention | removes the endpoint ≥ 3 runs | `I-CK-8192M-1..3`: rejected before allocation 3/3, no OOM; `IM-CK-8192M`: useful work continues (1 row) | yes |
| V5 Initiating failure | first error with thread/stack + dump showing the holder | `stdout.ts` first `OutOfMemoryError` line; hprof trace of the thread holding the error = NTR in `addEachElementToAll:359`; histogram ([`logs/T-CK-8192M-1/`](logs/T-CK-8192M-1/)) | yes |
| V6 Default constraints | every constraint at its shipped default | `in_select_cartesian_product_*` −1, `partition_keys_in_select_*` −1, `AllowAllAuthenticator`, message/frame 16 MiB, in-flight heap-derived, 128 NTR threads, read timeout 5 s; yaml diff = directories only | yes |
| V7 Acceptable budget | heap/direct a deployment could run | heap 8192M (cassandra-env.sh's value for a 16 GiB node; ≥ 512 MiB standing rule), direct 15872M resolved; no container limit (scope only for isolation, no scope OOM). Largest failing heap tested: **28672M, 3/3** | yes |

**Per-condition status.**

| Condition | Status |
|---|---|
| CK, 8192M, 160 × 1,600,000 (deciding) | `verified-OOM · deployment` (counted 3/3, strict 3/3; control 0/3; intervention 3/3) |
| CK budget search 12288M / 18432M / 28672M | OOM on the request thread 1/1, 1/1, 3/3 (no control or intervention at those heaps; budget evidence) |
| PK, 2G, 16 × 500,000 (x86 replication of U5) | OOM 3/3 counted, strict 2/3; control 0/3; intervention 3/3 — agrees with U5's `verified-OOM · deployment` |

**Limits of attribution.** One node and one architecture (x86_64) for R14; U5's aarch64 results are not used as R14
controls. Control and intervention were run only at 8192M. 2048M and the automatic 31744M were not run by design
(the model puts them between windows: a spiral, as U5 saw); the endpoint at a given heap depends on which growth
step's window contains it, so "largest failing heap" means the largest one tested, with requests chosen to reach that
heap's window. The holder at 12/18/28 GiB is attributed from the GC log (old gen at L(s), the predicted humongous count)
and the thrower stack; the 12/18/28 GiB CAL dumps' histograms put the product at 98–99 % of the heap (REP dumps: thrower only). The intervention is a diagnostic patch (pre-allocation count check), not a shipped
setting; the shipped guardrail, when enabled, was shown by U5 (arm G) to enforce only after the product exists.

**CP pattern.** Covered by existing patterns: CP-8 (a limit that exists but ships off), CP-12 (one item, the requested
clustering set, materialized whole) and CP-11 (the guardrail, when enabled, checks after the allocation). No new
pattern needed.
