# dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous — stage-4 results (run 1 not started)

> **Case:** stage-3 queue order 22, Jingsong's share (Hadoop). **Status: blocked 2026-11-25** — no reading exists.
> **Outcome class:** none yet (estimate `positive`; stage 4 has not run).

## Why blocked

Assigned node `pc99`. The node lock `/mydata/s4/NODE-LOCK` was held by `jingsong-o70-stage4` (owner file dated
Tue Nov 24 09:54:26 PM MST 2026). Polled every 2 min from 2026-11-25 06:58 to 07:59 EST (31 polls, `lockpoll.log`); still held,
so the run returned blocked as instructed. The lock looks stale: at 04:58 MST (node time) no Java or Maven process ran on
`pc99`, and no `o70` output existed on the session node. It was not removed (not this agent's lock). The owner of that
lock (or the parent session) should confirm it is stale and remove it before a retry.

Nothing was done on `pc99`: no source copy, no apt install, no daemon, no run folder; `/mydata/jingsong-s4/` holds only the
base build and an older folder of another case (`dfs.client.write.byte-array-manager...-run1`, 2026-11-23, untouched).
No process was started on the node or left on the session node.

## Ready for a retry (prepared, not yet run)

- **Audit** done against the pinned source (repository HEAD `cd9e1cded`, `systems/hadoop/source` clean): bottom line
  **Ready after amendments**; ratings in `audit-draft.md`.
- **Amended case file** `case-amended.md`: section D1 with amendments A1–A8 dated 2026-11-25, made before any harness run or
  reading, inline markers in B2a, B2d–B2g, B3a, B3d–B3g. sha256 as received
  `d8dac2b8e896a77973e6920b28c0bb9b93106783d43f8b86286b0164b632fd9e`; after amendments
  `634aa45bccf4daac6e7ec3f072a911297a92a1f6cec1dcf368a2f1f1fd583076` (frozen version). Text `**B2f.` up to `### B3.`:
  `4d4d636f…af945`; text `**B3f.` up to `**B4.`: `77ff10bc…cd73ab` (sha256).
- **Harness** `harness/` (not run, not compiled): `TestCrmPendingFit.java` (Test A ×3, Test B ×6 U + 3 C', Test C on
  U = 49152; line-534 DEBUG capture), `unit-run.sh compile|test|ablate`, `cluster-run.sh deps|setup|run|stop`
  (apt deps, native `hadoop-common`, phase 1 M = 0/64m/128m/256m/1g, phase 2 M = 128m with 60-s cache reports),
  `sampler.py`, `selfcheck.py`. Copy to the node (home is not shared with `pc99`), e.g.
  `/mydata/jingsong-s4/<stem>-run1/harness/`. Instrument checks (compile, known-answer) are still to do.
