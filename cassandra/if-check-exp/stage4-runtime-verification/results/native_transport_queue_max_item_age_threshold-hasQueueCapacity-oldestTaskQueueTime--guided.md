# native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided — stage-4 results  <!-- file: results/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.md; the stem ends in --guided or --autonomous -->
> **Case:** [`native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided`](../../stage3-ai-deep-read/cases/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.md)
>
> **Status:** **Closed 2026-10-20 — Refuted (unit and cluster) — caps in throwing mode, only slows growth in default mode.** Estimate negative (left as filed); run 1 on `pc13`, self-check 84/84, no run 2.
>
> **Agent:** guided (the suffix of the case-file stem). One results file per case file.

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
| **Case-file version** | Guided file, hash of §9's text after the audit's amendments (`sed -n '/^## 9\. /,/^## 10\. /p' <file> | git hash-object --stdin`): `dcad2ce895b243c8d9efb09f392df461e142dc89`, computed 2026-10-20 before any harness or run. §9a is frozen at this version, including the dated block 9f. Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`). |
| **Harness** | `harness/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided/` — written 2026-10-20 in step 1 (R5): `nqa.btm` (R2 stall + `chk` observation), `NqaHold.java`, `QueueAgeWriter.java` (replaces `fixed_rate_writer.py`), `NqaQueueAgeTest.java`, `unit-run.sh`, `cluster-run.py`, `make-node-yaml.sh`, `Jmx.java`, `client-logback.xml`, `README.md`. Instrument check and shakedowns in §2. |
| **Tiers and values** | Unit (9a step 1): `Dispatcher` over a held executor, `hasQueueCapacity()` at thresholds above, at and below the head's age. Cluster (9e): one node, `native_transport_max_threads` 4, Byteman stall, 100 × 64 KiB requests/s for 60 s, threshold off · 0.5 · 0.1 · 0.02 (throwing mode; one repeat in default mode at 0.1), positive control with in-flight limit 8 MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | 9a Claim, 9d: off-heap request bytes queued. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 9b values off (`Double.MAX_VALUE`), 0.5, 0.1, 0.02 (× the 12 s `native_transport_timeout`). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | The queued-bytes gauge was written as `type=Client,…`. **Amended** (R1): `type=Client,name=RequestsSize` plus the pool `Size` gauge. |
| A. Core question | usage driven to the limit and past it | Met | 375 MiB offered per run (100/s × 64 KiB × 60 s) against ceilings of 1.5 MiB (0.02) to 37.5 MiB (0.5) in throwing mode; the control budget (8 MiB) is far below the offer. |
| B. Logic | each step says what it establishes | Met | 9a block matches steps, prediction and rows. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | "Same at every threshold" had no numeric edge. **Amended** (R4). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Rows: same + control caps (Confirmed), falls with the threshold (Refuted), falls only in throwing mode (Refuted for that mode), never grows with the check off (Invalid), control does not cap (Not confirmed). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs equal peaks across thresholds, refusals in the log/client error (queue-time text) and the control capping. |
| B. Logic | alternative explanations and their controls | Met | Control: in-flight budget on the same workload; the age-check-off baseline; both overload modes. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | Intro explains the time check vs the byte budget and the mode split. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | The stall rule and the mode setting were not exact. **Amended** (R2, R3). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Rate, duration, thread count, client timeout exact; stall and mode fixed by R2, R3; `fixed_rate_writer.py` named, not written. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | `fixed_rate_writer.py` and the Byteman stall rule are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 375 MiB per run on a node with 251 GiB RAM and 47 GB disk; 60 s × 8 runs. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `Dispatcher.java:341-348` (`hasQueueCapacity`), `SEPExecutor.java:88-100` (`oldestTaskQueueTime` reads the queue head only), `CQLMessageHandler.java:208,237,585,618`, `PreV5Handlers.java:165,201`, `Config.java:1393-1399`, `StorageService.java:7638`, `ClientMetrics.java:129`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Queued bytes gauge = `type=Client,name=RequestsSize` + networking pool `Size` | Applied 2026-10-20 (9d, 9f) | the filed name was a placeholder |
| R2 | Byteman stall at `Dispatcher$RequestProcessor.run` until a flag file; four workers stalled, the rest queue; write and check in step 1 | Applied 2026-10-20 (9b, 9c, 9f) | `oldestTaskQueueTime` reads only queued tasks, so the stall must hold running workers |
| R3 | Mode via `native_transport_throw_on_overload` in the yaml (connection default) | Applied 2026-10-20 (9b, 9f) | `PipelineConfigurator.java:309-313` uses it when the STARTUP option is absent |
| R4 | Numeric edges: noise band = range of three check-off repeats; "falls" = > 50 % below and > 3× the band | Applied 2026-10-20 (9a, 9f) | fixed before any reading |
| R5 | Write `fixed_rate_writer.py` and the stall rule | step 1 (harness) | prerequisites, not design changes |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's runbook observables:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-20, 21:19–21:54 MDT (instrument check and shakedowns 21:19–21:31; run 1 unit 21:32–21:33, cluster 21:33–21:52) | not done |
| Node (CloudLab name and type) | `pc13` = `node3.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB), driven over ssh from a session on `pc07`; this run's node alone | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), built and `build-test` done before this session | |
| Case-file commit / harness commit | case file `cd7fec5`, §9 hash `dcad2ce8…` re-verified after run 1 (unchanged); harness not committed (no commit requested); node copy `~/stage4-harness-run/nqa/` equal by `md5sum` to the repo folder before run 1 (`~/stage4-harness-run/nqa.run1.md5`; the md5 prefixes are also in both `summary.txt`) | |
| Storage for node data | `pc13` local disk `/dev/sda3` (ext3, 55 GB free): node `~/stage4-nqa/{conf,data,logs}`; nothing on `/proj` | |
| Full logs (path, outside the repo) | `pc13:~/stage4-logs/nqa/` — `run1/unit/`, `run1/cluster/<label>/` (`client.txt` with one `r` line per request, `nqa.trace`, `poll.csv`, histograms, `system.log`), `run1/selfcheck.txt`; shakedowns `shakedown1`–`3/`, `instrument/`; 15 MB in all | |

