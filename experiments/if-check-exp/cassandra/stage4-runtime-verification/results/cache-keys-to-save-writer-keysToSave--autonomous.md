# cache-keys-to-save-writer-keysToSave--autonomous — stage-4 results  <!-- file: results/cache-keys-to-save-writer-keysToSave--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`cache-keys-to-save-writer-keysToSave--autonomous`](../../stage3-ai-deep-read/cases/cache-keys-to-save-writer-keysToSave--autonomous.md)
>
> **Status:** run 1 done and self-checked (2026-10-26); verdict filed; no run 2
>
> **Outcome class:** true positive (estimate positive, effect caps)
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | The case file at repository HEAD `e776524` (untracked there) plus the audit amendments of 2026-10-26 (the orchestrator commits). sha256 of the whole file after the amendments (frozen before any reading): `e2473018617aa5d1a37eaa12d37c1b04ec10342fe68afa42bdc9cf38ac7aa17c`. sha256 of the prediction and conclusions text of B2 (`awk` from the line starting `**B2f.` to the line before `**B2h.`): `8b8ff896f35232243b29f80879bb0e5b82c9a1c0368ee5cde16ae576cea87e8a`; of B3 (from `**B3f.` to the line before `**B3h.`): `95a08dab0b0c00a3aeac8125344691b56f07f7b8593449ea4ac61b78b208e020`. The case file changes after run 1 only in section D (feedback); its sha256 then is recorded in §8. |
| **Harness** | `harness/cache-keys-to-save-writer-keysToSave--autonomous/` (`KeysToSaveWriterTest.java`, `unit-run.sh`, `analyze_unit.py`, `known-answer-unit.txt`, `Jmx.java`, `make-node-yaml.sh`, `cluster-run.py`, `analyze_cluster.py`, `selfcheck.py`, `README.md`; written after this audit and before run 1; not committed by this agent). **Instrument checks before run 1 (shakedowns, not readings, discarded):** (1) `analyze_unit.py` on the synthetic `known-answer-unit.txt` (hdr 40 B, 100 B/entry): 0 MISMATCH; on a copy where K=100 writes 150 entries: flags n_K > K and the ratio row, classification "claim wrong". (2) The unit test at N = 50: K=1 logs 1 item, every K >= 50 logs 50, reload count equals the logged count, file length affine (16.1 B + 11.9 B/entry), counter cache n = 50 for K=100 and K=0; the test log's `Saved KeyCache (n items)` lines agree with the test's own record. (3) The cluster chain on a small data set (300,000-row write, 150,000-read passes, `CK_RUN=shake`): all three arms ran, JMX set/read-back/invoke worked, `Saved KeyCache` lines and file sizes read back, the periodic save at the yaml-captured K fired, stress errors 0, no leftover process; `selfcheck.py` and `analyze_cluster.py` ran on it (the two `control` relations MISMATCH there only because the 200 MiB arm held 139,443 entries, fewer than the 20 MiB arm; run 1 populates the 200 MiB arm to >= 700,000). Defects found and fixed in the harness during the shakedown: `statusbinary` check matched "not running"; the stress `Total partitions` regex missed thousands separators; a metadata-size row (the metadata file is 52 B at K=10000 and 348 B at full save, because it depends on the sstables the saved keys touch, `CacheService.java:433-447`) was removed from the analyzer as ill-founded (it was never a case-file row). |
| **Tiers and values** | Unit (B2): K in {1, 100, 500, 1000, 0, Integer.MAX_VALUE, 2000} at N = 1000 key-cache entries; counter-cache repeat K in {100, 0}. Cluster (B3): `key_cache_size` 200 MiB, K in {10000, 100000, 0, default MAX} at runtime plus a yaml-start arm (K = 10000), and the 20 MiB control arm with K in {10000, 0}. |
| **Audit bottom line** | **Ready after amendments** - 2026-10-26. B3f was corrected once before the freeze hash was taken for the final time (the 10x entry ratio and the 20 MiB arm's K list; no reading existed; the shakedown above gave the 88 B of weight per entry that shows 20 MiB holds ~240,000 entries). The hashes above are of the final text. |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: entries written to `<saved_caches_directory>/KeyCache-g.db`, a count with a derivable byte size (n x e); the real resource is the file bytes (`File.length()`); the heap side is also tested (B1). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b seven values spanning K<N, K=N, K>N, 0 and the MAX default; B3b four values plus a yaml-start arm. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d: file length by `File.length()` / `du -b`, not only the log count; live heap via `weightedSize()`, `nodetool info`, `jcmd`; the transient heap of `hottest(n)` is named as only coarsely observable. |
| A. Core question | usage driven to the limit and past it | Met after amendment | Unit: N = 1000 vs K up to 2000. Cluster: read passes until the cache holds at least 700,000 entries (two uniform 500,000-read passes touch ~787,000 distinct keys; the spec asks for 300,000) vs K = 10000 / 100000 (B3c); the 20 MiB arm holds ~200,000 entries and uses K in {10000, 0} (amended B3e). |
| B. Logic | each step says what it establishes | Met | B2e/B3e numbered steps with observables. |
| B. Logic | prediction stated in numbers or a clear relation | Met after amendment | B2f/B3f give n = min(K, N), file = hdr + n x e, ratios; amended: hot-key sentence informational (Caffeine `hottest` is not by read count), B3f entry-ratio relation made exact (< 0.5, not "10x"). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover cap holds, overshoot (n > K), bytes not governed by count, K=0 writes nothing, live memory changes, reload mismatch, limit not reached. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Ceiling = file bytes and logged n follow min(K, N); disallow evidence = the `Saved KeyCache (n items)` line with n = K < size and the reload count. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: K=0 vs MAX equal, fresh directory per K, same cache type (counter repeat), `key_cache_size` as the memory-side control. Positive file, so no negative-claim control is required. |
| C. Specific | a human can follow it from the intro and B2f/B3f | Met | A1-A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly, fixed | B3d/B3e named a nonexistent `nodetool getcachekeystosave`, an uninstalled `jmxterm`, and said `setcachekeystosave` triggers a save (it only reschedules, the first run is a full period later). Amended with the JMX route. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met after amendment | Values, sizes, log line, file names exact; save trigger and read-back path amended; heap sampling by `jstat`/`jcmd` is informational. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Tree `~/s4-b7-ck` by `copy-source.sh` on pc12 (`ant build-test` started); JDK 11.0.32.1, Ant 1.10.12; own JMX client and unit test are step-1 work (listed). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 2M partitions of stress `standard1` ~ 1-2 GB on tmpfs (126 GiB free); two 500,000-read uniform passes give ~787,000 distinct keys (> 100,000), key cache ~80 MB of 200 MiB; saved file well under 100 MB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Verified: `Config.java:466,477,483`; `AutoSavingCache.java:158-178` (`scheduleSaving`), `:302-313` (Writer), `:375-389` (loop and break), `:425` (log line); `CacheService.java:131,165,183,242-273,357-359`; `CaffeineCache.java:132-135`; `NodeTool.java:207`; `NodeProbe.java:1096`; MBean name `CacheService.java:80`. Finding: the loop counts `keysWritten++` even when `serialize` wrote nothing (entry evicted in between, `CacheService.java:487-488`), so n can slightly exceed the real entry count under eviction; irrelevant at 200 MiB, noted for the 20 MiB arm. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | B3d/B3e: no `nodetool getcachekeystosave`; read/set/trigger through JMX on `org.apache.cassandra.db:type=Caches` (`KeyCacheKeysToSave`, `saveCaches`) | Applied 2026-10-26 (B3d, B3e) | The named command and tool do not exist on the nodes; `setcachekeystosave` does not trigger a save. |
| 2 | B2f: hot-key sentence informational | Applied 2026-10-26 (B2f) | Caffeine `hottest` is policy order, not read count. |
| 3 | B3f / B3e: 20 MiB arm uses K in {10000, 0}; entry relation `< 0.5 x` | Applied 2026-10-26 (B3e, B3f) | "10x fewer" is wrong from the arithmetic (a 200 MiB cache is not full at ~787,000 entries); the 20 MiB cache holds ~200,000 entries. |
| 4 | B2b: counter-cache repeat made exact (N = 1000 counters, K in {100, 0}) | Applied 2026-10-26 (B2b) | B2h asked for it without a recipe. |
| 5 | `nodetool setcachekeystosave` text says "0 to disable"; the code saves all entries at 0 | Left for stage 3 (upstream doc candidate) | Code/doc mismatch, found while checking B2b's K=0 row. |
| 6 | The Writer counts `keysWritten++` for entries evicted between iteration and serialize | Left for stage 3 | Only matters under eviction. |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 09:03 MDT, cluster 09:05-09:09 MDT) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876...`, 40 cores, 251 GiB) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b7-ck` (unit, `ant build-test`) and `~/s4-b7-ck-n` (node, `ant jar`), both by `copy-source.sh` at repository HEAD `e776524` (tag `cassandra-5.0.9`) | |
| Case-file commit / harness commit | HEAD `e776524` plus the uncommitted amendments (sha256 in §1); harness uncommitted (md5 in `run1/unit/harness.md5`) | |
| Storage for node data | tmpfs `/dev/shm/s4-b7-ck` (126 GiB free); unit tests under the tree's `build/test` on local disk | |
| Full logs (path, outside the repo) | pc12 `~/s4-b7-ck-logs/run1/` (`unit/`, `cluster/{main,ctl20,yaml10k}/` with `system.log.full`, stress logs, heap csv) and `~/s4-b7-ck-logs/run1-*.out` | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B3d, B3e | `nodetool getcachekeystosave` does not exist; `jmxterm` is not installed; `setcachekeystosave` does not trigger a save | JMX client (`Jmx.java`) for get / set / invoke `saveCaches` | amended 2026-10-26 before run 1 (prediction unchanged) | uncommitted (orchestrator) |
| 2 | audit | B3f | "about 10x fewer entries" at 20 MiB wrong from the arithmetic | relation `< 0.5 x`; reads continue to >= 700,000 entries | amended 2026-10-26 before run 1 | uncommitted |
| 3 | self-check | harness | `selfcheck.py` took the whole unit test log, which the tree appends to on every run (it held the N = 50 shakedown) | takes the last 7 KeyCache and last 2 CounterCache saves | fixed 2026-10-26 after run 1; the readings are unaffected (they come from `unit.txt`) | n/a (harness) |

