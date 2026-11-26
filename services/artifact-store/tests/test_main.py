from fastapi.testclient import TestClient

from app.main import app


def test_openapi_title_is_service_name() -> None:
    response = TestClient(app).get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "artifact-store"
