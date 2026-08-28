# 规格：分流节点数据面第四阶段

> 公开版本中的域名和 IP 是示例值；`.201`、`.210` 等尾号仅保留为节点代号。

## 目标

在 v0.26.0 已发布的节点身份、签名心跳、中央认证、全局设备租约、在线快照、
durable 流量批次和固定命令协议之上，为已人工验证的远端节点提供第二段一键数据面
部署流程。管理员在面板中为指定节点生成短时一次性代码，在该节点以 root 粘贴后，
安装器只部署数据节点所需的 Hysteria、回环认证代理、控制循环和 systemd 单元。

第四阶段的成功标准是 `.210` 能以现有 `vpn.example.com`、现有用户认证材料和完全
相同的 Hysteria TLS 身份，通过直连 IP 灰度承载真实 Hysteria 流量，同时设备数和
流量仍只由 `.201` 中央面板统一判定和持久化。

本阶段不把 `.210` 加入 Cloudflare DNS。DNS admission 是第五阶段的独立管理员动作，
只有直连灰度和回滚演练通过后才能讨论。

## 已确认约束与实施假设

1. `.210` 只作为数据节点，不安装或开放管理面板。
2. 数据节点镜像现有 Hysteria UDP 19999 主入口和 UDP 443 授权入口；TCP 探测仅用于
   兼容现有端口探测，不承载代理流量。
3. 中央 SQLite 是用户启用状态、设备上限、流量配额、在线租约和累计流量的唯一
   权威；数据节点不保存用户数据库、HMAC 或可离线认证的用户副本。
4. 中央不可用、任一参与节点快照或流量 ACK 过期时，新认证失败关闭；已建立会话
   继续，不因控制面短暂故障被主动停止。
5. Hysteria `server.crt` 和 `server.key` 只允许从当前生产身份逐字节复制到数据节点；
   永远不生成、续签、替换、转换或重新编码它们。
6. 永远不改变 `vpn.example.com`、现有用户 URI、token 派生、HMAC 或证书指纹。
7. 面板的 Let’s Encrypt 证书与 Hysteria 节点证书继续完全分离。
8. Cloudflare DNS、防火墙云安全组和 DNS 入池不由一键数据面部署自动修改。

如需改变任一假设，必须先更新本规格并重新走人工批准门。

## 技术栈与命令

- Python 3.8+ 标准库、SQLite、OpenSSL Ed25519、Hysteria 官方固定版本。
- 单元/集成：`python3 -m unittest discover -s tests -v`
- Python 编译：`python3 -m compileall -q hysteria2_panel.py node_agent.py hy2panel tests`
- Ruff：`.venv-audit/bin/ruff check hysteria2_panel.py node_agent.py hy2panel tests`
- Bandit：`.venv-audit/bin/bandit -q -r hysteria2_panel.py node_agent.py hy2panel`
- Bash：`bash -n install.sh`
- ShellCheck：`shellcheck install.sh`
- 差异：`git diff --check`
- 浏览器：320、768、1440px，零横向溢出、零控制台错误。

## 项目结构与代码风格

- `hy2panel/nodes.py`：短时数据面 bootstrap 的控制面合同。
- `hy2panel/distributed.py`：既有中央授权/计量，不复制到节点。
- `hysteria2_panel.py`：SQLite 迁移、HTTPS 路由、管理员状态和 UI 编排。
- `node_agent.py`：受签名 bootstrap 客户端、回环认证代理、控制循环和数据面证明。
- `install.sh`：冲突检查、固定哈希下载、原子写入、systemd sandbox 和回滚。
- `tests/`：每个新行为先失败后实现；安装器合同只断言项目行为，不依赖真实公网。

代码继续使用小函数、稳定 JSON 字段、固定枚举和项目现有 `snake_case` 风格。边界输入
在路由/CLI 入口一次验证，内部函数不重复发明兼容分支。例如：

```python
if state != "protocol_ready":
    raise ValueError("node is not protocol ready")
```

## 状态机

状态严格单向推进，后一步不能由前一步自动推导：

```text
pending_verification
  -> verified
  -> protocol_ready
  -> bootstrap_issued
  -> data_plane_installed
  -> direct_canary_passed
  -> dns_admitted（第五阶段，本规格禁止）
```

- `protocol_ready`：只表示 v0.26 控制协议可用。
- `bootstrap_issued`：存在未过期、绑定节点/IP 的部署授权，不表示已收到 TLS 身份。
- `data_plane_installed`：节点签名证明本机服务、统计端点和身份摘要吻合。
- `direct_canary_passed`：由管理员在节点外部完成真实 Hysteria 数据通道后显式记录。
- `dns_admitted`：独立字段和独立审计事件；第四阶段代码不得自动设置。

撤销节点立即拒绝 bootstrap、认证、快照、流量和命令。撤销不远程删除 TLS 私钥，
因为任意远程删除不能作为密钥已销毁的证明；需要单独人工退役流程。

## 一键代码与 bootstrap 合同

