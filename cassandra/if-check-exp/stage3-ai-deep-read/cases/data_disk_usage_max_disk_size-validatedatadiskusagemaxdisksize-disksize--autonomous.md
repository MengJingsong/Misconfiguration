# data_disk_usage_max_disk_size validation (disk size vs. configured max) — verification solution  <!-- file: cases/data_disk_usage_max_disk_size-validatedatadiskusagemaxdisksize-disksize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`GuardrailsOptions.java:1257`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/GuardrailsOptions.java#L1257) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative` (no constraint): the check only validates a setting value against the physical disk size; it caps no memory or disk object. |
| Ground | The if rejects a too-large `data_disk_usage_max_disk_size` at startup or JMX set. It is input validation; no data, memtable or file is bounded by it. |

**Type:** non-config (runtime-queried). The compared `diskSize` comes from `FileStore.getTotalSpace()` (runtime); the other operand is the yaml entry `data_disk_usage_max_disk_size`. No declared constant or numeric literal takes part in the comparison (the `0` check is in the separate `validateSize` call, line 1201, not in this if).

## A. Constraint trace

**A1. The constraint.** `no constraint` (as a resource cap). Compared operands:
- `diskSize`: `long diskSize = DiskUsageMonitor.totalDiskSpace();` (GuardrailsOptions.java:1255). Origin: [`DiskUsageMonitor.totalDiskSpace()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L221), which sums `FileStore.getTotalSpace()` (via `totalSpace`, DiskUsageMonitor.java:~243) over the file stores of all data directories, capped at `Long.MAX_VALUE`. Runtime-queried, bytes.
- `maxDiskSize.toBytes()`: parameter of `validateDataDiskUsageMaxDiskSize` (GuardrailsOptions.java:1248), the yaml entry / JMX value [`data_disk_usage_max_disk_size`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L928) (`LongBytesBound`, default `null` = disabled; yaml example at conf/cassandra.yaml:2210; settable in yaml, or at runtime via JMX `setDataDiskUsageMaxDiskSize`, Guardrails.java:1211).

**A2. What it caps.** Nothing held. The check validates that the configured "pretend disk size" is not larger than the real total disk space. The setting itself is later used only as the denominator in the disk-usage-percentage guardrail (`total.min(maxDiskSize)`, DiskUsageMonitor.java:157-159); that guardrail blocks writes by percentage and is a different check. This if bounds no memory or disk object.

**A3. Mechanism.** Enclosing method `GuardrailsOptions.validateDataDiskUsageMaxDiskSize` (GuardrailsOptions.java:1248). Returns early on null (1250), rejects zero via `validateSize` (1253), then at [`GuardrailsOptions.java:1257`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/GuardrailsOptions.java#L1257) `if (diskSize < maxDiskSize.toBytes())`:
- true: throws `IllegalArgumentException` ("specified, but only %s are actually available on disk", 1258-1260); the value is not applied.
- false: method returns; the value is accepted.
Callers: constructor-time validation `GuardrailsOptions.java:87` (startup, from `config.data_disk_usage_max_disk_size`) and setter `GuardrailsOptions.java:762` (`setDataDiskUsageMaxDiskSize`, reached from JMX at Guardrails.java:1211). No bypass besides null (disabled).

**A4. Other consumers.** The accepted value is read at DiskUsageMonitor.java:157 to limit the denominator of the data-disk-usage ratio; nothing else. The real disk is consumed by sstables, commitlog, etc., independent of this check.

**A5. Evidence beyond the source.** Searched `totalDiskSpace` (only call is GuardrailsOptions.java:1255), `data_disk_usage_max_disk_size` (Config.java, GuardrailsOptions, Guardrails, GuardrailsMBean, DiskUsageMonitor, both yaml files), and the yaml comment "Valid values are in [1, max available disk size of all data directories]" (conf/cassandra.yaml:2208) which confirms this is a validity range. No tests, docs or history consulted beyond that.

## B. Verification solution

**B1. Claim under test.** This check does not cap memory or disk usage: it only rejects settings larger than the physical total disk size, and no resource is bounded by it.

### B2. Unit tier
n/a: no constraint, there is no usage-side value to drive to a limit. The question is answered by A3 (both outcomes only throw or return) and A2 (the setting is used solely as a percentage denominator elsewhere). Alternative sanity check: call `GuardrailsOptions.validateDataDiskUsageMaxDiskSize` (private; via `setDataDiskUsageMaxDiskSize`) with a value above and below `DiskUsageMonitor.totalDiskSpace()` and expect throw vs. accept, with no allocation or file written.

### B3. Cluster tier
n/a: no constraint, there is no resource to measure. A3/A2 show the only effect is accept or reject of the setting; if run, setting a too-large value via JMX would return an error and leave data and disk usage unchanged.

**B4. Risks and cleanup.** None; nothing is run.

## C. Sources read
- src/java/org/apache/cassandra/config/GuardrailsOptions.java (lines 80-90, 755-767, 1196-1262)
- src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java (lines 140-260)
- src/java/org/apache/cassandra/config/Config.java (line 928)
- src/java/org/apache/cassandra/db/guardrails/Guardrails.java (1205-1213)
- conf/cassandra.yaml (2195-2215)

## D. Stage-4 feedback
`none yet`
