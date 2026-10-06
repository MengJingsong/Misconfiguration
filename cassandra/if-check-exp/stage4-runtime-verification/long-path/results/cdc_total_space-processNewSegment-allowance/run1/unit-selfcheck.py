#!/usr/bin/env python3
"""Self-check of the unit tier (results §5): re-reads each JVM's raw files with its own parsing, not unit-readings.py or
cdc-analyze.py, and checks the statements the conclusion rests on. Prints one line per check, PASS or FAIL, and a count.

usage: unit-selfcheck.py <unit directory holding one folder per JVM>

Checks per blocking JVM (readings.txt = the test's STAGE4 lines, cdc-verdict.txt = the creation trace):
  C1  the settings in force match the label (A, S, mode) and S + A give k
  C2  L at the first rejection, recounted from the link timeline at that millisecond, equals the test's printed L
  C3  that L is k (exact multiple: k - 1 or k), or k + 1 with the overshoot attributed (C4)
  C4  every link beyond k was made by a creation with `S + pre.sip <= A` while `S + links_before * S > A` (stale counter)
  C5  the verdict formula holds for every creation in the trace: FORBIDDEN iff `S + pre.sip > A`
  C6  the number of permitted creations equals the number of links that appeared in the timeline before the release
  C7  after ten more tries: all ten rejected, L unchanged; a non-CDC write accepted
  C8  the counter in the message (N) is within L*S .. L*S + 64*L
  C9  release: the writer resumed (not for k = 0)
Checks per non-blocking JVM:
  D1  no rejection; D2  maximum per-tick L is at most k + 1; D3  removed links went in ascending segment order;
  D4  links deleted = distinct links seen - final links; D5  bytes retained < bytes written; D6  verdict formula (no FORBIDDEN)
"""
import os
import re
import sys

fails = 0
total = 0


def check(label, name, ok, note=""):
    global fails, total
    total += 1
    if not ok:
        fails += 1
    print("%-5s %-10s %-4s %s %s" % ("PASS" if ok else "FAIL", label, name, "", note))


def kv(line):
    return dict(re.findall(r"(\w+)=(\S+)", line))


def parse(d):
    rd = open(os.path.join(d, "readings.txt")).read().splitlines()
    cfg = first = counter = after = release = nb = nbb = None
    events, counts, nonCdc, skipped = [], [], False, False
    for line in rd:
        m = re.match(r"ms=(\d+) (.*)", line)
        if not m:
            continue
        ms, body = int(m.group(1)), m.group(2)
        if body.startswith("config "):
            cfg = kv(body)
        elif body.startswith("firstRejection "):
            first = dict(kv(body), ms=ms)
        elif body.startswith("rejectionCounter "):
            counter = kv(body)
        elif body.startswith("afterTenMore "):
            after = kv(body)
        elif body.startswith("nonCdcWrite "):
            nonCdc = "accepted=true" in body
        elif body.startswith("release resumed="):
            release = kv(body)
        elif body.startswith("release skipped"):
            skipped = True
        elif body.startswith("nonBlocking rowsWritten"):
            nb = kv(body)
        elif body.startswith("nonBlocking bytesWritten"):
            nbb = kv(body)
        elif body.startswith("linkEvent "):
            _, sign, name = body.split()
            events.append((ms, sign, name))
        elif body.startswith("linkCount "):
            counts.append((ms, int(kv(body)["n"])))
    pre, creations = {}, []
    for line in open(os.path.join(d, "cdc-verdict.txt")):
        f = kv(line)
        if line.startswith("pre "):
            pre[f["seg"]] = f
        elif line.startswith("post "):
            p = pre.pop(f["seg"], None)
            if p:
                creations.append((p, f))
    return cfg, first, counter, after, nonCdc, release, skipped, nb, nbb, events, counts, creations


def seg_id(name):
    return int(re.search(r"CommitLog-\d+-(\d+)", name).group(1))


def current_lifetime(events, creations):
    """Creations of the commit-log lifetime that the test measures: those with a segment id at or above the smallest id among the
    links the sampler saw at its first tick (an earlier lifetime was stopped, and its links deleted, in @Before)."""
    adds = [(ms, n) for ms, sign, n in events if sign == "+"]
    if not adds:
        return creations
    first = adds[0][0]
    boundary = min(seg_id(n) for ms, n in adds if ms - first <= 20)
    return [(p, q) for p, q in creations if seg_id(p["seg"]) >= boundary]


def live_at(events, ms):
    live = set()
    for t, sign, name in sorted(events, key=lambda e: (e[0], 0 if e[1] == "-" else 1)):
        if t > ms:
            break
        live.add(name) if sign == "+" else live.discard(name)
    return live


