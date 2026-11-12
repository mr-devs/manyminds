"""How the app is served: this machine only, no auto-reload, no foreign Host headers."""

from typing import Any

import httpx2
import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from manyminds.core.services import Services
from manyminds.ui import app as ui_app


@pytest.fixture
def run_arguments(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Capture what would be passed to NiceGUI instead of starting a server."""
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> None:
        captured["args"] = args
        captured.update(kwargs)

    monkeypatch.setattr(ui_app.ui, "run", fake_run)
    monkeypatch.setattr(
        ui_app, "install_host_check", lambda app: captured.setdefault("host_check", app)
    )
    return captured


def test_the_app_listens_on_this_machine_only(
    services: Services, run_arguments: dict[str, Any]
) -> None:
    ui_app.run(services)

    assert run_arguments["host"] == "127.0.0.1"


def test_auto_reload_is_off(services: Services, run_arguments: dict[str, Any]) -> None:
    ui_app.run(services)

    assert run_arguments["reload"] is False


def test_a_free_port_is_chosen_unless_one_is_given(
    services: Services, run_arguments: dict[str, Any]
) -> None:
    ui_app.run(services)
    chosen = run_arguments["port"]
    ui_app.run(services, port=8123)

    assert isinstance(chosen, int)
    assert 1024 < chosen < 65536
    assert run_arguments["port"] == 8123


def test_the_browser_opens_unless_asked_not_to(
    services: Services, run_arguments: dict[str, Any]
) -> None:
    ui_app.run(services)
    default = run_arguments["show"]
    ui_app.run(services, show=False)

    assert default is True
    assert run_arguments["show"] is False


def test_the_host_check_is_installed_on_the_served_app(
    services: Services, run_arguments: dict[str, Any]
) -> None:
    ui_app.run(services)

    assert run_arguments["host_check"] is ui_app.app


async def request_with_host(host: str) -> int:
    async def hello(request: Any) -> PlainTextResponse:
        return PlainTextResponse("hello")

    served = Starlette(routes=[Route("/", hello)])
    ui_app.install_host_check(served)
    transport = httpx2.ASGITransport(served)
    async with httpx2.AsyncClient(transport=transport, base_url="http://placeholder") as client:
        response = await client.get("/", headers={"Host": host})
    return response.status_code


@pytest.mark.parametrize("host", ["127.0.0.1:8123", "localhost:8123", "127.0.0.1", "localhost"])
async def test_requests_addressed_to_this_machine_are_served(host: str) -> None:
    assert await request_with_host(host) == 200


@pytest.mark.parametrize(
    "host", ["evil.example", "evil.example:8123", "127.0.0.1.evil.example", "192.168.1.20:8123"]
)
async def test_requests_with_any_other_host_header_are_refused(host: str) -> None:
    assert await request_with_host(host) == 400