Node JVM (shipped `cassandra-env.sh`, unchanged): `-Xms31744M -Xmx31744M`, G1. The client JVM: `-Xmx3g`, the module options of
`conf/jvm11-clients.options`. Node open-file limit 100,000 (checked in `/proc/<pid>/limits` at every start).

**Instrument check (step 1, not readings).** `TestScript`: 2 rules parsed and type-checked, no errors. Unit shakedown
(`shakedown1/unit`): 36/36 checks, the stall held 24 requests and released 24. Cluster shakedown 1 (10 s sends; `off1`,
`t0.1`, `d0.1`, `ctl`): every set-up check held; it showed the networking pool flat at 8 MiB with `UsedSize` 0 in every arm
— the decoded request's value is copied to the heap and the frame buffer is returned, so the pool cannot see the queued
bytes. The harness then added (before run 1, no §9 change) a class histogram at the idle control and at the peak (live
`byte[]` and total live bytes, the real resource) and the direct-buffer pool to the poll. Shakedown 2 (20 s; `off1`,
`t0.02`) found the histogram's `[B` row is printed as `[B (java.base@11.0.32.1)` on JDK 11 (parser fixed); shakedown 3 (5 s,
`off1`) confirmed it (byte[] +33.9 MB for 500 × 65.6 KB). The 12 s `native_transport_timeout` is kept as 9b fixes it (the
threshold is a fraction of it); it cannot cut the hold, which sits at `RequestProcessor.run` entry before the timeout test
(`Dispatcher.java:364-369`), so the held requests return "Query timed out before it could start" after the release and
after every reading.

## 3. Runbook defects

