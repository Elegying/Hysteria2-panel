# 规格：分布式中央认证与计量第三阶段

## 目标

在第二阶段已验证 Ed25519 节点身份和签名心跳之上，建立可在两个合成节点间
验收的中央策略协议：新节点通过本机回环认证代理把 Hysteria 新认证交给主面板，
节点把在线实例快照和已清零流量批次签名上报，主面板在一个 SQLite 写事务中执行
全局设备上限、流量配额和幂等结算，并通过固定类型命令清退被禁用或超额用户。

本阶段只实现、测试和观测控制协议，不向新服务器传输 Hysteria TLS 身份，不安装、
配置或启动新节点 Hysteria，不开放 UDP 端口，不修改防火墙、云安全组或 Cloudflare
DNS。只有本阶段通过双节点合成验收并由管理员另行批准后，后续阶段才可部署数据面。

已确认且持续生效的规则：

1. “设备数”表示 Hysteria `/online` 返回的客户端实例数，不表示物理设备。
2. 中央控制不可用、任一参与节点快照过期或计量状态不可确认时，新认证失败关闭；
   已建立的 Hysteria 会话不因控制面短暂故障被主动中断。
3. 永远不改变 Hysteria `server.crt`、`server.key`、`vpn.ssrvpn.vip`、现有用户 URI、
   HMAC 或证书指纹。本阶段也不复制这些材料。

## 依据与架构选择

Hysteria 官方 HTTP 认证只允许配置后端 URL 和 HTTPS 校验，认证时发送固定的
`addr`、`auth`、`tx` JSON；没有用于节点身份的自定义认证头。因此远端 Hysteria
不能直接调用公网主面板，必须只调用本机回环认证代理。代理复用第二阶段的 Ed25519
私钥签名后再通过 HTTPS 调用中央接口：

`Hysteria -> 127.0.0.1 认证代理 -> HTTPS + Ed25519 -> 主面板`

官方 Traffic Stats API 的 `/online`、`/traffic?clear=1` 和 `/kick` 分别作为全局
实例数、增量流量和清退能力的唯一数据源：

