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

STOPS_ARTIFACT_STORE = "stops_artifact_store"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{STOPS_ARTIFACT_STORE}: stops artifact-store, so it runs after every other test",
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # Stable sort: tests that break the stack go last, whatever order they were collected in.
    items.sort(key=lambda item: item.get_closest_marker(STOPS_ARTIFACT_STORE) is not None)


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
