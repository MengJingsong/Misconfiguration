# networking_cache_size-allocateMoreChunks-memoryUsageThreshold — stage-4 results  <!-- file: long-path/results/networking_cache_size-allocateMoreChunks-memoryUsageThreshold.md -->

> **Case:** [`networking_cache_size-allocateMoreChunks-memoryUsageThreshold`](../../stage3-ai-deep-read/cases/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md)
>
> **Status:** **Closed 2026-10-19 — all tiers verified at stage 4 (verdicts below).** verdict filed (2026-10-15) — **unit: Confirmed; cluster: Confirmed** (§9a row 1, including §8): with 192 MiB of held response frames the pool stopped at *T*′ = 16 · 32 · 64 · 96 · 128 MiB exactly and the rest went to overflow (1,390 · 1,262 · 1,006 · 750 · 494 refusals), so the stall's direct rise was flat at 182.8–183.3 MiB whatever the knob, while the memory retained afterwards followed the knob (9.6 · 25.2 · 57.0 · 89.0 · 121.1 MiB); a 48 MiB demand left the pool at 48 MiB, not at its limit, at 64 MiB and up; **arm L: leak as derived** — every large native-v5 request leaves its frame stashes unreturned (`OverflowSize` +58,724,288 B and 5,373,952 B of pooled slots for 64 requests, exactly); no run 2
> 
> **Outcome class:** true positive — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Path:** long. One results file per path, each in its path's folder.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base commit `d47b932` (the last commit touching the case file) plus the step-0 amendments of 2026-10-15 (uncommitted at freeze). §9 hash before the amendments `369bafaef99935e66796481f36ed757011ec5e89`, §9a `1d1fbf68c99b097ab86853fa34d51735e3b45971`; **after the amendments §9 `f322bcbcf4f04719519de145aeff930cb3e25bc4`, §9a `1d1fbf68c99b097ab86853fa34d51735e3b45971` (unchanged)**. §9a is frozen at this version. Recorded 2026-10-15 03:35 EDT, before any reading of this case existed (no folder for it under `pc57:~/stage4-logs/` or `~/stage4-harness-run/`). |
| **Harness** | `../harness/networking_cache_size-allocateMoreChunks-memoryUsageThreshold/`, written by this session after the freeze (§1.2). Node copy `pc57:~/stage4-harness-run/ncs/`. |
| **Tiers and values** | Unit: U1 upstream `BufferPoolTest`, `BufferPoolAllocatorTest`; U2–U3 `NetworkingPoolCeilingTest`; U4 `NetworkingPoolConfigTest`. Cluster (one node on `pc57`, 4 GiB heap): `networking_cache_size` 16 · 32 · 64 · 100 MiB and unset (128 MiB), each with A (4), M (48), B (192 held 1 MiB responses) and after-B; arm L (64 × 1 MB INSERTs over v5) at the default. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-15 |

### 1.1 Design audit

