#!/usr/bin/env python3
"""Fail if a task branch changes files outside its task spec.

The branch name must start with a task ID (e.g. T07-backend-jobs). The spec is
docs/tasks/<ID>.yml. Allowed: files matching `files_touched` (globs allowed),
plus docs/tasks/<ID>.md (the hand-off note). Branches that are not task
branches must start with one of HOUSEKEEPING_PREFIXES (lead and team housekeeping)
immediately followed by a task ID (e.g. spec-T200-foo, team-sync-T210-x); every
branch name carries a task ID, any other name fails (see classify_branch).
The spec is read from the BASE ref (not the PR checkout), so a branch cannot widen
its own files_touched. The diff is split on NUL with --no-renames, so a rename
cannot hide its old path and odd filenames are checked whole.
Per-repo exemptions: docs/team/branch_exemptions on the BASE ref lists branch-name prefixes (one per line,
# comments, blank lines ignored; end each entry with `/` or `-` since matching is startswith) that pass without a task ID and without a file-scope check. A missing file
means no exemptions; any other git error fails the check. This repo ships the file empty.
Usage: check_task_scope.py <branch> <base-ref>
       check_task_scope.py --self-test
"""
import fnmatch
import os
import re
import subprocess
import sys

import yaml


# Housekeeping prefixes (checked longest first); each must be followed by a task ID
# (T + digits) and then "-", "_" or the end of the name. No file-scope check for these.
HOUSEKEEPING_PREFIXES = ("team-sync-", "closeout-", "process-", "spec-", "team-", "docs-")


EXEMPTIONS_PATH = "docs/team/branch_exemptions"


def parse_exemptions(text: str) -> list[str]:
    """One prefix per line; '#' starts a comment; blank lines are ignored (an empty prefix would exempt everything)."""
    lines = (line.split("#", 1)[0].strip() for line in text.splitlines())
    return [line for line in lines if line]


def load_exemptions(base: str) -> list[str]:
    """Read the list from the BASE ref so a PR cannot exempt its own branch. Missing file = none."""
    env = {**os.environ, "LC_ALL": "C"}  # the missing-file check below reads git's English message
    proc = subprocess.run(["git", "show", f"{base}:{EXEMPTIONS_PATH}"], capture_output=True, text=True, env=env)
    if proc.returncode == 0:
        return parse_exemptions(proc.stdout)
    # a missing path is "no exemptions"; anything else (bad ref, git failure) must fail the check
    if "does not exist" in proc.stderr or "exists on disk, but not in" in proc.stderr:
        return []
    raise RuntimeError(f"cannot read {EXEMPTIONS_PATH} from {base}: {proc.stderr.strip()}")


def classify_branch(name: str, exempt: tuple[str, ...] | list[str] = ()) -> tuple[str, str | None]:
    """Return ("task", ID), ("housekeeping", ID), ("exempt", None) or ("invalid", None)."""
    m = re.match(r"^(T\d+)[-_]", name)
    if m:
        return "task", m.group(1)
    if any(name.startswith(p) for p in exempt):
        return "exempt", None
    for prefix in sorted(HOUSEKEEPING_PREFIXES, key=len, reverse=True):
        if name.startswith(prefix):
            m = re.match(r"(T\d+)(?:[-_]|$)", name[len(prefix):])
            if m:
                return "housekeeping", m.group(1)
    return "invalid", None


def matches(path: str, pattern: str) -> bool:
    pattern = pattern.rstrip("/")
    if fnmatch.fnmatch(path, pattern) or path.startswith(pattern + "/"):
        return True
    # "**" support: treat it as "any depth"
    regex = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.fullmatch(regex, path) is not None


def parse_z(raw: str) -> list[str]:
    return [f for f in raw.split("\0") if f]


def allowed_from_spec(text: str, task: str) -> list[str]:
    spec = yaml.safe_load(text) or {}
    allowed = list(spec.get("files_touched") or []) if isinstance(spec, dict) else []
    if allowed:
        allowed.append(f"docs/tasks/{task}.md")
    return allowed


