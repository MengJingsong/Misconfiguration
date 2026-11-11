# Stage 2 — Hadoop calibration anchors

The fixed rows repeated in every Hadoop stage-2 batch (playbook, "Anchor every batch"). **All
18 must come back band A.** If any does not, re-run that batch.

> **Row 9 is retired from the gate (2026-11-04).** In the stage-2 run, `FSDirectory.java:1272#1`
> (`length > maxComponentLength`) came back B from 3 of the 6 agents that saw it, each in all 7 of
> its batches. A row that readers split on cannot calibrate, so batches are recorded with
> `record-stage2-bands.py --exempt=<its uid>`. Its source read below is unchanged, it stays in the
> batches (so batch contents do not move), and it is in `bands.csv` as A with the other anchors.
> Pick a replacement before any future re-banding. Run record: [`README.md`](README.md).

Cassandra's anchors were rows that already had stage-3 verdicts. Hadoop had none, so these
were picked on 2026-11-04 by reading the source at each row against Rules 1–3 (method README
§3.4–§3.6). These are **anchor-level reads, not stage-3 case files**: each one checks the limit,
the gated allocation and the decision point, but none has a §9 test design, and none is in a
stage-3 `_INDEX.md`. When stage 3 reaches one of these rows it writes the case file as usual and
may refine what is noted here.

Source: `systems/hadoop/source/` @ `rel/release-3.4.2`. `uid` is `path:line#n` exactly as
`make-stage2-batches.py` builds it (n = 1-based index among comparisons on that line, in CSV
order). All 18 are in `NarrowedIfStatements.csv`, all magnitude class.

## Selection

- **Strong anchors only.** Every row below has a limit that bounds memory or disk bytes, an
  allocation it gates, and a disallow branch that visibly withholds, reroutes or stalls that
  allocation.
- **Spread.** 9 HDFS (NameNode, DataNode, client), 4 common (IPC, IO, local FS), 4 MapReduce,
  1 YARN. YARN is thin because most YARN limits are container resources (CPU, vcores, container
  memory on other hosts) rather than bytes held by the process that does the check.
- **Covering the row shapes stage 2 will see:** limit on the left (rows 11, 12); a usage side
  that renders as `... + ...` (row 11); a method-call limit (`getCacheCapacity()`,
  `getInodeXAttrsLimit()`, `getXattrMaxSize()`); a limit passed in as a parameter (row 4); a
  hardcoded-looking constant that is actually configured (row 3); and `>=` as well as `>`.
- **Neighbours on the same line are not anchors.** `Client.java:1937#1` (`maxResponseLength > 0`),
  `WritableUtils.java:489#1` (`length < 0`) and `PacketReceiver.java:166#2` (`totalLen < 0`) are
  the disable/sanity halves of the same conditions. Stage 2 bands them on their own merits.

## The anchors

