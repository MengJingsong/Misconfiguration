#!/usr/bin/env python3
"""Reads a run's creation trace and link timeline for the cdc_total_space case (case §9a, §9d) and prints:

  1. the verdict formula check: for every segment created, `post state == FORBIDDEN` iff
     `blocking and S + pre.sip > A` (CommitLogSegmentManagerCDC.java:335-337);
  2. for every creation, how far the counter lagged the files: links that existed just before the creation (from the
     timeline) times S, minus `pre.sip`. A positive lag is a stale counter (the directory walk overwrote it without the
     newest link: the walk is submitted inside processNewSegment, the hard link is made after it returns);
  3. the creations that made a link beyond k = floor(A / S), with their lag: the case's attribution of an overshoot
     (a creation permitted although `links_before * S + S > A`, while `pre.sip + S <= A`);
  4. the link timeline's peak and the count when the first rejection was traced; for non-blocking, the deletions.

usage: cdc-analyze.py --trace cdc-verdict.txt --events <file> --format unit|sampler [--csv sampler.csv --phases phases.csv] [--json out.json]
  --format unit     the events are the "linkEvent +|- <name>" lines the harness test writes into readings.txt
  --format sampler  the events are cdc-sampler.py's .events file: ms,+|-,name,size
  --csv, --phases   cluster tier: the sampler's .csv and the runner's phases.csv (ms,label). Adds 5. the links at each phase,
                    the plateau (median of L over the last 20 s of B or C) and the peak, from the exact per-tick counts, and
                    checks that the link bytes were exactly L x S at every tick.

Observation only. A creation preceded by a link event within 2 sampling intervals is reported as ambiguous and left out of the
lag statistics (the start-up pair, made 1 ms apart, always is).
"""
import argparse
import json
import re
import sys

LINK = re.compile(r"CommitLog-\d+-\d+\.log$")


def parse_trace(path):
    pre, creations, deletes, rejects = {}, [], [], []
    for line in open(path):
        line = line.strip()
        kv = dict(re.findall(r"(\w+)=(\S+)", line))
        if line.startswith("pre "):
            pre[kv["seg"]] = dict(pre_ms=int(kv["ms"]), pre_sip=int(kv["sip"]), allowance=int(kv["allowance"]),
                                  S=int(kv["segSize"]), blocking=kv["blocking"] == "true")
        elif line.startswith("post "):
            p = pre.pop(kv["seg"], None)
            if p is None:
                continue
            p.update(seg=kv["seg"], state=kv["state"], post_sip=int(kv["sip"]), post_ms=int(kv["ms"]))
            creations.append(p)
        elif line.startswith("deleteOld "):
            deletes.append(dict(ms=int(kv["ms"]), bytesToFree=int(kv["bytesToFree"]), remaining=int(kv["remaining"])))
        elif line.startswith("reject "):
            rejects.append(dict(ms=int(kv["ms"]), n=int(kv["n"])))
    return creations, deletes, rejects


def parse_events(path, fmt):
    ev = []
    for line in open(path):
        if fmt == "unit":
            m = re.match(r"ms=(\d+) linkEvent ([+-]) (\S+)", line)
            if m and LINK.search(m.group(3)):
                ev.append((int(m.group(1)), m.group(2), m.group(3)))
        else:
            parts = line.strip().split(",")
            if len(parts) >= 3 and LINK.search(parts[2]):
                ev.append((int(parts[0]), parts[1], parts[2]))
    ev.sort(key=lambda e: (e[0], 0 if e[1] == '-' else 1, e[2]))   # at the same millisecond, removals first
    return ev


def parse_counts(path):
    """(ms, n) from the "linkCount n=" lines the harness test writes: the link count at one 5 ms tick."""
    out = []
    for line in open(path):
        m = re.match(r"ms=(\d+) linkCount n=(\d+)", line)
        if m:
            out.append((int(m.group(1)), int(m.group(2))))
    return out


def seg_id(name):
    """The numeric id in CommitLog-<version>-<id>.log or a trace's seg=... (ids are creation times, so they increase)."""
    return int(re.search(r"CommitLog-\d+-(\d+)", name).group(1))


