/*
 * Stage-4 harness, unit tier (B2, amended 2026-10-27) of
 * max_hints_size_per_host-shouldHint-maxHintsSize--autonomous.
 *
 * Copied into test/unit/org/apache/cassandra/hints/ of the run clone only for the run, then removed.
 * For each C in hsc.cs (MiB, default 0,1,4,16): a fresh fake dead endpoint 192.168.1.(10+j) with a fresh host id;
 * N = hsc.n (default 20000) iterations of
 *     if (StorageProxy.shouldHint(replica)) StorageProxy.submitHint(mutation_i, replica, null);
 * with a wait on StorageMetrics.totalHintsInProgress == 0 and HintsService.flushAndFsyncBlockingly after every
 * 256th iteration and after the last. Prints one "HSC ..." line per value; never fails on a relation (PASS/FAIL lines).
 */
package org.apache.cassandra.hints;

import java.nio.ByteBuffer;
import java.util.List;
import java.util.UUID;

import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.gms.EndpointState;
import org.apache.cassandra.gms.Gossiper;
import org.apache.cassandra.gms.HeartBeatState;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.locator.Replica;
import org.apache.cassandra.metrics.StorageMetrics;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.service.StorageProxy;
import org.apache.cassandra.service.StorageService;
import org.apache.cassandra.utils.FBUtilities;

import static org.apache.cassandra.locator.ReplicaUtils.full;

public class HintsSizeCapUnitTest extends CQLTester
{
    static final int BATCH = 256;
    static final long HEADER = 42; // HintsDescriptor.serialize: 4+8+16+4+4+2("{}")+4

    static void out(String s) { System.out.println("HSC " + s); System.out.flush(); }

    static long dirBytes(UUID id)
    {
        long sum = 0;
        File dir = DatabaseDescriptor.getHintsDirectory();
        for (File f : dir.tryList())
        {
            String n = f.name();
            if (n.startsWith(id.toString() + "-") && n.endsWith(".hints"))
                sum += f.length();
        }
        return sum;
    }

    static int fileCount(UUID id)
    {
        int c = 0;
        for (File f : DatabaseDescriptor.getHintsDirectory().tryList())
            if (f.name().startsWith(id.toString() + "-") && f.name().endsWith(".hints"))
                c++;
        return c;
    }

    static void waitNoHintsInProgress() throws InterruptedException
    {
        long deadline = System.currentTimeMillis() + 60_000;
        while (StorageMetrics.totalHintsInProgress.getCount() != 0)
        {
            if (System.currentTimeMillis() > deadline)
                throw new AssertionError("hints in progress did not drain: " + StorageMetrics.totalHintsInProgress.getCount());
            Thread.sleep(1);
        }
    }

    static String rel(String name, boolean ok, String detail)
    {
        String s = "REL " + name + " " + (ok ? "PASS" : "FAIL") + " " + detail;
        out(s);
        return s;
    }

    @Test
    public void sweep() throws Throwable
    {
        int n = Integer.getInteger("hsc.n", 20000);
        String[] cs = System.getProperty("hsc.cs", "0,1,4,16").split(",");
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob)");
        TableMetadata tm = currentTableMetadata();
        byte[] raw = new byte[4096];
        for (int b = 0; b < raw.length; b++) raw[b] = (byte) (b * 31 + 7);

        int origMiB = DatabaseDescriptor.getMaxHintsSizePerHostInMiB();
        out("START n=" + n + " cs=" + String.join(",", cs) + " batch=" + BATCH + " orig_MiB=" + origMiB
            + " max_hints_file_size=" + DatabaseDescriptor.getMaxHintsFileSize()
            + " flush_period_ms=" + DatabaseDescriptor.getHintsFlushPeriodInMS()
            + " msg_version=" + MessagingService.current_version
            + " hints_version=" + HintsDescriptor.CURRENT_VERSION
            + " hints_dir=" + DatabaseDescriptor.getHintsDirectory().absolutePath()
            + " hinted_handoff=" + DatabaseDescriptor.hintedHandoffEnabled()
            + " max_hint_window_ms=" + DatabaseDescriptor.getMaxHintWindow());
        HintsService.instance.pauseDispatch();

