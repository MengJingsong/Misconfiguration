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

**Superseded 2026-10-27 by Amendments U1-U7 below (the tier is run).** Original text: `n/a: no constraint, there is no usage-side quantity compared against a limit.` Evidence in A answers the question instead: A1 (operands are a setter argument and the literal 1), A2 (nothing bounded), A3 (outcomes: throw or store; no resource held). Optional sanity check without a build: read `ActiveRepairServiceTest.java:491-510` which asserts the setter rejects invalid values and accepts valid ones.

**B2a-B2h (original).** `n/a: no constraint, see B2 and A1-A3.` Superseded by the amendments that follow.

> **Amendment U1 (2026-10-27, stage-4 audit), why the tier is run.** The claim in B1 has two parts that a program can test: the setter rejects only values below 1, and every accepted value up to `Integer.MAX_VALUE` is stored. A negative claim also needs a positive control (README, group A), and one exists on the same knob and the same code path: the closed case `repair_session_space-split-maxsize--guided` (both tiers Confirmed) shows that the stored value sets the Merkle-tree size of a real validation, with its harness. So the unit tier is run, with that harness reused for the control.
>
> **Amendment U2 (B2a, B2b).** JDK 11, local clone `~/cassandra-run4` built with `ant build-test`; the harness tests are copied into `test/unit/org/apache/cassandra/repair/` and run with `ant testsome -Dtest.name=<class>`: the new `SessionSpaceSetterTest` (S1-S3, harness folder), the closed `RepairSessionSpaceTreeTest` (positive control, 78 checks; its depth table is also the input of the cluster prediction) and upstream `ActiveRepairServiceTest` (known answer for the setter). Knob = the setter argument `v` of `DatabaseDescriptor.setRepairSessionSpaceInMiB`: rejected set {0, -1, `Integer.MIN_VALUE`}; accepted set {1, 2, 4, 128, T, T+1, 2048, `Integer.MAX_VALUE`}, with T = `maxMemory / 4 MiB` (the heap-pressure warning threshold, `DatabaseDescriptor.java:4096`). Control knob: the stored value s = 1, 2, 4 passed through a real `ValidationManager.submitValidation` on a table of 2^14 partitions (RF 1, Murmur3 test partitioner, `evenTreeDistribution = true`).
>
> **Amendment U3 (B2c, B2d, B2e).** S1: for each `v`, call the setter after storing 7; record the exception type and message, the getter, the thread-allocated bytes of the call (`ThreadMXBean`), and the MBean wrapper `ActiveRepairService.setRepairSessionSpaceInMiB(v)` (must turn the exception into `IllegalArgumentException`, `ActiveRepairService.java:334-345`). S2: with an accepted value stored, run the real validation and count the leaves of the returned tree by walking it (not the `size` field); the formula of `ValidationManager.java:62-79` is recomputed in the test with the same 32-bit arithmetic. A rejected value after a stored 2 must leave the next tree at 2's size. S3: write the raw field `DatabaseDescriptor.getRawConfig().repair_session_space` to 0, -1, -1000 (what the yaml loader does, no setter, no check: the world without the check) and validate. Real resource: heap bytes of the tree are read through leaves (80 B shallow per leaf and 200 to 208 B per leaf-plus-inner in the closed tier's table); the gap to whole-JVM heap is named, since the tier is in-process.
>
> **Amendment U4 (B2f, predictions, stated before any run, from the source).** S1: `v` in {0, -1, MIN} throw `ConfigurationException("Cannot set repair_session_space to <v> < 1 mebibyte")`, the getter keeps 7, the MBean wrapper throws `IllegalArgumentException`; every accepted `v` is stored exactly (`getRepairSessionSpaceInMiB() == v`, including `Integer.MAX_VALUE`; there is no upper clamp). The allocation of a call does not grow with `v` (a few KiB at most, rejected calls included). S2: s = 1, 2, 4 give 4096, 8192, 16384 leaves (init path, depth `min(ceil(log2 n) = 15, d(s))`, d = 12, 13, 14); a rejected 0 or -1 after a stored 2 gives 8192 again; 1024 and 2047 give 32768 (= 2^15, bound by the partition term); 2048 and `Integer.MAX_VALUE` give 2 leaves, because `DatabaseDescriptor.getRepairSessionSpaceInMiB() * 1048576` overflows `int` at `ValidationManager.java:62` (-2^31 and -2^20; the budget becomes `max(1, ...)` bytes). S3: raw 0, -1, -1000 give 2 leaves, not more than at s = 1 (4096).
>
> **Amendment U5 (B2g rows added).** Added to the table: (a) "A rejected value changes the getter or the next tree" is **Refuted**; (b) "An accepted value is clamped or rejected above some bound (getter differs from `v`)" is **Refuted** (claim: stored without upper bound); (c) "A raw 0 / -1 / -1000 tree is larger than the s = 1 tree" is **Refuted** (the check would then be what bounds usage); (d) "Leaves do not move with s = 1, 2, 4" is **Not confirmed** (the control did not move); (e) "Leaves differ from the 32-bit formula" is **Not confirmed** (re-trace).
>
> **Amendment U6 (B2h controls).** Positive control: S2 (the stored value moves the tree size ×2 per ×2) and the closed `RepairSessionSpaceTreeTest` re-run unchanged. Known answers: upstream `ActiveRepairServiceTest` and the closed test's own mismatch count (must be 0).
>
> **Amendment U7 (verdict wording).** Confirmed (unit) means: S1 and S3 as predicted, S2's control moved, no row (a) to (e) fired. Effect on the constraint: **does not cap**; the downstream formula is the cap, and large accepted values shrink the tree (overflow), which is outside this claim and recorded.

### B3. Cluster tier

