# 实施计划：面板独立 ACME/Let’s Encrypt HTTPS

## 架构决策

- 面板公网域名、TLS 证书和私钥与 Hysteria 节点身份分离。
- 使用发行版 Certbot 软件包与 standalone HTTP-01，不引入 DNS API 密钥。
- ACME 账户与证书状态放在 `/etc/hysteria2-panel/acme`，可随受管配置备份回滚。
- 续期由项目自有 systemd timer 保证，部署钩子只重启面板服务。

## 依赖顺序

面板配置合同 → 安装器输入与 ACME 签发 → 原子证书部署与续期 →
升级/回滚/防火墙合同 → 文档与全量质量门。

## 阶段 1：证书身份分离

- [x] RED：Settings 与安装器测试证明当前 HTTPS 复用节点证书。
- [x] GREEN：新增独立面板域名和面板证书配置，HTTPS 监听器只加载面板证书。

### 检查点

- [x] 定向测试通过；连接 URI 与 Hysteria 配置身份断言不变。

## 阶段 2：ACME 签发与续期

- [x] RED：覆盖域名校验、Certbot standalone 参数、独立证书部署和失败保留旧证书。
- [x] GREEN：实现 Certbot 安装、初次签发、原子部署及 systemd 续期 timer。
- [x] 把 TCP 80 纳入 HTTPS 模式受管防火墙和云安全组提示。

### 检查点

- [x] Bash 合同、语法与 ShellCheck 通过；timer 不依赖或重启 Hysteria。

## 阶段 3：升级、回滚与文档

- [x] 旧 HTTP 自动更新保持兼容；旧 HTTPS 缺少面板域名时安全拒绝自动更新。
- [x] 新增 ACME 文件和单元纳入受管路径、备份、回滚与首次安装事务。
- [x] 更新 README 与发布影响说明。

### 完成检查点

- [x] 全量单元/集成测试、Python 编译、Ruff、Bandit、Bash 与 ShellCheck 通过。
- [x] diff 安全复审确认没有节点身份写路径变化。

## 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| TCP 80 不可达或被占用 | 无法签发/续期 | 安装前检查并清晰失败；不停止未知服务 |
| Certbot 软件包不可用 | 一键 HTTPS 无法继续 | 使用系统仓库，RHEL 系缺包时由包管理器启用 EPEL；不执行远程脚本 |
| 续期后证书部署中断 | 面板证书不一致 | 同目录暂存、校验域名与密钥配对、原子替换 |
| 旧 HTTPS 升级仍复用节点证书 | 违反永久身份边界 | 缺新字段时自动更新安全拒绝，人工升级补录域名 |
| ACME 故障 | 证书临近过期 | 旧证书保持不变，timer 失败可从 journal 观测 |

## 开放问题

- 无；规格已由用户明确确认。
