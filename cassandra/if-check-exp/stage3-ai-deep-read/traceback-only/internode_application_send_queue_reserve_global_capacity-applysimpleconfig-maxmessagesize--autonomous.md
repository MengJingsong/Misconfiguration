# internode_application_send_queue_reserve_global_capacity — trace-back only  <!-- file: traceback-only/internode_application_send_queue_reserve_global_capacity-applysimpleconfig-maxmessagesize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:987` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `internode_application_send_queue_reserve_global_capacity` is a configuration entry (the check at DatabaseDescriptor.java:987 sits in `applySimpleConfig()`, declared at :478, and compares `maxMessageSize`, the value of `conf.internode_max_message_size.toBytes()` read at :976, against it). It is first declared in `Config.java:254` as a `DataStorageSpec.IntBytesBound`, with the deprecated old name `internode_application_send_queue_reserve_global_capacity_in_bytes` mapped at `Config.java:253`. Its unit is bytes, written with a size suffix such as MiB, and its minimum unit is B (`conf/cassandra.yaml:1384-1388`). The default is a hard-coded `"512MiB"` at `Config.java:254`, and it is commented out in `conf/cassandra.yaml:1388`. It caps the total bytes of messages queued for sending to all peers, not just one endpoint. The cap is enforced at runtime as a `ResourceLimits.Concurrent` built from `DatabaseDescriptor.getInternodeApplicationSendQueueReserveGlobalCapacityInBytes()` (`DatabaseDescriptor.java:3035-3037`, used at `MessagingService.java:321`). It can be set through the yaml key above, or through the old `_in_bytes` yaml name, and a change needs a restart. I found no JMX setter or -D property for it. The line at :987 only rejects startup (`ConfigurationException`, :988) when `internode_max_message_size`, which is either set explicitly or defaulted at :996 to the smaller of the two per-endpoint capacities, exceeds this global send-queue reserve.
