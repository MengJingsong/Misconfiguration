/*
 * Stage-4 harness, capacity-enforcement-exp, Hadoop queue order 29 (Jingsong):
 * dfs.datanode.reserve-for-archive.default.percentage-getVolumeByMount-getAvailable--autonomous
 * Unit tier B2 with amendments D1-1..D1-4. Not upstream code.
 * Every reading is printed on a line starting with "O29,".
 */
package org.apache.hadoop.hdfs.server.datanode.fsdataset.impl;

import java.io.File;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.fs.StorageType;
import org.apache.hadoop.hdfs.DFSConfigKeys;
import org.apache.hadoop.hdfs.DFSTestUtil;
import org.apache.hadoop.hdfs.HdfsConfiguration;
import org.apache.hadoop.hdfs.MiniDFSCluster;
import org.apache.hadoop.hdfs.protocol.ExtendedBlock;
import org.apache.hadoop.hdfs.server.datanode.DataNode;
import org.apache.hadoop.hdfs.server.datanode.fsdataset.FsDatasetSpi;
import org.apache.hadoop.hdfs.server.datanode.fsdataset.FsVolumeReference;
import org.apache.hadoop.hdfs.server.datanode.fsdataset.FsVolumeSpi;
import org.apache.hadoop.metrics2.MetricsRecordBuilder;
import org.apache.hadoop.test.MetricsAsserts;
import org.junit.Assert;
import org.junit.Test;

public class TestArchiveSameMountCap {
  static final long C = 128L << 20;
  static final long BS = 1L << 20;
  static final int N = 40;

  static void out(String s) {
    System.out.println("O29," + s);
    System.out.flush();
  }

  static long blkBytes(File dir) {
    long s = 0;
    File[] fs = dir.listFiles();
    if (fs == null) {
      return 0;
    }
    for (File f : fs) {
      if (f.isDirectory()) {
        s += blkBytes(f);
      } else if (f.getName().startsWith("blk_")) {
        s += f.length();
      }
    }
    return s;
  }

  static int blkCount(File dir) {
    int n = 0;
    File[] fs = dir.listFiles();
    if (fs == null) {
      return 0;
    }
    for (File f : fs) {
      if (f.isDirectory()) {
        n += blkCount(f);
      } else if (f.getName().startsWith("blk_") && !f.getName().endsWith(".meta")) {
        n++;
      }
    }
    return n;
  }

  static long counter(DataNode dn, String name) {
    MetricsRecordBuilder rb = MetricsAsserts.getMetrics(dn.getMetrics().name());
    return MetricsAsserts.getLongCounter(name, rb);
  }