None. Two observable gaps, recorded as deviations (§4.2 part 6), not defects: 9d's "log line from `logOverload`" is a
`TRACE` line (`CQLMessageHandler.java:320-328`) and never appears at the default level, so the disallow evidence is the
client's error, `RequestDiscarded` and the `chk` trace; R1's pool `Size` is flat (above), so the real resource is read from
the heap histograms instead, in addition to R1's `RequestsSize`.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| — | — | — | none | — | — | — |

## 4. Run 1

**Scope:** unit tier (9a step 1, steps u0–u5) and cluster tier (9e: idle control in every lifetime; A = `off1`–`off3`;
B = `t0.5`, `t0.1`, `t0.02` throwing, `d0.1` default mode; C = `ctl`), one node lifetime per label, run order `off1 t0.5
t0.1 t0.02 off2 d0.1 ctl off3`. **Command log:** `[stem]/run1/cluster/summary.txt`, `run1/unit/summary.txt`
(full `session.log` on the node).

### 4.1 Readings

*M* (bytes per request counted against the in-flight limits) = 65,605 B in the unit tier (`BytesReceived` − 9) and
65,592 B on the node (`BytesReceived`/request − 9); the per-connection receive queue capacity is the default 1 MiB, so
`RequestsSize` (the global reserve) = queued bytes − 1 MiB once a connection holds more than 1 MiB.

**Unit tier** (`run1/unit/test.out`, `summary.txt`; 36/36 checks, `ant` 1/1 tests)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| u0: 4 requests held running, none queued | `ActiveTasks` 4, `PendingTasks` 0, `oldestTaskQueueTime()` 0, `hasQueueCapacity()` **true at a 12 ns limit** (running tasks are not the operand, R2) | `unit/test.out` |
| u1: one queued, head age 601.8 ms | threshold 0, −1, `Double.MAX_VALUE` → true; limit age + 2 s → true; limit = an age read just before (607,992,025 ns, one ulp under) → **false** (strict `<`); limit age − 300 ms → false; pending 1 and `RequestsSize` 0 unchanged by the calls; with a second, newer request queued the age is still the head's (≥ 601.8 ms) | `unit/test.out` |
| u2: throwing connection, limit 100 ms under the head's age | refused: `OverloadedException` "Request has spent over 0.0444 time of the maximum timeout 12000ms in the queue"; `RequestDiscarded` +1; pending 2 and `RequestsSize` unchanged; at threshold off the next request is queued (3) | `unit/test.out` |
| u3: default-mode connection, same limit | queued anyway (pending 3 → 4), no response before the release, `ConnectionPaused` +1; after the release it ran with the "spent over" client warning | `unit/test.out` |
| u4: 50 req/s × 4 s, workers stalled, throwing | admitted (queued + running) / queued bytes / peak `RequestsSize` / refused: **off 200 / 13,121,000 / 12,069,824 / 0; 0.2 (2.4 s) 125 / 8,200,625 / 7,216,016 / 75; 0.05 (0.6 s) 35 / 2,296,175 / 1,312,736 / 165; 0.01 (0.12 s) 11 / 721,655 / 0 / 189** — admitted = 5 + 50 × limit exactly at every value | `unit/test.out` (`STAGE4 arm`) |
| u5: control, threshold off, global limit 2 MiB | admitted 47, `RequestsSize` peak 2,034,248 ≤ 2,097,152, 153 refused "bytes in flight" | `unit/test.out` |
| trace | 24 `hold in` = 24 `hold out`; 875 `chk` lines, every verdict = (age < timeout × threshold) away from a 20 ms edge | `selfcheck.txt` |

**Cluster tier** — one row per value; 6,000 requests sent in 59.99 s in every arm, every request answered, the stall held
exactly 4 running requests in every arm (`hold in` = 4, `ActiveTasks` 4), idle control clean (`RequestsSize` 0,
`PendingTasks` 0, no hold line) and every hold-fixed value read back over JMX in every lifetime (threshold, mode, 12,000 ms
timeout, in-flight 1 GiB / 8 MiB, per IP 1 GiB, request pool `MaxPoolSize` 4). Peak = the 2 s poll's maximum or the
sample at `sendend` + 2 s, whichever is larger; histograms at `sendend` + 2 s minus the idle control's.

