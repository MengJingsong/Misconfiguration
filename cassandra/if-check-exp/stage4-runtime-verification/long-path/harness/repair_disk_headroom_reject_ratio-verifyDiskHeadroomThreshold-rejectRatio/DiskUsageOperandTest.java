/*
 * Stage-4 harness, unit tier U3 of repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio (case 9e).
 * Not upstream. Copy into test/unit/org/apache/cassandra/service/disk/usage/. A real DiskUsageMonitor over a temporary
 * directory (its test constructor), memtables stubbed to 0, the cap set through Guardrails.
 * Prints "STAGE4 check <name> <expected> <actual> ok|MISMATCH" (also to -Dstage4.out); fails at the end on a mismatch.
 */
package org.apache.cassandra.service.disk.usage;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.io.RandomAccessFile;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

import com.google.common.collect.HashMultimap;
import com.google.common.collect.Multimap;
import org.junit.Assert;
import org.junit.Test;

import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.Directories;
import org.apache.cassandra.db.guardrails.Guardrails;
import org.apache.cassandra.io.util.File;

import static org.mockito.Mockito.doCallRealMethod;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.spy;

public class DiskUsageOperandTest extends CQLTester
{
    static PrintWriter out;
    static int checks = 0, mismatches = 0;

    static void line(String s) { System.out.println(s); if (out != null) { out.println(s); out.flush(); } }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        checks++; if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    @Test
    public void operand() throws Throwable
    {
        String f = System.getProperty("stage4.out");
        if (f != null) out = new PrintWriter(new FileWriter(f, true));
        Path dir = Files.createTempDirectory("stage4-hdr-u3");
        Directories.DataDirectory dd = new Directories.DataDirectory(new File(dir));
        FileStore store = Files.getFileStore(dir);
        Multimap<FileStore, Directories.DataDirectory> dirs = HashMultimap.create();
        dirs.put(store, dd);
        DiskUsageMonitor monitor = spy(new DiskUsageMonitor(() -> dirs));
        doCallRealMethod().when(monitor).getDiskUsage();
        doReturn(0L).when(monitor).getAllMemtableSize();
        try
        {
            Guardrails.instance.setDataDiskUsageMaxDiskSize("1048576B");
            check("U3_cap_readback", "1048576B", Guardrails.instance.getDataDiskUsageMaxDiskSize());
            check("U3_empty", 0.0, monitor.getDiskUsage());
            Files.write(dir.resolve("one.bin"), new byte[1]);
            check("U3_one_byte_rounds_up", 1.0E-5, monitor.getDiskUsage());
            try (RandomAccessFile raf = new RandomAccessFile(dir.resolve("sparse.bin").toFile(), "rw")) { raf.setLength(524288); }
            line("STAGE4 info sparse apparent " + Files.size(dir.resolve("sparse.bin")));
            check("U3_sparse_apparent", 0.50001, monitor.getDiskUsage());
            Files.createLink(dir.resolve("link.bin"), dir.resolve("sparse.bin"));
            check("U3_hard_link_counted_twice", 1.00001, monitor.getDiskUsage());
            Path snap = Files.createDirectories(dir.resolve("snapshots").resolve("x"));
            Files.write(snap.resolve("snap.bin"), new byte[1000]);
            check("U3_snapshot_counted", 1.00096, monitor.getDiskUsage());
            Guardrails.instance.setDataDiskUsageMaxDiskSize(null);
            long used = 1 + 524288 + 524288 + 1000;
            long usable = store.getUsableSpace();
            double expect = new BigDecimal(used).divide(new BigDecimal(used + usable), 5, RoundingMode.UP).doubleValue();
            double got = monitor.getDiskUsage();
            line("STAGE4 info uncapped used " + used + " usable " + usable + " expect " + expect + " got " + got);
            check("U3_uncapped_within_one_step", true, Math.abs(got - expect) <= 1.0E-5 + 1e-12);
        }
        finally
        {
            Guardrails.instance.setDataDiskUsageMaxDiskSize(null);
        }
        line("STAGE4 summary checks " + checks + " mismatches " + mismatches);
        Assert.assertEquals(0, mismatches);
    }
}
