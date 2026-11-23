"""Instance configuration and session-local selection."""

import json
import os
import sqlite3
import time
import tomllib
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import click

SESSION_ENV_VARS = (("dsh", "DSH_SESSION_ID"),)
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class Instance:
    url: str
    headers_file: Path
    user_agent: str = field(default=BROWSER_USER_AGENT, repr=False)

    def headers(self) -> dict[str, str]:
        try:
            raw = json.loads(self.headers_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise click.ClickException(
                f"Cannot read headers JSON: {self.headers_file}"
            ) from None
        if not isinstance(raw, dict) or not all(
            isinstance(value, str) for value in raw.values()
        ):
            raise click.ClickException(
                f"Expected a flat JSON object of string headers: {self.headers_file}"
            )
        headers = {
            key: value for key, value in raw.items() if key.lower() != "user-agent"
        }
        headers["User-Agent"] = self.user_agent
        return headers


def config_dir() -> Path:
    override = os.environ.get("SYC_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser() / "syc"


def current_session() -> tuple[str, str] | None:
    for harness, env_var in SESSION_ENV_VARS:
        if value := os.environ.get(env_var):
            return harness, value
    return None


def load_instances(root: Path) -> dict[str, Instance]:
    path = root / "config.toml"
    try:
        with path.open("rb") as handle:
            config = tomllib.load(handle)
    except FileNotFoundError:
        raise click.ClickException(f"Configuration file not found: {path}") from None
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        raise click.ClickException(f"Cannot read TOML configuration: {path}") from None
    entries = config.get("instances", {})
    if not isinstance(entries, dict):
        raise click.ClickException(f"Expected an [instances] table in {path}")
    instances: dict[str, Instance] = {}
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            raise click.ClickException(f"Expected an instance table for {name!r}")
        url = entry.get("url")
        if not isinstance(url, str) or not _valid_url(url):
            raise click.ClickException(
                f"Instance {name!r}: url must be an HTTP(S) base URL without credentials, query or fragment"
            )
        headers_file = entry.get("headers_file")
        if not isinstance(headers_file, str) or not headers_file:
            raise click.ClickException(
                f"Instance {name!r}: headers_file must be a path"
            )
        user_agent = entry.get("user_agent", BROWSER_USER_AGENT)
        if (
            not isinstance(user_agent, str)
            or not user_agent.strip()
            or "\r" in user_agent
            or "\n" in user_agent
        ):
            raise click.ClickException(
                f"Instance {name!r}: user_agent must be a non-empty single line"
            )
        instances[name] = Instance(
            url.rstrip("/"), root / Path(headers_file), user_agent
        )
    return instances


def _valid_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        _ = parts.port  # Validate the configured port, if present.
    except ValueError:
        return False
    return (
        parts.scheme in {"http", "https"}
        and bool(parts.hostname)
        and parts.username is None
        and not any(c in url for c in "?# \r\n\t")
    )


def _create_sessions(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE sessions ("
        "harness TEXT NOT NULL, session_id TEXT NOT NULL, instance TEXT NOT NULL, "
        "updated_at REAL NOT NULL, PRIMARY KEY (harness, session_id))"
    )


_MIGRATIONS = (_create_sessions,)


def _migrate(db: sqlite3.Connection) -> None:
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version == len(_MIGRATIONS):
        return
    with db:
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if not 0 <= version <= len(_MIGRATIONS):
            raise click.ClickException(
                f"Unsupported session database version: {version}"
            )
        for next_version, migrate in enumerate(
            _MIGRATIONS[version:], start=version + 1
        ):
            migrate(db)
            db.execute(f"PRAGMA user_version = {next_version}")


def get_session_instance(path: Path, session: tuple[str, str]) -> str | None:
    if not path.exists():
        return None
    with closing(sqlite3.connect(path, timeout=5)) as db:
        _migrate(db)
        row = db.execute(
            "SELECT instance FROM sessions WHERE harness = ? AND session_id = ?",
            session,
        ).fetchone()
    return row[0] if row else None


def set_session_instance(path: Path, session: tuple[str, str], instance: str) -> None:
    harness, session_id = session
    with closing(sqlite3.connect(path, timeout=5)) as db:
        _migrate(db)
        with db:
            db.execute(
                "INSERT INTO sessions (harness, session_id, instance, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(harness, session_id) DO UPDATE SET "
                "instance = excluded.instance, updated_at = excluded.updated_at",
                (harness, session_id, instance, time.time()),
            )
            db.execute(
                "DELETE FROM sessions WHERE rowid IN (SELECT rowid FROM sessions WHERE harness = ? "
                "ORDER BY updated_at DESC, rowid DESC LIMIT -1 OFFSET 9999)",
                (harness,),
            )


class NoSelectedInstance(click.ClickException):
    """No precedence rule selected an instance."""


def _choices(instances: dict[str, Instance]) -> str:
    listing = "\n".join(f"{name}  {item.url}" for name, item in instances.items())
    return (
        f"Configured instances:\n{listing or '(none)'}\n"
        "Select one with `syc use <name>` or `syc -i <name> ...`."
    )


def require_instance(instances: dict[str, Instance], name: str) -> Instance:
    if name not in instances:
        raise click.ClickException(f"Unknown instance {name!r}.\n{_choices(instances)}")
    return instances[name]


def resolve_instance(
    instances: dict[str, Instance], state: Path, flag: str | None
) -> tuple[str, str]:
    if flag is not None:
        name, source = flag, "flag"
    elif name := os.environ.get("SYC_INSTANCE"):
        source = "env"
    elif (session := current_session()) and (
        saved := get_session_instance(state, session)
    ) is not None:
        name, source = saved, "session"
    elif len(instances) == 1:
        name, source = next(iter(instances)), "only"
    else:
        raise NoSelectedInstance(f"No instance selected.\n{_choices(instances)}")

    require_instance(instances, name)
    return name, source
