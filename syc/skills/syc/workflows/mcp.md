# MCP tools

1. Run `syc tools` to see the available tools on the selected instance.
2. Run `syc describe TOOL --schema` to learn the tool's actions and arguments.
3. Run `syc call TOOL ARGS`, or use `-` to send JSON on stdin:

```sh
syc call system - <<'JSON'
{"action":"version"}
JSON
```

The result is JSON, including `isError`. A tool error exits with status 1
and still returns its MCP result. Binary MCP content is saved to local files
and carries a `path` instead of inline base64.
