# nopcache_capacity-setcapacity-capacity--autonomous — stage-4 results  <!-- file: results/nopcache_capacity-setcapacity-capacity--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`nopcache_capacity-setcapacity-capacity--autonomous`](../../stage3-ai-deep-read/cases/nopcache_capacity-setcapacity-capacity--autonomous.md)
>
> **Status:** verdict filed (2026-10-28) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true positive** (estimate `positive`, effect `caps`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); the feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository commit `6e6cf92` holds the file as filed (sha256 `361f73086f1c4c9724e8f75a4a5bb69acfdcbb9b4cf2b6d2f3513143765bb13c`). Amendments (section "B-audit", B2i, B3i, B2g/B3g additions, dated 2026-10-27, one same-day change to the N1 put count and heap threshold after a shakedown) are uncommitted. **sha256 after the amendments: `d71b62e0f473b82d1cc55cbd05e4830b88820d19783a9bc86aa9ab6d1af250a6`**, recorded 2026-10-27 before run 1; B2f/B2g/B3f/B3g frozen at this hash; only section D changes after it. |
| **Harness** | `harness/nopcache_capacity-setcapacity-capacity--autonomous/` (uncommitted): `NopCacheCapTest.java`, `unit-run.sh`, `analyze_unit.py`, `cluster-run.py`, `rc.yaml`, `Jmx.java`, `analyze_cluster.py`. md5s at start, at the cluster start and after the run are identical (`run1/harness.md5.start`, `.cluster-start`, `.final`). Patched-source diff: `run1/nopguard.diff`. |
| **Tiers and values** | Unit: guard operand 0, 1 MiB, 64 MiB, -1, Long.MAX on `NopCache`, the `InstrumentingCache` wrapper, an OHC control (16 MiB then 32 MiB), all on the unpatched tree and on `tree-nopguard`. Cluster: arms A (row_cache_size 0, request 64 MiB then 0), AP (A on the patched build), B32 (OHC 32 MiB then runtime 64 MiB), B8 (OHC 8 MiB). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

The literal cannot be varied by configuration, so the design uses two arms that differ in one condition (NopCache vs OHC provider) and a patched-literal build (guard removed). Not a negative-estimate file; no positive control required, but the OHC arms serve as one.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | quantity is memory/disk bytes | Met | A2: row-cache memory (off-heap), read as RowCache `Size` and process `RssAnon`. |
| A | knob varied, >= 3 values incl. default | Partly -> Met | Guard operand 0/1/64 MiB (+ -1, Long.MAX) in B2b; cluster had 2 arms; B3i.2 adds B8 and AP so row-cache sizes 0, 8, 32->64 are compared. |
| A | real resource measured, not only the counter | Partly -> Met | `Size` is the cache's own counter; `RssAnon` added (B3i.4), and its limits are recorded in §4.2. |
| A | usage driven to the limit and past it | Partly -> Met | Filed arm B (64 then 128 MiB) never reaches its cap with 82 MB of data; B3i.2 changes it to 32 -> 64 MiB and adds 8 MiB. |
| B | steps establish; prediction numeric | Partly -> Met | B2i.3, B3i.5 make thresholds exact. |
| B | every outcome has a row; disallow evidence | Partly -> Met | Added rows for the patched-guard arm (B2g/B3g additions); the rejection message is the direct disallow evidence. |
| B | alternative explanations and controls | Met | OHC control, v=0 baseline, patched arm. |
| C | human/AI can follow; exact commands | Partly -> Met | OHC control by hand impossible (B2i.4); pgrep -> ps; commands in B3i. |
| D | harness/prerequisites exist or listed | Met | Step-1 work. |
| D | workload arithmetic reaches the limit | Met (after B3i.2) | 20,000 x 4 KiB = 82 MB serialized vs caps of 8, 32, 64 MiB; local disk 63 GB, heap 2 GiB. |
| D | citations spot-checked | Met | `NopCacheProvider.java:32-42` (guard at 39), `CacheService.java:143-147, 327-333`, `InstrumentingCache.java:82-85`, `Config.java:472-474`, `NodeProbe.java:1088-1094` (order key, row, counter), `OHCProvider.java` (weightedSize = `memUsed`) all hold. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Runnable OHC control via CQL (B2i.4) | Applied 2026-10-27 | sentinels weigh nothing |
| 2 | Cluster arm B changed to 32 -> 64 MiB, add B8 and patched AP (B3i.2) | Applied | cap must be reached |
| 3 | 2,000,000 puts, 8 MiB heap threshold (B2i.3) | Applied 2026-10-27 after shakedown | heap noise ~2 MiB |
| 4 | `ps` process check (B3i.6) | Applied | `pgrep -f` self-match |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28 (unit and cluster, 05:00 to 06:30 MDT) |
| Node | `pc39` (`node1.jason92-321705...`), 40 cores, 251 GiB |
| OS / kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1; Ant 1.10.12; node JVM G1 `-Xms2G -Xmx2G` |
| Local source copy | `~/s4-cc/tree-base` from repository commit `6e6cf92` (`copy-source.sh`; local baseline `e0d60ab`); `~/s4-cc/tree-nopguard` the same plus `NopCacheProvider.java:39` `if (false)`; nothing built in the repository's `cassandra-5.0.9/` |
| Case-file / harness commit | `6e6cf92` as filed; amendments and harness uncommitted |
| Storage | `/dev/sda3` local; node data `~/s4-cc/ncnode` (removed afterwards) |
| Full logs | `pc39:~/s4-cc/run4/` ; excerpts in `results/nopcache_capacity-setcapacity-capacity--autonomous/run1/` |

