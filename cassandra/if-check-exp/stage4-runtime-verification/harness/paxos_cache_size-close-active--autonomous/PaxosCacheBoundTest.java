/*
 * Stage-4 harness, unit tier (B2, amendments U1-U7 of 2026-10-27) of
 * cassandra/if-check-exp/stage3-ai-deep-read/cases/paxos_cache_size-close-active--autonomous.md.
 * Copied into test/unit/org/apache/cassandra/service/paxos/ of the run clone only for the run.
 *
 * System properties (passed through -Dtest.jvm.args): paxos.cap = <MiB> | auto, paxos.v = value bytes, paxos.n = proposals.
 * Output (stdout, one line per write): PCB-START, PCB sample lines i,W,n,D,active,wmin,wmax, PCB-END.
 */
package org.apache.cassandra.service.paxos;

import java.nio.ByteBuffer;
import java.util.Random;

import com.google.common.collect.Iterables;
import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.partitions.PartitionUpdate;
import org.apache.cassandra.gms.Gossiper;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.FBUtilities;
import org.apache.cassandra.utils.ObjectSizes;

import static org.junit.Assert.assertTrue;

public class PaxosCacheBoundTest
{
    static TableMetadata metadata;
    static String capProp;

    @BeforeClass
    public static void setUpClass() throws Throwable
    {
        capProp = System.getProperty("paxos.cap", "auto");
        DatabaseDescriptor.daemonInitialization(() -> {
            Config c = DatabaseDescriptor.loadConfig();
            if (!"auto".equals(capProp))
                c.paxos_cache_size = new DataStorageSpec.LongMebibytesBound(Long.parseLong(capProp) + "MiB");
            else
                c.paxos_cache_size = null;
            return c;
        });
        SchemaLoader.loadSchema();
        SchemaLoader.schemaDefinition("PaxosCacheBoundTest");
        metadata = Keyspace.open("PaxosCacheBoundTestKeyspace1").getColumnFamilyStore("Standard1").metadata.get();
    }

    @AfterClass
    public static void stopGossiper()
    {
        Gossiper.instance.stop();
    }

    static long weight(PaxosState.Snapshot s)
    {
        // the weigher expression of PaxosState.java:74, without the int saturation (weights here are far below 2^31)
        return (s.accepted != null ? s.accepted.update.unsharedHeapSize() : 0L) + s.committed.update.unsharedHeapSize();
    }

    static long[] sample(int i)
    {
        long W = 0, wmin = Long.MAX_VALUE, wmax = Long.MIN_VALUE;
        int n = 0;
        for (PaxosState.Snapshot s : PaxosState.RECENT.values())
        {
            long w = weight(s);
            W += w;
            n++;
            wmin = Math.min(wmin, w);
            wmax = Math.max(wmax, w);
        }
        if (n == 0) { wmin = -1; wmax = -1; }
        long D = ObjectSizes.measureDeep(PaxosState.RECENT);
        int active = PaxosState.ACTIVE.size();
        System.out.println("PCB," + i + ',' + W + ',' + n + ',' + D + ',' + active + ',' + wmin + ',' + wmax);
        return new long[]{ W, n, D, active };
    }

    @Test
    public void bound() throws Throwable
    {
        int V = Integer.getInteger("paxos.v", 8192);
        int N = Integer.getInteger("paxos.n", 40000);
        long capMiB = DatabaseDescriptor.getPaxosCacheSizeInMiB();
        System.out.println("PCB-START,cap_prop=" + capProp + ",cap_mib=" + capMiB + ",max_bytes=" + (capMiB << 20) + ",v=" + V + ",n=" + N
                           + ",variant=" + DatabaseDescriptor.getPaxosVariant() + ",purging=" + DatabaseDescriptor.paxosStatePurging()
                           + ",total_memory=" + Runtime.getRuntime().totalMemory() + ",max_memory=" + Runtime.getRuntime().maxMemory());
        Random rnd = new Random(42);
        long base = FBUtilities.timestampMicros();
        int accepted = 0;
        long d1 = -1;
        for (int i = 0; i < N; i++)
        {
            byte[] b = new byte[V];
            for (int j = 0; j < V; j++)
                b[j] = (byte) (0x20 + rnd.nextInt(0x7f - 0x20));
            String key = "k" + i;
            RowUpdateBuilder builder = new RowUpdateBuilder(metadata, base + i, key);
            builder.clustering("a").add("val", ByteBuffer.wrap(b));
            PartitionUpdate update = Iterables.getOnlyElement(builder.build().getPartitionUpdates());
            Ballot ballot = Ballot.atUnixMicrosWithLsb(base + i, 0, Ballot.Flag.GLOBAL);
            Boolean ok = PaxosState.legacyPropose(new Commit.Accepted(ballot, update));
            if (Boolean.TRUE.equals(ok))
                accepted++;
            int done = i + 1;
            if (done == 1 || done % 1000 == 0 || done == N)
            {
                long[] r = sample(done);
                if (done == 1 && r[1] == 1)
                    d1 = r[2];
            }
        }
        System.out.println("PCB-END,proposed=" + N + ",accepted=" + accepted + ",d1=" + d1);
        assertTrue("every legacyPropose must return true", accepted == N);
    }
}