def outside(changed: list[str], allowed: list[str]) -> list[str]:
    return [f for f in changed if not any(matches(f, p) for p in allowed)]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def check(cond: bool, what: str) -> None:
    if not cond:
        print(f"self-test FAILED: {what}")
        raise SystemExit(1)


def exemption_repo_test() -> None:
    """Real git repo in a temp dir: the list is read from the BASE ref, never from the branch or working tree."""
    import tempfile

    def sh(cwd, *args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                       capture_output=True)

    with tempfile.TemporaryDirectory() as d:
        sh(d, "init", "-q", "-b", "main")
        sh(d, "commit", "-q", "--allow-empty", "-m", "empty base")  # base without the file
        here = os.getcwd()
        os.chdir(d)
        try:
            check(load_exemptions("main") == [], "missing file on base means no exemptions")
            check(classify_branch("dependabot/x", load_exemptions("main"))[0] == "invalid", "no file, no exemption")
            try:
                load_exemptions("no-such-ref")
                check(False, "a bad base ref must raise, not mean 'no exemptions'")
            except RuntimeError:
                pass
            # a branch adds its own exemption and also leaves it in the working tree: base must not see it
            sh(d, "checkout", "-q", "-b", "pr")
            os.makedirs("docs/team")
            with open(EXEMPTIONS_PATH, "w") as f:
                f.write("extra/\n")
            sh(d, "add", "-A")
            sh(d, "commit", "-q", "-m", "pr adds own exemption")
            check(load_exemptions("main") == [], "a PR cannot exempt its own branch (base has no file)")
            sh(d, "checkout", "-q", "main")
            os.makedirs("docs/team", exist_ok=True)
            with open(EXEMPTIONS_PATH, "w") as f:
                f.write("# c\ndependabot/\n\n")
            sh(d, "add", "-A")
            sh(d, "commit", "-q", "-m", "base gets the list")
            sh(d, "checkout", "-q", "pr")  # HEAD/working tree now differ from base
            check(load_exemptions("main") == ["dependabot/"], "list is read from the base ref")
            # the whole script, as CI runs it: exempt branch passes, any other name fails
            script = os.path.join(here, os.path.abspath(__file__)) if not os.path.isabs(__file__) else __file__
            for branch, want in (("dependabot/x", 0), ("feature-x", 1)):
                rc = subprocess.run([sys.executable, script, branch, "main"], cwd=d, capture_output=True).returncode
                check(rc == want, f"script exit code for {branch}: got {rc}, want {want}")
        finally:
            os.chdir(here)


