# Harness — repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio

Instruments for the case's §9 (stage 4), written 2026-10-15 after the step-0 audit froze §9a (`f04a15be…`). Results:
[`../../results/repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio.md`](../../results/repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio--guided.md).
Copy the folder to the node (`~/stage4-harness-run/hdr/`) and compare `md5sum` with the repository before a run. The unit tier
ran in `~/cassandra-run3`, the cluster tier from `~/cassandra-run1` (both at `b5f2a54`, `cassandra-5.0.9`), so no Ant build ran
in the clone the nodes ran from.

| File | What it is | Checked how |
|---|---|---|
| `RepairHeadroomCheckTest.java` | Unit U1 (verdict at the boundary for `r` 0.0 · 0.2 · 0.5 · 0.8, 1.0 and the default above 100 %, each `ERROR` line captured from the logger), U2 (setter / MBean range, the unvalidated raw value 1.5), U4a (`prepareForRepair` refuses and registers nothing; admits and registers). Package `org.apache.cassandra.service`; a Mockito `DiskUsageMonitor`, as upstream `ActiveRepairServiceTest`. | instrument runs (`~/stage4-logs/hdr/instrument*/`) |
| `RepairHeadroomVerbTest.java` | Unit U4b: `RepairMessageVerbHandler.doVerb` on `PREPARE_MSG` → `FAILURE_RSP` with `UNKNOWN`, failure cause, nothing registered, the dedup path; admits at the boundary. Set-up of `RepairMessageVerbHandlerOutOfRangeTest`. | same |
| `DiskUsageOperandTest.java` | Unit U3: a real `DiskUsageMonitor` on a temporary directory (rounding up, sparse apparent size, a hard link counted twice, a snapshot file, the cap removed). | same |
| `unit-run.sh [upstream\|harness\|all]` | Copies the three tests into the clone (`CASSANDRA_HOME`) and runs them plus upstream `ActiveRepairServiceTest`, `GuardrailDiskUsageTest`. | — |
| `headroom.btm` | Byteman, observation only: `HDR caller=coordinator\|participant`, `HDR usage session= usage= ratio=` (after `getDiskUsage()`), `HDR verdict session= admit=`. | `TestScript: no errors` (logged by `setup`) |
| `Jmx.java` | `get`, `setdouble`, `setstring` per JMX port, with read-back; prints `SETFAIL` and the exception chain on a refused write. | read-backs |
| `make-node-yaml.sh <N1\|N2> [k=v …]` | Per-node `conf/` under `~/stage4-hdr/<node>/` (loopback 127.0.0.2/.3, JMX 7102/7103, storage port 7010, one token each, cap `data_disk_usage_max_disk_size: 1073741824B`, `hinted_handoff_enabled: false`), adapted from `repair_session_space`. | yaml tail logged |
| `cluster-run.py <label> …` | Labels `setup`, `idle`, `sweep-p`, `sweep-k`, `types`, `valid`, `load`, `overshoot`, `down` (9e). Per trigger: ratio reset and flush on both nodes, the sparse pad (`U0 − D` by the `folderSize` walk), ratio write and read-back, `nodetool repair` with exit code, trace/log segments between byte offsets, `repair_participates`, table listings; `summary.txt`, `triggers.csv`, `samples.csv` (arm O). `HDR_RATIOS` restricts the sweep (a shakedown, not a reading). | shakedown 1 (`~/stage4-logs/hdr/shakedown1/`) |
