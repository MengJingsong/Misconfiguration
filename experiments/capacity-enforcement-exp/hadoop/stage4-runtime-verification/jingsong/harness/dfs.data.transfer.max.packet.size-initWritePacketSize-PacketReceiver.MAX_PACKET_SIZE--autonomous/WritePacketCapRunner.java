/*
 * Stage-4 harness (capacity-enforcement-exp, Hadoop, Jingsong), case
 * dfs.data.transfer.max.packet.size-initWritePacketSize-PacketReceiver.MAX_PACKET_SIZE--autonomous,
 * unit tier B2 (amended A1-A3 and A7, 2026-11-25). Shared body of TestWritePacketSizeCap and
 * TestWritePacketSizeCap4M. Not a test class itself (name does not match Test*).
 */
package org.apache.hadoop.hdfs;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;

import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.util.Random;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FSDataOutputStream;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.hdfs.client.HdfsClientConfigKeys;
import org.apache.hadoop.hdfs.protocol.datatransfer.PacketReceiver;
import org.apache.hadoop.test.Whitebox;

final class WritePacketCapRunner {
  private WritePacketCapRunner() {}

  static final int CHUNK_WRITE = 65536;            // 64 KiB write calls (B2c)
  static final long SMALL = 1048576L;               // 1 MiB (B2c)
  static final long BIG = 50331648L;                // 48 MiB (B2c)
  static final long BIG_BLOCK = 128L * 1024 * 1024; // 128 MiB block for /t/big

  // A7 (2026-11-25): the first write is one FSOutputSummer group (9 chunks of 512 B), which creates the
  // first packet and cannot fill it for any C here (>= 126 chunks), so (c)/(d) see the first packet.
  static final int FIRST_WRITE = 9 * 512;

  static void writeRest(FSDataOutputStream out, byte[] data, long done, long total) throws IOException {
    while (done < total) {
      int n = (int) Math.min(CHUNK_WRITE, total - done);
      out.write(data, 0, n);
      done += n;
    }
  }

  static int bufLen(DFSPacket p) {
    if (p == null) {
      return -1;
    }
    byte[] b = (byte[]) Whitebox.getInternalState(p, "buf");
    return b == null ? -1 : b.length;
  }

  static String exc(Throwable t) {
    String m = String.valueOf(t.getMessage()).replace('\n', ' ').replace(',', ';');
    if (m.length() > 300) {
      m = m.substring(0, 300);
    }
    return t.getClass().getSimpleName() + ":" + m;
  }

