// B13 data-template loader. Java driver 3.12.1 (shaded), protocol V4 (lesson: large v5 requests leak frame buffers).
// Creates b13.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) and inserts 64 partitions x 56 rows x 65,536 random bytes
// (3,670,016 value bytes per partition), 32 requests in flight.   java B13Load <host>
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;

public class B13Load {
    public static void main(String[] a) throws Exception {
        try (Cluster c = Cluster.builder().addContactPoint(a[0]).withProtocolVersion(ProtocolVersion.V4)
                 .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000)).withoutJMXReporting().withoutMetrics().build();
             Session s = c.connect()) {
            s.execute("CREATE KEYSPACE IF NOT EXISTS b13 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
            s.execute("CREATE TABLE IF NOT EXISTS b13.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))");
            PreparedStatement ps = s.prepare("INSERT INTO b13.t (pk, ck, v) VALUES (?, ?, ?)");
            ps.setConsistencyLevel(ConsistencyLevel.ONE);
            Semaphore sem = new Semaphore(32); Random r = new Random(13); long ok = 0; List<ResultSetFuture> fs = new ArrayList<>();
            for (int pk = 0; pk < 64; pk++) for (int ck = 0; ck < 56; ck++) {
                byte[] b = new byte[65536]; r.nextBytes(b);
                sem.acquire();
                ResultSetFuture f = s.executeAsync(ps.bind(pk, ck, ByteBuffer.wrap(b)));
                f.addListener(sem::release, MoreExecutors.directExecutor()); fs.add(f);
            }
            for (ResultSetFuture f : fs) { f.getUninterruptibly(); ok++; }
            Row row = s.execute("SELECT count(*) FROM b13.t").one();
            System.out.println("loaded " + ok + " rows; count(*) = " + row.getLong(0));
        }
        System.exit(0);
    }
}
