import java.io.*; import java.net.*;
public class StartupFlood {
// args: protoVersion(3|4|5|6) firstHostIndex count
public static void main(String[] a) throws Exception {
  int v = Integer.parseInt(a[0]), first = Integer.parseInt(a[1]), n = Integer.parseInt(a[2]);
  byte[] body = startupBody();
  for (int i = first; i < first + n; i++) {
    InetAddress src = InetAddress.getByAddress(new byte[]{127, (byte)(1 + (i >> 16)), (byte)(i >> 8), (byte)i});
    try (Socket s = new Socket()) {
      s.bind(new InetSocketAddress(src, 0));
      s.connect(new InetSocketAddress("127.0.0.1", 9042), 5000);
      s.setSoTimeout(5000);
      DataOutputStream out = new DataOutputStream(s.getOutputStream());
      out.writeByte(v); out.writeByte(v == 6 ? 0x10 : 0x00); out.writeShort(1); out.writeByte(0x01); out.writeInt(body.length); out.write(body); out.flush();
      DataInputStream in = new DataInputStream(s.getInputStream());
      int rv = in.readUnsignedByte(); in.readUnsignedByte(); in.readShort(); int op = in.readUnsignedByte();
      if (op != 0x02) System.err.println("src " + src + " got opcode " + op + " version byte " + rv);
    }
  }
}
static byte[] startupBody() throws IOException {
  ByteArrayOutputStream b = new ByteArrayOutputStream(); DataOutputStream d = new DataOutputStream(b);
  d.writeShort(1); writeStr(d, "CQL_VERSION"); writeStr(d, "3.0.0"); return b.toByteArray();
}
static void writeStr(DataOutputStream d, String s) throws IOException { byte[] x = s.getBytes("UTF-8"); d.writeShort(x.length); d.write(x); }
}
