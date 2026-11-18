// C4 dataset generator (stage 2). Usage: java GenSorted <outdir> <lo> <hi>
// Key i = PREFIX(988 chars of [a-z0-9] from new Random(49)) + %012d(i); v = 1.
// Rows are written in Murmur3 token order (ties by key bytes) with CQLSSTableWriter.sorted(): one sstable.
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Random;
import java.util.stream.IntStream;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.io.sstable.CQLSSTableWriter;

public class GenSorted
{
    static final String PREFIX;
    static
    {
        // amendment 4: write sstables in the version the victim reads (storage_compatibility_mode CASSANDRA_4 -> "nb").
        // Client mode forces NONE (5.0 version "oa", refused by a CASSANDRA_4 node as incompatible), so initialise as a
        // tool from the shipped, unmodified conf/cassandra.yaml (-Dcassandra.config), as the bundled sstable tools do.
        System.setProperty("cassandra.schema.force_load_local_keyspaces", "true");
        org.apache.cassandra.config.DatabaseDescriptor.toolInitialization();
        String chars = "abcdefghijklmnopqrstuvwxyz0123456789";
        Random r = new Random(49);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 988; i++) sb.append(chars.charAt(r.nextInt(36)));
        PREFIX = sb.toString();
    }

    static byte[] keyBytes(long i)
    {
        return (PREFIX + String.format("%012d", i)).getBytes(StandardCharsets.US_ASCII);
    }

    static void log(String s) { System.out.println(System.currentTimeMillis() + " " + s); System.out.flush(); }

    public static void main(String[] args) throws Exception
    {
        String out = args[0];
        long lo = Long.parseLong(args[1]), hi = Long.parseLong(args[2]);
        int n = (int) (hi - lo);
        log("start n=" + n + " lo=" + lo + " hi=" + hi + " prefixLen=" + PREFIX.length());
        long[] tok = new long[n];
        IntStream.range(0, n).parallel().forEach(j -> tok[j] = Murmur3Partitioner.instance.getToken(ByteBuffer.wrap(keyBytes(lo + j))).getLongValue());
        log("tokens done");
        // stable LSD radix sort on signed long (flip sign bit), carrying the index; ties keep ascending index = key byte order
        int[] idx = new int[n];
        for (int j = 0; j < n; j++) idx[j] = j;
        long[] t2 = new long[n]; int[] i2 = new int[n];
        long[] ta = tok; int[] ia = idx;
        for (int pass = 0; pass < 8; pass++)
        {
            int shift = pass * 8;
            int[] cnt = new int[257];
            for (int j = 0; j < n; j++) cnt[(int) (((ta[j] ^ Long.MIN_VALUE) >>> shift) & 0xFF) + 1]++;
            for (int b = 0; b < 256; b++) cnt[b + 1] += cnt[b];
            for (int j = 0; j < n; j++)
            {
                int b = (int) (((ta[j] ^ Long.MIN_VALUE) >>> shift) & 0xFF);
                int p = cnt[b]++;
                t2[p] = ta[j]; i2[p] = ia[j];
            }
            long[] tt = ta; ta = t2; t2 = tt; int[] it = ia; ia = i2; i2 = it;
        }
        int ties = 0;
        for (int j = 1; j < n; j++) { if (ta[j] < ta[j - 1]) throw new IllegalStateException("unsorted at " + j); if (ta[j] == ta[j - 1]) ties++; }
        log("sorted ties=" + ties);
        t2 = null; i2 = null;
        CQLSSTableWriter w = CQLSSTableWriter.builder().inDirectory(out)
                .forTable("CREATE TABLE c4.isx (pk text PRIMARY KEY, v int)")
                .using("INSERT INTO c4.isx (pk, v) VALUES (?, ?)")
                .sorted().build();
        Integer one = 1;
        for (int j = 0; j < n; j++)
        {
            w.addRow(PREFIX + String.format("%012d", lo + ia[j]), one);
            if ((j + 1) % 1_000_000 == 0) log("rows " + (j + 1));
        }
        w.close();
        log("done rows=" + n);
    }
}
