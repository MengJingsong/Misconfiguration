# memtable_offheap_space-tryAllocate-limit — stage-4 results  <!-- file: long-path/results/memtable_offheap_space-tryAllocate-limit.md or short-path/results/memtable_offheap_space-tryAllocate-limit.md -->

> **Case:** [`memtable_offheap_space-tryAllocate-limit`](../../../stage3-ai-deep-read/long-path/cases/memtable_offheap_space-tryAllocate-limit.md)
> (short path: `../../../stage3-ai-deep-read/short-path/cases/memtable_offheap_space-tryAllocate-limit.md`)
>
> **Status:** verdict filed (2026-10-13) — **Confirmed at both tiers**; **escape hatch as recorded**; oversize arm at 512 MiB and the default: **the process holds more** than the allocator; no run 2
>
> **Path:** long. One results file per path, each in its path's folder.
> For a short-path file (`short-path/results/memtable_offheap_space-tryAllocate-limit.md`), the "case file" below is the short-path
> solution, and for each tier "§9a" means that tier's predictions and conclusions
> table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or
> B3a–B3e. If the case has both paths, see [`comparison/memtable_offheap_space-tryAllocate-limit.md`](../../comparison/memtable_offheap_space-tryAllocate-limit.md)
> for the side-by-side.

**Relative links in this template** are written for where a *copy* of it lives
— inside `long-path/results/` or `short-path/results/` — not for the template's own location two levels up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../../README.md`](../../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base commit `1125f90` plus the step-0 amendments of 2026-10-13 (uncommitted at freeze; committed in `61c22b6`). §9 hash after the amendments: **`cebea1512a1abc4b3d4ad3838a7733d7c4a4f1b4`** (`sed -n '/^## 9\. /,/^## 10\. /p' <case> \| git hash-object --stdin`). §9a is frozen at this version. |
| **Harness** | `../harness/memtable_offheap_space-tryAllocate-limit/` (written 2026-10-13; uncommitted at run 1, committed in `61c22b6`): `NativePoolTest.java`, `unit-run.sh`, `escape-hatch.btm` (copied from the heap sibling, comments only differ), `region-ledger.btm`, `ledger.py`, `cluster-run.py`, `README.md`. Node copy `pc57:~/stage4-harness-run/mos/`, `md5sum` equal to the repo before run 1 (`cluster-run.py` `d01a73dd…`). **Instrument checks (2026-10-13, not readings):** Byteman `TestScript` against the build: all six rules type-checked, `TestScript: no errors` (the first try passed the class path wrongly and was informational only; fixed). Known answer, `cluster-run.py instrument` (`NativePoolTest` with both rules attached): test passed; escape-hatch trace exactly `forced=10 limit=100`; ledger exactly one `malloc cap=8192`, one `discard owns=110`, one `free` of the same peer `cap=8192 site=discard`, one `discarded` — `ledger.py` reads `P_m − A_m` = 8,082 B, within the bound. Logs `pc57:~/stage4-logs/mos/instrument/`. **Cluster shakedown** (`value 128 small`, 2026-10-13 18:47, log root `~/stage4-logs/mos-shakedown/`): every step and check ran; no harness defect. Its numbers are not readings. |
| **Tiers and values** | Unit: upstream `NativeAllocatorTest`, harness `NativePoolTest` (limit 100 B). Cluster (one node, `pc57`): `memtable_offheap_space` 128 · 256 · 512 MiB · unset (1024 MiB at `-Xmx4G`), each with the small-cell and the oversize arm; the cleanup-threshold control (256 MiB, small arm); the load-floor control (256 MiB, heap memtables, both arms). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-13 |

### 1.1 Design audit

