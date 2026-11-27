"""Coverage audit: python3 ledger_audit.py [results.json]  -> writes LEDGER.md, prints counts."""
import json, pathlib, re, sys
import ledger_data

HERE = pathlib.Path(__file__).parent
ids = {}
for f in sorted(HERE.glob("test_*.py")):
    for m in re.finditer(r'"""([^"]*?)"""', f.read_text(encoding="utf-8"), re.S):
        for i in re.findall(r"\bS[23]-[A-Z]{2,3}-\d+\b|\b(?:[A-Z]{1,3}\d?-[0-9A-Z]+|[A-Z]\d-[A-Z0-9]+)\b", m.group(1)):
            ids.setdefault(i, set()).add(f.name)
status = json.loads(pathlib.Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else {}
rows = ledger_data.ROWS
known = {r[0] for r in rows}
untested = [r[0] for r in rows if r[3].startswith("T") and r[0] not in ids]
stray = sorted(set(ids) - known - {"A4", "A1", "A2", "A3", "A5", "S2-", "S3-"})
out = ["# LEDGER (stage 3: stage-1 and stage-2 rows carried forward, then S3-* rows)", "", "Kinds: T acceptance test (`requirements/acceptance`), RUN run.sh measurement, "
       "R review inspection, M measurement. Status: open / passing / failing / ruled.", "",
       "| ID | § | Requirement (quoted) | Verification | Status |", "|---|---|---|---|---|"]
for i, sec, quote, kind in rows:
    where = ", ".join(sorted(ids.get(i, []))) if kind.startswith("T") else ""
    st = status.get(i, "open")
    out.append(f"| {i} | {sec} | {quote.replace('|', '\\|')} | {kind}{(' — ' + where) if where else ''} | {st} |")
(HERE.parent / "LEDGER.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"rows={len(rows)} untested={untested} stray_ids_in_tests={stray}")
