# HTTP 接口契约

本文是 Hysteria2-panel 的**内部协议参考**，面向开发者和维护者，不是对第三方承诺的通用公网 API。管理操作应使用同源网页；数据节点应使用安装器生成的固定版本 Agent，不要手工拼接签名请求。

## 阅读导航

| 部分 | 调用方 | 网络边界 |
|---|---|---|
| Hysteria 认证回调 | 面板本机 Hysteria 或数据节点回环代理 | 只监听回环地址 |
| 签名节点控制协议 | 已核验的固定版本数据节点 | 仅在独立面板 HTTPS 下开放 |
| 管理面板 | 管理员浏览器 | 同源会话、CSRF 和固定路由 |
| Android Mobile API v1 | Hysteria2管理 Android App | HTTPS、设备会话和 Bearer 令牌 |

所有大小、时间窗、状态码与失败关闭行为都是安全契约。修改时必须同步实现、测试、安装器固定哈希和相关 ADR。

## Android Mobile API v1

Android 客户端使用独立的 `/api/v1/mobile/*` JSON 接口。它不复用网页登录 Cookie/CSRF，也不能使用 `/api/v1/node-*` 节点 Agent 机器接口。

### 认证

- `GET /api/v1/mobile/capabilities`：无需登录，返回面板版本、API 版本和功能能力。
- `POST /api/v1/mobile/auth/login`：提交管理员账号、密码、设备 ID 和设备名称；沿用网页登录限流。
- `POST /api/v1/mobile/auth/refresh`：一次性轮换访问令牌与刷新令牌。
- `POST /api/v1/mobile/auth/logout`：撤销当前设备会话。
- `GET /api/v1/mobile/auth/session`：返回当前管理员和设备会话摘要。

除 capabilities、login 和 refresh 外，请求必须使用 `Authorization: Bearer <access-token>`。访问令牌默认 15 分钟有效，刷新令牌默认 30 天有效；服务端数据库只保存令牌 SHA-256 摘要。修改管理员账号或密码会撤销全部浏览器与移动设备会话。

### 管理接口

- `GET /api/v1/mobile/overview`：首页聚合状态、统计、预算和资源。
- `GET /api/v1/mobile/users`：返回全部用户，不分页。
- `GET /api/v1/mobile/domain-usage`：返回本月全部用户合计的可识别 TCP 目标域名 TOP10，按上传与下载流量合计降序排列。
- `GET /api/v1/mobile/users/{id}/domain-usage`：返回本月指定用户的可识别 TCP 目标域名 TOP10。
- `POST /api/v1/mobile/users`、`PATCH /api/v1/mobile/users/{id}`、`DELETE /api/v1/mobile/users/{id}`：创建、编辑和删除用户。
- `POST /api/v1/mobile/users/{id}/{enable|disable|share|rotate-secret|reset-traffic}`：用户操作。
- `GET /api/v1/mobile/nodes`：返回面板本机与远程节点的安全裁剪详情、累计流量和采样时间，不包含节点私钥、HMAC 或机器令牌。
- `POST /api/v1/mobile/node-enrollments`：生成短时节点对接授权和部署代码。
- `POST /api/v1/mobile/nodes/{node-id}/verify`：核对完整公钥指纹后确认节点。
- `POST /api/v1/mobile/nodes/local/{enable|disable}`：启用面板本机服务，或在先结算流量后紧急停用。
- `POST /api/v1/mobile/nodes/{node-id}/{enable|disable}`：向已验证远程节点下发固定的恢复或紧急停用命令。
- `POST /api/v1/mobile/service/{start|restart|stop}`：控制 Hysteria 服务；重启和停止前先结算流量。
- `POST /api/v1/mobile/system/reboot`：先结算流量并写入审计，再通过固定白名单排队重启服务器；成功返回 HTTP 202。

写操作继续执行维护互斥、并发 generation、流量结算、断开连接和审计。客户端不得自动重试没有幂等保护的危险写操作。节点页每 5 秒重新读取累计值并在本机计算速率，不新增匿名流量接口，也不把节点地址写进 APK。

