"""The wave 2 slice through all four real services (T028).

Every response goes through Stack.call, which validates it against its contract. Pipeline names
differ per test so artifact versions are predictable: shipyard-api is uploaded only by the main
flow, so its artifact is version 1 (Q-34: one artifact per passed build, named after the pipeline).
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

import httpx
import pytest

from contract import ContractError, Contracts
from stack import Stack

PASSING = [("install", "pip install -r requirements.txt"), ("test", "pytest")]
FAILING = [("install", "pip install -r requirements.txt"), ("test", "fail"), ("package", "make")]
RELEASE_VIEW_KEYS = {
    "release_id",
    "artifact",
    "status",
    "requested_by",
    "requested_at",
    "decided_by",
    "decided_at",
}


def request_release(stack: Stack, name: str, version: int, by: str) -> dict[str, Any]:
    r = stack.call(
        "release-service",
        "POST",
        "/releases",
        json={"artifact": {"name": name, "version": version}, "requested_by": by},
    )
    assert r.status_code == 201, r.text
    release: dict[str, Any] = r.json()
    assert release["status"] == "pending"
    return release


def decide(stack: Stack, release_id: str, decision: str, by: str) -> dict[str, Any]:
    r = stack.call(
        "release-service",
        "POST",
        f"/releases/{release_id}/decision",
        json={"decision": decision, "decided_by": by},
    )
    assert r.status_code == 200, r.text
    release: dict[str, Any] = r.json()
    return release


def test_passed_build_upload_release_approve_promote(stack: Stack) -> None:
    accepted = stack.start_run("shipyard-api", PASSING)
    build_id = accepted["build_id"]
    assert accepted["status"] == "running"
    assert [s["status"] for s in accepted["steps"]] == ["pending", "pending"]

    run = stack.wait_run(build_id)
    assert run["status"] == "passed"
    assert run["failed_step"] is None and run["failure_reason"] is None
    assert [s["status"] for s in run["steps"]] == ["passed", "passed"]

    # The one fake artifact, named after the pipeline, version 1 (first shipyard-api upload).
    r = stack.call("artifact-store", "GET", "/artifacts/shipyard-api/versions/1")
    assert r.status_code == 200
    assert r.content, "artifact body is empty"
    checksum = r.headers["X-Checksum-SHA256"]
    assert hashlib.sha256(r.content).hexdigest() == checksum

    release = request_release(stack, "shipyard-api", 1, "sam")
    rid = release["release_id"]
    assert release["requested_by"] == "sam"
    assert release["decided_by"] is None and release["promoted_at"] is None

    approved = decide(stack, rid, "approved", "dana")
    assert approved["status"] == "approved" and approved["decided_by"] == "dana"

    first = stack.call("release-service", "POST", f"/releases/{rid}/promote")
    assert first.status_code == 200, first.text
    assert first.json()["promoted_at"] is not None
    second = stack.call("release-service", "POST", f"/releases/{rid}/promote")
    assert second.status_code == 200, second.text
    assert second.json() == first.json()  # Q-31: unchanged, first promoted_at kept

    # Dashboard: build passed, the artifact, the release approved (no promotion field, Q-14).
    view = stack.wait_dashboard(
        "builds", lambda b: b["build_id"] == build_id and b["status"] == "passed"
    )
    assert view["pipeline_name"] == "shipyard-api"
    assert view["steps"] == run["steps"]
    assert view["finished_at"] == run["finished_at"]
    assert any(b["build_id"] == build_id for b in stack.dashboard_items("builds", status="passed"))

    artifact = stack.wait_dashboard("artifacts", lambda a: a["build_id"] == build_id)
    assert artifact["name"] == "shipyard-api" and artifact["version"] == 1
    assert artifact["checksum"] == checksum
    assert artifact["size_bytes"] == len(r.content)

    rel = stack.wait_dashboard(
        "releases", lambda x: x["release_id"] == rid and x["status"] == "approved"
    )
    assert rel["artifact"] == {"name": "shipyard-api", "version": 1}
    assert rel["requested_by"] == "sam" and rel["decided_by"] == "dana"
    assert rel["requested_at"] == release["requested_at"]
    assert rel["decided_at"] == approved["decided_at"]
    assert set(rel) == RELEASE_VIEW_KEYS  # no promoted_at
    assert "promoted_at" not in rel


def test_second_promote_is_200_unchanged(stack: Stack) -> None:
    rid = request_release(stack, "shipyard-web", 4, "sam")["release_id"]
    decide(stack, rid, "approved", "dana")
    first = stack.call("release-service", "POST", f"/releases/{rid}/promote")
    assert first.status_code == 200
    promoted_at = first.json()["promoted_at"]
    assert promoted_at is not None
    for _ in range(2):
        again = stack.call("release-service", "POST", f"/releases/{rid}/promote")
        assert again.status_code == 200
        assert again.json() == first.json()
    got = stack.call("release-service", "GET", f"/releases/{rid}")
    assert got.json() == first.json()
    assert got.json()["promoted_at"] == promoted_at


def test_failed_step_uploads_nothing_and_shows_in_failures(stack: Stack) -> None:
    name = "shipyard-fails"
    build_id = stack.start_run(name, FAILING)["build_id"]
    run = stack.wait_run(build_id)
    assert run["status"] == "failed"
    assert run["failed_step"] == "test"
    assert run["failure_reason"] is None
    assert [s["status"] for s in run["steps"]] == ["passed", "failed", "skipped"]

    view = stack.wait_dashboard(
        "builds", lambda b: b["build_id"] == build_id and b["status"] == "failed", status="failed"
    )
    assert view["failed_step"] == "test" and view["failure_reason"] is None
    assert view["steps"] == run["steps"]
    passed = stack.dashboard_items("builds", status="passed")
    assert all(b["build_id"] != build_id for b in passed)

    # Nothing uploaded (Q-34): no version of the pipeline's artifact, nothing on the dashboard.
    r = stack.call("artifact-store", "GET", f"/artifacts/{name}/versions/1")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    artifacts = stack.dashboard_items("artifacts")
    assert all(a["build_id"] != build_id and a["name"] != name for a in artifacts)


@pytest.mark.parametrize("name", ["bad name", "-app", "a" * 101, "", "app/x", "shipyard-api\n"])
def test_bad_pipeline_name_is_422(stack: Stack, name: str) -> None:
    before = len(stack.dashboard_items("builds"))
    r = stack.call(
        "pipeline-runner",
        "POST",
        "/runs",
        json={"name": name, "steps": [{"name": "a", "command": "b"}]},
    )
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert error["code"] == "validation_failed"
    assert any(d["location"] == "body.name" for d in error["details"])
    # No run created: no build.started reaches the dashboard.
    assert len(stack.dashboard_items("builds")) == before


def test_rejected_release_cannot_be_promoted(stack: Stack) -> None:
    rid = request_release(stack, "shipyard-web", 5, "sam")["release_id"]
    rejected = decide(stack, rid, "rejected", "lee")
    assert rejected["status"] == "rejected" and rejected["decided_by"] == "lee"

    r = stack.call("release-service", "POST", f"/releases/{rid}/promote")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "release_not_approved"
    got = stack.call("release-service", "GET", f"/releases/{rid}").json()
    assert got["status"] == "rejected" and got["promoted_at"] is None

    again = stack.call(
        "release-service",
        "POST",
        f"/releases/{rid}/decision",
        json={"decision": "approved", "decided_by": "dana"},
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "release_already_decided"

    rel = stack.wait_dashboard(
        "releases", lambda x: x["release_id"] == rid and x["status"] == "rejected"
    )
    assert rel["decided_by"] == "lee" and rel["requested_by"] == "sam"


def test_dashboard_serves_the_ui(stack: Stack) -> None:
    r = stack.call("dashboard", "GET", "/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<html" in r.text.lower()
    assert "/static/app.js" in r.text
    js = stack.call("dashboard", "GET", "/static/app.js")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]


def test_every_response_validates_against_contract_schema(stack: Stack) -> None:
    """Each operation of the four contracts, with every status reachable without 100 MiB bodies.

    Stack.call raises ContractError for a body, header or status the contract does not allow; the
    assertions here only check that the intended status was reached.
    """
    seen: list[tuple[str, str, str, int]] = []

    def call(service: str, method: str, path: str, expect: int, **kw: Any) -> Any:
        r = stack.call(service, method, path, **kw)
        assert r.status_code == expect, f"{service} {method} {path}: {r.status_code} {r.text}"
        seen.append((service, method, path, expect))
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r

    unknown = str(uuid.uuid4())
    # pipeline-runner
    run = call(
        "pipeline-runner",
        "POST",
        "/runs",
        202,
        json={"name": "contract-check", "steps": [{"name": "build", "command": "make"}]},
    )
    call("pipeline-runner", "POST", "/runs", 422, json={"name": "contract-check", "steps": []})
    call(
        "pipeline-runner",
        "POST",
        "/runs",
        422,
        json={"name": "x", "steps": [{"name": "a", "command": "b"}, {"name": "a", "command": "c"}]},
    )
    call(
        "pipeline-runner",
        "POST",
        "/runs",
        422,
        content=b"{not json",
        headers={"content-type": "application/json"},
    )
    stack.wait_run(run["build_id"])
    call("pipeline-runner", "GET", f"/runs/{run['build_id']}", 200)
    call("pipeline-runner", "GET", f"/runs/{unknown}", 404)
    call("pipeline-runner", "GET", "/runs/not-a-uuid", 422)

    # artifact-store
    body = b"contract check bytes\n"
    digest = hashlib.sha256(body).hexdigest()
    stored = call(
        "artifact-store",
        "POST",
        f"/artifacts/contract-direct?build_id={unknown}",
        201,
        content=body,
        headers={"content-type": "application/octet-stream", "X-Checksum-SHA256": digest},
    )
    assert stored["checksum"] == digest and stored["size_bytes"] == len(body)
    mismatch = call(
        "artifact-store",
        "POST",
        f"/artifacts/contract-direct?build_id={unknown}",
        422,
        content=body,
        headers={"X-Checksum-SHA256": "0" * 64},
    )
    assert mismatch["error"]["code"] == "checksum_mismatch"
    call("artifact-store", "POST", "/artifacts/contract-direct", 422, content=body)
    call("artifact-store", "POST", f"/artifacts/-bad?build_id={unknown}", 422, content=body)
    dl = call(
        "artifact-store", "GET", f"/artifacts/contract-direct/versions/{stored['version']}", 200
    )
    assert dl.content == body and dl.headers["X-Checksum-SHA256"] == digest
    call("artifact-store", "GET", "/artifacts/contract-direct/versions/999", 404)
    call("artifact-store", "GET", "/artifacts/contract-direct/versions/0", 422)
    call("artifact-store", "GET", "/artifacts/contract-direct/versions/x", 422)

    # release-service
    rel = call(
        "release-service",
        "POST",
        "/releases",
        201,
        json={"artifact": {"name": "contract-direct", "version": 1}, "requested_by": "sam"},
    )
    rid = rel["release_id"]
    call(
        "release-service",
        "POST",
        "/releases",
        422,
        json={"artifact": {"name": "contract-direct", "version": 0}, "requested_by": "sam"},
    )
    call(
        "release-service",
        "POST",
        "/releases",
        422,
        json={"artifact": {"name": "contract-direct", "version": 1}},
    )
    call("release-service", "GET", f"/releases/{rid}", 200)
    call("release-service", "GET", f"/releases/{unknown}", 404)
    call("release-service", "GET", "/releases/nope", 422)
    call("release-service", "POST", f"/releases/{rid}/promote", 409)
    call("release-service", "POST", f"/releases/{unknown}/promote", 404)
    call("release-service", "POST", "/releases/nope/promote", 422)
    call(
        "release-service",
        "POST",
        f"/releases/{rid}/decision",
        422,
        json={"decision": "maybe", "decided_by": "dana"},
    )
    call(
        "release-service",
        "POST",
        f"/releases/{unknown}/decision",
        404,
        json={"decision": "approved", "decided_by": "dana"},
    )
    call(
        "release-service",
        "POST",
        "/releases/nope/decision",
        422,
        json={"decision": "approved", "decided_by": "dana"},
    )
    call(
        "release-service",
        "POST",
        f"/releases/{rid}/decision",
        200,
        json={"decision": "approved", "decided_by": "dana"},
    )
    call(
        "release-service",
        "POST",
        f"/releases/{rid}/decision",
        409,
        json={"decision": "rejected", "decided_by": "lee"},
    )
    call("release-service", "POST", f"/releases/{rid}/promote", 200)

    # dashboard
    event = {
        "event_id": str(uuid.uuid4()),
        "type": "build.started",
        "schema_version": 1,
        "occurred_at": "2026-01-01T00:00:00Z",
        "source": "pipeline-runner",
        "data": {"build_id": str(uuid.uuid4()), "pipeline_name": "contract-event"},
    }
    call("dashboard", "POST", "/events", 202, json=event)
    call("dashboard", "POST", "/events", 202, json=event)  # repeated event_id: still 202
    call("dashboard", "POST", "/events", 422, json={**event, "type": "build.cancelled"})
    for view in ("builds", "artifacts", "releases"):
        call("dashboard", "GET", f"/{view}", 200)
        call("dashboard", "GET", f"/{view}?limit=1&offset=1", 200)
        call("dashboard", "GET", f"/{view}?limit=201", 422)
    for status in ("running", "passed", "failed"):
        call("dashboard", "GET", f"/builds?status={status}", 200)
    call("dashboard", "GET", "/builds?status=nope", 422)

    # Every operation of every contract was exercised at least once.
    ops = stack.contracts.operations()
    hit = {(svc, m, stack.contracts.template(svc, m, p.split("?")[0])) for svc, m, p, _ in seen}
    assert ops <= hit, f"operations not exercised: {sorted(ops - hit)}"


def test_contract_checker_rejects_what_the_contract_forbids(contracts: Contracts) -> None:
    """The checker is not vacuous: an undocumented status and a wrong body both fail."""
    request = httpx.Request("GET", "http://127.0.0.1:1/builds")
    with pytest.raises(ContractError, match="status not listed"):
        contracts.check("dashboard", httpx.Response(404, json={}, request=request))
    with pytest.raises(ContractError, match="does not match"):
        contracts.check(
            "dashboard",
            httpx.Response(
                200, json={"items": [{"x": 1}], "limit": 50, "offset": 0}, request=request
            ),
        )
    run_request = httpx.Request("GET", f"http://127.0.0.1:1/runs/{uuid.uuid4()}")
    bad_run = {
        "build_id": str(uuid.uuid4()),
        "pipeline_name": "x",
        "status": "passed",
        "created_at": "2026-01-01T00:00:00Z",
        "finished_at": None,  # passed requires finished_at (state table)
        "failed_step": None,
        "failure_reason": None,
        "steps": [
            {
                "name": "a",
                "status": "passed",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:01Z",
            }
        ],
    }
    with pytest.raises(ContractError, match="does not match"):
        contracts.check("pipeline-runner", httpx.Response(200, json=bad_run, request=run_request))
    with pytest.raises(ContractError, match="not in"):
        contracts.check(
            "pipeline-runner", httpx.Response(200, request=httpx.Request("GET", "http://x/nope"))
        )
