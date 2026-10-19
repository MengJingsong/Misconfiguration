| JVM | mode | A MiB | S MiB | k | idle L | accepted | L at first rejection | N (message) | N − L×S | after 10 more: L | non-CDC | release (ms, rejected first) | checks (pass / mismatch) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| u16 | blocking | 16 | 32 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | accepted | skipped | 10 / 0 |
| u48 | blocking | 48 | 32 | 1 | 2 | 62 | 2 | 67108864 | 0 | 2 | accepted | 115, 1 | 9 / 2 |
| u80 | blocking | 80 | 32 | 2 | 2 | 62 | 2 | 67108864 | 0 | 2 | accepted | 116, 1 | 11 / 0 |
| u128 | blocking | 128 | 32 | 4 | 2 | 124 | 4 | 134217771 | 43 | 4 | accepted | 119, 1 | 11 / 0 |
| u144 | blocking | 144 | 32 | 4 | 2 | 155 | 5 | 167772239 | 79 | 5 | accepted | 119, 1 | 10 / 1 |
| u272 | blocking | 272 | 32 | 8 | 2 | 279 | 9 | 301990021 | 133 | 9 | accepted | 145, 1 | 10 / 1 |
| u280-s16 | blocking | 280 | 16 | 17 | 2 | 255 | 17 | 285212949 | 277 | 17 | accepted | 147, 1 | 11 / 0 |

| JVM | trace: creations | verdict formula violations | stale creations (unambiguous) | links made beyond k | …of which not explained by a stale counter | peak L (per-tick) |
|---|---|---|---|---|---|---|
| u16 | 5 | 0 | 0 / 5 | 0 | 0 | 0 |
| u48 | 6 | 0 | 1 / 4 | 1 | 0 | 2 |
| u80 | 6 | 0 | 1 / 4 | 0 | 0 | 2 |
| u128 | 8 | 0 | 3 / 6 | 0 | 0 | 4 |
| u144 | 9 | 0 | 4 / 7 | 1 | 0 | 5 |
| u272 | 13 | 0 | 6 / 11 | 1 | 0 | 9 |
| u280-s16 | 21 | 0 | 10 / 19 | 0 | 0 | 17 |
| u80-nb | 14 | 0 | 8 / 11 | None | 0 | 3 |
| u144-nb | 16 | 0 | 7 / 10 | None | 0 | 5 |

| JVM (non-blocking) | rows | distinct links made | max L | final L | links deleted | bytes written | bytes retained | checks (pass / mismatch) |
|---|---|---|---|---|---|---|---|---|
| u80-nb | 311 | 12 | 3 | 3 | 9 | 326107136 | 100663296 | 6 / 0 |
| u144-nb | 374 | 14 | 5 | 5 | 9 | 392167424 | 167772160 | 6 / 0 |

mismatches in u48: [idle floor is min(k, 2) = 1 links, got 2, links at the first rejection: L = 2, expected k = 1]
mismatches in u144: [links at the first rejection: L = 5, expected k = 4]
mismatches in u272: [links at the first rejection: L = 9, expected k = 8]
junit: u16 tests=1 failures=0 errors=0; u48 tests=1 failures=1 errors=0; u80 tests=1 failures=0 errors=0; u128 tests=1 failures=0 errors=0; u144 tests=1 failures=1 errors=0; u272 tests=1 failures=1 errors=0; u280-s16 tests=1 failures=0 errors=0; u80-nb tests=1 failures=0 errors=0; u144-nb tests=1 failures=0 errors=0
