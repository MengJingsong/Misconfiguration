# internode_application_send_queue_reserve_endpoint_capacity — trace-back only  <!-- file: traceback-only/internode_application_send_queue_reserve_endpoint_capacity-applysimpleconfig-maxmessagesize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:984` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `internode_application_send_queue_reserve_endpoint_capacity` is a configuration entry, first declared at `src/java/org/apache/cassandra/config/Config.java:252` as a `DataStorageSpec.IntBytesBound` (old name `internode_application_send_queue_reserve_endpoint_capacity_in_bytes`, deprecated, via `@Replaces` at `Config.java:251`). It caps the bytes of outbound internode messages that may be queued per endpoint. The check is at `DatabaseDescriptor.java:984`, in `applySimpleConfig()` (declared at `DatabaseDescriptor.java:478`); it throws a ConfigurationException if `maxMessageSize` (`conf.internode_max_message_size.toBytes()`, `DatabaseDescriptor.java:976`) exceeds this capacity. `internode_max_message_size` is declared at `Config.java:239`. The unit is bytes, written in yaml with a size suffix. The default is a hard-coded `128MiB` (`Config.java:252`), shown commented out in `conf/cassandra.yaml:1387`, so it is not derived from heap or disk. It is set via the yaml key, and a change needs a restart because it is read once during config load; I found no JMX setter or -D override in the lines I read. When `internode_max_message_size` is unset, the else branch (`DatabaseDescriptor.java:992-996`) sets it to the smaller of the receive and send per-endpoint capacities.
