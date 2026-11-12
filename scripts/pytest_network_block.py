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

    real_sendto = socket.socket.sendto
    real_gethostbyname = socket.gethostbyname
    real_gethostbyname_ex = socket.gethostbyname_ex

    def sendto(self: socket.socket, data: Any, *rest: Any) -> int:
        if not _is_local(rest[-1]):
            raise NetworkBlockedError(rest[-1])
        return real_sendto(self, data, *rest)

    def gethostbyname(host: str) -> str:
        if host not in LOCAL_HOSTS:
            raise NetworkBlockedError(host)
        return real_gethostbyname(host)

    def gethostbyname_ex(host: str) -> Any:
        if host not in LOCAL_HOSTS:
            raise NetworkBlockedError(host)
        return real_gethostbyname_ex(host)

    monkeypatch.setattr(socket.socket, "sendto", sendto)
    monkeypatch.setattr(socket, "gethostbyname", gethostbyname)
    monkeypatch.setattr(socket, "gethostbyname_ex", gethostbyname_ex)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    yield
