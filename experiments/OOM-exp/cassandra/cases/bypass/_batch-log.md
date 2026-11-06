# Bypass batch log

## Current campaign status — 2026-11-06

Planning entries only; no bypass experiment has run in this update. Use the
[campaign plan](../../campaign-plan.md) and [protocol](../../../verification-protocol.md).
Append dated execution records with attempted/skipped cases, configuration/budget
regime, evidence, status/range and stopping reason.

| Mechanism / allocation domain | Priority | Status / next action |
|---|---|---|
| B1 / native-v5 request allocation lifecycle | P1 | open; audit recorded retention and construct repeated-cycle controls |
| B2 / memtable and pre-V5 exceptional admission | P2 | open; separate paths, quantify outstanding-work bounds |
| B3 / buffer-pool fallback | P2 | open; distinguish pool contract from total allocation |
| B4 / cache explicit-clear release | P2 | open; trace ownership before repeated-cycle test |
| B5 / periodic enforcement or replacement ordering | P3 | open; verify format/path and temporal bounds |
