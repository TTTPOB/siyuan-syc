---
name: syc
description: Read and edit SiYuan (思源笔记) notes, upload or download note attachments, and trigger SiYuan sync with the syc CLI. Use whenever a task touches SiYuan notebooks, documents, blocks, databases, assets, search, or sync.
---

# SiYuan with syc

`syc` runs official SiYuan MCP tools and uses HTTP for local-file attachment
transfer and sync. Commands print JSON on stdout. Commands that reach an
instance also print `syc: instance=<name> (<source>)` on stderr for each
instance they attempt.

If `syc` is missing, no instance is configured, or requests fail with HTTP
errors, read [DEPLOYMENT.md](DEPLOYMENT.md).

## Choose the instance first

`syc` picks the instance in this order: `-i NAME`, then `SYC_INSTANCE`, then
this session's `syc use NAME`, then the only configured instance. With several
instances and no selection, commands that reach an instance fail and list the
configured instances. `syc sync INSTANCE ...` selects its instances directly;
do not combine positional names with `-i`.

- In DSH, run `syc use NAME` once per session. Later commands in the same
  session need no flag.
- Other hosts do not have per-session selection yet. Pass `-i NAME` on every
  command.
- A subagent runs in its own session and does not inherit your `syc use`.
  Name the instance in the task you delegate.
- When you cannot tell which instance the user means, ask. Instances can hold
  different data, and replicas of the same notebooks can lag behind each other.

Good: check, then select once.

```sh
syc instances
syc use server
syc call notebook '{"action":"list"}'
```

Good: delegation names the instance.

> Edit the meeting note in SiYuan instance `server`. Run `syc use server`
> before any other `syc` command.

Bad: delegation without an instance.

> Edit the meeting note in SiYuan.

The subagent starts with no selection. Its first command fails, and it may
pick an instance arbitrarily to recover.

## Read the workflow for the task

| Task | Read |
|---|---|
| Notes, blocks, search, SQL, databases, any other MCP tool | [workflows/mcp.md](workflows/mcp.md) |
| Put a local file into a note; view or save an attachment | [workflows/assets.md](workflows/assets.md) |
| Sync after a batch of writes, or push from a writer then pull on a replica | [workflows/sync.md](workflows/sync.md) |
| Install, configure, HTTP 403 or connection errors | [DEPLOYMENT.md](DEPLOYMENT.md) |

## Rules for every command

- Check the exit code. 0 is success. 1 is either a `call` or `sync` error
  result on stdout with `"isError": true`, or a CLI error with a message on
  stderr. 2 is a usage error.
- Do not retry a failed write automatically. An error or timeout does not
  prove that nothing was written; read the target back first.
- Learn tools from `syc describe` on the instance, not from memory. Tools and
  actions change between SiYuan versions.
