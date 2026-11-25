#!/usr/bin/env python3
"""Insert the stage-4 audit amendments S1-S6 and the B5 note (2026-11-25, before any reading) into case-amended.md.
Each block is inserted just before the line that starts with the given anchor (first match), i.e. at the end of the
section it amends. Run once."""
import sys

P = sys.argv[1]
text = open(P).read()

AM = {}

AM["S1"] = ("**B2b. Knobs.**", """
> **Amendment S1 (stage 4, 2026-11-25, before any reading) — unit environment on `pc82`, pmem emulation.**
> The node has no persistent memory and no PMDK, and the base build has no `libhadoop` (`NativeIO.isAvailable()` false),
> so `MappableBlockLoaderFactory.java:46-49` picks the pure-Java `PmemMappableBlockLoader`. As in Hadoop's own
> `TestCacheByPmemMappableBlockLoader`, the pmem volumes are ordinary directories on local disk (`/mydata`, ext4) under
> MiniDFSCluster's base directory, and the per-volume cap is set with `PmemVolumeManager.setMaxBytes(M)`. The test prints
> `NativeIO.isAvailable()`, `isPmdkAvailable()` and the DataNode's loader class (`FsDatasetCache.cacheLoader` by reflection);
> any loader other than `PmemMappableBlockLoader` makes the U3 rows invalid. Copy and run (replaces the `rsync`/`-am install`
> of B2a; the node's `~/.m2` holds every 3.4.2 artifact): `copy-source.sh /mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-reserve-maxBytes-run1/src`,
> test class in the package `org.apache.hadoop.hdfs.server.datanode.fsdataset.impl`, `mvn -B -pl hadoop-hdfs-project/hadoop-hdfs
> test -Dtest=TestPmemCapacityCap -DfailIfNoTests=false -Dmaven.javadoc.skip=true`, JDK 8. The tests print readings and
> make no assertion on B2f (readings are compared in the results file); surefire counts, not the exit code, say whether they ran.
""")

AM["S2"] = ("**B2c. Workload.**", """
> **Amendment S2 (stage 4, 2026-11-25, before any reading) — a third cap value.** B2b has two values of `M`; a third,
> `M = 32768` (8 blocks of 4 KiB), is added to U1 and U3 so the cap takes three values (32768, 65536, 131072) besides the
> default path (`-1` → `getUsableSpace()`, U2). U1 at `M = 32768`: `r_1..r_8 = 4096 … 32768`, `r_9..r_12 = -1`, used 32768,
> map size 8; after the release used 28672 and the next reserve returns 32768; reflective `reserve(1)` → `-1`, used stays
> 32768. U3 at `M = 32768`: `/f1` (16 blocks) is itself past the cap: 8 blocks cached, `CacheUsed = 32768 = CacheCapacity`,
> on-disk sum 32768 at every sample; (a) `/f2` directive: still 8 cached; (b) direct `cache()` of `/f2`: 4 refusal lines,
> `CacheUsed` 32768, on-disk 32768, no `/f2` file. Order of U3 runs: 32768, 65536, 131072 (control).
""")

