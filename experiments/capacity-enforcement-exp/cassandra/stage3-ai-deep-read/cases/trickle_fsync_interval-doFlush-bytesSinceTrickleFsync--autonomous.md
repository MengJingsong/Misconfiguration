# trickle_fsync_interval — verification solution  <!-- file: cases/trickle_fsync_interval-doFlush-bytesSinceTrickleFsync--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set place, the declaration): [`Config.java:458`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L458); its main check is [`SequentialWriter.java:227`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SequentialWriter.java#L227) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`: `trickle_fsync_interval` sets how often a writer fsyncs (I/O pacing). It does not cap heap, off-heap, total page cache or disk. The only thing it bounds is how many of one writer's bytes are still unsynced (dirty), and those pages stay in the page cache after the fsync, now clean. One narrow exception, HintsWriter's cache drop, is tested separately (B1 sub-claim H). |
| Ground | (1) The check at `SequentialWriter.java:227` only calls `fdatasync`. It never refuses, delays or shrinks a write, so the bytes written to disk and the pages cached are the same at every value. Only their dirty/clean state changes. (2) It is off by default (`trickle_fsync: false`, `Config.java:456`, `conf/cassandra.yaml:954`). (3) The counter is per writer, and any number of writers (flushes, compactions, SAI, cache saves) run at once, so the code sets no node-wide figure. The kernel's `vm.dirty_*` limits already bound node-wide dirty memory. (4) The hints use (`HintsWriter.java:289-303`) treats the same value as a "file is big enough to drop from cache" threshold. That bounds only the clean, reclaimable cache of hints files, whose disk size is capped by other limits (`max_hints_file_size`, `max_hints_size_per_host`). |

## A. Constraint trace

**A1. The constraint.** `trickle_fsync_interval` is a cassandra.yaml configuration entry, declared at
[`Config.java:458`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L458)
as `DataStorageSpec.IntKibibytesBound trickle_fsync_interval = new DataStorageSpec.IntKibibytesBound("10240KiB")`.
- Unit: KiB. The value is an int number of KiB, at most `Integer.MAX_VALUE` KiB (`DataStorageSpec.java:281-284`). The old name `trickle_fsync_interval_in_kb` is still accepted (`Config.java:457`).
- Default: 10240 KiB (10 MiB), a literal in `Config.java:458`, repeated in `conf/cassandra.yaml:956`. `SequentialWriterOption.Builder` has its own default of `10 * 1024 * 1024` (`SequentialWriterOption.java:113`), used by writers that do not read the config.
- It does nothing in SequentialWriter unless the companion flag `trickle_fsync` is true (`Config.java:456`, default `false`; `SequentialWriter.java:224`). HintsWriter reads it whatever the flag says (`HintsWriter.java:291,301`).
- How to set it: only the yaml key (`trickle_fsync_interval: <n>KiB`). There is no `-D` property, no JMX or nodetool setter, and no validation beyond the int bound. The only accessor is `DatabaseDescriptor.getTrickleFsyncIntervalInKiB()` (`DatabaseDescriptor.java:3876-3879`). It is read when writer options are built (`IOOptions.java:35-36`, created per SSTable builder at `SSTable.java:392`; `AutoSavingCache.java:110-111`; `IndexFileUtils.java:43-44`, a static set once at class load; `HintsWriter.java:291,301`, read on each call). Since nothing at runtime changes `conf`, a change needs a restart.

**A2. What it caps.**
- Resource: none of heap, off-heap or disk. What it bounds is the number of bytes one `SequentialWriter` has handed to the kernel since its last data fsync. Those bytes sit in the OS page cache as dirty pages until written back.
- Quantity compared against the limit: `bytesSinceTrickleFsync` (`SequentialWriter.java:60`), an int per writer. It is compared with `option.trickleFsyncByteInterval()` = `getTrickleFsyncIntervalInKiB() * 1024`, computed as an **int** (`IOOptions.java:36`).
- For compressed data files the counter adds **uncompressed** bytes. `CompressedSequentialWriter.flushData` leaves `buffer.position()` at the uncompressed chunk length (`CompressedSequentialWriter.java:147,156`), so the dirty bytes on disk are ≤ the interval.
- Hints: `position()` of the hints file, compared with `lastSyncPosition + interval` (fsync) and with `interval` (cache drop), both in long arithmetic (`HintsWriter.java:291,301`).