Citations re-read against the local clone `~/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Off-heap bytes of the node-wide memtable pool (§4, §9a claim). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 128, 256, 512 MiB and the default, with the heap pinned so the default is a fixed 1024 MiB (9b). |
| A. Core question | real resource measured, not only the counter (gap named) | **Not met** | 9d read the physical bytes as NMT `Other`, on the claim that `MemoryUtil.allocate` is `Unsafe.allocateMemory`. At the tag it is JNA `Native.malloc()` (`MemoryUtil.java:25`, `:81-84`), a libc `malloc` NMT never sees; `P` would have read flat and fired a false Refuted row. Amended (rec. 1). |
| A. Core question | usage driven to the limit and past it | Met | `cleanup_threshold 0.99`, 256 client threads, about ten limit flushes per run at the default; scenario C forces a flush while writers wait (9b, 9c, 9e). |
| B. Logic | each step says what it establishes | Met | "How this verifies the hypothesis", Logic (1)–(5). |
| B. Logic | prediction stated in numbers or a clear relation | Partly | Stated, but the ±16 MiB band omits slack the source shows (the race stash alone holds up to 15.94 MiB, plus up to three live regions), and "sample at the `Enqueuing flush` line's time" pairs `P` and `A` at moments 1–2 s apart while the pool refills at tens of MiB/s. Re-derived as a per-memtable pairing at discard and a node-wide bound (rec. 2). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Missing: the process holding more native memory than the allocator (malloc retention), and a failed instrument. Added (rec. 3). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed row needs waits in every run (`BlockedOnAllocation`, frames at `MemtableAllocator.java:195`) and the peak following the knob; "Why the peak alone is not enough". |
| B. Logic | alternative explanations and their controls | Partly | On-heap pool binding → `memtable_heap_space 2048MiB` and the trap note; flush trigger → cleanup-threshold control; commit-log flushes → `durable_writes = false`. Not covered: native memory the load adds elsewhere (network buffers, flush writers) under the process reading. Load-floor control added (rec. 4). |
| C. Specific | a human can follow it from the intro and §9a | Met | §9 intro and §9a. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Commands, observables and traps given; the old NMT sampling steps replaced by continuous readings (rec. 1). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | The stop check used `pgrep -f`, which the stage-4 README's safety rule replaces with `ps -eo cmd \| grep '[C]assandraDaemon'` (rec. 5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Harness listed as step-1 work (9c, extended by recs. 1 and 6); `pc57` set up 2026-10-13 (JDK 11.0.32.1, Ant 1.10.12, `~/cassandra-run1` at the tag, `ant build-test` passed; Byteman 4.0.20 in `build/lib/jars/`). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | ≈ 10 GiB (small arm, n = 2,000,000 × ≈ 5 KiB) and ≈ 11 GiB (oversize arm, n = 60,000 × 192 KiB) per run, wiped between runs; about ten limit flushes at 1024 MiB. `pc57`: 56 GB free, 251 GiB RAM, 32 cores. Ledger volume ≈ 10⁴ lines (small arm), ≈ 1.2 × 10⁵ (oversize). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met, one defect | Read in context: `MemtablePool.java:47-48`, `:55-66` (`BlockedOnAllocation` timer at `:63`), `:125-135`, `:151-161`, `:177-197`; `MemtableAllocator.java:93-97`, `:151-155`, `:169-197` (frame `:195`), `:204-233`; `NativeAllocator.java:46-57`, `:138-206`, `:209-227`; `NativePool.java:21-33`; `AbstractAllocatorMemtable.java:59`, `:78-112`, `:199-202` (`markExtraOffHeapUsed`, no caller), `:289-295`, `:320-323` (`%.2f/%.2f`); `DatabaseDescriptor.java:583-594`, `:770-773`, `:4060-4063`; `Config.java:188-189`; `ColumnFamilyStore.java:1055`; `TableMetrics.java:498-521`; `MemtableCleanerThread` `Clean.run()` (no busy loop: `needsCleaning()` re-arms through `nextClean`); `conf/cassandra.yaml:783-825` (`skiplist` default, `heap_buffers` default type); `conf/jvm-server.options:128` (`AlwaysPreTouch`); `build.xml:33` (`debuglevel` includes `vars`, so Byteman can read locals). **Defect:** `MemoryUtil.allocate()` → `com.sun.jna.Native.malloc()` (rec. 1). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Replace NMT `Other` as the physical reading. `MemoryUtil.allocate()` is JNA `Native.malloc()`, so NMT cannot see memtable regions. Use a Byteman **region ledger** (one line per `Region` built, per region freed, and per `setDiscarded()` with the memtable's `owns`), and `RssAnon` from `/proc/<pid>/status` for the process; keep NMT as support. | Applied 2026-10-13 (9a How/Logic/Prediction/table, 9b NMT row, 9c, 9d Real resource, 9e); uncommitted | Without it the run reads `P` flat and fires "accounting is decorative", a false refutation; does not depend on any reading. |
| 2 | Re-derive the band. Per memtable at `setDiscarded()` entry (regions freed before accounting is released): `0 ≤ P_m − A_m ≤ 1 MiB + 0.002 A_m`. Node-wide: `0.99 limit − L_idle − 1 MiB ≤ max L − L_idle ≤ limit + F + 19 MiB + 0.002 limit` (stash 15.94 MiB + 3 × 1 MiB). The oversize arm keeps the same bounds (keys and clusterings still use slab regions; the stash is global). | Applied 2026-10-13 (9a Prediction, 9b Controls) | The old band was arithmetic short of what the source allows, and its sampling moment was ambiguous; source-only. |
| 3 | Add rows: "`P` within band, but the process holds more" (`max ΔRssAnon > max ΔL + max ΔRssAnon_ctl + 64 MiB`) and "ledger empty or stalled → invalid". | Applied 2026-10-13 (9a table) | Every plausible outcome needs a row. |
| 4 | Add a load-floor control per arm (256 MiB, `unslabbed_heap_buffers`, `memtable_heap_space 256MiB`, idle/A/B) for the process cross-check. | Applied 2026-10-13 (9b Controls, 9e) | Separates native memory the load adds elsewhere from the memtable's. |
| 5 | Stop check: `ps -eo cmd \| grep '[C]assandraDaemon'` instead of `pgrep -f`. | Applied 2026-10-13 (9e step 5) | Stage-4 README safety rule. |
| 6 | `NativePoolTest` ends by discarding its allocator, so the ledger's instrument check has a known answer (one 8,192 B region, `owns=110`). | Applied 2026-10-13 (9e unit step 6, 9e instrument check) | Instrument check needs a known answer. |
| 7 | §6b and §8 say `NativeAllocator.allocate()` "never reads the verdict". `SubAllocator.allocate()` returns `void` and parks inside, so the physical `malloc` waits behind the accounting call; the physical/accounted decoupling §8 names is at most region slack, not a missing gate (the 2026-10-06 §10 note says this too). | Left for stage 3 | Changes §6b/§8, not §9; the run tests it. |
| 8 | §7 "Lifetime / release" omits the global race stash: regions lost in a swap race are kept (up to 8 per size class, 15.94 MiB) and never freed. And because memtable regions come from JNA `malloc`, they are invisible to NMT and outside `-XX:MaxDirectMemorySize` (Target-3 note). | Left for stage 3 | Documentation of §7/§8; recorded for the Target-3 note. |
| 9 | `AbstractAllocatorMemtable.markExtraOffHeapUsed()` (`:199-202`) has no caller at the tag. | Left for stage 3 | Not load-bearing. |

**Agreement criteria** — not filled: run 2 was not chosen (§5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-13 (unit 18:48; cluster chain from 18:50, node clock MDT) | |
| Node (CloudLab name and type) | `pc57` = `node0.jason92-319347` (32 cores, 251 GiB) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `b5f2a54210` (`~/cassandra-run1`, `cassandra-5.0.9`) | |
| Case-file commit / harness commit | base `1125f90` + the 2026-10-13 amendments (§9 hash `cebea151…`) / harness uncommitted at run 1, node copy md5-equal to the repo; both committed in `61c22b6` | |
| Storage for node data | local `/dev/sda3` (ext3), under the clone | |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/mos/` (`unit/`, `<label>-<arm>/`, `chain.log`); shakedown `~/stage4-logs/mos-shakedown/` | |