  void run(String tag, double r, boolean tiering, int threads) throws Exception {
    Configuration conf = new HdfsConfiguration();
    conf.setBoolean(DFSConfigKeys.DFS_DATANODE_ALLOW_SAME_DISK_TIERING, tiering);
    conf.setDouble(DFSConfigKeys.DFS_DATANODE_RESERVE_FOR_ARCHIVE_DEFAULT_PERCENTAGE, r);
    conf.setLong(DFSConfigKeys.DFS_BLOCK_SIZE_KEY, BS);
    conf.setLong(DFSConfigKeys
        .DFS_DATANODE_ROUND_ROBIN_VOLUME_CHOOSING_POLICY_ADDITIONAL_AVAILABLE_SPACE_KEY, 0L);
    out(tag + ",config,r=" + r + ",tiering=" + tiering + ",threads=" + threads
        + ",baseDir=" + MiniDFSCluster.getBaseDirectory()
        + ",maxHeap=" + Runtime.getRuntime().maxMemory());
    MiniDFSCluster cl = new MiniDFSCluster.Builder(conf).numDataNodes(1)
        .storagesPerDatanode(2)
        .storageTypes(new StorageType[]{StorageType.DISK, StorageType.ARCHIVE})
        .storageCapacities(new long[]{C, C}).build();
    try {
      cl.waitActive();
      FileSystem fs = cl.getFileSystem();
      DataNode dn = cl.getDataNodes().get(0);
      FsDatasetImpl ds = (FsDatasetImpl) dn.getFSDataset();
      FsVolumeImpl arch = null;
      FsVolumeImpl disk = null;
      try (FsDatasetSpi.FsVolumeReferences refs = ds.getFsVolumeReferences()) {
        for (FsVolumeSpi v : refs) {
          if (v.getStorageType() == StorageType.ARCHIVE) {
            arch = (FsVolumeImpl) v;
          } else if (v.getStorageType() == StorageType.DISK) {
            disk = (FsVolumeImpl) v;
          }
        }
      }
      Assert.assertNotNull(arch);
      Assert.assertNotNull(disk);
      Field vf = FsDatasetImpl.class.getDeclaredField("volumes");
      vf.setAccessible(true);
      FsVolumeList vlist = (FsVolumeList) vf.get(ds);
      boolean sameMount = disk.getMount().equals(arch.getMount());
      boolean hasMount = ds.getMountVolumeMap() != null && ds.getMountVolumeMap().hasMount(arch.getMount());
      File archCur = new File(arch.getBaseURI().getPath(), "current");
      File diskCur = new File(disk.getBaseURI().getPath(), "current");
      out(tag + ",sanity,diskMount=" + disk.getMount() + ",archMount=" + arch.getMount()
          + ",sameMount=" + sameMount + ",hasMount=" + hasMount
          + ",archCapacity=" + arch.getCapacity() + ",expectedArchCapacity=" + (tiering ? (long) (C * r) : C)
          + ",diskCapacity=" + disk.getCapacity()
          + ",archDir=" + archCur + ",diskDir=" + diskCur
          + ",archDfsUsed0=" + arch.getDfsUsed() + ",diskDfsUsed0=" + disk.getDfsUsed()
          + ",archAvailable0=" + arch.getAvailable() + ",archDfAvailable=" + arch.getDfAvailable());

      List<ExtendedBlock> blocks = new ArrayList<>();
      for (int i = 0; i < N; i++) {
        Path p = new Path("/f" + i);
        DFSTestUtil.createFile(fs, p, 4096, BS, BS, (short) 1, i);
        blocks.add(DFSTestUtil.getFirstBlock(fs, p));
      }
      out(tag + ",written,files=" + N + ",diskDfsUsed=" + disk.getDfsUsed()
          + ",diskBlkBytes=" + blkBytes(diskCur) + ",diskBlkCount=" + blkCount(diskCur)
          + ",archDfsUsed=" + arch.getDfsUsed() + ",archAvailable=" + arch.getAvailable()
          + ",sameMountOps=" + counter(dn, "ReplaceBlockOpOnSameMount")
          + ",sameHostOps=" + counter(dn, "ReplaceBlockOpOnSameHost"));

      int moved = 0;
      int refused = 0;
      int probeMismatch = 0;
      if (threads <= 1) {
        for (int k = 0; k < N; k++) {
          ExtendedBlock b = blocks.get(k);
          long availBefore = arch.getAvailable();
          String probe = "skip";
          if (tiering) {
            FsVolumeReference pr = vlist.getVolumeByMount(StorageType.ARCHIVE,
                disk.getMount(), b.getNumBytes());
            probe = pr == null ? "null" : "pass";
            if (pr != null) {
              pr.close();
            }
          }
          long sm0 = counter(dn, "ReplaceBlockOpOnSameMount");
          String outcome;
          try {
            ds.moveBlockAcrossStorage(b, StorageType.ARCHIVE, null);
            moved++;
            outcome = "moved";
          } catch (Exception e) {
            refused++;
            outcome = "refused:" + e.getClass().getSimpleName() + ":"
                + String.valueOf(e.getMessage()).replace(',', ';');
          }
          long sm1 = counter(dn, "ReplaceBlockOpOnSameMount");
          if (tiering && (("pass".equals(probe)) != outcome.equals("moved"))) {
            probeMismatch++;
          }
          out(tag + ",move,k=" + k + ",blockBytes=" + b.getNumBytes() + ",availBefore=" + availBefore
              + ",probe=" + probe + ",outcome=" + outcome + ",sameMountDelta=" + (sm1 - sm0)
              + ",archDfsUsed=" + arch.getDfsUsed() + ",archBlkBytes=" + blkBytes(archCur)
              + ",archAvailable=" + arch.getAvailable());
        }
      } else {
        final ExecutorService ex = Executors.newFixedThreadPool(threads);
        final CountDownLatch go = new CountDownLatch(1);
        final AtomicInteger okN = new AtomicInteger();
        final AtomicInteger badN = new AtomicInteger();
        final FsDatasetImpl fds = ds;
        List<Future<?>> fs2 = new ArrayList<>();
        for (final ExtendedBlock b : blocks) {
          fs2.add(ex.submit(() -> {
            go.await();
            try {
              fds.moveBlockAcrossStorage(b, StorageType.ARCHIVE, null);
              okN.incrementAndGet();
            } catch (Exception e) {
              badN.incrementAndGet();
              out(tag + ",crefused," + e.getClass().getSimpleName() + ":"
                  + String.valueOf(e.getMessage()).replace(',', ';'));
            }
            return null;
          }));
        }
        go.countDown();
        for (Future<?> f : fs2) {
          f.get(120, TimeUnit.SECONDS);
        }
        ex.shutdown();
        moved = okN.get();
        refused = badN.get();
      }
      long archUsed = arch.getDfsUsed();
      long archBytes = blkBytes(archCur);
      out(tag + ",summary,r=" + r + ",tiering=" + tiering + ",T=" + threads + ",moved=" + moved
          + ",refused=" + refused + ",archDfsUsed=" + archUsed + ",archBlkBytes=" + archBytes
          + ",archBlkCount=" + blkCount(archCur) + ",diskBlkCount=" + blkCount(diskCur)
          + ",archCapacity=" + arch.getCapacity() + ",archAvailable=" + arch.getAvailable()
          + ",delta=" + (archUsed - archBytes)
          + ",sameMountOps=" + counter(dn, "ReplaceBlockOpOnSameMount")
          + ",sameHostOps=" + counter(dn, "ReplaceBlockOpOnSameHost")
          + ",probeMismatch=" + probeMismatch + ",sameMount=" + sameMount + ",hasMount=" + hasMount);
      if (tiering) {
        Assert.assertTrue("volumes not on the same mount", sameMount && hasMount);
      }
    } finally {
      cl.shutdown(true, true);
    }
  }

  @Test(timeout = 300000) public void r000() throws Exception { run("r000", 0.0, true, 1); }
  @Test(timeout = 300000) public void r010() throws Exception { run("r010", 0.1, true, 1); }
  @Test(timeout = 300000) public void r025() throws Exception { run("r025", 0.25, true, 1); }
  @Test(timeout = 300000) public void r050() throws Exception { run("r050", 0.5, true, 1); }
  @Test(timeout = 300000) public void controlTieringOff() throws Exception { run("ctl", 0.1, false, 1); }
  @Test(timeout = 300000) public void concurrentR010() throws Exception { run("c010", 0.1, true, 8); }
}
