"""pytest plugin: tests cannot reach the network unless they are marked ``live``.

Connections and name lookups for anything other than this machine raise NetworkBlockedError
before a single packet is sent.
"""

import socket
from collections.abc import Iterator
from typing import Any

import pytest

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "", None}


class NetworkBlockedError(RuntimeError):
    def __init__(self, target: object) -> None:
        super().__init__(
            f"Network access is blocked in tests (tried to reach {target!r}). "
            "Use a fake or a fixture, or mark the test 'live'."
        )


def _is_local(address: Any) -> bool:
    if isinstance(address, tuple) and address:
        return address[0] in LOCAL_HOSTS
    # Anything that is not a (host, port) tuple is a local socket path.
    return True


@pytest.fixture(autouse=True)
def _block_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    if request.node.get_closest_marker("live") is not None:
        yield
        return

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def connect(self: socket.socket, address: Any) -> None:
        if not _is_local(address):
            raise NetworkBlockedError(address)
        real_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        if not _is_local(address):
            raise NetworkBlockedError(address)
        return real_connect_ex(self, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        name = host.decode() if isinstance(host, bytes) else host
        if name not in LOCAL_HOSTS:
            raise NetworkBlockedError(name)
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    yield
