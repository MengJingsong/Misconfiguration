// B3e step 9 (W2), as filed, with the native port as a second argument (amendment AM2).
import java.io.*; import java.net.*; import java.nio.charset.StandardCharsets;
public class NativeProbe {
  static byte[] body(IOConsumer w) throws IOException { ByteArrayOutputStream b = new ByteArrayOutputStream(); w.accept(new DataOutputStream(b)); return b.toByteArray(); }
  interface IOConsumer { void accept(DataOutputStream d) throws IOException; }
  static void str(DataOutputStream d, String s) throws IOException { byte[] x = s.getBytes(StandardCharsets.UTF_8); d.writeShort(x.length); d.write(x); }
  static void send(DataOutputStream o, int op, byte[] b) throws IOException { o.writeByte(4); o.writeByte(0); o.writeShort(0); o.writeByte(op); o.writeInt(b.length); o.write(b); o.flush(); }
  static int recv(DataInputStream in) throws IOException { in.readByte(); in.readByte(); in.readShort(); int op = in.readUnsignedByte(); byte[] b = new byte[in.readInt()]; in.readFully(b);
    if (op == 0) throw new IOException("ERROR " + new String(b, StandardCharsets.UTF_8)); return op; }
  public static void main(String[] a) throws Exception {
    int m = Integer.parseInt(a[0]);
    int port = a.length > 1 ? Integer.parseInt(a[1]) : 9042;
    byte[] startup = body(d -> { d.writeShort(1); str(d, "CQL_VERSION"); str(d, "3.0.0"); });
    byte[] tok = "\0cassandra\0cassandra".getBytes(StandardCharsets.UTF_8);
    byte[] auth = body(d -> { d.writeInt(tok.length); d.write(tok); });
    byte[] q = "SELECT release_version FROM system.local".getBytes(StandardCharsets.UTF_8);
    byte[] query = body(d -> { d.writeInt(q.length); d.write(q); d.writeShort(1); d.writeByte(0); });
    long t0 = System.nanoTime();
    for (int i = 0; i < m; i++) {
      String src = "127.200." + (i / 250) + "." + (1 + i % 250);
      try (Socket s = new Socket()) {
        s.bind(new InetSocketAddress(src, 0));
        s.connect(new InetSocketAddress("127.0.0.1", port), 5000);
        DataOutputStream o = new DataOutputStream(new BufferedOutputStream(s.getOutputStream()));
        DataInputStream in = new DataInputStream(new BufferedInputStream(s.getInputStream()));
        send(o, 0x01, startup); if (recv(in) != 0x03) throw new IOException("expected AUTHENTICATE");
        send(o, 0x0F, auth);    if (recv(in) != 0x10) throw new IOException("expected AUTH_SUCCESS");
        send(o, 0x07, query);   if (recv(in) != 0x08) throw new IOException("expected RESULT");
      }
    }
    System.out.printf("done %d logins in %.1f s%n", m, (System.nanoTime() - t0) / 1e9);
  }
}
