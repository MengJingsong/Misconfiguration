/* Stage-4 unit tier (B2) of filename_length-validatesnapshotname-snapshotname--autonomous. Copied by unit-run.sh into
 * test/unit/org/apache/cassandra/db/. Not part of Cassandra. Output lines "STAGE4 ..." go to -Dstage4.out. */
package org.apache.cassandra.db;

import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;

import org.junit.Test;

import org.apache.cassandra.config.CassandraRelevantProperties;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.distributed.shared.WithProperties;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.schema.SchemaConstants;

public class SnapshotNameLengthTest extends CQLTester
{
    static PrintWriter out;
    static int checks = 0, bad = 0;

    static void p(String s) { System.out.println(s); out.println(s); out.flush(); }

    static void check(String what, boolean ok)
    {
        checks++; if (!ok) bad++;
        p("STAGE4 check " + what + (ok ? " ok" : " MISMATCH"));
    }

    static long heap()
    {
        for (int i = 0; i < 3; i++) { System.gc(); try { Thread.sleep(100); } catch (InterruptedException e) {} }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    /** sum of regular-file sizes (each link counted), count of files, in a directory */
    static long[] dirBytes(Path d) throws IOException
    {
        long[] r = new long[3]; // bytes, files, entries(dirs+files)
        if (!Files.exists(d)) return new long[]{ -1, -1, -1 };
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(d))
        {
            for (Path f : ds) { r[2]++; if (Files.isRegularFile(f)) { r[0] += Files.size(f); r[1]++; } }
        }
        return r;
    }

