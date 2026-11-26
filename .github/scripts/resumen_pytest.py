"""Writes a pytest and coverage summary to the GitHub job summary page ($GITHUB_STEP_SUMMARY).

Inputs: pytest's JUnit XML (--junitxml) and coverage.py's JSON report (--cov-report=json:...).
A missing file is reported, never fatal: this step runs after the tests even when they fail.
Usage: python resumen_pytest.py "<title>" <junit.xml> <coverage.json>
"""

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

titulo, junit, cobertura = sys.argv[1:4]
out = [f"### {titulo}", ""]

if Path(junit).exists():
    raiz = ET.parse(junit).getroot()
    suite = raiz if raiz.tag == "testsuite" else raiz.find("testsuite")
    a = suite.attrib if suite is not None else {}
    total, fallos = int(a.get("tests", 0)), int(a.get("failures", 0)) + int(a.get("errors", 0))
    omitidas = int(a.get("skipped", 0))
    ok = "✅ passed" if fallos == 0 else "❌ failed"
    pasadas, tiempo = total - fallos - omitidas, float(a.get("time", 0))
    out += [
        "| Result | Tests | Passed | Failed | Skipped | Time |",
        "|---|---|---|---|---|---|",
        f"| {ok} | {total} | {pasadas} | {fallos} | {omitidas} | {tiempo:.1f} s |",
        "",
    ]
    fallidas = [
        f"- `{c.get('classname', '')}` · {c.get('name', '')}"
        for c in raiz.iter("testcase")
        if c.find("failure") is not None or c.find("error") is not None
    ]
    if fallidas:
        out += ["**Failed tests**", "", *fallidas[:30], ""]
else:
    out += ["No test report (the tests did not run).", ""]

if Path(cobertura).exists():
    t = json.loads(Path(cobertura).read_text())["totals"]
    ramas = (
        f"{100 * t['covered_branches'] / t['num_branches']:.1f} %" if t.get("num_branches") else "—"
    )
    out += [
        "| Coverage | Lines | Branches |",
        "|---|---|---|",
        f"| gate: 70 | {t['percent_covered']:.1f} % | {ramas} |",
        "",
    ]

texto = "\n".join(out) + "\n"
destino = os.environ.get("GITHUB_STEP_SUMMARY")
if destino:
    with open(destino, "a", encoding="utf-8") as f:
        f.write(texto)
else:
    sys.stdout.write(texto)
