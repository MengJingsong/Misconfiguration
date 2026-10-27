# cache_keys_to_save-saveCache-keysEstimate--autonomous — stage-4 results

> **Case:** [`cache_keys_to_save-saveCache-keysEstimate--autonomous`](../../stage3-ai-deep-read/cases/cache_keys_to_save-saveCache-keysEstimate--autonomous.md)
>
> **Status:** verdict filed (2026-10-26); run 1 at both tiers, self-checked; no run 2
>
> **Outcome class:** true positive (estimate `positive`, effect `caps`)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the case file's feedback section is D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | repository HEAD `93d6365` (the case file is untracked there; the orchestrator commits it). sha256 of the whole file after the audit's amendments (B5, 2026-10-26): `0cf1eaf823806a79b6bf5b4f71e3b8edab7253b2f168309332681740231d9a89`. **Frozen prediction and conclusion tables** (text of B2f–B2g... precisely: B2f, B2g, B2h and B3f, B3g, B3h concatenated as filed; stored in `harness/cache_keys_to_save-saveCache-keysEstimate--autonomous/frozen-prediction.txt`): sha256 `c88c1547c3e1156cbfab6a7866531994acbbe41d22a05fb59b21a36bbe2f105c`. The amendments B5 (rows added to B2g/B3g by U5/C4): sha256 `cb9b79265458af967560eea2ce1fb0e226d4ed1cae1c24cb51a21d7e23e2ceb3`. Frozen 2026-10-26 before any reading. (After the runs, section D of the case file was filled with the feedback; the file's sha256 then is `c458464734694ee24daf7223ac79975489e34265f41cd6f33282658d64c82ec4`. B1 to B5 are unchanged.) |
| **Harness** | `harness/cache_keys_to_save-saveCache-keysEstimate--autonomous/` (see its README); commit: none (the orchestrator commits) |
| **Tiers and values** | unit: N in {1, 100, 1000, 9999, 10000, 20000, 0} on key cache (P = 10000), N in {100, 2000, 0} on row and counter (P = 2000), race test, load-back; cluster: one node, N in {unset(all), 10000, 100, 0} by yaml and runtime, key/row/counter together |
| **Audit bottom line** | Ready after amendments — 2026-10-26 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | disk: saved-cache file bytes via entry count × entry size (A2, B1) |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b seven values incl. 0 and above-P; B3b {100, 10000, unset} |
| A. Core question | real resource measured, not only the counter | Met | file length (`File.length()`, `ls -l`/`du -b`) next to the log counter (B2d, B3d); gap (hot-snapshot heap) named |
| A. Core question | usage driven to the limit and past it | Partly | unit populations P = 10000/2000 vs N up to 20000 reach and pass; cluster counter-cache population is not controlled (C2: measured, prediction relative to it) |
| B. Logic | each step says what it establishes | Met | B2e/B3e |
| B. Logic | prediction stated in numbers or relation | Met | B2f, B3f |
| B. Logic | every plausible outcome has a conclusions row | Partly | B2g/B3g lacked N≥P, hot-key mismatch, reload mismatch, runtime-needs-restart, limit-never-reached; added by U5/C4 |
| B. Logic | confirmation needs ceiling-follows-knob and disallow evidence | Met | items < population at N < P is the disallow evidence (the `hotKeyIterator` branch, `AutoSavingCache.java:312`); race test for line 388 |
| B. Logic | alternative explanations and their controls | Met | B2h, B3h (+ C3 capacity control, no-save control) |
| C. Specific | a human can follow it | Met | A2/A3 and B1 |
| C. Specific | an AI can run B2a–B2e / B3a–B3e without re-deriving | Partly | stub index entry unusable (U2), stress commands missing (C2), race wrapper impossible (U4), ports (C1): amended |
| C. Specific | knob, values, workload, commands, observables exact | Partly | as above; amended |
| D. Runnable | harness and prerequisites exist or are listed | Met | none existed; written in step 1 |
| D. Runnable | workload arithmetic reaches the limit | Met | 200000-row loads, ~tens of MB, tmpfs; unit populations tiny |
| D. Runnable | citations spot-checked | Met | `AutoSavingCache.java:304-314`, `:388`, `:290`, `CacheService.java:131-133,165-167,183-189,242-275,488,495`, `CaffeineCache.java:132-135`, `OHCProvider.java:107-110`, `Config.java:466,477,483`, `SetCacheKeysToSave` arg order all checked against the pinned tree. One non-load-bearing inexactness: "SerializingCacheProvider ... heap-free" (row cache in the unit yaml is OHC; U2) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | copy-source.sh, no storagedir flag | applied 2026-10-26 (B5) | path in B2a does not exist |
| U2 | real flushed SSTable for key cache; row cache is OHC in unit yaml; counter table | applied (B5) | stub entry cannot serialize; provider claim wrong |
| U3 | thread-allocated bytes around direct Writer call replaces jcmd mid-iteration | applied (B5) | instrument is not executable as written; side observation only |
| U4 | race test via private AutoSavingCache + stub serializer | applied (B5) | `cacheLoader` is final |
| U5 | add rows to B2g | applied (B5) | missing outcomes |
| C1 | slot-1 ports, tmpfs paths, leftover check | applied (B5) | environment |
| C2 | exact stress commands, population measured | applied (B5) | not runnable as written |
| C3 | capacity control by runtime setcachecapacity 8 | applied (B5) | 50 MiB would not bind |
| C4 | add rows to B3g | applied (B5) | missing outcomes |
| R1 | "Disabled by default" yaml text vs `0 = all`: nodetool help says "0 to disable" but 0 means save all | left for stage 3 / upstream doc candidate | `AutoSavingCache.java:305` |

(Run 2 agreement criteria: not applicable unless run 2 is chosen.)

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 |
| Node | pc07 (node0.jason92-320876), port slot 1 (127.0.1.1, JMX 7110) |
| OS and kernel | Ubuntu 22.04, 5.15.0-187-generic (`results/.../run1/env.txt`) |
| JDK / Ant | OpenJDK 11.0.32.1 / Ant 1.10.12 |
| Local source copies | `~/s4-b8-kt/u` (unit, `ant build-test`) and `~/s4-b8-kt/c` (node, `ant build`), from `cassandra/cassandra-5.0.9/` at repository commit 93d6365 |
| Case-file / harness commit | case file untracked at 93d6365 + working-tree edits; harness untracked |
| Storage for node data | `/dev/shm/s4-b8-kt/` (tmpfs); unit saved caches under the copy's `build/test/cassandra/saved_caches` (local disk) |
| Full logs | `~/s4-b8-kt-logs/` on pc07 (`run1/` first unit run and cluster run, `run1b/unit/` the unit run of record, `shake1*` shakedowns) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| R1 | run 1a (unit) | B2d(4) hot-key check | the lookup that counts how many of the 100 touched keys were persisted had no positive control (0 found could be a broken lookup) | added two checks to the test: the lookup finds all P keys before the save, and finds exactly the loaded entries after the load; the unit tier was restarted as `run1b` (the unit run of record). Run 1a's own numbers were identical for every B2g row (`run1/unit/summary-run1a-before-hotcheck-control.txt`) | 2026-10-26; instrument only, B2f/B2g untouched | none (harness) |
| R2 | run 1 (cluster) | cross-phase check | `rt100b` (the phase after the capacity control shrank the key cache to 95325 entries) was in the list of phases whose live entries must match, so one cross EXPECTED line reads NO (min 95325, max 200016) | none needed: the NO is the capacity control itself; the runtime phases before it show 200016 in all four | 2026-10-26 | none |
| R3 | self-check | `selfcheck.py` plateau test | required the last two counter-cache saves of the unset phase to be equal; the counter cache sits at its 50 MiB cap and the last save before the phase read 436858 against 436906 (workload had just ended) | test relaxed to "last value within 1% of the previous three"; the later N=0 windows must equal the last value (they do) | 2026-10-26 | none |
| – | shakedowns | – | stub shakedowns (`shake1*`, 20000 rows) found: `ant build` leaves no jar (need `ant jar`), `metadata_request_timeout` not a driver argument, a global `CassandraDaemon` check matched other sessions' nodes (now matches this harness's directory only). Not readings. | harness | 2026-10-26 | none |

