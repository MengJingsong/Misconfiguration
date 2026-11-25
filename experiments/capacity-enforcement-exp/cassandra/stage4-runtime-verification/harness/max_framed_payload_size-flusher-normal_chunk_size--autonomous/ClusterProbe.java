import java.nio.ByteBuffer; import java.nio.file.*; import java.util.*;
import javax.management.*; import javax.management.remote.*;
import org.apache.cassandra.config.DatabaseDescriptor; import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.db.ConsistencyLevel; import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.transport.*; import org.apache.cassandra.transport.messages.*;

public class ClusterProbe {
  static MBeanServerConnection mbs;
  static long v(String on, String attr) throws Exception { return ((Number) mbs.getAttribute(new ObjectName(on), attr)).longValue(); }
  static void sample(String tag) throws Exception {
    String bp = "org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=";
    System.out.printf("SAMPLE,%s,used=%d,size=%d,overflow=%d,nioDirect=%d%n", tag,
      v(bp+"UsedSize","Value"), v(bp+"Size","Value"), v(bp+"OverflowSize","Value"),
      v("java.nio:type=BufferPool,name=direct","MemoryUsed"));
  }
  public static void main(String[] a) throws Exception {
    DatabaseDescriptor.clientInitialization();
    DatabaseDescriptor.setNativeTransportMaxMessageSizeInBytes(256L << 20);   // amendment 2026-11-25 (runbook defect 1): client-mode config leaves the cached max message size at 0, so SimpleClient rejected every multi-frame response
    String mode = a[0]; int port = Integer.parseInt(a[1]); int m = Integer.parseInt(a[2]); int b = Integer.parseInt(a[3]);
    if (mode.equals("load")) {
      SimpleClient c = new SimpleClient("127.0.0.1", port, ProtocolVersion.V5).connect(false);
      c.execute("CREATE KEYSPACE IF NOT EXISTS probe WITH replication = {'class':'SimpleStrategy','replication_factor':1}", ConsistencyLevel.ONE);
      c.execute("CREATE TABLE IF NOT EXISTS probe.blobs (k int PRIMARY KEY, v blob)", ConsistencyLevel.ONE);
      ResultMessage.Prepared p = c.prepare("INSERT INTO probe.blobs (k, v) VALUES (?, ?)");
      Random r = new Random(7);
      for (int k = 0; k < m; k++) { byte[] v = new byte[b]; r.nextBytes(v);
        c.executePrepared(p, List.of(Int32Type.instance.decompose(k), ByteBuffer.wrap(v)), ConsistencyLevel.ONE); }
      c.close(); System.exit(0);
    }
    // mode read: a[4]=jmxPort a[5]=pauseFile a[6]=holdMillis ; port = proxy port
    mbs = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[4] + "/jmxrmi")).getMBeanServerConnection();
    Path pause = Paths.get(a[5]); long hold = Long.parseLong(a[6]);
    boolean noPause = a.length > 7 && a[7].equals("nopause");   // amendment 2026-11-25: unpaused control (B3e step 8)
    SimpleClient c = new SimpleClient("127.0.0.1", port, ProtocolVersion.V5).connect(false);   // no compression -> CRC frames
    c.execute("SELECT v FROM probe.blobs WHERE k = 0", ConsistencyLevel.ONE);                  // warm-up
    Thread.sleep(1000); sample("baseline");
    if (!noPause) { Files.createFile(pause); } Thread.sleep(200);
    List<Message.Request> reqs = new ArrayList<>();
    for (int k = 0; k < m; k++) reqs.add(new QueryMessage("SELECT v FROM probe.blobs WHERE k = " + k, QueryOptions.forInternalCalls(ConsistencyLevel.ONE, List.of())));
    final Object[] res = new Object[1];
    Thread t = new Thread(() -> { try { res[0] = c.execute(reqs); } catch (Throwable e) { res[0] = e; } }); t.start();
    Thread.sleep(hold); sample("held");
    if (!noPause) Files.delete(pause); t.join();
    System.out.println("RESULT," + (res[0] instanceof Map ? "ok,responses=" + ((Map<?,?>) res[0]).size() : "error," + res[0]));
    Thread.sleep(3000); sample("after");
    c.close(); System.exit(0);
  }
}
