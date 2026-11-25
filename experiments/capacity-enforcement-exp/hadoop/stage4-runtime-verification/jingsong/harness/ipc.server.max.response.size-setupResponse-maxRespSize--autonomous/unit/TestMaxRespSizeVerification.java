/*
 * Stage-4 harness (capacity-enforcement-exp, hadoop, Jingsong), case
 * ipc.server.max.response.size-setupResponse-maxRespSize--autonomous, unit tier (B2).
 * Written from the case file's B2a outline. Not part of Hadoop; lives only in a local copy.
 */
package org.apache.hadoop.ipc;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.net.InetSocketAddress;
import java.util.Arrays;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.CommonConfigurationKeys;
import org.apache.hadoop.io.BytesWritable;
import org.apache.hadoop.io.IntWritable;
import org.apache.hadoop.io.Writable;
import org.apache.hadoop.ipc.Client.ConnectionId;
import org.apache.hadoop.ipc.metrics.RpcMetrics;
import org.apache.hadoop.ipc.protobuf.TestProtos;
import org.apache.hadoop.ipc.protobuf.TestRpcServiceProtos;
import org.apache.hadoop.metrics2.lib.MutableCounterLong;
import org.apache.hadoop.net.NetUtils;
import org.apache.hadoop.security.UserGroupInformation;
import org.apache.hadoop.test.GenericTestUtils.LogCapturer;
import org.apache.hadoop.thirdparty.protobuf.RpcController;
import org.apache.hadoop.thirdparty.protobuf.ServiceException;
import org.junit.Test;

