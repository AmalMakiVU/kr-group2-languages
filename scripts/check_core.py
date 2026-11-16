"""Check the core ontology with HermiT.

Usage (from any folder):
    python scripts/check_core.py                    # checks ontology/core.owl
    python scripts/check_core.py path/to/file.owl   # checks another file
    python scripts/check_core.py --selftest         # checks that this script gives the right verdicts

Save your work in Protégé first: the script reads the file on disk.

Checks
    1  consistent: HermiT finds no contradiction and no unsatisfiable class
    2  disjointness: an individual typed Language AND LanguageFamily must make the KB inconsistent
    3  inference: Dutch memberOfFamily WestGermanic, WestGermanic subgroupOf Germanic
       -> HermiT must infer Dutch is a Language and Dutch memberOfFamily Germanic

Exit code 0 = all checks pass, 1 = a check failed or the file could not be checked.
Checks 2 and 3 add test individuals in memory only; the file on disk is never changed.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent  # works from any folder (C5: wrong folder)
DEFAULT_OWL = REPO / "ontology" / "core.owl"


class CheckError(Exception):
    """A problem that stops checking (missing file, missing Java, missing class...)."""


# ---------- preflight: laptop and file problems (C5) ----------

def preflight(path: Path):
    # macOS ships a /usr/bin/java stub even without Java, so run it rather than only look for it
    java_hint = "HermiT needs Java. macOS: brew install openjdk (see README)"
    if shutil.which("java") is None:
        raise CheckError(f"Java not found. {java_hint}")
    try:
        subprocess.run(["java", "-version"], capture_output=True, check=True, timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        raise CheckError(f"Java is not installed (only the macOS placeholder was found). {java_hint}")
    try:
        import owlready2  # noqa: F401
    except ImportError:
        raise CheckError("owlready2 not installed. Activate the venv, then: pip install -r requirements.txt")
    if not path.exists():
        raise CheckError(f"file not found: {path}")
    if path.suffix != ".owl":
        raise CheckError(f"expected a .owl file, got: {path.name}")
    if path.stat().st_size == 0:
        raise CheckError(f"file is empty: {path}")


def load(path: Path):
    """Load the file into a fresh World, so each check starts clean."""
    import owlready2 as owl

    if str(path.parent) not in owl.onto_path:  # resolve owl:imports (e.g. core) from the same folder
        owl.onto_path.append(str(path.parent))
    world = owl.World()
    try:
        onto = world.get_ontology(path.as_uri()).load()
    except Exception as e:  # corrupted / not RDF/XML
        raise CheckError(f"could not read {path.name} (corrupted or wrong format?): {e}")
    return world, onto


def find(world, name: str):
    """Look up a class or property by its short name; clear error if it was renamed (C5)."""
    entity = world.search_one(iri=f"*#{name}") or world.search_one(iri=f"*/{name}")
    if entity is None:
        raise CheckError(f"'{name}' not found in the ontology (renamed or deleted?)")
    return entity


def reason(world):
    import owlready2 as owl

    try:
        owl.sync_reasoner_hermit(world, infer_property_values=True, debug=0)
    except owl.OwlReadyJavaError as e:  # any other Java/HermiT crash: short message, no traceback
        raise CheckError(f"HermiT could not run: {str(e).strip().splitlines()[-1]}")


# ---------- the three checks: each returns (passed, message) ----------

def check_consistent(path: Path):
    import owlready2 as owl

    world, _ = load(path)
    try:
        reason(world)
    except owl.OwlReadyInconsistentOntologyError:
        return False, "ontology is inconsistent"
    empty = [c.name for c in world.inconsistent_classes() if c is not owl.Nothing]
    if empty:
        return False, "unsatisfiable classes: " + ", ".join(empty)
    return True, "consistent, no unsatisfiable classes"


def check_disjoint(path: Path):
    import owlready2 as owl

    world, onto = load(path)
    language, family = find(world, "Language"), find(world, "LanguageFamily")
    with onto:
        bad = language("TestGermanic")
        bad.is_a.append(family)
    try:
        reason(world)
    except owl.OwlReadyInconsistentOntologyError:
        return True, "Language + LanguageFamily on one individual is caught"
    return False, "an individual can be both Language and LanguageFamily (disjointness missing?)"


def check_inference(path: Path):
    world, onto = load(path)
    language = find(world, "Language")
    belongs, subgroup = find(world, "memberOfFamily"), find(world, "subgroupOf")
    with onto:
        thing = onto.world["http://www.w3.org/2002/07/owl#Thing"]
        dutch, west, germanic = thing("TestDutch"), thing("TestWestGermanic"), thing("TestGermanic")
        dutch.__setattr__(belongs.python_name, [west])
        west.__setattr__(subgroup.python_name, [germanic])
    reason(world)
    missing = []
    if language not in dutch.is_a:
        missing.append("Dutch is a Language (domain of memberOfFamily)")
    if germanic not in getattr(dutch, belongs.python_name):
        missing.append("Dutch memberOfFamily Germanic (property chain)")
    if missing:
        return False, "not inferred: " + "; ".join(missing)
    return True, "Dutch inferred as Language and as memberOfFamily Germanic"


def check_genealogy(path: Path):
    """languages.owl only: French -> Latin -> ProtoIndoEuropean must make both IndoEuropeanLanguage."""
    world, onto = load(path)
    if world.search_one(iri="*#IndoEuropeanLanguage") is None:
        return True, "skipped (no IndoEuropeanLanguage in this file; run it on languages.owl)"
    ie, parent = find(world, "IndoEuropeanLanguage"), find(world, "hasParentLanguage")
    pie = find(world, "ProtoIndoEuropean")
    with onto:
        thing = onto.world["http://www.w3.org/2002/07/owl#Thing"]
        french, latin = thing("TestFrench"), thing("TestLatin")
        french.__setattr__(parent.python_name, [latin])
        latin.__setattr__(parent.python_name, [pie])
    reason(world)
    missing = [name for name, ind in (("French", french), ("Latin", latin)) if ie not in ind.is_a]
    if missing:
        return False, "not inferred as IndoEuropeanLanguage: " + ", ".join(missing) + " (transitivity, hierarchy or nominal?)"
    return True, "French and Latin inferred as IndoEuropeanLanguage (two steps up to the nominal)"


CHECKS = [
    ("1 consistent", check_consistent),
    ("2 disjointness catches error", check_disjoint),
    ("3 domain + property chain inference", check_inference),
    ("4 genealogy + nominal inference", check_genealogy),
]


def run_checks(path: Path, quiet=False) -> dict:
    """Run all checks; return {check label: True/False}. Raises CheckError if it cannot check."""
    preflight(path)
    results = {}
    for label, fn in CHECKS:
        passed, msg = fn(path)
        results[label] = passed
        if not quiet:
            print(f"[{'PASS' if passed else 'FAIL'}] {label} - {msg}")
    return results


# ---------- self-test: inputs with a known right verdict (C6) ----------

def broken_copy(path: Path, what: str, folder: Path) -> Path:
    """Save a copy of the ontology with the disjointness or the property chain removed."""
    from rdflib import Graph
    from rdflib.namespace import OWL, RDF

    g = Graph()
    g.parse(path, format="xml")
    if what == "no-disjoint":
        g.remove((None, OWL.disjointWith, None))           # pairwise style
        for node in list(g.subjects(RDF.type, OWL.AllDisjointClasses)):  # one axiom, many classes
            g.remove((node, None, None))
    elif what == "no-chain":
        g.remove((None, OWL.propertyChainAxiom, None))
    out = folder / f"core-{what}.owl"
    g.serialize(out, format="xml")
    return out


def selftest(path: Path) -> bool:
    print(f"Self-test on {path}\n")
    ok = True

    def expect(name, got, want):
        nonlocal ok
        good = got == want
        ok &= good
        print(f"[{'PASS' if good else 'FAIL'}] {name}: expected {want}, got {got}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        all_pass = {label: True for label, _ in CHECKS}

        good = run_checks(path, quiet=True)
        if good != all_pass:  # the self-test needs a known-good starting file
            failed = ", ".join(label for label, passed in good.items() if not passed)
            print(f"[STOP] {path.name} itself fails: {failed}.\n"
                  "Fix the ontology first (run without --selftest to see why); "
                  "the self-test needs a file that passes all checks.")
            return False

        no_dis = run_checks(broken_copy(path, "no-disjoint", tmp), quiet=True)
        expect("no disjointness -> check 2 fails", no_dis["2 disjointness catches error"], False)

        no_chain = run_checks(broken_copy(path, "no-chain", tmp), quiet=True)
        expect("no property chain -> check 3 fails",
               no_chain["3 domain + property chain inference"], False)

        try:
            run_checks(tmp / "does-not-exist.owl", quiet=True)
            expect("missing file -> 'file not found'", "no error", "file not found")
        except CheckError as e:
            expect("missing file -> 'file not found'",
                   "file not found" if "file not found" in str(e) else str(e), "file not found")

    print("\nScript gives the right verdicts." if ok else "\nThe script itself has a bug.")
    return ok


def main(argv) -> int:
    args = [a for a in argv if not a.startswith("--")]
    path = Path(args[0]).resolve() if args else DEFAULT_OWL
    try:
        if "--selftest" in argv:
            return 0 if selftest(path) else 1
        print(f"Checking {path}\n")
        results = run_checks(path)
    except CheckError as e:
        print(f"[ERROR] {e}")
        return 1
    passed = all(results.values())
    print("\nAll checks pass." if passed else "\nSome checks failed - see FAIL lines above.")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
