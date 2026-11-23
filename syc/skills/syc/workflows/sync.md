# Sync

`syc sync` calls the native MCP `sync` tool with `{"action":"perform"}`
(full upload and download) on the selected instance. It does not trigger sync
on a peer, retry, or verify that replicas agree. Inspect the result before
choosing any further sync action.
