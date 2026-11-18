| Arm | Direct (resolved) | V | First OOM | t_death from S (s) | U_peak | K_peak | heap_peak | active=32 L / S | applied MiB/s (S) | forced GCs | coord heapOOM, ms0640 si/so, MemAvail min | clients ok/err |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHAKE_auto | 15872 | alive (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | - | 1292 | 544 | 1953 | 28/72 / 28/59 | 92 | 0 | ? | ? |
| E_d896_r1 | 896 | DEAD (dOOM 6, hOOM 0, netty 0, oom_kill 0) | direct MutationStage-20 CommitLog.add | 52 | 890 | 544 | 1992 | 12/60 / 12/44 | 86 | 32 | 0, 0/0, 13931 | 111/1128 |
| G_512k_d896_r1 | 896 | alive (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | - | 610 | 544 | 1807 | 125/192 / 125/176 | 91 | 0 | 0, 0/0, 12484 | 29099/25180 |
| I_onheap_d896_r1 | 896 | DEAD (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | 157 | 211 | 544 | 2001 | 84/164 / 84/148 | 86 | 0 | 0, 0/0, 13924 | 99/4416 |
| E_d896_r2 | 896 | DEAD (dOOM 4, hOOM 0, netty 0, oom_kill 0) | direct MutationStage-11 CommitLog.add | 47 | 870 | 544 | 1993 | 9/58 / 9/42 | 85 | 19 | 0, 0/0, 14098 | 120/966 |
| G_512k_d896_r2 | 896 | alive (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | - | 594 | 544 | 1888 | 118/192 / 118/174 | 92 | 0 | 0, 0/0, 12514 | 28953/26201 |
| I_onheap_d896_r2 | 896 | alive (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | - | 196 | 544 | 1970 | 102/189 / 102/172 | 89 | 0 | 0, 0/0, 13945 | 96/4490 |
| E_d896_r3 | 896 | DEAD (dOOM 4, hOOM 0, netty 0, oom_kill 0) | direct MutationStage-14 CommitLog.add | 73 | 893 | 544 | 2001 | 24/81 / 24/65 | 79 | 74 | 0, 0/0, 13889 | 86/1782 |
| G_512k_d896_r3 | 896 | alive (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | - | 598 | 544 | 1898 | 119/192 / 119/177 | 91 | 0 | 0, 0/0, 12415 | 29063/25771 |
| I_onheap_d896_r3 | 896 | DEAD (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | 130 | 205 | 544 | 1984 | 66/137 / 66/121 | 92 | 0 | 0, 0/0, 13958 | 123/3447 |
| E_d896_r4 | 896 | DEAD (dOOM 8, hOOM 1, netty 0, oom_kill 0) | direct MutationStage-20 CommitLog.add | 53 | 892 | 544 | 1949 | 15/62 / 15/45 | 84 | 47 | 0, 0/0, 13972 | 94/1196 |
| E_d896_r5 | 896 | DEAD (dOOM 4, hOOM 0, netty 0, oom_kill 0) | direct MutationStage-25 CommitLog.add | 64 | 896 | 544 | 1966 | 15/71 / 15/55 | 76 | 49 | 0, 0/0, 13931 | 103/1447 |
| H_d1024_r1 | 1024 | DEAD (dOOM 14, hOOM 0, netty 0, oom_kill 0) | direct MutationStage-21 CommitLog.add | 51 | 1004 | 544 | 2000 | 10/61 / 10/45 | 76 | 17 | 0, 0/0, 14007 | 101/1058 |
| H_d1024_r2 | 1024 | DEAD (dOOM 4, hOOM 0, netty 0, oom_kill 0) | direct MutationStage-22 CommitLog.add | 115 | 1022 | 544 | 1969 | 56/122 / 56/106 | 76 | 154 | 0, 0/0, 13985 | 73/3135 |
| H_d1024_r3 | 1024 | alive (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | - | 1024 | 544 | 1877 | 85/185 / 85/169 | 78 | 238 | 0, 0/0, 14075 | 85/4512 |
| H_d1024_r4 | 1024 | alive (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | - | 1020 | 544 | 1910 | 106/186 / 106/169 | 80 | 205 | 0, 0/0, 13971 | 57/4556 |
| H_d1024_r5 | 1024 | alive (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | - | 1020 | 544 | 1988 | 97/187 / 97/171 | 80 | 181 | 0, 0/0, 14012 | 88/4473 |
| H_d1152_r1 | 1152 | alive (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | - | 1150 | 544 | 1969 | 107/189 / 107/173 | 85 | 96 | 0, 0/0, 14109 | 74/4545 |
| I_cw8_d896_r1 | 896 | alive (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | - | 819 | 544 | 1953 | 0/189 / 0/172 | 83 | 1 | 0, 0/0, 14080 | 161/4447 |
| I_cw8_d896_r2 | 896 | alive (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | - | 826 | 544 | 1937 | 0/189 / 0/172 | 83 | 1 | 0, 0/0, 13974 | 169/4458 |
| I_cw8_d896_r3 | 896 | alive (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | - | 829 | 544 | 1984 | 0/192 / 0/175 | 82 | 1 | 0, 0/0, 13826 | 151/4478 |
| E_d896_r6 | 896 | alive (dOOM 0, hOOM 0, netty 0, oom_kill 0) | - | - | 894 | 544 | 1992 | 80/184 / 80/167 | 81 | 269 | 0, 0/0, 14014 | 98/4456 |
| E_d896_r7 | 896 | DEAD (dOOM 12, hOOM 2, netty 0, oom_kill 0) | direct MutationStage-9 CommitLog.add | 51 | 876 | 528 | 1969 | 9/59 / 9/42 | 74 | 34 | 0, 0/0, 14055 | 103/1088 |
