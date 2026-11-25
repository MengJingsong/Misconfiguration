/*
 * Stage-4 harness, capacity-enforcement-exp (Hadoop, Jingsong), case
 * dfs.datanode.pmem.cache.dirs-reserve-maxBytes--autonomous (B2, unit tier, with the stage-4 amendments
 * S1-S3 of 2026-11-25). Not upstream. Copied into
 * hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/
 * of the case's local source copy. Prints one PMCHK line per reading; makes no assertion on the
 * predictions (they are compared with B2f in the results file).
 *
 * u1*: PmemVolumeManager direct (B2c U1) at M = 32768, 65536, 131072.
 * u2*: runtime-queried cap, one and two directories on one file system (U2).
 * u3*: MiniDFSCluster end-to-end (U3) at M = 32768, 65536, 131072 (control).
 */
package org.apache.hadoop.hdfs.server.datanode.fsdataset.impl;

import java.io.File;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.hadoop.fs.FileUtil;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.fs.RemoteIterator;
import org.apache.hadoop.hdfs.DFSConfigKeys;
import org.apache.hadoop.hdfs.DFSTestUtil;
import org.apache.hadoop.hdfs.DistributedFileSystem;
import org.apache.hadoop.hdfs.ExtendedBlockId;
import org.apache.hadoop.hdfs.HdfsConfiguration;
import org.apache.hadoop.hdfs.MiniDFSCluster;
import org.apache.hadoop.hdfs.protocol.CacheDirectiveEntry;
import org.apache.hadoop.hdfs.protocol.CacheDirectiveInfo;
import org.apache.hadoop.hdfs.protocol.CachePoolInfo;
import org.apache.hadoop.hdfs.protocol.LocatedBlock;
import org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor;
import org.apache.hadoop.hdfs.server.datanode.DataNode;
import org.apache.hadoop.io.nativeio.NativeIO;
import org.apache.hadoop.io.nativeio.NativeIO.POSIX.CacheManipulator;
import org.apache.hadoop.io.nativeio.NativeIO.POSIX.NoMlockCacheManipulator;
import org.apache.hadoop.test.GenericTestUtils;
import org.apache.hadoop.test.GenericTestUtils.LogCapturer;
import org.apache.hadoop.test.MetricsAsserts;
import org.junit.After;
import org.junit.Before;
import org.junit.FixMethodOrder;
import org.junit.Test;
import org.junit.runners.MethodSorters;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.event.Level;

@FixMethodOrder(MethodSorters.NAME_ASCENDING)
public class TestPmemCapacityCap {
  static final long B = 4096;
  static final String BP = "bp-test";
  static final Pattern REJ = Pattern.compile("is not a valid possibility because the block has size");
  static final Pattern NORES = Pattern.compile("could not reserve more bytes");
  static final Pattern NOSPACE = Pattern.compile("There is no enough persistent memory space");
  static final Pattern ADDED = Pattern.compile("added to PENDING_CACHED on DataNode");

  private String pmem0;
  private String pmem1;
  private MiniDFSCluster cluster;
  private DistributedFileSystem dfs;
  private CacheManipulator prev;
  private final List<LogCapturer> caps = new ArrayList<>();

  private static void out(String s) {
    System.out.println("PMCHK," + s);
    System.out.flush();
  }

  @Before
  public void before() throws Exception {
    PmemVolumeManager.reset();
    PmemVolumeManager.setMaxBytes(-1);
    pmem0 = MiniDFSCluster.getBaseDirectory() + "pmem-o30-0";
    pmem1 = MiniDFSCluster.getBaseDirectory() + "pmem-o30-1";
    for (String d : new String[] {pmem0, pmem1}) {
      File f = new File(d).getAbsoluteFile();
      FileUtil.fullyDelete(f);
      if (!f.mkdirs()) {
        throw new RuntimeException("mkdirs failed " + f);
      }
    }
  }

