# MAX_KEY_SIZE-write-limit-2--autonomous — stage-4 results (queue order 6)

> **Status:** **blocked, 2026-11-25** — node lock on `pc99` held the whole 60-minute wait, so nothing ran. No reading
> exists. The audit and freeze (§1) and the harness are ready for the next attempt.
>
> **Outcome class:** none yet (stage-3 estimate `negative`; stage 4 not run).

## 0. Why blocked

- `/mydata/s4/NODE-LOCK/owner` on `pc99` reads `jingsong-o70-stage4 Tue Nov 24 09:54:26 PM MST 2026`. It was polled every
  2 minutes from 04:02 to 05:02 EST on 2026-11-25 (31 attempts, `harness/acquire-lock.log`) and never freed.
- The lock looks stale. It is about 7 hours old. `pc99` had no Java, Maven or Hadoop process (checked at 04:02, about
  04:20 and 05:03 EST), no `/mydata/s4/DRIVER-*.pid`, and no file under `/mydata` changed in the 30 minutes before
  04:20. This agent did not remove the lock because its task does not allow that. Whoever owns the run of order 70
  (or the parent session) should confirm that the lock is stale and run `ssh pc99 'rm -rf /mydata/s4/NODE-LOCK'`.
- What this agent left on `pc99`: nothing. It never got the lock, created no run folder (there is no
  `/mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-2-run1`) and started no process. Its only process on this machine was
  the poll loop, which has exited.

## 1. Before run 1: design audit and freeze (done 2026-11-25, before any reading)

| Field | Content |
|---|---|
| Case file | `hadoop/stage3-ai-deep-read/jingsong/cases/MAX_KEY_SIZE-write-limit-2--autonomous.md`, last commit `bef6bc8a6`, repository HEAD `cd9e1cded`. The sha256 at filing, `8f77da5c…0597649`, matches `_INDEX.md` §4. |
| Amended (frozen) version | `case-amended.md` in this folder, with amendments A1–A8 (section D1). Whole-file sha256 **`2da7b37fa94ee5cb51263a2cb21037b22c01c7f03cb481ed8a66923feff37db3`**. Text hashes (sha256 of the `sed -n` ranges): `**B2f.`–`**B2h.` `99017a03…e8433910`; `**B3f.`–`**B3h.` (with A8) `b13ee3e9…8202334`. |
| Harness | `harness/`: `TestBoundedLimitMemory.java` (md5 `bbd0f97b`, U1–U5 plus the instrument line), `unit-run.sh` (`ca0965a5`), `cluster-run.sh` (`35994760`: B3 with A5–A7, `--daemon` start and stop, the EXIT trap stops everything), `selfcheck.py` (`70120f3d`: checks the raw output against B2f/A3/A4 and B3f/A8), `acquire-lock.sh`. None has been compiled or run yet. The instrument check (`unit-run.sh <run> --compile-only`) is the first step of run 1. On the node, copy `harness/` to `<run-dir>/harness/` (the home directory is not shared with `pc99`). |
| Tiers and values | Unit: U1 `limit` 1024/32768/65536 at capacity 64 KiB; U2 `limit` 1 KiB/512 KiB/1 MiB at capacity 1 MiB; U3 capacity 64 KiB/1 MiB/16 MiB; U3b `ByteArrayOutputStream` with 200 writes of 1 KiB; U4 the TFile key through `prepareAppendKey(-1)` and `(65537)`; U5 TFile files of 1/10/100 records with 64 KiB keys. Cluster: DistributedShell stdout N = 1/16/64 MiB (×2 containers), with aggregated logs in TFile; a positive control with a 32 MiB HDFS space quota (after clearing `/tmp/logs/$USER`, A7); workload B, wordcount with memory-to-memory merge. |
| Audit bottom line | **Ready after amendments**, 2026-11-25 |

### 1.1 Audit (groups A–D)

| Group | Rating | Note |
|---|---|---|
| A: core question | Met | The quantity is heap bytes of the stream (thread-allocated bytes) and disk bytes (TFile length, aggregated HDFS bytes). `MAX_KEY_SIZE` is a compile-time constant (`TFile.java:155`), so the unit tier varies the stream's own `limit` (three values, including 65536) and capacity. The cluster tier varies the data volume past the limit (up to 2048×). Positive controls: U3/U3b, and the HDFS quota. |
| B: logic | Partly → Met | The predictions are numeric. The U5 prediction was arithmetically wrong (A3), some B2g rows were missing (A4), and "linear" and "caps" for B3g had no numbers (A8). |
| C: specific | Partly → Met | Paths, the `install` build and surefire options did not fit the node (A1); U4 had no warm-up (A2); the cluster start, the DS command quoting and the aggregated-log path were not exact (A5, A6). |
| D: runnable | Partly → Met | Spot-checked against `systems/hadoop/source` (clean): `BoundedByteArrayOutputStream.java:56, 91-92, 103-114`; `TFile.java:155, 289-290, 393-400, 418-472, 504, 527-536, 653-666, 2272-2313`; `BCFile.java:119-137` (no downstream buffer, so each 64 KiB record closes a block); `LogAggregationUtils.java:160-165`; `AggregatedLogFormat.java:150, 505-541`; `MergeManagerImpl.java:202, 221-229, 341-342, 405-428`; DS `Client.java` options; `hadoop-project/pom.xml:39, 187, 2469`. As cited, except A3 (the index holds each block's last key) and the bucket path (A6). The control needed A7: without it the quota would be exceeded before the control app wrote anything. |

Recommendations applied as amendments A1–A8 (see `case-amended.md`, section D1). None was left for stage 3.

## 2–8. Run, self-check and verdict

Not done (blocked). Next attempt: get the `pc99` lock (or another node's), then
`copy-source.sh /mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-2-run1/src`, copy `harness/` there and run
`unit-run.sh <run> --compile-only`, `unit-run.sh <run>` and `cluster-run.sh <run>` (each logs under `<run>/logs/`).
Then run `python3 -I selfcheck.py <run>/logs`, delete the bulk data (`src/`, `hadoop/`, `nn`, `dn`, `nm-*`, `tmp`, `in`),
keep `logs/` and release the lock.