## 4. Run 1

**Scope:** unit tier (`run1b/unit`, 170 checks) and cluster tier (`run1/cluster`, one chain of four node lifetimes), 2026-10-26, pc07. Excerpts: `results/cache_keys_to_save-saveCache-keysEstimate--autonomous/run1/` (`unit/summary.txt`, `unit/test.out`, `unit/saved-log-lines.txt`, `cluster/summary.txt`, `cluster/phases.jsonl`, `cluster/saved-lines.txt`, `cluster/session.log`, three stress outputs, `selfcheck-output.txt`, `env.txt`). Harness: `harness/cache_keys_to_save-saveCache-keysEstimate--autonomous/`.

### 4.1 Readings

**Unit tier** (`run1/unit/test.out`; two repetitions in shuffled order, each N row identical in both)

| Test or assertion | Result | Evidence |
|---|---|---|
| Key cache P = 10000, N = 1 / 100 / 1000 / 9999 / 10000 / 20000 / 0: items written (`Writer.getCompactionInfo().getCompleted()`), items reloaded, `size()` after reload | 1 / 100 / 1000 / 9999 / 10000 / 10000 / 10000, reload and size equal items | `unit/test.out` (`STAGE4 save cache=key`) |
| Key cache file length (`File.length()`) for the same N | 32 / 1,616 / 16,016 / 158,335 / 158,351 / 158,351 / 158,351 bytes; 15.83 B per item after a 16 B header; len(1000)/len(100) = 9.91 | same, `STAGE4 ratio` |
| Row cache P = 2000 (OHC), N = 100 / 2000 / 0 | items 100 / 2000 / 2000; file 1,216 / 22,906 / 22,906 B | same |
| Counter cache P = 2000, N = 100 / 2000 / 0 | items 100 / 2000 / 2000; file 2,416 / 48,016 / 48,016 B | same |
| Live `size()` before vs after each save | unchanged in all 26 rows (`live` = `liveAfterSave`) | same |
| `submitWrite(N)` path vs direct `Writer.saveCache()` | same file length in all 26 rows | same (`fileLen`, `fileLenDirect`) |
| Control: populated cache, no save | file absent, size P | `STAGE4 check keyT control` lines |
| Race (B2e 3), N = 0, 5000 keys added during the save | size at construction 10000, 15000 during, serializer called 10000 times, items written 10000; the counterfactual iterator (started at 10000, 5000 added after 100 steps) yields 15000 | `STAGE4 race` lines |
| Thread-allocated bytes of the save (side) | N=1: 127,088; N=100: 180,184; N=1000: 662,816; N=10000: 5,486,944 (about 0.53 KB per item) | `STAGE4 save ... allocBytesSave` |
| Hot-key check (side): of the 100 keys touched 5 extra times, number in the N=100 file | 0 of 100 (lookup control: all 10000 keys found before, loaded entries found after) | `STAGE4 hot N=100 loaded=100 hotPresent=0 anyPresent=100` |
| Upstream `AutoSavingCacheTest` | 2 tests pass | `unit/summary.txt` |