  @After
  public void after() throws Exception {
    if (cluster != null) {
      try {
        RemoteIterator<CacheDirectiveEntry> it = dfs.listCacheDirectives(null);
        List<Long> ids = new ArrayList<>();
        while (it.hasNext()) {
          ids.add(it.next().getInfo().getId());
        }
        for (long id : ids) {
          dfs.removeCacheDirective(id);
        }
        long t0 = System.currentTimeMillis();
        while (dn().getFSDataset().getCacheUsed() != 0
            && System.currentTimeMillis() - t0 < 30000) {
          Thread.sleep(500);
        }
        out("teardown,cacheUsed=" + dn().getFSDataset().getCacheUsed() + ",diskBytes="
            + diskBytes(pmem0) + ",diskFiles=" + diskFiles(pmem0) + ",waitMs="
            + (System.currentTimeMillis() - t0));
      } finally {
        cluster.shutdown();
        cluster = null;
      }
    }
    for (LogCapturer c : caps) {
      c.stopCapturing();
    }
    caps.clear();
    if (prev != null) {
      NativeIO.POSIX.setCacheManipulator(prev);
      prev = null;
    }
    PmemVolumeManager.reset();
    PmemVolumeManager.setMaxBytes(-1);
    FileUtil.fullyDelete(new File(pmem0).getAbsoluteFile());
    FileUtil.fullyDelete(new File(pmem1).getAbsoluteFile());
  }

  private LogCapturer cap(Class<?> c) {
    LogCapturer l = LogCapturer.captureLogs(LoggerFactory.getLogger(c));
    caps.add(l);
    return l;
  }

  private static int count(Pattern p, String s) {
    Matcher m = p.matcher(s);
    int n = 0;
    while (m.find()) {
      n++;
    }
    return n;
  }

  /** Sum of regular-file lengths under dir (recursive), tolerant to files vanishing. */
  static long diskBytes(String dir) {
    return walk(new File(dir), true);
  }

  static long diskFiles(String dir) {
    return walk(new File(dir), false);
  }

  private static long walk(File f, boolean bytes) {
    File[] l = f.listFiles();
    if (l == null) {
      return 0;
    }
    long s = 0;
    for (File c : l) {
      if (Files.isSymbolicLink(c.toPath())) {
        continue;
      }
      if (c.isDirectory()) {
        s += walk(c, bytes);
      } else if (c.isFile()) {
        s += bytes ? c.length() : 1;
      }
    }
    return s;
  }

  // ---------------------------------------------------------------- U1
  private void u1(long m) throws Exception {
    PmemVolumeManager.setMaxBytes(m);
    LogCapturer pvm = cap(PmemVolumeManager.class);
    PmemVolumeManager.init(new String[] {pmem0}, false);
    PmemVolumeManager mgr = PmemVolumeManager.getInstance();
    out("u1,instr,M=" + m + ",capacity=" + mgr.getCacheCapacity() + ",volumes=" + mgr.getVolumes());
    int n = (int) (m / B) + 4;
    int ok = 0;
    int fail = 0;
    long maxUsed = 0;
    StringBuilder rs = new StringBuilder();
    for (int i = 1; i <= n; i++) {
      long r = mgr.reserve(new ExtendedBlockId(i, BP), B);
      long used = mgr.getCacheUsed();
      maxUsed = Math.max(maxUsed, used);
      if (r >= 0) {
        ok++;
      } else {
        fail++;
      }
      rs.append(i == 1 ? "" : ";").append(r);
    }
    int warn = count(NOSPACE, pvm.getOutput());
    out("u1,reserves,M=" + m + ",r=" + rs);
    out("u1,full,M=" + m + ",ok=" + ok + ",fail=" + fail + ",used=" + mgr.getCacheUsed()
        + ",maxUsed=" + maxUsed + ",mapSize=" + mgr.getBlockKeyToVolume().size()
        + ",noSpaceWarns=" + warn);
    long afterRel = mgr.release(new ExtendedBlockId(1, BP), B);
    long usedAfterRel = mgr.getCacheUsed();
    long rNext = mgr.reserve(new ExtendedBlockId(n + 1, BP), B);
    out("u1,release,M=" + m + ",releaseReturn=" + afterRel + ",usedAfterRelease=" + usedAfterRel
        + ",nextReserve=" + rNext + ",usedAfterNext=" + mgr.getCacheUsed()
        + ",mapSize=" + mgr.getBlockKeyToVolume().size());
    // The target check itself (:77), reached by reflection with the volume full.
    Field f = PmemVolumeManager.class.getDeclaredField("usedBytesCounts");
    f.setAccessible(true);
    Object c = ((List<?>) f.get(mgr)).get(0);
    Method res = c.getClass().getDeclaredMethod("reserve", long.class);
    res.setAccessible(true);
    Method gu = c.getClass().getDeclaredMethod("getUsedBytes");
    gu.setAccessible(true);
    Method gm = c.getClass().getDeclaredMethod("getMaxBytes");
    gm.setAccessible(true);
    long before = (Long) gu.invoke(c);
    long rr = (Long) res.invoke(c, 1L);
    long afterR = (Long) gu.invoke(c);
    // known answer: reserve(0) on a full counter succeeds (next == maxBytes is allowed)
    long r0 = (Long) res.invoke(c, 0L);
    out("u1,reflect,M=" + m + ",class=" + c.getClass().getName() + ",maxBytes=" + gm.invoke(c)
        + ",usedBefore=" + before + ",reserve1=" + rr + ",usedAfter=" + afterR + ",reserve0=" + r0
        + ",noSpaceWarnsTotal=" + count(NOSPACE, pvm.getOutput()));
  }

