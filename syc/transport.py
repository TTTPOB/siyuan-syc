"""Proxy selection and helpers for raw SiYuan API requests."""

from typing import Any
from urllib.parse import urlsplit
from urllib.request import getproxies, proxy_bypass

import click
import httpx2

from .config import Instance


def proxy_for(url: str) -> str | None:
    endpoint = urlsplit(url)
    # Let urllib interpret bypass entries instead of parsing every entry as a URL.
    if proxy_bypass(endpoint.netloc):
        return None
    return getproxies().get(endpoint.scheme)


def request(
    instance: Instance, method: str, endpoint: str, **kwargs: Any
) -> httpx2.Response:
    # Let HTTPX2 set the JSON or multipart Content-Type for this particular request.
    headers = {
        k: v for k, v in instance.headers().items() if k.lower() != "content-type"
    }
    try:
        with httpx2.Client(
            headers=headers, timeout=60, trust_env=False, proxy=proxy_for(instance.url)
        ) as client:
            response = client.request(method, instance.url + endpoint, **kwargs)
        response.raise_for_status()
    except httpx2.HTTPStatusError as exc:
        raise click.ClickException(
            f"SiYuan {endpoint}: HTTP {exc.response.status_code}"
        ) from None
    except (httpx2.RequestError, httpx2.InvalidURL, UnicodeError) as exc:
        raise click.ClickException(f"SiYuan {endpoint}: {type(exc).__name__}") from None
    return response


def api_error(endpoint: str, result: dict[str, Any]) -> click.ClickException:
    msg = result.get("msg")
    detail = f" ({msg})" if isinstance(msg, str) and msg else ""
    return click.ClickException(
        f"SiYuan {endpoint}: API code {result.get('code', 'missing')}{detail}"
    )
