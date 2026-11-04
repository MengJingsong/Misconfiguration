import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.caffinitas.ohc.CacheSerializer;
import org.caffinitas.ohc.OHCache;
import org.caffinitas.ohc.OHCacheBuilder;

/**
 * Instrument check (known answer) for RcsLedger + rcs-ledger.btm, run before the cluster re-run's shakedown, outside Cassandra.
 * Builds an OHC 0.5.1 linked cache as OHCProvider does (capacity, throwOOME; here 4 segments and 4 MiB), puts N entries with a
 * 4-byte key and a V-byte value, so allocLen = 64 + 8 + V (Util.allocLen), and prints OHC's own size/memUsed next to the
 * ledger. Known answers: TableBlocks = 4, TableBytes = 4 x 65,536 (no rehash below 6,144 entries per segment),
 * EntryBlocks = size(), EntryBytes = memUsed(), UnknownFrees = 0; after clear(): EntryBlocks = 0, EntryBytes = 0;
 * after close(): LiveBlocks = 0.
 * usage: java -javaagent:byteman.jar=script:rcs-ledger.btm,boot:byteman.jar,sys:rcs-ledger.jar -cp ohc+jna+guava+slf4j LedgerKnownAnswer
 */
public class LedgerKnownAnswer
{
    static final CacheSerializer<Integer> KEY = new CacheSerializer<Integer>()
    {
        public void serialize(Integer v, ByteBuffer b) { b.putInt(v); }
        public Integer deserialize(ByteBuffer b) { return b.getInt(); }
        public int serializedSize(Integer v) { return 4; }
    };

    static int V = 1100;
    static final CacheSerializer<byte[]> VAL = new CacheSerializer<byte[]>()
    {
        public void serialize(byte[] v, ByteBuffer b) { b.put(v); }
        public byte[] deserialize(ByteBuffer b) { byte[] a = new byte[b.remaining()]; b.get(a); return a; }
        public int serializedSize(byte[] v) { return v.length; }
    };

    static String led(MBeanServer m) throws Exception
    {
        ObjectName o = new ObjectName("stage4:type=RcsLedger");
        StringBuilder sb = new StringBuilder();
        for (String a : new String[]{ "EntryBlocks", "EntryBytes", "EntryMalloc", "TableBlocks", "TableBytes", "TableMalloc", "LiveBlocks", "UnknownFrees", "DuplicateAllocs", "MallocSizeErrors", "EntryMaxBytes", "Histogram" })
            sb.append(a).append('=').append(m.getAttribute(o, a)).append(' ');
        return sb.toString();
    }

    public static void main(String[] a) throws Exception
    {
        int n = 10000;
        OHCache<Integer, byte[]> c = OHCacheBuilder.<Integer, byte[]>newBuilder().capacity(4L << 20).segmentCount(4)
                                                   .keySerializer(KEY).valueSerializer(VAL).throwOOME(true).build();
        MBeanServer m = ManagementFactory.getPlatformMBeanServer();
        System.out.println("KA built: size=" + c.size() + " memUsed=" + c.memUsed() + " | " + led(m));
        byte[] v = new byte[V];
        for (int i = 0; i < n; i++)
            c.put(i, v);
        System.out.println("KA after " + n + " puts (allocLen " + (64 + 8 + V) + "): size=" + c.size() + " memUsed=" + c.memUsed() + " evicted=" + c.stats().getEvictionCount() + " | " + led(m));
        c.setCapacity(1L << 20);
        System.out.println("KA after setCapacity(1 MiB), no put: size=" + c.size() + " memUsed=" + c.memUsed() + " | " + led(m));
        for (int i = n; i < n + 2000; i++)
            c.put(i, v);
        System.out.println("KA after 2000 more puts: size=" + c.size() + " memUsed=" + c.memUsed() + " | " + led(m));
        c.clear();
        System.out.println("KA after clear: size=" + c.size() + " memUsed=" + c.memUsed() + " | " + led(m));
        c.close();
        System.out.println("KA after close: | " + led(m));
    }
}
