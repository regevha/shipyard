#!/usr/bin/env python3
"""Fail if a per-service copy of a shared file differs from its canonical file.

Usage: check_shared_copy.py [--self-test] [--root DIR]

Rules per canonical file (T021, docs/team/environment.md "Error envelope"):
  - canonical present: every copy must exist and be byte-identical (one line per difference);
  - canonical absent and no copy present: "<file>: not created yet", passes;
  - canonical absent but a copy present: fails.
Standard library only, no network.
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

SERVICES = ["pipeline-runner", "artifact-store", "release-service", "dashboard"]

# canonical file -> template of the copy path ({s} = service name)
COPY_MAP = {
    "shared/errors.py": "services/{s}/app/errors.py",
    "shared/openapi_conformance.py": "services/{s}/tests/openapi_conformance.py",
    "shared/tests/test_errors.py": "services/{s}/tests/test_shared_errors.py",
    "shared/tests/test_openapi_conformance.py": "services/{s}/tests/test_shared_openapi_conformance.py",
}


def check(root: Path) -> tuple[list[str], list[str]]:
    """Return (problems, notes)."""
    problems: list[str] = []
    notes: list[str] = []
    for canonical, template in COPY_MAP.items():
        canon = root / canonical
        copies = [template.format(s=s) for s in SERVICES]
        if canon.is_file():
            data = canon.read_bytes()
            for copy in copies:
                path = root / copy
                if not path.is_file():
                    problems.append(f"{copy}: missing (copy of {canonical})")
                elif path.read_bytes() != data:
                    problems.append(f"{copy}: differs from {canonical}")
        else:
            present = [c for c in copies if (root / c).exists()]
            if present:
                for copy in present:
                    problems.append(f"{copy}: exists but canonical {canonical} is missing")
            else:
                notes.append(f"{canonical}: not created yet")
    return problems, notes


def _write(root: Path, rel: str, data: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def self_test() -> int:
    failures: list[str] = []

    def case(
        name: str, build: Callable[[Path], None], expect_ok: bool, expect_text: str = ""
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root)
            problems, notes = check(root)
            ok = not problems
            text = "\n".join(problems + notes)
            if ok != expect_ok or expect_text not in text:
                failures.append(f"{name}: ok={ok} (wanted {expect_ok}), text={text!r}")

    def identical(root: Path) -> None:
        for canonical, template in COPY_MAP.items():
            _write(root, canonical, b"same\n")
            for s in SERVICES:
                _write(root, template.format(s=s), b"same\n")

    def nothing(root: Path) -> None:
        pass

    def differs(root: Path) -> None:
        identical(root)
        _write(root, "services/dashboard/app/errors.py", b"changed\n")

    def one_byte(root: Path) -> None:
        identical(root)
        _write(root, "services/artifact-store/tests/openapi_conformance.py", b"same")

    def missing_copy(root: Path) -> None:
        identical(root)
        (root / "services/release-service/tests/test_shared_errors.py").unlink()

    def orphan_copy(root: Path) -> None:
        _write(root, "services/pipeline-runner/app/errors.py", b"x\n")

    case("none exist passes", nothing, True, "shared/errors.py: not created yet")
    case("identical passes", identical, True)
    case("differing copy fails", differs, False, "services/dashboard/app/errors.py: differs")
    case("one-byte difference fails", one_byte, False, "artifact-store/tests/openapi_conformance.py")
    case("missing copy fails", missing_copy, False, "test_shared_errors.py: missing")
    case("copy without canonical fails", orphan_copy, False, "canonical shared/errors.py is missing")

    for line in failures:
        print(f"self-test FAILED: {line}")
    if not failures:
        print("self-test ok (6 cases)")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    root = Path(__file__).resolve().parents[2]
    if "--root" in argv:
        root = Path(argv[argv.index("--root") + 1])
    problems, notes = check(root)
    for note in notes:
        print(note)
    for problem in problems:
        print(f"FAIL {problem}")
    if problems:
        print(f"{len(problems)} problem(s)")
        return 1
    print("shared copies ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
