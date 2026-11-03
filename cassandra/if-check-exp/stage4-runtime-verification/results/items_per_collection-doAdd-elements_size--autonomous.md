# items_per_collection-doAdd-elements_size--autonomous — stage-4 results  <!-- file: results/items_per_collection-doAdd-elements_size--autonomous.md -->

> **Case:** [`items_per_collection-doAdd-elements_size--autonomous`](../../stage3-ai-deep-read/cases/items_per_collection-doAdd-elements_size--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26. **Unit: Confirmed — caps only on some paths (bypass)** (B2g row 1, all three
> claims). **Cluster: Confirmed for claims (i)–(ii) — caps only on some paths (bypass)** (B3g row 1: every over-threshold
> ordinary-user write rejected with no memtable or disk usage, at T = 1000 and T = 10000; 200 appends grow one stored set to
> 200·T items, 1.80 MB and 18.6 MB on disk, never rejected; the superuser control and the disabled reference write the same
> workload). **Claim (iii) Not confirmed in the cluster tier** (amended B3g row 3): an empty append on a key not yet written
> adds no cells and no disk bytes, but leaves 8 B of memtable data size, the memtable's fixed charge for a new partition entry.
> No run 2.
>
> **Outcome class:** undetermined — the stage-3 estimate (`undetermined`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/items_per_collection-doAdd-elements_size--autonomous/`](../harness/items_per_collection-doAdd-elements_size--autonomous/).
>
> **Cluster re-run ("run 1b", 2026-10-28)** at the re-frozen version `8b256e69…5840`, after the user-authorised amendment of
> B3a, B3c, B3d, B3e, B3f (iii), B3g, B3h and B4 (claim (iii)'s bound restated from the source; phase (iii-b) added):
> **Cluster: Confirmed for claims (i)–(iii) — caps only on some paths (bypass)** (§7). The run-1 cluster verdict above stays on
> record as filed; the unit tier (Confirmed) was not re-run.
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).
> The case file was written by an earlier stage-3 session on the same day; this session did not write it.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `c21b718` (sha256 `50094009…5b32`). Frozen after the step-0 audit's sixteen amendments (2026-10-26, before any run-1 reading): sha256 `c7e60e9c198f23f6d8e47a935582ca540c01b9c6f47d11567b330553deea2612`. **Re-frozen** after runbook defect U1 in the first unit attempt (amendment B2c-2; claim, predictions and conclusions unchanged): sha256 **`268a63b5b67d1c670b4480861d06eeaae51a614317f0c41ac65ab57365c60be7`**. Both tiers' verdict readings were taken at this version. Both hashes are new rows in `_INDEX-advisor.md` §2; `run1/freeze.txt`. Not committed (no commit was asked for). |
| **Harness** | [`../harness/items_per_collection-doAdd-elements_size--autonomous/`](../harness/items_per_collection-doAdd-elements_size--autonomous/): `ItemsPerCollectionProbeTest.java` (B2c's text with amendments B2c and B2c-2), `unit-run.sh`; `ipc.py` (bundled-driver client, one call per phase), `cluster-run.sh` (one node lifetime, arms A, B, R). Instrument checks before run 1: the probe compiled and ran in the shakedown (`-Dprobe.t=20 -Dprobe.appends=10`, `shakedown/unit-t20-a10-summary.txt`); cluster shakedown at T1 = 50, T2 = 500, 20 reps (`shakedown/cluster-50-500-20-summary.txt`). It found two instrument problems, both fixed before the freeze: the `getguardrailsconfig` read-back grep matched nothing (a single guardrail prints `[fail, warn]`; checked on a 2-rep re-run, `shakedown/readback-*-cluster3.txt`), and the guardrail's write-time messages are folded by a `NoSpamLogger` (`Guardrail.java:47`). Self-check [`run1/selfcheck.py`](items_per_collection-doAdd-elements_size--autonomous/run1/selfcheck.py) was written before run 1 and tested on the shakedown files. |
| **Tiers and values** | Unit (B2): one `ant testsome` JVM; T ∈ {100, 1000} (warn T/2), 50 appends of T items, then the disabled reference −1/−1. Cluster (B3): one node, `-Xmx4G`, PasswordAuthenticator + CassandraAuthorizer, ordinary role `app`; arm A T = 1000 (yaml), arm B T = 10000 (runtime), arm R −1/−1 (runtime, W = 1000); 200 operations per phase. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the operand is an item count per write (`Sets.java:399`); its byte size is derivable (each item one cell, `:401-409`). Usage is read as memtable data size and sstable bytes. |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | Two values in each tier; the default −1 was named as a reference in B2b/B3b but no step ran it. Reference arm added to both tiers (amendments B2b, B2c, B3b, B3e). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Unit reads `memtableLiveDataSize` (the memtable's own accounting, gap named by amendment B2d); cluster reads sstable bytes on disk (real) and tablestats. |
| A. Core question | usage driven to the limit and past it | Met | T+1 single writes; appends to 50·T (unit) and 200·T (cluster). |
| B. Logic | each step says what it establishes | Met | B2h/B3h say what each phase and control establishes. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "about 0", "roughly linearly", "same order", "one ERROR line" had no exact form (amendments B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Missing: failed superuser control, reference rejecting, read-back mismatch, (iii) non-zero, one T only, automatic flush, no row fits; and the Effect rule (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The rejection boundary moves with T (T+1 rejected at each T) and the guardrail message is the direct disallow evidence (`Guardrail.java:139-140`). |
| B. Logic | alternative explanations and their controls | Met | Superuser control (same write accepted), disabled reference, flush after each phase; amendments add auto-compaction off and compression off. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Table names per arm, read-back command, observable file, phase split (amendments B2d, B2e, B3c–B3e). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | `printf` splits lines in the test log; BSD `du` has no `-b` (amendments B2c, B3d). |
| D. Runnable | harness and environment prerequisites exist or are listed | Not met → Met after amendment | As written: the probe does not compile (`GuardrailTester.java:89-90`: `USERNAME`, `PASSWORD` are `private`); `/local` paths; `PYTHONPATH=<zip>` cannot import `cassandra`; `du -sb`; `jmxterm` absent; `bin/cassandra -p` daemonizes and there is no `setsid` here. Fixed before the freeze (amendments B2a, B2c, B3a–B3d). One more surfaced in run 1 (§3, U1). |
| D. Runnable | workload arithmetic reaches the limit | Met, with a heap change | 200·10000 = 2,000,000 cells in one partition: at the filed 2G heap the flush trigger (≈ 170 MiB, `DatabaseDescriptor.java:586-587, 753-755`, `conf/cassandra.yaml:811`) was close enough to split phase (ii); heap 4G (amendment B3a). Disk: < 50 MB per run against 137 GiB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `~/cassandra-src` at `cassandra-5.0.9`: `Sets.java:343-420`, `Threshold.java:75-141`, `Guardrail.java:47, 85-145, 187-198`, `Guardrails.java:380-387, 988-1003`, `ClientState.java:595-605`, `SortedTableWriter.java:185-215, 393-430`, `GuardrailTester.java:89-150`, `CQLTester.java:579-630, 1517-1531`, `GuardrailsConfigCommand.java:60-260`, `Config.java:526, 919-920`, `conf/cassandra.yaml:198, 217, 300, 327, 2161-2169`, `test/conf/cassandra.yaml:48-67`. A1's yaml lines are 2166-2169 (cited 2161-2169; not load-bearing). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone and build | Amendment 2026-10-26 | `/local` does not exist here. |
| 2 | B2b: run the −1/−1 default as a reference | Amendment 2026-10-26 | Group A, third value. |
| 3 | B2c: compile fix, one `println` per reading, `-Dprobe.t`/`-Dprobe.appends` (shakedown only), read-back line, superuser memDelta, reference arm | Amendment 2026-10-26 | The probe does not compile; split log lines; instruments. |
| 4 | B2d: observable file; memtable accounting gap named | Amendment 2026-10-26 | Stdout lands in `build/test/logs`. |
| 5 | B2e: procedure via `unit-run.sh` | Amendment 2026-10-26 | Paths, clean clone. |
| 6 | B2f: exact forms | Amendment 2026-10-26 | Tolerances. |
| 7 | B2g: six rows, Effect rule | Amendment 2026-10-26 | Group B. |
| 8 | B3a: this host; heap 4G; read timeout 60 s; readiness incl. superuser login | Amendment 2026-10-26 | Paths; flush trigger; 2M-element read-back; superuser setup delay (`CassandraRelevantProperties.java:538`). |
| 9 | B3b: nodetool setter and read-back; reference arm R | Amendment 2026-10-26 | No `jmxterm`; group A. |
| 10 | B3c: driver import, auth, per-arm tables, compression off, auto-compaction off, GRANT wait | Amendment 2026-10-26 | Import fails as written; B3f's disk bound assumes uncompressed cells (`CompressionParams.java:61`); attribution. |
| 11 | B3d: byte count, per-phase observables, NoSpamLogger | Amendment 2026-10-26 | BSD `du`; instrument. |
| 12 | B3e: one script, one lifetime, three arms | Amendment 2026-10-26 | Order, names. |
| 13 | B3f: exact forms | Amendment 2026-10-26 | Tolerances. |
| 14 | B3g: seven rows, Effect rule | Amendment 2026-10-26 | Group B. |
| 15 | B4: this host | Amendment 2026-10-26 | Paths. |
| 16 | B2c-2: read thresholds off in the probe | Amendment 2026-10-26 (run 1, defect U1) | §3. |
| 17 | B3: the empty append should target an existing partition (as the unit tier does), or the prediction should allow the memtable's per-partition charge | Left for stage 3 (section D) | Found by run 1; changing it now would tune the prediction to a reading. |
| 18 | A1: yaml lines 2166-2169, not 2161-2169 | Left for stage 3 | Not load-bearing. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (unit 13:29–13:31 EDT, attempt 1 with defect 13:28–13:29; cluster 13:31–13:34 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab (`run1/stepE.txt`) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (Apple M1 Pro, T6000); 10 cores, 32 GiB RAM; internal SSD (APFS, solid state), 137 GiB free; loopback 127.0.0.1–.3 present (one node, 127.0.0.1); ports 7000/7199/9042/9091 free, no `CassandraDaemon` before or after |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: `ant testsome` forked JVM. Node: `-Xms4G -Xmx4G` (`MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`), no agent |
| Ant | 1.10.18 |
| Python / driver | Python 3.8.11; bundled `cassandra-driver-internal-only-3.29.0.zip`, protocol 5, `PlainTextAuthProvider` |
| Local `cassandra-src` clone commit | `$W/cassandra-run31` = `~/Library/Caches/stage4/cassandra-run31`, fresh clone of `~/cassandra-src` at `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` `BUILD SUCCESSFUL` in 56 s |
| Case-file commit / harness commit | filed `c21b718`; amendments, harness and results uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-ipc/{data,commitlog,hints,saved_caches,cdc_raw,logs}`, own `conf/`; wiped before and after |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/items_per_collection-doAdd-elements_size--autonomous/` — `clone-build-run31.log`, `stepE.txt`, `shakedown/` (not evidence), `unit-attempt1-defectU1/`, `unit/` (`ant.log`, `TEST.log`, `TEST.xml`, `probe.txt`, `commands.log`, `summary.txt`), `cluster/` (`node.out`, `system.log`, `commands.log`, `summary.txt`, `guardrail-<arm>-<phase>.txt`, `readback-*.txt`, `yaml-*.txt`), `cluster.out` |

**Machine facts relied on** (`environment-advisor.md` and earlier runs on this host): no `mkdir` in `$HOME` outside `$W`; every `ant` call with `-Dlocal.repository=$W/m2`; no `setsid`, so the node is a tracked background `bin/cassandra -f`; the forked test JVM writes stdout to `build/test/logs/**/TEST-<class>.log`, one line per `System.out` write (amendments B2c, B2d); `CQLTester` needs `requireNetwork()` (done by `GuardrailTester.setUpClass`); the test yaml enables read thresholds (`test/conf/cassandra.yaml:63-67`), which became defect U1; the bundled driver is under a subfolder of the zip, used with `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, `idle_heartbeat_interval=0`, reconnect on error (no retry was needed); **under AllowAllAuthenticator every client is a superuser (`ClientState.java:604`) and guardrails skip superusers (`Guardrail.java:93-96`)** — the case file already used PasswordAuthenticator + CassandraAuthorizer and a non-superuser role, so no amendment was needed for it, and `setup` confirmed `app_is_superuser=False` in each arm; the daemon pattern in the scripts is split so their own command lines never match; long steps ran in the background and were polled; no BSD/GNU `sed -i` mix (BSD form only); `jstat`/MAT not needed (no heap reading in this design).

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| A1 | audit | B2c | The probe does not compile: `GuardrailTester.USERNAME`/`PASSWORD` are `private` (`GuardrailTester.java:89-90`) | literals (amendment B2c item 1) | 2026-10-26, before the freeze; §9a unchanged | uncommitted |
| A2 | audit | B2e | `grep PROBE` on Ant's console finds nothing: the forked JVM's stdout goes to the test log; `printf` splits lines there | read the test log; `println(String.format(...))` (amendments B2c, B2d, B2e) | 2026-10-26, before the freeze | uncommitted |
| A3 | audit | B2a/B3a/B3c/B3d/B3e | `/local` paths; `PYTHONPATH=<zip>` cannot import `cassandra`; `du -sb` (BSD); `jmxterm` absent; `bin/cassandra -p` without `setsid` | this host's paths, zip-subfolder import, Python byte sum, `nodetool setguardrailsconfig`, tracked `bin/cassandra -f` | 2026-10-26, before the freeze | uncommitted |
| **U1** | **run 1, unit tier, attempt 1** | B2c/B2e (the probe's read-back `card(3)` at T = 1000) | The test errored after the 40th append at T = 1000: `ReadFailureException` on `SELECT v … WHERE k = 3` because the unit yaml enables read thresholds and the read loaded 8,846,516 bytes against `local_read_size_fail_threshold: 8192KiB` (`run1/unit-attempt1-defectU1/error-excerpt.txt`, `read-threshold-lines.txt`). The appends themselves were not rejected; the read instrument failed | probe calls `DatabaseDescriptor.setReadThresholdsEnabled(false)` and prints the setting (amendment B2c-2). The node's default is `false` (`Config.java:526`), so the cluster tier is unaffected | 2026-10-26; claim, predictions and conclusions unchanged; re-frozen (sha256 `268a63b5…60be7`); **unit tier restarted from its beginning** | uncommitted |

The attempt-1 readings (`run1/unit-attempt1-defectU1/summary.txt`) are kept as defect evidence and are not used for the verdict.

The cluster re-run session added these on 2026-10-28: the re-freeze after run 1 (R1, a case-file amendment authorised by the user) and the harness changes for the re-run (H1–H3). No runbook defect occurred in the re-run's shakedown or re-run.

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| R1 | Cluster run 1 (a reading, not a runbook defect) | B3a, B3c, B3d, B3e, B3f (iii), B3g, B3h, B4 | Claim (iii) was Not confirmed in the cluster tier only because phase (iii) left "Memtable data size" 8 B (no items, disk 0) against the frozen bound 0 (§4.2). | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-28:** eight dated amendments `Amendment 2026-10-28 (after run 1, authorised by the user)`. **B3f (iii):** the bound restated from the source: an empty update to a key new to the current memtable is charged exactly `initialSize = 8` (`SkipListMemtable.java:110-133`, `:126`), its own data size is 0 (`PartitionUpdate.java:913-916`, `BTreePartitionUpdater.java:80-109`, `BTree.java:347-348`); "Memtable data size" before (iii)'s flush = 8 B exactly. **B3c/B3d/B3f:** new phase (iii-b), seed key 3 with one item, then 200 empty appends, M_empty − M_seed = 0 exactly (strict reading). **B3g:** rows for (iii-a)/(iii-s)/automatic flush/all hold. **B3h:** the controls. **B3a, B3e, B4:** fresh clone `$W/cassandra-run73`, node `$W/node-ipc73`, order i, ii, iii, iii-b, iv. The whole cluster tier was re-run from its beginning (§7). B1, claims (i)–(ii), their predictions and rows, and the unit tier are unchanged. | user, 2026-10-28 | sha256 `8b256e69…5840` (uncommitted; no commit was asked for) |
| H1 | Cluster re-run | B3a/B4 paths, B3e order | `cluster-run.sh` used run 1's node directory and phases. | Reads `IPC_NODE` (node dir) and `IPC_PLAN` (`run1` = phases i ii iii iv, the default; `run2` = i ii iii iiib iv); for `iiib` it runs the seed, takes the "seeded" tablestats sample, then the phase as before, then `card 3`. sha256 prefix `ff0b60e7` → `03a6316e`. | AI, 2026-10-28 | n/a (harness) |
| H2 | Cluster re-run | B3c phase (iii-b) | — | `ipc.py` gains `phase iiibseed` (one append `{0}` on key 3) and `phase iiib` (empty appends on key 3), both as `app`. sha256 prefix `bec986c9` → `1bca02df`. | AI, 2026-10-28 | n/a (harness) |
| H3 | Cluster re-run | self-check | `run1/selfcheck.py` checks run 1's relations. | `run1b-cluster/selfcheck.py` copies the cluster part of `run1/selfcheck.py`; `--relations run1` reproduces run 1's cluster lines exactly; `--relations amended` (default) reads C12 as "memtable exactly 8 B", adds C12b ((iii-b)) and C18 (no automatic flush), prints the B3g reading and exits 1 on any failed check. `run1/selfcheck.py` is unchanged. | AI, 2026-10-28 | n/a (harness) |

**Shakedown note (instrument checks, not run-1 readings):** besides the read-back and NoSpamLogger fixes in §1, the cluster shakedown showed "Memtable data size: 8" after phase (iii). The prediction (amended B3f: 0) was **not** changed after seeing it, since that would tune a prediction to a reading; run 1 tested it as frozen (§4).

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `items_per_collection-doAdd-elements_size--autonomous/run1/unit/commands.log`, `items_per_collection-doAdd-elements_size--autonomous/run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/test-log-probe-lines.txt`, `ant-tests-run.txt`; `Tests run: 1, Failures: 0, Errors: 0`; `PROBE readThresholdsEnabled=false`)

| T | read-back | single T+1 (ordinary user) | memDelta on rejection | emptyAdd memDelta / card | append card at 10…50 appends | mem at 10…50 appends (B) | superuser T+1 card / memDelta |
|---|---|---|---|---|---|---|---|
| 100 | warn 50, fail 100 | rejected: `Guardrail items_per_collection violated: Detected collection v with 101 items, this exceeds the failure threshold of 100.` | 0 | 0 / 100 | 1,000 · 2,000 · 3,000 · 4,000 · 5,000 | 26,482 · 50,482 · 74,482 · 98,482 · 122,482 (+24,000 each) | 101 / 2,465 |
| 1000 | warn 500, fail 1000 | rejected: `… with 1001 items, this exceeds the failure threshold of 1000.` | 0 | 0 / 1,000 | 10,000 · … · 50,000 | 264,082 · 504,082 · 744,082 · 984,082 · 1,224,082 (+240,000 each) | 1,001 / 24,065 |
| −1 (reference) | warn −1, fail −1 | 1001 items **accepted** | memDelta 24,065 | — | — | — | card 1,001 |

**Cluster tier** (`run1/cluster/summary.txt`, `commands.log`, `readback-*.txt`, `guardrail-*-excerpt.txt`, `systemlog-flush-key1-lines.txt`; 0 connection errors and 0 retries in every phase; no automatic flush of a probe table; `app_is_superuser=False` in each arm). Disk = bytes of the table directory; Δ = change in that phase.

| Arm (T) | Phase | Client outcome | Memtable data size before flush (B) | Disk Δ (B) | Other |
|---|---|---|---|---|---|
| A (1000; read-back `[1000, 500]`) | (i) app, 200 × 1001 items | 0 accepted, 200 rejected, `… with 1001 items, this exceeds the failure threshold of 1000.` | 0 | 0 (no sstable) | keys 1000–1199 present: 0 |
| A | (ii) app, 200 appends × 1000 on key 1 | 200 accepted, 0 rejected | 4,800,041 | 1,801,145 | card(1) = 200,000; one flush-time line `… in row 1 in table probe.s1000 with 200000 items …`; flush rc 0; sstables 0 → 1 |
| A | (iii) app, 200 empty appends on key 2 | 200 accepted | **8** | 0 | card(2) = 0; sstables unchanged |
| A | (iv) cassandra, 200 × 1001 items | 200 accepted | 4,813,000 | 1,215,518 (0.675 × (ii)) | keys 2000–2199 present: 200; card(2000) = 1,001; 200 flush-time lines |
| B (10000; read-back `[10000, 5000]`) | (i) | 0 accepted, 200 rejected, `… with 10001 items, this exceeds the failure threshold of 10000.` | 0 | 0 | keys present: 0 |
| B | (ii) 200 appends × 10000 | 200 accepted | 48,000,041 | 18,586,169 | card(1) = 2,000,000 (read in 5.4 s); one flush-time line naming 2000000 items; flush rc 0; sstables 0 → 1 |
| B | (iii) | 200 accepted | **8** | 0 | card(2) = 0 |
| B | (iv) | 200 accepted | 48,013,000 | 12,016,561 (0.647 × (ii)) | keys present: 200; card(2000) = 10,001; 200 flush-time lines |
| R (−1; read-back `[-1, -1]`, W = 1000) | (i) app, 200 × 1001 items | **200 accepted** | 4,813,000 | 1,215,521 (1.000 × (iv)) | keys present: 200 |
| R | (ii) | 200 accepted | 4,800,041 | 1,794,144 | card(1) = 200,000; no flush-time line |
| R | (iii) | 200 accepted | 8 | 0 | card(2) = 0 |
| R | (iv) | 200 accepted | 4,813,000 | 1,215,514 | card(2000) = 1,001; no flush-time line in any arm-R phase |

Write-time failure lines in `system.log`: one per arm for the 200 rejections (folded by the `NoSpamLogger`, as amended B3d says).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — [observed: `unit/test-log-probe-lines.txt`] read-backs equal the set thresholds (50/100, 500/1000, −1/−1); read thresholds were off; the test passed; the limit was passed (T+1 per write, 50·T per stored set). Valid.
2. **Readings** — memtable data size grows exactly 24 B per item at both T (24,000 per 1,000 items; 240,000 per 10,000), and the superuser T+1 write and the reference 1001-item write add 24,065 B, the same as 1,001 items' worth. Nothing unusual.
3. **Matched row** — B2g row 1, "Single T+1 rejected with memDelta 0; appends reach 50T and mem grows; superuser accepted" [observed: rejection with the guardrail message and `with T+1 items`, memDelta 0, at both T; append cards 10T…50T with strictly increasing mem; superuser card T+1, memDelta > 0; the reference accepted with memDelta 24,065 and card 1,001; emptyAdd memDelta 0, card T].
4. **Excluded rows** — "an append is rejected once card exceeds T": the test passed and cards reached 50T. "single T+1 accepted": rejected at both T. "memDelta > 0 on rejection": 0. "appends flat": +24,000 / +240,000 per 10 appends. Added rows: control not failed; reference not rejecting; read-backs equal; (iii) holds; both T fit.
5. **Observed vs. inferred** — all observed.
6. **Deviations and gaps** — the first attempt stopped at defect U1 (§3); the tier was restarted at the re-frozen version. The unit tier reads the memtable's accounting, not the live heap (gap named in amendment B2d).
7. **Core question** — the knob caps what one ordinary-user write adds: at each T the T+1 write is refused before any cell is added (memDelta 0), while the same write by a superuser, or with the knob at its default, adds 1,001 items' worth. Usage of the stored set does not follow T: 50 appends of T items grow it to 50·T items, with memtable usage linear in items.

**Unit tier conclusion:** B2g row 1 — **confirmed**. Effect (amended B2g): **caps only on some paths (bypass)**.

**Cluster tier**

1. **Validity** — [observed: `cluster/readback-*.txt`, `summary.txt`] read-backs `[1000, 500]`, `[10000, 5000]`, `[-1, -1]`; `app` not a superuser in each arm; 0 connection errors; no automatic flush of a probe table; `yaml-diff.txt` shows only the B3a overrides; `-Xms4G -Xmx4G`. The limit was passed in every arm. Valid.
2. **Readings** — phase (iii) leaves 8 B of memtable data size in every arm, including the reference. [inferred: source] `SkipListMemtable.put` charges a fixed `initialSize = 8` to the live data size when an update creates a new partition (`SkipListMemtable.java:112-133`; skiplist is the default memtable, `conf/cassandra.yaml:789-790`). Key 2 had never been written, so the empty append's mutation created an empty partition entry; card(2) = 0, no sstable was written, and the unit tier's empty append on an existing partition left memDelta 0. The `:393` branch itself added nothing.
3. **Matched row** — B3g row 1, "(i) ~0 delta and all rejected; (ii) grows to 200·T and is accepted; (iv) grows" [observed: (i) 200/200 rejected with the guardrail message, memtable 0, disk Δ 0, keys present 0, at T = 1000 and 10000; (ii) 200/200 accepted, card 200·T exactly, disk Δ 1.80 MB > 1 MB and 18.6 MB > 10 MB, exactly one flush-time line naming 200·T items, flush rc 0, one new sstable; (iv) accepted, Δ 0.675 and 0.647 × (ii); arm R accepts (i) with Δ 1.000 × (iv) and logs no flush-time line]. **And** amended B3g row 3, "(iii) leaves a memtable or disk delta above the B3f bound … Claim (iii) wrong; recorded as Not confirmed for (iii); the other rows are read on their own" [observed: memtable 8 B against the frozen 0; disk Δ 0 and card(2) = 0 do hold].
4. **Excluded rows** — "(ii) rejections once the stored count exceeds T": 0 rejections, cards 200·T. "(i) accepted for app": 0 accepted. "(iv) delta ~0": 1.2 MB and 12.0 MB. "Flush fails or aborts": rc 0 and one sstable per phase (ii), the flush-time check only logged (`Guardrail.java:139-140`, state null). Added rows: read-backs equal, app not super, no connection errors (Invalid excluded); arm R behaves (Invalid excluded); (i) disk Δ 0 (no partial application); both arms fit row 1; no automatic flush; a row fits.
5. **Observed vs. inferred** — one inferred statement: the source explanation of the 8 B (part 2). The verdict does not depend on it: (iii) is Not confirmed by the frozen rule whatever the cause.
6. **Deviations and gaps** — none in the cluster run. Disk is read as file bytes of an uncompressed table (amendment B3c); heap was 4G, not the filed 2G (amendment B3a).
7. **Core question** — the knob caps what one ordinary-user write adds to the memtable and disk (zero for every T+1 write at both T), and the cap moves with T. It does not cap the stored collection: 200 appends grow one set to 200·T items (200,000 and 2,000,000), 1.80 MB and 18.6 MB on disk, never refused; the flush-time check only logs. Superusers bypass it (phase (iv)), and at the default (−1) it does nothing (arm R).

**Cluster tier conclusion:** B3g row 1 — **confirmed** for claims (i)–(ii), Effect **caps only on some paths (bypass)**; claim (iii) — **not confirmed** (amended B3g row 3).

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before run 1, extended before the restarted unit tier with one check for amendment B2c-2) re-reads `unit/TEST.log`, `unit/ant.log`, `cluster/system.log` (recounting the guardrail lines per arm by item count and table name), `cluster/commands.log` and the raw `readback-*.txt` files, and re-derives every B2f/B3f condition. Output: `run1/selfcheck.out` — **60 checks, 58 pass, 2 fail**. The two failures are C12 for arms A and B, the (iii) memtable reading of 8 B (the same reading as §4.2 part 3). Its row-1 summary: unit all hold; cluster arms A, B, R all hold for the row-1 conditions.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `readback-A/B/R.txt` hold `[1000, 500]`, `[10000, 5000]`, `[-1, -1]`; `summary.txt` `app_is_superuser=False` ×3, `conn_errors=0` ×12; `flush-lines.txt` no "Flushing largest"; `TEST.log` `readThresholdsEnabled=false` (U0b, C1–C3, C17) |
| 2. Readings | yes | 8 B in phase (iii) of all three arms in `summary.txt`; `SkipListMemtable.java:112-133` re-read: `initialSize = 8` only when `previous == null` |
| 3. Matched row | yes | U1–U9 and C4–C11, C13–C16 pass; the cluster's (iii) failure is filed under its own row, as amended B3g says |
| 4. Excluded rows | yes | No rejection in any (ii)/(iii)/(iv)/arm-R phase; flush rc 0 ×12; disk Δ of (i) 0 in A and B |
| 5. Observed vs. inferred | yes | The only inferred statement (cause of 8 B) is not needed for any verdict |
| 6. Deviations and gaps | yes | U1 recorded with its evidence (`unit-attempt1-defectU1/`); heap and compression amendments made before any reading |
| 7. Core question | yes | Per-write: rejection at T+1 with zero usage at four (T, tier) points, accepted under the superuser control and the reference. Stored: 50·T and 200·T items accepted with usage growing linearly (unit +24 B/item; cluster 1.80 → 18.6 MB at 10× items). The logic of B1 → B2g/B3g row 1 holds |

### 5.2 Run 2?

**No** — 2026-10-26. All verdict statements are observed and the self-check settles every part from run 1's files. The README lists a confirmed bypass as a reason to choose run 2; here the bypass is the design's own claim, read directly (superuser phase, reference arm, append series), so run 2 is left as an option for a fresh session rather than done now.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Cluster re-run ("run 1b") after the B3a, B3c, B3d, B3e, B3f (iii), B3g, B3h, B4 amendment — 2026-10-28

Session: Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-28, on the advisor's machine. Run 1's sections above are kept as filed; the
unit tier (Confirmed) was not re-run. Excerpts: [`run1b-cluster/`](items_per_collection-doAdd-elements_size--autonomous/run1b-cluster/).

### 7.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | Run 1's cluster tier confirmed claims (i)–(ii) (B3g row 1); claim (iii) was Not confirmed only because phase (iii)'s 200 empty appends on key 2, a key not yet written, left "Memtable data size" 8 B, against the frozen bound 0 (disk delta 0, card(2) = 0) (§4.2). The README says a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised on 2026-10-28 that claim (iii)'s bound be restated from the source and the whole cluster tier re-run. |
| **Source derivation** | (in the B3f amendment, with `file:line`) The empty bound set (non-null, 0 elements in the driver's serialisation) makes `Sets.Adder.doAdd` return at `Sets.java:393`; the UPDATE row has no liveness (`UpdateStatement.java:70-73`) and is dropped as empty (`PartitionUpdate.java:913-916`), but the empty `PartitionUpdate` is still wrapped in a `Mutation` and applied (`SingleTableUpdatesCollector.java:97-117`, `ModificationStatement.java:520-529`, `Keyspace.java:627-653`, `ColumnFamilyStore.java:1475-1477`). In `SkipListMemtable.put` (the default memtable, `conf/cassandra.yaml:783-790`) a key not in the **current** memtable gets an empty partition and `initialSize = 8` (`SkipListMemtable.java:110-128`, `:126`), and `liveDataSize += initialSize + updater.dataSize` (`:133`); the row overhead goes to the allocator, not to `liveDataSize` (`:124-125`). For an empty update `updater.dataSize = 0` (`BTreePartitionUpdater.java:80-109`; `BTree.java:347-348`). tablestats "Memtable data size" is that `liveDataSize` (`TableStatsHolder.java:337`, `TableMetrics.java:502-503`), and each `nodetool flush` starts a new memtable at 0 (`ColumnFamilyStore.java:1211-1212`, `SkipListMemtable.java:87`); a memtable of empty partitions writes no sstable (`Flushing.java:167`, `ColumnFamilyStore.java:1332-1339`). |
| **Amendment** | Eight dated amendments `Amendment 2026-10-28 (after run 1, authorised by the user)`, each next to the text it changes and each saying that it follows run 1's readings. **B3f (iii):** (iii) "Memtable data size" before the flush = **8 B exactly** (one new partition: the first empty append creates it, the other 199 find it); disk ≤ 1 % of (iv) and card(2) = 0 unchanged; derived disk Δ 0 reported. **Choice of key, and which reading each choice tests:** the charge depends on the key being in the current memtable, not on it existing in the table, so after a flush "a key that already exists" (e.g. key 1, on disk) is charged 8 B too; only a key written since the last flush avoids it. So the amendment does both: phase (iii) with the 8 B term tests reading **(iii-a)** (an empty addition adds no item, cell, data or disk byte of its own; the only charge is the memtable's fixed entry for a partition new to the memtable), and a new phase **(iii-b)** (seed key 3 with one item, then 200 empty appends on it) tests the strict reading **(iii-s)** (M_empty − M_seed = 0 exactly; card(3) = 1). **B3g:** rows: (iii) ≠ 8 B → (iii-a) wrong, Not confirmed; (iii-b) ≠ 0 → (iii-s) wrong, Not confirmed; automatic flush in (iii)/(iii-b) → Invalid; both hold with row 1 → Confirmed for (i)–(iii). **B3c/B3d/B3h:** the phase, its samples, the controls. **B3a/B3e/B4:** fresh clone, node dir, order and commands. B1, claims (i)–(ii), their predictions, row 1 and its Effect, the other rows and the unit tier are unchanged. |
| **What was known of run 1 when writing it, and would run 1 pass** | **Everything in run 1's §4–§5 and section D was known**, including the 8 B in phase (iii) of every arm (disk Δ 0, card(2) = 0), and section D's attribution to `SkipListMemtable.java:112-133`; the shakedown note in §3 (8 B also in run 1's shakedown) as well. The 8 B is the literal `initialSize = 8` and "one partition" follows from the code path; nothing was taken from the reading, but the amended (iii) relation was written knowing that run 1 read exactly that value. **Would run 1 pass? The (iii) relation: yes** (8 B in arms A and B; self-check pass 3 C12 passes). **Claim (iii) as amended: no** — run 1 did not run phase (iii-b), so under the amended relations claim (iii) is not evaluable from run 1's files (pass 3: 45 checks pass, 5 fail, all (iii-b) "missing"; verdict line "(iii-b) has no reading -> Not confirmed"). (iii-b) is therefore the part this re-run could newly fail; it was not run or probed before the re-freeze. |
| **Case-file version** | sha256 **`8b256e69c85db7c87012b1ba3d2f7a91752878c8261df4b2b57dc54c94ef5840`**, a new row in `_INDEX-advisor.md` §2: "re-frozen after run 1 for cluster re-run (B3a, B3c, B3d, B3e, B3f (iii), B3g, B3h, B4), authorised by the user". The earlier rows (`50094009…`, `c7e60e9c…`, `268a63b5…`) are kept. Hashed at 03:02:14 EDT, after the fresh clone and build (02:55:05–02:56:06) and before the shakedown (03:04) and any re-run reading ([`run1b-cluster/refreeze-run2.txt`](items_per_collection-doAdd-elements_size--autonomous/run1b-cluster/refreeze-run2.txt)); recorded again at 03:03:56 with the harness hashes ([`harness-sha-run2.txt`](items_per_collection-doAdd-elements_size--autonomous/run1b-cluster/harness-sha-run2.txt)); a copy of the file at that hash is `case-file-at-refreeze-8b256e69.md` in the log folder. Section D was filled afterwards, so the file's current hash differs by that section only. Base commit `ada3c9fa`; nothing committed. |
| **Harness** | Run 1's harness with H1 (paths, plan), H2 (phase (iii-b)) and H3 (self-check copy) only (§3). Commands: `C=$W/cassandra-run73 IPC_NODE=$W/node-ipc73 IPC_PLAN=run2 OUT=$L/cluster-shake2 cluster-run.sh 50 500 20` (shakedown), then `… OUT=$L/cluster-run2 caffeinate -ims cluster-run.sh` (1000 10000 200, as filed). **The self-check ran end to end on the shakedown first:** 48 checks, 46 pass, 2 fail, exit status 1; the two failures are C9 for arms A and B, the absolute disk limits (> 1 MB, > 10 MB) that hold only at the filed sizes (at W = 50/500 and 20 reps the (ii) deltas are 13,485 and 90,040 B), as in run 1's shakedown; every (iii) and (iii-b) check passed (8 B; M_seed = M_empty = 65 B) ([`run1b-cluster/shakedown/selfcheck.out`](items_per_collection-doAdd-elements_size--autonomous/run1b-cluster/shakedown/selfcheck.out)). The self-check was not changed after the shakedown. The shakedown ran every step with 0 connection errors and every read-back right; no runbook defect. |

### 7.2 Environment

Same host as run 1 (§2): `yangwang-mbp`, macOS 27.0.1 / Darwin 27.0.0 arm64, OpenJDK 11.0.32.1, Ant 1.10.18, Python 3.8.11 with the bundled driver 3.29.0; free disk 108 GiB;
loopback `.1`–`.3` present (only `.1` used); no `CassandraDaemon` before. 2026-10-28 (EDT): fresh clone and build 02:55:05–02:56:06; re-freeze 03:02:14; known-answer
self-check passes on run 1's files 03:03; shakedown 03:04:04–03:06:33; **re-run 03:07:11–03:09:57** under `caffeinate -ims`. Clone `$W/cassandra-run73` from `~/cassandra-src` at
`b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), no local change (`ant -Dlocal.repository=$W/m2 build-test`, `BUILD SUCCESSFUL`, 54 s;
[`run1b-cluster/clone-build-run73.txt`](items_per_collection-doAdd-elements_size--autonomous/run1b-cluster/clone-build-run73.txt)). Node as in run 1: `-Xms4G -Xmx4G`, PasswordAuthenticator + CassandraAuthorizer, yaml
thresholds 500/1000, `read_request_timeout: 60000ms`, no agent; node data `$W/node-ipc73`, wiped before and after. Full logs:
`~/Library/Caches/stage4/logs/items_per_collection-doAdd-elements_size--autonomous/`: `clone-build-run73.log`, `case-file-at-refreeze-8b256e69.md`, `refreeze-run2.txt`,
`harness-sha-run2.txt`, `cluster-shake2/`, `cluster-shake2.out`, `selfcheck-shake2.out`, `cluster-run2/` (as run 1's `cluster/`: `node.out`, `system.log`, `commands.log`,
`summary.txt`, `guardrail-<arm>-<phase>.txt`, `readback-*.txt`, `yaml-*.txt`, …), `cluster-run2.out`, `selfcheck-run2.out`, `selfcheck-run2-under-run1-relations.out`,
`selfcheck-ka-run1-relations-{run1,amended}.out`. Excerpts in `run1b-cluster/`: `cluster/` (run 1's kinds of files, plus the (iii-b) windows), `shakedown/`, `selfcheck.py`,
`selfcheck.out`, `selfcheck-rerun-under-run1-relations.out`, `selfcheck-known-answer-on-run1-relations-{run1,amended}.out`, `refreeze-run2.txt`, `harness-sha-run2.txt`,
`clone-build-run73.txt`.

### 7.3 Readings

From `run1b-cluster/cluster/summary.txt`, `commands.log`, `readback-*.txt`, `guardrail-*-excerpt.txt`, `systemlog-flush-key1-lines.txt`; recomputed from the raw `commands.log`
and `system.log` by `selfcheck.py`. 0 connection errors and 0 retries in every phase; `client.err` empty; no automatic flush of a probe table; `app_is_superuser=False` in each arm;
`-Xms4G -Xmx4G`; read-backs `[1000, 500]`, `[10000, 5000]`, `[-1, -1]`.

| Arm (T) | Phase | Client outcome | Memtable data size before flush (B) | Disk Δ (B) | Other |
|---|---|---|---|---|---|
| A (1000) | (i) app, 200 × 1001 items | 0 accepted, 200 rejected, `… with 1001 items, this exceeds the failure threshold of 1000.` | 0 | 0 | keys 1000–1199 present: 0 |
| A | (ii) 200 appends × 1000 on key 1 | 200 accepted | 4,800,041 | 1,801,145 | card(1) = 200,000; one flush-time line naming 200000 items; flush rc 0; sstables 0 → 1 |
| A | (iii) 200 empty appends on key 2 (new) | 200 accepted | **8** | 0 | card(2) = 0; sstables unchanged |
| A | (iii-b) seed `{0}` on key 3, then 200 empty appends | seed 1 accepted; 200 accepted | M_seed **65**, M_empty **65** (Δ **0**) | 5,039 | card(3) = 1; sstables 1 → 2 (the seed) |
| A | (iv) cassandra, 200 × 1001 items | 200 accepted | 4,813,000 | 1,215,517 (0.675 × (ii)) | keys 2000–2199: 200; card(2000) = 1,001; 200 flush-time lines |
| B (10000) | (i) | 0 accepted, 200 rejected, `… with 10001 items, this exceeds the failure threshold of 10000.` | 0 | 0 | keys present: 0 |
| B | (ii) 200 appends × 10000 | 200 accepted | 48,000,041 | 18,586,170 | card(1) = 2,000,000; one flush-time line naming 2000000 items; flush rc 0; sstables 0 → 1 |
| B | (iii) | 200 accepted | **8** | 0 | card(2) = 0 |
| B | (iii-b) | seed 1; 200 accepted | M_seed **65**, M_empty **65** (Δ **0**) | 5,039 | card(3) = 1 |
| B | (iv) | 200 accepted | 48,013,000 | 12,016,563 (0.647 × (ii)) | keys present: 200; card(2000) = 10,001; 200 flush-time lines |
| R (−1, W = 1000) | (i) app, 200 × 1001 items | **200 accepted** | 4,813,000 | 1,215,523 (1.000 × (iv)) | keys present: 200 |
| R | (ii) | 200 accepted | 4,800,041 | 1,792,145 | card(1) = 200,000; no flush-time line |
| R | (iii) | 200 accepted | 8 | 0 | card(2) = 0 |
| R | (iii-b) | seed 1; 200 accepted | 65 → 65 | 5,039 | card(3) = 1 |
| R | (iv) | 200 accepted | 4,813,000 | 1,215,511 | card(2000) = 1,001; no flush-time line in any arm-R phase |

Every claim-(i)/(ii) reading repeats run 1's to the byte except the (ii)/(iv) disk deltas, which differ by 1–2,000 B (sstable metadata). Other WARN lines: start-up notices and the
`setup` step's `count(*)` aggregation warning (`error-warn.txt`), none from a probe write.

### 7.4 Cluster re-run — conclusion and logic

1. **Validity.**
   - The re-run used the re-frozen version (`8b256e69…5840`, hashed at 03:02:14, before the shakedown and the re-run) [observed: `_INDEX-advisor.md` §2; `refreeze-run2.txt`, `harness-sha-run2.txt`; `summary.txt` start 03:07:11].
   - The whole tier ran from its beginning in a fresh clone, after a shakedown that ran every step, including (iii-b) [observed: `shakedown/cluster/summary.txt`, `cluster/summary.txt`].
   - Read-backs equal the set values; `app` is not a superuser; 0 connection errors; no automatic flush; yaml as in run 1 (`yaml-diff.txt`); heap 4G. Valid [observed].
2. **Readings.** Claims (i)–(ii) repeat run 1. Phase (iii) leaves exactly 8 B in each arm, the derived new-partition charge; phase (iii-b) leaves the memtable data size unchanged (65 → 65 B) after 200 empty appends to a partition already in the memtable [observed].
3. **Matched row.** B3g row 1 (unchanged) **and** the 2026-10-28 row "(iii) and (iii-b) hold in arms A and B, and row 1 holds — the tier is Confirmed for claims (i)–(iii)" [observed; computed by `run1b-cluster/selfcheck.py`]:
   - row 1: (i) 200/200 rejected with the guardrail message and `with W+1 items`, memtable 0, disk Δ 0, keys present 0, at T = 1000 and 10000; (ii) 200/200 accepted, card 200·W exactly, Δ 1.80 MB > 1 MB and 18.6 MB > 10 MB, exactly one flush-time line naming 200·W items, flush rc 0, one new sstable; (iv) accepted, card W+1, Δ 0.675 and 0.647 × (ii); arm R accepts (i) with Δ 1.000 × (iv) and logs no flush-time line;
   - (iii) (reading iii-a): memtable **8 B = 8 B**; disk Δ 0 ≤ 1 % of (iv); card(2) = 0 — arms A and B (derived disk Δ 0 and SSTable count unchanged also hold);
   - (iii-b) (reading iii-s): seed accepted; 200/200 empty appends accepted; **M_empty − M_seed = 0**; card(3) = 1 — arms A and B.
4. **Excluded rows.** "(ii) rejections once the stored count exceeds T": 0. "(i) accepted for app": 0. "(iv) delta ~0": 1.2 and 12.0 MB. "Flush fails or aborts": rc 0 throughout. 2026-10-26 added rows: Invalid excluded (read-backs, superuser, connection errors, arm R); no partial application; both arms fit; no automatic flush. 2026-10-28 rows: (iii) ≠ 8 B — no; (iii-b) ≠ 0 — no; automatic flush or connection error in (iii)/(iii-b) — no [observed].
5. **Observed vs. inferred.** All verdict statements are observed. Inferred (explanation, not needed for any condition): that the 8 B is `SkipListMemtable.put`'s `initialSize` and the 65 B seed charge is 8 B for key 3's new partition plus the seed cell's data size; the (iii-b) Δ of 0 is the observed condition.
6. **Deviations and gaps.** None against the re-frozen runbook; no runbook defect; harness changes H1–H3 only. The amendment was written knowing run 1's readings (§7.1); the shakedown, after the re-freeze, already showed 8 B and Δ 0, and nothing was changed after it. The memtable reading is the memtable's own data-size accounting, not live heap (gap named in run 1); disk is file bytes of an uncompressed table.
7. **Core question.** As in run 1: the knob caps what one ordinary-user write adds to memtable and disk (zero for every T+1 write at both T) and the cap moves with T; it does not cap the stored collection (200·T items, 1.80 MB and 18.6 MB on disk, never refused; the flush-time check only logs); superusers and the default −1 bypass it. The empty addition at `:393` adds no item, cell, data byte or disk byte; the only charge seen is the memtable's fixed 8 B entry when the key is new to the memtable, and none when it is not.

**Conclusion (one line):** B3g row 1 and the 2026-10-28 row for (iii)/(iii-b): **confirmed for claims (i)–(iii)** — caps only on some paths (bypass).

### 7.5 Self-check of the cluster re-run — AI

`run1b-cluster/selfcheck.py` (H3) re-reads the raw `commands.log`, `system.log`, `readback-*.txt` and per-phase guardrail windows, and does not read `summary.txt`. It was written
after the re-freeze and before any re-run reading, changed twice before the shakedown (a missing phase is skipped when chaining disk deltas and does not count toward row 1;
a verdict line for "(iii-b) not run"), and not after it.
- **Pass 0 (shakedown, run end to end first):** 48 checks, 46 pass, 2 fail (C9 A/B, size-dependent absolute limits at the reduced shakedown sizes), exit status 1 as expected for those sizes ([`shakedown/selfcheck.out`](items_per_collection-doAdd-elements_size--autonomous/run1b-cluster/shakedown/selfcheck.out)).
- **Pass 1 (re-run raw files, amended relations):** **48 checks, 48 pass, 0 fail**, exit status 0; `VERDICT B3g: row 1 holds and (iii), (iii-b) hold in A and B -> Confirmed for claims (i)-(iii), caps only on some paths (bypass)` ([`selfcheck.out`](items_per_collection-doAdd-elements_size--autonomous/run1b-cluster/selfcheck.out)).
- **Pass 2 (known answer: run 1's raw files, run-1 relations):** 42 checks, 40 pass, 2 fail (C12 A/B, 8 B against 0); its PASitems_per_collection-doAdd-elements_size--autonomous/FAIL/INFO lines are **identical** to the cluster lines of `run1/selfcheck.out` (`diff` empty) ([`selfcheck-known-answer-on-run1-relations-run1.out`](items_per_collection-doAdd-elements_size--autonomous/run1b-cluster/selfcheck-known-answer-on-run1-relations-run1.out)).
- **Pass 3 (run 1's raw files, amended relations):** 48 checks, 43 pass, 5 fail — all (iii-b) "missing" (C3 × 3, C12b × 2); C12 (8 B) passes; verdict "(iii-b) has no reading -> claim (iii) not evaluable, Not confirmed" ([`…-relations-amended.out`](items_per_collection-doAdd-elements_size--autonomous/run1b-cluster/selfcheck-known-answer-on-run1-relations-amended.out)).
- **Pass 4 (information: re-run raw files, run-1 relations):** 42 checks, 40 pass, 2 fail — the frozen 2026-10-26 bound "(iii) memtable 0" fails again by the same 8 B ([`selfcheck-rerun-under-run1-relations.out`](items_per_collection-doAdd-elements_size--autonomous/run1b-cluster/selfcheck-rerun-under-run1-relations.out)).

Raw files re-opened by hand: `cluster-run2/commands.log` (`STATS B iii before-flush | … Memtable data size: 8`; `STATS B iiib seeded | … 65`, `STATS B iiib before-flush | … 65`;
`RESULT card … k=2 card=0`, `k=3 card=1`); `cluster-run2/system.log` (0 "Flushing largest"; the (iii) flush logs "Completed flushing" but no sstable is kept, SSTable count 1 → 1);
`readback-B.txt` (`[10000, 5000]`); `client.err` (empty).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | Re-frozen hash before the shakedown; read-backs, superuser flag, connection errors and automatic flushes re-read. |
| 2. Readings | yes | Every number in §7.3 recomputed from the raw files. |
| 3. Matched row | yes | Row 1 conditions pass in A, B, R; C12 and C12b pass in A and B; C18 passes. |
| 4. Excluded rows | yes | |
| 5. Observed vs. inferred | yes | The cause of the 8 B and 65 B is explanation only. |
| 6. Deviations and gaps | yes | Non-blind amendment stated; (iii-b) was the newly falsifiable part. |
| 7. Core question — logic | yes | (iii) and (iii-b) together separate the `:393` branch (adds nothing) from the memtable's per-partition entry charge. |

**Run 2?** No (2026-10-28). Claims (i)–(ii) repeat run 1 exactly, and (iii)/(iii-b) are exact, deterministic quantities matching the source to the byte; a further run would not change the row.

### 7.6 Verdict of the cluster re-run

**Confirmed for claims (i)–(iii) — caps only on some paths (bypass)** (B3g row 1 and the 2026-10-28 row "(iii) and (iii-b) hold in arms A and B"). It is filed in §8 as a new cluster row; the run-1 cluster row is kept.

**End of the re-run:** no `CassandraDaemon` process; `$W/node-ipc73` removed; `git -C $W/cassandra-run73 status` clean; no `cassandra.logdir_IS_UNDEFINED/` folder; `results/items_per_collection-doAdd-elements_size--autonomous/run1/` unchanged.

## 8. Verdict — AI

**Stage-3 estimate:** undetermined (per write yes, per stored collection no).

**Claim tested (B1):** for an ordinary authenticated user with `items_per_collection_fail_threshold = T`, (i) a single write adding more than T items to a set is rejected and adds no cells, memtable or disk usage, while a write of at most T items is accepted; (ii) repeated appends of at most T items each grow the stored set, its memtable heap and its sstable disk usage well past T items, and are never rejected; (iii) an empty addition adds nothing. "Confirmed" below means this claim held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1; claims (i), (ii), (iii)) | **caps only on some paths (bypass)** — caps the items and memtable usage of one ordinary-user write; not the stored collection; superusers bypass | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed for claims (i)–(ii)** (B3g row 1); **claim (iii) Not confirmed** (amended B3g row 3: +8 B memtable for a new empty partition; disk 0, no items) | **caps only on some paths (bypass)** — per-write memtable and disk usage capped at both T; stored collection unbounded (200·T items, 18.6 MB at T = 10000); superusers bypass; the flush-time check only logs | run 1 + self-check | 2026-10-26 |
| Cluster (re-run at `8b256e69…`, after the user-authorised B3a, B3c, B3d, B3e, B3f (iii), B3g, B3h, B4 amendment) | **Confirmed for claims (i)–(iii)** (B3g row 1 and the 2026-10-28 row "(iii) and (iii-b) hold"): claims (i)–(ii) as in run 1 (all 200 T+1 writes by `app` rejected with 0 memtable and disk usage at T = 1000 and 10000; 200 appends to 200·T items, 1.80 MB / 18.6 MB on disk, never rejected; the flush-time check only logs); (iii) empty appends on a key new to the memtable leave exactly the derived 8 B partition entry (`SkipListMemtable.java:126`), disk 0, no items; (iii-b) 200 empty appends to a partition already in the memtable change its data size by 0 (65 → 65 B). Run 1's raw files pass the amended (iii) relation but have no (iii-b) reading | **caps only on some paths (bypass)** — per-write usage capped and following T; stored collection unbounded; superusers and the default bypass; the empty addition adds nothing beyond the memtable's per-partition entry | cluster re-run (§7) + self-check | 2026-10-28 |

**Positive control:** not required (not a negative-estimate file); the design's controls moved usage as required: the superuser's T+1 writes (unit memDelta 2,465 and 24,065 B; cluster Δ 1.2 MB and 12.0 MB) and the reference arm (accepted, 1.2 MB).

**Feedback filed:** the case file's section D updated (uncommitted); amendments B2a–B2g, B2c-2, B3a–B3g, B4 in the case file (uncommitted); `_INDEX-advisor.md` §2 rows `c7e60e9c…2612` and `268a63b5…60be7`, §1 Stage 4 column filled. `HANDOFF.md` not edited (`HANDOFF-ADVISOR.md` §8).

**Feedback filed for the cluster re-run (2026-10-28):** the eight amendments `Amendment 2026-10-28 (after run 1, authorised by the user)` in the case file (B3a, B3c, B3d, B3e, B3f (iii), B3g, B3h, B4); a new `_INDEX-advisor.md` §2 row (`8b256e69…`); the case file's section D (new entry); the §1 Stage 4 column (run-1 text kept, re-run verdict appended). The coverage section is not touched. No refutation, so no other case section is amended. Run-1 observations kept: the superuser bypass and the flush-time check that only logs. Recommendation for stage 3: a "zero memtable delta" prediction for a no-op write must say whether the key is already in the current memtable — `SkipListMemtable` charges 8 B of data size for every partition new to the memtable, whatever the update holds, and every flush makes every key new again.
