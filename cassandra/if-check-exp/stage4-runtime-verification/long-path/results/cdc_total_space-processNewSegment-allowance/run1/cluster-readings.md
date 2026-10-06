| value | A MiB (read back) | S MiB | k | idle L | L at first rejection | plateau L (median last 20 s of B) | B peak / min L | link bytes at plateau (apparent / allocated) | N in the WARN lines | WARN entries / logged rejected writes / traced `reject n` | `Failures` at B end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| b144 | 144 | 32 | 4 | 2 | 5 | 5.0 | 5 / 5 | 160 MiB / 155 MiB | 167772178..167772250 (2 distinct) | 9 / 6305 / 6301 | 6304 |
| b272 | 272 | 32 | 8 | 2 | 9 | 9.0 | 9 / 9 | 288 MiB / 279 MiB | 301989960..301990050 (2 distinct) | 8 / 6057 / 6001 | 6056 |
| b528 | 528 | 32 | 16 | 2 | 16 | 16.0 | 16 / 16 | 512 MiB / 496 MiB | 536871092..536871200 (2 distinct) | 8 / 6079 / 6001 | 6078 |
| bdef | 4096 (default) | 32 | 128 (exact multiple) | 2 | 127 | 127.0 | 127 / 127 | 4064 MiB / 3942 MiB | 4261413584..4261415150 (2 distinct) | 8 / 6132 / 6101 | 6131 |
| s16 | 280 | 16 | 17 | 2 | 17 | 17.0 | 17 / 17 | 272 MiB / 255 MiB | 285212816..285212978 (2 distinct) | 8 / 6091 / 6001 | 6090 |

| value | peak L over the run | ticks with bytes ≠ L×S | max sampler gap (ms) | segments created / forbidden | verdict formula violations | stale creations / unambiguous | links made beyond k | …not explained by a stale counter |
|---|---|---|---|---|---|---|---|---|
| b144 | 5 | 0 | 51 | 9 / 3 | 0 | 5 / 9 | 1 | 0 |
| b272 | 9 | 0 | 50 | 13 / 3 | 0 | 8 / 13 | 1 | 0 |
| b528 | 16 | 0 | 50 | 20 / 3 | 0 | 9 / 20 | 0 | 0 |
| bdef | 127 | 0 | 50 | 131 / 3 | 0 | 16 / 131 | 0 | 0 |
| s16 | 17 | 0 | 50 | 22 / 4 | 0 | 6 / 22 | 0 | 0 |
| n144 | 5 | 0 | 51 | 116 / 0 | 0 | 75 / 98 | None | 0 |
| n528 | 17 | 0 | 51 | 124 / 0 | 0 | 86 / 97 | None | 0 |
| c272 | 8 | 0 | 59 | 100 / 0 | 0 | 5 / 71 | 0 | 0 |

| value | non-CDC control B: errors / rows | CDC stress B: errors / rows attempted | release: consumer deleted | release: attempts, ms to the accepted write | L after release |
|---|---|---|---|---|---|
| b144 | 0 / 602 | 6015 / 6015 | 5 | 2, 1618 (accepted) | 1 |
| b272 | 0 / 602 | 6015 / 6015 | 9 | 2, 1627 (accepted) | 1 |
| b528 | 0 / 602 | 6015 / 6015 | 16 | 2, 1657 (accepted) | 1 |
| bdef | 0 / 602 | 6015 / 6015 | 127 | 2, 2773 (accepted) | 1 |
| s16 | 0 / 602 | 6015 / 6015 | 17 | 2, 1685 (accepted) | 1 |

| value | settle: probes | wait (ms) | slowest probe (ms) | final streak of prompt probes |
|---|---|---|---|---|
| b144 | 1 | 707 | 707 | (single probe) |
| b272 | 1 | 697 | 697 | (single probe) |
| b528 | 1 | 713 | 713 | (single probe) |
| bdef | 21 | 36796 | 2753 | 15 |
| s16 | 1 | 687 | 687 | (single probe) |
| n144 | 1 | 686 | 686 | (single probe) |
| n528 | 1 | 670 | 670 | (single probe) |

| non-blocking value | A MiB | k | peak L (per-tick, whole run) | B min L | segments created | links removed | removed in ascending order | deleteOld calls | WARN entries | CDC stress B errors / rows | L at B's end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| n144 | 144 | 4 | 5 | 3 | 116 | 111 | True | 105 | 0 | 0 / 3015 | 3 |
| n528 | 528 | 16 | 17 | 16 | 124 | 106 | True | 100 | 0 | 0 / 3014 | 16 |

consumer control c272: WARN entries 0, logged rejected writes 0, peak L 8 (k = 8), C window peak/min 8/2, links deleted by the consumer loop 97, CDC stress errors / rows 0 / 3015, segments created 100