域名流量接口是近似聚合，不是访问日志。采集端只读取 Hysteria 官方 `/dump/streams` 中采样时仍活动的 TCP 流，在内存中计算字节增量后只上传 `{user, domain, tx, rx}`；中央端每个来源/用户/月最多保留 500 个域名并只查询当前月 TOP10。IP 目标、原始流快照、URL 路径、请求内容、时间明细和 Cookie 均不落库；UDP/QUIC 目标及两次采样之间已经结束的短连接不会被统计。

### 返回格式

```json
{
  "data": {},
  "meta": {
    "requestId": "32位请求标识",
    "serverTime": 1788170000,
    "apiVersion": "1"
  },
  "error": null
}
```

失败时 `data` 通常为空，`error` 包含稳定 `code` 和中文 `message`。HTTP 状态码仍然表达认证失败、冲突、限流、维护或服务端故障，客户端不能只检查 JSON 文案。

## Hysteria 认证回调

监听：`127.0.0.1:19996`，不对公网开放。

### `POST /auth`

请求由 Hysteria 发出：

```json
{
  "addr": "192.0.2.10:44556",
  "auth": "客户端认证密钥",
  "tx": 123456
}
```

认证成功：

```json
{"ok": true, "id": "用户名称"}
```

认证失败仍返回 HTTP 200，以符合 Hysteria 的认证契约：

```json
{"ok": false, "id": ""}
```

认证成功前会同步持久流量并检查该用户的总流量和客户端实例上限。Hysteria `/online` 的数值是同一认证 ID 的客户端实例数，不是代理流数量或物理硬件指纹。达到任一上限或本地统计接口暂时不可用时，仍使用上述 HTTP 200 拒绝响应，避免绕过限额或改变 Hysteria 的认证契约；超过上限不会踢掉已在线实例。

无效 JSON、缺少 `auth` 或请求过大时返回结构化错误：

```json
{"error": {"code": "INVALID_REQUEST", "message": "Invalid request"}}
```