## 3. Runbook defects

None. Run 1 executed §9b–§9e as amended on 2026-10-13 without a stop: unit tier, then the 11 node runs in one chain (`run1/chain.log`, every run `rc=0`). Harness bugs found before run 1 (the `TestScript` class path) were fixed during the instrument checks (§1), not during the run.

## 4. Run 1

**Scope:** unit tier (2026-10-13 18:48 MDT); cluster tier 18:50–19:11 — `memtable_offheap_space` 128 · 256 · 512 MiB · default (1024 MiB), small arm and oversize arm; cleanup-threshold control (256 MiB, small); load-floor controls (256 MiB heap memtables, small and oversize). **Command log:** `pc57:~/stage4-logs/mos/<run>/session.log` (every command and its output); repo excerpts in [`memtable_offheap_space-tryAllocate-limit/run1/`](memtable_offheap_space-tryAllocate-limit/run1/): per run `summary.txt`, `readings.csv`, `cassandra.diff`, `submit-l.txt`, `flush-lines.txt`, `rss.csv`, `ledger-read.txt`, `nmt-*.txt`, `escape-hatch.txt`; `unit/`, `instrument/`, `chain.log`, `selfcheck.py` + `selfcheck.out`, and three analysis scripts with their output (`race.py` → `race-regions.txt`, `peak.py` → `cleanup256-small/peak-decomposition.txt`, `drop.py` → `rss-at-discard.txt`). Full ledgers (up to 33,000 mallocs) and system logs stay on the node.

