package stage4.rfp;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Queue;

import org.apache.cassandra.db.ReadCommand;
import org.apache.cassandra.db.rows.Rows;
import org.apache.cassandra.net.Message;
import org.apache.cassandra.utils.ObjectSizes;
import org.apache.cassandra.utils.concurrent.Accumulator;

/**
 * Stage-4 harness, cluster tier (amendment C4 of 2026-10-27) of cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.
 * Observe-only helper called by the Byteman rules in rfp.btm on the coordinator (node 1). It reads fields by reflection and
 * measures objects with ObjectSizes.measureDeep; it never modifies Cassandra state, and every Throwable is caught.
 * Appends to the file named by -Drfp.out:
 *   PEAK,kind,epoch_ms,table,failT,current,max,nonNull,bytes,shell,perBuilder,key
 *     kind = throw    (AT THROW in ReplicaFilteringProtection.incrementCachedRows: current = the count that tripped the check)
 *          | populate (AT ENTRY of ReplicaFilteringProtection$QueryMergeListener.populate: a partition fully consumed)
 *     current/max = currentRowsCached/maxRowsCached; nonNull = rows held in all PartitionBuilder.contents (+ non-empty static rows);
 *     bytes = measureDeep(Object[] of those rows) - shell, shell = sizeOfReferenceArray(nonNull);
 *     perBuilder = per builder "contentsSize/partitionRowsCached" separated by spaces.
 *   RESP,epoch_ms,table,nResponses,bytesTotal,perResponse
 *     (AT ENTRY of DataResolver.resolveWithReplicaFilteringProtection: measureDeep of each response payload, "from:bytes")
 */
public class RfpProbe
{
    private static synchronized void line(String s)
    {
        String out = System.getProperty("rfp.out");
        try (PrintWriter w = new PrintWriter(new FileWriter(out, true)))
        {
            w.println(s);
        }
        catch (Throwable t)
        {
            t.printStackTrace();
        }
    }

    private static Object field(Object o, String name) throws Exception
    {
        for (Class<?> c = o.getClass(); c != null; c = c.getSuperclass())
        {
            try
            {
                Field f = c.getDeclaredField(name);
                f.setAccessible(true);
                return f.get(o);
            }
            catch (NoSuchFieldException e)
            {
                // try the superclass
            }
        }
        throw new NoSuchFieldException(name + " in " + o.getClass().getName());
    }

    public static void peak(Object target, String kind)
    {
        long now = System.currentTimeMillis();
        try
        {
            Object rfp = kind.equals("populate") ? field(target, "this$0") : target;
            int cur = (Integer) field(rfp, "currentRowsCached");
            int max = (Integer) field(rfp, "maxRowsCached");
            int fail = (Integer) field(rfp, "cachedRowsFailThreshold");
            String table = ((ReadCommand) field(rfp, "command")).metadata().name;
            Object ml = field(rfp, "mergeListener");
            Object pl = field(ml, "currentListener");
            List<Object> rows = new ArrayList<>();
            StringBuilder per = new StringBuilder();
            String key = "-";
            if (pl != null)
            {
                key = String.valueOf(field(pl, "key"));
                for (Object b : (List<?>) field(pl, "builders"))
                {
                    Queue<?> q = (Queue<?>) field(b, "contents");
                    Object sr = field(b, "staticRow");
                    int prc = (Integer) field(b, "partitionRowsCached");
                    rows.addAll(q);
                    if (sr != null && sr != Rows.EMPTY_STATIC_ROW)
                        rows.add(sr);
                    if (per.length() > 0)
                        per.append(' ');
                    per.append(q.size()).append('/').append(prc);
                }
            }
            Object[] arr = rows.toArray();
            long shell = ObjectSizes.sizeOfReferenceArray(arr.length);
            long bytes = ObjectSizes.measureDeep(arr) - shell;
            line("PEAK," + kind + ',' + now + ',' + table + ',' + fail + ',' + cur + ',' + max + ',' + arr.length + ',' + bytes + ',' + shell + ',' + per + ',' + key.replace(',', ';'));
        }
        catch (Throwable t)
        {
            line("PEAK-ERROR," + kind + ',' + now + ',' + String.valueOf(t).replace(',', ';'));
        }
    }

    public static void resp(Object resolver)
    {
        long now = System.currentTimeMillis();
        try
        {
            String table = ((ReadCommand) field(resolver, "command")).metadata().name;
            Collection<?> msgs = ((Accumulator<?>) field(resolver, "responses")).snapshot();
            long total = 0;
            StringBuilder per = new StringBuilder();
            for (Object o : msgs)
            {
                Message<?> m = (Message<?>) o;
                long b = ObjectSizes.measureDeep(m.payload);
                total += b;
                if (per.length() > 0)
                    per.append(' ');
                per.append(m.from()).append(':').append(b);
            }
            line("RESP," + now + ',' + table + ',' + msgs.size() + ',' + total + ',' + per);
        }
        catch (Throwable t)
        {
            line("RESP-ERROR," + now + ',' + String.valueOf(t).replace(',', ';'));
        }
    }
}
