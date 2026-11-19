# U7 — in_select_cartesian_product: one UPDATE/DELETE with partition-key IN × clustering IN builds every row of the product on the coordinator heap  <!-- file: cassandra/cases/in_select_cartesian_product--modification-IN-product-row-build/in_select_cartesian_product--modification-IN-product-row-build.md -->

| Field | Value |
|---|---|
| Case ID | `U7` (unprotected accumulation / unprotected configuration; README "ID prefixes") |
| From | `OC-366` of the phase 1 OOM candidate list (cluster of one row; primary OC-366) |
| Phase-1 case file | [`none-validatekey-key_remaining--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/none-validatekey-key_remaining--autonomous.md); stage 4: none |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built tree `ms0625:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`, not a git checkout), OpenJDK 11.0.33 aarch64, Ubuntu 22.04.1, kernel 5.15.0-191 |
| Stage 1 (design) | OOM-agent stage-1 session (workflow, wave 4), 2026-11-18 13:40–14:20 America/New_York |
| Stage 2 (verify) | fresh OOM-agent session 2026-11-18 13:49 EST until the wave was suspended; resumed by a second fresh session 18:21–19:55 EST (§3.2 item 6) |
| Verdict | **true positive** — `verified-OOM · deployment` (2 GiB; largest OOM budget 4 GiB 3/3; 8 and 16 GiB: GC service loss without OOM within the caps) |

## Summary

- **Conclusion (stage 2):** **true positive**, `verified-OOM · deployment`. One prepared UPDATE of 176 KB (P 2,000 × Q 20,000) ends in `OutOfMemoryError: Java heap space` at a 2 GiB heap with every capacity at its shipped default, 3/3 (DELETE form 3/3); the matched controls survive 0/3 and the guardrail intervention removes it 3/3. See §4.
- **Hypothesis under test (stage 1):** a single prepared `UPDATE u7.t SET v = ? WHERE k IN ? AND c IN ?` (or the
  matching `DELETE`) with bound lists of P partition keys and Q clusterings makes the coordinator build all P × Q rows
  (P `PartitionUpdate`s of Q rows each) on its heap inside one Native-Transport-Requests task before anything is applied
  (`ModificationStatement.java:739-750`, `:790-816`). The only control whose contract covers the product,
  the `in_select_cartesian_product` guardrail, ships disabled (−1) and is skipped for superusers (every client under the
  default `AllowAllAuthenticator`); when enabled it checks P and Q separately, never P × Q. `max_mutation_size` bounds each
  of the P mutations, not their number, and runs after the build; the native in-flight limits charge the ≈ 8 B per bound
  value on the wire. One request of ≈ 176 KB (P 2,000 × Q 20,000 = 4 × 10⁷ rows ≈ 3.6–6.4 GB) is predicted to end in
  `OutOfMemoryError: Java heap space` at a 2 GiB heap with every capacity at its shipped default, and a ≈ 480 KB request
  at every heap up to the node's own auto-sized 31,744 MiB.
- **Root cause (claimed):** no byte or count bound applies to the rows a modification statement's IN product expands to;
  the bound that exists is off by default and, when on, has per-side (SELECT-shaped) scope.

## 1. Candidate

**The cluster (one row), quoted from
`capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md`, status as handed to this session:**

> | OC-366 | 2026-11-18 | `none-validatekey-key_remaining--autonomous` | guided | An UPDATE or DELETE with IN on partition-key and clustering columns expands to (product of the partition-key IN lists) mutations x (product of the clustering IN lists) rows each. [details](runs/wave2.md#oc-366) | CP-2, CP-8, CP-11, CP-13, CP-1 | picked: U7 |

**Full text** (the task pointed to `runs/wave3.md`; the row's link and the text are in `runs/wave2.md#oc-366`):

> An UPDATE or DELETE with IN on partition-key and clustering columns expands to (product of the partition-key IN lists)
> mutations x (product of the clustering IN lists) rows each. All of it is built in memory before anything is applied.
> ModificationStatement.getMutations builds every key (buildPartitionKeyNames), loops validateKey / decorateKey per key,
> adds a row for each clustering in createClustering's set to a PartitionUpdate.Builder per key, and then calls
> collector.toMutations. No count limit applies: the in_select_cartesian_product guardrail is off (-1) and is checked after
> the product is built. max_mutation_size bounds each mutation, not their number. The native in-flight limits charge the
> small request bytes, not the expansion. The mutations then stay referenced until the write completes or times out.
> Holder: the coordinator heap (mutations, rows and per-replica message copies). Size: bound lists of 10,000 partition
> keys x 10,000 clusterings (a request of about 200 KB) give 10,000 mutations of about 200 KB each (each under
> max_mutation_size) and 10^8 row objects, about 10-15 GB of heap from one statement, even with shared tiny values. Same
> root, the unguarded IN expansion, as none-queryprocessor-validatekey-key_remaining--autonomous (SELECT side).
>
> **Where:** src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java:369-377, :739-750, :796-818;
> src/java/org/apache/cassandra/cql3/Validation.java:47-51; src/java/org/apache/cassandra/db/MultiCBuilder.java:339-358

**Triage row** (`runs/triage-2026-11-18.md`, rank 5): "An UPDATE or DELETE with pk IN and ck IN builds the full
mutations-by-rows product on the coordinator heap before max_mutation_size, which applies per mutation, is checked, and the
mutations stay referenced until the write completes. 10,000 x 10,000 bound values (a request of about 200 KB) gives 1e8
rows, about 10-15 GB, and 2,000 x 2,000 (about 0.6-1 GB) with a few concurrent requests already passes a 2 GiB heap." —
Overlaps: "Write-side twin of OC-412 (same unguarded IN expansion), with OC-352 and OC-276 (batch form). Partly overlaps
B14 … but a single statement is enough here." Note 5: "OC-412, OC-366, OC-409 and OC-278 depend on the superuser and
AllowAll defaults, where guardrails are skipped, but they are off at -1 anyway."

**Coverage of the cluster.** The design covers OC-366 in full: the UPDATE form (arms T, L, M, I, IA, search) and the
DELETE form (arm D), single-column partition-key IN × single-column clustering IN; the per-mutation `max_mutation_size`
claim (every mutation of T is ≈ 0.2–0.4 MB); the in-flight claim (K measured). Not covered: (a) **composite** keys, where
the product is also taken within each side (`MultiCBuilder.addEachElementToAll`, `:339-358`) — the same row-building loop,
so a single-column table is enough to test the holder; (b) the "per-replica message copies" in the holder — on one node
with RF 1 nothing is serialized to peers, and the OOM is predicted before any mutation leaves `getMutations`; (c) the
"stay referenced until the write completes" leg (the build alone is predicted to exhaust the heap). Rows outside this
cluster and not covered: OC-412 (SELECT side, case U5 of this wave), OC-351/OC-365 (composite partition-key IN on reads),
OC-352/OC-276 (batch form). Stage-1 correction to the row: the guardrail is **not** checked after the product is built —
it is checked per restriction set on `buildSize()` before `build()` (`PartitionKeySingleRestrictionSet.java:95-96`,
`ClusteringColumnRestrictions.java:112-113`), but per side (P, then Q), so it never sees P × Q.

**Phase-1 case (stage 3, 2026-10-27).** `Validation.java:47` is an emptiness check (`key.remaining() == 0`) next to the
fixed 65,535-byte key-length bound (`:51`); estimate `negative` ("does not limit the number of keys, rows or partitions").
The stage-5 agent used that observation — the per-key validation in `addUpdates` runs once per key with nothing counting
keys × clusterings — to file OC-366. Stage 4: none.

**JIRA prior art (read only; nothing posted).** Survey file `jira-oom-survey.csv`: CASSANDRA-15250 ("Large cartesian
produces in IN queries cause the server to run out of memory", **Open/Unresolved**, 2019; a 9-column partition-key IN
SELECT of 10⁹ combinations sends the server into a GC spiral; survey: "unprotected configuration at defaults, guardrail
added later (CASSANDRA-17187) but off by default"); CASSANDRA-9454 (Duplicate, multi-partition IN warn → guardrail
17186). JIRA REST search 2026-11-18 (issues.apache.org reachable): `project = CASSANDRA AND text ~ "cartesian"` → 12 hits:
15250 (Open), 17187 ("Guardrail for SELECT IN terms and their cartesian product", Fixed 4.1; its description names only
SELECT, thresholds default −1), 17147/17153/19553/20778/20749 (guardrail plumbing), others unrelated;
`text ~ "in_select_cartesian_product"` → 10 hits, same set; `summary ~ "guardrail" AND text ~ "cartesian" AND (UPDATE |
DELETE | modification)` → 4 hits, none about modifications; `summary ~ "IN" AND (delete | update | modification) AND
(memory | OOM)` → 0; `summary ~ "partition keys" AND summary ~ "IN" AND (update | delete | batch)` → 0.
**Verdict:** the SELECT form is **`known-open`** (15250); the guardrail meant to cover it is **documented** as off by
default (`cassandra.yaml:2101-2105`). The write form — one UPDATE/DELETE building P × Q rows, and the guardrail's per-side
scope that never bounds P × Q even when enabled — is **`new`** (no report found). Not a known-fixed bug, so this is not a
positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

Native-Transport-Requests (NTR) thread, one prepared EXECUTE of
`UPDATE u7.t SET v = ? WHERE k IN ? AND c IN ?` with v = 1, k = list of P ints, c = list of Q ints:

1. **Decode** (event loop): the request body is ≈ 8 B per bound list element (4 length + 4 int) ≈ 8·(P + Q) + 60 B; it is
   charged to the native in-flight limits as wire bytes (`AbstractMessageHandler`, global `heap/10`, per IP `heap/40`,
   `DatabaseDescriptor.java:649-656`). One request of 176 KB is ≈ 0.08 % of the global limit at 2 GiB.
2. **Guardrails** at `ModificationStatement.execute` (`:491-503`): `writeConsistencyLevels` only. `validateDiskUsage`
   (`:517`, `:285-300`) is off (disk-usage guardrail −1).
3. **Keys** — `getMutations` (`:739-750`) → `buildPartitionKeyNames` (`:369-377`) → `StatementRestrictions.getPartitionKeys`
   → `PartitionKeySingleRestrictionSet.values` (`:89-101`): `MultiCBuilder` of P keys; the guardrail
   `in_select_cartesian_product` is consulted at `:95-96` **only if** `Guardrail.enabled(state)` (`Guardrail.java:93-96`:
   daemon initialised and `state.isOrdinaryUser()`); under `AllowAllAuthenticator`, `ClientState.isSuper()` is true for
   every client (`ClientState.java:602-605`, `requireAuthentication()` false), so it is skipped; its thresholds are −1
   anyway (`Config.java:877-878`). `QueryProcessor.validateKey` per key (`:374-375`).
4. **Clusterings** — `createClustering` (`:379-386`) → `ClusteringColumnRestrictions.valuesAsClustering` (`:105-118`): a
   `NavigableSet` of Q `Clustering`s, built once and shared by all keys; guardrail consulted on Q alone (`:112-113`).
5. **The product** — `addUpdates` (`:753-818`), non-slice branch (`:790-816`): for each of the P keys,
   `Validation.validateKey`, `decorateKey`, `collector.getPartitionUpdateBuilder` (`SingleTableUpdatesCollector.java:79-90`,
   one `PartitionUpdate.Builder` per key kept in `puBuilders`), then for each of the Q clusterings `clustering.validate()`
   and `UpdateStatement.addUpdateForKey` (`UpdateStatement.java:64-95`): `params.newRow`, `Constants.Setter` →
   `UpdateParameters.addCell` (`:159-175`, a new `BufferCell` referencing the one bound `v` buffer), `params.buildRow()`
   (`BTreeRow.Builder.build`, `BTreeRow.java:919-936`: a new `BTreeRow` + a one-cell `Object[]`), `updateBuilder.add` (a
   slot in the builder's `BTree.Builder`). For `DELETE FROM u7.t WHERE k IN ? AND c IN ?`: `DeleteStatement.java:75-80`
   (`newRow`, `addRowDeletion` → a new `Row.Deletion` per row, `UpdateParameters.java:129-138`, `buildRow`). **All P × Q
   rows are live at once in `puBuilders`**; nothing between rows counts them.
6. **After the build** — `toMutations` (`SingleTableUpdatesCollector.java:97-117`) builds each `PartitionUpdate`, then
   `validateIndexedColumns` and `validateSize` (`:111-112`, `max_mutation_size` per mutation). Then
   `StorageProxy.mutateWithTriggers` (`ModificationStatement.java:529`) applies the P mutations (commit log, memtable).

The claimed holder is the step-5 row set: ≈ (BTreeRow 40 B + BufferCell 40 B + one-cell `Object[]` 24 B + builder slot
4–8 B) ≈ 108–112 B per UPDATE row and ≈ (40 + `Row.Deletion` 16 + slot 4–8) ≈ 60–64 B per DELETE row (compressed oops,
16-byte headers rounded; error band below). The request is one task on one NTR thread; the memory it builds is
proportional to P × Q while the bytes any control sees are proportional to P + Q.

- **Direction (fixed before readings, by the protocol's "Unprotected results"):** **unprotected configuration**
  (`in_select_cartesian_product_*_threshold` −1 at default; guardrails skipped for the default superuser) **+ unprotected
  accumulation** (no byte/count bound on the rows a modification's IN product expands to; the in-flight control's contract
  is wire bytes and does not claim this memory, so U > C_inflight is not scored as a bypass of it). Interpretation to state
  at stage 2: validation/configuration gap (guardrail off by default; SELECT-shaped per-side scope), the SELECT form
  known-open upstream (15250). The workload is within documented guardrails and protocol limits: a prepared statement, two
  list markers, a request ≤ 0.5 MB.
- **Technique note:** [`bypass-playbook.md`](../../../bypass-playbook.md) only for the matched-payload control (same wire
  bytes, different product); the dial search follows the protocol's "Design and execution" items 3–4.

### 2.2 Protection map

| Domain | Holder (allocation → release) | Counter (K) | Limit (C), shipped default | At the limit |
|---|---|---|---|---|
| **Built rows of one modification** (claimed) | `BTreeRow` + `BufferCell` (or `Row.Deletion`) + cell `Object[]` + builder slots per (key, clustering), in `SingleTableUpdatesCollector.puBuilders` (`ModificationStatement.java:790-816`) → garbage after the write returns or the request fails | none (no counter of rows or bytes) | none applies. The guardrail `in_select_cartesian_product` (fail −1, `Config.java:878`; yaml `:2104-2105` "defaults to -1 to disable") would cap P and Q **separately** (`PartitionKeySingleRestrictionSet.java:95-96`, `ClusteringColumnRestrictions.java:112-113`), and only for ordinary users (`Guardrail.java:93-96`) | — (Java heap OOM predicted) |
| Native request in flight | the decoded request (P + Q + 1 `HeapByteBuffer`s, ≈ 72 B each) until the response | per-connection queue + per-IP / global reserves = **wire bytes** (gauge `org.apache.cassandra.metrics:type=Client,name=RequestsSize`) | global heap/10, per IP heap/40 (`DatabaseDescriptor.java:649-656`); queue 1 MiB (`native_transport_receive_queue_capacity`) | connection paused |
| Request size | one message | body bytes | `native_transport_max_message_size` = 16 MiB at heap ≥ 640 MiB (`DatabaseDescriptor.java:903-905`) | message refused |
| Mutation size | each of the P built mutations | serialized size | `max_mutation_size` = ½ × `commitlog_segment_size` 32 MiB = 16 MiB (`DatabaseDescriptor.java:898-899`), checked **after** the whole build (`SingleTableUpdatesCollector.java:112`) | `MutationExceededMaxSizeException` |
| Values per list | — | count | protocol: a list value is one `[bytes]` ≤ the message size; no element-count limit in CQL (`MultiCBuilder` has none) | — |
| Executing requests | NTR pool | active tasks | `native_transport_max_threads` 128 (`Config.java:283`) | queued (one request here) |
| Memtable | applied rows (`heap_buffers`) | pool bytes | `memtable_heap_space` heap/4; flush at cleanup threshold 1/3 | flush / writers block (not reached in T: the OOM is predicted inside step 5) |
| Heap budget | JVM heap | — | `-Xmx` 2 GiB, search 4 / 8 / 16 GiB and auto 31,744 MiB | `OutOfMemoryError: Java heap space` → shipped `-XX:+HeapDumpOnOutOfMemoryError` (`jvm-server.options:120`) and `-XX:OnOutOfMemoryError=kill -9 %p` (`cassandra-env.sh:209`) |
| Direct budget | Netty frames | JMX `java.nio:type=BufferPool,name=direct` | auto `MaxDirectMemorySize` 15,872 MiB on this node | not the endpoint; recorded only |

Not on the path at defaults (checked): `partition_keys_in_select` (SELECT only, `SelectStatement.java:722`),
disk-usage guardrail (off), user-timestamp guardrail (no `USING TIMESTAMP`), triggers (none), MV/indexes (none on `u7.t`),
read-before-write (`requiresRead` false for `SET v = ?`), tracing/audit/FQL (off), rate limiting (off).

### 2.3 Configuration and budget audit

- **Build:** copy `ms0625:/mydata/s4/cassandra-base` (205 MB; md5 `conf/cassandra.yaml` `714ee9bf58b3bc1710377ac16bcbba03`,
  `conf/jvm11-server.options` `fbad82a853f1b85aea0fa5ea34b6d1bf`, `conf/cassandra-env.sh`
  `8be0588e87c594a03360751b1dbf4fbf`, `conf/jvm-server.options` `26a957bf004efa3b3d91285fb0975750`, read-only check
  2026-11-18 13:45 EST) with `cp -a` to `/mydata/u7/cassandra`; never touch the shared tree. No patch, no rebuild.
- **Configuration (test, control, search, D arms):** the shipped `conf/` unchanged: single node on `127.0.0.1`, data and
  commit log under the copy's `data/`, `memtable_allocation_type: heap_buffers`, `authenticator: AllowAllAuthenticator`,
  `authorizer: AllowAllAuthorizer`, `role_manager: CassandraRoleManager`. Every constraint in §2.2 at its shipped default
  (V6): `in_select_cartesian_product_warn/fail_threshold` −1/−1, `partition_keys_in_select_*` −1, `max_mutation_size`
  derived 16 MiB, `commitlog_segment_size` 32 MiB, `native_transport_max_message_size` derived 16 MiB,
  `native_transport_max_request_data_in_flight` heap/10, `…_per_ip` heap/40, `native_transport_receive_queue_capacity`
  1 MiB, `native_transport_max_threads` 128, `memtable_heap_space` heap/4, `write_request_timeout` 2 s,
  `native_transport_timeout` 12 s.
- **Intervention conf `conf-i`** (copy of `conf/`): `authenticator: PasswordAuthenticator` (replacing line 198) and one
  appended line `in_select_cartesian_product_fail_threshold: 1000`. **Attribution conf `conf-a`**: only the authenticator
  change. **Diagnostic conf `conf-g`** (optional arm G): `conf-a` + `in_select_cartesian_product_fail_threshold: 5000`.
  The guardrail value is a capacity change allowed in intervention/diagnostic arms (V6); the authenticator is a supporting
  deviation needed because guardrails never apply to superusers.
- **Resolved values to record per run** (from `system.log`'s config line and `jcmd VM.flags`): at 2 GiB in-flight global
  214,748,364 B / per IP 53,687,091 B, memtable 512 MiB, max message 16,777,216 B; at 4 / 8 / 16 GiB: heap/10, heap/40,
  heap/4 accordingly; auto: heap 31,744 MiB (`cassandra-env.sh:54-62`, G1, MemTotal 65,791,808 kB → ½ RAM 32,124 MiB >
  31,744), direct 15,872 MiB (`:62`; the same 15,872 MiB with a hand-set heap, `:139-158`).
- **Environment (not capacity):** `MAX_HEAP_SIZE=<heap>` (unset for the auto run), `HEAP_NEWSIZE` unset (G1, `-Xms = -Xmx`),
  `CASSANDRA_HEAPDUMP_DIR=<run dir>`, `ulimit -n 100000`, `systemd-run --user --scope -p MemorySwapMax=0` (swap off for the
  measured process; **no `MemoryMax`**: no container budget); `sudo loginctl enable-linger jason92` at start (Linger is
  `no` now) and `disable-linger` at the end. GC log: the shipped `-Xlog:gc=info,heap*=trace,…` to `logs/gc.log`
  (`cassandra-env.sh:83`); G1 with `G1HeapRegionSize=16m`, `AlwaysPreTouch` (shipped). **Search runs ≥ 8 GiB only:**
  `JVM_EXTRA_OPTS=-XX:-HeapDumpOnOutOfMemoryError` (disk, see §2.5; instrumentation-only deviation, recorded).
- **Node claimed (V7):** `ms0625` (Utah m400, **aarch64**, 8 cores, MemTotal 65,791,808 kB, 8 GiB swap present,
  `/mydata` 39 GiB with 29 GiB free, cgroup v2; no Java running; other folders `/mydata/b8`, `/mydata/u1r2`,
  `/mydata/oom-smoke`, `/mydata/s4/cassandra-base` present and **not to be touched**; read-only check 2026-11-18
  13:43–13:50 EST). **Budgets:** heap 2 GiB (ideal) for V1–V4, search 4 → 8 → 16 GiB → the node's own auto heap
  31,744 MiB; all ≥ 512 MiB, so V7 is met by the standing rule without per-case review. Direct: auto 15,872 MiB (not the
  endpoint). No container limit is a budget, so no owner review is needed. ARM: never pool these runs with x86 runs.

### 2.4 Ceiling arithmetic

- **Contract capacities + baseline (2 GiB):** in-flight ≤ 214.7 MB of wire bytes (the decoded request of T is ≈ 22,001 ×
  72 B ≈ 1.6 MB), memtable ≤ 512 MiB, baseline live heap of an idle 5.0.9 on m400 ≈ 250–400 MiB ⇒ Σ ≈ 1.0–1.15 GiB
  < 2 GiB. **Every bounded pool full cannot OOM a 2 GiB heap; an OOM needs the uncovered row set.**
- **Row cost r** (estimate, compressed oops): UPDATE 108–112 B, DELETE 60–64 B; error band used for predictions:
  UPDATE 90–160 B, DELETE 55–100 B (unknowns: builder growth slack, G1 region fragmentation, JIT-scalar-replacement none).
- **Free heap at 2 GiB** ≈ 2,048 − baseline 250–400 MiB − ≈ 5 % G1 slack ≈ 1.55–1.7 GiB ⇒ **rows at OOM**: UPDATE
  ≈ 1.0–2.0 × 10⁷, DELETE ≈ 1.7–3.3 × 10⁷.

| Arm | Statement | P × Q (rows) | Wire body | Predicted live rows needed | vs budget |
|---|---|---|---|---|---|
| T (test) | UPDATE | 2,000 × 20,000 = 4 × 10⁷ | ≈ 176,060 B | 3.6–6.4 GB | 2 GiB: ≥ 2× the upper rows-at-OOM ⇒ OOM after ≈ 500–1,000 of the 2,000 keys |
| L (control, low product) | UPDATE | 100 × 20,000 = 2 × 10⁶ | ≈ 160,060 B | 0.18–0.32 GB | 2 GiB: ≤ 20 % of free heap ⇒ survives |
| M (control, matched wire) | UPDATE | 1 × 21,999 = 21,999 | ≈ 176,060 B (= T) | ≈ 2–4 MB | survives |
| D (DELETE) | DELETE | 4,000 × 20,000 = 8 × 10⁷ | ≈ 192,060 B | 4.4–8.0 GB | 2 GiB: ≥ 2.4× ⇒ OOM |
| S (search) | UPDATE | 40,000 × 20,000 = 8 × 10⁸ | ≈ 480,060 B | 72–128 GB | ≥ 2.2× the auto heap 31,744 MiB ⇒ OOM at every searched budget |
| I (intervention) | UPDATE = T, ordinary role, guardrail 1,000 | rejected at P = 2,000 > 1,000 | = T | ≈ 0 | survives |
| G (diag., optional) | UPDATE, ordinary role, guardrail 5,000 | 5,000 × 5,000 = 2.5 × 10⁷ (each side = 5,000 passes) | ≈ 80,060 B | 2.3–4.0 GB | 2 GiB: OOM despite the enabled guardrail |

Every T mutation has Q = 20,000 rows ≈ 0.2–0.4 MB serialized (int clustering + one int cell, ≈ 10–20 B/row) ≪ 16 MiB,
and S's are the same, so `max_mutation_size` would pass each of them even if the build completed. U/K for T at OOM ≈
1.6 GB / 176 KB ≈ 9,000×.

### 2.5 Workload, environment and harness

Work dir `/mydata/u7` on `ms0625` (run data, logs, dumps on local disk, never NFS): `/mydata/u7/cassandra` (copy),
`/mydata/u7/conf-i`, `conf-a`, `conf-g`, `/mydata/u7/harness`, `/mydata/u7/runs/<run-id>`. Harness source in
`<case folder>/harness/` (synced to the node; call scripts with `bash`/`python3 -I`). Reuse from B14
(`../batch_size_fail_threshold--single-partition-batch-heap-expansion/harness/`): `Jmx.java` (JMX poller; compile with
the node's `javac`), `hprof-histo.py` and `hprof_oome_thread.py` (dump histogram and OOME thread stack), the `run.sh` /
`monitor.sh` skeleton (pre-flight checks, `setsid nohup systemd-run --user --scope -p MemorySwapMax=0`, start wait,
`VM.flags`, resolved-config grep, disk guard, stop, `summarize.py`).

- **Client `u7.py`** (Python 3.10, the tree's bundled driver: `sys.path.insert(0,
  "<tree>/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0")`, import checked on ms0625 2026-11-18;
  `protocol_version=4`, `WhiteListRoundRobinPolicy(['127.0.0.1'])`, `token_metadata_enabled=False`,
  `PlainTextAuthProvider` only for conf-i/a/g):
  - `ddl`: `CREATE KEYSPACE u7 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
    `CREATE TABLE u7.t (k int, c int, v int, PRIMARY KEY (k, c))`. For conf-i/a/g, as `cassandra/cassandra` (retry login
    for ≤ 60 s: default superuser appears after `cassandra.superuser_setup_delay_ms` 10 s), also
    `CREATE ROLE u7 WITH PASSWORD = 'u7pw' AND LOGIN = true AND SUPERUSER = false` (AllowAllAuthorizer: no grants).
  - `send --kind {update|delete} --p P --q Q [--k0 K0] [--user u7]`: prepare
    `UPDATE u7.t SET v = ? WHERE k IN ? AND c IN ?` (or `DELETE FROM u7.t WHERE k IN ? AND c IN ?`), bind `1` (UPDATE
    only), `list(range(K0, K0+P))`, `list(range(Q))`; one `execute(..., timeout=1800)` at CL ONE; log `t_send`, `t_end`
    (epoch ms), outcome (OK / exception class + message), computed wire body bytes.
  - `count --k K`: `SELECT count(*) FROM u7.t WHERE k = K`.
- **`run.sh <run-id> <conf: base|i|a|g> <heap: 2G|4G|8G|16G|auto> <step> [<step> …]`**, a step being
  `kind:P:Q:K0[:user]`: abort if any `CassandraDaemon` runs, ports 7000/7199/9042 busy, or `/mydata` free < heap + 6 GiB
  (auto: no dump, free ≥ 8 GiB); fresh `data/` and `logs/`; start; wait ≤ 300 s for "Starting listening for CQL clients";
  record `VM.flags`, `VM.command_line`, resolved config lines, conf md5s; `ddl`; start monitors; **20 s baseline**; run the
  steps sequentially, each to completion or daemon exit; for a surviving step wait 15 s and `count` keys K0 and
  K0+P−1; per-run cap after the first send: 10 min (2–8 GiB), 25 min (16 GiB, auto) — at the cap, if the daemon is alive,
  record it and stop it (`kill`, then `kill -9` after 60 s); collect `system.log*`, `gc.log*`, stdout; `summarize.py`.
- **Disk:** a 2 GiB dump ≈ 2 GB, 4 GiB ≈ 4 GB. After a dump is parsed (histogram + OOME thread to `<run dir>/hprof-*.txt`)
  delete it, except T-1's, kept until the end of the session and then deleted. Search runs ≥ 8 GiB run without a dump
  (above). Stop starting runs if `/mydata` free < 10 GiB.

| Run id | Conf | Heap | Steps | Reps | Purpose |
|---|---|---|---|---|---|
| S0 | base | 2G | `update:10:10:0` | 1 | shakedown, not a reading: statement accepted, `count` = 10 for k 0 and 9 |
| CAL | base | 2G | `update:10:20000:0`, `update:50:20000:100`, `update:100:20000:200`, `update:200:20000:400`, `update:400:20000:800` | 1 | dial calibration: per-step latency, rows/s, post-GC heap rise per row (r); all steps predicted to survive (8 × 10⁶ rows ≈ 0.7–1.3 GB, the last one may fail at the band's top — record, do not repeat) |
| T-1..3 | base | 2G | `update:2000:20000:0` | 3 | V1 |
| L-1..3 | base | 2G | `update:100:20000:0`, then `update:1:21999:5000` (M) | 3 | V2 (L: nearest surviving low product; M: matched wire bytes) |
| I-1..3 | i | 2G | `update:2000:20000:0:u7`; I-1 also `update:1000:1000:10000:u7` ×2 (K0 10000, 11000) | 3 | V4 (rejection, heap flat; I-1: useful work in guardrail-sized chunks) |
| IA-1 | a | 2G | `update:2000:20000:0:u7` | 1 (3 if time) | attribution: the authenticator change alone does not stop the OOM |
| B4, B8, B16, BA | base | 4G, 8G, 16G, auto | `update:40000:20000:0` | 1 each | V7 upward search for the largest failing budget |
| D-1..3 | base | 2G | `delete:4000:20000:0` | 3 | the DELETE form |
| R-1, R-2 | base | largest failing budget of the search | as that search run | 2 | brings the largest failing budget to 3/3 |
| G-1 | g | 2G | `update:5000:5000:0:u7` | 1, optional | diagnostic: the enabled guardrail's per-side scope does not bound P × Q |

### 2.6 Instruments (U independent of K)

- **K:** JMX `Client.RequestsSize` (bytes in flight) and `Client.PausedConnections`, every 2 s; plus the client's computed
  wire body bytes per step.
- **U (independent of K):** (a) the GC log: post-GC heap occupancy for every GC during the step; U_peak = max post-GC
  occupancy during the step − the last post-GC occupancy of the baseline; (b) `jcmd GC.heap_info` + `RssAnon` every 2 s
  (non-forcing); (c) at OOM, the heap dump: `hprof-histo.py` counts and shallow bytes of `BTreeRow`, `BufferCell`,
  `Row$Deletion`, `Object[]`, `PartitionUpdate$Builder`, `BTree$Builder` — rows built ≈ count(`BTreeRow`) and r = their
  bytes / count; `hprof_oome_thread.py`: the thread and stack that threw. For search runs without a dump: one single-shot
  `jcmd <pid> GC.class_histogram` (forces a full GC; recorded as a deviation) at the first `heap_info` sample with used
  ≥ 75 % of max, and the GC log.
- **Attribution:** `jcmd Thread.print` every 5 s, recording the top frames of every `Native-Transport-Requests` thread
  (predicted: `ModificationStatement.addUpdates` / `UpdateStatement.addUpdateForKey` / `BTreeRow$Builder.build`, or
  `DeleteStatement.addUpdateForKey`).
- **Other:** JMX NTR `ActiveTasks`/`PendingTasks`, MutationStage `PendingTasks`, `u7.t` `AllMemtablesHeapSize`,
  `java.lang:Memory HeapMemoryUsage`, `java.nio:BufferPool direct MemoryUsed` (2 s); `df /mydata` (10 s); the endpoint lines
  in `stdout.txt` (`java.lang.OutOfMemoryError`, `Dumping heap`, `Executing … kill -9`); client outcome per step.

### 2.7 Predicted response and stopping budget

- **T (2 GiB):** after the send, heap rises steadily on one NTR thread (stack in `addUpdates`), K ≤ 0.2 MB throughout,
  no `RequestsSize` growth, no MutationStage activity (nothing applied); `OutOfMemoryError: Java heap space` within
  ≤ 5 min of the send, dump written, process killed by `OnOutOfMemoryError`; the client gets a connection error. Histogram
  `BTreeRow` ≈ `BufferCell` ≈ 1.0–2.0 × 10⁷ (≥ 70 % of the dump's shallow bytes in row objects + `Object[]`); `count` for
  k = 0 is not readable (node dead). **Predicted 3/3.**
- **L (2 GiB):** completes (OK, or a `WriteTimeout` after 2 s with rows landing — both are "no OOM"); U_peak
  ≈ 0.18–0.32 GB; `count` = 20,000 for k 0 and 99. **M:** completes, U_peak ≲ 10 MB, `count` = 21,999 for k 5000.
  **Predicted 0/3 OOM** each.
- **I (2 GiB):** `InvalidRequest` "Guardrail in_select_cartesian_product violated: … on partition key produces 2000
  values, this exceeds failure threshold of 1000" within < 1 s; heap flat (U_peak < 10 MB); node alive; I-1's two
  1,000 × 1,000 steps complete (or time out with rows landing; `count` = 1,000). **Predicted 0/3 OOM.**
- **IA:** as T (OOM). If IA survives, the intervention's attribution fails and the case is `retry` for V4.
- **D (2 GiB):** as T with `DeleteStatement.addUpdateForKey`, rows at OOM ≈ 1.7–3.3 × 10⁷, `Row$Deletion` ≈ `BTreeRow`.
  **Predicted 3/3.**
- **Search:** OOM at 4, 8, 16 GiB and at the auto 31,744 MiB, the time to OOM growing roughly with the heap (CAL's rows/s
  gives the estimate; if the estimate for BA exceeds 25 min, skip BA and report 16 GiB as the largest tested). The largest
  failing budget is predicted to be the node's own auto heap, i.e. a fully default deployment.
- **G (optional):** OOM as T: both sides at 5,000 pass a 5,000 fail threshold (`MaxThreshold` fails only above it).
- **Readings that would refute:** T or D survive with rows built ≥ 2× the predicted rows-at-OOM (→ r far below the band,
  re-check); a rejection by another check before the build (→ invalid path, `retry`); a `MutationExceededMaxSizeException`
  (→ the per-mutation claim is wrong); OOM in L/M (→ V2 unmet).
- **Stopping budget:** per run as in §2.5; no new run starts after **17:40 America/New_York**; all processes stopped,
  dumps deleted and linger disabled by **18:00**; hard deadline 18:07. No escalation after an OOM beyond the planned search.

### 2.8 Controls and intervention

- **Matched control (V2):** L ×3 — same statement, build, budget and table; the product is the only dial (20× smaller),
  ≥ 30 % margin (predicted ≤ 20 % of the free heap). M (in the same runs, after L) — the **same wire bytes and the same
  in-flight charge as T**, product 1 × 21,999: isolates the expansion from the request size.
- **Causal intervention (V4):** I ×3 — bound the multiplicity before the build with the existing guardrail (fail
  threshold 1,000 for an ordinary role). Record the rejection rate (1/1 of T sends) and the useful work still possible
  (I-1: two 10⁶-row requests). IA ×1 (×3 if time) separates the authenticator change from the guardrail. The guardrail
  bounds P ≤ X and Q ≤ X, so rows ≤ X² (10⁶ at X = 1,000); G-1 (optional) shows the bound is per side.

### 2.9 Time plan (America/New_York, 2026-11-18; stage 2 assumed to start ≈ 14:30)

| Window | Work | Est. |
|---|---|---|
| 14:30–15:00 | read, hash check, node check, copy tree, confs, harness, compile `Jmx.java`, S0, CAL | 30 min |
| 15:00–15:15 | T-1..3 (≈ 1 min start + 0.5 min baseline/DDL + ≤ 5 min to OOM + 1 min dump/parse) | 15 min |
| 15:15–15:30 | L-1..3 (+M) | 15 min |
| 15:30–15:50 | I-1..3, IA-1 | 20 min |
| 15:50–16:50 | B4, B8, B16, BA (BA: ≈ 1 min pre-touch + fill + full GCs; ≤ 25 min cap) | 60 min |
| 16:50–17:10 | D-1..3 | 20 min |
| 17:10–17:40 | R-1, R-2 at the largest failing budget; G-1 if time | 30 min |
| 17:40–18:00 | stop everything, delete dumps, disable linger, fill §3–§4, write-back | 20 min |

**Priority if late** (drop from the end): G-1, R-1/R-2, IA-2/3, BA, D-2/3, B16. V1–V4 at 2 GiB (T, L/M, I, IA-1) come
first and must not be dropped. Nothing stays running on `ms0625`; `/mydata/u7` keeps only small logs (no dumps, no data
directory) at the end.

`sha256 of §1–§2 at freeze: e73f760a3753d1f4f614d819d4120cfc24b8c4cb53b5887ddd9c94cbb4afaf4d` (computed over the lines from `## 1. Candidate` up to, not including, this line) ·
amendments after the freeze: none.

## 3. Runs (stage 2)

Stage-2 OOM-agent session (fresh; workflow wave 4), 2026-11-18 13:49 America/New_York until the owner suspended the wave
(the series was in B16), then a **second fresh stage-2 session resumed** the run 2026-11-18 18:21 America/New_York (§3.2
item 6). Freeze hash re-computed over `## 1. Candidate` … the line before the hash line: `e73f760a…afaf4d`, **matches**
(both sessions).

### 3.1 Environment (as run)

- **Node** `ms0625` (Utah m400, **aarch64**, 8 cores, MemTotal 65,791,808 kB, 8 GiB swap present, cgroup v2), Ubuntu
  22.04, kernel 5.15.0-191, OpenJDK 11.0.33+9 aarch64 (G1). Pre-flight 13:49 EST: no Java process, ports 7000/7199/9042
  free, `/mydata` 29 GiB free, other folders untouched. `sudo loginctl enable-linger jason92` at start (Linger was `no`).
- **Build:** `cp -a /mydata/s4/cassandra-base` → `/mydata/s4/u7-w4/cassandra` (5.0.9-SNAPSHOT; `conf/` md5s identical to
  §2.3: yaml `714ee9bf…`, jvm11 `fbad82a8…`, env `8be0588e…`, jvm-server `26a957bf…`). No patch, no rebuild.
- **Confs:** `base` = shipped `conf/`; `conf-i` = line 198 `authenticator: PasswordAuthenticator` + appended
  `in_select_cartesian_product_fail_threshold: 1000`; `conf-a` = the authenticator line only; `conf-g` = conf-a + threshold
  5000 (diffs in `logs/<run>/conf-md5.txt`).
- **Resolved values** (`system_views.settings`, per run in `logs/<run>/settings.txt`; the system.log config line prints
  `null` for derived values): at 2 GiB `max_mutation_size` 16,384 KiB, `memtable_heap_space` 512 MiB, in-flight
  214,748,364 B / per IP 53,687,091 B, `native_transport_max_message_size` 16,777,216 B, receive queue 1 MiB, NTR threads
  128, `commitlog_segment_size` 32 MiB, `in_select_cartesian_product_warn/fail_threshold` −1/−1,
  `partition_keys_in_select_fail_threshold` −1, `write_request_timeout` 2,000 ms, `native_transport_timeout` 12 s,
  `memtable_allocation_type` heap_buffers, `authenticator` AllowAllAuthenticator, disk-usage guardrail −1; at 4 GiB memtable
  1,024 MiB and in-flight 429,496,729 / 107,374,182 B. `jcmd VM.flags`: `MaxDirectMemorySize` 16,642,998,272 B
  (= 15,872 MiB) in every run; `+HeapDumpOnOutOfMemoryError` at 2/4 GiB, `−` at 8/16 GiB (`JVM_EXTRA_OPTS`, as designed);
  G1 region 16 MiB, `AlwaysPreTouch`, open files 100,000. Measured process in
  `systemd-run --user --scope -p MemorySwapMax=0` (no `MemoryMax`).
- **Harness** (`harness/`): `run.sh`, `series.sh`, `monitor.sh` (heap_info + RssAnon 2 s, `Thread.print` 5 s via
  `threadtop.py`, JMX 2 s via `Jmx.java`, df 10 s; for no-dump runs one `GC.class_histogram` at the first sample ≥ 75 %
  used), `u7.py` (bundled driver 3.29.0, protocol v4), `summarize.py`, `hprof-histo.py`, `hprof_oome_thread.py`,
  `excerpt.sh` (`series.sh` gained the `U7_CUTOFF` start cutoff in the resumed session, §3.2 item 6). Full logs on the node in `/mydata/s4/u7-w4/runs/<run>/`; excerpts in `logs/<run>/`.

### 3.2 Deviations and dated amendments

1. **Work dir (2026-11-18, before any run):** `/mydata/s4/u7-w4` instead of `/mydata/u7` (the stage-2 task fixed this
   directory). Location only.
2. **Harness step-end rule (2026-11-18 15:12 EST, after B8):** the first `run.sh` ended a step when the client process
   ended. In every large step the client lost its connection on the driver's 30-s heartbeat (`NoHostAvailable …
   heartbeat timeout`) while the request kept running on the NTR thread, so B8 was stopped by the harness at +8.4 min,
   **before the design's 10-min cap** (§2.5 "each to completion or daemon exit … per-run cap"). Fixed: a client that loses
   its connection does not end the step; the run waits for daemon exit, the OOM endpoint, or the cap. B8 is reported
   but does not count as the 8 GiB search reading; **B8b** re-runs it. The B16 run already started under the old script was
   aborted at start-up (13:12 node time, no send; `logs/B16-aborted/`), and the series' next five runs aborted at
   pre-flight (its daemon was still up; `*-preflight-abort`); all were re-queued.
3. **OOM endpoint rule (same time):** the shipped `-XX:OnOutOfMemoryError=kill -9 %p` **never fired** (T-1..3, IA-1, B4: no
   `Executing` line; the process stayed up after the dump until the harness stopped it). From D-1 on, the step ends 30 s
   after the OOM line and the completed dump (or the OOM line alone without dump), then the harness stops the daemon
   (`kill`, `kill -9` after 60 s). Earlier OOM runs were stopped the same way, only later. No change to what is measured.
4. **B4 without histogram:** B4's dump was cut by the old harness's `kill -9` (4.56 GB of ≈ 6.8 GB); only its OOME thread
   was parsed (the list marked it `nohisto` to save ≈ 7 min). D-2, D-3, IA-2, IA-3 also `nohisto` (OOME thread parsed).
5. **Endpoint label in `summary.txt`:** T-1/T-2 print `endpoint: survived oom:…` (old label = "client ended, daemon alive");
   the OOM line is in stdout, so they are OOM runs.
6. **Resumed after an interruption (2026-11-18 18:21 EST, resuming session).** The first stage-2 session was stopped
   mid-run when the owner suspended the wave (not because of the design); that session then stopped every process it had
   left running. At 18:21 EST nothing ran on `ms0625` (no Java, ports 7000/7199/9042 free, no `u7-*` scope, Linger still
   `yes`, `/mydata` 26 GiB free). **Reused as valid** (complete `driver.txt` ending in `done`, `summary.txt`, endpoint
   recorded, conf md5s as §2.3): the copied tree `/mydata/s4/u7-w4/cassandra` and `conf-i/a/g` (no data is generated
   ahead of a run: each run starts from a fresh `data/`), the compiled harness (node copy md5-identical to `harness/`), and
   the completed runs S0, CAL, T-1..3, L-1..3, I-1..3, IA-1, D-1..3, B4, B8, B8b (B8b had completed: `endpoint: cap` at the
   10-min cap, 13:53 node time). **Not reused:** the B16 run killed by the suspension ≈ 15 min after its start (client
   ended at the 600-s driver timeout, harness waiting for the 25-min cap; no `summary.txt`, no GC log collected) — renamed
   `runs/B16-interrupted` and re-run from a clean start as B16; its partial histogram is quoted below as context only.
   `runs/B16-aborted` (the earlier start-up abort, item 2) stays as it was. **Remaining list** run as
   `runs/list-5.txt`: B16, IA-2, IA-3 (both `nohisto`), R-1, R-2 (4 GiB, `nohisto`), G-1 (`nohisto`, to bound the parse
   time). The §2.7 start cutoff (17:40) had passed; the resuming session set the no-new-run cutoff to 19:45 EST
   (`series.sh` reads `U7_CUTOFF`; the only harness change) so that every run ends and §3–§4 are written before the
   task's hard deadline of 20:20 EST. The priority order of §2.9 was kept (B16 first, G-1 last).

### 3.3 Runs (all at shipped capacities; 2 GiB unless stated)

U_peak = max post-GC heap during the step − last post-GC heap before the send (GC log). K = JMX `Client.RequestsSize`
max. Rows at OOM = `BTreeRow` count in the OOM dump (histogram over all records in the dump, written after the failing GC).

| Run | Conf, heap | Step (P × Q = rows) | Outcome | Readings |
|---|---|---|---|---|
| S0 | base 2G | update 10 × 10 | OK 25 ms | count 10 / 10 (k 0, 9) |
| CAL | base 2G | update 10 / 50 / 100 / 200 / 400 × 20,000 | `WriteTimeout` (2 s CL ONE) at 2.6 / 4.2 / 8.0 / 17.6 / 37.9 s; no OOM | counts 20,000 for the first four steps' first and last keys; the 8 × 10⁶-row step's rows **not applied** (count 0 / 0); post-GC heap rose to 2,001 MiB of 2,048 in that step with 5 full GCs, MutationStage pending 354; K ≤ 163,259 B |
| T-1 | base 2G | update 2,000 × 20,000 = 4 × 10⁷ | **OOM** `Java heap space` (≈ +86 s; dump 3.39 GB in 100.9 s) | rows at OOM **18,819,589** (`BufferCell` 18,819,615, `Object[]` 18,833,653; row objects 98.2 % of 2.86 GB shallow); `PartitionUpdate$Builder` **941** of 2,000 keys; U_peak 1,968 MiB ⇒ **109.6 B/row**; K 176,059 B; memtable 0, MutationStage 0; 53 full GCs; OOME thread NTR: `PartitionUpdate$Builder.add` ← `UpdateStatement.addUpdateForKey:94` ← `ModificationStatement.addUpdates:816` ← `getMutations:749` |
| T-2 | base 2G | as T-1 | **OOM** (dump 88.1 s) | rows 18,831,043; builders 942; U_peak 1,983 MiB (110.4 B/row); K 176,059 B; OOME thread NTR, same frames |
| T-3 | base 2G | as T-1 | **OOM** (dump 88.7 s) | rows 18,844,186; builders 943; U_peak 1,969 MiB (109.6 B/row); K 176,059 B; OOME thread NTR `BTree.buildLeaf` ← `BTreeRow$Builder.build` ← `UpdateParameters.buildRow` |
| L-1..3 | base 2G | update 100 × 20,000 = 2 × 10⁶, then M 1 × 21,999 | no OOM (0/3) | L: `WriteTimeout` at 9.2 / 9.5 / 9.2 s, counts 20,000 (k 0, 99); U_peak 666 / 312 / 298 MiB, whole-run post-GC max 746 / 786 / 782 MiB (≤ 38 % of heap), memtable ≤ 169 MiB, MutationStage ≤ 67, 0 full GCs. M: OK in 227 / 237 / 254 ms, count 21,999; **K 176,059 B = T's** |
| I-1..3 | conf-i (PasswordAuthenticator, role `u7` non-superuser, fail threshold 1,000) 2G | update 2,000 × 20,000 as `u7` | **rejected** in 33 / 34 / 32 ms: `InvalidRequest … Guardrail in_select_cartesian_product violated: … the cartesian product of the IN restrictions on partition key produces 2000 values, this exceeds fail threshold of 1000`; no OOM (0/3) | count 0 / 0; post-GC max 69 / 64 MiB (I-2/3); I-1's two 1,000 × 1,000 steps: `WriteTimeout` 6.5 / 4.5 s, counts 1,000 each, post-GC max 406 MiB, 0 full GCs |
| IA-1 | conf-a (PasswordAuthenticator, no threshold) 2G | update 2,000 × 20,000 as `u7` | **OOM** (dump 100.6 s) | rows 18,811,915; builders 941; U_peak 1,983 MiB; OOME thread NTR `BufferCell.live` ← `UpdateParameters.addCell` ← `UpdateStatement.addUpdateForKey:92` |
| D-1 | base 2G | delete 4,000 × 20,000 = 8 × 10⁷ | **OOM** (dump 186 s) | rows at OOM **29,476,393** `BTreeRow` + 29,476,386 `Row$Deletion` (`BufferCell` 34, `Object[]` 14,605: deletion-only rows share the empty btree); builders **1,474** of 4,000; U_peak 1,968 MiB ⇒ **70.0 B/row**; K 192,051 B; OOME thread NTR `BTree$Builder.add` ← `PartitionUpdate$Builder.add` ← `DeleteStatement.addUpdateForKey:79` ← `addUpdates:816` |
| D-2 | base 2G | as D-1 | **OOM** (dump 250 s) | U_peak 1,968 MiB; OOME thread NTR `BTreeRow.columnData` ← `PartitionUpdate$Builder.add` (DELETE path); thread samples `DeleteStatement.addUpdateForKey` / `BTreeRow$Builder.build` |
| D-3 | base 2G | as D-1 | **OOM** (dump 219 s) | U_peak 1,968 MiB; OOME thread as D-2 |
| B4 | base 4G | update 40,000 × 20,000 = 8 × 10⁸ | **OOM** `Java heap space` | post-GC ≥ 97 % from +40 s; 48 full GCs; U_peak 4,032 MiB; K 480,059 B; first OOME thrown in an RMI TCP thread (the JMX poller's connection, `StreamRemoteCall.getResultStream`) — the heap was full of the NTR's rows (thread samples: NTR in `addUpdateForKey` / `BTreeRow$Builder.build` / `addUpdates` / `addCell` in 30 of 43 samples) |
| B8 | base 8G (no dump) | as B4 | **no OOM before the harness stop at +8.4 min** (deviation 2) | `GC.class_histogram` at +60 s (6.6 GiB used): **46,879,394** `BTreeRow` (1,875 MB) + 46,879,420 `BufferCell` (1,875 MB) + 46,908,827 `Object[]` (1,436 MB) = **110.6 B/row**; post-GC 8,123–8,166 MiB of 8,192 from +100 s, full GCs of ≈ 12 s, STW ≈ 100 % of every 60-s window to the stop (service-loss criterion met); K 480,335 B |
| B8b | base 8G (no dump) | as B4 | **no OOM within the 10-min cap** (`endpoint: cap`; daemon alive, stopped by the harness, `kill -9` after 60 s); **GC service loss** | `GC.class_histogram` at +57 s (6.0 GiB used): **44,603,405** `BTreeRow` + 44,603,432 `BufferCell` + 44,632,553 `Object[]` = 4,935 MB ⇒ **110.6 B/row**; post-GC 8,139–8,188 MiB of 8,192 from ≈ +60 s; 45 full GCs of ≈ 12 s; **STW ≥ 90 % in every 60-s window from +149 s to the stop (500 s)** (service-loss criterion met); U_peak 8,108 MiB; K 480,059 B; memtable 0, MutationStage 0 (nothing applied); client lost its connection at +330 s (driver heartbeat); NTR in `addUpdateForKey` / `BTreeRow$Builder.build` / `addCell` / `addUpdates` in 34 of 54 thread samples |
| B16-interrupted | base 16G (no dump) | as B4 | **killed by the wave suspension** ≈ 15 min after start (§3.2 item 6); not a reading | context only: `GC.class_histogram` at +107 s (13.2 GiB used): 85,216,508 `BTreeRow` + 85,216,534 `BufferCell` + 85,247,863 `Object[]` = 9,425 MB (110.6 B/row); heap_info used 16,344 MiB of 16,384 MiB at ≈ +13.5 min, RssAnon 17.3 GiB; K 480,059 B; GC log not collected |
| B16 | base 16G (no dump) | as B4 (resumed session, 18:22–18:50 EST) | **no OOM within the 25-min cap** (`endpoint: cap`; daemon alive, stopped by the harness, `kill -9` after 60 s); **GC service loss** | `GC.class_histogram` at +100 s (12.5 GiB used): **85,216,401** `BTreeRow` + 85,216,427 `BufferCell` + 85,247,757 `Object[]` = 9,425 MB ⇒ **110.6 B/row**; post-GC 16,353–16,382 MiB of 16,384 from ≈ +5 min; 56 full GCs of ≈ 24 s; **STW ≥ 90 % in every 60-s window from +323 s to the stop (1,220 s)**; U_peak 16,243 MiB; K 480,059 B; memtable 0, MutationStage 0; RssAnon 17.3 GiB; client lost its connection at +570 s; NTR in `addUpdateForKey` / `BTreeRow$Builder.build` / `addUpdates` / `addCell` in 43 of 108 thread samples (the rest: baseline samples before the send and samples where `Thread.print` returned no threads while a full GC ran) |
| IA-2 | conf-a 2G (`nohisto`) | as IA-1 (resumed session) | **OOM** `Java heap space` (endpoint, dump written, +3.4 min after the send; dump 3.39 GB, deleted after the OOME-thread parse) | U_peak 1,979 MiB; post-GC 2,032–2,048 MiB of 2,048; 33 full GCs in the step; K 176,059 B; memtable 0, MutationStage 0; OOME thread NTR (`SEPWorker` ← `Dispatcher` ← `ExecuteMessage`): `BTree.slice` ← `BTreeRow.iterator` ← `Columns.containsAll` ← `PartitionUpdate$Builder.add` ← `UpdateStatement.addUpdateForKey:94` ← `addUpdates:816` ← `getMutations:749` |
| IA-3 | conf-a 2G (`nohisto`) | as IA-1 (resumed session) | **OOM** `Java heap space` (endpoint +7.1 min after the send, after a GC spiral of 130 full GCs; dump 3.39 GB, deleted after the parse) | U_peak 1,968 MiB; post-GC 2,035 MiB of 2,048; K 176,059 B; memtable 0, MutationStage 0; OOME thread NTR: `HashMap$KeySet.iterator` ← `Roles.hasSuperuserStatus` ← `ClientState.isOrdinaryUser` ← `Guardrail.enabled` ← `Threshold.guard` ← `UpdateParameters.addCell:166` (the per-cell value-size guardrail check, which runs for the ordinary role and does not count rows) ← `Constants$Setter.execute` ← `UpdateStatement.addUpdateForKey:92` ← `addUpdates:816` |
| R-1 | base 4G (`nohisto`) | as B4 (resumed session) | **OOM** `Java heap space` (endpoint at +7.0 min incl. the dump of 6.81 GB; dump deleted after the OOME-thread parse) | U_peak 4,016 MiB; post-GC 4,080–4,096 MiB of 4,096; 30 full GCs in the step; K 480,059 B; memtable 0, MutationStage 0; first OOME thrown in a Netty epoll event-loop thread (`StacklessClosedChannelException.newInstance` while closing the client channel after the driver's heartbeat loss) — the heap was full of the NTR's rows (NTR in `addUpdateForKey` / `BTreeRow$Builder.build` / `addUpdates` / `addCell` in 28 of 47 thread samples), as in B4 |
| R-2 | base 4G (`nohisto`) | as B4 (resumed session) | **OOM** `Java heap space` at +9.0 min (gc.log: `Entering safepoint region: HeapDumper` 17:27:05 node time; stdout `java.lang.OutOfMemoryError: Java heap space` + `Dumping heap …`); the dump was still being written at the 10-min cap and was cut by the cap's `kill -9` (6.47 GB, OOME thread parsed from it; deleted) | U_peak 4,016 MiB; post-GC 4,064–4,096 MiB of 4,096; 77 full GCs (GC spiral before the OOM); K 480,059 B; memtable 0, MutationStage 0; first OOME thrown in the JMX `ServerCommunicatorAdmin$Timeout` thread (string concatenation) — the heap was full of the NTR's rows (NTR in `addUpdateForKey` / `BTreeRow$Builder.build` / `addUpdates` / `buildRow` in 44 of 60 thread samples) |
| G-1 | conf-g (PasswordAuthenticator, role `u7` non-superuser, fail threshold **5,000** — `conf-md5.txt`: yaml line 198 + line 2486) 2G (`nohisto`) | update 5,000 × 5,000 = 2.5 × 10⁷ as `u7` (resumed session) | **OOM** `Java heap space` (no guardrail rejection; endpoint +6.0 min after the send incl. the dump of 3.39 GB, deleted after the parse) | U_peak 1,979 MiB; post-GC 2,032–2,048 MiB of 2,048; 37 full GCs in the step; K 80,059 B; memtable 0, MutationStage 0; OOME thread NTR: `BufferCell.live` ← `UpdateParameters.addCell:172` ← `Constants$Setter.execute` ← `UpdateStatement.addUpdateForKey:92` ← `addUpdates:816` ← `getMutations:749` ← `ExecuteMessage.execute` |

Not run: BA (auto heap 31,744 MiB; skipped by the §2.7 rule: 8 and 16 GiB did not reach OOM within their caps, so the estimate for BA exceeds the 25-min cap); IA had 3 runs, R-1/R-2 and G-1 ran — every other run of §2.5 ran. `runs/list-4.txt` (R-1, R-2, G-1) was never started by the first session; its lines ran in `list-5.txt`. Nothing is left running on `ms0625`; dumps deleted (T-1's at the session end), the copy's `data/` and `logs/` removed, linger disabled (19:40 EST).

### 3.4 Against the predictions (§2.7)

- **T:** predicted OOM 3/3 within ≤ 5 min after 500–1,000 keys with 1.0–2.0 × 10⁷ rows, K ≤ 0.2 MB, nothing applied —
  **observed** 3/3, ≈ 1.5 min, after 941–943 keys, 1.88 × 10⁷ rows, K 176,059 B, memtable 0, MutationStage 0. Row cost
  109.6–110.4 B (predicted 108–112 B; B8/B8b/B16 histograms: 110.6 B). Refuting readings: none (no rejection before
  the build, no `MutationExceededMaxSizeException`, rows built ≈ predicted).
- **L/M:** predicted survive with U_peak ≈ 0.18–0.32 GB — **observed** 0/3 each; U_peak 298–666 MiB (L-1's peak includes
  the applied mutations queued on MutationStage and the memtable; every L run stayed ≤ 786 MiB post-GC, 0 full GCs).
- **I:** predicted rejection in < 1 s with the quoted message, heap flat — **observed** 3/3, 32–34 ms, exact message;
  I-1's 1,000 × 1,000 requests applied (count 1,000).
- **IA:** predicted OOM — **observed** (IA-1, IA-2, IA-3: **3/3 OOM**, U_peak 1,968–1,983 MiB as T, IA-1 rows 1.88 × 10⁷, OOME thread on the NTR in `addUpdateForKey` in all three). The authenticator change alone does not stop the OOM; the guardrail does (I 0/3).
- **D:** predicted 3/3 with 1.7–3.3 × 10⁷ rows — **observed** 3/3, 2.95 × 10⁷ rows (70 B/row), 1,474 of 4,000 keys.
- **Search:** predicted OOM at 4, 8, 16 GiB and auto — **observed** OOM at 4 GiB (**3/3**: B4, R-1, R-2; R-2 after a GC spiral at +9.0 min, dump cut by the cap); at 8 GiB the endpoint is
  **GC service loss without OOM within the 10-min cap** (B8, B8b); at 16 GiB likewise **GC service loss without OOM within the 25-min cap** (B16: ≈ 1.5 × 10⁸ rows of 110.6 B fill 16 GiB; full GCs then reclaim only 16–30 MiB each, so the build creeps on; STW ≥ 90 % over 1,220 s). BA skipped by the §2.7 rule (8 GiB did
  not reach OOM in 10 min, so the 31,744-MiB estimate exceeds the 25-min cap). **G-1:** predicted OOM as T despite the enabled guardrail at 5,000 — **observed** OOM (1/1): each side at 5,000 passes the per-side threshold while P × Q = 2.5 × 10⁷ rows are built.

## 4. Conclusion (stage 2)

Written 2026-11-18 ≈ 19:50 America/New_York by the resuming stage-2 session (§3.2 item 6).

- **Verdict:** **true positive.**
- **Protocol status (detail):** `verified-OOM · deployment` for the condition *Cassandra 5.0.9, single node, shipped
  `conf/`, 2 GiB heap, one prepared `UPDATE u7.t SET v = ? WHERE k IN ? AND c IN ?` with P 2,000 × Q 20,000* (and its
  DELETE form, P 4,000 × Q 20,000). Largest heap budget that reaches the OOM: **4 GiB, 3/3** (B4, R-1, R-2). At 8 GiB
  (B8, B8b) and 16 GiB (B16) the same 480 KB request ends in `verified-gap`-type **GC service loss without OOM** within
  the 10-/25-min caps (STW ≥ 90 % over 500 s and 1,220 s); the auto heap (31,744 MiB) was not run (§2.7 rule).
- **Interpretation:** a validation/configuration gap. The only control whose contract covers the IN product, the
  `in_select_cartesian_product` guardrail, ships disabled (−1) and is skipped for superusers (every client under the default
  `AllowAllAuthenticator`); when enabled it bounds P and Q **separately** (G-1: 5,000 × 5,000 passes a 5,000 threshold and
  OOMs). The native in-flight limit charges the 176 KB of wire bytes (K 176,059 B), ≈ 1/12,000 of the ≈ 1.97 GiB the request
  builds. The SELECT form is `known-open` upstream (CASSANDRA-15250); the modification form and the per-side scope of the
  guardrail are `new` (§1, no report found; nothing posted).

| Item | Holds? | Evidence |
|---|---|---|
| V1 Repetition | yes, 3/3 | T-1..3 OOM at 2 GiB from clean starts (also D-1..3 3/3, IA-1..3 3/3, 4 GiB 3/3) |
| V2 Matched control | yes, 0/3 | L-1..3 (product 20× smaller, same statement/budget) and M (same wire bytes and K as T, product 1 × 21,999) survive, post-GC ≤ 786 MiB, 0 full GCs |
| V3 Measurement | yes | U from the GC log (U_peak 1,968–1,983 MiB) and the dump histogram (1.88 × 10⁷ `BTreeRow` + `BufferCell` + `Object[]` = 98 % of shallow bytes, 109.6–110.4 B/row), independent of K (JMX `RequestsSize` 176,059 B); memtable 0, MutationStage 0 (nothing applied) |
| V4 Intervention | yes, 0/3 OOM | I-1..3: the guardrail (fail 1,000, ordinary role) rejects the T request in 32–34 ms, heap flat; useful work in guardrail-sized requests still applied (I-1). Attribution: IA-1..3 (authenticator change alone) OOM 3/3 |
| V5 Initiating failure | yes | first OOME on the NTR thread in `PartitionUpdate$Builder.add` / `BTreeRow$Builder.build` / `BufferCell` ← `UpdateStatement.addUpdateForKey` ← `ModificationStatement.addUpdates:816` ← `getMutations:749` (T-1..3, IA-1..3, D-1..3, G-1); histogram at failure (T-1..3, IA-1, D-1) |
| V6 Default constraints | yes | `system_views.settings` per run: guardrail −1/−1, `max_mutation_size` 16 MiB, in-flight heap/10 and heap/40, message 16 MiB, memtable heap/4, NTR 128, `AllowAllAuthenticator`; no patch; only the I/IA/G arms change the authenticator and guardrail |
| V7 Acceptable budget | yes | 2 GiB heap (the ideal), `MaxDirectMemorySize` resolved 15,872 MiB, no container limit; standing rule (≥ 512 MiB) |

**Reason.** One prepared UPDATE whose request body is 176,054 B (K 176,059 B in flight) makes the coordinator build
P × Q = 4 × 10⁷ rows on one Native-Transport-Requests thread before any mutation exists; at a 2 GiB heap with every
capacity at its shipped default it ended in `OutOfMemoryError: Java heap space` in 3/3 runs after ≈ 1.5 min, with
1.88 × 10⁷ rows (109.6–110.4 B/row, 941–943 of the 2,000 partition builders) holding 1,968–1,983 MiB, nothing applied
(memtable 0, MutationStage 0) and the OOME thrown on the NTR inside `ModificationStatement.addUpdates`. The DELETE form
OOMs 3/3 (2.95 × 10⁷ rows of 70 B). The low-product control (2 × 10⁶ rows) and the matched-wire control (same 176 KB, 21,999
rows) survive 0/3 with ≤ 786 MiB post-GC; the guardrail at 1,000 for an ordinary role rejects the request in 33 ms 3/3,
while the authenticator change alone still OOMs 3/3. The bigger 480 KB request (8 × 10⁸ rows) OOMs a 4 GiB heap 3/3 and
drives 8 and 16 GiB heaps into sustained GC service loss (≥ 90 % STW for 500 s and 1,220 s, post-GC within 0.1 % of the
heap) without an OOM within the caps. V1–V7 hold at 2 GiB, so the case is `verified-OOM · deployment`.

**Notes.** (1) The shipped `-XX:OnOutOfMemoryError=kill -9 %p` never fired in any OOM run (no `Executing` line in stdout;
the process stayed up after the dump until the harness stopped it, §3.2 item 3) — recorded, not investigated. (2) In the
search runs the first OOME was sometimes thrown on a bystander thread (RMI/JMX, Netty event loop) while the NTR's rows
filled the heap (B4, R-1, R-2); the 2 GiB runs that make V5 all threw on the NTR. (3) The composite-key product, the
per-replica message copies and the "referenced until the write completes" legs of OC-366 were out of scope (§1).

**Left on the node** `ms0625`: `/mydata/s4/u7-w4/` (≈ 420 MB: the copied tree `cassandra/` without `data/`/`logs/`,
`conf-i/a/g`, `harness/`, `runs/` with all run logs, no dumps). Nothing running; linger disabled. Excerpts in `logs/`.
