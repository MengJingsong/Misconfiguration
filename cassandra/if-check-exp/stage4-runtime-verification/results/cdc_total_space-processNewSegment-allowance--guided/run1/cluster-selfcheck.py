#!/usr/bin/env python3
"""Self-check of the cluster tier (results §5): re-reads each value's raw files with its own parsing, not cluster-readings.py or
cdc-analyze.py, and checks the statements the conclusion rests on. One line per check, PASS or FAIL, and a count.

usage: cluster-selfcheck.py <cluster directory holding one folder per value>

Blocking values (b144 b272 b528 bdef s16):
  K1  settings read back match the label (A, S, cdc_enabled, cdc_block_writes true)
  K2  valid run: sampler gap <= 1000 ms; a rejection WARN appeared; nothing was deleted from cdc_raw before the release
  K3  L at the first traced rejection, counted from the events file, equals the sampler CSV's L and is k (exact multiple: k - 1 or
      k) or k + 1 with the overshoot attributed (K7)
  K4  usage stops: L is the same at every tick from the first rejection to the end of B
  K5  the apparent bytes were exactly L x S at every tick, and the allocated bytes never above them
  K6  the verdict formula holds for every creation (FORBIDDEN iff S + pre.sip > A), re-parsed from the trace
  K7  every link beyond k was made by a creation with S + pre.sip <= A while S + links_before x S > A (a stale counter)
  K8  every counter N in the WARN lines is within L x S .. L x S + 64 x L
  K9  disallow evidence: WARN entries, logged rejected writes, the CDC stress's errors equal its attempts, and `Failures` is at least that
  K10 the non-CDC control had no errors and wrote rows
  K11 release: a consumer pass deleted links and a probe write was accepted
Non-blocking values (n144 n528):
  N1  no rejection: no WARN entries, no logged rejected writes, no stress errors
  N2  L <= k + 1 at every tick of the run
  N3  removed links went in ascending segment order, and the first link made was removed
  N4  deleteOld passes were traced, each leaving `remaining` at most A (links beyond the allowance were removed before the new one was made)
  N5  every creation was PERMITTED and the verdict formula held
Consumer control (c272):
  C1  no WARN entry, no logged rejected write, no stress error; C2  L <= k at every tick; C3  the loop deleted links and at least 3 x A bytes were written
Across values:
  X1  attributed ceiling (L minus the links beyond k) equals k at every blocking value (k - 1 or k at an exact multiple)
  X2  the raw plateau grows with A across b144, b272, b528 and the default; the byte ceiling moves with S (s16 against b272)
"""
import csv
import gzip
import os
import re
import statistics
import sys

fails = 0
total = 0


def check(label, name, ok, note=""):
    global fails, total
    total += 1
    if not ok:
        fails += 1
    print("%-5s %-6s %-4s %s" % ("PASS" if ok else "FAIL", label, name, note))


def tup(t):
    return "no result (the stress did not finish)" if t is None else "errors %s, rows %s" % t


def kv(line):
    return dict(re.findall(r"(\w+)=(\S+)", line))


def seg_id(n):
    return int(re.search(r"CommitLog-\d+-(\d+)", n).group(1))


