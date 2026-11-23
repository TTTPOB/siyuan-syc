import json
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from click.testing import CliRunner

from syc.cli import main
from syc.config import BROWSER_USER_AGENT

TEMPLATE = "Fichiers (%d/%d)<br>Blocs %d/%d<br>Octets %s/%s"
SUCCESS = "Fichiers (0/1)<br>Blocs 0/0<br>Octets 0 B/5 kB"
FAILURE = "Échec de la synchronisation : opération en cours"


@dataclass
class Mock:
    requests: list[tuple[str, str, dict[str, str], bytes]] = field(default_factory=list)
    replies: deque[object] = field(default_factory=deque)

    def attempt(
        self,
        before: tuple[int, str],
        after: tuple[int, str] | None = None,
        *,
        perform_code: int = 0,
        perform_msg: str = "",
    ) -> None:
        self.replies.extend(
            [
                {"code": 0, "data": {"conf": {"appearance": {"lang": "fr"}}}},
                {"_kernel": {"150": TEMPLATE}},
                sync_info(*before),
                {"code": perform_code, "msg": perform_msg, "data": None},
            ]
        )
        if after is not None:
            self.replies.append(sync_info(*after))

    def paths(self) -> list[tuple[str, str]]:
        return [(method, path) for method, path, _, _ in self.requests]


def sync_info(synced: int, stat: str) -> dict:
    return {
        "code": 0,
        "msg": "",
        "data": {"synced": synced, "stat": stat, "kernels": [], "kernel": "test"},
    }


def attempt_paths(name: str) -> list[tuple[str, str]]:
    return [
        ("POST", f"/{name}/api/setting/getSection"),
        ("GET", f"/{name}/appearance/langs/fr.json"),
        ("POST", f"/{name}/api/sync/getSyncInfo"),
        ("POST", f"/{name}/api/sync/performSync"),
        ("POST", f"/{name}/api/sync/getSyncInfo"),
    ]


@pytest.fixture
def server(config_root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Mock]:
    mock = Mock()

    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            headers = {key.lower(): value for key, value in self.headers.items()}
            mock.requests.append(
                (
                    self.command,
                    self.path,
                    headers,
                    self.rfile.read(int(headers.get("content-length", 0))),
                )
            )
            if not mock.replies:
                self.send_error(500, "Unexpected request")
                return
            body = json.dumps(mock.replies.popleft()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = respond
        do_POST = respond

        def log_message(self, format: str, *args: object) -> None:
            return

    monkeypatch.setenv("no_proxy", "127.0.0.1,<local>,10.*")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:8181")
    (config_root / "headers.json").write_text(
        '{"Authorization":"Token sample", "user-agent":"wrong", "content-TYPE":"wrong"}'
    )
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        (config_root / "config.toml").write_text(
            f'[instances.server]\nurl = "http://127.0.0.1:{http.server_port}/server"\n'
            'headers_file = "headers.json"\n'
        )
        thread = Thread(target=http.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield mock
        finally:
            http.shutdown()
            thread.join()


def test_sync_success_with_lan_stats(server: Mock) -> None:
    stat = SUCCESS + '<br data-type="lanSyncTraffic">&emsp;Réseau local 5 kB'
    server.attempt((1, ""), (2, stat))
    result = CliRunner().invoke(main, ["sync"])
    assert result.exit_code == 0, result.output
    assert result.stderr == "syc: instance=server (only)\n"
    assert json.loads(result.stdout) == {
        "content": [{"type": "text", "text": f"server: {stat}"}],
        "isError": False,
        "structuredContent": {
            "instances": [{"instance": "server", "ok": True, "message": stat}]
        },
    }
    assert server.paths() == attempt_paths("server")
    for method, _, headers, _ in server.requests:
        assert headers["authorization"] == "Token sample"
        assert headers["user-agent"] == BROWSER_USER_AGENT
        if method == "POST":
            assert headers["content-type"] == "application/json"
    assert [
        json.loads(body) if body else None for _, _, _, body in server.requests
    ] == [{"namespace": "appearance"}, None, {}, {}, {}]


@pytest.mark.parametrize(
    ("after", "did_not_run"),
    [((1, FAILURE), False), ((2, FAILURE), False), ((1, SUCCESS), True)],
)
def test_sync_failure_reports_stat(
    server: Mock, after: tuple[int, str], did_not_run: bool
) -> None:
    server.attempt((1, SUCCESS), after)
    result = CliRunner().invoke(main, ["-i", "server", "sync"])
    assert result.exit_code == 1, result.output
    assert result.stderr == "syc: instance=server (flag)\n"
    payload = json.loads(result.stdout)
    assert payload["isError"] is True
    [attempt] = payload["structuredContent"]["instances"]
    assert attempt["instance"] == "server"
    assert attempt["ok"] is False
    assert after[1] in attempt["message"]
    assert ("Sync did not appear to run" in attempt["message"]) is did_not_run
    assert server.paths() == attempt_paths("server")


def test_sync_stops_on_api_rejection(server: Mock) -> None:
    server.attempt((1, SUCCESS), perform_code=-1, perform_msg="Missing field [upload]")
    result = CliRunner().invoke(main, ["sync"])
    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert payload["isError"] is True
    assert "Missing field [upload]" in payload["content"][0]["text"]
    assert server.paths() == attempt_paths("server")[:-1]


def test_sync_stops_at_first_failed_instance(
    server: Mock, config_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = config_root / "config.toml"
    config = path.read_text()
    path.write_text(config + config.replace("server", "desktop"))
    monkeypatch.setenv("SYC_INSTANCE", "server")
    server.attempt((1, SUCCESS), (2, SUCCESS))
    server.attempt((3, SUCCESS), (4, FAILURE))
    result = CliRunner().invoke(main, ["sync", "desktop", "server", "desktop"])
    assert result.exit_code == 1, result.output
    assert result.stderr.splitlines() == [
        "syc: instance=desktop (argument)",
        "syc: instance=server (argument)",
    ]
    payload = json.loads(result.stdout)
    assert payload["isError"] is True
    attempts = payload["structuredContent"]["instances"]
    assert [(row["instance"], row["ok"]) for row in attempts] == [
        ("desktop", True),
        ("server", False),
    ]
    assert FAILURE in attempts[1]["message"]
    assert server.paths() == attempt_paths("desktop") + attempt_paths("server")


def test_sync_rejects_ambiguous_instance_selection(server: Mock) -> None:
    result = CliRunner().invoke(main, ["-i", "server", "sync", "desktop"])
    assert result.exit_code == 2
    assert "not both" in result.stderr
    assert not server.requests