**A3. Mechanism.**
1. Configured value → `DatabaseDescriptor.getTrickleFsyncIntervalInKiB()` (`DatabaseDescriptor.java:3876-3879`) → `SequentialWriterOption.trickleFsyncByteInterval(KiB*1024)` (`IOOptions.java:34-37`). The multiplication is int × int.
2. Each buffer flush of a `SequentialWriter` calls `doFlush` (`SequentialWriter.java:220`). This calls `flushData()` (`:248`, `channel.write`), then, if `option.trickleFsync()` (`:224`), adds the flushed byte count to `bytesSinceTrickleFsync` (`:226`).
3. **The check:** [`SequentialWriter.java:227`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SequentialWriter.java#L227) `if (bytesSinceTrickleFsync >= option.trickleFsyncByteInterval())`.
   - **true:** `syncDataOnlyInternal()` (`:196-205`) runs `SyncUtil.force(fchannel, false)` = `FileChannel.force(false)` (`SyncUtil.java:96`), which is `fdatasync`. The counter is then reset to 0 (`:230`). The writer then continues. Nothing is refused or throttled beyond the time the fsync blocks.
   - **false:** nothing happens and the data stays dirty until the kernel writes it back, or until the writer's own `syncInternal()` at prepare/finish (`:89-91`, `:213-217`).
   - So the limit is "reached" every interval bytes, and reaching it only turns dirty pages clean. Pages stay resident; nothing in this path calls `posix_fadvise`.
4. **Hints use** (independent of `trickle_fsync`). On `HintsWriter.Session.close()` (`HintsWriter.java:269-275`):
   - `maybeFsync` (`:289-293`): `if (position() >= lastSyncPosition + interval*1024L)` then `fsync()`, which is `force(true)` and updates `lastSyncPosition` (`:130-134`).
   - `maybeSkipCache` (`:295-303`): `if (position >= interval*1024L)` then `NativeLibrary.trySkipCache(fd, 0, pageAligned(position))`. That is `posix_fadvise(POSIX_FADV_DONTNEED)` (`NativeLibrary.java:250`). Linux drops only clean pages, so what stays resident after a session close is about `position - lastSyncPosition`, which is < interval. While `position < interval` the whole file stays cached.
   - `HintsWriter.close()` (`:118-123`) fsyncs but does not drop cache.
5. Bypasses and overshoot:
   - `trickle_fsync: false` (the default) disables the SequentialWriter check entirely (`:224`).
   - Entire-sstable streaming builds its own options with `.trickleFsync(false)` (`CassandraEntireSSTableStreamReader.java:180-189`). Zero-copy writes go straight to the channel via `writeDirectlyToChannel` (`SequentialWriter.java:445-452`, `SSTableZeroCopyWriter.java:241-260`) and never pass through `doFlush`.
   - Overshoot per writer: the counter is checked only after a whole buffer is written, so at most `interval + bufferSize` dirty bytes (64 KiB default buffer, `SequentialWriterOption.java:107`; 2 MiB for some writers).
   - The counter is per writer, so with W writers active the node has W × interval dirty bytes; the code sets no node-wide bound.
   - **Overflow:** `getTrickleFsyncIntervalInKiB() * 1024` is int. A value of 2097152 KiB (2 GiB) gives `Integer.MIN_VALUE`, 4194304 KiB gives 0, and any value ≥ 2 GiB that wraps negative or to 0 makes `:227` true on every flush, so the writer fsyncs every buffer. The hints path uses `1024L` and does not overflow.
   - `NativeLibrary.trySkipCache(int,long,long,String)` decrements `offset` (`:237`). That is a latent bug for lengths > 2 GiB and does not matter for hints files (≤ 128 MiB).

**A4. Other consumers.** Other things that use page cache and dirty memory without this knob:
- the commit log (its own sync policy, `commitlog_sync*`);
- memtable flush and compaction writers when `trickle_fsync` is false;
- streaming receivers (`CassandraEntireSSTableStreamReader.java:186`);
- reads (mmap/standard, cached by the kernel);
- early-open cache dropping of compaction inputs (`SSTableReader.trySkipFileCacheBefore`, `SSTableReader.java:1388-1392`, governed by `sstable_preemptive_open_interval`);
- hint reading (`ChecksummedDataInput.java:224`);
- the kernel-wide limits `vm.dirty_background_ratio/bytes`, `vm.dirty_ratio/bytes` and `vm.dirty_expire_centisecs`, which bound node-wide dirty memory whatever Cassandra does.

Heap: each writer's 64 KiB buffer (`SequentialWriterOption.java:107-109`), which does not depend on the knob. Disk: identical bytes at every knob value.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:949-956`: "fsync() at intervals in order to force the operating system to flush the dirty buffers. Enable this to avoid sudden dirty buffer flushing from impacting read latencies". The stated purpose is latency, not capacity.
- `doc/modules/cassandra/pages/managing/configuration/configuration.adoc:120` (rename table, `trickle_fsync_interval_in_kb` → `trickle_fsync_interval`, KiB).
- Tests only check parsing (`ParseAndConvertUnitsTest.java:101`, `LoadOldYAMLBackwardCompatibilityTest.java:95`). In-JVM dtests turn `trickle_fsync` on (`InstanceConfig.java:140`).
- Linux `posix_fadvise(2)` (POSIX_FADV_DONTNEED does not drop dirty pages; https://man7.org/linux/man-pages/man2/posix_fadvise.2.html).
- Kernel `Documentation/admin-guide/sysctl/vm.rst` (dirty_* limits; https://www.kernel.org/doc/html/latest/admin-guide/sysctl/vm.html).
- `fincore(1)` (util-linux).
- No git history in the copy, so none was used.

## B. Verification solution

**B1. Claim under test.**
- **Main (S):** with `trickle_fsync: true`, changing `trickle_fsync_interval` from 1 MiB to 100 MiB does **not** change the node's heap, process RSS, total page cache (`Cached`) or on-disk bytes for the same sstable-write workload. Every value leaves the written files fully resident and the same size. Only the unsynced (dirty) bytes per writer, and the fdatasync count, follow the knob. If total cached or disk usage follows the knob, the claim is refuted.
- **Sub-claim (H), stated so it can fail:** for hints files the same value is a cache-drop threshold. After each session close, a hints file's resident page cache is < interval (about 0 when one session ≥ interval), and the whole file when the file is smaller than the interval. This does not bound any other memory.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant, util-linux `fincore`, ≥ 4 GiB `MemAvailable`, and a local disk with ≥ 10 GiB free.
- `export RUN=/mydata/$USER-s4/o212` (any local, non-shared disk; check with `df -h $RUN`).
- `mkdir -p $RUN && rsync -a ~/cassandra-5.0.9/ $RUN/src/ && cd $RUN/src && ant jar` (never build in the shared tree).
- Probe source goes **outside** the tree: `$RUN/probe/src/org/apache/cassandra/hints/TrickleProbe.java`. It is in package `org.apache.cassandra.hints` so that it can reach the package-private `HintsWriter`.
- Do **not** run it through `ant testsome`. That target passes `-Dcassandra.skip_sync=true` (`build.xml:1390`), which turns `SyncUtil.force` into a no-op (`SyncUtil.java:89`). Also make sure the environment variable `CASSANDRA_SKIP_SYNC` is unset.
- JVM: `-Xmx1g`.

```java
package org.apache.cassandra.hints;

import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.SequentialWriter;
import org.apache.cassandra.io.util.SequentialWriterOption;

public class TrickleProbe
{
    // args: mode(sw|hints) trickle(true|false) intervalKiB dir totalMiB
    public static void main(String[] a) throws Exception
    {
        DatabaseDescriptor.toolInitialization();
        Config c = DatabaseDescriptor.getRawConfig();
        c.trickle_fsync = Boolean.parseBoolean(a[1]);
        c.trickle_fsync_interval = new DataStorageSpec.IntKibibytesBound(a[2] + "KiB");
        System.out.printf("CONF trickle=%s intervalKiB=%d intBytes=%d%n", DatabaseDescriptor.getTrickleFsync(),
                          DatabaseDescriptor.getTrickleFsyncIntervalInKiB(), DatabaseDescriptor.getTrickleFsyncIntervalInKiB() * 1024);
        if (a[0].equals("sw")) sw(new File(a[3]), Long.parseLong(a[4])); else hints(new File(a[3]), Long.parseLong(a[4]));
        System.exit(0);
    }

    static void sw(File dir, long totalMiB) throws Exception
    {
        // identical to IOOptions.fromDatabaseDescriptor().writerOptions (IOOptions.java:34-37)
        SequentialWriterOption opt = SequentialWriterOption.newBuilder()
                                     .trickleFsync(DatabaseDescriptor.getTrickleFsync())
                                     .trickleFsyncByteInterval(DatabaseDescriptor.getTrickleFsyncIntervalInKiB() * 1024)
                                     .build();
        Field op = SequentialWriter.class.getDeclaredField("bytesSinceTrickleFsync");
        op.setAccessible(true);
        long[] syncs = {0}, maxAtSync = {0};
        File f = new File(dir, "probe-sw.db");
        SequentialWriter w = new SequentialWriter(f, opt)
        {
            @Override protected void syncDataOnlyInternal()
            {
                try { maxAtSync[0] = Math.max(maxAtSync[0], op.getInt(this)); } catch (IllegalAccessException e) { throw new RuntimeException(e); }
                syncs[0]++;
                super.syncDataOnlyInternal();
            }
        };
        byte[] chunk = new byte[64 << 10];
        ThreadLocalRandom.current().nextBytes(chunk);
        long maxAfterWrite = 0;
        for (long i = 0; i < totalMiB * 16; i++) { w.write(chunk); maxAfterWrite = Math.max(maxAfterWrite, op.getInt(w)); }
        long trickleSyncs = syncs[0];
        w.finish();
        w.close();
        System.out.printf("SW trickleSyncs=%d syncsInclFinish=%d maxOperandAfterWrite=%d maxOperandAtSync=%d fileBytes=%d%n",
                          trickleSyncs, syncs[0], maxAfterWrite, maxAtSync[0], f.length());
    }

    static void hints(File dir, long totalMiB) throws Exception
    {
        HintsDescriptor d = new HintsDescriptor(UUID.randomUUID(), System.currentTimeMillis());
        ByteBuffer agg = ByteBuffer.allocateDirect(256 << 10);       // HintsWriteExecutor.WRITE_BUFFER_SIZE
        byte[] payload = new byte[4096];
        ThreadLocalRandom.current().nextBytes(payload);
        Field ls = HintsWriter.class.getDeclaredField("lastSyncPosition");
        ls.setAccessible(true);
        long sessionBytes = 8L << 20, written = 0;
        try (HintsWriter w = HintsWriter.create(dir, d))
        {
            while (written < (totalMiB << 20))
            {
                long pos;
                try (HintsWriter.Session s = w.newSession(agg))
                {
                    for (long b = 0; b < sessionBytes; b += 4096, written += 4096) s.append(ByteBuffer.wrap(payload));
                    pos = s.position();
                }
                System.out.printf("HINTS position=%d lastSyncPosition=%d%n", pos, ls.getLong(w));
                new ProcessBuilder("fincore", "--bytes", "--noheadings", "-o", "RES,SIZE,FILE", w.getFile().absolutePath())
                    .inheritIO().start().waitFor();
            }
        }
    }
}
```

**B2b. Knobs.**

| Run | `trickle_fsync` | `trickle_fsync_interval` | why |
|---|---|---|---|
| sw-off | false | 10240 | default: check disabled |
| sw-1M | true | 1024 | small interval |
| sw-10M | true | 10240 | default interval |
| sw-100M | true | 102400 | large interval |
| sw-2G | true | 2097152 | int overflow → `Integer.MIN_VALUE` |
| sw-4G | true | 4194304 | int overflow → 0 |
| h-1M / h-1M-off | true / **false** | 1024 | hints; the flag should not matter |
| h-10M | true | 10240 | session (8 MiB) < interval |
| h-100M | true | 102400 | drop starts at 100 MiB |
| h-256M | true | 262144 | interval > file (120 MiB): never dropped |

All values are set by the probe's arguments, which write `Config` fields before any writer is built.

**B2c. Workload.**
- sw: one `SequentialWriter` writes 1024 MiB (`totalMiB=1024`) in 64 KiB chunks, which is 16384 buffer flushes of exactly 64 KiB. Each interval above is a multiple of 64 KiB, so the counter reaches the limit after exactly I/64 KiB flushes: 1024 MiB / 1 MiB = 1024 crossings, 1024 / 10 = 102, 1024 / 100 = 10.
- hints: one file, 15 sessions × 8 MiB = 120 MiB (`totalMiB=120`, below `max_hints_file_size` 128 MiB), with 4 KiB raw entries.

**B2d. Observables and instruments.**
- Probe stdout:
  - the check's operand at each trigger (`maxOperandAtSync`) and its maximum between triggers (`maxOperandAfterWrite`);
  - the trickle fsync count before `finish()`;
  - file bytes (disk);
  - for hints, `position` and `lastSyncPosition` after each session.
- `fincore --bytes` on the output file after the run (sw) and after each session (hints), for page-cache residency.
- A background sampler for global dirty memory: `while sleep 0.2; do echo "$(date +%s.%N) $(awk '/^(Dirty|Writeback):/{printf "%s ",$2}' /proc/meminfo)"; done > $RUN/probe/meminfo-<run>.txt`.
- Not directly observable:
  - per-file dirty pages. `/proc/meminfo Dirty` is machine-wide, so on a shared machine it is noisy and only a secondary reading.
  - the probe heap, which is not a meaningful operand (the buffer is fixed at 64 KiB).

**B2e. Procedure.**
1. `mkdir -p $RUN/probe/{src/org/apache/cassandra/hints,classes,out,storage}`. Write the file above. `cp $RUN/src/conf/cassandra.yaml $RUN/probe/cassandra.yaml`, then set all `*_directory` / `data_file_directories` keys in it under `$RUN/probe/storage`.
2. `javac -cp "$RUN/src/build/classes/main:$RUN/src/lib/*" -d $RUN/probe/classes $RUN/probe/src/org/apache/cassandra/hints/TrickleProbe.java`
3. `CP="$RUN/probe/classes:$RUN/src/build/classes/main:$RUN/src/lib/*"; JOPT="-Xmx1g -Dcassandra.config=file://$RUN/probe/cassandra.yaml -Dcassandra.storagedir=$RUN/probe/storage"`
4. For each sw run R with args (T, I):
   1. `rm -f $RUN/probe/out/*`
   2. start the meminfo sampler in the background and let it record a baseline for 10 s
   3. `env -u CASSANDRA_SKIP_SYNC java $JOPT -cp "$CP" org.apache.cassandra.hints.TrickleProbe sw T I $RUN/probe/out 1024 | tee $RUN/probe/sw-R.txt`
   4. `fincore --bytes $RUN/probe/out/probe-sw.db >> $RUN/probe/sw-R.txt`
   5. stop the sampler, then `rm -f $RUN/probe/out/*`.
5. For each hints run R with args (T, I): `rm -f $RUN/probe/out/*; env -u CASSANDRA_SKIP_SYNC java $JOPT -cp "$CP" org.apache.cassandra.hints.TrickleProbe hints T I $RUN/probe/out 120 | tee $RUN/probe/h-R.txt; rm -f $RUN/probe/out/*`.
6. Positive control (see B2h), right after sw-1M is rewritten: rerun sw-1M without deleting the file, then `dd if=$RUN/probe/out/probe-sw.db iflag=nocache count=0 status=none` (GNU dd: fadvise DONTNEED on the whole file) and `fincore --bytes` again.

**B2f. Predictions** (stated before any run; S = 1073741824 bytes written).

| Run | trickleSyncs (before finish) | maxOperandAtSync | maxOperandAfterWrite | fileBytes | fincore RES |
|---|---|---|---|---|---|
| sw-off | 0 | 0 (only the finish sync, operand 0) | 0 | S | ≈ S (≥ 0.95 S) |
| sw-1M | 1024 (±1) | 1048576 | 983040 | S | ≈ S |
| sw-10M | 102 | 10485760 | 10420224 | S | ≈ S |
| sw-100M | 10 | 104857600 | 104792064 | S | ≈ S |
| sw-2G | 16384 (every flush) | 65536 | 0 | S | ≈ S |
| sw-4G | 16384 (every flush) | 65536 | 0 | S | ≈ S |

- `CONF intBytes` prints -2147483648 for sw-2G and 0 for sw-4G.
- `fileBytes` and RES are the same in every row: disk and page cache do not follow the knob.
- Secondary: the peak of (Dirty+Writeback) above baseline is ordered sw-1M ≤ sw-10M ≤ sw-100M ≤ sw-off. The sw-1M increase is ≤ ~2 MiB plus noise.

Hints, after each 8 MiB session close (k = 1…15, position ≈ 8k MiB):
- h-1M and h-1M-off: `lastSyncPosition == position` and RES ≤ 8 KiB after every session. The two runs are identical, so the flag has no effect.
- h-10M: RES alternates between ≈ 8 MiB (sessions with no fsync: k = 1, 3, 5, …) and ≈ 0 (sessions with an fsync), and is always < 10 MiB.
- h-100M: RES = position for k ≤ 12 (up to 96 MiB). At k = 13 (104 MiB) it drops to ≈ 0, then reads ≈ 8 MiB at k = 14 and ≈ 16 MiB at k = 15.
- h-256M: RES = position at every k (120 MiB at the end) and `lastSyncPosition` stays 0.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| fileBytes equal across sw runs and RES ≈ fileBytes in every sw run, while trickleSyncs/operand follow I as predicted | claim S confirmed at unit level: the check works as traced and caps neither disk nor cache |
| RES or fileBytes falls as I falls (e.g. sw-1M RES ≪ S while sw-off RES ≈ S) | **claim S refuted**: usage follows the knob |
| trickleSyncs = 0 or the operand never moves in a `trickle=true` run | the check was never reached (skip_sync, wrong config hook, or a probe bug). Not confirmed; fix and rerun |
| sw-2G / sw-4G sync on every flush | overflow confirmed (defect: very large values sync more, not less) |
| sw-2G behaves like a 2 GiB interval (≤ 1 sync) | overflow prediction wrong; amend A3 |
| hints RES follows I as predicted | sub-claim H confirmed (the only memory quantity that follows) |
| hints RES ≈ position in every run | the cache drop does not bind; H refuted |
| positive control: RES drops to ≈ 0 after `dd iflag=nocache` | the instrument detects a binding cache cap. If RES does not drop, fincore readings cannot be used and the result is not confirmed |

**B2h. Controls.**
- sw-off is the baseline, with the same workload and the check disabled.
- The `dd iflag=nocache` step is a positive control: a known cache cap (DONTNEED) applied to the same file must make RES drop.
- The h-1M-off run shows that the hints effect does not depend on `trickle_fsync`.
- Running outside `ant testsome`, with `CASSANDRA_SKIP_SYNC` unset, rules out no-op syncs. To check, `strace -f -c -e trace=fdatasync` on one sw-1M run shows ≈ 1024 calls.
- Require `MemAvailable` ≥ 4 GiB at the start, so that reclaim under memory pressure cannot be mistaken for a cap. Record `free -m` before each run.

### B3. Cluster tier

**B3a. Environment and build.**
- Same `$RUN/src` build plus `cd $RUN/src && ant stress-build` (for `tools/bin/cassandra-stress`). JDK 11.
- Phase S uses one node, n1 on 127.0.0.1. Phase H uses two nodes on one host, n1 on 127.0.0.1 and n2 on 127.0.0.2 (loopback aliases work on Linux without setup).
- Each node gets its own conf copy, `cp -r $RUN/src/conf $RUN/nX/conf`, with these edits in `$RUN/nX/conf/cassandra.yaml`:
  - `data_file_directories: [$RUN/nX/data]`
  - `commitlog_directory: $RUN/nX/commitlog`
  - `hints_directory: $RUN/nX/hints`
  - `saved_caches_directory: $RUN/nX/saved_caches`
  - `cdc_raw_directory: $RUN/nX/cdc`
  - `listen_address`, `rpc_address`: 127.0.0.X
  - `seeds: "127.0.0.1:7000"`
  - `concurrent_compactors: 1`
  - `compaction_throughput: 0MiB/s`
- In `$RUN/n2/conf/cassandra-env.sh` set `JMX_PORT="7299"` (n1 keeps 7199).
- Start a node with `CASSANDRA_CONF=$RUN/nX/conf CASSANDRA_LOG_DIR=$RUN/nX/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M $RUN/src/bin/cassandra -p $RUN/nX/pid`.
- Requirements: ≥ 30 GiB free local disk for `$RUN` and ≥ 12 GiB `MemAvailable`. If memory is smaller, scale the dataset to MemAvailable/3.

**B3b. Knobs.** These are set on n1's yaml and need a restart.
- Phase S: `trickle_fsync: false` (interval 10240KiB), then `trickle_fsync: true` with `trickle_fsync_interval` set to 1024KiB, 10240KiB and 102400KiB. An optional fifth run uses 2097152KiB (overflow). Each value is applied with `nodetool drain`, stop, edit, start.
- Phase H: `trickle_fsync: true` with 1024KiB and 262144KiB (larger than the 128 MiB hints file, so hints files are never dropped), plus 1024KiB with `trickle_fsync: false`.

**B3c. Workload.**
- **Phase S:** load about 4 GiB once.
  1. `nodetool -p 7199 disableautocompaction` is not needed, because the load is followed by a major compaction.
  2. `tools/bin/cassandra-stress write n=4000000 cl=ONE -col n=FIXED\(1\) size=FIXED\(1024\) -schema "replication(factor=1)" -rate threads=64 -node 127.0.0.1`. That is 4 M rows × about 1.05 KiB, about 4.1 GiB uncompressed.
  3. Then `nodetool flush keyspace1 standard1 && nodetool compact keyspace1 standard1` to leave one sstable.
  4. Per knob value: `nodetool upgradesstables -a -j 1 keyspace1 standard1`. This rewrites that sstable through the normal `SSTableWriter` path (IOOptions writer options), about U ≈ 4 GiB uncompressed. With `compaction_throughput: 0` it takes a few tens of seconds, enough for many intervals (U/1 MiB ≈ 4000 crossings).
- **Phase H:**
  1. Start n1 and n2. Create the schema with `cassandra-stress write n=1000 ... -schema "replication(factor=2)" keyspace=hk`.
  2. Stop n2 with `nodetool -p 7299 stopdaemon`, then wait until `nodetool status` on n1 shows DN.
  3. Write `cassandra-stress write n=600000 cl=ONE -col n=FIXED\(1\) size=FIXED\(1024\) -schema "replication(factor=2)" keyspace=hk -rate threads=32 -node 127.0.0.1`. That is about 630 MiB of hints for n2, which `max_hints_file_size` 128 MiB splits into about 5 files.
  4. Between knob values: `nodetool truncatehints`, then drain and restart n1. n2 stays down.

**B3d. Observables and instruments.** Sample every 0.5 s (S) or 1 s (H) into `$RUN/obs/<phase>-<run>.txt`:
- `/proc/meminfo` lines `Dirty`, `Writeback`, `Cached`, `MemAvailable`;
- n1 RSS from `ps -o rss= -p $(cat $RUN/n1/pid)`;
- heap from `jstat -gc $(cat $RUN/n1/pid) 1000`;
- disk from `du -sb $RUN/n1/data/keyspace1`, sampled before and after the rewrite;
- page cache of the new sstable from `fincore --bytes $RUN/n1/data/keyspace1/standard1-*/*-Data.db` after the rewrite;
- (H) `fincore --bytes $RUN/n1/hints/*.hints` and `ls -l $RUN/n1/hints`, every second;
- the fdatasync count during the rewrite: `strace -f -c -e trace=fdatasync,fsync $(for t in /proc/$(cat $RUN/n1/pid)/task/*; do printf -- '-p %s ' ${t##*/}; done) -o $RUN/obs/strace-<run>.txt`, started just before `upgradesstables` and stopped with Ctrl-C when it finishes. This needs `kernel.yama.ptrace_scope` ≤ 1 and the same user. If ptrace is not allowed, skip it and rely on Dirty.

Not directly observable: per-file dirty bytes. Dirty is machine-wide, so take a 60 s baseline before each rewrite and report peak − baseline median.

**B3e. Procedure.**
1. Build. Prepare n1 (and n2 for phase H). Check `df -h $RUN` and `free -g`.
2. Phase S:
   1. Start n1 with `trickle_fsync: false` and wait for `nodetool status` to show UN.
   2. Load, flush, compact (B3c). Record `nodetool tablestats keyspace1.standard1`: space used, compression ratio, so U = space / ratio.
3. For each knob value in B3b phase S:
   1. `nodetool drain`, then `kill $(cat $RUN/n1/pid)`, and wait until the pid is gone.
   2. Edit the yaml, start n1, and wait for UN.
   3. Start the samplers (and strace) and record a 60 s baseline.
   4. Run `nodetool upgradesstables -a -j 1 keyspace1 standard1`.
   5. Keep sampling for 60 s after it completes. Then run `fincore` and `du`.
   6. Stop the samplers.
4. Positive control S (B3h).
5. Phase H:
   1. Start n2 with its own conf. Create `hk` RF=2, then stop n2.
   2. For each H knob value: restart n1 with the value, `nodetool truncatehints`, start the hints sampler, and run the stress write.
   3. Then wait 30 s (more than 2 × `hints_flush_period`) so that the last buffers are flushed, and take a final `fincore` of all hints files.
6. Clean up (B4).

**B3f. Predictions.** U is the uncompressed size from step 2. These are relations fixed before the runs.
- **Disk:** `du` after the rewrite is equal across all S runs (± 1 %).
- **Total page cache:** `fincore` RES of the new `Data.db` ≈ its size (≥ 90 %) in every S run. The rise in `Cached` during the rewrite is roughly the new sstable size in every run (± 15 %), so the 1 MiB run is not lower than the off run.
- **Heap and RSS:** peak heap used and RSS do not differ between S runs by more than run-to-run noise (± 10 %).
- **Dirty:** the peak of (Dirty+Writeback) above the baseline median follows the knob:
  - off: large, governed by the kernel (≥ 10× the 1 MiB run; typically hundreds of MiB or more);
  - on, interval I: ≤ about W × (I + 64 KiB) plus noise, with W ≈ 2–3 concurrent writers (Data, primary Index, and small components): about ≤ 4 MiB for 1 MiB, ≤ 32 MiB for 10 MiB, ≤ 320 MiB for 100 MiB;
  - in all cases ordered 1M ≤ 10M ≤ 100M ≤ off.
- **fdatasync count:** about U/I plus the index size / I plus fewer than 50 finish syncs. For off: fewer than 50. For the 2097152KiB run: about U/64 KiB.
- **Phase H:**
  - 1024KiB, with `trickle_fsync` true or false: after each flush every hints file shows RES ≤ 1 MiB, and the total RES of all hints files is ≤ about files × 1 MiB plus the session in progress (≤ 32 MiB).
  - 262144KiB: every closed hints file is fully resident (RES ≈ size, about 128 MiB), and the total RES ≈ the total hints bytes (about 630 MiB).
  - Hints disk bytes are the same in all H runs.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| du, Data.db RES, Cached rise, heap and RSS are flat across S runs, while Dirty peak and fdatasync count follow I | **claim S confirmed**: the knob paces writeback and caps neither memory nor disk |
| Cached rise or Data.db RES is lower at small I than off (beyond ± 15 %), or du differs | **claim S refuted**: usage follows the knob |
| Dirty peak and fdatasync count are the same across all S runs | the check was never exercised (yaml not applied, `trickle_fsync` false, or a bypass path). Not confirmed; check the startup log line "Node configuration:[...]" (`Config.java:1371`) for `trickle_fsync=true; trickle_fsync_interval=...` and rerun |
| the positive control does not change Data.db RES or memory.current | the instruments cannot see a binding cap. Not confirmed |
| H: RES follows I as predicted | sub-claim H confirmed: hints cache residency is bounded per file |
| H: 1024KiB with `trickle_fsync: false` behaves like 262144KiB | hints use is gated by the flag after all; amend A3 |
| H: RES ≈ size in both runs | cache drop does not bind (e.g. no JNA/fadvise). H refuted; check the log for "Failed trySkipCache" |

**B3h. Controls.**
- The S off run is the baseline: the same rewrite with the check disabled.
- **Positive control S (a cap known to bind, same workload):** repeat the 1 MiB rewrite with n1 started inside a memory-capped cgroup: `systemd-run --user --scope -p MemoryMax=4G -- env CASSANDRA_CONF=... $RUN/src/bin/cassandra -f`. Use 4G = 2G heap + about 1G off-heap + 1G page cache, which is less than the 4 GiB output. Expected: the scope's `memory.current` stays ≤ 4G and the new Data.db RES is well below its size, so the same workload's page cache visibly follows a binding cap.
  - This needs cgroup v2 user delegation with `memory` listed in `/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers`.
  - If delegation is not available, the fallback is `dd if=<Data.db> iflag=nocache count=0 status=none` followed by `fincore`: RES must fall to about 0.
- Phase H's 262144KiB run is the "no drop" control for the 1024KiB run.
- Quiet-machine check: compare baseline Dirty and Cached before each run. If another tenant's I/O moves the baseline by more than the predicted 1 MiB-run increase, repeat the run.
- Keep the node otherwise idle during the rewrite (no client load), so the commit log and memtable flushes do not add dirty pages.

**B4. Risks and cleanup.**
- Disk: about 4 GiB of input, about 4 GiB for each rewrite (the old file is removed after it), about 630 MiB of hints, and the probe's 1 GiB file. Everything lives under `$RUN` on local disk. Never use NFS or `/proj` storage.
- Never drop the global page cache or change `vm.*` sysctls (machine-wide). Use only per-file `dd iflag=nocache` and a per-user cgroup scope.
- strace slows Cassandra. Detach it (Ctrl-C) as soon as the rewrite ends.
- Processes:
  1. After each tier, run `nodetool -p 7199 stopdaemon` and `nodetool -p 7299 stopdaemon` (or `kill $(cat $RUN/nX/pid)`) and kill the sampler loops.
  2. Check: `pgrep -u $USER -f CassandraDaemon`, `pgrep -u $USER -f TrickleProbe`, `pgrep -u $USER strace` and `pgrep -u $USER -f 'sleep 0'` must all be empty. Also stop the `systemd-run` scope (`systemctl --user stop <scope>`).
- Files: `rm -rf $RUN/n1 $RUN/n2 $RUN/probe/out $RUN/probe/storage` after copying `$RUN/obs` and `$RUN/probe/*.txt` to the results location. Remove `$RUN/src` when stage 4 is done.

## C. Sources read

- src/java/org/apache/cassandra/config/Config.java (440-475)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (270-285, 385, 3865-3880)
- src/java/org/apache/cassandra/config/DataStorageSpec.java (274-295)
- src/java/org/apache/cassandra/io/util/SequentialWriter.java
- src/java/org/apache/cassandra/io/util/SequentialWriterOption.java
- src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java (140-205)
- src/java/org/apache/cassandra/io/sstable/IOOptions.java
- src/java/org/apache/cassandra/io/sstable/SSTable.java (392)
- src/java/org/apache/cassandra/io/sstable/SSTableZeroCopyWriter.java (241-260)
- src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java (1375-1395)
- src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java (253, 393), bti/BtiTableWriter.java (174-176, 334) (grep)
- src/java/org/apache/cassandra/db/streaming/CassandraEntireSSTableStreamReader.java (180-190)
- src/java/org/apache/cassandra/cache/AutoSavingCache.java (100-116)
- src/java/org/apache/cassandra/index/sai/disk/io/IndexFileUtils.java (30-50)
- src/java/org/apache/cassandra/hints/HintsWriter.java
- src/java/org/apache/cassandra/hints/HintsWriteExecutor.java (200-257)
- src/java/org/apache/cassandra/hints/HintsService.java (79, 110-125)
- src/java/org/apache/cassandra/hints/HintsDescriptor.java (constructors)
- src/java/org/apache/cassandra/utils/NativeLibrary.java (200-270)
- src/java/org/apache/cassandra/utils/SyncUtil.java
- conf/cassandra.yaml (68-111, 945-957, 1172)
- build.xml (testsome target, 1382-1392; stress-build)
- doc/modules/cassandra/pages/managing/configuration/configuration.adoc (120)
- test/unit/org/apache/cassandra/config/ParseAndConvertUnitsTest.java (101), LoadOldYAMLBackwardCompatibilityTest.java (95), test/distributed/.../InstanceConfig.java (140), test/unit/org/apache/cassandra/hints/HintsStoreTest.java, HintsMaker.java (grep for HintsWriter usage)
- https://man7.org/linux/man-pages/man2/posix_fadvise.2.html (cited, not fetched in this session)
- https://www.kernel.org/doc/html/latest/admin-guide/sysctl/vm.html (cited, not fetched in this session)

## D. Stage-4 feedback

none yet
