/*
 * Stage-4 harness, cluster tier, positive control (9a Procedure 3, 9f R2) of
 * native_transport_max_concurrent_connections-channelActive-limit--guided. Written 2026-10-20 before any reading; the
 * connection set-up is NativeFlood's (native_transport_receive_queue_capacity harness).
 *
 * N protocol-v5 connections (SimpleClient, default overload mode: the server waits instead of refusing), each sending
 * ONE request: QUERY "SELECT pk FROM ks.t WHERE pk = 0 AND v = ? ALLOW FILTERING" at ONE with a --value-bytes blob
 * (default 1 MiB, above LARGE_MESSAGE_THRESHOLD, so the large-message path acquires the whole size at the first frame).
 * The node's "ncc hold request" Byteman rule holds each decoded request while the hold file exists. The client waits up
 * to --wait-s for all responses, then closes.
 *
 * Output: "conn <i> local=<address>", "sent n=<N> ms=", one "resp i=<conn> ok=<bool> ms= text=<error text>" per
 * response, "TOTAL ok= err= missing= ms=". Exit 0 when every connection got a response.
 *
 *   java <jvm11-clients.options> -cp <classes>:build/classes/main:build/lib/jars/'*':lib/'*' \
 *     org.apache.cassandra.transport.HeldRequests --host 127.0.0.1 --connections 64 --value-bytes 1048576 --wait-s 150
 */
package org.apache.cassandra.transport;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.transport.messages.ErrorMessage;
import org.apache.cassandra.transport.messages.QueryMessage;

public class HeldRequests
{
    public static void main(String[] args) throws Exception
    {
        Map<String, String> a = new HashMap<>();
        for (int i = 0; i + 1 < args.length; i += 2)
            a.put(args[i].replaceFirst("^--", ""), args[i + 1]);
        String host = a.getOrDefault("host", "127.0.0.1");
        int port = Integer.parseInt(a.getOrDefault("port", "9042"));
        int n = Integer.parseInt(a.getOrDefault("connections", "64"));
        int valueBytes = Integer.parseInt(a.getOrDefault("value-bytes", "1048576"));
        long waitMs = (long) (Double.parseDouble(a.getOrDefault("wait-s", "150")) * 1000);
        ByteBuffer value = ByteBuffer.allocate(valueBytes);

        DatabaseDescriptor.clientInitialization();
        List<SimpleClient> clients = new ArrayList<>();
        for (int i = 0; i < n; i++)
        {
            SimpleClient c = SimpleClient.builder(host, port).protocolVersion(ProtocolVersion.V5).build().connect(false, false);
            clients.add(c);
            System.out.println("conn " + i + " local=" + c.channel.localAddress());
        }
        for (SimpleClient c : clients)
        {
            QueryOptions options = QueryOptions.create(ConsistencyLevel.ONE, Collections.singletonList(value.duplicate()), false,
                                                       -1, null, null, ProtocolVersion.V5, null);
            Message.Request request = new QueryMessage("SELECT pk FROM ks.t WHERE pk = 0 AND v = ? ALLOW FILTERING", options);
            request.setSource(new Envelope(Envelope.Header.dummy(1, request.type), null));
            request.attach(c.connection);
            c.channel.writeAndFlush(Collections.singletonList(request));
        }
        System.out.println("sent n=" + n + " value_bytes=" + valueBytes + " ms=" + System.currentTimeMillis());
        System.out.flush();

        AtomicInteger ok = new AtomicInteger(), err = new AtomicInteger();
        boolean[] done = new boolean[n];
        long deadline = System.currentTimeMillis() + waitMs;
        int remaining = n;
        while (remaining > 0 && System.currentTimeMillis() < deadline)
        {
            for (int i = 0; i < n; i++)
            {
                if (done[i])
                    continue;
                Message.Response r = clients.get(i).responseHandler.responses.poll(0, TimeUnit.MILLISECONDS);
                if (r == null)
                    continue;
                done[i] = true;
                remaining--;
                boolean isErr = r instanceof ErrorMessage;
                (isErr ? err : ok).incrementAndGet();
                String text = isErr ? String.valueOf(((Throwable) ((ErrorMessage) r).error).getMessage()) : "";
                System.out.println("resp i=" + i + " ok=" + !isErr + " ms=" + System.currentTimeMillis() + " text=" + text);
                System.out.flush();
            }
            Thread.sleep(20);
        }
        System.out.println("TOTAL ok=" + ok.get() + " err=" + err.get() + " missing=" + remaining + " ms=" + System.currentTimeMillis());
        System.out.flush();
        for (SimpleClient c : clients)
            c.close();
        System.exit(remaining == 0 ? 0 : 3);
    }
}
