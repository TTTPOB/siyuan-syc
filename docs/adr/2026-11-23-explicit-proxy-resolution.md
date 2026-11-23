# ADR 2026-11-23：显式解析代理设置

状态：已接受。

## 背景

在 WSL 等环境中，`NO_PROXY` 常带有 Windows 风格的条目，例如 `<local>` 和 `10.*`。实测 httpx 在 `trust_env=True` 时会把每个条目解析成 URL 模式，遇到这类条目在创建客户端时就抛出 `InvalidURL`，导致任何请求都无法发出。迁移到 MCP SDK 2.x 使用的 httpx2 后沿用同一做法，未再验证 httpx2 自身的解析行为。

## 决策

**所有 httpx2 客户端（MCP 传输和附件 HTTP）都使用 `trust_env=False`，代理由标准库按实例决定：`urllib.request.proxy_bypass(host)` 为真时直连，否则使用 `urllib.request.getproxies()` 中对应 scheme 的代理。**

- 仍然遵循 `HTTP(S)_PROXY` 和 `NO_PROXY`，只是换成标准库解析。`NO_PROXY` 按 `host` 与 `host:port` 匹配；`<local>`、`10.*` 这类条目不会报错，但标准库也不把它们当通配符。
- 不清理或改写用户的环境变量。

## 依据

单元测试使用带 `<local>` 和通配条目的 `NO_PROXY`，验证代理与直连判断。2026-11-23 在保持原有代理环境不变的机器上完成了对两个实例的只读实测。
