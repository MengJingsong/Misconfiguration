# counter_cache_size — trace-back only  <!-- file: traceback-only/counter_cache_size-iscountercacheenabled-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `helper org.apache.cassandra.db.ColumnFamilyStore.isCounterCacheEnabled()` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `counter_cache_size` is a configuration entry (the check at `ColumnFamilyStore.java:3269` is `CacheService.instance.counterCache.getCapacity() > 0`, i.e. it enables the cache only when the capacity is nonzero) first declared at `Config.java:480` (`public DataStorageSpec.LongMebibytesBound counter_cache_size = null;`, replacing the deprecated `counter_cache_size_in_mb` at `Config.java:479`); it is documented in `conf/cassandra.yaml:595`. Its unit is MiB (`cassandra.yaml:594` "Min unit: MiB"), and it caps the heap memory used by the counter cache. The default is null/empty, which means "auto": `DatabaseDescriptor.java:834-836` computes `min(max(1, 2.5% of Runtime.totalMemory() in MiB), 50)`, so at most 50 MiB. An explicit value is taken via `toMebibytes()` (`DatabaseDescriptor.java:836`); a negative value throws a ConfigurationException (`DatabaseDescriptor.java:838-844`), and 0 disables the cache (`cassandra.yaml:593`). The resolved value is stored in `counterCacheSizeInMiB` and written back to `conf.counter_cache_size` (`DatabaseDescriptor.java:864`); it is exposed by `getCounterCacheSizeInMiB()` (`DatabaseDescriptor.java:3947-3950`). `CacheService.initCounterCache()` multiplies it by 1024*1024 to get the byte capacity of the Caffeine cache (`CacheService.java:176-179`, called from `CacheService.java:113`). It is set with the `counter_cache_size` key in cassandra.yaml, which needs a restart. It can also be changed at runtime through JMX `setCounterCacheCapacityInMB` (`CacheServiceMBean.java:58`, `CacheService.java:344-349`), which rejects negative values and does not persist across restarts.
