# ip_cache_max_size-cidrgroupsmappingcache-iptocidrgroupscache--autonomous — stage-4 results  <!-- file: results/ip_cache_max_size-cidrgroupsmappingcache-iptocidrgroupscache--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`ip_cache_max_size-cidrgroupsmappingcache-iptocidrgroupscache--autonomous`](../../stage3-ai-deep-read/cases/ip_cache_max_size-cidrgroupsmappingcache-iptocidrgroupscache--autonomous.md)
>
> **Status:** verdict filed (2026-11-12)
>
> **Outcome class:** true positive (estimate `positive`; unit **Confirmed — caps**, cluster **Confirmed — caps**)
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

The protocol behind each section is in
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `f74aade6` (the case file is untracked there; the coordinator commits it). Filing sha256 (`_INDEX.md` §4): `a10798882a146ddebe410de6d1bca0335e9acc6226addc999cb62a13f01de3e1`. sha256 of the whole file after the audit's amendments AM1-AM4 (2026-11-12, section D only): `eb772e9d1cd3aa6a398ff399d46940a2f688dfaf18bedc0ae0367ba42091f142`. sha256 of the frozen prediction and conclusions tables (text of B2f, B2g, B3f, B3g: from `**B2f.` up to `**B2h.` and from `**B3f.` up to `**B3h.`, concatenated, 48 lines; unchanged by the audit): `749f0e43fe35823424ac29c6bc749096d233046b64e3ef4d8d90a2ee3dd58123`. Frozen 2026-11-12T02:55Z, before any reading. Section D's later feedback lines are outside the table hash. |
| **Harness** | `harness/ip_cache_max_size-cidrgroupsmappingcache-iptocidrgroupscache--autonomous/` (files listed in its README; not committed by this session, the coordinator commits) |
| **Tiers and values** | Unit (B2): CQLTester probe, `ip_cache_max_size` in {0, 100, 100000, 1000000}, N = 600,000 matched lookups plus 1,000 unmatched. Cluster (B3): one node, 1 GiB heap, K in {100, 100000, 1000000}; W1 = 600,000 JMX lookups, W2 = 2,000 native-protocol logins from distinct loopback sources. Positive control in both tiers: the cap above N (1,000,000). |
| **Audit bottom line** | **Ready after amendments** — 2026-11-12 (AM1-AM4 applied in the case file's section D) |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A1/A2: the knob counts cache entries, not bytes; A2 derives the byte size per entry (~120-135 B) and the sketch size, so it is a count with a derivable byte size, and the claim is about heap (B1). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b: 0, 100 (default), 100000, 1000000; B3b: 100 (default), 100000, 1000000. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d: heap used after GC besides `estimatedSize()`; B3d: live-object histogram (retained `Inet4Address` etc.) and heap; the gap (no entry-count metric on a node) is named in B3d. AM3 fixes which heap number is read. |
| A. Core question | usage driven to the limit and past it | Met | N = 600,000 distinct matched IPs > 100,000 > 100 (B2c, B3c); W2's 2,000 > 100. |
| B. Logic | each step says what it establishes | Met | B2c-B2e, B3c-B3e; controls in B2h/B3h name what each rules out. |
| B. Logic | prediction stated in numbers or a clear relation | Met after AM4 | B2f/B3f give counts and MB bands; "≈", "a few", "a handful", "≫" had no tolerance: AM4 defines them (no value changed). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g: confirmed, count not capped, count capped but heap grows, positive control failed, nulls cached. B3g: confirmed, cap exceeded, retention elsewhere, per-entry cost off, positive control failed, W2 rows. Flat-across-values is covered by "positive control failed". A reading matching no row is "Not confirmed (no matching row)". |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Direct evidence of the eviction branch: after N > cap distinct inserts the exact entry count equals the cap (unit `estimatedSize`) and the retained key count is the cap (cluster); no other mechanism removes entries with the refresh at 1440 min. No eviction counter is read (Caffeine stats are off); named here as a gap, not needed. |
| B. Logic | alternative explanations and their controls | Met | Knob not reaching the cache: `policyMaximum` printout (B2h); unmatched IPs not cached: 192.168 control; periodic flush: refresh 1440; attribution to this cache on a node: `reloadcidrgroupscache` flush (B3h); workload not moving heap: K/max = 1,000,000. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate line, A2-A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Full test class and both client programs are given (B2e, B3e). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Paths (B2a) and ports (B3a) do not fit the run node, and the heap reading of B3d/B3e has two sources: AM1-AM3. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, `ant build-test` / `ant jar` (environment.md); the probe and the client programs are step-1 work (harness). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 600,000 entries × ~130 B ≈ 80 MB against a 1 GiB test heap and a 1 GiB node heap; disk < 1 GB; JMX at a few thousand calls/s ≈ minutes. Total memory on apt179: one 1 GiB test JVM or one 1 GiB node at a time, well within 14 GiB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in the copy (cassandra-5.0.9): `DatabaseDescriptor.java:1759-1771` (default 100, key, parseInt); `CIDRGroupsMappingCache.java:45, 59-62` (`maximumSize(getIpCacheMaxSize())`, `ImmediateExecutor`), `:83` (`invalidateAll` on reload), `:131-134` (lookup → `get`); `CassandraCIDRAuthorizer.java:47` (static cache), `:109-111`, `:121-128` (MONITOR mode reaches the lookup for roles without restrictions, superusers included); `CIDRPermissionsManager.java:125` (superusers unrestricted unless `cidr_checks_for_superusers`, which does not skip the lookup in MONITOR mode); `CIDRGroupsMappingManager.java:60, 234-244`; `CIDRGroupsMappingIntervalTree.java:113, 320, 328`; `ClientState.java:565-580`; `AuthTestUtils.java` (`LocalCassandraCIDRAuthorizer(mode)`, `insertCidrsMappings` reloads); `SchemaLoader.setupAuth` (5 args, calls `setup()`); `build.xml:94, 1192` (`test.jvm.args`); Caffeine 3.1.8 (`parent-pom-template.xml:1059-1061`, `build/lib/jars/caffeine-3.1.8.jar`). The Caffeine-internal lines (eviction loop, sketch) were not re-read (no Caffeine source on the node). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| AM1 | Work tree and build per environment.md (copy-source.sh copy on `/mydata/jingsong-cass-s4/o04`; `ant build-test`, then `ant jar` after the unit tier) | applied 2026-11-12 (section D; case file untracked, no commit) | B2a's paths are another user's home and `/tmp`; the node runs from the jar |
| AM2 | Ports 7300/7301/7499/9342 on the shared node; client programs take the port | applied 2026-11-12 | 7000/7199/9042 are reserved for other work on apt179 |
| AM3 | Heap Δ from the `GC.class_histogram` total (live), `heap_info` recorded beside it | applied 2026-11-12 | B3d/B3e named two heap sources; repo lesson: `heap_info` after `GC.run` is not live heap |
| AM4 | Tolerances for "≈", "a few", "a handful", "≫" | applied 2026-11-12 | a prediction must be contradictable; no value changed |
| R-a | The K=100 cluster prediction (Δ ≈ +100) is inside the stated baseline noise (± a few hundred): the default cap cannot be told from "no entries" on a node; K=100 is informative only against the ≫K row | left for stage 3 | design sensitivity, not needed for a valid run |
| R-b | Read Caffeine's eviction count (`recordStats()` is off; or a Byteman rule on `evictEntry`) as direct evidence of the disallow branch | left for stage 3 | count = cap after N > cap inserts already shows it |

**Agreement criteria** — not applicable (no run 2 planned).


## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-12 (UTC): unit 02:58-02:59; cluster K=100 03:02-03:13, K=100000 03:14-03:25, K=1000000 03:26-03:37; shakedowns 02:56-02:57 (unit) and 02:59-03:01 (cluster) | not done |
| Node (CloudLab name and type) | `apt179` (`node1.jason92-325433.misconfiguration-pg0.apt.emulab.net`), 16 cores, ~15 GiB RAM; shared with OOM-exp (nothing of it touched); ports 7300/7301/7499/9342 (AM2) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, 5.15.0-198-generic | |
| JDK (`java -version`) | openjdk 11.0.33 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `systems/cassandra/source/` at repository commit …) | `copy-source.sh` copy made locally at `/mydata/jingsong-cass-s4/o04-src` from repository HEAD `f74aade6` (tag `cassandra-5.0.9`), rsynced to `apt179:/mydata/jingsong-cass-s4/o04/src`; `ant build-test` (1 min 46 s), `ant jar` after the unit tier | |
| Case-file commit / harness commit | both untracked at HEAD `f74aade6` (the coordinator commits); case-file sha256 in section 1; harness md5 (end of run): `IpCacheMaxSizeProbeTest.java` 128b458a…, `unit-run.sh` a2246caa…, `cluster-run.sh` 841124088…, `configure.py` 085cf617…, `JmxProbe.java` d422df5f…, `NativeProbe.java` 05327a6c…, `cluster-analyze.py` 638e5c75…; `selfcheck.py` was fixed once (an off-by-one in its own fragment pairing) before its output was used | |
| Storage for node data | `/mydata` on apt179 (local LVM, 1.6 TB free); node heap 1 GiB (`MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M`); unit test JVM 1 GiB (`maxmemory=1024m`) | |
| Full logs (path, outside the repo) | `apt179:/mydata/jingsong-cass-s4/o04/logs/run1/` (`unit/unit-<M>.log`, junit XML; `cluster-K<K>/` with `session.txt`, `h-<K>-*.txt` histograms, `heap-<K>-*.txt`, `w1.txt`, `w2.txt`, `node-logs/system.log`, GC logs); shakedowns in `logs/shake/` | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | unit shakedown | B2e step 2 | `grep PROBE ... TEST-*.xml` finds nothing: in this build the test JVM's stdout is routed through a logger (`SubstituteLogger.java:222`) into the ant output, and each `printf` argument arrives as a separate log line, so the final PROBE line is split over 10 lines. | Harness only: `unit-extract.py` rebuilds the PROBE lines from the fragments of the ant log (the data is complete there). No case-file change needed (the test and its output are as filed). | 2026-11-12 | n/a |
| D2 | setup | B2a / AM1 | `/mydata` on apt179 is root-owned, so `/mydata/jingsong-cass-s4` could not be created by the run user. | Created `/mydata/jingsong-cass-s4` with `sudo mkdir` + `chown jason92`; everything else under it as the run user. Environment note, not a case defect. | 2026-11-12 | n/a |

