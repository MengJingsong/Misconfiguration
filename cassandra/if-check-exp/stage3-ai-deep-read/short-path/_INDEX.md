# Short-Path Solutions — Index

One row per filed solution. See [`README.md`](README.md) for how a solution is
produced, isolated, audited and frozen. A filed solution is never amended.

| Stem | Entry pointer | Feed | Filed | sha256 | Model | Isolation | Leakage audit | Comparison | Status |
|---|---|---|---|---|---|---|---|---|---|
| memtable_heap_space-tryAllocate-limit--v1 | `src/java/org/apache/cassandra/utils/memory/MemtablePool.java:156` | 3b | 2026-10-05 | `7f1a813e5c68ccee42ac4640e9e8e43ea1df9c5cfd45b6892c42bcfe27a61a38` | claude-sonnet-5 | restricted+web (allowlist v1), canary pass, claude 2.1.272 (Claude Code), 2026-10-05 | pass (reviewed) | pending | superseded 2026-10-05 by `memtable_heap_space-tryAllocate-limit.md` |
| memtable_heap_space-tryAllocate-limit | `src/java/org/apache/cassandra/utils/memory/MemtablePool.java:156` | 3b | 2026-10-05 | `31f017feea820dd6d9df3db04ef0d5aa50a81c1733819850d1fd027795e46126` | claude-sonnet-5 | restricted+web (allowlist v1), canary pass, claude 2.1.272 (Claude Code), 2026-10-05 | pass | [comparison](../../stage4-runtime-verification/comparison/memtable_heap_space-tryAllocate-limit.md) | current |
| max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction | `src/java/org/apache/cassandra/db/Directories.java:551` | 3a | 2026-10-08 | `e8b505e1802722d76642c664e71a55ee2cbb23536bb88e1852edecce143ae7b1` | claude-sonnet-5 | restricted+web (allowlist v1), canary pass, claude 2.1.294 (Claude Code), 2026-10-08 | pass (reviewed) | [comparison](../../stage4-runtime-verification/comparison/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md) | current |

<!-- One row per solution. Isolation: the index cell printed by isolation-test.py, e.g. restricted+web (allowlist v1), plus any variant (README, Limits of the standard run). Audit: pass | fail (discarded). Comparison: pending | link. Status: current | superseded (a superseded solution is renamed `<stem>--vN.md`, never edited). -->