- [Hysteria 完整服务端配置](https://v2.hysteria.network/docs/advanced/Full-Server-Config/)
- [Hysteria Traffic Stats API](https://v2.hysteria.network/docs/advanced/Traffic-Stats-API/)

不采用“把用户数据库复制到每台节点并各自判断”的方案，因为它会让每台节点只看到
局部在线数和局部流量，无法原子阻止跨节点并发认证越过同一个用户限额。

## 状态与数据合同

所有迁移只新增表或可空字段，不改变 `proxy_users` 的 token 派生、名称、限额、累计
流量或现有节点状态语义。

### 参与状态

已验证心跳不等于可承载用户流量。节点增加独立的策略参与状态：

- `standby`：默认；只能心跳，所有中央认证、快照、流量和命令请求均拒绝。
- `protocol_ready`：管理员在合成验收后显式放行；可调用第三阶段接口，但仍不代表
  已安装 Hysteria 或已进入 DNS 池。
- `revoked`：沿用现有撤销语义，立即拒绝全部节点接口。

`protocol_ready` 与未来 DNS pool admission 必须是两个不同的管理员动作和审计事件。

### 签名请求与防重放

新增通用 `node_request_nonces(node_id, purpose, nonce_digest, accepted_at)`，唯一键为
`(node_id, purpose, nonce_digest)`。认证、在线、流量、命令轮询和命令确认分别使用
不同 `purpose`，避免跨接口重放；记录按 10 分钟和每节点每 purpose 1024 条双上限
清理，不能被公网请求无限扩张。

每个请求包含 `nodeId`、`sentAt`、32 字节 URL-safe `nonce`、业务字段和
`signature`。签名消息使用固定域分隔符加排序、无空格 UTF-8 JSON，签名字段本身
不参与签名：

```text
hy2panel-node-<purpose>-v1\n<canonical-json>
```

- 只接受已验证、未撤销、来源 IP 匹配的节点。
- `sentAt` 与服务端偏差最多 120 秒。
- nonce 摘要验收与业务写入位于同一个 `BEGIN IMMEDIATE` 事务。
- 私钥、原始 token、nonce、签名、完整请求体不得进入日志、审计或数据库。
- 所有接口仅在独立面板 HTTPS 配置有效时开放；请求体有按接口固定的上限。
- 来源 IP 和节点状态必须在启动 OpenSSL 前检查；每节点速率、全局并发验签数和
  OpenSSL 超时均有硬上限，避免无效认证无限创建验签子进程。
- 认证决定、nonce、流量批次索引和命令队列均按时间与行数双上限清理；仍在重试的
  流量批次和未 ACK 命令不得被普通清理误删。

### 在线快照与认证租约

新增节点快照元数据和稀疏在线计数，只上报 `count > 0` 的当前 Hysteria 认证 ID。
快照包含单调递增 `sequence`、唯一 `snapshotId`、`observedAt`、最近成功流量 ACK
检查点和完整替换语义；旧 sequence、重复 ID、负数、未知用户、过期流量检查点或
超限条目失败关闭。控制面所在服务器的本机统计作为独立的 local participant 参与
同一汇总，但不伪装成第二阶段远端节点。本机新认证也在同一个 SQLite 写事务中创建
`local_auth_leases` 短租约；远端和本机授权都会同时计算本机租约、远端租约和全部
在线快照，避免本机与远端并发认证分别通过局部检查。

中央授权在一个 `BEGIN IMMEDIATE` 事务中：

1. 校验 token、启用状态和 UDP 443 账号授权。
2. 确认本机统计与每个 `protocol_ready` 节点的完整在线快照、最近流量 ACK 均不
   超过 5 秒。
3. 检查已确认的中央累计流量和用户总流量配额。
4. 汇总所有新鲜节点快照与尚未被快照吸收的 5 秒认证租约。
5. 未达上限时创建 `(node_id, request_id)` 唯一短租约并返回用户名；否则拒绝。

同一 `requestId` 重试返回原决定，不新增租约。两个节点并发请求同一限额时，SQLite
写锁保证最多只有剩余额度数量的请求成功。每个节点的快照计数增加后只按该节点差值
吸收该节点最早租约，不能用另一节点的变化抵消；租约超时只用于消除认证与 `/online`
可见之间的短竞态，不代表活动会话。

### 流量批次

节点计量循环必须遵守以下顺序：

1. 调用本机 `/traffic?clear=1`。
2. 调用前先确认 spool 的条数、字节数和磁盘余量仍可容纳一个最大合法响应；余量
   不足时不执行 clear，标记计量不可用并停止新认证。
3. 把 `batchId`、采集时间和完整增量以 `0600 root:root` 原子写入有界 spool，
   `fsync` 文件和目录。
4. 对批次签名并上传。
5. 中央在同一事务中累加用户流量并记录唯一 `(node_id, batch_id)`。
6. 只有收到已提交 ACK 后才删除本地批次并再次 `fsync` 目录。

重复批次返回成功但不重复累计。服务器必须限制用户项数量、单项计数、总请求大小和
SQLite 整数溢出。未知或已删除的认证 ID 不得阻塞其他用户结算：中央记录脱敏计数并
把该项归入有界 tombstone 统计，不保存 token 或请求原文。

节点 spool 同时限制条数、总字节数和磁盘预留；采集前还要为 JSON 信封预留额外空间。
控制面最多接收采集时间在 7 天内的待重放批次，幂等账本至少多保留 1 天且达到 25 万
条硬上限时拒绝新批次而不删除仍可能重放的键。超过离线窗口的节点保持 fail-closed，
需要管理员先处理未结算 spool，不能静默丢弃后恢复认证。

Hysteria 的清零响应和本地 spool 落盘之间仍存在掉电少计的极窄窗口；官方接口没有
事务 ID，本阶段明确不宣称 exactly-once。spool 之后提供 at-least-once 传输，中央
幂等提交提供 effect-once。

### 固定控制命令

为保持面板统一管理，中央只允许创建以下枚举命令，不提供 shell、路径、URL 或任意
参数执行能力：

- `KICK_USERS`：用户名数组，用本机 Traffic Stats `/kick` 执行。
- `REFRESH_SNAPSHOT`：立即重新采集 `/online`。
- `FLUSH_TRAFFIC`：立即执行一次流量采集和上报。

节点每 2 秒使用签名短轮询取得命令，执行后签名确认。命令 ID 幂等；失败保留并按有界退避
重试。禁用、删除、轮换、重置或流量超额等高风险动作在未来启用远端数据面前，必须
有“先结算/清退、再变更”的单独事务规格；第三阶段只证明命令交付和 ACK 合同，不
改变现有本机用户操作语义。

## HTTP 合同

所有路径均为 HTTPS-only JSON，错误使用稳定 `error.code`，不回显秘密。

### `POST /api/v1/node-auth-decisions`

- 最大 16 KiB。
- 业务字段：`requestId`、`entrypoint`（`main` 或 `udp443`）、`auth`、`tx`
  及签名信封。回环代理只在本地验证 Hysteria 原始 `addr` 的类型与长度，中央限额
  不使用它，因此不跨服务器转发或持久化客户端来源地址。
- 成功响应：`200 {ok, id, decisionId, expiresAt}`。
- 中央非 200、超时、无效 JSON 或签名错误均由本地代理映射为 Hysteria 所需的
  `200 {"ok":false,"id":""}`，不得把控制面错误透传给客户端。

### `POST /api/v1/node-online-snapshots`

- 最大 128 KiB，完整替换而非增量。
- 成功响应包含已接受的 `snapshotId`、`sequence` 与服务端时间。

### `POST /api/v1/node-traffic-batches`

- 最大 256 KiB。
- 成功响应包含 `batchId`、`committed:true`；重复提交返回相同提交结果。

### `POST /api/v1/node-commands/poll` 与 `/ack`

- poll 立即返回，Agent 每 2 秒调用；单次最多返回 32 条、总计不超过 64 KiB，
  不用长轮询占住面板的有界工作线程。
- ack 只能确认发给本节点的既有命令，不能改变命令内容或其他节点状态。

## 节点 Agent 合同

第三阶段增加代码和隔离测试模式，但正式安装器不得在新服务器自动启用数据面：

- 认证代理只监听 `127.0.0.1`，并限制 body、连接、读写和总请求时限。
- Agent 访问中央面板必须验证 Let’s Encrypt 证书，不允许 `insecure` 回退。
- Ed25519 私钥继续使用第二阶段 root-only 文件；Hysteria token 只在单次请求内存中
  存在，签名转发后清除引用，不写 spool。
- 流量 spool 只含用户名与计数，不含用户 token、HMAC、TLS 私钥或统计 API secret。
- 本机 Traffic Stats secret 未来由数据面阶段在节点本地随机生成，只通过 root-only
  环境文件提供给 Agent；第三阶段使用合成统计端点测试。
- 强 systemd sandbox、资源上限、失败退避和日志脱敏必须先通过安装器合同测试；本
  阶段不在 `.210` 激活这些新 unit。

## 威胁模型与故障语义

- 节点冒充：复用人工确认的 Ed25519 身份、来源 IP 和 HTTPS。
- 重放/乱序：时间窗、purpose 隔离 nonce、单调快照 sequence、幂等 request/batch/
  command ID。
- 双花设备额度：中央 `BEGIN IMMEDIATE` 短租约，而不是节点本地判断。
- 流量丢失/重复：先持久 spool、提交后 ACK、节点维度幂等键和容量上限。
- 秘密泄漏：token 不落盘、不记录；错误不回显；节点私钥永不离开节点。
- 控制面故障：新认证拒绝；旧会话继续；spool 有界保留并告警，不静默丢弃。
- 恶意/失控节点：管理员撤销后全部接口拒绝；异常计数、过大请求、旧序列和未知节点
  失败关闭。已泄露的 Hysteria TLS 私钥不属于本阶段，因为本阶段不传输该身份。

## 实施顺序

1. 通用签名信封、purpose nonce 和策略参与状态。
2. 完整在线快照与跨节点原子认证租约。
3. 回环认证代理和中央认证接口。
4. durable spool 与节点维度幂等流量结算。
5. 固定命令队列、协议状态 UI 和双节点合成验收。

每一步先写失败测试，再做最小实现；每个检查点必须保持全量测试通过。

## 永不触碰

- 不生成、续签、替换、转换或重新编码 Hysteria 节点证书与私钥。
- 不改变 `vpn.ssrvpn.vip`、用户 URI、认证 token、HMAC 或证书指纹。
- 不把 Hysteria TLS 私钥、HMAC、用户数据库或长期秘密放进部署代码、HTTP 日志、
  审计、GitHub Actions 或 Git。
- 不因节点心跳或协议就绪自动修改 Cloudflare DNS 或宣布节点已入池。

## 验收标准

1. 两个合成节点同时为设备上限 3 的用户发起 4 个认证，恰好 3 个成功；失败不会
   踢掉前三个已建立实例。
2. 中央不可用、任一参与节点快照超过 5 秒、统计失败、签名/IP/nonce/sequence
   无效或节点撤销时，新认证全部失败关闭。
3. 同一流量批次在超时、重试和进程重启后最多累计一次；两个节点的不同批次正确
   汇总到现有用户总流量，提交 ACK 前 spool 不删除。
4. token、节点私钥、签名、nonce 和完整请求体不出现在 SQLite、日志、审计或测试
   快照中。
5. `KICK_USERS` 只能作用于指定用户名，重复命令幂等；任意命令、路径和 shell 参数
   都无法进入执行面。
6. 全量 Python、Ruff、Bandit、Bash、ShellCheck 和 320/768/1440px 浏览器检查通过。
7. `.201` 的 351 用户身份摘要、Hysteria TLS/HMAC/配置/pin 逐字节不变；`.210`
   仍没有 Hysteria 服务、UDP 监听、网络/防火墙/DNS 修改。

## 人工批准门

本规格批准前只允许修改规格和任务文档。批准后第三阶段也只实现控制协议与合成双
节点验收；传输 Hysteria 身份、安装/启动新节点数据面、开放端口及 DNS 入池均需要
后续阶段的独立规格、备份、回滚和再次明确批准。