| Capacity value | Run | Peak `RequestsSize` (R1) | Admitted (queued + running) × *M* | Live `byte[]` rise (heap) | Refused (client) = `RequestDiscarded` = `chk` false | First refusal after the first queued request | Evidence (file) |
|---|---|---|---|---|---|---|---|
| off | A `off1` | 392,503,424 | 6,000 → 393,552,086 | 394,928,064 | 0 / 0 / 0 | — | `cluster/off1/`, `arms.csv` |
| off | A `off2` | 392,503,424 | 6,000 → 393,552,086 | 394,945,392 | 0 | — | `cluster/off2/` |
| off | A `off3` | 392,503,424 | 6,000 → 393,552,086 | 394,925,088 | 0 | — | `cluster/off3/` |
| 0.5 (6 s) | B `t0.5` | 38,634,584 (9.84 %) | 605 → 39,683,168 | 40,804,856 (10.33 %) | 5,395 (queue-age text) | 6,011 ms | `cluster/t0.5/` |
| 0.1 (1.2 s) | B `t0.1` | 7,150,424 (1.82 %) | 125 → 8,199,001 | 9,316,264 (2.36 %) | 5,875 | 1,211 ms | `cluster/t0.1/` |
| 0.02 (0.24 s) | B `t0.02` | 853,592 (0.22 %) | 29 → 1,902,168 | 2,997,464 (0.76 %) | 5,971 | 251 ms | `cluster/t0.02/` |
| 0.1, default mode | B `d0.1` | 33,321,632 (8.49 %), **still rising** at +1.97 MB per 6 s (5 requests/s) at the end of the send | 524 at the peak → 34,370,215 | 35,598,096 (9.01 %) | 0 refused; `ConnectionPaused` 399, `chk` false 402; 60 responses warned | 1,211 ms (first false) | `cluster/d0.1/poll.csv` |
| off, in-flight 8 MiB | C `ctl` | 8,331,080 (≤ 8,388,608) | 143 → 9,379,658 | 10,478,208 (2.65 %) | 5,857 "bytes in flight" | — | `cluster/ctl/` |

Also: the check-off band (R4: range of three repeats) is **0 B** on `RequestsSize` and 20,304 B on the `byte[]` rise; the
`RequestsSize` series rose monotonically through every check-off arm (33 samples) to 6,000 × *M* − 1 MiB exactly; live
`ExecuteMessage` = admitted in every throwing arm; the networking pool `Size` stayed 8,388,608 with `UsedSize` and
`OverflowSize` 0 in every arm; the direct-buffer pool stayed at 58.6–59.5 MB. Each queued request held 65,821 B of
`byte[]` (394.93 MB / 6,000), *M* + 229 B. The source's throwing-mode estimate 5 + rate × limit (4 running, the first
queued, then everything that arrives before the head ages out) is met exactly: 605, 125, 29 (unit: 125, 35, 11).

### 4.2 Conclusion and logic