The ports, paths and heap-reading choices were fixed in the audit (AM1-AM3), before the run, not as defects.

## 4. Run 1

**Scope:** unit tier (B2) all four values as filed; cluster tier (B3) all three K values as amended (AM1-AM4), one fresh node and wiped data per K, W1 = 600,000 JMX lookups, W2 = 2,000 native logins. **Command log:** `ip_cache_max_size-cidrgroupsmappingcache-iptocidrgroupscache--autonomous/run1/unit-session.txt`, `run1/cluster-K{100,100000,1000000}-session.txt`; raw readings `run1/unit-probe-lines.txt` (rebuilt from the ant logs), `run1/cluster-histogram-excerpts.txt`; analyzer output `run1/unit-analysis.txt`, `run1/cluster-analysis.txt`; self-check `run1/selfcheck.txt`. (`run1/` below means `ip_cache_max_size-cidrgroupsmappingcache-iptocidrgroupscache--autonomous/run1/`.)

### 4.1 Readings

**Unit tier** (N = 600,000 matched lookups, 1,000 unmatched; one forked JVM per value; every test `Tests run: 1, Failures: 0, Errors: 0`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `policyMaximum` (knob reached the cache) | 0 / 100 / 100000 / 1000000 = the set value in every run | `run1/unit-probe-lines.txt` |
| outsideGroups size after 1,000 unmatched (192.168.x.y) lookups | 0 in all four runs | same |
| `estimatedSize` after `cleanUp()` (max = 0 / 100 / 100000 / 1000000) | 0 / 100 / 100000 / 600000 | same |
| `maxSampledSize` (every 65,536 lookups) | 0 / 100 / 100000 / 600000 | same |
| heapDelta (used after 3× GC, after minus before the loop) | 77,864 B (0.07 MB) / 79,864 B (0.08 MB) / 14,171,560 B (13.52 MB) / 84,981,856 B (81.05 MB) | same |
| relations | heapDelta(1e6)/heapDelta(1e5) = 6.00; heapDelta(100) − heapDelta(0) = 2,000 B; (heapDelta(1e6) − heapDelta(1e5)) / 500,000 entries = 141.6 B per entry (sketch difference included) | `run1/unit-analysis.txt` (22 PASS, 0 FAIL) |

**Cluster tier** — deltas against `base2` from `GC.class_histogram` (live objects after a forced full GC); heap Δ = histogram `Total` (AM3); baseline noise = base2 − base1.

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| all K | baselines | Inet4Address base2 − base1; Total bytes base2 − base1 | −2 instances in each K; −137 KB / −180 KB / −139 KB | `run1/cluster-analysis.txt` |
| all K | setup | `getcidrgroupsofip 127.1.0.1`; W1 first/last result | `lo`; `[lo]` / `[lo]` | `run1/cluster-K*-session.txt` |
| K = 100 | W1 (600,000 lookups, 209.6 s) | ΔInet4Address / ΔInetAddressHolder / ΔCHM$Node / ΔPSMS | +102 / +102 / +149 / +100 | `run1/cluster-analysis.txt`, `run1/cluster-histogram-excerpts.txt` |
| K = 100 | W1 | heap Δ (histogram Total; heap_info) | +0.14 MB; +0.14 MB | same |
| K = 100 | w1b (60 s later) / flushed / W2 (2,000 logins, 297.5 s) | ΔInet4Address | +100 / +2 / +182 (ΔPSMS after W2 +200) | same |
| K = 100000 | W1 (206.6 s) | ΔInet4Address / Holder / CHM$Node / PSMS | +100,002 / +100,002 / +100,029 / +100,000 | same |
| K = 100000 | W1 | heap Δ (Total; heap_info) | +13.58 MB; +13.58 MB (142.4 B per retained entry) | same |
| K = 100000 | w1b / flushed / W2 (295.6 s) | ΔInet4Address | +100,000 / +2 / +2,000 | same |
| K = 1000000 (positive control) | W1 (201.0 s) | ΔInet4Address / Holder / CHM$Node / PSMS | +600,002 / +600,002 / +600,026 / +600,000 | same |
| K = 1000000 | W1 | heap Δ (Total; heap_info) | +88.79 MB; +88.79 MB (155.2 B per retained entry); the rest of the delta is `long[]` +8.39 MB (frequency sketch), `ConcurrentHashMap$Node[]` +4.19 MB (table), `int[]` +8.39 MB | same |
| K = 1000000 | w1b / flushed / W2 (296.0 s) | ΔInet4Address | +600,000 / +2 / +2,000 | same |
| K = 1000000 | flushed | heap Δ (Total) | +22.50 MB still retained after the flush: `long[]` +8.39 MB, `int[]` +8.39 MB, `ConcurrentHashMap$Node[]` +4.19 MB, `byte[]` +2.1 MB; the per-entry rows back at ≈ 0 | same (`flushed` block), `h-1000000-flushed.txt` on the node |
| all K | node health | `system.log` ERROR lines; OutOfMemoryError (outside the JVM-argument echo); WARN with "cidr" | 0; none; 0 | `run1/selfcheck.txt` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The knob reached the cache in every unit run (`policyMaximum` = set value) and every node ran with the configured K, MONITOR mode and refresh 1440 [observed: `run1/unit-probe-lines.txt`; `run1/selfcheck.txt` yaml lines]. The limit was reached and passed: N = 600,000 > 100,000 > 100, and the unit `maxSampledSize` and the cluster ΔInet4Address reach the cap at every binding value [observed]. The IPs matched a group (`getcidrgroupsofip 127.1.0.1` = `lo`; W1 results `[lo]`) [observed: session files]. No timed flush happened (w1b = w1 within 2 instances) [observed]. Fresh JVM per value / fresh node and data per K [observed: session files, step 1-2]. Baseline noise was −2 instances, far below every compared quantity [observed].
2. **Readings** — Unusual: (a) at K = 100 the W2 delta is +182 Inet4Address, 82 above the cap, while ΔPSMS = +200 against +100 after W1, and at K = 100000 and 1,000,000 ΔPSMS after W2 is +2,100 for +2,000 Inet4Address [observed: `run1/cluster-analysis.txt`]; (b) after the flush at K = 1,000,000 about 22.5 MB stays retained in four arrays while the per-entry rows return to +2 [observed]; (c) in the K = 1,000,000 W1 delta an `int[]` of +8.39 MB appears besides the expected sketch `long[]` [observed]; (d) heap_info and histogram Total agree to the KB in every W1 reading [observed].
3. **Matched row** — Unit, B2g row 1: "estimatedSize = min(N, max) for every max; heap delta scales as predicted" — estimatedSize 0 / 100 / 100000 / 600000 = min(600000, max); heapDelta 0.07 / 0.08 / 13.52 / 81.05 MB inside the B2f bands (< 2, < 2, 8-20, 50-110 MB), ratio 6.00 (5-7), heapDelta(100) ≈ heapDelta(0) (2 KB apart) [observed: `run1/unit-analysis.txt`]. Cluster, B3g row 1: "ΔInet4Address after W1 ≈ min(600,000, K) and heap Δ scales as predicted; drops to ≈ 0 after flush" — +102 / +100,002 / +600,002; heap Δ 0.14 / 13.58 / 88.79 MB inside < 5 / 8-20 / 50-110 MB; +2 after the flush in every K [observed: `run1/cluster-analysis.txt`]. With B3g row 6 ("W2: Δ ≈ +min(2,000, K): the native client path populates the same capped cache") — +182 (within AM4's ±505 of 100) / +2,000 / +2,000 [observed]. Every B3f line holds, including the four-row equality and w1b = w1 (`ALL EXPECTED HOLD`, 33 PASS, 0 FAIL) [observed].
4. **Excluded rows** — Unit: row 2 (count > max by more than a handful): count = max exactly [observed]. Row 3 (count capped but heap at 100 as large as at 1e6): 0.08 vs 81.05 MB [observed]. Row 4 (positive control failed): 600,000 entries and 81 MB at max = 1e6 [observed]. Row 5 (nulls cached): outsideGroups = 0 [observed]. Cluster: row 2 (Δ ≫ K and drops on flush, refuted): at K = 100 Δ = +102, not > 700; at K = 100000 +100,002, not > 200,500 [observed]. Row 3 (≫ K without a drop): not ≫ K, and it drops [observed]. Row 4 (per-entry cost > 500 B): 142-155 B [observed]. Row 5 (positive control Δ ≪ 600,000): +600,002 [observed]. Row 7 (W2 Δ ≈ 0 at K = 1e6): +2,000 [observed].
5. **Observed vs. inferred** — Inferred: (i) that the retained `Inet4Address`/`PSMS`/CHM-node rows are this cache's entries [inferred: the drop to +2 after `reloadcidrgroupscache`, whose only effect on per-IP state is `invalidateAll` of this cache (A3 step 5), and the 1:1:1:1 counts]; (ii) that reading (a) — 82 extra `Inet4Address` after W2 at K = 100 — is per-connection state outside this cache (e.g. state of the just-closed connections), not cache entries over the cap [inferred: ΔPSMS after W2 is +100 above the ip-cache size at every K (+200 vs 100; +2,100 vs 2,000), so the extra Caffeine nodes belong to other auth caches, and the ip-cache entries at K = 100 cannot exceed 100 nodes; the extra 82 addresses are not Caffeine nodes]; (iii) that the eviction branch (`evictEntries`) is what holds the count at the cap [inferred: count = cap exactly after N ≫ cap distinct inserts, with no flush in between; no eviction counter was read (R-b)].
6. **Deviations and gaps** — (a) Amendments AM1-AM4 (audit, before any reading) and defects D1-D2 (section 3). (b) The entry count on a node is a proxy (retained keys), as B3d states; the unit tier reads it exactly. (c) Reading (b): about 22.5 MB stays after a flush at K = 1,000,000 (sketch 8 MB, the CHM table 4 MB that does not shrink after `invalidateAll`, an 8 MB `int[]` whose owner was not identified, 2 MB `byte[]`); B3f predicts the flush only for the per-entry rows, so this does not change a row, but it means part of the heap the cap allows stays sized to the peak until restart (bounded by the cap: the sketch and table are sized by `maximum` / peak entries). (d) A scratch file `/tmp/x` on apt179 was written and deleted during the unit shakedown (outside the run directory, a few lines; nothing else outside `/mydata/jingsong-cass-s4/o04` and `~/.m2`).
7. **Core question** — Usage followed the constraint and the constraint caps it. With the same 600,000 distinct matched IPs, the number of cached entries and the retained heap followed min(N, cap): 0 / 100 / 100,000 / 600,000 entries and 0.07 / 0.08 / 13.5 / 81 MB in the unit tier, and +102 / +100,002 / +600,002 retained addresses with 0.14 / 13.6 / 88.8 MB of live heap on a node (parts 3 and 4); the positive control (cap above N) shows the same workload moves heap by 81-89 MB, the flush returns the entries to ≈ 0, and the native login path fills the same capped cache (W2 rows; part 3).

**Conclusion (one line):** Unit B2g row 1 and cluster B3g rows 1 and 6 — claim confirmed: `ip_cache_max_size` caps the IP-to-CIDR-groups cache's entry count and the heap it retains (effect: caps).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-read the raw ant logs (pairing the logger fragments by position, not by the extractor's regex), the junit test lines, every histogram (by column split, not the analyzer's regex), the session logs and each node's `system.log`; output `run1/selfcheck.txt`. Every number it printed equals the analyzer's.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: yaml K / 1440 / MONITOR present for every K, `lo` lookup true, W1 600,000 lookups and W2 2,000 logins done, node stopped, 0 ERROR lines; unit `policyMaximum` = set value, 4 × `Tests run: 1, Failures: 0`. |
| 2. Readings | yes | (a) re-read: Inet4Address +182, PSMS +200 at K=100 W2; +2,000 / +2,100 at the other K (`selfcheck.txt`, `cluster-histogram-excerpts.txt`). (b), (c) re-read in `cluster-histogram-excerpts.txt` (`[J`, `[I`, `[Ljava.util.concurrent.ConcurrentHashMap$Node;` rows). |
| 3. Matched row | yes | Unit sizes and heap deltas re-derived from the raw fragments; cluster w1/flushed/w2 deltas re-derived by column split; all inside the B2f/B3f values and AM4 tolerances. |
| 4. Excluded rows | yes | Each exclusion rests on a number reproduced in `selfcheck.txt`. |
| 5. Observed vs. inferred | yes | (i) rests on the flush control, re-read (+2 after flush at every K); (ii) rests on the PSMS offset of +100 seen at all three K; (iii) is the case's own logic (count = cap exactly). None changes the matched rows: under AM4 the K=100 W2 reading matches row 6 with or without (ii). |
| 6. Deviations and gaps | yes | The residual 22.5 MB after a flush is reported, not hidden; it is outside every frozen row. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 → B2b-B2e / B3b-B3e → B2f / B3f → B2g row 1 / B3g rows 1 and 6, with the positive control (cap above N) moving in both tiers. |

### 5.2 Run 2?

**No** (2026-11-12). Both tiers agree, every frozen prediction held with margin (exact counts in the unit tier, counts within 2 of the cap on the node, heap deltas mid-band), the positive control moved by 81-89 MB, and the conclusion rests on observed counts; the inferred points do not change a matched row.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps) — both tiers Confirmed, effect `caps`.

**Claim tested:** (B1) With `CassandraCIDRAuthorizer` enabled, the number of entries in `ipToCidrGroupsCache`, and the heap it retains, follow min(N, `ip_cache_max_size`) when N distinct client IPs that match a CIDR group are looked up; about 130 B per entry plus 8 B × ceilPow2(cap) for the frequency sketch. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1: **Confirmed** — estimatedSize = min(600000, max) exactly for max = 0 / 100 / 100000 / 1000000; heapDelta 0.07 / 0.08 / 13.5 / 81.0 MB, ratio 6.0 | caps | run 1 + self-check | 2026-11-12 |
| Cluster | B3g rows 1 and 6: **Confirmed** — retained addresses +102 / +100,002 / +600,002 for K = 100 / 100000 / 1000000, live heap +0.14 / 13.6 / 88.8 MB, ≈ 0 after the flush; native logins fill the same capped cache | caps | run 1 + self-check | 2026-11-12 |

**Positive control:** the cap above N (max/K = 1,000,000) in both tiers: the same workload filled the cache to 600,000 entries and moved heap by 81.0 MB (unit) and 88.8 MB (node).

**Feedback filed:** the case file's section D carries the audit amendments AM1-AM4 and a stage-4 feedback line (case file untracked; the coordinator commits). No section of the trace was refuted. Measured per-entry cost: ~120 B in the four per-entry rows (24 + 32 + 32 + 32 B), 142-155 B per entry with the arrays included (A2 estimated 120-135 B plus the sketch). **Open points for stage 3 / the user:** (1) R-a: the default cap (100) is about 13 KB of heap, so at K=100 the heap reading is noise-level (as filed); the entry count was distinguishable (baseline noise −2, not the "few hundred" B3f allowed). (2) After a flush (`reloadcidrgroupscache` or the periodic refresh), ~22.5 MB stays retained at K = 1,000,000 in the frequency sketch, the hash table and an unidentified `int[]`, sized by the peak, until restart (section 4.2, part 6 (c)). **Upstream / doc candidates:** none for a bug. **Leftovers on apt179:** nothing running (checked `ps -eo cmd | grep '[C]assandraDaemon'`: none; no java, JmxProbe, NativeProbe, ant or harness process of this run; ports 7300/7301/7499/9342/9391 not listening). Kept on the node: `/mydata/jingsong-cass-s4/o04/` (`src/` 470 MB with build, `logs/` 18 MB, `harness/`, `tools/`, `build.log`, `jar.log`); node data directory removed. Kept on the local machine: `/mydata/jingsong-cass-s4/o04-src` (185 MB copy).
