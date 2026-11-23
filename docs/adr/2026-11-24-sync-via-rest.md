# ADR 2026-11-24：通过 REST 同步并核对结果

状态：已接受。取代 [ADR 2026-11-23](2026-11-23-sync-via-mcp-perform.md)。

## 背景

思源 3.8.9 的写请求中间件 [`CheckReadonly`](https://github.com/siyuan-community/siyuan/blob/bb6dbe8bba589cdd94660771a15955e0b37751ef/kernel/model/session.go#L181-L228) 持有 `dataImportAccess` 读租约。MCP `sync` 的 `perform` 在同一请求内应用下载的变更时，[尝试取得写租约](https://github.com/siyuan-community/siyuan/blob/bb6dbe8bba589cdd94660771a15955e0b37751ef/kernel/model/sync_checkout_state.go#L179-L185) 会被自己持有的读租约挡住。只上传不走这一步；REST `/api/sync/performSync` 则在进入处理函数前释放读租约。

## 决策

- 使用与附件相同的 HTTP 传输。先后读取 `POST /api/sync/getSyncInfo` 的 `data.synced`（毫秒时间戳）和 `data.stat`（状态文字），中间同步调用 `POST /api/sync/performSync`，请求体为 `{}`。[状态响应](https://github.com/siyuan-community/siyuan/blob/bb6dbe8bba589cdd94660771a15955e0b37751ef/kernel/api/sync.go#L364-L380) 还包含 `data.kernels` 和 `data.kernel`。
- [`performSync`](https://github.com/siyuan-community/siyuan/blob/bb6dbe8bba589cdd94660771a15955e0b37751ef/kernel/api/sync.go#L401-L432) 在正常双向模式丢弃内核同步错误，且[开始同步时就更新 `synced`](https://github.com/siyuan-community/siyuan/blob/bb6dbe8bba589cdd94660771a15955e0b37751ef/kernel/model/sync.go#L370-L388)。因此，只有时间戳变化且状态匹配内核成功统计模板时才报告成功。使用 [`getSection`](https://github.com/siyuan-community/siyuan/blob/bb6dbe8bba589cdd94660771a15955e0b37751ef/kernel/api/setting_read.go#L114-L137) 的 `data.conf.appearance.lang`，从同一实例的 [`/appearance/langs/<lang>.json`](https://github.com/siyuan-community/siyuan/blob/bb6dbe8bba589cdd94660771a15955e0b37751ef/kernel/server/serve.go#L798-L868) 读取 [`_kernel["150"]`](https://github.com/siyuan-community/siyuan/blob/bb6dbe8bba589cdd94660771a15955e0b37751ef/kernel/model/repository.go#L2456-L2485)。如果内核推进时间戳后提前失败并保留了上一次的成功状态，这个判据仍可能误报。
- 同步未确认时报告当前状态；两个值都没变化时提示检查同步开关、思源账号和同步提供商。直接返回 HTTP 或 API 错误，不重试。完全手动模式（模式 3）需要显式上传/下载方向，`syc sync` 不代选方向。
- 无参数时按现有规则选实例。显式传入多个实例时按顺序同步，首次失败即止；一条 JSON 包含所有已尝试实例的结果，不推断副本已经一致。