  static void run(int c, int expectMax) throws Exception {
    System.out.println("IFCHK,BEGIN,C=" + c + ",MAX=" + PacketReceiver.MAX_PACKET_SIZE);
    System.out.flush();
    assertEquals("PacketReceiver.MAX_PACKET_SIZE", expectMax, PacketReceiver.MAX_PACKET_SIZE);
    Configuration conf = new HdfsConfiguration();
    conf.setInt(HdfsClientConfigKeys.DFS_CLIENT_WRITE_PACKET_SIZE_KEY, c);
    conf.setInt(DFSConfigKeys.DFS_REPLICATION_KEY, 1);
    assertFalse("byte-array-manager must be off (B2h)", conf.getBoolean(
        HdfsClientConfigKeys.Write.ByteArrayManager.ENABLED_KEY, false));
    com.sun.management.ThreadMXBean tmx =
        (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    long tid = Thread.currentThread().getId();
    byte[] data = new byte[CHUNK_WRITE];
    new Random(c).nextBytes(data);

    MiniDFSCluster cluster = new MiniDFSCluster.Builder(conf).numDataNodes(1).build();
    try {
      cluster.waitActive();
      DistributedFileSystem fs = cluster.getFileSystem();
      fs.mkdirs(new Path("/t"));

      // ---- small file: 1 MiB, hflush, close
      Path small = new Path("/t/small");
      FSDataOutputStream out = fs.create(small);
      DFSOutputStream dos = (DFSOutputStream) out.getWrappedStream();
      int wps = (Integer) Whitebox.getInternalState(dos, "writePacketSize");
      int ps0 = dos.packetSize;
      int cpp0 = dos.chunksPerPacket;
      Object bam = Whitebox.getInternalState(dos, "byteArrayManager");
      String bamClass = bam == null ? "null" : bam.getClass().getName();
      long a0 = tmx.getThreadAllocatedBytes(tid);
      out.write(data, 0, FIRST_WRITE);
      long a1 = tmx.getThreadAllocatedBytes(tid);
      DFSPacket p1 = dos.currentPacket;
      int firstBuf = bufLen(p1);
      String smallRes = "ok";
      try {
        writeRest(out, data, FIRST_WRITE, SMALL);
        out.hflush();
        out.close();
      } catch (IOException e) {
        smallRes = "fail:" + exc(e);
        try { out.close(); } catch (IOException ignored) { }
      }
      long smallLen = -1;
      try { smallLen = fs.getFileStatus(small).getLen(); } catch (IOException ignored) { }

      // ---- big file: 48 MiB in 64 KiB writes, block 128 MiB
      Path big = new Path("/t/big");
      FSDataOutputStream out2 = fs.create(big, true, 4096, (short) 1, BIG_BLOCK);
      DFSOutputStream d2 = (DFSOutputStream) out2.getWrappedStream();
      int bigPs0 = d2.packetSize;
      DFSPacket first = null;
      int bigFirstBuf = -1;
      int secondBuf = -1;
      int psAfter = -1;
      int cppAfter = -1;
      long secondAtWritten = -1;
      String bigRes = "ok";
      String failAt = "none";
      long written = 0;
      try {
        boolean firstCall = true;
        while (written < BIG) {
          int n = firstCall ? FIRST_WRITE : (int) Math.min(CHUNK_WRITE, BIG - written);
          firstCall = false;
          out2.write(data, 0, n);
          written += n;
          DFSPacket cur = d2.currentPacket;
          if (first == null) {
            first = cur;
            bigFirstBuf = bufLen(cur);
          } else if (secondBuf < 0 && cur != null && cur != first) {
            secondBuf = bufLen(cur);
            psAfter = d2.packetSize;
            cppAfter = d2.chunksPerPacket;
            secondAtWritten = written;
          }
        }
      } catch (IOException e) {
        bigRes = "fail:" + exc(e);
        failAt = "write@" + written;
      }
      if (failAt.equals("none")) {
        try {
          out2.close();
        } catch (IOException e) {
          bigRes = "fail:" + exc(e);
          failAt = "close";
        }
      } else {
        try { out2.close(); } catch (IOException ignored) { }
      }
      long bigLen = -1;
      try { bigLen = fs.getFileStatus(big).getLen(); } catch (IOException ignored) { }

      System.out.println("IFCHK,RESULT,C=" + c + ",MAX=" + PacketReceiver.MAX_PACKET_SIZE
          + ",writePacketSize=" + wps + ",packetSize0=" + ps0 + ",chunksPerPacket0=" + cpp0
          + ",firstBuf=" + firstBuf + ",firstWriteAlloc=" + (a1 - a0)
          + ",bam=" + bamClass
          + ",smallResult=" + smallRes + ",smallLen=" + smallLen
          + ",bigPacketSize0=" + bigPs0 + ",bigFirstBuf=" + bigFirstBuf
          + ",secondBuf=" + (secondBuf < 0 ? "none" : String.valueOf(secondBuf))
          + ",packetSizeAfter=" + psAfter + ",chunksPerPacketAfter=" + cppAfter
          + ",secondAtWritten=" + secondAtWritten
          + ",bigResult=" + bigRes + ",bigFailAt=" + failAt + ",bigLen=" + bigLen);
    } finally {
      cluster.shutdown();
      System.out.println("IFCHK,END,C=" + c);
      System.out.flush();
    }
  }
}