    /** physical bytes under a root: each inode counted once (hard links once), plus directory count */
    static long[] physical(Path root) throws IOException
    {
        final Set<Object> seen = new HashSet<>();
        final long[] r = new long[2];
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            public FileVisitResult visitFile(Path f, BasicFileAttributes a) {
                if (seen.add(a.fileKey())) r[0] += a.size(); return FileVisitResult.CONTINUE; }
            public FileVisitResult preVisitDirectory(Path d, BasicFileAttributes a) { r[1]++; return FileVisitResult.CONTINUE; }
        });
        return r;
    }

    static String name(int L) { return String.join("", Collections.nCopies(L, "a")); }

    @Test
    public void run() throws Throwable
    {
        out = new PrintWriter(new java.io.FileWriter(System.getProperty("stage4.out", "/tmp/stage4.out"), true));
        p("STAGE4 info FILENAME_LENGTH=" + SchemaConstants.FILENAME_LENGTH + " default_validation=" + CassandraRelevantProperties.SNAPSHOT_NAME_VALIDATION.getDefaultValue());
        int[] Ls = { 1, 100, 255, 256, 300 };
        int[] Ns = { 1000, 100000 };
        Map<String, Double> fileBytes = new TreeMap<>();
        Map<String, Double> physDelta = new TreeMap<>();
        Map<String, Double> heapDelta = new TreeMap<>();
        Map<String, Long> manifestSz = new TreeMap<>();
        Map<String, Long> schemaSz = new TreeMap<>();
        for (int N : Ns)
        {
            createTable("create table %s (id int primary key, v blob)");
            String value = String.join("", Collections.nCopies(100, "x"));
            for (int i = 0; i < N; i++)
                execute("insert into %s (id, v) values (?, textAsBlob(?))", i, value);
            ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
            cfs.disableAutoCompaction();
            cfs.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
            Collection<SSTableReader> live = cfs.getLiveSSTables();
            p("STAGE4 info N=" + N + " sstables=" + live.size() + " datasize=" + cfs.metric.liveDiskSpaceUsed.getCount());
            Path tableDir = cfs.getDirectories().getDirectoryForNewSSTables().toPath();
            Path snapRoot = tableDir.resolve("snapshots");
            for (boolean validation : new boolean[]{ false, true })
            {
                for (int L : Ls)
                {
                    for (int rep = 1; rep <= 3; rep++)
                    {
                        String nm = name(L);
                        String outcome; String msg = "";
                        long[] pre = physical(tableDir);
                        long h0 = heap();
                        try (WithProperties wp = new WithProperties().set(CassandraRelevantProperties.SNAPSHOT_NAME_VALIDATION, validation))
                        {
                            Throwable t = null;
                            try { cfs.snapshotWithoutMemtable(nm); } catch (Throwable e) { t = e; }
                            long h1 = heap();
                            long[] post = physical(tableDir);
                            Path sd = snapRoot.resolve(nm);
                            long[] d = dirBytes(sd);
                            long msz = Files.exists(sd.resolve("manifest.json")) ? Files.size(sd.resolve("manifest.json")) : -1;
                            long ssz = Files.exists(sd.resolve("schema.cql")) ? Files.size(sd.resolve("schema.cql")) : -1;
                            if (t == null) outcome = "accepted";
                            else { outcome = "threw:" + t.getClass().getSimpleName(); msg = String.valueOf(t.getMessage()); if (msg.length() > 60) msg = msg.substring(0, 60); msg = msg.replaceAll("a{20,}", "a..."); }
                            p("STAGE4 case N=" + N + " validation=" + validation + " L=" + L + " rep=" + rep + " outcome=" + outcome
                              + " snapFileBytes=" + d[0] + " snapFiles=" + d[1] + " snapEntries=" + d[2] + " manifest=" + msz + " schema=" + ssz
                              + " physDeltaBytes=" + (post[0] - pre[0]) + " dirsDelta=" + (post[1] - pre[1]) + " heapDelta=" + (h1 - h0) + " msg=" + msg.replace(' ', '_'));
                            String key = "N=" + N + ",v=" + validation + ",L=" + L;
                            boolean expectAccept = L <= 255;
                            if (rep == 1)
                            {
                                check(key + "_accept_iff_L<=255", (t == null) == expectAccept);
                                if (!expectAccept)
                                {
                                    check(key + "_no_snapshot_dir", d[0] == -1);
                                    boolean line2187 = t != null && msg.startsWith("Snapshot name must not be more");
                                    check(key + (validation ? "_IAE_line2187_text" : "_not_line2187_text_(OS)"), validation ? (t instanceof IllegalArgumentException && line2187) : (t != null && !line2187));
                                }
                            }
                            if (t == null)
                            {
                                fileBytes.merge(key, (double) d[0] / 3, Double::sum);
                                physDelta.merge(key, (double) (post[0] - pre[0]) / 3, Double::sum);
                                heapDelta.merge(key, (double) (h1 - h0) / 3, Double::sum);
                                manifestSz.put(key, msz); schemaSz.put(key, ssz);
                                cfs.clearSnapshot(nm);
                                check(key + "_rep" + rep + "_cleared", !Files.exists(sd));
                            }
                        }
                    }
                }
            }
            // across-L comparisons per (N, validation)
            for (boolean v : new boolean[]{ false, true })
            {
                String k1 = "N=" + N + ",v=" + v + ",L=1", k100 = "N=" + N + ",v=" + v + ",L=100", k255 = "N=" + N + ",v=" + v + ",L=255";
                check("N=" + N + ",v=" + v + "_snapFileBytes_equal_L1_L100_L255", fileBytes.get(k1).equals(fileBytes.get(k100)) && fileBytes.get(k1).equals(fileBytes.get(k255)));
                check("N=" + N + ",v=" + v + "_manifest_schema_sizes_equal", manifestSz.get(k1).equals(manifestSz.get(k100)) && manifestSz.get(k1).equals(manifestSz.get(k255)) && schemaSz.get(k1).equals(schemaSz.get(k255)));
                check("N=" + N + ",v=" + v + "_physDelta_L255_minus_L1_<=64KiB", Math.abs(physDelta.get(k255) - physDelta.get(k1)) <= 65536);
                check("N=" + N + ",v=" + v + "_heapDelta_L255_minus_L1_<1MiB", Math.abs(heapDelta.get(k255) - heapDelta.get(k1)) < 1048576);
                p("STAGE4 info N=" + N + " v=" + v + " mean snapFileBytes L1/L100/L255 = " + fileBytes.get(k1) + "/" + fileBytes.get(k100) + "/" + fileBytes.get(k255)
                  + " physDelta " + physDelta.get(k1) + "/" + physDelta.get(k100) + "/" + physDelta.get(k255) + " heapDelta " + heapDelta.get(k1) + "/" + heapDelta.get(k100) + "/" + heapDelta.get(k255));
            }
        }
        for (boolean v : new boolean[]{ false, true })
        {
            double small = fileBytes.get("N=1000,v=" + v + ",L=100"), big = fileBytes.get("N=100000,v=" + v + ",L=100");
            check("v=" + v + "_positive_control_snapFileBytes_N100k_>=5x_N1k (" + big + " vs " + small + ")", big >= 5 * small);
        }
        p("STAGE4 summary checks=" + checks + " mismatches=" + bad);
        out.close();
    }
}
