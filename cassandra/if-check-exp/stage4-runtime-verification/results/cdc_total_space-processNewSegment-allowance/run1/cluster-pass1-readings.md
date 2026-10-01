| value | A MiB (read back) | S MiB | k | idle L | L at first rejection | plateau L (median last 20 s of B) | B peak / min L | link bytes at plateau (apparent / allocated) | N in the WARN lines | WARN entries / logged rejected writes / traced `reject n` | `Failures` at B end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| b144 | 144 | 32 | 4 | 2 | 5 | 5.0 | 5 / 5 | 160 MiB / 155 MiB | 167772178..167772250 (3 distinct) | 9 / 6113 / 6101 | 6112 |
| b272 | 272 | 32 | 8 | 2 | 9 | 9.0 | 9 / 9 | 288 MiB / 279 MiB | 301989942..301990050 (3 distinct) | 9 / 6326 / 6301 | 6325 |
| b528 | 528 | 32 | 16 | 2 | 16 | 16 | 16 / 16 | 512 MiB / 496 MiB | 536871074..536871200 (3 distinct) | 9 / 6470 / 6401 | 6469 |
| bdef | 4096 (default) | 32 | 128 (exact multiple) | 2 | 127 | 127.0 | 127 / 127 | 4064 MiB / 3942 MiB | 4261413584..4261415150 (20 distinct) | 26 / 6343 / 6301 | 6342 |
| s16 | 280 | 16 | 17 | 2 | 17 | 17.0 | 17 / 17 | 272 MiB / 255 MiB | 285212708..285212978 (3 distinct) | 10 / 6394 / 6301 | 6393 |

| value | peak L over the run | ticks with bytes ≠ L×S | max sampler gap (ms) | segments created / forbidden | verdict formula violations | stale creations / unambiguous | links made beyond k | …not explained by a stale counter |
|---|---|---|---|---|---|---|---|---|
| b144 | 5 | 0 | 50 | 9 / 3 | 0 | 5 / 9 | 1 | 0 |
| b272 | 9 | 0 | 50 | 13 / 3 | 0 | 9 / 13 | 1 | 0 |
| b528 | 16 | 0 | 50 | 20 / 3 | 0 | 8 / 20 | 0 | 0 |
| bdef | 127 | 0 | 51 | 130 / 2 | 0 | 8 / 130 | 0 | 0 |
| s16 | 17 | 0 | 51 | 22 / 4 | 0 | 9 / 22 | 0 | 0 |
| n144 | 5 | 0 | 184 | 112 / 0 | 0 | 82 / 103 | None | 0 |
| n528 | 17 | 0 | 50 | 128 / 0 | 0 | 74 / 100 | None | 0 |
| c272 | 8 | 0 | 51 | 100 / 1 | 0 | 5 / 69 | 0 | 0 |

| value | non-CDC control B: errors / rows | CDC stress B: errors / rows attempted | release: consumer deleted | release: attempts, ms to the accepted write | L after release |
|---|---|---|---|---|---|
| b144 | 0 / 602 | 6015 / 6015 | 5 | 2, 1625 (accepted) | 1 |
| b272 | 0 / 602 | 6015 / 6015 | 9 | 2, 1613 (accepted) | 1 |
| b528 | 0 / 602 | 6015 / 6015 | 16 | 2, 1690 (accepted) | 1 |
| bdef | None / None | 6015 / 6015 | 127 | 2, 2861 (accepted) | 1 |
| s16 | 0 / 602 | 6015 / 6015 | 17 | 2, 1691 (accepted) | 1 |

| non-blocking value | A MiB | k | peak L (per-tick, whole run) | B min L | segments created | links removed | removed in ascending order | deleteOld calls | WARN entries | CDC stress B errors / rows | retained at the end (links × S) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| n144 | 144 | 4 | 5 | 4 | 112 | 107 | True | 102 | 0 | 0 / 3015 | 4 |
| n528 | 528 | 16 | 17 | 16 | 128 | 110 | True | 96 | 0 | 0 / 3015 | 16 |

consumer control c272: WARN entries 0, logged rejected writes 0, peak L 8 (k = 8), C window peak/min 8/2, links deleted by the consumer loop 97, CDC stress errors / rows 0 / 3016, segments created 100
