#!/usr/bin/env bash
# (Superseded before it ran: its one arm ran as the first arm of batch4.sh.)
# B8 batch 3 (2026-11-16, exploratory): restore emulation (DROP_SSTABLES=1) at 2 GiB defaults.
cd /mydata/b8
while pgrep -f 'harness/batch[12].sh' >/dev/null; do sleep 10; done
export REPLAY_TIMEOUT=900 DROP_SSTABLES=1
HISTO_AFTER="25" KEEP_DUMP=1 harness/arm3.sh x-p64-2g-drop-r1 2048 map 5900 150 64
