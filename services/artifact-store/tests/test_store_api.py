import hashlib
from collections.abc import Iterator

import pytest
from conftest import BUILD
from fastapi.testclient import TestClient
from httpx import Response
from openapi_conformance import find_contract, schema_validator

from app.core.config import MAX_UPLOAD_BYTES, Settings
from app.errors import ApiError

CONTRACT = find_contract("api-artifact-store.yml")
ARTIFACT = schema_validator(CONTRACT, "events.yml#/$defs/Artifact")
ENVELOPE = schema_validator(CONTRACT, "errors.yml#/$defs/ErrorEnvelope")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def upload(
    client: TestClient,
    name: str = "app",
    data: bytes = b"hello",
    build_id: str | None = BUILD,
    **headers: str,
) -> Response:
    params = {} if build_id is None else {"build_id": build_id}
    response: Response = client.post(
        f"/artifacts/{name}",
        params=params,
        content=data,
        headers={"Content-Type": "application/octet-stream", **headers},
    )
    return response


def test_q17_first_upload_is_version_1_then_2(client: TestClient) -> None:
    first = upload(client)
    second = upload(client, data=b"other")
    other = upload(client, name="other")
    assert first.status_code == second.status_code == 201
    assert (first.json()["version"], second.json()["version"], other.json()["version"]) == (1, 2, 1)
    assert first.json()["build_id"] == BUILD


def test_q17_checksum_is_sha256_of_bytes(client: TestClient) -> None:
    body = upload(client, data=b"abc").json()
    assert body["checksum"] == sha(b"abc") and body["size_bytes"] == 3
    assert upload(client, data=b"").json()["size_bytes"] == 0
    ok = upload(client, data=b"abc", **{"X-Checksum-SHA256": sha(b"abc")})
    assert ok.status_code == 201


def test_q17_checksum_header_mismatch_is_422_and_nothing_stored(
    client: TestClient, settings: Settings
) -> None:
    r = upload(client, data=b"abc", **{"X-Checksum-SHA256": sha(b"x")})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "checksum_mismatch"
    assert client.get("/artifacts/app/versions/1").status_code == 404
    assert list(settings.blob_dir.iterdir()) == []
    assert upload(client).json()["version"] == 1  # version not consumed


