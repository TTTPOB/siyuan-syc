import base64
import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner
from mcp.types import CallToolResult, ImageContent, TextContent

from syc import mcp_client
from syc.cli import main
from syc.config import Instance


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
                    mimeType="image/png",
                    data=base64.b64encode(sample).decode(),
                )
            ],
            structuredContent={"found": True},
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
    def stub(
        instance: Instance, tool: str, arguments: dict[str, str]
    ) -> CallToolResult:
        assert (tool, arguments) == expected
        return CallToolResult(
            content=[TextContent(type="text", text="tool failed")], isError=True
        )

    monkeypatch.setattr(mcp_client, "call_tool", stub)
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 1
    assert result.stderr.strip() == "syc: instance=server (only)"
    payload = json.loads(result.stdout)
    assert payload["isError"] is True
    assert payload["content"][0]["text"] == "tool failed"
