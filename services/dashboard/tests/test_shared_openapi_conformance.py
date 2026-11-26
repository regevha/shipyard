"""Tests of tests/openapi_conformance.py (shared copy, T022): OpenAPI vs contract comparison."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, Header, Query, Request, Response
from openapi_conformance import differences, find_contract, schema_validator
from pydantic import BaseModel, Field

from app.errors import install

SHARED_YML = """
$defs:
  Item:
    type: object
    additionalProperties: false
    required: [id, name, note]
    properties:
      id: {type: integer}
      name: {type: string}
      note:
        anyOf:
          - {type: string}
          - {type: "null"}
    examples:
      - {id: 1, name: a, note: null}
"""

ENVELOPE = {
    "content": {"application/json": {"schema": {"$ref": "errors.yml#/$defs/ErrorEnvelope"}}}
}


def contract_doc(item_ref: str = "shared.yml#/$defs/Item") -> dict[str, Any]:
    item = {"application/json": {"schema": {"$ref": item_ref}}}
    return {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/items": {
                "post": {
                    "requestBody": {"required": True, "content": item},
                    "responses": {
                        "201": {"description": "ok", "content": item},
                        "422": {"description": "bad", **ENVELOPE},
                        "500": {"description": "err", **ENVELOPE},
                    },
                }
            },
            "/items/{item_id}": {
                "get": {
                    "parameters": [
                        {
                            "name": "item_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        },
                        {"name": "X-Trace", "in": "header", "schema": {"type": "string"}},
                    ],
                    "responses": {
                        "200": {"description": "ok", "content": item},
                        "404": {"description": "none", **ENVELOPE},
                        "422": {"description": "bad", **ENVELOPE},
                        "500": {"description": "err", **ENVELOPE},
                    },
                }
            },
        },
    }


def write_contract(tmp_path: Path, doc: dict[str, Any] | None = None) -> Path:
    (tmp_path / "shared.yml").write_text(SHARED_YML)
    shutil.copy(find_contract("errors.yml"), tmp_path / "errors.yml")
    path = tmp_path / "api.yml"
    path.write_text(yaml.safe_dump(doc or contract_doc()))
    return path


class Item(BaseModel):
    id: int
    name: str
    note: str | None


class Loose(BaseModel):
    id: int
    name: str
    note: str | None = None


class Strict(BaseModel):
    id: int
    name: str = Field(min_length=5)
    note: str | None


class Wrong(BaseModel):
    id: str
    extra: int
    note: str | None = None


def good_app() -> FastAPI:
    app = FastAPI()

    @app.post("/items", status_code=201)
    def create(item: Item) -> Item:
        return item

    @app.get("/items/{item_id}", responses={404: {"description": "none"}})
    def read(item_id: int, x_trace: str | None = Header(default=None)) -> Item:
        return Item(id=item_id, name="a", note=None)

    install(app)
    return app


def test_identical_spec_has_no_differences(tmp_path: Path) -> None:
    assert differences(good_app().openapi(), write_contract(tmp_path)) == []


def test_missing_and_extra_path_reported(tmp_path: Path) -> None:
    app = FastAPI()

    @app.post("/items", status_code=201)
    def create(item: Item) -> Item:
        return item

    @app.get("/extra")
    def extra() -> Item:
        return Item(id=1, name="a", note=None)

    install(app)
    found = differences(app.openapi(), write_contract(tmp_path))
    assert "GET /items/{item_id}: in the contract but not in the app" in found
    assert "GET /extra: in the app but not in the contract" in found


def test_missing_status_reported(tmp_path: Path) -> None:
    app = FastAPI()

    @app.post("/items", status_code=201, responses={409: {"description": "x"}})
    def create(item: Item) -> Item:
        return item

    @app.get("/items/{item_id}")
    def read(item_id: int, x_trace: str | None = Header(default=None)) -> Item:
        return Item(id=item_id, name="a", note=None)

    install(app)
    found = differences(app.openapi(), write_contract(tmp_path))
    assert "GET /items/{item_id}: status 404 is in the contract but not in the app" in found
    assert "POST /items: status 409 is in the app but not in the contract" in found


def test_parameter_difference_reported(tmp_path: Path) -> None:
    app = FastAPI()

    @app.post("/items", status_code=201)
    def create(item: Item) -> Item:
        return item

    @app.get("/items/{item_id}", responses={404: {"description": "none"}})
    def read(item_id: int, limit: int = Query(), x_trace: str = Header()) -> Item:
        return Item(id=item_id, name="a", note=None)

    install(app)
    found = differences(app.openapi(), write_contract(tmp_path))
    assert (
        "GET /items/{item_id}: query parameter limit is in the app but not in the contract" in found
    )
    assert (
        "GET /items/{item_id}: header parameter x-trace required differs: contract False, app True"
    ) in found
    assert len(found) == 2


def test_required_property_difference_reported(tmp_path: Path) -> None:
    app = FastAPI()

    @app.post("/items", status_code=201)
    def create(item: Loose) -> Item:
        return Item(id=1, name="a", note=None)

    @app.get("/items/{item_id}", responses={404: {"description": "none"}})
    def read(item_id: int, x_trace: str | None = Header(default=None)) -> Item:
        return Item(id=item_id, name="a", note=None)

    install(app)
    found = differences(app.openapi(), write_contract(tmp_path))
    assert found == [
        "POST /items request application/json: property note required differs: "
        "contract True, app False"
    ]


def test_contract_example_rejected_by_app_schema_reported(tmp_path: Path) -> None:
    app = FastAPI()

    @app.post("/items", status_code=201)
    def create(item: Strict) -> Item:
        return Item(id=1, name="a", note=None)

    @app.get("/items/{item_id}", responses={404: {"description": "none"}})
    def read(item_id: int, x_trace: str | None = Header(default=None)) -> Item:
        return Item(id=item_id, name="a", note=None)

    install(app)
    found = differences(app.openapi(), write_contract(tmp_path))
    assert len(found) == 1
    assert found[0].startswith("POST /items request application/json: contract schema example #0")
    assert "rejected by the app schema at name" in found[0]


def test_every_difference_reported_not_only_first(tmp_path: Path) -> None:
    app = FastAPI()

    @app.post("/items", status_code=201, responses={409: {"description": "x"}})
    def create(item: Wrong) -> Wrong:
        return item

    @app.get("/other")
    def other() -> Wrong:
        return Wrong(id="1", extra=1)

    install(app)
    found = differences(app.openapi(), write_contract(tmp_path))
    joined = "\n".join(found)
    for expected in (
        "GET /items/{item_id}: in the contract but not in the app",
        "GET /other: in the app but not in the contract",
        "POST /items: status 409 is in the app but not in the contract",
        "property id types differ: contract [integer], app [string]",
        "property name is in the contract but not in the app",
        "property extra is in the app but not in the contract",
        "property note required differs",
    ):
        assert expected in joined, expected
    assert len(found) >= 8


def test_cross_file_refs_resolved(tmp_path: Path) -> None:
    # Item is read from shared.yml and the envelope from errors.yml; a change there shows up.
    path = write_contract(tmp_path)
    assert differences(good_app().openapi(), path) == []
    (tmp_path / "shared.yml").write_text(
        SHARED_YML.replace("required: [id, name, note]", "required: [id]")
    )
    found = differences(good_app().openapi(), path)
    assert any("property name required differs: contract False, app True" in f for f in found)
    envelope = tmp_path / "errors.yml"
    envelope.write_text(
        envelope.read_text().replace("required: [code, message]", "required: [code]")
    )
    assert any(
        "property error.message required differs" in f
        for f in differences(good_app().openapi(), path)
    )


def test_schema_validator_enforces_contract_state_table() -> None:
    events = find_contract("events.yml")
    step = schema_validator(events, "#/$defs/StepResult")
    running = {
        "name": "test",
        "status": "running",
        "started_at": "2026-11-25T11:00:00Z",
        "finished_at": None,
    }
    assert step.is_valid(running)
    assert not step.is_valid({**running, "status": "passed"})
    assert not step.is_valid({**running, "status": "pending"})
    assert not step.is_valid({**running, "status": "paused"})
    assert not step.is_valid({**running, "extra": 1})

    data = yaml.safe_load(events.read_text(encoding="utf-8"))["$defs"]["BuildFinishedData"]
    finished = schema_validator(events, "#/$defs/BuildFinishedData")
    for example in data["examples"]:
        finished.validate(example)
    upload_failed = next(e for e in data["examples"] if e["failure_reason"])
    passed = {**upload_failed, "outcome": "passed", "failure_reason": None}
    finished.validate(passed)
    assert not finished.is_valid({**passed, "failed_step": "install"})
    assert not finished.is_valid({**passed, "outcome": "failed"})
    assert not finished.is_valid({**upload_failed, "failure_reason": None})
    # a cross-file pointer from another contract resolves too
    assert schema_validator(
        find_contract("api-pipeline-runner.yml"), "events.yml#/$defs/StepResult"
    ).is_valid(running)
    assert not schema_validator(events, "#/$defs/BuildId").is_valid("not-a-uuid")


def test_binary_bodies_and_json_suffix_media_types_compare(tmp_path: Path) -> None:
    binary: dict[str, Any] = {"application/octet-stream": {}}
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/blobs/{name}": {
                "parameters": [
                    {"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "post": {
                    "requestBody": {"required": True, "content": binary},
                    "responses": {
                        "201": {"description": "ok", "content": {"application/json": {}}},
                        "422": ENVELOPE,
                        "500": ENVELOPE,
                    },
                },
                "get": {
                    "responses": {
                        "200": {"description": "bytes", "content": binary},
                        "422": ENVELOPE,
                        "500": ENVELOPE,
                    }
                },
            }
        },
    }
    shutil.copy(find_contract("errors.yml"), tmp_path / "errors.yml")
    path = tmp_path / "api.yml"
    path.write_text(yaml.safe_dump(doc))

    app = FastAPI()
    upload_body = {
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    }

    @app.post("/blobs/{name}", status_code=201, openapi_extra=upload_body)
    async def upload(name: str, request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    @app.get(
        "/blobs/{name}",
        response_class=Response,
        responses={200: {"content": {"application/octet-stream": {}}}},
    )
    def download(name: str) -> Response:
        return Response(b"x", media_type="application/octet-stream")

    install(app)
    assert differences(app.openapi(), path) == []

    spec = copy.deepcopy(app.openapi())
    spec["paths"]["/blobs/{name}"]["post"]["requestBody"]["content"] = {"application/json": {}}
    found = differences(spec, path)
    assert found == [
        "POST /blobs/{name} request: media types differ: contract [application/octet-stream], "
        "app [application/json]"
    ]


def test_find_contract_locates_contracts_folder() -> None:
    assert find_contract("errors.yml").is_file()