### 4.1 Readings

**Unit tier** (`run1/unit/`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Clone and harness copy | `b5f2a54210` `cassandra-5.0.9`; harness = compiled copy (sha256 `ace0c8bf…` both) | `unit/versions.txt` |
| `NativeAllocatorTest` (upstream) | 1 test, 0 failures, 0 errors | `unit/TEST-…NativeAllocatorTest.xml`, `unit/unit.console` |
| `NativePoolTest` (harness) | 1 test, 0 failures, 0 errors; 15 `STAGE4` lines, 0 mismatches | `unit/TEST-…NativePoolTest.xml`, `unit/NativePoolTest.out` |
| — step 1, fill to the limit | `used = 100`, `owns = 100` | `NativePoolTest.out` |
| — step 2, 11th piece | thread state `WAITING`, frames `MemtableAllocator$SubAllocator.allocate:195`, `NativeAllocator.allocate:141`; 300 ms `get()` timed out | same |
| — step 3, 2 s later | `used = 100`, still parked | same |
| — step 4, release 10 B | the parked call returned a peer; `used = 100` | same |
| — step 5, group marked blocking | a further 10 B returned at once; `used = 110`, `owns = 110` | same |
| — step 6, discard | `used = 0` | same |

**Cluster tier** — one node `pc57`, `offheap_objects`, `memtable_heap_space 2048MiB`, cleanup 0.99 (control: default), `-Xms4G -Xmx4G`, NMT, both Byteman rules from start, `durable_writes = false`. Source: `run1/<value>-<arm>/summary.txt` and `run1/selfcheck.out` unless named. *L* = ledger live region bytes; *A_m*, *P_m* per memtable at its discard (only memtables ≥ 8 MiB listed in ranges).

| Reading | 128 small | 256 small | 512 small | default small | 128 oversize | 256 oversize | 512 oversize | default oversize |
|---|---|---|---|---|---|---|---|---|
| Off-heap limit in `system.log` / `Memtables allocating with off-heap objects` | 128 MiB / yes | 256 / yes | 512 / yes | 1024 / yes | 128 / yes | 256 / yes | 512 / yes | 1024 / yes |
| Idle `BlockedOnAllocation` count | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **A** first limit flush after stress start | 7.5 s | 8.5 s | 10.0 s | 11.1 s | 6.5 s | 7.0 s | 7.5 s | 8.0 s |
| **A** its off-heap `Usage` | 127.997 MiB (100 %) | 254.947 (100 %) | 507.511 (99 %) | 1014.662 (99 %) | 127.901 (100 %) | 255.989 (100 %) | 511.977 (100 %) | 1023.953 (100 %) |
| **B** wait count at A → after B | 134 → 547 | 95 → 333 | 0 → 155 | 0 → 277 | 251 → 557 | 116 → 314 | 18 → 321 | 12 → 247 |
| **B** dumps with frames at `MemtableAllocator.java:195` (of 3) | 32 · 32 · 32 | 32 · 32 · 32 | 32 · 32 · 32 | 32 · 32 · 32 | 32 · 32 · 0 | 32 · 32 · 32 | 32 · 32 · 32 | 32 · 32 · 32 |
| `MEMTABLE_LIMIT` flushes of `keyspace1.standard1` | 16 | 10 | 6 | 7 | 15 | 9 | 7 | 6 |
| Largest off-heap `Used total` at any flush start | 1.00 | 1.00 | 0.99 | 0.99 | 1.00 | 1.00 | 1.00 | 1.00 |
| Escape hatch, off-heap lines (*F*) | 557 calls, 472,820 B | 396, 338,908 | 189, 164,193 | 177, 149,571 | 220, 19,860,005 | 160, 12,781,545 | 108, 10,618,182 | 114, 11,208,081 |
| Memtables with *A_m* > limit; largest excess | 2; 139,390 B | 1; 130,518 | 0 | 0 | 12; 6,188,230 | 5; 4,510,580 | 2; 3,515,044 | 2; 2,505,709 |
| Discards; all with 0 ≤ *P_m* − *A_m* ≤ 1 MiB + 0.002 *A_m* | 61; yes | 55; yes | 51; yes | 52; yes | 60; yes | 54; yes | 52; yes | 51; yes |
| *P_m* − *A_m*, memtables ≥ 8 MiB | 0.144–0.889 MiB | 0.306–1.156 | 0.431–1.283 | 0.572–1.648 | 0.003–0.012 | 0.000–0.031 | 0.007–0.009 | 0.007–0.027 |
| *P_m* / *A_m*, same memtables | 1.0011–1.0070 | 1.0012–1.0045 | 1.0009–1.1155 | 1.0009–1.0607 | 1.00005–1.00010 | 1.0000–1.0002 | 1.00001–1.00025 | 1.00002–1.00057 |
| *L_idle* | 0.03 MiB (all runs, ±) | | | | | | | |
| **max *L* − *L_idle*** | 142.77 MiB | 265.42 | 531.38 | 1039.26 | 133.94 | 262.44 | 518.09 | 1030.10 |
| 9a node-wide bounds | 125.69–147.71 | 252.41–275.84 | 505.85–532.18 | 1012.73–1045.19 | 125.69–166.20 | 252.41–287.70 | 505.85–542.15 | 1012.73–1055.74 |
| max *L* / limit | 1.115 | 1.037 | 1.038 | 1.015 | 1.046 | 1.025 | 1.012 | 1.006 |
| Race-loser regions live at max *L* (`race-regions.txt`) | 4 MiB | 0 | 5 | 3 | 0 | 0 | 0 | 0 |
| max Δ`RssAnon` | 348.3 MiB | 419.6 | 738.1 | 1259.8 | 868.1 | 1074.4 | 1471.5 | 2269.3 |
| Process bound: max Δ*L* + floor + 64 MiB | 407.9 — within | 530.6 — within | 796.5 — within | 1304.4 — within | 1041.6 — within | 1170.1 — within | 1425.8 — **above by 45.7** | 1937.8 — **above by 331.5** |
| NMT `Other` committed, idle → end of B | 62 → 1,096 MiB | 62 → 1,096 | 62 → 1,096 | 62 → 1,096 | 62 → 1,394 | 62 → 1,642 | 62 → 1,271 | 62 → 1,356 |
| Ledger consistency (unmatched frees, double mallocs, bad lines) | 0, 0, 0 (all runs) | | | | | | | |
| Node stopped, no `CassandraDaemon` left | yes (all runs) | | | | | | | |

**Controls** (same sources):

| Reading | cleanup256-small (default threshold) | floor256-small (heap memtables) | floor256-oversize (heap memtables) |
|---|---|---|---|
| First limit flush | 86.17 MiB (34 %) | (on-heap pool) | (on-heap pool) |
| Wait count at A → after B; dumps at `:195` | 201 → 481; 32 · 0 · 32 | 32 → 153; 32 · 32 · 32 | 48 → 151; 0 · 32 · 32 |
| Largest off-heap `Used total` | 0.68 | 0.00 | 0.00 |
| Escape hatch, off-heap lines | 0 | (0; 304 on-heap lines) | (0; 106 on-heap lines) |
| Ledger | 62 discards, all within the per-memtable bound; **max *L* − *L_idle* = 283.95 MiB**, above the 0.99 runs' bound (275.51); at that moment 3 `keyspace1` memtables live and **15 race-loser 1 MiB regions** in flight (`peak-decomposition.txt`, `race-regions.txt`) | no `malloc` line | no `malloc` line |
| max Δ`RssAnon` | 508.7 MiB | **201.2 MiB** (floor) | **843.7 MiB** (floor) |
| NMT `Other`, idle → end of B | 62 → 1,096 MiB | 62 → 1,096 | 62 → 1,665 |

**Other readings.** Race-loser regions (a region a writer allocated, lost the swap CAS for, and then stashed or freed) live 2–3 ms (median) and at most 77 ms (`race-regions.txt`). `RssAnon` across the discard of a 0.5–1 GiB memtable moves −106 to +386 MiB, never by the memtable's size (`rss-at-discard.txt`); glibc is 2.35. `Submit -l` lists the escape-hatch trigger in every run, and the three ledger triggers in every off-heap run (`submit-l.txt`).

### 4.2 Conclusion and logic — unit tier

1. **Validity — valid.** Pinned tag and harness copy [observed: `unit/versions.txt`]; the pool reached its limit (`used = 100` before the over-limit call) [observed: `NativePoolTest.out` step 1].
2. **Readings — nothing unusual.** Every assertion matched [observed: 0 mismatches].
3. **Matched row — the unit part of *Confirmed*, with *Escape hatch as recorded*.** The over-limit request waits, seen as thread state `WAITING` in `SubAllocator.allocate:195` called from `NativeAllocator.allocate:141`, not only as a timeout [observed: step 2] — so the physical allocation after `:141` has not happened while it waits [inferred: from the frame, `:141` is before the region slice at `:144-155`]; the counter does not move while it waits [observed: step 3]; a release wakes it [observed: step 4]; a blocking group forces 10 B through and the counter reads exactly `limit + 10` [observed: step 5].
4. **Excluded rows.** *Not confirmed (no writer waits)*: excluded [observed: step 2]. *Refuted (passes by more than the escape hatch)*: excluded, excess = the forced 10 B [observed: step 5]. The cross-value, physical and process rows are not testable at this tier.
5. **Observed vs. inferred.** That no `malloc` happens while parked is inferred from the frame's position; the cluster ledger observes it per memtable.
6. **Deviations and gaps.** The test's cleaner returns `false` rather than `true` (both do nothing; `true` would re-signal the cleaner thread in a loop while usage stays above 75 %); recorded in the harness.

**Conclusion (one line):** unit tier — **Confirmed**, with **Escape hatch as recorded** (10 B forced, counter 110 against 100).

### 4.3 Conclusion and logic — cluster tier

1. **Validity — valid at every value and arm, and in the three controls.** The limit took effect and the `NativePool` was built [observed: `flush-lines.txt` `Global memtable off-heap threshold is enabled at …`; `summary.txt` debug.log check]; the yaml diff is exactly the 9b lines [observed: `cassandra.diff`, self-check]; JVM `-Xms4G -Xmx4G`, NMT and the agent were present [observed: self-check on `jvm-args.txt`]; the instruments were in place [observed: `submit-l.txt`, a ledger with 2,621–32,998 mallocs and 0 inconsistencies per run]; writers waited in every run, so the *Invalid run* rows do not apply [observed: wait counts and dumps]; `keyspace1` had `durable_writes = false` [observed: `session.log` check].
2. **Readings — two features.** (a) The oversize arm forces 40–75× more bytes through the escape hatch than the small arm at the same limit (10.6–19.9 MB against 0.15–0.47 MB), because one forced write is 192 KiB [observed: trace; inferred: the cause]. (b) In the oversize arm `RssAnon` rises much more than *L* and does not fall when a memtable is discarded [observed: `rss.csv`, `rss-at-discard.txt`].
3. **Matched rows.**
   - **Confirmed — at all four values in both arms** (the first row): writers wait in every run [observed: counts 155–557 after B; 23 of 24 dumps with all 32 `MutationStage` threads at `:195`]; the accounted peak follows the knob, ratio 1 : 2 : 4 : 8 to within 1 % (small 128.0 · 254.9 · 507.5 · 1014.7 MiB; oversize 127.9 · 256.0 · 512.0 · 1024.0) [observed: first `Usage`]; the counter passes the limit only by forced bytes [observed: every *A_m* ≤ limit + *F*; largest `Used total` 1.00]; and *P* is within the band of *A*: per memtable 0 ≤ *P_m* − *A_m* ≤ 1 MiB + 0.002 *A_m* in all 436 discards, and node-wide max *L* − *L_idle* inside its bounds in all eight runs [observed: ledger, self-check]. §8's second ground ("physical can diverge from accounted") **is not borne out**: physical exceeds accounted by 0.0–1.6 MiB per memtable (*P_m* / *A_m* ≤ 1.007 at 128–256 MiB, ≤ 1.0006 in the oversize arm), i.e. region slack, as the 2026-10-06 §10 note predicted.
   - **Escape hatch as recorded — observed this time.** The counter is seen above the limit: 24 memtables across six runs had *A_m* > limit, by at most 6.19 MB (128 MiB oversize), each time below that run's forced bytes *F* [observed: ledger `discard` lines, trace]. Size, Target-3 material: *F* = 0.014–0.35 % of the limit per run in the small arm, 1.0–14.8 % in the oversize arm (19.9 MB at 128 MiB).
   - **Confirmed for the allocator; the process holds more — oversize arm at 512 MiB and the default.** max Δ`RssAnon` is 45.7 and 331.5 MiB above max Δ*L* + the oversize floor (843.7) + 64 MiB [observed]. At the other six (value, arm) pairs the process stays within the bound [observed].
4. **Excluded rows.** *Confirmed for the counter, bounded gap*: excluded — no memtable and no run outside the band [observed]. *Refuted — loosely or unbounded*: excluded — *L* follows the knob 1.006–1.115 × limit [observed]. *Refuted — passes by more than the escape hatch*: excluded per memtable (*A_m* − limit ≤ *F*) [observed]; the pool's instantaneous total is not read (part 5). *Refuted — flat*: excluded [observed]. *Not confirmed — no writer waits*: excluded [observed]. *Refuted — P flat*: excluded, *L* rises 133.9 → 1039.3 MiB with the knob [observed]. *Invalid (ledger empty or stalled)*: excluded [observed]. *Invalid (flushing keeps up / wrong type)*: excluded (part 1).
5. **Observed vs. inferred — what the conclusion rests on that was not directly seen.**
   - The pool's total (`SubPool.allocated`) is never read at an instant; "it does not pass the limit except by forced bytes" rests on per-memtable *A_m* (read at each discard) and the 2-decimal `Used total` at flush starts. A memtable's *A_m* at its discard includes bytes forced after it was switched out, so *A_m* ≤ limit + *F* is the observed form.
   - **Why the oversize process exceeds** is inferred: `RssAnon` never falls at a discard in either arm (observed), so glibc keeps freed region memory; that it then grows above the live bytes only with 192 KiB cells is consistent with fragmentation across per-thread arenas, not proven. **Alternative not excluded:** the load-floor control ran only at 256 MiB (as §9b specifies), so non-memtable native growth that scales with the limit (larger flushes, more compaction) would also produce it. The small arm staying within at 1024 MiB (margin 44.6 MiB) argues against a large scaling term, but does not exclude one.
   - That race-loser regions are in flight (allocated, CAS lost, not yet stashed or freed) at the cleanup control's peak is inferred from the count: 15 race-freed 1 MiB regions live at once, more than the stash's 8 per size class [observed count; inferred state].
6. **Deviations and gaps.**
   - **The cleanup-threshold control exceeds the 0.99 runs' node-wide bound** (283.95 against 275.51 MiB; self-check, its single failed check). No §9a row depends on the control. The decomposition (`peak-decomposition.txt`) shows the excess is transient race-loser regions (15 MiB, lifetimes ≤ 77 ms) with three memtables live; §9a's 19 MiB slack counts the stash but **omits regions in flight in a swap race** (up to `concurrent_writes` − 1 = 31 × 1 MiB). In the eight 0.99 runs they were 0–5 MiB at the peak and the bound held (tightest: 512 MiB small, 0.8 MiB margin). Feedback for stage 3, not an amendment: predictions are not re-tuned after a reading.
   - One oversize dump (128 MiB, B3) and one control dump caught no waiting frame (the flush had finished at that instant) [observed].
   - Wait counts lag their triggers by the `sjk` JVM start (1–2 s); A's counts were read after the first flush was enqueued.
   - NMT `Other` grows by 1.0–1.6 GiB under load in every run, the floor controls included, while `RssAnon` grows far less: committed-but-untouched `malloc` memory (direct buffers) [inferred]. It cannot see the memtable regions, as the audit found.

7. **Core question.** The check enforces the accounted bytes exactly as traced: writers park at the limit and the accounted peak moves one for one with the knob (Logic 2–3; part 3). The only way past it is the escape hatch, by the forced bytes (Logic 4; part 3). The physical bytes the allocator holds track the accounted bytes to within region slack at every value (Logic 5; part 3). So `memtable_offheap_space` does cap the off-heap memtable allocation, and usage follows it. It does **not** cap the process's native memory: freed regions stay with the C allocator, and with large cells the process grew 46–332 MiB beyond the bound at 512 MiB and above (part 5 gives the cause as inferred).

**Conclusion (one line):** cluster tier — **Confirmed** at 128, 256, 512 MiB and the default in both arms, **Escape hatch as recorded** (observed above the limit, by ≤ the forced bytes), and **Confirmed for the allocator; the process holds more** in the oversize arm at 512 MiB and the default.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` re-parses the raw files on the node with code of its own (it does not import `cluster-run.py` or `ledger.py`, and pairs discards by allocator id instead of the bracket `ledger.py` uses): **all checks of the unit tier and the eight runs hold; one check fails, the cleanup control's node-wide bound** (`run1/selfcheck.out`, exit 1). Its figures agree with the run script's to the byte (max *L* − *L_idle*, *F*, discard counts).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cassandra.diff`, `system.log`/`debug.log` lines, `jvm-args.txt` re-checked per run. |
| 2. Readings | yes | Flush lines, dumps, trace, ledger, `rss.csv`, NMT re-parsed; every figure in §4.1 re-derived. |
| 3. Matched row | yes | Per-memtable and node-wide bounds re-evaluated from the raw ledger; process bound re-evaluated from `rss.csv`; dose-response monotone in both arms. |
| 4. Excluded rows | yes | No run outside the band; `A_m` ≤ limit + `F` in every run. |
| 5. Observed vs. inferred | yes | The excess's cause and the scaling alternative stay marked inferred; the race-loser count re-derived (`race-regions.txt`). |
| 6. Deviations and gaps | yes | The control's failure is the only failed check, recorded with its decomposition; no row depends on it. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Logic 1–5 of §9a, each tied to a part above. |

### 5.2 Run 2?

**No** — decided 2026-10-13. The verdict rests on observed readings (ledger pairs at every discard, thread dumps, flush lines), and the self-check re-derived them independently. The one inferred part — why the oversize process exceeds — is not something a run 2 of the same design can settle, because it needs a load-floor control at 512 and 1024 MiB or an allocator change (`MALLOC_ARENA_MAX`), which §9 does not contain. Recorded as a recommendation (§8).

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2). §7 is left out.