面板只对已验证且 `protocol_ready` 的节点显示“部署数据面”。点击后生成固定正式标签
的一键代码。代码只包含：

- 固定仓库、严格 `vX.Y.Z` 标签、Cosign 固定版本/哈希和精确 OIDC identity；
- HTTPS 面板地址；
- 绑定单节点、10 分钟过期、最多 3 次取件的数据面 bootstrap token。

代码绝不包含 Hysteria 证书、私钥、用户 token、HMAC、统计 secret、数据库或管理员
Cookie。面板数据库只保存 token 的 SHA-256 摘要、节点 ID、过期时间、尝试次数和
状态；原 token 只在创建响应中显示一次，不进入审计或日志。

节点使用现有 Ed25519 私钥签名 bootstrap 请求，同时提交一次性 token。中央依次校验
HTTPS、节点已验证、`protocol_ready`、来源 IP、签名、purpose nonce、时间窗、token
摘要、过期时间和尝试上限。失败响应只返回稳定错误码，不回显 token、签名或秘密。

### `POST /api/v1/node-data-plane/bootstrap`

- HTTPS-only，最大请求 16 KiB。
- 请求业务字段：`bootstrapToken`、`requestId` 和既有签名信封。
- 成功响应最大 32 KiB，只在内存中生成并直接发送：严格原样的 PEM 证书/私钥、
  它们的文件/DER/公钥摘要、固定端口、固定 Hysteria 版本与二进制 SHA-256、
  `egressPolicy` 枚举和配置协议版本。
- 私钥不写临时文件、不写数据库、不写日志；HTTP handler 禁止打印响应体。
- 同一授权允许最多 3 次取件以容忍响应在网络中丢失；只接受同一节点/IP，并在 10 分钟
  内。节点成功 ACK 后立即烧毁授权，之后重试一律拒绝。

### `POST /api/v1/node-data-plane/ack`

- 节点安装成功后签名上报服务状态、监听端口、证书文件 SHA-256、证书 DER SHA-256、
  私钥公钥 SHA-256、Hysteria 版本和 stats 健康；不上传私钥或 stats secret。
- 中央摘要必须与当前生产身份实时计算值一致；不信任 bootstrap 响应中由节点原样
  回传的期望值。
- ACK 与烧毁授权、写入 `data_plane_installed` 位于同一 SQLite 事务。

## 节点安装合同

安装器新增显式 `--activate-data-plane` 模式，只允许在现有第二阶段节点目录和已启用
签名心跳基础上运行；完整面板主机、未知文件、符号链接、错误 owner/mode、未验证
节点或非正式标签均失败关闭。

安装顺序：

1. 完成所有命令、架构、磁盘、端口、systemd、路径和当前节点身份预检；预检失败零写入。
2. 下载并固定校验正式标签的 `node_agent.py`、Hysteria 二进制和 TCP probe。
3. 通过签名 HTTPS bootstrap 取件到 root-only 内存/临时目录；立即验证 PEM 可解析、
   证书与私钥公钥匹配、三个期望摘要一致。
4. 节点本地生成不少于 32 字节的随机 stats secret，只写 `0600 root:root` 环境文件。
5. 生成固定 schema 的两个 Hysteria 配置：主入口调用回环 `/auth/main`，443 入口调用
   `/auth/udp443`；两者共享原样 TLS 身份和本地 stats secret。
6. 原子安装项目专用二进制、配置和 systemd 单元；不覆盖通用 Hysteria 服务。
7. 若 UFW/firewalld 已启用且可安全归因，只开放 TCP/UDP 19999 与 443；未启用则不
   修改规则；未知 nftables/iptables 拒绝猜测。
8. 先启动认证代理与控制循环，再启动两个 Hysteria 和两个 TCP probe；认证代理或
   控制循环后续故障不停止既有 Hysteria 会话，但新认证自然失败关闭。
9. 验证 stats、监听、服务和身份摘要后发送签名 ACK。

数据节点只持有：节点 Ed25519 私钥、原样 Hysteria TLS 身份、本地 stats secret、
无用户秘密的 durable traffic spool 和固定配置。它不持有中央 HMAC、SQLite、管理员
凭据或可离线使用的用户 token 表。

## systemd 与最小权限

- 认证代理只监听 `127.0.0.1`，只读节点私钥/注册状态，不读取 TLS 私钥或 stats secret。
- 控制循环只读节点私钥/注册状态和本地 stats secret，可写固定 spool/state 目录。
- Hysteria 单元只读固定证书、私钥、配置和 stats 环境，不访问节点 Ed25519 私钥。
- 每个单元使用独立读写路径、`NoNewPrivileges`、`ProtectSystem=strict`、
  `ProtectHome=true`、空 capability bounding set（绑定 443 所需能力由 systemd 精确授予
  或由项目既有非特权高端口方案处理）、受限地址族和资源上限。
- 日志中禁止 bootstrap token、用户 auth、Hysteria 私钥、stats secret、签名、nonce
  和完整请求/响应体。

## 回滚与恢复

