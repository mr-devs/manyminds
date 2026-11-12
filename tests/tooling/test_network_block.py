"""The default suite cannot reach the network."""

import socket

import pytest
from pytest_network_block import NetworkBlockedError

# 192.0.2.0/24 is reserved for documentation, so nothing is contacted even without the block.
UNROUTABLE = ("192.0.2.1", 9)


def test_outbound_connections_are_refused() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        with pytest.raises(NetworkBlockedError, match=r"192\.0\.2\.1"):
            sock.connect(UNROUTABLE)


def test_name_lookups_are_refused() -> None:
    with pytest.raises(NetworkBlockedError, match=r"openrouter\.ai"):
        socket.getaddrinfo("openrouter.ai", 443)


def test_localhost_is_still_allowed() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(server.getsockname())

    assert socket.getaddrinfo("localhost", 80)


def test_connect_ex_is_refused_too() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        with pytest.raises(NetworkBlockedError, match=r"192\.0\.2\.1"):
            sock.connect_ex(UNROUTABLE)


@pytest.mark.parametrize("lookup", ["gethostbyname", "gethostbyname_ex"])
def test_older_name_lookups_are_refused(lookup: str) -> None:
    with pytest.raises(NetworkBlockedError, match=r"openrouter\.ai"):
        getattr(socket, lookup)("openrouter.ai")


def test_datagrams_are_refused() -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock,
        pytest.raises(NetworkBlockedError, match=r"192\.0\.2\.1"),
    ):
        sock.sendto(b"x", UNROUTABLE)