参考：[Hysteria 2 官方 HTTP Authentication 文档](https://v2.hysteria.network/docs/advanced/Full-Server-Config/#http-authentication)。

### `POST /auth/udp-443`

仅供本机 UDP `443` Hysteria 进程调用，请求和响应结构与 `/auth` 相同。除了启用状态、流量和客户端实例限制外，还要求账号的 `allow_udp_443` 为真；未开放的账号返回 HTTP 200 与 `{"ok": false, "id": ""}`。主端口认证不检查该字段，因此开放 UDP `443` 不会停止原端口。

## 签名节点控制协议

仅在独立面板 HTTPS 启用后开放。每个请求都包含已人工核验的 `nodeId`、服务端时间窗内的 `sentAt`、32 字节 URL-safe `nonce` 与 Ed25519 `signature`；各接口使用不同签名域，来源 IP 必须与注册绑定一致。除自动 bootstrap claim 外，节点还必须已经进入 `protocol_ready`。稳定错误只返回 `error.code`，不回显 token、nonce、签名或完整请求。

这里的 ACK 指中央已经把状态或流量持久化，不只是“HTTP 请求已收到”。节点只有在确认 ACK 后才删除对应 spool 批次。

| 方法 | 路径 | 最大请求 | 行为 |
|---|---|---:|---|
| `POST` | `/api/v1/node-auth-decisions` | 16 KiB | 在中央事务中统一检查本机与所有就绪节点的在线实例、短租约和流量额度 |
| `POST` | `/api/v1/node-online-snapshots` | 128 KiB | 以单调 `sequence` 完整替换该节点的稀疏在线计数和流量确认检查点 |
| `POST` | `/api/v1/node-traffic-batches` | 256 KiB | 以 `(nodeId,batchId)` 幂等累计已持久化的增量流量，可选携带有界域名聚合，提交后返回 ACK |
| `POST` | `/api/v1/node-control-cycles` | 512 KiB | 新节点用一次签名和一次 HTTPS 往返提交至多 8 个流量批次、可选在线快照并轮询命令；旧接口继续兼容 |
| `POST` | `/api/v1/node-commands/poll` | 8 KiB | 立即返回至多 32 条且总响应不超过 64 KiB 的固定枚举命令 |
| `POST` | `/api/v1/node-commands/ack` | 16 KiB | 幂等确认发给同一节点的既有命令，不能修改命令内容 |
| `POST` | `/api/v1/node-data-plane/claim` | 16 KiB | 已核验且心跳新鲜的节点自动启用协议并原子领取节点绑定 grant；重领会废止旧 grant |
| `POST` | `/api/v1/node-data-plane/bootstrap` | 16 KiB | 使用短时 token 与节点签名获取固定数据面身份和配置，最多成功取件 3 次 |
| `POST` | `/api/v1/node-data-plane/ack` | 16 KiB | 提交本机服务、端口、统计和身份三摘要证明；成功后烧毁 bootstrap 授权 |

节点侧 Hysteria 只访问 `127.0.0.1` 认证代理；代理删除客户端地址后签名转发。中央超时、非 200、无效 JSON，或节点快照/计量检查点超过 43 秒安全窗口时，新认证统一映射为 Hysteria 所需的 HTTP 200 拒绝，既有会话不会被控制面故障主动中断。流量采集先独立写入 0600 有界 spool 并 `fsync`，即使旧批次暂时上传失败也会在容量允许时继续采集；收到中央提交 ACK 后才删除。命令轮询与流量/快照失败相互隔离，并加入有界随机抖动，避免多节点同时重试。签名与验签消息通过标准输入交给 OpenSSL，不把用户 token 写入临时文件。

每个数据节点还在同一回环认证代理提供 `GET /healthz` 和 `GET /metrics`。指标文件由控制循环以 `0600`、同目录临时文件、`fsync` 和原子替换写入；认证代理只接受当前 root 所有的普通 0600 文件，缺失、不安全或超过 64 KiB 时 `/metrics` 返回 503。指标仅为低基数进程与 spool 汇总，不包含用户名、节点名、token 或来源地址。认证代理和控制循环分别以 systemd `Type=notify`、30 秒与 90 秒 watchdog 运行，退避等待也会持续报活。

正常全新节点流程由 root-only 的固定版本完成器调用 `claim`。服务端只允许已经人工核验完整 Ed25519 指纹、签名有效、来源 IP 精确匹配且心跳新鲜的节点领取；同一事务启用协议、废止未消费旧 grant 并返回新 grant。授权有效 10 分钟、最多成功取件 3 次，并同时绑定节点 ID、注册来源 IP 与 Ed25519 签名；服务端只保存 token SHA-256 摘要。原有管理员手工 bootstrap 路由继续作为旧节点故障恢复入口。

bootstrap 响应传输当前生产 Hysteria TLS 身份的原始字节及固定数据面参数，不传输数据库、HMAC、用户 token 或统计 secret。节点必须在内存中核验证书/私钥配对、证书文件 SHA-256、DER SHA-256 和私钥公钥 DER SHA-256，完成本机六个服务、双 stats 和四个 TCP/UDP 监听证明后才能 ACK。

自动 grant 在 bootstrap 取件后临时允许一个与该 grant 绑定的保留认证身份。中央面板分别通过节点公网 IP 的主 UDP 端口和 UDP `443` 启动真实 Hysteria 客户端，经本机 SOCKS 取得外部响应并精确核对出口公网 IP；它不创建或修改真实用户，也不计入用户设备和流量。两个入口均通过时，安装 ACK 原子推进到 `direct_canary_passed` 并烧毁 grant；任一步失败都不会 ACK 或误标成功。

独立的 DNS timer 只读解析 `PUBLIC_HOST`。仅当公开 A/AAAA 精确包含节点预期公网 IP，并且直连灰度、心跳、在线快照和流量 ACK 全部满足新鲜度门时，才调用既有状态转换记录 `dns_admitted`；它不写 DNS，也不自动移除记录。手工 canary 与 DNS admission/removal API 继续作为故障恢复接口。任何 bootstrap、中央认证或新鲜度校验失败都拒绝新认证，已经建立的 Hysteria 会话不会被控制面故障主动停止。

## 管理面板

监听：公网 TCP `19998`，全新安装默认 HTTPS，也可显式选择 HTTP；升级原样保留现有协议，不强制迁移。所有变更路由均要求有效管理会话和 CSRF token。

管理路由返回 HTML、下载文件或任务受理状态，没有承诺稳定的第三方 JSON SDK。需要自动化时，应先提交使用场景和最小权限设计，而不是依赖页面内部结构。

| 方法 | 路径 | 行为 |
|---|---|---|
| `GET` | `/healthz` | 仅表示 HTTP 进程存活；返回固定的 `{"status":"ok"}` |
| `GET` | `/readyz` | 数据库、内部认证、流量采集工作线程和最近统计同步均正常时返回 200，否则返回 503；不暴露内部故障细节 |
| `GET` | `/metrics` | 仅回环来源可访问的有界 Prometheus 文本指标；含预算状态汇总但不含节点名、用户名或来源 IP 标签，外部来源返回 404 |
| `GET` | `/login` | 登录页 |
| `POST` | `/login` | 创建 HttpOnly、SameSite=Strict 会话；HTTPS 模式额外设置 Secure；按来源 IP 执行登录限速 |
| `GET` | `/` | 服务控制、系统资源、版本、全局统计、高流量前五、完整用户列表、即时搜索与限额进度 |
| `POST` | `/users` | 创建带设备/总流量限制的用户并显示认证密钥和 URI |
| `POST` | `/users/{id}/edit` | 携带当前 `generation`，修改客户端实例数、总流量限制和账号级 UDP 443 权限，不修改 token 或 URI |
| `POST` | `/users/{id}/toggle` | 携带当前 `generation`，启用或禁用用户 |
| `POST` | `/users/{id}/rotate` | 携带当前 `generation`，轮换认证密钥并断开旧连接 |
| `POST` | `/users/{id}/delete` | 携带当前 `generation`，删除用户并断开连接 |
| `POST` | `/users/{id}/share` | 携带当前 `generation`，显示可复制的当前连接 URI |
| `POST` | `/users/{id}/reset` | 携带当前 `generation`，重置该用户流量并断开旧连接 |
| `POST` | `/users/reset-traffic` | 重置所有用户的持久累计流量 |
| `POST` | `/usage-origins/{local或node来源ID}/budget` | 为面板本机或已有数据节点设置 GiB 月预算、当前周期已用 GiB、1–99% 告警阈值和每月 UTC 重置日（1–31）；保存后只追加新流量，0 GiB 关闭预算 |
| `POST` | `/usage-origins/legacy-unattributed/delete` | 明确确认后只删除固定的升级前未归属来源、拆分明细和日账本；不修改用户总流量或已归属节点统计 |
| `POST` | `/node-enrollments` | 生成短时、单用途节点对接代码；要求面板 HTTPS |
| `POST` | `/node-enrollments/{id}/revoke` | 作废尚未消费的节点对接码 |
| `POST` | `/nodes/{id}/verify` | UI 核对双方 16 位短码，服务端仍精确确认完整 Ed25519 公钥 SHA-256 指纹 |
| `POST` | `/nodes/{id}/revoke` | 撤销节点身份并拒绝后续心跳与控制协议请求 |
| `POST` | `/nodes/{id}/protocol/{enable,disable}` | 独立启停中央控制协议参与状态；不部署 Hysteria 或修改 DNS |
| `POST` | `/nodes/{id}/data-plane/bootstrap` | 为已验证且协议就绪节点生成短时数据面一键部署代码；要求面板 HTTPS |
| `POST` | `/nodes/{id}/data-plane/canary/pass` | 仅记录独立直连灰度已通过；不修改或准入 DNS |
| `POST` | `/nodes/{id}/data-plane/dns/{admit,remove}` | 故障恢复用的 DNS 准入/撤出状态记录；不调用外部 DNS API |
| `POST` | `/nodes/{id}/lifecycle/drain` | 进入摘流状态但继续服务；等待管理员从外部 DNS 删除该节点 IP |
| `POST` | `/nodes/{id}/lifecycle/stop` | 只读确认 DNS 已删除、在线设备为 0 且流量 ACK 新鲜后，下发固定停用命令 |
| `POST` | `/nodes/{id}/lifecycle/emergency-stop` | 跳过 DNS 与设备门禁的紧急停用；旧 DNS 仍命中时用户会连接失败 |
| `POST` | `/nodes/{id}/lifecycle/{resume,archive}` | 固定恢复数据面，或在已停用且无待处理命令时归档旧节点记录 |
| `POST` | `/service/{start,stop,restart}` | 通过固定 sudoers 白名单控制项目专用 Hysteria 服务 |
| `POST` | `/egress/{web,full}` | 切换整台节点的出站策略；通过固定 root oneshot 同步更新两份 Hysteria 配置和持久状态，重启失败时恢复旧策略 |
| `POST` | `/system/reboot` | 二次确认后通过固定 sudoers 白名单排队重启整台服务器，成功返回 HTTP 202 |
| `POST` | `/updates/check` | 从固定 GitHub Release API 检查面板版本；有新正式版本时显示在线更新入口 |
| `POST` | `/updates/apply` | 不接收版本或地址参数；排队启动固定的一次性 root 更新服务，成功返回 HTTP 202 |
| `GET` | `/updates/status` | 查询持久更新状态；返回 `idle/queued/running/success/failed` 与目标版本和提示 |
| `POST` | `/backup` | 表单 CSRF 校验后返回 `application/zip` 敏感备份，响应强制 `no-store` |
| `POST` | `/restore` | 上传原始 `application/zip`；CSRF 通过 `X-HY2Panel-CSRF` 请求头提交，预检后排队执行一次性恢复服务 |
| `POST` | `/logout` | 撤销管理会话 |

面板没有对公网提供通用 JSON 管理 API，避免扩大认证和 CORS 攻击面。
节点生命周期命令只有 `STOP_DATA_PLANE` 与 `START_DATA_PLANE` 两个固定空参数枚举；节点 Agent 不接收 unit 名、文件路径或 shell。安全停用只停止两路 Hysteria 和相应 TCP 探针，Agent、Ed25519 私钥、Hysteria TLS 身份和 durable traffic spool 均保留。恢复成功后回到直连灰度已通过状态，必须重新加入 DNS 并通过只读准入检查后用户才会到达。
版本过期的用户变更返回 HTTP 409，避免并发操作覆盖刚生成的认证密钥。编辑用户时设备限制范围为 1 到 100，总流量必须为正值，`allow_udp_443=1` 表示开放 UDP `443`，缺少该字段表示关闭；该操作递增 `generation`，保留名称、认证 token 派生种子和累计流量。审计写入或断开在线连接失败会记录到服务日志，但不会吞掉已经生成的新凭据。

登录错误响应不区分账号不存在与密码错误。每个来源 IP 在 15 分钟窗口内前 4 次错误返回 HTTP `401`，第 5 次立即返回 HTTP `429` 并设置整数秒 `Retry-After`；同一 IPv6 `/64` 前缀按一个来源统计。锁定期间正确密码也会被拒绝，成功登录清除该来源的失败记录。限速表最多记录 4096 个来源并仅保存在进程内存，面板重启后清空。所有登录响应均带 `no-store`、CSP、`nosniff`、拒绝嵌入和禁止 Referrer 等安全头。

公网 HTTP 连接具有 10 秒读写空闲超时和 30 秒请求总截止时间；仅签名节点安装 ACK 因为需要顺序完成两次真实 Hysteria 数据面探测而使用 70 秒有界总截止时间。总截止时间到期会关闭连接并释放工作线程。`audit_log` 每次写入后在同一事务中删除超过 90 天的记录，并只保留最新 10,000 行，避免未认证登录失败无限扩张 SQLite。

全局统计只汇总当前数据库中的用户，避免已删除用户仍残留在 Hysteria 统计快照时污染总数。不活跃用户定义为上传和下载均为 0 的账户。面板分别从主入口和 UDP `443` 入口使用 Hysteria `/traffic?clear=1` 取得增量，按用户名相加后写入 SQLite；`/online` 实例数也按用户名相加，因此两个入口共同执行同一设备与流量额度，正常重启不会清空累计流量。

`POST /restore` 要求 `Content-Length` 在 1 字节到 131 MiB 之间（128 MiB 数据库内容上限加 3 MiB 身份与清单余量），不解析 multipart。服务端只接受格式版本 1 的固定五文件 ZIP，限制单项与总解压大小，拒绝额外文件、重复路径、目录和符号链接，并校验清单 SHA-256、SQLite 完整性/表结构、每个可恢复用户 token、证书/私钥、证书指纹、源域名及 UDP 端口。上传预检还必须在安装/更新/恢复共用锁文件上取得短暂只读共享准入；root 维护任务持排他锁或已有恢复标记时拒绝上传。预检通过后只写入固定待恢复路径，再用固定 sudoers 命令启动 root oneshot。

root 进程不信任 Web 预检，会以 `O_NOFOLLOW` 和固定所有权/权限合同再次读取归档，并把恢复推进为持久的 `queued → prepared → disk-consistent → services-pending` 事务。启动前的 `restore-recover` oneshot 只验证、完成或回滚数据库/HMAC 环境/TLS 身份并清理 SQLite sidecar；业务服务强依赖该阶段成功。服务启动后的 `restore-resume` oneshot 连续验证 systemd、HTTP、统计和 TCP 健康后才删除标记。普通退出、信号或重启均从标记幂等继续；孤立或失败归档会隔离并释放固定上传路径。

`POST /updates/apply` 只有在当前会话刚检查到新版本时可用，但 root 任务不会信任这份页面状态，而会重新访问固定仓库的 GitHub `releases/latest`。响应 tag 必须是比当前版本新的 `vX.Y.Z`，安装器只能从该 tag 对应的固定 `raw.githubusercontent.com/Elegying/Hysteria2-panel/` 路径下载。执行前还会限制响应大小、验证 UTF-8、bash 解释器头、内嵌版本与 tag 一致并通过 `bash -n`。更新进程使用固定环境变量进入安装器的现有受管安装模式，网页请求无法指定命令、仓库、版本、节点参数或管理员凭据。排队状态以 `0600` 原子文件保存在面板数据目录；`GET /updates/status` 再读取固定 systemd 单元状态，且只有更新单元已成功结束并且当前版本达到目标版本才返回 `success`。浏览器短暂失联时继续轮询，任务失败、退出码非零或任务结束但版本未变化时返回明确失败提示。

`POST /system/reboot` 不接收命令、主机或延时参数。后端只执行固定的 `/usr/bin/sudo -n /bin/systemctl --no-block reboot`，并在排队前尽力落盘最新流量及写入审计记录。接口返回 202 只表示重启已排队，不表示系统已重新上线。

`POST /egress/{web,full}` 不接收 ACL、命令、文件路径或端口参数，且作用于节点上的全部代理账号。面板只把严格匹配的目标映射到 `hysteria2-panel-egress-web.service` 或 `hysteria2-panel-egress-full.service`；两个 root oneshot 使用安装、更新和恢复共用的维护锁，拒绝并发维护。任务只读取 root 所有且不可组写/全局写的普通受管文件，用同目录临时文件、`fsync` 和原子替换同时更新主入口、UDP `443` 入口及 `HY2PANEL_EGRESS_POLICY`，随后重启并复核业务服务。写入或重启失败时恢复原内容并再次启动旧策略；面板显示持久化的当前状态，切换前明确提醒全部现有连接会短暂中断以及 `full` 的滥用风险。

Hysteria 流量统计客户端只接受带明确端口、无路径的 `http://127.0.0.1` 或 `http://[::1]`，单次响应最多 8 MiB，避免配置错误把面板变成外部请求入口或让异常统计响应无限占用内存。