Citations re-read against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Direct bytes of the `networking` pool's slabs (§7). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 16 · 32 · 64 · 100 MiB and unset (9b); restart-only (`BufferPools.java:44-45` is `static final`). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | `java.nio` direct `MemoryUsed` minus the chunk-cache `Size`; NMT recorded; the gap (Netty arenas outside `java.nio`) named (9d). |
| A. Core question | usage driven to the limit and past it | Met | *D* = 192 MiB exceeds every *T*′ by ≥ 64 MiB, ≫ *S* (≤ 4.2 MiB: `net.ipv4.tcp_wmem` max 4,194,304 on `pc57`, client `SO_RCVBUF` 64 KiB). |
| B. Logic | each step says what it establishes | Met | 9a Logic (1)–(6). |
| B. Logic | prediction stated in numbers or a clear relation | Met | *T*′ per value, M band [48, 56] MiB, B band [186.8, 193] MiB, after-B −6 B per overflowed frame, arm L 58,724,288 B exactly. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | 13 rows incl. invalid (client read, no refusal, OOM) and arm L's three outcomes. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | `P` per value plus `refuse`/`overflow` counts and `Misses`. |
| B. Logic | alternative explanations and their controls | Met | A (below every pool), M at ≥ 64 MiB (recycling control), after-B floor, idle floor. |
| C. Specific | a human can follow it from the intro and §9a | Met | — |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after rec. 1 | The `freed` rule as written counts every `BufferPoolAllocator$Wrapped` deallocation, including Netty's inbound read buffers (the same class, `BufferPoolAllocator.java:108-160`), so "held = encoded − freed" would not be the held response frames (rec. 1). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | 9c table (hold times, 30 s defect bound). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Listed as step-1 work, reusing the sibling's `PoolSampler.java` and `hold.btm` style. Private clone `~/cassandra-run3`; the node is shared in turns with another session (rec. 3). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 8 × 1 MiB rows; ≈ 3 min per value; direct peak ≈ 200 MiB against an 8 GiB limit. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Read in context: `BufferPools.java:38-55` (threshold, `recyclePartially = false`, INFO line); `DatabaseDescriptor.java:573-574` (default `min(128, maxMemory/16 MiB)`: 128 MiB at a 4 GiB heap); `BufferPool.java:436-470` (check, CAS, slab, OOM fallback), `:936-958` (size > 128 KiB misses), `:206-261`; `Flusher.java:46-48` (`MAX_FRAMED_PAYLOAD_SIZE` = min(131,072, 131,072 − 12) = 131,060, so a payload buffer of 131,070 B), `:150-213` (a ≥ 131,060-B response goes through `flushLargeMessage`, one `writeAndFlush` per frame, no writability check), `:225-260`; `FrameEncoder.java:32`, `:39-110`; `BufferPoolAllocator.java:100-160`; `CQLMessageHandler.java:755-840` (`LargeMessage.assembleFrame()` wraps the stashes with `Unpooled.wrappedBuffer`, `onComplete()` processes without `releaseBuffers()`; `onCorruptFrame()` and `abort()` release); `sysctl` values above. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Count only frame-sized buffers in `encoded` (payload capacity ≥ 131,070) and `freed` (`wrapped.capacity() >= 131070`). | Applied 2026-10-15 (9 intro, 9c `net.btm` row); uncommitted | Inbound read buffers share `Wrapped`; the response frames are the only frame-sized ones in A/M/B. |
| 2 | Ruling (5): search JIRA for the large-request leak before the run. | Done 2026-10-15, recorded in the 9 intro: no matching ticket; CASSANDRA-20753 (a `Wrapped.capacity` leak on the internode decoder) is fixed in 5.0.7 and is a different path. Search: Apache JIRA REST `text ~ "CQLMessageHandler"` (10 issues) and `text ~ "BufferPool leak" OR "OverflowSize" OR "large message leak"` (90 issues), summaries read. | Stage 3 asked for it; it does not change the design. Supporting observation from an earlier run: `native_transport_receive_queue_capacity` saw the networking pool's `UsedSize`/`OverflowSize` rise to 4.9 GB in its large-request arms and never fall (its results §4, "cause open"). |
| 3 | Run from the private clone `~/cassandra-run3`; take the node only between the other session's lifetimes. | Applied 2026-10-15 (9 intro) | As in the two other cases audited this session. |

**Agreement criteria** — not filled (run 2 not chosen yet).

### 1.2 Instrument checks (not readings)

- **Byteman:** `net.btm` type-checks (`TestScript: no errors`).
- **Unit instrument run** (`unit-run.sh instrument`, 03:38–03:41, `~/cassandra-run3`): U1 `BufferPoolTest` 38/38,
  `BufferPoolAllocatorTest` 9/9; `NetworkingPoolCeilingTest` 2/2 and `NetworkingPoolConfigTest` 1/1, 104 checks, 0 MISMATCH.
  U3 needed no change of the FIFO length (8). Not a reading; run 1 repeats the tier.
- **Build** (`cluster-run.py shakedown1 build`, 03:46–03:47): `ks1.t` with 8 rows of 1 MiB over protocol 4, one `Data.db`; the
  data directory `~/stage4-ncs/data` is kept for every later lifetime (9b reset rule).
