"""Short-lived MCP connections against the official SiYuan MCP endpoint."""

import asyncio
import base64
import logging
import mimetypes
import tempfile
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import click
import httpx2
from mcp import Client, MCPError
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, Tool

from .config import Instance
from .transport import proxy_for

T = TypeVar("T")


async def _run(instance: Instance, operation: Callable[[Client], Awaitable[T]]) -> T:
    status: int | None = None

    async def track_status(response: httpx2.Response) -> None:
        # The SDK turns HTTP failures into RPC errors, losing the status code.
        # Let auto negotiation handle discovery failures, except auth rejections.
        nonlocal status
        if response.request.method == "POST":
            status = response.status_code if not response.is_success else None
            if status in (401, 403):
                response.raise_for_status()

    try:
        async with (
            httpx2.AsyncClient(
                headers=instance.headers(),
                timeout=60,
                trust_env=False,
                proxy=proxy_for(instance.url),
                event_hooks={"response": [track_status]},
            ) as http,
            Client(
                streamable_http_client(instance.url + "/mcp", http_client=http),
                mode="auto",
                read_timeout_seconds=60,
            ) as client,
        ):
            return await operation(client)
    except* (httpx2.HTTPError, httpx2.InvalidURL, UnicodeError, MCPError) as group:
        error = _first_exception(group)
        if isinstance(error, httpx2.HTTPStatusError):
            detail = f"HTTP {error.response.status_code}"
        elif isinstance(error, MCPError):
            detail = f"HTTP {status}" if status is not None else error.message
        else:
            detail = type(error).__name__
        raise click.ClickException(f"SiYuan /mcp: {detail}") from None


def _first_exception(error: BaseException) -> BaseException:
    while isinstance(error, BaseExceptionGroup):
        error = error.exceptions[0]
    return error


def _request(instance: Instance, operation: Callable[[Client], Awaitable[T]]) -> T:
    # Keep SDK transport logs out of the CLI output, including HTTP error details.
    logging.getLogger("mcp").setLevel(logging.CRITICAL)
    return asyncio.run(_run(instance, operation))


def list_tools(instance: Instance) -> list[Tool]:
    async def load(client: Client) -> list[Tool]:
        page = await client.list_tools()
        tools = list(page.tools)
        while page.next_cursor is not None:
            page = await client.list_tools(cursor=page.next_cursor)
            tools.extend(page.tools)
        return tools

    return _request(instance, load)


def call_tool(instance: Instance, tool: str, args: dict[str, Any]) -> CallToolResult:
    return _request(instance, lambda client: client.call_tool(tool, args))


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
        include={"content", "structured_content", "is_error"},
    )
    output.setdefault("structuredContent", None)
    for block in output["content"]:
        if block["type"] in {"image", "audio"}:
            _replace_binary(block, "data")
        elif block["type"] == "resource" and "blob" in block["resource"]:
            _replace_binary(block["resource"], "blob")
    return output