**Superseded 2026-10-27 by Amendments C1-C6 below (the tier is run).** Original text: `n/a: no constraint, there is no memory or disk cap at this check to push to a boundary.` Evidence in A3/A2 answers the question: the only budget that takes effect is applied in `ValidationManager.java:62-76`, and it is not governed by this comparison. A cluster experiment on the validation budget would be a different case (target `ValidationManager.java:62-76`).

**B3a-B3h (original).** `n/a: no constraint, see B3 and A1-A3.` Superseded by the amendments that follow.

> **Amendment C1 (2026-10-27, stage-4 audit).** Why the tier is run: the live JMX setter is the only runtime route to the check (the yaml value goes through the twin check at line 612), and the closed case's two-node ring already measures what a stored value does to a real repair on a real node. A negative claim needs that control (A group). The tier is the closed ring with a new label, `m-range`, added.
>
> **Amendment C2 (B3a, B3b, B3c).** Two nodes on `pc32`, loopback 127.0.0.2/.3, JMX 7102/7103, RF 2, Murmur3, one token each, `MAX_HEAP_SIZE=2G`, Byteman split trace and hold rules from the closed harness, node data on local `/` (never `/proj`), clone `~/cassandra-run1`. Load: `cassandra-stress write n=1048576` (2^20 rows) at `cl=ALL`, flush, autocompaction disabled; each reading is one `nodetool repair -full -pr keyspace1 standard1` from node 1. The knob is the MBean attribute `RepairSessionSpaceInMiB` (`org.apache.cassandra.db:type=RepairService`), set on both nodes and read back. Positive-control sweep (closed label `m-a`): 1, 4, 16, 64 MiB. Range arm (`m-range`): accept 4 (repair, then a repair with N2 held for the heap histogram), reject 0 and -5 (each followed by a repair), accept `2147483647` (repair), accept 1 (repair), reset to 128.
>
> **Amendment C3 (B3d, B3e).** Observables per repair on each node: `Created <n> merkle trees ...` and `Prepared AEService trees of size <L>` in `debug.log`, the Byteman `split calls=` line, the off-heap `Allocating direct buffer of size` lines (coordinator), and under the hold N2's `OnHeapLeaf` / `OnHeapInner` instance counts from `jmap -histo:live`. The JMX write result (`SETFAIL ...` chain or read-back) is logged for every attempt. Predictions come from the unit tier's depth table (`ValidationManager.java:62-79`), recomputed by the script, which prints an `EXPECTED:` line per reading.
>
> **Amendment C4 (B3f, predictions, from the source).** Sweep: L = 2^min(ceil(log2 n), d(s/RF), 20): 2048, 8192, 32768, 131072 at 1, 4, 16, 64 MiB; heap: `OnHeapLeaf` +L and `OnHeapInner` +(L-1) on N2 under the hold; off-heap: two buffers of 82 L + 32 bytes on the coordinator. Range arm: setting 0 and -5 through JMX fails with `IllegalArgumentException: Cannot set repair_session_space to <v> < 1 mebibyte` on both nodes, the read-back stays 4, and the next repair has L = 8192 (the same as before the attempt); `2147483647` is accepted (read-back 2147483647, a heap-pressure WARN on each node) and the repair has L = 2 (32-bit overflow: -1048576 / RF 2 gives a 1-byte budget); setting 1 again gives L = 2048. Memory-side: no node's idle heap changes because of a rejected write (not measured separately; a rejected call stores nothing, S1).
>
> **Amendment C5 (B3g, conclusions table).** Rows: (1) all of C4 holds, sweep L moves with s: **Confirmed - does not cap** (the check is a lower bound on a setter argument; the stored value is the downstream cap). (2) A rejected write changes the read-back or the next repair's L: **Refuted**. (3) The write of `2147483647` is refused or clamped: **Refuted**. (4) The sweep L does not move with s, or the hold does not start (instrument silent): **Not confirmed** / **Invalid**. (5) L of the range arm differs from the formula for another reason: **Not confirmed** (re-trace). (6) The accepted `2147483647` yields a larger tree than s = 4: **Refuted** and a finding for stage 3.
>
> **Amendment C6 (B3h controls, cleanup).** Control: the closed `m-control` (default 128) and `m-a` readings in the same run; both nodes read the same L at every setting; one repair at a time. Stop both nodes with the label `down` and check `ps -eo cmd | grep '[C]assandraDaemon'` on the node.
>
> **Amendment C7 (2026-10-27, before any cluster reading; the unit tier had already run).** A source fact the audit missed, found when the unit tier's setter call crashed: `DatabaseDescriptor.setRepairSessionSpaceInMiB` ends in `new DataStorageSpec.IntMebibytesBound(sizeInMiB)` (`DatabaseDescriptor.java:4100`), whose constructor accepts at most 2147483646 and no negative value (`DataStorageSpec.java:108-111`). So `2147483647` passes the `< 1` check and is then refused by the type bound with `IllegalArgumentException: Invalid data storage: 2147483647 mebibytes. It shouldn't be more than 2147483646 in mebibytes`, and the stored value stays as it was. The unit tier's U4 and its row (b) were frozen before this was known and are **not** edited (the unit result records the miss). For the cluster tier, this is a fact of the source, not of any cluster reading, and is applied before its run 1: in C2/C4 the large accepted value is **2147483646** (the largest storable; 32-bit product -2097152, divided by RF 2 gives -1048576, a 1-byte budget, so L = 2), and **2147483647 is attempted first and must fail** with the text above, the read-back staying 4. Row (3) of C5 is read as: \"the write of 2147483646 is refused or clamped: Refuted\"; a new row (7): \"the write of 2147483647 is accepted by JMX: Refuted (the traced setter differs from the source)\".

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
