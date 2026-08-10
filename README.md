# Hysteria2-panel

一个轻量、无第三方 Python 依赖的 Hysteria 2 多用户管理面板。部署脚本下载并校验官方 Hysteria 二进制，通过官方 HTTP 认证回调动态管理用户，并通过官方流量统计 API 显示在线设备和流量。

- 上游：[apernet/hysteria](https://github.com/apernet/hysteria)
- Hysteria 服务端配置：[官方文档](https://v2.hysteria.network/docs/advanced/Full-Server-Config/)
- 流量统计 API：[官方文档](https://v2.hysteria.network/docs/advanced/Traffic-Stats-API/)
- 连接 URI：[官方文档](https://v2.hysteria.network/docs/developers/URI-Scheme/)

## 一键部署

支持使用 systemd 的 Linux amd64/arm64 主机，需要 root 权限。

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Elegying/Hysteria2-panel/main/install.sh)
```

安装程序会询问分享节点名称、公网 IP/域名、Hysteria UDP 端口、面板端口与协议、管理员账号和密码。密码输入不回显，也不会写入仓库或配置文件。也可以使用 `NODE_NAME`、`PUBLIC_HOST`、`HYSTERIA_PORT`、`PANEL_PORT`、`PANEL_SCHEME`、`ADMIN_USER` 和 `ADMIN_PASSWORD` 环境变量执行无人值守部署。

默认端口：

| 用途 | 监听地址 | 默认端口 |
|---|---|---:|
| Hysteria 2 | 公网 UDP | `19999` |
| 管理面板 | 公网 HTTPS/HTTP TCP | `19998` |
| 流量统计 API | `127.0.0.1` | `19997` |
| Hysteria 认证回调 | `127.0.0.1` | `19996` |

服务器使用带 IP/域名 SAN 的自签名证书。浏览器首次打开面板时会显示证书警告；面板生成的 Hysteria URI 同时包含 `insecure=1` 和证书 SHA-256 固定指纹。

面板默认使用 HTTPS。安装时可以明确选择 HTTP；HTTP 模式不会设置 Secure Cookie 或 HSTS，但管理员密码与会话会在网络中明文传输，只应在可信网络或另有加密隧道保护时使用。

> 云服务器安全组或主机防火墙必须放行 UDP `19999` 和 TCP `19998`。为避免意外改变现有防火墙策略，脚本不会自动添加规则。

## 多用户管理

登录面板后可以：

- 创建、启用、禁用和删除用户，并设置并发连接数与总流量限制（默认 `3` 个连接、`250 GiB`）；
- 轮换用户认证密钥，一键复制可导入的连接 URI；
- 查看在线设备数、上传/下载流量、总流量进度和高流量前五用户；
- 重置单个用户或全部用户的累计流量；
- 查看服务状态、当前用户数、不活跃用户数、在线设备总数以及总上传/下载流量；
- 查看 CPU、内存、磁盘、运行时长、面板版本并检查更新；
- 在面板内启动、停止或重启项目专用 Hysteria 服务。

分享 URI 的节点名称由安装参数 `NODE_NAME` 统一设置，不再随面板中的用户名称变化。

新建或轮换的用户密钥由随机种子和服务器 HMAC key 派生，因此面板可以重新生成分享 URI，但数据库仍不保存认证密钥明文。旧版本用户保持原连接有效；由于原密钥只有不可逆指纹，需明确轮换一次后才能使用分享按钮。禁用、删除或轮换用户时，面板会调用 Hysteria 流量 API 断开现有连接。

“设备限制”依据 Hysteria 官方 `/online` API 返回的并发认证连接数执行。该接口不能识别真实硬件，同一设备的多个连接或不同设备的连接都按并发连接计数。

> Hysteria TUN 只转发 TCP/UDP，不代理 ICMP。节点能正常访问网页但系统 `ping` 超时并不表示节点故障，服务端无法通过放行 UDP 端口改变这一协议边界。

## 运维

```bash
systemctl status hysteria2-panel hysteria2-panel-server
journalctl -u hysteria2-panel -u hysteria2-panel-server --since today
curl -k https://127.0.0.1:19998/healthz
```

关键路径：

| 路径 | 内容 |
|---|---|
| `/opt/hysteria2-panel/` | 面板程序和项目专用 Hysteria 二进制 |
| `/etc/hysteria2-panel/` | Hysteria 配置、TLS 证书和运行环境 |
| `/var/lib/hysteria2-panel/panel.db` | 用户、会话和审计记录 |
| `/var/backups/hysteria2-panel/` | 每次覆盖部署前的时间戳备份 |
| `/etc/sysctl.d/99-hysteria2-panel.conf` | quic-go UDP 收发缓冲上限优化 |
| `/etc/sudoers.d/hysteria2-panel` | 仅允许面板启停/重启项目专用 Hysteria 服务 |

### 回滚

安装器在覆盖已有部署前会在线生成一致的 SQLite 备份，并复制应用与配置。若升级后异常：

1. 停止 `hysteria2-panel-server` 和 `hysteria2-panel`；
2. 从最近的 `/var/backups/hysteria2-panel/<时间戳>/` 恢复 `opt`、`etc`、`panel.db` 和两个 unit 文件；
3. 执行 `systemctl daemon-reload`；
4. 重新启动两个服务并检查健康接口和 UDP/TCP 监听。

## 本地验证

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile hysteria2_panel.py
bash -n install.sh
shellcheck install.sh
```

## 架构与接口

- [ADR-001：使用本机 HTTP 认证回调和标准库面板](docs/decisions/ADR-001-local-auth-panel.md)
- [ADR-002：可选 HTTP 面板与 QUIC UDP 优化](docs/decisions/ADR-002-panel-http-and-udp-tuning.md)
- [ADR-003：持久流量、连接限额与受限服务控制](docs/decisions/ADR-003-usage-policy-and-service-control.md)
- [HTTP 接口契约](docs/API.md)

## 许可证

[MIT](LICENSE)
