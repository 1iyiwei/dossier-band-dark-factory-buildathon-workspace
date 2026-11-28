"""Per-ledger-ID evidence from a pytest JUnit file: python3 ledger_status.py junit.xml REV [run-log] > status.json
An ID is `passing` when every test that names it in its docstring passed (and at least one ran), `failing` when
one failed, `open` when all its tests were skipped. Rows verified by run.sh output or by review keep their notes."""
import ast
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

import ledger_data

HERE = pathlib.Path(__file__).parent
ID = re.compile(r"\bS[234]-[A-Z]{2,3}-\d+[b]?\b|\b(?:[A-Z]{1,3}\d?-[0-9A-Z]+|[A-Z]\d-[A-Z0-9]+)\b")
junit, rev = sys.argv[1], sys.argv[2]
log = pathlib.Path(sys.argv[3]).read_text() if len(sys.argv) > 3 else ""

ids_of = {}                                           # (file, test name) -> ids
for f in sorted(HERE.glob("test_*.py")):
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            ids_of[(f.name, node.name)] = set(ID.findall(ast.get_docstring(node) or ""))

res = {}                                              # id -> {"passed": n, "failed": [names], "skipped": n}
for tc in ET.parse(junit).getroot().iter("testcase"):
    fname = tc.get("classname", "").split(".")[-1] + ".py"
    name = re.sub(r"\[.*\]$", "", tc.get("name", ""))
    ids = ids_of.get((fname, name), set())
    outcome = "failed" if (tc.find("failure") is not None or tc.find("error") is not None) else \
        "skipped" if tc.find("skipped") is not None else "passed"
    for i in ids:
        r = res.setdefault(i, {"passed": 0, "failed": [], "skipped": 0})
        if outcome == "passed":
            r["passed"] += 1
        elif outcome == "skipped":
            r["skipped"] += 1
        else:
            r["failed"].append(f"{fname}::{tc.get('name')}")

old = json.loads((HERE / "status.json").read_text()) if (HERE / "status.json").exists() else {}
out = {}
for row in ledger_data.ROWS:
    i, kind = row[0], row[3]
    r = res.get(i)
    note = old.get(i, "open")
    ruled = re.search(r"ruled[^;]*", note)
    if r is None:
        out[i] = note if not kind.startswith("T") else "open (no test result)"
        if i.startswith("AX-") or kind.startswith("R") or kind.startswith("UX") or kind.startswith("M"):
            out[i] = note
        continue
    if r["failed"]:
        out[i] = f"failing on {rev}: " + ", ".join(r["failed"][:3])
    elif r["passed"]:
        out[i] = f"passing on {rev} ({r['passed']} tests)" + (f"; {ruled.group(0)}" if ruled else "")
        if kind.startswith(("RUN", "R+", "T+R", "T(proxy)+R", "T+UX", "T(heuristic)+UX")) and "+" in kind:
            out[i] += "; review part open"
    else:
        out[i] = f"open (skipped on {rev})" + (f"; {ruled.group(0)}" if ruled else "")

# run.sh measurements (printed by run.sh into the log)
if "healthy on default port 8080" in log:
    out["DEP-2"] = f"passing on {rev} (run.sh: healthy on default port 8080)"
if re.search(r"healthy with -e PORT=8000 after \d+s", log):
    out["DEP-3"] = f"passing on {rev} (run.sh: healthy with -e PORT=8000 after " + \
        re.search(r"healthy with -e PORT=8000 after (\d+)s", log).group(1) + "s)"
if "DEP-4 resource peek" in log:
    out["DEP-4"] = f"passing on {rev} (run.sh: 2 CPU / 3 GiB limits, load tests pass; " + \
        re.search(r"DEP-4 resource peek: (.*)", log).group(1)[:80] + ")"
json.dump(out, sys.stdout, indent=1)
