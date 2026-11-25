# maxSSTableSizeInMiB-SSTableSimpleUnsortedWriter-maxSStableSizeInBytes--autonomous — stage-4 results (o116)

> **Status:** BLOCKED 2026-11-25. Not run: the node lock on `pc99` was held the whole time.
> **Outcome class:** none (no stage-4 run)

## What happened
- Node `pc99` (`node4.jason92-326665`, x86_64, 32 cores, 125 GiB, 695 GB free on `/mydata`, JDK 11.0.33, Ant 1.10.12,
  built `/mydata/s4/cassandra-base` present). There was no `/mydata/jingsong-cass-s4/o116` partial folder on this node, so nothing needed cleaning.
- `/mydata/s4/NODE-LOCK` was held by `jingsong-o70-stage4 Tue Nov 24 09:54:26 PM MST 2026`. Polled every 2 min from
  00:48:45 to 01:49:00 EST (31 attempts, `run1/logs/lock.log`); timed out after 60 min. Throughout the wait no `java`
  or other user process ran on `pc99` (checked 00:48, 01:05 and 01:49 EST), so the lock may be stale (an interrupted o70 session).
  It was left untouched: it is not this session's lock.
- Nothing was started on the node, and nothing was written there.

## Prepared, ready for the next attempt (outside the repo)
- Design audit done. Filed sha256 `1299399d…173b` (equal to `_INDEX.md` §4; case commit `bef6bc8a6`, repo HEAD `cd9e1cded`).
  Amendments S4-A1 to S4-A3, dated 2026-11-25 and added before any reading, are in `case-amended.md` section D
  (sha256 `ffdeccf5…ee30`): (a) paths; (b) a probe sync-detection fix so Ubig's 5 hand-offs are visible;
  (c) quarter-point heap samples so the Uinf control is observable; (d) safety steps for starting the node; plus verdict
  labels for B2g and B3g. B1, B2f and B3f are unchanged. Audit bottom line: Ready after amendments.
- Harness in `harness/`: `MaxSSTableSizeProbeTest.java` (B2a plus S4-A1(b)(c); `.filed.java` is the verbatim copy), `BulkProbe.java`
  (B3a, verbatim), `setup.sh`, `unit-all.sh` (B2e), `cluster-all.sh` (B3e + B4 stop), `analyze.py` (S4-A2/A3 criteria),
  `acquire-lock.sh`, `md5.txt`, `freeze.sha256`, `freeze-pred.txt`. `setup.sh` expects the harness copied to `/tmp/o116-harness/` on the node.
  None of these has been run on a node yet; the instrument check is still to do.
