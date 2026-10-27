/*
 * Stage-4 harness (not upstream): unit tier of
 * max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous (B2, with amendments A1-A2 of 2026-10-26).
 * Copied into test/unit/org/apache/cassandra/db/compaction/ of a copy-source.sh tree.
 * It only RECORDS readings ("R <section> <key> <value>" lines in $L0_OUT); predictions are judged by
 * unit-analyze.py, so a failed prediction is never a failed test.
 */
package org.apache.cassandra.db.compaction;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.*;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.UpdateBuilder;
import org.apache.cassandra.Util;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.lifecycle.LifecycleTransaction;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.io.sstable.metadata.StatsMetadata;
import org.apache.cassandra.schema.CompactionParams;
import org.apache.cassandra.schema.KeyspaceParams;

public class LeveledManifestL0Test
{
    static final String KS = "L0Cap";
    static final long MIB = 1024L * 1024L;
    static final int[] NS = { 31, 32, 33, 64, 200 };
    static final int L1_SSTABLES = 30;
    static final int REPS = Integer.parseInt(System.getenv().getOrDefault("L0_REPS", "3"));
    static final Random RND = new Random(20261026L);

    @BeforeClass
    public static void defineSchema()
    {
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
                                    SchemaLoader.standardCFMD(KS, "mt32").compaction(lcs("32")),
                                    SchemaLoader.standardCFMD(KS, "mt8").compaction(lcs("8")));
    }

    static CompactionParams lcs(String maxThreshold)
    {
        Map<String, String> m = new HashMap<>();
        m.put("sstable_size_in_mb", "1");
        m.put("fanout_size", "10");
        m.put("max_threshold", maxThreshold);
        return CompactionParams.lcs(m);
    }

    static void out(String section, String key, Object value)
    {
        String line = "R " + section + " " + key + " " + value;
        System.out.println(line);
        try (PrintWriter w = new PrintWriter(new FileWriter(System.getenv().getOrDefault("L0_OUT", "/tmp/l0-readings.txt"), true)))
        {
            w.println(line);
        }
        catch (IOException e) { throw new RuntimeException(e); }
    }

    static ColumnFamilyStore fresh(String name)
    {
        DatabaseDescriptor.setDisableSTCSInL0(false);
        ColumnFamilyStore c = Keyspace.open(KS).getColumnFamilyStore(name);
        c.truncateBlocking();
        c.disableAutoCompaction();
        return c;
    }

    static LeveledCompactionStrategy lcsOf(ColumnFamilyStore c)
    {
        return (LeveledCompactionStrategy) c.getCompactionStrategyManager().getStrategies().get(1).get(0);
    }

    /** small L0 sstable: 100 rows x 100 B, unique keys, the same key range in every flush (so L0 sstables overlap) */
    static void flushSmall(ColumnFamilyStore c, int flush)
    {
        for (int r = 0; r < 100; r++)
        {
            byte[] b = new byte[100];
            RND.nextBytes(b);
            UpdateBuilder.create(c.metadata(), String.format("k%06d_%04d", r, flush)).newRow("c").add("val", ByteBuffer.wrap(b)).applyUnsafe();
        }
        Util.flush(c);
    }

    /** ~1 MiB sstable in its own key range ("p<idx>_..."), then moved to level 1 and announced to the strategy */
    static void flushToL1(ColumnFamilyStore c, int idx) throws IOException
    {
        Set<SSTableReader> before = new HashSet<>(c.getLiveSSTables());
        for (int r = 0; r < 1000; r++)
        {
            byte[] b = new byte[1024];
            RND.nextBytes(b);
            UpdateBuilder.create(c.metadata(), String.format("p%03d_%06d", idx, r)).newRow("c").add("val", ByteBuffer.wrap(b)).applyUnsafe();
        }
        Util.flush(c);
        Set<SSTableReader> added = new HashSet<>(c.getLiveSSTables());
        added.removeAll(before);
        if (added.size() != 1)
            throw new IllegalStateException("expected one new sstable, got " + added.size());
        SSTableReader s = added.iterator().next();
        StatsMetadata old = s.getSSTableMetadata();
        s.mutateLevelAndReload(1);
        c.getTracker().notifySSTableMetadataChanged(s, old);
    }

    static boolean overlaps(SSTableReader a, SSTableReader b)
    {
        return a.getFirst().compareTo(b.getLast()) <= 0 && b.getFirst().compareTo(a.getLast()) <= 0;
    }

    static void record(String section, String tag, ColumnFamilyStore c, LeveledManifest.CompactionCandidate cand, int l0before, SSTableReader held)
    {
        LeveledCompactionStrategy st = lcsOf(c);
        out(section, tag + ".l0count", st.getLevelSize(0));
        out(section, tag + ".l0countBeforeRead", l0before);
        if (cand == null)
        {
            out(section, tag + ".candidate", "null");
            return;
        }
        int minL = 99, maxL = -1;
        for (SSTableReader s : cand.sstables)
        {
            minL = Math.min(minL, s.getSSTableLevel());
            maxL = Math.max(maxL, s.getSSTableLevel());
        }
        out(section, tag + ".candidate", "non-null");
        out(section, tag + ".size", cand.sstables.size());
        out(section, tag + ".level", cand.level);
        out(section, tag + ".maxSSTableBytes", cand.maxSSTableBytes);
        out(section, tag + ".stcs", cand.level == 0 && cand.maxSSTableBytes == Long.MAX_VALUE);
        out(section, tag + ".inputLevels", minL + ".." + maxL);
        out(section, tag + ".containsHeld", held != null && cand.sstables.contains(held));
    }

    /** one route on one table, N ascending; both flag values are read at every N. */
    void series(String route, String table, int rep) throws IOException
    {
        String pre = route + "." + table + ".rep" + rep;
        ColumnFamilyStore c = fresh(table);
        LeveledCompactionStrategy st = lcsOf(c);
        LifecycleTransaction held = null;
        SSTableReader heldReader = null;
        int flushes = 0;
        String err = "none";
        try
        {
            if (route.equals("R1"))
                for (int i = 0; i < L1_SSTABLES; i++)
                    flushToL1(c, i);
            if (route.equals("R2"))
            {
                flushSmall(c, flushes++);
                SSTableReader first = c.getLiveSSTables().iterator().next();
                heldReader = first;
                held = c.getTracker().tryModify(first, OperationType.COMPACTION);
                out("setup", pre + ".heldNotNull", held != null);
                out("setup", pre + ".compactingCount", c.getTracker().getCompacting().size());
            }
            out("setup", pre + ".L1bytes", st.getAllLevelSizeBytes()[1]);
            out("setup", pre + ".L1target", LeveledManifest.maxBytesForLevel(1, 10, MIB));
            out("setup", pre + ".L1count", st.getLevelSize(1));
            for (int n : NS)
            {
                while (flushes < n)
                    flushSmall(c, flushes++);
                // overlap instrument check: first and last L0 sstable overlap each other
                List<SSTableReader> l0 = new ArrayList<>();
                for (SSTableReader s : c.getLiveSSTables())
                    if (s.getSSTableLevel() == 0) l0.add(s);
                boolean ov = true;
                for (SSTableReader s : l0) ov &= overlaps(l0.get(0), s);
                out("setup", pre + ".N" + n + ".l0allOverlapFirst", ov);
                out("setup", pre + ".N" + n + ".l0sstables", l0.size());
                for (boolean flag : new boolean[] { false, true })
                {
                    DatabaseDescriptor.setDisableSTCSInL0(flag);
                    int before = st.getLevelSize(0);
                    LeveledManifest.CompactionCandidate cand = st.manifest.getCompactionCandidates();
                    record("read", pre + ".N" + n + ".flag" + flag, c, cand, before, heldReader);
                    if (!flag)
                        out("read", pre + ".N" + n + ".estimatedTasks", st.manifest.getEstimatedTasks());
                    DatabaseDescriptor.setDisableSTCSInL0(false);
                }
            }
        }
        catch (RuntimeException e) { err = e.toString(); }
        finally
        {
            DatabaseDescriptor.setDisableSTCSInL0(false);
            if (held != null) held.abort();
        }
        out("read", pre + ".error", err);
        out("read", pre + ".finalL0", st.getLevelSize(0));
        c.truncateBlocking();
    }

    @Test
    public void routes() throws IOException
    {
        for (int rep = 1; rep <= REPS; rep++)
            for (String table : new String[] { "mt32", "mt8" })
                for (String route : new String[] { "R0", "R1", "R2" })
                    series(route, table, rep);
    }

    /** B2e step 3 on a fresh arm: execute the STCS candidate of R1 once; the L0 count must drop by size-1 */
    @Test
    public void execute() throws IOException
    {
        for (int rep = 1; rep <= REPS; rep++)
            for (String table : new String[] { "mt32", "mt8" })
                for (int n : new int[] { 33, 64 })
                {
                    String pre = "exec." + table + ".N" + n + ".rep" + rep;
                    ColumnFamilyStore c = fresh(table);
                    LeveledCompactionStrategy st = lcsOf(c);
                    for (int i = 0; i < L1_SSTABLES; i++)
                        flushToL1(c, i);
                    for (int i = 0; i < n; i++)
                        flushSmall(c, i);
                    int l0before = st.getLevelSize(0);
                    int totalBefore = c.getLiveSSTables().size();
                    AbstractCompactionTask t = st.getNextBackgroundTask(0);
                    out("exec", pre + ".taskNonNull", t != null);
                    if (t != null)
                    {
                        t.execute(ActiveCompactionsTracker.NOOP);
                        out("exec", pre + ".taskClass", t.getClass().getSimpleName());
                    }
                    out("exec", pre + ".l0before", l0before);
                    out("exec", pre + ".l0after", st.getLevelSize(0));
                    out("exec", pre + ".l1countAfter", st.getLevelSize(1));
                    out("exec", pre + ".totalBefore", totalBefore);
                    out("exec", pre + ".totalAfter", c.getLiveSSTables().size());
                    c.truncateBlocking();
                }
    }

    /** B2h positive control: L1 at 3x target, flag true, N = 32; execute the L1->L2 candidates until L1 is at target */
    @Test
    public void positiveControl() throws IOException
    {
        for (int rep = 1; rep <= REPS; rep++)
        {
            String pre = "ctl.rep" + rep;
            ColumnFamilyStore c = fresh("mt32");
            LeveledCompactionStrategy st = lcsOf(c);
            for (int i = 0; i < L1_SSTABLES; i++)
                flushToL1(c, i);
            for (int i = 0; i < 32; i++)
                flushSmall(c, i);
            long target = LeveledManifest.maxBytesForLevel(1, 10, MIB);
            out("ctl", pre + ".L1target", target);
            out("ctl", pre + ".L1before", st.getAllLevelSizeBytes()[1]);
            out("ctl", pre + ".L0before", st.getLevelSize(0));
            DatabaseDescriptor.setDisableSTCSInL0(true);
            int tasks = 0;
            String firstCand = "none";
            try
            {
                while (tasks < 200 && st.getAllLevelSizeBytes()[1] > (long) (target * 1.001))
                {
                    LeveledManifest.CompactionCandidate cand = st.manifest.getCompactionCandidates();
                    if (tasks == 0)
                        firstCand = cand == null ? "null" : "level=" + cand.level + ",size=" + cand.sstables.size() + ",inputLevel=" + cand.sstables.iterator().next().getSSTableLevel();
                    AbstractCompactionTask t = st.getNextBackgroundTask(0);
                    if (t == null) break;
                    t.execute(ActiveCompactionsTracker.NOOP);
                    tasks++;
                }
            }
            finally { DatabaseDescriptor.setDisableSTCSInL0(false); }
            out("ctl", pre + ".firstCandidate", firstCand);
            out("ctl", pre + ".tasks", tasks);
            out("ctl", pre + ".L1after", st.getAllLevelSizeBytes()[1]);
            out("ctl", pre + ".L2after", st.getAllLevelSizeBytes()[2]);
            out("ctl", pre + ".L0after", st.getLevelSize(0));
            c.truncateBlocking();
            out("ctl", pre + ".bytesAfterTruncate", st.getAllLevelSizeBytes()[0] + st.getAllLevelSizeBytes()[1] + st.getAllLevelSizeBytes()[2]);
        }
    }
}