- **Shakedown 1** (`cluster-run.py shakedown1 instrument`, 16 MiB, 03:47–03:48): `Capacity` 16,777,216; `stall-client.py 8`
  framed all 64 full frames in 1.0 s; at the peak 45 frames held (`encoded` 64 − `freed` 19), server `Send-Q` 2,488,848 B and
  client `Recv-Q` 65,496 B (*S* = 2.55 MB ≈ 19.5 frames, so held + *S* accounts for the 64); after the close 0 held, `O` 0;
  `P` 8 MiB throughout (no refusal at 8 MiB of demand). Instrument check passed; no harness change.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-15 | — |
| Node (CloudLab name and type) | `pc57` (`node0.jason92-319347`), 32 cores, 251 GiB RAM; the session ran on the node itself | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local `cassandra-src` clone commit | `~/cassandra-run3` at `cassandra-5.0.9` (`b5f2a54210d5`), cloned and built 2026-10-15 03:20 for this session's runs | — |
| Case-file commit / harness commit | case file: base commit plus the uncommitted step-0 amendments (§1); harness: uncommitted, node copy checked by `md5sum` (`~/stage4-harness-run/*.md5`) | — |
| Storage for node data | `~/stage4-ncs/` on `/dev/sda3` (local disk, ext4) | — |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/ncs/run1/<label>/` (unit: `~/stage4-logs/ncs/unit-run1/`) | — |

## 3. Runbook defects

None. (Before run 1: the build and one shakedown, §1.2; the harness was not changed after it.)

## 4. Run 1

**Scope:** unit tier (U1–U4) 2026-10-15 03:42–03:45; cluster 05:10–05:30 EDT (`chainB.sh`): `networking_cache_size` 16, 32, 64,
100 MiB and unset, each its own lifetime (control, A, M, B, after-B), then arm L at the default. The dataset of the build
lifetime (03:46) was kept, as 9b says. **Command log:** `session.log` per lifetime on the node; excerpts in
`networking_cache_size-allocateMoreChunks-memoryUsageThreshold/run1/` (`unit/`, `value-<v>/` and `leak/` with `summary.txt`,
`phases.csv`, `ss/`, `bm-excerpt.txt`, `log-lines.txt`, `nmt-*.txt`; `selfcheck.py`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/`): U1 `BufferPoolTest` 38/38, `BufferPoolAllocatorTest` 9/9; U2–U4 3/3, **104 checks, 0 MISMATCH**.
U2: pooled = *T*′ = 0 · 0 · 16 · 16 · 64 · 96 MiB for *T* = 0 · 4 · 16 · 20 · 64 · 100 MiB, pooled buffers 0 · 0 · 128 · 128 · 512 ·
768 of 131,072 B, the first other buffer exactly 131,070 B of overflow; five more 6 × 131,070 = 786,420 B, `Misses` +5;
`tryGetAtLeast` null; overflow back to 0; the same count again all pooled with no new slab. U3 (FIFO 8, 20,000 steps):
`recyclePartially = false` — `recyclePartial` 0, pooled **8 MiB**; `true` — `recyclePartial` 5,554, pooled **64 MiB** (the
limit). U4 (the real instance at 16 MiB): `MAX_FRAMED_PAYLOAD_SIZE` 131,060; payloads 1–128 pooled (131,072), pooled 16 MiB;
payload 129 overflow 131,070; after `finish()` and `release()` `OverflowSize` **−6**, pooled 16 MiB.

**Cluster tier** (`value-<v>/summary.txt`, `phases.csv`; `P` from the `made` lines, `O` = `OverflowSize`; *S* = server
`Send-Q` 2,488,848 + client `Recv-Q` 65,496 = 2,554,344 B in every scenario; the direct reading is `java.nio` direct minus the
chunk-cache `Size`, as a rise over the idle median ≈ 48.62 MB)

