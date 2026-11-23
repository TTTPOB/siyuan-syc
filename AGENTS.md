# siyuan-syc agent guide

`syc` is a thin CLI over the official SiYuan MCP server plus raw HTTP attachment
transfer. Read `docs/adr/` before changing behaviour.

## Public repository

This repository is public. Never commit hostnames, instance names, paths,
tokens, proxy settings, or other details of a real deployment. Use
`*.example.invalid`, instance names `server` and `desktop`, and synthetic data
in code, tests, skill files, docs, and commit messages.

## Decisions

- Record significant design decisions as ADRs in `docs/adr/`, named
  `YYYY-MM-DD-<slug>.md` with the title `# ADR YYYY-MM-DD：<decision>`. Use the
  date the decision was accepted; no sequence numbers.
- Keep accepted ADRs as written. To change a decision, add a new ADR and mark
  the old one `状态：已被 [ADR ...](<file>) 取代。`.

## Development

```sh
uv sync --extra test
uv run pytest
uvx ruff check && uvx ruff format --check && uvx pyrefly check
uv build
```

- Tests use temp files and a loopback mock HTTP server only. Live checks
  against real instances stay outside the repository.
- Keep the MCP SDK import lazy; non-MCP commands must not import it.
- The bundled skill in `syc/skills/syc/` ships in the wheel. Update it with any
  change to command behaviour or output.
- Release: bump `version` in `pyproject.toml` and the wheel URL in README and
  `DEPLOYMENT.md`, commit, then push a `vX.Y.Z` tag; CI attaches the wheel to
  the GitHub release.
