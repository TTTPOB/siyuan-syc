# Deployment

Install a release wheel and install the bundled skill for your host:

```sh
uv tool install https://github.com/TTTPOB/siyuan-syc/releases/download/v0.1.0/siyuan_syc-0.1.0-py3-none-any.whl
syc setup dsh
```

Replace `dsh` with `codex`, `claude`, or `opencode` as needed. Add `--remove`
to uninstall the managed skill. Setup does not change host MCP configuration.

The config directory is `${SYC_CONFIG_DIR:-${XDG_CONFIG_HOME:-~/.config}/syc}`.
Place the following in `config.toml`:

```toml
[instances.server]
url = "https://notes.example.invalid"
headers_file = "headers/server.json"
# user_agent = "Mozilla/5.0 ..."
```

The URL is the SiYuan base URL; `syc` appends `/mcp` for MCP. The headers file
is an absolute path or relative to the config directory. It contains a flat
JSON object of string headers, for example `{"Authorization":"Token <token>"}`.
Keep credentials private; `syc` reads them at request time and supplies a
browser User-Agent, overriding any value in the JSON.

Selection order: `-i/--instance`, `SYC_INSTANCE`, the current session's
choice in `state.db`, then the sole configured instance. There is no global
default. Session selection currently supports DSH (`DSH_SESSION_ID`) only;
other hosts use `-i` or `SYC_INSTANCE`.
