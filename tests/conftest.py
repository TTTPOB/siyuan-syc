from pathlib import Path

import pytest


@pytest.fixture
def config_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SYC_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("SYC_INSTANCE", raising=False)
    monkeypatch.delenv("DSH_SESSION_ID", raising=False)
    (tmp_path / "config.toml").write_text(
        '[instances.server]\nurl = "https://notes.example.invalid"\nheaders_file = "headers.json"\n',
        encoding="utf-8",
    )
    (tmp_path / "headers.json").write_text("{}", encoding="utf-8")
    return tmp_path