def test_checksum_header_with_trailing_newline_is_422(client: TestClient) -> None:
    r = upload(client, data=b"abc", **{"X-Checksum-SHA256": sha(b"abc") + "\n"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"
    assert upload(client, data=b"abc", **{"X-Checksum-SHA256": "A" * 64}).status_code == 422


def test_upload_over_limit_is_413(client: TestClient) -> None:
    r = upload(client, data=b"x" * (MAX_UPLOAD_BYTES + 1))
    assert r.status_code == 413
    assert r.json() == {
        "error": {
            "code": "payload_too_large",
            "message": "upload is larger than 104857600 bytes",
        }
    }
    assert client.get("/artifacts/app/versions/1").status_code == 404


def test_upload_over_limit_without_content_length_is_413(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(101):
            yield b"x" * (1024 * 1024)

    r = client.post(f"/artifacts/app?build_id={BUILD}", content=chunks())
    assert r.status_code == 413


def test_body_reader_stops_as_soon_as_limit_is_passed() -> None:
    import asyncio

    from starlette.requests import Request

    from app.routers.artifacts import read_upload

    pulled = 0
    chunk = b"x" * (1024 * 1024)

    async def receive() -> dict[str, object]:
        nonlocal pulled
        pulled += 1
        return {"type": "http.request", "body": chunk, "more_body": True}

    async def run() -> None:
        request = Request({"type": "http", "headers": [], "method": "POST"}, receive)
        gen = read_upload(request)
        with pytest.raises(ApiError) as exc:
            await anext(gen)
        assert exc.value.status == 413

    asyncio.run(run())
    assert pulled == 101  # 100 MiB fit, the 101st chunk crossed the limit; nothing more was read


def test_limit_is_104857600_bytes(client: TestClient) -> None:
    assert MAX_UPLOAD_BYTES == 104_857_600
    r = upload(client, data=b"y" * MAX_UPLOAD_BYTES)
    assert r.status_code == 201 and r.json()["size_bytes"] == MAX_UPLOAD_BYTES
    back = client.get("/artifacts/app/versions/1")
    assert len(back.content) == MAX_UPLOAD_BYTES


def test_error_precedence_413_then_validation_then_checksum(client: TestClient) -> None:
    big = b"x" * (MAX_UPLOAD_BYTES + 1)
    bad = {"X-Checksum-SHA256": "nope"}
    r = upload(client, name="-bad", data=big, build_id=None, **bad)
    assert r.status_code == 413
    r = upload(client, name="-bad", data=b"abc", build_id=None, **bad)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed"
    r = upload(client, data=b"abc", **{"X-Checksum-SHA256": sha(b"zzz")})
    assert r.json()["error"]["code"] == "checksum_mismatch"
    r = upload(client, name="-bad", data=b"abc", **{"X-Checksum-SHA256": sha(b"zzz")})
    assert r.json()["error"]["code"] == "validation_failed"


@pytest.mark.parametrize(
    "name",
    ["-app", ".app", "_app", "a" * 101, "my%20app", "app%0A", "caf%C3%A9", "a$b"],
)
def test_q29_bad_names_are_422(client: TestClient, name: str) -> None:
    r = client.post(
        f"/artifacts/{name}?build_id={BUILD}", content=b"x", headers={"Content-Length": "1"}
    )
    assert r.status_code == 422, name
    assert r.json()["error"]["code"] == "validation_failed"
    assert r.json()["error"]["details"][0]["location"] == "path.name"
    assert client.get(f"/artifacts/{name}/versions/1").status_code == 422


def test_q29_names_are_case_sensitive(client: TestClient) -> None:
    assert upload(client, name="App").json()["version"] == 1
    assert upload(client, name="app").json()["version"] == 1
    assert upload(client, name="App").json()["version"] == 2
    for ok in ["a", "0", "Web_2.1", "a" * 100]:
        assert upload(client, name=ok).status_code == 201


@pytest.mark.parametrize("build_id", [None, "", "not-a-uuid", BUILD + "\n", BUILD.replace("-", "")])
def test_missing_or_bad_build_id_is_422(client: TestClient, build_id: str | None) -> None:
    r = upload(client, build_id=build_id)
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["location"] == "query.build_id"


def test_download_returns_bytes_and_checksum_header(client: TestClient) -> None:
    data = bytes(range(256)) * 10
    upload(client, data=data)
    r = client.get("/artifacts/app/versions/1")
    assert r.status_code == 200
    assert r.content == data
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["x-checksum-sha256"] == sha(data)


def test_download_ignores_range_header(client: TestClient) -> None:
    upload(client, data=b"hello")
    r = client.get("/artifacts/app/versions/1", headers={"Range": "bytes=0-1"})
    assert r.status_code == 200
    assert r.content == b"hello"
    assert r.headers["x-checksum-sha256"] == sha(b"hello")
    assert r.headers["content-length"] == "5"
    assert "accept-ranges" not in r.headers


def test_download_unknown_is_404(client: TestClient) -> None:
    upload(client)
    for path in [
        "/artifacts/app/versions/2",
        "/artifacts/nope/versions/1",
        "/artifacts/app/versions/9223372036854775807",
        "/artifacts/app/versions/9223372036854775808",
        "/artifacts/app/versions/99999999999999999999999",
    ]:
        r = client.get(path)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("version", ["0", "-1", "abc", "1.5"])
def test_download_bad_version_is_422(client: TestClient, version: str) -> None:
    r = client.get(f"/artifacts/app/versions/{version}")
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["location"] == "path.version"


def test_blob_written_under_data_dir(client: TestClient, settings: Settings) -> None:
    upload(client, data=b"one")
    upload(client, data=b"two")
    files = sorted(p.read_bytes() for p in settings.blob_dir.iterdir())
    assert settings.blob_dir == settings.data_dir / "artifact_store_blobs"
    assert files == [b"one", b"two"]


def test_download_with_missing_blob_is_500(client: TestClient, settings: Settings) -> None:
    upload(client)
    for p in settings.blob_dir.iterdir():
        p.unlink()
    quiet = TestClient(client.app, raise_server_exceptions=False)
    r = quiet.get("/artifacts/app/versions/1")
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"


def test_every_response_validates_against_contract_schema(client: TestClient) -> None:
    created = upload(client)
    ARTIFACT.validate(created.json())
    responses = [
        upload(client, name="-x"),
        upload(client, build_id=None),
        upload(client, data=b"a", **{"X-Checksum-SHA256": sha(b"b")}),
        upload(client, data=b"x" * (MAX_UPLOAD_BYTES + 1)),
        client.get("/artifacts/app/versions/9"),
        client.get("/artifacts/app/versions/0"),
        client.get("/nothing"),
        client.get("/artifacts/app"),
    ]
    assert [r.status_code for r in responses] == [422, 422, 422, 413, 404, 422, 404, 405]
    for r in responses:
        ENVELOPE.validate(r.json())


def test_version_retry_after_concurrent_insert(client: TestClient, settings: Settings) -> None:
    from sqlalchemy.orm import Session

    from app.repos.artifacts import ArtifactRow

    repo = client.app.state.repo  # type: ignore[attr-defined]
    original = Session.commit
    state = {"raced": False}

    def racing_commit(self: Session) -> None:
        if not state["raced"]:
            state["raced"] = True
            # another upload takes version 1 first
            from datetime import datetime

            with Session(repo._engine) as other:
                other.add(
                    ArtifactRow(
                        id="x",
                        name="race",
                        version=1,
                        checksum="0" * 64,
                        size_bytes=0,
                        build_id=BUILD,
                        uploaded_at=datetime(2026, 1, 1),
                        blob_path="x",
                    )
                )
                original(other)
        original(self)

    Session.commit = racing_commit  # type: ignore[method-assign]
    try:
        r = upload(client, name="race")
    finally:
        Session.commit = original  # type: ignore[method-assign]
    assert r.status_code == 201 and r.json()["version"] == 2
