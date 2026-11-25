import java.nio.ByteBuffer;
import java.util.Random;
import org.apache.cassandra.io.sstable.CQLSSTableWriter;

public class BulkProbe
{
    public static void main(String[] a) throws Exception
    {
        int mib = Integer.parseInt(a[0]);      // -1: do not call withMaxSSTableSizeInMiB
        int rows = Integer.parseInt(a[1]);
        String out = a[2];                     // existing empty dir .../probe_ks/t
        String schema = "CREATE TABLE probe_ks.t (k bigint, c int, v blob, PRIMARY KEY (k, c)) WITH compression = {'enabled': 'false'}";
        CQLSSTableWriter.Builder b = CQLSSTableWriter.builder().inDirectory(out).forTable(schema)
                                                     .using("INSERT INTO probe_ks.t (k, c, v) VALUES (?, ?, ?)");
        if (mib != -1) b.withMaxSSTableSizeInMiB(mib);
        CQLSSTableWriter w = b.build();
        Random r = new Random(42);
        long t0 = System.nanoTime();
        for (int i = 0; i < rows; i++)
        {
            byte[] v = new byte[1024]; r.nextBytes(v);
            w.addRow((long) (i / 16), i % 16, ByteBuffer.wrap(v));
        }
        w.close();
        System.out.println("BULK done rows=" + rows + " secs=" + (System.nanoTime() - t0) / 1e9);
        System.exit(0);
    }
}
