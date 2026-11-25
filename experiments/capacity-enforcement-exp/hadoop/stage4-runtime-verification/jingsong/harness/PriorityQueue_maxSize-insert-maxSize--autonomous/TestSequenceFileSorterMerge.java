/*
 * Stage-4 harness (capacity-enforcement-exp, Hadoop, order 9, PriorityQueue_maxSize-insert-maxSize--autonomous).
 * Copied into hadoop-common/src/test/java/org/apache/hadoop/io/ of the run's private source copy only.
 * Case file B2c Part 2: drive SequenceFile.Sorter.MergeQueue through a real multi-run sort.
 * Factor from -Dpqcap.factor (passed inside maven-surefire-plugin.argLine, amendment A1).
 */
package org.apache.hadoop.io;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.io.File;
import java.lang.reflect.Field;
import java.util.Random;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.FileUtil;
import org.apache.hadoop.fs.LocalFileSystem;
import org.apache.hadoop.fs.Path;
import org.junit.Test;

public class TestSequenceFileSorterMerge {
  static final int RECORDS = 50000;

  @Test
  public void testSorterMerge() throws Exception {
    int f = Integer.getInteger("pqcap.factor", 100);
    File base = new File(System.getProperty("test.build.data", "target/test-dir"), "pqcap-sorter-f" + f);
    FileUtil.fullyDelete(base);
    assertTrue(base.mkdirs());
    Configuration conf = new Configuration();
    conf.unset("io.sort.mb");
    conf.unset("io.sort.factor");
    conf.setInt("seq.io.sort.mb", 1);
    conf.setInt("seq.io.sort.factor", f);
    conf.set("io.seqfile.local.dir", new File(base, "local").getAbsolutePath());
    LocalFileSystem fs = FileSystem.getLocal(conf);
    Path in = new Path(base.getAbsolutePath(), "in.seq");
    Path out = new Path(base.getAbsolutePath(), "out.seq");
    Random r = new Random(20261124L);
    byte[] v = new byte[100];
    try (SequenceFile.Writer w = SequenceFile.createWriter(conf, SequenceFile.Writer.file(in),
        SequenceFile.Writer.keyClass(IntWritable.class), SequenceFile.Writer.valueClass(BytesWritable.class),
        SequenceFile.Writer.compression(SequenceFile.CompressionType.NONE))) {
      for (int i = 0; i < RECORDS; i++) {
        r.nextBytes(v);
        w.append(new IntWritable(r.nextInt()), new BytesWritable(v));
      }
    }
    SequenceFile.Sorter s = new SequenceFile.Sorter(fs, IntWritable.class, BytesWritable.class, conf);
    Field mf = SequenceFile.Sorter.class.getDeclaredField("memory");
    mf.setAccessible(true);
    Field ff = SequenceFile.Sorter.class.getDeclaredField("factor");
    ff.setAccessible(true);
    System.out.println("PQCAP sorter memory=" + mf.get(s) + " factor=" + ff.get(s) + " inBytes=" + fs.getFileStatus(in).getLen());
    long t0 = System.nanoTime();
    s.sort(in, out);
    long ms = (System.nanoTime() - t0) / 1000000;
    int n = 0;
    boolean sorted = true;
    IntWritable k = new IntWritable();
    BytesWritable val = new BytesWritable();
    Integer prev = null;
    try (SequenceFile.Reader rd = new SequenceFile.Reader(conf, SequenceFile.Reader.file(out))) {
      while (rd.next(k, val)) {
        if (prev != null && k.get() < prev) sorted = false;
        prev = k.get();
        n++;
      }
    }
    System.out.println("PQCAP sorter f=" + f + " outRecords=" + n + " sorted=" + sorted + " sortMs=" + ms);
    assertEquals(RECORDS, n);
    assertTrue(sorted);
    FileUtil.fullyDelete(base);
  }
}
