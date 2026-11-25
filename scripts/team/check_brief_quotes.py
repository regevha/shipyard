#!/usr/bin/env python3
"""T013 acceptance: every brief quote in docs/OPEN_QUESTIONS.md is word for word in docs/BRIEF.md.

Checks (run from the repo root; exit 0 = pass, 1 = fail):
1. Every double-quoted passage (12+ characters) in a "**Brief (verbatim)...:**" bullet or after "the user brief:"
   appears in the verbatim block of docs/BRIEF.md (whitespace normalised; "..." splits a quote into parts that
   must each appear). Quotes of section names (preceded by "§ ") and of the lead's own earlier wording
   (preceded by "said "), and parenthesised names after a section name, are skipped.
2. Every "Status:** `resolved-by-user-brief`" line says "quoted above", i.e. its entry carries a verbatim quote.
"""
import re
import sys


def norm(s: str) -> str:
    return " ".join(s.split())


def main() -> int:
    brief = norm(open("docs/BRIEF.md", encoding="utf-8").read().split("```text", 1)[1].split("```", 1)[0])
    oq = open("docs/OPEN_QUESTIONS.md", encoding="utf-8").read()
    blocks = re.findall(r"(?:Brief \(verbatim\)[^:]*:\*\*|the user brief:)(.*?)(?=\n- \*\*|\n### |\Z)", oq, re.S)
    quotes = []
    for block in blocks:
        for m in re.finditer(r'"([^"]{12,})"', block):
            before = block[max(0, m.start() - 8):m.start()]
            if re.search(r"(§ |said |§ \"[^\"]*\" \()$", before) or before.endswith("("):
                continue
            quotes.append(norm(m.group(1)))
    bad = [q for q in quotes if not all(norm(p) in brief for p in q.split("...") if p.strip())]
    unquoted = [line for line in oq.splitlines()
                if "Status:** `resolved-by-user-brief`" in line and "quoted above" not in line]
    print(f"{len(quotes)} brief quotes checked")
    for q in bad:
        print(f"NOT IN docs/BRIEF.md: {q}")
    for line in unquoted:
        print(f"resolved-by-user-brief without a quote: {line.strip()}")
    return 1 if bad or unquoted or not quotes else 0


if __name__ == "__main__":
    sys.exit(main())