        long[] finals = new long[cs.length];
        int fails = 0;
        for (int j = 0; j < cs.length; j++)
        {
            int c = Integer.parseInt(cs[j].trim());
            long cap = (long) c << 20;
            InetAddressAndPort ep = InetAddressAndPort.getByName("192.168.1." + (10 + j));
            UUID id = UUID.randomUUID();
            Replica replica = full(ep);
            try
            {
                HintsService.instance.deleteAllHints();
                StorageService.instance.getTokenMetadata().updateHostId(id, ep);
                EndpointState state = new EndpointState(new HeartBeatState(0, 0));
                Gossiper.runInGossipStageBlocking(() -> Gossiper.instance.markDead(ep, state));
                DatabaseDescriptor.setMaxHintsSizePerHostInMiB(c);
                out("BEGIN C=" + c + " ep=" + ep + " id=" + id + " readback_MiB=" + DatabaseDescriptor.getMaxHintsSizePerHostInMiB()
                    + " readback_bytes=" + DatabaseDescriptor.getMaxHintsSizePerHost()
                    + " operand0=" + HintsService.instance.getTotalHintsSize(id) + " dir0=" + dirBytes(id));

                long admitted = 0, rejected = 0, hMin = Long.MAX_VALUE, hMax = 0;
                long firstRejIdx = -1, firstRejOperand = -1;
                long ts = FBUtilities.timestampMicros();
                boolean eqAll = true;
                int flushes = 0;
                for (int i = 0; i < n; i++)
                {
                    Mutation m = new RowUpdateBuilder(tm, ts + i, i).add("v", ByteBuffer.wrap(raw)).build();
                    long h = Hint.serializer.serializedSize(Hint.create(m, System.currentTimeMillis()), MessagingService.current_version)
                             + HintsBuffer.ENTRY_OVERHEAD_SIZE;
                    hMin = Math.min(hMin, h); hMax = Math.max(hMax, h);
                    if (StorageProxy.shouldHint(replica))
                    {
                        StorageProxy.submitHint(m, replica, null);
                        admitted++;
                    }
                    else
                    {
                        if (rejected == 0)
                        {
                            firstRejIdx = i;
                            firstRejOperand = HintsService.instance.getTotalHintsSize(id);
                        }
                        rejected++;
                    }
                    if ((i + 1) % BATCH == 0 || i == n - 1)
                    {
                        waitNoHintsInProgress();
                        HintsService.instance.flushAndFsyncBlockingly(List.of(id));
                        long op = HintsService.instance.getTotalHintsSize(id);
                        long db = dirBytes(id);
                        if (op != db) eqAll = false;
                        flushes++;
                        out("ROW C=" + c + " i=" + (i + 1) + " operand=" + op + " dirBytes=" + db + " admitted=" + admitted + " rejected=" + rejected);
                    }
                }
                long op = HintsService.instance.getTotalHintsSize(id);
                long db = dirBytes(id);
                finals[j] = op;
                out("END C=" + c + " cap_bytes=" + cap + " admitted=" + admitted + " rejected=" + rejected + " operand=" + op
                    + " dirBytes=" + db + " files=" + fileCount(id) + " h_min=" + hMin + " h_max=" + hMax
                    + " first_rej_idx=" + firstRejIdx + " first_rej_operand=" + firstRejOperand + " flushes=" + flushes
                    + " eq_all_rows=" + eqAll);
                long h = hMax;
                String t = "C=" + c;
                if (!rel(t + ":h_constant", hMin == hMax, "h_min=" + hMin + " h_max=" + hMax).contains("PASS")) fails++;
                if (!rel(t + ":operand_eq_dir_every_flush", eqAll, "").contains("PASS")) fails++;
                if (!rel(t + ":final_eq_header_plus_admitted_h", op == HEADER + admitted * h && db == op,
                         "operand=" + op + " dir=" + db + " 42+admitted*h=" + (HEADER + admitted * h)).contains("PASS")) fails++;
                if (!rel(t + ":counts_sum_n", admitted + rejected == n, "").contains("PASS")) fails++;
                if (c == 0)
                {
                    if (!rel(t + ":all_admitted", admitted == n && rejected == 0, "admitted=" + admitted).contains("PASS")) fails++;
                }
                else
                {
                    if (!rel(t + ":rejected_ge_1", rejected >= 1, "rejected=" + rejected).contains("PASS")) fails++;
                    if (!rel(t + ":first_rej_operand_gt_cap", firstRejOperand > cap, "first_rej_operand=" + firstRejOperand + " cap=" + cap).contains("PASS")) fails++;
                    if (!rel(t + ":final_gt_cap", op > cap, "operand=" + op).contains("PASS")) fails++;
                    if (!rel(t + ":final_le_cap_plus_256h", op <= cap + BATCH * h, "operand=" + op + " bound=" + (cap + BATCH * h)).contains("PASS")) fails++;
                }
            }
            finally
            {
                HintsService.instance.excise(id);
                StorageService.instance.getTokenMetadata().removeEndpoint(ep);
                DatabaseDescriptor.setMaxHintsSizePerHostInMiB(origMiB);
                out("CLEAN C=" + c + " dir_after_excise=" + dirBytes(id) + " restored_MiB=" + DatabaseDescriptor.getMaxHintsSizePerHostInMiB());
            }
        }
        // (d) ordering, only for the frozen value set
        if (String.join(",", cs).equals("0,1,4,16"))
        {
            boolean ord = finals[1] < finals[2] && finals[2] < finals[3] && finals[3] < finals[0];
            if (!rel("order:final1<final4<final16<final0", ord, "f0=" + finals[0] + " f1=" + finals[1] + " f4=" + finals[2] + " f16=" + finals[3]).contains("PASS")) fails++;
        }
        out("DONE relation_fails=" + fails);
    }
}