AM["S3"] = ("**B2h. Controls.**", """
> **Amendment S3 (stage 4, 2026-11-25, before any reading) — observables, settle rules and rows added to B2d/B2f/B2g.**
> 1. *Which check refused.* `PmemVolumeManager.reserve` (manager level, U1 and U3) gets `-1` from `chooseVolume`
>    (`:407`, `:414-416`, WARN "There is no enough persistent memory space") before `UsedBytesCount.reserve` (`:77`) runs;
>    only the reflective call reaches `:77` with the volume full. The test counts those WARN lines with a `LogCapturer` on
>    `PmemVolumeManager`: predicted one per refused manager-level reserve (4 per `M` in U1, 4 per `M` ≤ 65536 in U3 (b)).
> 2. *NameNode gate.* `CacheReplicationMonitor` is set to TRACE in U3; the test counts "is not a valid possibility because
>    the block has size" lines (`CacheReplicationMonitor.java:745-752`) after the `/f1` settle and during (a). Predicted > 0
>    in (a) for `M` ≤ 65536 (and during `/f1` for `M = 32768`).
> 3. *U3 (b) counter.* `NumBlocksFailedToCache` also counts a repeat cache command for a block already in the map
>    (`FsDatasetCache.java:276-281`), as order 23's run showed. The decisive (b) reading is the number of DataNode
>    "could not reserve more bytes" lines naming a `/f2` block id (predicted 4 for `M` ≤ 65536); the counter delta,
>    measured from just before the call, is predicted ≥ 4, and a delta above 4 with exactly 4 refusal lines reads as B2f.
> 4. *U3 control (b).* At `M = 131072`, (a) caches `/f2`, so the direct call repeats commands for cached blocks:
>    predicted 0 refusal lines, counter +4 (duplicates), `CacheUsed` stays 81920.
> 5. *Settle rules.* `/f1`: poll every 500 ms until `NumBlocksCached` equals the predicted count (8/16/16) or 30 s, then
>    5 s more; (a) 10 s; (b) 5 s; teardown waits for `CacheUsed = 0` (max 30 s). The on-disk sum (regular files under
>    `PMEMx/hdfs_pmem_cache`) and `CacheUsed` are sampled every 500 ms through all waits; the maxima are reported.
> 6. *Rows added to B2g* (same meaning column):
>
> | Observation | Meaning |
> |---|---|
> | U1: manager-level `-1` with the matching "no enough persistent memory space" WARNs | Refusal at the volume choice (`:407`), which applies `:77`'s inequality; with the reflective row it shows `:77`'s own branch also refuses. |
> | U3 (b) at `M` ≤ 65536: 4 refusal lines naming `/f2` ids, counter delta > 4 | Extra delta = duplicate commands (`:276-281`); reads as the B2f row. |
> | U3 (a): 0 NN reject lines and `/f2` not cached at `M` ≤ 65536 | NameNode gate not seen at TRACE; the DataNode gate is still tested by (b); not a refutation. |
> | U3 control (b): refusal lines > 0, or `/f2` not cached in (a) | Something other than the cap refuses; control fails; the `M` ≤ 65536 U3 rows are inconclusive (Not confirmed). |
> | Loader is not `PmemMappableBlockLoader` | Invalid run (wrong path). |
""")

AM["S4"] = ("**B3b. Knobs.**", """
> **Amendment S4 (stage 4, 2026-11-25, before any reading) — cluster environment on `pc82`, pmem emulation.**
> No real persistent memory on the node: the pmem directory is a size-limited tmpfs, as B3a designs (Hadoop's own pmem
> tests use plain directories through the same pure-Java mapped-file loader). No build: the distribution is a copy of the
> node's base build (`cp -a /mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2 <run>/hadoop`); it has no
> `libhadoop`, so the pure-Java loader is used; check the DataNode log for "Initializing cache loader:
> …PmemMappableBlockLoader" (or "MemoryMappableBlockLoader" in run D) and "Starting DataNode with maxLockedMemory = 0".
> `<run>` = `/mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-reserve-maxBytes-run1/cluster`. Daemons start and stop with
> `hdfs --daemon` (no SSH to localhost on the node; not `start-dfs.sh`). `JAVA_HOME` = JDK 8. The NameNode's
> `log4j.properties` gets `log4j.logger.org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor=TRACE` so the
> NameNode gate's reject line is countable. Daemon log timestamps are the node's local time (MST).
""")

AM["S5"] = ("**B3c. Workload.**", """
> **Amendment S5 (stage 4, 2026-11-25, before any reading) — a third tmpfs size.** Run **A0**, `S = 128m`, is added before
> run A (same steps 4–7), so the pmem file system takes three sizes (128, 256, 512 MiB) besides the default (run D, key
> unset). Run order: A0, A, B, C, D.
""")

