import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
from click.testing import CliRunner

from syc.cli import main
from syc.config import get_session_instance, load_instances, set_session_instance
from syc.transport import proxy_for


def _add_desktop(root: Path) -> None:
    with (root / "config.toml").open("a", encoding="utf-8") as handle:
        handle.write(
            '\n[instances.desktop]\nurl = "https://desktop.example.invalid"\n'
            'headers_file = "headers.json"\n'
        )


def test_instance_resolution_order(
    config_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()

    def current(*flags: str) -> tuple[str, str]:
        result = runner.invoke(main, [*flags, "current"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        return payload["name"], payload["source"]

    assert current() == ("server", "only")
    assert not (config_root / "state.db").exists()
    _add_desktop(config_root)
    monkeypatch.setenv("DSH_SESSION_ID", "session-a")
    assert runner.invoke(main, ["use", "desktop"]).exit_code == 0
    assert current() == ("desktop", "session")
    listed = runner.invoke(main, ["instances"])
    assert [
        entry["name"] for entry in json.loads(listed.stdout) if entry["current"]
    ] == ["desktop"]
    monkeypatch.setenv("SYC_INSTANCE", "server")
    assert current() == ("server", "env")
    assert current("-i", "desktop") == ("desktop", "flag")


def test_missing_or_unknown_instance_lists_choices(config_root: Path) -> None:
    _add_desktop(config_root)
    runner = CliRunner()
    for args in (["current"], ["-i", "unknown", "current"]):
        result = runner.invoke(main, args)
        assert result.exit_code == 1
        assert not result.stdout
        assert "server  https://notes.example.invalid" in result.stderr
        assert "desktop  https://desktop.example.invalid" in result.stderr
        assert "syc use <name>" in result.stderr
        assert "syc -i <name> ..." in result.stderr
    listed = runner.invoke(main, ["instances"])
    assert not any(entry["current"] for entry in json.loads(listed.stdout))
    use = runner.invoke(main, ["use", "server"])
    assert use.exit_code == 1
    assert "export SYC_INSTANCE=NAME" in use.stderr and "-i" in use.stderr


def test_session_upsert_and_prune_are_scoped_to_harness(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    set_session_instance(path, ("dsh", "same"), "server")
    set_session_instance(path, ("other", "same"), "desktop")
    with closing(sqlite3.connect(path)) as db, db:
        db.executemany(
            "INSERT INTO sessions VALUES (?, ?, ?, ?)",
            (("dsh", str(n), "server", n) for n in range(10_001)),
        )
    set_session_instance(path, ("dsh", "same"), "desktop")
    assert get_session_instance(path, ("dsh", "same")) == "desktop"
    assert get_session_instance(path, ("other", "same")) == "desktop"
    with closing(sqlite3.connect(path)) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM sessions WHERE harness = 'dsh'"
        ).fetchone() == (9999,)
        assert db.execute(
            "SELECT session_id FROM sessions WHERE harness = 'dsh' ORDER BY updated_at, rowid LIMIT 1"
        ).fetchone() == ("3",)
        assert db.execute("PRAGMA user_version").fetchone() == (1,)


def test_headers_are_loaded_at_call_time_and_user_agent_wins(config_root: Path) -> None:
    config = config_root / "config.toml"
    with config.open("a", encoding="utf-8") as handle:
        handle.write('user_agent = "Mozilla/5.0 custom"\n')
    instance = load_instances(config_root)["server"]
    path = config_root / "headers.json"
    path.write_text(
        '{"Authorization":"example1","uSeR-aGeNt":"ignored","user-agent":"ignored"}'
    )
    assert instance.headers() == {
        "Authorization": "example1",
        "User-Agent": "Mozilla/5.0 custom",
    }
    path.write_text('{"Authorization":"example2"}')
    assert instance.headers()["Authorization"] == "example2"


def test_headers_file_expands_home(
    config_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(config_root / "home"))
    (config_root / "config.toml").write_text(
        '[instances.server]\nurl = "https://notes.example.invalid"\n'
        'headers_file = "~/creds/server.json"\n'
    )
    instance = load_instances(config_root)["server"]
    assert instance.headers_file == config_root / "home" / "creds" / "server.json"


def test_non_mcp_commands_do_not_import_the_sdk(config_root: Path) -> None:
    code = (
        "import sys; from syc.cli import main\n"
        "try: main(['instances'])\n"
        "except SystemExit: pass\n"
        "assert 'mcp' not in sys.modules, 'mcp imported'\n"
    )
    env = {**os.environ, "SYC_CONFIG_DIR": str(config_root)}
    subprocess.run([sys.executable, "-c", code], check=True, env=env)


def test_proxy_selection_accepts_windows_style_bypass_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1,<local>,10.*,example.test")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:8181")
    assert proxy_for("https://notes.example.invalid") == "http://127.0.0.1:8181"
    assert proxy_for("https://notes.example.test") is None
    assert proxy_for("https://127.0.0.1") is None
