"""Proxy selection shared by the MCP and raw HTTP transports."""

from urllib.parse import urlsplit
from urllib.request import getproxies, proxy_bypass


def proxy_for(url: str) -> str | None:
    endpoint = urlsplit(url)
    # Let urllib interpret bypass entries instead of parsing every entry as a URL.
    if proxy_bypass(endpoint.hostname or ""):
        return None
    return getproxies().get(endpoint.scheme)