AM["S6"] = ("**B3h. Controls.**", """
> **Amendment S6 (stage 4, 2026-11-25, before any reading) — predictions in terms of the logged cap, exact byte measure,
> ENOSPC forms, settle and stop rules.**
> 1. *Block counts.* On tmpfs a directory holds no data pages, so the usable space at DataNode start can equal `S` exactly
>    (B3f assumed "a few KiB less", giving 7 and 15). The predicted cached count for runs A0/A/B is **N = floor(X/33554432)**,
>    `X` from "Added persistent memory - … with size=X": N = 4/8/16 if X = S, and 3/7/15 if X is below S by less than one
>    block. `CacheUsed = BYTES_CACHED = N·33554432`; cache bytes ≤ X at every sample and = N·33554432 at the end; N rises
>    with S (B/A ratio N_B/N_A). The claim-wrong conditions of B3f are unchanged (more than floor(X/32 MiB) blocks,
>    `CacheUsed` or cache bytes > X, B not above A).
> 2. *Cache bytes.* "Cache bytes" = the sum of regular-file sizes under the pmem mount (`find <pmem0> -type f -printf '%s\\n'`),
>    since `du --apparent-size` also counts directory entries; `du -sb --apparent-size`, `df -B1` Used and the file count are
>    sampled too (every 2 s, B3d).
> 3. *ENOSPC forms.* `PmemMappableBlockLoader.load:97` ignores the count `FileChannel.transferTo` returns; on JDK 8 a copy
>    that runs out of space can come back short instead of throwing, and then `verifyChecksum` fails with "checksum
>    verification failed: premature EOF" (`MappableBlockLoader.java:157`) or a checksum error. Any DataNode "Failed to cache"
>    WARN whose cause is "No space left on device", "premature EOF" or a checksum failure, while `df` Used is at the tmpfs
>    size, counts as ENOSPC evidence (B3d's `grep -c "No space left"` is kept and these are counted beside it); the B3g
>    row "C: `CacheCapacity ≈ 2X` and ENOSPC failures" is read with these forms.
> 4. *Run C bound.* At most floor(df size / 33554432) = 8 complete cache files fit; with 4 caching threads per volume
>    (default) concurrent copies can all fail at the boundary, so run C may end with fewer than 8 cached. The double-count
>    row is read from `CacheCapacity ≈ 2X` (two "Added persistent memory" lines) plus ENOSPC-form failures, not from a count.
> 5. *NameNode gate.* NameNode TRACE reject lines are counted per run; predicted > 0 in A0, A, B and D (demand above
>    capacity) and in C if the NameNode schedules up to 2X.
> 6. *Settle and stop.* Each run samples 90 s after its directive (as B3c) and records the last sample; step 7 waits until
>    `CacheUsed = 0` and no regular file is left under the pmem mount, at most 120 s (not reaching it is recorded).
> 7. *Rows added to B3g:*
>
> | Observation | Meaning |
> |---|---|
> | A0/A/B: fewer than floor(X/B) blocks cached, no ENOSPC-form failure, no reserve refusal | Caching did not complete within the window; that run is not settled (Not confirmed for the tier unless the other runs settle the staircase and this one only lags). |
> | A0/A/B: counts = floor(X/B) and cache bytes ≤ X, but ENOSPC-form failures appear | As the "`No space left` in A" row: reservations allowed more than the file system held. |
> | C: CacheCapacity ≈ 2X but no failure of any kind and ≤ 8 blocks cached | The NameNode did not schedule past the physical space (e.g. demand reached first); double count shown on capacity only; bypass not exercised (Partly). |
""")

AM["S8"] = ("## C. Sources read", """**B5. Stage-4 audit amendments (2026-11-25).** S1–S6 above were added by the stage-4 audit before any reading
(results file `results/dfs.datanode.pmem.cache.dirs-reserve-maxBytes--autonomous.md` §1). They add a third cap value at each tier, name the
node environment and pmem emulation, count the checks' own log lines, and restate the cluster block counts as
`floor(X/B)`; B1's claim and the claim-wrong conditions of B2f/B3f are unchanged.

""")

order = ["S1", "S2", "S3", "S4", "S5", "S6"]
for k in order:
    anchor, block = AM[k]
    i = text.find("\n" + anchor)
    assert i >= 0, k
    text = text[:i] + "\n" + block.rstrip("\n") + "\n" + text[i:]
anchor, block = AM["S8"]
i = text.find("\n" + anchor)
assert i >= 0
text = text[:i + 1] + block + text[i + 1:]
open(P, "w").write(text)
print("applied", order + ["S8"])
