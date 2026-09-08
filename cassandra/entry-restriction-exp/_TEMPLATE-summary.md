# [entry_name] — Pair [NN] · Summary

> **Codepath:** [[entry_name]-[NN]-codepath.md]([entry_name]-[NN]-codepath.md) · **Index:** [../_INDEX.md](../_INDEX.md)

## Identity

| Field | Content |
|-------|---------|
| **Entry Point ID** | e.g. MEMTABLE_001 |
| **Name** | e.g. memtable_heap_space |
| **Type** | Configuration / Hardcoded constant / Variable type / Enum / ... |
| **Declaration Location** | `file:line` (where the constraint is declared/defined) |
| **Default Value** | |
| **Value Type / Size** | e.g. long (bytes), int (count), double (fraction) — note overflow surface |
| **Description** | What this constraint limits |
| **Restriction Location** | `Class.method():line` — the resource-restriction location for **this** pair |
| **Pair** | [NN] of [M] |

## Key Decision Points

_Distilled critical nodes (full trace lives in the codepath file)._

1. **read:** `Class.method():line`
2. **check:** `Class.method():line`
3. **enforce:** `Class.method():line`

## Enforcement

| Field | Content |
|-------|---------|
| **Enforcement Point** | `Class.method():line` |
| **Action on Breach** | e.g. trigger flush / throw exception / reject request / block |

## Failure Mode Analysis

| Mode | Status (✓/✗/⚠) | Notes |
|------|----------------|-------|
| **Proxy Match** | | Does it measure the actual resource, or a weakly-correlated proxy? |
| **Enforcement Point** | | Right lifecycle stage, or after resource already used? |
| **Default State** | | Enabled by default? |

## Related / Dependent Constraints

- _Other limits that interact with this one._

## Bypass Potential (Target 3 seed)

- _Initial hypotheses for how enforcement could be bypassed / exhausted._

## Verification

| Field | Content |
|-------|---------|
| **Status** | pending / in-progress / verified |
| **CodeQL Pattern** | which of the 3 if-check patterns (if applicable) |
| **Verified By / Date** | |

## Notes

- 
