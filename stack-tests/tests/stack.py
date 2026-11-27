"""Start, stop and talk to the four-service stack of one SHIPYARD_SLOT."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from contract import Contracts

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "dev"
SERVICES = ("pipeline-runner", "artifact-store", "release-service", "dashboard")

# Short simulated steps keep the suite fast; the start script passes the environment on.
DEFAULT_STEP_SECONDS = "0.05"


def slot_env() -> dict[str, str]:
    slot = os.environ.get("SHIPYARD_SLOT", "")
    if not slot.isdigit():
        raise RuntimeError(
            "set SHIPYARD_SLOT to your slot number (0-99); stack-tests never default it"
        )
    env = dict(os.environ)
    env["SHIPYARD_SLOT"] = slot
    env.setdefault("PIPELINE_RUNNER_STEP_SECONDS", DEFAULT_STEP_SECONDS)
    return env


def read_ports(env: dict[str, str]) -> dict[str, str]:
    """The URLs and data dir that scripts/dev/ports.sh derives for the slot."""
    out = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1" && printf "%s\\n" "$PIPELINE_RUNNER_URL" "$ARTIFACT_STORE_URL" '
            '"$RELEASE_SERVICE_URL" "$DASHBOARD_URL" "$SHIPYARD_DATA_DIR"',
            "ports",
            str(SCRIPTS / "ports.sh"),
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split("\n")
    return dict(zip([*SERVICES, "data_dir"], out[:5], strict=True))


def run_script(name: str, env: dict[str, str], timeout: float = 300) -> None:
    proc = subprocess.run(
        [str(SCRIPTS / name)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{name} exited {proc.returncode}\n{proc.stdout}\n{proc.stderr}")


def port_open(url: str) -> bool:
    parsed = httpx.URL(url)
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((parsed.host, parsed.port or 80)) == 0


def poll[T](fn: Callable[[], T | None], timeout: float, what: str, interval: float = 0.1) -> T:
    """Call fn until it returns something other than None; fail after `timeout` seconds."""
    deadline = time.monotonic() + timeout
    last: T | None = None
    while True:
        last = fn()
        if last is not None:
            return last
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out after {timeout} s waiting for {what}")
        time.sleep(interval)


@dataclass
class Stack:
    env: dict[str, str]
    urls: dict[str, str]
    data_dir: Path
    contracts: Contracts
    clients: dict[str, httpx.Client] = field(default_factory=dict)

    def client(self, service: str) -> httpx.Client:
        if service not in self.clients:
            self.clients[service] = httpx.Client(base_url=self.urls[service], timeout=15)
        return self.clients[service]

    def call(self, service: str, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """One request; the response is always checked against the service's contract."""
        response = self.client(service).request(method, path, **kwargs)
        self.contracts.check(service, response)
        return response

    def close(self) -> None:
        for c in self.clients.values():
            c.close()
        self.clients.clear()

    # ------------------------------------------------------------------ flows
    def start_run(self, name: str, commands: list[tuple[str, str]]) -> dict[str, Any]:
        body = {"name": name, "steps": [{"name": n, "command": c} for n, c in commands]}
        r = self.call("pipeline-runner", "POST", "/runs", json=body)
        assert r.status_code == 202, r.text
        run: dict[str, Any] = r.json()
        return run

    def wait_run(self, build_id: str, timeout: float = 30) -> dict[str, Any]:
        def final() -> dict[str, Any] | None:
            r = self.call("pipeline-runner", "GET", f"/runs/{build_id}")
            assert r.status_code == 200, r.text
            run: dict[str, Any] = r.json()
            return run if run["status"] != "running" else None

        return poll(final, timeout, f"run {build_id} to finish")

    def dashboard_items(self, view: str, **params: Any) -> list[dict[str, Any]]:
        """Every item of a dashboard view (pages of 200)."""
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            r = self.call(
                "dashboard", "GET", f"/{view}", params={**params, "limit": 200, "offset": offset}
            )
            assert r.status_code == 200, r.text
            page = r.json()["items"]
            items.extend(page)
            if len(page) < 200:
                return items
            offset += 200

    def wait_dashboard(
        self,
        view: str,
        match: Callable[[dict[str, Any]], bool],
        timeout: float = 20,
        **params: Any,
    ) -> dict[str, Any]:
        def find() -> dict[str, Any] | None:
            hits = [i for i in self.dashboard_items(view, **params) if match(i)]
            assert len(hits) <= 1, f"{view}: more than one match: {hits}"
            return hits[0] if hits else None

        return poll(find, timeout, f"dashboard /{view} to show the item")
