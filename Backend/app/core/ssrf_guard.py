import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    pass


def _assert_public_host(hostname: str) -> None:
    """Block SSRF: reject hostnames that resolve to private/loopback/link-local ranges."""
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve host: {hostname}") from exc
    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UnsafeUrlError(f"Refusing to reach a non-public address: {ip}")


def assert_safe_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"Unsupported scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise UnsafeUrlError("URL has no hostname")
    _assert_public_host(parsed.hostname)
