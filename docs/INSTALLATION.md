# 安装与升级

这份文档面向第一次部署或升级 Hysteria2-panel 的管理员。若只想快速体验，请先看项目首页的[一分钟开始](../README.md#一分钟开始)；生产环境建议完整阅读本页。

## 部署前检查

### 服务器

- 带 systemd 的 Linux；
- `root` 或可用的 `sudo` 权限；
- Python 3.8 或更高版本；
- `apt`、`dnf` 或 `yum` 中至少一个可用；
- amd64 或 arm64 架构；
- 备份分区有足够空间保存升级前快照。

定期完整 E2E 覆盖 Ubuntu 24.04 LTS、Debian stable 和 Rocky Linux 9 的 amd64/arm64。其他兼容发行版属于尽力支持，生产部署前应先在同版本测试机验证。

### 域名和端口

准备两个概念不同的地址：

| 名称 | 用途 | 示例 |
|---|---|---|
| `PANEL_PUBLIC_HOST` | 管理员访问面板，默认申请 Let’s Encrypt HTTPS | `panel.example.com` |
| `PUBLIC_HOST` | Hysteria 用户连接节点，可由多个节点共享 DNS | `node.example.com` |

首次 HTTPS 安装前，必须把 `PANEL_PUBLIC_HOST` 的 A/AAAA 记录指向当前服务器。公网 TCP `80` 要能被 Let’s Encrypt 访问，且不能被本机其他程序占用。

云安全组至少放行：

- 面板 TCP 端口，默认 `19998`；
- Hysteria 主端口的 UDP 和兼容 TCP 探测，默认 `19999`；
- 如需账号专属入口，放行 UDP/TCP `443`；
- HTTPS 首次签发和续期所需的 TCP `80`。

安装器可以管理已启用的 UFW 或 firewalld，但无法修改云厂商安全组。检测到不明确的自定义 nftables/iptables 策略时，安装器会停止而不是猜测规则。

## 安装方式

### 跟随稳定主线

项目首页提供一行安装命令。它先把安装器保存成权限为 `0600` 的普通临时文件，再执行并在退出时删除。这个方式把 GitHub HTTPS 和受保护的 `main/install.sh` 作为首次信任入口。

不要改成 `curl … | bash` 或 `bash <(curl …)`。安装器需要从同一个普通文件在维护锁下重新执行，并会明确拒绝管道或进程替换输入。

### 固定正式版本

对供应链要求更高的环境，请使用 README 中的[固定版本验签流程](../README.md#更严格的固定版本验签安装)。它会依次检查：

1. 固定版本 Release 资产；
2. Cosign 二进制的固定 SHA-256；
3. 安装器的 GitHub Actions OIDC/Sigstore 身份；
4. 安装器 shell 语法；
5. 全部通过后才用 root 执行。

## 交互参数

安装器会询问：

- 分享链接中的节点名称；
- Hysteria 节点域名或公网 IP；
- Hysteria UDP 主端口；
- 面板 TCP 端口；
- 面板使用 HTTP 还是 HTTPS；
- HTTPS 面板的独立公网域名；
- 管理员账号和密码。

无人值守部署可使用以下环境变量：

| 变量 | 说明 |
|---|---|
| `NODE_NAME` | 分享 URI 中显示的节点名称 |
| `PUBLIC_HOST` | Hysteria 用户连接地址 |
| `HYSTERIA_PORT` | Hysteria UDP 主端口 |
| `PANEL_PORT` | 管理面板 TCP 端口 |
| `PANEL_SCHEME` | `https` 或明确接受风险后的 `http` |
| `PANEL_PUBLIC_HOST` | HTTPS 面板域名 |
| `EGRESS_POLICY` | `full` 或 `web` |
| `ADMIN_USER` | 初次安装的管理员账号 |
| `ADMIN_PASSWORD` | 初次安装的管理员密码，至少 8 个字符 |
| `RESET_ADMIN=1` | 升级时明确重置管理员 |

不要把真实密码写进 shell 历史、Git、Issue 或 CI 日志。生产环境更适合在短时 root 会话中安全注入环境变量。

## 安装器会修改什么

安装器会部署：

- 面板程序、本机 Hysteria 和 TCP 兼容探测；
- 独立的面板 TLS 与 Hysteria TLS 身份；
- systemd 服务、恢复任务、定时备份和证书续期；
- 项目专用 sudoers 白名单；
- 至少 16 MiB UDP 缓冲，以及内核支持时的 `fq`/TCP BBR；
- UFW 或 firewalld 中由本项目拥有的端口规则。

安装器不会修改云安全组、托管 DNS 或客户端配置，也不会把面板 TLS 与 Hysteria 节点证书混用。

## 重复运行与升级

在已有受管安装上重复运行安装器会进入升级流程。升级会保留：

- 管理员和数据库；
- 用户 URI、认证身份、设备与流量限制；
- HMAC、统计密钥和节点来源 ID；
- Hysteria 证书、私钥和固定指纹；
- 当前端口、面板协议和出站策略；
- 数据节点 Ed25519 身份与 durable traffic spool。

覆盖程序前，安装器会暂停面板写入、结算流量、截断 SQLite WAL、创建带 SHA-256 清单的一致性备份，并持久化可跨重启恢复的事务标记。任何步骤失败都会尝试恢复完整旧状态，而不是留下半升级服务。

### 面板内在线更新

“检查更新”只查询固定 GitHub Release 来源。“立即更新”只能启动固定的 `hysteria2-panel-update.service`，浏览器不能指定版本、URL 或命令。

更新目标在排队时固定为一个 `vX.Y.Z` 正式版本。任务会验证安装器版本、Sigstore 身份、解释器头和 shell 语法；只有任务成功结束且新进程版本达到目标值，页面才会显示成功。

### 从旧 HTTPS 安装升级

历史版本可能复用了 Hysteria 节点证书作为面板证书。此类安装必须人工运行一次安装器，补充独立的 `PANEL_PUBLIC_HOST`。在线更新会拒绝缺少该字段的旧 HTTPS 配置，避免静默延续错误的证书边界。

## 安装后验收

至少完成以下检查：

1. `systemctl is-active hysteria2-panel hysteria2-panel-server` 均为 `active`；
2. 面板 `/healthz` 与 `/readyz` 返回 HTTP 200；
3. 面板端口和 Hysteria UDP 主端口正在监听；
4. 使用真实客户端和新建测试账号完成 Hysteria 握手；
5. 获准账号可使用 UDP `443`，未获准账号会被拒绝；
6. 流量会写入用户总量与对应机器统计；
7. 下载并验证一份完整备份。

TCP `19999`/`443` 只用于兼容连通性探测，不代表真实 UDP/QUIC 数据面可用。ICMP `ping` 也不属于 Hysteria 可用性验收。

## 常见停止原因

| 现象 | 先检查什么 |
|---|---|
| HTTPS 证书申请前停止 | 面板域名是否有公网 A/AAAA、是否指向本机、TCP `80` 是否可达 |
| 防火墙检查停止 | 是否同时启用了多个管理器，或存在安装器无法证明安全的自定义规则 |
| 在线更新被拒绝 | 当前是否为受管安装、是否配置独立面板域名、是否已有维护任务运行 |
| 升级后仍显示旧版本 | 查看更新服务状态和日志，不要重复点击或手工覆盖文件 |
| 数据节点对接失败 | 确认面板 HTTPS、来源 IP、短时命令有效期和双方指纹短码 |

继续排障时请看[运维手册](OPERATIONS.md)。
