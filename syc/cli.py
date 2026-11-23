"""Click entry point for syc."""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from .config import (
    Instance,
    NoSelectedInstance,
    config_dir,
    current_session,
    load_instances,
    require_instance,
    resolve_instance,
    set_session_instance,
)


@dataclass(frozen=True)
class Context:
    flag: str | None

    def resolve(self, *, report: bool = False) -> tuple[str, str, Instance]:
        root = config_dir()
        instances = load_instances(root)
        name, source = resolve_instance(instances, root / "state.db", self.flag)
        if report:
            click.echo(f"syc: instance={name} ({source})", err=True)
        return name, source, instances[name]


pass_context = click.make_pass_decorator(Context)


def _json(value: Any) -> None:
    click.echo(json.dumps(value, ensure_ascii=False))


@click.group()
@click.version_option(package_name="siyuan-syc")
@click.option(
    "-i",
    "--instance",
    metavar="NAME",
    help="Select a SiYuan instance for this command.",
)
@click.pass_context
def main(ctx: click.Context, instance: str | None) -> None:
    """Work with SiYuan instances over MCP and HTTP."""
    ctx.obj = Context(instance)


@main.command()
@pass_context
def instances(ctx: Context) -> None:
    """List configured instances and the one selected for this command."""
    root = config_dir()
    entries = load_instances(root)
    try:
        selected, _ = resolve_instance(entries, root / "state.db", ctx.flag)
    except NoSelectedInstance:
        selected = None
    _json(
        [
            {"name": name, "url": item.url, "current": name == selected}
            for name, item in entries.items()
        ]
    )


@main.command()
@pass_context
def current(ctx: Context) -> None:
    """Show the resolved instance and its selection source."""
    name, source, instance = ctx.resolve()
    _json({"name": name, "url": instance.url, "source": source})


@main.command()
@click.argument("name")
def use(name: str) -> None:
    """Select an instance for this agent session."""
    session = current_session()
    if session is None:
        raise click.ClickException(
            "No supported agent session found. Use `syc -i <name> ...` or `export SYC_INSTANCE=NAME`."
        )
    root = config_dir()
    require_instance(load_instances(root), name)
    set_session_instance(root / "state.db", session, name)
    _json({"name": name, "source": "session"})


@main.command()
@pass_context
def tools(ctx: Context) -> None:
    """List tools offered by the selected instance."""
    from .mcp_client import list_tools

    _, _, instance = ctx.resolve(report=True)
    _json(
        [
            {
                "name": tool.name,
                "description": (tool.description or "").partition("\n")[0],
            }
            for tool in list_tools(instance)
        ]
    )


@main.command()
@click.argument("tool")
@click.option(
    "--schema",
    is_flag=True,
    help="Include input schema, annotations and output schema.",
)
@pass_context
def describe(ctx: Context, tool: str, schema: bool) -> None:
    """Read a tool's full description and optional schema."""
    from .mcp_client import list_tools

    _, _, instance = ctx.resolve(report=True)
    for entry in list_tools(instance):
        if entry.name == tool:
            keys = {"name", "description"}
            if schema:
                keys.update({"inputSchema", "annotations", "outputSchema"})
            _json(entry.model_dump(mode="json", include=keys))
            return
    raise click.ClickException(
        f"Unknown MCP tool {tool!r}; run `syc tools` to list tools."
    )


def _call(ctx: Context, tool: str, args: dict[str, Any]) -> None:
    from .mcp_client import call_tool, result_json

    _, _, instance = ctx.resolve(report=True)
    result = call_tool(instance, tool, args)
    _json(result_json(result))
    if result.isError:
        raise click.exceptions.Exit(1)


@main.command()
@click.argument("tool")
@click.argument("args")
@pass_context
def call(ctx: Context, tool: str, args: str) -> None:
    """Call an MCP tool with a JSON object or '-' to read stdin."""
    payload = sys.stdin.read() if args == "-" else args
    try:
        arguments = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(
            f"invalid JSON: {exc.msg}", param_hint="ARGS"
        ) from None
    if not isinstance(arguments, dict):
        raise click.BadParameter("expected a JSON object", param_hint="ARGS")
    _call(ctx, tool, arguments)


@main.command()
@pass_context
def sync(ctx: Context) -> None:
    """Request bidirectional sync on one instance; does not verify convergence."""
    _call(ctx, "sync", {"action": "perform"})


@main.group()
def asset() -> None:
    """Upload or download attachment files."""


@asset.command()
@click.argument(
    "files",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
)
@pass_context
def upload(ctx: Context, files: tuple[Path, ...]) -> None:
    """Upload files with distinct basenames."""
    from .assets import upload_assets

    _, _, instance = ctx.resolve(report=True)
    _json(upload_assets(instance, files))


@asset.command()
@click.argument("asset")
@click.option(
    "-o", "output", type=click.Path(dir_okay=False, path_type=Path), metavar="PATH"
)
@click.option("--temp", is_flag=True, help="Save in a new temporary directory.")
@pass_context
def get(ctx: Context, asset: str, output: Path | None, temp: bool) -> None:
    """Download a relative assets/... path without overwriting files."""
    from .assets import get_asset

    if (output is not None) == temp:
        raise click.UsageError("Specify exactly one of -o PATH or --temp.")
    _, _, instance = ctx.resolve(report=True)
    _json(get_asset(instance, asset, output))


@main.command()
@click.argument("host", type=click.Choice(["dsh", "codex", "claude", "opencode"]))
@click.option("--remove", is_flag=True, help="Remove the bundled skill.")
@click.option(
    "--force",
    is_flag=True,
    help="Replace a conflicting skill directory during installation.",
)
def setup(host: str, remove: bool, force: bool) -> None:
    """Install or remove the bundled user-level skill for HOST."""
    from .skill import install_skill, remove_skill, skill_target

    target = skill_target(host)
    operation = remove_skill if remove else install_skill
    changed = operation(target, force=force)
    _json({"host": host, "path": str(target), "changed": changed})
