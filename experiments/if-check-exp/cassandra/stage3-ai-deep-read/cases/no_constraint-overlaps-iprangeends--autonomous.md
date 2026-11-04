# CIDR range overlap test (CIDR.overlaps) — verification solution  <!-- file: cases/[stem]--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | helper `CIDR.overlaps(CIDR, CIDR)`; its comparison: [`CIDR.java:268`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/CIDR.java#L268) (ordering test [`CIDR.java:261`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/CIDR.java#L261)) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: no constraint; the check is an IP-range overlap predicate that only decides which tree level a CIDR entry sits on. It caps no memory or disk. |
| Ground | The predicate affects only the placement (and thus search depth) of already-built entries; it neither rejects nor limits any entry, and the number of entries stored is the same for either outcome. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands: `lower.endIpAddress` and `higher.startIpAddress`, both `InetAddress` fields of `CIDR` ([`CIDR.java:29-31`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/CIDR.java#L29-L31) region; fields set in the constructor from `calcIpRangeOfCidr`, `CIDR.java:36-46`, derived from the CIDR's IP and netmask). The ordering test at line 261 compares `left.startIpAddress` with `right.startIpAddress`. No yaml entry, JVM property or constant takes part. Comparison is by `compareIPs` (`CIDR.java:239-252`), a byte-wise unsigned compare.

**A2. What it caps.** Nothing. The check could in principle bound a held object (the interval tree built from CIDR-group mappings), but it does not: it is a geometric predicate on two address ranges. Both outcomes keep every entry; one leaves a node in the lower level (`newLower`), the other lifts it to the upper level (`newUpper`). Total entry count is unchanged, and each node is a CIDR plus a value set, whose size does not depend on the outcome.

**A3. Mechanism.** Enclosing method: [`CIDR.overlaps`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/CIDR.java#L255-L269), lines 255-269. Lines 258-265 order the two ranges by start address (if at [`CIDR.java:261`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/CIDR.java#L261)); line [`268`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/CIDR.java#L268) returns true when lower.end >= higher.start. True means the ranges intersect; false means disjoint. No exception, no limit, no allocation.
Only call site in `src/java`: `CIDRGroupsMappingIntervalTree.IPIntervalTree.optimizeLevels`, [`CIDRGroupsMappingIntervalTree.java:380`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/auth/CIDRGroupsMappingIntervalTree.java#L380) (called from `optimizeAllLevels` :408-420, from `build` :473-478). If true, the lower-level entry stays in `newLower` (:382-385); if false it is added to `newUpper` (:391-394). Both lists are then copied back into the levels (:397-401). Purpose per the javadoc (:357-366): lift non-overlapping CIDRs closer to the root to shorten search. Test coverage: `test/unit/org/apache/cassandra/cql3/CIDRTest.java`, `test/unit/org/apache/cassandra/auth/CIDRGroupsMappingIntervalTreeTest.java` (mention `overlaps`).
Bypass or overshoot: not applicable.

**A4. Other consumers.** The tree itself (heap, one node per CIDR-group mapping) is sized by the number of CIDR groups in the `system_auth` CIDR tables, not bounded by this predicate. Transient lists in `optimizeLevels` (`new ArrayList<>(upper.size()+lower.size())`, :370-373) are sized by entry counts, independent of the overlap result.

**A5. Evidence beyond the source.** Searched `src/java` for callers of `overlaps(` (one call site), for yaml keys (`conf/cassandra.yaml`, `Config.java`) and `CassandraRelevantProperties` relating to CIDR overlap (none gate this check), and tests above. History not consulted beyond the pinned tree. No external docs relied on.

## B. Verification solution

**B1. Claim under test.** `CIDR.overlaps` does not cap memory or disk usage: it holds no limit, and the memory of the CIDR interval tree is independent of its result.

### B2. Unit tier

n/a: no constraint, there is no limit operand to drive to a boundary. The question is answered by A3: both outcomes of the check retain all entries (`newUpper` plus `newLower` equal the input in size).

**B2a-B2h.** n/a: no constraint, see A1-A3 for the evidence that answers the question instead.

### B3. Cluster tier

n/a: no constraint, no limit exists whose boundary a node could be pushed to; A2 shows the stored object count is the same under either outcome.

**B3a-B3h.** n/a: no constraint, see A2/A3.

**B4. Risks and cleanup.** None; nothing is run.

## C. Sources read

- src/java/org/apache/cassandra/cql3/CIDR.java
- src/java/org/apache/cassandra/auth/CIDRGroupsMappingIntervalTree.java
- (grep only) test/unit/org/apache/cassandra/cql3/CIDRTest.java, test/unit/org/apache/cassandra/auth/CIDRGroupsMappingIntervalTreeTest.java

## D. Stage-4 feedback

`none yet`
