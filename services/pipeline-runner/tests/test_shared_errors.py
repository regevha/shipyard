"""Tests of app/errors.py (shared copy, T022): the error envelope of contracts/errors.yml."""

from __future__ import annotations

from typing import Any, get_args

import pytest
import yaml
from fastapi import FastAPI, Header, HTTPException, Path, Query
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from openapi_conformance import find_contract, schema_validator
from pydantic import BaseModel, Field
from starlette.staticfiles import StaticFiles

from app.errors import ALLOWED_PAIRS, ApiError, ErrorCode, ErrorDetail, ErrorEnvelope, install

ERRORS_YML = find_contract("errors.yml")


class Step(BaseModel):
    name: str = Field(min_length=1)


class Definition(BaseModel):
    steps: list[Step] = Field(min_length=1)


def make_app() -> FastAPI:
    app = FastAPI()

    @app.post("/definitions", status_code=201)
    def create(definition: Definition) -> dict[str, int]:
        return {"steps": len(definition.steps)}

    @app.get("/things/{name}")
    def thing(
        name: str = Path(pattern="^[a-z]+$"),
        build_id: int = Query(),
        x_checksum_sha256: str | None = Header(default=None, min_length=64),
    ) -> dict[str, str]:
        return {"name": name}

    @app.get("/raise/{kind}", responses={404: {"description": "No such thing"}})
    def raise_it(kind: str) -> dict[str, str]:
        if kind == "413":
            raise ApiError(413, "payload_too_large", "upload is larger than 104857600 bytes")
        if kind == "409":
            raise ApiError(409, "release_already_decided", "already decided")
        if kind == "422":
            raise ApiError(
                422, "validation_failed", "bad", [ErrorDetail(location="query.x", message="bad x")]
            )
        if kind == "400":
            raise HTTPException(400, "bad thing")
        if kind == "401":
            raise HTTPException(401, {"not": "a string"}, headers={"WWW-Authenticate": "Basic"})
        if kind == "503":
            raise HTTPException(503, "database password is hunter2")
        if kind == "boom":
            raise RuntimeError("secret internals: hunter2")
        raise ApiError(404, "not_found", f"thing {kind} not found")

    @app.get("/")
    def root() -> dict[str, str]:
        return {"ok": "yes"}

    install(app)
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(make_app(), raise_server_exceptions=False)