No step of run 1 failed or was changed during the run.

## 4. Run 1

**Scope:** unit tier (B2) at N = 1000, K in {1, 100, 500, 1000, 0, Integer.MAX_VALUE, 2000}, plus the counter-cache repeat (K = 100, 0); cluster tier (B3) arms `main` (200 MiB key cache, K in {10000, 100000, 0, MAX} through JMX), `ctl20` (20 MiB, K in {10000, 0}), `yaml10k` (yaml `key_cache_keys_to_save: 10000`, `key_cache_save_period: 60s`). **Command log:** `cache-keys-to-save-writer-keysToSave--autonomous/run1/` (`unit/session.log`, `unit/summary.txt`, `cluster/*/summary.txt`, `cluster/analysis.txt`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (N = 1000 key-cache entries before every save; `run1/unit/unit.txt`, `run1/unit/summary.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `size() == 1000` before every save | 1000 for all seven K | `unit/unit.txt` (`start_size`) |
| logged `Saved KeyCache (n items)` n for K = 1, 100, 500, 1000, 0, MAX, 2000 | 1, 100, 500, 1000, 1000, 1000, 1000 (= min(K, N), 0 and MAX mean N) | `unit/saved-lines.txt`, `unit/unit.txt` |
| `KeyCache-g.db` length | 29, 1266, 6248, 12464, 12464, 12464, 12464 B; affine: 16.6 B + 12.45 B/entry, residual <= 5 B; L(100)/L(1000) = 0.1016 (bound 0.1027); L(1000) = L(0) = L(MAX) = L(2000) | `unit/summary.txt` |
| `size()` and `weightedSize()` before/after each save | 1000 and 80,000 unchanged for all K | `unit/summary.txt` |
| reload (`clear(); loadSaved()`) count | equals the logged n for every K | `unit/unit.txt` |
| counter-cache repeat | K = 100 logs 100 items (1716 B), K = 0 logs 1000 (17,016 B); reload equal | `unit/unit.txt` |
| hot keys among the saved ones (informational) | K = 100 saved none of the 100 repeated keys; K = 1 none | `unit/summary.txt` |
| analyzer | 0 MISMATCH, "claim holds (disk)" | `unit/summary.txt` |

**Cluster tier** (`cluster/analysis.txt`; the key cache held 846,505 entries, weight 74,492,368 B, before every save of `main`; stress writes 2,000,000 partitions and 2 read passes, errors 0)

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| `key_cache_size` 200 MiB | main K=10000 | logged n; `KeyCache-g.db` bytes; entries/size | 10000; 199,883 B; 846,505 / 74,492,368 unchanged | `cluster/main/summary.txt`, `results.json` |
| 200 MiB | main K=100000 | same | 100000; 1,998,556 B; unchanged | same |
| 200 MiB | main K=0 | same | 846,505; 16,918,090 B; unchanged | same |
| 200 MiB | main K=MAX (default) | same | 846,505; 16,918,090 B (equal to K=0); unchanged | same |
| 200 MiB | derived | bytes per entry; F(10000)/F(100000) | 19.99 B/entry at every K (hdr 25 B); ratio 0.1000 | `cluster/analysis.txt` |
| `key_cache_size` 20 MiB (control) | ctl20 K=10000 / K=0 | entries; size; n; bytes | 238,312 entries (0.28 x 846,505), size 20,971,448 B (<= 20 MiB); n = 10000 -> 199,882 B; n = 238,312 -> 4,763,087 B | `cluster/ctl20/summary.txt` |
| 200 MiB, yaml start | yaml10k | JMX `KeyCacheKeysToSave` at startup; periodic save; manual save | 10000; periodic save (60 s, K captured at startup) logged 10000 items; manual save 10000 items; file 199,888 B (main K=10000: 199,883 B) | `cluster/yaml10k/summary.txt` |
| all | system.log MB column | cross-check of file sizes | 0, 1, 16, 16 MB for 199,883 / 1,998,556 / 16,918,090 / 16,918,090 B | `cluster/main/system.log.excerpt` |
| all | heap used during the save (JMX, 100 ms) | peak | 1.29 / 1.35 / 1.79 / 1.92 GB for K = 10000 / 100000 / 0 / MAX: heap used steps with young-generation allocation and includes garbage, so it does not isolate the `hottest(n)` map; not used | `cluster/main/results.json` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The limit was reached: 1000 entries before each unit save and 846,505 before each cluster save, above every K (10000, 100000) [observed: `unit/unit.txt` `start_size`; `cluster/main/summary.txt`]. Held-fixed settings: `key_cache_size` read back as 200 MiB (capacity 209,715,200) and 20 MiB (20,971,520) [observed: `cluster/*/summary.txt`]; each K read back through JMX equal to the value set [observed: `analysis.txt`]; no reads between saves, entries and size identical before and after every save [observed: `analysis.txt`]; stress errors 0 [observed: `stress-results.txt`, `selfcheck.txt`]; autocompaction disabled before the write [observed: `cluster/main/session.log`].
2. **Readings** — nothing contradicts another. The measured bytes per entry (12.45 B unit, 19.99 B cluster) are below the B2f guess "roughly 50 to 150 B"; the guess is not a conclusions-table row and the affine relation, not the magnitude, is the prediction. The hot-key sentence of B2f (informational after the amendment) did not hold: K = 100 saved none of the 100 repeated keys [observed: `unit/summary.txt`]. The metadata file is 68 B (K-limited) against 556 B (full), the crc file 20-1040 B: both small and not the capped quantity [observed: `analysis.txt`].
3. **Matched row** — Unit B2g row 1 "n_K = min(K,N), L_K affine in n_K: claim holds (disk)": n matches for all seven K [observed: `saved-lines.txt`], L is affine with residual <= 5 B [observed: `summary.txt`]. Cluster B3g row 1 "file size and logged n follow min(K, entries): claim holds (disk cap works on a real node)": n = 10000 and 100000 for K < entries and n = entries for K = 0 and MAX; file bytes = 25 B + 19.99 B x n at every K [observed: `analysis.txt`]. Also holds: "live key-cache size changes only with `key_cache_size`" (control): 846,505 entries / 74.5 MB at 200 MiB, 238,312 entries / 21.0 MB at 20 MiB, and neither changes with K [observed: `analysis.txt`].
4. **Excluded rows** — "n_K > K for some 0<K<N" / "file larger than K e_max": no, n = K exactly and the files are below 1.05 x e K + hdr [observed: `analysis.txt`]. "L not monotone in n / grows with N at fixed K": no, the K=10000 file is 199,883 B at 846,505 entries and 199,882 B at 238,312 entries [observed: `ctl20/summary.txt`]. "K=0 writes 0 entries": no, 0 saves all [observed]. "`weightedSize()` changes with K": no [observed]. "reload count differs from n_K": no (unit) [observed]. "size() < N at start" / "entries < K for every K": no [observed]. "file at K=0 or default equals K=10000 file": no, 16.9 MB against 0.2 MB [observed].
5. **Observed vs. inferred** — Inferred: that `hotKeyIterator(n)`'s n hottest keys are not read counts is inferred from the saved set missing the repeated keys; not needed for the verdict. Inferred: the real resource (disk) equals the file bytes read with `os.path.getsize` once the rename is logged [inferred: the log line is written after the renames, `AutoSavingCache.java:425`, and the logged MB agrees with the sizes]. Inferred: the heap half of B1 (the knob does not reduce live memory) from `Size` and `Entries` unchanged by K [observed: gauges] — what is not observed is the transient heap of `hottest(n)` during the save.
6. **Deviations and gaps** — (a) The cache was populated to 846,505 entries, above the spec's 300,000, to make the 20 MiB control unambiguous (a stated reading rule). (b) The transient heap cost of `hottest(n)` during a save was not isolated (heap-used sampling is too coarse and polluted by garbage); B3f's last sentence about the heap peak is therefore neither confirmed nor refuted, and no row depends on it. (c) `nodetool setcachekeystosave` was not used: JMX attribute set (same MBean method) was; the nodetool command itself was not exercised. (d) One data set and one key-cache-bearing table; the unit tier also covered the counter cache; the row cache was not exercised (row cache is shared code but needs OHC; the unit test yaml has a 16 MiB row cache and the cache-type check of B2h was done with the counter cache only).
7. **Core question** — Yes: the number of entries written, and therefore the size of the saved-cache file, follows `key_cache_keys_to_save`: with 846,505 entries in the cache, K = 10000 wrote 10000 entries (0.2 MB) and K = 100000 wrote 100000 (2.0 MB) against 16.9 MB for K = 0 or the default, a constant 19.99 B per entry [unit: steps B2e 2-3 -> `saved-lines.txt`, `summary.txt`; cluster: steps B3e 3 -> `analysis.txt`]. The knob does not change the live cache (entries and weight identical across K) and is not what bounds it (`key_cache_size` is: the 20 MiB control holds 0.28 x the entries); the same K read from the yaml at startup also holds on the periodic save path. The constraint caps disk (the saved-cache file), as estimated, and does not cap memory.

**Conclusion (one line):** Unit B2g "n_K = min(K,N), L_K affine in n_K" and cluster B3g "file size and logged n follow min(K, entries)" — confirmed (caps, disk; no memory cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses the raw logs (the Cassandra test log's `Saved ... (n items)` lines, each arm's `system.log.full`, the stress logs, the heap csv) and recomputes the relations with its own code: 0 parts do not hold (`run1/selfcheck.txt`). The MB column of the log lines was also compared by hand with the file sizes.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `start_size` 1000 in `unit.txt`; 846,505 entries and capacities 209,715,200 / 20,971,520 in `main/summary.txt`, `ctl20/summary.txt`; stress "Total errors 0" in every `stress-*.log` (`selfcheck.txt`). |
| 2. Readings | yes | Logged n in `system.log.full` equals `results.json` n_logged for all four `main` saves, both `ctl20` saves and the `yaml10k` periodic and manual saves (`selfcheck.txt`); bytes per entry 19.99 at every K. |
| 3. Matched row | yes | `unit.txt` n = [1, 100, 500, 1000, 1000, 1000, 1000] equals the test log's; cluster files 199,883 / 1,998,556 / 16,918,090 / 16,918,090 B at n = 10000 / 100000 / 846,505 / 846,505; logged MB 0 / 1 / 16 / 16 (`system.log.excerpt`) agree. |
| 4. Excluded rows | yes | No n above K; K=10000 file unchanged between the 200 MiB and 20 MiB arms (199,883 vs 199,882 B); `Size`/`Entries` identical across K. |
| 5. Observed vs. inferred | yes | The inferred points (rename before the log line; heap half from gauges) are named in 4.2(5); the disk statement rests on `getsize` plus the independent log MB column. |
| 6. Deviations and gaps | yes | The transient heap and the row cache are the stated gaps; neither feeds a row. The self-check script itself needed one fix (defect 3), found by running it on run 1's files. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 -> B2e/B3e steps -> B2f/B3f relations -> B2g/B3g row 1, each with a cited file above. |

### 5.2 Run 2?

**No** (2026-10-26). The conclusion rests on logged counts and file sizes that two independent records give (the node's `system.log` and the harness's `getsize`), the two tiers and the yaml arm agree, the control behaves as predicted, and the result neither refutes the case nor confirms a bypass. A run 2 would not settle the heap-peak gap either, which needs a different instrument (allocation profiling), not a repeat.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive (disk). **Outcome class:** true positive (positive, caps).

**Claim tested:** (B1) for a cache holding N entries, the saved-cache data file contains min(K, N) entries (K = keys_to_save, K = 0 meaning N), so its size scales linearly with min(K, N), independent of the live cache size once K < N; the knob does not reduce live-cache memory (heap half). "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g "n_K = min(K,N), L_K affine in n_K: claim holds (disk)"; live memory unchanged by K | caps (disk); does not cap memory | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed — B3g "file size and logged n follow min(K, entries): claim holds (disk cap works on a real node)"; live size changes only with `key_cache_size` (control) | caps (disk); does not cap memory | run 1 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): not applicable (positive estimate). For the memory half, the `key_cache_size` control (20 MiB against 200 MiB) moved the live cache (238,312 against 846,505 entries) while K did not.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (uncommitted, the orchestrator commits); no section other than the step-0 amendments (dated 2026-10-26) amended. Upstream/doc candidates: the `nodetool setcachekeystosave` description and the yaml say "0 to disable" / "Disabled by default, meaning all keys are saved", but 0 saves all entries (`AutoSavingCache.java:305`); the Writer counts `keysWritten++` for an entry that `serialize` skipped because it was evicted meanwhile (`AutoSavingCache.java:387`, `CacheService.java:487-488`).

Case-file sha256 after the feedback in section D (frozen prediction hashes above are of the earlier text): `bcfc3a8c700202ed7af7471b95a1e331aed4ac89f8cad674111f6d308fbb7fd4`. Leftovers on pc12: none running; tmpfs `/dev/shm/s4-b7-ck` removed; trees `~/s4-b7-ck`, `~/s4-b7-ck-n` (471 MB each) and logs `~/s4-b7-ck-logs` (1.3 MB) remain.