Own tag `nc`: loopback `127.39.8.1`, JMX 7438.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Commit |
|---|---|---|---|---|---|---|
| 1 | audit | B2c/B2f | OHC control with 1 KiB entries by hand is impossible; arm B never reaches 128 MiB | B2i.4, B3i.2 | 2026-10-27 | none |
| 2 | shakedown | B2f | heap threshold 1 MiB on 10,000 puts is below the JVM's reading noise (-2.2 MiB seen) | 2,000,000 puts, 8 MiB (B2i.3) | 2026-10-27, before freeze | none |
| 3 | run 1 | B3f (RSS clause) | `RssAnon` is not a usable instrument for a 64 MiB off-heap cache here: the process holds 2.9 GB (pre-touched 2 GiB heap) and drifts about 20 to 45 MiB under the read workload in every arm. The prediction "A growth < half of B32" was contradicted (A 34.2 MiB, B32 44.6 MiB). Recorded as a result, not edited (§4.2). | none | 2026-10-28 | none |
| 4 | shakedown (not a reading) | cleanup | an earlier shakedown of the sibling counter files left a `cassandra-stress` java process (pid 735028, 9 h 43 min) after a stalled `-pop dist=uniform` run; found when the session resumed, killed, no `CassandraDaemon` was running | recorded in the counter_cache_size results §3 item 2 | 2026-10-28 | none |

## 4. Run 1

**Scope:** all unit parts on both trees; cluster arms A, B32, B8 (unpatched) and AP (patched). **Command log:** `run1/unit/*/session.log`, `run1/cluster/session.log`; analyzers `run1/analyze_unit_base.out`, `analyze_unit_nopguard.out`, `analyze_cluster.out`.

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| N1 `NopCache.setCapacity` on the unpatched tree | v=0 no exception; v=1 MiB, 64 MiB, -1, Long.MAX: `UnsupportedOperationException: Setting capacity of NopCache is not permitted as this cache is disabled...`; `capacity()` 0 after each | `run1/unit/base/unit.txt` `N1 setCapacity` |
| N1 after 2,000,000 put/putIfAbsent/replace/get | `size` 0, `weightedSize` 0, putIfAbsent/replace true 0 times, get non-null 0 times; heapDelta -2,498,232 B, rssAnonDelta -4,001,792 B | `unit.txt` `N1 puts=` |
| N2 wrapper | `setCapacity(0)` ok; `setCapacity(64 MiB)` throws; `getCapacity()` 0 | `unit.txt` `N2` |
| N3 OHC control (16 MiB unit row cache) | `weightedSize` 5.88 / 11.76 / 16.77 MB then 16,774,464 (>= 14 MiB, <= 16 MiB); `setRowCacheCapacityInMB(32)` no exception, capacity 33,554,432; then 23,519,969 (all 20,000 partitions, between 16 and 32 MiB); RssAnon growth 84.3 MB | `unit.txt` `N3`; `analyze_unit_base.out` (all PASS, 0 FAIL) |
| Patched tree (`if (false)`) | all five requests accepted, `capacity()` stays 0, 2,000,000 puts: `size` 0, `weightedSize` 0, get null; N3 identical to unpatched | `run1/unit/nopguard/unit.txt`; `analyze_unit_nopguard.out` (0 FAIL) |