| # | uid (path under `<module>/src/main/java/org/apache/hadoop/`) | Row text | Limit (config key) | Gated allocation and disallow effect | Pattern |
|---|---|---|---|---|---|
| 1 | `hadoop-common-project/hadoop-common` :: `ipc/Server.java:2452#1` | `dataLength > maxDataLength` | `ipc.maximum.data.length` | `checkDataLength` throws before `ByteBuffer.allocate(dataLength)` at `:2544` (RPC request buffer) | (c) |
| 2 | `hadoop-common-project/hadoop-common` :: `ipc/Client.java:1937#2` | `length > maxResponseLength` | `ipc.maximum.response.length` | throws before `ByteBuffer.allocate(length)` at `:1941` (RPC response buffer); a limit ≤ 0 disables it (`#1`) | (c) |
| 3 | `hadoop-hdfs-project/hadoop-hdfs-client` :: `hdfs/protocol/datatransfer/PacketReceiver.java:166#1` | `totalLen > MAX_PACKET_SIZE` | `dfs.data.transfer.max.packet.size` (read into a static at `:82`) | throws before `reallocPacketBuf(...)` at `:173` (packet buffer) | (c) |
| 4 | `hadoop-common-project/hadoop-common` :: `io/WritableUtils.java:489#2` | `length > maxLength` | parameter; the one in-scope caller passes `ShuffleHeader.MAX_ID_LENGTH` = 1000 | throws before `new byte[length]` at `:494` | (c) |
| 5 | `hadoop-hdfs-project/hadoop-hdfs` :: `hdfs/server/namenode/FSEditLogOp.java:5248#1` | `opLength > maxOpSize` | `dfs.namenode.max.op.size` (`FSImage.java:724`) | throws before the op is buffered (`in.mark(maxOpSize)`) and decoded; the comment says it exists to prevent OOM on NameNode/JournalNode | (c) |
| 6 | `hadoop-hdfs-project/hadoop-hdfs` :: `hdfs/server/namenode/FSDirWriteFileOp.java:183#1` | `length >= maxBlocksPerFile` | `dfs.namenode.fs-limits.max-blocks-per-file` | `validateAddBlock` throws, so no new block is allocated; disk bytes per file ≤ count × the file's preferred block size, plus a NameNode `BlockInfo` per block | (c) |
| 7 | `hadoop-hdfs-project/hadoop-hdfs` :: `hdfs/server/namenode/FSDirXAttrOp.java:383#1` | `userVisibleXAttrsNum > getInodeXAttrsLimit()` | `dfs.namenode.fs-limits.max-xattrs-per-inode` | throws before the new xattr list is stored on the inode (held in NameNode heap and logged to edits) | (c) |
| 8 | `hadoop-hdfs-project/hadoop-hdfs` :: `hdfs/server/namenode/FSDirXAttrOp.java:440#1` | `size > getXattrMaxSize()` | `dfs.namenode.fs-limits.max-xattr-size` | throws, so the xattr is never stored; with row 7, bytes per inode ≤ count × size | (c) |
| 9 | `hadoop-hdfs-project/hadoop-hdfs` :: `hdfs/server/namenode/FSDirectory.java:1272#1` | `length > maxComponentLength` | `dfs.namenode.fs-limits.max-component-length` (0 disables, `:1267`) | throws before the inode with that name is added. Escape hatch: logs instead of throwing while edits replay (`isImageLoaded()` false) | (c) |
| 10 | `hadoop-hdfs-project/hadoop-hdfs` :: `hdfs/server/namenode/FSDirectory.java:1293#1` | `count >= maxDirItems` | `dfs.namenode.fs-limits.max-directory-items` | throws before a child inode is added to the directory. Same edit-replay escape hatch as row 9 | (c) |
| 11 | `hadoop-hdfs-project/hadoop-hdfs` :: `hdfs/server/datanode/fsdataset/RoundRobinVolumeChoosingPolicy.java:111#1` | `availableVolumeSize > ... + ...` | runtime free space (`getAvailable()`, net of `dfs.datanode.du.reserved`), plus `...additional-available-space` | a volume is chosen for the new replica only if it has room; if every volume fails, `DiskOutOfSpaceException`. **Limit on the left**, the Hadoop counterpart of Cassandra's compaction disk anchor | (a) |
| 12 | `hadoop-common-project/hadoop-common` :: `fs/LocalDirAllocator.java:531#1` | `capacity > size` | runtime free space of each local dir | the file is created in that dir only if it has room; otherwise try the next dir, then `DiskErrorException`. Limit on the left (`capacity`). Not `:528#1` (`capacity > maxCapacity`), which only tracks the best dir for the error message | (a) |
| 13 | `hadoop-hdfs-project/hadoop-hdfs` :: `hdfs/server/datanode/fsdataset/impl/CacheStats.java:100#1` | `next > getCacheCapacity()` | `dfs.datanode.max.locked.memory` | `reserve` returns −1, and `FsDatasetCache.CachingTask.run` (`:415–420`) returns without mmap/mlock-ing the block | (b) |
| 14 | `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core` :: `mapreduce/task/reduce/MergeManagerImpl.java:292#1` | `usedMemory > memoryLimit` | `mapreduce.reduce.shuffle.input.buffer.percent` × heap (or `mapreduce.reduce.memory.totalbytes`) | `reserve` returns null and the fetcher stalls; otherwise an in-memory map output is reserved. By design one fetcher can overshoot (`:279–290`) | (a)/(b) |
| 15 | `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core` :: `mapreduce/task/reduce/MergeManagerImpl.java:268#1` | `requestedSize > maxSingleShuffleLimit` | `mapreduce.reduce.shuffle.memory.limit.percent` × `memoryLimit` | a map output that is too large goes to an `OnDiskMapOutput` instead of a heap buffer: the memory allocation is withheld and rerouted to disk | (a) |
| 16 | `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core` :: `mapred/MapTask.java:1698#1` | `totalIndexCacheMemory >= indexCacheMemoryLimit` | `mapreduce.task.index.cache.limit.bytes` | over the limit the spill index goes to a file; under it the `SpillRecord` is kept in `indexCacheList`. The check comes before the add, so the last record can overshoot | (a) |
| 17 | `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core` :: `mapreduce/counters/Limits.java:100#1` | `size > countersMax` | `mapreduce.job.counters.max` | throws `LimitExceededException` (and remembers it), so no new counter object is created; counter and group name lengths are also capped, so per-counter size is bounded | (c) |
| 18 | `hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager` :: `yarn/server/resourcemanager/ClientRMService.java:649#1` | `capacity() > maxSize` | `yarn.resourcemanager.delegation-token.max-conf-size` | `submitApplication` throws, so the app (and the token conf it would keep in RM memory and the state store) is not accepted | (c) |

## Read and not used as anchors

These were read in the same pass. They are not rejected: stage 2 bands them like any other row,
and stage 3 decides. They are left out only because an anchor must be unambiguous.

| uid (short) | Row | Why not an anchor |
|---|---|---|
| `DirectorySnapshottableFeature.java:188#1` | `... + ... > snapshotQuota` | caps the number of snapshots, but a snapshot's memory and disk cost is its diff, which has no fixed size (Rule 2 unclear) |
| `ContainerImpl.java:1101#1` | `length() > diagnosticsMaxSize` | bounds a held `StringBuilder` by trimming it, not by withholding creation; Rule 3 has no precedent for this shape yet |
| `DataXceiverServer.java:246#1` | `curXceiverCount > maxXceiverCount` | a thread/concurrency cap (Rule 2 reject class), although each xceiver holds buffers |
| `NameNodeResourceChecker.java:87#1` | `availableSpace < duReserved` | disk check whose verdict reaches safe mode far away (pattern (b)); the path was not traced |

## Note for the batch script: overloaded helpers merge

HDFS namespace and space **quotas** (`DirectoryWithQuotaFeature.java:176/183/198`,
`FSDirectory.java:926/934`) are in `HelperGuardedIfStatements.csv` behind the helper
`Quota.isViolated()`: 15 rows at 6 call sites. The query names a helper without its parameter
types, so the two overloads (`Quota.java:52`, two arguments, and `:61`, three arguments) share
the name, and `make-stage2-batches.py`'s one-unit-per-helper grouping merges them into a single
unit. Harmless here, because both overloads are the same check. They are not anchors only
because helper units render with the first call site's operands, which makes their text less
predictable than a narrowed row's.
