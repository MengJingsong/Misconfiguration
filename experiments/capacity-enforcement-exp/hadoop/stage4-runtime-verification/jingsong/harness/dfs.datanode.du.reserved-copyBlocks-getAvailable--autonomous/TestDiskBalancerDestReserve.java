/*
 * Stage-4 unit tier (B2, as amended 2026-11-25 by D1-1/D1-2) for
 * dfs.datanode.du.reserved-copyBlocks-getAvailable--autonomous (Jingsong queue order 26).
 * Not upstream code. Copied into a private source copy on the node; never into the repository.
 *
 * One test method per run (U0..U4), each with its own two MiniDFSClusters:
 * cluster 1 writes /f (64 x 1 MiB) and gathers every block on volume 0; cluster 2 restarts on the
 * same data with dfs.datanode.du.reserved = R (computed from the filesystem so that the destination's
 * headroom A0 hits the target), then a DiskBalancerMover over a spied dataset copies from volume 0 to
 * volume 1. The spy records dest.getAvailable() before every move (= the operand of the check at
 * DiskBalancer.java:1138, single-threaded, no writers).
 *
 * Output: lines starting with "O26," (CSV-like key=value) and "O26-BEGIN <run>" / "O26-END <run>"
 * markers, so the DiskBalancer log lines of each run can be separated. The test asserts only the setup
 * (B2e step 7: reservedSpace(dst) == R); every prediction is checked from the readings afterwards.
 */
package org.apache.hadoop.hdfs.server.diskbalancer;

import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.FileUtil;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.fs.StorageType;
import org.apache.hadoop.hdfs.DFSConfigKeys;
import org.apache.hadoop.hdfs.DFSTestUtil;
import org.apache.hadoop.hdfs.HdfsConfiguration;
import org.apache.hadoop.hdfs.MiniDFSCluster;
import org.apache.hadoop.hdfs.protocol.ExtendedBlock;
import org.apache.hadoop.hdfs.server.datanode.DataNode;
import org.apache.hadoop.hdfs.server.datanode.DiskBalancer.DiskBalancerMover;
import org.apache.hadoop.hdfs.server.datanode.DiskBalancer.VolumePair;
import org.apache.hadoop.hdfs.server.datanode.DiskBalancerWorkItem;
import org.apache.hadoop.hdfs.server.datanode.fsdataset.FsDatasetSpi;
import org.apache.hadoop.hdfs.server.datanode.fsdataset.FsVolumeSpi;
import org.apache.hadoop.test.GenericTestUtils;
import org.junit.Assert;
import org.junit.FixMethodOrder;
import org.junit.Test;
import org.junit.runners.MethodSorters;
import org.mockito.Mockito;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;

@FixMethodOrder(MethodSorters.NAME_ASCENDING)
public class TestDiskBalancerDestReserve {
  private static final Logger LOG =
      LoggerFactory.getLogger(TestDiskBalancerDestReserve.class);

  static final long MIB = 1L << 20;
  static final long BLK = MIB;                       // dfs.blocksize
  static final long META = 7 + 4 * (BLK / 512);      // 8199: header + CRC32C per 512-byte chunk
  static final long C = BLK + META;                  // 1056775
  static final long B = 40 * MIB;                    // 41943040

  @Test(timeout = 600000) public void u0() throws Exception { run("U0", B, -1L, 0); }
  @Test(timeout = 600000) public void u1() throws Exception { run("U1", B, 53039178L, 0); }
  @Test(timeout = 600000) public void u2() throws Exception { run("U2", B, 63606928L, 0); }
  @Test(timeout = 600000) public void u3() throws Exception { run("U3", B, 40886265L, 0); }
  @Test(timeout = 600000) public void u4() throws Exception { run("U4", 600000L, 800000L, 100); }