1. **Validity** — valid. The workers were stalled (4 `hold in` lines and `ActiveTasks` 4 in every arm
   **[observed: `cluster/*/final.json`, `trace-head.txt`]**); with the check off queued bytes grew for the whole run to
   374.3 MiB, the offered load (9f R4's expectation "near 375 MiB") **[observed: `cluster/off1/poll.csv`, `selfcheck.txt`]**;
   every 9b hold-fixed value was read back over JMX in every lifetime **[observed: `cluster/summary.txt` JMX read-back
   lines]**; 100 req/s for 59.99 s and every response received within the 180 s wait **[observed: `client-excerpt.txt`,
   `selfcheck.txt`]**. The limits were reached: refusals began within 11 ms after each limit **[observed: `arms.csv`
   `first_false_after_first_queued_ms`]**.
2. **Readings** — nothing contradicts. The R1 pool `Size` gauge never moved (8 MiB, `UsedSize` 0): the bytes are not in
   the pool but in the heap (`byte[]` rise = admitted × 65,821 B) **[observed: histograms; inferred: the decode copies the
   value (CBUtil) and the frame is released, consistent with every arm]**. `RequestsSize` is the global reserve only, i.e.
   1 MiB under the queued bytes (it reads 0 in unit u4 at 0.01, with 0.72 MB queued) **[observed: `unit/test.out` u4;
   `AbstractMessageHandler.java:419-439`]**.
3. **Matched row** — "Peak queued bytes fall as the threshold falls, near `rate × size × timeout × threshold`" →
   **Refuted**. Peak `RequestsSize` at 0.02 is 0.22 % of the check-off peak (> 50 % below, and > 3 × the 0 B band below);
   at 0.5 / 0.1 / 0.02 the queued bytes are 39.7 / 8.2 / 1.9 MB against `rate × size × timeout × thr` = 39.4 / 7.9 / 1.6 MB
   (+5 requests: the four running and the head) **[observed: `arms.csv`, `selfcheck.txt`]**. Disallow evidence:
   5,395 / 5,875 / 5,971 queue-age `OverloadedException`s = `RequestDiscarded` = `chk ret=false` **[observed]**.
4. **Excluded rows** — *Confirmed* (same across thresholds, control caps): the peaks are 9.84 / 1.82 / 0.22 % of the
   check-off peak, none within the band. *Refuted for throwing mode only*: the default-mode arm also fell, to 8.49 % at
   the end of the 60 s send — but it was not capped: it grew linearly at 5 requests/s (the 200 ms maximum back-off,
   `QueueBackpressure.java`, `Config.java:1396`) to the end **[observed: `cluster/d0.1/poll.csv`]**, so default mode
   slows the queue's growth about 20× rather than bounding it; the row's own wording (throwing falls, default does not)
   does not fit either. *Invalid* (no growth with the check off): excluded by part 1. *Not confirmed* (control does not
   cap): the control capped `RequestsSize` at 8,331,080 ≤ 8 MiB with 5,857 byte-budget refusals.
5. **Observed vs. inferred** — the conclusion rests on observed counts and gauges. Inferred: that the heap `byte[]` rise is
   the queued requests' values (supported by its exact proportionality to admitted count, 65,821 B each, and the live
   `ExecuteMessage` count) and the default-mode reading that growth continues past 60 s (inferred from the constant slope
   over the last 50 s).
6. **Deviations and gaps** — R1's pool `Size` cannot see the queued bytes (it is flat); the real resource was read from
   heap histograms added before run 1 (§2). The `logOverload` line is `TRACE` (not observable at the default level);
   the other three disallow observables were used. The default mode was run at one value only (as 9e says), so its
   "slope" is a time slope, not a threshold slope. The node heap was the shipped default (31 GiB); 9b does not fix it.
7. **Core question** — Usage follows the constraint: in throwing mode the queue-age threshold caps queued request bytes
   at about `(rate × timeout × threshold + 5) × M` (parts 3, 1), the same workload uncapped reaches the whole offered
   load (part 1), and the byte-budget control moves the same reading (part 4). So the time check bounds memory
   indirectly, through the arrival rate; in default mode it only slows growth (part 4). The rejection's claim "does not
   bound queued memory" is refuted for throwing mode.

