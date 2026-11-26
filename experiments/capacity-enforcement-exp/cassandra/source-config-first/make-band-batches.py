#!/usr/bin/env python3
"""Config-first source, step 2 input: banding batches for Cassandra (method: ../../source-config-first/README.md).

Takes the in-scope entries of config-coverage.csv in the given tiers, adds what a banding agent may use
(kind, default, the cassandra.yaml comment, tier, read sites), puts name-hinted entries first, splits them
into N batches and appends the same anchor entries (known band A) to every batch.

Usage (from the repository root):
    python3 .../make-band-batches.py OUTDIR [--tiers 3,4,5,6] [--batches 4]
"""
import argparse, csv, importlib.util, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, *[".."] * 4))
SRC = os.path.join(ROOT, "systems/cassandra/source")
CFG = os.path.join(SRC, "src/java/org/apache/cassandra/config")

# Anchors: tier-1 entries whose phase-1 cases are stage-4 true positives of a memory limit.
ANCHORS = ["memtable_heap_space", "key_cache_size", "native_transport_max_frame_size",
           "commitlog_segment_size", "MAX_HINT_BUFFERS"]


def lines(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def defaults():
    d = {}
    for l in lines(os.path.join(CFG, "Config.java")):
        m = re.match(r"^    public (?!static)(?:volatile )?(?:final )?([A-Za-z0-9_<>.,\[\] ?]+) ([a-z][a-z0-9_]*)( = (.*))?;", l)
        if m:
            d[m.group(2)] = f'{m.group(1).strip()} = {m.group(4).strip() if m.group(4) else "(unset)"}'
    for l in lines(os.path.join(CFG, "CassandraRelevantProperties.java")):
        m = re.match(r'^    ([A-Z][A-Z0-9_]+)\("([^"]+)"(?:,\s*(.*?))?\)[,;]', l)
        if m:
            d[m.group(1)] = f'-D{m.group(2)} default {m.group(3) or "(none)"}'
    return d


def yaml_comments():
    out, block = {}, []
    for l in lines(os.path.join(SRC, "conf/cassandra.yaml")):
        m = re.match(r"^#?\s?([a-z][a-z0-9_]*):(.*)$", l)
        if m and not l.startswith("#  "):
            key = m.group(1)
            text = " ".join(b.lstrip("# ").strip() for b in block if b.strip("# ").strip())
            out.setdefault(key, (text[-600:], m.group(2).strip()))
            block = []
        elif l.startswith("#"):
            block.append(l)
        else:
            block = []
    return out


def read_lines(entries):
    """Up to two source lines (file:line: text) that read each entry, found as coverage-diff.py finds reads;
    lines in DatabaseDescriptor/GuardrailsOptions (the getters themselves) are skipped."""
    spec = importlib.util.spec_from_file_location("cd", os.path.join(HERE, "coverage-diff.py"))
    cd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cd)
    getters = cd.yaml_getters()
    src = cd.java_files()
    out = {}
    for kind, name in entries:
        names = (sorted(getters.get(name, ())) + ["conf." + name, "config." + name]) if kind == "yaml" else [name]
        rx = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b")
        hits = []
        for skip in (("/Config.java", "/CassandraRelevantProperties.java", "/DatabaseDescriptor.java",
                      "/GuardrailsOptions.java"), ("/Config.java", "/CassandraRelevantProperties.java")):
            for path, whole, ls in src:
                if path.endswith(skip) or not any(n in whole for n in names):
                    continue
                for i, l in enumerate(ls, 1):
                    if rx.search(l) and not re.search(r"\bpublic static \S+ \w+\(", l):
                        hits.append(f"{os.path.basename(path)}:{i}: {l.strip()[:160]}")
                        if len(hits) >= 2:
                            break
                if len(hits) >= 2:
                    break
            if hits:
                break
        out[name] = " | ".join(hits)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--tiers", default="3,4,5,6")
    ap.add_argument("--batches", type=int, default=4)
    a = ap.parse_args()
    tiers = set(a.tiers.split(","))
    rows = list(csv.DictReader(open(os.path.join(HERE, "config-coverage.csv"))))
    dflt, yc = defaults(), yaml_comments()
    todo = [r for r in rows if r["scope"] == "in" and r["tier"][0] in tiers]
    reads = read_lines([(r["kind"], r["name"]) for r in rows if r in todo or r["name"] in ANCHORS])

    def item(r):
        c, yv = yc.get(r["name"], ("", ""))
        return {"kind": r["kind"], "name": r["name"], "default": dflt.get(r["name"], "?"),
                "yaml_value": yv, "yaml_comment": c, "tier": r["tier"], "read_sites": r["read_sites"], "read_lines": reads.get(r["name"], "")}

    todo.sort(key=lambda r: (r["name_hint"] != "yes", r["kind"], r["name"]))
    anchors = [item(r) for r in rows if r["name"] in ANCHORS]
    assert len(anchors) == len(ANCHORS), "anchor missing"
    os.makedirs(a.outdir, exist_ok=True)
    n = a.batches
    size = -(-len(todo) // n)
    for i in range(n):
        part = [item(r) for r in todo[i * size:(i + 1) * size]] + anchors
        p = os.path.join(a.outdir, f"config-batch-{i + 1:02d}.csv")
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(part[0]))
            w.writeheader()
            w.writerows(part)
        print(p, len(part) - len(anchors), "+", len(anchors), "anchors")


if __name__ == "__main__":
    main()
