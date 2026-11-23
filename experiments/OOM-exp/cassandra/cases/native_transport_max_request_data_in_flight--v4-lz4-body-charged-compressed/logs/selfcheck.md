| arm | heap | outcome (HotSpot banner) | JVM gone after FLOOD_START (s) | K max (MiB) | K at last live sample (MiB) | paused max | heap used max (MiB) | client sent / ROWS / errors | 32 MiB byte[] in dump or histogram | oom_kill |
|---|---|---|---|---|---|---|---|---|---|---|
| T_r1 | 2048M | OOM: Java heap space → kill -9 | 3.6 | 4.02 | 4.02 | 0 | 2024 | 199 / 0 / {} | dump 36 (1152.0 MiB) | 0 |
| C1_r1 | 2048M | alive (no banner) | — | 59.76 | 24.61 | 4 | 1568 | 3494 / 0 / {0x1002c=1607, 0x20070=1315} | histo-end [B total 188 MiB | 0 |
| I1_r1 | 2048M | alive (no banner) | — | 992.00 | 896.00 | 4 | 1974 | 297 / 149 / {} | histo-end [B total 219 MiB | 0 |
| T_r2 | 2048M | OOM: Java heap space → kill -9 | 4.1 | 4.02 | 4.02 | 0 | 1950 | 191 / 0 / {} | dump 36 (1152.0 MiB) | 0 |
| C1_r2 | 2048M | alive (no banner) | — | 51.60 | 15.44 | 4 | 1527 | 3473 / 0 / {0x1300=480, 0x1200=2426} | histo-end [B total 187 MiB | 0 |
| I1_r2 | 2048M | OOM: Java heap space → kill -9 | — | 1088.00 | 1088.00 | 4 | 2018 | 294 / 146 / {0x1200=1} | dump 37 (1184.0 MiB) | 0 |
| T_r3 | 2048M | OOM: Java heap space → kill -9 | 9.4 | 4.27 | 4.27 | 0 | 1951 | 181 / 0 / {} | dump 36 (1152.0 MiB) | 0 |
| C1_r3 | 2048M | alive (no banner) | — | 58.12 | 22.97 | 4 | 1554 | 3496 / 0 / {0x1300=536, 0x1200=2380} | histo-end [B total 186 MiB | 0 |
| I1_r3 | 2048M | OOM: Java heap space → kill -9 | 99.9 | 928.00 | -0.00 | 4 | 1984 | 304 / 143 / {} | dump 37 (1184.0 MiB) | 0 |
| T2_r1 | 2048M | OOM: Java heap space → kill -9 | 0.3 | 0.00 | 0.00 | 0 | 0 | results={IOEXC Connection reset=1} | dump 0 (0.0 MiB) | 0 |
| C2_r1 | 2048M | alive (no banner) | — | 0.00 | 0.00 | 0 | 2000 | results={IOEXC Connection reset=50} | histo-end [B total 202 MiB | 0 |
| I2_r1 | 2048M | alive (no banner) | — | 0.00 | 0.00 | 0 | 1019 | results={IOEXC Connection reset=1} | histo-end [B total 58 MiB | 0 |
| T2_r2 | 2048M | OOM: Java heap space → kill -9 | 0.4 | 0.00 | 0.00 | 0 | 0 | results={IOEXC Connection reset=1} | dump 0 (0.0 MiB) | 0 |
| C2_r2 | 2048M | alive (no banner) | — | 0.00 | 0.00 | 0 | 1844 | results={IOEXC Connection reset=50} | histo-end [B total 202 MiB | 0 |
| I2_r2 | 2048M | alive (no banner) | — | 0.00 | 0.00 | 0 | 1000 | results={IOEXC Connection reset=1} | histo-end [B total 58 MiB | 0 |
| T2_r3 | 2048M | OOM: Java heap space → kill -9 | 0.4 | 0.00 | 0.00 | 0 | 0 | results={IOEXC Connection reset=1} | dump 0 (0.0 MiB) | 0 |
| C2_r3 | 2048M | alive (no banner) | — | 0.00 | 0.00 | 0 | 1972 | results={IOEXC Connection reset=50} | histo-end [B total 202 MiB | 0 |
| I2_r3 | 2048M | alive (no banner) | — | 0.00 | 0.00 | 0 | 1016 | results={IOEXC Connection reset=1} | histo-end [B total 58 MiB | 0 |
| T_4G | 4096M | alive (no banner) | — | 8.16 | 3.77 | 0 | 4032 | 704 / 0 / {0x1300=365, 0x1200=137} | histo-end [B total 2180 MiB | 0 |
| P0 | 2048M | OOM: Java heap space → kill -9 | 3.6 | 3.64 | 3.64 | 0 | 1983 | 189 / 0 / {} |  | 0 |
| S_vm | 15872M | OOM: Requested array size exceeds VM limit → kill -9 | 0.3 | 0.00 | 0.00 | 0 | 0 | results={IOEXC Connection reset=1} |  | 0 |
