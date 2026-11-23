# siyuan-syc

`syc` lets agents work with SiYuan instances over native MCP and transfer local
attachments over HTTP. It requires Python 3.11 or later.

Install the release wheel:

```sh
uv tool install https://github.com/TTTPOB/siyuan-syc/releases/download/v0.1.0/siyuan_syc-0.1.0-py3-none-any.whl
```

Follow the [configuration guide](syc/skills/syc/DEPLOYMENT.md) to add an instance and,
optionally, install the skill for DSH, Codex, Claude Code, or OpenCode.
Per-session `syc use` currently supports DSH; other hosts select with `-i` or
`SYC_INSTANCE`.

Use `syc instances` to list instances, `syc tools` to discover the selected
instance's tools, and `syc describe TOOL --schema` before `syc call TOOL ARGS`.

Development: `uv sync --extra test && uv run pytest`; build with `uv build`.
