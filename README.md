# siyuan-syc

`syc` lets agents work with SiYuan instances over native MCP, transfer local
attachments, and sync instances over HTTP. It requires Python 3.11 or later.

Install the release wheel:

```sh
uv tool install https://github.com/TTTPOB/siyuan-syc/releases/download/v0.1.1/siyuan_syc-0.1.1-py3-none-any.whl
```

Follow the [configuration guide](syc/skills/syc/DEPLOYMENT.md) to add an instance and,
optionally, install the skill for DSH, Codex, Claude Code, or OpenCode.
Per-session `syc use` currently supports DSH; other hosts select with `-i` or
`SYC_INSTANCE`.

Use `syc instances` to list instances, `syc tools` to discover the selected
instance's tools, and `syc describe TOOL --schema` before `syc call TOOL ARGS`.

## Sync

After a batch of writes, run `syc sync` once on the selected instance. To push
those writes to the cloud and then pull them on a replica, name the writer
first and the replica second:

```sh
syc sync server desktop
```

`syc sync [INSTANCE ...]` processes explicit names in order and stops at the
first failure. Use either positional names or `syc -i NAME sync`, not both.
Stdout contains one JSON result for all attempted instances. Check the exit
code, and on failure report the instance and message to the user; do not loop
or retry automatically. A successful sync does not prove that replicas have
identical data.

Development: `uv sync --extra test && uv run pytest`; build with `uv build`.