  @Test
  public void u1aM32768() throws Exception {
    u1(32768);
  }

  @Test
  public void u1bM65536() throws Exception {
    u1(65536);
  }

  @Test
  public void u1cM131072() throws Exception {
    u1(131072);
  }

  // ---------------------------------------------------------------- U2
  @Test
  public void u2UsableSpace() throws Exception {
    PmemVolumeManager.setMaxBytes(-1);
    PmemVolumeManager.init(new String[] {pmem0}, false);
    long cap1 = PmemVolumeManager.getInstance().getCacheCapacity();
    long us1 = new File(pmem0, PmemVolumeManager.CACHE_DIR).getUsableSpace();
    out("u2,one,capacity=" + cap1 + ",usable=" + us1 + ",diff=" + (cap1 - us1));
    PmemVolumeManager.reset();
    PmemVolumeManager.init(new String[] {pmem0, pmem1}, false);
    long cap2 = PmemVolumeManager.getInstance().getCacheCapacity();
    long us2 = new File(pmem0, PmemVolumeManager.CACHE_DIR).getUsableSpace();
    String fs0 = Files.getFileStore(new File(pmem0).toPath()).toString();
    String fs1 = Files.getFileStore(new File(pmem1).toPath()).toString();
    out("u2,two,capacity=" + cap2 + ",usable=" + us2 + ",diffFrom2x=" + (cap2 - 2 * us2)
        + ",ratio=" + String.format("%.6f", (double) cap2 / us2) + ",store0=" + fs0
        + ",store1=" + fs1 + ",sameStore=" + fs0.equals(fs1));
  }

  // ---------------------------------------------------------------- U3
  private DataNode dn() {
    return cluster.getDataNodes().get(0);
  }

  private long blocksCachedMetric() {
    return MetricsAsserts.getLongCounter("BlocksCached",
        MetricsAsserts.getMetrics(dn().getMetrics().name()));
  }

  private String read(String tag) throws Exception {
    return tag + ",cacheUsed=" + dn().getFSDataset().getCacheUsed() + ",cacheCapacity="
        + dn().getFSDataset().getCacheCapacity() + ",numBlocksCached="
        + dn().getFSDataset().getNumBlocksCached() + ",blocksCachedMetric=" + blocksCachedMetric()
        + ",failedToCache=" + dn().getFSDataset().getNumBlocksFailedToCache() + ",diskBytes="
        + diskBytes(pmem0) + ",diskFiles=" + diskFiles(pmem0);
  }

