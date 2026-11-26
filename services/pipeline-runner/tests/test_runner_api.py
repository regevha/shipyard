from __future__ import annotations

import uuid
from typing import Any

import pytest
from conftest import Fakes, steps_body
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openapi_conformance import find_contract, schema_validator

RUN = schema_validator(find_contract("api-pipeline-runner.yml"), "#/components/schemas/Run")
ERROR = schema_validator(find_contract("errors.yml"), "errors.yml#/$defs/ErrorEnvelope")


def test_q28_start_run_is_202_with_build_id(client: TestClient) -> None:
    response = client.post("/runs", json=steps_body("echo", "echo"))
    assert response.status_code == 202
    body = response.json()
    assert str(uuid.UUID(body["build_id"])) == body["build_id"]
    assert body["pipeline_name"] == "shipyard-api"
    # the 202 shows the run as accepted, before any step ran
    assert body["status"] == "running"
    assert [s["status"] for s in body["steps"]] == ["pending", "pending"]
    assert body["finished_at"] is None and body["failed_step"] is None
    assert body["failure_reason"] is None
    assert "run_id" not in body


def test_q28_get_run_by_build_id(client: TestClient) -> None:
    build_id = client.post("/runs", json=steps_body("echo")).json()["build_id"]
    response = client.get(f"/runs/{build_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["build_id"] == build_id
    assert body["status"] == "passed"  # the background task has finished
    assert body["steps"][0]["status"] == "passed"


def test_get_unknown_build_id_is_404(client: TestClient) -> None:
    missing = uuid.uuid4()
    response = client.get(f"/runs/{missing}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    ERROR.validate(response.json())


@pytest.mark.parametrize("bad", ["abc", "123", "5d0c6f1e-2b7a-4c39-9e8d"])
def test_get_malformed_build_id_is_422(client: TestClient, bad: str) -> None:
    response = client.get(f"/runs/{bad}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"
    ERROR.validate(response.json())


@pytest.mark.parametrize(
    "name", ["my pipeline", "a/b", "-x", ".x", "", "a" * 101, "app\n", "_x", "é"]
)
def test_n119_bad_pipeline_name_is_422_and_no_run(
    client: TestClient, app: FastAPI, fakes: Fakes, name: str
) -> None:
    response = client.post("/runs", json=steps_body("echo", name=name))
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["location"] == "body.name"
    ERROR.validate(response.json())
    assert app.state.repo.count() == 0
    assert fakes.calls == []  # nothing uploaded, no event


@pytest.mark.parametrize("name", ["a", "0", "Web_2.1", "x" * 100, "shipyard-api"])
def test_n119_good_pipeline_names_are_accepted(client: TestClient, name: str) -> None:
    assert client.post("/runs", json=steps_body("echo", name=name)).status_code == 202


def test_duplicate_step_names_are_422(client: TestClient, app: FastAPI) -> None:
    body = {
        "name": "p",
        "steps": [{"name": "a", "command": "x"}, {"name": "a", "command": "y"}],
    }
    response = client.post("/runs", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["location"] == "body.steps"
    assert app.state.repo.count() == 0


def test_empty_steps_are_422(client: TestClient) -> None:
    response = client.post("/runs", json={"name": "p", "steps": []})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["location"] == "body.steps"


@pytest.mark.parametrize(
    "body",
    [
        {"name": "p"},
        {"name": "p", "steps": [{"name": "", "command": "x"}]},
        {"name": "p", "steps": [{"name": "a", "command": ""}]},
        {"name": "p", "steps": [{"name": "a", "command": "x", "extra": 1}]},
        {"name": "p", "steps": [{"name": "a", "command": "x"}], "extra": 1},
        [],
    ],
)
def test_invalid_definitions_are_422(client: TestClient, body: Any) -> None:
    response = client.post("/runs", json=body)
    assert response.status_code == 422
    ERROR.validate(response.json())


def test_invalid_json_is_422(client: TestClient) -> None:
    response = client.post("/runs", content=b"{", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["location"] == "body"


def test_wrong_method_is_405_and_unknown_path_404(client: TestClient) -> None:
    assert client.delete("/runs").status_code == 405
    assert client.get("/runs").status_code == 405
    assert client.get("/nope").status_code == 404


def test_every_response_validates_against_contract_schema(client: TestClient) -> None:
    accepted = client.post("/runs", json=steps_body("a", "b"))
    RUN.validate(accepted.json())
    passed = client.get(f"/runs/{accepted.json()['build_id']}")
    RUN.validate(passed.json())
    failed_body = client.post("/runs", json=steps_body("a", "fail", "c")).json()
    failed = client.get(f"/runs/{failed_body['build_id']}")
    RUN.validate(failed.json())
    assert failed.json()["status"] == "failed"
    for response in (
        client.get(f"/runs/{uuid.uuid4()}"),
        client.get("/runs/zzz"),
        client.post("/runs", json={}),
    ):
        ERROR.validate(response.json())
