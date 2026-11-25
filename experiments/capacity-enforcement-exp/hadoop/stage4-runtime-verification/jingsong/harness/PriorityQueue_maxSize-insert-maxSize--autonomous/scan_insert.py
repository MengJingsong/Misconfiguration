#!/usr/bin/env python3
"""Stage-4 harness, order 9 (PriorityQueue_maxSize-insert-maxSize--autonomous), amendment A3.

Static scan for call sites of org.apache.hadoop.util.PriorityQueue.insert (or the same method named through a
subclass). Usage: scan_insert.py <dir-or-jar> [...]

Pass 1 reads every .class (in directories, in jars, and in jars nested one level inside jars) and records its
superclass; the transitive subclasses of org/apache/hadoop/util/PriorityQueue are computed.
Pass 2 reports every class whose constant pool holds a Methodref/InterfaceMethodref to
<PriorityQueue or subclass>.insert:(Ljava/lang/Object;)Z  (a constant-pool entry is the superset of every
invoke instruction and method reference, so no HIT means no call site).
Output: SUBCLASS lines, HIT lines, and a SUMMARY line.
"""
import io
import os
import struct
import sys
import zipfile

PQ = "org/apache/hadoop/util/PriorityQueue"


def parse(data):
    """Return (this_class, super_class, [(class, name, desc) of method refs]) or None."""
    if data[:4] != b"\xca\xfe\xba\xbe":
        return None
    n = struct.unpack(">H", data[8:10])[0]
    cp = [None] * n
    i, p = 1, 10
    while i < n:
        tag = data[p]
        if tag == 1:
            ln = struct.unpack(">H", data[p + 1:p + 3])[0]
            cp[i] = ("utf8", data[p + 3:p + 3 + ln].decode("utf-8", "replace"))
            p += 3 + ln
        elif tag in (3, 4):
            p += 5
        elif tag in (5, 6):
            p += 9
            i += 1
        elif tag in (7, 8, 16, 19, 20):
            cp[i] = ("ref1", tag, struct.unpack(">H", data[p + 1:p + 3])[0])
            p += 3
        elif tag in (9, 10, 11, 12, 17, 18):
            a, b = struct.unpack(">HH", data[p + 1:p + 5])
            cp[i] = ("ref2", tag, a, b)
            p += 5
        elif tag == 15:
            p += 4
        else:
            raise ValueError("bad constant tag %d" % tag)
        i += 1

    def utf(k):
        return cp[k][1]

    def cls(k):
        return utf(cp[k][2])

    this_c, super_c = struct.unpack(">HH", data[p + 2:p + 6])
    sup = cls(super_c) if super_c else None
    refs = []
    for e in cp:
        if e and e[0] == "ref2" and e[1] in (10, 11):
            nat = cp[e[3]]
            refs.append((cls(e[2]), utf(nat[2]), utf(nat[3])))
    return cls(this_c), sup, refs


def classes(path):
    """Yield (location, bytes) for every class file under path."""
    def from_zip(zf, loc):
        for name in zf.namelist():
            if name.endswith(".class"):
                yield "%s!%s" % (loc, name), zf.read(name)
            elif name.endswith(".jar"):
                try:
                    inner = zipfile.ZipFile(io.BytesIO(zf.read(name)))
                except Exception:
                    continue
                for x in from_zip(inner, "%s!%s" % (loc, name)):
                    yield x

    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for f in sorted(files):
                fp = os.path.join(root, f)
                if f.endswith(".class"):
                    with open(fp, "rb") as fh:
                        yield fp, fh.read()
                elif f.endswith(".jar"):
                    try:
                        with zipfile.ZipFile(fp) as zf:
                            for x in from_zip(zf, fp):
                                yield x
                    except zipfile.BadZipFile:
                        print("WARN bad jar", fp)
    elif path.endswith(".jar"):
        with zipfile.ZipFile(path) as zf:
            for x in from_zip(zf, path):
                yield x


def main(paths):
    supers = {}
    parsed = []
    nclass = 0
    for p in paths:
        for loc, data in classes(p):
            nclass += 1
            try:
                r = parse(data)
            except Exception as e:
                print("WARN unparsable", loc, e)
                continue
            if r is None:
                continue
            supers.setdefault(r[0], set()).add(r[1])
            parsed.append((loc, r))
    subs = {PQ}
    changed = True
    while changed:
        changed = False
        for c, ss in supers.items():
            if c not in subs and ss & subs:
                subs.add(c)
                changed = True
    for c in sorted(subs - {PQ}):
        print("SUBCLASS", c)
    hits = 0
    for loc, (c, _, refs) in parsed:
        for owner, name, desc in refs:
            if owner in subs and name == "insert" and desc == "(Ljava/lang/Object;)Z":
                print("HIT", c, "->", owner + ".insert" + desc, "in", loc)
                hits += 1
    print("SUMMARY classes=%d pqClassesSeen=%d subclasses=%d hits=%d" % (
        nclass, len([1 for loc, r in parsed if r[0] == PQ]), len(subs) - 1, hits))


if __name__ == "__main__":
    main(sys.argv[1:])
