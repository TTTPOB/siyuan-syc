"""Short-lived sessions against the official SiYuan MCP endpoint."""

import asyncio
import base64
import logging
import mimetypes
import tempfile
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, TypeVar

import click
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError
from mcp.types import CallToolResult, PaginatedRequestParams, Tool

from .config import Instance
from .transport import proxy_for

T = TypeVar("T")


async def _run(
    instance: Instance, operation: Callable[[ClientSession], Awaitable[T]]
) -> T:
    async with (
        httpx.AsyncClient(
            headers=instance.headers(),
            timeout=60,
            trust_env=False,
            proxy=proxy_for(instance.url),
        ) as http,
        streamable_http_client(instance.url + "/mcp", http_client=http) as (
            read,
            write,
            _,
        ),
        ClientSession(
            read, write, read_timeout_seconds=timedelta(seconds=60)
        ) as session,
    ):
        await session.initialize()
        return await operation(session)


def _first_exception(error: BaseException) -> BaseException:
    while isinstance(error, BaseExceptionGroup):
        error = error.exceptions[0]
    return error


def _request(
    instance: Instance, operation: Callable[[ClientSession], Awaitable[T]]
) -> T:
    # Keep SDK transport logs out of the CLI output, including HTTP error details.
    logging.getLogger("mcp").setLevel(logging.CRITICAL)
    try:
        return asyncio.run(_run(instance, operation))
    except* (httpx.HTTPError, httpx.InvalidURL, UnicodeError, McpError) as group:
        error = _first_exception(group)
        if isinstance(error, httpx.HTTPStatusError):
            detail = f"HTTP {error.response.status_code}"
        elif isinstance(error, McpError):
            detail = str(error)
        else:
            detail = type(error).__name__
        raise click.ClickException(f"SiYuan /mcp: {detail}") from None


def list_tools(instance: Instance) -> list[Tool]:
    async def load(session: ClientSession) -> list[Tool]:
        page = await session.list_tools()
        tools = list(page.tools)
        while page.nextCursor is not None:
            page = await session.list_tools(
                params=PaginatedRequestParams(cursor=page.nextCursor)
            )
            tools.extend(page.tools)
        return tools

    return _request(instance, load)


def call_tool(instance: Instance, tool: str, args: dict[str, Any]) -> CallToolResult:
    return _request(instance, lambda session: session.call_tool(tool, args))


def _replace_binary(block: dict[str, Any], key: str) -> None:
    try:
        data = base64.b64decode(block.pop(key), validate=True)
    except ValueError:
        raise click.ClickException(
            "SiYuan /mcp: invalid base64 in binary content"
        ) from None
    media_type = block.get("mimeType")
    suffix = mimetypes.guess_extension(media_type) if media_type else None
    with tempfile.NamedTemporaryFile(
        prefix="syc-mcp-", suffix=suffix or ".bin", delete=False
    ) as handle:
        handle.write(data)
        block["path"] = handle.name


def result_json(result: CallToolResult) -> dict[str, Any]:
    output = result.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        include={"content", "structuredContent", "isError"},
    )
    output.setdefault("structuredContent", None)
    for block in output["content"]:
        if block["type"] in {"image", "audio"}:
            _replace_binary(block, "data")
        elif block["type"] == "resource" and "blob" in block["resource"]:
            _replace_binary(block["resource"], "blob")
    return output
