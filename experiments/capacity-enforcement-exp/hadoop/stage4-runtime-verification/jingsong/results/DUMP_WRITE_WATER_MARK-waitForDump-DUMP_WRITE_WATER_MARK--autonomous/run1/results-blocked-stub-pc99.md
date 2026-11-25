# DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK--autonomous — stage-4 results (order 14)

> **Status:** blocked — node lock on pc99 not acquired (2026-11-25); no run started
>
> **Outcome class:** — (not run)

## Why blocked

- `/mydata/s4/NODE-LOCK` on pc99 was held by `jingsong-o70-stage4 Tue Nov 24 09:54:26 PM MST 2026`
  for the whole poll window: polled every 2 min from 05:35 to 06:35 EST 2026-11-25
  (`run1/lock-poll.log`, 31 attempts, then "BLOCKED after 60 min").
- At 03:34 MST (lock about 5.7 h old) pc99 showed no java/mvn/Cassandra process of any user and no
  `/mydata/s4/DRIVER-*.pid`, so the lock looks stale (left by an interrupted o70 session), but it is not
  this agent's lock and was not removed. Someone with authority over the o70 run should remove it.
- Nothing was started on pc99: no run folder `/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-run1`
  exists (none existed before either), no daemon, no mount, rpcbind untouched.

## Ready for the next attempt (harness/, outside the repo)

- `harness/TestDumpWaterMark.java` — unit tier B2 (cases wm256k, wm1m, wm4m, dumpDisabled, dumpDirMissing,
  concurrent4), counter M, dump length D, ALLOW_DUMP sum, DUMPED count, payload bytes still held (HB), log peak
  plus an AtomicLong-subclass peak cross-check.
- `harness/unit-run.sh` — copies the test into the per-case source copy, checks lines 73/278, runs surefire.
- `harness/cluster-run.sh` (`jars | setup | arm A|B|Aprime|C|D | teardown`), `harness/ooo_write.py`
  (B3c workload with progress lines), `harness/analyze.py`.

## Audit findings already made (to apply as dated amendments at the next attempt)

1. **B3c/B3e hold vs `nfs.stream.timeout` (runbook defect, prediction unchanged):** B3a sets
   `nfs.stream.timeout=60000` but B3c holds 120 s (A, B) / 60 s (A′, C) with no traffic. The stream monitor
   closes a context idle longer than the timeout (`OpenFileCtx.java:190-192`, `:939-956`;
   `OpenFileCtxCache.java:148-183`, scan every 5 s) and `cleanup()` fails all pending writes and deletes the
   dump file (`OpenFileCtx.java:1218-1273`), so the hole-filling write and the `(N+1) × C` HDFS length check
   would break. Fix: hold 40 s for every arm (harness already uses it).
2. **B2e dumpDirMissing "interrupt and clean up":** `waitForDump` swallows `InterruptedException` in its wait
   loop (`OpenFileCtx.java:294-299`), so interrupting cannot free the writer. Fix: reset the counter to 0 and
   `notifyAll()` under the context lock before `cleanup()` (harness does this).
3. Not a defect, noted: O_DIRECT writes answered UNSTABLE may make the kernel send COMMIT; with
   `nfs.large.file.upload` (default true) a COMMIT over a hole returns `COMMIT_SPECIAL_SUCCESS`
   (`OpenFileCtx.java:868-884`), so the client is not blocked by it.
4. Spot-checked citations hold: `OpenFileCtx.java:73, 278, 284, 294, 379, 383, 562-573`,
   `WriteManager.java:181-184`, `RpcProgramNfs3.java:200-215, 1012-1014`.

Case file unchanged: sha256 `65bb6724569d71171456407456332adca7de4a354f01d1b3964c049b0b33355d`
(commit `bef6bc8a6`); `case-amended.md` is an unmodified copy (amendments not applied because no run started).
