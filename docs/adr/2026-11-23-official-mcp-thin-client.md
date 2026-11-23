# ADR 2026-11-23：用薄 Python 客户端包装官方 MCP

状态：已接受。

## 背景

agent 需要读写思源笔记，并在多个思源实例间显式切换。原有接入有两部分：每个实例在 agent 宿主中各注册一套官方 MCP 工具，另有一个只服务单一宿主的插件负责附件上传、下载和同步。每多一个实例，宿主里就多一整套约 30 个工具，渐进式工具检索会返回重复结果；插件也不能给其他 agent 宿主复用。

可选做法有三种：

1. 直接针对思源 HTTP API 写 CLI。覆盖面最全，但思源 API 面大、语义不够统一，维护成本高；早先自写的 Rust CLI 正是因此停止维护。
2. 使用通用的 MCP 转 CLI 工具（例如 mcp2cli）。零开发即可调用全部 MCP 工具，但无法容纳附件传输等非 MCP 命令，也需要第二套实例配置。
3. 自己写一个薄客户端，用官方 MCP SDK 透传工具调用，附件单独走 HTTP。

## 决策

**采用第 3 种：Python + uv 分发，用官方 MCP SDK 透传全部 MCP 工具；附件上传、下载直接调用思源 HTTP API。** 笔记语义由上游 MCP 负责，`syc` 只负责实例选择、凭据、输出格式和附件字节传输。

- 通用命令只有 `tools`、`describe`、`call`，不为单个工具做专门封装，也不冻结工具表。工具描述和 schema 以服务端为准。
- 官方 MCP 的 `asset.upload` 读取的是思源服务器本机路径，不能上传 agent 所在机器的文件；因此附件走 `/api/asset/upload` 和 `/api/file/getFile`。
- MCP SDK 只在 MCP 命令里导入。`use`、`instances`、`asset`、`setup` 不加载 SDK。
- 与 agent skill 安装器保持同一技术栈，安装逻辑沿用 jcli 的 managed marker 做法。

不选 Rust：它只省进程启动开销，主要耗时在网络往返；还会增加多平台二进制分发成本。

## 依据

2026-11-23 对思源 3.8.9 官方 MCP（31 个工具，经 Cloudflare Tunnel 访问）的只读实测，耗时均为墙钟时间，样本量小：

| 项目 | 耗时 |
|---|---|
| mcp2cli 热启动 list | 约 2.8 s |
| 官方 SDK 一次连接完成 list 与 call | 约 2.2–2.5 s |
| Python 进程启动并导入 `mcp` | 约 0.7 s，其中 `import mcp` 约 0.5 s |
| `syc call system version` 全程 | 约 1.3–1.4 s |
| `syc asset get`（不导入 SDK） | 约 0.6–0.7 s |

- 每次调用都新建 MCP 会话（initialize 后再调用），握手往返占大头；换语言只能省下导入开销。
- mcp2cli 为每个工具生成的 `--help` 把所有 action 的字段平铺列出，单个 action 的帮助与整工具帮助相同。工具描述开头的 action 签名（如 `get(id)`、`create(notebook, parentID, title, markdown?)`）对 agent 更有用，`syc describe` 原样输出描述。