def self_test() -> int:
    base_spec = "files_touched:\n  - scripts/ci/a.py\n  - docs/x/\n"
    allowed = allowed_from_spec(base_spec, "T9")
    check(allowed == ["scripts/ci/a.py", "docs/x/", "docs/tasks/T9.md"], "spec parse")
    check(outside(["scripts/ci/a.py", "docs/x/y.md", "docs/tasks/T9.md"], allowed) == [], "in scope and hand-off pass")
    check(allowed_from_spec("title: x\n", "T9") == [], "no files_touched gives empty list")
    # rename: with --no-renames git reports delete + add, so the old path is checked
    check(outside(["docs/other/old.md", "docs/x/new.md"], allowed) == ["docs/other/old.md"], "rename from outside fails")
    # filenames with a space and a newline survive NUL splitting and are checked whole
    names = parse_z("docs/x/a b.md\0docs/other/x\ny.md\0")
    check(names == ["docs/x/a b.md", "docs/other/x\ny.md"], "NUL split")
    check(outside(names, allowed) == ["docs/other/x\ny.md"], "odd names checked whole")
    # spec widened in the PR: allowed comes from the base text, so the PR's version is never read
    check(outside(["backend/app.py", "docs/tasks/T9.yml"], allowed) == ["backend/app.py", "docs/tasks/T9.yml"],
          "widened spec in the PR does not approve new files")
    for good in ("spec-T200-foo", "docs-T215-readme", "spec-T112", "spec-T113-T114", "team-sync-T210-x"):
        check(classify_branch(good)[0] == "housekeeping", f"branch ok: {good}")
    check(classify_branch("spec-T200-foo") == ("housekeeping", "T200"), "housekeeping id")
    check(classify_branch("T07-backend") == ("task", "T07"), "task branch")
    for bad in ("feature-x", "spec-foo", "team-sync-x", "dependabot/x", "t07-x", "T07", "feature/T7-x", "scratch"):
        check(classify_branch(bad) == ("invalid", None), f"branch rejected: {bad}")
    check(parse_exemptions("# c\n\n  dependabot/  # bots\n   \nlegacy-\n") == ["dependabot/", "legacy-"], "exemptions parse, blanks ignored")
    check(parse_exemptions("") == [] and parse_exemptions("\n  \n# only comment\n") == [], "empty list stays empty")
    check(classify_branch("dependabot/pip/x", ["dependabot/"]) == ("exempt", None), "listed prefix is exempt")
    check(classify_branch("dependabot/pip/x", []) == ("invalid", None), "unlisted prefix still fails")
    check(classify_branch("feature-x", ["dependabot/"]) == ("invalid", None), "other names still fail")
    check(classify_branch("T07-x", ["dependabot/"]) == ("task", "T07"), "task branches unaffected")
    check(classify_branch("dependabotevil/x", ["dependabot/"]) == ("invalid", None), "prefix needs its slash")
    check(classify_branch("x-dependabot/y", ["dependabot/"]) == ("invalid", None), "match is a prefix, not a substring")
    exemption_repo_test()
    print("self-test ok")
    return 0


def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    if len(sys.argv) != 3:
        print("Usage: check_task_scope.py <branch> <base-ref> | --self-test")
        return 2
    branch, base = sys.argv[1], sys.argv[2]
    try:
        exempt = load_exemptions(base)
    except RuntimeError as e:
        print(f"FAIL: {e}")
        return 1
    kind, task = classify_branch(branch, exempt)
    if kind == "exempt":
        print(f"Branch '{branch}' matches an exemption in {EXEMPTIONS_PATH} on {base}; no task scope to check.")
        return 0
    if kind == "housekeeping":
        print(f"Branch '{branch}' is a housekeeping branch for {task}; no task scope to check.")
        return 0
    if kind == "invalid":
        print(f"FAIL: branch '{branch}' carries no task ID. Accepted forms:")
        print("  task branch:        T<nn>-<name>  (e.g. T07-backend-jobs)")
        print(f"  housekeeping branch: <prefix>T<nn>[-<name>] with prefix one of {', '.join(HOUSEKEEPING_PREFIXES)}")
        print("  (e.g. spec-T200-task-manager-specs). Rename the branch.")
        return 1
    spec_path = f"docs/tasks/{task}.yml"
    try:
        spec_text = git("show", f"{base}:{spec_path}")
    except subprocess.CalledProcessError:
        print(f"FAIL: {spec_path} not found on {base}. The architect must write the task spec, and it must be merged first.")
        return 1
    try:
        allowed = allowed_from_spec(spec_text, task)
    except yaml.YAMLError as e:
        print(f"FAIL: {spec_path} on {base} is not valid YAML: {e}")
        return 1
    if not allowed:
        print(f"FAIL: {spec_path} on {base} has no files_touched.")
        return 1
    changed = parse_z(git("diff", "--name-only", "-z", "--no-renames", f"{base}...HEAD"))
    bad = outside(changed, allowed)
    if bad:
        print(f"FAIL: {task} changed files outside its files_touched (as on {base}):")
        for f in bad:
            print(f"  {f!r}")
        print("Request a spec change from the lead instead of editing other areas.")
        return 1
    print(f"ok: {len(changed)} changed file(s), all within {task}'s files_touched (as on {base}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