def main():
    root = sys.argv[1]
    for label in ["u16", "u48", "u80", "u128", "u144", "u272", "u280-s16", "u80-nb", "u144-nb"]:
        d = os.path.join(root, label)
        if not os.path.isdir(d):
            continue
        cfg, first, counter, after, nonCdc, release, skipped, nb, nbb, events, counts, creations = parse(d)
        creations = current_lifetime(events, creations)
        S, A = int(cfg["S"]), int(cfg["A"])
        k = A // S
        blocking = cfg["mode"] == "blocking"
        want = re.match(r"u(\d+)(?:-s(\d+))?(-nb)?$", label)
        A_label, S_label = int(want.group(1)), int(want.group(2) or 32)
        check(label, "C1", int(cfg["totalSpaceMiB"]) == A_label and int(cfg["segmentMiB"]) == S_label and (cfg["mode"] == "nonblocking") == bool(want.group(3))
              and k == int(cfg["k"]), "A=%dMiB S=%dMiB mode=%s k=%d" % (A_label, S_label, cfg["mode"], k))
        # C5/D6: the formula for every creation
        bad = []
        for p, q in creations:
            forb = p["blocking"] == "true" and int(p["segSize"]) + int(p["sip"]) > int(p["allowance"])
            if forb != (q["state"] == "FORBIDDEN"):
                bad.append(p["seg"])
        check(label, "C5" if blocking else "D6", not bad, "%d creations, %d violations" % (len(creations), len(bad)))
        permitted = [(p, q) for p, q in creations if q["state"] == "PERMITTED"]
        names_seen = {n for t, s, n in events if s == "+"}
        if blocking:
            L_first = len(live_at(events, int(first["ms"]) - 1))
            printed = int(first["links"])
            # the timeline samples every 5 ms: allow the printed value to lead by one link made within 10 ms of the reading
            check(label, "C2", L_first == printed or abs(L_first - printed) == 1 and any(0 <= int(first["ms"]) - t <= 10 for t, s, n in events if s == "+"),
                  "timeline says %d, test printed %d" % (L_first, printed))
            exact = A % S == 0
            ok_k = (printed in (k - 1, k)) if exact else (printed == k)
            beyond_ok = True
            note = ""
            if printed > k:
                # attribute: the creations that took the link count past k
                beyond = []
                made = 0
                for p, q in creations:
                    if q["state"] != "PERMITTED":
                        continue
                    lb = made          # links that existed before this creation: every earlier permitted one (nothing is deleted before the release)
                    made += 1
                    if lb + 1 > k:
                        beyond.append((p, lb))
                for p, lb in beyond:
                    stale = int(p["sip"]) + S <= A and lb * S + S > A
                    beyond_ok &= stale
                    note += " [%s links_before=%d pre.sip=%.2fS stale=%s]" % (p["seg"][-6:], lb, int(p["sip"]) / S, stale)
                check(label, "C4", beyond_ok and printed == k + 1, "L=%d=k+1; links beyond k:%s" % (printed, note))
            check(label, "C3", ok_k or (printed == k + 1 and beyond_ok), "L=%d k=%d exact_multiple=%s" % (printed, k, exact))
            # links made before the release: the release step makes one more link without a creation (permitSegmentMaybe flips
            # the forbidden segment and hard-links it, CommitLogSegmentManagerCDC.java:203-208), so count only the '+' events
            # before the first removal. (The first version of this check counted every link and failed for that reason.)
            first_removal = min((t for t, sg, n in events if sg == "-"), default=None)
            before_release = {n for t, sg, n in events if sg == "+" and (first_removal is None or t < first_removal)}
            check(label, "C6", len(permitted) == len(before_release), "permitted creations %d, links made before the release %d (links ever seen %d)" % (len(permitted), len(before_release), len(names_seen)))
            check(label, "C7", int(after["rejected"]) == 10 and int(after["links"]) == printed and nonCdc is True,
                  "rejected %s of 10, L after %s, non-CDC accepted %s" % (after["rejected"], after["links"], nonCdc))
            N = int(counter["N"])
            check(label, "C8", printed * S <= N <= printed * S + 64 * max(printed, 1), "N=%d, L*S=%d, N-L*S=%d" % (N, printed * S, N - printed * S))
            check(label, "C9", skipped if k == 0 else (release is not None and release["resumed"] == "true"),
                  "skipped (k=0)" if skipped else ("resumed after %s ms, %s rejected first" % (release["afterMs"], release["rejectedBefore"]) if release else "no release line"))
        else:
            check(label, "D1", not any("REJECTED" in l for l in open(os.path.join(d, "readings.txt"))), "no write rejected")
            mx = max(n for t, n in counts) if counts else -1
            check(label, "D2", 0 <= mx <= k + 1, "max per-tick L = %d, k + 1 = %d" % (mx, k + 1))
            removed = [n for t, s, n in sorted(events) if s == "-"]
            ids = [int(n.split("-")[2].split(".")[0]) for n in removed]
            check(label, "D3", ids == sorted(ids) and len(ids) > 0, "%d links removed, ascending: %s" % (len(ids), ids == sorted(ids)))
            check(label, "D4", int(nb["deletedLinks"]) == int(nb["distinctLinksSeen"]) - int(nb["finalLinks"]), "deleted %s = distinct %s - final %s" % (nb["deletedLinks"], nb["distinctLinksSeen"], nb["finalLinks"]))
            check(label, "D5", int(nbb["bytesRetained"]) < int(nbb["bytesWritten"]), "retained %s < written %s" % (nbb["bytesRetained"], nbb["bytesWritten"]))
    print("\n%d checks, %d FAIL" % (total, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