**Cluster tier** (`run1/cluster/phases.jsonl`; one node, 2 GiB heap, tmpfs, 200000 stress partitions, saves every 10 s; "saved" = the last `Saved … (n items)` log line of the phase, "file" = `.db` bytes)

| Setting (how set) | Cache | Live entries (`nodetool info`) | Saved items | File bytes | Evidence |
|---|---|---|---|---|---|
| unset (yaml) | key / row / counter | 200,016 / 200,000 / 436,906 | 200,016 / 200,000 / 436,906 | 3,981,567 / 3,000,016 / 10,485,760 | `phases.jsonl` line 1 |
| 10000 (runtime) | key / row / counter | same | 10,000 each | 200,016 / 150,016 / 240,016 (5.02% / 5.00% / 2.29% of the unset file) | line 2 |
| 100 (runtime) | key / row / counter | same | 100 each | 2,016 / 1,516 / 2,416 (0.05% / 0.05% / 0.02%) | line 3 |
| 0 (runtime) | key / row / counter | same | = live | = unset files | line 4 |
| 0 + `setcachecapacity 8 100 50` | key | 95,325 | 95,325 | 1,906,516 | line 5 (control C3) |
| 100 (runtime), then restart with yaml 100 | all | warm-load entries 255 / 100 / 100; after the workload again 400,024 / 200,000 / 436,906 | 100 each | 1,996 / 1,516 / 2,416 | lines 7, `summary.txt` |
| yaml 10000 after restart | all | 400,202 / 200,000 / 436,906 | 10,000 each | 199,570 / 150,016 / 240,016 | line 8 |
| save periods 0 (control), caches populated (798,817 / 200,000 / 436,906 entries) | all | – | no `Saved` line, no file | – | `summary.txt` "nosave" |
| Steady heap after `GC.run` (jcmd) in the four runtime phases | – | – | – | 234.4 MB in each; `RssAnon` 2,819 to 2,821 MB | `phases.jsonl` lines 1 to 4 |