def assert_envelope(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/json"
    body: dict[str, Any] = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    schema_validator(ERRORS_YML, "#/$defs/ErrorEnvelope").validate(body)
    return body


def test_validation_error_is_422_envelope_with_dotted_location(client: TestClient) -> None:
    body = assert_envelope(
        client.post("/definitions", json={"steps": [{"name": "a"}, {"name": ""}]}),
        422,
        "validation_failed",
    )
    assert body["error"]["message"] == "request validation failed"
    assert [d["location"] for d in body["error"]["details"]] == ["body.steps.1.name"]

    locations = {
        d["location"]
        for d in assert_envelope(
            client.get("/things/ab1", headers={"X-Checksum-SHA256": "short"}),
            422,
            "validation_failed",
        )["error"]["details"]
    }
    assert {"query.build_id", "header.x-checksum-sha256"} <= locations
    assert_envelope(client.post("/definitions", json={"steps": []}), 422, "validation_failed")


def test_path_location_is_prefixed_with_path() -> None:
    app = FastAPI()

    @app.get("/n/{count}")
    def n(count: int) -> int:
        return count

    install(app)
    body = assert_envelope(TestClient(app).get("/n/x"), 422, "validation_failed")
    assert body["error"]["details"][0]["location"] == "path.count"


def test_invalid_json_body_is_422_validation_failed(client: TestClient) -> None:
    response = client.post(
        "/definitions", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    body = assert_envelope(response, 422, "validation_failed")
    assert body["error"]["details"] == [
        {"location": "body", "message": "request body is not valid JSON"}
    ]
    assert_envelope(client.post("/definitions"), 422, "validation_failed")


def test_unknown_path_is_404_not_found(client: TestClient) -> None:
    assert_envelope(client.get("/no/such/path"), 404, "not_found")


def test_unknown_path_with_static_mount_is_404_and_root_still_served(tmp_path: Any) -> None:
    (tmp_path / "app.js").write_text("x")
    app = make_app()
    app.mount("/static", StaticFiles(directory=tmp_path), name="static")
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/static/app.js").status_code == 200
    assert_envelope(client.get("/static/missing.js"), 404, "not_found")
    assert_envelope(client.get("/events"), 404, "not_found")
    assert client.get("/").json() == {"ok": "yes"}


def test_wrong_method_is_405_and_keeps_allow_header(client: TestClient) -> None:
    response = client.delete("/definitions")
    assert_envelope(response, 405, "method_not_allowed")
    assert "POST" in response.headers["allow"]


def test_api_error_413_payload_too_large(client: TestClient) -> None:
    body = assert_envelope(client.get("/raise/413"), 413, "payload_too_large")
    assert body["error"]["message"] == "upload is larger than 104857600 bytes"
    assert "details" not in body["error"]
    assert_envelope(client.get("/raise/409"), 409, "release_already_decided")
    detailed = assert_envelope(client.get("/raise/422"), 422, "validation_failed")
    assert detailed["error"]["details"] == [{"location": "query.x", "message": "bad x"}]
    assert_envelope(client.get("/raise/missing"), 404, "not_found")


def test_other_4xx_is_422_validation_failed(client: TestClient) -> None:
    body = assert_envelope(client.get("/raise/400"), 422, "validation_failed")
    assert body["error"]["message"] == "bad thing"
    response = client.get("/raise/401")
    body = assert_envelope(response, 422, "validation_failed")
    assert body["error"]["message"] == "request validation failed"
    assert response.headers["www-authenticate"] == "Basic"


def test_5xx_http_error_is_500_internal_error(client: TestClient) -> None:
    response = client.get("/raise/503")
    body = assert_envelope(response, 500, "internal_error")
    assert "hunter2" not in response.text
    assert body["error"]["message"] == "internal server error"


def test_unhandled_exception_is_500_internal_error(client: TestClient) -> None:
    response = client.get("/raise/boom")
    body = assert_envelope(response, 500, "internal_error")
    assert "hunter2" not in response.text and "RuntimeError" not in response.text
    assert body["error"]["message"] == "internal server error"


def test_validation_details_are_capped() -> None:
    app = FastAPI()

    @app.post("/many")
    def many(items: list[int]) -> int:
        return len(items)

    install(app)
    response = TestClient(app).post("/many", json=["x"] * 500)
    body = assert_envelope(response, 422, "validation_failed")
    assert len(body["error"]["details"]) == 100


def test_openapi_has_no_httpvalidationerror(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    assert "HTTPValidationError" not in spec["components"]["schemas"]
    assert "ValidationError" not in spec["components"]["schemas"]
    assert "HTTPValidationError" not in str(
        spec
    ) and "'#/components/schemas/ValidationError'" not in str(spec)
    assert "ErrorEnvelope" in spec["components"]["schemas"]
    app = make_app()
    assert app.openapi() is app.openapi()


def test_openapi_lists_envelope_for_422_500_and_declared_errors(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    envelope = {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorEnvelope"}}}
    for path, item in spec["paths"].items():
        for method, op in item.items():
            for status in ("422", "500"):
                assert op["responses"][status]["content"] == envelope, (method, path, status)
    declared = spec["paths"]["/raise/{kind}"]["get"]["responses"]["404"]
    assert declared == {"description": "No such thing", "content": envelope}
    assert spec["paths"]["/"]["get"]["responses"]["200"]["content"]["application/json"]


def test_status_code_pairs_match_errors_yml() -> None:
    contract = yaml.safe_load(ERRORS_YML.read_text(encoding="utf-8"))
    pairs = {(int(e["status"]), str(e["code"])) for e in contract["x-status-codes"]}
    assert pairs == set(ALLOWED_PAIRS)
    assert set(get_args(ErrorCode)) == set(contract["$defs"]["ErrorCode"]["enum"])
    with pytest.raises(ValueError):
        ApiError(400, "validation_failed", "no such pair")
    with pytest.raises(ValueError):
        ApiError(404, "not_found", "")
    for status, code in sorted(pairs):
        assert ApiError(status, code, "m").status == status  # type: ignore[arg-type]


def test_envelope_examples_of_errors_yml_validate(client: TestClient) -> None:
    contract = yaml.safe_load(ERRORS_YML.read_text(encoding="utf-8"))
    examples = contract["$defs"]["ErrorEnvelope"]["examples"]
    assert examples
    component = Draft202012Validator(
        {
            "$ref": "#/components/schemas/ErrorEnvelope",
            "components": client.get("/openapi.json").json()["components"],
        }
    )
    contract_validator = schema_validator(ERRORS_YML, "#/$defs/ErrorEnvelope")
    for example in examples:
        parsed = ErrorEnvelope.model_validate(example)
        assert parsed.model_dump(mode="json", exclude_none=True) == example
        component.validate(example)
        contract_validator.validate(example)
    for bad in ({"error": {"code": "nope", "message": "m"}}, {"error": {"code": "not_found"}}):
        assert not component.is_valid(bad)
        assert not contract_validator.is_valid(bad)
        with pytest.raises(ValueError):
            ErrorEnvelope.model_validate(bad)