def load(d):
    r = {}
    st = open(os.path.join(d, "settings.txt")).read()
    val = lambda key: (re.search(key + r"\s*\|\s*(\S+)", st) or [None, ""])[1]
    r["A"] = int(re.sub(r"\D", "", val("cdc_total_space"))) << 20
    r["S"] = int(re.sub(r"\D", "", val("commitlog_segment_size"))) << 20
    r["enabled"], r["blocking"] = val("cdc_enabled").lower(), val("cdc_block_writes").lower()
    r["phases"] = {}
    for line in open(os.path.join(d, "phases.csv")):
        if "," in line:
            ms, name = line.strip().split(",", 1)
            r["phases"][name] = int(ms)
    r["ticks"] = []
    for line in open(os.path.join(d, "sampler.csv")).read().splitlines()[1:]:
        f = line.split(",")
        r["ticks"].append(tuple(int(x) for x in f))      # ms, links, bytes, alloc, idx, idxb, other, gap
    r["events"] = []
    for line in open(os.path.join(d, "sampler.events")):
        f = line.strip().split(",")
        if len(f) >= 3 and re.search(r"CommitLog-\d+-\d+\.log$", f[2]):
            r["events"].append((int(f[0]), f[1], f[2]))
    pre, r["creations"], r["rejects"], r["deleteOld"] = {}, [], [], []
    for line in open(os.path.join(d, "cdc-verdict.txt")):
        f = kv(line)
        if line.startswith("pre "):
            pre[f["seg"]] = f
        elif line.startswith("post "):
            p = pre.pop(f["seg"], None)
            if p:
                r["creations"].append((p, f))
        elif line.startswith("reject "):
            r["rejects"].append((int(f["ms"]), int(f["n"])))
        elif line.startswith("deleteOld "):
            r["deleteOld"].append((int(f["bytesToFree"]), int(f["remaining"])))
    sp = os.path.join(d, "system.log")
    sl = (open(sp) if os.path.exists(sp) else gzip.open(sp + ".gz", "rt")).read().splitlines()
    r["warns"] = [l for l in sl if l.startswith("WARN") and "Rejecting mutation to keyspace" in l]
    r["stacks"] = sum(1 for l in sl if l.startswith("org.apache.cassandra.exceptions.CDCWriteException"))
    def stress(name):
        p = os.path.join(d, name)
        if not os.path.exists(p):
            return None
        t = open(p).read()
        e = re.search(r"Total errors\s*:\s*([\d,]+)", t)
        n = re.search(r"Total partitions\s*:\s*([\d,]+)", t)
        return (int(e.group(1).replace(",", "")), int(n.group(1).replace(",", ""))) if e and n else None
    r["cdcB"], r["plainB"], r["cdcC"] = stress("stress-cdc-B.txt"), stress("stress-plain-B.txt"), stress("stress-cdc-C.txt")
    rows = list(csv.DictReader(open(os.path.join(d, "readings.csv"))))
    r["failures"] = next((x["Failures"] for x in rows if x["phase"] in ("Bend", "Cend")), None)
    rp = os.path.join(d, "release-probe.txt")
    r["probe"] = open(rp).read().splitlines() if os.path.exists(rp) else None
    cp = os.path.join(d, "consumer-release.txt")
    r["consumer_deleted"] = sum(1 for l in open(cp) if ",deleted," in l) if os.path.exists(cp) else None
    cl = os.path.join(d, "consumer.txt")
    r["consumer_loop_deleted"] = sum(1 for l in open(cl) if ",deleted," in l) if os.path.exists(cl) else None
    return r


def live_at(events, ms):
    live = set()
    for t, sg, n in sorted(events, key=lambda e: (e[0], 0 if e[1] == "-" else 1)):
        if t > ms:
            break
        live.add(n) if sg == "+" else live.discard(n)
    return live


def tick_at(ticks, ms):
    best = None
    for t in ticks:
        if t[0] <= ms:
            best = t
    return best


