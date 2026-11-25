import java.nio.ByteBuffer;
import java.util.*;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.io.sstable.CQLSSTableWriter;
import org.apache.cassandra.utils.ByteBufferUtil;

public class GenSorted
{
    public static void main(String[] a) throws Exception
    {
        String out = a[0], table = a[1]; boolean sorted = a[3].equals("sorted"); int n = Integer.parseInt(a[4]);
        new java.io.File(out).mkdirs();
        CQLSSTableWriter.Builder b = CQLSSTableWriter.builder().inDirectory(out)
            .forTable("CREATE TABLE s4ks." + table + " (k int PRIMARY KEY, v blob) WITH compression = {'enabled': 'false'}")
            .using("INSERT INTO s4ks." + table + " (k, v) VALUES (?, ?)");
        if (sorted) b.sorted();
        if (!a[2].equals("unset")) b.withMaxSSTableSizeInMiB(Integer.parseInt(a[2]));
        CQLSSTableWriter w = b.build();
        Integer[] keys = new Integer[n];
        for (int i = 0; i < n; i++) keys[i] = i;
        // Murmur3 order: token, then key bytes (DecoratedKey order)
        Arrays.sort(keys, Comparator.comparingLong((Integer k) -> (Long) Murmur3Partitioner.instance.getToken(ByteBufferUtil.bytes(k)).getTokenValue())
                                    .thenComparing(k -> ByteBufferUtil.bytes(k)));
        Random rnd = new Random(42);
        for (Integer k : keys) { byte[] v = new byte[1000]; rnd.nextBytes(v); w.addRow(k, ByteBuffer.wrap(v)); }
        w.close();
        System.exit(0);
    }
}
