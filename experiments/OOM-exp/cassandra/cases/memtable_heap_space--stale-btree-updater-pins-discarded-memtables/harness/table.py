#!/usr/bin/env python3
"""R21: one markdown row per lifetime from analyze.py's JSON lines (stdin). usage: python3 -I table.py < analyze.jsonl"""
import json, sys
print('| Lifetime | Outcome (s) | acked MiB | gate waits / retired | Writing max % / contention lines | K max (sampler) ×C | '
      'dump | U regions (×C) | U_pin (×C) | K pool MiB (×C) | uncounted | D / M_D / f | stale updaters / SEP workers | '
      'old after full GC max MiB / after any GC max MiB | end hist MiB |')
print('|' + '---|' * 15)
for l in sys.stdin:
    r = json.loads(l)
    if r.get('error'):
        print(f"| {r['label']} | error {r['error']} |"); continue
    g = r.get('gate') or {}
    dumps = [k for k in r if k.startswith('dump_')]
    if not dumps:
        dumps = [None]
    for k in dumps:
        x = r.get(k) or {}
        print(f"| {r['label']} | {r.get('outcome')} ({r.get('outcome_at_s')}) | {r.get('acked_MiB')} | {g.get('gate_waits')} / {g.get('retired')} | "
              f"{r.get('writing_max_pct')} / {r.get('contention_n')} | {r.get('K_max_xC')} | {k[5:] if k else '-'} | "
              f"{x.get('U_regions')} ({x.get('U_xC')}) | {x.get('U_pin')} ({x.get('U_pin_xC')}) | {x.get('K_MiB')} ({x.get('K_xC')}) | "
              f"{x.get('uncounted')} | {x.get('D')} / {x.get('M_D')} / {x.get('f')} | {x.get('updaters_with_updateF')} / {x.get('sep_workers')} | "
              f"{(r.get('gc') or {}).get('max_full_after_MiB')} / {(r.get('gc') or {}).get('max_after_MiB')} | {x.get('hist_total_MiB', r.get('U_end_MiB'))} |")