def main():
    root = sys.argv[1]
    data = {}
    for label in ["b144", "b272", "b528", "bdef", "s16", "n144", "n528", "c272"]:
        d = os.path.join(root, label)
        if os.path.isdir(d):
            data[label] = load(d)
    adjusted = {}
    for label, r in data.items():
        S, A = r["S"], r["A"]
        k = A // S
        ph, ticks = r["phases"], r["ticks"]
        blocking = r["blocking"] in ("true",)
        kind = "consumer" if label == "c272" else ("blocking" if blocking else "nonblocking")
        first_removal = min((t for t, sg, n in r["events"] if sg == "-"), default=None)
        # lifetime boundary: nothing earlier than the segments present at the sampler's first tick (a fresh node: none)
        bound = min((seg_id(n) for t, sg, n in r["events"][:3] if sg == "+"), default=None)
        creations = [(p, q) for p, q in r["creations"] if bound is None or seg_id(p["seg"]) >= bound]
        bad = [p["seg"] for p, q in creations
               if (p["blocking"] == "true" and int(p["segSize"]) + int(p["sip"]) > int(p["allowance"])) != (q["state"] == "FORBIDDEN")]
        if kind in ("blocking", "consumer"):
            pass
        if kind == "blocking":
            want = {"b144": 144, "b272": 272, "b528": 528, "s16": 280}.get(label)
            check(label, "K1", r["enabled"] == "true" and r["blocking"] == "true" and (want is None or r["A"] == want << 20) and
                  r["S"] == (16 if label == "s16" else 32) << 20 and (label != "bdef" or r["A"] == 4096 << 20),
                  "A=%d MiB S=%d MiB enabled=%s block_writes=%s" % (A >> 20, S >> 20, r["enabled"], r["blocking"]))
            gap = max(t[7] for t in ticks)
            pre_release_removals = [t for t, sg, n in r["events"] if sg == "-" and t < ph["R_start"]]
            check(label, "K2", gap <= 1000 and len(r["warns"]) >= 1 and not pre_release_removals and "A_first_rejection" in ph,
                  "max sampler gap %d ms, WARN entries %d, removals before the release %d" % (gap, len(r["warns"]), len(pre_release_removals)))
            first_rej = r["rejects"][0][0]
            L_events = len(live_at(r["events"], first_rej))
            L_csv = tick_at(ticks, first_rej)[1]
            exact = A % S == 0
            # K7 first, so K3 can use it
            made, beyond, stale_ok = 0, [], True
            for p, q in creations:
                if q["state"] != "PERMITTED":
                    continue
                if first_removal is not None and int(p["ms"]) >= first_removal:
                    continue
                lb = made
                made += 1
                if lb + 1 > k:
                    stale = int(p["sip"]) + S <= A and lb * S + S > A
                    beyond.append((p["seg"][-6:], lb, int(p["sip"]) / S, stale))
                    stale_ok &= stale
            check(label, "K7", stale_ok and len(beyond) <= 1, "links beyond k: %d %s" % (len(beyond), beyond))
            ok3 = L_events == L_csv and ((L_csv in (k - 1, k)) if exact else (L_csv == k or (L_csv == k + 1 and stale_ok and len(beyond) == 1)))
            check(label, "K3", ok3, "L at the first rejection: events %d, csv %d; k=%d exact_multiple=%s" % (L_events, L_csv, k, exact))
            window = [t[1] for t in ticks if t[0] >= first_rej and t[0] <= ph["B_end"]]
            check(label, "K4", len(set(window)) == 1, "L over %d ticks from the first rejection to B's end: min %d max %d" % (len(window), min(window), max(window)))
            check(label, "K5", all(t[2] == t[1] * S for t in ticks) and all(t[3] <= t[2] for t in ticks),
                  "ticks %d; bytes != L x S: %d; allocated > apparent: %d" % (len(ticks), sum(1 for t in ticks if t[2] != t[1] * S), sum(1 for t in ticks if t[3] > t[2])))
            check(label, "K6", not bad, "%d creations, %d violations" % (len(creations), len(bad)))
            Ns = [int(m.group(1)) for l in r["warns"] for m in [re.search(r"Total CDC bytes on disk is (\d+)", l)] if m]
            Lp = statistics.median([t[1] for t in ticks if ph["B_end"] - 20000 <= t[0] <= ph["B_end"]])
            check(label, "K8", all(Lp * S <= n <= Lp * S + 64 * max(Lp, 1) for n in Ns), "plateau L=%d; N in %d..%d (%d distinct)" % (Lp, min(Ns), max(Ns), len(set(Ns))))
            fcount = int(r["failures"]) if (r["failures"] or "").isdigit() else -1
            check(label, "K9", len(r["warns"]) >= 1 and r["stacks"] >= 1000 and bool(r["cdcB"]) and r["cdcB"][0] == r["cdcB"][1] and fcount >= r["cdcB"][0],
                  "WARN %d, logged rejected writes %d, CDC stress B %s (errors must equal attempts), Failures %s" % (len(r["warns"]), r["stacks"], tup(r["cdcB"]), r["failures"]))
            check(label, "K10", bool(r["plainB"]) and r["plainB"][0] == 0 and r["plainB"][1] > 0, "non-CDC control: " + tup(r["plainB"]))
            accepted = bool(r["probe"]) and re.search(r"rc=0", r["probe"][-1]) is not None
            check(label, "K11", (r["consumer_deleted"] or 0) > 0 and accepted, "consumer pass deleted %s links; probe attempts %d, last accepted %s" % (r["consumer_deleted"], len(r["probe"] or []), accepted))
            adjusted[label] = (L_csv - len(beyond), k, L_csv, S, exact)
        elif kind == "nonblocking":
            check(label, "N1", len(r["warns"]) == 0 and r["stacks"] == 0 and bool(r["cdcB"]) and r["cdcB"][0] == 0, "WARN %d, logged rejected writes %d, CDC stress B %s" % (len(r["warns"]), r["stacks"], tup(r["cdcB"])))
            mx = max(t[1] for t in ticks)
            check(label, "N2", mx <= k + 1, "max L over %d ticks = %d, k + 1 = %d" % (len(ticks), mx, k + 1))
            removed = [n for t, sg, n in sorted(r["events"]) if sg == "-"]
            ids = [seg_id(n) for n in removed]
            made_names = [n for t, sg, n in sorted(r["events"]) if sg == "+"]
            check(label, "N3", ids == sorted(ids) and len(ids) > 0 and made_names[0] in removed, "%d links removed, ascending %s, first link made was removed %s" % (len(ids), ids == sorted(ids), made_names[0] in removed))
            check(label, "N4", len(r["deleteOld"]) > 0 and all(rem <= A for b, rem in r["deleteOld"]), "%d deleteOld passes; max remaining %.2f x S (A = %.2f x S)" % (len(r["deleteOld"]), max(rem for b, rem in r["deleteOld"]) / S, A / S))
            check(label, "N5", all(q["state"] == "PERMITTED" for p, q in creations) and not bad, "%d creations, all PERMITTED: %s, formula violations %d" % (len(creations), all(q["state"] == "PERMITTED" for p, q in creations), len(bad)))
        else:
            check(label, "C1", len(r["warns"]) == 0 and r["stacks"] == 0 and bool(r["cdcC"]) and r["cdcC"][0] == 0, "WARN %d, logged rejected writes %d, CDC stress %s" % (len(r["warns"]), r["stacks"], tup(r["cdcC"])))
            mx = max(t[1] for t in ticks)
            check(label, "C2", mx <= k, "max L over %d ticks = %d, k = %d" % (len(ticks), mx, k))
            written = len(creations) * S
            check(label, "C3", (r["consumer_loop_deleted"] or 0) > 0 and written >= 3 * A, "consumer loop deleted %s links; %d segments created = %.0f MiB against 3 x A = %.0f MiB" % (r["consumer_loop_deleted"], len(creations), written / 2**20, 3 * A / 2**20))
    # across values
    if adjusted:
        # (the first version demanded adj == k at every value, including the exact multiple, where 9a predicts k - 1 or k: corrected)
        check("all", "X1", all((adj in (k - 1, k)) if exact else adj == k for adj, k, raw, S, exact in adjusted.values()),
              "; ".join("%s: raw %d, attributed %d, k %d%s" % (l, raw, adj, k, " (exact multiple: k - 1 or k)" if exact else "") for l, (adj, k, raw, S, exact) in adjusted.items()))
        main_vals = [l for l in ("b144", "b272", "b528", "bdef") if l in adjusted]
        raws = [adjusted[l][2] for l in main_vals]
        bytes_s16 = adjusted["s16"][0] * adjusted["s16"][3] if "s16" in adjusted else None
        bytes_272 = adjusted["b272"][0] * adjusted["b272"][3] if "b272" in adjusted else None
        check("all", "X2", raws == sorted(raws) and len(set(raws)) == len(raws) and (bytes_s16 is None or bytes_272 is None or bytes_s16 - bytes_272 == 16 << 20),
              "raw plateaus %s; attributed byte ceilings s16 %s MiB, b272 %s MiB" % (dict(zip(main_vals, raws)), None if bytes_s16 is None else bytes_s16 >> 20, None if bytes_272 is None else bytes_272 >> 20))
    print("\n%d checks, %d FAIL" % (total, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
