# internode_application_receive_queue_reserve_global_capacity — trace-back only  <!-- file: traceback-only/internode_application_receive_queue_reserve_global_capacity-applysimpleconfig-maxmessagesize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:981` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `internode_application_receive_queue_reserve_global_capacity` is a configuration entry (memory cap on the bytes of inbound internode application messages held in receive queues, across all links to or from any node) that is checked at `DatabaseDescriptor.java:981` in `applySimpleConfig()` (declared at `DatabaseDescriptor.java:478`), where `maxMessageSize` (= `conf.internode_max_message_size.toBytes()`, `DatabaseDescriptor.java:976`) must not exceed it or a `ConfigurationException` is thrown (`DatabaseDescriptor.java:981-982`). It is first declared at `Config.java:261` as `DataStorageSpec.IntBytesBound` (unit: bytes, minimum unit B per `conf/cassandra.yaml:1384`; it replaces the deprecated `internode_application_receive_queue_reserve_global_capacity_in_bytes`, `Config.java:260`). Its default is a hard-coded `"512MiB"` (`Config.java:261`, also shown commented-out at `conf/cassandra.yaml:1391`), not derived from heap or system resources. It is set through the yaml key of the same name (or the old `_in_bytes` name); `DatabaseDescriptor.java:3050-3052` only exposes a getter and I found no setter or JMX method for it, so a change requires a node restart. The compared operand `internode_max_message_size` is declared at `Config.java:239` with no default (null); when null, `DatabaseDescriptor.java:991-996` derives it from the minimum of the receive/send endpoint-capacity settings.