**Conclusion (one line):** §9a row 2 "Peak queued bytes fall as the threshold falls, near `rate × size × timeout ×
threshold`" — **refuted** (unit and cluster); default mode slows but does not cap.

## 5. Self-check of run 1 — AI

Independent script `run1/selfcheck.py` (re-parses `test.out`, the traces, every `client.txt` `r` line, `poll.csv`,
`final.json` and the histograms; compares `arms.csv`; evaluates R4 itself): **84 ok / 0 FAIL** (`run1/selfcheck.txt`).

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read each label's `final.json` (active 4), traces (4 `hold in`), JMX read-back lines, check-off `poll.csv` (monotone, 33 samples, end 392,503,424 = 6,000 × 65,592 − 1,048,576 + 0) |
| 2. Readings | yes | Pool `Size` 8,388,608 in every `poll.csv` row; histograms: `[B` idle 16.2 MB, peaks per arm as tabled |
| 3. Matched row | yes | `selfcheck.txt`: R4 "falls" true, "same" false on `RequestsSize`, `byte[]` and total live bytes alike; refusals = discards = false `chk`s in all three throwing threshold arms; first refusal 6,011 / 1,211 / 251 ms |
| 4. Excluded rows | yes | `d0.1/poll.csv` re-read: +1,967,760 B per 6 s for the last 50 s, `ConnectionPaused` 399, 0 refusals; `ctl` 8,331,080 ≤ 8,388,608 |
| 5. Observed vs. inferred | yes | The heap attribution holds by count (`ExecuteMessage` = admitted in each throwing arm) and size (*M* + 229 B each); the d0.1 extrapolation is labelled inferred and is not needed for the throwing-mode verdict |
| 6. Deviations and gaps | yes | None changes the row: the frozen R1 gauge alone gives the same R4 outcome |
| 7. Core question | yes | Logic steps (1)–(4) of 9a: (1) growth with the check off; (2) peaks per threshold; (3) control caps; (4) peaks fall → the Refuted row |

### 5.2 Run 2?

**No** — decided 2026-10-20. The result refutes the case, which the README names as a reason to consider run 2, but the
refutation rests on observed, exact counts (refusals = discards = `chk` false; admitted = 5 + rate × limit to the request
at three values and three unit values; band 0), the stage-3 source reading predicted exactly this outcome (§10 Notes),
and the unit and cluster tiers agree independently. Nothing in §5.1 depends on an inference.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative (Rule 2: time-based check).

**Claim tested:** "the queue-age threshold does not bound the memory held by queued requests: with workers stalled, peak
queued request bytes are the same at every threshold value." "Confirmed" below would mean this claim held.

| Tier | Verdict (§9a row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Refuted** (row 2) — queued bytes 13.1 / 8.2 / 2.3 / 0.72 MB at off / 0.2 / 0.05 / 0.01; admitted = 5 + 50 × limit exactly; `hasQueueCapacity` strict `<` on the head's age only | caps (throwing mode; the unit sweep ran throwing mode only, u3 shows default mode queues past the limit) | run 1 + self-check | 2026-10-20 |
| Cluster | **Refuted** (row 2) — peak `RequestsSize` 392.5 MB (band 0) off vs 38.6 / 7.15 / 0.85 MB at 0.5 / 0.1 / 0.02; heap `byte[]` 394.9 vs 40.8 / 9.3 / 3.0 MB; default mode at 0.1: 33.3 MB after 60 s and still rising at 5 req/s | caps only on some paths (bypass): caps in throwing mode at ≈ (rate × timeout × threshold + 5) × *M*; default (non-throwing, the shipped default) mode only slows growth to 1 request per maximum back-off | run 1 + self-check | 2026-10-20 |

**Positive control:** threshold off, `native_transport_max_request_data_in_flight` 8 MiB, same workload and instruments:
`RequestsSize` stopped at 8,331,080 B (≤ 8,388,608), heap `byte[]` +10.5 MB against +394.9 MB uncapped, 5,857
"bytes in flight" refusals (unit: 2 MiB limit, 2,034,248 B).

**Feedback filed:** the case file's §10 "Stage-4 feedback" field updated 2026-10-20 (not committed; no commit was
requested): Refuted in throwing mode at both tiers, the default-mode result, R1's pool gauge cannot see the bytes (heap
`byte[]` instead), `RequestsSize` excludes the 1 MiB per-connection capacity, `logOverload` is TRACE. The Estimate line is
left as filed (README "A refuted negative estimate is not re-estimated").
