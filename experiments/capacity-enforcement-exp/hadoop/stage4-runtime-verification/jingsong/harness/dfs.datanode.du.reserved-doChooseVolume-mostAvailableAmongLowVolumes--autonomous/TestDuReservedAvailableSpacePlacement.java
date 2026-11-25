package org.apache.hadoop.hdfs.server.datanode.fsdataset.impl;

// Stage-4 harness, order 27: the B2d test source of the case file, with amendment D1-2
// (columns rfr0,rfr1 = getReservedForReplicas() before each step). Nothing else changed.

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import java.io.File;
import java.util.*;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.DF;
import org.apache.hadoop.fs.FileSystemTestHelper;
import org.apache.hadoop.fs.StorageType;
import org.apache.hadoop.hdfs.DFSConfigKeys;
import org.apache.hadoop.hdfs.server.common.Storage.StorageDirectory;
import org.apache.hadoop.hdfs.server.datanode.BlockScanner;
import org.apache.hadoop.hdfs.server.datanode.StorageLocation;
import org.apache.hadoop.hdfs.server.datanode.fsdataset.*;
import org.apache.hadoop.test.GenericTestUtils;
import org.apache.hadoop.util.DiskChecker.DiskOutOfSpaceException;
import org.apache.hadoop.util.ReflectionUtils;
import org.junit.Test;
import org.slf4j.LoggerFactory;

public class TestDuReservedAvailableSpacePlacement {
  static final long MiB = 1L << 20, B = 100 * MiB, C0 = 1024 * MiB, C1 = 3072 * MiB;

  private FsVolumeImpl vol(Configuration conf, String base, String name, long cap) throws Exception {
    File d = new File(base, name); d.mkdirs();
    DF df = mock(DF.class);
    when(df.getCapacity()).thenReturn(cap);
    when(df.getUsed()).thenReturn(0L);
    when(df.getAvailable()).thenReturn(cap);
    return new FsVolumeImplBuilder().setConf(conf).setDataset(mock(FsDatasetImpl.class))
        .setStorageID("sid-" + name)
        .setStorageDirectory(new StorageDirectory(StorageLocation.parse(d.getPath())))
        .setUsage(df).build();
  }

  private void run(String tag, long reserved, float f, long threshold) throws Exception {
    GenericTestUtils.setLogLevel(LoggerFactory.getLogger(AvailableSpaceVolumeChoosingPolicy.class),
        org.slf4j.event.Level.DEBUG);
    Configuration conf = new Configuration();
    conf.setLong(DFSConfigKeys.DFS_DATANODE_DU_RESERVED_KEY, reserved);
    conf.setLong(DFSConfigKeys.DFS_DATANODE_AVAILABLE_SPACE_VOLUME_CHOOSING_POLICY_BALANCED_SPACE_THRESHOLD_KEY, threshold);
    conf.setFloat(DFSConfigKeys.DFS_DATANODE_AVAILABLE_SPACE_VOLUME_CHOOSING_POLICY_BALANCED_SPACE_PREFERENCE_FRACTION_KEY, f);
    conf.setInt(DFSConfigKeys.DFS_DATANODE_SCAN_PERIOD_HOURS_KEY, -1);
    @SuppressWarnings("unchecked")
    VolumeChoosingPolicy<FsVolumeImpl> p =
        ReflectionUtils.newInstance(AvailableSpaceVolumeChoosingPolicy.class, conf);
    FsVolumeList list = new FsVolumeList(Collections.emptyList(),
        new BlockScanner(null, conf), p, conf, null);
    String base = new FileSystemTestHelper().getTestRootDir() + "/" + tag;  // unique per run
    FsVolumeImpl[] v = { vol(conf, base, "d0", C0), vol(conf, base, "d1", C1) };
    for (FsVolumeImpl x : v) list.addVolume(x.obtainReference());
    System.out.println("CSV,tag,step,R,reserved0,reserved1,avail0,avail1,rfr0,rfr1,mostLow,chosen");
    for (int step = 1; step <= 100; step++) {
      long a0 = v[0].getAvailable(), a1 = v[1].getAvailable();
      long r0 = v[0].getReservedForReplicas(), r1 = v[1].getReservedForReplicas();
      long least = Math.min(a0, a1), mostLow = Long.MIN_VALUE;
      if (a0 <= least + threshold) mostLow = Math.max(mostLow, a0);
      if (a1 <= least + threshold) mostLow = Math.max(mostLow, a1);
      String chosen;
      try (FsVolumeReference ref = list.getNextVolume(StorageType.DISK, null, B)) {
        FsVolumeImpl c = (FsVolumeImpl) ref.getVolume();
        c.reserveSpaceForReplica(B);
        chosen = c == v[0] ? "d0" : "d1";
      } catch (DiskOutOfSpaceException e) {
        chosen = "EXC:" + e.getMessage();
      }
      System.out.println("CSV," + tag + "," + step + "," + reserved + "," + v[0].getReserved() + ","
          + v[1].getReserved() + "," + a0 + "," + a1 + "," + r0 + "," + r1 + "," + mostLow + "," + chosen);
      if (chosen.startsWith("EXC")) break;
    }
  }

  @Test public void r0()        throws Exception { run("U-R0",   0L,          0.0f,  MiB); }
  @Test public void r512()      throws Exception { run("U-R512", 512 * MiB,   0.0f,  MiB); }
  @Test public void r960()      throws Exception { run("U-R960", 960 * MiB,   0.0f,  MiB); }
  @Test public void eq()        throws Exception { run("U-EQ",   C0 - B,      0.0f,  MiB); }
  @Test public void eq1()       throws Exception { run("U-EQ1",  C0 - B + 1,  0.0f,  MiB); }
  @Test public void r0f75()     throws Exception { run("U-R0-f75",   0L,        0.75f, MiB); }
  @Test public void r512f75()   throws Exception { run("U-R512-f75", 512 * MiB, 0.75f, MiB); }
  @Test public void r512bal()   throws Exception { run("U-R512-bal", 512 * MiB, 0.0f,  10240 * MiB); }
}
