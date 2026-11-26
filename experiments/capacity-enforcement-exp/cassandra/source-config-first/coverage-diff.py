#!/usr/bin/env python3
"""Config-first source, step 1: coverage diff for Cassandra 5.0.9 (no agents).

Lists every configuration entry (Config.java fields = cassandra.yaml entries, and
CassandraRelevantProperties = JVM system properties) and records how far phase 1
(and phase 2) already reach it. Method: ../../source-config-first/README.md.

Usage (from the repository root):
    python3 experiments/capacity-enforcement-exp/cassandra/source-config-first/coverage-diff.py
Writes config-coverage.csv next to this script and prints the tier counts.
"""
import csv, glob, os, re, sys, collections

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 4))
SRC = os.path.join(ROOT, "systems/cassandra/source")
CFG = os.path.join(SRC, "src/java/org/apache/cassandra/config")
P1 = os.path.join(ROOT, "experiments/capacity-enforcement-exp/cassandra")
P2 = os.path.join(ROOT, "experiments/OOM-exp/cassandra")
CQL = os.path.join(ROOT, "codeql-queries/results/cassandra")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config-coverage.csv")
NEAR = 30  # lines: a stage-1 unit this close to a read of the entry counts as "nearby"

# Name hint for memory relevance (a prefilter only; banding decides).
HINT = re.compile(r"(size|capacity|max|limit|threshold|buffer|cache|queue|concurren|thread|pool|writer|worker|"
                  r"growth|factor|ratio|expir|retention|parallel|throughput|"
                  r"memory|heap|space|bytes|_mb|_kb|mib|kib|count|entries|batch|page|frame|"
                  r"window|in_flight|inflight|outstanding|pending|slab|chunk|interval)", re.I)


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def config_entries():
    out = []
    pat = re.compile(r"^    public (?!static)(?:volatile )?(?:final )?[A-Za-z0-9_<>.,\[\] ?]+ ([a-z][a-z0-9_]*)( =.*)?;")
    for i, line in enumerate(read(os.path.join(CFG, "Config.java")).splitlines(), 1):
        m = pat.match(line)
        if m:
            out.append(dict(kind="yaml", name=m.group(1), prop="", decl=f"Config.java:{i}"))
    pat = re.compile(r'^    ([A-Z][A-Z0-9_]+)\("([^"]+)"')
    for i, line in enumerate(read(os.path.join(CFG, "CassandraRelevantProperties.java")).splitlines(), 1):
        m = pat.match(line)
        if m:
            out.append(dict(kind="jvm", name=m.group(1), prop=m.group(2), decl=f"CassandraRelevantProperties.java:{i}"))
    return out


def yaml_getters():
    """Methods of DatabaseDescriptor and GuardrailsOptions that read conf.<field> / config.<field>:
    field -> {method names}."""
    g = collections.defaultdict(set)
    # any method declaration resets the current method; only public getter-like methods are kept
    meth = re.compile(r"^    (public |private |protected |static |final |synchronized |abstract )+[^=;(]*? (\w+)\(")
    for fname in ("DatabaseDescriptor.java", "GuardrailsOptions.java"):
        cur = None
        for line in read(os.path.join(CFG, fname)).splitlines():
            m = meth.match(line)
            if m:
                name = m.group(2)
                cur = name if (line.lstrip().startswith("public") and len(name) > 6
                               and not name.startswith(("set", "apply", "create", "validate", "load"))) else None
            if cur:
                for f in re.findall(r"\b(?:conf|config)\.([a-z][a-z0-9_]*)", line):
                    g[f].add(cur)
    return g


# JVM properties that only serve tests, the JDK, logging or JMX: out of scope for memory constraints.
OUT_OF_SCOPE = re.compile(r"^(TEST_|DTEST_|SIMULATOR_|JAVA_|JAVAX_|SUN_|COM_SUN_|JDK_|LOG4J|LOGBACK|"
                          r"MX4J|ORG_APACHE_CASSANDRA_DISABLE_MBEAN|CASSANDRA_JMX|NODETOOL_|GIT_SHA|CASSANDRA_VERSION)")


def java_files():
    out = []
    for p in glob.glob(os.path.join(SRC, "src/java/**/*.java"), recursive=True):
        t = read(p)
        out.append((os.path.relpath(p, SRC), t, t.splitlines()))
    return out


def units():
    """(path -> [(line, uid-ish text)]) for every stage-1 row, and the band of each uid."""
    bands = {}
    with open(os.path.join(P1, "stage2-ai-preprocessing/bands.csv")) as f:
        for r in csv.DictReader(f):
            bands[r["uid"].split("#")[0]] = min(bands.get(r["uid"].split("#")[0], "Z"), r["band"])
    rows = collections.defaultdict(list)
    for p in glob.glob(os.path.join(CQL, "*.csv")):
        with open(p) as f:
            for r in csv.DictReader(f):
                text = " ".join(v for k, v in r.items() if k not in ("path", "pkg", "declaringType"))
                rows[r["path"]].append((int(r["line"]), text, bands.get(f'{r["path"]}:{r["line"]}', "?")))
    return rows


