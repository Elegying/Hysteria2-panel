# 规格：节点控制第二阶段

## 目标

在第一阶段“待验证 Agent”之上增加最小可信控制通道：管理员核对节点本机
Ed25519 公钥指纹后显式放行，节点随后每分钟发送签名心跳，面板验证签名、
来源 IP、时间窗和一次性 nonce，并在“对接节点”弹窗显示已验证、在线或离线。

本阶段只证明“这台已登记服务器仍持有注册时的私钥并可访问控制面”，不部署
Hysteria 数据面，不复制 Hysteria 证书、HMAC 或用户数据，不参与用户认证、
设备租约、流量结算、跨节点 kick 或 DNS 分流。

## 已确认假设

1. 设备数仍表示在线 Hysteria 客户端实例数；节点心跳不计入设备数。
2. 中央控制不可用时，后续新认证失败关闭，已建立连接继续；本阶段尚不接线认证。
3. 节点服务器使用稳定公网 IP；登记了预期 IP 时，心跳来源必须完全匹配。
4. Hysteria 身份链、`vpn.ssrvpn.vip`、用户链接和证书指纹是永久不变量。

## 技术栈与命令

- Python 3.8+ 标准库、SQLite、`http.server`。
- OpenSSL 3 Ed25519 `pkeyutl`，systemd oneshot service + timer。
- 定向测试：`python3 -m unittest tests.test_node_control -v`
- 面板回归：`python3 -m unittest tests.test_panel -v`
- 安装器回归：`python3 -m unittest tests.test_installer -v`
- 全量测试：`python3 -m unittest discover -s tests -v`
- 静态门禁：现有 CI 中 Ruff、Bandit、Bash、ShellCheck 与 `git diff --check`。

## 数据合同

在 `nodes` 上仅增加可空字段，避免改变第一阶段状态枚举：

- `verified_at`、`verified_by`：管理员显式核验记录。
- `last_heartbeat_at`、`last_heartbeat_ip`：最近一次有效签名心跳。

新增 `node_heartbeat_nonces`：

- `(node_id, nonce_digest)` 唯一；只保存 nonce 的 SHA-256 摘要。
- `sent_at` 与 `accepted_at` 用于防重放和有界清理。
- 心跳验收和节点最后在线时间更新位于同一个 `BEGIN IMMEDIATE` 事务。

## 管理员接口

`POST /nodes/{nodeId}/verify`

- 管理员会话 + CSRF；表单必须回传页面展示的 64 位小写公钥 SHA-256。
- 只有已注册、未撤销的节点可验证；重复提交同一指纹保持幂等。
- 指纹不匹配返回稳定冲突，不返回公钥原文。

`POST /nodes/{nodeId}/revoke`

- 管理员会话 + CSRF；撤销后所有心跳失败关闭。

## Agent 心跳接口

`POST /api/v1/node-heartbeats`

- 仅在面板 HTTPS 模式开放，JSON 请求体上限 8 KiB。
- 字段：`nodeId`、`sentAt`、`nonce`、`hostname`、`agentVersion`、`signature`。
- `sentAt` 与服务端时间偏差最多 120 秒；nonce 为 32 字节 URL-safe 随机值。
- 签名消息为 `hy2panel-node-heartbeat-v1\n` 加排序、无空格的 UTF-8 JSON，
  JSON 只包含签名字段（不含 `signature`）。
- 使用注册时保存的 Ed25519 SPKI DER 验签；固定 argv 调用 OpenSSL，不经 shell。
- 未验证、撤销、IP 不符、过期、重放或签名错误统一返回稳定 JSON 错误，日志不含
  nonce、签名、公钥或请求体。
- 成功返回 `200 {nodeId,status:"ONLINE",acceptedAt,nextHeartbeatSeconds:60}`。

## Agent 激活合同

- 正式签名安装器新增 `--activate-node-agent`，只接管第一阶段创建且权限正确的
  `/opt/hysteria2-panel-node` 与 `/etc/hysteria2-panel-node`。
- 复核私钥、公钥配对和 registration.json 后，更新固定版本 Agent，安装 root 运行、
  强 systemd sandbox 的 oneshot service 与 60 秒 timer。
- 心跳私钥保持 `0600 root:root`；unit 不读取其他项目配置，不开放监听端口。
- 激活模式拒绝完整面板、未知路径、软链接、错误所有者/权限和不匹配密钥。

## 威胁模型

- 冒充：管理员指纹确认 + Ed25519 请求签名。
- 重放：120 秒时间窗 + 每节点 nonce 摘要唯一约束。
- 篡改：签名覆盖全部语义字段；安装器固定正式标签并验 Sigstore 身份。
- 越权：管理员接口保留会话/CSRF；公网接口只接受已验证节点。
- DoS：8 KiB 请求体、字段长度上限、OpenSSL 超时、数据库事务短小。
- 信息泄漏：不记录或返回私钥、原始公钥、nonce、签名和部署代码。

## 实施顺序

1. 数据迁移、指纹核验和 nonce 原子消费。
2. 管理员验证/撤销与公网心跳 HTTP 合同。
3. Agent 签名心跳、激活安装模式与 systemd timer。
4. 节点状态 UI、完整回归、签名发布和真实服务器验收。

## 永不触碰

- Hysteria `server.crt`、`server.key`、`HY2PANEL_HMAC_KEY`。
- `vpn.ssrvpn.vip`、现有用户 URI、证书指纹和 Cloudflare DNS。
- 用户认证、设备数、流量结算与数据面服务（留给后续独立阶段）。

## 验收标准

1. 未验证节点的心跳失败；管理员确认正确指纹后才能成功。
2. 错误签名、重放、过期、错误 IP、撤销节点全部失败关闭。
3. 150 秒内有效心跳显示在线，超时显示离线。
4. 新服务器 timer 连续产生有效心跳，同时仍只有 SSH 监听、没有 Hysteria。
5. 面板 351 用户、Hysteria 证书/私钥、配置身份摘要和用户身份摘要不变。

## 开放问题

无；数据面、中央认证、流量汇总和 DNS 入池均明确不在本阶段。
