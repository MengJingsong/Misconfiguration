# repair_session_space minimum-value check — verification solution  <!-- file: cases/repair_session_space-setrepairsessionspaceinmib-sizeinmib--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:4093`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4093) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (Claude Code agent), 2026-10-27 |
| Estimate | `negative`: no constraint. The check `sizeInMiB < 1` only rejects an invalid (non-positive) runtime setter argument; it caps no memory or disk object. |
| Ground | The check is a lower-bound validation on a JMX setter argument. It bounds nothing held in memory or on disk. The real memory budget (Merkle tree size) is applied elsewhere (`ValidationManager.createMerkleTrees`) and is not enforced by this comparison. |

**Type:** non-config (hard-coded constant: the numeric literal `1`; the validated value is the argument of a JMX setter that, when accepted, overwrites the yaml entry `repair_session_space` at runtime)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Compared operands: (1) `sizeInMiB`, the int parameter of `setRepairSessionSpaceInMiB` (origin: JMX argument, `ActiveRepairService.java:334`, `ActiveRepairServiceMBean.java:50`; deprecated variants at `ActiveRepairService.java:307,322`); (2) the numeric literal `1` (a literal, no named declaration; counts as a constant under the widened constant rule). The value later stored belongs to the yaml entry `repair_session_space` ([`Config.java:208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L208), `IntMebibytesBound`, default null, derived at `DatabaseDescriptor.java:609-610` as `max(1, maxMemory/(16*1048576))` MiB, i.e. 1/16 of max heap; settable in `cassandra.yaml` with restart, or via JMX at runtime). The startup twin of this check is `DatabaseDescriptor.java:612` (`toMebibytes() < 1`).

**A2. What it caps.** Nothing. If the check could bound anything, it would be the Merkle-tree heap budget of repair validation (`repair_session_space`), but the check is only a lower bound: it blocks `0` and negatives, which would otherwise yield a non-positive budget. It does not limit how large the setting, or the trees, may become. The upper-side test at line 4096 (`> maxMemory/(4*1048576)`) only logs a warning.

**A3. Mechanism.** Method `DatabaseDescriptor.setRepairSessionSpaceInMiB(int)` (`DatabaseDescriptor.java:4091-4101`). The check is [`DatabaseDescriptor.java:4093`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4093). True: throws `ConfigurationException` (4094), the setting is unchanged. False: falls to the heap-pressure warn check (4096-4098), then assigns `conf.repair_session_space` (4100). Callers: `ActiveRepairService.java:307, 322, 338` (JMX setters; line 338 converts the exception to `IllegalArgumentException`); test `ActiveRepairServiceTest.java:491-503`. The stored value is read by `ValidationManager.java:62` to compute `availableBytes`, then `estimatedMaxDepthForBytes` and `maxDepth` (lines 62-76) size the Merkle trees; that is where the memory is actually capped, and even there `Math.max(1, ...)` (line 71) floors the per-range bytes, so a value below 1 could not produce a zero budget. Bypass: none needed; the check guards only against invalid input.

**A4. Other consumers.** Merkle tree memory is also bounded by `repair_session_max_tree_depth` (`DatabaseDescriptor.java:598-606`, setter 4075-4084) and by RF (divides budget, `ValidationManager.java:62-63`). Validation compaction also uses heap for the partition iterator; not under this check.

**A5. Evidence beyond the source.** Searched: all callers of `setRepairSessionSpaceInMiB` and `getRepairSessionSpaceInMiB` (`src/java`), all uses of `repair_session_space`, `conf/cassandra.yaml:840-855` (documentation of the entry), unit test `ActiveRepairServiceTest.java:491`. Deprecation notes cite CASSANDRA-15234 and CASSANDRA-17668 (in source comments). No history or docs say this check bounds resource use.

## B. Verification solution

**B1. Claim under test.** The `sizeInMiB < 1` check does not cap memory or disk: it only rejects non-positive input, and any accepted value (1 up to Integer.MAX_VALUE) is stored without upper bound.

### B2. Unit tier

`n/a: no constraint, there is no usage-side quantity compared against a limit.` Evidence in A answers the question instead: A1 (operands are a setter argument and the literal 1), A2 (nothing bounded), A3 (outcomes: throw or store; no resource held). Optional sanity check without a build: read `ActiveRepairServiceTest.java:491-510` which asserts the setter rejects invalid values and accepts valid ones.

**B2a-B2h.** `n/a: no constraint, see B2 and A1-A3.`

### B3. Cluster tier

`n/a: no constraint, there is no memory or disk cap at this check to push to a boundary.` Evidence in A3/A2 answers the question: the only budget that takes effect is applied in `ValidationManager.java:62-76`, and it is not governed by this comparison. A cluster experiment on the validation budget would be a different case (target `ValidationManager.java:62-76`).

**B3a-B3h.** `n/a: no constraint, see B3 and A1-A3.`

**B4. Risks and cleanup.** None: nothing is built or run.

## C. Sources read

- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (lines 598-616, 4070-4110)
- `src/java/org/apache/cassandra/config/Config.java` (lines 207-208)
- `src/java/org/apache/cassandra/service/ActiveRepairService.java` (lines 295-345)
- `src/java/org/apache/cassandra/service/ActiveRepairServiceMBean.java` (grep)
- `src/java/org/apache/cassandra/repair/ValidationManager.java` (lines 52-85)
- `conf/cassandra.yaml` (grep, lines 840-855)
- `test/unit/org/apache/cassandra/service/ActiveRepairServiceTest.java` (grep)

## D. Stage-4 feedback

`none yet`
