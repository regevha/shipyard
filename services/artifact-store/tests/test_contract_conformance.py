from openapi_conformance import differences, find_contract

from app.main import app


def test_openapi_matches_contract() -> None:
    assert differences(app.openapi(), find_contract("api-artifact-store.yml")) == []
