# DF_getAvailable — verification solution  <!-- file: cases/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`LocalDirAllocator.java:528`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/LocalDirAllocator.java#L528) — `if (capacity > maxCapacity)` in `AllocatorPerContext.getLocalPathForWrite(String, long, Configuration, boolean)` (known-size branch) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-06 |
| Estimate | `negative`: the check at line 528 only keeps a running maximum of the free space seen (`maxCapacity`, a local initialised to 0) so that it can be printed in the failure message at line 566; it never gates an allocation and never limits how much is written. |
| Ground | `maxCapacity` is read in exactly one place, the error string built at `LocalDirAllocator.java:561-566`, after the loop has already failed. No branch depends on it, so the check bounds nothing. The real placement gate is the next check, `capacity > size` (line 531). That gate is a one-time free-space test against the caller's *estimated* size; it is not a cap on bytes written either. |

Parts of the stem: constraint = `DF_getAvailable` (a limit queried at runtime with no declared variable: the value compared at line 528 comes from `DF.getAvailable()`); function = `getLocalPathForWrite` (the method that encloses line 528); operand = `maxCapacity` (the limit-side operand as written at line 528).

## A. Constraint trace

**A1. The constraint.**
- Name: `DF.getAvailable()`, the usable free bytes of the filesystem that holds one configured local directory. Both operands at line 528 come from it: `capacity = ctx.dirDF[dirNum].getAvailable()` (line 527), and `maxCapacity` is the running maximum of those values.
- Kind: a limit queried at runtime, with no configuration key, property or constant behind it. The comparison variable `maxCapacity` is a method local, declared `long maxCapacity = 0;` at [`LocalDirAllocator.java:429`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/LocalDirAllocator.java#L429).
- First declaration of the accessor: [`DF.java:95-97`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/DF.java#L95-L97). It returns `dirFile.getUsableSpace()`, which is read live on every call. The `dfInterval` of 30000 ms passed at `LocalDirAllocator.java:340` only throttles the shell-based `df` run (`getFilesystem`/`getMount`), not `getAvailable`.
- Unit: bytes. Default: none, since it is whatever the filesystem reports.
- How it can be set: only by changing the free space on the volume (filling or freeing disk, or choosing which directories go into the context key). Which directories are probed comes from the allocator's *context key*, read in `confChanged` (`LocalDirAllocator.java:317`). Examples: `mapreduce.cluster.local.dir` (`MRConfig.java:35`, default `${hadoop.tmp.dir}/mapred/local` in `mapred-default.xml:1126-1127`; inside a YARN task it is overwritten with the container's `LOCAL_DIRS`, `YarnChild.java:278-282`), `yarn.nodemanager.local-dirs`/`log-dirs` (`LocalDirsHandlerService.java:185-190`), `fs.s3a.buffer.dir`, `io.seqfile.local.dir`. The directory list is re-read on every call (`confChanged`, lines 314-365), so no restart is needed for an allocator in a running process, but daemon configuration is read at daemon start.
- Read by: any process that uses `LocalDirAllocator` with a known size. The main one is the MapReduce task JVM (map spills and merges through `YarnOutputFiles`/`MROutputFiles` → `getLocalPathForWrite(..., size, conf)`, e.g. `MapTask.java:1620-1628`, `1727-1734`).

**A2. What it caps.** Nothing. The quantity is local-disk free space on the volumes behind the context's directories, and the check at line 528 only computes `maxCapacity = max(capacity_i)` over the directories probed. The *neighbouring* check, `capacity > size` (line 531), decides whether a directory may be *chosen* for a file whose caller-estimated size is `size`. Even that is admission/placement, not a cap on bytes written.

**A3. Mechanism.**
1. A caller asks for a path with a known size: `LocalDirAllocator.getLocalPathForWrite(pathStr, size, conf)` → `getLocalPathForWrite(..., checkWrite=true)` (lines 150-153, 167-172) → `AllocatorPerContext.getLocalPathForWrite` (line 417).
2. `confChanged` builds or reuses the directory list and one `DF` per directory (lines 314-365). `maxCapacity = 0` (line 429).
3. A "roulette" pre-pass reads `getAvailable()` for every directory into `availableOnDisk[]` (lines 446-476). In the known-size branch this is used only for the history log.
4. Known-size branch (line 517 onward): start at a randomised index (lines 521-525). Loop over all directories (line 526):
   - `capacity = ctx.dirDF[dirNum].getAvailable()` (line 527), a fresh read;
   - **the check:** [`if (capacity > maxCapacity)`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/LocalDirAllocator.java#L528) → `maxCapacity = capacity` (line 529). If false, nothing happens. Neither outcome affects control flow;
   - the gate: `if (capacity > size)` (line 531) → `createPath` with a writability check (lines 532-540); on success, advance the round-robin pointer and `break` (lines 541-545);
   - otherwise move to the next directory (lines 550-552).
5. If no path is found, the message "Could not find any valid local directory for … with requested size … as the max capacity in any directory ( … ) is `maxCapacity`" is built (lines 560-566), logged, and `DiskErrorException` is thrown (line 572). This is the **only** read of `maxCapacity` (`grep -n maxCapacity` gives only lines 429, 528, 529, 566).
- When the "limit" is reached: nothing happens at line 528 in either outcome.
- Bypass and overshoot of the real gate (line 531): `size` is only an estimate (for example `MapTask.java:1620` estimates from the buffer span plus per-partition header bytes, and line 1727 uses `kvbuffer.length + partitions*APPROX_HEADER_LENGTH`). The returned path is not reserved, so the file can grow past `size`, and concurrent writers can take the space between the check and the write (see the class Javadoc, lines 59-62). `SIZE_UNKNOWN` (-1) calls skip the known-size branch entirely (lines 481-516). The check is strict `>`, so a directory with exactly `size` bytes free is rejected.

**A4. Other consumers.** Other tasks and containers sharing the same NodeManager local dirs, NodeManager localisation (distributed cache, `usercache`, `filecache`), container logs if `log-dirs` share the volume, HDFS DataNode volumes on the same disk, and any non-Hadoop process. None of them goes through this check. The NodeManager's own guard is the disk-health checker (`yarn.nodemanager.disk-health-checker.max-disk-utilization-per-disk-percentage`, default 90.0, `yarn-default.xml:1996-1997`; `min-free-space-per-disk-mb`, default 0, `yarn-default.xml:2017-2018`), which marks a directory bad. That is a separate mechanism.

**A5. Evidence beyond the source.** Existing tests in `hadoop-common/src/test/java/org/apache/hadoop/fs/TestLocalDirAllocator.java`: `testGetLocalPathForWriteForLessSpace` (lines 538-547) asserts only the failure message prefix for a request of `Long.MAX_VALUE - 1`, and does not assert the `maxCapacity` value. `testDirectoryRecovery`/`testDirectoryRecoveryKnownSize` (lines 552-587) relate to HADOOP-18636 and HADOOP-19554 (https://issues.apache.org/jira/browse/HADOOP-18636, https://issues.apache.org/jira/browse/HADOOP-19554), which touched this method's directory re-creation and diagnostics. JDK `File.getUsableSpace()` Javadoc (https://docs.oracle.com/javase/8/docs/api/java/io/File.html#getUsableSpace--) says it is a hint that guarantees nothing about later writes.

## B. Verification solution

**B1. Claim under test.** The comparison `capacity > maxCapacity` at `LocalDirAllocator.java:528` does not limit local-disk usage. Which directory is chosen, whether allocation succeeds, and how many bytes end up on disk are the same whether or not the check runs. Its only effect is the number printed as "max capacity in any directory" when allocation fails, and that number equals the largest `getUsableSpace()` seen. (Positive control: the adjacent gate `capacity > size`, line 531, does refuse allocation when every directory has ≤ `size` free.)

### B2. Unit tier

**B2a. Environment and build.** JDK 8, Maven 3.3+. Copy the tree to local disk (`rsync -a ~/hadoop-3.4.2/ /mydata/<you>/s4-ldA/src/`). Use two copies: **baseline** (unchanged) and **ablated**, where lines 528-530 are replaced by nothing, so `maxCapacity` stays 0. Build each with `mvn -pl hadoop-common-project/hadoop-common -am install -DskipTests -Dmaven.javadoc.skip=true` (ablated copy with `-Dmaven.repo.local=/mydata/<you>/m2-ablated` so the two jars do not overwrite each other). Put a new test class `TestLdaMaxCapacity.java` in `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/` (same package, so it can see `E_NO_SPACE_AVAILABLE`) in both copies. Default surefire JVM options.

Free space on a known, small filesystem: create two small ext4 loop filesystems if root is available (`truncate -s 256M /mydata/<you>/ldA/img0; mkfs.ext4 -q -F img0; sudo mount -o loop img0 /mnt/ldA0`, likewise `img1` at 512M on `/mnt/ldA1`, then `chown` both to the test user). Without root, use two directories on one local disk; then both report the same `getUsableSpace()`, and the test uses sizes relative to that value (see B2c).

> *Amended 2026-11-06 (D, A1), before any run:* stage-4 node `pc41`, `RUN=/mydata/jingsong-s4/DF_getAvailable-getLocalPathForWrite-maxCapacity-run1`. The two copies are made with `experiments/if-check-exp/hadoop/stage4-runtime-verification/jingsong/copy-source.sh $RUN/src-baseline` and `… $RUN/src-ablated` (the repository's pinned `systems/hadoop/source/`, local tag `rel/release-3.4.2`). Ablation: in `src-ablated` only, delete lines 528-530 of `LocalDirAllocator.java` (`if (capacity > maxCapacity) {`, `maxCapacity = capacity;`, `}`); `git -C $RUN/src-ablated diff --numstat` must show 0 added, 3 deleted. `JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64`. No `install` and no `-Dmaven.repo.local`: step B2e.2/3 runs `mvn -o -B test -Dtest=TestLdaMaxCapacity -DfailIfNoTests=false` in `hadoop-common-project/hadoop-common` of each copy, which compiles that module's main classes from the copy itself (the other 3.4.2 modules come from the node's `~/.m2`); nothing ablated reaches the shared `~/.m2`. Loop filesystems (root is available): images `$RUN/ldA/img0` (256M) and `$RUN/ldA/img1` (512M), `mkfs.ext4 -q -F`, `sudo mount -o loop` at `$RUN/mnt/ldA0` and `$RUN/mnt/ldA1` (not under `/mnt`), `sudo chown jason92`; dir0 = `$RUN/mnt/ldA0/lda`, dir1 = `$RUN/mnt/ldA1/lda`. The test reads them from the environment variables `LDA_DIR0`, `LDA_DIR1` and writes its CSV to `LDA_OUT` (the surefire fork inherits the environment). The build ignores test failures, so the run script reads the surefire count, not Maven's exit code. Harness: `experiments/if-check-exp/hadoop/stage4-runtime-verification/jingsong/harness/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous/`.

**B2b. Knobs.**
- K1, the code variant: baseline vs ablated (line 528 present vs removed).
- K2, the requested `size`, relative to `A0 = getUsableSpace(dir0)` and `A1 = getUsableSpace(dir1)` read in the test just before each call: `size ∈ {1024, min(A0,A1) − 64 MiB, max(A0,A1) − 64 MiB, max(A0,A1) + 64 MiB, Long.MAX_VALUE − 1}`.
- K3, directory sets: `{dir0}`, `{dir0,dir1}`. Set with `conf.set("test.lda.ctx", dir0 + "," + dir1)`.

> *Amended 2026-11-06 (D, A2), before any run:* `min` and `max` in K2 are taken over the directories of the K3 set in use. For `{dir0}`, min = max = A0, so K2 is `{1024, A0 − 64 MiB, A0 − 64 MiB, A0 + 64 MiB, Long.MAX_VALUE − 1}` (the repeated value is run as its own block). A *block* is the 200 calls of one (K2, K3); A0, A1, min and max are read once at the start of each block to fix its `size`, and the per-call before/after samples of B2d are recorded as well.

**B2c. Workload.** For each (K2, K3), 200 calls of `new LocalDirAllocator("test.lda.ctx").getLocalPathForWrite("f/x"+i, size, conf)`. Record the returned parent directory, or the exception message. For each successful call with `size ≤ 64 MiB`, also write `2 × size` bytes (or 128 MiB when `size` is large and the volume allows) to the returned path with `FileOutputStream`. This shows that the bytes written are not limited by `size` or by `maxCapacity`. Arithmetic: with `size = max(A0,A1)+64 MiB`, no directory satisfies `capacity > size`, so the call must throw. With `size = min − 64 MiB`, every directory qualifies.

> *Amended 2026-11-06 (D, A3), before any run:* the write rule, made exact so that the volumes are not filled by the writes. A successful call with `size ≤ 64 MiB` (here only `size = 1024`) writes `2 × size` = 2048 bytes to the returned path, on every call; these files stay until the end of the block, then are deleted. A successful call with `size > 64 MiB` writes `size + 32 MiB` bytes to the returned path on the **first** successful call of the block only (it fits: by construction of K2 every directory that can be chosen has about `size + 64 MiB` free or more), records the file size, and deletes the file before the next call; the other 199 calls write nothing (199 writes of ≥ 150 MiB do not fit on the volumes). The "128 MiB" alternative is dropped. `du -sb` of each directory is taken at the end of each block, before the deletion.

**B2d. Observables and instruments.**
- Outcome per call (directory index or exception), tallied as a histogram.
- The number after "is " in the exception message (parse with a regex `is (\d+)$` on the first line).
- `File.getUsableSpace()` of each directory, sampled immediately before and after each call.
- Bytes written: `Files.size(returned)` and `du -sb` of each directory after the run.
- Not directly observable: the internal `capacity` at line 527. It is bracketed by the before/after `getUsableSpace()` samples. Enable `log4j.logger.org.apache.hadoop.fs.LocalDirAllocator=DEBUG` to get the per-directory "bytes available" notes (line 471).

**B2e. Procedure.**
1. Prepare the directories (loop mounts or local dirs). Record `df -B1` for each.
2. Build the baseline copy and run `mvn -pl hadoop-common-project/hadoop-common test -Dtest=TestLdaMaxCapacity -DfailIfNoTests=false`. Save the CSV output (`target/lda-baseline.csv`).
3. Build the ablated copy and run the same test. Save `target/lda-ablated.csv`.
4. Diff the two CSVs, ignoring the message number. Then compare the message numbers.
5. `rm -rf` the test directories. `sudo umount /mnt/ldA0 /mnt/ldA1` if mounted.

> *Amended 2026-11-06 (D, A4), before any run:* the order is baseline rep 1, ablated rep 1, baseline rep 2, ablated rep 2 (B2h's "each variant twice"), on the same mounted directories, emptied before each run; each run's CSV is `$RUN/logs/unit/<variant>-rep<k>.csv`. Step 4 compares per block: success count, failure count, directory histogram, and the message number (baseline vs ablated, and rep 1 vs rep 2 of each variant). Step 5 also unmounts and deletes the images once the self-check has read the CSVs.

**B2f. Predictions.**
- For every (K2, K3), the success/failure outcome is identical between baseline and ablated. The directory histograms agree within sampling noise; selection is randomised (lines 521-525), so compare with a χ² test at p > 0.01.
- `size ≤ min − 64 MiB`: 200/200 succeed in both variants. With 2 dirs, roughly 50/50 split.
- `min − 64 MiB < size ≤ max − 64 MiB` (loop mounts only): 200/200 succeed, all in the larger directory.
- `size ≥ max + 64 MiB` and `Long.MAX_VALUE − 1`: 200/200 throw `DiskErrorException` in both variants. In baseline, the message number equals `max(A0,A1)` within the drift between samples (expect < 1 MiB on an idle test volume). In ablated it is 0.
- The bytes written after a successful call equal `2 × size` (the amount written), which exceeds `size`. Nothing at allocation time stops this.

> *Amended 2026-11-06 (D, A5), before any run:* (a) "within the drift between samples" means |N − max over the K3 set of the before-call `getUsableSpace()` samples| ≤ 1 MiB. (b) The χ² test is the 2 × 2 test of (dir0, dir1) counts, baseline vs ablated, for each two-directory block with successes, p > 0.01; a one-directory block agrees when its counts are equal. (c) The last bullet reads: the size of each written file equals the amount written (2048 = 2 × size for `size = 1024`; `size + 32 MiB` for the first successful call of a block with `size > 64 MiB`), which exceeds `size`; nothing at allocation time or during the write stops it. (d) In the `{dir0}` blocks: `1024` and `A0 − 64 MiB` succeed 200/200 in dir0; `A0 + 64 MiB` and `Long.MAX_VALUE − 1` fail 200/200.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Outcomes and histograms equal between baseline and ablated; only the message number differs (max avail vs 0) | Claim confirmed: line 528 is diagnostic only |
| Any call succeeds in one variant and fails in the other, or directory choice shifts significantly | Claim refuted: line 528 influences allocation (usage would follow the check) |
| Allocation fails when `size > max avail`, in both variants (positive control: the line-531 gate binds) and baseline number ≈ max avail | The workload reached the limit; the control moved |
| `size > max avail` calls succeed | Limit never reached (wrong volume measured, or free space changed). Not confirmed; redo with loop mounts |
| Written bytes are capped near `size` | Contradicts the trace that nothing limits the write. Investigate before concluding |

> *Amended 2026-11-06 (D, A6), before any run:* verdicts. **Confirmed** needs row 1 and row 3 together, with every written file as large as written (B2f, A5c). Row 2 → **Refuted**. Row 4 → **Not confirmed**. Row 5 → **Not confirmed**. New rows: (a) outcomes and histograms equal, but a baseline N differs from the max avail by more than 1 MiB, or an ablated N is not 0 → **Not confirmed** (the message trace is wrong or the ablated classes were not the ones tested); (b) the two repeats of one variant disagree in the success or failure count of any block → **Not confirmed** (not deterministic; free space moved); (c) a write after a successful call fails (`IOException`, no space) → **Not confirmed** (the write arithmetic was wrong; the block shows nothing about the cap).

**B2h. Controls.** The ablation isolates line 528 from line 531. Sampling `getUsableSpace()` before and after each call rules out free-space drift. A loop-mounted, otherwise idle filesystem rules out other writers. Running each variant twice checks the randomised start index.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, pseudo-distributed: NameNode, DataNode, ResourceManager, NodeManager (single node), JDK 8. Build the distribution from a local copy: `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`, unpacked to `/mydata/<you>/hadoop-base`. Daemon heaps `HADOOP_HEAPSIZE_MAX=1g`. Data and logs on local disk: `hadoop.tmp.dir=/mydata/<you>/ldc/tmp`, `dfs.namenode.name.dir`/`dfs.datanode.data.dir` under `/mydata/<you>/ldc/dfs`, `HADOOP_LOG_DIR=/mydata/<you>/ldc/logs`, `yarn.nodemanager.log-dirs=/mydata/<you>/ldc/nmlogs`. **`yarn.nodemanager.local-dirs=/mnt/ldc0`**: a 1 GiB ext4 loop filesystem on local disk (`truncate -s 1G /mydata/<you>/ldc/nmlocal.img; mkfs.ext4 -q -F …; sudo mount -o loop … /mnt/ldc0; sudo chown $USER /mnt/ldc0`). In `yarn-site.xml`, also set `yarn.nodemanager.disk-health-checker.max-disk-utilization-per-disk-percentage=100.0` and `min-free-space-per-disk-mb=0`, so the NM health checker does not mark the nearly full directory bad before the allocator sees it. In `mapred-site.xml`: `mapreduce.framework.name=yarn`, `mapreduce.map.memory.mb=1024`, `mapreduce.task.io.sort.mb=100`, `mapreduce.map.maxattempts=1`. In `yarn-site.xml`: `yarn.nodemanager.resource.memory-mb=4096`.

Optional ablation: build a second distribution from the ablated copy of B2a and swap only `share/hadoop/common/hadoop-common-3.4.2.jar`.

> *Amended 2026-11-06 (D, A7), before any run:* on `pc41`, `RUN=/mydata/jingsong-s4/DF_getAvailable-getLocalPathForWrite-maxCapacity-run1`. No tarball build: `cp -a /mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2 $RUN/hadoop`, `HADOOP_HOME=$RUN/hadoop`, `HADOOP_CONF_DIR=$RUN/conf` (`cp -r $HADOOP_HOME/etc/hadoop/* $RUN/conf/`), `HADOOP_LOG_DIR=$RUN/logs/daemons`, `HADOOP_PID_DIR=$RUN/pids`; `JAVA_HOME` and `HADOOP_HEAPSIZE_MAX=1g` in `$RUN/conf/hadoop-env.sh`. `/mydata/<you>/ldc` is `$RUN/ldc`; `yarn.nodemanager.local-dirs` is `$RUN/mnt/ldc0` (the 1 GiB image is `$RUN/ldc/nmlocal.img`, mounted there with `sudo mount -o loop`, not at `/mnt/ldc0`). Daemons start and stop with `hdfs --daemon start|stop namenode|datanode` and `yarn --daemon start|stop resourcemanager|nodemanager` (SSH to localhost has no key on this node, so `start-dfs.sh`/`start-yarn.sh` do not work). Settings MapReduce on YARN needs that the filed list leaves implicit: `fs.defaultFS=hdfs://localhost:9000`, `dfs.replication=1`, `yarn.nodemanager.aux-services=mapreduce_shuffle`, `yarn.app.mapreduce.am.env`, `mapreduce.map.env`, `mapreduce.reduce.env` = `HADOOP_MAPRED_HOME=$HADOOP_HOME`, `yarn.nodemanager.vmem-check-enabled=false` (JDK 8 virtual memory on a 40-core host; a memory check, not disk), `yarn.log-aggregation-enable=false`, `yarn.nodemanager.delete.debug-delay-sec=0` (the default, stated). Ports checked free before start (`ss -ltn`): 9000, 9870, 9864, 9866, 9867, 8088, 8030–8033, 8040, 8042, 13562. The ablated arm is not optional (A11).

**B3b. Knobs.** The only lever on `DF.getAvailable()` is free space on `/mnt/ldc0`. Vary it with a filler file (`fallocate -l <F> /mnt/ldc0/filler`) so that free space before the job is `free ∈ {≈900 MiB (no filler), ≈300 MiB, ≈60 MiB}`. Remove and recreate the filler between jobs; no restart needed. Optional K2: baseline vs ablated `hadoop-common` jar (needs an NM restart, `yarn --daemon stop/start nodemanager`).

> *Amended 2026-11-06 (D, A8), before any run:* "free" is the `df -B1` Avail of `$RUN/mnt/ldc0` (the same quantity as `getUsableSpace()`: non-root, after ext4's 5 % reserve), read just before the job is submitted. Levels: L900 = no filler (whatever the fresh 1 GiB filesystem gives, 850–950 MiB expected); L300 = 300 ± 15 MiB; L60 = 60 ± 10 MiB. The filler is `fallocate -l $((avail − target)) $RUN/mnt/ldc0/filler`, made after the previous job's application directories are gone (wait until no `$RUN/mnt/ldc0/usercache/*/appcache/application_*` is left, timeout 120 s).

**B3c. Workload.** `teragen` of 1,000,000 rows (≈95 MiB) with `-Dmapreduce.job.maps=1`, then `terasort` with 1 reducer. The single map's spill request is ≈ buffer span + header bytes, a little under 100 MiB (`MapTask.java:1620`; the sort buffer is 100 MiB). Arithmetic: with free ≈ 900 or 300 MiB, every check `capacity > size` passes. With free ≈ 60 MiB < ≈95 MiB, it fails and the map attempt dies with `DiskErrorException`. Each job takes about 1-3 min.

> *Amended 2026-11-06 (D, A9), before any run:* arithmetic correction from the source alone (`MapTask.java:985-1022`, `1619-1628`, `1864-1903`). The 100 MiB sort buffer spills at 80 % (`mapreduce.map.sort.spill.percent` default 0.8), and every record also takes 16 bytes of metadata in it. A teraSort record serialises as 102 bytes (two `Text`, 11 + 91), so the first spill starts at ≈ 83,886,080 × 102 / 118 ≈ 72.5 MB ≈ 69 MiB of record data, and its known-size request S1 is ≈ 69 MiB plus a header. The rest (≈ 28 MiB) is a second spill, and `mergeParts` then asks for about the sum of the spill files (≈ 97-100 MiB). So the map's **first** known-size request is ≈ 69 MiB, not ≈ 95-100 MiB, and at L60 it is that request that fails (S1 > 60 MiB). At L300 the peak local usage is about two copies of the map output (the spill files plus the merged file, or the merged map output plus the reducer's on-disk merge), ≈ 200 MiB < 300 MiB, so L300 still succeeds. Each job's counters must show `Launched map tasks=1`.

**B3d. Observables and instruments.**
- `df -B1 /mnt/ldc0` and `du -sb /mnt/ldc0/usercache` every 1 s during the job (a `while` loop writing a CSV).
- Job outcome: `mapred job -status`, plus the map task syslog under `/mydata/<you>/ldc/nmlogs/application_*/container_*/syslog` (read via `yarn logs -applicationId <id>` once aggregation is off or after finish). Grep for "Could not find any valid local directory" and extract "max capacity in any directory ( … ) is N".
- Not directly observable: the exact `size` the map passed. Turn on DEBUG for `org.apache.hadoop.fs.LocalDirAllocator` in the task (`-Dmapreduce.map.log.level=DEBUG`) so the "Requested file size is …" note (line 518) is logged.

> *Amended 2026-11-06 (D, A10), before any run:* the sampler runs every 0.5 s (not 1 s, so that the short merge peak is not missed): time, `df -B1` Avail, `du -sb $RUN/mnt/ldc0/usercache`, into `$RUN/logs/cluster/<arm>-<level>-samples.csv`. The peak is the maximum `du` sample of the job. Task logs are read from `$RUN/ldc/nmlogs/application_*/container_*/syslog` (aggregation off). The job client output and `mapred job -status` (counters) are kept per job. With `-Dmapreduce.map.log.level=DEBUG` the map's root log level is DEBUG, so the "Requested file size is …" (line 518) and "bytes available under path" (line 471) notes are in its syslog.

> *Amended 2026-11-06 (D, A15; runbook defect 2 of the stage-4 run 1, cluster tier):* the NodeManager deletes the non-aggregated container logs in `yarn.nodemanager.log-dirs` when it restarts (A11 step 4), so the baseline arm's task syslogs were gone before they could be re-read. Each application's log directory is copied to `$RUN/logs/cluster/<arm>-<level>-applog/` right after its job. The map container is the one whose syslog has lines from the `org.apache.hadoop.mapred.MapTask` logger (the AM's syslog also names `MapTask` in a failed task's stack trace); its count is checked against the job counter `Launched map tasks`. B3f and B3g are unchanged; the cluster tier restarts from its beginning.

**B3e. Procedure.**
1. Format the NameNode, then `start-dfs.sh` and `start-yarn.sh`. Check `jps`.
2. `yarn jar share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.2.jar teragen -Dmapreduce.job.maps=1 1000000 /tg`.
3. For each free level (no filler, 300 MiB, 60 MiB): set the filler, start the samplers, run `yarn jar … terasort -Dmapreduce.job.reduces=1 -Dmapreduce.map.log.level=DEBUG /tg /ts-<level>`, stop the samplers, and collect the logs. `hdfs dfs -rm -r /ts-<level>`. Clean `/mnt/ldc0/usercache/*/appcache` after the job ends; the NM deletes it unless `yarn.nodemanager.delete.debug-delay-sec` is set.
4. Optional: swap in the ablated jar, restart the NM, and repeat step 3.
5. Run `stop-yarn.sh` and `stop-dfs.sh`, check that `jps` is empty, `sudo umount /mnt/ldc0`, and remove `/mydata/<you>/ldc`.

> *Amended 2026-11-06 (D, A11), before any run:* the steps as run. (1) Mount; format the NameNode; start NameNode, DataNode, ResourceManager, NodeManager with `--daemon`; wait (≤ 120 s) for 1 live DataNode (`hdfs dfsadmin -report`) and 1 RUNNING node (`yarn node -list`). (2) teragen as filed, once (its output is reused by every job). (3) Baseline arm: L900, L300, L60 in that order; each `terasort` runs under `timeout 900`; afterwards `hdfs dfs -rm -r -skipTrash /ts-<arm>-<level>`, remove the filler, wait for the application directories to go (A8). **First-trigger stop:** if the baseline L900 map syslog has no "Requested file size is" note (the known-size branch was not reached), the tier stops there. (4) Ablated arm — **required**, because B3g row 1 needs it: build `hadoop-common-3.4.2.jar` from `src-ablated` with `mvn -o -B package -DskipTests -Dmaven.javadoc.skip=true` in `hadoop-common-project/hadoop-common` (not installed); stop all four daemons; replace `$RUN/hadoop/share/hadoop/common/hadoop-common-3.4.2.jar` with it (the original kept as `$RUN/hadoop-common-3.4.2.jar.orig`, md5 of both recorded); start all four again (HDFS data kept); repeat step 3 as arm `ablated`. (5) Stop all daemons; check that no NameNode, DataNode, ResourceManager, NodeManager, MRAppMaster or YarnChild of this run is left (`ps`); `sudo umount $RUN/mnt/ldc0`. The images are deleted after the self-check; the logs stay on the node.

> *Amended 2026-11-06 (D, A14; runbook defect 1 of the stage-4 run 1, cluster tier):* after the daemons are restarted for the ablated arm (A11 step 4), the NameNode is still in its safe-mode extension (30 s) when the DataNode reports live, and `terasort` fails at once with `SafeModeException` ("Cannot create file /ts-ablated-L900/_partition.lst. Name node is in safe mode"). After every daemon start, `hdfs dfsadmin -safemode wait` runs before any job is submitted. B3f and B3g are unchanged; the cluster tier restarts from its beginning.

**B3f. Predictions.**
- free ≈ 900 and ≈ 300 MiB: the job succeeds. Peak `du` of `usercache` follows the workload (map output ≈ 95-100 MiB plus merge and shuffle copies). It does not depend on free space and is not bounded by any "max capacity" value.
- free ≈ 60 MiB: the map attempt fails, the log contains "with requested size S … max capacity in any directory ( /mnt/ldc0/… ) is N", with S ≈ 95-100 MiB > N, and N within a few MiB of the `df` avail sampled at that moment. No spill file is created (the `du` increase stays well under S).
- Ablated jar: the same success/failure pattern at each level. N in the message is 0.

> *Amended 2026-11-06 (D, A12), before any run:* (a) In the L60 bullet, "S ≈ 95-100 MiB > N" becomes: S (the requested size in the message) is the first spill's request, 60 MiB < S ≤ 100 MiB (≈ 69 MiB by A9), and S > N. (b) "N within a few MiB of the `df` avail" means within 4 MiB of the last 0.5-s `df` sample before the failure (baseline arm). (c) "It does not depend on free space" means: the peak `du` at L300 is within 5 % of the peak at L900 in the same arm. (d) "No spill file is created" means the peak `du` at L60 stays below S / 2. (e) The L60 job ends FAILED with its map attempt failed, and the map syslog has the "Could not find any valid local directory" line.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Success/failure depends only on free vs S, and the ablated jar shows the same pattern with N = 0 | Claim confirmed: line 528 bounds nothing and only feeds the message |
| Usage peak at 900 MiB free ≈ usage peak at 300 MiB free (within 5%) | Usage follows the workload, not any value derived from line 528 (claim confirmed) |
| Usage scales with the reported max capacity, or the ablated jar changes success/failure | Claim refuted |
| At 60 MiB free the map fails with the expected message (positive control: the line-531 gate binds) | Limit reached; the control moved |
| At 60 MiB free the job succeeds, or the NM marks the dir bad first | Limit not reached or a different guard intervened (check the health-checker settings). Not confirmed |

> *Amended 2026-11-06 (D, A13), before any run:* verdicts. **Confirmed** needs rows 1, 2 and 4 together, in both arms. Row 3 → **Refuted**; made exact: the ablated arm differs in success or failure at any level, or the L300 peak is lower than the L900 peak by more than 5 % and lies within 5 % of the free space at L300 (usage pinned to the reported capacity). Row 5 → **Not confirmed**. New rows: (a) the L900 and L300 peaks differ by more than 5 % in a way row 3 does not describe → **Not confirmed**; (b) a job at L900 or L300 fails for any reason (a task failure, no space) → **Not confirmed** (the workload arithmetic was wrong); (c) at L60 the ablated N is not 0, or the baseline N is not within 4 MiB of the sampled avail → **Not confirmed** (the jar swap did not take effect, or the message trace is wrong); (d) L60 fails but S ≤ N or S is outside (60, 100] MiB → **Not confirmed** (an allocation other than the traced one failed); (e) a job ran more than one map task → that job is invalid and is repeated once.

**B3h. Controls.** A single local dir on a dedicated loop filesystem means no other writers and a known capacity. The disk-health checker is disabled at 100% so the NM guard does not act first. One map and `maxattempts=1` mean exactly one allocation sequence. The ablated jar separates line 528 from line 531. DEBUG notes record S and the per-directory availability.

**B4. Risks and cleanup.** Loop mounts need `sudo`. Mount only under `/mnt/ldc0` and `/mnt/ldA*`, with image files on local disk (never shared storage), and unmount at the end. Filling a filesystem must never target `/` or shared storage. Default Hadoop ports (9870, 8088, 8042, 9000, …) must be free; check with `ss -ltn` first. After each tier, run `stop-yarn.sh`, `stop-dfs.sh` and `mapred --daemon stop historyserver` if it was started. `jps` must list only `Jps`. Delete `/mydata/<you>/ldc`, `/mydata/<you>/ldA`, and the ablated Maven repo. Never build in or add files to the shared source tree.

## C. Sources read

hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/LocalDirAllocator.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/DF.java
hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/TestLocalDirAllocator.java
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRConfig.java
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/resources/mapred-default.xml
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/MapTask.java (grep only)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/MROutputFiles.java (grep only)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-app/src/main/java/org/apache/hadoop/mapred/YarnOutputFiles.java (grep only)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-app/src/main/java/org/apache/hadoop/mapred/YarnChild.java (grep only)
hadoop-yarn-project/hadoop-yarn/hadoop-yarn-common/src/main/resources/yarn-default.xml (grep only)
Repository-wide grep for `new LocalDirAllocator(` (callers list)
https://docs.oracle.com/javase/8/docs/api/java/io/File.html#getUsableSpace-- (cited, not fetched)
https://issues.apache.org/jira/browse/HADOOP-18636, https://issues.apache.org/jira/browse/HADOOP-19554 (cited from test comments, not fetched)

## D. Stage-4 feedback

### D1. Step-0 amendments, 2026-11-06 (before any harness run or reading)

Made by the stage-4 audit ([results file](../../../stage4-runtime-verification/jingsong/results/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md) section 1). None depends on a reading. The claim (B1) is unchanged. Two filed predictions are corrected from the source alone: the map's first known-size request is ≈ 69 MiB, not ≈ 95-100 MiB (A9, A12a), and the write rule of B2c is made exact (A3, A5c). The other amendments adapt paths to the stage-4 node, define tolerances, make the ablated cluster arm required (B3g row 1 needs it), and give each conclusions row a verdict.

| # | Where | Amendment | Reason |
|---|---|---|---|
| A1 | B2a | `$RUN` on `/mydata`, copies by `copy-source.sh`, exact ablation, `mvn -o test` in the module (no `install`), loop mounts under `$RUN`, env-var inputs | the filed paths do not exist on the node; an ablated install would overwrite the shared `~/.m2` |
| A2 | B2b | min/max over the K3 set; definition of a block | for `{dir0}` the filed bands gave a wrong prediction |
| A3 | B2c | exact write rule (2048 B every call; `size + 32 MiB` once per large block) | 200 large writes do not fit; "128 MiB" was below `size` |
| A4 | B2e | run order (two repeats each), CSV paths, per-block comparison | B2h asks for two runs per variant |
| A5 | B2f | drift = 1 MiB; χ² definition; write prediction; `{dir0}` bands | tolerances undefined |
| A6 | B2g | verdict per row; rows for a wrong message number, disagreeing repeats, failed writes | outcomes without a row |
| A7 | B3a | distribution copy, `--daemon` start, implicit MR-on-YARN settings, loop mount under `$RUN`, ports | node facts (no SSH to localhost) |
| A8 | B3b | "free" = `df` Avail; level tolerances; filler and wait rule | levels undefined |
| A9 | B3c | first spill request ≈ 69 MiB (sort buffer arithmetic); L300 peak ≈ 200 MiB | the filed S ignored the 80 % spill threshold and record metadata |
| A10 | B3d | 0.5-s sampler, files, log paths | the merge peak is short |
| A11 | B3e | exact steps, timeouts, first-trigger stop, required ablated arm with jar swap | B3g row 1 needs the ablated arm |
| A12 | B3f | S range (60, 100] MiB; tolerances for N, peaks and "no spill file" | follows from A9; tolerances undefined |
| A13 | B3g | verdict per row; Refuted made exact; rows for other failures, a failed jar swap, an unexpected S, more than one map | outcomes without a row |

**Runbook-defect amendments after the freeze (2026-11-06).** A14, B3e: wait for the NameNode to leave safe mode after every daemon start (results §3, defect 1). A15, B3d: copy each application's log directory after its job, because the NodeManager deletes them on restart; identify the map container by the `MapTask` logger (results §3, defect 2). B1, B2f–B2g and B3f–B3g are unchanged (their text hashes in results §1 still hold); the cluster tier restarted.

### D2. Stage-4 result, 2026-11-06

[Results file](../../../stage4-runtime-verification/jingsong/results/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md). Run 1 against the file at sha256 `8bd5cc94b71a30bc43f3ce3bb2d96d8bb49607d379bb127ab32a59d87ca61293` (A1–A15; uncommitted, repository HEAD `38acb6bf`), `pc41`, JDK 8, Hadoop 3.4.2.

- **Unit tier: Confirmed — does not cap** (B2g rows 1 and 3). In all 10 blocks (`{dir0}`, `{dir0,dir1}` × 5 sizes, 200 calls each) the baseline and the ablated build (lines 528-530 removed) gave the same successes, failures and directory histograms, in both repeats; the only difference was the number in the failure message: baseline = the largest `getUsableSpace()` (215,781,376 / 473,268,224 B, deviation 0 B), ablated = 0. Every written file was as large as written and larger than `size` (2048 B for 1024; up to 439,713,792 B for 406,159,360). The line-531 gate refused every request above the free space in both builds (positive control).
- **Cluster tier: Confirmed — does not cap** (B3g rows 1, 2 and 4). teraSort (1 map, 1 reduce): L900 and L300 succeeded with the same peak local usage, 208,971,148 B (199.3 MiB), in both arms; at L60 the map's first spill request of 72,511,848 B (A9 predicted ≈ 72.5 MB) was refused in both arms, peak usage 0.9 MiB; the message's N was 61,792,256 B (baseline, 0.4 MiB from the sampled `df` avail) and 0 (ablated jar).
- **Outcome class: true negative.** No run 2 (exact, observed readings; the control moved).
- **Runbook defects:** (1) B3e, NameNode in safe-mode extension after the daemon restart → A14; (2) B3d, the NodeManager deletes container logs on restart → A15. The cluster tier restarted; no prediction or conclusions row changed.
- **For stage 3:** the filed first-spill size (≈ 95-100 MiB) ignored the 80 % spill threshold and the 16-byte record metadata (corrected before the run, A9); the line-531 gate is the only placement gate and it is a one-time check, not a cap (written bytes exceeded `size` without hindrance).
