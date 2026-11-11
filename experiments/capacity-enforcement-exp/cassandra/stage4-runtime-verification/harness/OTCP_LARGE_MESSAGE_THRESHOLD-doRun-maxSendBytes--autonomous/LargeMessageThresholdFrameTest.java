/*
 * Stage-4 harness, case OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous, unit tier (B2).
 * Copied into test/unit/org/apache/cassandra/net/ of the run clone by unit-run.sh and removed after.
 *
 * B2c: fill one SMALL_MESSAGES outbound link to C while its peer's inbound socket is closed (phase 1), then open the
 * inbound socket and let EventLoopDelivery drain the backlog in frames of at most LARGE_MESSAGE_THRESHOLD (phase 2).
 * B2d: per-frame payload size (onSendSmallFrame), networking-pool usedSizeInBytes peak minus the baseline taken just
 * before inbound.open() (1 ms sampler plus one sample inside each onSendSmallFrame, amendment S4-A2), pendingPeak at
 * the end of phase 1, sent/errors after the drain. One RESULT line per method (B2e step 1), also appended to the file
 * named by -Dstage4.out if set.
 */
package org.apache.cassandra.net;

import java.io.FileWriter;
import java.io.IOException;
import java.util.Collections;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.LockSupport;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.commitlog.CommitLog;
import org.apache.cassandra.io.IVersionedSerializer;
import org.apache.cassandra.io.util.DataInputPlus;
import org.apache.cassandra.io.util.DataOutputPlus;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.utils.FBUtilities;
import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;

import static java.util.concurrent.TimeUnit.SECONDS;
import static org.apache.cassandra.config.CassandraRelevantProperties.OTCP_LARGE_MESSAGE_THRESHOLD;
import static org.apache.cassandra.net.ConnectionType.SMALL_MESSAGES;
import static org.apache.cassandra.net.MessagingService.current_version;

public class LargeMessageThresholdFrameTest
{
    private static final SocketFactory factory = new SocketFactory();
    private static final int PAYLOAD = 1000;          // B2c: 125 writeLong
    private static final int R = 65536;               // B2b: reserve, endpoint and global

    @BeforeClass
    public static void startup()
    {
        DatabaseDescriptor.daemonInitialization();
        CommitLog.instance.start();
    }

    @AfterClass
    public static void cleanup() throws InterruptedException
    {
        factory.shutdownNow();
    }

    @Test
    public void fillAndDrain_C4M() throws Throwable
    {
        fillAndDrain("C4M", 4 << 20);
    }

    @Test
    public void fillAndDrain_C1M() throws Throwable
    {
        fillAndDrain("C1M", 1 << 20);
    }

    @Test
    public void fillAndDrain_C4M_repeat() throws Throwable
    {
        fillAndDrain("C4M_repeat", 4 << 20);
    }

    static final class FrameStats implements OutboundDebugCallbacks
    {
        final BufferPool pool = BufferPools.forNetworking();
        final AtomicLong frames = new AtomicLong();
        final AtomicLong maxFrame = new AtomicLong();
        final AtomicLong poolPeak = new AtomicLong(Long.MIN_VALUE);
        final AtomicLong overflowPeak = new AtomicLong(Long.MIN_VALUE);
        final AtomicLong callbackSamples = new AtomicLong();
        final Map<Integer, Long> histogram = new TreeMap<>();   // payload size / 1024 -> frames

        void sample()
        {
            long used = pool.usedSizeInBytes();
            long overflow = pool.overflowMemoryInBytes();
            poolPeak.accumulateAndGet(used, Math::max);
            overflowPeak.accumulateAndGet(overflow, Math::max);
        }

        public void onSendSmallFrame(int messageCount, int payloadSizeInBytes)
        {
            // the frame's buffer is allocated and trimmed (finish()) but not yet written: sample the pool now (S4-A2)
            sample();
            callbackSamples.incrementAndGet();
            frames.incrementAndGet();
            maxFrame.accumulateAndGet(payloadSizeInBytes, Math::max);
            synchronized (histogram)
            {
                histogram.merge(payloadSizeInBytes / 1024, 1L, Long::sum);
            }
        }

        public void onSentSmallFrame(int messageCount, int payloadSizeInBytes) {}
        public void onFailedSmallFrame(int messageCount, int payloadSizeInBytes) {}
        public void onConnect(int messagingVersion, OutboundConnectionSettings settings) {}
    }