def lifetime_boundary(events):
    """The smallest segment id among the links at the sampler's first tick: the segments the current commit-log lifetime had made
    before sampling began (the start-up pair). Creations with a smaller id belong to an earlier lifetime of the commit log, whose
    links were deleted when it was stopped (the unit test starts the commit log in setUpClass and again in @Before)."""
    adds = [(ms, n) for ms, sign, n in events if sign == "+"]
    if not adds:
        return None
    first_ms = adds[0][0]
    return min(seg_id(n) for ms, n in adds if ms - first_ms <= 20)


def links_at(events, t):
    live = set()
    for ms, sign, name in events:
        if ms > t:
            break
        if sign == "+":
            live.add(name)
        else:
            live.discard(name)
    return live


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if n == 0 else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)


def summarize_csv(csv_path, phases_path, S, blocking, out):
    rows = []
    for line in open(csv_path).read().splitlines()[1:]:
        f = line.split(",")
        if len(f) >= 8:
            rows.append(dict(ms=int(f[0]), links=int(f[1]), bytes=int(f[2]), alloc=int(f[3]), idx=int(f[4]), idxb=int(f[5]), gap=int(f[7])))
    phases = {}
    if phases_path:
        for line in open(phases_path):
            if "," in line:
                ms, name = line.strip().split(",", 1)
                phases[name] = int(ms)
    print("\n5. sampler CSV: %d ticks, max gap %d ms" % (len(rows), max(r["gap"] for r in rows)))
    out["ticks"], out["max_gap_ms"] = len(rows), max(r["gap"] for r in rows)
    bad = [r for r in rows if r["bytes"] != r["links"] * S]
    out["ticks_with_bytes_not_L_times_S"] = len(bad)
    print("   ticks where the link bytes were not exactly L x S: %d" % len(bad))

    def at(ms):
        best = None
        for r in rows:
            if r["ms"] <= ms:
                best = r
        return best

    def show(label, r):
        if r:
            print("   %-28s L=%-4d link_bytes=%-12d (%.2f S)  allocated=%-12d idx=%d/%d" % (label, r["links"], r["bytes"], r["bytes"] / S, r["alloc"], r["idx"], r["idxb"]))
            out["L_at_" + label.replace(" ", "_")] = r["links"]

    for name in ("idle_end", "A_first_rejection", "A_segments_reached", "A_end", "B_end", "C_end", "R_start", "R_end"):
        if name in phases:
            show(name, at(phases[name]))
    for start, end, tag in (("B_start", "B_end", "B"), ("C_start", "C_end", "C")):
        if start in phases and end in phases:
            win = [r for r in rows if phases[start] <= r["ms"] <= phases[end]]
            last = [r["links"] for r in rows if phases[end] - 20000 <= r["ms"] <= phases[end]]
            if win:
                out[tag + "_peak_L"] = max(r["links"] for r in win)
                out[tag + "_plateau_L_median_last20s"] = median(last)
                out[tag + "_min_L"] = min(r["links"] for r in win)
                print("   %s window: peak L=%d, min L=%d, plateau (median over its last 20 s) L=%s, bytes at peak=%d" %
                      (tag, out[tag + "_peak_L"], out[tag + "_min_L"], out[tag + "_plateau_L_median_last20s"], max(r["bytes"] for r in win)))
    out["peak_L_all_ticks"] = max(r["links"] for r in rows)
    out["peak_link_bytes_all_ticks"] = max(r["bytes"] for r in rows)
    print("   peak L over the whole run: %d (%d bytes = %.2f S)" % (out["peak_L_all_ticks"], out["peak_link_bytes_all_ticks"], out["peak_link_bytes_all_ticks"] / S))