public class TestMaxRespSizeVerification extends TestRpcBase {
  static final com.sun.management.ThreadMXBean TMX =
      (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
  static volatile long a1, a2;
  static volatile int capAtProbe;

  static final int[] KS = {1024, 1048576, 67108864};
  static final int[] NS = {524288, 4194304, 16777216};
  static final Pattern WARN = Pattern.compile("Large response size (\\d+) for call");
  static final String REP = System.getProperty("maxresp.rep", "1");

  static long alloc() {
    return TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
  }

  @SuppressWarnings("unchecked")
  static int tlCapacity() throws Exception {      // handler thread's ResponseBuffer
    Field f = Server.class.getDeclaredField("responseBuffer");
    f.setAccessible(true);
    return ((ThreadLocal<ResponseBuffer>) f.get(Server.get())).get().capacity();
  }

  static long sent(Server s) throws Exception {
    Field f = RpcMetrics.class.getDeclaredField("sentBytes");
    f.setAccessible(true);
    return ((MutableCounterLong) f.get(s.getRpcMetrics())).value();
  }

  // --- Writable path (setupResponseForWritable) ---
  static class WServer extends Server {
    WServer(Configuration c) throws IOException {
      super("0.0.0.0", 0, IntWritable.class, 1, c);
    }
    @Override
    public Writable call(RPC.RpcKind k, String p, Writable param, long t) throws IOException {
      int n = ((IntWritable) param).get();
      if (n == 0) {
        a2 = alloc();
        try { capAtProbe = tlCapacity(); } catch (Exception e) { throw new IOException(e); }
        return new BytesWritable(new byte[0]);
      }
      BytesWritable out = new BytesWritable(new byte[n]);
      a1 = alloc();
      return out;
    }
  }

  // --- Protobuf path (setupResponseForProtobuf) ---
  static class ProbeImpl extends PBServerImpl {
    @Override
    public TestProtos.EchoResponseProto echo(RpcController c, TestProtos.EchoRequestProto r)
        throws ServiceException {
      boolean probe = r.getMessage().length() == 1;
      if (probe) {
        a2 = alloc();
        try { capAtProbe = tlCapacity(); } catch (Exception e) { throw new ServiceException(e); }
      }
      TestProtos.EchoResponseProto resp =
          TestProtos.EchoResponseProto.newBuilder().setMessage(r.getMessage()).build();
      resp.getSerializedSize();   // memoize size before A1
      // Harness fix (stage 4, 2026-11-25): the B2a outline set a1 on every call, so the probe
      // overwrote the big call's A1 before D = a2 - a1 was read. A1 is taken on big calls only.
      if (!probe) {
        a1 = alloc();
      }
      return resp;
    }
  }

  static PrintWriter csv(String path) throws IOException {
    File f = new File("target", "maxresp-" + path + ".csv");
    boolean head = !f.exists();
    PrintWriter w = new PrintWriter(new FileWriter(f, true));
    if (head) {
      w.println("rep,path,K,N,R1,R2,C0,C1,C2,D1,D2,S1,S2,warn_count,warn_lengths");
    }
    return w;
  }

  static String row(String path, int k, int n, long r1, long r2, int c0, int c1, int c2,
      long d1, long d2, long s1, long s2, String logs) {
    Matcher m = WARN.matcher(logs);
    int cnt = 0; StringBuilder lens = new StringBuilder();
    while (m.find()) { cnt++; if (lens.length() > 0) lens.append(';'); lens.append(m.group(1)); }
    return String.join(",", REP, path, "" + k, "" + n, "" + r1, "" + r2, "" + c0, "" + c1,
        "" + c2, "" + d1, "" + d2, "" + s1, "" + s2, "" + cnt, lens.toString());
  }

  @Test(timeout = 600000)
  public void testWritablePath() throws Exception {
    try (PrintWriter w = csv("writable")) {
      for (int k : KS) {
        for (int n : NS) {
          Configuration c = new Configuration();
          c.setInt(CommonConfigurationKeys.IPC_SERVER_RPC_MAX_RESPONSE_SIZE_KEY, k);
          WServer ws = new WServer(c);
          ws.start();
          Client cl = new Client(BytesWritable.class, c);
          LogCapturer logs = LogCapturer.captureLogs(Server.LOG);
          try {
            InetSocketAddress addr = NetUtils.getConnectAddress(ws);
            ConnectionId id = ConnectionId.getConnectionId(addr, null,
                UserGroupInformation.getCurrentUser(), 0, null, c);
            cl.call(RPC.RpcKind.RPC_BUILTIN, new IntWritable(0), id,
                RPC.RPC_SERVICE_CLASS_DEFAULT, null);
            int c0 = capAtProbe;
            long s0 = sent(ws);
            long r1 = ((BytesWritable) cl.call(RPC.RpcKind.RPC_BUILTIN, new IntWritable(n), id,
                RPC.RPC_SERVICE_CLASS_DEFAULT, null)).getLength();
            cl.call(RPC.RpcKind.RPC_BUILTIN, new IntWritable(0), id,
                RPC.RPC_SERVICE_CLASS_DEFAULT, null);
            long d1 = a2 - a1; int c1 = capAtProbe; long sA = sent(ws);
            long r2 = ((BytesWritable) cl.call(RPC.RpcKind.RPC_BUILTIN, new IntWritable(n), id,
                RPC.RPC_SERVICE_CLASS_DEFAULT, null)).getLength();
            cl.call(RPC.RpcKind.RPC_BUILTIN, new IntWritable(0), id,
                RPC.RPC_SERVICE_CLASS_DEFAULT, null);
            long d2 = a2 - a1; int c2 = capAtProbe; long sB = sent(ws);
            String line = row("writable", k, n, r1, r2, c0, c1, c2, d1, d2, sA - s0, sB - sA,
                logs.getOutput());
            System.out.println("MAXRESP " + line);
            w.println(line);
          } finally {
            logs.stopCapturing();
            cl.stop();
            ws.stop();
          }
        }
      }
    }
  }

  @Test(timeout = 600000)
  public void testProtobufPath() throws Exception {
    char[] big = new char[NS[NS.length - 1]];
    Arrays.fill(big, 'a');
    try (PrintWriter w = csv("protobuf")) {
      for (int k : KS) {
        for (int n : NS) {
          setupConf();
          conf.setInt(CommonConfigurationKeys.IPC_SERVER_RPC_MAX_RESPONSE_SIZE_KEY, k);
          RPC.Server s = new RPC.Builder(conf).setProtocol(TestRpcService.class)
              .setInstance(TestRpcServiceProtos.TestProtobufRpcProto
                  .newReflectiveBlockingService(new ProbeImpl()))
              .setBindAddress("0.0.0.0").setPort(0).setNumHandlers(1).build();
          s.start();
          TestRpcService proxy = null;
          LogCapturer logs = LogCapturer.captureLogs(Server.LOG);
          try {
            proxy = getClient(NetUtils.getConnectAddress(s), conf);
            String msg = new String(big, 0, n);
            proxy.echo(null, newEchoRequest("x"));
            int c0 = capAtProbe;
            long s0 = sent(s);
            long r1 = proxy.echo(null, newEchoRequest(msg)).getMessage().length();
            proxy.echo(null, newEchoRequest("x"));
            long d1 = a2 - a1; int c1 = capAtProbe; long sA = sent(s);
            long r2 = proxy.echo(null, newEchoRequest(msg)).getMessage().length();
            proxy.echo(null, newEchoRequest("x"));
            long d2 = a2 - a1; int c2 = capAtProbe; long sB = sent(s);
            String line = row("protobuf", k, n, r1, r2, c0, c1, c2, d1, d2, sA - s0, sB - sA,
                logs.getOutput());
            System.out.println("MAXRESP " + line);
            w.println(line);
          } finally {
            logs.stopCapturing();
            if (proxy != null) {
              RPC.stopProxy(proxy);
            }
            s.stop();
          }
        }
      }
    }
  }
}