| *T* | *T*′ | Idle `P` | A (*D* 4 MiB): `P`, `O` | M (48 MiB): `P`, `O_peak` | B (192 MiB): `P`, `O_peak`, refusals | B direct rise | After B: `O`, direct rise | Evidence |
|---|---|---|---|---|---|---|---|---|
| 16 MiB | 16 MiB | 8 MiB | 8 MiB, 0 | **16 MiB**, 31.19 MB | **16 MiB**, 182.18 MB, 1,390 | 192.20 MB | −9,768 B (= −6 × 1,628), 10.01 MB | `value-16/` |
| 32 MiB | 32 MiB | 8 MiB | 8 MiB, 0 | **32 MiB**, 14.42 MB | **32 MiB**, 165.40 MB, 1,262 | 191.79 MB | −8,232 (−6 × 1,372), 26.38 MB | `value-32/` |
| 64 MiB | 64 MiB | 8 MiB | 8 MiB, 0 | **48 MiB**, 0 | **64 MiB**, 131.85 MB, 1,006 | 191.64 MB | −6,036 (−6 × 1,006), 59.79 MB | `value-64/` |
| 100 MiB | 96 MiB | 8 MiB | 8 MiB, 0 | **48 MiB**, 0 | **96 MiB**, 98.30 MB, 750 | 191.67 MB | −4,500 (−6 × 750), 93.36 MB | `value-100/` |
| unset (128 MiB) | 128 MiB | 8 MiB | 8 MiB, 0 | **48 MiB**, 0 | **128 MiB**, 64.75 MB, 494 | 191.78 MB | −2,964 (−6 × 494), 127.03 MB | `value-default/` |

Every lifetime: `Capacity` = *T* in every sample and the startup line `… and <T>.000MiB for networking`; every scenario framed
its 8 *R* full frames within 1.5 s; held frames at B's peak 1,517 (of 1,536; the kernel holds the rest), 0 after the close;
overflow bytes = 131,070 × refusals exactly (no remainder: the small last frame of each response was pooled); `Misses` =
refusals; one INFO `Maximum memory usage reached … for networking buffer pool` per lifetime; no `failed to allocate chunk`.
NMT `Other` (recorded only): ≈ 252–269 MB idle, 0.90–1.09 GB at B's peak, 0.80–0.95 GB after B.

**Arm L** (`leak/`): 64 of 64 one-MB INSERTs acknowledged over protocol v5; 30 s after the connection closed: **`OverflowSize`
+58,724,288 B** (= 64 × 7 × 131,081), **`UsedSize − OverflowSize` +5,373,952 B** (= 64 × 83,968); overflow bytes added
58,724,288, **subtracted 0**; `java.nio` direct 48.62 MB idle → 124.15 MB → 65.38 MB after `jcmd GC.run`, while `OverflowSize`
stayed at 58,724,288.

### 4.2 Conclusion and logic

