# row_cache_size — trace-back only  <!-- file: traceback-only/row_cache_size-isrowcacheenabled-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `helper org.apache.cassandra.db.ColumnFamilyStore.isRowCacheEnabled()` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `row_cache_size` is a configuration entry (an off-heap/in-memory cap on the row cache). It is first declared at `src/java/org/apache/cassandra/config/Config.java:474` (`DataStorageSpec.LongMebibytesBound row_cache_size = new DataStorageSpec.LongMebibytesBound("0MiB")`, replacing the legacy `row_cache_size_in_mb` at `Config.java:473`). The check is `ColumnFamilyStore.isRowCacheEnabled()` at `ColumnFamilyStore.java:3262`, which tests `CacheService.instance.rowCache.getCapacity() > 0`. That capacity is seeded from the setting via `DatabaseDescriptor.getRowCacheSizeInMiB()` (`DatabaseDescriptor.java:3918`, `conf.row_cache_size.toMebibytes()`) times 1024*1024 in `OHCProvider.java:40` and `SerializingCacheProvider.java:33`. `CacheService.initRowCache()` (`CacheService.java:146-147`) falls back to `NopCacheProvider` when the size is 0. The unit is MiB (bytes after the conversion above). The default is a hard-coded 0MiB, set at `Config.java:474` and repeated in `conf/cassandra.yaml:564`, so row caching is disabled by default (`cassandra.yaml:562`). It is set with the yaml key `row_cache_size` (min unit MiB, `cassandra.yaml:563`) and read at startup, so a yaml change needs a restart. It can also be changed at runtime through the JMX `CacheServiceMBean.setRowCacheCapacityInMB` (`CacheService.java:327-332`, `CacheServiceMBean.java:54`, which `NodeProbe.java:1092` calls). That call rejects negative values and does not persist to yaml. A test-only setter exists at `DatabaseDescriptor.java:3922-3925`. The second operand, `metadata().params.caching.cacheRows()` (`ColumnFamilyStore.java:3262`), is a per-table schema option and not a memory limit.
