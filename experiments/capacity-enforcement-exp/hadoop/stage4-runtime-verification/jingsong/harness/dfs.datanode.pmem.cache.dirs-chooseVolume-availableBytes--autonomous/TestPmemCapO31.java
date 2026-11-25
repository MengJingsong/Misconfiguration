/*
 * Stage-4 unit tier for capacity-enforcement-exp Hadoop order 31
 * (dfs.datanode.pmem.cache.dirs-chooseVolume-availableBytes--autonomous), case file B2 with amendments A1-A4.
 * Not upstream code. Every reading is printed as one "O31,<tag>,k=v,..." line before it is asserted.
 */
package org.apache.hadoop.hdfs.server.datanode.fsdataset.impl;

import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_DATANODE_FSDATASETCACHE_MAX_THREADS_PER_VOLUME_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_DATANODE_PMEM_CACHE_DIRS_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_DATANODE_PMEM_CACHE_RECOVERY_KEY;
import static org.apache.hadoop.test.MetricsAsserts.getLongCounter;
import static org.apache.hadoop.test.MetricsAsserts.getMetrics;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.commons.io.FileUtils;
import org.apache.commons.io.filefilter.TrueFileFilter;
import org.apache.hadoop.conf.Configuration;
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
import org.apache.hadoop.hdfs.protocol.DatanodeInfo;
import org.apache.hadoop.hdfs.server.datanode.DataNode;
import org.apache.hadoop.io.nativeio.NativeIO;
import org.apache.hadoop.io.nativeio.NativeIO.POSIX.CacheManipulator;
import org.apache.hadoop.io.nativeio.NativeIO.POSIX.NoMlockCacheManipulator;
import org.apache.hadoop.test.GenericTestUtils.LogCapturer;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class TestPmemCapO31 {
  private static final Logger LOG = LoggerFactory.getLogger(TestPmemCapO31.class);
  private static final String BASE = MiniDFSCluster.getBaseDirectory() + "o31/";
  private static final String REFUSAL = "There is no enough persistent memory space";
  private static final Pattern MAXAVAIL =
      Pattern.compile("max available space is (\\d+), but (\\d+)is required");

  private static void out(String s) {
    System.out.println("O31," + s);
    System.out.flush();
  }

  @Before
  public void before() {
    PmemVolumeManager.reset();
    PmemVolumeManager.setMaxBytes(-1);
  }

  @After
  public void after() {
    PmemVolumeManager.reset();
    PmemVolumeManager.setMaxBytes(-1);
  }

  private static String[] freshDirs(String method, int n) throws IOException {
    File m = new File(BASE + method);
    FileUtils.deleteDirectory(m);
    String[] d = new String[n];
    for (int i = 0; i < n; i++) {
      File f = new File(m, "pmem" + i);
      assertTrue(f.mkdirs());
      d[i] = f.getAbsolutePath();
    }
    return d;
  }

  /** Per-volume [used, max] read from the private UsedBytesCount list by reflection. */
  private static long[][] usedMax(PmemVolumeManager mgr) throws Exception {
    Field f = PmemVolumeManager.class.getDeclaredField("usedBytesCounts");
    f.setAccessible(true);
    List<?> l = (List<?>) f.get(mgr);
    long[][] r = new long[l.size()][2];
    for (int i = 0; i < l.size(); i++) {
      Object c = l.get(i);
      Method u = c.getClass().getDeclaredMethod("getUsedBytes");
      Method m = c.getClass().getDeclaredMethod("getMaxBytes");
      u.setAccessible(true);
      m.setAccessible(true);
      r[i][0] = (Long) u.invoke(c);
      r[i][1] = (Long) m.invoke(c);
    }
    return r;
  }

  private static String fmt(long[][] um) {
    StringBuilder used = new StringBuilder(), max = new StringBuilder();
    for (int i = 0; i < um.length; i++) {
      used.append(i == 0 ? "" : "/").append(um[i][0]);
      max.append(i == 0 ? "" : "/").append(um[i][1]);
    }
    return "usedPerVol=" + used + ",maxPerVol=" + max;
  }

  private static int[] perVolCount(PmemVolumeManager mgr, int n) {
    int[] c = new int[n];
    for (Byte b : mgr.getBlockKeyToVolume().values()) {
      c[b]++;
    }
    return c;
  }

  // ---------------------------------------------------------------- U1
  @Test(timeout = 60000)
  public void u1Direct() throws Exception {
    long[][] pairs = {{65536, 4096}, {65536, 12288}, {131072, 4096}, {131072, 12288}};
    long[][] expect = {{32, 131072, 16, 0}, {10, 122880, 5, 4096}, {64, 262144, 32, 0},
        {20, 245760, 10, 8192}};
    for (int p = 0; p < pairs.length; p++) {
      long m = pairs[p][0], b = pairs[p][1];
      PmemVolumeManager.reset();
      PmemVolumeManager.setMaxBytes(m);
      String[] dirs = freshDirs("u1_" + m + "_" + b, 2);
      PmemVolumeManager.init(dirs, false);
      PmemVolumeManager mgr = PmemVolumeManager.getInstance();
      int ok = 0;
      for (long i = 1; i < 10000; i++) {
        long r = mgr.reserve(new ExtendedBlockId(i, "BP-o31"), b);
        if (r == -1) {
          break;
        }
        ok++;
      }
      String msg = "none";
      try {
        mgr.chooseVolume(b);
      } catch (IOException e) {
        msg = e.getMessage();
      }
      int[] pv = perVolCount(mgr, 2);
      long[][] um = usedMax(mgr);
      out("U1,M=" + m + ",B=" + b + ",reserves=" + ok + ",cacheUsed=" + mgr.getCacheUsed()
          + ",cacheCapacity=" + mgr.getCacheCapacity() + ",keysPerVol=" + pv[0] + "/" + pv[1]
          + "," + fmt(um) + ",msg=" + msg);
      // B2f
      assertEquals(expect[p][0], ok);
      assertEquals(expect[p][1], mgr.getCacheUsed());
      assertEquals(expect[p][2], pv[0]);
      assertEquals(expect[p][2], pv[1]);
      for (long[] v : um) {
        assertTrue("used > max", v[0] <= v[1]);
      }
      assertTrue(msg, msg.contains("max available space is " + expect[p][3] + ", but " + b
          + "is required"));
      PmemVolumeManager.reset();
    }
  }

  // ---------------------------------------------------------------- U1-real
  @Test(timeout = 60000)
  public void u1Real() throws Exception {
    PmemVolumeManager.setMaxBytes(-1);
    String[] dirs = freshDirs("u1real", 2);
    PmemVolumeManager.init(dirs, false);
    long s0 = new File(PmemVolumeManager.getRealPmemDir(dirs[0])).getUsableSpace();
    long s1 = new File(PmemVolumeManager.getRealPmemDir(dirs[1])).getUsableSpace();
    PmemVolumeManager mgr = PmemVolumeManager.getInstance();
    long cap = mgr.getCacheCapacity();
    long[][] um = usedMax(mgr);
    out("U1REAL,cacheCapacity=" + cap + ",usable0=" + s0 + ",usable1=" + s1 + ",sumUsable="
        + (s0 + s1) + ",diff=" + (cap - (s0 + s1)) + ",cacheUsed=" + mgr.getCacheUsed() + ","
        + fmt(um));
    assertEquals(0, mgr.getCacheUsed());
    assertTrue("diff beyond 1 MiB", Math.abs(cap - (s0 + s1)) <= 1048576);
  }

  // ---------------------------------------------------------------- U2
  private static long fileBytes(File dir) {
    if (!dir.exists()) {
      return 0;
    }
    long s = 0;
    Collection<File> fs = FileUtils.listFiles(dir, TrueFileFilter.INSTANCE, TrueFileFilter.INSTANCE);
    for (File f : fs) {
      if (f.isFile()) {
        s += f.length();
      }
    }
    return s;
  }

  private static int countFiles(File dir) {
    if (!dir.exists()) {
      return 0;
    }
    int n = 0;
    for (File f : FileUtils.listFiles(dir, TrueFileFilter.INSTANCE, TrueFileFilter.INSTANCE)) {
      if (f.isFile()) {
        n++;
      }
    }
    return n;
  }

  private static int countOcc(String s, String needle) {
    int n = 0, i = 0;
    while ((i = s.indexOf(needle, i)) >= 0) {
      n++;
      i += needle.length();
    }
    return n;
  }

  private void runU2(String tag, long maxPerVol, int expBlocks, long expUsed, long expPerVol)
      throws Exception {
    PmemVolumeManager.setMaxBytes(maxPerVol);
    String[] dirs = freshDirs(tag, 2);
    Configuration conf = new HdfsConfiguration();
    conf.setLong(DFSConfigKeys.DFS_NAMENODE_PATH_BASED_CACHE_REFRESH_INTERVAL_MS, 100);
    conf.setLong(DFSConfigKeys.DFS_CACHEREPORT_INTERVAL_MSEC_KEY, 500);
    conf.setLong(DFSConfigKeys.DFS_BLOCK_SIZE_KEY, 4096);
    conf.setLong(DFSConfigKeys.DFS_HEARTBEAT_INTERVAL_KEY, 1);
    conf.setInt(DFS_DATANODE_FSDATASETCACHE_MAX_THREADS_PER_VOLUME_KEY, 10);
    conf.set(DFS_DATANODE_PMEM_CACHE_DIRS_KEY, dirs[0] + "," + dirs[1]);
    conf.setBoolean(DFS_DATANODE_PMEM_CACHE_RECOVERY_KEY, false);
    CacheManipulator prev = NativeIO.POSIX.getCacheManipulator();
    NativeIO.POSIX.setCacheManipulator(new NoMlockCacheManipulator());
    LogCapturer pvmLog = LogCapturer.captureLogs(LoggerFactory.getLogger(PmemVolumeManager.class));
    LogCapturer cacheLog = LogCapturer.captureLogs(LoggerFactory.getLogger(FsDatasetCache.class));
    MiniDFSCluster cluster = null;
    try {
      cluster = new MiniDFSCluster.Builder(conf).numDataNodes(1).build();
      cluster.waitActive();
      DistributedFileSystem fs = cluster.getFileSystem();
      DataNode dn = cluster.getDataNodes().get(0);
      FsDatasetCache cm = ((FsDatasetImpl) dn.getFSDataset()).cacheManager;
      Field lf = FsDatasetCache.class.getDeclaredField("cacheLoader");
      lf.setAccessible(true);
      String loader = lf.get(cm).getClass().getName();
      String bpid = cluster.getNamesystem().getBlockPoolId();
      PmemVolumeManager mgr = PmemVolumeManager.getInstance();
      out("U2INSTR," + tag + ",loader=" + loader + ",dnCacheCapacity=" + cm.getCacheCapacity()
          + "," + fmt(usedMax(mgr)) + ",bpid=" + bpid);
      Path p = new Path("/o31");
      DFSTestUtil.createFile(fs, p, 24 * 4096, (short) 1, 0xbeef);
      fs.addCachePool(new CachePoolInfo("o31"));
      long t0 = System.currentTimeMillis();
      fs.addCacheDirective(new CacheDirectiveInfo.Builder().setPath(p).setPool("o31")
          .setReplication((short) 1).build());
      long lastN = -1, lastU = -1, lastChange = t0, maxUsed = 0;
      boolean settled = false;
      while (true) {
        Thread.sleep(500);
        long now = System.currentTimeMillis();
        long n = cm.getNumBlocksCached(), u = cm.getCacheUsed();
        maxUsed = Math.max(maxUsed, u);
        if (n != lastN || u != lastU) {
          lastN = n;
          lastU = u;
          lastChange = now;
        }
        out("U2POLL," + tag + ",t=" + (now - t0) + ",numBlocksCached=" + n + ",cacheUsed=" + u
            + ",failed=" + cm.getNumBlocksFailedToCache() + ",refusals="
            + countOcc(pvmLog.getOutput(), REFUSAL));
        if (now - lastChange >= 20000 && now - t0 >= 35000) {
          settled = true;
          break;
        }
        if (now - t0 >= 90000) {
          break;
        }
      }
      long blocksCachedMetric = getLongCounter("BlocksCached", getMetrics(dn.getMetrics().name()));
      String pvm = pvmLog.getOutput(), cl = cacheLog.getOutput();
      int refusals = countOcc(pvm, REFUSAL);
      TreeMap<String, Integer> vals = new TreeMap<>();
      Matcher mt = MAXAVAIL.matcher(pvm);
      while (mt.find()) {
        vals.merge(mt.group(1) + "/" + mt.group(2), 1, Integer::sum);
      }
      int couldNot = countOcc(cl, "could not reserve");
      long[] fb = new long[2];
      int[] fc = new int[2];
      for (int i = 0; i < 2; i++) {
        File d = new File(PmemVolumeManager.getRealPmemDir(dirs[i]), bpid);
        fb[i] = fileBytes(d);
        fc[i] = countFiles(d);
      }
      long[][] um = usedMax(mgr);
      int[] pv = perVolCount(mgr, 2);
      long bc = -1, bn = -1;
      RemoteIterator<CacheDirectiveEntry> it = fs.listCacheDirectives(null);
      while (it.hasNext()) {
        CacheDirectiveEntry e = it.next();
        bc = e.getStats().getBytesCached();
        bn = e.getStats().getBytesNeeded();
      }
      DatanodeInfo[] di = fs.getDataNodeStats();
      out("U2," + tag + ",maxPerVol=" + maxPerVol + ",settled=" + settled + ",settleMs="
          + (System.currentTimeMillis() - t0) + ",numBlocksCached=" + cm.getNumBlocksCached()
          + ",BlocksCachedMetric=" + blocksCachedMetric + ",cacheUsed=" + cm.getCacheUsed()
          + ",maxCacheUsed=" + maxUsed + ",cacheCapacity=" + cm.getCacheCapacity()
          + ",numBlocksFailedToCache=" + cm.getNumBlocksFailedToCache() + ",fileBytes="
          + fb[0] + "/" + fb[1] + ",files=" + fc[0] + "/" + fc[1] + ",keysPerVol=" + pv[0] + "/"
          + pv[1] + "," + fmt(um) + ",refusalLines=" + refusals + ",refusalValues=" + vals
          + ",couldNotReserveLines=" + couldNot + ",bytesCached=" + bc + ",bytesNeeded=" + bn
          + ",nnCacheCapacity=" + di[0].getCacheCapacity() + ",nnCacheUsed=" + di[0].getCacheUsed());
      // dump the first refusal lines for the record
      int shown = 0;
      for (String line : pvm.split("\n")) {
        if (line.contains(REFUSAL) && shown++ < 3) {
          out("U2REFUSAL," + tag + "," + line.trim());
        }
      }
      fs.removeCacheDirective(fs.listCacheDirectives(null).next().getInfo().getId());
      // B2f assertions (A4 tier rule is applied in the results file, not here)
      for (int i = 0; i < 2; i++) {
        assertTrue("used > max", um[i][0] <= um[i][1]);
        assertTrue("file bytes > max", fb[i] <= um[i][1]);
      }
      assertEquals(expBlocks, cm.getNumBlocksCached());
      assertEquals(expUsed, cm.getCacheUsed());
      assertEquals(expPerVol, fb[0]);
      assertEquals(expPerVol, fb[1]);
    } finally {
      pvmLog.stopCapturing();
      cacheLog.stopCapturing();
      if (cluster != null) {
        cluster.shutdown();
      }
      NativeIO.POSIX.setCacheManipulator(prev);
    }
  }

  @Test(timeout = 180000)
  public void u2Fragmented() throws Exception {
    runU2("u2frag", 30720, 14, 57344, 28672);
  }

  @Test(timeout = 180000)
  public void u2Control() throws Exception {
    runU2("u2ctrl", 32768, 16, 65536, 32768);
  }

  // ---------------------------------------------------------------- U3
  private static void write4k(String path) throws IOException {
    try (FileOutputStream o = new FileOutputStream(path)) {
      o.write(new byte[4096]);
    }
  }

  @Test(timeout = 60000)
  public void u3CancelOrder() throws Exception {
    PmemVolumeManager.setMaxBytes(65536);
    String[] dirs = freshDirs("u3", 1);
    PmemVolumeManager.init(dirs, false);
    PmemVolumeManager mgr = PmemVolumeManager.getInstance();
    LogCapturer blk = LogCapturer.captureLogs(LoggerFactory.getLogger(PmemMappedBlock.class));
    try {
      // cancel order (FsDatasetCache.java:479-484): release, then close
      ExtendedBlockId k = new ExtendedBlockId(1, "BP-o31");
      long r = mgr.reserve(k, 4096);
      String path = mgr.getCachePath(k);
      write4k(path);
      PmemMappedBlock b = new PmemMappedBlock(4096, k);
      mgr.release(k, 4096);
      b.close();
      File f = new File(path);
      String log1 = blk.getOutput();
      boolean warn = log1.contains("Failed to delete the mapped File: null");
      out("U3CANCEL,reserve=" + r + ",path=" + path + ",cacheUsedAfter=" + mgr.getCacheUsed()
          + ",fileExists=" + f.exists() + ",fileLength=" + f.length() + ",warnNull=" + warn);
      // uncache order (FsDatasetCache.java:558-563): close, then release
      ExtendedBlockId k2 = new ExtendedBlockId(2, "BP-o31");
      long r2 = mgr.reserve(k2, 4096);
      String path2 = mgr.getCachePath(k2);
      write4k(path2);
      new PmemMappedBlock(4096, k2).close();
      mgr.release(k2, 4096);
      File f2 = new File(path2);
      out("U3UNCACHE,reserve=" + r2 + ",path=" + path2 + ",cacheUsedAfter=" + mgr.getCacheUsed()
          + ",fileExists=" + f2.exists() + ",realBytesOnVolume="
          + fileBytes(new File(PmemVolumeManager.getRealPmemDir(dirs[0]))));
      assertEquals(0, mgr.getCacheUsed());
      assertTrue(f.exists());
      assertEquals(4096, f.length());
      assertTrue(warn);
      assertFalse(f2.exists());
    } finally {
      blk.stopCapturing();
    }
  }
}
