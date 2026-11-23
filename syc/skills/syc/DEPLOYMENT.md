# Deploying syc

Read this file only when `syc` is missing, no instance is configured, requests
fail with HTTP or connection errors, or the user asks for setup.

## Install

```sh
command -v syc >/dev/null && syc --version || echo "not installed"
uv tool install https://github.com/TTTPOB/siyuan-syc/releases/download/v0.1.1/siyuan_syc-0.1.1-py3-none-any.whl
```

Install the skill for the host the user is working in, only when asked:

```sh
syc setup dsh        # or: codex, claude, opencode
```

`--remove` uninstalls the managed skill. Setup changes nothing else in the
host's configuration.

## Configure instances

The config directory is `${SYC_CONFIG_DIR:-${XDG_CONFIG_HOME:-~/.config}/syc}`.
Keep it `0700` and header files `0600`.

`config.toml`, one table per instance:

```toml
[instances.server]
url = "https://notes.example.invalid"
headers_file = "headers/server.json"

[instances.desktop]
url = "https://desktop.example.invalid"
headers_file = "headers/desktop.json"
# user_agent = "Mozilla/5.0 ..."
```

- `url` is the SiYuan base URL; `syc` appends `/mcp` for MCP calls.
- `headers_file` is relative to the config directory or absolute. It holds a
  flat JSON object of string headers, such as
  `{"Authorization": "Token <api token>"}`. The token is in SiYuan under
  Settings → About → API token.
- `syc` reads headers on every request and always sends a browser
  User-Agent, which replaces any User-Agent in the file.

Ask the user for missing URLs or tokens. Do not print header files.

## Check

```sh
syc instances
syc -i server call system '{"action":"version"}'
```

## Troubleshooting

| Symptom | Check |
|---|---|
| `No instance selected` with a list | Choose one: `syc use NAME` (DSH) or `-i NAME`. |
| HTTP 401 | Token in the header file is wrong or expired. |
| HTTP 403 | A proxy or WAF in front of SiYuan rejects the request; check `user_agent` and the access policy of that proxy. |
| Connection or timeout errors | The instance or its tunnel is down, or the host is asleep. `syc` follows `HTTP(S)_PROXY` and `NO_PROXY` from the environment. |
