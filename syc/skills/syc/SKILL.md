---
name: syc
description: Use syc to work with SiYuan notebooks, documents, blocks, assets, and sync across explicitly selected instances.
---

# SiYuan with syc

Run `syc instances` and `syc current` to check which instance will be used.
In DSH, run `syc use <name>` once per session. Pass `syc -i <name> ...` when
delegating to subagents; their sessions do not inherit this choice. Other hosts
can select with `-i` or `SYC_INSTANCE`.

Read the workflow for the current operation:

- [MCP](workflows/mcp.md): discover, describe, and call tools.
- [Assets](workflows/assets.md): upload, save, and inspect attachments.
- [Sync](workflows/sync.md): sync one instance.
- [Deployment](DEPLOYMENT.md): install and configure instances.
