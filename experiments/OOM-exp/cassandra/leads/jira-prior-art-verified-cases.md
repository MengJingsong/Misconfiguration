# JIRA prior-art check — OOM-exp verified Cassandra cases (2026-11-16)

**Purpose.** Before any upstream report: is each verified mechanism already reported in Apache JIRA (fixed, open,
closed as by design), a regression of a past fix, already documented, or apparently new?

**ID prefixes** (rule in [`../../README.md`](../../README.md#id-prefixes-rule-2026-11-16)): **B** = bypass
investigation, **C** = convergence investigation, **R** = recheck of a pre-protocol convergence OOM (suffix **-V** =
re-test at default constraints and an acceptable budget), **S** = stacked combo case, **U** = unprotected-accumulation
lead (S1's layer U1). Condition letters (B6 **A**/**B**, C2 **S-A**) are sub-cases inside one case file.

**Method.** Case summaries/root-cause sections read from `cases/` (links in [`../cases/_INDEX.md`](../cases/_INDEX.md)).
JIRA searched through the REST API (`/rest/api/2/search`, sequential, ≈ 1 s apart): 83 JQL queries, every one listed
below with its hit count (counts as of 2026-11-16). Closest issues read in full
(`/rest/api/2/issue/<KEY>?fields=summary,description,comment,resolution,fixVersions,issuelinks`). Fix commits read in
the bare clone `/mydata/j1/cassandra-history.git` (`git log --all --grep`, `git show`, `git merge-base --is-ancestor
<fix> cassandra-5.0.9`); 5.0.9 code, `conf/cassandra.yaml`, `conf/cassandra-env.sh`, `conf/jvm-server.options`
and `doc/` read at `systems/cassandra/source` (read-only). Raw issue dumps and the query log are in the session
scratchpad only, not kept here.

**Verdict vocabulary.** **new** = no issue reports the mechanism; **known-open** = an unresolved issue reports it (or its
core); **known-fixed → regression** = a fix exists and the mechanism came back; **by design (closed)** = closed as
intended behaviour; **documented** = shipped docs already warn about it; **unclear**.

## Summary

| Case | Mechanism (short) | Verdict | Closest issue(s) | Upstream action suggested |
|---|---|---|---|---|
| **B1** (negative, release defect) | v5 `LargeMessage.onComplete()` never calls `releaseBuffers()` | **known-open** | **CASSANDRA-21884** (filed 2026-11-12, *Needs Committer*, PR for 4.1, one +1) | No new ticket. Optionally comment on 21884 with our 5.0.9 numbers (pool pinned at cap after ≈ 1,000 requests, `OverflowSize` 21 GB/10 min, forced-GC count at 512 MiB direct, patch removes it 3/3). |
| **B6** | internode queues charge on-wire bytes; tiny-cell mutations ≈ 17–20× on heap; `hintOnFailure` retention | **new** (contract documented as on-wire; heap consequence unreported) | 15066 (introduced limits, Fixed 4.0), 9318 (retention acknowledged 2015, Fixed 3.10, mechanism removed in 4.0 by 15375), 8639 (same ratio problem in CL replay, Fixed 3.2), 7402 (Open, request memory metrics) | New ticket (Improvement / documentation + optional heap-aware charge). |
| **B7** | key/counter cache Caffeine weigher omits ≈ 90 B per-entry container overhead | **new** — **not a regression** (overhead never counted, CLHM era included) | 4315, 4860 (Fixed 1.2), 5549 (2.1), 10855 (Fixed 4.0); 6709 (Later; "100 + key length bytes" per entry acknowledged), 9738 (Won't Fix) | New ticket (Bug, low severity: bounded overshoot 1.8–2.1×). |
| **R1-V** | off-heap memtable + chunk cache at defaults exceed a container limit | **documented** (+ general **known-open**) | 10930 (Open, "Limit off-heap memory", oomkiller if RAM ≤ 2×heap), 20491 (Open, "Document offheap memory used by Cassandra") | No bug report. At most a comment on 20491 / a doc patch. Our failing container breaks the documented "heap ≤ 50 % of RAM" rule. |
| **C1** | internode receive-queue reserves (N·Q + G) live in direct memory, not checked against `MaxDirectMemorySize` | **new** (low priority) | none on point; 15066 (limits), 21529 / 19535 / 18762 (direct OOM reports, open / cannot reproduce, other holders) | Optional Improvement: startup warning when G (+ N·Q) + pools ≥ `MaxDirectMemorySize`. Weak: needs explicit direct ≤ 640 MiB. |
| **C2** | concurrent reads × slow clients: encoded native responses unbounded, Netty direct OOM | **known-open** | **CASSANDRA-11082** (Open since 2016: "watermarks set but `isWritable()` never checked → OOM with slow receivers"; downgraded for lack of evidence), 15013 (Fixed 4.0, bounded request bytes not response bytes) | Comment on 11082 with the 5.0.9 reproduction (fresh evidence that it was missing in 2016), or a new ticket linked to it. |
| **S1** | stacked direct-memory combo; unbounded in-flight DOB fill for large mutations in `CommitLog.add` | **known-open** (U1 layer) + **new** (stack / direct-limit framing) | **CASSANDRA-21656** (*In Progress*, 2026-09-05: large mutations over-allocate native memory on the commit-log path, WIP branch removes the buffer); **16471** (Fixed 5.0-alpha1: moved DOB scratch to **direct** by default — origin of the direct exposure) | Comment on 21656 (concurrency × direct-limit consequence, OOM evidence); no separate ticket for the stack. |
| **S2** | coordinator's own CL=ONE local writes queued unboundedly on `MutationStage` behind a faster replica; expired local writes resubmitted as hints | **known-open** (core) + **new** (trigger and OOM) | **CASSANDRA-19958** (*Needs Committer*, 4.1.x/5.0.x: local hints and local mutations share the unbounded MUTATION queue, piles to > 1 M), 6510 / 4753 (Fixed 1.2: resubmit-as-hint is intended), 13213 (Open, pending mutations → OOM) | Comment on 19958 (its fix only separates queues; it does not bound the local backlog) or a linked new ticket. |

Two **side findings** (5.0.9 docs): `jvm-server.options` says "By default, [`MaxDirectMemorySize`] is half of max heap
size", but `cassandra-env.sh` sets ¼ RAM (or `heap_limit/2`) whenever `MAX_HEAP_SIZE` is given explicitly — C2's
auto 3,982 MiB at a 2 GiB heap; and CASSANDRA-16471 switched DOB scratch buffers to direct memory with a CHANGES.txt
line but no NEWS.txt entry.

---

## B1 — native-v5 large-request release defect (negative · release defect)

**Case:** [`negatives/networking_cache_size-release-defect/`](../cases/negatives/networking_cache_size-release-defect/networking_cache_size--release-defect.md).
`CQLMessageHandler.LargeMessage.onComplete()` (5.0.9 `CQLMessageHandler.java:821-835`) never calls
`releaseBuffers()`; pooled slots pinned until the networking pool sits at its cap, `OverflowSize` grows without bound.

**Verdict: known-open.**

| Issue | Status / fix | One line |
|---|---|---|
| **CASSANDRA-21884** | *Needs Committer*, unresolved; fixVersions 4.0.x, 4.1.x, 5.0.x, 6.0.x, 7.x; created 2026-11-12 (Yuqi Yan) | "v5 protocol multi-frame CQL requests do not return networking buffers": exactly our mechanism (`Envelope.release()` frees only the Netty wrapper, never `ShareableBytes.release()`); notes the two impacts we measured (pool capacity stranded; overflow counter never decremented, not live RSS). 4.1 PR #5420, one +1 (2026-11-16), PRs for the other branches pending. |
| CASSANDRA-21815 | Fixed (2026-11-02), fixVersions 4.0.x…7.x; commit `d103e7522d`, **not in 5.0.9** | `BufferPool.putUnusedPortion` on overflow buffers makes `OverflowSize` negative; the precursor that led its reporter to 21884. |
| CASSANDRA-21117 | *Review In Progress* (4.1.x, 5.0.x, 7.x) | `nodetool info` reports Network Cache size 30–76 GiB or negative — the operator-visible symptom of 21815 + 21884. |
| CASSANDRA-19535 | Cannot Reproduce (2024) | "Running with default configuration OOMs under light load": direct OOM in `BufferPool.allocate` on a client event-loop thread at an 8 GiB limit; no comments. Possibly B1-related (or C2); not enough data to tell. |
| CASSANDRA-20052 | Fixed 4.1.8 / 5.0.3 | v5 message size not limited; touches the same large-message path, no release discussion. |

**Queries (hits):** `text ~ "releaseBuffers"` (4); `"LargeMessage" AND "leak"` (3); `"CQLMessageHandler" AND "large"`
(8); `"v5" AND "\"buffer pool\"" AND "leak"` (1); `"OverflowSize"` (58, tokenizer noise); `"networking_cache_size"` (33);
`summary ~ "large message" AND "v5"` (0); `"\"protocol v5\"" AND "memory leak"` (1).

**What an upstream contribution would need:** nothing new is needed for the defect. Useful extra evidence for 21884:
5.0.9 reproduction (3/3), the pooled-vs-overflow split, the cost at the smallest acceptable direct budget (≈ 125 forced
Full GCs / 10 min at 512 MiB vs 14 patched), glibc RSS retention (+625–688 MiB vs +50–61 patched), and that the
same one-line release fixes it on 5.0.

---

## B6 — internode queues charge on-wire bytes; tiny-cell mutations ≈ 17–20× on heap (verified-gap · service-loss)

**Case:** [`bypass/internode_application_queue_capacity-accounting-mismatch/`](../cases/bypass/internode_application_queue_capacity-accounting-mismatch/internode_application_queue_capacity--accounting-mismatch.md).

**Verdict: new.** The unit is documented (`cassandra.yaml` 5.0.9 l. 1370–1372: "These limits are applied to the
on-wire size of the message"), so the counter behaves as specified; no issue or doc says that a receive queue within
its 528 MiB on-wire limit can hold ≈ 9 GiB of heap for dense small-cell writes, nor that the coordinator's after-flush
`hintOnFailure` copy is charged to no sender counter. The retention itself is long-known design (9318).

| Issue | Status / fix | One line |
|---|---|---|
| CASSANDRA-15066 | Fixed 4.0-alpha1 | "Improvements to Internode Messaging": introduced the three-tier send/receive limits "measured by the serializedSize of the message"; discussion has no heap-vs-wire ratio. |
| CASSANDRA-9318 | Fixed 3.10 (`BackPressureStrategy`), removed in 4.0 by **CASSANDRA-15375** (`d8993934e9`) | "Bound the number of in-flight requests at the coordinator"; comment 2015: "We already keep the original request around until we either get acks from all replicas, or they time out (and we write a hint)" — retention acknowledged; the bound it added no longer exists. Duplicate: 8518 (in-flight data limit). |
| CASSANDRA-8639 | Fixed 3.2 | "Can OOM on CL replay with dense mutations": same root ratio (count/serialized bound vs `unsharedHeapSize`), fixed only for commit-log replay by bounding replay by heap size. Prior art that heap-size charging is the accepted remedy. |
| CASSANDRA-8969 | Fixed 3.11.12 / 4.0.2 / 4.1 | Added the yaml warning that high timeouts cause memory build-up (yaml l. 1305–1318). Our condition A uses default timeouts, so the warning does not cover it. |
| CASSANDRA-13299 | Fixed 4.0-alpha1 | Large mutations from streaming/MV held on heap; split into batches. Different path. |
| CASSANDRA-7402 | Open (7.x) | "Add metrics to track memory used by client requests" — no metric for request heap exists. |
| CASSANDRA-18304 / 17164 | Fixed 4.1.2 | Moved hint submission to `AbstractWriteResponseHandler.onFailure` (`hintOnFailure`). Checked: 4.0's `WriteCallbackInfo` also kept the payload, so the retention is not a 4.1 regression. |
| 14855 / 15013 | Fixed 3.0.18 / 4.0 | Native-transport Flusher queue and request-bytes bounds (client side), not internode. |

**Queries (hits):** `"internode_application_send_queue_capacity"` (9); `"internode_application_receive_queue_capacity"`
(8); `"\"on-wire size\""` (0); `"hintOnFailure"` (3); `"\"serialized size\"" AND "\"heap size\"" AND "mutation"` (0);
`"\"small cells\"" AND "OOM"` (0); `"\"MutationStage\"" AND "OOM"`, created ≥ 2019 (1); `"\"inbound\"" AND "\"heap\""
AND "OOM"`, ≥ 2019 (1); `"\"Full GC\"" AND "internode"`, ≥ 2019 (1); `"serializedSize" AND "heap"`, ≥ 2019 (9);
`"\"queue capacity\"" AND "heap"`, ≥ 2019 (7); `"\"internode\"" AND "OutOfMemoryError" AND "heap"`, ≥ 2019-06 (2);
`"\"write callbacks\"" AND "memory"` (0); `"\"slow replica\"" AND "memory"` (2); `"\"tiny\"" AND "cells" AND "heap"`
(17); `"\"application_send_queue\""` (8); `"\"internode_application\""` (11); `"AbstractWriteResponseHandler" AND
"memory"` (9).

**What a report would need to show:** (1) the ratio from a class histogram (on-wire 10.8 KiB vs ≈ 213 / 181 KiB
heap for a 1000-cell map write; ≈ 2.2 for blobs), (2) the default-settings outcome (condition A: 8 GiB replica,
30 s storage stall, ≈ 99 % live / ≈ 97 % in Full GC, 3/3; blob 0/3) with the 8 MiB endpoint-reserve intervention,
(3) a framing as Improvement, since the contract is honest about the unit: either document that the limits do not
bound heap (by a factor up to ≈ 20), or charge `max(serializedSize, estimated heap size)` as 8639 did for replay.
Expect pushback that a 30 s storage stall is an overload condition; condition A is the strongest answer because
timeouts and threads are default.

**Draft summary.** *Internode application queue limits are charged by on-wire size, but queued small-cell mutations
occupy 17–20× that on the heap.* The send and receive application queues (`internode_application_*_queue_*capacity`,
CASSANDRA-15066) limit queued messages by `serializedSize`. Writes with many tiny cells serialize compactly but
deserialize into one object graph per cell: in 5.0.9 a 1000-int-cell map write is 10.8 KiB on the wire and ≈ 213 KiB
on the coordinator heap, ≈ 181 KiB on the replica heap, so a receive queue within its default 528 MiB ceiling can pin
≈ 9 GiB of heap. The coordinator also retains each sent mutation for `hintOnFailure` until the replica answers,
charged to no queue counter. With all settings at their defaults, a 30 s storage stall on an 8 GiB replica drove it
to ≈ 99 % live heap and ≈ 97 % of two minutes in Full GC (3/3), while blob writes of the same on-wire size did not
(0/3); an 8 MiB endpoint reserve removed the effect (4/4). CASSANDRA-8639 fixed the same mismatch for commit-log
replay by bounding replay with heap size; we suggest either documenting that these limits do not bound heap, or
charging the larger of serialized and estimated heap size for messages that are deserialized on arrival.

---

## B7 — key/counter cache weigher omits per-entry overhead (verified-gap · overshoot)

**Case:** [`bypass/key_cache_size+counter_cache_size-accounting-mismatch/`](../cases/bypass/key_cache_size+counter_cache_size-accounting-mismatch/key_cache_size+counter_cache_size--accounting-mismatch.md).

**Verdict: new — not a regression.** The question was whether per-entry overhead accounting was lost in the move to
Caffeine. History of the weigher (bare clone):

| Version | Commit | Weigher | Container overhead counted? |
|---|---|---|---|
| 1.2 | `8aaaacd09d` (CASSANDRA-4315) | `meter.measure(key) + meter.measure(value)` (shallow, jamm) | no |
| 1.2 | `94fa82558f` (CASSANDRA-4860) | `measureDeep` (key byte[] included) | no |
| 2.1 | `4b54b8acd2` (CASSANDRA-5549) | `key.unsharedHeapSize() + value.unsharedHeapSize()` | no |
| 4.0 | `c607d76413` (CASSANDRA-10855) | same expression, moved into `CaffeineCache.create` | no |

The CLHM node / hash-table cost was never in the weight; 10855 copied the expression unchanged. So the overshoot is
as old as weighted key caches (1.2) and the ratio simply depends on the per-entry container (CLHM then, Caffeine
`PSMW` + `ConcurrentHashMap$Node` + table + sketch now).

| Issue | Status / fix | One line |
|---|---|---|
| CASSANDRA-4315 | Fixed 1.2.0-beta1 | EntryWeigher for caches; mentions "Key capacity (In-Heap Overhead)" as a wish, not implemented. |
| CASSANDRA-4860 | Fixed 1.2.0-beta3 (follow-up 5564) | Row cache size underestimated (always 24 B): `measure` → `measureDeep`; payload only. |
| CASSANDRA-10855 | Fixed 4.0-alpha1 | Caffeine for on-heap caches; the issue cites "very small time/space overhead to LRU" but no weight change. |
| CASSANDRA-6709 | Resolved *Later* (2014) | "KeyCache … requires a lot of overhead per entry … 100 + <key length> bytes": the overhead is acknowledged, but as a density problem; no one connects it to the configured size. |
| CASSANDRA-9738 | Won't Fix (2016) | Off-heap key cache (OHC); review asked whether the stale "singleton weigher 48 bytes" comment in `CacheService` still makes sense — it was removed on that branch, which was never merged; the comment is still in 5.0.9 `initKeyCache`. |
| CASSANDRA-19703 | Fixed 5.0.5 | Prepared-statement Caffeine cache eviction race; different cache, no overhead discussion. |

5.0.9 docs: `cassandra.yaml` documents `row_cache_size` with an explicit overhead caveat ("OHC … requires some
additional off-heap memory to manage the map structures … This overhead is usually small") but the key and counter
cache text says only "Maximum size of the … cache in memory"; `hardware.adoc` lists "row, key, and counter caches" as
**off-heap** consumers, which is wrong for key/counter caches since 3.0 (on-heap Caffeine). No text warns about the
overshoot.

**Queries (hits):** `"weigher"` (13); `"\"key cache\"" AND "overhead" AND "size"` (37); `"key_cache_size" AND "heap"`
(179, skimmed top 25); `"CaffeineCache"` (4); `"\"counter cache\"" AND "memory" AND "overhead"` (8); `summary ~ "key
cache" AND summary ~ "size"` (2); `"unsharedHeapSize" AND "cache"` (6); `"\"key cache\"" AND "underestimat*"` (5);
`"\"key cache\"" AND "\"per entry\""` (4); `"\"key cache\"" AND "\"more memory than\""` (1); `"Caffeine" AND
"overhead" AND "weight"` (3); `"\"counter_cache_size\"" AND "OOM"` (2); `"\"key cache\"" AND "\"heap dump\""` (10);
`"maximumWeight"` (2).

**What a report would need to show:** dump-based U vs JMX `Size`/`Capacity` at the default caps (2.14× key, 1.80×
counter; 1.15× at 512 B keys), stable over time and across heaps; the per-entry breakdown (PSMW 40 B, CHM node 32 B,
table + sketch ≈ 18 B); the +104 B weigher removing it (and the hit-rate cost: 48–57 % fewer entries). Frame as a
Bug with low severity (bounded, ≈ 155 MiB beyond contract at defaults, no OOM alone; contributes to the R3/R4 heap
OOMs only with raised capacities). Offer two fixes: add a constant per-entry overhead to the weigher, or change the
yaml/metrics text to "payload size".

**Draft summary.** *Key and counter cache sizes do not include per-entry container overhead; a cache at its
configured size uses 1.8–2.1× that much heap.* `CacheService` builds both caches with
`CaffeineCache.create(capacity)`, whose weigher is `key.unsharedHeapSize() + value.unsharedHeapSize()`. That counts
the key and value objects but not the ≈ 90 B per entry that Caffeine and its backing map need (node 40 B,
`ConcurrentHashMap$Node` 32 B, hash-table and frequency-sketch slots ≈ 18 B). Key-cache entries weigh ≈ 80 B and
counter-cache entries ≈ 112 B, so the overhead is +114 % / +80 %. On 5.0.9 with the shipped yaml, a key cache filled
to its default 100 MiB holds ≈ 214 MiB of heap and a counter cache at 50 MiB holds ≈ 90 MiB (heap dumps, 3/3 at 512 MiB,
2 GiB and 8 GiB heaps), while JMX `Size` equals `Capacity`. The expression predates Caffeine (CLHM since
CASSANDRA-4315/5549, carried over by CASSANDRA-10855), and CASSANDRA-6709 already noted ≈ 100 B overhead per key, but
the yaml documents both settings as "Maximum size of the … cache in memory". Adding a fixed per-entry overhead to the
weigher (≈ 104 B brings usage to 0.93–0.95× the configured size) or documenting the setting as payload size would
close the gap.

---

## R1-V — off-heap memtable + chunk cache at defaults exceed a container limit (verified-OOM · deployment)

**Case:** [`convergence/memtable_offheap_space+file_cache_size--default/`](../cases/convergence/memtable_offheap_space+file_cache_size--default/memtable_offheap_space+file_cache_size--default.md).

**Verdict: documented** (plus general **known-open** issues). The 5.0.9 docs state the pieces an operator needs:

- `cassandra.yaml` l. 740–752 (`file_cache_size`): "This pool is allocated off-heap, so is in addition to the memory
  allocated for heap"; l. 791–799: memtable spaces default to ¼ heap each.
- `doc/.../operating/hardware.adoc`: "In addition to the heap, Cassandra will use significant amounts of RAM
  offheap … The Cassandra heap should be no less than 2GB, and **no more than 50% of your system RAM**."
- `cassandra-env.sh`: heap = ½ RAM, direct = ¼ RAM — Cassandra's own memory model.

The verified failing condition (family B) gives the heap **60 %** of the container (3,413 MiB for 2 GiB), i.e. outside
the documented 50 % rule; under L = 2 × heap (the documented ratio) heaps 1–2 GiB survive and only 768 MiB failed
1/5 (candidate). The case file argues 60 % from external container guidance (Red Hat, K8ssandra, DataStax); upstream
will measure it against `hardware.adoc` and likely answer "documented / misconfiguration".

| Issue | Status / fix | One line |
|---|---|---|
| CASSANDRA-10930 | Open (7.x), 2015 | "Limit off-heap memory": default direct memory can make the OOM killer act "if max_mem <= 2*heap"; asks for a check; reply: default feels fine. |
| CASSANDRA-20491 | Open, 2025 | "Document offheap memory used by Cassandra": draft table lists off-heap memtables and chunk cache with their settings, no sum or budget rule yet. |
| CASSANDRA-11681 / 11940 | Open (2016) | Better `file_cache_size` defaults (tuning upward, not about budgets). |
| CASSANDRA-21529 | Open (2026-07, 5.0.6) | Direct-buffer OOMs with chunk cache 8 GiB, `offheap_objects`, 96 GB VM; no comments; a JVM direct OOM, not a memcg kill, but the same "pools sum past the budget" family. |
| CASSANDRA-8552 / 8723 / 12699 | Cannot Reproduce / Open | Older RSS-growth / OOM-killer reports, other causes. |

**Queries (hits):** `"file_cache_size" AND "\"OOM killer\""` (4); `"offheap_objects" AND "\"OOM killer\""` (0);
`"\"chunk cache\"" AND "RSS"` (1); `"memtable_offheap_space" AND "file_cache_size"` (35); `"container" AND
"\"off-heap\"" AND "memory limit"` (31); `"cgroup" AND "memory" AND "heap"` (6); `summary ~ "off-heap" AND summary ~
"memory" AND (summary ~ total|limit|budget)` (1); `"\"file_cache_size\"" AND "default"`, ≥ 2016 (30).

**What an upstream contribution would need:** a failure inside the documented model (heap ≤ ½ container) — we have
only 768/1536 at 1/5. Without it, the useful contribution is a doc patch to 20491 (state that the default
memtable-off-heap + chunk-cache pair needs ≈ ½ heap of native memory beyond heap and direct baseline, and that
`file_cache_enabled` + `offheap_objects` together need the full ½-RAM headroom), or a startup warning when
`memtable_offheap_space + file_cache_size + heap + MaxDirectMemorySize` exceeds the cgroup limit (the JVM can read
it). No draft bug report.

---

## C1 — internode receive-queue reserves × peers vs `MaxDirectMemorySize` (verified-OOM · diagnostic, run 4)

**Case:** [`convergence/internode_application_receive_queue_capacity-multiplicity/…run4.md`](../cases/convergence/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run4.md).

**Verdict: new** (low priority). The multiplicity is partly documented — `cassandra.yaml` l. 1374–1378: "any given
node may have a maximum of N*3*(send+receive capacity) … queued without any coordination" — but nothing says that
the receive side (queued LARGE frames) lives in **direct** memory or relates G = 512 MiB (+ N·Q) to
`MaxDirectMemorySize`. No issue reports a direct OOM from receive-queue frames.

| Issue | Status / fix | One line |
|---|---|---|
| CASSANDRA-15066 | Fixed 4.0 | Introduced Q/E/G; no direct-memory budget discussion. |
| CASSANDRA-15358 | Fixed 4.0-alpha4 | LARGE_MESSAGE connection allocated heap when `BufferPool` was exhausted; fixed to stay on direct. Same path, opposite concern. |
| CASSANDRA-20296 + follow-up `d954c19b21` | Fixed 5.0.4, in 5.0.9 | Defaults `-XX:MaxDirectMemorySize` explicitly (heap_limit/2 or ¼ RAM). At a 2 GiB heap the resolved value is ≥ 1 GiB, above C1's largest failing 640 MiB. |
| CASSANDRA-21529 | Open (5.0.6) | Direct OOM in production (compaction thread), no holder analysis. |
| CASSANDRA-19535 | Cannot Reproduce | Default-config direct OOM under light load, BufferPool via client event loop. |
| CASSANDRA-18762 / 17025 / 16154 | Cannot Reproduce / Invalid / Triage | Direct OOMs from Merkle trees, chunk cache, unknown; other holders. |
| CASSANDRA-10930 | Open | General off-heap limit discussion (2015). |

**Queries (hits):** `"MaxDirectMemorySize"`, ≥ 2019 (9); `"\"Direct buffer memory\""`, ≥ 2019-06 (16);
`"receive_queue"` (67, tokenizer noise, top 30 skimmed); `"LargeMessage" AND "direct"` (7); `"\"large messages\""
AND "direct memory"` (4); `"\"reserve_global\""` (7); `"InboundMessageHandler" AND "memory"` (13);
`"internode_application_receive_queue_capacity"` (8).

**What a report would need to show:** a failure at a direct budget an operator would plausibly run. Run 4 fails only
at 512–640 MiB, below what `cassandra-env.sh` resolves for any node (≥ 1 GiB at a 2 GiB heap); S1 raises the failing
budget to 768 MiB only with 15 MiB mutations. Best framing is an Improvement: warn at startup when
`internode_application_receive_queue_reserve_global_capacity` + N·Q + `networking_cache_size` approaches
`MaxDirectMemorySize`, with run-4 dumps (66–68 % of direct in `LargeMessage.buffers`) as evidence. Probably not worth
filing alone; could be folded into the S1 comment.

**Draft summary.** *Internode receive-queue reserves are not checked against the JVM direct-memory limit.* Queued
LARGE internode messages keep their raw frames (direct `BufferPool` buffers) until a stage thread deserializes them,
and the receive queue admits up to N·Q + G on-wire bytes (default Q = 4 MiB per connection, G = 512 MiB global). With
eight coordinators writing 1 MiB mutations to one node during its own flush stalls, all counters stay within their
contracts while the admitted 528–544 MiB plus ≈ 50 MiB baseline and the networking pool exceed a 512–640 MiB
`MaxDirectMemorySize`: direct OOM 10/10 at 2 GiB heap, heap dumps attribute 66–68 % of direct memory to
`InboundMessageHandler$LargeMessage.buffers`; one or two loaded peers at the same total load never fail. The shipped
G alone equals the smallest such budget, and nothing in startup validation or the yaml relates the reserves to the
direct limit. A startup warning (or documenting that the receive reserves are direct memory) would let operators
size `MaxDirectMemorySize` accordingly.

---

## C2 — concurrent reads × slow clients: no outbound backpressure (verified-OOM · deployment, condition S-A)

**Case:** [`convergence/coordinator_read_size_fail_threshold-concurrent-reads/`](../cases/convergence/coordinator_read_size_fail_threshold-concurrent-reads/coordinator_read_size_fail_threshold--concurrent-reads.md).

**Verdict: known-open — CASSANDRA-11082.**

| Issue | Status / fix | One line |
|---|---|---|
| **CASSANDRA-11082** | **Open**, no fixVersion, created 2016-01-28 | "netty's level hadn't prevent OOM when receiver handle slow": Cassandra configures write high/low watermarks but never checks `isWritable()`, so `ChannelOutboundBuffer` grows with slow clients. Sylvain Lebresne confirmed ("we never check `Channel.isWritable()`") and lowered priority because "there isn't too much evidence so far that OOM due to clients being too slow … is very common"; T Jake Luciani: "we should be checking isWritable()". Three fix options proposed (drop, close, disable autoRead); stalled since 2016-02. Our 5.0.9 source still has the 8/32 KiB watermark (`PipelineConfigurator.java:139`) and no `isWritable()` in `transport/`. |
| CASSANDRA-15013 | Fixed 3.0.19 / 3.11.5 / 4.0 | Follow-up of 14855 whose description names the missing `isWritable` check; the fix bounded **request bytes** in flight (`native_transport_max_request_data_in_flight(_per_ip)`) and moved to autoRead backpressure — response bytes stay uncounted (released when handed to the flusher, as C2 measured). |
| CASSANDRA-14855 | Fixed 3.0.18 | Flusher scheduling fell off the event loop → heap OOM from the Flusher queue; different cause (scheduling bug), same holder family. |
| CASSANDRA-19534 | Fixed 4.1.6 / 5.0-rc1 | Unbounded native-transport request queue; added `native_transport_timeout` shedding. Inbound only. |
| CASSANDRA-21508 | Fixed **5.0.9** (`9ddfe0fb22`) | Moved pre-v5 response encoding onto the request worker (`PreV5Handlers.toFlushItem` → `response.encode`). C2's allocation site (`PreV5Handlers.java:91-97`) is this change; before it the same bytes were encoded on the event loop and still queued in `ChannelOutboundBuffer`, so C2 is not a 5.0.9 regression, but the holder moved. |
| CASSANDRA-21766 | Fixed **5.0.10** (`8208f031ef`), not in 5.0.9 | Follow-up of 21508: response bodies encoded off-loop leak when the client disconnects mid-flight. Not C2 (clients stayed connected), but a 5.0.9 user with slow *and* disconnecting clients loses the same buffers permanently. |
| CASSANDRA-12034 | Fixed 3.8 | Netty `OutOfDirectMemoryError` routed to `JVMStabilityInspector` (by design → forced heap OOM and exit, as C2 observed). |
| CASSANDRA-11521 | Won't Fix | Streaming bulk reads; mentions slow clients and watermarks. |
| CASSANDRA-20052 | Fixed 5.0.3 | v5 request size limit; inbound. |

5.0.9 docs: no yaml text bounds outstanding responses; `native_transport_max_request_data_in_flight` is not even in
`cassandra.yaml`. The read size thresholds are documented per query.

**Queries (hits):** `"isWritable"` (10); `"ChannelOutboundBuffer"` (3); `"OutOfDirectMemoryError"` (1);
`"\"slow client\""` (1); `"\"slow clients\""` (2); `"\"write watermark\"" OR "WriteBufferWaterMark"` (2);
`"\"native transport\"" AND "backpressure" AND "response"` (10); `"Flusher" AND "memory"` (28); `"\"outbound\"" AND
"\"native transport\"" AND "OOM"` (5).

**What an upstream contribution would need:** exactly the evidence 11082 lacked: a default-config reproduction
(S-A: 1,024 outstanding 3.5 MiB reads, clients draining 128 MiB/s, Netty direct OOM 3/3 at auto 3,982 MiB; same at
auto heap; 1/1 at 7,936 MiB), the dump holders (≈ 1,700–1,800 `ChannelOutboundBuffer$Entry`, ≈ 245 × 16 MiB
`PoolChunk`), the two survivals (128 outstanding; client cap 512), and the observation that request-side limits
(15013) and read thresholds cannot see it. Post as a comment on 11082 (suggest: stop dispatching / disable autoRead
while `!isWritable()`, or charge encoded response bytes to the in-flight limit until `ChannelFuture` completion), or
open a new ticket linked to it if a committer prefers.

**Draft comment summary (for 11082).** *Fresh 5.0.9 evidence: slow clients make Netty direct memory grow without
bound.* Cassandra 5.0.9 still sets an 8/32 KiB write watermark (`PipelineConfigurator`) and never calls
`isWritable()` in `transport/`. Responses are encoded into pooled direct memory on the request thread and handed to
the channel; the request thread, the `native_transport_max_request_data_in_flight` charge (request bytes only,
CASSANDRA-15013) and the client's stream id are all released before the socket drains, so outstanding response memory
is outstanding reads × page size, limited only by the client. With every setting at its default and a 2 GiB heap,
64 connections × 16 outstanding 3.5 MiB single-partition reads, drained at 128 MiB/s in aggregate, killed the node
with Netty `OutOfDirectMemoryError` at the auto-resolved 3,982 MiB direct limit in ≈ 11 s (3/3; also with read
thresholds enabled, at the auto 7,965 MiB heap, and 1/1 at 7,936 MiB direct). 128 outstanding reads, or a client
capped at 512, survive with the same throughput. Heap dumps at failure show ≈ 1,700–1,800 `ChannelOutboundBuffer`
entries in ≈ 245 × 16 MiB pool chunks.

---

## S1 — stacked JVM-direct combo with in-flight DOB fill for large mutations (verified-OOM · deployment)

**Case:** [`convergence/internode_receive_queue+hint_slabs+DOB+networking_pool--direct-combo/`](../cases/convergence/internode_receive_queue+hint_slabs+DOB+networking_pool--direct-combo/internode_receive_queue+hint_slabs+DOB+networking_pool--direct-combo.md).

**Verdict: known-open for the decisive layer (U1), new for the stacked framing.** And one historical finding: the
direct exposure of U1 is a **5.0 design change**, not a regression of a fix.

| Issue | Status / fix | One line |
|---|---|---|
| **CASSANDRA-21656** | **In Progress**, unresolved, no fixVersion, created 2026-09-05 | "large mutations over-allocate on the commit log path": `CommitLog.add` serializes into the scratch buffer, rebuilt per large write; 10.42 MB native per 4 MiB mutation (6.0 branch, async-profiler); WIP branch serializes straight into the segment slot (−99.8 % native). Frames it as allocation churn on one thread, not as a concurrent peak against `MaxDirectMemorySize`. |
| **CASSANDRA-16471** | Fixed 5.0-alpha1 (`60db95cba1`), in 5.0.9 | "DataOutputBuffer#scratchBuffer can use off-heap or on-heap memory": default `cassandra.dob.allocate_type` = **DIRECT**; `CommitLog.add` and `HintsWriter` use it. In 4.x the same fill was heap (`ByteBuffer.allocate`). Reviewer asked how much memory per thread could be used; the answer kept the 1 MiB post-close trim, nothing bounds the in-flight size × `concurrent_writes`. Listed in CHANGES.txt, not in NEWS.txt. |
| CASSANDRA-11937 | Fixed 3.8 | Throw away (not trim) large DOB buffers after the Netty upgrade; origin of the recycle limit. |
| CASSANDRA-10971 / 10972 | Fixed 3.0.4–3.5 | Compressed commit log / file hints had no backpressure and could OOM; fixed with buffer pools. Not the scratch buffer. |
| CASSANDRA-13754 | Fixed 3.11.1 | `BTree.Builder` thread-local leak (heap); thread-local-retention family, not direct. |
| CASSANDRA-16201 | Fixed 4.0 | Batch-statement allocation reduction; heap. |
| CASSANDRA-21535 | Review In Progress (6.0.x) | Avoid extra copy for cached Mutation serialization; adjacent path. |
| CASSANDRA-12783 | Open | Break up large MV mutations to prevent OOMs; heap, MV. |

**Queries (hits):** `"DataOutputBuffer" AND "direct"` (32); `"DOB_MAX_RECYCLE_BYTES"` (2); `"dob_max_recycle_bytes"`
(2); `"scratchBuffer"` (8); `"expandToFit"` (3); `"\"CommitLog.add\"" AND "memory"` (4); `"\"large mutations\"" AND
"memory"` (6); `"max_mutation_size" AND "OOM"` (8); plus the C1 queries for the receive-queue layer.

**What an upstream contribution would need:** a comment on 21656 with the concurrency consequence: 32
`MutationStage` threads each growing the direct scratch buffer to 15–30 MiB for mutations within the default 16 MiB
`max_mutation_size`, first OOM thread in `CommitLog.add` → `expandToFit` in 3/3, dumps showing DOB scratch 210–435 MiB
at failure; that the exposure became direct with 16471; and the ingredient-removal controls (1 MiB mutations 0/3).
Note the limit: the failing budget (768 MiB direct at 2 GiB heap) is below the auto value (≥ 1 GiB), and Netty's
separate counter makes C2 not stackable on it. A stand-alone ticket for the five-layer stack would be judged a
sizing issue.

**Draft comment summary (for 21656).** *The commit-log scratch buffer is direct memory since CASSANDRA-16471, so
large-mutation over-allocation also multiplies across `MutationStage` threads into a direct-memory OOM.* In 5.0.9,
`CommitLog.add` serializes every mutation into `DataOutputBuffer.scratchBuffer`, which CASSANDRA-16471 made direct
by default; `dob_max_recycle_bytes` trims it only after use. With eight coordinators sending 15 MiB mutations (within
the default `max_mutation_size`) to a 2 GiB-heap node, all 32 `MutationStage` threads were inside `CommitLog.add` at
once, each scratch buffer at 15–30 MiB: heap dumps at failure show 210–435 MiB of DOB scratch alongside the
networking pool (136 MiB), hint slabs (96 MiB) and queued receive frames, and the first `OutOfMemoryError: Direct
buffer memory` is thrown from `expandToFit` (3/3 at 768 MiB direct). 1 MiB mutations, a single coordinator, or
removing the other direct consumers each survive (0/3). Serializing directly into the segment slot, as the WIP branch
here does, would remove this layer; otherwise the in-flight size needs a bound or a heap fallback above the recycle
limit.

---

## S2 — coordinator's own CL=ONE local-write backlog on `MutationStage` (verified-OOM · deployment)

**Case:** [`convergence/coordinator-local-write-backlog--combo/`](../cases/convergence/coordinator-local-write-backlog--combo/coordinator-local-write-backlog--combo.md).

**Verdict: known-open (core) + new (trigger).** The unbounded `MutationStage` queue with local mutations and local
hints, and its pile-up under load, are reported and have a pending patch; the specific trigger — CL=ONE answered by a
faster replica releases the client slot and the in-flight byte charge while the coordinator's own write is still
queued, so no client-side limit applies — and the heap OOM at defaults are not in JIRA. Resubmitting an expired local
write as a hint is intended (6510 / 4753).

| Issue | Status / fix | One line |
|---|---|---|
| **CASSANDRA-19958** | **Needs Committer**, fixVersions 4.1.x, 5.0.x, 7.x; created 2024-09-26 (Jaydeepkumar Chovatia) | "Local Hints are stepping on local mutations": `Stage.MUTATION` is shared by local mutations and local hint writes; under load it "will pile up to >1 million" and the node stops accepting writes. Patch (PR 3580 / 4061) moves hints to their own stage — removes head-of-line blocking but does **not** bound the local-mutation backlog. Discussion notes the expired `LocalMutationRunnable` → `submitHint` path (since 4753) and that `enforce_native_deadline_for_hints` cannot help because the deadline is checked on the transport thread. Last activity 2025-04 (one committer review, waiting for a second). |
| CASSANDRA-6510 / 4753 | Fixed 1.2.14 / 2.0.4 and 1.2.1 | Timed-out local mutations must leave a hint: origin of resubmit-as-hint (by design). |
| CASSANDRA-19534 | Fixed 4.1.6 / 5.0-rc1 | Unbounded native-transport queue; added `native_transport_timeout`; does not cover the stage queue behind it (19958 calls itself the follow-up). |
| CASSANDRA-9318 | Fixed 3.10 → removed 4.0 (15375) | Coordinator in-flight bound; discussion: "At CL=1 … there is nothing to be gained by bounding the number of in-flight requests at a coordinator by not reading" — the CL=ONE release effect was seen as a feature. |
| CASSANDRA-13213 | Open (2017) | "node eventually OOMs due to pending mutations" (compaction hang cause); same symptom, other trigger. |
| CASSANDRA-12689 / 13235 | Fixed 3.0.10 / Open | All `MutationStage` threads blocked; writes pending. Different cause. |
| CASSANDRA-16499 | Open | Single-threaded writes waiting on SEPExecutor; `performLocally` path, performance only. |
| CASSANDRA-7402 | Open | Metrics for memory used by client requests. |

**Queries (hits):** `"LocalMutationRunnable"` (48, top 25 skimmed); `"MutationStage" AND "pending" AND "OOM"` (8);
`"MutationStage" AND "unbounded"` (2); `"performLocally"` (11); `"HintRunnable"` (12); `"\"local write\"" AND
"hint" AND "timeout"` (8); `"\"bounded queue\"" AND "mutation"` (5); `"\"CL=ONE\"" AND "OOM" AND "coordinator"` (4);
`"\"enforce_native_deadline_for_hints\""` (3); `"\"consistency level ONE\"" AND "\"mutation stage\"" AND "backlog"`
(0); `"\"mutation stage\"" AND "heap"`, ≥ 2020 (1).

**What an upstream contribution would need:** the trigger (heterogeneous replicas, CL=ONE, client window 2,048) at
defaults with the heap OOM (3/3 at 2 GiB, ≈ 61.5 k `LocalMutationRunnable`s ≈ 90 % of heap), the LOCAL_ONE and
rate-cap survivals, the equal-heap-replica survival (the faster replica is part of the condition), and the
post-load OOM (backlog persists after the client stops). Argue (or test with PR 4061) that 19958's patch would not
remove it: hints are on in the S2 arms and expired local writes become `HintRunnable`s on the same stage in 5.0.9;
19958 moves those to a separate stage, so the backlog would split across two unbounded queues, not vanish. Expect the answer that CL=ONE
with an overloaded local replica is an overload condition; the strongest point is that every client-visible limit is
released early, so the client never sees backpressure.

**Draft comment summary (for 19958, or a linked ticket).** *At CL=ONE the coordinator's own local writes can queue
on `MutationStage` without any bound and OOM the heap, even without hints from other nodes.* When a coordinator is
also a replica, `StorageProxy.performLocally` submits a `LocalMutationRunnable` to `Stage.MUTATION`, whose queue is
unbounded. At CL=ONE the client is answered as soon as any replica acknowledges; if the other replica is faster, the
request, its `native_transport_max_request_data_in_flight` charge and the client's in-flight slot are all released
while the local write is still queued, so no client or transport limit sees the backlog, and an expired local write
is resubmitted as a hint on the same stage rather than shed. On 5.0.9 with all defaults, a 2 GiB-heap coordinator
paired with a faster 8 GiB replica died of heap OOM 3/3 within 28–210 s of a 13–17 k writes/s burst from a client
that never had more than 2,048 writes in flight; the heap held ≈ 61.5 k queued mutations (≈ 90 % of the heap), and
one node failed 120 s after the load had stopped. LOCAL_ONE or a 2,000 writes/s cap survives 3/3. Separating hints
from mutations (this ticket) keeps local writes from waiting behind hints but leaves the local-write backlog
unbounded; a bound on `MutationStage` pending bytes, or shedding expired local writes when a replica already
answered, would close it.

---

## Notes and limits

- JIRA `text ~` is tokenized: quoted identifiers such as `"MutationStage"` still match loosely, and some broad
  queries (`OverflowSize` 58, `receive_queue` 67, `key_cache_size AND heap` 179) are mostly noise; only their top
  20–30 results were read. Absence of a hit is evidence, not proof. GitHub PRs and the dev@ mailing list were not
  searched.
- B1 (21884) and S1 (21656) are recent (Sept–Nov 2026) and moving; re-check their state right before any comment.
- Fix-presence checks: 21508 (`9ddfe0fb22`) and 20296 follow-up (`d954c19b21`) are ancestors of the
  `cassandra-5.0.9` tag; 21815 (`d103e7522d`) is not; 21766 (`8208f031ef`) is fixVersion 5.0.10; 21884, 21656,
  19958 and 11082 have no commits.
- The S2 statement about 19958's patch is from the issue text, not from applying PR 4061.
