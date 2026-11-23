import json
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from click.testing import CliRunner

from syc.cli import main


@dataclass
class Mock:
    response: bytes = b""
    media_type: str = "application/json"
    requests: list[tuple[str, dict[str, str], bytes]] = field(default_factory=list)

    def reply_json(self, value: object) -> None:
        self.media_type = "application/json"
        self.response = json.dumps(value).encode()


@pytest.fixture
def server(config_root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Mock]:
    mock = Mock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            headers = {key.lower(): value for key, value in self.headers.items()}
            mock.requests.append(
                (self.path, headers, self.rfile.read(int(headers["content-length"])))
            )
            self.send_response(200)
            self.send_header("Content-Type", mock.media_type)
            self.send_header("Content-Length", str(len(mock.response)))
            self.end_headers()
            self.wfile.write(mock.response)

        def log_message(self, format: str, *args: object) -> None:
            return

    monkeypatch.setenv("no_proxy", "127.0.0.1,<local>,10.*")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:8181")
    monkeypatch.setattr(tempfile, "tempdir", str(config_root))
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        (config_root / "config.toml").write_text(
            f'[instances.server]\nurl = "http://127.0.0.1:{http.server_port}/prefix"\n'
            'headers_file = "headers.json"\n'
        )
        (config_root / "headers.json").write_text(
            '{"Authorization":"Token sample", "user-agent":"wrong", "content-TYPE":"wrong"}'
        )
        thread = Thread(target=http.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield mock
        finally:
            http.shutdown()
            thread.join()


def test_upload_uses_multipart_and_reports_mapping(
    server: Mock, tmp_path: Path
) -> None:
    first, second = tmp_path / "one.png", tmp_path / "two.bin"
    first.write_bytes(b"\x00first")
    second.write_bytes(b"second")
    mapping = {"one.png": "assets/one-id.png", "two.bin": "assets/two-id.bin"}
    server.reply_json({"code": 0, "data": {"succMap": mapping, "errFiles": []}})
    result = CliRunner().invoke(main, ["asset", "upload", str(first), str(second)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == [
        {"file": str(path), "assetPath": mapping[path.name]} for path in (first, second)
    ]
    [(endpoint, headers, body)] = server.requests
    assert endpoint == "/prefix/api/asset/upload"
    assert headers["authorization"] == "Token sample"
    assert headers["user-agent"].startswith("Mozilla/5.0")
    assert "Token sample" not in result.output
    content_type = headers["content-type"]
    assert content_type.startswith("multipart/form-data; boundary=")
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\n\r\n".encode() + body
    )
    parts = [
        (
            part.get_param("name", header="content-disposition"),
            part.get_filename(),
            part.get_payload(decode=True),
        )
        for part in message.iter_parts()
    ]
    assert parts == [
        ("assetsDirPath", None, b"/assets/"),
        ("file[]", "one.png", b"\x00first"),
        ("file[]", "two.bin", b"second"),
    ]


@pytest.mark.parametrize(
    "data",
    [
        {"errFiles": ["one.txt"], "succMap": {"one.txt": "assets/one.txt"}},
        {"succMap": {}},
    ],
)
def test_upload_detects_partial_result_without_retry(
    server: Mock, tmp_path: Path, data: dict
) -> None:
    path = tmp_path / "one.txt"
    path.write_text("example")
    server.reply_json({"code": 0, "data": data})
    result = CliRunner().invoke(main, ["asset", "upload", str(path)])
    assert result.exit_code == 1
    assert not result.stdout
    assert "assets may already exist" in result.stderr
    assert len(server.requests) == 1


def test_upload_rejects_duplicate_basenames_before_request(
    server: Mock, tmp_path: Path
) -> None:
    first, second = tmp_path / "a" / "same.png", tmp_path / "b" / "same.png"
    for path in (first, second):
        path.parent.mkdir()
        path.touch()
    result = CliRunner().invoke(main, ["asset", "upload", str(first), str(second)])
    assert result.exit_code == 1
    assert "filenames must be distinct" in result.stderr
    assert not server.requests


def test_get_asset_saves_original_bytes_and_never_overwrites(server: Mock) -> None:
    server.media_type = "image/png"
    server.response = b"\x00asset bytes"
    runner = CliRunner()
    result = runner.invoke(main, ["asset", "get", "assets/nested/test.png", "--temp"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    output = Path(payload["path"])
    assert output.name == "test.png"
    assert output.read_bytes() == server.response
    assert payload == {
        "asset": "assets/nested/test.png",
        "path": str(output),
        "bytes": len(server.response),
        "mediaType": "image/png",
    }
    [(endpoint, headers, body)] = server.requests
    assert endpoint == "/prefix/api/file/getFile"
    assert headers["content-type"] == "application/json"
    assert json.loads(body) == {"path": "/data/assets/nested/test.png"}
    server.response = b"replacement"
    collision = runner.invoke(
        main, ["asset", "get", "assets/nested/test.png", "-o", str(output)]
    )
    assert collision.exit_code == 1
    assert "already exists" in collision.stderr
    assert output.read_bytes() == b"\x00asset bytes"


def test_get_asset_distinguishes_api_error_from_json_file(
    server: Mock, tmp_path: Path
) -> None:
    output = tmp_path / "out.json"
    runner = CliRunner()
    command = ["asset", "get", "assets/example.json", "-o", str(output)]
    server.reply_json({"code": -1, "msg": "missing"})
    result = runner.invoke(main, command)
    assert result.exit_code == 1
    assert "API code -1 (missing)" in result.stderr
    assert not output.exists()
    server.reply_json({"sample": [1, 2]})
    assert runner.invoke(main, command).exit_code == 0
    assert output.read_bytes() == server.response


@pytest.mark.parametrize(
    "asset",
    [
        "/assets/test.png",
        "assets/../test.png",
        "assets/./test.png",
        "assets//test.png",
        "assets/test\\file.png",
    ],
)
def test_get_asset_rejects_nonrelative_paths(server: Mock, asset: str) -> None:
    result = CliRunner().invoke(main, ["asset", "get", asset, "--temp"])
    assert result.exit_code == 1
    assert not server.requests
