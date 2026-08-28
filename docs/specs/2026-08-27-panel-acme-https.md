# 规格：面板独立 ACME/Let’s Encrypt HTTPS

> 公开版本中的域名是示例值，不代表实际生产拓扑。

## 目标

在一键部署流程中增加面板公网域名输入。选择 HTTPS 时，安装器使用
Certbot standalone HTTP-01 为该域名申请 Let’s Encrypt 证书，并通过
systemd 定时续期。面板浏览器连接使用受信任证书，节点数据面身份保持不变。

## 已确认边界

- `HY2PANEL_PUBLIC_HOST`、`server.crt`、`server.key` 和
  `HY2PANEL_CERT_PIN` 永远只属于 Hysteria 节点身份。
- 安装、升级、签发、续期、回滚和恢复都不得改变 Hysteria 节点证书、
  `vpn.example.com`、任何用户链接或证书指纹。
- 面板域名使用独立的 `HY2PANEL_PANEL_PUBLIC_HOST`；面板 TLS 使用独立的
  `HY2PANEL_PANEL_TLS_CERT` 与 `HY2PANEL_PANEL_TLS_KEY`。
- 本次不改变用户、流量、订阅、节点 URI 或 Hysteria 服务配置语义。

## 技术栈与命令

- 运行时：Python 3.8+ 标准库、Bash、systemd、OpenSSL。
- ACME 客户端：发行版软件包提供的 Certbot；不下载或执行第三方安装脚本。
- 签发：`certbot certonly --standalone --preferred-challenges http-01 ...`。
- 续期：受管 systemd timer 调用 `certbot renew --cert-name ...`；仅在证书实际
  更新后复制面板证书并重启 `hysteria2-panel.service`。
- 定向测试：`python3 -m unittest tests.test_installer tests.test_panel -v`。
- 全量测试：`python3 -m unittest discover -s tests -v`。
- 静态检查：`bash -n install.sh tests/*.sh`、`shellcheck install.sh tests/*.sh`、
  `ruff check hysteria2_panel.py tcp_probe.py hy2panel .github/scripts tests`。

## 项目结构

- `install.sh`：交互输入、域名校验、Certbot 安装/签发、证书部署、systemd 单元、
  升级与回滚合同。
- `hysteria2_panel.py`：区分节点 TLS 与面板 TLS；HTTPS 监听器只加载面板证书。
- `tests/test_installer.py`：安装器、升级、续期和身份不可变合同。
- `tests/test_panel.py`：Settings 与 HTTPS 证书路径回归。
- `README.md`：部署前提、环境变量、续期与排障说明。

## 代码风格

沿用现有 Bash/Python 3.8 风格，输入先校验再使用，路径使用固定前缀，不把域名
拼进 shell 命令字符串：

```bash
[[ "${PANEL_PUBLIC_HOST}" =~ ^[A-Za-z0-9.-]+$ ]] || fail "面板域名无效"
certbot certonly --standalone --cert-name "${PANEL_PUBLIC_HOST}" \
  -d "${PANEL_PUBLIC_HOST}"
```

## 测试策略

- RED：先增加字符串合同和 Settings 行为测试，证明当前版本仍复用节点证书。
- GREEN：最小实现独立面板证书路径、HTTPS 域名输入、ACME 签发和续期单元。
- 回归：明确断言 Hysteria 配置仍引用 `server.crt/server.key`，URI 仍使用
  `HY2PANEL_PUBLIC_HOST` 与 `HY2PANEL_CERT_PIN`。
- 安全：拒绝 URL、通配符、路径、控制字符、单标签主机名；私钥保持 `0640`，
  续期部署先验证证书域名、证书/私钥配对，再原子替换。
- 失败：签发或续期失败时保留旧面板证书；不得触碰节点证书或重启 Hysteria。

## 边界

- 始终：HTTPS 才要求面板域名；HTTP 兼容旧配置；TCP 80 加入受管防火墙规则；
  ACME 状态保存在受管目录并纳入升级备份。
- 需要用户另行决定：TCP 80 无法公网开放时改用 DNS-01；本次不保存 DNS API
  凭据，也不实现 Cloudflare 插件。
- 永不：复用、复制、轮换、覆盖或重新签发 Hysteria 节点证书；把密钥、账户状态
  或真实凭据提交到仓库；停止或重启 Hysteria 以完成面板证书续期。

## 成功标准

1. 新安装选择 HTTPS 后会要求填写 `panel.example.com` 一类的完整域名。
2. 面板只加载独立 Let’s Encrypt 证书，浏览器不再出现自签名警告。
3. 自动续期 timer 已启用；未到期时不重启，续期成功时只重启面板。
4. HTTP 安装和既有配置保持兼容；旧 HTTPS 配置必须人工补充面板域名，不能静默
   继续复用节点证书。
5. Hysteria 节点证书、`vpn.example.com`、用户 URI 和证书指纹在所有路径中保持
   字节级/值级不变。
6. 全量测试与静态质量门通过。

## 运行前提与已知风险

- HTTP-01 首次签发与续期时，公网 TCP 80 必须到达当前服务器，且本机端口 80
  不能被其他服务占用。
- DNS 必须指向当前服务器；安装器不能替代云安全组配置。
- Let’s Encrypt、DNS 或网络故障会导致本次续期失败，但旧证书继续使用并由
  systemd/journal 记录失败。

## 开放问题

无。用户已明确选择 ACME/Let’s Encrypt，并确认节点身份永久不可变边界。
