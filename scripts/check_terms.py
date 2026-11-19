"""Fill 'kind', 'class_group' and 'in_owl' in terms/terms.csv from the ontology.

Usage: python scripts/check_terms.py ontology/languages.owl terms/terms.csv

Terms are matched ignoring case, spaces and underscores ("Word order type" = WordOrderType).
Ontology names missing from the CSV are added as new rows (definition left empty).
Only rows whose term is found get kind and class_group overwritten; your own entries for
terms not built yet stay as they are.
"""
import csv
import sys
from pathlib import Path

from owlready2 import get_ontology, onto_path

SKIP = {None, "Thing", "topObjectProperty", "topDataProperty", "ObjectProperty", "DataProperty", "DatatypeProperty",
        "FunctionalProperty", "TransitiveProperty"}


def norm(text):
    """Lower case, no spaces, underscores or slashes: 'class_group' == 'Class/Group'."""
    return "".join(ch for ch in text.lower() if ch not in " _/-")


def first_name(things):
    for t in things:
        name = getattr(t, "name", None)
        if name not in SKIP:
            return name
    return ""


owl_file, csv_file = Path(sys.argv[1]), Path(sys.argv[2])
onto_path.append(str(owl_file.resolve().parent))  # find core.owl next to it
onto = get_ontology(owl_file.resolve().as_uri()).load()

found = {}  # normalised name -> (kind, group, original name)
for o in [onto, *onto.imported_ontologies]:
    for c in o.classes():
        found[norm(c.name)] = ("defined class" if c.equivalent_to else "class", first_name(c.is_a), c.name)
    for p in o.object_properties():
        found[norm(p.name)] = ("role", first_name(p.is_a), p.name)
    for p in o.data_properties():
        found[norm(p.name)] = ("data role", first_name(p.is_a), p.name)
    for i in o.individuals():
        found[norm(i.name)] = ("individual", first_name(i.is_a), i.name)

with csv_file.open(newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    header = reader.fieldnames or []
    rows = list(reader)


def col(want):
    for h in header:
        if norm(h) == norm(want):
            return h
    sys.exit(f"Column '{want}' not found. The header is: {', '.join(header)}")


term_col, kind_col = col("term"), col("kind")
group_col, owl_col = col("class_group"), col("in_owl")

missing = []
for r in rows:
    key = norm(r[term_col].strip())
    if not key:
        continue
    if key in found:
        r[kind_col], group, _ = found[key]
        if group:
            r[group_col] = group
        r[owl_col] = "yes"
    else:
        r[owl_col] = "no"
        missing.append(r[term_col].strip())

# ontology names that are not in the CSV yet: add them as new rows
listed = {norm(r[term_col].strip()) for r in rows}
added = []
for key, (kind, group, name) in sorted(found.items(), key=lambda kv: (kv[1][0], kv[1][2])):
    if key not in listed and not name.startswith("Test"):
        row = {h: "" for h in header}
        row.update({term_col: name, kind_col: kind, group_col: group, owl_col: "yes"})
        rows.append(row)
        added.append(name)

with csv_file.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=header)
    w.writeheader()
    w.writerows(rows)

filled = sum(1 for r in rows if r[term_col].strip()) - len(added)
print(f"{filled - len(missing)} of {filled} terms found in the ontology.")
print("Not built yet:", ", ".join(missing) or "none")
print(f"Added {len(added)} ontology names that were missing from the CSV:", ", ".join(added) or "none")
