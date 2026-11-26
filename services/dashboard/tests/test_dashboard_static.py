import pytest
from conftest import build_started, new_id
from fastapi.testclient import TestClient


def test_index_served_at_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_api_routes_win_over_static(client: TestClient) -> None:
    for path in ("/builds", "/artifacts", "/releases"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
    assert client.get("/openapi.json").status_code == 200


def test_get_events_is_405_with_allow_post(client: TestClient) -> None:
    response = client.get("/events")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert "POST" in response.headers["allow"]


def test_post_builds_is_405_with_allow_get(client: TestClient) -> None:
    for path in ("/builds", "/artifacts", "/releases", "/"):
        response = client.post(path, json={})
        assert response.status_code == 405
        assert response.json()["error"]["code"] == "method_not_allowed"
        assert "GET" in response.headers["allow"]


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_unknown_path_any_method_is_404_envelope(client: TestClient, method: str) -> None:
    response = client.request(method, "/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_static_asset_served_under_static(client: TestClient) -> None:
    response = client.get("/static/index.html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_unknown_static_path_is_404_envelope(client: TestClient) -> None:
    for path in (
        "/static/missing.js",
        "/static/",
        "/static/../app/main.py",
        "/static/%2e%2e/pyproject.toml",
    ):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.json()["error"]["code"] == "not_found"


def test_static_asset_wrong_method_is_405(client: TestClient) -> None:
    response = client.post("/static/index.html", json={})
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert "GET" in response.headers["allow"] and "HEAD" in response.headers["allow"]


def test_only_write_endpoint_is_post_events(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    writes = {
        (method, path)
        for path, item in spec["paths"].items()
        for method in item
        if method in {"post", "put", "patch", "delete"}
    }
    assert writes == {("post", "/events")}
    assert client.post("/events", json=build_started(new_id())).status_code == 202
