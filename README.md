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

安装程序会询问公网 IP/域名、端口、管理员账号和密码。密码输入不回显，也不会写入仓库或配置文件。

默认端口：

| 用途 | 监听地址 | 默认端口 |
|---|---|---:|
| Hysteria 2 | 公网 UDP | `19999` |
| 管理面板 | 公网 HTTPS TCP | `19998` |
| 流量统计 API | `127.0.0.1` | `19997` |
| Hysteria 认证回调 | `127.0.0.1` | `19996` |

服务器使用带 IP/域名 SAN 的自签名证书。浏览器首次打开面板时会显示证书警告；面板生成的 Hysteria URI 同时包含 `insecure=1` 和证书 SHA-256 固定指纹。

> 云服务器安全组也必须放行 UDP `19999` 和 TCP `19998`。脚本只会在 UFW 已启用时添加对应规则，无法代替云平台安全组配置。

## 多用户管理

登录面板后可以：

- 创建、启用、禁用和删除用户；
- 轮换用户认证密钥；
- 查看在线设备数与上传/下载流量；
- 获得可直接导入客户端的 `hysteria2://` 地址。

用户认证密钥只在创建或轮换时显示一次。数据库仅保存带服务器密钥的 HMAC 指纹，不保存认证密钥明文。禁用、删除或轮换用户时，面板会调用 Hysteria 流量 API 断开现有连接。

## 运维

```bash
systemctl status hysteria2-panel hysteria2
journalctl -u hysteria2-panel -u hysteria2 --since today
curl -k https://127.0.0.1:19998/healthz
```

关键路径：

| 路径 | 内容 |
|---|---|
| `/opt/hysteria2-panel/` | 面板程序 |
| `/etc/hysteria2-panel/` | Hysteria 配置、TLS 证书和运行环境 |
| `/var/lib/hysteria2-panel/panel.db` | 用户、会话和审计记录 |
| `/var/backups/hysteria2-panel/` | 每次覆盖部署前的时间戳备份 |

### 回滚

安装器在覆盖已有部署前会在线生成一致的 SQLite 备份，并复制应用与配置。若升级后异常：

1. 停止 `hysteria2` 和 `hysteria2-panel`；
2. 从最近的 `/var/backups/hysteria2-panel/<时间戳>/` 恢复 `opt`、`etc` 和 `panel.db`；
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
- [HTTP 接口契约](docs/API.md)

## 许可证

[MIT](LICENSE)
