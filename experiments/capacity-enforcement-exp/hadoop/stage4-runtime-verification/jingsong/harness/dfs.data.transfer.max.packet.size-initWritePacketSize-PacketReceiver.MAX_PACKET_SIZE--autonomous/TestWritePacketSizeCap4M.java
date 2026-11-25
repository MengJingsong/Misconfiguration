/* Stage-4 harness, unit tier B2, MAX = 4 MiB via maxpkt-4m-site.xml (amendment A2). */
package org.apache.hadoop.hdfs;

import org.apache.hadoop.conf.Configuration;
import org.junit.Test;

public class TestWritePacketSizeCap4M {
  static final int MAX = 4194304;

  static {
    // A2: load HdfsConfiguration (adds hdfs-default.xml etc.) first, so that the resource added
    // here comes after hdfs-default.xml and wins; then nothing has touched PacketReceiver yet.
    HdfsConfiguration.init();
    Configuration.addDefaultResource("maxpkt-4m-site.xml");
  }

  @Test(timeout = 300000)
  public void testC4194304() throws Exception {
    WritePacketCapRunner.run(4194304, MAX);
  }

  @Test(timeout = 300000)
  public void testC8388608() throws Exception {
    WritePacketCapRunner.run(8388608, MAX);
  }
}