All 48 `EXPECTED:` lines of the saved-items and file-ratio kind read yes; the one NO is R2 above. The runtime setters took effect at the next 10-s save (the windows in `selfcheck-output.txt`), without a restart.

### 4.2 Conclusion and logic

1. **Validity.** [observed: `cluster/summary.txt`] the caches were populated well past both N values (200016 / 200000 / 436906 entries against N = 100 and 10000), so the limit was reached and passed; stress runs ended with 0 errors (`cluster/stress-*.out`); the reader scanned 200000 keys with 0 errors; the node ran on a 2 GiB heap on tmpfs with saves every 10 s as B3a. Unit: [observed: `unit/test.out`] populations equal P before every save (26 checks). Valid.
2. **Readings.** [observed: `run1/cluster/summary.txt`] key-cache entries grow from 200016 to about 400000 and 798817 across restarts: [inferred: the restarted node reads `keyspace1.counter1` sstables during `counter_write`, which adds that table's partitions to the key cache; the three tiers' saved items use the live number measured in the same phase, so this does not enter the relation]. The warm-load key count of 255 is above the 100 saved: [inferred: entries the node itself adds after start; the log line "Completed loading (n keys)" prints the key cache's size for every cache type, `AutoSavingCache.java:192`, so its row and counter numbers are not those caches' counts]. Cluster counter cache sits at its 50 MiB cap (10485760 B file = 436906 x 24 B + 16), which does not touch the relation.
3. **Matched row.** Unit: B2g row 1 "items == min(N,P), length monotone in N: claim holds" [observed: `unit/test.out`: items 1/100/1000/9999/10000 for N = 1/100/1000/9999/10000, 10000 for N = 20000 and 0, file lengths monotone]; with B5-U5(a) (N >= P writes the whole cache, the cap not binding) for N = 10000, 20000 and 0. B2f's items == min(N,P), reloaded size == items, linear length (9.91 against 10 within 10%), unchanged live size, race <= 10000 all held; the one B2f clause that did not hold is "N=100 persisted keys are the hot 100" (0 of 100), which is a side check with its own B5-U5(b) row (side finding, claim on count unaffected). Cluster: B3g row 1 "saved items and file size scale with N, plateau at the live population: claim holds" [observed: `phases.jsonl` lines 1 to 4, 7, 8] and row 2 "live entries and steady memory unchanged by N: claim holds for the memory side" [observed: entries 200016/200000/436906 in all four runtime phases, steady heap 234.4 MB each, `RssAnon` 2819 to 2821 MB, off-heap 0.49 MB]; the restart row "after restart entries ~ N" holds for row (100) and counter (100) and is 255 for the key cache (see 2), against 200016 live before.
4. **Excluded rows.** B2g "items > N for some 0 < N < P" (refutation): no row has completed > N (26 rows). "Live size changes with N": no (live = liveAfterSave in 26 rows; cluster entries equal across phases). "Race writes > size at construction": 10000 written of 15000 (counterfactual iterator would yield 15000, so the break at `AutoSavingCache.java:388` did the bounding). "Items < min(N,P) with nothing dropped": none. B3g "file size independent of N": no (ratios 5.02%, 0.05% against 5.00%, 0.05%). "Steady heap/off-heap changes with N": no. "File exceeds N x entry size by a large factor": no (per item: key 15.8 to 19.9 B, row 11.5 B at P=2000 and 15 B on the node, counter 24 B). "Runtime change needs a restart" (B5-C4a): no (first save after each setter carried the new N). "Limit never reached" (C4b): no. The no-save control created no file.
5. **Observed vs inferred.** Inferred statements the conclusion rests on: (a) that the `hotKeyIterator` branch at `:312` (not `:307`) produced the N < population saves [inferred: from items < live; no branch trace was taken; the counterfactual iterator shows the loop break at `:388` alone would not have limited a weakly consistent iterator, which is separate]; (b) that the file bytes are disk usage of the saved cache [observed: `ls`-equivalent `os.stat` sizes in `phases.jsonl` and `File.length()` in the unit test]; (c) the key-cache growth across restarts (item 2).
6. **Deviations and gaps.** The transient heap of the hottest-N snapshot is not separable: thread-allocated bytes grow with N (127 KB at N=1 to 5.5 MB at N=10000, 0.53 KB per item), which includes serialisation and is not a retained-heap measurement; `jstat`/class histograms inside the iteration were not taken (B3d lists it as not observable). The unit populations are small (P = 2000 to 10000) and the OHC row cache is the unit yaml's 16 MiB. One cluster node and one yaml per lifetime; yaml 10000 and 100 were each one lifetime. The hot-key side check failed (0 of 100). No positive control is needed (positive estimate). Run 1a of the unit tier lacked the hot-check lookup control (R1); run1b is the record.
7. **Core question.** The number of entries written per save is capped at `*_cache_keys_to_save` and the saved-cache file size follows it, up to the live population and no further, on all three caches, at the unit tier (items = min(N,P), file linear in items) and on a running node (file bytes = items x constant, 5.02% / 0.05% of the unset file for N = 10000 / 100), by yaml and at runtime; the live cache and the steady heap do not move with N, and the capacity control shows memory follows `key_cache_size`. Usage (disk) follows the constraint, so the constraint caps disk; it does not cap memory, as the case's estimate says.

