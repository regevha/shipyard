#!/usr/bin/env python3
"""Fail if a team-sync branch changes files outside docs/team/SYNC_FILES.

Applies only to branches starting `team-sync-`; any other branch passes.
The allowlist is read from the BASE ref, so a PR cannot approve its own new lines.
Usage: check_sync_scope.py <branch> <base-ref>
       check_sync_scope.py --self-test
"""
import subprocess
import sys
from pathlib import Path

from check_task_scope import matches  # same matching logic as the task-scope check

PREFIX = "team-sync-"
SYNC_FILES = Path("docs/team/SYNC_FILES")


def load_patterns(text: str) -> list[str]:
    lines = (line.split("#", 1)[0].strip() for line in text.splitlines())
    pats = [line for line in lines if line]
    for p in pats:
        if any(c in p for c in "*?["):
            raise ValueError(f"globs are not supported in SYNC_FILES: {p}")
    return pats


def outside(changed: list[str], patterns: list[str]) -> list[str]:
    return [f for f in changed if not any(matches(f, p) for p in patterns)]


def parse_z(raw: str) -> list[str]:
    return [f for f in raw.split("\0") if f]


def check(cond: bool, what: str) -> None:
    if not cond:
        print(f"self-test FAILED: {what}")
        raise SystemExit(1)


def self_test() -> int:
    pats = load_patterns("# c\nCLAUDE.md  # x\n\n.claude/agents/\ndocs/team/SYNC_FILES\n")
    check(pats == ["CLAUDE.md", ".claude/agents/", "docs/team/SYNC_FILES"], "parse")
    check(outside(["CLAUDE.md", ".claude/agents/a.md"], pats) == [], "listed files pass")
    check(outside([".claude/agentsx"], pats) == [".claude/agentsx"], "prefix is not a folder match")
    # rename (with --no-renames git reports delete + add): old path is outside the list
    check(
        outside(["docs/team/environment.md", ".claude/agents/environment.md"], pats)
        == ["docs/team/environment.md"],
        "rename out of an unlisted path fails",
    )
    # filename with a space and a newline survives NUL splitting
    names = parse_z(".claude/agents/a b.md\0docs/x\ny.md\0")
    check(names == [".claude/agents/a b.md", "docs/x\ny.md"], "NUL split")
    check(outside(names, pats) == ["docs/x\ny.md"], "odd names checked whole")
    # self-edit: allowlist comes from base, so a line added in the PR does not count
    check(
        outside(["docs/team/SYNC_FILES", "docs/PLAN.md"], pats) == ["docs/PLAN.md"],
        "SYNC_FILES self-edit does not approve new lines",
    )
    try:
        load_patterns("docs/*\n")
        check(False, "globs rejected")
    except ValueError:
        pass
    print("self-test ok")
    return 0


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    if len(sys.argv) != 3:
        print("Usage: check_sync_scope.py <branch> <base-ref> | --self-test")
        return 2
    branch, base = sys.argv[1], sys.argv[2]
    if not branch.startswith(PREFIX):
        print(f"Branch '{branch}' is not a {PREFIX}* branch; no sync scope to check.")
        return 0
    try:
        patterns = load_patterns(git("show", f"{base}:{SYNC_FILES}"))
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"FAIL: cannot read a valid {SYNC_FILES} from {base}: {e}")
        return 1
    changed = parse_z(git("diff", "--name-only", "-z", "--no-renames", f"{base}...HEAD"))
    bad = outside(changed, patterns)
    if bad:
        print(f"FAIL: sync branch changed files not listed in {SYNC_FILES} (as on {base}):")
        for f in bad:
            print(f"  {f!r}")
        print("Add the file to SYNC_FILES in a separate merged change first, or remove it from the branch.")
        return 1
    print(f"ok: {len(changed)} changed file(s), all listed in {SYNC_FILES} (as on {base}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
