# 规格：节点对接第一阶段

## 目标

在现有控制台“服务控制”按钮区增加“对接节点”入口。管理员可以创建一个
10 分钟有效、单用途、可撤销的对接令牌，并复制一段经过 Sigstore 身份校验的
部署代码。新服务器执行后只安装节点 Agent、在本机生成 Ed25519 身份并注册为
“待验证”；本阶段不部署 Hysteria 数据面、不接收用户连接、不修改 DNS。

用户确认的运行规则：

1. “设备数”继续表示在线 Hysteria 客户端实例数，不宣称物理设备识别。
2. 后续中央控制不可用时，新认证失败关闭，已建立连接继续运行。

## 技术栈与命令

- Python 3.8+ 标准库、SQLite、`http.server`。
- Bash、systemd、OpenSSL、Cosign/Sigstore。
- 定向测试：`python3 -m unittest tests.test_node_onboarding -v`
- 面板回归：`python3 -m unittest tests.test_panel -v`
- 安装器回归：`python3 -m unittest tests.test_installer -v`
- 全量测试：`python3 -m unittest discover -s tests -v`
- 静态检查：`ruff check hysteria2_panel.py hy2panel node_agent.py tcp_probe.py tests`
- 安全检查：`bandit -q -r hysteria2_panel.py hy2panel node_agent.py tcp_probe.py`
- Shell：`bash -n install.sh tests/*.sh`、`shellcheck install.sh tests/*.sh`

## 数据合同

### `nodes`

- 不透明随机 `node_id`、管理员填写的名称、可选预期公网 IP。
- 状态仅允许 `pending_registration`、`pending_verification`、`revoked`。
- Agent Ed25519 公钥、实际来源 IP、平台、架构、Agent 版本。
- 创建、注册和最后在线时间。

### `node_enrollments`

- 不透明随机 `enrollment_id` 与所属 `node_id`。
- 只保存 256 位随机令牌的 SHA-256 摘要，不保存令牌原文。
- 创建人、创建时间、过期时间、消费时间和撤销时间。
- 消费在 `BEGIN IMMEDIATE` 事务中完成，确保并发请求只能成功一次。

## HTTP 合同

### 管理员创建令牌

`POST /node-enrollments`

- 必须有管理员会话和 CSRF。
- 表单字段：`name`（1–64 个可打印字符）、`expected_ip`（可空）、
  `ttl_minutes`（5–30，默认 10）。
- JSON 返回：节点 ID、令牌 ID、过期时间、状态和一次性部署代码。
- 令牌原文只在本次响应中出现，审计和日志不得记录。

### 管理员撤销令牌

`POST /node-enrollments/{enrollment_id}/revoke`

- 必须有管理员会话和 CSRF。
- 只有尚未消费的令牌可撤销；重复撤销保持幂等。

### Agent 注册

`POST /api/v1/node-registrations`

- 只在面板配置为 HTTPS 时开放。
- `Content-Type: application/json`，请求体不超过 8 KiB。
- 输入：`enrollmentToken`、Ed25519 SPKI DER 的 Base64、公认的平台/架构和
  主机名；所有字段在边界验证。
- 可选预期 IP 与 TCP 来源 IP 不一致时拒绝。
- 成功返回 `201`、节点 ID 和 `PENDING_VERIFICATION`；错误使用稳定的 JSON
  `error.code`/`error.message`，不泄漏令牌是否存在。

## 部署代码与 Agent 合同

- 部署代码固定到当前正式版本标签，下载 `install.sh` 及其 Sigstore bundle。
- Cosign 使用安装器内固定版本和架构 SHA-256 引导，随后校验 GitHub Actions
  OIDC 身份；未验签的安装器绝不执行。
- `install.sh --join-node` 只允许 root/systemd Linux，拒绝接管已存在的完整面板
  或未知同名路径。
- Agent 私钥只在新服务器生成并以 root-only 权限保存；令牌通过环境变量一次性
  传入，注册后立即清除，不写配置文件、日志或 systemd unit。
- 安装结果只包含 Agent、节点私钥/公钥和非秘密注册状态；不安装或启动 Hysteria，
  不写 Hysteria TLS/HMAC/用户数据库，不开放端口，不修改防火墙或 DNS。

## 项目结构与代码风格

- `hy2panel/nodes.py`：输入验证、令牌服务和部署代码生成。
- `hysteria2_panel.py`：SQLite 持久化和现有 HTTP 编排的最小接线。
- `node_agent.py`：新服务器的最小注册客户端。
- `install.sh`：受签名安装器的 `--join-node` 模式。
- `hy2panel/web_assets.py`：复用现有设计系统的弹窗交互。
- `tests/test_node_onboarding.py`：纯逻辑、数据库并发和 Agent 合同。
- `tests/test_panel.py`、`tests/test_installer.py`：HTTP/UI 与安装器边界回归。

保持项目现有 Python 3.8 兼容写法、参数化 SQL、服务端 HTML 转义、原生
`dialog` 和事件委托；不增加第三方运行时依赖。

## 威胁模型

- 伪造/重放：高熵单次令牌、摘要存储、事务消费、短过期、可撤销。
- 信息泄漏：部署代码只显示一次；令牌不进入数据库原文、日志和审计。
- 篡改：固定 Release、Cosign SHA-256 引导、Sigstore OIDC 身份验证。
- 越权：创建/撤销必须管理员会话和 CSRF；公网注册端点只能消费令牌。
- DoS：请求体与字段长度受限，失败响应统一，数据库写事务短小。
- 命令注入：部署代码只使用服务端生成的固定 URL/标签和 URL-safe 令牌，
  所有 shell 值仍进行单引号安全编码。

## 边界

### 必须

- 每个新行为先有失败测试。
- 注册成功后显示“待验证”，不得自动进入生产。
- 所有管理操作审计，但不得审计令牌、公钥私钥或完整部署代码。
- 保持现有页面响应式、键盘可操作和 CSP 不变。

### 另行确认

- 传输 Hysteria 身份材料。
- 启动新节点 Hysteria 数据面。
- 中央认证、设备租约、流量上报和跨节点 kick。
- 修改 `vpn.ssrvpn.vip` DNS 或分流权重。

### 永不

- 改变或续签 Hysteria 节点证书。
- 改变 `vpn.ssrvpn.vip`、现有用户链接、HMAC 或证书指纹。
- 把长期秘密写进部署代码、HTML、日志或 Git。

## 验收标准

1. 截图红框位置出现“对接节点”按钮，桌面和 320px 手机布局无溢出。
2. 管理员可创建、复制和撤销 10 分钟一次性部署代码。
3. 数据库从未出现令牌原文，并发消费只有一次成功。
4. 新服务器执行代码后安装 Agent，本地生成 Ed25519 密钥并显示为待验证。
5. 篡改安装器、过期/重放/撤销令牌、错误 IP、公钥或 HTTP 模式全部失败关闭。
6. 安装前后没有 Hysteria TLS/HMAC/用户配置、服务、端口、防火墙或 DNS 写路径。
7. 全量测试、静态检查和真实浏览器控制台/响应式检查通过。

## 开放问题

无；以上来自用户已经确认的两条运行规则和第一阶段规划。