**Cluster tier** (20,000 partitions x 4 KiB, 4 read passes of 20,000 reads, 0 stress errors):

| Arm | Observable | Reading | Evidence (file) |
|---|---|---|---|
| A (row_cache_size 0) | RowCache Capacity/Size/Entries/Hits | 0 at all 15 samples, including after pass 4 (80,000 reads) | `cluster/A/samples.csv` |
| A | `nodetool setcachecapacity 0 64 0` | exit 2, `error: Setting capacity of NopCache is not permitted as this cache is disabled...` (stack at `NopCacheProvider.java:41`); the key cache was already set to 0 by the same command (entries 0, capacity 0 bytes afterwards): the partial update | `cluster/A/setcap-req64.out`, `summary.json` `info_after_req64` |
| A | `nodetool setcachecapacity 0 0 0` | exit 0 | `cluster/A/setcap-req0.out` |
| AP (patched) | request `0 64 0` | exit 0; Capacity/Size/Entries/Hits 0 at all 15 samples after pass 4 | `cluster/AP/setcap-req64.out`, `samples.csv` |
| B32 | Capacity; Size; Entries after passes 1-2 | 33,554,432; 33,168,384 (98.8 %); 7,808 | `cluster/B32/samples.csv` |
| B32 | request `0 64 0` then passes 3-4 | exit 0; Capacity 67,108,864; Size 64,395,417 (96 %); Entries 15,159; nodetool Row Cache line: 61.41 MiB of 64 MiB | `setcap-req64.out`, `samples.csv`, `summary.json` |
| B8 | Capacity; Size; Entries | 8,388,608; 8,156,160; 1,920 | `cluster/B8/samples.csv` |
| B32 / B8 | Size ratio at 32 vs 8 MiB | 33,168,384 / 8,156,160 = 4.07 | `analyze_cluster.out` |
| all | `RssAnon` growth after load -> end | A 34.2 MiB, AP 19.0, B32 44.6, B8 27.4 | `analyze_cluster.out` INFO; `samples.csv` `rssAnon` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The cap was reached in the control arms: B32 at 98.8 % then 96 % of its caps with 82 MB offered, B8 at 97 % [observed: `B32/B8 samples.csv`]; the knob was applied (`Initializing row cache with capacity of N MiBs` in each `summary.json` `row_init_log`; `cassandra.yaml.<arm>` files); same data and reads in every arm (`tablestats.txt`); `errors_in_log` 0 [observed: `summary.json`]; harness md5 unchanged [observed: `harness.md5.*`].
2. **Readings** — nothing contradicts another, except the secondary `RssAnon` clause: A grew 34.2 MiB, B32 44.6 MiB. `RssAnon` includes the 2 GiB heap (2.9 GB resident) and drifts 19 to 45 MiB in every arm, including the patched arm AP, whose row cache holds nothing; the instrument cannot resolve a 64 MiB off-heap cache against that drift. The prediction "A growth below half of B32 growth" was **contradicted** by the reading and is recorded as such [observed: `samples.csv`].
3. **Matched row** — unit B2g row 1 "NopCache rejects v>0, size and weightedSize stay 0 | claim confirmed": v>0 (four values) threw, `size`/`weightedSize` 0 after 2,000,000 puts [observed: `unit.txt`]; the OHC control grew and plateaued at its cap (16,774,464 of 16 MiB) and accepted the raise [observed: `N3`]. Cluster B3g row 1 "Arm A rejects non-zero capacity, Size/Entries 0 after reads; arm B grows and plateaus at cap | claim confirmed": A rejected with the expected message and held 0 after 80,000 reads; B32 plateaued at 33.2 MB then 64.4 MB, B8 at 8.16 MB [observed: `A/setcap-req64.out`, `samples.csv`]. Additions: the patched arms (unit and AP) accepted the request and still stored nothing [observed: `nopguard/unit.txt`, `AP/samples.csv`] — row "arm AP accepts the request and shows Capacity 0, Size 0 | memory stays 0 without the guard (no-op cache); the guard protects the contract only".
4. **Excluded rows** — "NopCache accepts v>0 or holds entries": no. "OHC control does not grow": no. "arm A accepts or shows Size > 0": no. "arm B Size above Capacity or no growth to 80 %": no. "arm AP Capacity > 0 or Size > 0": no. No Refuted row applies.
5. **Observed vs. inferred** — inferred: that "row-cache memory stays 0" in A is shown by `Size`/`Entries` 0 and not by `RssAnon` (which is uninformative); that the guard does not by itself keep memory at 0 (inferred from AP and the patched unit tree storing nothing).
6. **Deviations and gaps** — (a) the `RssAnon` clause failed as an instrument (§3 item 3); real off-heap memory of arm A is evidenced by `Size`/`Entries`/`Hits` 0 and by `NopCache` having no storage, not by RSS. (b) The filed arm B (64 -> 128 MiB) was replaced (B3i.2). (c) The unit control is the unit yaml's 16 MiB row cache through CQL, not a hand-built cache. (d) One run per arm.
7. **Core question** — the constraint (a zero-only capacity on the disabled cache) is enforced: a request to raise it is refused, and the row cache holds 0 entries and 0 bytes after 80,000 reads, while the same workload fills an enabled row cache to its cap (8, 32, 64 MiB), proportionally (ratio 4.07 for 32 vs 8). The patched arms show the 0 does not come from the guard but from `NopCache` storing nothing; so the check caps row-cache memory at 0 in effect (with the guard as contract protection).

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 (with the patched-arm additions) — confirmed; the `RssAnon` secondary clause was not supported by the instrument.

