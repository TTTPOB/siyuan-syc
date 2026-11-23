import base64
import json
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from click.testing import CliRunner
from mcp.types import CallToolResult, ImageContent, TextContent

from syc import mcp_client
from syc.cli import main
from syc.config import BROWSER_USER_AGENT, Instance


def test_call_reads_stdin_and_writes_binary_blocks_to_temp(
    config_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sample = b"sample image bytes"

    def stub(instance: Instance, tool: str, args: dict[str, str]) -> CallToolResult:
        assert instance.url == "https://notes.example.invalid"
        assert tool == "example"
        assert args == {"action": "get"}
        return CallToolResult(
            content=[
                ImageContent(
                    type="image",
                    mime_type="image/png",
                    data=base64.b64encode(sample).decode(),
                )
            ],
            structured_content={"found": True},
        )

    monkeypatch.setattr(mcp_client, "call_tool", stub)
    monkeypatch.setattr(tempfile, "tempdir", str(config_root))
    result = CliRunner().invoke(
        main, ["call", "example", "-"], input='{"action":"get"}\n'
    )
    assert result.exit_code == 0, result.output
    assert result.stderr.strip() == "syc: instance=server (only)"
    payload = json.loads(result.stdout)
    assert payload["isError"] is False
    assert payload["structuredContent"] == {"found": True}
    image = payload["content"][0]
    assert "data" not in image
    assert image["mimeType"] == "image/png"
    assert Path(image["path"]).read_bytes() == sample


@pytest.mark.parametrize(
    "args,expected",
    [
        (["call", "example", "{}"], ("example", {})),
        (["sync"], ("sync", {"action": "perform"})),
    ],
)
def test_mcp_error_result_stays_on_stdout(
    config_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    expected: tuple[str, dict[str, str]],
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def stub(
        instance: Instance, tool: str, arguments: dict[str, str]
    ) -> CallToolResult:
        calls.append((tool, arguments))
        return CallToolResult(
            content=[TextContent(type="text", text="tool failed")], is_error=True
        )

    monkeypatch.setattr(mcp_client, "call_tool", stub)
    result = CliRunner().invoke(main, args)
    assert calls == [expected]
    assert result.exit_code == 1
    assert result.stderr.strip() == "syc: instance=server (only)"
    payload = json.loads(result.stdout)
    assert payload["isError"] is True
    assert payload["content"][0]["text"] == "tool failed"


@pytest.mark.parametrize("status", [200, 401, 403])
def test_mcp_streamable_http(
    config_root: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    requests = []
    tool_result = {
        "content": [{"type": "text", "text": "3.8.9"}],
        "structuredContent": {"version": "3.8.9"},
        "isError": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, self.headers, request))
            if status != 200:
                # An HTTP auth rejection must not be treated as a legacy probe failure.
                self.send_response(status)
                self.end_headers()
                return
            if request["method"] == "server/discover":
                payload = {
                    "supportedVersions": ["2026-07-28"],
                    "capabilities": {"tools": {}},
                }
            elif request["method"] == "tools/list":
                payload = {
                    "tools": [{"name": "system", "inputSchema": {"type": "object"}}],
                    "cacheScope": "private",
                    "ttlMs": 0,
                    "resultType": "complete",
                }
            else:
                payload = {**tool_result, "resultType": "complete"}
            body = json.dumps(
                {"jsonrpc": "2.0", "id": request["id"], "result": payload}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    monkeypatch.setenv("no_proxy", "127.0.0.1,<local>,10.*")
    (config_root / "headers.json").write_text(
        '{"Authorization":"Token sample", "user-agent":"ignored"}'
    )
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        (config_root / "config.toml").write_text(
            f'[instances.server]\nurl = "http://127.0.0.1:{http.server_port}"\n'
            'headers_file = "headers.json"\n'
        )
        thread = Thread(target=http.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            result = CliRunner().invoke(
                main, ["call", "system", '{"action":"version"}']
            )
        finally:
            http.shutdown()
            thread.join()

    for path, headers, _ in requests:
        assert path == "/mcp"
        assert headers["Authorization"] == "Token sample"
        assert headers["User-Agent"] == BROWSER_USER_AGENT
    methods = [request["method"] for _, _, request in requests]
    if status == 200:
        assert result.exit_code == 0, result.exception
        assert json.loads(result.stdout) == tool_result
        assert result.stderr == "syc: instance=server (only)\n"
        assert methods.count("tools/call") == 1
        [params] = [
            request["params"]
            for _, _, request in requests
            if request["method"] == "tools/call"
        ]
        assert params["name"] == "system"
        assert params["arguments"] == {"action": "version"}
    else:
        assert result.exit_code == 1, result.exception
        assert not result.stdout
        assert (
            result.stderr
            == f"syc: instance=server (only)\nError: SiYuan /mcp: HTTP {status}\n"
        )
        assert methods == ["server/discover"]
