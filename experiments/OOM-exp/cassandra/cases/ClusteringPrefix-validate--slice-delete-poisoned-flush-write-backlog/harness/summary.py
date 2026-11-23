#!/usr/bin/env python3
"""U15: one line per run from <base>/<run>/analysis.json. usage: python3 -I summary.py <run> ..."""
import json, sys
for run in sys.argv[1:]:
    try:
        r = json.load(open('/mydata/s4/u15/%s/analysis.json' % run))
    except Exception as e:
        print(run, 'no analysis', e)
        continue
    d = r.get('dump') or {}
    p = r.get('poison') or {}
    t = r.get('data_totals') or {}
    print(run, '| stop=%s W=%s oom=%s oom_at=W+%s thr=%s' % (r.get('W_stop'), r.get('W_s'), r.get('oom'), r.get('oom_first_W_rel_s'), r.get('oom_first_thread')),
          '| sw=%s enq=%s assert=%s/%s fl=%s done_fl=%s' % (r.get('switches_W_rel_s'), [(e[1], e[2]) for e in r.get('enqueue_u15_t', [])][:6] if len(r.get('enqueue_u15_t', [])) <= 6 else '%d enq' % len(r['enqueue_u15_t']),
                                                         r.get('assert_65535_n'), r.get('assert_lengths'), r.get('flushing_largest')[:3], r.get('completed_flush_u15_t_n')),
          '| flat@%s Kpool=%s Klive_max=%s stall=%s' % (r.get('applied_flat_from_W_s'), r.get('K_pool_D1D2_MiB'), r.get('K_live_max_MiB'), r.get('stall_check')),
          '| applied=%s (%s/s) data iss=%s cap=%s ok=%s to=%s err=%s poison ok=%s to=%s err=%s inv=%s' % (r.get('applied_W'), r.get('applied_per_s_W'), t.get('issued'), t.get('capped'), t.get('ok'), t.get('timeouts'), t.get('errors'), p.get('ok'), p.get('timeouts'), p.get('errors'), p.get('invalid_request')),
          '| backlog peak=%s last=%s slope20=%s slope120=%s act=%s pend=%s ntr=%s' % (r.get('backlog_peak'), r.get('backlog_last'), r.get('backlog_slope_first20_after_stall_per_s'), r.get('backlog_slope_last120_per_s'), r.get('active_max'), r.get('pending_max'), r.get('ntr_active_max')),
          '| old_coll_max=%s fullgc n=%s first@%s after=%s stw60=%s cl=%s rss=%s' % (r.get('old_coll_max_MiB'), r.get('gc_full_n'), r.get('gc_full_first_W_rel_s'), r.get('gc_full_after_MiB'), r.get('stw_max_share_60s'), r.get('cl_size_max_MiB'), r.get('rssanon_max_MiB')),
          '| dump total=%s 1MiB=%s SP4=%s Mut=%s PU=%s SLM=%s poison=%s' % (d.get('total'), d.get('byte_1MiB'), d.get('SP4'), d.get('Mutation'), d.get('PartitionUpdate'), d.get('SkipListMemtable'), d.get('poison_lengths')),
          '| L1=%s' % ((r.get('hist') or {}).get('L1.txt')),
          '| MDM=%s' % r.get('MaxDirectMemorySize'))
    print()
