#!/usr/bin/env python3
"""Real-resource sampler for the cdc_total_space case (case §9d, "Real resource").

usage: cdc-sampler.py <cdc_raw directory> <output prefix> [interval seconds, default 0.05]

Lists the directory every interval and writes

  <prefix>.csv      one row per tick:
                    ms,links,link_bytes,link_alloc_bytes,idx_files,idx_bytes,other_files,gap_ms
                      links            files named CommitLog-<version>-<id>.log (hard links to commit-log segments)
                      link_bytes       their apparent size (st_size), the quantity the check's counter tracks
                      link_alloc_bytes their allocated size (st_blocks * 512), lower while a segment is sparse
                      idx_files/bytes  the CommitLog-..._cdc.idx index files
                      gap_ms           time since the previous tick (a gap over 1000 ms makes the run invalid, case 9a)
  <prefix>.events   one line whenever a file appears (+) or disappears (-): ms,+|-,name,size
  <prefix>.summary  written at exit: ticks, max links, max link bytes, max gap, first and last ms

Stops on SIGTERM or SIGINT. Observation only: it never touches the directory's contents.
"""
import os
import re
import signal
import sys
import time

LINK = re.compile(r"^CommitLog-\d+-\d+\.log$")
IDX = re.compile(r"^CommitLog-\d+-\d+_cdc\.idx$")

stop = False


def on_signal(signum, frame):
    global stop
    stop = True


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    directory, prefix = sys.argv[1], sys.argv[2]
    interval = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    known = {}                      # name -> size, files seen at the previous tick
    ticks = 0
    max_links = max_link_bytes = max_gap = 0
    first_ms = last_ms = None
    with open(prefix + ".csv", "w", buffering=1) as csv, open(prefix + ".events", "w", buffering=1) as events:
        csv.write("ms,links,link_bytes,link_alloc_bytes,idx_files,idx_bytes,other_files,gap_ms\n")
        prev_ms = None
        next_tick = time.monotonic()
        while not stop:
            ms = int(time.time() * 1000)
            now = {}
            links = link_bytes = link_alloc = idx_files = idx_bytes = other = 0
            try:
                with os.scandir(directory) as it:
                    for entry in it:
                        try:
                            st = entry.stat(follow_symlinks=False)
                        except FileNotFoundError:
                            continue            # deleted between the listing and the stat
                        name = entry.name
                        now[name] = st.st_size
                        if LINK.match(name):
                            links += 1
                            link_bytes += st.st_size
                            link_alloc += st.st_blocks * 512
                        elif IDX.match(name):
                            idx_files += 1
                            idx_bytes += st.st_size
                        else:
                            other += 1
            except FileNotFoundError:
                pass                            # the directory does not exist yet: zero files
            for name in sorted(set(now) - set(known)):
                events.write("%d,+,%s,%d\n" % (ms, name, now[name]))
            for name in sorted(set(known) - set(now)):
                events.write("%d,-,%s,%d\n" % (ms, name, known[name]))
            known = now
            gap = 0 if prev_ms is None else ms - prev_ms
            prev_ms = ms
            csv.write("%d,%d,%d,%d,%d,%d,%d,%d\n" % (ms, links, link_bytes, link_alloc, idx_files, idx_bytes, other, gap))
            ticks += 1
            max_links = max(max_links, links)
            max_link_bytes = max(max_link_bytes, link_bytes)
            max_gap = max(max_gap, gap)
            first_ms = first_ms or ms
            last_ms = ms
            next_tick += interval
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.monotonic()    # fell behind: do not burst to catch up
    with open(prefix + ".summary", "w") as out:
        out.write("ticks=%d max_links=%d max_link_bytes=%d max_gap_ms=%d first_ms=%s last_ms=%s\n"
                  % (ticks, max_links, max_link_bytes, max_gap, first_ms, last_ms))


if __name__ == "__main__":
    main()