def attribute_ceiling(creations, events, S, A, k, out):
    """Blocking mode: how many links were made beyond k, and was each one made under a stale counter; and, at an exact multiple
    of S, was the segment that would have been the k-th forbidden because the counter held the index-file bytes."""
    permitted = [c for c in creations if c["state"] == "PERMITTED"]
    # links the node ever made: one per permitted creation (the start-up pair included)
    made = len(permitted)
    beyond = [c for c in permitted if c["links_before"] + 1 > k]
    print("\n6. ceiling attribution (blocking): permitted creations = %d, k = %d, links made beyond k = %d" % (made, k, len(beyond)))
    out["permitted_creations"] = made
    out["links_beyond_k"] = len(beyond)
    unexplained = [c["seg"] for c in beyond if not ((c["pre_sip"] + S <= A) and (c["links_before"] * S + S > A))]
    out["links_beyond_k_unexplained_by_stale_counter"] = unexplained
    print("   each beyond-k link made while `S + counter <= A` but `S + files > A` (stale counter): %s" %
          ("yes" if beyond and not unexplained else ("n/a, none beyond k" if not beyond else "NO: " + str(unexplained))))
    if A % S == 0 and k >= 1:
        forb = [c for c in creations if c["state"] == "FORBIDDEN" and c["links_before"] == k - 1 and c["pre_sip"] > (k - 1) * S]
        out["exact_multiple_kth_forbidden_by_idx_bytes"] = [(c["seg"], c["pre_sip"] - (k - 1) * S) for c in forb]
        print("   exact multiple: creations forbidden with k - 1 links and a counter above (k - 1) * S (the index-file bytes): %s" %
              ([(c["seg"][-18:], c["pre_sip"] - (k - 1) * S) for c in forb] or "none"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--format", required=True, choices=["unit", "sampler"])
    ap.add_argument("--json")
    ap.add_argument("--interval-ms", type=int)
    ap.add_argument("--csv")
    ap.add_argument("--phases")
    a = ap.parse_args()
    interval = a.interval_ms or (5 if a.format == "unit" else 50)

    creations, deletes, rejects = parse_trace(a.trace)
    events = parse_events(a.events, a.format)
    out = dict(creations=len(creations))
    if not creations:
        print("no creations in the trace")
        return 1
    boundary = lifetime_boundary(events)
    earlier = [c for c in creations if boundary is not None and seg_id(c["seg"]) < boundary]
    if earlier:
        print("%d creation(s) before the current commit-log lifetime (segment id below %s) are left out: %s" %
              (len(earlier), boundary, ", ".join(c["seg"][-18:] for c in earlier)))
        creations = [c for c in creations if c not in earlier]
    out["creations_earlier_lifetime"] = len(earlier)
    S, A, blocking = creations[0]["S"], creations[0]["allowance"], creations[0]["blocking"]
    k = A // S
    out.update(S=S, A=A, k=k, blocking=blocking, exact_multiple=(A % S == 0))
    print("S=%d  A=%d  k=%d  blocking=%s  exact multiple of S: %s" % (S, A, k, blocking, A % S == 0))

    # 1. the verdict formula
    bad = []
    for c in creations:
        expected_forbidden = c["blocking"] and c["S"] + c["pre_sip"] > c["allowance"]
        c["expected_forbidden"] = expected_forbidden
        if (c["state"] == "FORBIDDEN") != expected_forbidden:
            bad.append(c["seg"])
    out["formula_violations"] = bad
    print("\n1. verdict formula  FORBIDDEN <=> blocking and S + pre.sip > A:  %d creations, %d violations %s"
          % (len(creations), len(bad), bad))

    # 2. counter lag against the files
    print("\n2. each creation (links = files that existed just before it: counted from the earlier permitted creations in blocking mode, from the timeline otherwise)")
    print("   %-28s %5s %6s %14s %12s %-9s %s" % ("segment", "links", "pre.sip/S", "pre.sip", "lag bytes", "verdict", "note"))
    rows, stale = [], 0
    last_link_event = [e[0] for e in events]
    permitted = 0
    first_removal_ms = next((ms for ms, sign, name in events if sign == "-"), None)
    for c in creations:
        t = c["pre_ms"]
        # the timeline: ambiguous only if a link event falls just before this creation's own link (made after its post line)
        near = any(t - 2 * interval <= ms < c["post_ms"] for ms in last_link_event)
        live = links_at(events, t - 1)
        c["links_timeline"] = len(live)
        # blocking mode, before anything is deleted: every earlier permitted creation made its link before this one began
        # (the manager thread runs processNewSegment and the hard link, then the next creation), so the count is exact
        # whatever the sampling interval
        logical = blocking and (first_removal_ms is None or t < first_removal_ms)
        c["links_before"] = permitted if logical else len(live)
        c["links_source"] = "logical" if logical else "timeline"
        c["lag"] = c["links_before"] * S - c["pre_sip"]
        c["ambiguous"] = near and not logical
        disagree = logical and not near and len(live) != c["links_before"]
        if c["state"] == "PERMITTED":
            permitted += 1
        note = "ambiguous (a link event within %d ms before)" % (2 * interval) if c["ambiguous"] else ""
        if not c["ambiguous"] and c["lag"] >= S // 2:
            stale += 1
            note = "STALE: counter %.2f segments low" % (c["lag"] / S)
        if disagree:
            note += "  [timeline says %d links]" % len(live)
        print("   %-28s %5d %6.2f %14d %12d %-9s %s" % (c["seg"][-18:], c["links_before"], c["pre_sip"] / S, c["pre_sip"], c["lag"], c["state"], note))
        rows.append({k_: v for k_, v in c.items()})
    usable = [c for c in creations if not c["ambiguous"]]
    out.update(creations_permitted=permitted, creations_forbidden=len(creations) - permitted,
               stale_creations=stale, unambiguous_creations=len(usable))
    print("   stale (lag >= S/2) among %d unambiguous creations: %d" % (len(usable), stale))

    # 3. the creations that made a link beyond k
    print("\n3. creations that made a link beyond k = %d%s" % (k, "" if blocking else "  (blocking mode only: in non-blocking mode every segment is permitted and the oldest links are deleted)"))
    beyond = [c for c in creations if blocking and c["state"] == "PERMITTED" and c["links_before"] + 1 > k]
    out["beyond_k"] = []
    if not beyond:
        print("   none")
    for c in beyond:
        stale_proof = (c["pre_sip"] + S <= A) and (c["links_before"] * S + S > A)
        rec = dict(seg=c["seg"], links_before=c["links_before"], pre_sip=c["pre_sip"], lag=c["lag"],
                   counter_allowed=(c["pre_sip"] + S <= A), files_would_forbid=(c["links_before"] * S + S > A),
                   stale_proof=stale_proof, ambiguous=c["ambiguous"])
        out["beyond_k"].append(rec)
        print("   %s: links before %d, counter %d (%.2f S), S + counter <= A: %s, S + files*S <= A: %s  => %s"
              % (c["seg"][-18:], c["links_before"], c["pre_sip"], c["pre_sip"] / S, c["pre_sip"] + S <= A,
                 c["links_before"] * S + S <= A,
                 "stale counter let it through" if stale_proof else "NOT explained by a stale counter"))

    # 4. timeline
    first_removal = next((ms for ms, sign, name in events if sign == "-"), None)
    if a.format == "unit":
        counts = parse_counts(a.events)
        series = [n for ms, n in counts if first_removal is None or not blocking or ms < first_removal]
        peak = max(series) if series else 0
        how = "per-tick link counts"
    else:
        peak, how = None, "see the sampler's CSV (peak of its links column)"
        live, peak = set(), 0
        for ms, sign, name in events:
            live.add(name) if sign == "+" else live.discard(name)
            if (first_removal is None or not blocking or ms < first_removal) and len(live) > peak:
                peak = len(live)
        how = "from the events; same-tick ordering can inflate it by 1, the CSV is exact"
    out["peak_links"] = peak
    print("\n4. link timeline: peak L = %d%s  (%s)" % (peak, " before the first removal" if blocking else "", how))
    if rejects:
        first = rejects[0]["ms"]
        L_first = len(links_at(events, first))
        out.update(L_at_first_reject_trace=L_first, rejects_traced=len(rejects), rejections_counted=rejects[-1]["n"])
        print("   first rejection traced at %d: L = %d; rejection lines traced: %d, rejections counted up to the last: %d"
              % (first, L_first, len(rejects), rejects[-1]["n"]))
    if deletes or not blocking:
        removed = [(ms, n) for ms, s, n in events if s == "-"]
        ids = [int(n.split("-")[2].split(".")[0]) for ms, n in removed]
        out.update(deleteOld_calls=len(deletes), links_removed=len(removed), removed_in_ascending_order=(ids == sorted(ids)))
        print("   deleteOld calls: %d; links removed: %d; removed in ascending segment order: %s"
              % (len(deletes), len(removed), ids == sorted(ids)))
    if a.csv:
        summarize_csv(a.csv, a.phases, S, blocking, out)
    if blocking:
        attribute_ceiling(creations, events, S, A, k, out)
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
