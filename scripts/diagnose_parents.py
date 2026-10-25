#!/usr/bin/python3
"""Find the persons of a Gramps tree that are the child of several families,
and say what the families look like, to tell a bug of the import from a
legitimate case (adoption, remarriage recorded twice...).

Standalone: reads a .gramps export (Gramps > Family Trees > Export > "Gramps
XML", compressed or not), needs no Gramps module and never writes anything.

Usage:
    python3 scripts/diagnose_parents.py my_tree.gramps
"""
import gzip
import sys
import xml.etree.ElementTree as ET


def local(tag):
    return tag.rsplit("}", 1)[-1]


def children_of(node, name):
    return [c for c in node if local(c.tag) == name]


def load(path):
    with open(path, "rb") as f:
        magic = f.read(2)
    opener = gzip.open if magic == b"\x1f\x8b" else open
    with opener(path, "rb") as f:
        root = ET.parse(f).getroot()
    people, families = {}, {}
    for node in root.iter():
        kind = local(node.tag)
        if kind == "person":
            name = ""
            for n in children_of(node, "name"):
                first = next((c.text for c in children_of(n, "first")), "") or ""
                surname = next((c.text for c in n.iter() if local(c.tag) == "surname"), "") or ""
                name = ("%s %s" % (first, surname)).strip()
                break
            urls = [u.get("href") for u in children_of(node, "url") if u.get("href")]
            people[node.get("handle")] = {
                "id": node.get("id"), "name": name or "(no name)", "urls": urls,
                "parent_families": [c.get("hlink") for c in children_of(node, "childof")]}
        elif kind == "family":
            def link(tag):
                found = children_of(node, tag)
                return found[0].get("hlink") if found else None
            families[node.get("handle")] = {
                "id": node.get("id"), "father": link("father"), "mother": link("mother"),
                "children": {c.get("hlink"): (c.get("frel", "Birth"), c.get("mrel", "Birth"))
                             for c in children_of(node, "childref")}}
    return people, families


def label(people, handle):
    if not handle:
        return "-"
    p = people.get(handle)
    return "%s %s" % (p["id"], p["name"]) if p else "?%s" % handle


def main(path):
    people, families = load(path)
    print("%d persons, %d families" % (len(people), len(families)))

    multi = {h: p for h, p in people.items() if len(set(p["parent_families"])) > 1}
    print("\n== Persons that are the child of several families: %d ==" % len(multi))
    for handle, p in sorted(multi.items(), key=lambda kv: kv[1]["id"]):
        print("\n%s %s" % (p["id"], p["name"]))
        for url in p["urls"]:
            print("   url: %s" % url)
        couples = []
        for fh in dict.fromkeys(p["parent_families"]):
            f = families.get(fh)
            if not f:
                print("   family ?%s (missing)" % fh)
                continue
            frel, mrel = f["children"].get(handle, ("not listed in the family", ""))
            print("   %s: father %s | mother %s | relation %s %s | %d children" % (
                f["id"], label(people, f["father"]), label(people, f["mother"]),
                frel, mrel, len(f["children"])))
            couples.append((f["father"], f["mother"]))
        # What it most probably is.
        known_f = {c[0] for c in couples if c[0]}
        known_m = {c[1] for c in couples if c[1]}
        if len(couples) != len(set(couples)):
            print("   -> same couple in two families: a duplicated family")
        elif any(c[0] is None or c[1] is None for c in couples) and (
                len(known_f) < sum(1 for c in couples if c[0]) or len(known_m) < sum(1 for c in couples if c[1])
                or (len(couples) > 1 and (len(known_f) == 1 or len(known_m) == 1))):
            print("   -> a family with one parent next to a family with the same parent:"
                  " likely the import")
        elif any(rel not in ("Birth", "") for f in (families.get(h) for h in p["parent_families"]) if f
                 for rel in f["children"].get(handle, ())):
            print("   -> a non-birth relation is recorded: possibly an adoption, on purpose")
        else:
            print("   -> different couples: two persons merged, or a wrong link in Geneanet")

    print("\n== Same Geneanet address on several persons ==")
    by_url = {}
    for h, p in people.items():
        for url in p["urls"]:
            by_url.setdefault(url, []).append(p)
    dup = {u: ps for u, ps in by_url.items() if len(ps) > 1}
    for url, ps in dup.items():
        print("%s: %s" % (url, ", ".join("%s %s" % (p["id"], p["name"]) for p in ps)))
    if not dup:
        print("none")

    print("\n== Families with the same couple ==")
    seen, any_dup = {}, False
    for h, f in families.items():
        key = (f["father"], f["mother"])
        if key == (None, None):
            continue
        if key in seen:
            any_dup = True
            print("%s and %s: %s / %s" % (seen[key]["id"], f["id"],
                                         label(people, f["father"]), label(people, f["mother"])))
        seen.setdefault(key, f)
    if not any_dup:
        print("none")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