  private void u3(long m, int expectF1) throws Exception {
    PmemVolumeManager.setMaxBytes(m);
    HdfsConfiguration conf = new HdfsConfiguration();
    conf.setLong(DFSConfigKeys.DFS_NAMENODE_PATH_BASED_CACHE_REFRESH_INTERVAL_MS, 100);
    conf.setLong(DFSConfigKeys.DFS_CACHEREPORT_INTERVAL_MSEC_KEY, 500);
    conf.setLong(DFSConfigKeys.DFS_BLOCK_SIZE_KEY, B);
    conf.setLong(DFSConfigKeys.DFS_HEARTBEAT_INTERVAL_KEY, 1);
    conf.setInt(DFSConfigKeys.DFS_DATANODE_FSDATASETCACHE_MAX_THREADS_PER_VOLUME_KEY, 10);
    conf.setInt(DFSConfigKeys.DFS_REPLICATION_KEY, 1);
    conf.set(DFSConfigKeys.DFS_DATANODE_PMEM_CACHE_DIRS_KEY, pmem0);
    prev = NativeIO.POSIX.getCacheManipulator();
    NativeIO.POSIX.setCacheManipulator(new NoMlockCacheManipulator());
    Logger crm = LoggerFactory.getLogger(CacheReplicationMonitor.class);
    GenericTestUtils.setLogLevel(crm, Level.TRACE);
    LogCapturer crmCap = cap(CacheReplicationMonitor.class);
    LogCapturer dnCap = cap(FsDatasetCache.class);
    LogCapturer pvmCap = cap(PmemVolumeManager.class);
    cluster = new MiniDFSCluster.Builder(conf).numDataNodes(1).build();
    cluster.waitActive();
    dfs = cluster.getFileSystem();
    FsDatasetCache cm = ((FsDatasetImpl) dn().getFSDataset()).cacheManager;
    Field lf = FsDatasetCache.class.getDeclaredField("cacheLoader");
    lf.setAccessible(true);
    out("u3,instr,M=" + m + ",nativeAvailable=" + NativeIO.isAvailable() + ",pmdkAvailable="
        + NativeIO.POSIX.isPmdkAvailable() + ",loader=" + lf.get(cm).getClass().getName()
        + ",manipulator=" + NativeIO.POSIX.getCacheManipulator().getClass().getSimpleName()
        + ",dnCacheCapacity=" + dn().getFSDataset().getCacheCapacity() + ",pmem0="
        + new File(pmem0).getAbsolutePath());

    // background sampler: max CacheUsed and max on-disk bytes every 500 ms
    final AtomicLong maxUsed = new AtomicLong();
    final AtomicLong maxDisk = new AtomicLong();
    final AtomicLong samples = new AtomicLong();
    final AtomicBoolean stop = new AtomicBoolean();
    Thread sampler = new Thread(() -> {
      while (!stop.get()) {
        try {
          maxUsed.accumulateAndGet(dn().getFSDataset().getCacheUsed(), Math::max);
          maxDisk.accumulateAndGet(diskBytes(pmem0), Math::max);
          samples.incrementAndGet();
          Thread.sleep(500);
        } catch (Exception e) {
          // keep sampling
        }
      }
    });
    sampler.setDaemon(true);
    sampler.start();
    try {
      Path f1 = new Path("/f1");
      DFSTestUtil.createFile(dfs, f1, 16 * B, (short) 1, 0xFADEDL);
      dfs.addCachePool(new CachePoolInfo("p"));
      long t0 = System.currentTimeMillis();
      dfs.addCacheDirective(new CacheDirectiveInfo.Builder().setPool("p").setPath(f1).build());
      while (dn().getFSDataset().getNumBlocksCached() < expectF1
          && System.currentTimeMillis() - t0 < 30000) {
        Thread.sleep(500);
      }
      long reached = System.currentTimeMillis() - t0;
      Thread.sleep(5000);
      out(read("u3,f1,M=" + m) + ",waitMs=" + reached + ",nnReject="
          + count(REJ, crmCap.getOutput()) + ",nnAdded=" + count(ADDED, crmCap.getOutput())
          + ",couldNotReserve=" + count(NORES, dnCap.getOutput()) + ",noSpaceWarns="
          + count(NOSPACE, pvmCap.getOutput()));

      // (a) NameNode gate
      Path f2 = new Path("/f2");
      DFSTestUtil.createFile(dfs, f2, 4 * B, (short) 1, 0xBEEFL);
      List<LocatedBlock> lbs = DFSTestUtil.getAllBlocks(dfs, f2);
      long[] ids = new long[lbs.size()];
      StringBuilder idS = new StringBuilder();
      for (int i = 0; i < ids.length; i++) {
        ids[i] = lbs.get(i).getBlock().getBlockId();
        idS.append(i == 0 ? "" : ";").append(ids[i]);
      }
      int rejA0 = count(REJ, crmCap.getOutput());
      int addA0 = count(ADDED, crmCap.getOutput());
      dfs.addCacheDirective(new CacheDirectiveInfo.Builder().setPool("p").setPath(f2).build());
      Thread.sleep(10000);
      out(read("u3,a,M=" + m) + ",f2ids=" + idS + ",nnRejectDelta="
          + (count(REJ, crmCap.getOutput()) - rejA0) + ",nnAddedDelta="
          + (count(ADDED, crmCap.getOutput()) - addA0) + ",f2FilesOnDisk="
          + f2Files(ids));

      // (b) DataNode gate, NameNode bypassed
      String bpid = cluster.getNamesystem().getBlockPoolId();
      int dnLen = dnCap.getOutput().length();
      int pvmLen = pvmCap.getOutput().length();
      long failB0 = dn().getFSDataset().getNumBlocksFailedToCache();
      long usedB0 = dn().getFSDataset().getCacheUsed();
      dn().getFSDataset().cache(bpid, ids);
      Thread.sleep(5000);
      String dnNew = dnCap.getOutput().substring(dnLen);
      int refusalsF2 = 0;
      for (String line : dnNew.split("\n")) {
        if (NORES.matcher(line).find()) {
          for (long id : ids) {
            if (line.contains("Failed to cache " + id + "_" + bpid + ":")) {
              refusalsF2++;
            }
          }
        }
      }
      out(read("u3,b,M=" + m) + ",bpid=" + bpid + ",usedBefore=" + usedB0 + ",failedDelta="
          + (dn().getFSDataset().getNumBlocksFailedToCache() - failB0) + ",couldNotReserveNew="
          + count(NORES, dnNew) + ",couldNotReserveF2=" + refusalsF2 + ",noSpaceWarnsNew="
          + count(NOSPACE, pvmCap.getOutput().substring(pvmLen)) + ",f2FilesOnDisk="
          + f2Files(ids));
      for (String line : dnNew.split("\n")) {
        if (NORES.matcher(line).find()) {
          out("u3,b,line,M=" + m + "," + line.trim());
        }
      }
    } finally {
      stop.set(true);
      sampler.join(2000);
    }
    out("u3,max,M=" + m + ",maxCacheUsed=" + maxUsed.get() + ",maxDiskBytes=" + maxDisk.get()
        + ",samples=" + samples.get() + ",nnRejectTotal=" + count(REJ, crmCap.getOutput())
        + ",couldNotReserveTotal=" + count(NORES, dnCap.getOutput()));
  }

  private int f2Files(long[] ids) {
    int n = 0;
    List<File> stack = new ArrayList<>();
    stack.add(new File(pmem0));
    while (!stack.isEmpty()) {
      File d = stack.remove(stack.size() - 1);
      File[] l = d.listFiles();
      if (l == null) {
        continue;
      }
      for (File c : l) {
        if (c.isDirectory()) {
          stack.add(c);
        } else {
          for (long id : ids) {
            if (c.getName().equals(Long.toString(id))) {
              n++;
            }
          }
        }
      }
    }
    return n;
  }

  @Test
  public void u3aM32768() throws Exception {
    u3(32768, 8);
  }

  @Test
  public void u3bM65536() throws Exception {
    u3(65536, 16);
  }

  @Test
  public void u3cM131072() throws Exception {
    u3(131072, 16);
  }
}
