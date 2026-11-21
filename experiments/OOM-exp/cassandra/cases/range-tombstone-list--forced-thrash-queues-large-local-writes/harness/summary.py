import json,sys
for run in sys.argv[1:]:
    try:
        r=json.load(open("/mydata/s4/r22/logs/%s/analysis.json"%run))
    except Exception as e:
        print(run, "no analysis", e); continue
    f=r.get("fill",{}); p=r.get("poll_W",{}); b=r.get("backlog",{}); i=r.get("issued_W",{}); g=r.get("gc_W",{})
    h=r.get("hot",{})
    print(run, "| fill n=%s K=%s K/n=%s %ss" % (f.get("tombstones"), f.get("K_after"), f.get("K_per_tombstone"), f.get("seconds")),
          "| W=%s stop=%s gap=%s" % (r.get("W_s"), r.get("W_stop"), r.get("gc_gap_ge10s")),
          "| mu=%s blobapp/s=%s hotapp=%s blobapp=%s W40=%s act_mean30=%s pend_max30=%s ntr=%s/%s oldcoll_max=%s Kblob=%s sw_rt=%s sw_blob=%s CL=%s" % (
              p.get("mu_h_per_s"), p.get("blob_applied_per_s"), p.get("hot_applied"), p.get("blob_applied"), p.get("at_W40"), p.get("after_W30_active_mean"), p.get("after_W30_pending_max"),
              p.get("ntr_active_max"), p.get("ntr_pending_max"), p.get("old_coll_max_MiB"), p.get("K_blob_max_MiB"), p.get("sw_rt"), p.get("sw_blob"), p.get("cl_size_max_MiB")),
          "| backlog peak=%s last=%s hotpeak=%s" % (b.get("blob_peak"), b.get("blob_last"), b.get("hot_peak")),
          "| issued %s" % i,
          "| hot ok=%s to=%s err=%s lat_ok=%s lat_to=%s rate=%s" % (h.get("ok"), h.get("timeouts"), h.get("errors"), h.get("lat_ok_ms"), h.get("lat_timeout_ms"), h.get("ok_per_s")),
          "| gc %s" % g, "| L1 %s" % (r.get("hist",{}).get("L1") if isinstance(r.get("hist"),dict) else None), "| rss=%s done=%s" % (r.get("rssanon_max_MiB"), r.get("done")))
    print()
