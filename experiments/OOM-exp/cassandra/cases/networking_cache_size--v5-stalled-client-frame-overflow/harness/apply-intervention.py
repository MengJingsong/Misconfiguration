#!/usr/bin/env python3
# Apply the B13 diagnostic intervention (case §2.8) to <tree>/src/java/org/apache/cassandra/transport/Dispatcher.java.
import sys
p = sys.argv[1] + '/src/java/org/apache/cassandra/transport/Dispatcher.java'
s = open(p).read()
old = """        @Override
        public void run()
        {
            startTimeNanos = MonotonicClock.Global.preciseTime.now();"""
new = """        @Override
        public void run()
        {
            // B13 diagnostic intervention (not upstream): defer a request whose channel is above its
            // outbound high water mark, so no response is built for a client that is not reading.
            if (channel.isActive() && !channel.isWritable())
            {
                org.apache.cassandra.concurrent.ScheduledExecutors.scheduledFastTasks
                    .schedule(() -> requestExecutor.submit(this), 100, TimeUnit.MILLISECONDS);
                return;
            }
            startTimeNanos = MonotonicClock.Global.preciseTime.now();"""
assert s.count(old) == 1, 'anchor not found once'
open(p, 'w').write(s.replace(old, new))
print('patched', p)
