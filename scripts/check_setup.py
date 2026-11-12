"""Check that the project tools are installed. Run: python scripts/check_setup.py"""

import shutil
import sys


def check(label, fn):
    try:
        detail = fn()
        print(f"[ OK ] {label}" + (f" — {detail}" if detail else ""))
        return True
    except Exception as e:  # report any failure, keep checking the rest
        print(f"[FAIL] {label} — {e}")
        return False


def python_version():
    if sys.version_info < (3, 10):
        raise RuntimeError(f"need 3.10+, found {sys.version.split()[0]}")
    return sys.version.split()[0]


def clingo_solves():
    import clingo

    ctl = clingo.Control()
    ctl.add("base", [], "#defined abnormal/1. bird(tweety). flies(X) :- bird(X), not abnormal(X).")
    ctl.ground([("base", [])])
    atoms = []
    ctl.solve(on_model=lambda m: atoms.extend(str(a) for a in m.symbols(shown=True)))
    if "flies(tweety)" not in atoms:
        raise RuntimeError(f"unexpected model {atoms}")
    return f"clingo {clingo.__version__}, test inference OK"


def owlready_imports():
    import owlready2

    return f"owlready2 {owlready2.VERSION}"


def rdflib_imports():
    import rdflib

    return f"rdflib {rdflib.__version__}"


def java_on_path():
    path = shutil.which("java")
    if not path:
        raise RuntimeError("not found (only needed for reasoning from Python)")
    return path


results = [
    check("Python", python_version),
    check("clingo", clingo_solves),
    check("owlready2", owlready_imports),
    check("rdflib", rdflib_imports),
    check("Java", java_on_path),
]
print("\nAll good." if all(results) else "\nFix the FAIL lines above.")
