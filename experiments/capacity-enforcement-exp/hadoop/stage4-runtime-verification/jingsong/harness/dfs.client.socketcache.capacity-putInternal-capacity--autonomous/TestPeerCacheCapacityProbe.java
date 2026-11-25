/*
 * Stage-4 unit tier (B2 + A1-A4) for
 * dfs.client.socketcache.capacity-putInternal-capacity--autonomous.
 * Not upstream. Copied into the per-case source copy only
 * (hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/).
 *
 * Part 1 (operandBound): pure PeerCache with fake peers, C in {0,1,16,256,1024}, N = 2048 puts.
 * Part 2 (realPeers): MiniDFSCluster, 1 DataNode, N = 1024 one-block 64 KiB files, C = -Dprobe.capacity,
 *   rep = -Dprobe.rep, histogram written to -Dprobe.out.
 */
package org.apache.hadoop.hdfs;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.nio.channels.ReadableByteChannel;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FSDataInputStream;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.hdfs.net.Peer;
import org.apache.hadoop.hdfs.protocol.DatanodeID;
import org.apache.hadoop.net.unix.DomainSocket;
import org.junit.Test;

public class TestPeerCacheCapacityProbe {

  /** Copy of TestPeerCache.FakePeer (private there). */
  static class FakePeer implements Peer {
    private boolean closed = false;
    private final boolean hasDomain;
    private final DatanodeID dnId;
    FakePeer(DatanodeID dnId, boolean hasDomain) { this.dnId = dnId; this.hasDomain = hasDomain; }
    @Override public ReadableByteChannel getInputStreamChannel() { throw new UnsupportedOperationException(); }
    @Override public void setReadTimeout(int timeoutMs) { throw new UnsupportedOperationException(); }
    @Override public int getReceiveBufferSize() { throw new UnsupportedOperationException(); }
    @Override public boolean getTcpNoDelay() { return false; }
    @Override public void setWriteTimeout(int timeoutMs) { throw new UnsupportedOperationException(); }
    @Override public boolean isClosed() { return closed; }
    @Override public void close() { closed = true; }
    @Override public String getRemoteAddressString() { return dnId.getInfoAddr(); }
    @Override public String getLocalAddressString() { return "127.0.0.1:123"; }
    @Override public InputStream getInputStream() { throw new UnsupportedOperationException(); }
    @Override public OutputStream getOutputStream() { throw new UnsupportedOperationException(); }
    @Override public boolean isLocal() { return true; }
    @Override public DomainSocket getDomainSocket() { return null; }
    @Override public boolean hasSecureChannel() { return false; }
    @Override public String toString() { return "FakePeer(dnId=" + dnId + ")"; }
  }

  // Part 1: pure PeerCache, operand only.
  @Test
  public void operandBound() throws Exception {
    printJvm("PART1");
    for (int c : new int[]{0, 1, 16, 256, 1024}) {
      PeerCache cache = new PeerCache(c, 600_000);
      int n = 2048, closed = 0, maxSize = 0;
      FakePeer[] p = new FakePeer[n];
      for (int i = 0; i < n; i++) {
        DatanodeID dn = new DatanodeID("127.0.0.1", "h" + (i % 8), "dn" + (i % 8), 1, 2, 3, 4);
        p[i] = new FakePeer(dn, false);
        cache.put(dn, p[i]);
        maxSize = Math.max(maxSize, cache.size());
      }
      for (FakePeer f : p) {
        if (f.isClosed()) {
          closed++;
        }
      }
      System.out.println("PART1 C=" + c + " N=" + n + " maxSize=" + maxSize
          + " size=" + cache.size() + " closed=" + closed);
      cache.close();
    }
  }