## 5. Self-check of run 1 — AI

I re-opened the cited copies under `results/nopcache_capacity-setcapacity-capacity--autonomous/run1/`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `B32/samples.csv` end-pass rows 33,168,384 and 64,395,417; `B8` 8,156,160; `summary.json` init logs; stress `Total errors` 0 (the script asserts it) |
| 2. Readings | yes | `A/samples.csv` 15 rows all 0; `rssAnon` column shows 2.86 to 2.93 GB in every arm |
| 3. Matched row | yes | `A/setcap-req64.out` exit 2 and message; `unit.txt` N1/N2/N3 lines; `AP/setcap-req64.out` exit 0 |
| 4. Excluded rows | yes | `analyze_cluster.out`: all checks PASS except the RSS clause; `analyze_unit_*.out` 0 FAIL |
| 5. Observed vs. inferred | yes | inferred items do not carry the matched row |
| 6. Deviations and gaps | yes | listed |
| 7. Core question | yes | logic follows B1: refusal, zero storage, control growth, patched arm |

**Run 2?** No (2026-10-28): counts are exact, the one failed clause is an instrument limit that does not bear on the matched row.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison

Not applicable.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps).

**Claim tested:** On a node started with `row_cache_size: 0MiB`, a request to set a non-zero row cache capacity at runtime is rejected and row-cache memory stays 0 with row caching enabled on a table and a read workload; with `row_cache_size > 0` at startup the same request succeeds and memory use grows toward the cap. (B1) "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 (NopCache rejects v>0, size and weightedSize stay 0), with the patched-guard addition | caps | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed — B3g row 1 (arm A rejects, Size/Entries 0; arm B grows and plateaus at cap), with the AP addition; RSS clause not supported | caps | run 1 + self-check | 2026-10-28 |

Nuance: the cap on memory is 0 because `NopCache` stores nothing; the guard only turns a raise request into an error (patched build accepts the request and still holds nothing).

**Feedback filed:** section D of the case file updated (uncommitted); audit amendments in its "B-audit" section.
