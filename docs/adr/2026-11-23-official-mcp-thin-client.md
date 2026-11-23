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
- 使用 MCP SDK 2.x 的 `Client(mode="auto")`。思源支持 2026-07-28 协议时走无握手的 stateless 请求，旧版本服务端自动回落到握手流程。不固定协议版本：固定只再省一次探测请求（约 0.06 s），却会失去对旧服务端的兼容。
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
| `syc asset get`（不导入 SDK） | 约 0.6–0.7 s |

SDK 版本与协议模式对比，同一服务端、热启动：

| 模式 | HTTP 请求 | 网络耗时 |
|---|---|---|
| 握手流程（SDK 1.x 及 2.x `legacy`） | POST×4、GET、DELETE | 约 0.75 s |
| 2.x `auto` | POST×3 | 约 0.42 s |
| 2.x 固定 `2026-07-28` | POST×2 | 约 0.36 s |

迁移到 SDK 2.3 后，`syc call system version` 全程中位数从 1.41 s 降到 1.29 s（同机五次）。网络省下的时间被更重的导入抵消了一部分：`import syc.mcp_client` 从约 409 ms 增至约 565 ms。

- 剩余耗时中，Python 启动加导入 SDK 约占 0.7 s，网络约 0.4 s。换语言只能省下导入部分；若以后单次调用延迟成为瓶颈，可以先评估直接用 HTTP 发送 2026-07-28 的 stateless 请求、不经过 SDK。
- mcp2cli 为每个工具生成的 `--help` 把所有 action 的字段平铺列出，单个 action 的帮助与整工具帮助相同。工具描述开头的 action 签名（如 `get(id)`、`create(notebook, parentID, title, markdown?)`）对 agent 更有用，`syc describe` 原样输出描述。