def a1(text):
    m = re.search(r"\*\*A1\..*?(?=\*\*A2\.|\n## )", text, re.S)
    return m.group(0) if m else text[:3000]


def main():
    if not os.path.isdir(SRC):
        sys.exit(f"no Cassandra source at {SRC}")
    entries = config_entries()
    getters = yaml_getters()
    cases = {os.path.basename(p)[:-3]: read(p) for p in glob.glob(os.path.join(P1, "stage3-ai-deep-read/cases/*.md"))}
    p2 = {p: read(p) for p in glob.glob(os.path.join(P2, "cases/**/*.md"), recursive=True)}
    p2 = {p: t for p, t in p2.items() if not p.endswith("_INDEX.md")}
    unit_rows = units()
    src = java_files()
    a1s = {s: a1(t) for s, t in cases.items()}

    out = []
    for e in entries:
        keys = [e["name"]] + ([e["prop"]] if e["prop"] else [])
        wre = re.compile(r"(?<![A-Za-z0-9_.])(" + "|".join(re.escape(k) for k in keys) + r")(?![A-Za-z0-9_])")
        # how the entry is read in the source
        if e["kind"] == "yaml":
            names = sorted(getters.get(e["name"], ())) + ["conf." + e["name"], "config." + e["name"]]
            reader = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b")
        else:
            names = [e["name"]]
            reader = re.compile(r"\b" + re.escape(e["name"]) + r"\b")
        # tiers
        constraint_in = sorted(s for s, t in cases.items()
                               if s.split("-")[0] in keys or (any(k in a1s[s] for k in keys) and wre.search(a1s[s])))
        mentioned_in = sorted(s for s, t in cases.items()
                              if s not in constraint_in and any(k in t for k in keys) and wre.search(t))
        p2_in = sorted(os.path.relpath(p, P2) for p, t in p2.items() if any(k in t for k in keys) and wre.search(t))
        text_units, near_units, read_sites = [], [], 0
        for path, whole, lines in src:
            if path.endswith(("Config.java", "CassandraRelevantProperties.java")):
                hits = []
            elif any(n in whole for n in names):
                hits = [i for i, l in enumerate(lines, 1) if reader.search(l)]
            else:
                hits = []
            read_sites += len(hits)
            if not hits and not any(k in whole for k in keys):
                continue
            for (ln, text, band) in unit_rows.get(path, ()):
                if wre.search(text) or reader.search(text):
                    text_units.append((path, ln, band))
                elif any(abs(ln - h) <= NEAR for h in hits):
                    near_units.append((path, ln, band))
        if constraint_in:
            tier = "1-case-constraint"
        elif mentioned_in or p2_in:
            tier = "2-case-mentioned"
        elif text_units:
            tier = "3-unit-reads-it"
        elif near_units:
            tier = "4-unit-nearby"
        elif read_sites == 0:
            tier = "6-not-read"
        else:
            tier = "5-no-unit"
        best = min([b for *_, b in text_units + near_units] or ["-"])
        out.append(dict(
            kind=e["kind"], name=e["name"], property=e["prop"], declared=e["decl"],
            scope="out" if e["kind"] == "jvm" and OUT_OF_SCOPE.match(e["name"]) else "in",
            name_hint="yes" if HINT.search(e["name"] + " " + e["prop"]) else "no",
            tier=tier, read_sites=read_sites,
            case_constraint=len(constraint_in), case_mentioned=len(mentioned_in), phase2_files=len(p2_in),
            units_reading=len(text_units), units_nearby=len(near_units), best_unit_band=best,
            example=(constraint_in or mentioned_in or p2_in or [f"{p}:{l}" for p, l, _ in (text_units + near_units)[:1]] or [""])[0],
        ))
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print("out of scope (test/JDK/logging/JMX JVM properties):", sum(r["scope"] == "out" for r in out))
    out_in = [r for r in out if r["scope"] == "in"]
    c = collections.Counter((r["kind"], r["tier"], r["name_hint"]) for r in out_in)
    for kind in ("yaml", "jvm"):
        print(kind, "in scope", sum(v for (k, *_), v in c.items() if k == kind))
        for tier in sorted({t for (_, t, _) in c}):
            print(f"  {tier:20s} hint yes {c[(kind, tier, 'yes')]:4d}  no {c[(kind, tier, 'no')]:4d}")
    print("wrote", os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    main()
