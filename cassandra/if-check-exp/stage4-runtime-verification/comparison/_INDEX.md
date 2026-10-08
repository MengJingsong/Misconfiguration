# Side-by-Side Comparisons — Index

One row per case that has both a long-path and a short-path solution and whose
runs are done. See the README's
[Two paths, two tiers each](../README.md#two-paths-two-tiers-each). Cases with
only a long-path file are not listed.

| Case stem | Long: unit / cluster | Short: unit / cluster | Conclusions agree? | File |
|---|---|---|---|---|
| memtable_heap_space-tryAllocate-limit | Confirmed / Confirmed | Confirmed / Confirmed | yes | [memtable_heap_space-tryAllocate-limit.md](memtable_heap_space-tryAllocate-limit.md) |
| max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction | Confirmed / Confirmed | Confirmed / Not confirmed | partly | [max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md](max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md) |

<!-- Verdicts are the row names each path's results file filed; "n/a" for a tier not run. Agree: yes | no | partly. -->
