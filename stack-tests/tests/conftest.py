"""Session fixture: the real stack of SHIPYARD_SLOT, started with scripts/dev/start-stack.sh.

SHIPYARD_SLOT is required (never defaulted: slot 0 is the lead's). The stack is stopped with
stop-stack.sh at the end; logs stay in the slot's data dir for debugging.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from contract import Contracts
from stack import Stack, read_ports, run_script, slot_env

STOPS_DASHBOARD = "stops_dashboard"
STOPS_ARTIFACT_STORE = "stops_artifact_store"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{STOPS_DASHBOARD}: pauses the dashboard (SIGSTOP, then SIGCONT), so it runs after the "
        "ordinary tests and before the ones that stop artifact-store",
    )
    config.addinivalue_line(
        "markers",
        f"{STOPS_ARTIFACT_STORE}: stops artifact-store, so it runs after every other test",
    )


def _order(item: pytest.Item) -> int:
    if item.get_closest_marker(STOPS_ARTIFACT_STORE) is not None:
        return 2  # artifact-store never comes back: last
    if item.get_closest_marker(STOPS_DASHBOARD) is not None:
        return 1  # the dashboard comes back, but events sent meanwhile may be lost
    return 0


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # Stable sort: tests that disturb the stack go last, whatever order they were collected in.
    items.sort(key=_order)


@pytest.fixture(scope="session")
def contracts() -> Contracts:
    return Contracts()


@pytest.fixture(scope="session")
def stack(contracts: Contracts) -> Iterator[Stack]:
    env = slot_env()
    ports = read_ports(env)
    run_script("start-stack.sh", env)
    s = Stack(
        env=env,
        urls={k: v for k, v in ports.items() if k != "data_dir"},
        data_dir=Path(ports["data_dir"]),
        contracts=contracts,
    )
    try:
        yield s
    finally:
        s.close()
        run_script("stop-stack.sh", env)