1. **Validity.** Valid: at 192 MiB of demand every value refused (the limit was passed) [observed: refusals 494–1,390]; the
   client never read (held frames 1,517 at B's peak, *S* 2.55 MB) [observed: `phases.csv`, `ss/B.txt`]; the knob took effect
   [observed: `Capacity`, startup line]; no OOM fallback.
2. **Readings.** Nothing unusual. The overflow counted no small remainders (§9a allowed < 1 KiB per response).
3. **Matched row.** "B: `P` = *T*′ at every value, moving in 8 MiB steps, refusals and overflow allocations counted, `Capacity`
   = *T*; the stall's direct rise flat across *T*; after B the overflow returns to ≈ 0 and the retained rise follows *T*′ −
   `P_idle`; M leaves `P` in [48, 64] MiB at *T* ≥ 64 MiB" — **Confirmed**: `P` = 16 · 32 · 64 · 96 · 128 MiB [observed], the
   direct rise 191.64–192.20 MB (spread 0.56 MB ≤ 12 MiB) [observed], after B `O` = −6 B × overflowed frames exactly and the
   retained rise 10.0 · 26.4 · 59.8 · 93.4 · 127.0 MB = *T*′ − 8 MiB + 1.6–1.7 MB [observed], M at 64–128 MiB: `P` = 48 MiB
   [observed].
4. **Excluded rows.** "M fills `P` to *T*′" — no, 48 MiB at 64, 100, 128 MiB. "Direct rise falls with *T*" — flat. "`P`
   passes *T*′" — never (`selfcheck.txt`). "`P` does not move with *T*" — it does. "`O` > 0 while `P` < *T*′" — A: `O` 0; M
   at 16/32 only after `P` = *T*′. "After B, `O` stays above zero or held frames" — `O` −2,964 to −9,768 B, held 0. "Held
   frames near zero", "no refusal at 128 MiB", "failed to allocate" — none. Arm L: residuals at the predicted figures → "Leak
   as derived", not "No leak" or "Not confirmed".
5. **Observed vs. inferred.** That the arm-L residuals are the never-released stashes of the large requests (the 7 overflow
   stashes of 131,081 B and one pooled 83,968-B stash per request) is inferred from the exact figures and the code
   (`CQLMessageHandler.onComplete()` never calls `releaseBuffers()`); the trace counts only the overflow bytes added and
   subtracted (58,724,288 vs 0).
6. **Deviations and gaps.** None. The retained rise after B is 1.6–1.7 MB above *T*′ − `P_idle` in every lifetime (within the
   ± 2 MiB band; the B frames' small last buffers and Netty-side direct allocations, not separated).
7. **Core question.** The knob caps the networking pool's slabs at *T*′ exactly (Logic 2–3: `P` = *T*′, refusals counted) but
   not the node's direct memory during a burst, which followed the demand (182.8–183.3 MiB at every value, Logic 4); what it
   bounds is what stays reserved afterwards (*T*′, Logic 4), and below the limit the pool grows only to the demand (Logic 5).
   Large native-v5 requests leak their frame stashes' accounting and pooled slots (Logic 6).

**Conclusion (one line):** §9a row 1 — **confirmed**, including §8; arm L — **leak as derived**.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (none of the run script's code; `bm.trace` `made` and `dump` lines, `samples.csv`, `ss/`, `system.log`,
`cassandra.yaml`, the session log's phase times) re-derives every figure: **75 checks, 0 failed** (`selfcheck.txt`). Its first
version disagreed on 3 counter readings (values 64 and 100) because it matched a phase to the dump line up to one second
*after* the phase's truncated log time, which at B fell inside the stall; corrected to the last dump at or before that second
(counters are flat during an idle or a hold). No reading changed.

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | refusals and held frames re-derived from `bm.trace`; `Capacity` in every sample |
| 2. Readings | yes | overflow bytes = 131,070 × refusals in `bm.trace` |
| 3. Matched row | yes | `P` from `made` lines; direct rise and after-B rise from `samples.csv` |
| 4. Excluded rows | yes | M at ≥ 64 MiB = 48 MiB; after-B `O` = −6 × overflowed frames |
| 5. Observed vs. inferred | yes | arm L residuals from `samples.csv` and the trace's added/subtracted bytes |
| 6. Deviations and gaps | yes | after-B rise within ± 2 MiB at every value |
| 7. Core question | yes | follows Logic 1–6 |

### 5.2 Run 2?

**No** — 2026-10-15. Every figure is re-derived from raw files and equals an exact prediction (to the byte for `P`, the −6 B
drift and arm L). Arm L confirms a derived leak; the evidence is exact accounting at two gauges and the trace, so a repeat
would add nothing; the leak should instead go upstream (§8 feedback).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** (U2 ceiling *T*′ at six *T*; U3 recycle contrast: 8 MiB vs 64 MiB; U4 the real instance and the −6 B drift) | run 1 + self-check | 2026-10-15 |
| Cluster | **Confirmed** (row 1, including §8: the burst follows the demand, the retained memory follows the knob, the pool grows only to the demand below its limit); arm L **leak as derived** | run 1 + self-check | 2026-10-15 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" and §10 Target-3 note (2026-10-15, uncommitted): the large-request
leak is observed (no JIRA ticket found, results §1.1 rec. 2: candidate for an upstream report); the `native_transport_receive_
queue_capacity` run's 4.9 GB `OverflowSize` that never fell (its large-request arms) is consistent with it (inferred, not re-tested).
