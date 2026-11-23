# MCP tools

Most SiYuan MCP tools are action-dispatched: one tool such as `document` takes
an `action` plus the fields that action needs.

## Discover, describe, call

1. `syc tools` lists tool names with one-line summaries.
2. `syc describe TOOL` prints the full description, including per-action
   signatures such as `get(id), create(notebook, parentID, title, markdown?)`.
   `--schema` adds the JSON schema. The schema lists the fields of all actions
   together and marks only `action` as required, so take each action's fields
   from the signatures in the description.
3. `syc call TOOL JSON` takes one JSON object as an argument, or `-` to read it
   from stdin.

Good: describe, then call with the documented names.

```sh
syc describe document
syc call document '{"action":"get","id":"20250101120000-abcdefg"}'
```

Bad: guessed tool, action, and field names.

```sh
syc call documents '{"action":"read","docId":"20250101120000-abcdefg"}'
```

## Pass JSON safely

Use a quoted heredoc for prose, quotes, or newlines. The shell then passes the
text unchanged.

Good:

```sh
syc call block - <<'JSON'
{"action":"append","parentID":"20250101120000-abcdefg","dataType":"markdown","data":"It's done.\n\n- next step"}
JSON
```

Bad: the apostrophe in `It's` ends the single-quoted shell string.

```sh
syc call block '{"action":"append","parentID":"20250101120000-abcdefg","dataType":"markdown","data":"It's done."}'
```

## Read the result

stdout is the MCP result:

```json
{"content": [{"type": "text", "text": "3.8.9"}], "isError": false, "structuredContent": null}
```

A tool error exits with 1 and keeps the result on stdout:

```json
{"content": [{"type": "text", "text": "id is required"}], "isError": true, "structuredContent": null}
```

Fix the arguments from the message instead of rerunning the same call. Image or
other binary content blocks carry a local `path` in place of base64 data.

## Find documents and blocks

- Use `search` for keywords and the read-only `sql` tool for structure. Run
  `syc call sql '{"action":"schema"}'` once before writing queries.
- Identify documents and blocks by ID. Display paths are not unique.
- `sql` returns a Markdown table whose columns are sorted alphabetically, not
  in `SELECT` order. Read values by header name. A list of block links follows
  the table, so select only the columns you need and set `LIMIT`.

Good: locate by query, then act on the returned ID.

```sh
syc call sql - <<'JSON'
{"action":"query","stmt":"SELECT id, content FROM blocks WHERE type = 'd' AND content LIKE '%weekly review%' LIMIT 10"}
JSON
```

Bad: deriving a document from its display path.

```sh
syc call document '{"action":"get","path":"/Projects/Weekly review"}'
```
