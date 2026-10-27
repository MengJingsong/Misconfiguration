# counter_cache_size — trace-back only  <!-- file: traceback-only/counter_cache_size-getcachedcounter-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/ColumnFamilyStore.java:2501` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `counter_cache_size` is a configuration entry, declared in `src/java/org/apache/cassandra/config/Config.java:480` as `DataStorageSpec.LongMebibytesBound counter_cache_size = null` (it replaces the old `counter_cache_size_in_mb`, `Config.java:479`). The check at `ColumnFamilyStore.java:2501` sits in `getCachedCounter` and tests `CacheService.instance.counterCache.getCapacity() == 0L`, which means "counter cache disabled". The cache capacity is set in `CacheService.initCounterCache` (`CacheService.java:172-178`) as `DatabaseDescriptor.getCounterCacheSizeInMiB() * 1024 * 1024` bytes, passed to `CaffeineCache.create(capacity)`. It is a cap on the on-heap size of the counter cache. The unit is MiB (the yaml notes "Min unit: MiB", `conf/cassandra.yaml:594`). The default is empty, which means "auto". `DatabaseDescriptor.java:834-836` computes that as min(max(1, 2.5% of `Runtime.getRuntime().totalMemory()` in MiB), 50) MiB, and `DatabaseDescriptor.java:864` writes the result back into `conf.counter_cache_size`. A negative value is rejected (`DatabaseDescriptor.java:838-844`), and 0 disables the cache (`conf/cassandra.yaml:594`). It is set with the `counter_cache_size:` key in cassandra.yaml (`conf/cassandra.yaml:595`), and a change in the yaml needs a restart. It can also be changed at runtime, without a restart, through JMX `CacheService.setCounterCacheCapacityInMB` (`CacheService.java:344-350`, `CacheServiceMBean.java:58`), which nodetool reaches via `NodeProbe.java:1093`. That runtime change is not persisted to the yaml.
