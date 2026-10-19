from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from macrorail.api import create_app
from macrorail.config import Config, RailConfig
from macrorail.machine import build_machine

from .conftest import SPEEDUP


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    machine = build_machine(
        Config(rail=RailConfig(port="sim"), data_dir=tmp_path), sim=True, sim_speedup=SPEEDUP
    )
    with TestClient(create_app(machine)) as test_client:
        deadline = time.monotonic() + 5
        while not test_client.get("/api/state").json()["rail"]["connected"]:
            assert time.monotonic() < deadline, "simulated rail did not connect"
            time.sleep(0.05)
        yield test_client


def as_client(client_id: str) -> dict[str, str]:
    return {"X-Client-Id": client_id}


def test_state_shape(client: TestClient) -> None:
    state: dict[str, Any] = client.get("/api/state").json()
    assert state["activity"] == "idle"
    assert state["rail"]["steps_per_mm"] == 400
    assert state["camera"]["connected"]
    assert state["control"] == {"mine": False, "held": False}
    assert state["plan"]["error"] == "Set the start point first."


def test_first_connection_gets_control_and_state(client: TestClient) -> None:
    with client.websocket_connect("/api/ws?client=phone") as ws:
        assert ws.receive_json()["type"] == "log"
        message = ws.receive_json()
        assert message["type"] == "state"
        assert message["state"]["control"] == {"mine": True, "held": True}


def test_commands_require_control(client: TestClient) -> None:
    with client.websocket_connect("/api/ws?client=phone"):
        response = client.post("/api/rail/home", headers=as_client("laptop"))
        assert response.status_code == 403
        assert client.post("/api/rail/home", headers=as_client("phone")).status_code == 204


def test_take_control_hands_over(client: TestClient) -> None:
    with client.websocket_connect("/api/ws?client=phone"):
        assert client.post("/api/control/take", headers=as_client("laptop")).status_code == 204
        assert client.post("/api/camera/test", headers=as_client("phone")).status_code == 403
        assert client.post("/api/camera/test", headers=as_client("laptop")).status_code == 204


def test_refused_command_explains_why(client: TestClient) -> None:
    client.post("/api/control/take", headers=as_client("phone"))
    response = client.post("/api/points/start/go", headers=as_client("phone"))
    assert response.status_code == 409
    assert response.json()["detail"] == "Home the rail first."


def test_invalid_settings_are_refused(client: TestClient) -> None:
    client.post("/api/control/take", headers=as_client("phone"))
    response = client.patch(
        "/api/settings", json={"motion": {"run_current_ma": 5000}}, headers=as_client("phone")
    )
    assert response.status_code == 409
    assert "Invalid settings" in response.json()["detail"]


def test_settings_update(client: TestClient) -> None:
    client.post("/api/control/take", headers=as_client("phone"))
    response = client.patch(
        "/api/settings", json={"stack": {"step": 8}}, headers=as_client("phone")
    )
    assert response.status_code == 204
    assert client.get("/api/state").json()["settings"]["stack"]["step"] == 8


def test_stop_is_allowed_without_control(client: TestClient) -> None:
    client.post("/api/control/take", headers=as_client("phone"))
    client.post("/api/rail/home", headers=as_client("phone"))
    assert client.post("/api/stop", headers=as_client("laptop")).status_code == 204


def test_serves_ui(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>MacroRail</title>" in response.text
    assert response.headers["cache-control"] == "no-cache"
