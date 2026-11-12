/*
 * Stage-4 harness, unit tier (B2) of streaming_state_size-streammanager-states--autonomous.
 * The test of the case file's B2a, with N = 5000 (amendment S4-A2) and the insert-time weight printed first (S4-A1).
 */
package org.apache.cassandra.streaming;

import java.util.*;
import org.junit.*;
import org.apache.cassandra.config.*;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.utils.*;
import static org.apache.cassandra.utils.TimeUUID.Generator.nextTimeUUID;

public class StreamingStateCapTest
{
    static final int N = 5000;
    static final String[] SIZES = { "16KiB", "256KiB", "1MiB", "40MiB" };

    @BeforeClass public static void init() { DatabaseDescriptor.daemonInitialization(); }

    static StreamingState newState(StreamManager m, boolean addPeer) throws Exception
    {
        StreamResultFuture f = new StreamResultFuture(nextTimeUUID(), StreamOperation.REBUILD, null, null); // follower: not completed in ctor
        StreamingState s = new StreamingState(f);
        m.putStreamingState(s);                       // weighed here, peers empty
        s.phase.start();
        if (addPeer)                                  // what a real plan does after registration
            s.handleStreamEvent(new StreamEvent.SessionPreparedEvent(s.id(),
                new SessionInfo(InetAddressAndPort.getByName("127.0.0.2:7000"), 0, InetAddressAndPort.getByName("127.0.0.1:7000"),
                                Collections.emptyList(), Collections.emptyList(), StreamSession.State.PREPARING, null),
                StreamSession.PrepareDirection.ACK));
        s.onSuccess(null);
        return s;
    }

    @Test public void cap() throws Exception
    {
        System.out.println("O53 EMPTY=" + StreamingState.EMPTY + " TIMEUUID_SIZE=" + TimeUUID.TIMEUUID_SIZE
                           + " w=" + (StreamingState.EMPTY + TimeUUID.TIMEUUID_SIZE) + " N=" + N);
        for (boolean peer : new boolean[]{ false, true })
            for (String size : SIZES)
            {
                DatabaseDescriptor.setStreamingStateSize(new DataStorageSpec.LongBytesBound(size));
                StreamManager m = new StreamManager();          // reads the knob in its constructor
                long cap = DatabaseDescriptor.getStreamingStateSize().toBytes();
                for (int i = 1; i <= N; i++)
                {
                    newState(m, peer);
                    if (i % 250 == 0)
                    {
                        Collection<StreamingState> live = new ArrayList<>(m.getStreamingStates());
                        long weight = 0;
                        for (StreamingState s : live) weight += s.unsharedHeapSize() + TimeUUID.TIMEUUID_SIZE; // weight as of now
                        long deep = ObjectSizes.measureDeep(live) - ObjectSizes.measureDeep(new ArrayList<>(live.size()));
                        System.out.println(String.format("O53 peer=%s size=%s cap=%d inserted=%d retained=%d weightNow=%d deep=%d",
                                          peer, size, cap, i, live.size(), weight, deep)); // one write per line (S4 harness)
                    }
                }
            }
    }
}
