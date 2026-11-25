#!/usr/bin/env python3
"""Lead lock: only one Claude Code session may act as lead on this repo at a time.

The lock is a GitHub issue labelled `lead-lock`. Its body holds a JSON block with
the holder's session ID, what it is working on, and a heartbeat time. A lock with
no heartbeat for STALE_MINUTES is free.

Commands (run from the repo root; use the REST API via `gh api`):
  status                      show who holds the lock
  acquire --purpose "<text>"  take the lock (fails if another live session holds it)
          [--force]           take it even from a live holder (only when the user says so)
  release                     give the lock back (only by the holder)
  heartbeat                   refresh the heartbeat if this session holds the lock
  check-settings [path]       fail unless .claude/settings.json wires all four hooks (CI)
  --self-test                 offline checks of the parsing, staleness and command guard (CI)

The repo is taken from LEAD_LOCK_REPO (owner/name) or else from the git `origin` URL;
there is no built-in default, so a copy of this script can never lock another repo.

Hook entry points (Claude Code passes the hook's JSON on stdin):
  hook-session-start          record this session's ID; print the lock status into context
  hook-pre-bash               block pushes, PR creation and merges unless this session holds the lock
  hook-heartbeat              refresh the heartbeat at most every HEARTBEAT_EVERY_MINUTES
  hook-session-end            release the lock if this session holds it

If GitHub cannot be reached, the hooks warn and let the command through, so a
network problem never locks a session out; the lead must then check by hand.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

LABEL = "lead-lock"
TITLE = "Lead lock (do not close)"
STALE_MINUTES = 60
HEARTBEAT_EVERY_MINUTES = 10
CONFIRM_WAIT_SECONDS = 2
BEGIN, END = "<!-- lead-lock:begin -->", "<!-- lead-lock:end -->"

# Bash commands that publish work and therefore need the lock.
_I = re.IGNORECASE
GUARDED = [
    re.compile(r"\bgit\b(\s+-\S+(\s+\S+)?)*\s+(push|send-pack)\b"),
    re.compile(r"\bgh\s+pr\s+(create|merge|ready)\b"),
    # gh api with an explicit write method on pulls (also --method=PUT, lower case)
    re.compile(r"\bgh\s+api\b.*\bpulls\b.*(-X|--method)[\s=]*(POST|PUT|PATCH)\b", _I),
    re.compile(r"\bgh\s+api\b.*(-X|--method)[\s=]*(POST|PUT|PATCH)\b.*\bpulls\b", _I),
    # gh api switches to POST when it is given fields, the usual way to open a PR through the API
    re.compile(r"\bgh\s+api\b(?!.*(-X|--method)[\s=]*GET\b)(?=.*\b(pulls|merges|git/refs)\b)"
               r"(?=.*\s(-[fF]\S*|--field\S*|--raw-field\S*|--input\S*))", _I),
    # direct merges and ref updates that publish without a PR
    re.compile(r"\bgh\s+api\b.*\b(merges|git/refs)\b.*(-X|--method)[\s=]*(POST|PUT|PATCH)\b", _I),
    # GraphQL pull request mutations
    re.compile(r"\bgh\s+api\b.*\b(createPullRequest|mergePullRequest|markPullRequestReadyForReview|mergeBranch|createCommitOnBranch|updateRef|createRef)\b"),
]


class GitHubError(RuntimeError):
    pass


def repo_from_url(url: str) -> str | None:
    m = re.match(r"^(?:https?://(?:[^@/]+@)?|ssh://git@|git@)github\.com[:/]+([\w.-]+)/([\w.-]+?)(?:\.git)?/?$",
                 url.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def repo() -> str:
    env = os.environ.get("LEAD_LOCK_REPO")
    if env:
        return env
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True,
                             text=True, check=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitHubError(f"cannot read the git origin URL ({exc}); set LEAD_LOCK_REPO") from exc
    found = repo_from_url(url)
    if not found:
        raise GitHubError(f"origin {url.strip()!r} is not a GitHub URL; set LEAD_LOCK_REPO")
    return found


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def gh(*args: str, body: dict | None = None) -> object:
    cmd = ["gh", "api", *args]
    if body is not None:
        cmd += ["--input", "-"]
    try:
        out = subprocess.run(
            cmd,
            input=json.dumps(body) if body is not None else None,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitHubError(str(exc)) from exc
    if out.returncode != 0:
        raise GitHubError(out.stderr.strip() or f"gh api exited {out.returncode}")
    return json.loads(out.stdout) if out.stdout.strip() else None


def state_dir() -> Path:
    """Per-checkout folder inside .git (shared by worktrees, never committed)."""
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        path = Path(common) / "lead-lock"
    except (OSError, subprocess.CalledProcessError):
        path = Path(".lead-lock")
    path.mkdir(parents=True, exist_ok=True)
    return path


def my_session() -> str | None:
    env = os.environ.get("LEAD_SESSION_ID")
    if env:
        return env
    f = state_dir() / "session-id"
    return f.read_text().strip() or None if f.exists() else None


def find_issue() -> dict | None:
    issues = gh(f"repos/{repo()}/issues?labels={LABEL}&state=open&per_page=5")
    return issues[0] if issues else None


def ensure_issue() -> dict:
    issue = find_issue()
    if issue:
        return issue
    try:
        gh(f"repos/{repo()}/labels", "-X", "POST",
           body={"name": LABEL, "color": "5319e7", "description": "Holds the one-lead-per-repo lock"})
    except GitHubError:
        pass  # label already exists
    return gh(f"repos/{repo()}/issues", "-X", "POST",
              body={"title": TITLE, "labels": [LABEL], "body": render({})})


def parse(issue: dict | None) -> dict:
    if not issue:
        return {}
    m = re.search(re.escape(BEGIN) + r"\s*```json\s*(.*?)\s*```\s*" + re.escape(END),
                  issue.get("body") or "", re.DOTALL)
    try:
        return json.loads(m.group(1)) if m else {}
    except json.JSONDecodeError:
        return {}


def render(lock: dict) -> str:
    return (
        "Only the session named here may act as lead on this repo (push, open or merge PRs).\n"
        "Managed by `scripts/team/lead_lock.py`; see CLAUDE.md \"Lead lock\". "
        "Do not edit by hand unless a stale lock must be cleared.\n\n"
        f"{BEGIN}\n```json\n{json.dumps(lock, indent=2)}\n```\n{END}\n"
    )


def save(issue: dict, lock: dict) -> None:
    gh(f"repos/{repo()}/issues/{issue['number']}", "-X", "PATCH", body={"body": render(lock)})


def is_live(lock: dict) -> bool:
    if not lock.get("session"):
        return False
    try:
        beat = datetime.fromisoformat(lock["heartbeat"])
    except (KeyError, ValueError):
        return False
    return now() - beat < timedelta(minutes=STALE_MINUTES)


def describe(lock: dict) -> str:
    if not lock.get("session"):
        return "The lead lock is free."
    age = ""
    try:
        mins = int((now() - datetime.fromisoformat(lock["heartbeat"])).total_seconds() // 60)
        age = f", last heartbeat {mins} min ago"
    except (KeyError, ValueError):
        pass
    live = "live" if is_live(lock) else f"STALE (over {STALE_MINUTES} min, free to take)"
    return (f"Lead lock held by session {lock['session']} ({live}{age}), "
            f"working on: {lock.get('purpose', '?')}; since {lock.get('acquired', '?')}.")


# ---- commands -------------------------------------------------------------

def cmd_status() -> int:
    lock = parse(find_issue())
    print(describe(lock))
    me = my_session()
    if me and lock.get("session") == me:
        print("This session holds the lock.")
    return 0


def cmd_acquire(purpose: str, force: bool) -> int:
    me = my_session()
    if not me:
        print("No session ID recorded (the hooks did not run in this session). Start a new "
              "session in this repo; do not invent an ID, the hooks only match the real one.",
              file=sys.stderr)
        return 1
    issue = ensure_issue()
    lock = parse(issue)
    if is_live(lock) and lock["session"] != me and not force:
        print("REFUSED: " + describe(lock), file=sys.stderr)
        print("Coordinate with that session, wait for it to go stale, or take over with --force "
              "only if the user says so.", file=sys.stderr)
        return 1
    stamp = now().isoformat()
    acquired = lock.get("acquired", stamp) if lock.get("session") == me else stamp
    new = {"session": me, "purpose": purpose, "acquired": acquired, "heartbeat": stamp}
    if force and lock.get("session") not in (None, me):
        new["took_over_from"] = lock["session"]
    save(issue, new)
    # The read-then-write above is not atomic. Wait a moment and read it back: if another
    # session wrote after us, it holds the lock and we must stand down. This narrows the race,
    # it does not remove it.
    time.sleep(CONFIRM_WAIT_SECONDS)
    held = parse(gh(f"repos/{repo()}/issues/{issue['number']}"))
    if held.get("session") != me:
        print("REFUSED: another session took the lock at the same moment. " + describe(held),
              file=sys.stderr)
        return 1
    (state_dir() / f"last-heartbeat-{me}").write_text(stamp)
    print(f"Lead lock acquired by {me}: {purpose}")
    return 0


def cmd_release(session: str | None = None) -> int:
    me = session or my_session()
    issue = find_issue()
    lock = parse(issue)
    if not issue or not me or lock.get("session") != me:
        print("This session does not hold the lead lock; nothing to release.")
        return 0
    save(issue, {})
    print("Lead lock released.")
    return 0


def cmd_heartbeat(throttled: bool, session: str | None = None) -> int:
    me = session or my_session()
    if not me:
        return 0
    marker = state_dir() / f"last-heartbeat-{me}"
    if throttled and marker.exists():
        try:
            last = datetime.fromisoformat(marker.read_text().strip())
            if now() - last < timedelta(minutes=HEARTBEAT_EVERY_MINUTES):
                return 0
        except ValueError:
            pass
    issue = find_issue()
    lock = parse(issue)
    if issue and lock.get("session") == me:
        lock["heartbeat"] = now().isoformat()
        save(issue, lock)
    marker.write_text(now().isoformat())
    return 0


# ---- hooks ----------------------------------------------------------------

def read_hook_input() -> dict:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def hook_session_start() -> int:
    data = read_hook_input()
    sid = data.get("session_id")
    if sid:
        (state_dir() / "session-id").write_text(sid)
    try:
        lock = parse(find_issue())
    except GitHubError as exc:
        print(f"[lead-lock] Could not read the lead lock ({exc}). Check it by hand before "
              "pushing or merging: python3 scripts/team/lead_lock.py status")
        return 0
    msg = ["[lead-lock] " + describe(lock)]
    if sid and lock.get("session") == sid:
        msg.append("This session holds the lock.")
    elif is_live(lock):
        msg.append("Another session is the lead. This session may answer questions and "
                   "investigate, but must not change code, push, open or merge PRs. "
                   "Tell the user which session holds the lock.")
    else:
        msg.append("Before changing code, take the lock: "
                   "python3 scripts/team/lead_lock.py acquire --purpose \"<what this session will do>\"")
    print(" ".join(msg))
    return 0


def hook_pre_bash() -> int:
    data = read_hook_input()
    command = (data.get("tool_input") or {}).get("command", "")
    if not isinstance(command, str):
        return 0
    sid = data.get("session_id")
    if sid and "lead_lock.py" in command:
        # The command that follows runs in THIS session. Several sessions can share one clone and
        # the session-id file, so bind it to this session just before lead_lock.py reads it.
        (state_dir() / "session-id").write_text(sid)
    if not any(p.search(command) for p in GUARDED):
        return 0
    if not sid:
        print("[lead-lock] warning: the hook input has no session_id; allowing the command. "
              "Confirm this session holds the lead lock.", file=sys.stderr)
        return 0
    try:
        lock = parse(find_issue())
    except GitHubError as exc:
        print(f"[lead-lock] warning: could not check the lead lock ({exc}); allowing the command. "
              "Confirm no other session is lead.", file=sys.stderr)
        return 0
    if lock.get("session") == sid and is_live(lock):
        return 0
    if lock.get("session") == sid:  # sid is set here, so this is a real match
        print("[lead-lock] Your lock went stale. Re-take it first: "
              "python3 scripts/team/lead_lock.py acquire --purpose \"...\"", file=sys.stderr)
    elif is_live(lock):
        print("[lead-lock] BLOCKED: " + describe(lock) + " Only the lead session may push, open "
              "or merge PRs. Tell the user; do not work around this.", file=sys.stderr)
    else:
        print("[lead-lock] BLOCKED: this session does not hold the lead lock. Take it first: "
              "python3 scripts/team/lead_lock.py acquire --purpose \"...\"", file=sys.stderr)
    return 2


def hook_heartbeat() -> int:
    sid = read_hook_input().get("session_id")
    if not sid:
        return 0
    try:
        return cmd_heartbeat(throttled=True, session=sid)
    except GitHubError:
        return 0


def hook_session_end() -> int:
    sid = read_hook_input().get("session_id")
    if not sid:
        return 0
    try:
        return cmd_release(session=sid)
    except GitHubError:
        return 0


# ---- CI checks ------------------------------------------------------------

REQUIRED_HOOKS = {
    "SessionStart": "hook-session-start",
    "PreToolUse": "hook-pre-bash",
    "PostToolUse": "hook-heartbeat",
    "SessionEnd": "hook-session-end",
}


def _runs_hook(entry: dict, name: str) -> bool:
    """True if a hook entry is a command hook that ends in `python3 <lead_lock.py> <name>`."""
    if entry.get("type") != "command":
        return False
    cmd = entry.get("command", "")
    tail = re.search(r'python3\s+"?(\$P|\$CLAUDE_PROJECT_DIR/scripts/team/lead_lock\.py)"?\s+'
                     + re.escape(name) + r"\s*$", cmd)
    return bool(tail) and "scripts/team/lead_lock.py" in cmd


def settings_problems(settings: dict) -> list[str]:
    """Which of the four lead-lock hooks are missing, or would not run, in .claude/settings.json."""
    problems = []
    if settings.get("disableAllHooks"):
        problems.append("disableAllHooks is set: none of the hooks would run")
    hooks = settings.get("hooks") or {}
    for event, name in REQUIRED_HOOKS.items():
        groups = [g for g in hooks.get(event, []) if isinstance(g, dict)]
        if not any(_runs_hook(h, name) for g in groups for h in g.get("hooks", [])):
            problems.append(f"{event}: no command hook runs `lead_lock.py {name}`")
    pre = [g for g in hooks.get("PreToolUse", []) if isinstance(g, dict)]
    if not any(g.get("matcher") == "Bash" and any(_runs_hook(h, "hook-pre-bash")
                                                   for h in g.get("hooks", [])) for g in pre):
        problems.append("PreToolUse: the hook-pre-bash entry must have matcher \"Bash\"")
    return problems


def cmd_check_settings(path: str) -> int:
    try:
        settings = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"check-settings FAILED: cannot read {path}: {exc}", file=sys.stderr)
        return 1
    problems = settings_problems(settings)
    for p in problems:
        print(f"check-settings FAILED: {p}", file=sys.stderr)
    if not problems:
        print(f"check-settings OK: {path} wires all four lead-lock hooks.")
    return 1 if problems else 0



class _FakeGitHub:
    """One lock issue held in memory; stands in for `gh api` so the enforcement code runs offline."""

    def __init__(self, lock: dict | None = None) -> None:
        self.body = render(lock or {})
        self.on_patch = None  # called after each write, to simulate another session writing next
        self.down = False

    def __call__(self, path: str, *args: str, body: dict | None = None) -> object:
        if self.down:
            raise GitHubError("offline")
        issue = {"number": 1, "body": self.body}
        if "-X" in args and "PATCH" in args:
            self.body = body["body"]
            if self.on_patch:
                self.on_patch(self)
            return {"number": 1, "body": self.body}
        if "-X" in args and "POST" in args:
            return issue
        if "/issues?" in path:
            return [issue]
        return issue

    def lock(self) -> dict:
        return parse({"body": self.body})


def enforcement_tests(check) -> None:
    """Offline tests of the acquire / release / heartbeat / hook logic (no network, no real clone)."""
    import contextlib
    import io
    import shutil
    import tempfile

    g = globals()
    names = ("gh", "repo", "state_dir", "read_hook_input", "time")

    @contextlib.contextmanager
    def world(fake: _FakeGitHub, hook_input: dict | None = None, session: str | None = None):
        saved = {n: g[n] for n in names}
        old_env = os.environ.pop("LEAD_SESSION_ID", None)
        tmp = Path(tempfile.mkdtemp(prefix="lead-lock-test-"))
        g["gh"], g["repo"], g["state_dir"] = fake, (lambda: "o/r"), (lambda: tmp)
        g["read_hook_input"] = lambda: hook_input or {}

        class _NoSleep:
            sleep = staticmethod(lambda _s: None)
        g["time"] = _NoSleep
        if session:
            (tmp / "session-id").write_text(session)
        try:
            yield tmp
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            g.update(saved)
            if old_env is not None:
                os.environ["LEAD_SESSION_ID"] = old_env

    def run(fn, *a, **kw):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = fn(*a, **kw)
        return rc, out.getvalue() + err.getvalue()

    def lock_of(session: str, minutes_old: int = 1, purpose: str = "p") -> dict:
        beat = (now() - timedelta(minutes=minutes_old)).isoformat()
        return {"session": session, "purpose": purpose, "acquired": beat, "heartbeat": beat}

    def bash(command: str, sid: str | None = "A") -> dict:
        d: dict = {"tool_input": {"command": command}}
        if sid:
            d["session_id"] = sid
        return d

    push = "git push origin T1-x"

    # --- pre-bash: who may publish
    with world(_FakeGitHub(lock_of("A")), bash(push)):
        check(run(hook_pre_bash)[0] == 0, "pre-bash: live holder may push")
    with world(_FakeGitHub(lock_of("A", 61)), bash(push)):
        check(run(hook_pre_bash)[0] == 2, "pre-bash: holder with a stale lock is blocked")
    with world(_FakeGitHub(lock_of("B")), bash(push)):
        check(run(hook_pre_bash)[0] == 2, "pre-bash: another live holder blocks the push")
    with world(_FakeGitHub({}), bash(push)):
        check(run(hook_pre_bash)[0] == 2, "pre-bash: a free lock still blocks a session that has not taken it")
    down = _FakeGitHub(lock_of("B"))
    down.down = True
    with world(down, bash(push)):
        check(run(hook_pre_bash)[0] == 0, "pre-bash: GitHub unreachable fails open")
    with world(_FakeGitHub(lock_of("B")), bash(push, sid=None)):
        check(run(hook_pre_bash)[0] == 0, "pre-bash: no session_id fails open")
    with world(_FakeGitHub(lock_of("B")), bash("git status")):
        check(run(hook_pre_bash)[0] == 0, "pre-bash: unguarded command passes while another session leads")
    with world(_FakeGitHub({}), bash("python3 scripts/team/lead_lock.py acquire --purpose x", "A"), session="B") as tmp:
        run(hook_pre_bash)
        check((tmp / "session-id").read_text() == "A", "pre-bash binds the session id for lead_lock.py commands")

    # --- acquire / release
    os.environ["LEAD_SESSION_ID"] = "A"
    try:
        fake = _FakeGitHub({})
        with world(fake):
            os.environ["LEAD_SESSION_ID"] = "A"
            rc, _ = run(cmd_acquire, "first", False)
            check(rc == 0 and fake.lock().get("session") == "A", "acquire: free lock is taken")
            old = lock_of("A", 30)
            fake.body = render(old)
            first = old["acquired"]
            rc, _ = run(cmd_acquire, "again", False)
            check(rc == 0 and fake.lock()["acquired"] == first, "acquire: re-acquire by the holder keeps the original time")
            os.environ["LEAD_SESSION_ID"] = "B"
            rc, _ = run(cmd_acquire, "other", False)
            check(rc == 1 and fake.lock()["session"] == "A", "acquire: refused while another session is live")
            rc, _ = run(cmd_acquire, "forced", True)
            check(rc == 0 and fake.lock()["session"] == "B" and fake.lock().get("took_over_from") == "A",
                  "acquire --force takes over and records who was displaced")
            rc, _ = run(cmd_release)
            check(rc == 0 and fake.lock() == {}, "release by the holder frees the lock")
        # the read-back: another session writes right after us
        fake = _FakeGitHub({})
        with world(fake):
            os.environ["LEAD_SESSION_ID"] = "A"
            fake.on_patch = lambda f: setattr(f, "body", render(lock_of("B", 0)))
            rc, _ = run(cmd_acquire, "race", False)
            check(rc == 1, "acquire: stands down when another session wrote last")
        # a stale lock is free to take
        fake = _FakeGitHub(lock_of("B", 61))
        with world(fake):
            os.environ["LEAD_SESSION_ID"] = "A"
            check(run(cmd_acquire, "x", False)[0] == 0 and fake.lock()["session"] == "A", "acquire: stale lock is taken")
    finally:
        os.environ.pop("LEAD_SESSION_ID", None)

    # --- two sessions sharing one clone (the session-id file says B, the hooks come from A)
    fake = _FakeGitHub(lock_of("B", 30))
    with world(fake, {"session_id": "A"}, session="B"):
        run(hook_session_end)
        check(fake.lock().get("session") == "B", "session end by A does not release B's lock")
        before = fake.lock()["heartbeat"]
        run(cmd_heartbeat, False, "A")
        check(fake.lock()["heartbeat"] == before, "heartbeat from A does not refresh B's lock")
    with world(fake, {"session_id": "B"}, session="A"):
        run(hook_session_end)
        check(fake.lock() == {}, "session end by the holder (B) releases, whatever the shared file says")
    fake = _FakeGitHub(lock_of("B", 30))
    with world(fake, {"session_id": "B"}, session="A"):
        before = fake.lock()["heartbeat"]
        run(hook_heartbeat)
        check(fake.lock()["heartbeat"] != before, "heartbeat hook refreshes the lock of the session in its input")
    fake = _FakeGitHub(lock_of("B"))
    with world(fake, {}, session="B"):
        check(run(hook_session_end)[0] == 0 and fake.lock().get("session") == "B",
              "session end without a session_id leaves the lock alone")

    # --- session start must not claim a lock for a session that has no id
    with world(_FakeGitHub({}), {}):
        check("This session holds the lock" not in run(hook_session_start)[1], "session start: no id never holds the lock")

    # --- settings check
    def cfg(event: str = "PreToolUse", **over: object) -> dict:
        base = {ev: [{"matcher": "Bash", "hooks": [{"type": "command",
                "command": f'P="$CLAUDE_PROJECT_DIR/scripts/team/lead_lock.py"; [ -f "$P" ] || exit 0; python3 "$P" {n}'}]}]
                for ev, n in REQUIRED_HOOKS.items()}
        out = {"hooks": base}
        out.update(over)
        return out
    check(settings_problems(cfg()) == [], "settings: guarded form passes")
    check(settings_problems(cfg(disableAllHooks=True)) != [], "settings: disableAllHooks fails")
    wrong_event = cfg()
    wrong_event["hooks"]["PostToolUse"] = wrong_event["hooks"].pop("SessionEnd")
    check(settings_problems(wrong_event) != [], "settings: a hook under the wrong event fails")
    prompt = cfg()
    prompt["hooks"]["SessionStart"][0]["hooks"][0]["type"] = "prompt"
    check(settings_problems(prompt) != [], "settings: a non-command hook fails")
    echo = cfg()
    echo["hooks"]["SessionStart"][0]["hooks"][0]["command"] = "echo scripts/team/lead_lock.py hook-session-start"
    check(settings_problems(echo) != [], "settings: a command that only echoes the script name fails")


def self_test() -> int:
    fails: list[str] = []

    def check(cond: bool, what: str) -> None:
        if not cond:
            fails.append(what)

    # repo name from the origin URL
    check(repo_from_url("https://github.com/regevha/shipyard") == "regevha/shipyard", "https url")
    check(repo_from_url("https://github.com/regevha/shipyard.git") == "regevha/shipyard", ".git url")
    check(repo_from_url("git@github.com:regevha/shipyard.git") == "regevha/shipyard", "ssh url")
    check(repo_from_url("https://example.com/a/b") is None, "non-GitHub url")
    check(repo_from_url("https://evilgithub.com/a/b") is None, "look-alike host")
    check(repo_from_url("https://gitlab.com/github.com/a/b") is None, "github.com in the path")

    # JSON block round trip, and a broken block reads as free
    lock = {"session": "s1", "purpose": "x", "acquired": "a", "heartbeat": "h"}
    check(parse({"body": render(lock)}) == lock, "render/parse round trip")
    check(parse({"body": render({})}) == {}, "empty lock")
    check(parse({"body": BEGIN + "\n```json\n{broken\n```\n" + END}) == {}, "broken JSON is free")
    check(parse(None) == {}, "no issue")

    # staleness
    def beat(minutes: int) -> dict:
        return {"session": "s1", "heartbeat": (now() - timedelta(minutes=minutes)).isoformat()}
    check(is_live(beat(5)), "5 min old is live")
    check(is_live(beat(59)) and not is_live(beat(61)), "stale after 60 minutes")
    check(not is_live({"session": "s1"}), "no heartbeat is not live")
    check(not is_live({}), "empty is not live")

    # which commands need the lock
    blocked = [
        "git push origin T1-x", "git push", "git -C /tmp/wt push -u origin T1-x",
        "gh pr create --title x", "gh pr merge 5 --squash", "gh pr ready 5",
        "gh api repos/o/r/pulls -X POST -f title=x", "gh api -X PUT repos/o/r/pulls/5/merge",
        "gh api repos/o/r/pulls/5/merge --method PUT", "gh api --method=PUT repos/o/r/pulls/5/merge",
        "gh api -X put repos/o/r/pulls/5/merge",
        "gh api repos/o/r/pulls -f title=x -f head=a -f base=main",
        "gh api repos/o/r/merges -X POST -f base=main -f head=a",
        "gh api repos/o/r/git/refs/heads/main -X PATCH -f sha=abc",
        "gh api graphql -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'",
        "git send-pack origin main",
        "gh api repos/o/r/merges -f base=main -f head=x",
        "gh api repos/o/r/git/refs -f ref=refs/heads/x -f sha=abc",
        "gh api repos/o/r/pulls --input pr.json", "gh api repos/o/r/pulls -ftitle=x",
    ]
    allowed = [
        "git status", "git commit -m 'update push docs'", "git log --oneline", "gh pr view 5",
        "gh pr list", "gh api repos/o/r/pulls/5", "gh api repos/o/r/issues -X POST",
        "python3 scripts/team/lead_lock.py acquire --purpose x",
        "gh api repos/o/r/pulls -X GET -f state=open", "gh api repos/o/r/issues -f title=x",
        "gh api repos/o/r/issues --input x.json",
    ]
    for c in blocked:
        check(any(p.search(c) for p in GUARDED), f"should be guarded: {c}")
    for c in allowed:
        check(not any(p.search(c) for p in GUARDED), f"should NOT be guarded: {c}")

    # the settings check
    good = {"hooks": {ev: [{"matcher": "Bash", "hooks": [{"type": "command",
            "command": f'python3 "$CLAUDE_PROJECT_DIR/scripts/team/lead_lock.py" {name}'}]}]
            for ev, name in REQUIRED_HOOKS.items()}}
    check(settings_problems(good) == [], "complete settings pass")
    check(len(settings_problems({})) >= 4, "empty settings fail")
    broken = json.loads(json.dumps(good))
    del broken["hooks"]["SessionEnd"]
    check(len(settings_problems(broken)) == 1, "one missing hook is reported")
    nomatcher = json.loads(json.dumps(good))
    nomatcher["hooks"]["PreToolUse"][0].pop("matcher")
    check(len(settings_problems(nomatcher)) == 1, "PreToolUse without matcher Bash fails")


    enforcement_tests(check)

    for f in fails:
        print(f"self-test FAILED: {f}", file=sys.stderr)
    if not fails:
        print("lead_lock self-test OK")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "status":
            return cmd_status()
        if cmd == "acquire":
            i = rest.index("--purpose") if "--purpose" in rest else -1
            purpose = rest[i + 1] if 0 <= i < len(rest) - 1 else "unspecified"
            return cmd_acquire(purpose, force="--force" in rest)
        if cmd == "release":
            return cmd_release()
        if cmd == "--self-test":
            return self_test()
        if cmd == "check-settings":
            return cmd_check_settings(rest[0] if rest else ".claude/settings.json")
        if cmd == "heartbeat":
            return cmd_heartbeat(throttled=False)
        hooks = {
            "hook-session-start": hook_session_start,
            "hook-pre-bash": hook_pre_bash,
            "hook-heartbeat": hook_heartbeat,
            "hook-session-end": hook_session_end,
        }
        if cmd in hooks:
            return hooks[cmd]()
    except GitHubError as exc:
        print(f"GitHub error: {exc}", file=sys.stderr)
        return 1
    print(f"Unknown command: {cmd}\n{__doc__}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
