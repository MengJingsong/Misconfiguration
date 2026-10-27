# repair_disk_headroom_reject_ratio — trace-back only  <!-- file: traceback-only/repair_disk_headroom_reject_ratio-setrepairdiskheadroomrejectratio-value--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:5347` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `repair_disk_headroom_reject_ratio` is a configuration entry, declared in Config.java:352 as `public volatile double repair_disk_headroom_reject_ratio = 0.0`. Its unit is a dimensionless ratio of disk that must stay unused, in the range 0.0 to 1.0. The check at DatabaseDescriptor.java:5347 is in `setRepairDiskHeadroomRejectRatio(double value)` (line 5345), which rejects values outside [0,1] with an IllegalArgumentException (line 5349) and otherwise stores the value in `conf` (line 5351). The default is a hard-coded 0.0, which disables the check; the comment says it is disabled by default on 5.0 for backward compatibility (Config.java:352; conf/cassandra.yaml:2326-2331). It is meant to cap disk use: repair is rejected when disk usage plus the ratio exceeds 1, i.e. less than that fraction of disk is free (ActiveRepairService.java:651-659, `verifyDiskHeadroomThreshold`, called from `prepareForRepair` at line 669). It can be set in cassandra.yaml as `repair_disk_headroom_reject_ratio` (commented out at conf/cassandra.yaml:2331 and conf/cassandra_latest.yaml:2289). It can also be changed at runtime over JMX through `setIncrementalRepairDiskHeadroomRejectRatio` (ActiveRepairServiceMBean.java:80, ActiveRepairService.java:1087-1089, which calls the DatabaseDescriptor setter), so a change does not need a restart. The yaml value is loaded directly into the field and is not validated by this setter. No -D system property was found for it.
