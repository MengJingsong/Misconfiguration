package stage4.pcca;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Map;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.service.paxos.PaxosState;
import org.apache.cassandra.utils.ObjectSizes;

/**
 * Stage-4 harness, cluster tier (amendment C4 (3), 2026-10-27) of paxos_cache_size-close-active--autonomous.
 * Observe-only helper called by the Byteman rule pcca.btm at the entry of StorageService.getConcurrentViewBuilders()
 * (i.e. on `nodetool getconcurrentviewbuilders`). Appends to the file named by -Dpcca.out one line
 *   PROBE,epoch_ms,cap_mib,n,W,wmin,wmax,D,Mtm,active
 * n = RECENT.size(); W = sum over entries of the weigher expression of PaxosState.java:74; D = ObjectSizes.measureDeep(RECENT);
 * Mtm = ObjectSizes.measureDeep(TableMetadata of one entry's committed update) (0 when empty); active = ACTIVE.size().
 * It never modifies any Cassandra state.
 */
public class PcacheProbe
{
    public static synchronized void report()
    {
        String out = System.getProperty("pcca.out");
        try (PrintWriter w = new PrintWriter(new FileWriter(out, true)))
        {
            try
            {
                long cap = DatabaseDescriptor.getPaxosCacheSizeInMiB();
                long W = 0, wmin = Long.MAX_VALUE, wmax = Long.MIN_VALUE;
                int n = 0;
                Object tm = null;
                for (Map.Entry<PaxosState.Key, PaxosState.Snapshot> e : PaxosState.RECENT.entrySet())
                {
                    PaxosState.Snapshot s = e.getValue();
                    long x = (s.accepted != null ? s.accepted.update.unsharedHeapSize() : 0L) + s.committed.update.unsharedHeapSize();
                    W += x;
                    n++;
                    wmin = Math.min(wmin, x);
                    wmax = Math.max(wmax, x);
                    if (tm == null)
                        tm = s.committed.update.metadata();
                }
                if (n == 0) { wmin = -1; wmax = -1; }
                long D = ObjectSizes.measureDeep(PaxosState.RECENT);
                long mtm = tm == null ? 0 : ObjectSizes.measureDeep(tm);
                int active = PaxosState.ACTIVE.size();
                w.println("PROBE," + System.currentTimeMillis() + ',' + cap + ',' + n + ',' + W + ',' + wmin + ',' + wmax + ',' + D + ',' + mtm + ',' + active);
            }
            catch (Throwable t)
            {
                w.println("PROBE-ERROR," + System.currentTimeMillis() + ',' + t);
            }
        }
        catch (Throwable t)
        {
            t.printStackTrace();
        }
    }
}
