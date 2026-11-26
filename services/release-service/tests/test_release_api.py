"""Acceptance tests of contracts/api-release-service.yml (Q-10, Q-16, Q-30, Q-31, error order)."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from conftest import Fakes, decide, make_release, request_body
from fastapi.testclient import TestClient
from openapi_conformance import find_contract, schema_validator

from app.core.config import Settings
from app.main import create_app

UNKNOWN = "11111111-2222-4333-8444-555555555555"
TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z$")


def error_code(response: Any) -> str:
    code: str = response.json()["error"]["code"]
    return code


def test_q30_request_is_201_pending_with_requested_by(client: TestClient) -> None:
    response = client.post("/releases", json=request_body(requested_by="any free text 42"))
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["requested_by"] == "any free text 42"
    assert body["artifact"] == {"name": "shipyard-api", "version": 3}
    assert TIMESTAMP.match(body["requested_at"])
    assert body["decided_by"] is None and body["decided_at"] is None and body["promoted_at"] is None
    assert client.get(f"/releases/{body['release_id']}").json() == body


@pytest.mark.parametrize("bad", [None, "", 5, True, ["sam"]])
def test_q30_missing_or_empty_requested_by_is_422(client: TestClient, bad: Any) -> None:
    body = request_body()
    body["requested_by"] = bad
    assert client.post("/releases", json=body).status_code == 422
    del body["requested_by"]
    response = client.post("/releases", json=body)
    assert response.status_code == 422
    assert error_code(response) == "validation_failed"


@pytest.mark.parametrize(
    "name", ["a/b", "my app", "", "-app", ".app", "a" * 101, "app\n", 5, None, ["a"]]
)
def test_request_bad_artifact_name_is_422(client: TestClient, name: Any) -> None:
    body = request_body()
    body["artifact"]["name"] = name
    response = client.post("/releases", json=body)
    assert response.status_code == 422
    assert error_code(response) == "validation_failed"


def test_request_name_boundaries_are_accepted(client: TestClient) -> None:
    for name in ["a", "0", "Web_2.1", "a" * 100]:
        assert client.post("/releases", json=request_body(name=name)).status_code == 201


@pytest.mark.parametrize("version", [0, -1, "3", True, False, 3.0, 3.5, None, [3]])
def test_request_version_is_strict_integer_at_least_one(client: TestClient, version: Any) -> None:
    body = request_body()
    body["artifact"]["version"] = version
    assert client.post("/releases", json=body).status_code == 422


def test_request_huge_version_is_accepted_and_round_trips(client: TestClient) -> None:
    for version in (2**63, 2**200):
        release = make_release(client, version=version)
        assert release["artifact"]["version"] == version
        assert client.get(f"/releases/{release['release_id']}").json()["artifact"]["version"] == (
            version
        )


def test_request_rejects_extra_fields_and_bad_bodies(client: TestClient) -> None:
    body = request_body()
    assert client.post("/releases", json={**body, "requested_at": "x"}).status_code == 422
    assert client.post("/releases", json={**body, "status": "approved"}).status_code == 422
    assert client.post("/releases", content=b"{not json").status_code == 422
    assert client.post("/releases", json=[1]).status_code == 422
    assert client.post("/releases").status_code == 422


def test_q10_approve_records_decided_by_and_decided_at(client: TestClient) -> None:
    release = make_release(client)
    response = decide(client, release["release_id"], "approved", "dana")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["decided_by"] == "dana"
    assert TIMESTAMP.match(body["decided_at"])
    assert body["promoted_at"] is None
    assert body["requested_by"] == "sam"  # no self-approval rule
    assert client.get(f"/releases/{release['release_id']}").json() == body
    assert decide(client, make_release(client)["release_id"], "approved", "sam").status_code == 200


def test_q10_reject_stays_rejected(client: TestClient) -> None:
    release = make_release(client)
    response = decide(client, release["release_id"], "rejected", "lee")
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["decided_by"] == "lee"
    again = decide(client, release["release_id"], "approved", "dana")
    assert again.status_code == 409
    after = client.get(f"/releases/{release['release_id']}").json()
    assert after["status"] == "rejected" and after["decided_by"] == "lee"


def test_q10_second_decision_is_409_release_already_decided(client: TestClient) -> None:
    release = make_release(client)
    first = decide(client, release["release_id"], "approved", "dana").json()
    for decision in ("approved", "rejected"):
        response = decide(client, release["release_id"], decision, "other")
        assert response.status_code == 409
        assert error_code(response) == "release_already_decided"
        assert release["release_id"] in response.json()["error"]["message"]
    assert client.get(f"/releases/{release['release_id']}").json() == first


@pytest.mark.parametrize(
    "value", ["approve", "Approved", "pending", "", None, 1, True, ["approved"]]
)
def test_decision_enum_rejects_values_outside_the_contract(client: TestClient, value: Any) -> None:
    release = make_release(client)
    response = client.post(
        f"/releases/{release['release_id']}/decision",
        json={"decision": value, "decided_by": "dana"},
    )
    assert response.status_code == 422
    assert client.get(f"/releases/{release['release_id']}").json()["status"] == "pending"


@pytest.mark.parametrize("value", ["approved", "rejected"])
def test_decision_enum_accepts_every_contract_value(client: TestClient, value: str) -> None:
    release = make_release(client)
    assert decide(client, release["release_id"], value).json()["status"] == value


@pytest.mark.parametrize("by", [None, "", 7, False, ["x"]])
def test_decision_decided_by_is_a_strict_non_empty_string(client: TestClient, by: Any) -> None:
    release = make_release(client)
    response = client.post(
        f"/releases/{release['release_id']}/decision",
        json={"decision": "approved", "decided_by": by},
    )
    assert response.status_code == 422


def test_decision_rejects_extra_and_missing_fields(client: TestClient) -> None:
    rid = make_release(client)["release_id"]
    url = f"/releases/{rid}/decision"
    assert client.post(url, json={"decision": "approved"}).status_code == 422
    assert client.post(url, json={"decided_by": "d"}).status_code == 422
    body = {"decision": "approved", "decided_by": "d", "decided_at": "2026-01-01T00:00:00Z"}
    assert client.post(url, json=body).status_code == 422
    assert client.post(url).status_code == 422
    assert client.get(f"/releases/{rid}").json()["status"] == "pending"


def test_q16_promote_pending_is_409_release_not_approved(client: TestClient) -> None:
    release = make_release(client)
    response = client.post(f"/releases/{release['release_id']}/promote")
    assert response.status_code == 409
    assert error_code(response) == "release_not_approved"
    assert client.get(f"/releases/{release['release_id']}").json()["promoted_at"] is None


def test_q16_promote_rejected_is_409_release_not_approved(client: TestClient) -> None:
    release = make_release(client)
    decide(client, release["release_id"], "rejected")
    response = client.post(f"/releases/{release['release_id']}/promote")
    assert response.status_code == 409
    assert error_code(response) == "release_not_approved"
    assert client.get(f"/releases/{release['release_id']}").json()["promoted_at"] is None


def test_q16_promote_approved_sets_promoted_at(client: TestClient) -> None:
    release = make_release(client)
    approved = decide(client, release["release_id"]).json()
    response = client.post(f"/releases/{release['release_id']}/promote")
    assert response.status_code == 200
    body = response.json()
    assert TIMESTAMP.match(body["promoted_at"])
    assert {**body, "promoted_at": None} == approved
    assert client.get(f"/releases/{release['release_id']}").json() == body


def test_q31_second_promote_is_200_unchanged(client: TestClient) -> None:
    release = make_release(client)
    decide(client, release["release_id"])
    first = client.post(f"/releases/{release['release_id']}/promote")
    second = client.post(f"/releases/{release['release_id']}/promote")
    assert second.status_code == 200
    assert second.json() == first.json()
    assert client.get(f"/releases/{release['release_id']}").json() == first.json()


def test_get_unknown_release_is_404(client: TestClient) -> None:
    response = client.get(f"/releases/{UNKNOWN}")
    assert response.status_code == 404
    assert error_code(response) == "not_found"
    assert UNKNOWN in response.json()["error"]["message"]


def test_decide_error_precedence(client: TestClient) -> None:
    release = make_release(client)
    rid = release["release_id"]
    bad_body = {"decision": "maybe"}
    # 422 path before 404 and body
    assert client.post("/releases/not-a-uuid/decision", json=bad_body).status_code == 422
    # 404 before 422 body (also for a body that is not even JSON)
    for kwargs in ({"json": bad_body}, {"content": b"{oops"}, {}):
        response = client.post(f"/releases/{UNKNOWN}/decision", **kwargs)
        assert response.status_code == 404, kwargs
        assert error_code(response) == "not_found"
    # 422 body before 409
    decide(client, rid, "approved")
    response = client.post(f"/releases/{rid}/decision", json=bad_body)
    assert response.status_code == 422
    assert error_code(response) == "validation_failed"
    # then 409
    assert decide(client, rid, "rejected").status_code == 409


def test_promote_error_precedence(client: TestClient) -> None:
    assert client.post("/releases/not-a-uuid/promote").status_code == 422
    assert client.post(f"/releases/{UNKNOWN}/promote").status_code == 404
    release = make_release(client)
    assert client.post(f"/releases/{release['release_id']}/promote").status_code == 409


@pytest.mark.parametrize("method", ["get", "post"])
def test_malformed_release_id_is_422_on_every_route(client: TestClient, method: str) -> None:
    for suffix in ("", "/decision", "/promote"):
        if method == "get" and suffix:
            continue
        response = getattr(client, method)(f"/releases/xyz{suffix}")
        if method == "post" and suffix == "":
            assert response.status_code == 405
            continue
        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["location"] == "path.release_id"


@pytest.mark.parametrize("path", [str(2**64), str(2**200), "-1", "0"])
def test_huge_or_odd_ids_are_422_never_500(client: TestClient, path: str) -> None:
    for call in (
        client.get(f"/releases/{path}"),
        client.post(f"/releases/{path}/promote"),
        client.post(f"/releases/{path}/decision", json={"decision": "approved", "decided_by": "d"}),
    ):
        assert call.status_code == 422


def test_every_response_validates_against_contract_schema(client: TestClient) -> None:
    contract = find_contract("api-release-service.yml")
    release_schema = schema_validator(contract, "#/components/schemas/Release")
    error_schema = schema_validator(contract, "errors.yml#/$defs/ErrorEnvelope")

    created = client.post("/releases", json=request_body())
    release_schema.validate(created.json())
    rid = created.json()["release_id"]
    release_schema.validate(client.get(f"/releases/{rid}").json())
    release_schema.validate(decide(client, rid).json())
    release_schema.validate(client.post(f"/releases/{rid}/promote").json())
    release_schema.validate(client.post(f"/releases/{rid}/promote").json())
    rejected = make_release(client)["release_id"]
    release_schema.validate(decide(client, rejected, "rejected").json())

    pending = make_release(client)["release_id"]
    errors = [
        client.get(f"/releases/{UNKNOWN}"),
        client.get("/releases/zzz"),
        client.post("/releases", json={}),
        decide(client, rid, "rejected"),
        client.post(f"/releases/{pending}/promote"),
        client.post(f"/releases/{rejected}/promote"),
    ]
    assert [r.status_code for r in errors] == [404, 422, 422, 409, 409, 409]
    for response in errors:
        error_schema.validate(response.json())


def test_contract_state_table_rejects_inconsistent_release() -> None:
    from jsonschema import ValidationError

    schema = schema_validator(
        find_contract("api-release-service.yml"), "#/components/schemas/Release"
    )
    body = {
        "release_id": UNKNOWN,
        "artifact": {"name": "a", "version": 1},
        "status": "pending",
        "requested_by": "s",
        "requested_at": "2026-11-25T10:10:00Z",
        "decided_by": "d",
        "decided_at": None,
        "promoted_at": None,
    }
    with pytest.raises(ValidationError):
        schema.validate(body)


def test_concurrent_decisions_have_exactly_one_winner(tmp_path: Path, fakes: Fakes) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/r.db", dashboard_url="http://dashboard.test"
    )
    with TestClient(create_app(settings, fakes.transport(), fakes.sleeps.append)) as client:
        rid = make_release(client)["release_id"]

        def attempt(i: int) -> int:
            decision = "approved" if i % 2 else "rejected"
            return decide(client, rid, decision, f"u{i}").status_code

        with ThreadPoolExecutor(20) as pool:
            codes = list(pool.map(attempt, range(40)))
        assert codes.count(200) == 1 and codes.count(409) == 39
        promotes = list(
            ThreadPoolExecutor(10).map(lambda _: client.post(f"/releases/{rid}/promote"), range(20))
        )
        released = client.get(f"/releases/{rid}").json()
        if released["status"] == "approved":
            assert {p.status_code for p in promotes} == {200}
            assert {p.json()["promoted_at"] for p in promotes} == {released["promoted_at"]}
        else:
            assert {p.status_code for p in promotes} == {409}


def test_many_concurrent_requests_all_succeed_on_a_file_db(tmp_path: Path, fakes: Fakes) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/many.db", dashboard_url="http://dashboard.test"
    )
    with TestClient(create_app(settings, fakes.transport(), fakes.sleeps.append)) as client:
        with ThreadPoolExecutor(32) as pool:
            codes = list(
                pool.map(
                    lambda i: (
                        client.post("/releases", json=request_body(version=i + 1)).status_code
                    ),
                    range(150),
                )
            )
    assert codes == [201] * 150
