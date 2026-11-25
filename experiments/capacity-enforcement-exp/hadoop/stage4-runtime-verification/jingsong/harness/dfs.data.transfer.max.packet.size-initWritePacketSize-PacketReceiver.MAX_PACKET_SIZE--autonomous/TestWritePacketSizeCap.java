/* Stage-4 harness, unit tier B2, default MAX (16 MiB). See WritePacketCapRunner. */
package org.apache.hadoop.hdfs;

import org.junit.Test;

public class TestWritePacketSizeCap {
  static final int MAX = 16777216;

  @Test(timeout = 300000)
  public void testC065536() throws Exception {
    WritePacketCapRunner.run(65536, MAX);
  }

  @Test(timeout = 300000)
  public void testC16777216() throws Exception {
    WritePacketCapRunner.run(16777216, MAX);
  }

  @Test(timeout = 300000)
  public void testC33554432() throws Exception {
    WritePacketCapRunner.run(33554432, MAX);
  }

  @Test(timeout = 300000)
  public void testC268435456() throws Exception {
    WritePacketCapRunner.run(268435456, MAX);
  }
}
