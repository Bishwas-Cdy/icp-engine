import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeURLError(ValueError):
    pass


async def validate_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeURLError("URL must use http or https and include a hostname")
    if parsed.username or parsed.password:
        raise UnsafeURLError("URL credentials are not allowed")
    if parsed.hostname.lower() == "localhost":
        raise UnsafeURLError("Local addresses are not allowed")

    try:
        literal_ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        if not literal_ip.is_global:
            raise UnsafeURLError(
                "Private, loopback, link-local, and reserved addresses are not allowed"
            )
        return

    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve hostname: {parsed.hostname}") from exc

    if not addresses:
        raise UnsafeURLError("Hostname did not resolve")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise UnsafeURLError(
                "Private, loopback, link-local, and reserved addresses are not allowed"
            )
