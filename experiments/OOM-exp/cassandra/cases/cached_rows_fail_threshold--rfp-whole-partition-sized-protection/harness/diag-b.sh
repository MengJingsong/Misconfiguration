#!/usr/bin/env bash
# R24 DIAG-B (optional calibration probe, design §2.5 step 5, run in the slack after the readings): victim 8 GiB with Byteman rfp.btm
# (observe-only RfpProbe: PEAK populate lines with measureDeep of the held rows), peer 16 GiB; w2k QUORUM F = 128, 3 sequential first pages.
set -uo pipefail
L=DIAG-B; ROOT=/mydata/s4/r24; H=$ROOT/harness; R=$ROOT/runs/$L; V="bash $H/ctl.sh"; C="bash $H/client.sh"
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cached_rows_fail_threshold--rfp-whole-partition-sized-protection
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V prep "$L" CLONE || exit 1
$V start "$L" 1 8G auto diag && $V ready "$L" 1 && $V start "$L" 2 16G auto && $V ready "$L" 2 && $V ring "$L" || { $V stop "$L"; exit 1; }
grep -i byteman "$R/n1/stdout.log" | head -3
$C "$L" one 127.0.0.1 w2k QUORUM 128 3 2>&1 | grep -v '^SLF4J' | tee -a "$R/diag-client.txt"
sleep 2; $V stop "$L"
D=$REPO/logs/$L; mkdir -p "$D"; cp "$R"/{probe.txt,diag-client.txt,run.meta,ring.txt} "$D"/ 2>/dev/null
log "$L done; probe lines: $(wc -l < "$R/probe.txt" 2>/dev/null)"
