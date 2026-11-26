#!/usr/bin/env python3
"""T013 acceptance: what the repo attributes to the user's brief is word for word in docs/BRIEF.md.

Rules (checked in docs/OPEN_QUESTIONS.md and docs/PLAN.md; inline code spans and fenced blocks are ignored):
1. Every double-quoted passage of 12+ characters must appear in the verbatim block of docs/BRIEF.md (the
   ```text fence), whitespace-normalised ("..." inside a quote splits it into parts that must each appear),
   unless it is one of these, which are not the brief's words:
   - a section name: right after "§ ", or in parentheses right after a quoted section name;
   - explicitly labelled as not the brief: followed within 80 characters by "paraphrase", "not the brief" or
     "lead's wording";
   - listed in OTHER_SOURCES below (quotes from other files or tools, or plan terms), each with its source.
   So a new quote either matches the brief word for word or is knowingly declared as something else.
2. Every "### Q-nn" entry of docs/OPEN_QUESTIONS.md whose Status line is `resolved-by-user-brief` must contain a
   "**Brief (verbatim)" bullet with at least one quote found in the brief.
3. docs/BRIEF.md must have exactly one ```text fenced block; otherwise the check fails with a clear message.

Usage: check_brief_quotes.py [--root DIR]   (default: the repo root containing this script)
       check_brief_quotes.py --self-test
Exit: 0 pass, 1 fail.
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

MIN_LEN = 12
# Quotes that are not the brief's words, with where they come from. Adding a line here is a deliberate decision.
OTHER_SOURCES = {
    "whether the dashboard is server-rendered or a separate frontend": "docs/team/environment.md \u00a7 Open",
    "Branch not protected": "gh api .../branches/main/protection response",
    "going around": "lead's question about the brief's 'go around', Q-05",
    "artifact upload failed": "user decision on issue #120 (Q-36), 2026-11-26",
    "contracts + CI": "docs/PLAN.md wave 1 heading (lead's wording, Q-25)",
    "T012 default: assumed, pending user": "docs/OPEN_QUESTIONS.md status marker",
    "any valid event": "docs/PLAN.md contract format term",
    "YAML must load as JSON": "docs/PLAN.md subsection name",
    "<base URI>#<JSON pointer to the schema>": "docs/PLAN.md contract format placeholder",
    "every example validates against its schema": "docs/PLAN.md section title; the brief's own words are "
                                                   "'validates against its schema', checked where quoted as brief",
}
NOT_BRIEF_LABEL = re.compile(r"paraphrase|not the brief|lead's wording", re.I)
QUOTE = re.compile(r'"([^"]*)"')
FILES = ("docs/OPEN_QUESTIONS.md", "docs/PLAN.md")


def norm(s: str) -> str:
    return " ".join(s.split())


def load_brief(root: Path) -> tuple[str | None, str | None]:
    path = root / "docs/BRIEF.md"
    if not path.exists():
        return None, "docs/BRIEF.md: missing"
    parts = path.read_text(encoding="utf-8").split("```text")
    if len(parts) != 2 or "```" not in parts[1]:
        return None, "docs/BRIEF.md: needs exactly one ```text ... ``` block holding the verbatim brief"
    return norm(parts[1].split("```", 1)[0]), None


def in_brief(quote: str, brief: str) -> bool:
    pieces = [norm(p) for p in quote.split("...") if p.strip()]
    return bool(pieces) and all(p in brief for p in pieces)


def block_start(text: str, pos: int) -> int:
    """Start of the paragraph, bullet, heading or table row holding pos."""
    return max(max(text.rfind(sep, 0, pos) for sep in ("\n\n", "\n- ", "\n### ", "\n## ", "\n| ")), 0)


def strip_code(text: str) -> str:
    """Blank out fenced blocks and inline code spans, keeping offsets and line numbers."""
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))
    text = re.sub(r"(?ms)^```.*?^```", blank, text)
    return re.sub(r"`[^`\n]*`", blank, text)


def quotes(text: str):
    """Yield (offset, quote, needs_check) for every quoted passage of MIN_LEN+ characters outside code."""
    text = strip_code(text)
    for m in QUOTE.finditer(text):
        q = norm(m.group(1))
        if len(q) < MIN_LEN or "\n\n" in m.group(1):
            continue
        before = text[block_start(text, m.start()):m.start()]
        if re.search(r"§ $", before) or re.search(r'§ "[^"]*" \($', before):
            continue
        if NOT_BRIEF_LABEL.search(text[m.end():m.end() + 80]):
            continue
        yield m.start(), q, q not in OTHER_SOURCES


def check(root: Path) -> list[str]:
    brief, err = load_brief(root)
    if err:
        return [err]
    failures: list[str] = []
    checked = 0
    for rel in FILES:
        path = root / rel
        if not path.exists():
            failures.append(f"{rel}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        for pos, q, claim in quotes(text):
            if not claim:
                continue
            checked += 1
            if not in_brief(q, brief):
                line = text.count("\n", 0, pos) + 1
                failures.append(f'{rel}:{line}: quote not in docs/BRIEF.md and not declared in OTHER_SOURCES: "{q}"')
    oq_path = root / FILES[0]
    oq = oq_path.read_text(encoding="utf-8") if oq_path.exists() else ""
    for entry in re.split(r"(?m)^(?=### )", oq):
        if not re.search(r"(?m)^- \*\*Status:\*\* `resolved-by-user-brief`", entry):
            continue
        head = entry.splitlines()[0]
        m = re.search(r"(?ms)^- \*\*Brief \(verbatim\)[^\n]*?:\*\*(.*?)(?=^- \*\*|\Z)", entry)
        found = m and any(len(norm(q)) >= MIN_LEN and in_brief(q, brief) for q in QUOTE.findall(m.group(1)))
        if not found:
            failures.append(f"{FILES[0]}: {head}: resolved-by-user-brief without a verbatim brief quote")
    if checked == 0 and not failures:
        failures.append("no brief quotes found at all; the check would be vacuous")
    print(f"{checked} brief quote(s) checked in {', '.join(FILES)}")
    return failures


def self_test() -> int:
    brief = ("# Brief\n\n```text\nWave 1 is CONTRACTS ONLY. Write no service code.\n"
             "Set up CI from day one: a required aggregate check.\n```\n")
    oq = ("# Open questions\n\n### Q-01 Location\n- **Brief (verbatim):** \"Wave 1 is CONTRACTS ONLY.\"\n"
          "- **Status:** `resolved-by-user-brief` (quoted above).\n\n"
          "### Q-02 Rounds\n- **Point:** the user brief asks: \"Set up CI from day one\".\n"
          "  Earlier this file said \"caps fix rounds at two\", which is the lead's paraphrase, not the brief.\n"
          "  The user's lead.md § \"Communication\" (\"Requests become issues\") says something else.\n"
          "- **Status:** `needs-decision`.\n")
    plan = "# Plan\n\nThe brief says \"Wave 1 is CONTRACTS ONLY\" and \"Set up CI from day one\".\n"
    cases = {
        "valid": (brief, oq, plan, True),
        "a_changed_verbatim_quote": (brief, oq.replace('"Wave 1 is CONTRACTS ONLY."', '"Wave 1 is CONTRACTS AND CI."'), plan, False),
        "b_resolved_without_quote": (brief, oq + "\n### Q-03 X\n- **Point:** none.\n- **Status:** `resolved-by-user-brief` (quoted above).\n", plan, False),
        "c_changed_inline_quote": (brief, oq.replace('"Set up CI from day one"', '"Set up CI in wave 1 only"'), plan, False),
        "d_changed_plan_quote": (brief, oq, plan.replace('"Wave 1 is CONTRACTS ONLY"', '"Wave 1 is CONTRACTS AND CI ONLY"'), False),
        "e_missing_fence": ("# Brief\n\nno fence here\n", oq, plan, False),
        "g_changed_quote_without_brief_word": (brief, oq + "\n### Q-04 Y\n- **Point:** the runner must \"Set up CI in wave 2\".\n- **Status:** `open`.\n", plan, False),
        "h_code_span_ignored": (brief, oq + "\n### Q-05 Z\n- **Point:** `\"some literal string\"` is code.\n- **Status:** `open`.\n", plan, True),
        "f_unlabelled_paraphrase": (brief, oq.replace(", which is the lead's paraphrase, not the brief.", "."), plan, False),
    }
    bad = []
    for name, (b, o, p, should_pass) in cases.items():
        tmp = Path(tempfile.mkdtemp(prefix="t013-selftest-"))
        try:
            (tmp / "docs").mkdir()
            (tmp / "docs/BRIEF.md").write_text(b, encoding="utf-8")
            (tmp / "docs/OPEN_QUESTIONS.md").write_text(o, encoding="utf-8")
            (tmp / "docs/PLAN.md").write_text(p, encoding="utf-8")
            failures = check(tmp)
        finally:
            shutil.rmtree(tmp)
        if (not failures) != should_pass:
            bad.append(f"self-test case {name}: expected {'pass' if should_pass else 'fail'}, got {failures or 'pass'}")
    for line in bad:
        print(line)
    print("self-test ok (9 cases)" if not bad else "self-test FAILED")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if argv[1:] == ["--self-test"]:
        return self_test()
    root = Path(__file__).resolve().parents[2]
    if len(argv) == 3 and argv[1] == "--root":
        root = Path(argv[2])
    elif len(argv) != 1:
        print(__doc__)
        return 1
    failures = check(root)
    for f in failures:
        print(f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