  private static void out(String s) {
    // System.out goes to the surefire -output.txt next to the log lines.
    System.out.println(s);
    System.out.flush();
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> volInfo(FsDatasetSpi<?> ds, String baseDir) {
    Map<String, Object> m = ds.getVolumeInfoMap();
    for (Map.Entry<String, Object> e : m.entrySet()) {
      if (new File(e.getKey()).getAbsolutePath().equals(baseDir)) {
        return (Map<String, Object>) e.getValue();
      }
    }
    throw new IllegalStateException("no volume info for " + baseDir + " in " + m);
  }

  private static long lv(Map<String, Object> m, String k) {
    return ((Number) m.get(k)).longValue();
  }

  private static FsVolumeSpi byId(FsDatasetSpi.FsVolumeReferences refs, String id) {
    for (FsVolumeSpi v : refs) {
      if (v.getStorageID().equals(id)) {
        return v;
      }
    }
    throw new IllegalStateException("no volume " + id);
  }

  private void run(final String label, final long bytesToCopy, final long a0Target,
      final int tolerance) throws Exception {
    out("O26-BEGIN " + label);
    HdfsConfiguration conf = new HdfsConfiguration();
    conf.setLong(DFSConfigKeys.DFS_BLOCK_SIZE_KEY, BLK);
    conf.setBoolean(DFSConfigKeys.DFS_DISK_BALANCER_ENABLED, true);
    conf.setLong(DFSConfigKeys.DFS_DISK_BALANCER_MAX_DISK_THROUGHPUT, 1000);
    conf.setLong(DFSConfigKeys.DFS_DISK_BALANCER_BLOCK_TOLERANCE, 10);
    conf.setLong(DFSConfigKeys.DFS_HEARTBEAT_INTERVAL_KEY, 1);
    conf.setLong("fs.du.interval", 3600000L);
    // D1-2: one fresh base dir per run, shared by cluster 1 and cluster 2.
    File base = new File(GenericTestUtils.getTestDir("o26"), label);
    FileUtil.fullyDelete(base);
    conf.set(MiniDFSCluster.HDFS_MINIDFS_BASEDIR, base.getAbsolutePath());
    StorageType[] types = new StorageType[] {StorageType.DISK, StorageType.DISK};

    String srcId;
    String dstId;
    String dstBase;
    long uDest;
    // ---- steps 2-4: cluster 1, write /f, gather on volume 0
    MiniDFSCluster c1 = new MiniDFSCluster.Builder(conf).numDataNodes(1)
        .storagesPerDatanode(2).storageTypes(types).build();
    try {
      c1.waitActive();
      FileSystem fs = c1.getFileSystem();
      DFSTestUtil.createFile(fs, new Path("/f"), 64L * MIB, (short) 1, 0L);
      DataNode dn = c1.getDataNodes().get(0);
      FsDatasetSpi<?> ds = dn.getFSDataset();
      try (FsDatasetSpi.FsVolumeReferences refs = ds.getFsVolumeReferences()) {
        DiskBalancerTestUtil.moveAllDataToDestVolume(ds, refs.get(1), refs.get(0));
        srcId = refs.get(0).getStorageID();
        dstId = refs.get(1).getStorageID();
        dstBase = new File(refs.get(1).getBaseURI()).getAbsolutePath();
        String srcBase = new File(refs.get(0).getBaseURI()).getAbsolutePath();
        Map<String, Object> vs = volInfo(ds, srcBase);
        Map<String, Object> vd = volInfo(ds, dstBase);
        uDest = lv(vd, "usedSpace");
        out("O26," + label + ",cluster1,srcId=" + srcId + ",dstId=" + dstId
            + ",srcBase=" + srcBase + ",dstBase=" + dstBase
            + ",srcUsed=" + lv(vs, "usedSpace") + ",srcBlocks=" + lv(vs, "numBlocks")
            + ",dstUsed=" + uDest + ",dstBlocks=" + lv(vd, "numBlocks"));
      }
    } finally {
      c1.shutdown(false);   // keep the data (MiniDFSCluster.java:2173)
    }

    // ---- step 5: compute R from the destination's filesystem
    File d = new File(dstBase);
    long total = d.getTotalSpace();
    long free = d.getFreeSpace();
    long usable = d.getUsableSpace();
    long g = free - usable;
    long r = a0Target < 0 ? 0L : total - g - uDest - a0Target;
    out("O26," + label + ",step5,total=" + total + ",free=" + free + ",usable=" + usable
        + ",g=" + g + ",uDest=" + uDest + ",a0Target=" + a0Target + ",R=" + r);
    conf.setLong(DFSConfigKeys.DFS_DATANODE_DU_RESERVED_KEY, r);

    // ---- steps 6-10: cluster 2 on the same data with the reserve
    MiniDFSCluster c2 = new MiniDFSCluster.Builder(conf).format(false).numDataNodes(1)
        .storagesPerDatanode(2).storageTypes(types).build();
    try {
      c2.waitActive();
      DataNode dn = c2.getDataNodes().get(0);
      final FsDatasetSpi<?> real = dn.getFSDataset();
      try (FsDatasetSpi.FsVolumeReferences refs = real.getFsVolumeReferences()) {
        FsVolumeSpi src = byId(refs, srcId);
        final FsVolumeSpi dst = byId(refs, dstId);
        String srcBase = new File(src.getBaseURI()).getAbsolutePath();
        Map<String, Object> vs0 = volInfo(real, srcBase);
        Map<String, Object> vd0 = volInfo(real, dstBase);
        long reservedDst = lv(vd0, "reservedSpace");
        long a0 = dst.getAvailable();
        long used0 = lv(vd0, "usedSpace");
        final long gNow = d.getFreeSpace() - d.getUsableSpace();
        final long totalNow = d.getTotalSpace();
        final long rr = r;
        long h0 = totalNow - gNow - r - used0;
        out("O26," + label + ",step7,reservedDst=" + reservedDst + ",R=" + r
            + ",reservedSrc=" + lv(vs0, "reservedSpace") + ",A0=" + a0 + ",usedDst0=" + used0
            + ",freeSpaceDst0=" + lv(vd0, "freeSpace") + ",H0=" + h0
            + ",rfrDst0=" + lv(vd0, "reservedSpaceForReplicas")
            + ",dstBlocks0=" + lv(vd0, "numBlocks") + ",srcBlocks0=" + lv(vs0, "numBlocks")
            + ",srcUsed0=" + lv(vs0, "usedSpace") + ",total=" + totalNow + ",g=" + gNow);
        Assert.assertEquals("reserve did not reach the destination volume", r, reservedDst);

        // step 8: spy records the operand before each move, then does the real move
        final List<Long> preAvail = new ArrayList<>();
        final List<Long> preH = new ArrayList<>();
        final List<Long> blkLen = new ArrayList<>();
        final FsDatasetSpi<?> spy = Mockito.spy(real);
        doAnswer(inv -> {
          ExtendedBlock blk = (ExtendedBlock) inv.getArguments()[0];
          FsVolumeSpi v = (FsVolumeSpi) inv.getArguments()[1];
          preAvail.add(v.getAvailable());
          long u = lv(volInfo(real, dstBase), "usedSpace");
          preH.add(totalNow - gNow - rr - u);
          blkLen.add(blk.getNumBytes());
          real.moveBlockAcrossVolumes(blk, v);
          return null;
        }).when(spy).moveBlockAcrossVolumes(any(ExtendedBlock.class), any(FsVolumeSpi.class));

        DiskBalancerMover mover = new DiskBalancerMover(spy, conf);
        mover.setRunnable();
        DiskBalancerWorkItem item = new DiskBalancerWorkItem(bytesToCopy, 0);
        if (tolerance > 0) {
          item.setTolerancePercent(tolerance);
        }
        VolumePair pair = new VolumePair(srcId, src.getBaseURI().getPath(),
            dstId, dst.getBaseURI().getPath());
        long t0 = System.currentTimeMillis();
        mover.copyBlocks(pair, item);
        long t1 = System.currentTimeMillis();

        // step 9: readings
        Map<String, Object> vd1 = volInfo(real, dstBase);
        Map<String, Object> vs1 = volInfo(real, srcBase);
        long used1 = lv(vd1, "usedSpace");
        long h1 = d.getTotalSpace() - (d.getFreeSpace() - d.getUsableSpace()) - r - used1;
        long nPred = Math.min(37L, Math.max(0L,
            (long) Math.ceil((double) (a0 - bytesToCopy) / (double) C)));
        if (a0Target < 0) {
          nPred = 37L;
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < preAvail.size(); i++) {
          out("O26," + label + ",move," + (i + 1) + ",preAvail=" + preAvail.get(i)
              + ",preH=" + preH.get(i) + ",blockLen=" + blkLen.get(i)
              + ",dAvail=" + (i == 0 ? 0 : preAvail.get(i - 1) - preAvail.get(i))
              + ",gtB=" + (preAvail.get(i) > bytesToCopy));
        }
        out("O26," + label + ",result,B=" + bytesToCopy + ",tol=" + tolerance
            + ",blocksCopied=" + item.getBlocksCopied() + ",bytesCopied=" + item.getBytesCopied()
            + ",errMsg=" + item.getErrMsg() + ",errorCount=" + item.getErrorCount()
            + ",moves=" + preAvail.size() + ",A0=" + a0 + ",nPredFromA0=" + nPred
            + ",usedDst0=" + used0 + ",usedDst1=" + used1 + ",dUsed=" + (used1 - used0)
            + ",freeSpaceDst1=" + lv(vd1, "freeSpace") + ",Afinal=" + dst.getAvailable()
            + ",H1=" + h1 + ",dstBlocks1=" + lv(vd1, "numBlocks")
            + ",srcBlocks1=" + lv(vs1, "numBlocks") + ",Bminusc=" + (bytesToCopy - C)
            + ",c=" + C + ",ms=" + (t1 - t0));
      }
    } finally {
      c2.shutdown(true);
      out("O26-END " + label);
    }
  }
}