## 8. Verdict — AI

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed**, with **Escape hatch as recorded** (counter 110 against 100, by the 10 B forced) | run 1 + self-check | 2026-10-13 |
| Cluster | **Confirmed** at 128 · 256 · 512 MiB · default in both arms (writers wait; peak 1 : 2 : 4 : 8; *P_m* − *A_m* within 0–1.6 MiB in all 436 discards); **Escape hatch as recorded** (24 memtables above the limit, by ≤ the forced bytes; 0.014–0.35 % of the limit in the small arm, 1.0–14.8 % in the oversize arm); **Confirmed for the allocator; the process holds more** in the oversize arm at 512 MiB (+45.7 MiB) and the default (+331.5 MiB), cause inferred (glibc retention), the scaling alternative not excluded | run 1 + self-check, no run 2 | 2026-10-13 |

**Recommendations from the result** (for stage 3; not applied): (1) §9a's node-wide slack omits race-loser regions in flight (up to `concurrent_writes` − 1 regions of 1 MiB); the cleanup control exceeded the bound by 8.4 MiB on them. (2) §8's second ground should be restated: the physical bytes track the accounted ones per memtable within region slack (observed); what escapes the knob is the process's C-heap retention, not the allocator. (3) To settle the oversize excess: a load-floor control at 512 and 1024 MiB, and the oversize arm repeated under `MALLOC_ARENA_MAX=2`.

**Feedback filed:** the case file's §10 "Stage-4 feedback" updated, and §8 annotated (dated 2026-10-13) with the observed physical-versus-accounted result and the process retention; committed in `61c22b6`.