- 写入前在 `/var/backups/hysteria2-panel-node/` 创建唯一 root-only 快照，记录节点 Agent、
  phase4 路径、单元、防火墙归因和 SHA-256 manifest。
- 首次数据面安装失败时，只清理本次事务明确创建的 phase4 文件、单元和受管防火墙
  规则；保留第二阶段 Ed25519 身份、注册状态和心跳 timer。
- 若 TLS 身份已落盘但 ACK 未成功，回滚删除仅由本事务创建的节点副本并 fsync 目录；
  中央生产证书、私钥和现有节点不发生任何写入。
- 升级已有数据面时，先备份再原子替换；健康检查失败恢复旧数据面，不旋转身份。
- 每个回滚动作必须可由安装器合同测试证明，不使用通配符删除或未知路径。

## 直连灰度与统一管理验收

DNS 变更前从 `.201` 或另一独立主机把 `vpn.example.com` SNI/证书校验固定解析到
`.210`，使用一个现有且启用的用户做最小真实连接；不显示或保存其 token。验收：

1. `.210:19999` 经真实 Hysteria SOCKS 数据通道访问外部 204，出口为 `.210`。
2. 同一账号跨 `.201`/`.210` 并发达到设备上限后，下一次新认证被拒绝；既有会话继续。
3. `.210` 产生的小额流量通过 durable spool 只累计一次到 `.201`；重放不重复计费。
4. 中央断开时 `.210` 新认证拒绝，既有会话在测试窗口内继续传输。
5. 禁用/清退固定命令只作用目标用户名，无任意命令面。
6. 灰度完成后删除所有临时客户端配置和进程；现有用户 URI/身份字段不变。

## 威胁模型

| 威胁 | 控制 |
|---|---|
| 一键代码泄漏 | 10 分钟、节点/IP/Ed25519 三重绑定、摘要存储、3 次上限、ACK 后烧毁 |
| 中间人窃取 TLS 私钥 | Let’s Encrypt HTTPS 强校验，无 insecure 回退，签名请求和来源 IP |
| token/私钥进入日志 | 固定脱敏日志、禁止 body logging、测试扫描 SQLite/日志/审计 |
| 恶意响应替换身份 | 节点本地解析、证书/私钥匹配和三摘要校验；ACK 中央实时复核 |
| 节点被攻陷 | 不下发 HMAC/用户库；撤销后新认证和控制请求失败；TLS 泄漏需独立退役 |
| DNS 误入池 | `dns_admitted` 独立字段；第四阶段无 Cloudflare 写路径 |
| 控制面中断 | 新认证 fail-closed、旧会话继续、spool 有界持久重试 |
| 部署半失败 | root-only 快照、事务 marker、精确回滚、保留 phase2 身份 |

## 测试策略

- Small：token 生命周期、摘要、状态机、配置渲染、身份匹配、日志脱敏、固定枚举。
- Medium：真实 SQLite、临时目录、回环 HTTP、OpenSSL、伪 Hysteria stats 和 systemd
  安装合同；每个失败点断言回滚结果。
- Large：正式标签六平台安装器矩阵、`.201` 生产升级不变量、`.210` 直连真实数据面。

每项行为必须先有失败测试，再写最小实现；一个薄切片通过目标测试和全量回归后才提交。

## 永不触碰

- 不生成、续签、替换、转换或重新编码 Hysteria `server.crt`/`server.key`。
- 不改变 `vpn.example.com`、现有用户 URI/token 派生、HMAC、证书 DER 指纹或公钥。
- 不把 Hysteria 私钥、HMAC、用户数据库、统计 secret 或管理员凭据写入一键代码、
  Git、GitHub Actions、面板数据库、审计或日志。
- 不让数据节点获得管理员面板、用户数据库或本地离线授权能力。
- 不在第四阶段自动修改 Cloudflare、DNS、云安全组或 `dns_admitted`。

## 成功标准

1. 面板为合格节点生成不含秘密材料的短时一键代码；未验证、standby、撤销、错 IP、
   过期、重放、超次数和 ACK 后请求全部失败关闭。
2. `.210` 安装两入口数据面且不安装面板；仅 phase4-owned 路径被写入。
3. `.201` 与 `.210` 的 Hysteria 证书文件、DER 指纹和私钥公钥摘要完全一致；`.201`
   的原文件字节、mtime/owner/mode、HMAC 和配置不变。
4. `.201` 的 351 个现有用户身份投影和 URI 不变；`.210` 无用户数据库/HMAC。
5. 直连 19999/443、全局设备上限、流量幂等、中央故障和固定清退命令验收通过。
6. 全量测试、Ruff、Bandit、Bash、ShellCheck、六平台矩阵和浏览器三宽度通过。
7. `.210` 保持不在 `vpn.example.com` 权威 DNS 中，直到第五阶段另行批准。

## 人工批准门

本规格、`tasks/plan.md` 和 `tasks/todo.md` 必须先由用户确认。确认前只允许提交这些
文档；不得实现 bootstrap API、传输 TLS 身份、部署 `.210` 数据面、开放端口或修改 DNS。