**Conclusion (one line):** unit B2g row 1 and cluster B3g rows 1 and 2 (with the B5 N >= P and restart rows) — confirmed, the setting caps the saved-cache file and does not cap the live cache.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` (output `run1/selfcheck-output.txt`, 0 failures after R3) re-parses `unit/test.out` and `unit/saved-log-lines.txt` (the test JVM's own log lines `Saved … (n items)`), and on the cluster tier `system.log` (the `Saved` lines with their UTC times) against the setter times in `session.log`, without using `phases.jsonl`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | stress outputs 0 errors; populations 200016/200000/436906 from the unset-phase `Saved` lines (self-check) against N = 100 / 10000 |
| 2. Readings | yes | the key-cache growth is explained by inference only (kept as inferred); the log line quirk was checked in the source (`AutoSavingCache.java:189-192` prints `keyCache.size()`) |
| 3. Matched row | yes | self-check: every `Saved` line in each setter window after the first 10-s cycle equals min(N, population) (12 setter windows) and the yaml lifetimes end at 100 and 10000; unit: 26 rows completed == loaded == size == min(N,P) and the test log's `Saved` multiset covers every row |
| 4. Excluded rows | yes | no row with items > N; unit live size unchanged; file length linear in items (0.95% max deviation) |
| 5. Observed vs inferred | yes | inference (a) stays inferred; no run proves the branch taken, only that the cap held |
| 6. Deviations and gaps | yes | the heap gap is recorded as not observable |
| 7. Core question | yes | the chain steps (items, file bytes, live entries, heap, capacity control) each trace to the rows above |

### 5.2 Run 2?

No — 2026-10-26. The result confirms the filed estimate, the relations are exact (items equal min(N, population) in every phase of both tiers) and the independent re-parse agrees; the inferred statements do not change the verdict.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive (disk). **Outcome class:** true positive (positive, caps).

**Claim tested:** (B1) for each cache type, the saved-cache file written by one save holds at most N entries and its size grows with N up to the live cache population and no further, where N = `*_cache_keys_to_save` (0 or >= population means all); and the setting does not change the live cache population or its memory. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1; B5 N >= P row; race row not triggered; heap row: allocation grows about 0.5 KB per saved item, side finding) | caps | run 1b + self-check | 2026-10-26 |
| Cluster | Confirmed (B3g rows 1 and 2; restart row: row/counter 100, key 255 against 200016) | caps | run 1 + self-check | 2026-10-26 |

**Positive control:** not required (the file's claim is that the cap binds).

**Side findings** (not part of the claim): (1) `hotKeyIterator(100)` on the key cache returned none of the 100 keys touched five extra times, so the persisted N keys are not necessarily the most-used ones; (2) the log line "Completed loading (n keys) <type> cache" prints the key cache size for every type (`AutoSavingCache.java:189-192`); (3) `nodetool setcachekeystosave` help text says "0 to disable" while 0 saves all keys (already in HANDOFF follow-ups); (4) the save thread allocates about 0.5 KB per saved item.

**Feedback filed:** the case file's section D updated (not committed); amendments B5 filed before run 1; no change to B1, B2f/B3f or any row's meaning. Leftovers: none running (`ps` checked); `/dev/shm/s4-b8-kt` removed; work trees `~/s4-b8-kt/{u,c}` and logs `~/s4-b8-kt-logs` kept on pc07.
