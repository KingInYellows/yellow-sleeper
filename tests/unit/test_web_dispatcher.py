from __future__ import annotations

from starlette.testclient import TestClient

from yellow_sleeper.web import TOOLS, app


def test_health_reports_eleven_tools_and_stage_two() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "tools": 11, "stage": 2}
    assert len(TOOLS) == 11
    assert all(name.startswith("dynasty_") for name in TOOLS)


def test_unknown_tool_is_404() -> None:
    with TestClient(app) as client:
        response = client.post("/tools/not_a_tool", json={})
    assert response.status_code == 404
    assert "unknown tool" in response.json()["error"]


def test_non_object_body_is_400() -> None:
    with TestClient(app) as client:
        response = client.post("/tools/dynasty_health_check", json=["nope"])
    assert response.status_code == 400
