# sai_options.segment_write_buffer_size — trace-back only  <!-- file: traceback-only/sai_options.segment_write_buffer_size-validate-segment_write_buffer_size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java:41` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `sai_options.segment_write_buffer_size` is a configuration entry (field of the nested `StorageAttachedIndexOptions` object, `Config.sai_options` at `config/Config.java:804`), first declared at `config/StorageAttachedIndexOptions.java:36` as a `DataStorageSpec.IntMebibytesBound`; it caps the total memory used for writing SAI index segments, shared among all SAI indexes being built (`conf/cassandra.yaml:1791-1794`). The check in `validate()` (`StorageAttachedIndexOptions.java:40-46`, comparison at line 43; line 41 is just the opening brace) rejects values above the hard-coded constant `MAXIMUM_SEGMENT_BUFFER_MB = 32768` (line 29) with `INVALID_BUFFER_SIZE_ERROR` (lines 31-33), and `validate()` is invoked at startup from `DatabaseDescriptor.java:1022`. Unit: mebibytes (yaml accepts e.g. `1024MiB`). Default: the constant `DEFAULT_SEGMENT_BUFFER_MB = 1024` (line 26), i.e. 1024MiB, not derived from heap or system memory; the yaml entry is commented out (`cassandra.yaml:1790,1794`). It is set only via the yaml key `sai_options: segment_write_buffer_size:`; there is no -D property or JMX setter found (only a getter, `DatabaseDescriptor.java:5264-5267`), and it is read once into the static final `V1OnDiskFormat.SEGMENT_BUILD_MEMORY_LIMIT` (`index/sai/disk/v1/V1OnDiskFormat.java:126`), so a change requires a restart.
