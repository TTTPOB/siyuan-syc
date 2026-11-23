# ADR 2026-11-23：同步使用 MCP 的 perform

状态：已接受。

## 背景

触发思源同步有两个入口：HTTP `POST /api/sync/performSync`，以及官方 MCP `sync` 工具（actions：`perform`、`upload`、`download`、`status`）。此前的插件使用 HTTP 入口，只能报告“请求已被接受”。

对照思源 3.8.9 源码：

- [MCP `sync`](https://github.com/siyuan-community/siyuan/blob/bb6dbe8bba589cdd94660771a15955e0b37751ef/kernel/mcp/tools/sync.go#L48-L53) 的 `perform` 调用 `model.SyncData(true)`，失败时返回 `isError`。
- [HTTP `performSync`](https://github.com/siyuan-community/siyuan/blob/bb6dbe8bba589cdd94660771a15955e0b37751ef/kernel/api/sync.go#L401-L432) 在同步模式不为 3 时调用同一函数，但不回传该错误；模式为 3 时改走单向同步。

## 决策

**`syc sync` 调用所选实例 MCP `sync` 工具的 `{"action":"perform"}`（完整上传加下载）。** 结果按 MCP 输出，`isError` 时退出码为 1。

- 只同步所选的一个实例，不自动串联其他实例，不重试。
- 成功只表示该实例完成了同步请求，不表示各副本数据一致。需要传到另一副本时，由调用方依次同步写入方和接收方。
- 不保留 HTTP `performSync` 入口。若将来需要手动模式（模式 3）下的单向语义，另行决策。

## 依据

MCP 入口会报告同步失败，HTTP 入口不会；对 agent 而言，能看到失败比只看到“已接受”更重要。