    private void fillAndDrain(String label, int C) throws Throwable
    {
        int property = OTCP_LARGE_MESSAGE_THRESHOLD.getInt();
        int lmt = OutboundConnections.LARGE_MESSAGE_THRESHOLD;
        Assert.assertEquals("LMT must be the property minus 21 (S4-A2)", property - 21, lmt);

        Object oldSerializer = Verb._TEST_1.unsafeSetSerializer(() -> new IVersionedSerializer<Object>()
        {
            public void serialize(Object o, DataOutputPlus out, int version) throws IOException
            {
                for (int i = 0; i < PAYLOAD / 8; i++)
                    out.writeLong(i);
            }

            public Object deserialize(DataInputPlus in, int version) throws IOException
            {
                in.skipBytesFully(PAYLOAD);
                return null;
            }

            public long serializedSize(Object o, int version)
            {
                return PAYLOAD;
            }
        });
        Object oldHandler = Verb._TEST_1.unsafeSetHandler(() -> msg -> {});
        Object oldExpiration = Verb._TEST_1.unsafeSetExpiration(u -> u.convert(120, SECONDS));

        InetAddressAndPort endpoint = FBUtilities.getBroadcastAddressAndPort();
        InboundConnectionSettings inboundSettings = new InboundConnectionSettings().withBindAddress(endpoint)
                                                                                   .withSocketFactory(factory);
        InboundSockets inbound = new InboundSockets(Collections.singletonList(inboundSettings));
        FrameStats stats = new FrameStats();
        OutboundConnectionSettings template = new OutboundConnectionSettings(endpoint)
                                              .withFraming(OutboundConnectionSettings.Framing.CRC)
                                              .withApplicationSendQueueCapacityInBytes(C)
                                              .withApplicationReserveSendQueueCapacityInBytes(R, new ResourceLimits.Concurrent(R))
                                              .withDebugCallbacks(stats)
                                              .withDefaultReserveLimits()
                                              .withSocketFactory(factory)
                                              .withDefaults(ConnectionCategory.MESSAGING);
        ResourceLimits.EndpointAndGlobal reserve =
            new ResourceLimits.EndpointAndGlobal(new ResourceLimits.Concurrent(template.applicationSendQueueReserveEndpointCapacityInBytes),
                                                 template.applicationSendQueueReserveGlobalCapacityInBytes);
        OutboundConnection outbound = new OutboundConnection(SMALL_MESSAGES, template, reserve);
        Thread sampler = null;
        try
        {
            Assert.assertEquals(C, (int) outbound.settings().applicationSendQueueCapacityInBytes);
            int S = Message.out(Verb._TEST_1, new Object()).serializedSize(current_version);

            // phase 1: fill with the inbound socket closed
            long nMax = 2L * C / S;
            long pendingPeak = 0;
            for (long i = 0; i < nMax; i++)
            {
                outbound.enqueue(Message.out(Verb._TEST_1, new Object()));
                pendingPeak = Math.max(pendingPeak, outbound.pendingBytes());
                if (outbound.overloadedCount() > 0)
                    break;
            }
            long accepted = outbound.submittedCount() - outbound.overloadedCount();
            long pendingEnd = outbound.pendingBytes();
            long pendingCountEnd = outbound.pendingCount();
            Thread.sleep(200);

            // phase 2: drain
            BufferPool pool = BufferPools.forNetworking();
            long baseline = pool.usedSizeInBytes();
            long baseOverflow = pool.overflowMemoryInBytes();
            stats.poolPeak.set(baseline);
            stats.overflowPeak.set(baseOverflow);
            final java.util.concurrent.atomic.AtomicBoolean stop = new java.util.concurrent.atomic.AtomicBoolean(false);
            final AtomicLong pollSamples = new AtomicLong();
            sampler = new Thread(() -> {
                while (!stop.get())
                {
                    stats.sample();
                    pollSamples.incrementAndGet();
                    LockSupport.parkNanos(1_000_000L);
                }
            }, "stage4-pool-sampler");
            sampler.setDaemon(true);
            sampler.start();
            long t0 = System.nanoTime();
            inbound.open().sync();
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(60);
            while ((outbound.pendingBytes() > 0 || outbound.sentCount() + outbound.errorCount() < accepted) && System.nanoTime() < deadline)
                Thread.sleep(5);
            long drainMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - t0);
            Thread.sleep(200);
            stop.set(true);
            sampler.join(5000);

            StringBuilder hist = new StringBuilder();
            synchronized (stats.histogram)
            {
                for (Map.Entry<Integer, Long> e : stats.histogram.entrySet())
                    hist.append(hist.length() == 0 ? "" : ",").append(e.getKey()).append("K:").append(e.getValue());
            }
            String line = String.format("RESULT label=%s V=%d lmt=%d C=%d R=%d S=%d accepted=%d overloaded=%d pendingPeak=%d pendingEnd=%d pendingCountEnd=%d " +
                                        "frames=%d maxFrame=%d poolBaseline=%d poolPeakDelta=%d overflowDelta=%d sent=%d sentBytes=%d errors=%d " +
                                        "pendingAfter=%d drainMs=%d pollSamples=%d callbackSamples=%d hist=%s",
                                        label, property, lmt, C, R, S, accepted, outbound.overloadedCount(), pendingPeak, pendingEnd, pendingCountEnd,
                                        stats.frames.get(), stats.maxFrame.get(), baseline, stats.poolPeak.get() - baseline,
                                        stats.overflowPeak.get() - baseOverflow, outbound.sentCount(), outbound.sentBytes(), outbound.errorCount(),
                                        outbound.pendingBytes(), drainMs, pollSamples.get(), stats.callbackSamples.get(), hist);
            System.out.println(line);
            String out = System.getProperty("stage4.out");
            if (out != null)
            {
                try (FileWriter w = new FileWriter(out, true))
                {
                    w.write(line + "\n");
                }
            }
        }
        finally
        {
            if (sampler != null)
                sampler.interrupt();
            outbound.close(false);
            inbound.close().get(30L, SECONDS);
            outbound.close(false).get(30L, SECONDS);
            Verb._TEST_1.unsafeSetSerializer((java.util.function.Supplier) oldSerializer);
            Verb._TEST_1.unsafeSetHandler((java.util.function.Supplier) oldHandler);
            Verb._TEST_1.unsafeSetExpiration((java.util.function.ToLongFunction) oldExpiration);
            MessagingService.instance().messageHandlers.clear();
        }
    }
}