  // Part 2: real sockets through MiniDFSCluster; one run per (C, rep).
  @Test
  public void realPeers() throws Exception {
    int c = Integer.getInteger("probe.capacity", 16);
    int rep = Integer.getInteger("probe.rep", 1);
    String out = System.getProperty("probe.out", "target");
    int n = 1024;
    printJvm("PART2");
    Configuration conf = new HdfsConfiguration();
    conf.setInt("dfs.datanode.socket.reuse.keepalive", 600_000);
    conf.setInt("dfs.datanode.max.transfer.threads", 4096);
    MiniDFSCluster cl = new MiniDFSCluster.Builder(conf).numDataNodes(1).build();
    try {
      cl.waitActive();
      FileSystem fs0 = cl.getFileSystem();
      for (int i = 0; i < n; i++) {
        DFSTestUtil.createFile(fs0, new Path("/p/f" + i), 65536, (short) 1, i);
      }
      Configuration cc = new Configuration(conf);
      cc.set("dfs.client.context", "probe-" + c);            // fresh, isolated cache
      cc.setInt("dfs.client.socketcache.capacity", c);
      cc.setLong("dfs.client.socketcache.expiryMsec", 600_000);
      FileSystem fs = FileSystem.newInstance(cl.getURI(), cc);
      PeerCache cache = ClientContext.getFromConf(cc).getPeerCache();
      long h0 = heapAfterGc();
      int fd0 = fdCount();
      long d0 = directUsed();
      int x0 = cl.getDataNodes().get(0).getXceiverCount();
      FSDataInputStream[] in = new FSDataInputStream[n];
      byte[] b = new byte[65536];
      long bytes = 0;
      for (int i = 0; i < n; i++) {
        in[i] = fs.open(new Path("/p/f" + i));
        int r;
        while ((r = in[i].read(b)) > 0) {
          bytes += r;
        }
      }
      long hOpen = heapAfterGc();
      int fdOpen = fdCount();
      long dOpen = directUsed();
      int xOpen = cl.getDataNodes().get(0).getXceiverCount();
      int sizeOpen = cache.size();
      for (FSDataInputStream s : in) {
        s.close();
      }
      in = null;
      long h1 = heapAfterGc();
      int fd1 = fdCount();
      long d1 = directUsed();
      int x1 = cl.getDataNodes().get(0).getXceiverCount();
      int size = cache.size();
      String full = histogramFull();
      File hf = new File(out, "histo-C" + c + "-r" + rep + ".txt");
      try (PrintWriter w = new PrintWriter(new FileWriter(hf))) {
        w.print(full);
      }
      Pattern re = Pattern.compile("NioInetPeer|SocketChannelImpl|PeerCache\\$|LinkedListMultimap\\$Node");
      StringBuilder sel = new StringBuilder();
      for (String line : full.split("\n")) {
        if (re.matcher(line).find()) {
          sel.append("HISTO C=").append(c).append(" rep=").append(rep).append(' ').append(line.trim()).append('\n');
        }
      }
      System.out.println("PART2 C=" + c + " rep=" + rep + " N=" + n + " bytesRead=" + bytes
          + " sizeOpen=" + sizeOpen + " size=" + size
          + " heap0=" + h0 + " heapOpen=" + hOpen + " heapClosed=" + h1
          + " fd0=" + fd0 + " fdOpen=" + fdOpen + " fdClosed=" + fd1
          + " direct0=" + d0 + " directOpen=" + dOpen + " directClosed=" + d1
          + " xceivers0=" + x0 + " xceiversOpen=" + xOpen + " xceivers=" + x1
          + " maxHeap=" + Runtime.getRuntime().maxMemory() + " gc=" + gcNames()
          + " histo=" + hf.getAbsolutePath());
      System.out.print(sel);
      System.out.flush();
      fs.close();
    } finally {
      cl.shutdown();
    }
  }

  static void printJvm(String tag) {
    System.out.println(tag + "-JVM maxHeap=" + Runtime.getRuntime().maxMemory() + " gc=" + gcNames()
        + " java=" + System.getProperty("java.version")
        + " args=" + ManagementFactory.getRuntimeMXBean().getInputArguments());
  }

  static String gcNames() {
    List<String> l = new ArrayList<>();
    for (GarbageCollectorMXBean g : ManagementFactory.getGarbageCollectorMXBeans()) {
      l.add(g.getName());
    }
    return String.join(",", l).replace(' ', '_');
  }

  static long heapAfterGc() throws InterruptedException {
    for (int i = 0; i < 3; i++) {
      System.gc();
    }
    Thread.sleep(200);
    return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
  }

  static int fdCount() {
    String[] l = new File("/proc/self/fd").list();
    return l == null ? -1 : l.length;
  }

  static long directUsed() {
    for (BufferPoolMXBean p : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
      if ("direct".equals(p.getName())) {
        return p.getMemoryUsed();
      }
    }
    return -1;
  }

  static String histogramFull() throws IOException, InterruptedException {
    String pid = ManagementFactory.getRuntimeMXBean().getName().split("@")[0];
    File jcmd = new File(System.getProperty("java.home"), "../bin/jcmd");
    if (!jcmd.exists()) {
      jcmd = new File(System.getProperty("java.home"), "bin/jcmd");
    }
    Process pr = new ProcessBuilder(jcmd.getCanonicalPath(), pid, "GC.class_histogram")
        .redirectErrorStream(true).start();
    StringBuilder sb = new StringBuilder();
    try (BufferedReader r = new BufferedReader(new InputStreamReader(pr.getInputStream()))) {
      String line;
      while ((line = r.readLine()) != null) {
        sb.append(line).append('\n');
      }
    }
    pr.waitFor();
    return sb.toString();
  }
}
