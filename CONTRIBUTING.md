# 贡献指南

感谢你改进 Hysteria2-panel。项目涉及 root 安装器、systemd、用户身份、流量账本和在线更新，因此“小改动”也可能影响已有连接或服务器恢复能力。提交前请先说明影响范围，并用与风险相称的测试证明行为。

## 先选择正确入口

- 使用问题或排障：阅读[支持范围](SUPPORT.md)并创建支持请求；
- 可复现缺陷：使用 Bug 报告模板；
- 新能力或行为变化：先创建功能建议，说明使用场景和兼容性；
- 安全漏洞：不要创建公开 Issue，按[安全政策](SECURITY.md)私密报告；
- 小型文档、错字或明确测试修复：可以直接提交 PR。

## 开发环境

最低要求：

- Python 3.8 或更高版本；
- Bash；
- 推荐安装 Ruff、Bandit 和 ShellCheck；
- 修改页面时需要 Chromium/Chrome 进行真实视口回归；
- 完整安装、systemd 和防火墙测试需要 Linux 环境。

克隆后先运行基础测试：

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile hysteria2_panel.py qrcodegen.py tcp_probe.py
bash -n install.sh tests/firewall_integration.sh tests/systemd_integration.sh
```

安装静态检查工具后运行：

```bash
ruff check hysteria2_panel.py node_agent.py offsite_backup.py tcp_probe.py hy2panel tests
bandit -q -r hysteria2_panel.py node_agent.py offsite_backup.py tcp_probe.py hy2panel
shellcheck install.sh tests/firewall_integration.sh tests/systemd_integration.sh tests/installer_e2e.sh
```

## 变更原则

### 保持兼容

除非提案明确要求迁移，否则变更应保留：

- 用户 URI、认证身份、设备与流量限制；
- Hysteria 证书、私钥和固定指纹；
- 节点 Ed25519 身份与 durable traffic spool；
- 已有数据库和备份格式；
- systemd 单元、健康检查和回滚语义；
- 旧节点协议的兼容路径。

### 保持最小权限

- 不向网页开放任意 shell、路径、URL、unit 名或 ACL；
- 新 root 操作必须是固定 systemd oneshot，并通过严格 sudoers 白名单调用；
- 新敏感文件必须定义所有者、权限、大小、符号链接和原子写入合同；
- 远端请求必须固定来源、限制响应大小并设有界超时；
- 故障时优先失败关闭，不在状态未知时放行认证或删除恢复证据。

### 同步文档

- 用户可见变化写入 `CHANGELOG.md` 的 `Unreleased`；
- 安装或操作变化更新对应用户文档；
- HTTP 协议变化更新 `docs/API.md`；
- 新的长期架构取舍增加 ADR；
- 不在历史审计中改写过去结论。

## 测试要求

| 变更类型 | 至少需要 |
|---|---|
| Python 逻辑 | 对应单元/集成回归，完整 unittest |
| 安装器或 systemd | shell 语法、ShellCheck、契约测试；高风险变更增加 E2E |
| 数据库或恢复 | 正常、损坏、中断、重启继续和回滚测试 |
| 节点协议 | 签名、重放、来源绑定、过期、兼容和故障关闭测试 |
| 页面结构或文案 | HTML 结构测试；影响布局时运行桌面和手机浏览器 smoke |
| 发布或签名 | 工作流契约、标签绑定、资产和验签测试 |
| 文档 | 相对链接检查、命令语法检查和敏感信息扫描 |

截图只能证明一个视口的视觉结果，不能替代键盘、200% 缩放、屏幕阅读器或真实客户端验收。

## 提交与 PR

- 一个 PR 聚焦一个明确问题；
- 标题用简洁的结果描述，例如“修复节点 ACK 中断后的重复提示”；
- 正文说明问题、方案、兼容性、安全影响、验证结果和回滚方法；
- 不提交真实域名、服务器地址、token、私钥、备份或临时凭据；
- 不提交 `__pycache__`、数据库、`.env`、证书或本地截图凭据；
- 不绕过失败检查，不用重复运行掩盖不稳定测试。

维护者会重点检查：行为是否可验证、失败是否可恢复、权限是否最小、现有身份是否保持、文档是否与实现一致。

## 发布说明

正式版本只能从最新受保护 `main` 提交创建严格的 `vX.Y.Z` 标签，并完成[发布与回滚](docs/DEPLOYMENT.md)中的全部远端门禁。普通贡献者不需要自行创建标签或 Release。
